"""Push a scored pool into Ashby.

    python -m sourcing.cli_push --req reqs/example-backend-engineer.yaml \
        --job-id <ashby-job-id> --dry-run

`--dry-run` is the default and needs no credentials: it prints every request
that would be sent, in full, so the integration can be reviewed without a
tenant behind it. Sending for real requires `--send` and `ASHBY_API_KEY`.

Nothing here rejects a candidate. Set-aside candidates are pushed too --
tagged and annotated -- because a rejection written into the system of
record is where an automated call stops being reversible.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import load_req
from .integrations.ashby import (
    HttpTransport,
    RecordingTransport,
    push_pool,
)
from .pipeline import gather_and_score


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--req", required=True, help="Path to a req YAML file")
    parser.add_argument(
        "--job-id",
        default="ashby-job-id-placeholder",
        help="Ashby job id to attach advanced candidates to",
    )
    parser.add_argument("--linkedin-csv", default=None)
    parser.add_argument("--skip-github", action="store_true")
    parser.add_argument("--max-github-results", type=int, default=15)
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually call Ashby. Requires ASHBY_API_KEY. Off by default.",
    )
    parser.add_argument(
        "--show-payloads",
        action="store_true",
        help="Print the full JSON body of every request that would be sent.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    req = load_req(args.req)

    results = gather_and_score(
        req,
        linkedin_csv=args.linkedin_csv,
        skip_github=args.skip_github,
        max_github_results=args.max_github_results,
        github_token=args.github_token,
    )
    if not results:
        print("No candidates to push.", file=sys.stderr)
        return 1

    if args.send:
        api_key = os.environ.get("ASHBY_API_KEY")
        if not api_key:
            raise SystemExit(
                "--send needs ASHBY_API_KEY in the environment. "
                "Drop the flag to dry-run instead."
            )
        transport = HttpTransport(api_key=api_key)
        print(f"Sending {len(results)} candidates to Ashby job {args.job_id}\n")
    else:
        transport = RecordingTransport()
        print(
            f"DRY RUN — nothing is sent. {len(results)} candidates would be "
            f"pushed to Ashby job {args.job_id}.\n"
        )

    pushed = push_pool(results, job_id=args.job_id, transport=transport)

    by_tier: dict[str, int] = {}
    for entry in pushed:
        by_tier[entry.tier] = by_tier.get(entry.tier, 0) + 1
    print("  " + " · ".join(f"{tier} {n}" for tier, n in sorted(by_tier.items())))

    failed = [p for p in pushed if not p.pushed]
    print(f"  {len(pushed) - len(failed)} pushed, {len(failed)} failed")
    for entry in failed:
        print(f"    ! {entry.candidate_name}: {entry.skipped_reason}")

    if isinstance(transport, RecordingTransport):
        counts: dict[str, int] = {}
        for path, _payload in transport.sent:
            counts[path] = counts.get(path, 0) + 1
        print("\n  Requests that would be sent:")
        for path, n in sorted(counts.items()):
            print(f"    {n:>4}x  POST /{path}")

        # No rejection endpoint appears here, and that is the point.
        print(
            "\n  Note: no candidate.reject / archive call appears above. "
            "This tool never rejects in the ATS."
        )

        if args.show_payloads:
            print("\n  Full payloads:")
            for path, payload in transport.sent:
                print(f"\n  POST /{path}")
                for line in json.dumps(payload, indent=2).splitlines():
                    print(f"    {line}")
        else:
            print("\n  Re-run with --show-payloads to see every request body.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
