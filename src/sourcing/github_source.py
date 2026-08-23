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


def build_search_query(req: Req) -> str:
    """Build the GitHub `search/users` query string for a req. Pulled out
    as a pure function so it's unit-testable without hitting the network.
    """
    query_parts = []

    language_skill = next(
        (rs.skill for rs in req.required_skills if rs.skill in _KNOWN_LANGUAGES), None
    )
    if language_skill:
        query_parts.append(f"language:{language_skill}")

    # A req that's remote_ok shouldn't narrow the search to its office
    # location at all — that excludes exactly the remote candidates the req
    # says it's fine hiring. Only apply the location qualifier for reqs that
    # actually require it.
    if req.location and not req.remote_ok and req.location.strip().lower() != "remote":
        # GitHub's location qualifier is a loose match against the free-text
        # profile location field, so this is best-effort, not exact.
        query_parts.append(f'location:"{req.location.split(",")[0].strip()}"')

    # Everything else goes in as free text, matched loosely against bio/login.
    free_text_skills = [rs.skill for rs in req.required_skills if rs.skill != language_skill]
    query_parts.extend(free_text_skills[:2])  # keep the query from getting too narrow

    query_parts.append("type:user")
    return " ".join(query_parts)


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
        resp = self._get(
            f"{API_ROOT}/search/users",
            params={
                "q": build_search_query(req),
                "sort": "followers",
                "order": "desc",
                "per_page": max_results,
            },
        )
        if resp is None:
            return []
        return [item["login"] for item in resp.json().get("items", [])]

    def search_by_repositories(self, req: Req, max_results: int) -> list[str]:
        """Find candidates by the repositories they own, not their bio text.

        GitHub's *user* search only matches free text against login, name and
        bio, so a req listing several skills produces a query almost nobody
        satisfies -- `pandas scikit-learn` needs both words written in someone's
        profile. Two of the three example reqs returned literally zero results
        that way, permanently.

        Repository search matches what people actually build. One query per
        required skill, unioned, with each owner scored by how many distinct
        required skills their repositories covered -- which is a far better
        skill signal than whether they mentioned it in a bio.
        """
        language = next(
            (rs.skill for rs in req.required_skills if rs.skill in _KNOWN_LANGUAGES),
            None,
        )
        hits: dict[str, set[str]] = {}

        for required in req.required_skills:
            terms = []
            if language and required.skill != language:
                terms.append(f"language:{language}")
            # `topic:` matches curated repo topics; falling back to free text
            # keeps skills that aren't established topics from dropping out.
            terms.append(f"topic:{required.skill}")
            query = " ".join(terms)

            resp = self._get(
                f"{API_ROOT}/search/repositories",
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": min(max_results * 2, 50),
                },
            )
            if resp is None:
                continue

            for item in resp.json().get("items", []):
                owner = item.get("owner") or {}
                # Organisations own a lot of popular repositories and are not
                # candidates.
                if owner.get("type") != "User":
                    continue
                login = owner.get("login")
                if login:
                    hits.setdefault(login, set()).add(required.skill)

        # Most distinct required skills covered wins.
        ranked = sorted(hits.items(), key=lambda kv: len(kv[1]), reverse=True)
        return [login for login, _skills in ranked[:max_results]]

    def discover(self, req: Req, max_results: int) -> list[str]:
        """Repository-based discovery, falling back to user search.

        Repository search is the better signal and the default. User search
        still runs when it turns up nothing, since a req whose skills are not
        established GitHub topics can legitimately come back empty.
        """
        logins = self.search_by_repositories(req, max_results)
        if logins:
            return logins
        print(
            "  [github] repository search found nobody; falling back to user search",
            file=sys.stderr,
        )
        return self.search_users(req, max_results)

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

        now = dt.datetime.now(dt.timezone.utc)
        last_pushed = None
        # Used by the experimental scorer's momentum axis (see
        # EXPERIMENTAL_SCORING.md): how much of this candidate's repo
        # activity falls in the last 6 months vs. the 6-18 months before
        # that. None (not 0) when there are no repos at all, so the scorer
        # can tell "no data" apart from "went quiet".
        recent_push_count = 0 if repos else None
        prior_push_count = 0 if repos else None
        for r in repos:
            pushed_at = r.get("pushed_at")
            if not pushed_at:
                continue
            if last_pushed is None or pushed_at > last_pushed:
                last_pushed = pushed_at
            pushed_dt = dt.datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=dt.timezone.utc
            )
            days_ago = (now - pushed_dt).days
            if days_ago <= 182:
                recent_push_count += 1
            elif days_ago <= 548:  # ~18 months
                prior_push_count += 1

        days_since_active = None
        if last_pushed:
            pushed_dt = dt.datetime.strptime(last_pushed, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=dt.timezone.utc
            )
            days_since_active = (now - pushed_dt).days

        # Used by the experimental scorer's bonus axis: crude "has this
        # person documented their work" proxy. A real README check would
        # cost one extra API call per repo; a non-empty description is a
        # free stand-in for the purposes of this proof of concept.
        docs_repo_ratio = (
            sum(1 for r in repos if (r.get("description") or "").strip()) / len(repos)
            if repos
            else None
        )

        account_age_years = None
        created_at = profile.get("created_at")
        if created_at:
            created_dt = dt.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=dt.timezone.utc
            )
            account_age_years = (dt.datetime.now(dt.timezone.utc) - created_dt).days / 365.25

        # Most-starred owned repos, as reviewer context.
        top_repos = [
            f"{r['name']} ({r.get('stargazers_count', 0)}★)"
            for r in sorted(
                repos, key=lambda r: r.get("stargazers_count", 0), reverse=True
            )[:5]
        ]

        return Candidate(
            name=profile.get("name") or login,
            bio=profile.get("bio"),
            company=profile.get("company"),
            top_repos=top_repos,
            source="github",
            profile_url=profile.get("html_url", f"https://github.com/{login}"),
            skills=skills,
            location=profile.get("location"),
            account_age_years=account_age_years,
            total_stars=total_stars,
            days_since_last_active=days_since_active,
            github_handle=login,
            recent_push_count=recent_push_count,
            prior_push_count=prior_push_count,
            docs_repo_ratio=docs_repo_ratio,
        )


def fetch_github_candidates(req: Req, token: str | None, max_results: int = 15) -> list[Candidate]:
    source = GitHubSource(token=token)
    logins = source.discover(req, max_results=max_results)
    candidates = []
    for login in logins:
        candidate = source.fetch_candidate(login)
        if candidate:
            candidates.append(candidate)
    return candidates
