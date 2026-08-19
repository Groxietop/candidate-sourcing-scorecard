"""Experimental scorer: three separate axes instead of one blended number.

Read EXPERIMENTAL_SCORING.md first — this is the code form of that doc.
This module is deliberately independent of scoring.py (the traditional,
single-score pass): nothing here is imported by cli.py, and nothing in
scoring.py is changed. Run both against the same req/candidates and use
compare_passes.py to see how the results differ — that comparison is the
point, so the traditional pass is left exactly as it was, relocation
penalty and all.

The three axes:

  Foundation  — objective fit (skill match + experience). The only axis
                that gates "qualified". Reused directly from scoring.py.
  Bonus       — reward-only positive signals. Floor 0, never subtracts.
                Missing data contributes 0, not a penalty.
  Momentum    — reward-only trajectory/potential signals. Same floor-at-0
                philosophy as Bonus, kept as a separate axis because it
                measures a different thing: rate of change, not level.

Location is deliberately NOT a gating factor anywhere in this module — see
"the relocation fix" in EXPERIMENTAL_SCORING.md. It only ever contributes a
small bonus for candidates who already happen to be local.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .candidate import Candidate
from .config import Req
from .scoring import _experience, _recency, _skill_match, _tokenize_location

FOUNDATION_WEIGHTS = {"skill_match": 60, "experience": 40}

GITHUB_BONUS_WEIGHTS = {"breadth": 25, "activity": 25, "docs": 20, "traction": 20, "location": 10}
LINKEDIN_BONUS_WEIGHTS = {
    "certifications": 20,
    "open_source": 15,
    "volunteer": 15,
    "education": 15,
    "location": 15,
    "availability": 20,
}

GITHUB_MOMENTUM_WEIGHTS = {"acceleration": 60, "traction_per_tenure": 40}
LINKEDIN_MOMENTUM_WEIGHTS = {"title_velocity": 100}

# Rough, illustrative years-to-title benchmarks for the LinkedIn momentum
# signal. NOT a validated industry norm — "senior" means very different
# things at different companies. Checked in title-substring order, most
# senior first, so "Senior Director" matches "director" not "senior".
_TITLE_BENCHMARK_YEARS = [
    ("vp", 14),
    ("director", 12),
    ("head", 12),
    ("principal", 10),
    ("staff", 8),
    ("lead", 6),
    ("manager", 6),
    ("senior", 5),
]

_ADVANCED_DEGREES = {"ms", "msc", "m.s.", "phd", "ph.d.", "md", "jd"}


@dataclass
class ExperimentalScoreResult:
    candidate: Candidate
    foundation: float
    bonus: float
    momentum: float
    matched_skills: list[str]
    qualified: bool
    reasons: list[str] = field(default_factory=list)

    def as_row(self) -> dict:
        return {
            "name": self.candidate.name,
            "source": self.candidate.source,
            "foundation": round(self.foundation, 1),
            "bonus": round(self.bonus, 1),
            "momentum": round(self.momentum, 1),
            "qualified": self.qualified,
            "matched_skills": ";".join(self.matched_skills),
            "profile_url": self.candidate.profile_url,
            "reasons": " | ".join(self.reasons),
        }


def _location_bonus(candidate: Candidate, req: Req) -> float:
    """Reward-only: 1.0 if the candidate already happens to be local, else
    0.0. Never a penalty — a non-local candidate might relocate, work
    remote, or the req might not care. See EXPERIMENTAL_SCORING.md.
    """
    if not candidate.location or not req.location:
        return 0.0
    return 1.0 if _tokenize_location(req.location) & _tokenize_location(candidate.location) else 0.0


def foundation_score(candidate: Candidate, req: Req) -> tuple[float, list[str]]:
    skill_score, matched = _skill_match(candidate, req)
    experience_score = _experience(candidate, req)
    total = skill_score * FOUNDATION_WEIGHTS["skill_match"] + experience_score * FOUNDATION_WEIGHTS["experience"]
    return total, matched


def _github_bonus(candidate: Candidate, req: Req) -> tuple[float, dict[str, float]]:
    required = {rs.skill for rs in req.required_skills}
    candidate_canon = {req.canonical_skill(s) for s in candidate.skills}
    breadth = min(len(candidate_canon - required) / 5, 1.0)

    activity = _recency(candidate)

    docs = candidate.docs_repo_ratio if candidate.docs_repo_ratio is not None else 0.0

    stars = candidate.total_stars or 0
    traction = min(math.log10(stars + 1) / math.log10(101), 1.0)  # 100 stars -> full credit

    location = _location_bonus(candidate, req)

    subs = {"breadth": breadth, "activity": activity, "docs": docs, "traction": traction, "location": location}
    total = sum(v * GITHUB_BONUS_WEIGHTS[k] for k, v in subs.items())
    return total, subs


def _linkedin_bonus(candidate: Candidate, req: Req) -> tuple[float, dict[str, float]]:
    certifications = 1.0 if candidate.certifications else 0.0
    open_source = 1.0 if candidate.open_source_contributor else 0.0
    volunteer = 1.0 if candidate.volunteer_experience else 0.0
    education = (
        1.0
        if candidate.education_level and candidate.education_level.strip().lower() in _ADVANCED_DEGREES
        else 0.0
    )
    location = _location_bonus(candidate, req)
    # LinkedIn has no repo-activity timestamps to build a recency signal
    # from, so "currently open to work" stands in for reachability/
    # availability right now. Unknown (None) contributes 0, not a penalty.
    availability = 1.0 if candidate.currently_open_to_work else 0.0

    subs = {
        "certifications": certifications,
        "open_source": open_source,
        "volunteer": volunteer,
        "education": education,
        "location": location,
        "availability": availability,
    }
    total = sum(v * LINKEDIN_BONUS_WEIGHTS[k] for k, v in subs.items())
    return total, subs


def bonus_score(candidate: Candidate, req: Req) -> tuple[float, dict[str, float]]:
    if candidate.source == "github":
        return _github_bonus(candidate, req)
    if candidate.source == "linkedin":
        return _linkedin_bonus(candidate, req)
    return 0.0, {}


def _acceleration_score(candidate: Candidate) -> float:
    """Fraction of recent+prior repo pushes that fall in the recent (last
    6mo) window. 1.0 = all activity is recent (accelerating/new). 0.0 =
    all activity is in the older window (cooled off) — this is a floor,
    not a penalty, since the axis only ever adds points on top of 0.
    """
    if candidate.recent_push_count is None or candidate.prior_push_count is None:
        return 0.0
    total = candidate.recent_push_count + candidate.prior_push_count
    return candidate.recent_push_count / total if total else 0.0


def _traction_per_tenure_score(candidate: Candidate) -> float:
    """Stars earned per year of account age — rewards a newer account
    punching above its age, which is exactly a "promise" signal rather
    than a "level" signal.
    """
    if candidate.total_stars is None or candidate.account_age_years is None:
        return 0.0
    stars_per_year = candidate.total_stars / max(candidate.account_age_years, 0.5)
    return min(stars_per_year / 20.0, 1.0)  # 20 stars/year -> full credit (illustrative)


def _title_velocity_score(candidate: Candidate) -> float:
    """Reward reaching a senior-sounding title faster than an illustrative
    benchmark. No senior-ish keyword found, or missing years_experience,
    scores 0 — a neutral floor, not a judgment that the candidate lacks
    promise; there just isn't a trend signal to read here.
    """
    if not candidate.current_title or candidate.years_experience is None:
        return 0.0
    title_lower = candidate.current_title.lower()
    for keyword, expected_years in _TITLE_BENCHMARK_YEARS:
        if keyword in title_lower:
            if candidate.years_experience >= expected_years:
                return 0.0  # at/behind the illustrative benchmark pace: no bonus, not a penalty
            gap = expected_years - candidate.years_experience
            return min(gap / expected_years, 1.0)
    return 0.0


def _github_momentum(candidate: Candidate) -> tuple[float, dict[str, float]]:
    acceleration = _acceleration_score(candidate)
    traction_per_tenure = _traction_per_tenure_score(candidate)
    subs = {"acceleration": acceleration, "traction_per_tenure": traction_per_tenure}
    total = sum(v * GITHUB_MOMENTUM_WEIGHTS[k] for k, v in subs.items())
    return total, subs


def _linkedin_momentum(candidate: Candidate) -> tuple[float, dict[str, float]]:
    subs = {"title_velocity": _title_velocity_score(candidate)}
    total = sum(v * LINKEDIN_MOMENTUM_WEIGHTS[k] for k, v in subs.items())
    return total, subs


def momentum_score(candidate: Candidate, req: Req) -> tuple[float, dict[str, float]]:
    if candidate.source == "github":
        return _github_momentum(candidate)
    if candidate.source == "linkedin":
        return _linkedin_momentum(candidate)
    return 0.0, {}


def score_candidate_experimental(candidate: Candidate, req: Req) -> ExperimentalScoreResult:
    foundation, matched = foundation_score(candidate, req)
    bonus, bonus_subs = bonus_score(candidate, req)
    momentum, momentum_subs = momentum_score(candidate, req)

    reasons = [f"foundation: matched {len(matched)}/{len(req.required_skills)} required skills"]
    fired_bonus = [k for k, v in bonus_subs.items() if v > 0]
    reasons.append(f"bonus signals: {', '.join(fired_bonus) if fired_bonus else 'none'}")
    fired_momentum = [k for k, v in momentum_subs.items() if v > 0]
    reasons.append(f"momentum signals: {', '.join(fired_momentum) if fired_momentum else 'none'}")

    return ExperimentalScoreResult(
        candidate=candidate,
        foundation=foundation,
        bonus=bonus,
        momentum=momentum,
        matched_skills=matched,
        qualified=foundation >= req.qualify_threshold,
        reasons=reasons,
    )


assert sum(FOUNDATION_WEIGHTS.values()) == 100
assert sum(GITHUB_BONUS_WEIGHTS.values()) == 100
assert sum(LINKEDIN_BONUS_WEIGHTS.values()) == 100
assert sum(GITHUB_MOMENTUM_WEIGHTS.values()) == 100
assert sum(LINKEDIN_MOMENTUM_WEIGHTS.values()) == 100
