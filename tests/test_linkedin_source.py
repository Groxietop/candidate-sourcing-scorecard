from pathlib import Path

from sourcing.linkedin_source import load_linkedin_candidates

DATA_PATH = Path(__file__).parent.parent / "data" / "fake_linkedin_candidates.csv"


def test_loads_demo_csv():
    candidates = load_linkedin_candidates(DATA_PATH)
    assert len(candidates) == 26
    alex = next(c for c in candidates if c.name == "Alex Rivera")
    assert "python" in alex.skills
    assert alex.years_experience == 7
    assert alex.currently_open_to_work is True
    assert alex.github_handle == "alexrivera-dev"
    assert alex.current_title == "Senior Backend Engineer"
    assert alex.certifications == "AWS Certified Solutions Architect"
    assert alex.open_source_contributor is True
    assert alex.education_level == "BS"


def test_handles_blank_optional_fields():
    candidates = load_linkedin_candidates(DATA_PATH)
    sam = next(c for c in candidates if c.name == "Sam O'Brien")
    assert sam.github_handle is None
    assert sam.currently_open_to_work is False
    jordan = next(c for c in candidates if c.name == "Jordan Kim")
    assert jordan.certifications is None
    assert jordan.open_source_contributor is False
    assert jordan.volunteer_experience is False


def test_demo_csv_includes_sparse_profiles():
    """Real recruiter exports have gaps, and the fixture has to as well.

    A fixture where every scored field is populated cannot exercise the
    CAVEATED tier at all, which is the behaviour this tool exists for.
    """
    candidates = load_linkedin_candidates(DATA_PATH)
    assert any(c.years_experience is None for c in candidates)
    assert any(not c.location for c in candidates)
