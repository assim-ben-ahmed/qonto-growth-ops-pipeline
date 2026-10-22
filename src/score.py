"""Step 3 - Lead scoring.

Transparent, rule-based score from 0 to 100. Each of the 4 components is kept
separately so a sales rep can see *why* a lead is hot. All weights are in config.yaml.
"""
from dataclasses import dataclass
from typing import Any


@dataclass
class ScoreResult:
    headcount: int
    age: int
    sector: int
    channel: int

    @property
    def total(self) -> int:
        return self.headcount + self.age + self.sector + self.channel


def band_points(value: float | None, bands: list[list[float]], unknown: int) -> int:
    """Points of the highest band whose minimum is <= value.

    bands = [[0, 5], [10, 30], [50, 35]] and value 12 -> 30.
    """
    if value is None:
        return unknown
    points = unknown
    for minimum, pts in sorted(bands):
        if value >= minimum:
            points = int(pts)
    return points


def score_lead(company: dict[str, Any], channel: str, rules: dict[str, Any]) -> ScoreResult:
    """Score one enriched company coming from a given acquisition channel."""
    return ScoreResult(
        headcount=band_points(company.get("headcount_min"), rules["headcount_bands"],
                              rules["headcount_unknown"]),
        age=band_points(company.get("company_age_years"), rules["age_bands"],
                        rules["age_unknown"]),
        sector=rules["sector_points"].get(company.get("sector_section"), rules["sector_default"]),
        channel=rules["channel_points"].get(channel, 0),
    )
