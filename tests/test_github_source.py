from sourcing.config import Req, RequiredSkill
from sourcing.github_source import build_search_query


def _req(**overrides) -> Req:
    defaults = dict(
        req_id="r1",
        title="t",
        required_skills=[RequiredSkill(skill="python"), RequiredSkill(skill="postgresql")],
        location="New York, NY",
        remote_ok=False,
    )
    defaults.update(overrides)
    return Req(**defaults)


def test_remote_ok_req_does_not_narrow_search_to_a_location():
    query = build_search_query(_req(remote_ok=True))
    assert "location:" not in query


def test_onsite_req_narrows_search_to_the_req_location():
    query = build_search_query(_req(remote_ok=False))
    assert 'location:"New York"' in query


def test_location_literally_remote_is_never_added_regardless_of_remote_ok():
    query = build_search_query(_req(location="Remote", remote_ok=False))
    assert "location:" not in query


def test_known_language_skill_becomes_a_language_qualifier():
    query = build_search_query(_req())
    assert "language:python" in query
    # only the first known-language skill becomes a qualifier; the rest stay free text
    assert "postgresql" in query
