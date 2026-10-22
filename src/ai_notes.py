"""Step 5 - AI sales notes.

For each hot lead, ask an LLM (Mistral) for a one-line note a sales rep can read
before calling. Without MISTRAL_API_KEY, a template is used instead.

Every note - LLM or template - goes through `validate_note`, which flags
anything that is not backed by the enriched data (invented numbers, revenue,
funding, other cities...). Flagged notes are kept but marked for review.
"""
import hashlib
import json
import logging
import os
import re
import time
from typing import Any

import requests

from src.config import CACHE_DIR

log = logging.getLogger(__name__)

NOTES_CACHE = CACHE_DIR / "ai_notes"

# Things we never have in the data, so any mention is invented.
UNSUPPORTED_TERMS = ["revenue", "turnover", "chiffre d'affaires", "funding", "raised", "investor",
                     "million", "profit", "growth rate", "fast-growing", "award", "founded by",
                     "ceo", "discount", "free months"]
UNSUPPORTED_SYMBOLS = ["€", "$", "%"]
# Big French cities: flagged if mentioned but not the lead's own city.
MAJOR_CITIES = ["paris", "lyon", "marseille", "toulouse", "nice", "nantes", "strasbourg",
                "montpellier", "bordeaux", "lille", "rennes", "reims", "grenoble", "dijon"]

SYSTEM_PROMPT = (
    "You write one-line notes for B2B sales reps at Qonto, a French business bank. "
    "Use ONLY the facts given. Never invent numbers, revenue, funding, clients or locations. "
    "Max 30 words, English, plain text (no markdown, quotes or emojis). Suggest one relevant Qonto angle "
    "(e.g. invoicing, expense cards, multi-user access, accountant integration)."
)


def lead_facts(lead: dict[str, Any], company: dict[str, Any], plan: str) -> dict[str, Any]:
    """The only facts the LLM is allowed to use."""
    return {
        "company": company["company_name"],
        "sector": company["sector_label"],
        "activity": company["naf_label"],
        "employees": company["headcount_label"],
        "company_age_years": company["company_age_years"],
        "created": company["creation_date"],
        "city": company["city"],
        "legal_form": company["legal_form"],
        "lead_source": lead["LeadSource"],
        "plan_chosen": plan,
        "lead_score": lead["Lead_Score__c"],
    }


def template_note(facts: dict[str, Any]) -> str:
    """Deterministic fallback note - safe by construction."""
    return (f"{facts['company']} ({facts['activity']}, {facts['employees']} employees, "
            f"{facts['company_age_years']} yrs old) came via {facts['lead_source']} on the "
            f"{facts['plan_chosen']} plan - lead with multi-user access and expense cards.")


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", text.replace(",", ".")))


def validate_note(note: str, facts: dict[str, Any]) -> list[str]:
    """Return a list of problems; empty list = the note only uses known facts."""
    flags = []
    facts_text = json.dumps(facts, ensure_ascii=False).lower()
    allowed = _numbers(facts_text)
    age = facts.get("company_age_years")
    if age is not None:  # "about 9 years" is fine for 8.7
        allowed |= {str(int(age)), str(round(age))}

    invented = sorted(_numbers(note) - allowed)
    if invented:
        flags.append(f"unknown numbers: {', '.join(invented)}")
    low = note.lower()
    for term in UNSUPPORTED_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", low):  # whole word: "nonprofit" != "profit"
            flags.append(f"unsupported claim: '{term}'")
    for symbol in UNSUPPORTED_SYMBOLS:
        if symbol in note:
            flags.append(f"unsupported claim: '{symbol}'")
    own_city = (facts.get("city") or "").lower()
    for city in MAJOR_CITIES:
        if re.search(rf"\b{city}\b", low) and city not in own_city:
            flags.append(f"wrong city: '{city}'")
    if len(note.split()) > 40 or "\n" in note.strip():
        flags.append("not a one-liner")
    return flags


class MistralNoteWriter:
    """Calls Mistral's chat API with rate limiting, retries and a per-lead cache."""

    def __init__(self, api_key: str, cfg: dict[str, Any]) -> None:
        self.api_key = api_key
        self.model = cfg["model"]
        self.url = cfg["api_url"]
        self.min_interval = 1.0 / cfg["max_requests_per_second"]
        self._last_call = 0.0
        NOTES_CACHE.mkdir(parents=True, exist_ok=True)

    def write(self, facts: dict[str, Any]) -> str:
        # Cache key includes model + prompt + facts: change any of them -> new note.
        key = hashlib.sha1(json.dumps([self.model, SYSTEM_PROMPT, facts],
                                      sort_keys=True, default=str).encode()).hexdigest()[:16]
        path = NOTES_CACHE / f"{key}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")

        payload = {"model": self.model, "temperature": 0.2, "max_tokens": 80, "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Facts: " + json.dumps(facts, ensure_ascii=False, default=str)},
        ]}
        for attempt in range(1, 4):
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            resp = requests.post(self.url, json=payload, timeout=30,
                                 headers={"Authorization": f"Bearer {self.api_key}"})
            if resp.status_code == 429 or resp.status_code >= 500:
                log.warning("Mistral HTTP %d (attempt %d/3), backing off", resp.status_code, attempt)
                time.sleep(2 * attempt)  # 2s, 4s
                continue
            resp.raise_for_status()
            note = resp.json()["choices"][0]["message"]["content"]
            note = note.replace("*", "").strip().strip('"')
            path.write_text(note, encoding="utf-8")
            return note
        raise RuntimeError("Mistral API kept failing")


def run(leads: list[dict[str, Any]], companies: dict[str, dict[str, Any]],
        plans: dict[str, str], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Add Sales_Note__c / Note_Source__c / Note_Flags__c to each CRM lead."""
    api_key = os.getenv("MISTRAL_API_KEY", "").strip()
    writer = MistralNoteWriter(api_key, cfg["ai"]) if api_key else None
    if writer is None:
        log.warning("MISTRAL_API_KEY not set - using template notes")

    leads = sorted(leads, key=lambda l: -l["Lead_Score__c"])
    for i, lead in enumerate(leads):
        facts = lead_facts(lead, companies[lead["siren"]], plans[lead["siren"]])
        source = "template"
        note = template_note(facts)
        if writer and i < cfg["ai"]["max_notes"]:
            try:
                note, source = writer.write(facts), "llm"
            except (requests.RequestException, RuntimeError, KeyError) as exc:
                # Circuit breaker: one hard failure = stop calling the LLM for this run.
                log.error("LLM failed (%s) - template notes for the remaining leads", exc)
                writer = None
        flags = validate_note(note, facts)
        if flags:
            log.warning("note for %s flagged: %s", facts["company"], "; ".join(flags))
        lead.update(Sales_Note__c=note, Note_Source__c=source, Note_Flags__c="; ".join(flags))

    n_flagged = sum(1 for l in leads if l["Note_Flags__c"])
    log.info("wrote %d notes (%d by LLM), %d flagged for review", len(leads),
             sum(1 for l in leads if l["Note_Source__c"] == "llm"), n_flagged)
    return leads
