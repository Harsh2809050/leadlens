"""Seed the LeadLens cache from a JSON file.

Usage: python seed.py payload.json
The JSON must be a full /api/search payload (company, industry, competitors,
leads, positioning, trends, report, sources).
"""
import json
import sys

import db

if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    db.save(data["company"], data["industry"], data)
    print(f"Seeded cache for {data['company']} / {data['industry']}")
