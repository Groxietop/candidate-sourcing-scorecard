"""Entry point: python -m sourcing.cli --req reqs/example-backend-engineer.yaml [...]

Loads a req, pulls candidates from every enabled source, scores each one
against the req, and writes a ranked CSV. See README.md for a full example
and SCORING.md for what the score means.
"""

from __future__ import annotations

import argparse
import os
import sys

from .config import load_req
from .pipeline import gather_and_score, write_csv


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

    qualified_count = sum(1 for r in results if r.qualified)
    print(f"{qualified_count}/{len(results)} candidates meet qualify_threshold={req.qualify_threshold}\n")

    header = f"{'name':<28} {'source':<9} {'score':>6} {'qualified':>10}  matched_skills"
    print(header)
    print("-" * len(header))
    for r in results[: args.top]:
        print(
            f"{r.candidate.name:<28.28} {r.candidate.source:<9} {r.total:>6.1f} "
            f"{str(r.qualified):>10}  {','.join(r.matched_skills)}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
