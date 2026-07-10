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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS serp_cache (
            query       TEXT PRIMARY KEY,
            results     TEXT NOT NULL,
            ts          REAL NOT NULL
        )
        """
    )
    return conn


SERP_CACHE_MAX_AGE = 14 * 24 * 3600  # 14 days


def get_serp(query: str):
    """A raw search-engine query result, persisted to disk (not just this
    process's memory) so that once ANY run has successfully searched
    something, every future run — even after a restart, even during a
    rate-limited window — gets it instantly with zero network calls. This
    is the main lever against rate-limiting at real traffic: the fraction of
    queries that need a live engine at all shrinks over time as the cache
    warms up."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT results, ts FROM serp_cache WHERE query = ?", (query,)
        ).fetchone()
        if row and (time.time() - row[1]) < SERP_CACHE_MAX_AGE:
            return json.loads(row[0])
        return None
    finally:
        conn.close()


def save_serp(query: str, results: list):
    conn = _conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO serp_cache (query, results, ts) VALUES (?, ?, ?)",
            (query, json.dumps(results), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def make_key(company: str, industry: str, location: str = "") -> str:
    return ((company or "").strip().lower() + "::" + (industry or "").strip().lower()
            + "::" + (location or "").strip().lower())


def get_cached(company: str, industry: str, location: str = ""):
    key = make_key(company, industry, location)
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


def save(company: str, industry: str, data: dict, location: str = ""):
    key = make_key(company, industry, location)
    payload = dict(data)
    payload.pop("cached", None)
    conn = _conn()
    try:
        # one row per (company, location) — a Mumbai run must never wipe out
        # the Bangalore run for the same company
        conn.execute(
            "DELETE FROM searches WHERE company = ? COLLATE NOCASE "
            "AND key LIKE ?",
            (company.strip(), f"%::{(location or '').strip().lower()}"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO searches (key, company, industry, data, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, company.strip(), industry.strip(), json.dumps(payload), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def find_by_company(company: str, location: str = ""):
    """Latest cached result for a company under ANY industry — but only for
    the SAME location. A search for 'tutelaprep in Mumbai' must never be
    silently answered with the cached Bangalore run (found live: it was)."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT data, created_at FROM searches WHERE company = ? COLLATE NOCASE "
            "AND key LIKE ? ORDER BY created_at DESC LIMIT 1",
            ((company or "").strip(), f"%::{(location or '').strip().lower()}"),
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
            "SELECT company, industry, key, created_at FROM searches "
            "ORDER BY created_at DESC"
        ).fetchall()
        return [
            {"company": r[0], "industry": r[1],
             "location": (r[2].split("::") + ["", "", ""])[2],
             "researched_at": r[3]} for r in rows
        ]
    finally:
        conn.close()
