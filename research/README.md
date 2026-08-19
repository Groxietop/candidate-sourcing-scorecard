# Research

Background research that informed (or should inform) the scoring design,
kept separate from the scoring code itself so it can be updated without
touching `SCORING.md`/`EXPERIMENTAL_SCORING.md`.

- [`market-practice-comparison.md`](market-practice-comparison.md) — how
  the traditional pass and the experimental 3-axis pass compare to what's
  actually used in the recruiting industry (rubric methodology, commercial
  sourcing-tool scoring, and the regulatory bias-audit landscape), with
  sources.
- [`dataset-options.md`](dataset-options.md) — public datasets that could
  replace the hand-written `data/fake_linkedin_candidates.csv` so the demo
  isn't running against invented data, with a concrete recommendation and
  field-mapping.
- [`dataset-run-results.md`](dataset-run-results.md) — two of those
  datasets actually pulled in and converted (`scripts/convert_hf_resumes.py`,
  `scripts/convert_resume_fit_dataset.py`), with both scoring passes run
  against them and against the hand-written demo data, compared.
