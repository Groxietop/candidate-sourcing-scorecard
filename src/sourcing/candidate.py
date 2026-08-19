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

    def identity_key(self) -> str:
        """Loose dedupe/corroboration key: prefer github handle, else name."""
        if self.github_handle:
            return f"gh:{self.github_handle.strip().lower()}"
        return f"name:{self.name.strip().lower()}"
