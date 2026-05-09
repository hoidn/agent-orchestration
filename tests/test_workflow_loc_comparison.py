from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "workflows/library/scripts/compare_workflow_loc.py"


def _write_file(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _run_compare(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_compare_workflow_loc_reports_reduction(tmp_path: Path) -> None:
    old_file = _write_file(tmp_path / "old.yaml", "a\nb\nc\nd\n")
    new_file = _write_file(tmp_path / "new.yaml", "a\nb\n")

    result = _run_compare(
        "--old",
        str(old_file),
        "--new",
        str(new_file),
        "--require-total-reduction-pct",
        "1",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["totals"] == {
        "old_loc": 4,
        "new_loc": 2,
        "absolute_delta": 2,
        "percent_delta": 50.0,
    }
    assert payload["meets_threshold"] is True


def test_compare_workflow_loc_fails_when_total_regresses(tmp_path: Path) -> None:
    old_file = _write_file(tmp_path / "old.yaml", "a\nb\n")
    new_file = _write_file(tmp_path / "new.yaml", "a\nb\nc\nd\n")

    result = _run_compare(
        "--old",
        str(old_file),
        "--new",
        str(new_file),
        "--require-total-reduction-pct",
        "1",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["totals"] == {
        "old_loc": 2,
        "new_loc": 4,
        "absolute_delta": -2,
        "percent_delta": -100.0,
    }
    assert payload["meets_threshold"] is False


def test_compare_workflow_loc_groups_multiple_files(tmp_path: Path) -> None:
    old_a = _write_file(tmp_path / "old-a.yaml", "1\n2\n3\n")
    old_b = _write_file(tmp_path / "old-b.yaml", "1\n2\n")
    new_a = _write_file(tmp_path / "new-a.yaml", "1\n2\n")
    new_b = _write_file(tmp_path / "new-b.yaml", "1\n")

    result = _run_compare(
        "--old",
        str(old_a),
        "--old",
        str(old_b),
        "--new",
        str(new_a),
        "--new",
        str(new_b),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["totals"] == {
        "old_loc": 5,
        "new_loc": 3,
        "absolute_delta": 2,
        "percent_delta": 40.0,
    }
    assert payload["old_files"] == [str(old_a), str(old_b)]
    assert payload["new_files"] == [str(new_a), str(new_b)]
