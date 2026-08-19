"""Compare a traditional-pass output CSV against an experimental-pass one.

    python -m sourcing.compare_passes \\
      --traditional-csv out/backend-engineer-candidates.csv \\
      --experimental-csv out/backend-engineer-candidates-experimental.csv \\
      --out out/backend-engineer-comparison.csv

Matches candidates by (name, source) across both files, and reports how
much each candidate's rank moved between the traditional single-score
ranking and the experimental Foundation-axis ranking — plus which
candidates flipped `qualified` status between the two passes. Rank moves
and qualified flips are exactly where the two models disagree, which is
the interesting part to review by hand.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def _load_ranked(path: str) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for i, row in enumerate(rows, start=1):
        row["_rank"] = i
    return rows


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traditional-csv", required=True)
    parser.add_argument("--experimental-csv", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    traditional = _load_ranked(args.traditional_csv)
    experimental = _load_ranked(args.experimental_csv)

    trad_by_key = {(r["name"], r["source"]): r for r in traditional}
    exp_by_key = {(r["name"], r["source"]): r for r in experimental}
    all_keys = set(trad_by_key) | set(exp_by_key)

    comparison_rows = []
    for name, source in all_keys:
        t = trad_by_key.get((name, source))
        e = exp_by_key.get((name, source))
        rank_delta = int(t["_rank"]) - int(e["_rank"]) if t and e else None
        qualified_flip = (
            t["qualified"] != e["qualified"] if t and e else None
        )
        comparison_rows.append(
            {
                "name": name,
                "source": source,
                "traditional_rank": t["_rank"] if t else "",
                "traditional_score": t["score"] if t else "",
                "traditional_qualified": t["qualified"] if t else "",
                "experimental_rank": e["_rank"] if e else "",
                "experimental_foundation": e["foundation"] if e else "",
                "experimental_bonus": e["bonus"] if e else "",
                "experimental_momentum": e["momentum"] if e else "",
                "experimental_qualified": e["qualified"] if e else "",
                "rank_delta": rank_delta if rank_delta is not None else "",
                "qualified_flip": qualified_flip if qualified_flip is not None else "",
                "only_in": "" if (t and e) else ("traditional" if t else "experimental"),
            }
        )

    comparison_rows.sort(
        key=lambda r: abs(r["rank_delta"]) if isinstance(r["rank_delta"], int) else -1,
        reverse=True,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(comparison_rows[0].keys()))
        writer.writeheader()
        writer.writerows(comparison_rows)
    print(f"Wrote {len(comparison_rows)} comparison rows to {out_path}\n")

    movers = [r for r in comparison_rows if isinstance(r["rank_delta"], int) and r["rank_delta"] != 0]
    print(f"Biggest rank movers between traditional and experimental ({len(movers)} candidates moved):")
    header = f"{'name':<28} {'trad_rank':>10} {'exp_rank':>9} {'delta':>7}  why"
    print(header)
    print("-" * len(header))
    for r in movers[:10]:
        why = []
        if r["traditional_qualified"] in ("False", False) and r["experimental_qualified"] in ("True", True):
            why.append("now qualified (location/recency no longer penalized)")
        if float(r["experimental_momentum"] or 0) >= 20:
            why.append("high momentum score")
        if float(r["experimental_bonus"] or 0) >= 40:
            why.append("high bonus score")
        print(
            f"{r['name']:<28.28} {r['traditional_rank']:>10} {r['experimental_rank']:>9} "
            f"{r['rank_delta']:>7}  {', '.join(why)}"
        )

    flips = [r for r in comparison_rows if r["qualified_flip"] in ("True", True)]
    if flips:
        print(f"\n{len(flips)} candidates flipped `qualified` status between passes:")
        for r in flips:
            print(
                f"  {r['name']} ({r['source']}): traditional={r['traditional_qualified']} "
                f"-> experimental={r['experimental_qualified']}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
