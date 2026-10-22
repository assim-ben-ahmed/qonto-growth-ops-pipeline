"""Step 1 - Sign-up events.

Pull real French SMEs from the public API, then simulate one "Account Signed Up"
event per company in Segment's track-event format (what Segment would forward
to the warehouse when a new customer finishes onboarding).
"""
import json
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from src.api_client import CompanyApiClient
from src.config import RAW_DIR

log = logging.getLogger(__name__)

PER_PAGE = 25  # API maximum


def fetch_companies(client: CompanyApiClient, cfg: dict[str, Any]) -> list[dict[str, str]]:
    """Return ~n_companies unique {siren, company_name}, spread evenly across search terms."""
    terms = cfg["ingest"]["search_terms"]
    target = cfg["run"]["n_companies"]
    per_term = -(-target // len(terms))  # ceiling division
    seen: dict[str, str] = {}

    for term in terms:
        found_for_term, page = 0, 1
        while found_for_term < per_term and page <= 5:
            params = {"q": term, "page": page, "per_page": PER_PAGE, **cfg["ingest"]["filters"]}
            body = client.get(params, cache_key=f"search_{term}_p{page}")
            results = (body or {}).get("results", [])
            if not results:
                break
            for r in results:
                if r["siren"] not in seen and found_for_term < per_term:
                    seen[r["siren"]] = r.get("nom_complet") or r.get("nom_raison_sociale") or ""
                    found_for_term += 1
            page += 1
        log.info("search '%s': %d companies", term, found_for_term)

    companies = [{"siren": s, "company_name": n} for s, n in seen.items()]
    return companies[:target]


def make_signup_event(company: dict[str, str], cfg: dict[str, Any],
                      rng: random.Random, now: datetime) -> dict[str, Any]:
    """Build one Segment track event for a company sign-up."""
    channels = cfg["channels"]
    channel = rng.choices(list(channels), weights=[c["weight"] for c in channels.values()])[0]
    plan = rng.choices(list(cfg["plans"]), weights=list(cfg["plans"].values()))[0]
    ts = now - timedelta(seconds=rng.randint(0, cfg["run"]["signup_window_days"] * 86400))
    utm = channels[channel]

    return {
        "type": "track",
        "event": "Account Signed Up",
        "messageId": str(uuid.UUID(int=rng.getrandbits(128))),
        "anonymousId": str(uuid.UUID(int=rng.getrandbits(128))),
        "timestamp": ts.isoformat(timespec="seconds"),
        "properties": {
            "siren": company["siren"],
            "company_name": company["company_name"],
            "source_channel": channel,
            "utm_source": utm["utm_source"],
            "utm_medium": utm["utm_medium"],
            "utm_campaign": utm["utm_campaign"],
            "plan_chosen": plan,
        },
    }


def event_to_row(e: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Segment event into the `events` table shape."""
    p = e["properties"]
    return {"message_id": e["messageId"], "anonymous_id": e["anonymousId"], "event": e["event"],
            "timestamp": e["timestamp"], **{k: p[k] for k in (
                "siren", "company_name", "source_channel", "utm_source",
                "utm_medium", "utm_campaign", "plan_chosen")}}


def load_events() -> list[dict[str, Any]]:
    """Read back the events written by the last ingest run (for running later stages alone)."""
    with open(RAW_DIR / "signup_events.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def run(client: CompanyApiClient, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch companies, generate events, save them as JSON lines. Returns the events."""
    companies = fetch_companies(client, cfg)
    rng = random.Random(cfg["run"]["random_seed"])
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    events = [make_signup_event(c, cfg, rng, now) for c in companies]

    out = RAW_DIR / "signup_events.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    log.info("wrote %d sign-up events to %s", len(events), out.name)
    return events
