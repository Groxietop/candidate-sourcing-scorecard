from pathlib import Path

from sourcing.config import load_req

REQS_DIR = Path(__file__).parent.parent / "reqs"


def test_load_example_backend_req():
    req = load_req(REQS_DIR / "example-backend-engineer.yaml")
    assert req.req_id == "eng-backend-001"
    assert req.remote_ok is True
    assert req.qualify_threshold == 60
    skills = {rs.skill for rs in req.required_skills}
    assert "python" in skills
    assert "postgresql" in skills


def test_canonical_skill_resolves_aliases():
    req = load_req(REQS_DIR / "example-backend-engineer.yaml")
    assert req.canonical_skill("psql") == "postgresql"
    assert req.canonical_skill("k8s") == "kubernetes"
    assert req.canonical_skill("Python") == "python"  # passthrough, case-insensitive


def test_load_example_data_scientist_req():
    req = load_req(REQS_DIR / "example-data-scientist.yaml")
    assert req.req_id == "ds-004"
    assert req.qualify_threshold == 55
