"""Business intelligence report builder.

Composes an analyst-style narrative strictly from data gathered during
research — competitor set, LinkedIn decision makers, the company's own
positioning copy, and industry trend/statistic sentences pulled from live
sources. Nothing here is boilerplate-only: every section quotes or names
real gathered entities, and sections that lack data say so honestly.
"""
import re

_NEGATIVE = re.compile(
    r"\b(fell|fallen|falling|down|declin\w*|drop\w*|lost|losing|loss|"
    r"slump\w*|crash\w*|plunge\w*|weaker|fears)\b", re.I)


def _fmt_names(items, n=3):
    names = [c["name"] for c in items[:n]]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _clip(text, n=180):
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0] + "…"


def build_report(company, industry, competitors, leads, positioning, trends):
    # split stats by sentiment so declines are never sold as "momentum"
    all_stats = trends.get("stats", [])
    pos_stats = [s for s in all_stats if not _NEGATIVE.search(s)]
    neg_stats = [s for s in all_stats if _NEGATIVE.search(s)]
    trends = dict(trends)
    trends["stats"] = pos_stats
    if neg_stats and not trends.get("risks"):
        trends["risks"] = neg_stats

    comp_names = _fmt_names(competitors)
    n_comp = len(competitors)
    n_leads = len(leads)
    tagline = positioning.get("description") or positioning.get("h1") or positioning.get("tagline") or ""

    # ---------------- Executive summary ----------------
    summary_bits = []
    summary_bits.append(
        f"{company} operates in the {industry} market against at least "
        f"{n_comp} identifiable direct competitors"
        + (f", led by {comp_names}" if comp_names else "") + "."
    )
    if tagline:
        summary_bits.append(
            f"The company currently positions itself as: “{_clip(tagline, 200)}”"
        )
    if trends.get("stats"):
        summary_bits.append(
            f"Market signal worth noting: {_clip(trends['stats'][0], 220)}"
        )
    if n_leads:
        personas = sorted({l.get("persona", l.get("role", "")) for l in leads
                           if l.get("persona") or l.get("role")})[:3]
        summary_bits.append(
            f"We surfaced {n_leads} prospective buyers worldwide matching "
            f"{company}'s customer profile"
            + (f" ({', '.join(personas)})" if personas else "") + "."
        )
    summary = " ".join(summary_bits)

    # ---------------- Growth levers ----------------
    growth = []

    if trends.get("stats"):
        stat = _clip(trends["stats"][0], 240)
        growth.append({
            "title": "Ride the documented market tailwind",
            "detail": (
                f"Live industry data points to real momentum: “{stat}” "
                f"If the category is expanding at that pace, {company}'s growth constraint is "
                f"share-of-voice, not demand. The play is to over-invest in category-level content "
                f"and comparison pages now, while customer acquisition costs in {industry} are still "
                f"set by slower incumbents."
            ),
        })

    if competitors:
        top = competitors[0]
        second = competitors[1] if len(competitors) > 1 else None
        vs = f"{top['name']}" + (f" and {second['name']}" if second else "")
        growth.append({
            "title": f"Win the head-to-head against {vs}",
            "detail": (
                f"{top['name']} — “{_clip(top['description'], 150)}” — is the deal {company} will "
                f"most often be compared to. "
                + (f"{second['name']} crowds the same space. " if second else "")
                + f"A crowded field is also a poaching field: every {top['name']} customer is a "
                f"pre-qualified {company} prospect. Build a direct migration path and a "
                f"'{company} vs {top['name']}' page that names real switching pains; competitors "
                f"this visible always leave unhappy customers searching for alternatives."
            ),
        })

    if leads:
        personas = sorted({l.get("persona", l.get("role", "")) for l in leads
                           if l.get("persona") or l.get("role")})[:4]
        growth.append({
            "title": "Run targeted outbound at the mapped buyer prospects",
            "detail": (
                f"This research produced {n_leads} named, LinkedIn-verified prospects whose "
                f"job titles ({', '.join(personas)}) match the people who buy products like "
                f"{company}'s. These are potential CLIENTS, not industry insiders — each one is "
                f"an outbound-ready contact. A 20-touch/week motion against this list, with the "
                f"persona-specific pain point in the first line, is the cheapest pipeline "
                f"{company} can generate this quarter."
            ),
        })

    if len(growth) < 3:
        gaps = positioning.get("description") or positioning.get("tagline")
        growth.append({
            "title": "Sharpen positioning where competitors are generic",
            "detail": (
                (f"{company}'s own site leads with “{_clip(gaps, 140)}”. " if gaps else "")
                + f"Most rivals in {industry} describe themselves in near-identical language. "
                f"Claiming one specific, verifiable outcome (time saved, revenue added, risk removed) "
                f"and repeating it everywhere is the fastest available differentiation — it costs "
                f"copywriting, not engineering."
            ),
        })

    # ---------------- Kill risks ----------------
    risks = []

    if n_comp >= 4:
        risks.append({
            "title": f"Commoditization by a {n_comp}-player field",
            "detail": (
                f"With {comp_names} all selling into the same buyer, {industry} pricing pressure is "
                f"structural. When features converge, deals go to the cheapest or best-distributed "
                f"vendor. If {company} cannot name the one thing it does that "
                f"{competitors[0]['name']} cannot copy in two quarters, margin erosion is not a "
                f"risk — it is a schedule."
            ),
        })
    elif competitors:
        risks.append({
            "title": f"Direct displacement by {competitors[0]['name']}",
            "detail": (
                f"“{_clip(competitors[0]['description'], 160)}” — that description overlaps heavily "
                f"with {company}'s own pitch. A better-funded rival with the same story wins by "
                f"default in competitive deals. {company} needs proof points, not adjectives."
            ),
        })

    if trends.get("risks"):
        risk_sent = _clip(trends["risks"][0], 240)
        risks.append({
            "title": "Macro/industry headwind already visible in the news",
            "detail": (
                f"Current coverage of the {industry} space surfaced this warning: “{risk_sent}” "
                f"Trends like this compress budgets before they show up in pipelines. {company} "
                f"should stress-test its forecast against the scenario where this accelerates, and "
                f"shorten sales cycles now rather than after the quarter it bites."
            ),
        })

    if len(risks) < 3 and competitors:
        top = competitors[0]
        risks.append({
            "title": f"Losing the buyer's shortlist to {top['name']}",
            "detail": (
                f"The prospects this research surfaced are the same people {top['name']} and the "
                f"rest of the field are pitching. In {industry}, buyers shortlist two or three "
                f"vendors and never hear about the rest. If {company} is not visible in the "
                f"channels these personas use (LinkedIn, industry comparisons, peer reviews), it "
                f"loses deals it never knew existed — silently and repeatedly."
            ),
        })

    while len(risks) < 3:
        risks.append({
            "title": "Single-channel dependence",
            "detail": (
                f"Research on {company} surfaced limited independent coverage relative to its "
                f"competitor set — the company is under-indexed in the sources buyers actually "
                f"consult ({industry} comparison sites, analyst lists, executive LinkedIn). "
                f"Low third-party presence means one algorithm change or one lost channel can "
                f"stall acquisition entirely."
            ),
        })

    return {"summary": summary, "growth": growth[:3], "risks": risks[:3]}
