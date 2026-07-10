"""Regression tests for bugs found and fixed during live debugging of the
research pipeline (industry detection, competitor verification, B2C venue
mining, and search-engine resilience).

Network-free by design — no server, no background process, no real HTTP
calls for the bulk of the suite. web_search is monkeypatched to a stub that
records what queries were requested; the resilience tests (9-13) restore the
real web_search but point ENGINES at fake in-process stand-ins instead of
real search engines, so the retry/backoff/cooldown logic under test actually
executes without touching the network.

Run with: python backend/tests/test_research.py
"""
import os
import sys
import time
import unicodedata
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import research

_REAL_WEB_SEARCH = research.web_search  # save before any test monkeypatches it
RUN_ID = uuid.uuid4().hex[:8]  # every run gets fresh query strings — the
                               # persistent disk cache (by design) would
                               # otherwise serve a prior run's leftover
                               # result and short-circuit the engines this
                               # test is trying to exercise

calls = []


def fake_web_search(query, max_results=10):
    calls.append(query)
    return []  # simulate: nothing found anywhere for a made-up company


research.web_search = fake_web_search
research.fetch_page_text = lambda url, limit=6000: ("", None)

# --- Test 1: verify_competitor mega-cap guard (no network needed at all) ---
ok, desc, site = research.verify_competitor("Apple", "SomeMadeUpCo",
                                            "technology", require_vs=False)
assert ok is False, "Apple must NEVER be accepted via the loose category-fallback path"
print("[PASS] mega-cap guard blocks Apple in category-fallback verification")

ok2, _, _ = research.verify_competitor("Salesforce", "SomeMadeUpCo",
                                       "crm software", require_vs=False)
assert ok2 is False
print("[PASS] mega-cap guard blocks Salesforce too")

# --- Test 2: detect_industry returns confident=False for a fictitious company ---
calls.clear()
industry, confident = research.detect_industry("Edvincible Technologies", {})
print(f"[INFO] detect_industry -> industry={industry!r} confident={confident}")
assert confident is False, "a company with zero web signal must not be 'confident'"
print("[PASS] detect_industry correctly reports low confidence for an unknown company")

# --- Test 3: find_competitors must NOT run the 'top {industry} companies'
# category fallback when industry_confident=False (this is the exact bug:
# that fallback is what pulled Apple/Alphabet/AMD as fake competitors) ---
calls.clear()
competitors, sources = research.find_competitors(
    "Edvincible Technologies", "technology", industry_confident=False)
category_queries = [q for q in calls if q == "top technology companies"
                    or q == "best technology platforms"]
assert not category_queries, f"category fallback ran anyway: {category_queries}"
assert competitors == []
print("[PASS] find_competitors skips the category fallback when industry_confident=False")
print(f"[INFO] queries issued: {calls}")

# --- Test 4: sanity check the fallback DOES still run when confident=True
# (so we haven't broken legitimate small-company competitor discovery) ---
calls.clear()
competitors2, _ = research.find_competitors(
    "RealCo", "productivity software", industry_confident=True)
category_queries2 = [q for q in calls if q == "top productivity software companies"]
assert category_queries2, "category fallback should still run when confident=True"
print("[PASS] category fallback still runs normally when industry_confident=True")

# --- Test 5: find_competitors now issues company-anchored, industry-agnostic
# queries too (the fix for "competitors are very less" for real niche companies
# whose industry doesn't match the crude keyword list) ---
calls.clear()
research.find_competitors("RealNicheCo", "technology", industry_confident=False)
anchored_queries = [q for q in calls if q in
                    ("companies like RealNicheCo", "RealNicheCo similar companies")]
assert len(anchored_queries) == 2, f"missing anchored queries: {calls}"
print("[PASS] find_competitors issues company-anchored fallback-free queries")

# --- Test 6: find_leads never issues a fully bare, unqualified query ---
calls.clear()
research.find_leads("SomeCo", "productivity software", {}, location="Bangalore",
                    max_leads=5)
bare = [q for q in calls if q.strip().endswith('" linkedin profile')
       and "Bangalore" not in q and "productivity" not in q]
assert not bare, f"found a bare unqualified query: {bare}"
print("[PASS] find_leads queries are always industry/location-qualified")

# --- Test 7: venue listicle titles are never stored as a business name ---
from bs4 import BeautifulSoup
fake_html = """
<html><body>
<div class="item">
<h2>1. Bright Minds Coaching Centre</h2>
<p>Located in HSR Layout, this coaching centre has helped over 500 students crack competitive exams with personalized mentoring.</p>
</div>
<div class="item">
<h2>2. Apex IIT Academy</h2>
<p>A well-known name in Bangalore for IIT-JEE preparation, offering both online and offline batches for students.</p>
</div>
<h3>Best Coaching Institutes</h3>
<div class="item">
<li>3. Zenith Learning Point</li>
<p>Zenith Learning Point is a boutique tutoring center known for small batch sizes and individual attention.</p>
</div>
<nav>
<h3>About Us</h3>
<li>Contact</li>
</nav>
<div class="item">
<h4>Random Heading No Description</h4>
</div>
<div class="item">
<h3>72% of businesses use blended work arrangements</h3>
<p>A statistic pulled from an unrelated article about remote work trends in the city.</p>
</div>
<div class="item">
<h3>Xbox Gaming: ₹100 per hour</h3>
<p>Pricing information for a console gaming section inside some venue nearby.</p>
</div>
<div class="item">
<h3>Popular Places in Bangalore</h3>
<p>A generic section heading introducing the list below, not a business itself.</p>
</div>
<div class="item">
<h4>FAQs</h4>
<p>Frequently asked questions about booking hostels in this city and nearby areas.</p>
</div>
<div class="item">
<h3>Alternatives to Hostels in Bangalore?</h3>
<p>A section suggesting other kinds of accommodation for travellers visiting the city.</p>
</div>
<div class="item">
<h3>Hostels in Bangalore from Just $4</h3>
<p>A promotional banner advertising low prices, not a specific hostel's name.</p>
</div>
<div class="item">
<h3>𝐁𝐨𝐨𝐤 𝐰𝐢𝐭𝐡 𝐅𝐑𝐄𝐄</h3>
<p>Stylized unicode bold text spelling Book with FREE, a filter-dodging promo banner exactly as seen in a real run.</p>
</div>
</body></html>
"""
soup = BeautifulSoup(fake_html, "html.parser")
mined = research._mine_venue_names(soup, "Coaching Institute", "Bangalore")
print(f"[INFO] mined venue names: {mined}")
assert "Bright Minds Coaching Centre" in mined
assert "Apex IIT Academy" in mined
assert "Zenith Learning Point" in mined
assert "Best Coaching Institutes" not in mined, "listicle heading itself must not be mined as a business"
assert "About Us" not in mined, "nav/chrome noise word filter should block this"
assert "Contact" not in mined, "nav/chrome noise word filter should block this"
assert "Random Heading No Description" not in mined, \
    "heading with no nearby description must be rejected (structural nav/chrome defense)"
assert not any("72%" in n for n in mined), "a random statistic must not be mined as a venue name"
assert not any("Xbox" in n for n in mined), "a pricing line must not be mined as a venue name"
assert not any("Popular Places" in n for n in mined), "a generic section heading must be rejected"
assert not any(n.upper() == "FAQS" for n in mined), "FAQs (plural) must be rejected"
assert not any("Alternatives to" in n for n in mined), "an 'alternatives to X' phrase must be rejected"
assert not any("from Just" in n for n in mined), "promotional 'from just $X' pricing copy must be rejected"
assert not any("BOOK" in unicodedata.normalize("NFKC", n).upper() for n in mined), \
    "stylized unicode text used to dodge filters must still be caught after normalization"
print("[PASS] _mine_venue_names extracts real names, skips listicle headings, "
      "nav/chrome noise words, headings with no nearby description, random "
      "statistics, pricing lines, generic location phrases, and unicode-"
      "obfuscated promotional text")

# listicle-title detection: a SERP result titled like an aggregation article
# must be routed to page-mining, not stored as a venue name directly
assert research._LISTICLE_TITLE.search("10 Best Coaching Institutes in HSR Layout - JustDial")
assert not research._LISTICLE_TITLE.search("Bright Minds Coaching Centre - HSR Layout")
print("[PASS] listicle-title detector correctly distinguishes aggregation pages from single businesses")

# --- Test 8: the real "tutelaprep" case — positioning copy that phrases
# things naturally ("coaching for competitive exams") instead of the exact
# literal phrase "test prep" that the old flat KNOWN_INDUSTRIES list
# required. This is exactly why detect_industry fell through to the generic
# "technology" placeholder for a real education company in production. ---
calls.clear()
industry, confident = research.detect_industry("TutelaPrep", {
    "tagline": "TutelaPrep — Coaching for Competitive Exams",
    "description": "We help students crack entrance exams with expert coaching classes.",
    "h1": "",
})
print(f"[INFO] tutelaprep-style positioning -> industry={industry!r} confident={confident}")
assert industry != "technology", "must not fall back to the generic placeholder when real signal exists"
assert confident is True
print("[PASS] taxonomy-based classifier correctly labels a real education company")

# --- Test 9: broad rate-limit detector skips the 5s backoff-and-retry once
# 5 queries in a row have come back empty from every engine. Uses the REAL
# web_search (saved before other tests replaced it) with a fake dead engine
# list, so the actual retry/backoff logic under test actually executes. ---
research.web_search = _REAL_WEB_SEARCH
research.ENGINES = [("dead_engine", lambda q, n=10: [])]
research._preferred_engine[0] = None
research._engine_fails.clear()
research._serp_cache.clear()
research._engine_empty_streak.clear()
research._engine_cooldown_until.clear()

sleep_calls = []
_orig_sleep = research.time.sleep
research.time.sleep = lambda s: sleep_calls.append(s)
try:
    research.set_deadline(60)  # resets _consecutive_empty too
    for i in range(6):
        research.web_search(f"dead query {i} {RUN_ID}")
finally:
    research.time.sleep = _orig_sleep

backoffs = [s for s in sleep_calls if s == 5]
# queries 0-4 each still pay the backoff (consecutive_empty reaches 5 only
# after the 5th one finishes); query 5 is the first to see broadly_blocked
# and skip it.
assert len(backoffs) == 5, f"expected exactly 5 backoff sleeps (queries 0-4), got {len(backoffs)}"
print(f"[INFO] backoff sleeps triggered: {len(backoffs)} (query 6 skips it)")
print("[PASS] rate-limit detector stops paying the backoff after 5 consecutive empty queries")

# --- Test 10: persistent disk-backed cache — a query answered once is
# served from disk on a LATER call even with the in-memory cache cleared
# and the engine that answered it no longer available at all. ---
research.set_deadline(60)  # clean slate for _consecutive_empty
UNIQUE_Q = f"offline-check persistent cache probe query {RUN_ID}"
FAKE_RESULT = [{"title": "Probe Result", "url": "https://example.com/probe",
               "snippet": "hello"}]
research.ENGINES = [("one_shot", lambda q, n=10: FAKE_RESULT)]
research._preferred_engine[0] = None
out1 = research.web_search(UNIQUE_Q)
assert out1 == FAKE_RESULT
persisted = research.db.get_serp(UNIQUE_Q)
assert persisted == FAKE_RESULT, "result was not persisted to disk"
print("[PASS] successful search result persisted to db.serp_cache")

research._serp_cache.clear()  # wipe the in-memory cache only


def _must_not_be_called(q, n=10):
    raise AssertionError("engine was called — persistent cache was not used")


research.ENGINES = [("must_not_run", _must_not_be_called)]
out2 = research.web_search(UNIQUE_Q)
assert out2 == FAKE_RESULT
print("[PASS] later call served from persistent disk cache without touching any engine")

# --- Test 11: per-engine cooldown benches an engine after repeated empty
# (not erroring) results, instead of retrying it forever — as long as an
# ALTERNATIVE engine exists (the no-alternative case is Test 12 below,
# where trying the benched engine anyway is the correct behavior). ---
research.set_deadline(60)
call_count = [0]
backup_calls = [0]


def _flaky(q, n=10):
    call_count[0] += 1
    return []


def _backup(q, n=10):
    backup_calls[0] += 1
    return [{"title": "ok", "url": "https://example.com", "snippet": "x"}]


research.ENGINES = [("flaky", _flaky), ("backup", _backup)]
research._engine_empty_streak.clear()
research._engine_cooldown_until.clear()
for i in range(4):
    # reset each time: once "backup" succeeds once, _preferred_engine
    # promotes it to be tried FIRST on subsequent calls, which would stop
    # "flaky" from being tried again at all (sensible prod behavior — favor
    # what just worked) and never let its streak build up. Forcing no
    # preference isolates the streak mechanic this test is actually about.
    research._preferred_engine[0] = None
    research.web_search(f"cooldown probe query {i} {RUN_ID}")
assert research._engine_cooldown_until.get("flaky", 0) > time.time(), \
    "engine should be benched after 4 consecutive empty results"
calls_before = call_count[0]
research.web_search(f"cooldown probe query 4 {RUN_ID} (should skip flaky, use backup)")
assert call_count[0] == calls_before, \
    "benched engine should not be retried while a working alternative exists"
assert backup_calls[0] > 0
print("[PASS] engine with 4 consecutive empty results gets benched and skipped "
      "in favor of a working alternative")

# --- Test 12: when EVERY engine ends up in cooldown at once, a later query
# must still try one of them rather than guarantee an empty result. This is
# the exact bug seen live: cooldowns benched all 7 engines mid-run, and
# venues/individuals/trends came back empty afterward regardless of how good
# their queries were, because nothing was left to even attempt. ---
research.set_deadline(60)
calls_a, calls_b = [0], [0]


def _engine_a(q, n=10):
    calls_a[0] += 1
    return []


def _engine_b(q, n=10):
    calls_b[0] += 1
    return []


research.ENGINES = [("engine_a", _engine_a), ("engine_b", _engine_b)]
research._engine_fails.clear()
research._engine_empty_streak.clear()
research._engine_cooldown_until.clear()
research._preferred_engine[0] = None
# force both into cooldown directly (faster than 4 real empty queries each)
now = time.time()
research._engine_cooldown_until["engine_a"] = now + 300
research._engine_cooldown_until["engine_b"] = now + 300

research.web_search(f"probe query after both engines cooled down {RUN_ID}")
assert calls_a[0] + calls_b[0] > 0, \
    "with every engine in cooldown, the safety valve should still try one"
print("[PASS] safety valve tries an engine anyway when all are in cooldown")

# sanity: a HARD-failed engine (real exceptions) must stay excluded even by
# the safety valve — only the soft cooldown gets overridden
research.set_deadline(60)
research._engine_fails.clear()
research._engine_empty_streak.clear()
research._engine_cooldown_until.clear()
research._preferred_engine[0] = None


def _broken(q, n=10):
    raise RuntimeError("simulated hard failure")


research.ENGINES = [("broken", _broken)]
for i in range(3):
    research.web_search(f"trip the hard-failure breaker {i} {RUN_ID}")
assert research._engine_fails.get("broken", 0) >= 3
calls_after_break = [0]
research.ENGINES = [("broken", _broken)]
out = research.web_search(f"query after breaker tripped {RUN_ID}")
assert out == [], "hard-failed engine must stay excluded even with nothing else available"
print("[PASS] hard-failed (exception) engines stay excluded even when no alternative exists")

# --- Test 13: category-fallback (require_vs=False) website matching must
# not accept a coincidental substring match for a short/generic name — a
# real run had "Erik" (a testimonial's first name) verified as a
# "competitor" because some unrelated domain happened to contain "erik". ---
research.web_search = _REAL_WEB_SEARCH
research.set_deadline(60)


def _fake_desc_search(q, n=10):
    if "vs" in q:
        return []  # no head-to-head evidence at all
    return [{"title": "Erik test prep company", "url": "https://somerandomerikblog.com/post",
            "snippet": "Erik used our test prep company services and loved it, a great "
                       "software product for students."}]


research.ENGINES = [("fake", _fake_desc_search)]
research._preferred_engine[0] = None
research._serp_cache.clear()
ok, desc, website = research.verify_competitor("Erik", "TutelaPrep", "test prep",
                                                require_vs=False)
assert ok is False, "a short/generic name must not pass on a coincidental domain substring match"
print("[PASS] category-fallback verification rejects a coincidental short-name domain match")

print("\nALL OFFLINE CHECKS PASSED — no network or server involved.")
