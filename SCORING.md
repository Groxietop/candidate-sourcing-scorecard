# What "qualified" means here

Every candidate gets a score from **0–100** and a **per-category breakdown**
so the number is never a black box. A candidate is labeled `qualified` in
the output if their total score meets the req's `qualify_threshold`
(default: 60 — see `reqs/*.yaml`).

This is deliberately a simple, auditable weighted rubric — not a model.
Anyone can read this file, read `src/sourcing/scoring.py`, and reproduce a
score by hand.

## Categories and weights

| Category | Weight | What it measures | Source |
|---|---|---|---|
| Skill match | 40 | Overlap between the req's `required_skills` and the candidate's observed skills | GitHub: languages used + repo topics + bio/README text. LinkedIn: `skills` column. |
| Experience level | 20 | Does the candidate's apparent seniority meet the req's `min_years_experience` / `seniority`? | GitHub: account age + repo count/stars as a proxy. LinkedIn: `years_experience` + `current_title`. |
| Recent activity | 20 | Is the candidate active/plausibly reachable now, vs. a dormant profile? | GitHub: commits/contributions in the last 6 months. LinkedIn: `currently_open_to_work` / `last_active_hint` if present, else neutral score. |
| Location fit | 10 | Does the candidate match the req's `location` (or is the req `remote_ok`)? | GitHub: profile `location` field (self-reported, free text — matched loosely). LinkedIn: `location` column. |
| Multi-source corroboration | 10 | Bonus for candidates who show up with matching signals from more than one source, since independent corroboration is more trustworthy than a single signal | Computed at merge time by matching on name/handle |

Each category is scored 0–1 internally, then multiplied by its weight and
summed. See `scoring.py::score_candidate` for the exact arithmetic — it is a
small, readable function on purpose.

## Skill match, in detail

1. Normalize both the req's `required_skills` and the candidate's observed
   skills to lowercase tokens (e.g. "React.js" -> "react").
2. Score = (number of req skills the candidate has) / (number of req
   skills), capped at 1.0.
3. `required_skills` in the req YAML can be marked `weight: high` to count
   double — e.g. a "must-have" language vs. a "nice to have" framework.

This is intentionally literal (keyword overlap), not semantic — it will
miss a candidate who knows "Postgres" when the req says "SQL". Add synonyms
to the req's `skill_aliases` block to handle known cases; don't expect the
tool to infer them.

## Experience level, in detail

- GitHub proxy: `account_age_years` and `total_stars` are combined into a
  rough experience estimate (see `scoring.py::_github_experience_score`).
  This is explicitly a **weak proxy** — a very experienced engineer with a
  new GitHub account, or a private-repo-only workflow, will score low here.
  Don't over-trust it in isolation; that's why it's only 20% of the total.
- LinkedIn: if `years_experience` is present, compared directly against the
  req's `min_years_experience`.

## Recent activity, in detail

Recency matters because a highly-qualified but totally dormant profile is a
low-value outreach target right now. GitHub activity in the last 6 months
scores 1.0; linearly decaying to 0 at 24+ months of inactivity.

## Location fit, in detail

- If the req sets `remote_ok: true`, this category always scores 1.0.
- Otherwise it's a loose substring/synonym match against the req's
  `location` (e.g. "NYC" matches "New York, NY"). This is intentionally
  generous — false negatives (excluding a real match) are worse than false
  positives here, since a human reviews the final list anyway.

## Multi-source corroboration, in detail

If a candidate's name (normalized) or a shared identifier (e.g. a GitHub
handle listed in a LinkedIn profile) appears in more than one source, they
get the full 10 points. Single-source candidates get 0 here — not a
penalty, just no bonus. This rewards signal strength, not source count for
its own sake.

## Known failure modes (be honest about these with stakeholders)

- **Survivorship bias toward open-source-visible engineers.** People who
  don't have public GitHub activity (very common for senior engineers at
  companies with strict IP policies) will systematically underscore on the
  GitHub-derived categories.
- **Self-reported fields are unverified.** Location, skills, and years of
  experience as written by the candidate are not fact-checked by this tool.
- **English-centric keyword matching.** Skill matching is literal string
  matching; it doesn't handle multilingual profiles well.
- **Not a substitute for human judgment or your EEO/compliance process.**
  Treat the score as a sort order for a longlist, not a hiring decision.
