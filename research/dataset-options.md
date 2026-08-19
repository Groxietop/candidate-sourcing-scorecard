# Dataset options — replacing the hand-written LinkedIn CSV

**Update:** `datasetmaster/resumes` and `cnamuangtoun/resume-job-description-fit`
were pulled in and both scoring passes run against them — see
[`dataset-run-results.md`](dataset-run-results.md) for what happened and
the conversion scripts used. The Kaggle and OSS-developer rows in the
table below were **not** pulled in (Kaggle needs an API token this
environment doesn't have; the OSS-developer set maps to the GitHub side,
not the LinkedIn CSV, which is a different piece of work).

`data/fake_linkedin_candidates.csv` is 20 rows invented by hand for this
proof of concept (see `README.md`). That's fine for exercising the code
path, but it's thin and it's not blind — whoever wrote it knows the
"right" ranking in advance, which makes it a weak test of whether the
scoring logic actually works. This doc looks at whether a public dataset
could stand in for it instead. Research done 2026-08-19.

## Constraint that rules out the obvious answer

The obvious source — a real LinkedIn Recruiter/Sales Navigator export —
requires a licensed seat this project doesn't have, and this repo's
explicit policy (see `README.md`, `linkedin_source.py` docstring) is to
**never scrape LinkedIn**, full stop. So "find a scraped LinkedIn dataset
on Kaggle" is off the table on principle, not just practicality — several
exist, but using one would contradict the exact thing this project is
built to avoid (see `README.md`'s citation of *hiQ Labs v. LinkedIn*).

The real question is narrower: is there a **non-LinkedIn** dataset of
real (or realistic) candidate profiles — skills, experience, education —
that can be mapped onto the existing `Candidate` schema and
`linkedin_source.py` CSV columns?

## Options found

| Dataset | Source | Real or synthetic | License | Size | Fit |
|---|---|---|---|---|---|
| **`datasetmaster/resumes`** | Hugging Face | Mixed — real resumes anonymized from CV submissions + synthetic profiles generated with Faker for roles the real set didn't cover | MIT | 4,817 rows, structured JSON | **Best fit.** Already has personal info, work experience (company/title/dates), education (degree/institution), skills categorized by type, and projects — close to a 1:1 mapping onto our CSV columns (see below). |
| **Kaggle "Resume Dataset"** (`snehaanbhawal/resume-dataset`, similar ones exist under other Kaggle accounts) | Kaggle | Real — sourced from livecareer.com resume postings | CC0 (public domain) | ~2,400 resumes, string + PDF | Real people's actual resumes, not LinkedIn-derived, so no ToS conflict. But it's raw resume text/PDF, categorized by job title only — would need an extraction step (regex or an LLM pass) to pull out skills/years/education into columns before it's usable. |
| **`cnamuangtoun/resume-job-description-fit`** | Hugging Face | Real resumes paired with job descriptions and a human-labeled fit category | Not confirmed at fetch time — check before use | ~1K–10K rows | Not a candidate-list replacement, but useful as a **held-out validation set**: run our scorer against these resume/JD pairs and check whether high-scoring candidates correlate with the dataset's own "good fit" label. This is exactly the "test against 10-20 historic profiles" step both `SCORING.md` and `EXPERIMENTAL_SCORING.md` flag as not yet done (see [`market-practice-comparison.md`](market-practice-comparison.md)). |
| **Open-source-developer research dataset** (ScienceDirect / PMC, ~700 developers across 17 GitHub projects, labeled by experience level with 24 software metrics) | Academic research release | Real | Research/academic use | ~700 developers | Not a LinkedIn substitute, but a candidate for a **deterministic GitHub fixture**: `github_source.py` currently hits the live API with no test mocking, so CI runs are subject to GitHub rate limits and network flakiness. This dataset (or a small hand-picked snapshot of real GitHub API responses) could back an offline fixture for `tests/`. Separate from this doc's main question but worth flagging since it showed up in the same research pass. |

## Recommendation

Use **`datasetmaster/resumes`** (Hugging Face, MIT) as the primary
replacement/supplement for `data/fake_linkedin_candidates.csv`. It's the
only option that's both realistic (partially real, ToS-clean) and
already structured enough to map without an extraction step:

| Our CSV column | `datasetmaster/resumes` field |
|---|---|
| `name` | Personal Information → name |
| `current_title` / `headline` | Experience[0] → job title |
| `current_company` | Experience[0] → company |
| `skills` | Skills → flatten categorized lists into one `;`-separated string |
| `location` | Personal Information → location |
| `years_experience` | Derive from Experience[] employment dates |
| `education_level` | Education[] → degree |
| `certifications` | Not present — leave blank (neutral, per existing "missing = no penalty" design) |
| `open_source_contributor`, `volunteer_experience` | Not present — leave blank |
| `github_handle`, `profile_url` | Personal Information → social profiles, if present, else blank |

A small conversion script (`datasetmaster/resumes` JSON → our CSV schema)
would be a reasonable follow-up if this is worth doing — it's a mapping
job, not new scoring logic, so it wouldn't touch `scoring.py` or
`scoring_experimental.py` at all. Blank `certifications` /
`open_source_contributor` / `volunteer_experience` for every row is a
real limitation (the Bonus axis would get no signal from LinkedIn-side
fields for this dataset), but that's an honest gap to document rather
than a reason to keep hand-writing candidates.

Secondary recommendation: once there's a converted candidate set, also
pull a sample from `cnamuangtoun/resume-job-description-fit` and run it
through `compare_passes.py`-style analysis against its own fit labels —
that's the cheapest available step toward the "validate against real
outcomes" gap called out in `market-practice-comparison.md`.

## Sources

- [`datasetmaster/resumes` · Hugging Face](https://huggingface.co/datasets/datasetmaster/resumes)
- [Kaggle — Resume Dataset (`snehaanbhawal/resume-dataset`)](https://www.kaggle.com/datasets/snehaanbhawal/resume-dataset)
- [`cnamuangtoun/resume-job-description-fit` · Hugging Face](https://huggingface.co/datasets/cnamuangtoun/resume-job-description-fit)
- [ScienceDirect — Dataset of open-source software developers labeled by experience level](https://www.sciencedirect.com/science/article/pii/S2352340922010459)
- [PMC — same dataset, open-access mirror](https://pmc.ncbi.nlm.nih.gov/articles/PMC9813504/)
