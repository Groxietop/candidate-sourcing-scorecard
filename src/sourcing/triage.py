"""Tiering a candidate pool without quietly throwing anyone away.

The scorer this replaces ended in `qualified = total >= threshold`. One
number, one cut, no appeal: a candidate at 59.9 was indistinguishable from
one at 12, and nothing recorded *why* either fell where it did.

The replacement is four tiers and one hard rule.

    STRONG     clears the bar on measured evidence
    REVIEW     mixed, or clears the bar but partly on guesswork
    CAVEATED   looks weak, but the weakness rests on signals we did not
               actually observe. Never auto-removed, always carries the
               reason and the reason that reason may be wrong.
    DISCARD    positive, observed evidence of a disqualifying miss

The rule: **DISCARD requires evidence, never its absence.** A candidate we
know little about cannot be discarded, however low their score, because a
low score built from imputed signals is a statement about our data, not
about them. That inverts the usual default, and it is the point — the cost
of a recruiter spending thirty seconds on a false positive is not remotely
comparable to the cost of never contacting the person who should have got
the job.

Everything except DISCARD stays in the recruiter's queue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .evidence import Evidence, caveat_for

# Below this share of measured evidence, a low score is not trustworthy
# enough to act on. Set deliberately high: two of five categories imputed
# already puts a candidate here.
CONFIDENT = 0.75

# A discarded candidate must be clearly below the bar, not marginally.
# Expressed as a fraction of the req's own threshold.
CLEARLY_BELOW = 0.6

# A measured category at or under this counts as a genuine weakness.
WEAK = 0.4


class Tier(str, Enum):
    STRONG = "strong"
    REVIEW = "review"
    CAVEATED = "caveated"
    DISCARD = "discard"

    @property
    def stays_in_queue(self) -> bool:
        return self is not Tier.DISCARD


# Ordering for reports: what a recruiter should read first.
TIER_ORDER = [Tier.STRONG, Tier.REVIEW, Tier.CAVEATED, Tier.DISCARD]


@dataclass
class TriageResult:
    tier: Tier
    confidence: float
    reason: str
    caveat: str = ""
    missing_must_haves: list[str] = field(default_factory=list)
    imputed_categories: list[str] = field(default_factory=list)

    @property
    def stays_in_queue(self) -> bool:
        return self.tier.stays_in_queue

    def as_row(self) -> dict:
        return {
            "tier": self.tier.value,
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
            "caveat": self.caveat,
            "missing_must_haves": ";".join(self.missing_must_haves),
            "scored_on_guesswork": ";".join(self.imputed_categories),
        }


def missing_must_haves(req, matched_skills) -> list[str]:
    """Required skills marked `weight: high` that the candidate did not match."""
    matched = {s.lower() for s in matched_skills}
    return [
        rs.skill
        for rs in req.required_skills
        if rs.weight == "high" and rs.skill.lower() not in matched
    ]


def triage(
    total: float,
    req,
    evidence: Evidence,
    weights: dict[str, float],
    matched_skills,
    confident_at: float = CONFIDENT,
    clearly_below: float = CLEARLY_BELOW,
) -> TriageResult:
    """Assign a tier, and say why — including why the reason might be wrong."""
    confidence = evidence.confidence(weights)
    imputed = evidence.imputed_categories()
    threshold = req.qualify_threshold
    missing = missing_must_haves(req, matched_skills)

    by_category = evidence.by_category()
    skills_observed = by_category.get("skill_match")
    skills_were_observed = bool(skills_observed and skills_observed.observed)

    weak = evidence.observed_weaknesses(weights, threshold=WEAK)
    weak_categories = [s.category for s in weak]

    # --- clears the bar -------------------------------------------------
    if total >= threshold:
        if confidence >= confident_at and not missing:
            return TriageResult(
                tier=Tier.STRONG,
                confidence=confidence,
                reason=(
                    f"scored {total:.0f} against a bar of {threshold:.0f}, "
                    f"with {confidence:.0%} of that resting on measured signals"
                ),
                imputed_categories=imputed,
            )
        if missing:
            return TriageResult(
                tier=Tier.REVIEW,
                confidence=confidence,
                reason=(
                    f"scored {total:.0f}, over the bar, but is missing a "
                    f"must-have: {', '.join(missing)}"
                ),
                caveat=caveat_for(["skill_match"]),
                missing_must_haves=missing,
                imputed_categories=imputed,
            )
        return TriageResult(
            tier=Tier.REVIEW,
            confidence=confidence,
            reason=(
                f"scored {total:.0f}, over the bar, but only {confidence:.0%} "
                "of that is measured"
            ),
            caveat=caveat_for(imputed),
            imputed_categories=imputed,
        )

    # --- below the bar --------------------------------------------------
    # This is where the old scorer silently deleted people. Everything from
    # here on must justify itself on observed evidence or stay in the queue.

    confidently_measured = confidence >= confident_at
    well_below = total < threshold * clearly_below
    provably_missing_must_have = bool(missing) and skills_were_observed

    if confidently_measured and (provably_missing_must_have or (well_below and weak)):
        if provably_missing_must_have:
            reason = (
                f"we observed this candidate's public skill set and it does "
                f"not include the must-have: {', '.join(missing)}"
            )
        else:
            reason = (
                f"scored {total:.0f} against a bar of {threshold:.0f}, weak on "
                f"measured signals: {', '.join(weak_categories)}"
            )
        return TriageResult(
            tier=Tier.DISCARD,
            confidence=confidence,
            reason=reason,
            # Even a discard carries its caveat. Nothing here is certain, and
            # a recruiter reviewing the discard pile deserves to know the
            # basis on which someone was set aside.
            caveat=caveat_for(weak_categories or ["skill_match"]),
            missing_must_haves=missing,
            imputed_categories=imputed,
        )

    # Below the bar, but we cannot stand behind it. This is the tier the
    # whole redesign exists to create.
    if not confidently_measured:
        reason = (
            f"scored {total:.0f}, under the bar, but {1 - confidence:.0%} of "
            f"that score is guesswork — we have no data on: "
            f"{', '.join(imputed)}"
        )
        caveat = caveat_for(imputed)
    elif missing:
        reason = (
            f"scored {total:.0f} and appears to be missing {', '.join(missing)}"
        )
        caveat = caveat_for(["skill_match"])
    else:
        reason = (
            f"scored {total:.0f}, under the bar of {threshold:.0f}, but not "
            "clearly enough to set aside"
        )
        caveat = caveat_for(weak_categories or imputed or ["skill_match"])

    return TriageResult(
        tier=Tier.CAVEATED,
        confidence=confidence,
        reason=reason,
        caveat=caveat,
        missing_must_haves=missing,
        imputed_categories=imputed,
    )


def summarise(results) -> dict:
    """Counts per tier, for the run summary."""
    counts = {tier: 0 for tier in TIER_ORDER}
    for result in results:
        counts[result.tier] += 1
    return {tier.value: counts[tier] for tier in TIER_ORDER}
