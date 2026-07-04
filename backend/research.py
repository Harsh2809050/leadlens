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
from collections import Counter
from urllib.parse import quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

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


ENGINES = [
    ("ddg_lite", _ddg_lite),
    ("ddg_html", _ddg_search),
    ("bing", _bing_search),
    ("yahoo", _yahoo_search),
    ("ecosia", _ecosia_search),
    ("brave", _brave_search),
    ("mojeek", _mojeek_search),
]
if BRAVE_API_KEY:
    ENGINES.insert(0, ("brave_api", _brave_api))


_preferred_engine = [None]  # promotes the engine that last worked
_serp_cache = {}            # query -> results, avoids repeat hits in one run
_engine_fails = {}          # engine -> consecutive errors; 3+ = skip (circuit breaker)


def web_search(query, max_results=10):
    """Search the live web, falling through engines until one returns results.
    Slow cadence + one retry pass: search engines rate-limit fast crawlers."""
    if query in _serp_cache:
        return _serp_cache[query][:max_results]
    for attempt in (1, 2):
        time.sleep(random.uniform(1.5, 2.5))  # polite pace beats rate limits
        order = list(ENGINES)
        if _preferred_engine[0]:
            order.sort(key=lambda e: e[0] != _preferred_engine[0])
        for name, fn in order:
            if _engine_fails.get(name, 0) >= 3:
                continue  # circuit breaker: engine is dead this run
            try:
                res = fn(query, max_results)
            except Exception as e:
                _engine_fails[name] = _engine_fails.get(name, 0) + 1
                if _engine_fails[name] == 3:
                    print(f"[search] {name} disabled after 3 errors", flush=True)
                continue
            _engine_fails[name] = 0
            if res:
                _preferred_engine[0] = name
                _serp_cache[query] = res
                print(f"[search] {len(res):>2} results via {name}: {query!r}",
                      flush=True)
                return res
        if attempt == 1:
            print(f"[search] all engines empty for {query!r}; backing off 15s",
                  flush=True)
            time.sleep(15)
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

KNOWN_INDUSTRIES = [
    "productivity software", "project management software", "developer tools",
    "cybersecurity", "cloud computing", "artificial intelligence",
    "data analytics", "marketing software", "hr software", "crm software",
    "e-commerce", "fintech", "payments", "banking", "insurance technology",
    "healthcare technology", "biotechnology", "pharmaceuticals", "edtech",
    "food delivery", "ride hailing", "travel technology", "hospitality",
    "streaming media", "social media", "gaming", "consumer electronics",
    "semiconductors", "electric vehicles", "automotive", "aerospace",
    "logistics", "supply chain", "real estate technology", "retail",
    "fashion", "food and beverage", "energy", "telecommunications", "saas",
]

_IND_PAT = re.compile(
    r"industr(?:y|ies)\s*[:\-–]\s*([A-Za-z &/]{3,40})", re.I)


_IS_A_PAT = re.compile(
    r"\bis an? ([a-z][a-z ,/&\-]{4,70}?)(?:\.|,| that| which| developed| founded|"
    r" headquartered| based| owned| primarily| used )", re.I)


def detect_industry(company):
    """Work out what industry a company is in from live search results."""
    rs = web_search(f"{company} wikipedia company", 6)
    rs += web_search(f"{company} company profile industry", 6)
    text = " ".join((r["title"] + " " + r["snippet"]) for r in rs).lower()

    scores = {k: text.count(k) for k in KNOWN_INDUSTRIES}
    best = max(scores, key=lambda k: (scores[k], len(k)))
    if scores[best] > 1:
        return best

    # "Figma is a collaborative web application for interface design..."
    for r in rs:
        m = _IS_A_PAT.search(r["snippet"]) or _IS_A_PAT.search(r["title"])
        if m:
            phrase = m.group(1).strip().lower()
            phrase = re.sub(r"^(american|indian|british|german|french|chinese|"
                            r"japanese|multinational|global|leading|popular|"
                            r"proprietary|free|online|web.based)\s+", "", phrase)
            if 4 <= len(phrase) <= 60:
                # prefer what comes after "for" ("web application for interface design")
                tail = phrase.split(" for ")[-1]
                return (tail if 4 <= len(tail) <= 40 else phrase)[:40]

    if scores[best] > 0:
        return best
    m = _IND_PAT.search(" ".join(r["snippet"] for r in rs))
    if m:
        return m.group(1).strip().lower()
    return "technology"


# --------------------------------------------------------------------------
# Competitor discovery
# --------------------------------------------------------------------------

_CAP_NAME = re.compile(r"\b([A-Z][A-Za-z0-9&.']+(?:[ \-][A-Z][A-Za-z0-9&.']+){0,2})\b")
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
    if all(w in NOISE_NAMES for w in words):
        return None
    if words[0] in NOISE_NAMES and len(words) > 1:
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


def find_competitors(company, industry, max_competitors=8, progress=None):
    queries = [
        f"{company} top competitors",
        f"{company} alternatives {industry}",
        f"top {industry} companies competing with {company}",
        f"{company} vs",
    ]
    serp_results = []
    texts = []
    for q in queries:
        rs = web_search(q, 10)
        serp_results.extend(rs)
        for r in rs:
            texts.append((1, r["title"]))
            texts.append((1, r["snippet"]))

    # Pull headings from the two most promising comparison articles
    fetched = 0
    for r in serp_results:
        dom = urlparse(r["url"]).netloc.lower()
        if fetched >= 2:
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
    ranked = [(n, s) for n, s in ranked if s >= 3][: max_competitors + 6]
    print(f"[competitors] candidates: {[(n, s) for n, s in ranked]}", flush=True)

    competitors = []
    for name, score in ranked:
        if len(competitors) >= max_competitors:
            break
        verified, desc, website = verify_competitor(name, company, industry)
        print(f"[verify] {name}: {'OK' if verified else 'dropped'}", flush=True)
        if not verified:
            continue  # no head-to-head evidence on the web — drop it
        competitors.append({
            "name": name,
            "description": desc,
            "website": website,
            "confidence": min(99, 55 + score * 3),
        })
    return competitors, [r["url"] for r in serp_results[:12]]


_COMPANYISH = re.compile(
    r"\b(compan|software|platform|app\b|application|tool|startup|founded|"
    r"design|saas|cloud|service|product|enterprise|workspace|collaborat)", re.I)


def verify_competitor(name, company, industry):
    """A candidate only counts if the live web shows real head-to-head
    evidence: a '<name> vs <company>' title or an 'alternative to <company>'
    context. Kills SERP noise like 'Download' or 'Learn'."""
    nl, cl = name.lower(), company.lower()
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
    if not verified:
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
                if slug[:6] in dom.replace("-", "").replace(".", ""):
                    website = "https://" + dom
    if not desc:
        for r in rs + rs2:  # fall back to the vs-page snippet
            snip = _clean_snip(r["snippet"])
            if nl in r["title"].lower() and len(snip) > 60:
                desc = snip[:260].rsplit(" ", 1)[0]
                break
    if desc and not website:
        for r in rs2:
            dom = urlparse(r["url"]).netloc.lower().replace("www.", "")
            if not any(d in dom for d in DIRECTORY_DOMAINS):
                website = "https://" + dom
                break
    return bool(desc), desc, website


# --------------------------------------------------------------------------
# Lead discovery (decision makers via LinkedIn search results)
# --------------------------------------------------------------------------

LEAD_ROLES = ["CEO", "Founder", "CTO", "Head of Marketing"]

_LI_TITLE_SPLIT = re.compile(r"\s+[-–—|]\s+")


_LI_URL = re.compile(r"https?://[a-z]{0,3}\.?linkedin\.com/in/[A-Za-z0-9\-_%.]+")


def _parse_linkedin_result(r, company_hint):
    m = _LI_URL.search(r["url"]) or _LI_URL.search(unquote(r["url"]))
    if not m:
        return None
    url = m.group(0)
    parts = _LI_TITLE_SPLIT.split(r["title"].replace(" | LinkedIn", "").replace(" - LinkedIn", ""))
    parts = [p.strip() for p in parts if p.strip() and p.strip().lower() != "linkedin"]
    if not parts:
        return None
    name = parts[0]
    if len(name) > 45 or len(name.split()) > 4 or not re.match(r"^[A-Z]", name):
        return None
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


def _lead_queries(role, target):
    return [
        f'site:linkedin.com/in "{role}" "{target}"',
        f'{target} {role} linkedin.com/in',
    ]


def find_leads(company, industry, competitors, max_leads=12):
    """Decision makers at the target company and its top competitors."""
    targets = [company] + [c["name"] for c in competitors[:3]]
    leads, seen = [], set()
    sources = []
    for target in targets:
        for role in LEAD_ROLES:
            if len(leads) >= max_leads:
                return leads, sources
            found = None
            for q in _lead_queries(role, target):
                for r in web_search(q, 6):
                    lead = _parse_linkedin_result(r, target)
                    if lead and lead["linkedin_url"] not in seen:
                        # the lead must actually mention the target company
                        blob = (r["title"] + " " + r["snippet"]).lower()
                        if target.lower() not in blob:
                            continue
                        found = lead
                        break
                if found:
                    break
            if found:
                seen.add(found["linkedin_url"])
                found["is_target_company"] = target.lower() == company.lower()
                leads.append(found)
                sources.append(found["linkedin_url"])
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
