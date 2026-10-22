"""Scoring rules: these tests double as documentation of the score."""
import pytest

from src.config import load_config
from src.score import band_points, score_lead

RULES = load_config()["scoring"]


@pytest.mark.parametrize("value,expected", [
    (None, 5),   # unknown headcount
    (0, 5),      # non-employer
    (3, 15),     # 1-9 employees
    (10, 30),    # 10-49
    (50, 35),    # 50-249: sweet spot
    (500, 20),   # large company, less of a fit
])
def test_headcount_bands(value, expected):
    assert band_points(value, RULES["headcount_bands"], RULES["headcount_unknown"]) == expected


def test_band_lower_bound_is_inclusive():
    assert band_points(1.0, RULES["age_bands"], RULES["age_unknown"]) == 15
    assert band_points(0.99, RULES["age_bands"], RULES["age_unknown"]) == 10


def test_ideal_lead_scores_100():
    company = {"headcount_min": 50, "company_age_years": 5.0, "sector_section": "J"}
    result = score_lead(company, "partner_accountant", RULES)
    assert (result.headcount, result.age, result.sector, result.channel) == (35, 25, 20, 20)
    assert result.total == 100


def test_unknown_company_still_gets_a_score():
    """A failed enrichment must not crash scoring: it gets the 'unknown' points."""
    result = score_lead({}, "paid_meta", RULES)
    assert result.total == 5 + 5 + 5 + 5
    assert result.total < RULES["threshold"]


def test_unknown_sector_and_channel_use_defaults():
    company = {"headcount_min": 10, "company_age_years": 4, "sector_section": "Z"}
    result = score_lead(company, "tiktok", RULES)
    assert result.sector == RULES["sector_default"]
    assert result.channel == 0
