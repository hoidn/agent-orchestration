from pathlib import Path


def test_monitor_docs_are_discoverable():
    assert "orchestrator monitor" in Path("specs/cli.md").read_text(encoding="utf-8")
    assert "workflow_monitoring.md" in Path("docs/index.md").read_text(encoding="utf-8")
    assert "COMPLETED" in Path("specs/observability.md").read_text(encoding="utf-8")
    assert "workflow_monitoring.md" in Path("README.md").read_text(encoding="utf-8")
