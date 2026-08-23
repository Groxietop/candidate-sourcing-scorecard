"""End-to-end checks on the command-line entry points.

Written after walking the README as a new user and finding that two
documented capabilities -- the Ashby `--dry-run` and the feedback loop --
had no way to invoke them. These tests exist so that can't silently
regress: if a CLI the README promises stops working, this fails.
"""

import json

import pytest

from sourcing import cli_feedback, cli_push


# --- ashby push ------------------------------------------------------------


def test_dry_run_is_the_default_and_sends_nothing(capsys):
    """A user with no credentials must be able to inspect the integration."""
    code = cli_push.main(
        [
            "--req", "reqs/example-backend-engineer.yaml",
            "--linkedin-csv", "data/fake_linkedin_candidates.csv",
            "--skip-github",
            "--job-id", "job_test",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "DRY RUN" in out
    assert "nothing is sent" in out


def test_dry_run_reports_every_request_it_would_make(capsys):
    cli_push.main(
        ["--req", "reqs/example-backend-engineer.yaml",
         "--linkedin-csv", "data/fake_linkedin_candidates.csv",
         "--skip-github", "--job-id", "job_test"]
    )
    out = capsys.readouterr().out
    assert "POST /candidate.create" in out
    assert "POST /candidate.createNote" in out
    assert "POST /application.create" in out


def test_dry_run_never_lists_a_rejection_call(capsys):
    """The load-bearing property, asserted on real output."""
    cli_push.main(
        ["--req", "reqs/example-backend-engineer.yaml",
         "--linkedin-csv", "data/fake_linkedin_candidates.csv",
         "--skip-github", "--job-id", "job_test"]
    )
    out = capsys.readouterr().out
    assert "candidate.reject" not in out.replace(
        "no candidate.reject / archive call appears above", ""
    )
    assert "never rejects in the ATS" in out


def test_show_payloads_prints_the_note_with_its_caveat(capsys):
    cli_push.main(
        ["--req", "reqs/example-backend-engineer.yaml",
         "--linkedin-csv", "data/fake_linkedin_candidates.csv",
         "--skip-github", "--job-id", "job_test", "--show-payloads"]
    )
    out = capsys.readouterr().out
    assert "Sourcing scorecard" in out
    assert "does not reject" in out


def test_send_without_a_key_refuses_rather_than_half_running(monkeypatch):
    monkeypatch.delenv("ASHBY_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ASHBY_API_KEY"):
        cli_push.main(
            ["--req", "reqs/example-backend-engineer.yaml",
             "--linkedin-csv", "data/fake_linkedin_candidates.csv",
             "--skip-github", "--send"]
        )


# --- feedback --------------------------------------------------------------


def test_empty_log_reports_no_numbers(tmp_path, capsys):
    """The honesty requirement: never render an invented accuracy."""
    log = tmp_path / "d.jsonl"
    cli_feedback.main(["--log", str(log), "report"])
    out = capsys.readouterr().out
    assert "Decisions recorded: 0" in out
    assert "Nothing to report yet" in out
    assert "%" not in out


def test_record_then_report_round_trip(tmp_path, capsys):
    log = tmp_path / "d.jsonl"
    cli_feedback.main(
        ["--log", str(log), "record", "--candidate", "Ada", "--req", "r1",
         "--tier", "strong", "--verdict", "advance"]
    )
    cli_feedback.main(
        ["--log", str(log), "record", "--candidate", "Grace", "--req", "r1",
         "--tier", "discard", "--verdict", "advance", "--reason", "actually_strong"]
    )
    capsys.readouterr()

    cli_feedback.main(["--log", str(log), "report"])
    out = capsys.readouterr().out
    assert "Decisions recorded: 2" in out
    # Grace was set aside and wanted -> she must be named for recovery.
    assert "Grace" in out
    assert "should not have" in out


def test_report_refuses_a_before_after_split_on_thin_data(tmp_path, capsys):
    log = tmp_path / "d.jsonl"
    cli_feedback.main(
        ["--log", str(log), "record", "--candidate", "A", "--req", "r1",
         "--tier", "strong", "--verdict", "advance"]
    )
    capsys.readouterr()
    cli_feedback.main(["--log", str(log), "report"])
    assert "needs 20 decisions" in capsys.readouterr().out


def test_calibrate_proposes_nothing_without_evidence(tmp_path, capsys):
    log = tmp_path / "d.jsonl"
    cli_feedback.main(
        ["--log", str(log), "record", "--candidate", "A", "--req", "r1",
         "--tier", "strong", "--verdict", "reject", "--reason", "insufficient_seniority"]
    )
    capsys.readouterr()
    cli_feedback.main(
        ["--log", str(log), "calibrate", "--out", str(tmp_path / "c.json")]
    )
    assert "No weight changes proposed" in capsys.readouterr().out


def test_calibrate_fires_once_the_evidence_is_there(tmp_path, capsys):
    log = tmp_path / "d.jsonl"
    for i in range(12):
        cli_feedback.main(
            ["--log", str(log), "record", "--candidate", f"C{i}", "--req", "r1",
             "--tier", "strong", "--verdict", "reject",
             "--reason", "insufficient_seniority"]
        )
    capsys.readouterr()

    out_path = tmp_path / "c.json"
    cli_feedback.main(["--log", str(log), "calibrate", "--out", str(out_path)])
    out = capsys.readouterr().out

    assert "experience" in out
    assert "decrease" in out
    payload = json.loads(out_path.read_text())
    assert payload["applied"] is False


def test_import_verdicts_bridges_the_ui_into_the_durable_log(tmp_path, capsys):
    """The UI keeps verdicts in page state; this is how they become data."""
    log = tmp_path / "d.jsonl"
    exported = tmp_path / "ui.json"
    exported.write_text(
        json.dumps(
            [
                {"name": "Nadia Osei", "tier": "caveated", "verdict": "advance",
                 "reason": "actually_strong"},
                {"name": "Nobody", "tier": "strong", "verdict": ""},  # undecided
            ]
        )
    )
    cli_feedback.main(
        ["--log", str(log), "import-verdicts", "--file", str(exported), "--req", "r1"]
    )
    out = capsys.readouterr().out
    # The undecided card must not become a decision.
    assert "Imported 1 verdicts" in out


def test_invalid_tier_is_rejected_by_the_parser(tmp_path):
    with pytest.raises(SystemExit):
        cli_feedback.main(
            ["--log", str(tmp_path / "d.jsonl"), "record", "--candidate", "A",
             "--req", "r1", "--tier", "banana", "--verdict", "advance"]
        )
