"""The tiered review queue — what a recruiter actually opens.

A flat ranked CSV answers "who scored highest". It does not answer the two
questions that decide whether a tool is trustworthy: *who did you set aside,
and why might you be wrong about them?*

So the queue leads with the discard pile's reasoning rather than hiding it.
Every set-aside candidate is listed with the evidence behind the decision and
the caveat that evidence may be misleading — which means a recruiter can
audit the tool's judgement in about a minute, and overrule it.

Order is deliberate: STRONG, REVIEW, CAVEATED, then DISCARD. Caveated sits
directly above the discard pile because that is where a missed dream
candidate is most likely to be sitting.
"""

from __future__ import annotations

from .triage import TIER_ORDER, Tier

TIER_HEADINGS = {
    Tier.STRONG: "Strong — clears the bar on measured evidence",
    Tier.REVIEW: "Review — over the bar, with something worth checking",
    Tier.CAVEATED: "Caveated — under the bar, but we can't stand behind that",
    Tier.DISCARD: "Set aside — positive evidence of a miss",
}

TIER_BLURBS = {
    Tier.CAVEATED: (
        "Nobody here was removed. Each scored below the threshold, but the "
        "weakness rests on signals we did not actually observe, so the low "
        "score describes our data rather than the candidate."
    ),
    Tier.DISCARD: (
        "Set aside only because we measured the relevant signal and it came "
        "up short. Listed in full so the judgement can be audited and "
        "overruled."
    ),
}


def _group(results) -> dict:
    grouped = {tier: [] for tier in TIER_ORDER}
    for result in results:
        if result.triage is None:
            continue
        grouped[result.triage.tier].append(result)
    for tier in grouped:
        grouped[tier].sort(key=lambda r: getattr(r, "total", getattr(r, "foundation", 0.0)), reverse=True)
    return grouped


def _score_of(result) -> float:
    return getattr(result, "total", getattr(result, "foundation", 0.0))


def render_markdown(results, req, title: str | None = None) -> str:
    """A review queue a human reads, grouped by tier."""
    grouped = _group(results)
    total = sum(len(v) for v in grouped.values())
    kept = total - len(grouped[Tier.DISCARD])

    lines = [
        f"# {title or f'Candidate review queue — {req.req_id}'}",
        "",
        f"**{req.title}** · {total} candidates sourced · "
        f"**{kept} kept in the queue** · {len(grouped[Tier.DISCARD])} set aside",
        "",
        "> A candidate is only set aside on positive evidence of a miss. "
        "A low score built from signals we never observed is a statement "
        "about our data, not about the person, and never removes anyone.",
        "",
    ]

    for tier in TIER_ORDER:
        entries = grouped[tier]
        lines.append(f"## {TIER_HEADINGS[tier]} ({len(entries)})")
        lines.append("")
        if tier in TIER_BLURBS:
            lines.append(f"_{TIER_BLURBS[tier]}_")
            lines.append("")
        if not entries:
            lines.append("_None._")
            lines.append("")
            continue

        for result in entries:
            decision = result.triage
            name = result.candidate.name
            url = result.candidate.profile_url
            lines.append(
                f"### [{name}]({url}) — {_score_of(result):.0f} pts, "
                f"{decision.confidence:.0%} measured"
            )
            lines.append("")
            lines.append(f"- **Why:** {decision.reason}")
            if decision.caveat:
                lines.append(f"- **But:** {decision.caveat}")
            if result.matched_skills:
                lines.append(f"- **Matched:** {', '.join(result.matched_skills)}")
            if decision.missing_must_haves:
                lines.append(
                    f"- **Missing must-have:** {', '.join(decision.missing_must_haves)}"
                )
            if decision.imputed_categories:
                lines.append(
                    f"- **Scored on guesswork:** "
                    f"{', '.join(decision.imputed_categories)}"
                )
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_console(results, req, top: int = 8) -> str:
    """Compact terminal summary, tier by tier."""
    grouped = _group(results)
    total = sum(len(v) for v in grouped.values())
    kept = total - len(grouped[Tier.DISCARD])

    out = [
        "",
        f"{total} candidates · {kept} kept in queue · "
        f"{len(grouped[Tier.DISCARD])} set aside on evidence",
        "",
    ]
    for tier in TIER_ORDER:
        entries = grouped[tier]
        out.append(f"{TIER_HEADINGS[tier]} ({len(entries)})")
        out.append("-" * 66)
        if not entries:
            out.append("  (none)")
            out.append("")
            continue
        for result in entries[:top]:
            decision = result.triage
            out.append(
                f"  {result.candidate.name:<26.26} {_score_of(result):>5.1f}  "
                f"{decision.confidence:>4.0%} measured"
            )
            out.append(f"      why: {decision.reason}")
            if decision.caveat:
                out.append(f"      but: {decision.caveat}")
        if len(entries) > top:
            out.append(f"  ... and {len(entries) - top} more")
        out.append("")
    return "\n".join(out)
