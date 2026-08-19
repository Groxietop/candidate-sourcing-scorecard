from sourcing.candidate import Candidate
from sourcing.config import Req, RequiredSkill
from sourcing.scoring_experimental import (
    FOUNDATION_WEIGHTS,
    GITHUB_BONUS_WEIGHTS,
    GITHUB_MOMENTUM_WEIGHTS,
    LINKEDIN_BONUS_WEIGHTS,
    LINKEDIN_MOMENTUM_WEIGHTS,
    bonus_score,
    foundation_score,
    momentum_score,
    score_candidate_experimental,
)


def make_req(**overrides) -> Req:
    defaults = dict(
        req_id="test-001",
        title="Test Req",
        required_skills=[
            RequiredSkill(skill="python", weight="high"),
            RequiredSkill(skill="postgresql", weight="normal"),
        ],
        skill_aliases={},
        min_years_experience=5,
        location="New York, NY",
        remote_ok=False,
        qualify_threshold=60,
    )
    defaults.update(overrides)
    return Req(**defaults)


def test_all_weight_tables_sum_to_100():
    assert sum(FOUNDATION_WEIGHTS.values()) == 100
    assert sum(GITHUB_BONUS_WEIGHTS.values()) == 100
    assert sum(LINKEDIN_BONUS_WEIGHTS.values()) == 100
    assert sum(GITHUB_MOMENTUM_WEIGHTS.values()) == 100
    assert sum(LINKEDIN_MOMENTUM_WEIGHTS.values()) == 100


def test_non_local_candidate_is_not_penalized_on_foundation():
    """The relocation fix: a candidate far from the req's location must
    score identically to an otherwise-identical local candidate on the
    Foundation axis, since location isn't part of it at all.
    """
    req = make_req()
    local = Candidate(
        name="Local",
        source="linkedin",
        profile_url="https://example.test/local",
        skills={"python", "postgresql"},
        years_experience=6,
        location="New York, NY",
    )
    remote = Candidate(
        name="Remote",
        source="linkedin",
        profile_url="https://example.test/remote",
        skills={"python", "postgresql"},
        years_experience=6,
        location="Tokyo, Japan",
    )
    local_result = score_candidate_experimental(local, req)
    remote_result = score_candidate_experimental(remote, req)
    assert local_result.foundation == remote_result.foundation
    assert local_result.qualified == remote_result.qualified


def test_non_local_candidate_gets_no_bonus_but_not_a_penalty():
    req = make_req()
    remote = Candidate(
        name="Remote",
        source="linkedin",
        profile_url="https://example.test/remote",
        skills={"python", "postgresql"},
        years_experience=6,
        location="Tokyo, Japan",
    )
    _, subs = bonus_score(remote, req)
    assert subs["location"] == 0.0  # no bonus...
    total, _ = bonus_score(remote, req)
    assert total >= 0  # ...but never negative


def test_dormant_github_profile_not_penalized_only_unrewarded():
    req = make_req(remote_ok=True)
    dormant = Candidate(
        name="Dormant",
        source="github",
        profile_url="https://github.com/dormant",
        skills={"python", "postgresql"},
        account_age_years=8,
        total_stars=10,
        days_since_last_active=900,  # long inactive
    )
    total, subs = bonus_score(dormant, req)
    assert subs["activity"] == 0.0
    assert total >= 0


def test_missing_experience_signal_scores_neutral_experience_component():
    req = make_req(remote_ok=True)
    candidate = Candidate(
        name="No Data",
        source="linkedin",
        profile_url="https://example.test/no-data",
        skills={"python", "postgresql"},
    )
    foundation, matched = foundation_score(candidate, req)
    assert "python" in matched
    assert foundation > 0  # skill match alone still contributes


def test_bonus_never_negative_with_zero_data():
    req = make_req(remote_ok=True)
    candidate = Candidate(
        name="Blank",
        source="linkedin",
        profile_url="https://example.test/blank",
        skills=set(),
    )
    total, _ = bonus_score(candidate, req)
    assert total == 0.0  # floor, not negative


def test_momentum_floors_at_zero_with_no_trend_data():
    req = make_req(remote_ok=True)
    github_candidate = Candidate(
        name="No Trend",
        source="github",
        profile_url="https://github.com/no-trend",
        skills={"python"},
    )
    linkedin_candidate = Candidate(
        name="No Title",
        source="linkedin",
        profile_url="https://example.test/no-title",
        skills={"python"},
    )
    gh_total, _ = momentum_score(github_candidate, req)
    li_total, _ = momentum_score(linkedin_candidate, req)
    assert gh_total == 0.0
    assert li_total == 0.0


def test_github_acceleration_rewards_recent_concentration():
    req = make_req(remote_ok=True)
    accelerating = Candidate(
        name="Accelerating",
        source="github",
        profile_url="https://github.com/accelerating",
        skills={"python"},
        recent_push_count=10,
        prior_push_count=0,
    )
    steady = Candidate(
        name="Steady",
        source="github",
        profile_url="https://github.com/steady",
        skills={"python"},
        recent_push_count=5,
        prior_push_count=5,
    )
    accel_total, _ = momentum_score(accelerating, req)
    steady_total, _ = momentum_score(steady, req)
    assert accel_total > steady_total


def test_title_velocity_rewards_fast_progression_not_slow():
    req = make_req(remote_ok=True)
    fast = Candidate(
        name="Fast Track",
        source="linkedin",
        profile_url="https://example.test/fast",
        skills={"python"},
        years_experience=2,
        current_title="Senior Engineer",  # benchmark: 5 years
    )
    on_pace = Candidate(
        name="On Pace",
        source="linkedin",
        profile_url="https://example.test/on-pace",
        skills={"python"},
        years_experience=6,
        current_title="Senior Engineer",
    )
    fast_total, _ = momentum_score(fast, req)
    on_pace_total, _ = momentum_score(on_pace, req)
    assert fast_total > 0
    assert on_pace_total == 0
    assert fast_total > on_pace_total


def test_qualified_determined_by_foundation_only():
    # High bonus/momentum should never make a low-foundation candidate "qualified".
    req = make_req(remote_ok=True, qualify_threshold=90)
    candidate = Candidate(
        name="Flashy But Underqualified",
        source="linkedin",
        profile_url="https://example.test/flashy",
        skills={"python"},  # misses postgresql
        years_experience=1,
        certifications="Everything",
        open_source_contributor=True,
        volunteer_experience=True,
        education_level="PhD",
        current_title="Senior Engineer",
    )
    result = score_candidate_experimental(candidate, req)
    assert result.bonus > 0
    assert not result.qualified
