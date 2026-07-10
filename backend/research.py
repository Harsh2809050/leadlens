"""LeadLens live research engine.

Primary source: real web pages — DuckDuckGo HTML SERPs with a Bing HTML
fallback, plus direct fetches of company sites and comparison articles.
No API keys required. All network failures degrade gracefully; whatever
was gathered is still returned.
"""
import os
import re
import time
import random
import unicodedata
from collections import Counter
from urllib.parse import quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

import db
import llm

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Domains / words that are never a competitor company name
NOISE_NAMES = {
    "the", "a", "an", "top", "best", "free", "new", "great", "leading",
    "company", "companies", "competitor", "competitors", "alternative",
    "alternatives", "review", "reviews", "pricing", "software", "platform",
    "tools", "tool", "guide", "list", "market", "industry", "startups",
    "inc", "llc", "ltd", "corp", "vs", "versus", "comparison", "compare",
    "what", "why", "how", "who", "when", "which", "is", "are", "in", "for",
    "and", "or", "of", "to", "with", "your", "you", "we", "our", "its",
    "g2", "capterra", "gartner", "trustradius", "crunchbase", "glassdoor",
    "indeed", "forbes", "reddit", "quora", "medium", "wikipedia", "linkedin",
    "youtube", "facebook", "twitter", "instagram", "tiktok", "google",
    "bing", "yahoo", "getapp", "softwareadvice", "sourceforge", "producthunt",
    "techcrunch", "bloomberg", "reuters", "cnbc", "statista", "similarweb",
    "zoominfo", "apollo", "owler", "craft", "cbinsights", "pitchbook",
    "features", "overview", "ranked", "rated", "updated", "ultimate",
    "complete", "definitive", "january", "february", "march", "april",
    "may", "june", "july", "august", "september", "october", "november",
    "december",
}

DIRECTORY_DOMAINS = (
    "g2.com", "capterra.com", "gartner.com", "trustradius.com",
    "crunchbase.com", "wikipedia.org", "linkedin.com", "reddit.com",
    "quora.com", "medium.com", "forbes.com", "youtube.com", "glassdoor.com",
    "indeed.com", "getapp.com", "softwareadvice.com", "sourceforge.net",
    "producthunt.com", "similarweb.com", "zoominfo.com", "owler.com",
    "craft.co", "cbinsights.com", "facebook.com", "twitter.com", "x.com",
    "bing.com", "duckduckgo.com", "yahoo.com", "google.com",
    "microsoft.com/en-us/bing", "support.microsoft.com",
)

# extra junk words that show up as fake "companies" in SERP titles
NOISE_NAMES.update({
    "download", "downloads", "learn", "explore", "videos", "video",
    "images", "image", "news", "sign", "login", "help", "support",
    "about", "contact", "home", "search", "maps", "shopping", "apps",
    "app", "store", "microsoft", "windows", "read", "see", "get",
    "try", "start", "watch", "discover", "find", "browse", "more",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
    "oct", "nov", "dec", "ux", "ui", "ai", "t.o.p", "pros", "cons",
    "pro", "con", "faq", "faqs", "web", "online", "site", "page",
    "world's", "worlds", "edtech", "fintech", "saas", "tech",
    "united", "states", "india", "america", "europe", "global",
    "funded", "funding", "startups", "startup", "sequoia", "time",
    "statista", "ranking", "rankings", "list", "lists", "guide",
    "companies", "company", "solutions", "services", "platforms",
    # Generic prose/heading fragments that survive as isolated capitalized
    # words on listicle/blog pages but are never themselves a company name
    # (surfaced by a real run against a test-prep company):
    "trust", "trusted", "where", "course", "courses", "resources",
    "resource", "tips", "tests", "test", "practice", "need", "needs",
    "every", "schools", "school", "counseling", "admissions", "admission",
    # Standardized exam/qualification names — topically relevant to a
    # test-prep search but they are exams, not competing companies.
    "sat", "act", "psat", "gre", "gmat", "mcat", "lsat", "ielts", "toefl",
    "cat", "jee", "neet", "ged", "gcse", "ap",
})


def _client():
    return httpx.Client(headers=HEADERS,
                        timeout=httpx.Timeout(12.0, connect=5.0),
                        follow_redirects=True)


def _fix_ddg_href(href):
    if "uddg=" in href:
        href = unquote(href.split("uddg=")[1].split("&")[0])
    if href.startswith("//"):
        href = "https:" + href
    return href


def _ddg_lite(query, max_results=10):
    """DuckDuckGo Lite — simplest, most bot-tolerant HTML endpoint."""
    results = []
    with _client() as c:
        r = c.post("https://lite.duckduckgo.com/lite/", data={"q": query})
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.select("a.result-link")
        snips = soup.select("td.result-snippet")
        for i, a in enumerate(links[:max_results]):
            href = _fix_ddg_href(a.get("href", ""))
            if not href.startswith("http"):
                continue
            results.append({
                "title": a.get_text(" ", strip=True),
                "url": href,
                "snippet": snips[i].get_text(" ", strip=True) if i < len(snips) else "",
            })
    return results


def _ddg_search(query, max_results=10):
    results = []
    with _client() as c:
        r = c.post("https://html.duckduckgo.com/html/", data={"q": query})
        soup = BeautifulSoup(r.text, "html.parser")
        for res in soup.select(".result"):
            a = res.select_one(".result__a")
            sn = res.select_one(".result__snippet")
            if not a:
                continue
            href = _fix_ddg_href(a.get("href", ""))
            results.append({
                "title": a.get_text(" ", strip=True),
                "url": href,
                "snippet": sn.get_text(" ", strip=True) if sn else "",
            })
            if len(results) >= max_results:
                break
    return results


def _bing_search(query, max_results=10):
    results = []
    with _client() as c:
        r = c.get(
            "https://www.bing.com/search?q=" + quote_plus(query) + "&count=10&setlang=en",
            headers={**HEADERS, "Cookie": "SRCHHPGUSR=NRSLT=10; _EDGE_CD=m=en-us"},
        )
        soup = BeautifulSoup(r.text, "html.parser")
        for li in soup.select("li.b_algo, div.b_algo"):
            a = li.select_one("h2 a") or li.select_one("a[href^='http']")
            p = li.select_one("p") or li.select_one(".b_caption")
            if not a or not a.get("href"):
                continue
            href = a["href"]
            dom = urlparse(href).netloc.lower()
            # skip bing's own redirect/internal chrome links
            if "bing.com" in dom or "microsoft.com" in dom:
                continue
            results.append({
                "title": a.get_text(" ", strip=True),
                "url": href,
                "snippet": p.get_text(" ", strip=True) if p else "",
            })
            if len(results) >= max_results:
                break
    return results


_YAHOO_BREADCRUMB = re.compile(r"^\S+\s+https?://\S+(?:\s*›\s*\S+)*\s*")


def _yahoo_search(query, max_results=10):
    results = []
    with _client() as c:
        r = c.get("https://search.yahoo.com/search?p=" + quote_plus(query))
        soup = BeautifulSoup(r.text, "html.parser")
        for d in soup.select("div.algo, li div.dd"):
            a = d.select_one("h3 a") or d.select_one("a[href]")
            if not a or not a.get("href"):
                continue
            href = a["href"]
            m = re.search(r"RU=([^/]+)/", href)  # yahoo redirect wrapper
            if m:
                href = unquote(m.group(1))
            if not href.startswith("http") or "yahoo.com" in urlparse(href).netloc:
                continue  # skip yahoo-internal nav links ("Videos", "Past day")
            title = _YAHOO_BREADCRUMB.sub("", a.get_text(" ", strip=True)).strip()
            if not title:
                title = a.get_text(" ", strip=True)
            p = d.select_one(".compText, p")
            results.append({
                "title": title,
                "url": href,
                "snippet": p.get_text(" ", strip=True) if p else "",
            })
            if len(results) >= max_results:
                break
    return results


def _generic_results(soup, max_results, skip_domains=()):
    """Tolerant SERP extraction: content links with real titles."""
    results, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            continue
        dom = urlparse(href).netloc.lower()
        if any(s in dom for s in skip_domains):
            continue
        title = a.get_text(" ", strip=True)
        if len(title) < 15 or href.split("?")[0] in seen:
            continue
        seen.add(href.split("?")[0])
        parent = a.find_parent()
        p = parent.find("p") if parent else None
        results.append({"title": title, "url": href,
                        "snippet": p.get_text(" ", strip=True) if p else ""})
        if len(results) >= max_results:
            break
    return results


def _ecosia_search(query, max_results=10):
    with _client() as c:
        r = c.get("https://www.ecosia.org/search?q=" + quote_plus(query))
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for d in soup.select("div.result, article"):
            a = d.select_one("a.result__link, a.result-title, h2 a, a[href^='http']")
            if not a or not a.get("href", "").startswith("http"):
                continue
            p = d.select_one(".result__description, .result-snippet, p")
            results.append({"title": a.get_text(" ", strip=True), "url": a["href"],
                            "snippet": p.get_text(" ", strip=True) if p else ""})
            if len(results) >= max_results:
                break
        return results or _generic_results(soup, max_results, ("ecosia.org",))


def _brave_search(query, max_results=10):
    with _client() as c:
        r = c.get("https://search.brave.com/search?q=" + quote_plus(query))
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for d in soup.select("div.snippet"):
            a = d.select_one("a[href^='http']")
            t = d.select_one(".title, .snippet-title")
            p = d.select_one(".snippet-description, .snippet-content, p")
            if not a:
                continue
            results.append({
                "title": (t or a).get_text(" ", strip=True), "url": a["href"],
                "snippet": p.get_text(" ", strip=True) if p else ""})
            if len(results) >= max_results:
                break
        return results or _generic_results(soup, max_results, ("brave.com",))


def _mojeek_search(query, max_results=10):
    with _client() as c:
        r = c.get("https://www.mojeek.com/search?q=" + quote_plus(query))
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for li in soup.select("ul.results-standard li, li.result"):
            a = li.select_one("h2 a, a.title, a[href^='http']")
            p = li.select_one("p.s, p")
            if not a or not a.get("href", "").startswith("http"):
                continue
            title = a.get_text(" ", strip=True)
            if title.startswith("http") or "›" in title:
                h2 = li.select_one("h2")
                if h2:
                    title = h2.get_text(" ", strip=True)
            if title.startswith("http") or "›" in title:
                continue  # couldn't recover a real title
            results.append({"title": title, "url": a["href"],
                            "snippet": p.get_text(" ", strip=True) if p else ""})
            if len(results) >= max_results:
                break
        return results or _generic_results(soup, max_results, ("mojeek.com",))


BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")


def _brave_api(query, max_results=10):
    """Official Brave Search API (free tier: 2,000 queries/month).
    Used automatically when BRAVE_API_KEY is set — essential on cloud
    hosts whose datacenter IPs get blocked by search engines."""
    if not BRAVE_API_KEY:
        return []
    with httpx.Client(timeout=10) as c:
        r = c.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(max_results, 20)},
            headers={"X-Subscription-Token": BRAVE_API_KEY,
                     "Accept": "application/json"},
        )
        data = r.json()
    return [
        {"title": w.get("title", ""), "url": w.get("url", ""),
         "snippet": w.get("description", "")}
        for w in data.get("web", {}).get("results", [])
    ]


# ---- free, key-less power engines ----------------------------------------
try:  # the ddgs library speaks DuckDuckGo's real protocol (vqd tokens etc.)
    from ddgs import DDGS as _DDGS_CLS
except ImportError:
    try:
        from duckduckgo_search import DDGS as _DDGS_CLS
    except ImportError:
        _DDGS_CLS = None


def _ddgs_lib(query, max_results=10):
    """DuckDuckGo via the `ddgs` library — free, no key, and far more
    reliable than raw HTML scraping because it negotiates DDG's anti-bot
    tokens the way a real client does."""
    if _DDGS_CLS is None:
        return []
    results = []
    with _DDGS_CLS() as d:
        for r in d.text(query, max_results=max_results):
            url = r.get("href") or r.get("url") or ""
            title = r.get("title", "")
            if not url.startswith("http") or not title:
                continue
            results.append({"title": title, "url": url,
                            "snippet": r.get("body", "") or r.get("description", "")})
    return results


# Public SearXNG metasearch instances with the JSON API enabled — each one
# aggregates Google/Bing/DDG server-side, for free, no key. Instances come
# and go; the per-engine circuit breaker handles dead ones automatically.
SEARXNG_INSTANCES = [
    "https://searx.be",
    "https://search.inetol.net",
    "https://searx.tiekoetter.com",
    "https://priv.au",
    "https://opnxng.com",
]


def _searxng(query, max_results=10):
    insts = list(SEARXNG_INSTANCES)
    random.shuffle(insts)
    for inst in insts[:3]:
        try:
            with _client() as c:
                r = c.get(f"{inst}/search",
                          params={"q": query, "format": "json"})
            if r.status_code != 200:
                continue
            data = r.json()
            results = []
            for x in data.get("results", [])[:max_results]:
                url = x.get("url", "")
                if not url.startswith("http"):
                    continue
                results.append({"title": x.get("title", ""), "url": url,
                                "snippet": x.get("content", "")})
            if results:
                return results
        except Exception:
            continue
    return []


ENGINES = [
    ("ddgs_lib", _ddgs_lib),
    ("ddg_lite", _ddg_lite),
    ("ddg_html", _ddg_search),
    ("bing", _bing_search),
    ("yahoo", _yahoo_search),
    ("ecosia", _ecosia_search),
    ("brave", _brave_search),
    ("mojeek", _mojeek_search),
    ("searxng", _searxng),
]
if BRAVE_API_KEY:
    ENGINES.insert(0, ("brave_api", _brave_api))


_preferred_engine = [None]  # promotes the engine that last worked
_serp_cache = {}            # query -> results, in-process — avoids repeat hits
_engine_fails = {}          # engine -> consecutive EXCEPTIONS; 3+ = skip (process lifetime)
_engine_empty_streak = {}   # engine -> consecutive EMPTY (but not erroring) results
_engine_cooldown_until = {} # engine -> unix ts until which to skip it entirely
_deadline = [None]          # time budget for the CURRENT section (see main.py)
_consecutive_empty = [0]    # queries in a row (current section) where EVERY
                            # engine returned zero results — controls the
                            # backoff-skip optimization below, resets fresh
                            # each section (see set_deadline)
_rate_limited_this_run = [False]  # sticky for the WHOLE run — surfaced to the
                            # UI as "degraded" so an empty section reads as
                            # "we got rate-limited," not "this company is fake"

EMPTY_STREAK_COOLDOWN = 300  # 5 minutes benched once an engine goes quiet


def set_deadline(seconds):
    """Cap the CURRENT SECTION: past the deadline all searches return empty
    and that section finishes with whatever it has instead of spinning
    forever. Called once per pipeline section (see main.py's
    _section_deadline) so one slow section can't starve the ones after it."""
    _deadline[0] = time.time() + seconds
    _consecutive_empty[0] = 0  # fresh judgment for this section


def reset_run_stats():
    """Call once at the very start of a full research run (not per-section):
    resets the sticky rate-limited flag surfaced to the UI as 'degraded'."""
    _consecutive_empty[0] = 0
    _rate_limited_this_run[0] = False


def was_rate_limited():
    return _rate_limited_this_run[0]


def out_of_time():
    return _deadline[0] is not None and time.time() > _deadline[0]


def web_search(query, max_results=10):
    """Search the live web, falling through engines until one returns results.
    Three layers of resilience against rate-limiting:
      1. A persistent, disk-backed cache (db.serp_cache) — once ANY run has
         successfully searched something, every future run gets it instantly
         with zero network calls, even after a restart. This is the main
         lever: the fraction of queries needing a live engine shrinks over
         time as real usage warms the cache.
      2. Per-engine cooldown — an engine that goes quiet (zero results, no
         exception — what a soft rate-limit looks like) 4 times in a row
         gets benched for 5 minutes instead of retried every single query.
      3. Same-section backoff-skip — if the last 5 queries in THIS section
         all came back empty from every engine, stop paying the 5s
         backoff-and-retry; it isn't going to start working mid-section.
    """
    if query in _serp_cache:
        return _serp_cache[query][:max_results]
    if out_of_time():
        return []
    persisted = db.get_serp(query)
    if persisted is not None:
        _serp_cache[query] = persisted
        return persisted[:max_results]

    broadly_blocked = _consecutive_empty[0] >= 5
    max_attempts = 1 if broadly_blocked else 2
    now = time.time()
    for attempt in range(1, max_attempts + 1):
        time.sleep(random.uniform(0.7, 1.2))  # polite pace beats rate limits
        order = list(ENGINES)
        if _preferred_engine[0]:
            order.sort(key=lambda e: e[0] != _preferred_engine[0])
        not_hard_failed = [(n, fn) for n, fn in order if _engine_fails.get(n, 0) < 3]
        eligible = [(n, fn) for n, fn in not_hard_failed
                   if _engine_cooldown_until.get(n, 0) <= now]
        if not eligible and not_hard_failed:
            # Every non-broken engine is in a soft cooldown at once — seen
            # live: empty-streak cooldowns benched all 7 mid-run, guaranteeing
            # every later section (venues/individuals/trends) would fail
            # regardless of query quality, since nothing was left to even
            # attempt. Trying the one closest to ready beats a guaranteed
            # empty. Engines with real repeated EXCEPTIONS stay excluded —
            # only the soft (empty-result) cooldown gets overridden here.
            eligible = sorted(not_hard_failed,
                              key=lambda e: _engine_cooldown_until.get(e[0], 0))
        for name, fn in eligible:
            try:
                res = fn(query, max_results)
            except Exception as e:
                _engine_fails[name] = _engine_fails.get(name, 0) + 1
                if _engine_fails[name] == 3:
                    print(f"[search] {name} disabled after 3 errors", flush=True)
                continue
            if res:
                _engine_fails[name] = 0
                _engine_empty_streak[name] = 0
                _preferred_engine[0] = name
                _serp_cache[query] = res
                db.save_serp(query, res)
                _consecutive_empty[0] = 0
                print(f"[search] {len(res):>2} results via {name}: {query!r}",
                      flush=True)
                return res
            _engine_empty_streak[name] = _engine_empty_streak.get(name, 0) + 1
            if _engine_empty_streak[name] >= 4:
                _engine_cooldown_until[name] = now + EMPTY_STREAK_COOLDOWN
                print(f"[search] {name} benched for {EMPTY_STREAK_COOLDOWN}s "
                      f"after {_engine_empty_streak[name]} empty results in a row",
                      flush=True)
        if attempt < max_attempts:
            if out_of_time():
                break
            print(f"[search] all engines empty for {query!r}; backing off 5s",
                  flush=True)
            time.sleep(5)
    _consecutive_empty[0] += 1
    if _consecutive_empty[0] == 5:
        _rate_limited_this_run[0] = True
        print("[search] 5 queries in a row came back empty from every engine "
              "— likely rate-limited right now; skipping retry/backoff for "
              "the rest of this section", flush=True)
    _serp_cache[query] = []
    return []


def diagnose():
    """Test every engine + raw egress so failures are visible from /api/diag."""
    out = {}
    for name, fn in ENGINES:
        t0 = time.time()
        try:
            rs = fn("notion competitors", 5)
            out[name] = {
                "ok": bool(rs),
                "results": len(rs),
                "sample": rs[0]["title"][:80] if rs else "",
                "secs": round(time.time() - t0, 1),
            }
        except Exception as e:
            out[name] = {"ok": False, "error": (type(e).__name__ + ": " + str(e))[:200]}
    try:
        with _client() as c:
            r = c.get("https://example.com")
            out["raw_egress"] = {"status": r.status_code}
    except Exception as e:
        out["raw_egress"] = {"error": (type(e).__name__ + ": " + str(e))[:200]}
    return out


def fetch_page_text(url, limit=6000):
    try:
        with _client() as c:
            r = c.get(url)
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            return soup.get_text(" ", strip=True)[:limit], soup
    except Exception:
        return "", None


# --------------------------------------------------------------------------
# Industry auto-detection (user only types a company name)
# --------------------------------------------------------------------------

# Each canonical label maps to a bucket of loose synonyms — matching the
# same "keyword bucket -> label" pattern already used successfully by
# BUYER_PERSONAS/AUDIENCE_GATEKEEPERS below. A flat list of exact phrases
# ("test prep") missed real companies that phrase it differently ("coaching
# for competitive exams", "SAT prep courses") and fell through to the
# generic "technology" placeholder — which then poisoned every downstream
# query (competitors, lead qualifiers, venue categories) with a wrong label.
INDUSTRY_TAXONOMY = [
    ("test prep", ("test prep", "exam prep", "entrance exam", "competitive exam",
                   "sat prep", "act prep", "coaching classes", "coaching institute",
                   "coaching for")),
    ("tutoring", ("tutoring", "tutor", "home tuition", "private lessons")),
    ("edtech", ("edtech", "e-learning", "elearning", "online learning",
                "online courses", "online education", "learning platform",
                "learning app")),
    ("language learning", ("language learning", "learn a language", "language app")),
    ("productivity software", ("productivity app", "productivity tool", "task management",
                              "note-taking", "notes app", "workspace app")),
    ("project management software", ("project management", "kanban", "sprint planning")),
    ("developer tools", ("developer tools", "api platform", "sdk", "devops platform")),
    ("cybersecurity", ("cybersecurity", "cyber security", "infosec", "threat detection")),
    ("cloud computing", ("cloud computing", "cloud infrastructure", "cloud platform")),
    ("artificial intelligence", ("artificial intelligence", "machine learning",
                                "generative ai", "ai model", "ai platform")),
    ("data analytics", ("data analytics", "business intelligence", "data platform")),
    ("marketing software", ("marketing software", "marketing automation", "seo tool")),
    ("hr software", ("hr software", "human resources platform", "payroll software")),
    ("crm software", ("crm platform", "customer relationship management")),
    ("e-commerce", ("e-commerce", "ecommerce", "online store", "online shopping",
                    "online marketplace")),
    ("fintech", ("fintech", "digital payments", "neobank", "financial technology",
                "payment gateway")),
    ("banking", ("banking", "bank account", "digital bank")),
    ("insurance technology", ("insurtech", "insurance technology", "digital insurance")),
    ("healthcare technology", ("healthtech", "healthcare technology", "digital health",
                              "telemedicine")),
    ("biotechnology", ("biotech", "biotechnology", "life sciences")),
    ("pharmaceuticals", ("pharmaceutical", "pharma company", "drug development")),
    ("food delivery", ("food delivery", "food ordering app")),
    ("ride hailing", ("ride hailing", "ride-sharing", "ride sharing", "cab booking")),
    ("travel technology", ("travel booking", "travel technology", "trip planning app")),
    ("hospitality", ("hospitality", "hotel booking", "hotel management")),
    ("streaming media", ("streaming service", "video on demand", "ott platform")),
    ("social media", ("social media", "social network", "social app")),
    ("gaming", ("gaming studio", "video game", "game studio", "mobile game")),
    ("consumer electronics", ("consumer electronics", "smart devices")),
    ("electric vehicles", ("electric vehicle", "ev maker", "ev startup")),
    ("automotive", ("automotive", "car manufacturer", "vehicle manufacturer")),
    ("logistics", ("logistics", "supply chain", "freight", "fleet management")),
    ("real estate technology", ("proptech", "real estate platform", "property listing")),
    ("retail", ("retail chain", "retail store", "retailer")),
    ("fashion", ("fashion brand", "apparel brand", "clothing brand")),
    ("food and beverage", ("food and beverage", "restaurant chain", "beverage brand")),
    ("energy", ("energy company", "renewable energy", "solar energy")),
    ("telecommunications", ("telecom operator", "telecommunications", "mobile network operator")),
    ("saas", ("saas platform", "software as a service", "b2b software")),
]


def _keyword_score(blob, synonyms):
    score = 0
    for syn in synonyms:
        if " " in syn or len(syn) > 5:
            score += blob.count(syn)
        else:
            score += len(re.findall(r"\b" + re.escape(syn) + r"\b", blob))
    return score


def _best_industry_match(blob):
    """Highest-scoring taxonomy label for a blob of text, or (None, 0)."""
    scored = [(label, _keyword_score(blob, syns)) for label, syns in INDUSTRY_TAXONOMY]
    best_label, best_score = max(scored, key=lambda x: x[1])
    return (best_label, best_score) if best_score > 0 else (None, 0)

_IND_PAT = re.compile(
    r"industr(?:y|ies)\s*[:\-–]\s*([A-Za-z &/]{3,40})", re.I)


_IS_A_PAT = re.compile(
    r"\bis an? ([a-z][a-z ,/&\-]{4,70}?)(?:\.|,| that| which| developed| founded|"
    r" headquartered| based| owned| primarily| used )", re.I)


def detect_industry(company, positioning=None):
    """Work out what industry a company is in. Returns (industry, confident).
    The company's OWN website copy is the strongest signal — check it before
    anything from search results. `confident=False` means no real signal was
    found anywhere (rule-based or LLM) — callers must NOT treat the returned
    label as a real category to search against (see find_competitors), only
    as a harmless display placeholder."""
    positioning = positioning or {}
    own = " ".join(str(positioning.get(k, "")) for k in
                   ("tagline", "description", "h1")).lower()
    own_best, own_score = _best_industry_match(own)
    if own_best:
        return own_best, True

    # The company's own copy often phrases it in free text instead of one of
    # our known-category keywords ("We help teams plan sprints faster") —
    # try the same anchored "X is a ..." extraction against it before
    # spending any network calls, since it's already fetched and it's the
    # single best signal of what the company actually does.
    own_anchored = re.compile(
        r"\bis an? ([a-z][a-z ,/&\-]{4,70}?)"
        r"(?:\.|,| that| which| developed| founded| headquartered| based|"
        r" owned| primarily| used |$)", re.I)
    m = own_anchored.search(own)
    if m:
        phrase = re.sub(r"\s+", " ", m.group(1)).strip(" -,.")
        if 4 <= len(phrase) <= 60:
            tail = phrase.split(" for ")[-1].strip()
            cand = tail if 4 <= len(tail) <= 40 else phrase
            if len(cand) > 40:
                cand = cand[:40].rsplit(" ", 1)[0]
            if len(cand) >= 4:
                return cand, True

    rs = web_search(f"{company} wikipedia company", 6)
    rs += web_search(f"{company} company profile industry", 6)
    text = " ".join((r["title"] + " " + r["snippet"]) for r in rs).lower()

    best, best_score = _best_industry_match(text)
    if best_score > 1:
        return best, True

    # "Figma is a collaborative web application for interface design..."
    # anchored to the company name so a stray "Wikipedia is a free online
    # encyclopedia" snippet can never hijack the industry
    anchored = re.compile(
        re.escape(company) + r"[^.]{0,50}?\bis an? ([a-z][a-z ,/&\-]{4,70}?)"
        r"(?:\.|,| that| which| developed| founded| headquartered| based|"
        r" owned| primarily| used )", re.I)
    for r in rs:
        m = anchored.search(r["title"] + ". " + r["snippet"])
        if m:
            phrase = m.group(1).strip().lower()
            # never echo the company's own name inside its industry label
            phrase = phrase.replace(company.lower(), " ")
            phrase = re.sub(r"^(?:(?:american|indian|british|german|french|"
                            r"chinese|japanese|multinational|global|leading|"
                            r"popular|proprietary|free|online|web.based|the)"
                            r"\s+)+", "", phrase)
            phrase = re.sub(r"\s+", " ", phrase).strip(" -,.")
            if 4 <= len(phrase) <= 60:
                # prefer what comes after "for" ("web application for interface design")
                tail = phrase.split(" for ")[-1].strip()
                cand = tail if 4 <= len(tail) <= 40 else phrase
                if len(cand) > 40:  # cut at a word boundary, never mid-word
                    cand = cand[:40].rsplit(" ", 1)[0]
                if len(cand) >= 4:
                    return cand, True

    if best_score > 0:
        return best, True
    m = _IND_PAT.search(" ".join(r["snippet"] for r in rs))
    if m:
        return m.group(1).strip().lower(), True

    # No rule-based signal at all. Try the LLM as a last resort — it can
    # recognize real but obscure companies keyword-counting can't, and will
    # honestly report "not confident" for made-up ones instead of us
    # silently defaulting to a generic bucket like "technology" (which is
    # exactly what caused fake FAANG "competitors" to show up for unknown
    # companies — see find_competitors' category fallback).
    if llm.available():
        try:
            guess, confident = llm.detect_industry(company, positioning, text)
            if guess:
                return guess, confident
        except Exception:
            pass

    return "technology", False


# --------------------------------------------------------------------------
# Competitor discovery
# --------------------------------------------------------------------------

# Mega-caps only ever count as a competitor when real head-to-head evidence
# names them (require_vs=True) — never through the loose category fallback,
# which is how "Apple / Alphabet / AMD" leaked in as fake competitors for
# small or made-up companies whose industry couldn't be confidently detected.
MEGA_CAPS = {
    "apple", "google", "alphabet", "microsoft", "amazon", "meta", "facebook",
    "samsung", "sony", "netflix", "nvidia", "tesla", "ibm", "oracle", "intel",
    "amd", "salesforce", "adobe", "sap",
}


def is_mega_cap(name):
    return (name or "").strip().lower() in MEGA_CAPS


_CAP_NAME = re.compile(r"\b([A-Z][A-Za-z0-9&.']+(?:[ \-][A-Z][A-Za-z0-9&.']+){0,2})\b")
_LIST_CUE = re.compile(
    r"(?:like|such as|including|includes?|alternatives?(?:\s+(?:to\s+\S+|are|:))?|"
    r"competitors?(?:\s+(?:of\s+\S+|are|include|:))?)\s+([A-Z][^.;!?]{5,120})")
_VS = re.compile(r"(?:\bvs\.?\s+|\bversus\s+)([A-Z][A-Za-z0-9&.'\-]+(?:\s[A-Z][A-Za-z0-9&.'\-]+)?)")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s*([A-Z][A-Za-z0-9&.' \-]{1,40})$")


def _clean_candidate(name, company):
    name = re.sub(r"[|:,–—-]+$", "", name).strip(" .,'\"")
    if not name or len(name) < 2 or len(name) > 40:
        return None
    low = name.lower()
    if low == company.lower() or company.lower() in low or low in company.lower():
        return None
    words = low.split()
    if len(words) > 4:
        return None
    # ANY junk token disqualifies: kills "World's Top EdTech", "United States".
    # NB: strip a trailing possessive ('s / 's) with a targeted regex, not
    # str.strip(".'’s") — that treats the argument as a CHARACTER SET and
    # strips 's' from both ends of ANY word, silently mangling "services"
    # into "ervice" and "solutions" into "olution" so they'd never match
    # the (correctly spelled, plural) NOISE_NAMES entries. That single bug
    # is why generic words like "Services" were leaking through as if they
    # were real competitor names.
    def _norm_word(w):
        return re.sub(r"[’']s$", "", w).strip(".,'’\"")
    if any(_norm_word(w) in NOISE_NAMES for w in words):
        return None
    if any(ch.isdigit() for ch in name) and not re.match(r"^[A-Za-z]+\d+$", name):
        return None
    return name


def _mine_candidates(texts, company):
    """Frequency-vote capitalized entities across many independent sources."""
    votes = Counter()
    for weight, text in texts:
        seen_in_text = set()
        for m in _VS.finditer(text):
            c = _clean_candidate(m.group(1), company)
            if c:
                seen_in_text.add((c, weight + 2))
        for m in _CAP_NAME.finditer(text):
            c = _clean_candidate(m.group(1), company)
            if c:
                seen_in_text.add((c, weight))
        for c, w in seen_in_text:
            votes[c] += w
    # merge case-variants / near-duplicates (e.g. "Hubspot" vs "HubSpot")
    merged = {}
    for name, score in votes.most_common():
        key = name.lower().replace(" ", "")
        if key in merged:
            merged[key] = (merged[key][0], merged[key][1] + score)
        else:
            merged[key] = (name, score)
    return sorted(merged.values(), key=lambda x: -x[1])


def find_competitors(company, industry, max_competitors=8, progress=None,
                      industry_confident=True):
    # Kept to 5 queries (trimmed from 7) — each web_search costs real time
    # and is exposed to rate-limiting, so redundant phrasings were cut.
    queries = [
        f"{company} top competitors",
        f"{company} alternatives {industry}",
        f"{company} vs",
        # Company-anchored, industry-agnostic: these find real competitors
        # for niche/local businesses whose industry doesn't cleanly match a
        # known category, WITHOUT the risk of the generic category fallback
        # below (pulling unrelated big names) — a fictitious company simply
        # won't have any real pages using these phrases either.
        f"companies like {company}",
        f"{company} similar companies",
    ]
    serp_results = []
    texts = []  # STRUCTURED evidence only — no loose words from headlines
    for q in queries:
        rs = web_search(q, 10)
        serp_results.extend(rs)
        for r in rs:
            blob = r["title"] + ". " + r["snippet"]
            for m in _VS.finditer(blob):              # "X vs Figma"
                texts.append((3, m.group(1)))
            for m in _LIST_CUE.finditer(blob):        # "like A, B and C"
                for part in re.split(r",|\band\b|&", m.group(1)):
                    part = part.strip()
                    if part:
                        texts.append((2, part))

    # Pull headings from the most promising comparison articles — the
    # highest-quality source: list items on "alternatives" pages ARE names
    fetched = 0
    for r in serp_results:
        dom = urlparse(r["url"]).netloc.lower()
        if fetched >= 3 or out_of_time():
            break
        if any(d in dom for d in ("linkedin.com", "youtube.com", "reddit.com")):
            continue
        if "competitor" in (r["title"] + r["url"]).lower() or "alternative" in (r["title"] + r["url"]).lower():
            text, soup = fetch_page_text(r["url"])
            if soup is not None:
                for h in soup.select("h2, h3"):
                    line = h.get_text(" ", strip=True)
                    m = _NUMBERED.match(line)
                    cand = m.group(1) if m else line
                    texts.append((3, cand))
                fetched += 1

    ranked = _mine_candidates(texts, company)
    # keep only candidates seen with meaningful support
    # Buffer trimmed from +4 to +2 — each extra candidate costs up to 2 more
    # web_search calls in verify_competitor, real time exposed to rate limits.
    ranked = [(n, s) for n, s in ranked if s >= 3][: max_competitors + 2]
    print(f"[competitors] candidates: {[(n, s) for n, s in ranked]}", flush=True)

    competitors = []
    for name, score in ranked:
        if len(competitors) >= max_competitors or out_of_time():
            break
        verified, desc, website = verify_competitor(name, company, industry)
        print(f"[verify] {name}: {'OK' if verified else 'dropped'}", flush=True)
        if not verified:
            continue
        competitors.append({
            "name": name,
            "description": desc,
            "website": website,
            "confidence": min(99, 55 + score * 3),
        })

    # Small/unknown company fallback: no head-to-head pages exist on the web,
    # so pull the leading players of the same industry as the competitive set.
    # Only safe to do this when the industry itself is a confident, real
    # signal — otherwise (e.g. a made-up company defaulting to generic
    # "technology") this pulls category giants like Apple/Alphabet as fake
    # "competitors" for a company that may not even exist.
    if len(competitors) < 3 and not out_of_time() and industry_confident:
        print(f"[competitors] falling back to category search for {industry}",
              flush=True)
        rs = web_search(f"top {industry} companies", 8)
        rs += web_search(f"best {industry} platforms", 6)
        # mine the list-article PAGES (headings = names), not their headlines
        cat_texts = []
        cat_fetched = 0
        for r in rs:
            if cat_fetched >= 3 or out_of_time():
                break
            dom = urlparse(r["url"]).netloc.lower()
            if any(d in dom for d in ("linkedin.com", "youtube.com", "reddit.com")):
                continue
            _, soup = fetch_page_text(r["url"])
            if soup is None:
                continue
            for h in soup.select("h2, h3"):
                line = h.get_text(" ", strip=True)
                m = _NUMBERED.match(line)
                cat_texts.append((3, m.group(1) if m else line))
            cat_fetched += 1
        seen = {c["name"].lower() for c in competitors}
        for name, score in _mine_candidates(cat_texts, company):
            if len(competitors) >= max_competitors or out_of_time():
                break
            if score < 3 or name.lower() in seen:
                continue
            verified, desc, website = verify_competitor(
                name, company, industry, require_vs=False)
            print(f"[verify/cat] {name}: {'OK' if verified else 'dropped'}",
                  flush=True)
            if verified:
                seen.add(name.lower())
                competitors.append({
                    "name": name, "description": desc, "website": website,
                    "confidence": min(90, 45 + score * 3),
                })
    return competitors, [r["url"] for r in serp_results[:12]]


_COMPANYISH = re.compile(
    r"\b(compan|software|platform|app\b|application|tool|startup|founded|"
    r"design|saas|cloud|service|product|enterprise|workspace|collaborat)", re.I)


def _same_domain(desc, industry, company):
    """The candidate's description must actually mention the industry (or the
    target company). Kills cross-domain junk like a 3D render engine showing
    up as a food-delivery competitor."""
    d = desc.lower()
    if company.lower() in d:
        return True
    toks = [t for t in re.split(r"[^a-z]+", industry.lower()) if len(t) > 3]
    return any(t[:6] in d for t in toks) if toks else True


def verify_competitor(name, company, industry, require_vs=True):
    """A candidate only counts if the live web shows real head-to-head
    evidence: a '<name> vs <company>' title or an 'alternative to <company>'
    context — AND its description matches the industry. With require_vs=False
    (category fallback for small companies) the industry match alone decides."""
    nl, cl = name.lower(), company.lower()
    if not require_vs and is_mega_cap(name):
        return False, "", ""
    vs_pat = re.compile(
        r"(?:{n}.{{0,30}}\b(?:vs|versus)\b\.?.{{0,30}}{c}|"
        r"{c}.{{0,30}}\b(?:vs|versus)\b\.?.{{0,30}}{n})"
        .format(n=re.escape(nl), c=re.escape(cl)))

    verified = False
    rs = web_search(f"{name} vs {company}", 6)
    # sub-brand guard: "Swiggy Instamart" style phrases mean the candidate
    # is the target's own product line, not a competitor
    combo_hits = sum(
        1 for r in rs
        if f"{cl} {nl}" in (r["title"] + " " + r["snippet"]).lower())
    if combo_hits >= 2:
        return False, "", ""
    for r in rs:
        t = (r["title"] + " " + r["url"]).lower()
        if vs_pat.search(t):
            verified = True
            break
        s = r["snippet"].lower()
        if nl in t and (f"alternative to {cl}" in s or f"{cl} alternative" in s):
            verified = True
            break
    if require_vs and not verified:
        return False, "", ""

    # get a description + website from an independent query
    rs2 = web_search(f'"{name}" {industry} company', 6)
    desc, website = "", ""
    slug = re.sub(r"[^a-z0-9]", "", nl)
    def _clean_snip(s):
        s = s.strip()
        if s.startswith("http") or "›" in s[:80]:
            return ""  # SERP breadcrumb, not a real description
        return s

    for r in rs2:
        dom = urlparse(r["url"]).netloc.lower().replace("www.", "")
        if nl in r["title"].lower() and r["snippet"]:
            snip = _clean_snip(r["snippet"])
            if not desc and len(snip) > 60 and _COMPANYISH.search(snip):
                desc = snip[:260].rsplit(" ", 1)[0]
            if not website and not any(d in dom for d in DIRECTORY_DOMAINS):
                dom_slug = dom.replace("-", "").replace(".", "")
                # require_vs=False (category fallback) has no real
                # head-to-head evidence at all, so a coincidental substring
                # match is dangerously easy to satisfy — a real run had
                # "Erik" (a testimonial's first name, 4 letters) match some
                # unrelated domain that happened to contain "erik" anywhere.
                # Require the domain to actually START WITH a substantial
                # slice of the name, and don't even try for short/common
                # names where a coincidence is likely.
                slug_match = (
                    dom_slug.startswith(slug[:10]) if not require_vs and len(slug) >= 5
                    else slug[:6] in dom_slug if require_vs
                    else False
                )
                if slug_match:
                    website = "https://" + dom
    if not desc:
        for r in rs + rs2:  # fall back to the vs-page snippet
            snip = _clean_snip(r["snippet"])
            if nl in r["title"].lower() and len(snip) > 60:
                desc = snip[:260].rsplit(" ", 1)[0]
                break
    if desc and not website and require_vs:
        # Loose "pick any non-directory domain" fallback — acceptable only
        # when require_vs already gave us strong head-to-head evidence.
        for r in rs2:
            dom = urlparse(r["url"]).netloc.lower().replace("www.", "")
            if not any(d in dom for d in DIRECTORY_DOMAINS):
                website = "https://" + dom
                break
    if require_vs:
        ok = bool(desc) and _same_domain(desc, industry, company)
    else:
        # Category fallback has no real head-to-head evidence at all — a
        # description "matching the industry" is trivially true for almost
        # any industry-relevant noun (an exam name like "MCAT", a generic
        # word like "Trust"/"Services"), which is exactly how those leaked
        # in as fake "competitors". Also require an actual matching website
        # domain: real companies almost always have one; generic words and
        # exam acronyms essentially never do.
        ok = bool(desc) and bool(website) and _same_domain(desc, industry, company)
    return ok, desc, website


# --------------------------------------------------------------------------
# Lead discovery — PROSPECTIVE CLIENTS, not company insiders.
# We infer who would BUY this product (buyer personas from the industry and
# the company's own positioning), then find real people worldwide holding
# those roles on LinkedIn. Small business owner or enterprise head — anyone
# whose job matches the product's customer profile.
# --------------------------------------------------------------------------

BUYER_PERSONAS = [
    (("education", "edtech", "campus", "college", "university", "school",
      "student", "placement", "admission"),
     ["Training and Placement Officer", "College Principal",
      "Director of Admissions", "Dean of Students", "Head of Academics"]),
    (("food delivery", "restaurant", "food and beverage", "kitchen"),
     ["Restaurant Owner", "F&B Manager", "Cloud Kitchen Founder",
      "Restaurant Operations Manager"]),
    (("productivity", "project management", "collaboration", "workspace",
      "saas", "crm"),
     ["Head of Operations", "Chief of Staff", "IT Manager",
      "Program Manager", "Operations Director"]),
    (("design", "interface", "creative", "prototyp"),
     ["Head of Design", "Creative Director", "UX Manager",
      "Product Design Lead"]),
    (("fintech", "payment", "banking", "brokerage", "trading", "invest",
      "insurance"),
     ["CFO", "Finance Manager", "Head of Treasury", "Wealth Manager"]),
    (("marketing", "seo", "advertis", "social media", "brand"),
     ["Head of Marketing", "CMO", "Growth Manager",
      "Digital Marketing Manager"]),
    (("logistics", "supply chain", "delivery", "freight", "fleet"),
     ["Supply Chain Manager", "Head of Logistics", "Fleet Manager",
      "Warehouse Operations Manager"]),
    (("health", "medical", "pharma", "biotech", "clinic", "hospital"),
     ["Hospital Administrator", "Medical Director", "Clinic Owner",
      "Head of Procurement Healthcare"]),
    (("retail", "ecommerce", "e-commerce", "commerce", "store"),
     ["Ecommerce Manager", "Retail Store Owner", "Head of Merchandising",
      "Category Manager"]),
    (("cyber", "security", "cloud", "devops", "developer"),
     ["CISO", "IT Director", "Head of Engineering", "DevOps Lead"]),
    (("real estate", "property", "construction"),
     ["Real Estate Broker", "Property Manager", "Head of Leasing"]),
    (("travel", "hotel", "hospitality", "tourism"),
     ["Hotel General Manager", "Travel Agency Owner",
      "Head of Revenue Management"]),
    (("hr", "recruit", "talent", "hiring", "people"),
     ["HR Director", "Talent Acquisition Manager", "Head of People"]),
]

GENERIC_BUYERS = ["Head of Operations", "Procurement Manager",
                  "Business Owner", "Managing Director"]

# GATEKEEPERS: people in DAILY contact with the product's END USERS — the
# professor who tells students about a study-abroad platform, the chef who
# picks the delivery apps, the GP who recommends the health app. They don't
# sign the cheque, but they make or break adoption.
AUDIENCE_GATEKEEPERS = [
    (("student", "education", "edtech", "test prep", "study abroad",
      "tutoring", "college", "university", "exam", "campus", "school",
      "learning", "sat", "ielts", "admission"),
     ["Professor", "School Teacher", "Career Counselor",
      "Study Abroad Consultant", "Coaching Institute Director",
      "Student Activities Coordinator"]),
    (("food delivery", "restaurant", "dining", "food and beverage"),
     ["Chef", "Food Blogger", "Restaurant Consultant", "Food Court Manager"]),
    (("health", "clinic", "patient", "pharma", "medical", "wellness"),
     ["General Practitioner", "Pharmacist", "Physiotherapist", "Nutritionist"]),
    (("developer", "devops", "cloud", "software", "saas", "api"),
     ["Developer Advocate", "Tech Community Organizer", "Bootcamp Instructor",
      "Engineering Mentor"]),
    (("travel", "hotel", "tourism", "trip"),
     ["Travel Agent", "Tour Guide", "Hotel Concierge", "Travel Blogger"]),
    (("invest", "trading", "brokerage", "fintech", "banking", "insurance"),
     ["Financial Advisor", "Chartered Accountant", "Wealth Manager",
      "Insurance Agent"]),
    (("design", "creative", "prototyp"),
     ["Design Educator", "Design Community Organizer", "Freelance Designer"]),
    (("marketing", "brand", "seo", "advertis"),
     ["Marketing Consultant", "Agency Owner", "Brand Strategist"]),
    (("fitness", "gym", "sport"),
     ["Personal Trainer", "Gym Owner", "Sports Coach"]),
]

GENERIC_GATEKEEPERS = ["Industry Consultant", "Community Manager",
                       "Trade Association Director"]


def gatekeeper_roles(industry, positioning):
    """Who talks to this product's end users every single day?"""
    blob = (industry + " " + positioning.get("description", "") + " " +
            positioning.get("tagline", "") + " " +
            positioning.get("h1", "")).lower()
    roles = []
    for keys, gk_roles in AUDIENCE_GATEKEEPERS:
        if any(k in blob for k in keys):
            roles.extend(r for r in gk_roles if r not in roles)
        if len(roles) >= 6:
            break
    return roles[:6] if roles else GENERIC_GATEKEEPERS


def buyer_roles(industry, positioning):
    """Which job titles are likely BUYERS of this company's product?"""
    blob = (industry + " " + positioning.get("description", "") + " " +
            positioning.get("tagline", "") + " " +
            positioning.get("h1", "")).lower()
    roles = []
    for keys, persona_roles in BUYER_PERSONAS:
        if any(k in blob for k in keys):
            roles.extend(r for r in persona_roles if r not in roles)
        if len(roles) >= 6:
            break
    return roles[:6] if roles else GENERIC_BUYERS

_LI_TITLE_SPLIT = re.compile(r"\s+[-–—|]\s+")


_LI_URL = re.compile(r"https?://[a-z]{0,3}\.?linkedin\.com/in/[A-Za-z0-9\-_%.]+")

_BAD_LEAD_NAMES = {"sign in", "log in", "login", "linkedin", "join linkedin",
                   "sign up", "join now"}
_ROLE_WORDS_IN_NAME = re.compile(
    r"\b(officer|principal|director|admissions?|training|placement|manager|"
    r"head|dean|professor|recruiter)\b", re.I)


def _parse_linkedin_result(r, company_hint):
    m = _LI_URL.search(r["url"]) or _LI_URL.search(unquote(r["url"]))
    if not m:
        return None
    url = m.group(0)
    # normalize country subdomains so in./au./www. duplicates collapse
    url = re.sub(r"https?://[a-z]{0,3}\.?linkedin\.com", "https://www.linkedin.com", url)
    parts = _LI_TITLE_SPLIT.split(r["title"].replace(" | LinkedIn", "").replace(" - LinkedIn", ""))
    parts = [p.strip() for p in parts if p.strip() and p.strip().lower() != "linkedin"]
    if not parts:
        return None
    name = parts[0]
    if len(name) > 45 or len(name.split()) > 4 or not re.match(r"^[A-Z]", name):
        return None
    if name.lower() in _BAD_LEAD_NAMES or _ROLE_WORDS_IN_NAME.search(name):
        return None  # page chrome or a job title masquerading as a person
    role = parts[1] if len(parts) > 1 else ""
    company = company_hint
    # titles are often "Name - Role at Company"
    m = re.search(r"(.+?)\s+(?:at|@)\s+(.+)", role)
    if m:
        role, company = m.group(1).strip(), m.group(2).strip()
    return {
        "name": name,
        "role": role[:80],
        "company": company[:60],
        "linkedin_url": url.split("?")[0],
        "snippet": r["snippet"][:200],
    }


def find_leads(company, industry, positioning, location="", max_leads=50):
    """Prospective CLIENTS worldwide: real people whose job title matches
    the buyer personas for this product — the people an outbound motion
    would actually pitch. Targets 50 contacts across personas.

    Every query variant is anchored to industry and/or location — a bare
    "{role} linkedin profile" query with no qualifier returns the exact same
    people for any two searches that share a generic fallback persona, which
    is why leads used to look identical across unrelated companies."""
    roles = buyer_roles(industry, positioning)
    print(f"[leads] buyer personas: {roles}", flush=True)
    leads, seen, sources = [], set(), []
    ind_short = " ".join(industry.split()[:2])
    loc_q = f" {location}" if location else ""
    per_role = max(6, max_leads // max(len(roles), 1) + 2)
    for role in roles:
        if len(leads) >= max_leads or out_of_time():
            break
        # Trimmed from 4 to 3 variants — the dropped one duplicated ground
        # already covered by the first, more precise site: query.
        queries = [
            f'site:linkedin.com/in "{role}" {ind_short}{loc_q}',
            f'site:linkedin.com/in "{role}"{loc_q or " " + ind_short}',
            f'"{role}"{loc_q} {ind_short} linkedin profile',
        ]
        got_for_role = 0
        for q in queries:
            if got_for_role >= per_role or len(leads) >= max_leads:
                break
            for r in web_search(q, 10):
                if got_for_role >= per_role or len(leads) >= max_leads:
                    break
                lead = _parse_linkedin_result(r, "")
                if not lead or lead["linkedin_url"] in seen:
                    continue
                # their own employer parsed from the LinkedIn title
                if not lead["company"]:
                    lead["company"] = "—"
                lead["persona"] = role
                lead["segment"] = "b2b"
                lead["lead_type"] = "decision_maker"
                seen.add(lead["linkedin_url"])
                leads.append(lead)
                sources.append(lead["linkedin_url"])
                got_for_role += 1
    return leads, sources


# --------------------------------------------------------------------------
# B2C reach — real people don't buy through a procurement process the way
# organizations do. Two kinds of B2C lead:
#   1. VENUES: public businesses the target audience physically visits
#      (coaching institutes, cafes, gyms, gamezones...) — outreach targets
#      for partnerships/promos/ads, not private individuals.
#   2. INDIVIDUALS: public creators/community accounts that self-publish a
#      contact (an Instagram/YouTube bio email) — kept strictly best-effort
#      and public-only; nothing here is scraped private contact data.
# --------------------------------------------------------------------------

CONSUMER_VENUES = [
    (("student", "education", "edtech", "test prep", "study abroad",
      "tutoring", "college", "university", "exam", "campus", "school",
      "learning", "admission"),
     ["Coaching Institute", "Cafe near college", "Gaming Zone", "Bookstore",
      "Hostel"]),
    (("food delivery", "restaurant", "dining", "food and beverage",
      "cloud kitchen"),
     ["Restaurant", "Cafe", "Cloud Kitchen", "Food Court"]),
    (("fitness", "gym", "sport", "wellness"),
     ["Gym", "Sports Academy", "Yoga Studio", "Nutrition Store"]),
    (("fintech", "payment", "banking", "invest", "insurance", "trading"),
     ["Co-working Space", "Business Networking Club"]),
    (("travel", "hotel", "tourism", "trip"),
     ["Travel Agency", "Tour Operator", "Backpacker Hostel"]),
    (("gaming", "esports"),
     ["Gaming Cafe", "Esports Arena", "Gaming Zone"]),
    (("retail", "ecommerce", "e-commerce", "commerce", "fashion", "store"),
     ["Shopping Mall", "Retail Market", "Fashion Store"]),
    (("real estate", "property"),
     ["Real Estate Agency", "Property Consultant Office"]),
    (("health", "medical", "clinic", "pharma"),
     ["Clinic", "Pharmacy", "Wellness Center"]),
]

GENERIC_VENUES = ["Community Center", "Co-working Space", "Popular Cafe"]

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}")
_SOCIAL_DOMAINS = ("instagram.com", "youtube.com", "twitter.com", "x.com",
                   "facebook.com")


def venue_categories(industry, positioning):
    """Which kinds of local venues does this product's audience frequent?"""
    blob = (industry + " " + positioning.get("description", "") + " " +
            positioning.get("tagline", "") + " " +
            positioning.get("h1", "")).lower()
    cats = []
    for keys, venues in CONSUMER_VENUES:
        if any(k in blob for k in keys):
            cats.extend(v for v in venues if v not in cats)
        if len(cats) >= 6:
            break
    return cats[:6] if cats else GENERIC_VENUES


# A search result title like "10 Best Coaching Institutes in HSR Layout —
# JustDial" is a LISTICLE — the title names an article, not a business. It
# must never be stored as if it were one venue's name; the real names live
# INSIDE that page and have to be mined out of it, the same way
# find_competitors fetches "alternatives" pages instead of trusting headlines.
_LISTICLE_TITLE = re.compile(
    r"\b(\d{1,3}\s*\+?\s*(?:best|top)|top\s*\d|best\s*\d|"
    r"\btop\b.{0,20}\bin\b|\bbest\b.{0,20}\bin\b)", re.I)
_VENUE_NOISE = re.compile(
    r"\b(best|top|list|guide|review|reviews|rated|ranked|places?\s+to|"
    r"you must|near me|things to do|20\d{2}|"
    # website navigation / UI chrome — a real run showed these leaking
    # through from a page's nav menu, footer link list, or tag cloud as if
    # they were business names ("About Us", "Contact", "Blog", "Casino"
    # from a gaming-zone site's own nav; "Categories", "Community", "Job
    # Search" from a blog's sidebar)
    r"home|about us|about|contact us|contact|blog|blogs|categor(?:y|ies)|"
    r"community|coliving|job search|career growth|career\s+and\s+education|"
    r"city life|faqs?|privacy policy|terms|sitemap|subscribe|newsletter|"
    r"sign up|sign in|login|register|follow us|social media|share|"
    r"related posts?|recent posts?|popular posts?|tags?|archive|search|"
    r"menu|navigation|team building|casino|games?|"
    # promotional/nav copy seen in a real run scraping a booking-site
    # listing page ("Popular Places in Bangalore", "Alternatives to
    # Hostels in Bangalore?", "Other Locations in India", "Hostels in
    # Bangalore from Just $4")
    r"popular places|other locations|alternatives?\s+to|from\s+just|"
    r"book\s+now|book\s+with|\d+%\s*off|discount|\bdeals?\b|\boffers?\b)\b",
    re.I)
# A random statistic ("72% of businesses...") or a pricing line ("Xbox
# Gaming: ₹100 per hour") is never a business name.
_VENUE_NUMERIC_NOISE = re.compile(r"\d+\s*%|[₹$€£]\s*\d|\d\s*[₹$€£]")


def _clean_venue_name(title):
    name = re.split(r"[|–—]", title)[0].strip()
    name = re.sub(r"^\d+[.)]\s*", "", name).strip(" -,.")
    if len(name) < 3 or len(name) > 70 or len(name.split()) > 8:
        return None
    return name


def _has_nearby_description(tag, min_len=40):
    """Genuine listicle entries are followed by 1+ sentences describing the
    place; pure navigation/chrome (nav menus, tag clouds, footer links)
    never is. This is the second, structural defense against mining page
    chrome as if it were a business name — the noise-word list above can
    only catch junk we've already seen, this catches junk we haven't."""
    candidates = []
    nxt = tag.find_next_sibling()
    if nxt is not None:
        candidates.append(nxt)
    if tag.parent is not None:
        p = tag.parent.find("p")
        if p is not None:
            candidates.append(p)
    return any(len(c.get_text(" ", strip=True)) >= min_len for c in candidates)


def _mine_venue_names(soup, cat, location, max_names=8):
    """Pull real business names out of a listicle/directory page's headings
    and list items — mirrors _mine_candidates' heading-scrape approach for
    competitor "alternatives" pages."""
    names, seen = [], set()
    cat_l = cat.lower()
    loc_l = (location or "").lower()
    for tag in soup.select("h2, h3, h4, li"):
        line = tag.get_text(" ", strip=True)
        if not line or len(line) > 90:
            continue
        m = _NUMBERED.match(line)
        cand = (m.group(1) if m else line)
        cand = re.split(r"[|–—]", cand)[0].strip(" .,:-")
        # Fold stylized unicode (mathematical bold/italic letters etc, a
        # common trick to dodge plain-text filters — a real run had
        # "𝐁𝐨𝐨𝐤 𝐰𝐢𝐭𝐡 𝐅𝐑𝐄𝐄") back to plain ASCII before any filter runs.
        cand = unicodedata.normalize("NFKC", cand)
        if not (3 <= len(cand) <= 60) or len(cand.split()) > 8:
            continue
        if _VENUE_NOISE.search(cand) or _VENUE_NUMERIC_NOISE.search(cand):
            continue
        # A phrase describing the location/category itself, not a specific
        # business ("Hostels in Bangalore from Just $4", "Popular Places in
        # Bangalore") — real business names essentially never embed the
        # city name as a descriptive clause like this.
        if loc_l and len(loc_l) >= 4 and loc_l in cand.lower():
            continue
        cl = cand.lower()
        # skip lines that are just the category/location repeated, not a
        # real business name ("Coaching Institutes", "HSR Layout")
        if cl == cat_l or cl == loc_l or cl in (cat_l + "s", cat_l + "es"):
            continue
        if cl in seen:
            continue
        if not _has_nearby_description(tag):
            continue
        seen.add(cl)
        names.append(cand)
        if len(names) >= max_names:
            break
    return names


def find_b2c_venues(company, industry, positioning, location, max_venues=30):
    """Public businesses the target audience visits — partnership/ad-outreach
    targets, geo-targeted when a location is given. Most SERP hits for these
    queries are "best/top N" listicles, so those get fetched and mined for
    the real business names inside; only a genuinely single-business result
    title is trusted directly."""
    cats = venue_categories(industry, positioning)
    loc_suffix = f" in {location}" if location else ""
    venues, seen, sources = [], set(), []
    per_cat = max(4, max_venues // max(len(cats), 1) + 1)
    for cat in cats:
        if len(venues) >= max_venues or out_of_time():
            break
        # One query per category (was two) — halves this section's search
        # volume; "best" reliably surfaces listicles worth mining.
        queries = [f"best {cat.lower()}{loc_suffix}"]
        got, fetched = 0, 0
        for q in queries:
            if got >= per_cat or len(venues) >= max_venues:
                break
            for r in web_search(q, 10):
                if got >= per_cat or len(venues) >= max_venues:
                    break
                if _LISTICLE_TITLE.search(r["title"]):
                    if fetched >= 3 or out_of_time():
                        continue
                    _, soup = fetch_page_text(r["url"])
                    fetched += 1
                    if soup is None:
                        continue
                    for name in _mine_venue_names(soup, cat, location):
                        if got >= per_cat or len(venues) >= max_venues:
                            break
                        if name.lower() in seen:
                            continue
                        seen.add(name.lower())
                        venues.append({
                            "name": name,
                            "category": cat,
                            "location": location or "",
                            "contact": {"phone": "", "email": "", "website": ""},
                            "source_url": r["url"],
                            "segment": "b2c",
                            "lead_type": "venue",
                        })
                        sources.append(r["url"])
                        got += 1
                    continue
                # a genuine single-business result (own site or a directory's
                # individual listing page, not an aggregation article)
                dom = urlparse(r["url"]).netloc.lower()
                if any(d in dom for d in DIRECTORY_DOMAINS):
                    continue
                name = _clean_venue_name(r["title"])
                if not name or name.lower() in seen or _VENUE_NOISE.search(name):
                    continue
                blob = r["title"] + " " + r["snippet"]
                email_m = _EMAIL_RE.search(blob)
                phone_m = _PHONE_RE.search(blob)
                seen.add(name.lower())
                venues.append({
                    "name": name,
                    "category": cat,
                    "location": location or "",
                    "contact": {
                        "phone": phone_m.group(0) if phone_m else "",
                        "email": email_m.group(0) if email_m else "",
                        "website": r["url"],
                    },
                    "source_url": r["url"],
                    "segment": "b2c",
                    "lead_type": "venue",
                })
                sources.append(r["url"])
                got += 1
    return venues, sources


def find_b2c_individuals(company, industry, positioning, location, max_leads=20):
    """Best-effort public creator/community contacts who self-publish an
    email in their bio — never fabricated, kept strictly to what's actually
    indexed. Availability of public self-published contacts is the limit,
    not the code, so this is intentionally lower-volume than venue leads."""
    # Must be a short noun phrase, not the site's own tagline sentence — a
    # real run showed `positioning["h1"]` was "For Students and Parents who
    # demand the best Test Prep", and quoting that whole sentence in a
    # search query guarantees zero matches. `industry` is already a clean,
    # short label (e.g. "test prep") thanks to the taxonomy classifier.
    niche = industry.strip()
    loc_suffix = f" {location}" if location else ""
    leads, seen, sources = [], set(), []
    queries = [
        f'site:instagram.com "{niche}"{loc_suffix} email',
        f'"{niche}"{loc_suffix} collab email instagram',
        f'"{niche}" creator{loc_suffix} contact email',
    ]
    for q in queries:
        if len(leads) >= max_leads or out_of_time():
            break
        for r in web_search(q, 10):
            if len(leads) >= max_leads:
                break
            blob = r["title"] + " " + r["snippet"]
            email_m = _EMAIL_RE.search(blob)
            if not email_m:
                continue
            dom = urlparse(r["url"]).netloc.lower()
            if not any(d in dom for d in _SOCIAL_DOMAINS):
                continue
            key = email_m.group(0).lower()
            if key in seen:
                continue
            handle = r["title"].split("(")[0].split("|")[0].strip()[:60]
            seen.add(key)
            leads.append({
                "name": handle or "—",
                "platform": dom.replace("www.", ""),
                "contact": {"email": email_m.group(0)},
                "source_url": r["url"],
                "segment": "b2c",
                "lead_type": "individual",
            })
            sources.append(r["url"])
    return leads, sources


# --------------------------------------------------------------------------
# Positioning & industry trends
# --------------------------------------------------------------------------

def get_positioning(company, industry):
    """What the company says about itself (title/meta/h1 of its own site)."""
    rs = web_search(f"{company} official website", 6)
    site_url = ""
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    for r in rs:
        dom = urlparse(r["url"]).netloc.lower().replace("www.", "")
        if any(d in dom for d in DIRECTORY_DOMAINS):
            continue
        if slug[:6] in dom.replace("-", "").replace(".", ""):
            site_url = r["url"]
            break
    if not site_url and rs:
        site_url = rs[0]["url"]
    positioning = {"website": site_url, "tagline": "", "description": "", "h1": ""}
    if site_url:
        _, soup = fetch_page_text(site_url)
        if soup is not None:
            if soup.title:
                positioning["tagline"] = soup.title.get_text(strip=True)[:160]
            meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
                "meta", attrs={"property": "og:description"})
            if meta and meta.get("content"):
                positioning["description"] = meta["content"][:300]
            h1 = soup.find("h1")
            if h1:
                positioning["h1"] = h1.get_text(" ", strip=True)[:160]
    return positioning


_STAT_SENT = re.compile(r"[^.]*(?:\$[\d.]+|\d+(?:\.\d+)?%|CAGR|billion|million)[^.]*\.")
_RISK_WORDS = re.compile(
    r"[^.]*(?:regulat|decline|slowdown|risk|consolidat|layoff|churn|saturat|"
    r"pressure|lawsuit|antitrust|tariff|shortage|breach)[^.]*\.", re.I)


def get_trends(company, industry):
    queries = [
        f"{industry} industry trends 2026",
        f"{industry} market size growth forecast",
        f"{company} news 2026",
    ]
    snippets, stats, risks, sources = [], [], [], []
    for q in queries:
        for r in web_search(q, 6):
            s = r["snippet"]
            if not s or len(s) < 50:
                continue
            snippets.append({"text": s, "source": r["url"], "title": r["title"]})
            sources.append(r["url"])
            for m in _STAT_SENT.finditer(s):
                stats.append(m.group(0).strip())
            for m in _RISK_WORDS.finditer(s):
                risks.append(m.group(0).strip())
    return {
        "snippets": snippets[:10],
        "stats": list(dict.fromkeys(stats))[:5],
        "risks": list(dict.fromkeys(risks))[:5],
        "sources": sources[:10],
    }
