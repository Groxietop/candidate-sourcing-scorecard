"""Shared gather-and-score pipeline used by both `sourcing.cli` (one-shot,
human-run) and `sourcing.watch` (scheduled, autonomous). Pulled out of
cli.py so the two entry points can't silently drift apart on how candidates
are gathered, corroborated, or scored.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from .candidate import Candidate
from .config import Req
from .github_source import fetch_github_candidates
from .linkedin_source import load_linkedin_candidates
from .scoring import ScoreResult, score_candidate


def gather_candidates(
    req: Req,
    *,
    linkedin_csv: str | None = None,
    skip_github: bool = False,
    max_github_results: int = 15,
    github_token: str | None = None,
) -> list[Candidate]:
    candidates: list[Candidate] = []

    if linkedin_csv:
        linkedin_candidates = load_linkedin_candidates(linkedin_csv)
        print(f"Loaded {len(linkedin_candidates)} candidates from {linkedin_csv}")
        candidates.extend(linkedin_candidates)

    if not skip_github:
        if not github_token:
            print(
                "  [warn] no GITHUB_TOKEN set — using a very low unauthenticated "
                "rate limit. See README.md.",
                file=sys.stderr,
            )
        github_candidates = fetch_github_candidates(
            req, token=github_token, max_results=max_github_results
        )
        print(f"Fetched {len(github_candidates)} candidates from GitHub")
        candidates.extend(github_candidates)

    return candidates


def score_candidates(candidates: list[Candidate], req: Req) -> list[ScoreResult]:
    """Score candidates against a req, using cross-source corroboration:
    does this candidate's identity show up under more than one source?
    """
    keys_by_source: dict[str, set[str]] = {}
    for c in candidates:
        keys_by_source.setdefault(c.source, set()).add(c.identity_key())

    def is_corroborated(candidate: Candidate) -> bool:
        key = candidate.identity_key()
        return any(
            key in keys for source, keys in keys_by_source.items() if source != candidate.source
        )

    results = [score_candidate(c, req, corroborated=is_corroborated(c)) for c in candidates]
    results.sort(key=lambda r: r.total, reverse=True)
    return results


def gather_and_score(
    req: Req,
    *,
    linkedin_csv: str | None = None,
    skip_github: bool = False,
    max_github_results: int = 15,
    github_token: str | None = None,
) -> list[ScoreResult]:
    candidates = gather_candidates(
        req,
        linkedin_csv=linkedin_csv,
        skip_github=skip_github,
        max_github_results=max_github_results,
        github_token=github_token,
    )
    return score_candidates(candidates, req)


def write_csv(results: list[ScoreResult], out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.as_row() for r in results]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return out_path
