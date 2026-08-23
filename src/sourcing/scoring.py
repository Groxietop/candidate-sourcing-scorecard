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
from .evidence import Evidence, Signal
from .triage import TriageResult, triage

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
    evidence: Evidence = field(default_factory=Evidence)
    triage: TriageResult | None = None

    @property
    def tier(self):
        return self.triage.tier if self.triage else None

    @property
    def stays_in_queue(self) -> bool:
        """Everything except an evidence-backed discard stays in the queue."""
        return self.triage.stays_in_queue if self.triage else True

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
            signal = self.evidence.by_category().get(category)
            row[f"{category}_observed"] = signal.observed if signal else True
        if self.triage is not None:
            row.update(self.triage.as_row())
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


def _experience(candidate: Candidate, req: Req) -> tuple[float, bool, str]:
    """Returns (value, observed, detail).

    `observed` is False when the 0.5 fallback fires. That distinction is the
    whole point -- see evidence.py.
    """
    if candidate.years_experience is not None:
        if req.min_years_experience <= 0:
            return 1.0, True, "stated years of experience"
        return (
            min(candidate.years_experience / req.min_years_experience, 1.0),
            True,
            f"{candidate.years_experience:g}y stated vs {req.min_years_experience:g}y required",
        )

    if candidate.account_age_years is not None:
        # GitHub proxy: account age (up to 6y = full credit) + a small stars bonus.
        age_component = min(candidate.account_age_years / 6.0, 1.0) * 0.7
        stars = candidate.total_stars or 0
        stars_component = min(stars / 50.0, 1.0) * 0.3
        return (
            min(age_component + stars_component, 1.0),
            True,
            f"GitHub proxy: {candidate.account_age_years:.1f}y account, {stars} stars",
        )

    # Neutral, not zero -- and explicitly NOT observed, so nothing may be
    # held against the candidate on this basis.
    return 0.5, False, "no experience signal available"


def _recency(candidate: Candidate) -> tuple[float, bool, str]:
    if candidate.days_since_last_active is not None:
        days = candidate.days_since_last_active
        if days <= 182:
            value = 1.0
        elif days >= 730:
            value = 0.0
        else:
            value = 1.0 - (days - 182) / (730 - 182)
        return value, True, f"last public activity {days}d ago"

    if candidate.currently_open_to_work is not None:
        return (
            1.0 if candidate.currently_open_to_work else 0.5,
            True,
            "open-to-work flag",
        )

    return 0.5, False, "no activity signal available"


def _tokenize_location(loc: str) -> set[str]:
    tokens = re.split(r"[,\s/]+", loc.lower())
    return {t for t in tokens if t and t not in _STOPWORDS}


def _location(candidate: Candidate, req: Req) -> tuple[float, bool, str]:
    if req.remote_ok:
        return 1.0, True, "req is remote-friendly"
    if not candidate.location or not req.location:
        return 0.5, False, "no location on file"
    req_tokens = _tokenize_location(req.location)
    cand_tokens = _tokenize_location(candidate.location)
    if req_tokens & cand_tokens:
        return 1.0, True, f"located in {candidate.location}"
    return 0.0, True, f"located in {candidate.location}, req wants {req.location}"


def score_candidate(candidate: Candidate, req: Req, corroborated: bool) -> ScoreResult:
    skill_score, matched = _skill_match(candidate, req)
    experience_score, experience_seen, experience_detail = _experience(candidate, req)
    recency_score, recency_seen, recency_detail = _recency(candidate)
    location_score, location_seen, location_detail = _location(candidate, req)
    corroboration_score = 1.0 if corroborated else 0.0

    # We only ever see a candidate's *public* skills. Treat the category as
    # observed when we found any at all -- an empty skill set means our
    # discovery found nothing, not that the person can do nothing.
    skills_seen = bool(candidate.skills)

    evidence = Evidence(
        signals=[
            Signal("skill_match", skill_score, skills_seen,
                   f"matched {len(matched)}/{len(req.required_skills)} required skills"
                   if skills_seen else "no public skill signal found"),
            Signal("experience", experience_score, experience_seen, experience_detail),
            Signal("recency", recency_score, recency_seen, recency_detail),
            Signal("location", location_score, location_seen, location_detail),
            # Corroboration is always "known" -- but it describes our search
            # coverage, not the candidate, so evidence.py excludes it from
            # counting as a measured weakness.
            Signal("corroboration", corroboration_score, True,
                   "found on more than one source" if corroborated
                   else "found on one source only"),
        ]
    )

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

    decision = triage(total, req, evidence, WEIGHTS, matched)

    return ScoreResult(
        candidate=candidate,
        total=total,
        category_scores=category_scores,
        matched_skills=matched,
        # Kept for backwards compatibility with the existing CSVs and tests.
        # The tier is the decision that actually matters now.
        qualified=total >= req.qualify_threshold,
        reasons=reasons,
        evidence=evidence,
        triage=decision,
    )


assert sum(WEIGHTS.values()) == 100, "category weights must sum to 100"
