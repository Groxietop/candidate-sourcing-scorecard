"""Entry point: python -m sourcing.cli --req reqs/example-backend-engineer.yaml [...]

Loads a req, pulls candidates from every enabled source, scores each one
against the req, and writes a ranked CSV. See README.md for a full example
and SCORING.md for what the score means.
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
from .scoring import score_candidate


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

    # Corroboration: does this candidate's identity show up under more than
    # one source? (e.g. a LinkedIn row with a github_handle that also turned
    # up in the GitHub search.)
    keys_by_source: dict[str, set[str]] = {}
    for c in candidates:
        keys_by_source.setdefault(c.source, set()).add(c.identity_key())

    def is_corroborated(candidate) -> bool:
        key = candidate.identity_key()
        return any(
            key in keys for source, keys in keys_by_source.items() if source != candidate.source
        )

    results = [score_candidate(c, req, corroborated=is_corroborated(c)) for c in candidates]
    results.sort(key=lambda r: r.total, reverse=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.as_row() for r in results]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} scored candidates to {out_path}\n")

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
