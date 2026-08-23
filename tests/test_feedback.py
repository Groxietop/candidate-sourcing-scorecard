import pytest

from sourcing.calibration import (
    MIN_EVIDENCE,
    propose_adjustments,
    underrated_signal,
    write_report,
)
from sourcing.feedback import (
    ADVANCE,
    REJECT,
    Decision,
    FeedbackLog,
    compare_periods,
    evaluate,
    reason_rate,
    rejection_reasons,
)
from sourcing.scoring import WEIGHTS


def _decision(tier="strong", verdict=ADVANCE, reason="other", name="A"):
    return Decision(
        candidate_key=f"gh:{name}",
        candidate_name=name,
        req_id="r1",
        predicted_tier=tier,
        verdict=verdict,
        reason_code=reason,
    )


# --- the log ---------------------------------------------------------------


def test_log_round_trips_through_disk(tmp_path):
    log = FeedbackLog(tmp_path / "d.jsonl")
    log.record(_decision(name="Ada"))
    log.record(_decision(name="Grace", verdict=REJECT, reason="wrong_skills"))

    stored = log.all()
    assert [d.candidate_name for d in stored] == ["Ada", "Grace"]
    assert stored[1].reason_code == "wrong_skills"


def test_empty_log_reads_as_empty_not_an_error(tmp_path):
    assert FeedbackLog(tmp_path / "nothing.jsonl").all() == []


def test_log_is_append_only(tmp_path):
    log = FeedbackLog(tmp_path / "d.jsonl")
    for i in range(3):
        log.record(_decision(name=f"C{i}"))
    assert len(log.all()) == 3
    log.record(_decision(name="C0"))  # same candidate again
    assert len(log.all()) == 4, "an earlier decision was overwritten"


def test_invalid_verdict_is_rejected():
    with pytest.raises(ValueError, match="verdict must be"):
        _decision(verdict="maybe")


def test_invalid_reason_code_is_rejected():
    with pytest.raises(ValueError, match="unknown reason_code"):
        _decision(reason="vibes")


# --- metrics honesty -------------------------------------------------------


def test_no_decisions_yields_no_numbers_not_zeros():
    """The whole point: an empty log must not render as 0% performance."""
    metrics = evaluate([])
    assert metrics["decisions"] == 0
    assert metrics["precision"] is None
    assert metrics["recall"] is None
    assert metrics["missed_rate"] is None


def test_precision_counts_only_advanced_candidates():
    decisions = [
        _decision("strong", ADVANCE),
        _decision("review", ADVANCE),
        _decision("strong", REJECT, "wrong_skills"),
        # Set-aside candidates must not enter the precision denominator.
        _decision("discard", REJECT, "wrong_skills"),
    ]
    assert evaluate(decisions)["precision"] == pytest.approx(2 / 3)


def test_missed_rate_is_the_false_negative_rate_on_the_discard_pile():
    decisions = [
        _decision("discard", REJECT, "wrong_skills"),
        _decision("caveated", REJECT, "wrong_skills"),
        _decision("caveated", ADVANCE, "actually_strong"),  # we were wrong
        _decision("discard", ADVANCE, "actually_strong"),   # we were wrong
    ]
    metrics = evaluate(decisions)
    assert metrics["set_aside"] == 4
    assert metrics["missed_count"] == 2
    assert metrics["missed_rate"] == pytest.approx(0.5)


def test_missed_candidates_are_named_so_they_can_be_recovered():
    decisions = [_decision("discard", ADVANCE, "actually_strong", name="Dream")]
    assert evaluate(decisions)["missed_candidates"][0]["name"] == "Dream"


def test_recall_accounts_for_the_ones_we_set_aside_wrongly():
    decisions = [
        _decision("strong", ADVANCE),          # true positive
        _decision("discard", ADVANCE, "actually_strong"),  # missed
    ]
    assert evaluate(decisions)["recall"] == pytest.approx(0.5)


def test_rejection_reasons_are_counted_most_common_first():
    decisions = [
        _decision("strong", REJECT, "insufficient_seniority"),
        _decision("strong", REJECT, "insufficient_seniority"),
        _decision("strong", REJECT, "location"),
        _decision("strong", ADVANCE),
    ]
    counts = rejection_reasons(decisions)
    assert list(counts) == ["insufficient_seniority", "location"]
    assert counts["insufficient_seniority"] == 2


def test_reason_rate_is_none_without_advanced_candidates():
    assert reason_rate([_decision("discard", REJECT)], "wrong_skills") is None


# --- before/after ----------------------------------------------------------


def test_period_comparison_refuses_to_split_thin_data():
    result = compare_periods([_decision() for _ in range(6)])
    assert result["available"] is False
    assert "needs" in result["reason"]


def test_period_comparison_splits_when_there_is_enough():
    decisions = [_decision("strong", REJECT, "insufficient_seniority") for _ in range(10)]
    decisions += [_decision("strong", ADVANCE) for _ in range(10)]
    result = compare_periods(decisions)
    assert result["available"] is True
    assert result["before"]["precision"] == pytest.approx(0.0)
    assert result["after"]["precision"] == pytest.approx(1.0)


# --- calibration -----------------------------------------------------------


def test_no_proposal_from_thin_evidence():
    decisions = [_decision("strong", REJECT, "insufficient_seniority")] * (
        MIN_EVIDENCE - 1
    )
    assert propose_adjustments(decisions, WEIGHTS) == []


def test_repeated_seniority_rejections_propose_lowering_experience_weight():
    decisions = [
        _decision("strong", REJECT, "insufficient_seniority") for _ in range(12)
    ]
    decisions += [_decision("strong", ADVANCE) for _ in range(8)]

    proposals = propose_adjustments(decisions, WEIGHTS)
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.category == "experience"
    assert proposal.direction == "decrease"
    assert proposal.proposed_weight < proposal.current_weight
    assert proposal.supporting_decisions == 12
    assert "insufficient" in proposal.rationale.lower() or "senior" in proposal.rationale.lower()


def test_adjustment_is_capped_however_bad_the_rate():
    decisions = [
        _decision("strong", REJECT, "insufficient_seniority") for _ in range(50)
    ]
    proposal = propose_adjustments(decisions, WEIGHTS)[0]
    # Never more than a 20% cut in one round.
    assert proposal.proposed_weight >= proposal.current_weight * 0.79


def test_reasons_that_are_not_model_errors_propose_nothing():
    """'Not interested' says nothing about whether our scoring was right."""
    decisions = [_decision("strong", REJECT, "not_interested") for _ in range(20)]
    assert propose_adjustments(decisions, WEIGHTS) == []


def test_rescued_candidates_argue_for_a_looser_discard_rule():
    decisions = [_decision("discard", REJECT, "wrong_skills") for _ in range(9)]
    decisions += [_decision("discard", ADVANCE, "actually_strong")]
    signal = underrated_signal(decisions)
    assert signal["available"] is True
    assert signal["rescued"] == 1
    assert "too aggressive" in signal["verdict"]


def test_clean_discard_pile_reports_no_concern():
    decisions = [_decision("discard", REJECT, "wrong_skills") for _ in range(10)]
    assert "no evidence" in underrated_signal(decisions)["verdict"]


def test_report_is_written_unapplied(tmp_path):
    import json

    decisions = [
        _decision("strong", REJECT, "insufficient_seniority") for _ in range(12)
    ]
    path = write_report(
        propose_adjustments(decisions, WEIGHTS),
        underrated_signal(decisions),
        tmp_path / "calibration.json",
    )
    payload = json.loads(path.read_text())
    assert payload["applied"] is False
    assert len(payload["proposals"]) == 1
