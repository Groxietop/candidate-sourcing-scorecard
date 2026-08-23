"""Tests for the rule the whole tool rests on:

    a candidate may only be set aside on positive evidence of a miss,
    never on the absence of evidence.

Most of these are written as the specific failure they prevent — the dream
candidate who gets deleted because we knew nothing about them.
"""

from sourcing.candidate import Candidate
from sourcing.config import Req, RequiredSkill
from sourcing.evidence import Evidence, Signal, caveat_for
from sourcing.scoring import WEIGHTS, score_candidate
from sourcing.triage import Tier, summarise, triage


def _req(**overrides) -> Req:
    defaults = dict(
        req_id="r1",
        title="Backend Engineer",
        required_skills=[
            RequiredSkill(skill="python", weight="high"),
            RequiredSkill(skill="docker"),
        ],
        min_years_experience=5,
        location="New York, NY",
        remote_ok=True,
        qualify_threshold=60,
    )
    defaults.update(overrides)
    return Req(**defaults)


def _evidence(**values) -> Evidence:
    """values maps category -> (value, observed)."""
    return Evidence(
        signals=[Signal(cat, val, seen) for cat, (val, seen) in values.items()]
    )


# --- confidence ------------------------------------------------------------


def test_confidence_is_the_weighted_share_of_measured_signals():
    evidence = _evidence(
        skill_match=(1.0, True),   # weight 40
        experience=(0.5, False),   # weight 20
        recency=(0.5, False),      # weight 20
        location=(1.0, True),      # weight 10
        corroboration=(0.0, True), # weight 10
    )
    # observed weight 60 of 100
    assert evidence.confidence(WEIGHTS) == 0.6


def test_confidence_is_one_when_everything_was_measured():
    evidence = _evidence(
        skill_match=(1.0, True), experience=(1.0, True), recency=(1.0, True),
        location=(1.0, True), corroboration=(1.0, True),
    )
    assert evidence.confidence(WEIGHTS) == 1.0


def test_corroboration_never_counts_as_a_measured_weakness():
    """A zero here reflects where we searched, not the candidate."""
    evidence = _evidence(
        skill_match=(1.0, True), experience=(1.0, True), recency=(1.0, True),
        location=(1.0, True), corroboration=(0.0, True),
    )
    weak = evidence.observed_weaknesses(WEIGHTS)
    assert [s.category for s in weak] == []


# --- the core rule ---------------------------------------------------------


def test_low_score_built_on_guesswork_is_never_discarded():
    """The dream candidate: senior engineer, all work in private repos.

    Scores badly because we could not observe anything. Must survive.
    """
    evidence = _evidence(
        skill_match=(0.5, True),
        experience=(0.5, False),
        recency=(0.5, False),
        location=(0.5, False),
        corroboration=(0.0, True),
    )
    result = triage(45.0, _req(), evidence, WEIGHTS, matched_skills=["python"])
    assert result.tier is Tier.CAVEATED
    assert result.stays_in_queue
    assert "guesswork" in result.reason
    assert result.caveat  # must explain why we might be wrong


def test_discard_requires_the_skill_set_to_have_been_observed():
    """Missing a must-have only counts if we actually saw their skills."""
    unobserved = _evidence(
        skill_match=(0.0, False),
        experience=(1.0, True), recency=(1.0, True),
        location=(1.0, True), corroboration=(1.0, True),
    )
    result = triage(30.0, _req(), unobserved, WEIGHTS, matched_skills=[])
    assert result.tier is not Tier.DISCARD
    assert result.stays_in_queue


def test_discard_fires_on_an_observed_missing_must_have():
    observed = _evidence(
        skill_match=(0.2, True),
        experience=(1.0, True), recency=(1.0, True),
        location=(1.0, True), corroboration=(1.0, True),
    )
    result = triage(35.0, _req(), observed, WEIGHTS, matched_skills=["docker"])
    assert result.tier is Tier.DISCARD
    assert not result.stays_in_queue
    assert "python" in result.missing_must_haves
    # Even a discard has to say why it might be wrong.
    assert result.caveat


def test_marginal_score_is_caveated_not_discarded():
    """59 against a bar of 60 is not evidence of anything."""
    evidence = _evidence(
        skill_match=(0.9, True), experience=(0.6, True), recency=(0.6, True),
        location=(1.0, True), corroboration=(0.0, True),
    )
    result = triage(59.0, _req(), evidence, WEIGHTS, matched_skills=["python", "docker"])
    assert result.tier is Tier.CAVEATED
    assert result.stays_in_queue


def test_strong_requires_both_the_bar_and_real_evidence():
    evidence = _evidence(
        skill_match=(1.0, True), experience=(1.0, True), recency=(1.0, True),
        location=(1.0, True), corroboration=(1.0, True),
    )
    result = triage(95.0, _req(), evidence, WEIGHTS, matched_skills=["python", "docker"])
    assert result.tier is Tier.STRONG


def test_clearing_the_bar_on_guesswork_is_only_review():
    """A high score we cannot vouch for should not read as 'strong'."""
    evidence = _evidence(
        skill_match=(1.0, True),
        experience=(0.5, False), recency=(0.5, False), location=(0.5, False),
        corroboration=(1.0, True),
    )
    result = triage(75.0, _req(), evidence, WEIGHTS, matched_skills=["python", "docker"])
    assert result.tier is Tier.REVIEW
    assert result.stays_in_queue


def test_over_the_bar_but_missing_a_must_have_is_review():
    evidence = _evidence(
        skill_match=(0.6, True), experience=(1.0, True), recency=(1.0, True),
        location=(1.0, True), corroboration=(1.0, True),
    )
    result = triage(80.0, _req(), evidence, WEIGHTS, matched_skills=["docker"])
    assert result.tier is Tier.REVIEW
    assert result.missing_must_haves == ["python"]


# --- caveats ---------------------------------------------------------------


def test_every_non_strong_tier_carries_a_caveat():
    for total, ev, matched in [
        (45.0, _evidence(skill_match=(0.5, True), experience=(0.5, False),
                         recency=(0.5, False), location=(0.5, False),
                         corroboration=(0.0, True)), ["python"]),
        (35.0, _evidence(skill_match=(0.2, True), experience=(1.0, True),
                         recency=(1.0, True), location=(1.0, True),
                         corroboration=(1.0, True)), ["docker"]),
    ]:
        result = triage(total, _req(), ev, WEIGHTS, matched_skills=matched)
        assert result.caveat, f"{result.tier} had no caveat"


def test_caveat_text_names_the_actual_failure_mode():
    assert "private" in caveat_for(["recency"])
    assert "relocate" in caveat_for(["location"])
    assert "public repositories" in caveat_for(["skill_match"])


def test_caveat_joins_multiple_reasons_readably():
    text = caveat_for(["recency", "location"])
    assert "; and " in text


def test_unknown_category_contributes_no_caveat_text():
    assert caveat_for(["not_a_category"]) == ""


# --- end to end through the real scorer ------------------------------------


def test_sparse_github_profile_survives_scoring():
    """The regression this redesign exists to prevent."""
    candidate = Candidate(
        name="Private Repo Veteran",
        source="github",
        profile_url="https://github.com/example",
        skills={"python"},
        github_handle="example",
        # No account age, no stars, no activity, no location.
    )
    result = score_candidate(candidate, _req(), corroborated=False)
    assert result.triage is not None
    assert result.stays_in_queue, "a candidate we know nothing about was discarded"
    assert result.triage.confidence < 0.75
    assert "experience" in result.triage.imputed_categories


def test_fully_observed_mismatch_is_discardable():
    """Every signal measured, genuinely wrong skill set, clearly under the bar."""
    candidate = Candidate(
        name="Genuine Mismatch",
        source="github",
        profile_url="https://github.com/example2",
        skills={"cobol", "fortran"},
        account_age_years=8.0,
        total_stars=100,
        days_since_last_active=900,   # measured, and genuinely dormant
        location="Reykjavik, Iceland",  # measured, and genuinely not the req
        github_handle="example2",
    )
    result = score_candidate(candidate, _req(remote_ok=False), corroborated=True)
    assert result.triage.confidence >= 0.75
    assert result.triage.tier is Tier.DISCARD


def test_non_skill_signals_alone_cannot_read_as_qualified():
    """A candidate with none of the required skills must not pass silently.

    Under the old binary flag, being active, experienced, local and
    corroborated summed to exactly the threshold with zero skill match, and
    `qualified` came back True. Triage catches it as a missing must-have.
    """
    candidate = Candidate(
        name="Wrong Stack, Great Profile",
        source="github",
        profile_url="https://github.com/example3",
        skills={"cobol"},
        account_age_years=8.0,
        total_stars=100,
        days_since_last_active=10,
        location="New York, NY",
        github_handle="example3",
    )
    result = score_candidate(candidate, _req(remote_ok=False), corroborated=True)
    assert result.qualified is True  # the old flag still says yes
    assert result.triage.tier is Tier.REVIEW  # the new one flags it
    assert result.triage.missing_must_haves == ["python"]


def test_summarise_counts_every_tier():
    counts = summarise([])
    assert set(counts) == {"strong", "review", "caveated", "discard"}
    assert all(v == 0 for v in counts.values())
