from sourcing.candidate import Candidate
from sourcing.config import Req, RequiredSkill
from sourcing.scoring import WEIGHTS, score_candidate


def make_req(**overrides) -> Req:
    defaults = dict(
        req_id="test-001",
        title="Test Req",
        required_skills=[
            RequiredSkill(skill="python", weight="high"),
            RequiredSkill(skill="postgresql", weight="normal"),
        ],
        skill_aliases={"postgresql": ["postgres", "psql"]},
        min_years_experience=5,
        location="New York, NY",
        remote_ok=False,
        qualify_threshold=60,
    )
    defaults.update(overrides)
    return Req(**defaults)


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def test_perfect_candidate_scores_100():
    req = make_req(remote_ok=True)
    candidate = Candidate(
        name="Perfect Match",
        source="linkedin",
        profile_url="https://example.test/perfect",
        skills={"python", "postgresql"},
        years_experience=10,
        currently_open_to_work=True,
    )
    result = score_candidate(candidate, req, corroborated=True)
    assert result.total == 100
    assert result.qualified


def test_skill_alias_is_recognized():
    req = make_req(remote_ok=True)
    candidate = Candidate(
        name="Alias User",
        source="linkedin",
        profile_url="https://example.test/alias",
        skills={"python", "postgres"},  # alias, not canonical "postgresql"
        years_experience=10,
    )
    result = score_candidate(candidate, req, corroborated=False)
    assert "postgresql" in result.matched_skills


def test_high_weight_skill_counts_double():
    req = make_req(remote_ok=True)
    # Only has the high-weight skill (python), not the normal-weight one (postgresql).
    python_only = Candidate(
        name="Python Only",
        source="linkedin",
        profile_url="https://example.test/python-only",
        skills={"python"},
        years_experience=10,
    )
    # Only has the normal-weight skill (postgresql), not the high-weight one (python).
    postgres_only = Candidate(
        name="Postgres Only",
        source="linkedin",
        profile_url="https://example.test/postgres-only",
        skills={"postgresql"},
        years_experience=10,
    )
    python_result = score_candidate(python_only, req, corroborated=False)
    postgres_result = score_candidate(postgres_only, req, corroborated=False)
    assert python_result.total > postgres_result.total


def test_no_matching_skills_scores_low_and_not_qualified():
    req = make_req(remote_ok=True)
    candidate = Candidate(
        name="No Match",
        source="linkedin",
        profile_url="https://example.test/no-match",
        skills={"cobol"},
        years_experience=1,
    )
    result = score_candidate(candidate, req, corroborated=False)
    assert not result.qualified


def test_remote_ok_ignores_location_mismatch():
    req = make_req(remote_ok=True, location="New York, NY")
    candidate = Candidate(
        name="Faraway",
        source="linkedin",
        profile_url="https://example.test/faraway",
        skills={"python", "postgresql"},
        years_experience=10,
        location="Tokyo, Japan",
    )
    result = score_candidate(candidate, req, corroborated=False)
    assert result.category_scores["location"] == 1.0


def test_location_mismatch_scores_zero_when_not_remote_ok():
    req = make_req(remote_ok=False, location="New York, NY")
    candidate = Candidate(
        name="Faraway",
        source="linkedin",
        profile_url="https://example.test/faraway",
        skills={"python", "postgresql"},
        years_experience=10,
        location="Tokyo, Japan",
    )
    result = score_candidate(candidate, req, corroborated=False)
    assert result.category_scores["location"] == 0.0


def test_corroboration_bonus_applied():
    req = make_req(remote_ok=True)
    candidate = Candidate(
        name="Multi Source",
        source="linkedin",
        profile_url="https://example.test/multi",
        skills={"python", "postgresql"},
        years_experience=10,
    )
    corroborated = score_candidate(candidate, req, corroborated=True)
    not_corroborated = score_candidate(candidate, req, corroborated=False)
    assert corroborated.total - not_corroborated.total == WEIGHTS["corroboration"]


def test_missing_experience_signal_is_neutral_not_zero():
    req = make_req(remote_ok=True)
    candidate = Candidate(
        name="No Experience Data",
        source="linkedin",
        profile_url="https://example.test/no-exp",
        skills={"python", "postgresql"},
    )
    result = score_candidate(candidate, req, corroborated=False)
    assert result.category_scores["experience"] == 0.5
