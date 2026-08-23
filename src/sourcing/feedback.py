"""Recruiter decisions, and what they say about the model.

The scorer makes claims. This is the only thing in the repo that can tell
you whether those claims are any good — a recorded stream of "the tool said
X, the recruiter said Y".

Every number this module reports is computed from decisions actually stored
in the log. With an empty log it reports that it has no idea, rather than a
plausible-looking accuracy. A screening tool that displays invented
performance figures is worse than one that displays none.

The metric that matters most here is deliberately not precision. Precision
asks "of the people we advanced, how many were good" — a question you can
answer by advancing almost nobody. Given that this tool exists to avoid
discarding the dream candidate, the number to watch is the inverse:

    missed_rate = of the candidates we set aside or caveated,
                  how many did the recruiter say were actually good?

That is the false-negative rate on our own discard pile, and it is the only
metric that gets worse when the tool becomes too confident.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .triage import Tier

# Why a recruiter overruled us. Coarse on purpose: a short closed list gets
# used consistently, a free-text box does not.
REASON_CODES = {
    "insufficient_seniority": "Not senior enough for the scope of the role",
    "wrong_skills": "Skill set does not match what the role needs",
    "not_interested": "Candidate not interested or unavailable",
    "location": "Location or work authorisation does not work",
    "already_pipelined": "Already in the pipeline from another source",
    "actually_strong": "Tool underrated them — this is a good candidate",
    "other": "Something else",
}

# Verdicts a recruiter can return.
ADVANCE = "advance"
REJECT = "reject"

DEFAULT_LOG = Path("data/feedback/decisions.jsonl")


@dataclass
class Decision:
    """One recruiter judgement on one candidate."""

    candidate_key: str
    candidate_name: str
    req_id: str
    predicted_tier: str          # what the tool said
    verdict: str                 # ADVANCE or REJECT
    reason_code: str = "other"
    note: str = ""
    decided_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    decision_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __post_init__(self):
        if self.verdict not in (ADVANCE, REJECT):
            raise ValueError(
                f"verdict must be {ADVANCE!r} or {REJECT!r}, got {self.verdict!r}"
            )
        if self.reason_code not in REASON_CODES:
            raise ValueError(
                f"unknown reason_code {self.reason_code!r}; "
                f"expected one of {sorted(REASON_CODES)}"
            )


class FeedbackLog:
    """Append-only JSONL log of recruiter decisions.

    Append-only on purpose: the point is to be able to say what the model
    predicted *before* it was adjusted, so a rewritable store would quietly
    destroy the only evidence of whether adjustment helped.
    """

    def __init__(self, path: Path | str = DEFAULT_LOG):
        self.path = Path(path)

    def record(self, decision: Decision) -> Decision:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as handle:
            handle.write(json.dumps(asdict(decision)) + "\n")
        return decision

    def all(self) -> list[Decision]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if line:
                out.append(Decision(**json.loads(line)))
        return out

    def recent(self, n: int = 30) -> list[Decision]:
        return self.all()[-n:]


# --- metrics ---------------------------------------------------------------

# Tiers we advanced (kept visible as recommendations) vs set aside.
ADVANCED_TIERS = {Tier.STRONG.value, Tier.REVIEW.value}
SET_ASIDE_TIERS = {Tier.CAVEATED.value, Tier.DISCARD.value}


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    """None, not zero, when there is nothing to divide by.

    A rate of 0.0 and 'we have no data' render identically on a dashboard
    and mean opposite things.
    """
    return numerator / denominator if denominator else None


def evaluate(decisions) -> dict:
    """Model performance, computed from recorded decisions only.

    Any metric with no supporting decisions comes back None so the caller
    has to render 'no data' rather than a number.
    """
    decisions = list(decisions)

    advanced = [d for d in decisions if d.predicted_tier in ADVANCED_TIERS]
    set_aside = [d for d in decisions if d.predicted_tier in SET_ASIDE_TIERS]

    true_positives = sum(1 for d in advanced if d.verdict == ADVANCE)
    false_positives = sum(1 for d in advanced if d.verdict == REJECT)
    # The ones that matter: we set them aside, the recruiter wanted them.
    missed = [d for d in set_aside if d.verdict == ADVANCE]
    correctly_set_aside = sum(1 for d in set_aside if d.verdict == REJECT)

    return {
        "decisions": len(decisions),
        "advanced": len(advanced),
        "set_aside": len(set_aside),
        "precision": _safe_ratio(true_positives, len(advanced)),
        "recall": _safe_ratio(
            true_positives, true_positives + len(missed)
        ),
        # The headline for this tool's philosophy.
        "missed_rate": _safe_ratio(len(missed), len(set_aside)),
        "missed_count": len(missed),
        "missed_candidates": [
            {"name": d.candidate_name, "tier": d.predicted_tier, "req_id": d.req_id}
            for d in missed
        ],
        "true_positives": true_positives,
        "false_positives": false_positives,
        "correctly_set_aside": correctly_set_aside,
    }


def rejection_reasons(decisions) -> dict[str, int]:
    """Counts per reason code, most common first."""
    counts: dict[str, int] = {}
    for decision in decisions:
        if decision.verdict == REJECT:
            counts[decision.reason_code] = counts.get(decision.reason_code, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def reason_rate(decisions, reason_code: str) -> float | None:
    """Share of *advanced* candidates rejected for one specific reason.

    This is the per-reason false-positive rate: how often does the tool
    recommend someone the recruiter then rejects because of, say,
    insufficient seniority. It is what tells you which signal is
    miscalibrated, as opposed to merely that something is.
    """
    advanced = [d for d in decisions if d.predicted_tier in ADVANCED_TIERS]
    if not advanced:
        return None
    hits = sum(
        1
        for d in advanced
        if d.verdict == REJECT and d.reason_code == reason_code
    )
    return hits / len(advanced)


def compare_periods(decisions, split: int | None = None) -> dict:
    """Before/after on the same metrics, splitting the log in two.

    Returns None-valued halves rather than numbers when either side is too
    thin to mean anything -- an 'improvement' computed from three decisions
    is noise wearing a percentage sign.
    """
    decisions = list(decisions)
    minimum = 10  # per side
    if len(decisions) < minimum * 2:
        return {
            "available": False,
            "reason": (
                f"needs {minimum * 2} decisions to split; have {len(decisions)}"
            ),
        }

    split = split if split is not None else len(decisions) // 2
    before, after = decisions[:split], decisions[split:]
    return {
        "available": True,
        "before": evaluate(before),
        "after": evaluate(after),
        "before_n": len(before),
        "after_n": len(after),
    }
