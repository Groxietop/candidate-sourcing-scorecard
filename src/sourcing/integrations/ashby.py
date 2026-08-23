"""Pushing a scored pool into Ashby, the ATS of record.

Built against Ashby's real API — RPC-style paths (`candidate.create`,
`candidate.createNote`, `application.create`), everything POST with a JSON
body, Basic auth with the API key as the username and an empty password.
With a real key this code runs; without one it refuses to invent a response.

Not wired to a live workspace here: there is no Ashby tenant behind this
repo, so the tests drive it through a recording transport instead. Every
request it would send is inspectable via `--dry-run`, which is the honest
version of a demo — you can read the exact payload without anyone
pretending an API call happened.

The rule this integration exists to protect
-------------------------------------------
**It never rejects anyone in the ATS.** Not the discard tier, not the low
scores, nobody. Pushing a rejection into the system of record is the moment
an automated judgement becomes irreversible — the candidate stops appearing
in searches, and no recruiter ever sees the caveat that said we might be
wrong.

So set-aside candidates are pushed too, tagged and annotated with the
reasoning, and left in the pipeline for a human. The tool's opinion travels
with the candidate; the decision does not.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

API_ROOT = "https://api.ashbyhq.com"

# Only what this integration actually uses.
JOB_LIST = "job.list"
CANDIDATE_CREATE = "candidate.create"
CANDIDATE_NOTE = "candidate.createNote"
CANDIDATE_TAG = "candidate.addTag"
APPLICATION_CREATE = "application.create"

# Tags written onto the candidate so a recruiter can filter by our verdict
# inside Ashby without trusting it.
TIER_TAGS = {
    "strong": "scorecard:strong",
    "review": "scorecard:review",
    "caveated": "scorecard:caveated-do-not-cut",
    "discard": "scorecard:set-aside",
}


class Transport(Protocol):
    """Anything that can carry a request. Lets tests run the real code path."""

    def post(self, path: str, payload: dict) -> dict: ...


class HttpTransport:
    """The real thing. Requires a key; will not fabricate a response."""

    def __init__(self, api_key: str, timeout: float = 15.0):
        if not api_key:
            raise ValueError("an Ashby API key is required for HttpTransport")
        self.timeout = timeout
        token = base64.b64encode(f"{api_key}:".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{API_ROOT}/{path}",
            data=json.dumps(payload).encode(),
            headers=self._headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode())


@dataclass
class RecordingTransport:
    """Records what would be sent and returns canned successes.

    Used by `--dry-run` and by the tests. It deliberately does not resemble
    a real Ashby response beyond the `success`/`results` envelope -- the
    point is to show the request, not to simulate the service.
    """

    sent: list[tuple[str, dict]] = field(default_factory=list)
    next_id: int = 1

    def post(self, path: str, payload: dict) -> dict:
        self.sent.append((path, payload))
        identifier = f"dry-run-{self.next_id:04d}"
        self.next_id += 1
        return {"success": True, "results": {"id": identifier}}

    def calls_to(self, path: str) -> list[dict]:
        return [payload for sent_path, payload in self.sent if sent_path == path]


@dataclass
class PushResult:
    candidate_name: str
    tier: str
    ashby_candidate_id: str | None
    pushed: bool
    tagged: str | None = None
    note_written: bool = False
    skipped_reason: str = ""


def _note_body(result) -> str:
    """The reasoning, formatted for a recruiter reading it inside Ashby.

    The caveat is not an afterthought here -- for a set-aside candidate it
    is the most important line in the note, because it is the only thing
    standing between them and being forgotten.
    """
    decision = result.triage
    lines = [
        f"Sourcing scorecard — {decision.tier.value.upper()}",
        f"Score {getattr(result, 'total', 0):.0f} · "
        f"{decision.confidence:.0%} of it backed by measured signals",
        "",
        f"Why: {decision.reason}",
    ]
    if decision.caveat:
        lines += ["", f"But: {decision.caveat}"]
    if decision.missing_must_haves:
        lines.append(f"Missing must-have: {', '.join(decision.missing_must_haves)}")
    if decision.imputed_categories:
        lines.append(
            f"Scored on guesswork: {', '.join(decision.imputed_categories)}"
        )
    if result.matched_skills:
        lines.append(f"Matched: {', '.join(result.matched_skills)}")
    lines += [
        "",
        "This tool does not reject candidates. A set-aside verdict is a "
        "suggestion to look later, not a decision — overrule it freely.",
    ]
    return "\n".join(lines)


def _candidate_payload(result) -> dict:
    candidate = result.candidate
    payload = {"name": candidate.name}
    # Ashby accepts these optionally; only send what we actually have rather
    # than padding the request with empty strings.
    if candidate.profile_url:
        payload["websiteUrls"] = [candidate.profile_url]
    if candidate.location:
        payload["location"] = {"city": candidate.location}
    if candidate.github_handle:
        payload["sourceTitle"] = f"GitHub: {candidate.github_handle}"
    return payload


class AshbyClient:
    """Thin client over the handful of Ashby endpoints this needs."""

    def __init__(self, transport: Transport):
        self.transport = transport

    def list_jobs(self) -> list[dict]:
        response = self.transport.post(JOB_LIST, {})
        return response.get("results", []) if response.get("success") else []

    def create_candidate(self, result) -> str | None:
        response = self.transport.post(CANDIDATE_CREATE, _candidate_payload(result))
        if not response.get("success"):
            return None
        return (response.get("results") or {}).get("id")

    def add_tag(self, candidate_id: str, tag: str) -> bool:
        response = self.transport.post(
            CANDIDATE_TAG, {"candidateId": candidate_id, "tagName": tag}
        )
        return bool(response.get("success"))

    def add_note(self, candidate_id: str, note: str) -> bool:
        response = self.transport.post(
            CANDIDATE_NOTE,
            {"candidateId": candidate_id, "note": {"type": "text/plain", "value": note}},
        )
        return bool(response.get("success"))

    def create_application(self, candidate_id: str, job_id: str) -> bool:
        response = self.transport.post(
            APPLICATION_CREATE, {"candidateId": candidate_id, "jobId": job_id}
        )
        return bool(response.get("success"))


def push_pool(
    results,
    job_id: str,
    transport: Transport,
    apply_tiers=("strong", "review"),
) -> list[PushResult]:
    """Push a scored pool into Ashby.

    Everyone is created and annotated. `apply_tiers` controls only who is
    additionally attached to the job as an *application* -- an active
    consideration. Caveated and set-aside candidates still land in the ATS,
    tagged and with their reasoning, so a recruiter can find them later;
    they are simply not queued as active applicants.

    Nobody is ever rejected. There is no code path here that does that, and
    that is deliberate.
    """
    client = AshbyClient(transport)
    pushed: list[PushResult] = []

    for result in results:
        decision = getattr(result, "triage", None)
        if decision is None:
            pushed.append(
                PushResult(
                    candidate_name=result.candidate.name,
                    tier="unknown",
                    ashby_candidate_id=None,
                    pushed=False,
                    skipped_reason="candidate was never triaged",
                )
            )
            continue

        tier = decision.tier.value
        candidate_id = client.create_candidate(result)
        if candidate_id is None:
            pushed.append(
                PushResult(
                    candidate_name=result.candidate.name,
                    tier=tier,
                    ashby_candidate_id=None,
                    pushed=False,
                    skipped_reason="candidate.create did not return an id",
                )
            )
            continue

        tag = TIER_TAGS.get(tier)
        tagged = client.add_tag(candidate_id, tag) if tag else False
        noted = client.add_note(candidate_id, _note_body(result))

        if tier in apply_tiers:
            client.create_application(candidate_id, job_id)

        pushed.append(
            PushResult(
                candidate_name=result.candidate.name,
                tier=tier,
                ashby_candidate_id=candidate_id,
                pushed=True,
                tagged=tag if tagged else None,
                note_written=noted,
            )
        )

    return pushed
