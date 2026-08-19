"""Load and validate a req (job requisition) YAML file into a Req object.

See reqs/example-backend-engineer.yaml for the file format and comments on
each field. Keeping this loader small and explicit (rather than a generic
schema library) is deliberate: the whole point is that a non-engineer can
open the YAML and understand exactly what will be scored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class RequiredSkill:
    skill: str
    weight: str = "normal"  # "normal" or "high"

    @property
    def weight_multiplier(self) -> float:
        return 2.0 if self.weight == "high" else 1.0


@dataclass(frozen=True)
class Req:
    req_id: str
    title: str
    required_skills: list[RequiredSkill]
    skill_aliases: dict[str, list[str]] = field(default_factory=dict)
    min_years_experience: float = 0
    seniority: str = ""
    location: str = ""
    remote_ok: bool = False
    qualify_threshold: float = 60
    notes: str = ""

    def canonical_skill(self, raw_skill: str) -> str:
        """Map a raw skill string to its canonical form using skill_aliases.

        e.g. if skill_aliases has `postgresql: [postgres, psql]`, then both
        "postgres" and "psql" normalize to "postgresql". Unrecognized
        skills pass through unchanged (lowercased).
        """
        normalized = raw_skill.strip().lower()
        for canonical, aliases in self.skill_aliases.items():
            if normalized == canonical.lower() or normalized in (a.lower() for a in aliases):
                return canonical.lower()
        return normalized


def load_req(path: str | Path) -> Req:
    path = Path(path)
    with path.open() as f:
        raw = yaml.safe_load(f)

    required_skills = [
        RequiredSkill(skill=s["skill"].strip().lower(), weight=s.get("weight", "normal"))
        for s in raw.get("required_skills", [])
    ]

    return Req(
        req_id=raw["req_id"],
        title=raw["title"],
        required_skills=required_skills,
        skill_aliases=raw.get("skill_aliases", {}) or {},
        min_years_experience=float(raw.get("min_years_experience", 0)),
        seniority=raw.get("seniority", ""),
        location=raw.get("location", ""),
        remote_ok=bool(raw.get("remote_ok", False)),
        qualify_threshold=float(raw.get("qualify_threshold", 60)),
        notes=raw.get("notes", ""),
    )
