"""LeadLens API — FastAPI backend.

Endpoints:
  GET /api/search?company=&industry=&refresh=0  -> full intelligence payload
  GET /api/competitors  (same params)           -> competitors slice
  GET /api/leads                                -> leads slice
  GET /api/report                               -> report slice
  GET /api/history                              -> previously researched companies

Industry is optional everywhere — when omitted it is auto-detected from live
search results (the user only has to type a company name).
Also serves the built React frontend from ../frontend/dist at /.
"""
import os
import threading
import time
import traceback

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import db
import llm
import report as report_mod
import research

app = FastAPI(title="LeadLens", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_locks = {}
_locks_guard = threading.Lock()


def _lock_for(key):
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


TOTAL_RESEARCH_BUDGET = 240
# Per-section ceilings (seconds). A single global deadline let competitor
# verification (expensive: up to 2 web_search calls per candidate) consume
# the ENTIRE budget under degraded/rate-limited search conditions, leaving
# 0 seconds for leads/venues/individuals/trends — confirmed live: a real run
# came back with 3 good competitors but leads=[] entirely empty. Giving each
# section its own slice of whatever budget remains means one slow section
# can no longer starve every section after it.
SECTION_CAPS = {"competitors": 70, "leads": 70, "venues": 35,
                "individuals": 20, "trends": 20}


def _section_deadline(t_start, section):
    remaining = TOTAL_RESEARCH_BUDGET - (time.time() - t_start)
    research.set_deadline(max(5, min(SECTION_CAPS[section], remaining)))


def run_research(company: str, industry: str, location: str = "",
                  industry_confident: bool = True) -> dict:
    """Full live research pipeline. Returns the complete payload."""
    sources = []
    t_start = time.time()
    research.reset_run_stats()

    positioning = research.get_positioning(company, industry)
    if positioning.get("website"):
        sources.append(positioning["website"])

    # No footprint at all (no confident industry AND no real website found)
    # means we couldn't verify this company exists publicly — flag it so the
    # UI can say so honestly instead of presenting a confident-looking but
    # possibly fabricated report.
    low_confidence = not industry_confident and not positioning.get("website")

    _section_deadline(t_start, "competitors")
    competitors, comp_sources = research.find_competitors(
        company, industry, industry_confident=industry_confident)
    sources.extend(comp_sources)

    _section_deadline(t_start, "leads")
    leads, lead_sources = research.find_leads(company, industry, positioning, location)
    sources.extend(lead_sources)

    _section_deadline(t_start, "venues")
    venues, venue_sources = research.find_b2c_venues(
        company, industry, positioning, location)
    sources.extend(venue_sources)

    _section_deadline(t_start, "individuals")
    individuals, individual_sources = research.find_b2c_individuals(
        company, industry, positioning, location)
    sources.extend(individual_sources)

    leads = leads + venues + individuals

    _section_deadline(t_start, "trends")
    trends = research.get_trends(company, industry)
    sources.extend(trends.get("sources", []))

    # LLM upgrade (free GROQ_API_KEY): real competitor extraction + a
    # company-specific report. Falls back to rule-based on any failure.
    if llm.available():
        try:
            # Bug fix: this used to look up _serp_cache[f"{company} competitors"],
            # which never matched any query find_competitors actually issues
            # (e.g. "{company} top competitors") — so the LLM always got an
            # EMPTY evidence blob and had nothing real to ground on, silently
            # relying on its own training knowledge instead (against its own
            # system prompt) whenever it did manage to name real companies.
            # Pull evidence from every query find_competitors actually ran.
            comp_queries = [
                f"{company} top competitors", f"{company} alternatives {industry}",
                f"{company} vs", f"companies like {company}",
                f"{company} similar companies",
                f"top {industry} companies", f"best {industry} platforms",
            ]
            evidence_results = []
            for q in comp_queries:
                evidence_results.extend(research._serp_cache.get(q, []))
            serp_blob = " | ".join(
                r["title"] + " — " + r["snippet"] for r in evidence_results
            ) + " | ".join(f'{c["name"]}: {c["description"]}' for c in competitors)
            refined = llm.refine_competitors(company, industry, serp_blob,
                                             competitors)
            # Safety net: a mega-cap can only survive if it was already
            # independently verified via real vs-evidence above — never
            # accept one freshly introduced by the LLM.
            verified_names = {c["name"].strip().lower() for c in competitors}
            refined = [c for c in refined if not research.is_mega_cap(c["name"])
                      or c["name"].strip().lower() in verified_names]
            if len(refined) >= 3:
                competitors = refined
                print(f"[llm] competitors refined: "
                      f"{[c['name'] for c in competitors]}", flush=True)
            else:
                print(f"[llm] refine returned only {len(refined)} (<3), "
                      f"keeping rule-based competitors", flush=True)
        except Exception as e:
            print(f"[llm] competitor refine failed: {e}", flush=True)

    rep = None
    if llm.available():
        try:
            rep = llm.write_report(company, industry, competitors, leads,
                                   positioning, trends)
            print("[llm] report written by LLM", flush=True)
        except Exception as e:
            print(f"[llm] report failed, falling back: {e}", flush=True)
    if rep is None:
        rep = report_mod.build_report(company, industry, competitors, leads,
                                      positioning, trends)

    return {
        "company": company,
        "industry": industry,
        "location": location,
        "low_confidence": low_confidence,
        "degraded": research.was_rate_limited(),
        "competitors": competitors,
        "leads": leads,
        "positioning": positioning,
        "trends": {"stats": trends.get("stats", []),
                   "risks": trends.get("risks", [])},
        "report": rep,
        "sources": list(dict.fromkeys(sources))[:25],
        "cached": False,
        "researched_at": time.time(),
    }


def get_or_research(company: str, industry: str, location: str = "",
                    refresh: bool = False) -> dict:
    company = (company or "").strip()
    industry = (industry or "").strip()
    location = (location or "").strip()
    if not company:
        raise HTTPException(status_code=422, detail="company is required")

    # No industry given: reuse any cached research for this company,
    # otherwise auto-detect it — the company's own website is read first
    # because it is the strongest signal of what they actually sell.
    industry_confident = True
    if not industry:
        if not refresh:
            cached = db.find_by_company(company, location)
            if cached:
                return cached
        pos = research.get_positioning(company, "")
        industry, industry_confident = research.detect_industry(company, pos)

    key = db.make_key(company, industry, location)
    if not refresh:
        cached = db.get_cached(company, industry, location)
        if cached:
            return cached

    # one research run at a time per company
    with _lock_for(key):
        if not refresh:
            cached = db.get_cached(company, industry, location)
            if cached:
                return cached
        try:
            data = run_research(company, industry, location, industry_confident)
        except Exception:
            traceback.print_exc()
            raise HTTPException(status_code=500,
                                detail="research crashed — see server console")
        if not data["competitors"] and not data["leads"]:
            if data.get("low_confidence"):
                detail = (
                    "No public web presence could be found for this company — "
                    "it may be too new, too small, or misspelled to research."
                )
            elif data.get("degraded"):
                detail = (
                    "Search engines are rate-limiting this server right now, "
                    "so this run came back empty. This is temporary — wait a "
                    "few minutes and try again."
                )
            else:
                detail = (
                    "Live research could not reach search engines from this "
                    "machine, and this company is not in the cache yet. "
                    "Check your network connection and try again."
                )
            raise HTTPException(status_code=502, detail=detail)
        db.save(company, industry, data, location)
        return data


@app.get("/api/search")
def api_search(company: str = Query(...), industry: str = Query(""),
               location: str = Query(""), refresh: int = 0):
    return get_or_research(company, industry, location, refresh == 1)


@app.get("/api/competitors")
def api_competitors(company: str = Query(...), industry: str = Query(""),
                    location: str = Query(""), refresh: int = 0):
    data = get_or_research(company, industry, location, refresh == 1)
    return {"company": data["company"], "industry": data["industry"],
            "cached": data["cached"], "competitors": data["competitors"]}


@app.get("/api/leads")
def api_leads(company: str = Query(...), industry: str = Query(""),
              location: str = Query(""), refresh: int = 0):
    data = get_or_research(company, industry, location, refresh == 1)
    return {"company": data["company"], "industry": data["industry"],
            "cached": data["cached"], "leads": data["leads"]}


@app.get("/api/report")
def api_report(company: str = Query(...), industry: str = Query(""),
               location: str = Query(""), refresh: int = 0):
    data = get_or_research(company, industry, location, refresh == 1)
    return {"company": data["company"], "industry": data["industry"],
            "cached": data["cached"], "report": data["report"]}


@app.get("/api/history")
def api_history():
    return {"searches": db.list_searches()}


@app.get("/api/diag")
def api_diag():
    """Which search engines are reachable from this machine?"""
    return research.diagnose()


@app.get("/api/debug_serp")
def api_debug_serp(q: str = Query(...)):
    """Raw parsed search results for a query — for tuning the parsers."""
    return {"query": q, "results": research.web_search(q, 10)}


# ---- serve built frontend ------------------------------------------------
_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
else:
    @app.get("/")
    def _no_frontend():
        return {
            "app": "LeadLens API is running",
            "problem": "frontend/dist not found next to the backend folder",
            "fix": "run 'npm install && npm run build' inside the frontend folder, then restart",
        }
