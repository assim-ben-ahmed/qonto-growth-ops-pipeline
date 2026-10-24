"""Website tracking, ingest filters, score validation and routing helpers (no network)."""
import random
from datetime import date, datetime, timezone

from src.config import load_config
from src.ingest import keep_result, make_signup_event
from src.outcomes import auc, true_probability
from src.route import carry_over_notes, nurture_track, owner_queue
from src.tracking import channel_from_utm, dropoff_visitors, signup_journey, to_row

CFG = load_config()
NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def signup(channel: str = "paid_meta") -> dict:
    event = make_signup_event({"siren": "123456789", "company_name": "ACME"}, CFG, random.Random(1), NOW)
    event["properties"]["source_channel"] = channel
    return event


# ---------- tracking ----------
def test_journey_is_one_visitor_ending_with_identify_then_signup():
    s = signup()
    calls = signup_journey(s, CFG, random.Random(2))
    assert {c["anonymousId"] for c in calls} == {s["anonymousId"]}
    assert [c["type"] for c in calls[-2:]] == ["identify", "track"]
    assert calls[-2]["userId"] == s["userId"] == "org_123456789"
    assert [c["timestamp"] for c in calls] == sorted(c["timestamp"] for c in calls)


def test_meta_landing_page_carries_utms_and_click_id():
    landing = signup_journey(signup("paid_meta"), CFG, random.Random(2))[0]
    row = to_row(landing, CFG["channels"])
    assert "utm_source=facebook" in landing["properties"]["url"]
    assert row["channel"] == "paid_meta"
    assert row["click_id"] and f"fbclid={row['click_id']}" in landing["properties"]["url"]


def test_dropoffs_never_identify_or_sign_up():
    calls = dropoff_visitors([signup("seo")] * 10, CFG, random.Random(3), NOW)
    assert calls
    assert not any(c["type"] == "identify" or c.get("event") == "Account Signed Up" for c in calls)


def test_channel_from_utm_falls_back_to_direct():
    assert channel_from_utm("google", "cpc", CFG["channels"]) == "paid_google"
    assert channel_from_utm("google", "organic", CFG["channels"]) == "seo"
    assert channel_from_utm("newsletter", "email", CFG["channels"]) == "direct"


# ---------- ingest filters ----------
def test_keep_result_excludes_sole_traders_and_old_companies():
    new = {"max_age_days": 365}
    today = date(2026, 10, 22)
    assert keep_result({"nature_juridique": "5710", "date_creation": "2026-03-01"}, new, ["1000"], today)
    assert not keep_result({"nature_juridique": "1000", "date_creation": "2026-03-01"}, new, ["1000"], today)
    assert not keep_result({"nature_juridique": "5710", "date_creation": "2019-03-01"}, new, ["1000"], today)
    assert not keep_result({"nature_juridique": "5710", "date_creation": None}, new, ["1000"], today)
    assert keep_result({"nature_juridique": "5710", "date_creation": None}, {}, ["1000"], today)


# ---------- score validation ----------
def test_auc_perfect_random_and_reversed():
    assert auc([90, 80, 20, 10], [1, 1, 0, 0]) == 1.0
    assert auc([10, 20, 80, 90], [1, 1, 0, 0]) == 0.0
    assert auc([50, 50, 50, 50], [1, 0, 1, 0]) == 0.5  # ties count as half
    assert auc([50, 60], [1, 1]) is None                # needs both classes


def test_true_probability_uses_highest_headcount_band():
    small = true_probability({"headcount_min": 10}, "seo")
    large = true_probability({"headcount_min": 250}, "seo")
    assert 0 < large < small < 1  # 250+ band (0.3) is below the 10-49 band (0.6)


# ---------- routing ----------
def test_owner_queue_and_nurture_track():
    assert owner_queue({"headcount_min": 100}, "partner_accountant", CFG) == "Partnerships"
    assert owner_queue({"headcount_min": 100}, "seo", CFG) == "MidMarket_AE"
    assert owner_queue({"headcount_min": None}, "seo", CFG) == "SMB_Outbound"
    assert nurture_track({"company_age_years": 0.4, "headcount_min": 0}) == "new_business_onboarding"
    assert nurture_track({"company_age_years": 5, "headcount_min": 0}) == "solo_founder_tips"


def test_rescoring_keeps_existing_notes():
    new_rows = [{"siren": "1", "Sales_Note__c": None}, {"siren": "2", "Sales_Note__c": None}]
    old = {"1": {"Sales_Note__c": "Call them", "Note_Source__c": "llm", "Note_Flags__c": ""}}
    assert carry_over_notes(new_rows, old) == 1
    assert new_rows[0]["Sales_Note__c"] == "Call them"
    assert new_rows[1]["Sales_Note__c"] is None
