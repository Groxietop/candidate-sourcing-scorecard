# Market practice comparison

How this repo's two scoring passes — the traditional single-score pass
(`scoring.py`/`SCORING.md`) and the experimental 3-axis pass
(`scoring_experimental.py`/`EXPERIMENTAL_SCORING.md`) — stack up against
what's actually standard in recruiting today: manual rubric methodology,
commercial sourcing-tool scoring, and the regulatory bias-audit landscape.
Research done 2026-08-19; sources at the bottom.

## The three things "market practice" actually means here

**1. Manual rubric methodology.** The dominant pattern recruiters are
taught: pick 6–10 criteria, split into **must-haves** (gating, heavier
weight) and **nice-to-haves** (additive, lighter weight), score each on a
fixed scale with written anchors for what a 1/3/5 looks like, sum to a
weighted total. The rubric is written *before* seeing candidates — writing
it post-hoc is the most commonly cited failure mode, because interviewers
unconsciously reverse-engineer criteria to justify someone they already
like.

The most-cited named framework is **"Who: The A Method for Hiring"**
(Smart & Street): a scorecard of mission + outcomes + competencies,
evaluated through structured interviews (screening → historical → focused
→ reference, with 7 references per candidate), collapsing to a single
**A/B/C grade** — only hire A-players.

**2. Commercial sourcing-tool scoring.** Vendors that source/rank
candidates from public signals the way this repo's GitHub source does:

- **SeekOut** — assigns a "coder score" from GitHub contribution
  volume/patterns, aggregated with Stack Overflow, patents, publications
  into one ranked view.
- **hireEZ** — aggregates 45+ sources (LinkedIn, GitHub, Google Scholar)
  into one AI-ranked list; scoring logic isn't exposed to the recruiter.
- **Entelo** — scores on *likelihood to move* (tenure patterns, recent
  activity, engagement signals) rather than skill fit — a "will they
  leave their current job" signal, not a "can they do this job" one.

**3. The regulatory bias-audit layer.** **NYC Local Law 144** — the first
US law of its kind — requires any "Automated Employment Decision Tool"
used to screen candidates (explicitly including "candidate matching
algorithms") to undergo an **independent annual bias/disparate-impact
audit**, publish a summary of results, and give candidates 10 business
days' notice plus an opt-out. Other jurisdictions (Illinois, Colorado, EU
AI Act) are converging on similar audit/disclosure requirements, though
commentary flags patchy, under-enforced compliance industry-wide.

## Side-by-side

| Dimension | Approach 1: Traditional pass (`scoring.py`) | Approach 2: Experimental pass (`scoring_experimental.py`) | Market practice |
|---|---|---|---|
| **Output shape** | One blended 0–100 score | Three independent 0–100 axes (Foundation / Bonus / Momentum) — a point in 3-D space, not a leaderboard position | Overwhelmingly one blended score or grade (rubric total, "Who" A/B/C grade, vendor ranked list). Multi-axis scoring is the exception, not the rule. |
| **Gating logic** | Skill match + experience + location all blend into the one number that determines `qualified` | Only Foundation (skill match + experience) gates `qualified`; location and reward signals never gate | Matches rubric best practice: must-haves gate, nice-to-haves are additive — but most tools/rubrics still don't separate location out from the gating tier the way Axis 1 does here |
| **Location handling** | Candidate scores 0 on location if not already local and req isn't `remote_ok` — silently assumes unwillingness to relocate | Excluded from the gating axis entirely; only shows up as a small reward signal in Bonus | Rubric guidance doesn't call this out explicitly; commercial tools vary (some treat non-local as a hard filter, mirroring Approach 1's bias) |
| **Missing/quiet data** | Dormant GitHub or missing LinkedIn fields score low — treated as a negative signal | Missing data contributes 0 to Bonus/Momentum — a neutral floor, never a penalty | SeekOut's coder-score approach effectively penalizes quiet profiles the same way Approach 1 does (volume-based); no major vendor documents a neutral-floor design |
| **Transparency** | Full per-criterion breakdown written to CSV | Same, per axis | "Who" method is fully transparent (it's a manual scorecard); most commercial vendor tools are comparative black boxes — ranking logic isn't exposed to the recruiter |
| **Validation against outcomes** | Weights are a documented starting point, not validated (see `SCORING.md` limitations) | Same, explicitly unvalidated | Best-practice guidance: test candidate rubric against 10–20 historic profiles, compare predicted rank to actual hire/performance outcomes, then tune. Neither pass here has done this yet. |
| **Bias/disparate-impact audit** | None | None | NYC Local Law 144 (and similar emerging state/EU rules) would require an independent annual bias audit + public disclosure if this were used to screen real candidates for a covered employer |
| **Candidate notice/opt-out** | None (not applicable — this is a sourcing/triage aid, not an adverse-decision tool) | None | LL144 requires 10 business days' notice + opt-out for any AEDT used in screening. Would become relevant if this pipeline were ever wired into an actual ATS decision. |
| **Data sourcing policy** | Real GitHub API (ToS-compliant), LinkedIn via licensed CSV export only, never scraped | Same | Commercial vendors (hireEZ, SeekOut) aggregate LinkedIn data at scale in ways whose ToS-compliance is contested; this repo's no-scraping stance is stricter than typical market practice |

## Takeaways

- The experimental pass's core idea — split gating (objective fit) from
  reward-only signals, with a neutral floor for missing data — is **not**
  something the researched commercial tools or the classic "Who" method
  do. It's a genuine improvement over both, not just over the traditional
  pass in this repo.
- The one thing every source agrees on that neither pass here does yet:
  **validate the weights against real outcomes** before trusting them.
  `SCORING.md` and `EXPERIMENTAL_SCORING.md` already flag this as a
  limitation; this research doesn't change that, it just confirms it's
  the standard next step, not an afterthought.
- If this project is ever pointed at real candidates for an actual hiring
  decision (not just triage/outreach-list generation), NYC LL144-style
  bias auditing and candidate notice become real requirements, not
  optional hardening. Worth a line in `README.md`'s Limitations section
  if/when that's on the table.

## Sources and systems referenced

- [SeekOut — Interview Scorecard vs Hiring Rubric](https://www.seekout.com/blog/interview-scorecard-vs-hiring-rubric/)
- [Testask — Candidate Scoring Methods, 2026 Hiring Guide](https://testask.org/blog/candidate-scoring-methods-a-2026-hiring-guide)
- [ZYTHR — How to Build a Weighted Candidate Scoring Matrix](https://zythr.com/resources/candidate-scoring-model-in-recruiting-what-it-is-and-how-to-build-one/how-to-build-a-weighted-candidate-scoring-matrix-stepbystep-template-and-examples)
- [Welcome to the Jungle — Who: The A Method for Hiring](https://www.welcometothejungle.com/en/articles/who-the-a-method-for-hiring-by-geoff-smart-and-randy-street)
- [Readingraphics — Book Summary: Who: The A Method for Hiring](https://readingraphics.com/book-summary-who-the-a-method-for-hiring/)
- [HackerEarth — 8 best candidate sourcing tools in 2026](https://assessment.hackerearth.com/blog/8-best-candidate-sourcing-tools-in-2026-an-expert-evaluation-guide)
- [DLA Piper — Critical audit of NYC's AI hiring law signals increased risk for employers](https://www.dlapiper.com/en-us/insights/publications/2026/01/critical-audit-of-nyc-ai-hiring-law-signals-increased-risk-for-employers)
- [Deloitte — NYC Local Law 144-21 and Algorithmic Bias](https://www.deloitte.com/us/en/services/audit-assurance/articles/nyc-local-law-144-algorithmic-bias.html)

Systems referenced but not directly cited above: SeekOut, hireEZ, Entelo
(commercial sourcing/scoring vendors); "Who: The A Method for Hiring"
(Smart & Street, structured-interview scorecard methodology).
