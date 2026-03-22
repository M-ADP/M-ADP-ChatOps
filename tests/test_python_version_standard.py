from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_repo_declares_python_3_12_default() -> None:
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip().startswith("3.12")


def test_docs_declare_python_3_12_plus() -> None:
    docs = [
        ROOT / "docs/superpowers/plans/2026-03-21-langgraph-orchestrator-service.md",
        ROOT / "docs/superpowers/plans/2026-03-22-downstream-client-refactor.md",
        ROOT / "docs/superpowers/plans/2026-03-21-ai-registry-from-openapi.md",
    ]
    for doc in docs:
        assert "Python 3.12+" in doc.read_text(encoding="utf-8")
