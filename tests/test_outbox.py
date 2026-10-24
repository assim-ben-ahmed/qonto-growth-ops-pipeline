"""Integration payloads: the shape each real API expects (no network)."""
from datetime import datetime, timezone

from src.outbox import (BRAZE_BATCH, SALESFORCE_BATCH, braze_requests, meta_event,
                        salesforce_requests, sha256)

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def lead(siren: str = "123456789", flags: str = "") -> dict:
    return {"siren": siren, "Company": "ACME", "Industry": "IT & Telecom", "NumberOfEmployees": 10,
            "LeadSource": "Paid Social", "Rating": "Hot", "Status": "Open - Not Contacted",
            "City": "LYON", "Lead_Score__c": 88, "OwnerQueue": "SMB_Outbound",
            "Sales_Note__c": "ACME, 10 people in Lyon.", "Note_Flags__c": flags}


def test_salesforce_upserts_on_external_id_in_batches_of_200():
    reqs = salesforce_requests([lead(str(i)) for i in range(SALESFORCE_BATCH + 1)])
    assert len(reqs) == 2
    assert reqs[0]["method"] == "PATCH" and reqs[0]["url"].endswith("/Lead/SIREN__c")
    assert len(reqs[0]["body"]["records"]) == SALESFORCE_BATCH
    assert reqs[0]["body"]["records"][0]["SIREN__c"] == "0"


def test_flagged_note_is_not_sent_to_salesforce():
    record = salesforce_requests([lead(flags="unsupported claim: 'revenue'")])[0]["body"]["records"][0]
    assert record["Sales_Note__c"] is None
    assert record["Note_Needs_Review__c"] is True


def test_braze_batches_attributes_and_events_together():
    rows = [{"external_id": str(i), "company_name": "X", "industry": "Y", "city": "Z", "lead_score": 40,
             "source_channel": "seo", "plan_chosen": "Basic", "nurture_track": "solo_founder_tips"}
            for i in range(BRAZE_BATCH + 5)]
    reqs = braze_requests(rows, NOW)
    assert [len(r["body"]["attributes"]) for r in reqs] == [BRAZE_BATCH, 5]
    assert reqs[1]["body"]["events"][0] == {"external_id": "75", "name": "nurture_enrolled",
                                            "time": NOW.isoformat(timespec="seconds"),
                                            "properties": {"track": "solo_founder_tips"}}


def test_meta_event_hashes_ids_and_adds_fbc_only_for_meta_clicks():
    meta_click = {"channel": "paid_meta", "click_id": "abc123", "timestamp": "2026-10-20T10:00:00+00:00"}
    event = meta_event(lead(), meta_click, NOW)
    assert event["user_data"]["external_id"] == [sha256("123456789")]
    assert "123456789" not in str(event["user_data"])  # never the raw identifier
    assert event["user_data"]["fbc"].startswith("fb.1.") and event["user_data"]["fbc"].endswith(".abc123")

    google_click = {"channel": "paid_google", "click_id": "xyz", "timestamp": "2026-10-20T10:00:00+00:00"}
    assert "fbc" not in meta_event(lead(), google_click, NOW)["user_data"]
