# Candidate Sourcing Scorecard

A sourcing tool built on one rule: **it is inexcusable to discard the dream candidate.**

---

## 1. The problem

Most automated screening tools spit out a binary. Above the line you exist, below it you were never there. Nobody sees who got cut or why.

That's fine when the score is right. The problem is that a score built on data you don't have looks identical to one built on data you do.

The errors aren't symmetric either:

| | Cost |
|---|---|
| **False positive** — a mediocre candidate reaches a human | ~30 seconds |
| **False negative** — the right person is silently removed | The hire that never happened, and nobody finds out |

Optimizing for total error trades the second away for the first.

---

## 2. The fix

**Track whether I actually measured something.** Every category carries its value plus an observed/imputed flag ([`evidence.py`](src/sourcing/evidence.py)). Confidence is the share of scoring weight backed by real observation.

**One rule:** a candidate can only be set aside on positive evidence of a miss, never on missing evidence. If I don't know something about someone, that's a fact about my data, not about them.

**Four tiers instead of a cut** ([`triage.py`](src/sourcing/triage.py)):

| Tier | Meaning |
|---|---|
| **Strong** | Clears the bar on measured evidence |
| **Review** | Over the bar, but partly on guesswork or missing a must-have |
| **Caveated** | Under the bar, but the weakness is on signals I never observed. Never auto-removed. |
| **Set aside** | I observed the relevant signal and it came up short |

Only the last leaves the queue. Those are still listed with full reasoning so you can overrule them.

Caveats name a specific failure mode, not a generic hedge:

> *"a quiet public profile can mean private-repo work, a career break, parental leave, or simply not coding in public"*

![Two candidates in the review queue, both scoring 59 points. Nadia Osei is Caveated at 80% measured with experience flagged as scored on guesswork; Finley Okonkwo is Set aside at 100% measured with an observed missing must-have.](docs/ui-caveated.png)

The whole idea is in that screenshot. Both candidates score **59** against a bar of 60.

- **Nadia Osei** — 80% measured. The missing 20% is experience, and the caveat says why that matters: seniority is inferred from GitHub account age, which tells you nothing about a veteran who made an account last year. Stays in the queue.
- **Finley Okonkwo** — 100% measured. I saw the skill set and PostgreSQL isn't in it. That's evidence, so it's set aside — with the caveat still attached, since public repos hide what people use at work.

Same score, different amounts of knowledge. A binary can't tell them apart and cuts both.

---

## 3. Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Optional. Without it you get GitHub's very low unauthenticated rate
# limit. Any token with no scopes works.
export GITHUB_TOKEN=...
```

Score a req and get both a CSV and a tiered review queue:

```bash
python -m sourcing.cli \
  --req reqs/example-backend-engineer.yaml \
  --linkedin-csv data/fake_linkedin_candidates.csv \
  --out out/candidates.csv \
  --review-out out/review.md
```

Add `--skip-github` for a fully offline run against the demo data. That one is deterministic — 26 candidates, 10 kept in the queue, 16 set aside:

```
tiers: strong 5 · review 3 · caveated 2 · discard 16
```

There's also a **[working review-queue UI](https://claude.ai/code/artifact/f7ef6f6f-671f-444b-9d7e-d17ff3608233)** — job description, per-candidate detail, and Advance / Not-a-fit verdicts that persist and sync between viewers.

![Review queue header: the job description the model scores against, the standing rule that a candidate is only set aside on positive evidence of a miss, and a scoreboard showing missed rate, precision, recall and candidates reviewed.](docs/ui-overview.png)

```bash
pytest -q     # 107 tests
```

---

## 4. Measuring whether it works

Every verdict gets recorded, and metrics come only from recorded decisions ([`feedback.py`](src/sourcing/feedback.py)). An empty log says "no decisions yet" instead of showing a made-up number.

The headline metric is **not** precision. Precision asks "of the people we advanced, how many were good" — you can ace that by advancing almost nobody. The number I care about is the inverse:

```
missed_rate = of the candidates I set aside,
              how many did the recruiter actually want?
```

That's the false-negative rate on my own discard pile. It's the only metric that gets worse when the tool gets overconfident.

Feedback also drives recalibration ([`calibration.py`](src/sourcing/calibration.py)). Repeated "not senior enough" rejections on advanced candidates means the experience signal is reading high, so it proposes a weight cut with the evidence attached. **Never auto-applied** — a model that silently re-weights itself is how you end up with a bias nobody can point at.

```bash
python -m sourcing.cli_feedback record --candidate "Nadia Osei" --req eng-backend-001 \
  --tier caveated --verdict advance --reason actually_strong

python -m sourcing.cli_feedback report      # metrics, and who we wrongly set aside
python -m sourcing.cli_feedback calibrate   # proposed weight changes, unapplied
```

The UI holds verdicts in its own page state; the CLI log is the durable one. `cli_feedback import-verdicts --file ui.json` bridges them.

---

## 5. Integrations

| | Status |
|---|---|
| **GitHub** | Live. Repository/topic search. |
| **LinkedIn Recruiter** ([code](src/sourcing/integrations/linkedin_recruiter.py)) | Seat-export connector, tracks provenance and staleness |
| **Ashby ATS** ([code](src/sourcing/integrations/ashby.py)) | Built against Ashby's real API. No tenant behind this repo, so it dry-runs by default |

The Ashby adapter **never rejects anyone in the ATS.** Set-aside candidates still get pushed, tagged `scorecard:caveated-do-not-cut`, with the reasoning in a note. A rejection in the system of record is where an automated call becomes irreversible. The tool's opinion travels with the candidate; the decision doesn't.

```bash
# Dry run by default — no credentials needed, prints every request it would send
python -m sourcing.cli_push --req reqs/example-backend-engineer.yaml \
  --linkedin-csv data/fake_linkedin_candidates.csv --skip-github \
  --job-id <ashby-job-id> --show-payloads

# For real: needs ASHBY_API_KEY
python -m sourcing.cli_push --req ... --job-id ... --send
```

On that offline demo pool: 26 `candidate.create`, 26 `candidate.addTag`, 26 `candidate.createNote` — and only 8 `application.create`. Everyone lands in the ATS with their reasoning; only the advanced tiers become active applications. No rejection call appears, because there isn't one.

---

## 6. It runs itself

```bash
python -m sourcing.watch --req reqs/example-backend-engineer.yaml \
  --report-out out/watch-report.md
```

`.github/workflows/watch.yml` runs that weekly, diffs against the last snapshot in `data/snapshots/`, commits the new state, and opens a GitHub Issue when the pool changes. Cron plus `workflow_dispatch` and `repository_dispatch`. Free tier.

---

## 7. Choices I made, and why

**Discovery favors people who build in public.** Repo search finds candidates by what they ship, so engineers under strict IP policies are harder to surface. The triage layer can't fix this one — you can't caveat someone you never found.

**"Set aside" is still a judgement call.** 16 of 26 in the offline demo run land there. Defensible (observed skills, real missing must-have) but that pile is worth reading.

**Corroboration was a hidden penalty.** SCORING.md called it "not a penalty, just no bonus," but on a 100-point scale with a 60-point bar, scoring 0 is a 10-point penalty for only existing on GitHub. Now excluded from counting as a measured weakness.

**The demo LinkedIn export was too clean.** Every scored field was populated, so the Caveated tier could never fire — the main thing this tool does was untestable. Added sparse rows, since real exports have gaps.

**No LLM, on purpose** ([`escalation.py`](src/sourcing/escalation.py)). Designed and priced, left off for cost at this stage. The escalation queue would be the Caveated tier only — that tier *is* the ambiguity, so spend tracks genuine judgement calls rather than pool size. If I turn it on, an LLM can only move someone *up* a tier; model output isn't the positive evidence the discard rule needs.

**Not a compliance or EEO tool.** This is triage for building an outreach list, not a basis for hiring decisions.

---

## Scoring rubric

0–100 across five weighted categories. Full detail in [`SCORING.md`](SCORING.md), plus an experimental three-axis pass in [`EXPERIMENTAL_SCORING.md`](EXPERIMENTAL_SCORING.md). Both produce tiers now.

| Category | Weight | Measures |
|---|---|---|
| Skill match | 40 | Overlap with the req's `required_skills` |
| Experience | 20 | Seniority vs `min_years_experience` |
| Recency | 20 | Active and reachable now |
| Location | 10 | Matches `location`, or 1.0 when `remote_ok` |
| Corroboration | 10 | Bonus for appearing in more than one source |
