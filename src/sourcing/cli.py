"""Entry point: python -m sourcing.cli --req reqs/example-backend-engineer.yaml [...]

Loads a req, pulls candidates from every enabled source, scores each one
against the req, and writes a ranked CSV. See README.md for a full example
and SCORING.md for what the score means.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import load_req
from .pipeline import gather_and_score, write_csv
from .review_queue import render_console, render_markdown
from .triage import summarise


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
        "--review-out",
        default=None,
        help="Optional path for the tiered review queue (markdown).",
    )
    parser.add_argument(
        "--top", type=int, default=8, help="How many rows to print per tier"
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    req = load_req(args.req)
    print(f"Sourcing for req: {req.req_id} — {req.title}\n")

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

    out_path = write_csv(results, args.out)
    print(f"\nWrote {len(results)} scored candidates to {out_path}\n")

    counts = summarise([r.triage for r in results if r.triage])
    print(
        "  tiers: "
        + " · ".join(f"{name} {count}" for name, count in counts.items())
    )

    print(render_console(results, req, top=args.top))

    if args.review_out:
        review_path = Path(args.review_out)
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(render_markdown(results, req))
        print(f"Review queue written to {review_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
