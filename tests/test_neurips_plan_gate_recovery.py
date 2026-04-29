import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RECOVERY_SCRIPT = REPO_ROOT / "workflows/library/scripts/recover_neurips_plan_gate_outputs.py"


def _write_item(workspace: Path, item_path: str, *, plan_path: str) -> None:
    target = workspace / item_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"""---
priority: 10
plan_path: {plan_path}
check_commands:
  - python -m compileall -q workflows
prerequisites: []
related_roadmap_phases:
  - phase-2-pdebench
---

# Backlog Item
""",
        encoding="utf-8",
    )


def _run_recovery(
    workspace: Path,
    *,
    selection_mode: str,
    item_path: str,
) -> dict:
    output = workspace / "state/item/plan-gate-recovery.json"
    report = workspace / "artifacts/review/NEURIPS-HYBRID-RESNET-2026/backlog/item-plan-recovery.md"
    result = subprocess.run(
        [
            sys.executable,
            str(RECOVERY_SCRIPT),
            "--selection-mode",
            selection_mode,
            "--selected-item-path",
            item_path,
            "--recovery-report-target-path",
            report.relative_to(workspace).as_posix(),
            "--output",
            output.relative_to(workspace).as_posix(),
        ],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stderr == ""
    return json.loads(output.read_text(encoding="utf-8"))


def test_recovers_approved_plan_gate_from_in_progress_item_frontmatter(tmp_path: Path) -> None:
    plan_path = "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/item/execution_plan.md"
    (tmp_path / plan_path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / plan_path).write_text("# Execution plan\n", encoding="utf-8")
    _write_item(tmp_path, "docs/backlog/in_progress/item.md", plan_path=plan_path)

    payload = _run_recovery(
        tmp_path,
        selection_mode="RECOVERED_IN_PROGRESS",
        item_path="docs/backlog/in_progress/item.md",
    )

    assert payload["plan_gate_status"] == "RECOVERED"
    assert payload["plan_path"] == plan_path
    assert payload["plan_review_decision"] == "APPROVE"
    assert payload["plan_review_report_path"] == (
        "artifacts/review/NEURIPS-HYBRID-RESNET-2026/backlog/item-plan-recovery.md"
    )
    assert (tmp_path / payload["plan_review_report_path"]).is_file()


def test_active_selection_does_not_recover_existing_plan_path(tmp_path: Path) -> None:
    plan_path = "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/item/execution_plan.md"
    (tmp_path / plan_path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / plan_path).write_text("# Execution plan\n", encoding="utf-8")
    _write_item(tmp_path, "docs/backlog/active/item.md", plan_path=plan_path)

    payload = _run_recovery(
        tmp_path,
        selection_mode="ACTIVE_SELECTION",
        item_path="docs/backlog/active/item.md",
    )

    assert payload == {"plan_gate_status": "MISSING"}


def test_recovered_item_with_missing_or_unsafe_plan_path_falls_back_to_fresh_plan(tmp_path: Path) -> None:
    cases = [
        "",
        "docs/other/item-plan.md",
        "../outside.md",
        "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/item/missing.md",
    ]

    for index, plan_path in enumerate(cases):
        item_path = f"docs/backlog/in_progress/item-{index}.md"
        _write_item(tmp_path, item_path, plan_path=plan_path)

        payload = _run_recovery(
            tmp_path,
            selection_mode="RECOVERED_IN_PROGRESS",
            item_path=item_path,
        )

        assert payload == {"plan_gate_status": "MISSING"}
