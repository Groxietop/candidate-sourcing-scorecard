# Running both passes against real datasets: results

Follow-up to [`dataset-options.md`](dataset-options.md): pulled in the
datasets that were actually reachable, converted them to the LinkedIn CSV
schema, and ran both scoring passes (`sourcing.cli` / `sourcing.cli_experimental`,
`--skip-github`, since no `GITHUB_TOKEN` was available in this environment)
against each — plus the original hand-written demo data as a baseline.
Run 2026-08-19, against `reqs/example-backend-engineer.yaml` (remote_ok,
so location contributes its max score for every candidate in every pass —
this run isolates weighting/data-shape effects from the location-bias fix
already demonstrated in the main `README.md` walkthrough).

## What got pulled in, and what didn't

| Dataset | Pulled in? | Why / why not |
|---|---|---|
| `datasetmaster/resumes` (Hugging Face) | Yes — `data/hf_resume_candidates.csv` (300 rows, seeded sample) | Directly downloadable, no auth. Names replaced with `Candidate-NNNN` (see `scripts/convert_hf_resumes.py` docstring for why — the source's "anonymized" claim didn't hold up on inspection). |
| `cnamuangtoun/resume-job-description-fit` (Hugging Face) | Yes — `data/resume_fit_candidates.csv` (300 rows, seeded sample) | Directly downloadable, no auth. Raw resume text, no structured fields, so skills/education/years are extracted via keyword/regex matching (`scripts/convert_resume_fit_dataset.py`) — blunter signal than the other two sources, by construction. The dataset's own fit label (against a *different*, per-row job description) is preserved separately in `data/resume_fit_labels.csv` but not used here — see "What wasn't attempted" below. |
| Kaggle "Resume Dataset" (CC0) | **No** | Kaggle's API requires an authenticated request even for public/CC0 datasets (`curl` to the download endpoint 302-redirects to login) — no credentials available in this environment. Left as a documented option in `dataset-options.md`; would need a Kaggle API token (`~/.kaggle/kaggle.json`) to pull. |
| Open-source-developer research dataset (Mendeley/ScienceDirect) | **No** | This one maps onto the GitHub side, not the LinkedIn CSV — it's real GitHub developer metrics, not resumes. Wiring it in means building a mock `github_source.py` fixture, not another CSV, which is a different piece of work than "convert to our CSV schema." Left as-is in `dataset-options.md`. |

`data/fake_linkedin_candidates.csv` (the original 20-row hand-written set)
was left untouched — `tests/test_linkedin_source.py` asserts on its exact
contents, and it's the known-answer sanity check the other two datasets
don't have.

## Aggregate results, all three datasets, same req

| Dataset | n | Traditional qualified % | Traditional avg score | Experimental qualified % (Foundation) | Foundation avg | Bonus avg | Momentum avg |
|---|--:|--:|--:|--:|--:|--:|--:|
| `fake_linkedin_candidates` (hand-written demo) | 20 | 40.0% | 57.8 | 40.0% | 54.9 | 42.8 | 2.0 |
| `hf_resume_candidates` (real+synthetic resumes) | 300 | 8.3% | 48.1 | 20.0% | 50.2 | 7.8 | 0.0 |
| `resume_fit_candidates` (real resume text, keyword-extracted) | 300 | 4.0% | 37.9 | 6.7% | 33.6 | 6.8 | 0.0 |

Raw per-candidate output: `out/*-traditional.csv`, `out/*-experimental.csv`
(gitignored — regenerate with the commands in "Reproducing this" below).

## What this actually shows

**1. The hand-written demo data was flattering.** 40% of the invented
candidates qualify under both passes; only 4–8% of real-ish candidates do,
on the same req. That's not a scoring bug — it's what happens when the
demo set is 20 candidates written by someone who already knew what
"qualified" was supposed to look like, versus a broad, unfiltered resume
sample where most people (as in reality) aren't backend engineers. Worth
flagging in `README.md`'s Limitations section: results demoed against
`fake_linkedin_candidates.csv` alone will look more successful than the
tool actually is against an unfiltered candidate pool.

**2. The experimental pass qualifies more candidates than the traditional
pass on every dataset — and on the real datasets, the gap is not about
location.** With `remote_ok: true`, location scores its max in *both*
passes, so this run isolates a different effect than the README's
onsite-req walkthrough: **internal re-weighting.** Traditional splits its
100 points as skill 40 / experience 20 / recency 20 / location 10 /
corroboration 10 (`SCORING.md`). Foundation splits its 100 points as skill
60 / experience 40 — and drops recency, location, and corroboration
entirely. For `hf_resume_candidates` and `resume_fit_candidates`, recency
is always neutral (0.5) because `currently_open_to_work` isn't a field
either source has, and corroboration is always 0 because there's no
GitHub match to corroborate against. So on real datasets built from a
single source, **30 of the traditional pass's 100 points go to signals
that are structurally absent, silently diluting the skill/experience
signal that's actually present** — Foundation doesn't have that dilution.
That's a second, previously undocumented bias worth adding to
`EXPERIMENTAL_SCORING.md`: the traditional pass doesn't just penalize
non-local candidates and dormant GitHub profiles, it penalizes *any*
single-source candidate pool, structurally, regardless of location.

**3. Bonus and Momentum are close to zero on both real datasets** — not
because those candidates lack certifications/open-source work/momentum,
but because neither source dataset has those fields (`dataset-options.md`
flagged this as a known gap: `certifications`, `open_source_contributor`,
`volunteer_experience` are blank for every converted row). Momentum is
exactly 0.0 everywhere in this run because it's GitHub-only and this run
used `--skip-github`. This isn't a finding about the scorer — it's a
reminder that Bonus/Momentum are only as good as the optional fields a
real LinkedIn export or live GitHub pull would actually supply; the
converted datasets under-test those two axes by construction.

## What wasn't attempted

- **Validating against `resume_fit_candidates`' own fit labels.** That
  dataset's label is Good Fit / Potential Fit / No Fit against the *row's
  own* paired job description, not against `reqs/example-backend-engineer.yaml`.
  Comparing our score to that label would be comparing answers to two
  different questions. A real validation pass would need to either (a)
  turn a sample of the dataset's job descriptions into req YAMLs and score
  each resume against its own paired req, or (b) restrict to rows whose
  paired job description is close enough to one of our existing reqs to
  be a fair comparison. Neither was done here; `data/resume_fit_labels.csv`
  is kept so this is a smaller follow-up, not a re-download.
- **Running with live GitHub data.** Every run above used `--skip-github`.
  Momentum is untested until this runs with a real `GITHUB_TOKEN`.
- **Kaggle CC0 dataset and the OSS-developer GitHub dataset** — see the
  table above.

## Reproducing this

```bash
# datasetmaster/resumes -> data/hf_resume_candidates.csv
curl -L -o /tmp/master_resumes.jsonl \
  https://huggingface.co/datasets/datasetmaster/resumes/resolve/main/master_resumes.jsonl
python3 scripts/convert_hf_resumes.py /tmp/master_resumes.jsonl \
  data/hf_resume_candidates.csv --limit 300 --seed 42

# cnamuangtoun/resume-job-description-fit -> data/resume_fit_candidates.csv
curl -L -o /tmp/resume_fit_train.csv \
  https://huggingface.co/datasets/cnamuangtoun/resume-job-description-fit/resolve/main/train.csv
python3 scripts/convert_resume_fit_dataset.py /tmp/resume_fit_train.csv \
  data/resume_fit_candidates.csv --limit 300 --seed 42

# Run both passes against all three datasets
for ds in fake_linkedin_candidates hf_resume_candidates resume_fit_candidates; do
  python -m sourcing.cli --req reqs/example-backend-engineer.yaml \
    --linkedin-csv data/$ds.csv --skip-github --out out/$ds-traditional.csv
  python -m sourcing.cli_experimental --req reqs/example-backend-engineer.yaml \
    --linkedin-csv data/$ds.csv --skip-github --out out/$ds-experimental.csv
  python -m sourcing.compare_passes \
    --traditional-csv out/$ds-traditional.csv \
    --experimental-csv out/$ds-experimental.csv \
    --out out/$ds-comparison.csv
done
```
