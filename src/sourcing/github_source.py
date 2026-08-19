"""Pulls candidates from GitHub's public Search + REST API — no scraping,
just the documented API, within its rate limits
(https://docs.github.com/en/rest/using-the-api/rate-limits-for-the-rest-api).

Auth is optional but strongly recommended: unauthenticated requests share a
very small rate limit (10 search requests/min, 60 REST requests/hour) that
this tool will burn through in a couple of candidates. Set GITHUB_TOKEN
(a token with no scopes at all is sufficient — this only reads public data)
to get 30 search requests/min and 5,000 REST requests/hour.

This module fails soft: any network/API error for an individual candidate
is logged and skipped rather than crashing the whole run, since a partial
candidate list is more useful than none.
"""

from __future__ import annotations

import datetime as dt
import sys

import requests

from .candidate import Candidate
from .config import Req

API_ROOT = "https://api.github.com"

# GitHub's Linguist recognizes many more, but these are the common ones
# worth treating as a `language:` search qualifier rather than free text.
_KNOWN_LANGUAGES = {
    "python", "javascript", "typescript", "java", "ruby", "go", "rust",
    "c", "c++", "c#", "php", "swift", "kotlin", "scala", "html", "css",
}


class GitHubSource:
    def __init__(self, token: str | None = None, timeout: float = 10.0):
        self.session = requests.Session()
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.session.headers.update(headers)
        self.timeout = timeout

    def _get(self, url: str, **kwargs) -> requests.Response | None:
        try:
            resp = self.session.get(url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            print(f"  [github] request failed for {url}: {exc}", file=sys.stderr)
            return None
        if resp.status_code == 403:
            print(
                f"  [github] rate-limited (403) on {url} — "
                "set GITHUB_TOKEN for a much higher limit. Skipping.",
                file=sys.stderr,
            )
            return None
        if not resp.ok:
            print(f"  [github] {resp.status_code} on {url}: {resp.text[:200]}", file=sys.stderr)
            return None
        return resp

    def search_users(self, req: Req, max_results: int) -> list[str]:
        """Return up to max_results GitHub logins matching the req's skills/location."""
        query_parts = []

        language_skill = next(
            (rs.skill for rs in req.required_skills if rs.skill in _KNOWN_LANGUAGES), None
        )
        if language_skill:
            query_parts.append(f"language:{language_skill}")

        if req.location and req.location.strip().lower() != "remote":
            # GitHub's location qualifier is a loose match against the free-text
            # profile location field, so this is best-effort, not exact.
            query_parts.append(f'location:"{req.location.split(",")[0].strip()}"')

        # Everything else goes in as free text, matched loosely against bio/login.
        free_text_skills = [
            rs.skill for rs in req.required_skills if rs.skill != language_skill
        ]
        query_parts.extend(free_text_skills[:2])  # keep the query from getting too narrow

        query_parts.append("type:user")
        query = " ".join(query_parts)

        resp = self._get(
            f"{API_ROOT}/search/users",
            params={"q": query, "sort": "followers", "order": "desc", "per_page": max_results},
        )
        if resp is None:
            return []
        return [item["login"] for item in resp.json().get("items", [])]

    def fetch_candidate(self, login: str) -> Candidate | None:
        profile_resp = self._get(f"{API_ROOT}/users/{login}")
        if profile_resp is None:
            return None
        profile = profile_resp.json()

        repos_resp = self._get(
            f"{API_ROOT}/users/{login}/repos",
            params={"sort": "pushed", "per_page": 100, "type": "owner"},
        )
        repos = repos_resp.json() if repos_resp is not None else []

        skills = {r["language"].lower() for r in repos if r.get("language")}
        for r in repos:
            skills.update(t.lower() for t in (r.get("topics") or []))

        total_stars = sum(r.get("stargazers_count", 0) for r in repos)

        last_pushed = None
        for r in repos:
            pushed_at = r.get("pushed_at")
            if pushed_at and (last_pushed is None or pushed_at > last_pushed):
                last_pushed = pushed_at
        days_since_active = None
        if last_pushed:
            pushed_dt = dt.datetime.strptime(last_pushed, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=dt.timezone.utc
            )
            days_since_active = (dt.datetime.now(dt.timezone.utc) - pushed_dt).days

        account_age_years = None
        created_at = profile.get("created_at")
        if created_at:
            created_dt = dt.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=dt.timezone.utc
            )
            account_age_years = (dt.datetime.now(dt.timezone.utc) - created_dt).days / 365.25

        return Candidate(
            name=profile.get("name") or login,
            source="github",
            profile_url=profile.get("html_url", f"https://github.com/{login}"),
            skills=skills,
            location=profile.get("location"),
            account_age_years=account_age_years,
            total_stars=total_stars,
            days_since_last_active=days_since_active,
            github_handle=login,
        )


def fetch_github_candidates(req: Req, token: str | None, max_results: int = 15) -> list[Candidate]:
    source = GitHubSource(token=token)
    logins = source.search_users(req, max_results=max_results)
    candidates = []
    for login in logins:
        candidate = source.fetch_candidate(login)
        if candidate:
            candidates.append(candidate)
    return candidates
