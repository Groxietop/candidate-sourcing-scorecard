"""Entry point: python -m sourcing.watch --req reqs/example-backend-engineer.yaml [...]

The scheduled counterpart to `sourcing.cli`. Runs the same gather-and-score
pipeline, but instead of just printing a table it:

  1. Loads the previous snapshot for this req from data/snapshots/<req_id>/latest.json
  2. Diffs it against the fresh run (new candidates, qualified flips, big
     score movers, dropped candidates)
  3. Writes the new snapshot back, and a human-readable diff report
  4. Signals whether anything changed, so a CI workflow can decide whether
     to open/update a GitHub Issue — this is the part that makes the repo a
     live pipeline instead of a script someone has to remember to run.

See .github/workflows/watch.yml for how this gets scheduled and wired to
GITHUB_OUTPUT.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import load_req
from .pipeline import gather_and_score, write_csv
from .store import (
    DEFAULT_SCORE_DELTA_THRESHOLD,
    build_snapshot,
    diff_snapshots,
    load_snapshot,
    save_snapshot,
    snapshot_path,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--req", required=True, help="Path to a req YAML file")
    parser.add_argument(
        "--linkedin-csv", default=None, help="Path to a LinkedIn export CSV (real or synthetic)"
    )
    parser.add_argument(
        "--skip-github", action="store_true", help="Don't hit the GitHub API at all"
    )
    parser.add_argument("--max-github-results", type=int, default=15)
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument(
        "--snapshot-dir",
        default="data/snapshots",
        help="Where per-req snapshots live (default: data/snapshots)",
    )
    parser.add_argument(
        "--out-csv", default=None, help="Optional: also write the full ranked CSV here"
    )
    parser.add_argument(
        "--report-out",
        default=None,
        help="Optional: write the markdown diff report to this path",
    )
    parser.add_argument(
        "--score-delta-threshold",
        type=float,
        default=DEFAULT_SCORE_DELTA_THRESHOLD,
        help="Minimum |score change| to flag a candidate as a mover",
    )
    return parser.parse_args(argv)


def _write_github_output(changed: bool, req_id: str, report_path: str | None) -> None:
    """If running inside a GitHub Actions job, expose the result as step
    outputs so the workflow can conditionally open/update an Issue.
    """
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if not gh_output:
        return
    with open(gh_output, "a") as f:
        f.write(f"changed={'true' if changed else 'false'}\n")
        f.write(f"req_id={req_id}\n")
        if report_path:
            f.write(f"report_path={report_path}\n")


def main(argv=None) -> int:
    args = parse_args(argv)
    req = load_req(args.req)
    print(f"Watching req: {req.req_id} — {req.title}\n")

    results = gather_and_score(
        req,
        linkedin_csv=args.linkedin_csv,
        skip_github=args.skip_github,
        max_github_results=args.max_github_results,
        github_token=args.github_token,
    )

    if not results:
        print("No candidates from any source — nothing to score.", file=sys.stderr)
        return 1

    if args.out_csv:
        write_csv(results, args.out_csv)

    snap_path = snapshot_path(req.req_id, args.snapshot_dir)
    previous = load_snapshot(snap_path)
    current = build_snapshot(req.req_id, results)
    diff = diff_snapshots(previous, current, score_delta_threshold=args.score_delta_threshold)

    save_snapshot(snap_path, current)
    print(f"Snapshot written to {snap_path}")

    was_first_run = previous is None
    if was_first_run:
        status = "first_run"
    elif diff.is_empty:
        status = "unchanged"
    else:
        status = "changed"

    report = diff.summary_markdown()
    if was_first_run:
        report = (
            f"Baseline snapshot for `{req.req_id}` — nothing to compare against yet. "
            "Future watch runs will diff against this.\n"
        )
    # Machine-readable marker consumed by watch.yml's shell loop (grep for
    # it) so a workflow driving multiple reqs in one step can tell first
    # runs, no-ops, and real changes apart without relying on step outputs.
    report = f"<!-- watch-status: {status} -->\n" + report
    print("\n" + report)

    report_path = None
    if args.report_out:
        report_path = Path(args.report_out)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report)

    _write_github_output(status == "changed", req.req_id, str(report_path) if report_path else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
