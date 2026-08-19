"""Persistence for watch mode: snapshot a scored run to JSON, and diff two
snapshots to find what changed.

This is deliberately plain JSON on disk (committed to the repo by the watch
workflow), not a database — the whole point is that anyone can `git log
data/snapshots/` and read the history by eye, same philosophy as SCORING.md
being a plain-language rubric instead of buried code.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path

from .scoring import ScoreResult

# A candidate's score has to move by at least this many points for watch
# mode to call it out as a "mover" rather than noise (GitHub signals like
# star counts and recency drift a little between runs even when nothing
# meaningful changed).
DEFAULT_SCORE_DELTA_THRESHOLD = 5.0


def snapshot_path(req_id: str, snapshot_dir: str | Path = "data/snapshots") -> Path:
    return Path(snapshot_dir) / req_id / "latest.json"


def _row_from_result(r: ScoreResult) -> dict:
    return {
        "name": r.candidate.name,
        "source": r.candidate.source,
        "profile_url": r.candidate.profile_url,
        "score": round(r.total, 1),
        "qualified": r.qualified,
        "matched_skills": list(r.matched_skills),
    }


def build_snapshot(req_id: str, results: list[ScoreResult]) -> dict:
    """Turn a scored run into the JSON-serializable snapshot shape, keyed
    by each candidate's identity_key() so runs can be compared even when
    ranking order shifts.
    """
    return {
        "req_id": req_id,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "candidates": {r.candidate.identity_key(): _row_from_result(r) for r in results},
    }


def load_snapshot(path: str | Path) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    with path.open() as f:
        return json.load(f)


def save_snapshot(path: str | Path, snapshot: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(snapshot, f, indent=2, sort_keys=True)
        f.write("\n")
    return path


@dataclass
class Diff:
    req_id: str
    new_candidates: list[dict] = field(default_factory=list)
    dropped_candidates: list[dict] = field(default_factory=list)
    newly_qualified: list[dict] = field(default_factory=list)
    no_longer_qualified: list[dict] = field(default_factory=list)
    movers: list[dict] = field(default_factory=list)  # {name, old_score, new_score, delta}

    @property
    def is_empty(self) -> bool:
        return not (
            self.new_candidates
            or self.dropped_candidates
            or self.newly_qualified
            or self.no_longer_qualified
            or self.movers
        )

    def summary_markdown(self) -> str:
        if self.is_empty:
            return f"No changes for `{self.req_id}` since the last watch run."

        lines = [f"## Candidate pool changes — `{self.req_id}`", ""]

        def _list(title: str, rows: list[dict], line_fn) -> None:
            if not rows:
                return
            lines.append(f"### {title}")
            for row in rows:
                lines.append(f"- {line_fn(row)}")
            lines.append("")

        _list(
            f"🆕 New candidates ({len(self.new_candidates)})",
            self.new_candidates,
            lambda c: f"[{c['name']}]({c['profile_url']}) — {c['score']} pts, "
            f"{'qualified' if c['qualified'] else 'not qualified'}",
        )
        _list(
            f"✅ Newly qualified ({len(self.newly_qualified)})",
            self.newly_qualified,
            lambda c: f"[{c['name']}]({c['profile_url']}) — {c['score']} pts",
        )
        _list(
            f"⚠️ No longer qualified ({len(self.no_longer_qualified)})",
            self.no_longer_qualified,
            lambda c: f"[{c['name']}]({c['profile_url']}) — {c['score']} pts",
        )
        _list(
            f"📈 Score moved ≥ threshold ({len(self.movers)})",
            self.movers,
            lambda c: f"[{c['name']}]({c['profile_url']}) — "
            f"{c['old_score']} → {c['new_score']} ({c['delta']:+.1f})",
        )
        _list(
            f"👋 Dropped from results ({len(self.dropped_candidates)})",
            self.dropped_candidates,
            lambda c: f"{c['name']} — last seen at {c['score']} pts",
        )

        return "\n".join(lines).rstrip() + "\n"


def diff_snapshots(
    previous: dict | None,
    current: dict,
    score_delta_threshold: float = DEFAULT_SCORE_DELTA_THRESHOLD,
) -> Diff:
    req_id = current["req_id"]
    prev_candidates: dict = (previous or {}).get("candidates", {})
    curr_candidates: dict = current.get("candidates", {})

    diff = Diff(req_id=req_id)

    for key, curr in curr_candidates.items():
        prev = prev_candidates.get(key)
        if prev is None:
            diff.new_candidates.append(curr)
            if curr["qualified"]:
                diff.newly_qualified.append(curr)
            continue

        if curr["qualified"] and not prev["qualified"]:
            diff.newly_qualified.append(curr)
        elif prev["qualified"] and not curr["qualified"]:
            diff.no_longer_qualified.append(curr)

        delta = curr["score"] - prev["score"]
        if abs(delta) >= score_delta_threshold:
            diff.movers.append(
                {
                    "name": curr["name"],
                    "profile_url": curr["profile_url"],
                    "old_score": prev["score"],
                    "new_score": curr["score"],
                    "delta": delta,
                }
            )

    for key, prev in prev_candidates.items():
        if key not in curr_candidates:
            diff.dropped_candidates.append(prev)

    return diff
