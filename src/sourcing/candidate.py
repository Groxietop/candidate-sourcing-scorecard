"""The common shape every source normalizes into, so scoring.py never has
to know whether a candidate came from GitHub or a LinkedIn CSV.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Candidate:
    name: str
    source: str  # "github" or "linkedin"
    profile_url: str
    skills: set[str] = field(default_factory=set)
    location: str | None = None
    years_experience: float | None = None  # direct (LinkedIn) or proxy (GitHub)
    account_age_years: float | None = None  # GitHub only
    total_stars: int | None = None  # GitHub only
    days_since_last_active: int | None = None
    currently_open_to_work: bool | None = None  # LinkedIn only, if present
    github_handle: str | None = None  # used to corroborate across sources
    current_title: str | None = None  # LinkedIn only

    # --- Fields below are only used by the experimental scorer (scoring_experimental.py). ---
    # They're additive/reward-only inputs, never gating — see EXPERIMENTAL_SCORING.md.

    # GitHub-only, used for the momentum axis's acceleration signal: how many
    # of the candidate's repos were pushed to in the last 6 months vs. the
    # 6-18 months before that. Two raw counts rather than one ratio so the
    # scorer can tell "no data" (both None) apart from "zero activity".
    recent_push_count: int | None = None
    prior_push_count: int | None = None
    # GitHub-only, used for the bonus axis's docs signal: fraction of the
    # candidate's repos that have a non-empty description.
    docs_repo_ratio: float | None = None

    # LinkedIn-only, used for the bonus axis. All optional in the source CSV;
    # missing/blank means "no data", which contributes 0 (never a penalty).
    certifications: str | None = None
    open_source_contributor: bool | None = None
    volunteer_experience: bool | None = None
    education_level: str | None = None

    def identity_key(self) -> str:
        """Loose dedupe/corroboration key: prefer github handle, else name."""
        if self.github_handle:
            return f"gh:{self.github_handle.strip().lower()}"
        return f"name:{self.name.strip().lower()}"
