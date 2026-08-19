"""Entry point for the experimental (3-axis) scorer:

    python -m sourcing.cli_experimental --req reqs/example-backend-engineer.yaml [...]

Same sourcing (GitHub + LinkedIn CSV) as cli.py, different scoring model —
see EXPERIMENTAL_SCORING.md. Deliberately mirrors cli.py's structure and
flags so the two are easy to diff, and writes to a separate output file so
nothing overwrites the traditional pass's results. Use compare_passes.py
afterwards to see how the two rank differently.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

from .config import load_req
from .github_source import fetch_github_candidates
from .linkedin_source import load_linkedin_candidates
from .scoring_experimental import score_candidate_experimental


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--req", required=True, help="Path to a req YAML file")
    parser.add_argument(
        "--linkedin-csv", default=None, help="Path to a LinkedIn export CSV (real or synthetic)"
    )
    parser.add_argument(
        "--skip-github", action="store_true", help="Don't hit the GitHub API at all"
    )
    parser.add_argument(
        "--max-github-results",
        type=int,
        default=15,
        help="Max GitHub profiles to pull and score (keeps API usage bounded)",
    )
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token (defaults to $GITHUB_TOKEN). Optional but recommended.",
    )
    parser.add_argument("--out", required=True, help="Path to write the ranked CSV to")
    parser.add_argument(
        "--top", type=int, default=15, help="How many rows to print to the console"
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    req = load_req(args.req)
    print(f"[experimental] Sourcing for req: {req.req_id} — {req.title}\n")

    candidates = []

    if args.linkedin_csv:
        linkedin_candidates = load_linkedin_candidates(args.linkedin_csv)
        print(f"Loaded {len(linkedin_candidates)} candidates from {args.linkedin_csv}")
        candidates.extend(linkedin_candidates)

    if not args.skip_github:
        if not args.github_token:
            print(
                "  [warn] no GITHUB_TOKEN set — using a very low unauthenticated "
                "rate limit. See README.md.",
                file=sys.stderr,
            )
        github_candidates = fetch_github_candidates(
            req, token=args.github_token, max_results=args.max_github_results
        )
        print(f"Fetched {len(github_candidates)} candidates from GitHub")
        candidates.extend(github_candidates)

    if not candidates:
        print("No candidates from any source — nothing to score.", file=sys.stderr)
        return 1

    results = [score_candidate_experimental(c, req) for c in candidates]
    # Default sort: Foundation axis only (the objective-fit gate). Bonus and
    # momentum are shown but deliberately don't move anyone up or down this
    # ordering — see EXPERIMENTAL_SCORING.md on why that's a conscious choice.
    results.sort(key=lambda r: r.foundation, reverse=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.as_row() for r in results]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} scored candidates to {out_path}\n")

    qualified_count = sum(1 for r in results if r.qualified)
    print(f"{qualified_count}/{len(results)} candidates meet qualify_threshold={req.qualify_threshold} (on Foundation axis)\n")

    header = f"{'name':<28} {'source':<9} {'foundation':>10} {'bonus':>7} {'momentum':>9} {'qualified':>10}"
    print(header)
    print("-" * len(header))
    for r in results[: args.top]:
        print(
            f"{r.candidate.name:<28.28} {r.candidate.source:<9} {r.foundation:>10.1f} "
            f"{r.bonus:>7.1f} {r.momentum:>9.1f} {str(r.qualified):>10}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
