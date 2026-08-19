"""One-off converter: datasetmaster/resumes (Hugging Face) -> our LinkedIn CSV schema.

See research/dataset-options.md for why this dataset and why this mapping.

Source: https://huggingface.co/datasets/datasetmaster/resumes (MIT license)
Download the source file first (not committed to this repo — it's ~16MB):

    curl -L -o /tmp/master_resumes.jsonl \
        https://huggingface.co/datasets/datasetmaster/resumes/resolve/main/master_resumes.jsonl

Then run:

    python3 scripts/convert_hf_resumes.py /tmp/master_resumes.jsonl \
        data/hf_resume_candidates.csv --limit 300 --seed 42

Deliberately does NOT carry over the source `personal_info.name` field.
The source dataset's own card claims resumes are "anonymized from CV
submissions", but in practice most rows still have a real-looking full
name attached to specific employers/titles/projects — that's not
meaningfully anonymized, and republishing it here would be exactly the
kind of privacy risk this project's README already refuses to take on
for LinkedIn data (see the hiQ Labs v. LinkedIn discussion there). Every
row gets a synthetic `Candidate-NNNN` name instead. No dependency on a
name-generation library on purpose, to avoid new runtime deps for what's
a one-off data-prep script.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from pathlib import Path

_PLACEHOLDER_VALUES = {"", "unknown", "not provided", "none", "n/a", "na"}


def _clean(value: object) -> str | None:
    """Normalize a source field: strip, drop placeholder sentinels."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() not in _PLACEHOLDER_VALUES else None


def _flatten_skills(skills_block: dict) -> set[str]:
    technical = (skills_block or {}).get("technical", {}) or {}
    names: set[str] = set()
    for category in technical.values():
        if not isinstance(category, list):
            continue
        for entry in category:
            name = _clean(entry.get("name")) if isinstance(entry, dict) else _clean(entry)
            if name:
                names.add(name.lower())
    return names


def _location(personal_info: dict) -> str | None:
    loc = (personal_info or {}).get("location", {}) or {}
    city = _clean(loc.get("city"))
    country = _clean(loc.get("country"))
    parts = [p for p in (city, country) if p]
    return ", ".join(parts) if parts else None


_YEAR_RE = re.compile(r"(19|20)\d{2}")


def _years_experience(experience: list) -> float | None:
    """Best-effort: earliest start year to latest end year (or 2026 for
    "Present"/"Current") across all listed jobs. Source dates are messy
    free text ("Not Provided", "May 2016", "2016-01", "Present", ...), so
    this is a rough proxy, not a precise calculation. Returns None (blank
    in the CSV -> scored neutral, never penalized) when nothing parseable
    is found, rather than inventing a number.
    """
    years: list[int] = []
    for job in experience or []:
        dates = (job or {}).get("dates", {}) or {}
        start = _clean(dates.get("start"))
        end = _clean(dates.get("end"))
        if start:
            m = _YEAR_RE.search(start)
            if m:
                years.append(int(m.group()))
        if end:
            if end.lower() in ("present", "current"):
                years.append(2026)
            else:
                m = _YEAR_RE.search(end)
                if m:
                    years.append(int(m.group()))
    if len(years) < 2:
        return None
    span = max(years) - min(years)
    return float(span) if span > 0 else None


def _most_recent_job(experience: list) -> dict:
    return experience[0] if experience else {}


def convert(rows: list[dict], limit: int, seed: int) -> list[dict]:
    random.Random(seed).shuffle(rows)

    out = []
    idx = 0
    for row in rows:
        personal = row.get("personal_info", {}) or {}
        skills = _flatten_skills(row.get("skills", {}) or {})
        location = _location(personal)
        # Require at least skills or location to have something worth scoring;
        # skip rows that are almost entirely placeholder sentinels.
        if not skills and not location:
            continue

        job = _most_recent_job(row.get("experience", []))
        education = (row.get("education") or [{}])[0] or {}

        idx += 1
        out.append(
            {
                "name": f"Candidate-{idx:04d}",
                "headline": _clean(personal.get("summary")) or "",
                "current_title": _clean(job.get("title")) or "",
                "current_company": _clean(job.get("company")) or "",
                "skills": ";".join(sorted(skills)),
                "location": location or "",
                "years_experience": _years_experience(row.get("experience", [])) or "",
                "currently_open_to_work": "",  # not present in source; blank = neutral
                "github_handle": _clean(personal.get("github")) or "",
                "profile_url": _clean(personal.get("linkedin")) or "",
                "certifications": "",  # not present in source; blank = no bonus, no penalty
                "open_source_contributor": "",
                "volunteer_experience": "",
                "education_level": _clean((education.get("degree") or {}).get("level")) or "",
            }
        )
        if len(out) >= limit:
            break

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_jsonl", help="Path to downloaded master_resumes.jsonl")
    parser.add_argument("out_csv", help="Path to write the converted CSV to")
    parser.add_argument("--limit", type=int, default=300, help="Max rows to emit")
    parser.add_argument("--seed", type=int, default=42, help="Shuffle seed, for reproducibility")
    args = parser.parse_args()

    rows = []
    with open(args.source_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    converted = convert(rows, limit=args.limit, seed=args.seed)

    fieldnames = [
        "name",
        "headline",
        "current_title",
        "current_company",
        "skills",
        "location",
        "years_experience",
        "currently_open_to_work",
        "github_handle",
        "profile_url",
        "certifications",
        "open_source_contributor",
        "volunteer_experience",
        "education_level",
    ]
    out_path = Path(args.out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(converted)

    print(f"Wrote {len(converted)} candidates to {out_path} (from {len(rows)} source rows)")


if __name__ == "__main__":
    main()
