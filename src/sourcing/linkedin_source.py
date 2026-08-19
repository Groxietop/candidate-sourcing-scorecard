"""Ingests LinkedIn candidate data from a CSV — never from scraping.

In real use, this CSV is a manual export from a LinkedIn Recruiter or Sales
Navigator seat the requester is already licensed to use. LinkedIn does not
offer a public search API for this kind of query, and scraping linkedin.com
violates its Terms of Service, so this project does not do that.

Expected columns (see data/fake_linkedin_candidates.csv for a synthetic
example, since this proof of concept was built without a real Recruiter
seat):

    name, headline, current_title, current_company, skills, location,
    years_experience, currently_open_to_work, github_handle, profile_url

`skills` is a ";"-separated list. `currently_open_to_work` and
`github_handle` may be blank. Extra columns are ignored; missing optional
columns default to None/blank.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .candidate import Candidate


def _parse_bool(value: str) -> bool | None:
    if value is None or value.strip() == "":
        return None
    return value.strip().lower() in ("true", "1", "yes", "y")


def load_linkedin_candidates(csv_path: str | Path) -> list[Candidate]:
    path = Path(csv_path)
    candidates: list[Candidate] = []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            skills = {
                s.strip().lower() for s in (row.get("skills") or "").split(";") if s.strip()
            }
            years_raw = (row.get("years_experience") or "").strip()
            candidates.append(
                Candidate(
                    name=row["name"].strip(),
                    source="linkedin",
                    profile_url=row.get("profile_url", "").strip(),
                    skills=skills,
                    location=(row.get("location") or "").strip() or None,
                    years_experience=float(years_raw) if years_raw else None,
                    currently_open_to_work=_parse_bool(row.get("currently_open_to_work", "")),
                    github_handle=(row.get("github_handle") or "").strip() or None,
                )
            )

    return candidates
