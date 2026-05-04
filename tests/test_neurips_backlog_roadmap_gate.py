import json
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = REPO_ROOT / "workflows/library/scripts/build_neurips_backlog_manifest.py"
RECONCILE_SCRIPT = REPO_ROOT / "workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py"
VALIDATE_GAP_DRAFT_SCRIPT = REPO_ROOT / "workflows/library/scripts/validate_neurips_backlog_gap_draft.py"
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


def _write_missing_plan_item(
    workspace: Path,
    item_id: str,
    *,
    priority: int,
    phase: str = "phase-2-pdebench-128x128-image-suite",
) -> None:
    item_path = workspace / f"docs/backlog/active/{item_id}.md"
    item_path.parent.mkdir(parents=True, exist_ok=True)
    item_path.write_text(
        f"""---
priority: {priority}
plan_path: docs/plans/NEURIPS-HYBRID-RESNET-2026/{item_id}-missing.md
check_commands:
  - python -m compileall -q workflows
prerequisites: []
related_roadmap_phases:
  - {phase}
---

# Backlog Item: {item_id}

## Objective

- This item is intentionally invalid.
""",
        encoding="utf-8",
    )


def _write_gate_inputs(
    workspace: Path,
    *,
    allowed: list[str] | None = None,
    disallowed: list[str] | None = None,
) -> tuple[Path, Path, Path]:
    policy_path = workspace / "state/backlog/gate-policy.json"
    progress_path = workspace / "state/backlog/progress.json"
    run_state_path = workspace / "state/backlog/run-state.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(
            {
                "allowed_roadmap_phase_prefixes": allowed or ["phase-2"],
                "disallowed_roadmap_phase_prefixes": disallowed or ["phase-4"],
                "gap_policy": "draft_backlog_item",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    progress_path.write_text('{"completed_items": []}\n', encoding="utf-8")
    run_state_path.write_text('{"completed_items": [], "blocked_items": {}}\n', encoding="utf-8")
    return policy_path, progress_path, run_state_path


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


def test_manifest_builder_records_missing_plan_target_as_invalid_item(tmp_path: Path) -> None:
    _write_backlog_item(
        tmp_path,
        "2026-05-04-valid-phase2",
        priority=10,
        prerequisites=[],
        phase="phase-2-pdebench-128x128-image-suite",
    )
    _write_missing_plan_item(tmp_path, "2026-05-04-missing-plan", priority=11)

    output_path = tmp_path / "state/backlog/manifest.json"
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
    assert {item["item_id"] for item in manifest["items"]} == {"2026-05-04-valid-phase2"}
    invalid = {item["item_id"]: item for item in manifest["invalid_items"]}
    assert "2026-05-04-missing-plan" in invalid
    assert any(
        "plan_path target does not exist" in reason
        for reason in invalid["2026-05-04-missing-plan"]["invalid_reasons"]
    )


def test_roadmap_gate_continues_with_valid_eligible_item_when_another_item_has_missing_plan(
    tmp_path: Path,
) -> None:
    _write_backlog_item(
        tmp_path,
        "2026-05-04-valid-phase2",
        priority=10,
        prerequisites=[],
        phase="phase-2-pdebench-128x128-image-suite",
    )
    _write_missing_plan_item(tmp_path, "2026-05-04-missing-plan", priority=11)

    manifest_path = tmp_path / "state/backlog/manifest.json"
    output_path = tmp_path / "state/backlog/roadmap-gate.json"
    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--backlog-root",
            "docs/backlog/active",
            "--output",
            manifest_path.relative_to(tmp_path).as_posix(),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    policy_path, progress_path, run_state_path = _write_gate_inputs(tmp_path)

    subprocess.run(
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

    gate = json.loads(output_path.read_text(encoding="utf-8"))
    assert gate["gate_status"] == "ELIGIBLE"
    assert {item["item_id"] for item in gate["eligible_items"]} == {"2026-05-04-valid-phase2"}
    assert gate["invalid_count"] == 1
    assert gate["invalid_items"][0]["item_id"] == "2026-05-04-missing-plan"


def test_roadmap_gate_blocks_when_only_current_phase_item_is_invalid(tmp_path: Path) -> None:
    _write_missing_plan_item(tmp_path, "2026-05-04-missing-plan", priority=11)

    manifest_path = tmp_path / "state/backlog/manifest.json"
    output_path = tmp_path / "state/backlog/roadmap-gate.json"
    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--backlog-root",
            "docs/backlog/active",
            "--output",
            manifest_path.relative_to(tmp_path).as_posix(),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    policy_path, progress_path, run_state_path = _write_gate_inputs(tmp_path)

    subprocess.run(
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

    gate = json.loads(output_path.read_text(encoding="utf-8"))
    assert gate["gate_status"] == "BLOCKED"
    assert gate["eligible_items"] == []
    assert gate["invalid_count"] == 1


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


def test_gap_draft_validator_accepts_block_scalar_check_commands(tmp_path: Path) -> None:
    gap_request = tmp_path / "state/gap_request.json"
    draft_bundle = tmp_path / "state/draft_bundle.json"
    policy_path = tmp_path / "docs/backlog/roadmap_gate.json"
    plan_path = tmp_path / "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog-gaps/2026-05-04-phase2.md"
    item_path = tmp_path / "docs/backlog/active/2026-05-04-phase2-gap.md"
    output_path = tmp_path / "state/draft_validation.json"
    gap_request.parent.mkdir(parents=True, exist_ok=True)
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    item_path.parent.mkdir(parents=True, exist_ok=True)

    gap_request.write_text(
        json.dumps(
            {
                "allowed_roadmap_phase_prefixes": ["phase-2-pdebench-"],
                "disallowed_roadmap_phase_prefixes": ["phase-3-"],
                "gap_item_target_dir": "docs/backlog/active",
                "gap_plan_target_root": "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog-gaps",
                "roadmap_path": "docs/plans/2026-04-20-neurips-hybrid-resnet-submission-roadmap.md",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "allowed_roadmap_phase_prefixes": ["phase-2-pdebench-"],
                "disallowed_roadmap_phase_prefixes": ["phase-3-"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    plan_path.write_text("# Phase 2 Plan\n", encoding="utf-8")
    item_path.write_text(
        f"""---
priority: 5
plan_path: {plan_path.relative_to(tmp_path).as_posix()}
check_commands:
  - |
    python - <<'PY'
    print("valid block command")
    PY
related_roadmap_phases:
  - phase-2-pdebench-full-training-evidence
---

# Backlog Item: Phase 2 Gap

## Objective

- Close the missing Phase 2 evidence gap.
""",
        encoding="utf-8",
    )
    draft_bundle.write_text(
        json.dumps(
            {
                "draft_status": "DRAFTED",
                "backlog_item_path": item_path.relative_to(tmp_path).as_posix(),
                "seed_plan_path": plan_path.relative_to(tmp_path).as_posix(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(VALIDATE_GAP_DRAFT_SCRIPT),
            "--gap-request-path",
            gap_request.relative_to(tmp_path).as_posix(),
            "--draft-bundle-path",
            draft_bundle.relative_to(tmp_path).as_posix(),
            "--gate-policy-path",
            policy_path.relative_to(tmp_path).as_posix(),
            "--output",
            output_path.relative_to(tmp_path).as_posix(),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["draft_validation_status"] == "VALID"
    assert payload["backlog_item_path"] == "docs/backlog/active/2026-05-04-phase2-gap.md"


def test_gap_draft_validator_writes_invalid_diagnostic_on_rejection(tmp_path: Path) -> None:
    gap_request = tmp_path / "state/gap_request.json"
    draft_bundle = tmp_path / "state/draft_bundle.json"
    policy_path = tmp_path / "docs/backlog/roadmap_gate.json"
    plan_path = tmp_path / "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog-gaps/2026-05-04-future.md"
    item_path = tmp_path / "docs/backlog/active/2026-05-04-future-gap.md"
    output_path = tmp_path / "state/draft_validation.json"
    gap_request.parent.mkdir(parents=True, exist_ok=True)
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    item_path.parent.mkdir(parents=True, exist_ok=True)

    gap_request.write_text(
        json.dumps(
            {
                "allowed_roadmap_phase_prefixes": ["phase-2-pdebench-"],
                "disallowed_roadmap_phase_prefixes": ["phase-3-"],
                "gap_item_target_dir": "docs/backlog/active",
                "gap_plan_target_root": "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog-gaps",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "allowed_roadmap_phase_prefixes": ["phase-2-pdebench-"],
                "disallowed_roadmap_phase_prefixes": ["phase-3-"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    plan_path.write_text("# Future Plan\n", encoding="utf-8")
    item_path.write_text(
        f"""---
priority: 5
plan_path: {plan_path.relative_to(tmp_path).as_posix()}
check_commands:
  - python -c "print('future')"
related_roadmap_phases:
  - phase-3-cdi-anchor-regeneration
---

# Backlog Item: Future Gap

## Objective

- Draft future work.
""",
        encoding="utf-8",
    )
    draft_bundle.write_text(
        json.dumps(
            {
                "draft_status": "DRAFTED",
                "backlog_item_path": item_path.relative_to(tmp_path).as_posix(),
                "seed_plan_path": plan_path.relative_to(tmp_path).as_posix(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATE_GAP_DRAFT_SCRIPT),
            "--gap-request-path",
            gap_request.relative_to(tmp_path).as_posix(),
            "--draft-bundle-path",
            draft_bundle.relative_to(tmp_path).as_posix(),
            "--gate-policy-path",
            policy_path.relative_to(tmp_path).as_posix(),
            "--output",
            output_path.relative_to(tmp_path).as_posix(),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "disallowed" in result.stderr.lower() or "allowed" in result.stderr.lower()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["draft_validation_status"] == "INVALID"
    assert "disallowed" in payload["reason"].lower() or "allowed" in payload["reason"].lower()


def test_gap_draft_validator_installs_candidate_item_atomically(tmp_path: Path) -> None:
    gap_request = tmp_path / "state/gap_request.json"
    draft_bundle = tmp_path / "state/draft_bundle.json"
    policy_path = tmp_path / "docs/backlog/roadmap_gate.json"
    candidate_item = tmp_path / "state/gap-drafter/candidate/item.md"
    candidate_plan = tmp_path / "state/gap-drafter/candidate/plan.md"
    final_plan = tmp_path / "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog-gaps/2026-05-04-phase2.md"
    final_item = tmp_path / "docs/backlog/active/2026-05-04-phase2-gap.md"
    output_path = tmp_path / "state/draft_validation.json"
    gap_request.parent.mkdir(parents=True, exist_ok=True)
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_item.parent.mkdir(parents=True, exist_ok=True)

    gap_request.write_text(
        json.dumps(
            {
                "allowed_roadmap_phase_prefixes": ["phase-2-pdebench-"],
                "disallowed_roadmap_phase_prefixes": ["phase-3-"],
                "gap_item_target_dir": "docs/backlog/active",
                "gap_plan_target_root": "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog-gaps",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "allowed_roadmap_phase_prefixes": ["phase-2-pdebench-"],
                "disallowed_roadmap_phase_prefixes": ["phase-3-"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    candidate_plan.write_text("# Candidate Phase 2 Plan\n", encoding="utf-8")
    candidate_item.write_text(
        f"""---
priority: 5
plan_path: {final_plan.relative_to(tmp_path).as_posix()}
check_commands:
  - python -m compileall -q workflows
related_roadmap_phases:
  - phase-2-pdebench-full-training-evidence
---

# Backlog Item: Phase 2 Gap

## Objective

- Close the missing Phase 2 evidence gap.
""",
        encoding="utf-8",
    )
    draft_bundle.write_text(
        json.dumps(
            {
                "draft_status": "DRAFTED",
                "candidate_backlog_item_path": candidate_item.relative_to(tmp_path).as_posix(),
                "candidate_plan_path": candidate_plan.relative_to(tmp_path).as_posix(),
                "backlog_item_path": final_item.relative_to(tmp_path).as_posix(),
                "seed_plan_path": final_plan.relative_to(tmp_path).as_posix(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(VALIDATE_GAP_DRAFT_SCRIPT),
            "--gap-request-path",
            gap_request.relative_to(tmp_path).as_posix(),
            "--draft-bundle-path",
            draft_bundle.relative_to(tmp_path).as_posix(),
            "--gate-policy-path",
            policy_path.relative_to(tmp_path).as_posix(),
            "--output",
            output_path.relative_to(tmp_path).as_posix(),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["draft_validation_status"] == "VALID"
    assert payload["backlog_item_path"] == final_item.relative_to(tmp_path).as_posix()
    assert payload["seed_plan_path"] == final_plan.relative_to(tmp_path).as_posix()
    assert final_plan.read_text(encoding="utf-8") == "# Candidate Phase 2 Plan\n"
    installed_item = final_item.read_text(encoding="utf-8")
    assert f"plan_path: {final_plan.relative_to(tmp_path).as_posix()}" in installed_item


def test_gap_draft_validator_rejects_candidate_without_installing_active_item(tmp_path: Path) -> None:
    gap_request = tmp_path / "state/gap_request.json"
    draft_bundle = tmp_path / "state/draft_bundle.json"
    policy_path = tmp_path / "docs/backlog/roadmap_gate.json"
    candidate_item = tmp_path / "state/gap-drafter/candidate/item.md"
    candidate_plan = tmp_path / "state/gap-drafter/candidate/plan.md"
    final_plan = tmp_path / "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog-gaps/2026-05-04-phase2.md"
    final_item = tmp_path / "docs/backlog/active/2026-05-04-phase2-gap.md"
    output_path = tmp_path / "state/draft_validation.json"
    gap_request.parent.mkdir(parents=True, exist_ok=True)
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_item.parent.mkdir(parents=True, exist_ok=True)

    gap_request.write_text(
        json.dumps(
            {
                "allowed_roadmap_phase_prefixes": ["phase-2-pdebench-"],
                "disallowed_roadmap_phase_prefixes": ["phase-3-"],
                "gap_item_target_dir": "docs/backlog/active",
                "gap_plan_target_root": "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog-gaps",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "allowed_roadmap_phase_prefixes": ["phase-2-pdebench-"],
                "disallowed_roadmap_phase_prefixes": ["phase-3-"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    candidate_plan.write_text("# Candidate Phase 2 Plan\n", encoding="utf-8")
    candidate_item.write_text(
        """---
priority: 5
plan_path: docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog-gaps/wrong.md
check_commands:
  - python -m compileall -q workflows
related_roadmap_phases:
  - phase-2-pdebench-full-training-evidence
---

# Backlog Item: Phase 2 Gap

## Objective

- Close the missing Phase 2 evidence gap.
""",
        encoding="utf-8",
    )
    draft_bundle.write_text(
        json.dumps(
            {
                "draft_status": "DRAFTED",
                "candidate_backlog_item_path": candidate_item.relative_to(tmp_path).as_posix(),
                "candidate_plan_path": candidate_plan.relative_to(tmp_path).as_posix(),
                "backlog_item_path": final_item.relative_to(tmp_path).as_posix(),
                "seed_plan_path": final_plan.relative_to(tmp_path).as_posix(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATE_GAP_DRAFT_SCRIPT),
            "--gap-request-path",
            gap_request.relative_to(tmp_path).as_posix(),
            "--draft-bundle-path",
            draft_bundle.relative_to(tmp_path).as_posix(),
            "--gate-policy-path",
            policy_path.relative_to(tmp_path).as_posix(),
            "--output",
            output_path.relative_to(tmp_path).as_posix(),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["draft_validation_status"] == "INVALID"
    assert not final_item.exists()
    assert not final_plan.exists()
