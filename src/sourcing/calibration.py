"""Turning recruiter feedback into an actual model adjustment.

Reporting that the tool is wrong is only half a loop. This closes it: map
each rejection reason onto the scoring category responsible for it, measure
how often that category misleads, and propose a concrete weight change.

Two things this deliberately does *not* do.

It does not adjust automatically. Every proposal is written to disk for a
human to apply, because a screening model that silently re-weights itself
from a handful of decisions is exactly how a hiring tool acquires a bias
nobody can point at. The proposal records the evidence it rests on so the
change can be argued with.

It does not propose anything from thin data. Below `MIN_EVIDENCE` decisions
for a reason, the answer is "not enough signal yet" -- which is the same
discipline the triage layer applies to candidates, applied to ourselves.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .feedback import ADVANCED_TIERS, REJECT, REASON_CODES

# Which scoring category a rejection reason implicates. A recruiter saying
# "not senior enough" is telling us our experience signal read too high.
REASON_TO_CATEGORY = {
    "insufficient_seniority": "experience",
    "wrong_skills": "skill_match",
    "location": "location",
    "not_interested": None,       # nothing about our scoring was wrong
    "already_pipelined": None,    # a pipeline-state fact, not a model error
    "actually_strong": None,      # handled separately -- see below
    "other": None,
}

# Below this many decisions implicating a category, we say nothing.
MIN_EVIDENCE = 8

# How hard a single calibration round is allowed to push a weight, as a
# fraction of its current value. Small on purpose: many small corrections
# with a human in the loop beat one large automatic swing.
MAX_ADJUSTMENT = 0.20

# Rejections for this share of advanced candidates before we act.
CONCERN_THRESHOLD = 0.10


@dataclass
class Proposal:
    """A suggested weight change, with the evidence behind it."""

    category: str
    current_weight: float
    proposed_weight: float
    direction: str            # "increase" or "decrease"
    reason_code: str
    observed_rate: float
    supporting_decisions: int
    rationale: str
    proposed_at: str = ""

    def __post_init__(self):
        if not self.proposed_at:
            self.proposed_at = datetime.now(timezone.utc).isoformat()

    @property
    def delta(self) -> float:
        return self.proposed_weight - self.current_weight


def propose_adjustments(decisions, weights: dict[str, float]) -> list[Proposal]:
    """Weight changes implied by the recorded decisions.

    A category whose signal keeps leading to rejections is over-trusted and
    its weight comes down. The freed weight is not redistributed
    automatically -- that is the human's call, and the report says so.
    """
    decisions = list(decisions)
    advanced = [d for d in decisions if d.predicted_tier in ADVANCED_TIERS]
    if not advanced:
        return []

    proposals: list[Proposal] = []

    for reason_code, category in REASON_TO_CATEGORY.items():
        if category is None or category not in weights:
            continue

        implicated = [
            d for d in advanced
            if d.verdict == REJECT and d.reason_code == reason_code
        ]
        if len(implicated) < MIN_EVIDENCE:
            continue

        rate = len(implicated) / len(advanced)
        if rate < CONCERN_THRESHOLD:
            continue

        current = weights[category]
        # Scale the cut with the observed rate, capped.
        shrink = min(rate, MAX_ADJUSTMENT)
        proposed = round(current * (1.0 - shrink), 1)

        proposals.append(
            Proposal(
                category=category,
                current_weight=current,
                proposed_weight=proposed,
                direction="decrease",
                reason_code=reason_code,
                observed_rate=rate,
                supporting_decisions=len(implicated),
                rationale=(
                    f"{len(implicated)} of {len(advanced)} advanced candidates "
                    f"({rate:.1%}) were rejected for "
                    f"'{REASON_CODES[reason_code]}'. The {category} signal is "
                    f"reading higher than it should; reduce its weight from "
                    f"{current:g} to {proposed:g} and re-measure."
                ),
            )
        )

    return sorted(proposals, key=lambda p: p.observed_rate, reverse=True)


def underrated_signal(decisions) -> dict:
    """Evidence that the tool is too aggressive, not too lenient.

    Every `actually_strong` on a set-aside candidate is a recorded near-miss
    of the exact kind this tool exists to prevent. It argues for loosening
    the discard rule, not for re-weighting any single category.
    """
    decisions = list(decisions)
    set_aside = [d for d in decisions if d.predicted_tier not in ADVANCED_TIERS]
    rescued = [d for d in set_aside if d.reason_code == "actually_strong"]

    if not set_aside:
        return {"available": False, "reason": "no set-aside candidates reviewed yet"}

    rate = len(rescued) / len(set_aside)
    return {
        "available": True,
        "set_aside_reviewed": len(set_aside),
        "rescued": len(rescued),
        "rescue_rate": rate,
        "verdict": (
            "the discard rule is too aggressive; raise the confidence bar "
            "required to set anyone aside"
            if rate > 0.05
            else "no evidence the discard rule is losing good candidates"
        ),
        "candidates": [d.candidate_name for d in rescued],
    }


def write_report(
    proposals, underrated: dict, path: Path | str
) -> Path:
    """Persist proposals for a human to apply. Never auto-applied."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "applied": False,
        "note": (
            "Proposals only. Nothing here has been applied to the live "
            "weights; edit WEIGHTS in scoring.py deliberately, then record "
            "the change so the next comparison has a baseline."
        ),
        "proposals": [asdict(p) for p in proposals],
        "underrated_signal": underrated,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path
