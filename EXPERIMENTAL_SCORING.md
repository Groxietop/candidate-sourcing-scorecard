# Experimental scoring: three axes instead of one number

**Status: experimental, run alongside — not instead of — the traditional
pass in `SCORING.md`.** They're intentionally two separate code paths
(`scoring.py` vs `scoring_experimental.py`, `cli.py` vs
`cli_experimental.py`) writing to separate output files, so you can run
both on the same req/candidates and use `compare_passes.py` to see exactly
where and why they disagree. The traditional pass is left completely
unmodified as the baseline — including the behavior this doc fixes.

## Why this exists

The traditional pass collapses everything into one 0–100 score, which
hides two problems:

1. **It penalizes candidates for things we never actually asked about.**
   If a candidate isn't already in the req's city and the req isn't
   `remote_ok`, they score 0 on location — silently assuming they wouldn't
   relocate. Same shape of problem for a dormant GitHub profile: it scores
   low on recency, silently assuming inactivity means unqualified rather
   than, say, "works in private repos" or "on a career break."
2. **A single number can't distinguish "safe, proven fit" from "less
   track record but real upside."** Two candidates can land on the same
   total score for completely different reasons, and the number alone
   doesn't tell a recruiter which kind of bet they're looking at.

## The three axes

Each candidate gets three independent 0–100 scores instead of one. Think
of it as a point in a 3-D space, not a leaderboard position.

### Axis 1 — Foundation (objective, gating)

The only axis that determines `qualified`. Reused directly from the
traditional pass's `_skill_match` and `_experience` functions — same
literal-keyword skill matching, same GitHub-account-age/LinkedIn-years
experience proxy, same weaknesses (see `SCORING.md` for those). Weighted
60% skill match / 40% experience.

**Location is not part of this axis, at all.** That's the fix: a candidate
who isn't currently local is not "less qualified." See Axis 2 for where
location shows up instead.

### Axis 2 — Bonus signals (reward-only, floor at 0)

Nothing here can subtract. Missing data contributes 0, which is a neutral
floor, not a penalty — a candidate is never worse off than a candidate
about whom we simply have less information.

| Signal | GitHub weight | LinkedIn weight | What it rewards |
|---|---|---|---|
| Breadth beyond required skills | 25 | — | Skills/topics beyond what the req asked for, capped at 5 extra |
| Recent activity / availability | 25 | 20 | GitHub: pushed in the last 6mo (same decay curve as the traditional pass's recency, just additive now instead of gating). LinkedIn: `currently_open_to_work` — the closest analog we have to "reachable now." |
| Docs presence | 20 | — | Fraction of repos with a non-empty description (a free proxy for a real README check — see caveat below) |
| Traction | 20 | — | Total stars, log-scaled so an already-famous account doesn't dominate (100 stars = full credit) |
| Certifications | — | 20 | Any value in the `certifications` column |
| Open source contributor | — | 15 | `open_source_contributor` flag |
| Volunteer experience | — | 15 | `volunteer_experience` flag |
| Education | — | 15 | Advanced degree (MS/PhD/MD/JD) in `education_level`. **Deliberately not required or negatively scored for its absence** — a bootcamp grad or self-taught candidate isn't penalized for not having one; an advanced degree is treated purely as a nice-to-have. |
| Location | 10 | 15 | Candidate already local to the req's location. This is the *only* place location affects the score, and it can only help, never hurt. |

Each source has its own weight table (summing to 100) rather than one
shared table, since a GitHub-only candidate and a LinkedIn-only candidate
have access to completely different signals — there's no meaningful way to
force them onto one shared scale without one source structurally
outscoring the other.

### Axis 3 — Momentum / potential (reward-only, floor at 0)

Same non-punitive philosophy as Axis 2, but measuring *trajectory* instead
of *presence*. A candidate with no visible trend data scores 0 here — not
penalized, just no signal to reward.

| Signal | GitHub weight | LinkedIn weight | What it rewards |
|---|---|---|---|
| Acceleration | 60 | — | Fraction of repo pushes in the last 6mo vs. the 6–18mo window before that. All-recent = 1.0 (ramping up); all-older = 0.0 (this is a *floor*, not a penalty for having gone quiet). |
| Traction per tenure | 40 | — | Stars earned per year of account age. Rewards a newer account punching above its age — this is what actually makes it a "potential" signal rather than a re-run of Axis 1's experience proxy. |
| Title velocity | — | 100 | Reaching a senior-sounding title (`current_title`) faster than an illustrative years-of-experience benchmark (e.g. "senior" at 5 years, "staff" at 8). At/behind the benchmark, or no senior-ish keyword found: 0, not negative. |

**The title-velocity benchmarks are illustrative, not validated.** "Senior"
means different things at different companies; treat this signal as a
rough directional hint to sanity-check, not a fact.

## What's deliberately *not* here

- **No penalty anywhere for being non-local, inactive, self-taught, or
  lacking a data point.** Every axis's floor is 0 (or, for Foundation,
  whatever `_experience`/`_skill_match` naturally produce from what's
  actually observed) — nothing here infers a negative from an absence.
- **No forced single ranking.** `cli_experimental.py` sorts by Foundation
  only; Bonus and Momentum are shown as separate columns so a recruiter
  can consciously choose "closest objective fit" vs. "worth a look for
  upside" rather than have that trade-off silently pre-decided by a
  blended weight.

## Known caveats, honestly

- `docs_repo_ratio` uses non-empty repo *description* as a stand-in for
  "has documentation." A real README-content check would cost one extra
  GitHub API call per repo; this proof of concept doesn't spend that
  budget. It will both over- and under-credit candidates relative to a
  real docs check.
- Momentum's acceleration signal will read a legitimate career break
  (parental leave, immigration delay, sabbatical, time in a job that's
  entirely closed-source) the same as someone who's simply disengaged —
  it can't tell those apart. That's exactly why it's a reward-only bonus
  and not a penalty: worst case, it just doesn't add points, rather than
  actively working against that candidate.
- The `certifications` / `open_source_contributor` / `volunteer_experience`
  / `education_level` LinkedIn columns are self-reported and unverified,
  same as everything else in the CSV — see `SCORING.md`'s existing caveats
  on that.
- Weights (60/40 on Foundation, the per-signal splits in Axes 2 and 3) are
  starting points, not a validated model — same status as the traditional
  pass's weights. Tune per role.
