"""Step 1b - Website tracking.

What Segment's web SDK would have collected *before* each sign-up:
- `page` calls (landing page with UTMs + ad click id, then the pricing page),
- a `track` "Signup Started" when the sign-up form is opened,
- an `identify` call at sign-up that ties the anonymous visitor to the new
  account (identity stitching: anonymousId -> userId).
Visitors who left before signing up are simulated too, so we can build a funnel.
"""
import json
import logging
import random
import uuid
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.config import RAW_DIR

log = logging.getLogger(__name__)

LANDING_PAGES = {
    "paid_meta": "/lp/compte-pro-independants",
    "paid_google": "/lp/compte-bancaire-professionnel",
    "seo": "/blog/ouvrir-un-compte-pro",
    "partner_accountant": "/partenaires/experts-comptables",
    "referral": "/parrainage",
}
PRICING_PAGE = "/tarifs"
CLICK_ID_PARAM = {"paid_meta": "fbclid", "paid_google": "gclid"}  # added to the URL by the ad network


def channel_from_utm(utm_source: str | None, utm_medium: str | None,
                     channels: dict[str, Any]) -> str:
    """Attribution: map a visit's UTM tags back to a channel name (else 'direct')."""
    for name, c in channels.items():
        if (c["utm_source"], c["utm_medium"]) == (utm_source, utm_medium):
            return name
    return "direct"


def _base(call_type: str, anonymous_id: str, ts: datetime, rng: random.Random) -> dict[str, Any]:
    return {"type": call_type, "messageId": str(uuid.UUID(int=rng.getrandbits(128))),
            "anonymousId": anonymous_id, "timestamp": ts.isoformat(timespec="seconds")}


def page_call(anonymous_id: str, ts: datetime, name: str, path: str, channel: str,
              cfg: dict[str, Any], rng: random.Random, click_id: str | None = None) -> dict[str, Any]:
    """A Segment page call. Landing pages carry the UTMs (and click id) in the URL."""
    utm = cfg["channels"][channel]
    url = cfg["tracking"]["site_url"] + path
    if name == "Landing":
        url += (f"?utm_source={utm['utm_source']}&utm_medium={utm['utm_medium']}"
                f"&utm_campaign={utm['utm_campaign']}")
        if click_id:
            url += f"&{CLICK_ID_PARAM[channel]}={click_id}"
    return {**_base("page", anonymous_id, ts, rng), "name": name,
            "properties": {"path": path, "url": url},
            "context": {"campaign": {"source": utm["utm_source"], "medium": utm["utm_medium"],
                                     "name": utm["utm_campaign"]}}}


def signup_started(anonymous_id: str, ts: datetime, rng: random.Random) -> dict[str, Any]:
    return {**_base("track", anonymous_id, ts, rng), "event": "Signup Started",
            "properties": {"path": "/signup"}}


def visit(anonymous_id: str, channel: str, start: datetime, cfg: dict[str, Any],
          rng: random.Random, pricing: bool, started: bool) -> list[dict[str, Any]]:
    """Landing page, then optionally pricing, then optionally 'Signup Started'."""
    click_id = uuid.UUID(int=rng.getrandbits(128)).hex[:16] if channel in CLICK_ID_PARAM else None
    calls = [page_call(anonymous_id, start, "Landing", LANDING_PAGES[channel], channel, cfg, rng, click_id)]
    ts = start
    if pricing:
        ts += timedelta(seconds=rng.randint(20, 600))
        calls.append(page_call(anonymous_id, ts, "Pricing", PRICING_PAGE, channel, cfg, rng))
        if started:
            ts += timedelta(seconds=rng.randint(30, 900))
            calls.append(signup_started(anonymous_id, ts, rng))
    return calls


def signup_journey(signup: dict[str, Any], cfg: dict[str, Any],
                   rng: random.Random) -> list[dict[str, Any]]:
    """Everything one customer did on the site, ending with identify + 'Account Signed Up'."""
    signed_up_at = datetime.fromisoformat(signup["timestamp"])
    channel = signup["properties"]["source_channel"]
    # First visit between 1 hour and 7 days before the sign-up; form opened a few minutes before.
    first_visit = signed_up_at - timedelta(seconds=rng.randint(3600, 7 * 86400))
    calls = visit(signup["anonymousId"], channel, first_visit, cfg, rng, pricing=True, started=False)
    calls.append(signup_started(signup["anonymousId"],
                                signed_up_at - timedelta(seconds=rng.randint(120, 900)), rng))
    identify = {**_base("identify", signup["anonymousId"], signed_up_at, rng),
                "userId": signup["userId"],
                "traits": {"company_name": signup["properties"]["company_name"],
                           "siren": signup["properties"]["siren"],
                           "plan": signup["properties"]["plan_chosen"]}}
    return calls + [identify, signup]


def dropoff_visitors(signups: list[dict[str, Any]], cfg: dict[str, Any], rng: random.Random,
                     now: datetime) -> list[dict[str, Any]]:
    """Visitors who never signed up. How many depends on the channel (see config.yaml)."""
    t = cfg["tracking"]
    window = cfg["run"]["signup_window_days"] * 86400
    calls = []
    for channel, per_signup in t["dropoffs_per_signup"].items():
        n_signups = sum(1 for s in signups if s["properties"]["source_channel"] == channel)
        for _ in range(round(n_signups * per_signup)):
            pricing = rng.random() < t["pricing_view_rate"]
            started = rng.random() < t["signup_start_rate"]
            anonymous_id = str(uuid.UUID(int=rng.getrandbits(128)))
            start = now - timedelta(seconds=rng.randint(0, window))
            calls += visit(anonymous_id, channel, start, cfg, rng, pricing, started)
    return calls


def to_row(call: dict[str, Any], channels: dict[str, Any]) -> dict[str, Any]:
    """Flatten any Segment call into the `web_events` table shape."""
    campaign = call.get("context", {}).get("campaign", {})
    props = call.get("properties", {})
    query = parse_qs(urlparse(props.get("url", "")).query)
    click_id = (query.get("fbclid") or query.get("gclid") or [None])[0]
    return {
        "message_id": call["messageId"],
        "type": call["type"],
        "name": call.get("name") or call.get("event") or call["type"],
        "anonymous_id": call["anonymousId"],
        "user_id": call.get("userId"),
        "timestamp": call["timestamp"],
        "path": props.get("path"),
        "utm_source": campaign.get("source"),
        "utm_medium": campaign.get("medium"),
        "channel": channel_from_utm(campaign.get("source"), campaign.get("medium"), channels)
                   if campaign else None,
        "click_id": click_id,
    }


def run(signups: list[dict[str, Any]], cfg: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    """Build the full Segment stream (journeys + drop-offs), save it as JSON lines."""
    rng = random.Random(cfg["run"]["random_seed"] + 1)  # own seed: sign-up events stay unchanged
    calls = [c for s in signups for c in signup_journey(s, cfg, rng)]
    calls += dropoff_visitors(signups, cfg, rng, now)
    calls.sort(key=lambda c: c["timestamp"])

    out = RAW_DIR / "web_events.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for c in calls:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    visitors = len({c["anonymousId"] for c in calls})
    log.info("wrote %d Segment calls from %d visitors to %s", len(calls), visitors, out.name)
    return calls
