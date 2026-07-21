"""Optional Apollo.io people-search integration.

Set APOLLO_API_KEY (free at apollo.io, no card required) and LeadLens uses
Apollo's structured people database for B2B decision-maker leads instead of
scraping LinkedIn/Crunchbase/Wellfound search results. This is the durable
fix for lead accuracy/volume/speed: Apollo is a real people+company
database, not search-engine scraping, so it isn't subject to the same
rate-limiting and noisy-title-parsing problems as research.find_leads.

The People Search endpoint (mixed_people/api_search) is credit-free on the
free plan — it returns names/titles/companies but not emails/phones (those
require paid enrichment, which this integration does NOT use). Without the
key everything falls back to research.find_leads (scraping).
"""
import os

import httpx

APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "")

_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/api_search"


def available():
    return bool(APOLLO_API_KEY)


def _headers():
    # Apollo's documented auth header for the api_search family of
    # endpoints. If this 401s against a real key, the fix is here — swap
    # to `Authorization: Bearer {APOLLO_API_KEY}` (their newer "master key"
    # convention) and re-test.
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Api-Key": APOLLO_API_KEY,
    }


def _search_people(person_titles, location="", per_page=10):
    """One page of Apollo's People Search. Query params only (per Apollo's
    docs — this endpoint does NOT take a JSON body for filters)."""
    params = [("per_page", per_page), ("page", 1)]
    for t in person_titles:
        params.append(("person_titles[]", t))
    if location:
        params.append(("person_locations[]", location))
    with httpx.Client(timeout=15) as c:
        resp = c.post(_SEARCH_URL, headers=_headers(), params=params)
    if resp.status_code != 200:
        print(f"[apollo] {resp.status_code}: {resp.text[:300]}", flush=True)
        return []
    data = resp.json()
    return data.get("people", []) or []


def _parse_person(p):
    name = (p.get("name") or "").strip()
    if not name:
        first = p.get("first_name") or ""
        last = p.get("last_name") or ""
        name = f"{first} {last}".strip()
    if not name:
        return None
    org = p.get("organization") or {}
    company = org.get("name") or ""
    profile_url = p.get("linkedin_url") or ""
    if not profile_url:
        pid = p.get("id")
        if not pid:
            return None
        profile_url = f"https://app.apollo.io/#/people/{pid}"
    location_bits = [b for b in (p.get("city"), p.get("state"), p.get("country")) if b]
    return {
        "name": name,
        "role": (p.get("title") or "")[:80],
        "company": company[:60] or "—",
        "profile_url": profile_url,
        "platform": "apollo",
        "snippet": ", ".join(location_bits)[:200],
    }


def find_leads(roles, location="", max_leads=60, per_role=10):
    """Real people matching each buyer-persona title, from Apollo's people
    database. Returns (leads, sources) in the same shape research.find_leads
    produces, so main.py/the frontend need no branching on which source
    was used."""
    leads, seen, sources = [], set(), []
    for role in roles:
        if len(leads) >= max_leads:
            break
        got = 0
        try:
            people = _search_people([role], location, per_page=per_role)
        except Exception as e:
            print(f"[apollo] search failed for {role!r}: {e}", flush=True)
            continue
        for p in people:
            if got >= per_role or len(leads) >= max_leads:
                break
            lead = _parse_person(p)
            if not lead or lead["profile_url"] in seen:
                continue
            lead["persona"] = role
            lead["segment"] = "b2b"
            lead["lead_type"] = "decision_maker"
            seen.add(lead["profile_url"])
            leads.append(lead)
            sources.append(lead["profile_url"])
            got += 1
    return leads, sources
