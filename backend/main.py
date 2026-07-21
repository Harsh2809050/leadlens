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

import apollo_client
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


TOTAL_RESEARCH_BUDGET = 450
# Per-section ceilings (seconds). A single global deadline let competitor
# verification (expensive: up to 2 web_search calls per candidate) consume
# the ENTIRE budget under degraded/rate-limited search conditions, leaving
# 0 seconds for leads/venues/individuals/trends — confirmed live: a real run
# came back with 3 good competitors but leads=[] entirely empty. Giving each
# section its own slice of whatever budget remains means one slow section
# can no longer starve every section after it.
# competitors gets more than leads: it's the first section, so it's the one
# that pays the cost of discovering the search engines are rate-limited
# (each empty query eats a 5s backoff before the fast-fail path kicks in —
# see research.set_deadline) — a real run only got through 1 of 10
# well-ranked candidates before its 70s ran out. leads consistently returns
# 40-50 results well within 70s, so it has slack to give up.
# Raised from 240/95/60/35/20/20 now that /api/search/start + /api/search/poll
# means a slow run shows live progress instead of looking like a hard
# failure — these ceilings only ever get PAID on bad (rate-limited) days,
# since every section exits early the moment it has enough results. More
# patience on bad days costs nothing on good ones.
# Raised leads/venues/individuals to match the wider query sets added to
# research.py (more queries per section = more time needed to pay them off,
# especially on a rate-limited day when every query eats a 5s backoff).
SECTION_CAPS = {"competitors": 140, "leads": 120, "venues": 90,
                "individuals": 50, "trends": 30}


def _section_deadline(t_start, section):
    remaining = TOTAL_RESEARCH_BUDGET - (time.time() - t_start)
    research.set_deadline(max(5, min(SECTION_CAPS[section], remaining)))


def run_research(company: str, industry: str, location: str = "",
                  industry_confident: bool = True, positioning: dict = None,
                  target_domain: str = None) -> dict:
    """Full live research pipeline. Returns the complete payload.

    positioning/target_domain are pre-filled when the search was started
    from a URL (see resolve_target below) — skips the "{company} official
    website" search entirely (one fewer query, one fewer chance of picking
    the wrong company's site) and gives find_competitors a domain to
    anchor its verification against."""
    sources = []
    t_start = time.time()
    research.reset_run_stats()

    if positioning is None:
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
        company, industry, industry_confident=industry_confident,
        target_domain=target_domain)
    sources.extend(comp_sources)

    _section_deadline(t_start, "leads")
    if apollo_client.available():
        # Apollo is a real people/company database, not search-engine
        # scraping — it doesn't hit the rate-limiting or noisy-title-
        # parsing problems research.find_leads does. Preferred whenever a
        # key is configured; falls back to scraping only if Apollo errors
        # or comes back thin (e.g. a very niche role with no matches).
        roles = research.buyer_roles(industry, positioning)
        print(f"[leads] using Apollo for buyer personas: {roles}", flush=True)
        try:
            leads, lead_sources = apollo_client.find_leads(roles, location)
        except Exception as e:
            print(f"[apollo] find_leads crashed, falling back to scraping: {e}",
                  flush=True)
            leads, lead_sources = [], []
        if len(leads) < 10:
            extra, extra_sources = research.find_leads(
                company, industry, positioning, location, max_leads=60 - len(leads))
            seen_urls = {l["profile_url"] for l in leads}
            leads.extend(l for l in extra if l["profile_url"] not in seen_urls)
            lead_sources.extend(extra_sources)
    else:
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


def resolve_target(company: str, url: str):
    """Turn either a typed company name or a pasted URL into
    (company_name, positioning_or_None, target_domain_or_None).

    URL wins when given — it's the fix for "it gets confused between
    companies": a typed name like "Military" or a real company name shared
    by multiple businesses is ambiguous by construction, and every
    downstream check (industry detection, competitor verification, own-
    person exclusion) was guessing off that ambiguous text. A URL points at
    exactly one company, so resolve_from_url derives the display name,
    positioning, AND a canonical domain from the page itself — no guessing,
    and one fewer "{company} official website" search per run."""
    url = (url or "").strip()
    if url:
        name, positioning, domain = research.resolve_from_url(url)
        if not domain:
            raise HTTPException(
                status_code=422,
                detail="Couldn't reach that URL — check it's correct (e.g. "
                       "https://example.com) and try again.",
            )
        return name, positioning, domain
    return (company or "").strip(), None, None


def get_or_research(company: str, industry: str, location: str = "",
                    refresh: bool = False, url: str = "",
                    _resolved: tuple = None) -> dict:
    # _resolved lets a caller that already ran resolve_target (e.g.
    # api_search_start, which needs the resolved name before it can even
    # compute the background job's cache key) pass it straight through
    # instead of re-resolving — resolving means an extra page fetch, so
    # doing it twice per run is pure waste.
    if _resolved is not None:
        company, positioning, target_domain = _resolved
    else:
        company, positioning, target_domain = resolve_target(company, url)
    industry = (industry or "").strip()
    location = (location or "").strip()
    if not company:
        raise HTTPException(status_code=422, detail="company or url is required")

    # No industry given: reuse any cached research for this company,
    # otherwise auto-detect it — the company's own website is read first
    # because it is the strongest signal of what they actually sell (already
    # fetched above if a URL was given — no need to fetch it twice).
    industry_confident = True
    if not industry:
        if not refresh:
            cached = db.find_by_company(company, location)
            if cached:
                return cached
        pos = positioning if positioning is not None else research.get_positioning(company, "")
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
            data = run_research(company, industry, location, industry_confident,
                                positioning=positioning, target_domain=target_domain)
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
def api_search(company: str = Query(""), industry: str = Query(""),
               location: str = Query(""), refresh: int = 0,
               url: str = Query("")):
    return get_or_research(company, industry, location, refresh == 1, url=url)


# ---- async start/poll ------------------------------------------------
# A first-time (uncached) research run regularly takes 2-4 minutes once
# search engines are rate-limiting this machine (see SECTION_CAPS above).
# The synchronous /api/search endpoint holds that whole HTTP request open
# for the entire duration — a real run showed the browser getting a 502
# from an intermediary gateway/proxy well before the backend finished,
# surfacing as "Research failed" in the UI even though the research was
# still running fine underneath and cached successfully seconds later.
# /api/search/start returns almost instantly (cache hit, or "a background
# thread is now running"); the frontend polls /api/search/poll every few
# seconds instead of holding one long request open, so no single HTTP
# round-trip is ever slow enough to hit an external timeout.
_jobs = {}
_jobs_guard = threading.Lock()


def _job_key(company, location):
    return ((company or "").strip().lower(), (location or "").strip().lower())


@app.get("/api/search/start")
def api_search_start(company: str = Query(""), industry: str = Query(""),
                     location: str = Query(""), refresh: int = 0,
                     url: str = Query("")):
    location = (location or "").strip()
    industry = (industry or "").strip()
    if not (company or "").strip() and not (url or "").strip():
        raise HTTPException(status_code=422, detail="company or url is required")

    # Resolve once, here, before anything else — a URL needs a single page
    # fetch to turn into a company name, and every caller downstream
    # (cache check, job key, background worker) needs that SAME resolved
    # name, so resolving twice would double the page fetches for nothing.
    resolved = resolve_target(company, url)
    resolved_company = resolved[0]

    if not refresh:
        cached = (db.find_by_company(resolved_company, location) if not industry
                  else db.get_cached(resolved_company, industry, location))
        if cached:
            return {"status": "done", "data": cached, "company": resolved_company}

    jkey = _job_key(resolved_company, location)
    with _jobs_guard:
        existing = _jobs.get(jkey)
        if existing and existing["status"] == "running":
            return {"status": "started", "company": resolved_company}
        _jobs[jkey] = {"status": "running", "data": None, "detail": None,
                       "started_at": time.time()}

    def _worker():
        try:
            data = get_or_research(resolved_company, industry, location, refresh == 1,
                                   _resolved=resolved)
            with _jobs_guard:
                _jobs[jkey] = {"status": "done", "data": data,
                               "detail": None, "started_at": time.time()}
        except HTTPException as e:
            with _jobs_guard:
                _jobs[jkey] = {"status": "error", "data": None,
                               "detail": e.detail, "started_at": time.time()}
        except Exception as e:
            traceback.print_exc()
            with _jobs_guard:
                _jobs[jkey] = {"status": "error", "data": None,
                               "detail": str(e), "started_at": time.time()}

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started", "company": resolved_company}


@app.get("/api/search/poll")
def api_search_poll(company: str = Query(...), location: str = Query("")):
    jkey = _job_key(company, location)
    with _jobs_guard:
        job = _jobs.get(jkey)
    if not job:
        raise HTTPException(status_code=404,
                            detail="no research job found — call /api/search/start first")
    return job


@app.get("/api/competitors")
def api_competitors(company: str = Query(""), industry: str = Query(""),
                    location: str = Query(""), refresh: int = 0,
                    url: str = Query("")):
    data = get_or_research(company, industry, location, refresh == 1, url=url)
    return {"company": data["company"], "industry": data["industry"],
            "cached": data["cached"], "competitors": data["competitors"]}


@app.get("/api/leads")
def api_leads(company: str = Query(""), industry: str = Query(""),
              location: str = Query(""), refresh: int = 0,
              url: str = Query("")):
    data = get_or_research(company, industry, location, refresh == 1, url=url)
    return {"company": data["company"], "industry": data["industry"],
            "cached": data["cached"], "leads": data["leads"]}


@app.get("/api/report")
def api_report(company: str = Query(""), industry: str = Query(""),
               location: str = Query(""), refresh: int = 0,
               url: str = Query("")):
    data = get_or_research(company, industry, location, refresh == 1, url=url)
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
