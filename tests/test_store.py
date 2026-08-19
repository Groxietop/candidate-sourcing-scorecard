from sourcing.store import diff_snapshots


def _candidate(name, score, qualified, url=None):
    return {
        "name": name,
        "source": "github",
        "profile_url": url or f"https://github.com/{name}",
        "score": score,
        "qualified": qualified,
        "matched_skills": [],
    }


def _snapshot(req_id, candidates: dict):
    return {"req_id": req_id, "generated_at": "2026-01-01T00:00:00+00:00", "candidates": candidates}


def test_first_run_has_no_previous_but_diff_still_reports_new_candidates():
    current = _snapshot("req-1", {"gh:alice": _candidate("Alice", 80, True)})
    diff = diff_snapshots(None, current)

    assert not diff.is_empty
    assert diff.new_candidates == [_candidate("Alice", 80, True)]
    assert diff.newly_qualified == [_candidate("Alice", 80, True)]


def test_no_changes_between_identical_snapshots_is_empty():
    snap = _snapshot("req-1", {"gh:alice": _candidate("Alice", 80, True)})
    diff = diff_snapshots(snap, snap)

    assert diff.is_empty
    assert diff.summary_markdown().startswith("No changes")


def test_qualified_flip_in_both_directions():
    previous = _snapshot(
        "req-1",
        {
            "gh:alice": _candidate("Alice", 55, False),
            "gh:bob": _candidate("Bob", 90, True),
        },
    )
    current = _snapshot(
        "req-1",
        {
            "gh:alice": _candidate("Alice", 65, True),
            "gh:bob": _candidate("Bob", 40, False),
        },
    )

    diff = diff_snapshots(previous, current)

    assert [c["name"] for c in diff.newly_qualified] == ["Alice"]
    assert [c["name"] for c in diff.no_longer_qualified] == ["Bob"]


def test_score_mover_only_flagged_above_threshold():
    previous = _snapshot("req-1", {"gh:alice": _candidate("Alice", 50, False)})
    current = _snapshot("req-1", {"gh:alice": _candidate("Alice", 53, False)})

    diff = diff_snapshots(previous, current, score_delta_threshold=5.0)
    assert diff.movers == []
    assert diff.is_empty

    diff = diff_snapshots(previous, current, score_delta_threshold=2.0)
    assert len(diff.movers) == 1
    assert diff.movers[0]["delta"] == 3.0


def test_dropped_candidate_no_longer_in_current():
    previous = _snapshot("req-1", {"gh:alice": _candidate("Alice", 80, True)})
    current = _snapshot("req-1", {})

    diff = diff_snapshots(previous, current)
    assert [c["name"] for c in diff.dropped_candidates] == ["Alice"]
    assert not diff.is_empty


def test_summary_markdown_includes_all_sections_for_a_busy_diff():
    previous = _snapshot(
        "req-1",
        {
            "gh:bob": _candidate("Bob", 90, True),
            "gh:carol": _candidate("Carol", 50, False),
        },
    )
    current = _snapshot(
        "req-1",
        {
            "gh:alice": _candidate("Alice", 70, True),
            "gh:carol": _candidate("Carol", 65, True),
        },
    )

    diff = diff_snapshots(previous, current)
    md = diff.summary_markdown()

    assert "New candidates" in md
    assert "Newly qualified" in md
    assert "Dropped from results" in md
    assert "Alice" in md and "Bob" in md and "Carol" in md
