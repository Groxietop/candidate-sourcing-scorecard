# Candidate Sourcing Scorecard

A small, transparent tool that takes an open req (job requisition) and produces
a **ranked, scored candidate list** from public signals — with every score
broken down so a human can see exactly why a candidate ranked where they did.

**Status: proof of concept.** Live GitHub data, synthetic LinkedIn data (see
below). Not connected to any real ATS or real LinkedIn account.

## Why it's built this way

- **Cheap/free**: GitHub's Search + REST API is free at the tier this needs
  (5,000 authenticated requests/hour). No paid data vendor, no scraping
  infrastructure.
- **Defensible**: GitHub data is pulled through GitHub's own public API,
  within its rate limits and terms of service — nothing here scrapes GitHub's
  website. LinkedIn does **not** offer a public search API, and scraping it
  violates LinkedIn's Terms of Service (and carries real legal risk — see
  *hiQ Labs v. LinkedIn* for how contested this is even for "public" data).
  So this project **never scrapes LinkedIn**. The LinkedIn path is a CSV
  importer: in real use, that CSV is a manual export from a LinkedIn
  Recruiter/Sales Navigator seat the requester is already licensed to use.
  Since this proof of concept was built without such a seat, the included
  `data/fake_linkedin_candidates.csv` is 100% invented — fictional names at
  fictional companies (Acme Corp, Globex, Initech, Hooli...) — used only to
  demonstrate the ingestion and scoring code path.
- **Scalable**: sources are pluggable (`src/sourcing/*_source.py`), scoring
  is a pure function over a common `Candidate` shape, and reqs are just YAML
  files — add a req, run the CLI, get a ranked CSV.
- **Well documented**: the full scoring rubric — the actual definition of
  "qualified" used here — lives in [`SCORING.md`](SCORING.md), not buried in
  code.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .   # installs the `sourcing` package so `python -m sourcing.cli` resolves

cp .env.example .env
# edit .env and set GITHUB_TOKEN (a classic PAT with no scopes needed for
# public search is fine: https://github.com/settings/tokens)
export GITHUB_TOKEN=...   # or pass --github-token directly

python -m sourcing.cli \
  --req reqs/example-backend-engineer.yaml \
  --linkedin-csv data/fake_linkedin_candidates.csv \
  --out out/backend-engineer-candidates.csv
```

This prints a ranked table to the console and writes the full scorecard
(every candidate, every sub-score, every reason) to the `--out` CSV.

## Project layout

```
reqs/                    Open req definitions (YAML) — what "this job needs" means
data/                    Synthetic demo data (fake LinkedIn export)
src/sourcing/
  config.py              Loads/validates a req YAML into a Req object
  github_source.py       Live GitHub Search API -> candidates
  linkedin_source.py     CSV -> candidates (real export or synthetic demo file)
  scoring.py             The rubric: Candidate + Req -> score + breakdown
  cli.py                 Wires it together, writes ranked CSV
tests/                   Unit tests (scoring is fully unit-testable, no network)
SCORING.md               The definition of "qualified", spelled out
```

## Writing a real req

Copy `reqs/example-backend-engineer.yaml` and edit the fields — see comments
in that file. No code changes needed to source a new req.

## Using real data instead of the demo

- **GitHub**: already real and live — just set `GITHUB_TOKEN` and run it.
  Respect GitHub's rate limits (the client backs off automatically on 403s).
- **LinkedIn**: replace `data/fake_linkedin_candidates.csv` with an export
  from your own LinkedIn Recruiter/Sales Navigator seat, matching the same
  column headers (see `src/sourcing/linkedin_source.py` docstring). Do not
  point this at scraped data — that's explicitly the one thing this project
  is designed to avoid.

## Limitations (read before trusting the output)

- GitHub activity is a proxy for skill, not proof of it — it's biased toward
  candidates who work in the open (open source, public side projects) and
  against people who do all their work in private repos.
- The scoring weights in `SCORING.md` are a starting point, not a validated
  model. Tune them per role and sanity-check against a few candidates you
  already know.
- This is not a compliance/EEO tool. Don't use the score as the sole basis
  for a hiring decision — it's a triage aid for building an outreach list.
