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


def refine_competitors(company, industry, serp_blob, current):
    """Feed the raw search evidence to the LLM and get back real,
    same-domain competitor companies — never listicle fragments."""
    system = (
        "You are a precise market analyst. From the raw web search evidence, "
        "identify REAL companies that directly compete with the target. "
        "NEVER return publications (TIME, Forbes), directories, categories "
        "('EdTech'), countries, investors (Sequoia), or article fragments. "
        "Only actual product/service companies a buyer would compare against "
        "the target. Return JSON: {\"competitors\": [{\"name\": str, "
        "\"description\": one factual sentence, \"website\": str}]} "
        "with 5-10 entries, best matches first. Use evidence + your own "
        "knowledge of the market."
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
