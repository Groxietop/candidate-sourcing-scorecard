from datetime import datetime, timedelta, timezone

import pytest

from sourcing.candidate import Candidate
from sourcing.config import Req, RequiredSkill
from sourcing.integrations import linkedin_recruiter as seat
from sourcing.integrations.ashby import (
    APPLICATION_CREATE,
    CANDIDATE_CREATE,
    CANDIDATE_NOTE,
    CANDIDATE_TAG,
    AshbyClient,
    HttpTransport,
    RecordingTransport,
    push_pool,
)
from sourcing.scoring import score_candidate


def _req(**overrides) -> Req:
    defaults = dict(
        req_id="r1",
        title="Backend Engineer",
        required_skills=[RequiredSkill(skill="python", weight="high")],
        min_years_experience=5,
        location="New York, NY",
        remote_ok=True,
        qualify_threshold=60,
    )
    defaults.update(overrides)
    return Req(**defaults)


def _scored(name, skills, **kwargs):
    candidate = Candidate(
        name=name,
        source="github",
        profile_url=f"https://github.com/{name}",
        skills=set(skills),
        github_handle=name,
        **kwargs,
    )
    return score_candidate(candidate, _req(), corroborated=False)


# --- the rule that matters -------------------------------------------------


def test_nobody_is_ever_rejected_in_the_ats():
    """The integration must have no path that rejects a candidate.

    Pushing a rejection into the system of record is where an automated
    judgement becomes irreversible.
    """
    results = [
        _scored("Strong", ["python"], account_age_years=9.0, total_stars=400,
                days_since_last_active=5),
        _scored("SetAside", ["cobol"], account_age_years=9.0, total_stars=400,
                days_since_last_active=900),
    ]
    transport = RecordingTransport()
    push_pool(results, job_id="job-1", transport=transport)

    paths = [path for path, _ in transport.sent]
    assert not any("reject" in p.lower() or "archive" in p.lower() for p in paths)


def test_set_aside_candidates_still_reach_the_ats():
    """Being set aside must not mean being dropped on the floor."""
    results = [
        _scored("SetAside", ["cobol"], account_age_years=9.0, total_stars=400,
                days_since_last_active=900)
    ]
    transport = RecordingTransport()
    pushed = push_pool(results, job_id="job-1", transport=transport)

    assert pushed[0].pushed is True
    assert pushed[0].ashby_candidate_id
    assert len(transport.calls_to(CANDIDATE_CREATE)) == 1


def test_only_advanced_tiers_become_active_applications():
    results = [
        _scored("Strong", ["python"], account_age_years=9.0, total_stars=400,
                days_since_last_active=5),
        _scored("SetAside", ["cobol"], account_age_years=9.0, total_stars=400,
                days_since_last_active=900),
    ]
    transport = RecordingTransport()
    push_pool(results, job_id="job-1", transport=transport)

    # Both created; only the strong one attached to the job.
    assert len(transport.calls_to(CANDIDATE_CREATE)) == 2
    assert len(transport.calls_to(APPLICATION_CREATE)) == 1


def test_the_caveat_travels_into_the_ats_note():
    """A set-aside note is useless without the reason it might be wrong."""
    results = [
        _scored("Sparse", ["python"])  # no age/stars/activity -> imputed
    ]
    transport = RecordingTransport()
    push_pool(results, job_id="job-1", transport=transport)

    note = transport.calls_to(CANDIDATE_NOTE)[0]["note"]["value"]
    assert "But:" in note
    assert "does not reject" in note


def test_note_records_how_much_of_the_score_was_measured():
    results = [_scored("Sparse", ["python"])]
    transport = RecordingTransport()
    push_pool(results, job_id="job-1", transport=transport)
    note = transport.calls_to(CANDIDATE_NOTE)[0]["note"]["value"]
    assert "measured signals" in note


def test_tier_tag_marks_caveated_candidates_as_do_not_cut():
    from sourcing.integrations.ashby import TIER_TAGS

    assert "do-not-cut" in TIER_TAGS["caveated"]


def test_tag_is_written_for_every_candidate():
    results = [_scored("Sparse", ["python"])]
    transport = RecordingTransport()
    pushed = push_pool(results, job_id="job-1", transport=transport)
    assert pushed[0].tagged
    assert len(transport.calls_to(CANDIDATE_TAG)) == 1


# --- client shape ----------------------------------------------------------


def test_payloads_only_carry_fields_we_actually_have():
    results = [_scored("Bare", ["python"])]
    transport = RecordingTransport()
    push_pool(results, job_id="job-1", transport=transport)

    payload = transport.calls_to(CANDIDATE_CREATE)[0]
    assert payload["name"] == "Bare"
    # No location was known, so no empty location object should be sent.
    assert "location" not in payload


def test_untriaged_result_is_reported_not_silently_dropped():
    class Bare:
        candidate = Candidate(name="X", source="github", profile_url="u")
        triage = None
        matched_skills = []

    pushed = push_pool([Bare()], job_id="j", transport=RecordingTransport())
    assert pushed[0].pushed is False
    assert "never triaged" in pushed[0].skipped_reason


def test_failed_create_is_surfaced_not_swallowed():
    class Failing(RecordingTransport):
        def post(self, path, payload):
            super().post(path, payload)
            return {"success": False, "errors": ["nope"]}

    pushed = push_pool([_scored("A", ["python"])], job_id="j", transport=Failing())
    assert pushed[0].pushed is False
    assert "did not return an id" in pushed[0].skipped_reason


def test_http_transport_refuses_to_run_without_a_key():
    with pytest.raises(ValueError, match="API key is required"):
        HttpTransport(api_key="")


def test_list_jobs_returns_empty_on_an_unsuccessful_response():
    class Bad(RecordingTransport):
        def post(self, path, payload):
            return {"success": False}

    assert AshbyClient(Bad()).list_jobs() == []


# --- LinkedIn seat connector ----------------------------------------------


def _export(tmp_path, rows="Ada,python;docker,https://li/ada\n", age_days=1):
    path = tmp_path / "export.csv"
    path.write_text("name,skills,profile_url\n" + rows)
    return seat.SeatExport(
        path=path,
        seat_owner="recruiter@example.com",
        exported_at=datetime.now(timezone.utc) - timedelta(days=age_days),
    )


def test_export_validates_required_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("name,headline\nAda,Engineer\n")
    problems = seat.validate_export(bad)
    assert any("missing required columns" in p for p in problems)


def test_export_with_no_rows_is_rejected(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("name,skills,profile_url\n")
    assert any("no candidate rows" in p for p in seat.validate_export(empty))


def test_missing_file_is_reported_clearly(tmp_path):
    assert "does not exist" in seat.validate_export(tmp_path / "nope.csv")[0]


def test_load_raises_rather_than_returning_a_short_pool(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("name,headline\nAda,Engineer\n")
    export = seat.SeatExport(
        path=bad, seat_owner="r", exported_at=datetime.now(timezone.utc)
    )
    with pytest.raises(ValueError, match="cannot load"):
        seat.load(export)


def test_fresh_export_is_not_stale(tmp_path):
    assert _export(tmp_path, age_days=3).is_stale is False


def test_stale_export_clears_open_to_work(tmp_path):
    """An 'open to work' flag from six months ago is not evidence today."""
    rows = "Ada,python,https://li/ada\n"
    path = tmp_path / "e.csv"
    path.write_text("name,skills,profile_url,currently_open_to_work\n" + "Ada,python,https://li/ada,true\n")
    export = seat.SeatExport(
        path=path,
        seat_owner="r",
        exported_at=datetime.now(timezone.utc) - timedelta(days=200),
    )
    assert export.is_stale
    candidates = seat.load(export)
    assert candidates[0].currently_open_to_work is None


def test_provenance_names_the_seat_and_warns_when_stale(tmp_path):
    export = _export(tmp_path, age_days=200)
    note = export.provenance()
    assert "recruiter@example.com" in note
    assert "may no longer hold" in note


def test_freshness_summary_counts_stale_exports(tmp_path):
    exports = [_export(tmp_path, age_days=2), _export(tmp_path, age_days=300)]
    summary = seat.describe_freshness(exports)
    assert summary["exports"] == 2
    assert summary["stale"] == 1
    assert summary["oldest_days"] >= 300


def test_freshness_summary_handles_no_exports():
    assert seat.describe_freshness([])["exports"] == 0
