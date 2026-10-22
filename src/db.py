"""SQLite schema and helpers. One file = our mini data warehouse."""
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (          -- Segment 'track' events
    message_id     TEXT PRIMARY KEY,         -- Segment's dedup key -> idempotent inserts
    anonymous_id   TEXT,
    event          TEXT,
    timestamp      TEXT,
    siren          TEXT,
    company_name   TEXT,
    source_channel TEXT,
    utm_source     TEXT,
    utm_medium     TEXT,
    utm_campaign   TEXT,
    plan_chosen    TEXT
);

CREATE TABLE IF NOT EXISTS companies (       -- enrichment output, one row per SIREN
    siren             TEXT PRIMARY KEY,
    company_name      TEXT,
    naf_code          TEXT,
    naf_label         TEXT,
    sector_section    TEXT,
    sector_label      TEXT,
    headcount_code    TEXT,
    headcount_label   TEXT,
    headcount_min     INTEGER,
    creation_date     TEXT,
    company_age_years REAL,
    city              TEXT,
    postal_code       TEXT,
    legal_form_code   TEXT,
    legal_form        TEXT,
    missing_fields    TEXT,
    enrichment_status TEXT                   -- ok | partial | failed
);

CREATE TABLE IF NOT EXISTS scored_leads (
    siren         TEXT PRIMARY KEY,
    message_id    TEXT,
    score         INTEGER,
    pts_headcount INTEGER,
    pts_age       INTEGER,
    pts_sector    INTEGER,
    pts_channel   INTEGER,
    routed_to     TEXT                       -- crm | braze
);

CREATE TABLE IF NOT EXISTS crm_leads (       -- mock Salesforce Lead object
    siren             TEXT PRIMARY KEY,      -- would be an External ID field in Salesforce
    Company           TEXT,
    Industry          TEXT,
    NumberOfEmployees INTEGER,
    LeadSource        TEXT,
    Rating            TEXT,
    OwnerQueue        TEXT,
    Lead_Score__c     INTEGER,
    City              TEXT,
    Status            TEXT,
    Sales_Note__c     TEXT,
    Note_Source__c    TEXT,                  -- llm | template
    Note_Flags__c     TEXT                   -- empty = validation passed
);

CREATE TABLE IF NOT EXISTS braze_nurture (   -- Braze user-import rows
    external_id    TEXT PRIMARY KEY,
    company_name   TEXT,
    industry       TEXT,
    city           TEXT,
    lead_score     INTEGER,
    source_channel TEXT,
    plan_chosen    TEXT,
    nurture_track  TEXT
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the database (creating tables if needed). Rows behave like dicts."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> int:
    """INSERT OR REPLACE rows keyed by the table's primary key, so reruns never duplicate."""
    if not rows:
        return 0
    cols = list(rows[0].keys())
    sql = (f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) "
           f"VALUES ({', '.join('?' for _ in cols)})")
    conn.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
    conn.commit()
    return len(rows)
