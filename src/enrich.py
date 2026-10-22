"""Step 2 - Enrichment.

A sign-up event only carries a SIREN. Look it up in the public API and add the
firmographics Sales needs: sector, headcount, age, city, legal form.
"""
import logging
from datetime import date
from typing import Any

from src.api_client import CompanyApiClient
from src.reference import HEADCOUNT_BRACKETS, LEGAL_FORMS, NAF_DIVISIONS, NAF_SECTIONS

log = logging.getLogger(__name__)

# Fields we expect; anything None after parsing is reported as missing.
CHECKED_FIELDS = ["naf_code", "sector_section", "headcount_code", "creation_date",
                  "city", "legal_form_code"]


def company_age_years(creation_date: str | None, today: date) -> float | None:
    """Age in years (1 decimal) from an ISO date string, or None if unparseable."""
    if not creation_date:
        return None
    try:
        created = date.fromisoformat(creation_date)
    except ValueError:
        return None
    return round((today - created).days / 365.25, 1)


def parse_company(raw: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """Turn one API result into a flat `companies` row. Never raises on missing fields."""
    today = today or date.today()
    siege = raw.get("siege") or {}  # head office

    naf_code = raw.get("activite_principale") or siege.get("activite_principale")
    section = raw.get("section_activite_principale")
    division = naf_code[:2] if naf_code else None
    headcount_code = raw.get("tranche_effectif_salarie")
    headcount_label, headcount_min = HEADCOUNT_BRACKETS.get(headcount_code, (None, None))
    legal_code = raw.get("nature_juridique")
    creation = raw.get("date_creation")

    row = {
        "siren": raw.get("siren"),
        "company_name": raw.get("nom_complet") or raw.get("nom_raison_sociale"),
        "naf_code": naf_code,
        "naf_label": NAF_DIVISIONS.get(division, f"NAF division {division}") if division else None,
        "sector_section": section,
        "sector_label": NAF_SECTIONS.get(section) if section else None,
        "headcount_code": headcount_code,
        "headcount_label": headcount_label,
        "headcount_min": headcount_min,
        "creation_date": creation,
        "company_age_years": company_age_years(creation, today),
        "city": siege.get("libelle_commune"),
        "postal_code": siege.get("code_postal"),
        "legal_form_code": legal_code,
        "legal_form": LEGAL_FORMS.get(legal_code, f"Other ({legal_code})") if legal_code else None,
    }
    missing = [f for f in CHECKED_FIELDS if row[f] is None]
    row["missing_fields"] = ",".join(missing)
    row["enrichment_status"] = "partial" if missing else "ok"
    return row


def failed_row(siren: str, company_name: str) -> dict[str, Any]:
    """Placeholder row when the API gave nothing - keeps the lead in the funnel."""
    row: dict[str, Any] = {k: None for k in (
        "naf_code", "naf_label", "sector_section", "sector_label", "headcount_code",
        "headcount_label", "headcount_min", "creation_date", "company_age_years",
        "city", "postal_code", "legal_form_code", "legal_form")}
    row.update(siren=siren, company_name=company_name,
               missing_fields=",".join(CHECKED_FIELDS), enrichment_status="failed")
    return row


def lookup_siren(client: CompanyApiClient, siren: str) -> dict[str, Any] | None:
    """Search the API by SIREN and return the exact match (not just the first hit)."""
    body = client.get({"q": siren, "page": 1, "per_page": 1}, cache_key=f"siren_{siren}")
    for r in (body or {}).get("results", []):
        if r.get("siren") == siren:
            return r
    return None


def run(client: CompanyApiClient, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enrich every event's company. Returns `companies` rows."""
    rows = []
    for e in events:
        siren, name = e["properties"]["siren"], e["properties"]["company_name"]
        raw = lookup_siren(client, siren)
        if raw is None:
            log.warning("SIREN %s (%s): not found, kept as 'failed'", siren, name)
            rows.append(failed_row(siren, name))
            continue
        row = parse_company(raw)
        if row["missing_fields"]:
            log.info("SIREN %s: missing %s", siren, row["missing_fields"])
        rows.append(row)

    statuses = [r["enrichment_status"] for r in rows]
    log.info("enriched %d companies: %d ok, %d partial, %d failed", len(rows),
             statuses.count("ok"), statuses.count("partial"), statuses.count("failed"))
    return rows
