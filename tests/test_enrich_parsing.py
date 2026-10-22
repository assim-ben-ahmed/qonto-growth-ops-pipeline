"""Enrichment parsing + AI-note validation on fixed API payloads (no network)."""
from datetime import date

from src.ai_notes import template_note, validate_note
from src.enrich import company_age_years, failed_row, parse_company

TODAY = date(2026, 10, 22)

# Trimmed real response from recherche-entreprises.api.gouv.fr
FULL = {
    "siren": "478455793",
    "nom_complet": "BOULANGERIES BG (B B G)",
    "activite_principale": "56.10C",
    "section_activite_principale": "I",
    "tranche_effectif_salarie": "12",
    "date_creation": "2004-08-25",
    "nature_juridique": "5710",
    "siege": {"libelle_commune": "CHATEAURENARD", "code_postal": "13160"},
}


def test_parse_full_payload():
    row = parse_company(FULL, TODAY)
    assert row["siren"] == "478455793"
    assert row["naf_label"] == "Restaurants & bars"
    assert row["sector_label"] == "Hospitality & Food"
    assert (row["headcount_label"], row["headcount_min"]) == ("20-49", 20)
    assert row["legal_form"] == "SAS"
    assert row["city"] == "CHATEAURENARD"
    assert row["company_age_years"] == 22.2
    assert row["enrichment_status"] == "ok"
    assert row["missing_fields"] == ""


def test_parse_missing_fields_is_partial_not_crash():
    raw = {"siren": "123456789", "nom_complet": "ACME", "siege": None,
           "tranche_effectif_salarie": None, "date_creation": None}
    row = parse_company(raw, TODAY)
    assert row["enrichment_status"] == "partial"
    assert "city" in row["missing_fields"]
    assert row["headcount_min"] is None
    assert row["company_age_years"] is None


def test_unknown_codes_get_readable_fallbacks():
    raw = {**FULL, "nature_juridique": "9999", "tranche_effectif_salarie": "XX"}
    row = parse_company(raw, TODAY)
    assert row["legal_form"] == "Other (9999)"
    assert row["headcount_label"] is None


def test_naf_falls_back_to_head_office():
    raw = {**FULL, "activite_principale": None, "siege": {"activite_principale": "62.01Z"}}
    assert parse_company(raw, TODAY)["naf_label"] == "Software & IT consulting"


def test_company_age_handles_bad_dates():
    assert company_age_years("not-a-date", TODAY) is None
    assert company_age_years(None, TODAY) is None
    assert company_age_years("2025-10-22", TODAY) == 1.0


def test_failed_row_keeps_lead_in_funnel():
    row = failed_row("999999999", "GHOST SAS")
    assert row["enrichment_status"] == "failed"
    assert row["company_name"] == "GHOST SAS"


FACTS = {"company": "ACME", "activity": "Restaurants & bars", "employees": "20-49",
         "company_age_years": 8.7, "created": "2018-01-30", "city": "LYON",
         "lead_source": "Paid Search", "plan_chosen": "Smart", "lead_score": 75}


def test_validator_accepts_grounded_note():
    assert validate_note("ACME, a 9-year-old restaurant in Lyon with 20-49 staff: pitch cards.", FACTS) == []
    assert validate_note(template_note(FACTS), FACTS) == []


def test_validator_flags_hallucinations():
    flags = validate_note("ACME made 2 million in revenue, offer 10% discount, open in Paris.", FACTS)
    text = " ".join(flags)
    assert "unknown numbers" in text
    assert "'revenue'" in text and "'discount'" in text and "'%'" in text
    assert "wrong city: 'paris'" in text


def test_validator_whole_words_only():
    assert validate_note("ACME is a nonprofit-style family restaurant.", FACTS) == []
