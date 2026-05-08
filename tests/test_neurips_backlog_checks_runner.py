import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "workflows/library/scripts/run_neurips_backlog_checks.py"


def _run(
    tmp_path: Path,
    checks: list[str],
    report_name: str = "report.json",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    checks_path = tmp_path / "state/checks.json"
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    checks_path.write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    report_path = tmp_path / f"artifacts/checks/{report_name}"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--checks-path",
            str(checks_path),
            "--report-path",
            str(report_path),
            "--cwd",
            str(tmp_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, report_path


def test_run_neurips_backlog_checks_reports_failures_without_process_failure(
    tmp_path: Path,
) -> None:
    result, report_path = _run(
        tmp_path,
        [
            f'{sys.executable} -c "print(\'ok\')"',
            f'{sys.executable} -c "import sys; sys.exit(3)"',
        ],
    )

    assert result.returncode == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "FAIL"
    assert report["failed_count"] == 1
    assert report["command_count"] == 2
    assert report["results"][1]["exit_code"] == 3


def test_run_neurips_backlog_checks_preserves_existing_matching_log_paths(
    tmp_path: Path,
) -> None:
    command = f'{sys.executable} -c "print(\'ok\')"'
    checks_path = tmp_path / "state/checks.json"
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    checks_path.write_text(json.dumps([command], indent=2) + "\n", encoding="utf-8")

    archived_log = tmp_path / "artifacts/work/checks/ok.log"
    archived_log.parent.mkdir(parents=True, exist_ok=True)
    archived_log.write_text("archived ok\n", encoding="utf-8")

    report_path = tmp_path / "artifacts/checks/report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "failed_count": 0,
                "command_count": 1,
                "checks_path": checks_path.as_posix(),
                "results": [
                    {
                        "index": 1,
                        "command": command,
                        "exit_code": 0,
                        "log_path": archived_log.relative_to(tmp_path).as_posix(),
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--checks-path",
            str(checks_path),
            "--report-path",
            str(report_path),
            "--cwd",
            str(tmp_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["results"][0]["command"] == command
    assert report["results"][0]["log_path"] == archived_log.relative_to(tmp_path).as_posix()
