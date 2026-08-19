"""The scoring rubric. This is the code-form of SCORING.md — read that file
first for *why* these weights and formulas exist. Kept deliberately small
and free of external dependencies so it's easy to unit test and to audit by
hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .candidate import Candidate
from .config import Req

# Category weights, out of 100. Must sum to 100 (checked by a test).
WEIGHTS = {
    "skill_match": 40,
    "experience": 20,
    "recency": 20,
    "location": 10,
    "corroboration": 10,
}

_STOPWORDS = {"remote", "hybrid", "onsite", "on-site", "the", "area", "greater"}


@dataclass
class ScoreResult:
    candidate: Candidate
    total: float
    category_scores: dict[str, float]  # 0..1 per category, before weighting
    matched_skills: list[str]
    qualified: bool
    reasons: list[str] = field(default_factory=list)

    def as_row(self) -> dict:
        row = {
            "name": self.candidate.name,
            "source": self.candidate.source,
            "score": round(self.total, 1),
            "qualified": self.qualified,
            "matched_skills": ";".join(self.matched_skills),
            "profile_url": self.candidate.profile_url,
        }
        for category, raw in self.category_scores.items():
            row[f"{category}_raw"] = round(raw, 2)
            row[f"{category}_points"] = round(raw * WEIGHTS[category], 1)
        row["reasons"] = " | ".join(self.reasons)
        return row


def _skill_match(candidate: Candidate, req: Req) -> tuple[float, list[str]]:
    if not req.required_skills:
        return 1.0, []
    candidate_skills = {req.canonical_skill(s) for s in candidate.skills}
    total_weight = sum(rs.weight_multiplier for rs in req.required_skills)
    matched = [rs.skill for rs in req.required_skills if rs.skill in candidate_skills]
    matched_weight = sum(
        rs.weight_multiplier for rs in req.required_skills if rs.skill in candidate_skills
    )
    score = matched_weight / total_weight if total_weight else 0.0
    return min(score, 1.0), matched


def _experience(candidate: Candidate, req: Req) -> float:
    if candidate.years_experience is not None:
        if req.min_years_experience <= 0:
            return 1.0
        return min(candidate.years_experience / req.min_years_experience, 1.0)

    if candidate.account_age_years is not None:
        # GitHub proxy: account age (up to 6y = full credit) + a small stars bonus.
        age_component = min(candidate.account_age_years / 6.0, 1.0) * 0.7
        stars = candidate.total_stars or 0
        stars_component = min(stars / 50.0, 1.0) * 0.3
        return min(age_component + stars_component, 1.0)

    return 0.5  # no experience signal available at all: neutral, not zero


def _recency(candidate: Candidate) -> float:
    if candidate.days_since_last_active is not None:
        days = candidate.days_since_last_active
        if days <= 182:
            return 1.0
        if days >= 730:
            return 0.0
        return 1.0 - (days - 182) / (730 - 182)

    if candidate.currently_open_to_work is not None:
        return 1.0 if candidate.currently_open_to_work else 0.5

    return 0.5  # unknown: neutral


def _tokenize_location(loc: str) -> set[str]:
    tokens = re.split(r"[,\s/]+", loc.lower())
    return {t for t in tokens if t and t not in _STOPWORDS}


def _location(candidate: Candidate, req: Req) -> float:
    if req.remote_ok:
        return 1.0
    if not candidate.location or not req.location:
        return 0.5  # unknown: neutral, don't punish missing data
    req_tokens = _tokenize_location(req.location)
    cand_tokens = _tokenize_location(candidate.location)
    return 1.0 if req_tokens & cand_tokens else 0.0


def score_candidate(candidate: Candidate, req: Req, corroborated: bool) -> ScoreResult:
    skill_score, matched = _skill_match(candidate, req)
    experience_score = _experience(candidate, req)
    recency_score = _recency(candidate)
    location_score = _location(candidate, req)
    corroboration_score = 1.0 if corroborated else 0.0

    category_scores = {
        "skill_match": skill_score,
        "experience": experience_score,
        "recency": recency_score,
        "location": location_score,
        "corroboration": corroboration_score,
    }
    total = sum(score * WEIGHTS[cat] for cat, score in category_scores.items())

    reasons = [f"matched {len(matched)}/{len(req.required_skills)} required skills"]
    if corroborated:
        reasons.append("corroborated across multiple sources")
    if candidate.years_experience is None and candidate.account_age_years is None:
        reasons.append("no experience signal available (scored neutral)")

    return ScoreResult(
        candidate=candidate,
        total=total,
        category_scores=category_scores,
        matched_skills=matched,
        qualified=total >= req.qualify_threshold,
        reasons=reasons,
    )


assert sum(WEIGHTS.values()) == 100, "category weights must sum to 100"
