"""Where an LLM would go, and why it is switched off.

Deliberately not wired up. This module defines the contract and the cost
model so the decision is legible, because "we didn't use an LLM" and "we
thought about where an LLM belongs and chose not to pay for it yet" look
identical in a repo that simply omits the question.

The escalation argument
-----------------------
The triage tiers already sort candidates by how much judgement they need:

    STRONG    unambiguous. Cheap rules answer it. An LLM adds cost, latency
              and non-determinism to a question already settled.
    DISCARD   unambiguous in the other direction, and evidence-backed.
    CAVEATED  genuinely ambiguous. We could not observe enough to decide,
              and a keyword rubric is the wrong instrument for the question.

So the caveated pile *is* the escalation queue. That is a useful property
rather than a coincidence: it means LLM spend lands only on the slice where
judgement is actually required, and the slice stays small because most
candidates resolve deterministically.

What an LLM would actually add
------------------------------
Not "score the candidate better" -- a model with the same thin evidence has
the same problem. It would add things the rubric structurally cannot do:

  1. Read a README or bio as prose. "Led the migration off a monolith" is
     seniority evidence that no `topic:` match will ever capture.
  2. Resolve skill equivalence semantically. The rubric needs
     `skill_aliases` maintained by hand and misses "Postgres" for "SQL"
     unless someone wrote the mapping. That single gap currently flags
     Sebastian Raschka as missing SQL.
  3. Judge whether an absence is meaningful. A quiet GitHub with a detailed
     profile reads differently from a quiet GitHub with nothing at all, and
     the rubric scores both 0.5.

All three are exactly the CAVEATED tier's problems.

Cost model
----------
Escalating only the caveated slice is what makes this affordable. On the
current example reqs that tier runs roughly 10-25% of a pool. At ~15
candidates per req and a few thousand tokens per candidate, a full pass over
one req's caveated candidates is fractions of a cent -- but the number that
matters is not per-run, it is per-run x reqs x weekly schedule x forever.
Hence: designed, priced, and off.

Guardrails, if it is ever turned on
-----------------------------------
The philosophy does not change because the instrument does.

  * An LLM may only ever move a candidate *up* a tier, never down. It can
    rescue someone from CAVEATED; it cannot create a DISCARD. Model output
    is not the "positive evidence of a miss" the discard rule requires.
  * Its output is evidence with a source, recorded like any other signal,
    not a score that silently replaces the rubric.
  * Every escalated decision is logged to the same feedback store, so the
    LLM tier is measured against recruiter judgement exactly like the rules
    are.
"""

from __future__ import annotations

from dataclasses import dataclass

from .triage import Tier

# The only tier worth spending a model call on.
ESCALATE_TIERS = frozenset({Tier.CAVEATED})

# An LLM may raise a candidate out of these tiers, never push one into them.
MODEL_MAY_PROMOTE_FROM = frozenset({Tier.CAVEATED, Tier.DISCARD})


@dataclass(frozen=True)
class EscalationCandidate:
    """What would be sent for a second opinion, and why."""

    candidate_name: str
    profile_url: str
    tier: str
    reason: str
    caveat: str
    unobserved: list[str]

    @property
    def question(self) -> str:
        """The specific question an LLM would be asked about this candidate."""
        gaps = ", ".join(self.unobserved) if self.unobserved else "none"
        return (
            f"Our rubric set {self.candidate_name} aside: {self.reason} "
            f"We could not observe: {gaps}. Reading their profile and "
            f"repositories as prose, is there evidence the rubric missed? "
            f"Answer only with evidence you can point at."
        )


def select_for_escalation(results, limit: int | None = None) -> list[EscalationCandidate]:
    """Which candidates would go to a model, if escalation were enabled.

    Pure selection: builds the queue and returns it without calling anything.
    Lets the CLI report what escalation *would* cost before anyone pays it.
    """
    queue = []
    for result in results:
        decision = getattr(result, "triage", None)
        if decision is None or decision.tier not in ESCALATE_TIERS:
            continue
        queue.append(
            EscalationCandidate(
                candidate_name=result.candidate.name,
                profile_url=result.candidate.profile_url,
                tier=decision.tier.value,
                reason=decision.reason,
                caveat=decision.caveat,
                unobserved=list(decision.imputed_categories),
            )
        )
    return queue[:limit] if limit else queue


def escalation_summary(results) -> dict:
    """What a model pass over this run would cover. Costs nothing to compute."""
    total = sum(1 for r in results if getattr(r, "triage", None) is not None)
    queue = select_for_escalation(results)
    return {
        "enabled": False,
        "candidates_in_run": total,
        "would_escalate": len(queue),
        "share_of_run": (len(queue) / total) if total else 0.0,
        "note": (
            "Escalation is designed but switched off. Only the caveated tier "
            "would be sent, which is what keeps the cost proportional to "
            "genuine ambiguity rather than to pool size."
        ),
    }
