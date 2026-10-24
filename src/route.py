"""Step 4 - Routing.

Score >= threshold -> Salesforce-like Lead (for the Sales team to call).
Score <  threshold -> Braze user import (automated nurture emails / push).
"""
import csv
import logging
from pathlib import Path
from typing import Any

from src.score import score_lead

log = logging.getLogger(__name__)


def owner_queue(company: dict[str, Any], channel: str, cfg: dict[str, Any]) -> str:
    """Which Sales queue owns the lead: partners first, then size."""
    if channel == "partner_accountant":
        return "Partnerships"
    if (company.get("headcount_min") or 0) >= cfg["routing"]["midmarket_min_headcount"]:
        return "MidMarket_AE"
    return "SMB_Outbound"


def nurture_track(company: dict[str, Any]) -> str:
    """Pick a Braze nurture journey (used as a custom attribute to trigger a Canvas)."""
    if (company.get("company_age_years") or 99) < 1:
        return "new_business_onboarding"
    if (company.get("headcount_min") or 0) == 0:
        return "solo_founder_tips"
    return "team_features_upsell"


def run(events: list[dict[str, Any]], companies: dict[str, dict[str, Any]],
        cfg: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Score every sign-up and split into CRM leads and Braze nurture rows."""
    rules = cfg["scoring"]
    scored, crm, braze = [], [], []

    for e in events:
        p = e["properties"]
        company, channel = companies[p["siren"]], p["source_channel"]
        s = score_lead(company, channel, rules)
        is_hot = s.total >= rules["threshold"]
        scored.append({"siren": p["siren"], "message_id": e["messageId"], "score": s.total,
                       "pts_headcount": s.headcount, "pts_age": s.age, "pts_sector": s.sector,
                       "pts_channel": s.channel, "routed_to": "crm" if is_hot else "braze"})

        if is_hot:
            crm.append({
                "siren": p["siren"],
                "Company": company["company_name"],
                "Industry": company["sector_label"],
                "NumberOfEmployees": company["headcount_min"],  # lower bound of INSEE bracket
                "LeadSource": cfg["routing"]["lead_source_map"][channel],
                "Rating": "Hot" if s.total >= rules["hot_rating_threshold"] else "Warm",
                "OwnerQueue": owner_queue(company, channel, cfg),
                "Lead_Score__c": s.total,
                "City": company["city"],
                "Status": "Open - Not Contacted",
                "Sales_Note__c": None, "Note_Source__c": None, "Note_Flags__c": None,
            })
        else:
            braze.append({
                "external_id": p["siren"],  # in prod: Qonto's internal user/org id
                "company_name": company["company_name"],
                "industry": company["sector_label"],
                "city": company["city"],
                "lead_score": s.total,
                "source_channel": channel,
                "plan_chosen": p["plan_chosen"],
                "nurture_track": nurture_track(company),
            })

    log.info("scored %d sign-ups: %d -> CRM (threshold %d), %d -> Braze nurture",
             len(scored), len(crm), rules["threshold"], len(braze))
    return {"scored_leads": scored, "crm_leads": crm, "braze_nurture": braze}


def carry_over_notes(crm_rows: list[dict[str, Any]],
                     old_notes: dict[str, dict[str, Any]]) -> int:
    """Keep the AI notes of leads that are still in the CRM after re-scoring.

    Without this, re-running only the score stage would wipe every note.
    Returns how many notes were kept.
    """
    kept = 0
    for row in crm_rows:
        old = old_notes.get(row["siren"])
        if old and old["Sales_Note__c"]:
            row.update({k: old[k] for k in ("Sales_Note__c", "Note_Source__c", "Note_Flags__c")})
            kept += 1
    return kept


def write_braze_csv(rows: list[dict[str, Any]], path: Path) -> None:
    """Braze user CSV import format: `external_id` column + one column per custom attribute."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    log.info("wrote %d rows to %s", len(rows), path.name)
