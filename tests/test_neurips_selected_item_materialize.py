import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZE_SCRIPT = REPO_ROOT / "workflows/library/scripts/materialize_neurips_selected_item_inputs.py"


def _write_active_item(workspace: Path, item_id: str) -> str:
    plan_path = f"docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/{item_id}/execution_plan.md"
    item_path = f"docs/backlog/active/{item_id}.md"
    (workspace / plan_path).parent.mkdir(parents=True, exist_ok=True)
    (workspace / plan_path).write_text("# Existing plan\n", encoding="utf-8")
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
  - phase-3-cdi-anchor-regeneration
---

# Backlog Item: {item_id}

## Objective

- Do the selected work.
""",
        encoding="utf-8",
    )
    return item_path


def test_active_selection_rejects_pre_gate_manifest(tmp_path: Path) -> None:
    item_id = "2026-04-30-selected-item"
    item_path = _write_active_item(tmp_path, item_id)
    selection_path = tmp_path / "state/selector/selection.json"
    manifest_path = tmp_path / "state/iteration/manifest.json"
    output_path = tmp_path / "state/iteration/materialized.json"
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    selection_path.write_text(
        json.dumps(
            {
                "selection_status": "SELECTED",
                "selection_mode": "ACTIVE_SELECTION",
                "selected_item_id": item_id,
                "selected_item_path": item_path,
                "roadmap_sync_hint": "NO_CHANGE",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "backlog_root": "docs/backlog/active",
                "active_count": 1,
                "items": [
                    {
                        "item_id": item_id,
                        "title": item_id,
                        "path": item_path,
                        "plan_path": f"docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/{item_id}/execution_plan.md",
                        "check_commands": ["python -m compileall -q workflows"],
                        "summary": "pre-gate raw manifest row",
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
            str(MATERIALIZE_SCRIPT),
            "--selection-path",
            selection_path.relative_to(tmp_path).as_posix(),
            "--manifest-path",
            manifest_path.relative_to(tmp_path).as_posix(),
            "--state-root",
            "state/iteration",
            "--output",
            output_path.relative_to(tmp_path).as_posix(),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Active selection manifest must be roadmap-gated" in result.stderr


def test_active_selection_accepts_gated_eligible_manifest(tmp_path: Path) -> None:
    item_id = "2026-04-30-selected-item"
    item_path = _write_active_item(tmp_path, item_id)
    selection_path = tmp_path / "state/selector/selection.json"
    raw_manifest_path = tmp_path / "state/iteration/manifest.json"
    gated_manifest_path = tmp_path / "state/iteration/eligible_manifest.json"
    output_path = tmp_path / "state/iteration/materialized.json"
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    gated_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    selection_path.write_text(
        json.dumps(
            {
                "selection_status": "SELECTED",
                "selection_mode": "ACTIVE_SELECTION",
                "selected_item_id": item_id,
                "selected_item_path": item_path,
                "roadmap_sync_hint": "NO_CHANGE",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    gated_manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "backlog_root": "docs/backlog/active",
                "active_count": 1,
                "source_manifest_path": raw_manifest_path.relative_to(tmp_path).as_posix(),
                "roadmap_gate_status": "ELIGIBLE",
                "items": [
                    {
                        "item_id": item_id,
                        "title": item_id,
                        "path": item_path,
                        "plan_path": f"docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/{item_id}/execution_plan.md",
                        "check_commands": ["python -m compileall -q workflows"],
                        "summary": "gated eligible manifest row",
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
            str(MATERIALIZE_SCRIPT),
            "--selection-path",
            selection_path.relative_to(tmp_path).as_posix(),
            "--manifest-path",
            gated_manifest_path.relative_to(tmp_path).as_posix(),
            "--state-root",
            "state/iteration",
            "--output",
            output_path.relative_to(tmp_path).as_posix(),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stderr == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["item_id"] == item_id
    assert payload["selected_item_active_path"] == item_path
