"""The LinkedIn Recruiter seat, as a first-class connector.

This is the same CSV import the repo has always had, promoted from "a demo
file path" to a documented integration boundary — because in a real
deployment that boundary is the whole story, and it is a legal boundary as
much as a technical one.

Why there is no API client here
-------------------------------
LinkedIn does not offer a public search or profile API, and scraping it
violates their Terms of Service with real legal exposure (see *hiQ Labs v.
LinkedIn* for how contested this remains even for data anyone can see).
There is a partner Talent Solutions API, but access is granted per-company
under contract, not obtainable by a project like this.

So the supported path is the one a licensed seat already gives you: an
export the requesting company is entitled to, dropped into this connector.
That is not a workaround — for most companies it is the only lawful route,
and building the tool around it is the honest design rather than a
limitation to apologise for.

What this module adds over the raw CSV loader
---------------------------------------------
Provenance. A pool assembled from an export needs to record which seat it
came from and when, because an export is a snapshot: a candidate marked
"open to work" in March is not evidence about them in September. The
scorer's recency logic already knows how to distrust stale signals — it
just needs to be told the age.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..linkedin_source import load_linkedin_candidates

# Past this age, an export's "open to work" and title fields describe a
# person who may have moved on. Not a hard cutoff -- consistent with the
# rest of the tool, staleness annotates rather than removes.
STALE_AFTER_DAYS = 90

REQUIRED_COLUMNS = {"name", "skills", "profile_url"}


@dataclass
class SeatExport:
    """One export from one licensed LinkedIn Recruiter seat."""

    path: Path
    seat_owner: str
    exported_at: datetime
    project: str = ""

    @property
    def age_days(self) -> int:
        return (datetime.now(timezone.utc) - self.exported_at).days

    @property
    def is_stale(self) -> bool:
        return self.age_days > STALE_AFTER_DAYS

    def provenance(self) -> str:
        note = (
            f"LinkedIn Recruiter export by {self.seat_owner}, "
            f"{self.exported_at:%Y-%m-%d} ({self.age_days}d old)"
        )
        if self.project:
            note += f", project '{self.project}'"
        if self.is_stale:
            note += (
                " — older than "
                f"{STALE_AFTER_DAYS} days; titles and open-to-work flags in it "
                "may no longer hold"
            )
        return note


def validate_export(path: Path | str) -> list[str]:
    """Problems that would make an export unusable, as readable strings.

    Returns an empty list for a good file. Checking up front beats
    discovering a missing column halfway through a scored run.
    """
    path = Path(path)
    if not path.exists():
        return [f"{path} does not exist"]

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        rows = sum(1 for _ in reader)

    problems = []
    missing = REQUIRED_COLUMNS - columns
    if missing:
        problems.append(f"missing required columns: {', '.join(sorted(missing))}")
    if rows == 0:
        problems.append("export contains no candidate rows")
    return problems


def load(export: SeatExport):
    """Candidates from a seat export, with provenance attached.

    Raises rather than silently returning a short list -- a truncated pool
    is indistinguishable from a genuinely small one, and quietly losing
    candidates is precisely what this tool is built to avoid.
    """
    problems = validate_export(export.path)
    if problems:
        raise ValueError(
            f"cannot load {export.path}: " + "; ".join(problems)
        )

    candidates = load_linkedin_candidates(export.path)

    if export.is_stale:
        # Don't silently trust a stale open-to-work flag. Clearing it moves
        # the signal from "measured" to "unobserved", which is exactly the
        # treatment an unknowable fact should get.
        for candidate in candidates:
            candidate.currently_open_to_work = None

    return candidates


def from_directory(
    directory: Path | str, seat_owner: str, project: str = ""
) -> list[SeatExport]:
    """Every CSV in a drop directory, dated by file mtime.

    Matches how these actually arrive: a recruiter exports from their seat
    and drops the file somewhere shared, with no metadata beyond the
    filesystem's.
    """
    directory = Path(directory)
    exports = []
    for path in sorted(directory.glob("*.csv")):
        stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        exports.append(
            SeatExport(
                path=path, seat_owner=seat_owner, exported_at=stamp, project=project
            )
        )
    return exports


def describe_freshness(exports) -> dict:
    """Summary of how much of a pool rests on stale exports."""
    exports = list(exports)
    if not exports:
        return {"exports": 0, "stale": 0, "oldest_days": None}
    return {
        "exports": len(exports),
        "stale": sum(1 for e in exports if e.is_stale),
        "oldest_days": max(e.age_days for e in exports),
        "notes": [e.provenance() for e in exports],
    }


def recent(days: int = STALE_AFTER_DAYS) -> datetime:
    """Convenience for constructing a fresh export timestamp in tests/CLI."""
    return datetime.now(timezone.utc) - timedelta(days=days // 2)
