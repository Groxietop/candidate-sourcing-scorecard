from pathlib import Path

from sourcing.linkedin_source import load_linkedin_candidates

DATA_PATH = Path(__file__).parent.parent / "data" / "fake_linkedin_candidates.csv"


def test_loads_demo_csv():
    candidates = load_linkedin_candidates(DATA_PATH)
    assert len(candidates) == 20
    alex = next(c for c in candidates if c.name == "Alex Rivera")
    assert "python" in alex.skills
    assert alex.years_experience == 7
    assert alex.currently_open_to_work is True
    assert alex.github_handle == "alexrivera-dev"


def test_handles_blank_optional_fields():
    candidates = load_linkedin_candidates(DATA_PATH)
    sam = next(c for c in candidates if c.name == "Sam O'Brien")
    assert sam.github_handle is None
    assert sam.currently_open_to_work is False
