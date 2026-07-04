"""SQLite caching layer for LeadLens.

Every completed research run is stored keyed on (company, industry) so the
same company is never researched twice. Cached rows are returned instantly;
pass refresh=1 to force a re-run.
"""
import json
import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leadlens.db")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS searches (
            key         TEXT PRIMARY KEY,
            company     TEXT NOT NULL,
            industry    TEXT NOT NULL,
            data        TEXT NOT NULL,
            created_at  REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key         TEXT NOT NULL,
            hit         INTEGER NOT NULL,
            ts          REAL NOT NULL
        )
        """
    )
    return conn


def make_key(company: str, industry: str) -> str:
    return (company or "").strip().lower() + "::" + (industry or "").strip().lower()


def get_cached(company: str, industry: str):
    key = make_key(company, industry)
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT data, created_at FROM searches WHERE key = ?", (key,)
        ).fetchone()
        conn.execute(
            "INSERT INTO search_log (key, hit, ts) VALUES (?, ?, ?)",
            (key, 1 if row else 0, time.time()),
        )
        conn.commit()
        if row:
            data = json.loads(row[0])
            data["cached"] = True
            data["researched_at"] = row[1]
            return data
        return None
    finally:
        conn.close()


def save(company: str, industry: str, data: dict):
    key = make_key(company, industry)
    payload = dict(data)
    payload.pop("cached", None)
    conn = _conn()
    try:
        # one company keeps only its latest research
        conn.execute("DELETE FROM searches WHERE company = ? COLLATE NOCASE",
                     (company.strip(),))
        conn.execute(
            "INSERT OR REPLACE INTO searches (key, company, industry, data, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, company.strip(), industry.strip(), json.dumps(payload), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def find_by_company(company: str):
    """Latest cached result for a company under ANY industry."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT data, created_at FROM searches WHERE company = ? COLLATE NOCASE "
            "ORDER BY created_at DESC LIMIT 1",
            ((company or "").strip(),),
        ).fetchone()
        if row:
            data = json.loads(row[0])
            data["cached"] = True
            data["researched_at"] = row[1]
            return data
        return None
    finally:
        conn.close()


def list_searches():
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT company, industry, created_at FROM searches ORDER BY created_at DESC"
        ).fetchall()
        return [
            {"company": r[0], "industry": r[1], "researched_at": r[2]} for r in rows
        ]
    finally:
        conn.close()
