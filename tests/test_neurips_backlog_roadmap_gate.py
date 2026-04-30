import json
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = REPO_ROOT / "workflows/library/scripts/build_neurips_backlog_manifest.py"
RECONCILE_SCRIPT = REPO_ROOT / "workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py"
STEERED_DRAIN_WORKFLOW = REPO_ROOT / "workflows/examples/neurips_steered_backlog_drain.yaml"


def _write_backlog_item(
    workspace: Path,
    item_id: str,
    *,
    priority: int,
    prerequisites: list[str],
    phase: str = "phase-3-cdi-anchor-regeneration",
) -> None:
    plan_path = workspace / f"docs/plans/NEURIPS-HYBRID-RESNET-2026/{item_id}.md"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(f"# Plan for {item_id}\n", encoding="utf-8")

    prereq_lines = "".join(f"  - {prereq}\n" for prereq in prerequisites)
    item_path = workspace / f"docs/backlog/active/{item_id}.md"
    item_path.parent.mkdir(parents=True, exist_ok=True)
    item_path.write_text(
        f"""---
priority: {priority}
plan_path: {plan_path.relative_to(workspace).as_posix()}
check_commands:
  - python -m compileall -q workflows
prerequisites:
{prereq_lines}related_roadmap_phases:
  - {phase}
---

# Backlog Item: {item_id}

## Objective

- Do the work for {item_id}.
""",
        encoding="utf-8",
    )


def test_roadmap_gate_refreshes_stale_manifest_before_prerequisite_routing(tmp_path: Path) -> None:
    prerequisite_id = "2026-04-29-cdi-lines128-minimum-paper-table"
    dependent_id = "2026-04-29-cdi-lines128-paper-benchmark-execution"
    _write_backlog_item(tmp_path, prerequisite_id, priority=21, prerequisites=[])
    _write_backlog_item(tmp_path, dependent_id, priority=20, prerequisites=[prerequisite_id])

    stale_manifest = {
        "manifest_version": 1,
        "backlog_root": "docs/backlog/active",
        "active_count": 1,
        "items": [
            {
                "item_id": dependent_id,
                "title": f"Backlog Item: {dependent_id}",
                "path": f"docs/backlog/active/{dependent_id}.md",
                "status": "active",
                "priority": 20,
                "plan_path": f"docs/plans/NEURIPS-HYBRID-RESNET-2026/{dependent_id}.md",
                "check_commands": ["python -m compileall -q workflows"],
                "summary": "stale manifest row without the new prerequisite",
                "prerequisites": [],
                "related_roadmap_phases": ["phase-3-cdi-anchor-regeneration"],
                "blocking_signals": [],
                "signals_for_selection": [],
            }
        ],
    }
    manifest_path = tmp_path / "state/backlog/manifest.json"
    policy_path = tmp_path / "state/backlog/gate-policy.json"
    progress_path = tmp_path / "state/backlog/progress.json"
    run_state_path = tmp_path / "state/backlog/run-state.json"
    output_path = tmp_path / "state/backlog/roadmap-gate.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(stale_manifest, indent=2) + "\n", encoding="utf-8")
    policy_path.write_text(
        json.dumps(
            {
                "allowed_roadmap_phase_prefixes": ["phase-3"],
                "disallowed_roadmap_phase_prefixes": ["phase-4"],
                "gap_policy": "draft_backlog_item",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    progress_path.write_text('{"completed_items": []}\n', encoding="utf-8")
    run_state_path.write_text('{"completed_items": [], "blocked_items": {}}\n', encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(RECONCILE_SCRIPT),
            "--manifest-path",
            manifest_path.relative_to(tmp_path).as_posix(),
            "--gate-policy-path",
            policy_path.relative_to(tmp_path).as_posix(),
            "--progress-ledger-path",
            progress_path.relative_to(tmp_path).as_posix(),
            "--run-state-path",
            run_state_path.relative_to(tmp_path).as_posix(),
            "--output",
            output_path.relative_to(tmp_path).as_posix(),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stderr == ""

    gate = json.loads(output_path.read_text(encoding="utf-8"))
    eligible_ids = {item["item_id"] for item in gate["eligible_items"]}
    ineligible_by_id = {item["item_id"]: item for item in gate["ineligible_items"]}

    assert gate["gate_status"] == "ELIGIBLE"
    assert prerequisite_id in eligible_ids
    assert dependent_id not in eligible_ids
    assert "missing prerequisites: " + prerequisite_id in ineligible_by_id[dependent_id]["ineligibility_reasons"]


def test_steered_drain_selected_item_uses_selector_eligible_manifest() -> None:
    workflow = yaml.safe_load(STEERED_DRAIN_WORKFLOW.read_text(encoding="utf-8"))
    drain_step = next(step for step in workflow["steps"] if step["name"] == "DrainBacklogItems")
    iteration_steps = drain_step["repeat_until"]["steps"]

    select_step = next(step for step in iteration_steps if step["name"] == "SelectNextItem")
    route_step = next(step for step in iteration_steps if step["name"] == "RouteItemSelection")
    selected_case_steps = route_step["match"]["cases"]["SELECTED"]["steps"]
    run_selected_step = next(step for step in selected_case_steps if step["name"] == "RunSelectedItem")

    expected_ref = "self.steps.ReconcileBacklogRoadmapGate.artifacts.eligible_manifest_path"
    assert select_step["with"]["manifest_path"] == {"ref": expected_ref}
    assert run_selected_step["with"]["manifest_path"] == {
        "ref": expected_ref.replace("self.steps", "parent.steps", 1)
    }


def test_manifest_builder_accepts_block_scalar_check_commands(tmp_path: Path) -> None:
    plan_path = tmp_path / "docs/plans/NEURIPS-HYBRID-RESNET-2026/block-command.md"
    item_path = tmp_path / "docs/backlog/active/2026-04-29-block-command-item.md"
    output_path = tmp_path / "state/backlog/manifest.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    item_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("# Plan\n", encoding="utf-8")
    item_path.write_text(
        f"""---
priority: 10
plan_path: {plan_path.relative_to(tmp_path).as_posix()}
check_commands:
  - python -m compileall -q scripts
  - |
    python - <<'PY'
    print("hello")
    PY
prerequisites: []
related_roadmap_phases:
  - phase-3-cdi-anchor-regeneration
---

# Backlog Item: Block Command

## Objective

- Validate block commands.
""",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--backlog-root",
            "docs/backlog/active",
            "--output",
            output_path.relative_to(tmp_path).as_posix(),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )

    manifest = json.loads(output_path.read_text(encoding="utf-8"))
    commands = manifest["items"][0]["check_commands"]
    assert commands[0] == "python -m compileall -q scripts"
    assert "print(\"hello\")" in commands[1]
