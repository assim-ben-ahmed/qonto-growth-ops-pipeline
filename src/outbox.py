"""Step 6 - Integration payloads (dry run).

Build the exact HTTP requests Salesforce, Braze and Meta would receive, and
save them in output/outbox/ instead of sending them. No credentials needed:
tokens appear as {PLACEHOLDERS}, and the files can be reviewed before a real
sender replays them.
"""
import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SALESFORCE_API = "/services/data/v61.0"
META_API = "https://graph.facebook.com/v21.0"
SALESFORCE_BATCH = 200  # sObject Collections: max 200 records per request
BRAZE_BATCH = 75        # /users/track: max 75 objects per array per request
META_BATCH = 1000       # Conversions API: max 1000 events per request


def chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def sha256(value: str) -> str:
    """Meta requires customer identifiers to be normalised (trim, lowercase) and hashed."""
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def salesforce_record(lead: dict[str, Any]) -> dict[str, Any]:
    """One Lead for an upsert on the SIREN__c External ID (replays update, never duplicate)."""
    flagged = bool(lead["Note_Flags__c"])
    return {
        "attributes": {"type": "Lead"},
        "SIREN__c": lead["siren"],
        "Company": lead["Company"],
        "LastName": "(sign-up contact)",  # required field; in prod: the user's name from sign-up
        "Industry": lead["Industry"],
        "NumberOfEmployees": lead["NumberOfEmployees"],
        "LeadSource": lead["LeadSource"],
        "Rating": lead["Rating"],
        "Status": lead["Status"],
        "City": lead["City"],
        "Country": "France",
        "Lead_Score__c": lead["Lead_Score__c"],
        "Owner_Queue__c": lead["OwnerQueue"],  # a Lead assignment rule routes on this field
        # A flagged AI note is held back: Sales never sees an unchecked claim.
        "Sales_Note__c": None if flagged else lead["Sales_Note__c"],
        "Note_Needs_Review__c": flagged,
    }


def salesforce_requests(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = [salesforce_record(l) for l in leads]
    return [{"method": "PATCH",
             "url": f"{{SALESFORCE_INSTANCE}}{SALESFORCE_API}/composite/sobjects/Lead/SIREN__c",
             "headers": {"Authorization": "Bearer {SALESFORCE_TOKEN}"},
             "body": {"allOrNone": False, "records": batch}}
            for batch in chunks(records, SALESFORCE_BATCH)]


def braze_requests(rows: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Custom attributes + a 'nurture_enrolled' event that triggers the Canvas."""
    requests = []
    for batch in chunks(rows, BRAZE_BATCH):
        requests.append({
            "method": "POST", "url": "{BRAZE_REST_ENDPOINT}/users/track",
            "headers": {"Authorization": "Bearer {BRAZE_API_KEY}"},
            "body": {
                "attributes": [{k: r[k] for k in ("external_id", "company_name", "industry", "city",
                                                  "lead_score", "source_channel", "plan_chosen",
                                                  "nurture_track")} for r in batch],
                "events": [{"external_id": r["external_id"], "name": "nurture_enrolled",
                            "time": now.isoformat(timespec="seconds"),
                            "properties": {"track": r["nurture_track"]}} for r in batch],
            },
        })
    return requests


def meta_event(lead: dict[str, Any], landing: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
    """'QualifiedLead' for the Conversions API, so ads optimise for leads Sales wants."""
    user_data: dict[str, Any] = {"external_id": [sha256(lead["siren"])]}
    if landing and landing["channel"] == "paid_meta" and landing["click_id"]:
        # fbc = fb.1.<click time in ms>.<fbclid>: ties the conversion to the ad click.
        click_ms = int(datetime.fromisoformat(landing["timestamp"]).timestamp() * 1000)
        user_data["fbc"] = f"fb.1.{click_ms}.{landing['click_id']}"
    return {
        "event_name": "QualifiedLead",
        "event_time": int(now.timestamp()),  # when it was qualified (must be < 7 days old)
        "event_id": f"qualified_{lead['siren']}",  # Meta dedups on event_name + event_id
        "action_source": "system_generated",  # comes from the CRM, not the browser
        "user_data": user_data,
        "custom_data": {"lead_score": lead["Lead_Score__c"], "rating": lead["Rating"],
                        "lead_source": lead["LeadSource"]},
    }


def meta_requests(leads: list[dict[str, Any]], landings: dict[str, dict[str, Any]],
                  now: datetime) -> list[dict[str, Any]]:
    events = [meta_event(l, landings.get(l["siren"]), now) for l in leads]
    return [{"method": "POST", "url": f"{META_API}/{{PIXEL_ID}}/events",
             "params": {"access_token": "{META_ACCESS_TOKEN}"}, "body": {"data": batch}}
            for batch in chunks(events, META_BATCH)]


def run(conn: sqlite3.Connection, out_dir: Path, now: datetime) -> dict[str, int]:
    """Write one JSON file per destination. Returns the number of records in each."""
    rows = lambda sql: [dict(r) for r in conn.execute(sql)]  # noqa: E731
    leads = rows("SELECT * FROM crm_leads ORDER BY Lead_Score__c DESC, siren")
    nurture = rows("SELECT * FROM braze_nurture ORDER BY lead_score DESC, external_id")
    # Landing page of each customer: same anonymousId as their sign-up event.
    landings = {r["siren"]: r for r in rows("""
        SELECT e.siren, w.channel, w.click_id, w.timestamp
        FROM events e JOIN web_events w ON w.anonymous_id = e.anonymous_id
        WHERE w.type = 'page' AND w.name = 'Landing'""")}

    outbox = {
        "salesforce_leads_upsert": salesforce_requests(leads),
        "braze_users_track": braze_requests(nurture, now),
        "meta_conversions_api": meta_requests(leads, landings, now),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, requests in outbox.items():
        (out_dir / f"{name}.json").write_text(json.dumps(requests, indent=2, ensure_ascii=False),
                                              encoding="utf-8")
    meta_events = [e for req in outbox["meta_conversions_api"] for e in req["body"]["data"]]
    counts = {"salesforce": len(leads), "braze": len(nurture), "meta": len(meta_events),
              "meta_with_click_id": sum(1 for e in meta_events if "fbc" in e["user_data"])}
    log.info("outbox (dry run): %s", counts)
    return counts
