"""Ingests LinkedIn candidate data from a CSV — never from scraping.

In real use, this CSV is a manual export from a LinkedIn Recruiter or Sales
Navigator seat the requester is already licensed to use. LinkedIn does not
offer a public search API for this kind of query, and scraping linkedin.com
violates its Terms of Service, so this project does not do that.

Expected columns (see data/fake_linkedin_candidates.csv for a synthetic
example, since this proof of concept was built without a real Recruiter
seat):

    name, headline, current_title, current_company, skills, location,
    years_experience, currently_open_to_work, github_handle, profile_url,
    certifications, open_source_contributor, volunteer_experience,
    education_level

`skills` is a ";"-separated list. `certifications` is a ";"-separated list
or free text. Everything after `profile_url` is optional and used only by
the experimental scorer's bonus axis (see EXPERIMENTAL_SCORING.md) — a real
Recruiter export won't have these columns, and that's fine: missing/blank
means "no data", which the experimental scorer treats as 0 contribution,
never a penalty. Extra columns beyond what's listed here are ignored.
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
                    current_title=(row.get("current_title") or "").strip() or None,
                    certifications=(row.get("certifications") or "").strip() or None,
                    open_source_contributor=_parse_bool(row.get("open_source_contributor", "")),
                    volunteer_experience=_parse_bool(row.get("volunteer_experience", "")),
                    education_level=(row.get("education_level") or "").strip() or None,
                )
            )

    return candidates
