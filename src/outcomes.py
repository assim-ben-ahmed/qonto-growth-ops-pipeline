"""Step 3b - Score validation.

A score is only useful if high scores actually convert. We have no real CRM
history, so we simulate one: each sign-up gets a hidden "true" conversion
probability (active, paying customer within 60 days) and a coin flip decides
the outcome. The score never sees this hidden model.

The hidden model deliberately disagrees with the scoring rules in a few places
(e.g. brand-new businesses convert well, referral is weaker than assumed), so
the validation has something to find - exactly what a real backtest is for.
"""
import logging
import math
import random
from typing import Any

log = logging.getLogger(__name__)

# "Reality" (log-odds). Pretend nobody knows these numbers.
BASE = -1.1
HEADCOUNT_EFFECT = [(0, -0.6), (1, 0.0), (10, 0.6), (50, 0.8), (250, 0.3)]  # [min, effect]
NEW_BUSINESS_EFFECT = 1.2       # < 1 year old: they need an account to deposit their capital
CHANNEL_EFFECT = {"partner_accountant": 1.0, "paid_google": 0.5, "referral": 0.2,
                  "seo": 0.1, "paid_meta": -0.3}
SECTOR_EFFECT = {"J": 0.3, "M": 0.3, "I": -0.3}


def true_probability(company: dict[str, Any], channel: str) -> float:
    """Hidden conversion probability of one sign-up (logistic of the effects above)."""
    logit = BASE
    headcount = company.get("headcount_min")
    if headcount is not None:
        logit += [e for m, e in HEADCOUNT_EFFECT if headcount >= m][-1]  # highest band reached
    age = company.get("company_age_years")
    if age is not None and age < 1:
        logit += NEW_BUSINESS_EFFECT
    logit += CHANNEL_EFFECT.get(channel, 0.0) + SECTOR_EFFECT.get(company.get("sector_section"), 0.0)
    return 1 / (1 + math.exp(-logit))


def auc(scores: list[float], labels: list[int]) -> float | None:
    """Chance that a random converter scored higher than a random non-converter.

    0.5 = the score is a coin flip, 1.0 = perfect ranking. Ties count as half.
    """
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def run(events: list[dict[str, Any]], companies: dict[str, dict[str, Any]],
        cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """One simulated outcome per sign-up -> `outcomes` rows."""
    rng = random.Random(cfg["run"]["random_seed"] + 2)
    rows = []
    for e in events:
        p = e["properties"]
        prob = true_probability(companies[p["siren"]], p["source_channel"])
        rows.append({"siren": p["siren"], "converted": int(rng.random() < prob),
                     "true_probability": round(prob, 3)})
    log.info("simulated outcomes: %d of %d sign-ups converted",
             sum(r["converted"] for r in rows), len(rows))
    return rows
