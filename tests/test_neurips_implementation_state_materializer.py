import json
import subprocess
import sys
import time
from pathlib import Path


SCRIPT = Path("workflows/library/scripts/materialize_neurips_implementation_state.py")


def test_materializer_accepts_markdown_blocker_class_heading(tmp_path: Path) -> None:
    progress_report = tmp_path / "progress_report.md"
    execution_report = tmp_path / "execution_report.md"
    bundle = tmp_path / "implementation_state.json"
    phase_started = tmp_path / "phase_started_at_ns.txt"

    phase_started.write_text(str(time.time_ns()) + "\n", encoding="utf-8")
    time.sleep(0.001)
    progress_report.write_text(
        "\n".join(
            [
                "# Progress Report",
                "",
                "## Blocker",
                "",
                "Phase 2 is blocked by a roadmap contradiction.",
                "",
                "## Blocker Class",
                "",
                "`roadmap_conflict`",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bundle-path",
            str(bundle),
            "--execution-report-target",
            str(execution_report),
            "--progress-report-target",
            str(progress_report),
            "--phase-started-at-ns-path",
            str(phase_started),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(bundle.read_text(encoding="utf-8")) == {
        "implementation_state": "BLOCKED",
        "progress_report_path": str(progress_report),
        "blocker_class": "roadmap_conflict",
    }
