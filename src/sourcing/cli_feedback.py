"""Record recruiter verdicts and read the model's performance.

    python -m sourcing.cli_feedback record --candidate "Nadia Osei" \
        --req eng-backend-001 --tier caveated --verdict advance \
        --reason actually_strong

    python -m sourcing.cli_feedback report
    python -m sourcing.cli_feedback calibrate

`report` computes everything from the decision log and nothing else. With an
empty log it says so rather than printing a number, because a screening tool
that displays invented accuracy is worse than one that displays none.

The web UI records verdicts in its own page state; this log is the durable
one. `import-verdicts` bridges them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .feedback import (
    ADVANCE,
    DEFAULT_LOG,
    REASON_CODES,
    REJECT,
    Decision,
    FeedbackLog,
    compare_periods,
    evaluate,
    rejection_reasons,
)
from .calibration import propose_adjustments, underrated_signal, write_report
from .scoring import WEIGHTS


def _pct(value):
    """Render a rate, or say we don't have one. Never render None as 0%."""
    return "no data yet" if value is None else f"{value:.0%}"


def cmd_record(args) -> int:
    log = FeedbackLog(args.log)
    decision = Decision(
        candidate_key=args.key or f"name:{args.candidate.lower()}",
        candidate_name=args.candidate,
        req_id=args.req,
        predicted_tier=args.tier,
        verdict=args.verdict,
        reason_code=args.reason,
        note=args.note,
    )
    log.record(decision)
    print(f"Recorded: {decision.candidate_name} — {decision.verdict} ({decision.reason_code})")
    print(f"  log now holds {len(log.all())} decisions ({log.path})")
    return 0


def cmd_report(args) -> int:
    log = FeedbackLog(args.log)
    decisions = log.all()
    metrics = evaluate(decisions)

    print(f"Decisions recorded: {metrics['decisions']}")
    if not decisions:
        print("\nNothing to report yet. Record some verdicts first.")
        return 0

    print(f"  advanced by the tool: {metrics['advanced']}")
    print(f"  set aside by the tool: {metrics['set_aside']}\n")

    print("Performance (from recorded decisions only)")
    print("-" * 52)
    print(f"  missed rate      {_pct(metrics['missed_rate']):>12}   "
          "set-aside candidates a recruiter wanted")
    print(f"  precision        {_pct(metrics['precision']):>12}   of those we advanced")
    print(f"  recall           {_pct(metrics['recall']):>12}   of the good ones, how many surfaced")

    if metrics["missed_candidates"]:
        print("\n  Candidates we set aside and should not have:")
        for entry in metrics["missed_candidates"]:
            print(f"    - {entry['name']} (we said: {entry['tier']})")

    reasons = rejection_reasons(decisions)
    if reasons:
        print("\n  Rejection reasons:")
        for code, count in reasons.items():
            print(f"    {count:>4}  {REASON_CODES[code]}")

    periods = compare_periods(decisions)
    print("\nBefore / after")
    print("-" * 52)
    if not periods["available"]:
        print(f"  {periods['reason']}")
    else:
        before, after = periods["before"], periods["after"]
        print(f"  {'':<16}{'first half':>14}{'second half':>14}")
        for label, key in (("missed rate", "missed_rate"), ("precision", "precision")):
            print(f"  {label:<16}{_pct(before[key]):>14}{_pct(after[key]):>14}")

    return 0


def cmd_calibrate(args) -> int:
    log = FeedbackLog(args.log)
    decisions = log.all()
    proposals = propose_adjustments(decisions, WEIGHTS)
    underrated = underrated_signal(decisions)

    print(f"Calibration from {len(decisions)} decisions\n")
    if not proposals:
        print("  No weight changes proposed — not enough evidence implicating")
        print("  any single scoring category yet.")
    else:
        for proposal in proposals:
            print(f"  {proposal.category}: {proposal.current_weight:g} → "
                  f"{proposal.proposed_weight:g}  ({proposal.direction})")
            print(f"    {proposal.rationale}\n")

    print("Discard rule")
    print("-" * 52)
    if underrated.get("available"):
        print(f"  {underrated['rescued']}/{underrated['set_aside_reviewed']} "
              f"set-aside candidates were actually wanted")
        print(f"  {underrated['verdict']}")
    else:
        print(f"  {underrated.get('reason')}")

    path = write_report(proposals, underrated, args.out)
    print(f"\nWritten to {path} — nothing applied. Edit WEIGHTS deliberately.")
    return 0


def cmd_import(args) -> int:
    """Ingest verdicts exported from the web UI.

    The UI keeps verdicts as `data-verdict` / `data-reason` attributes on its
    candidate cards. Paste that out as JSON and this folds it into the
    durable log so `report` and `calibrate` can see it.
    """
    payload = json.loads(Path(args.file).read_text())
    log = FeedbackLog(args.log)
    added = 0
    for row in payload:
        if not row.get("verdict"):
            continue
        log.record(
            Decision(
                candidate_key=row.get("key") or f"name:{row['name'].lower()}",
                candidate_name=row["name"],
                req_id=row.get("req_id", args.req or "unknown"),
                predicted_tier=row["tier"],
                verdict=row["verdict"],
                reason_code=row.get("reason") or "other",
            )
        )
        added += 1
    print(f"Imported {added} verdicts into {log.path}")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", default=DEFAULT_LOG, help="Path to the decision log")
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="Record one recruiter verdict")
    record.add_argument("--candidate", required=True)
    record.add_argument("--req", required=True)
    record.add_argument(
        "--tier", required=True,
        choices=["strong", "review", "caveated", "discard"],
        help="What the tool predicted",
    )
    record.add_argument("--verdict", required=True, choices=[ADVANCE, REJECT])
    record.add_argument("--reason", default="other", choices=sorted(REASON_CODES))
    record.add_argument("--key", default=None)
    record.add_argument("--note", default="")
    record.set_defaults(func=cmd_record)

    report = sub.add_parser("report", help="Model performance from recorded decisions")
    report.set_defaults(func=cmd_report)

    calibrate = sub.add_parser("calibrate", help="Propose weight changes from feedback")
    calibrate.add_argument("--out", default="data/feedback/calibration.json")
    calibrate.set_defaults(func=cmd_calibrate)

    imp = sub.add_parser("import-verdicts", help="Ingest verdicts exported from the UI")
    imp.add_argument("--file", required=True)
    imp.add_argument("--req", default=None)
    imp.set_defaults(func=cmd_import)

    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
