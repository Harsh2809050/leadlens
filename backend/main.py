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


def run_research(company: str, industry: str) -> dict:
    """Full live research pipeline. Returns the complete payload."""
    sources = []
    research.set_deadline(180)  # hard budget: return what we have, never spin

    positioning = research.get_positioning(company, industry)
    if positioning.get("website"):
        sources.append(positioning["website"])

    competitors, comp_sources = research.find_competitors(company, industry)
    sources.extend(comp_sources)

    leads, lead_sources = research.find_leads(company, industry, positioning)
    sources.extend(lead_sources)

    trends = research.get_trends(company, industry)
    sources.extend(trends.get("sources", []))

    # LLM upgrade (free GROQ_API_KEY): real competitor extraction + a
    # company-specific report. Falls back to rule-based on any failure.
    if llm.available():
        try:
            serp_blob = " | ".join(
                r["title"] + " — " + r["snippet"]
                for r in research._serp_cache.get(f"{company} competitors", [])
            ) + " | ".join(f'{c["name"]}: {c["description"]}' for c in competitors)
            refined = llm.refine_competitors(company, industry, serp_blob,
                                             competitors)
            if len(refined) >= 3:
                competitors = refined
                print(f"[llm] competitors refined: "
                      f"{[c['name'] for c in competitors]}", flush=True)
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


def get_or_research(company: str, industry: str, refresh: bool = False) -> dict:
    company = (company or "").strip()
    industry = (industry or "").strip()
    if not company:
        raise HTTPException(status_code=422, detail="company is required")

    # No industry given: reuse any cached research for this company,
    # otherwise auto-detect it — the company's own website is read first
    # because it is the strongest signal of what they actually sell.
    if not industry:
        if not refresh:
            cached = db.find_by_company(company)
            if cached:
                return cached
        pos = research.get_positioning(company, "")
        industry = research.detect_industry(company, pos)

    key = db.make_key(company, industry)
    if not refresh:
        cached = db.get_cached(company, industry)
        if cached:
            return cached

    # one research run at a time per company
    with _lock_for(key):
        if not refresh:
            cached = db.get_cached(company, industry)
            if cached:
                return cached
        try:
            data = run_research(company, industry)
        except Exception:
            traceback.print_exc()
            raise HTTPException(status_code=500,
                                detail="research crashed — see server console")
        if not data["competitors"] and not data["leads"]:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Live research could not reach search engines from this "
                    "machine, and this company is not in the cache yet. "
                    "Check your network connection and try again."
                ),
            )
        db.save(company, industry, data)
        return data


@app.get("/api/search")
def api_search(company: str = Query(...), industry: str = Query(""),
               refresh: int = 0):
    return get_or_research(company, industry, refresh == 1)


@app.get("/api/competitors")
def api_competitors(company: str = Query(...), industry: str = Query(""),
                    refresh: int = 0):
    data = get_or_research(company, industry, refresh == 1)
    return {"company": data["company"], "industry": data["industry"],
            "cached": data["cached"], "competitors": data["competitors"]}


@app.get("/api/leads")
def api_leads(company: str = Query(...), industry: str = Query(""),
              refresh: int = 0):
    data = get_or_research(company, industry, refresh == 1)
    return {"company": data["company"], "industry": data["industry"],
            "cached": data["cached"], "leads": data["leads"]}


@app.get("/api/report")
def api_report(company: str = Query(...), industry: str = Query(""),
               refresh: int = 0):
    data = get_or_research(company, industry, refresh == 1)
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
