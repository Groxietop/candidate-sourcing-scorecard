"""Whether we actually *measured* something, or just guessed it.

This module exists because of one defect in the original scorer: when a
signal was unavailable it returned `0.5` — the same value it returns for a
signal that was measured and came out mediocre. Downstream, `qualified =
total >= threshold` then treated that guess as evidence.

That is the exact mechanism by which a strong candidate gets dropped. A
senior backend engineer whose work all lives in private repos at an
IP-strict employer has no public recency signal, no stars, a thin account:
three categories scored on nothing, ~35 points of pure imputation, a total
under the bar, and a silent discard. The system could not tell "we looked
and it's weak" from "we have no idea".

So every category now carries its value *and* whether that value was
observed. Confidence is the share of scoring weight backed by real
observation. The rule that falls out of it is simple and is the whole
philosophy of the tool:

    a candidate may only be discarded on positive evidence of a miss,
    never on the absence of evidence.

Absence of evidence about a person is a fact about our data collection, not
a fact about the person.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Signal:
    """One scoring category, plus whether we actually observed it.

    `value` is the 0-1 category score the rubric produced. `observed` is
    False when that value is a fallback rather than a measurement — the
    number is still used (dropping the category would be its own kind of
    guess) but nothing may be held against the candidate on its basis.
    """

    category: str
    value: float
    observed: bool
    detail: str = ""

    @property
    def imputed(self) -> bool:
        return not self.observed


# Why a weak signal might be wrong about the person. Keyed by category, used
# to build the caveat a recruiter reads next to any non-obvious exclusion.
# These are not hedges — each names a specific, documented failure mode of
# the underlying data.
CAVEATS = {
    "skill_match": (
        "we only see public repositories; skills used daily at work can be "
        "completely invisible here"
    ),
    "experience": (
        "seniority is inferred from GitHub account age and stars, which says "
        "nothing about a 20-year veteran who opened an account last year"
    ),
    "recency": (
        "a quiet public profile can mean private-repo work, a career break, "
        "parental leave, or simply not coding in public"
    ),
    "location": (
        "not currently local, but candidates relocate — the req assumed they "
        "would not"
    ),
    "corroboration": (
        "found on only one source, which reflects where we searched rather "
        "than anything about the candidate"
    ),
}

# Categories whose low score is a property of our *search*, not the person.
# A candidate may never be discarded on the strength of these alone.
DISCOVERY_ARTEFACTS = frozenset({"corroboration"})


@dataclass
class Evidence:
    """The observation record behind one candidate's score."""

    signals: list[Signal] = field(default_factory=list)

    def by_category(self) -> dict[str, Signal]:
        return {s.category: s for s in self.signals}

    def confidence(self, weights: dict[str, float]) -> float:
        """Share of total scoring weight that rests on measured signals.

        1.0 means every category was observed. 0.0 means the score is
        entirely guesswork wearing a number's clothing.
        """
        total = sum(weights.get(s.category, 0.0) for s in self.signals)
        if total <= 0:
            return 0.0
        observed = sum(
            weights.get(s.category, 0.0) for s in self.signals if s.observed
        )
        return observed / total

    def imputed_categories(self) -> list[str]:
        return [s.category for s in self.signals if s.imputed]

    def observed_weaknesses(
        self, weights: dict[str, float], threshold: float = 0.4
    ) -> list[Signal]:
        """Categories we genuinely measured and that genuinely came out weak.

        Discovery artefacts are excluded: a zero on corroboration is a
        statement about our search coverage, not about the candidate, and
        letting it count as a measured weakness would reintroduce the bug
        this module exists to fix.
        """
        return [
            s
            for s in self.signals
            if s.observed
            and s.value <= threshold
            and s.category not in DISCOVERY_ARTEFACTS
            and weights.get(s.category, 0.0) > 0
        ]


def caveat_for(categories) -> str:
    """Human-readable caveat covering the given weak categories."""
    notes = [CAVEATS[c] for c in categories if c in CAVEATS]
    if not notes:
        return ""
    if len(notes) == 1:
        return notes[0]
    return "; ".join(notes[:-1]) + "; and " + notes[-1]
