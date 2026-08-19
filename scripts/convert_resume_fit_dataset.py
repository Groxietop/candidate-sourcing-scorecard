"""One-off converter: cnamuangtoun/resume-job-description-fit (Hugging Face)
-> our LinkedIn CSV schema.

See research/dataset-options.md. Unlike datasetmaster/resumes, this source
is raw resume *text* (real resumes, no structured fields at all), paired
with a job description and a human "fit" label we don't use here (see
below). No name field exists in the source at all, so there's no PII
question for this one -- candidates are Candidate-NNNN by construction.

Download first (~35MB):

    curl -L -o /tmp/resume_fit_train.csv \
        https://huggingface.co/datasets/cnamuangtoun/resume-job-description-fit/resolve/main/train.csv

Then:

    python3 scripts/convert_resume_fit_dataset.py /tmp/resume_fit_train.csv \
        data/resume_fit_candidates.csv --limit 300 --seed 42

Extraction is keyword matching against a fixed skill vocabulary (union of
every skill/alias across this repo's example reqs, plus a handful of
common adjacent technologies) -- there's no structured skills field to
read, so this is a blunter signal than the other two datasets. Years of
experience and location aren't reliably extractable from free text without
an NLP pass this script doesn't attempt, so both are left blank (neutral,
per the same "missing != penalty" design used everywhere else).

The source label column (Good Fit / Potential Fit / No Fit, against the
paired job_description_text) is NOT carried into the CSV -- our CLI scores
against one of *our* reqs, not the per-row job description in this
dataset, so the label isn't comparable to our output. It's kept in
data/resume_fit_labels.csv (row index -> label) in case a future pass
wants to validate scores against it directly.
"""

from __future__ import annotations

import argparse
import csv
import random
import re
from pathlib import Path

# Union of skills/aliases from reqs/*.yaml plus common adjacent tech, so
# extraction isn't limited to only what one specific req asks for.
_SKILL_VOCAB = [
    "python", "postgresql", "postgres", "psql", "docker", "kubernetes", "k8s",
    "aws", "amazon web services", "pandas", "scikit-learn", "sklearn", "sql",
    "mysql", "java", "javascript", "typescript", "react", "angular", "vue",
    "django", "flask", "spring", "node.js", "nodejs", "c#", "c++", "go",
    "golang", "ruby", "rails", "azure", "gcp", "google cloud", "redis",
    "mongodb", "kafka", "terraform", "linux", "git", "ci/cd", "jenkins",
    "graphql", "rest api", "microservices", "machine learning", "tensorflow",
    "pytorch", "spark", "hadoop", "tableau", "excel", "salesforce",
]

_EDU_PATTERNS = [
    (re.compile(r"\bph\.?d\b", re.I), "PhD"),
    (re.compile(r"\bmaster'?s?\b|\bm\.?s\.?\b|\bmba\b", re.I), "MS"),
    (re.compile(r"\bbachelor'?s?\b|\bb\.?s\.?\b|\bb\.?a\.?\b", re.I), "BS"),
    (re.compile(r"\bassociate'?s?\b", re.I), "Associate"),
]

_YEARS_RE = re.compile(r"(\d{1,2})\+?\s*years?\b", re.I)


def _extract_skills(text: str) -> set[str]:
    lowered = text.lower()
    return {skill for skill in _SKILL_VOCAB if skill in lowered}


def _extract_education(text: str) -> str | None:
    for pattern, label in _EDU_PATTERNS:
        if pattern.search(text):
            return label
    return None


def _extract_years(text: str) -> float | None:
    matches = [int(m.group(1)) for m in _YEARS_RE.finditer(text)]
    if not matches:
        return None
    # Free text often mentions several "N years" spans (per job, per skill);
    # take the max as a rough proxy for total experience rather than
    # summing, which double-counts overlapping roles.
    return float(max(matches))


def convert(rows: list[dict], limit: int, seed: int) -> tuple[list[dict], list[dict]]:
    random.Random(seed).shuffle(rows)

    out = []
    labels = []
    idx = 0
    for row in rows:
        text = row.get("resume_text", "") or ""
        skills = _extract_skills(text)
        if not skills:
            continue  # no signal at all -- not worth including

        idx += 1
        name = f"Candidate-{idx:04d}"
        out.append(
            {
                "name": name,
                "headline": text[:140].replace("\n", " ").strip(),
                "current_title": "",
                "current_company": "",
                "skills": ";".join(sorted(skills)),
                "location": "",
                "years_experience": _extract_years(text) or "",
                "currently_open_to_work": "",
                "github_handle": "",
                "profile_url": "",
                "certifications": "",
                "open_source_contributor": "",
                "volunteer_experience": "",
                "education_level": _extract_education(text) or "",
            }
        )
        labels.append({"name": name, "source_fit_label": row.get("label", "")})
        if len(out) >= limit:
            break

    return out, labels


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_csv", help="Path to downloaded train.csv/test.csv")
    parser.add_argument("out_csv", help="Path to write the converted candidate CSV to")
    parser.add_argument("--limit", type=int, default=300, help="Max rows to emit")
    parser.add_argument("--seed", type=int, default=42, help="Shuffle seed, for reproducibility")
    args = parser.parse_args()

    with open(args.source_csv, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    converted, labels = convert(rows, limit=args.limit, seed=args.seed)

    fieldnames = [
        "name", "headline", "current_title", "current_company", "skills",
        "location", "years_experience", "currently_open_to_work",
        "github_handle", "profile_url", "certifications",
        "open_source_contributor", "volunteer_experience", "education_level",
    ]
    out_path = Path(args.out_csv)
    _write_csv(out_path, converted, fieldnames)

    labels_path = out_path.with_name("resume_fit_labels.csv")
    _write_csv(labels_path, labels, ["name", "source_fit_label"])

    print(f"Wrote {len(converted)} candidates to {out_path} (from {len(rows)} source rows)")
    print(f"Wrote source fit labels to {labels_path} (not used by the scorer)")


if __name__ == "__main__":
    main()
