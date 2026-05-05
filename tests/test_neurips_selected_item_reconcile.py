import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "workflows/library/scripts/reconcile_neurips_selected_item.py"
ITEM_NAME = "2026-05-04-example.md"


def _write_item(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "id: 2026-05-04-example\n"
        "plan_path: docs/plans/old-plan.md\n"
        "---\n"
        "# Example\n",
        encoding="utf-8",
    )


def _run_reconcile(tmp_path: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--active-path",
            f"docs/backlog/active/{ITEM_NAME}",
            "--in-progress-path",
            f"docs/backlog/in_progress/{ITEM_NAME}",
            "--plan-path",
            "docs/plans/example-plan.md",
            "--output-path",
            "state/reconciled.txt",
            *extra_args,
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )


def test_reconcile_recovers_premature_done_move_when_enabled(tmp_path: Path):
    done_path = tmp_path / "docs/backlog/done" / ITEM_NAME
    in_progress_path = tmp_path / "docs/backlog/in_progress" / ITEM_NAME
    _write_item(done_path)

    result = _run_reconcile(tmp_path, "--recover-premature-done")

    assert result.returncode == 0, result.stderr
    assert not done_path.exists()
    assert in_progress_path.is_file()
    assert "plan_path: docs/plans/example-plan.md" in in_progress_path.read_text(encoding="utf-8")
    assert (tmp_path / "state/reconciled.txt").read_text(encoding="utf-8").strip() == (
        f"docs/backlog/in_progress/{ITEM_NAME}"
    )


def test_reconcile_rejects_premature_done_move_by_default(tmp_path: Path):
    _write_item(tmp_path / "docs/backlog/done" / ITEM_NAME)

    result = _run_reconcile(tmp_path)

    assert result.returncode != 0
    assert "neither active nor in_progress" in result.stderr


def test_reconcile_rejects_duplicate_done_and_in_progress_state(tmp_path: Path):
    _write_item(tmp_path / "docs/backlog/done" / ITEM_NAME)
    _write_item(tmp_path / "docs/backlog/in_progress" / ITEM_NAME)

    result = _run_reconcile(tmp_path, "--recover-premature-done")

    assert result.returncode != 0
    assert "ambiguous queue state" in result.stderr
