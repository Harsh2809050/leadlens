"""Optional LLM brain (Groq free tier).

Set GROQ_API_KEY (free at console.groq.com) and LeadLens uses an LLM to:
  1. extract REAL competitor names from the raw research evidence
  2. write a company-specific analyst report (not a template)
Without the key everything falls back to the rule-based engine.
"""
import json
import os

import httpx

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def available():
    return bool(GROQ_API_KEY)


def _chat(system, user, max_tokens=2500):
    r = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 0.3,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def detect_industry(company, positioning, serp_blob):
    """Best-effort industry classification when rule-based keyword counting
    found nothing. Must say confident=false rather than guess a generic
    category for companies it doesn't recognize — a confident-but-wrong
    guess here is what causes downstream competitor search to go off the
    rails (see research.find_competitors' category fallback)."""
    system = (
        "You are a precise research assistant. Determine the industry/"
        "category of the target company using ONLY the evidence provided. "
        "If the evidence does not clearly identify a real, recognizable "
        "company, set confident to false rather than guessing a generic "
        "category — do not default to something vague like 'technology'. "
        "Return JSON: {\"industry\": str (2-4 lowercase words, e.g. "
        "'project management software'), \"confident\": bool}."
    )
    user = json.dumps({
        "company": company,
        "positioning": positioning,
        "search_evidence": serp_blob[:4000],
    })
    out = _chat(system, user, max_tokens=200)
    industry = str(out.get("industry", "")).strip().lower()
    confident = bool(out.get("confident", False)) and bool(industry)
    return industry, confident


def refine_competitors(company, industry, serp_blob, current):
    """Feed the raw search evidence to the LLM and get back real,
    same-domain competitor companies — never listicle fragments."""
    system = (
        "You are a precise market analyst. From the raw web search evidence, "
        "identify REAL companies that directly compete with the target. "
        "ONLY name a company that is explicitly mentioned by name in the "
        "search evidence below — never invent or recall a competitor from "
        "general knowledge, even if it feels like an obvious market leader "
        "(e.g. do not add Apple/Google/Microsoft unless the evidence itself "
        "names them). If fewer than 3 companies are actually mentioned in "
        "the evidence, return fewer entries — never pad the list. NEVER "
        "return publications (TIME, Forbes), directories, categories "
        "('EdTech'), countries, investors (Sequoia), or article fragments. "
        "Return JSON: {\"competitors\": [{\"name\": str, "
        "\"description\": one factual sentence, \"website\": str}]} "
        "with up to 10 entries, best matches first."
    )
    user = json.dumps({
        "target_company": company,
        "industry": industry,
        "already_found": [c["name"] for c in current],
        "search_evidence": serp_blob[:7000],
    })
    out = _chat(system, user)
    comps = []
    for i, c in enumerate(out.get("competitors", [])[:10]):
        name = str(c.get("name", "")).strip()
        if not name or name.lower() == company.lower():
            continue
        comps.append({
            "name": name[:40],
            "description": str(c.get("description", ""))[:280],
            "website": str(c.get("website", ""))[:100],
            "confidence": max(60, 96 - i * 4),
        })
    return comps


def write_report(company, industry, competitors, leads, positioning, trends):
    """Company-specific analyst report grounded in the gathered data."""
    system = (
        "You are a senior business analyst writing for a founder. Using ONLY "
        "the provided research data plus well-known market facts, write a "
        "sharp, specific intelligence report. No generic advice — every "
        "point must reference actual competitor names, real personas, or "
        "real numbers from the data. Return JSON: {\"summary\": str (4-6 "
        "sentences), \"growth\": [{\"title\": str, \"detail\": 3-4 specific "
        "sentences}] x3, \"risks\": [{\"title\": str, \"detail\": 3-4 "
        "specific sentences}] x3}."
    )
    user = json.dumps({
        "company": company,
        "industry": industry,
        "competitors": [{"name": c["name"], "description": c["description"]}
                        for c in competitors[:8]],
        "buyer_prospects_found": [
            {"name": l["name"], "role": l.get("role", ""),
             "persona": l.get("persona", "")} for l in leads[:12]],
        "total_prospects": len(leads),
        "company_positioning": positioning,
        "market_stats": trends.get("stats", []),
        "market_risks": trends.get("risks", []),
    })
    out = _chat(system, user)
    rep = {
        "summary": str(out.get("summary", ""))[:1500],
        "growth": [{"title": str(g.get("title", ""))[:120],
                    "detail": str(g.get("detail", ""))[:900]}
                   for g in out.get("growth", [])[:3]],
        "risks": [{"title": str(r.get("title", ""))[:120],
                   "detail": str(r.get("detail", ""))[:900]}
                  for r in out.get("risks", [])[:3]],
    }
    if rep["summary"] and len(rep["growth"]) == 3 and len(rep["risks"]) == 3:
        return rep
    raise ValueError("LLM report incomplete")
