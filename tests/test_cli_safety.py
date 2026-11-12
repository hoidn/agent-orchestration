"""Safety behavior of the public evaluated run command."""

from pathlib import Path

from orchestrator.cli.main import main
from tests.test_workflow_evaluated_cli import _build


def test_evaluated_run_does_not_apply_retired_processed_directory_flags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source, _program = _build(tmp_path)
    processed = tmp_path / "processed"
    processed.mkdir()
    marker = processed / "keep.txt"
    marker.write_text("preserve this file", encoding="utf-8")
    archive = tmp_path / "archive.zip"
    monkeypatch.chdir(tmp_path)

    exit_code = main([
        "run",
        str(source),
        "--input",
        "score=0.75",
        "--clean-processed",
        "--archive-processed",
        str(archive),
    ])

    assert exit_code == 0
    assert marker.read_text(encoding="utf-8") == "preserve this file"
    assert not archive.exists()
