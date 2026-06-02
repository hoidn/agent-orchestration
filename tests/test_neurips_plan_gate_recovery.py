import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.adapters import (
    load_canonical_phase_result,
    validate_reusable_phase_state,
    write_reusable_phase_state_v1,
)


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
    report_relpath: str = "artifacts/review/NEURIPS-HYBRID-RESNET-2026/backlog/item-plan-recovery.md",
) -> tuple[dict, str]:
    output = workspace / "state/item/plan-gate/final_plan_gate.json"
    status_output = workspace / "state/item/plan_gate_status.txt"
    report = workspace / report_relpath
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
            "--status-output",
            status_output.relative_to(workspace).as_posix(),
        ],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stderr == ""
    return json.loads(output.read_text(encoding="utf-8")), status_output.read_text(encoding="utf-8").strip()


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _structured_contract_fingerprint(
    *,
    structured_contract_kind: str,
    structured_contract: dict[str, object],
    return_type_name: str,
) -> str:
    digest = hashlib.sha256(
        json.dumps(structured_contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"2.14:{return_type_name}:{structured_contract_kind}:{digest}"


def _plan_gate_payload_path(workspace: Path, *, resume_from: str) -> Path:
    structured_contract = {
        "discriminant": {
            "name": "variant",
            "json_pointer": "/variant",
            "type": "enum",
            "allowed": ["APPROVED", "BLOCKED"],
        },
        "shared_fields": [
            {
                "name": "shared_report_path",
                "json_pointer": "/shared_report_path",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ],
        "variants": {
            "APPROVED": {
                "fields": [
                    {
                        "name": "execution_report_path",
                        "json_pointer": "/execution_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    }
                ]
            },
            "BLOCKED": {
                "fields": [
                    {
                        "name": "progress_report_path",
                        "json_pointer": "/progress_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    },
                    {
                        "name": "blocker_class",
                        "json_pointer": "/blocker_class",
                        "type": "string",
                    },
                ]
            },
        },
    }
    return _write_json(
        workspace / "state" / "payloads" / "plan_gate_validate.json",
        {
            "bundle_path": resume_from,
            "resume_from": resume_from,
            "target_dsl_version": "2.14",
            "return_type_name": "PlanGateResult",
            "structured_contract_kind": "union",
            "expected_contract_fingerprint": _structured_contract_fingerprint(
                structured_contract_kind="union",
                structured_contract=structured_contract,
                return_type_name="PlanGateResult",
            ),
            "structured_contract": structured_contract,
            "summary_schema": "ReusablePhaseState.v1",
            "summary_version": "v1",
            "sidecar_suffix": ".reusable_state.json",
            "canonical_bundle_digest_field": "canonical_bundle_sha256",
            "reusable_variants": ["APPROVED"],
            "artifact_requirements": {
                "APPROVED": [
                    {
                        "field_path": ["shared_report_path"],
                        "under": "artifacts/work",
                    },
                    {
                        "field_path": ["execution_report_path"],
                        "under": "artifacts/work",
                    }
                ],
                "BLOCKED": [
                    {
                        "field_path": ["progress_report_path"],
                        "under": "artifacts/work",
                    }
                ],
            },
            "public_input_hash_basis": [
                "phase-ctx__phase-name",
                "inputs__selected_item_path",
                "inputs__recovery_report_target_path",
            ],
            "current_public_inputs": {
                "phase-ctx__phase-name": "plan-gate",
                "inputs__selected_item_path": "docs/backlog/in_progress/item.md",
                "inputs__recovery_report_target_path": (
                    "artifacts/review/NEURIPS-HYBRID-RESNET-2026/backlog/item-plan-recovery.md"
                ),
            },
            "producer_fingerprint_basis": {
                "workflow_name": "resume-plan-gate",
                "return_type_name": "PlanGateResult",
                "structured_contract_kind": "union",
                "expected_contract_fingerprint": _structured_contract_fingerprint(
                    structured_contract_kind="union",
                    structured_contract=structured_contract,
                    return_type_name="PlanGateResult",
                ),
                "target_dsl_version": "2.14",
                "compiler_version": "0.1.0",
                "reusable_variants": ["APPROVED"],
                "public_input_hash_basis": [
                    "phase-ctx__phase-name",
                    "inputs__selected_item_path",
                    "inputs__recovery_report_target_path",
                ],
            },
            "source_run_id": "test-run",
            "source_step_id": "plan-gate",
            "source_call_frame_id": "root",
            "phase_id": "plan-gate",
            "created_at": "2026-06-02T00:00:00Z",
        },
    )


def test_recovers_approved_plan_gate_from_in_progress_item_frontmatter(tmp_path: Path) -> None:
    plan_path = "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/item/execution_plan.md"
    (tmp_path / plan_path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / plan_path).write_text("# Execution plan\n", encoding="utf-8")
    _write_item(tmp_path, "docs/backlog/in_progress/item.md", plan_path=plan_path)

    payload, status = _run_recovery(
        tmp_path,
        selection_mode="RECOVERED_IN_PROGRESS",
        item_path="docs/backlog/in_progress/item.md",
    )

    assert status == "APPROVED"
    assert payload["status"] == "APPROVED"
    assert payload["source"] == "RECOVERED"
    assert payload["selected_item_path"] == "docs/backlog/in_progress/item.md"
    assert payload["plan_path"] == plan_path
    assert payload["plan_review_decision"] == "APPROVE"
    assert payload["plan_review_report_path"] == (
        "artifacts/review/NEURIPS-HYBRID-RESNET-2026/backlog/item-plan-recovery.md"
    )
    assert (tmp_path / payload["plan_review_report_path"]).is_file()


def test_recovers_approved_plan_gate_to_hidden_artifacts_review_root(tmp_path: Path) -> None:
    plan_path = "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/item/execution_plan.md"
    (tmp_path / plan_path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / plan_path).write_text("# Execution plan\n", encoding="utf-8")
    _write_item(tmp_path, "docs/backlog/in_progress/item.md", plan_path=plan_path)

    payload, status = _run_recovery(
        tmp_path,
        selection_mode="RECOVERED_IN_PROGRESS",
        item_path="docs/backlog/in_progress/item.md",
        report_relpath=".artifacts/review/NEURIPS-HYBRID-RESNET-2026/backlog/item-plan-recovery.md",
    )

    assert status == "APPROVED"
    assert payload["status"] == "APPROVED"
    assert payload["source"] == "RECOVERED"
    assert payload["plan_review_report_path"] == (
        ".artifacts/review/NEURIPS-HYBRID-RESNET-2026/backlog/item-plan-recovery.md"
    )
    assert (tmp_path / payload["plan_review_report_path"]).is_file()


def test_active_selection_does_not_recover_existing_plan_path(tmp_path: Path) -> None:
    plan_path = "docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/item/execution_plan.md"
    (tmp_path / plan_path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / plan_path).write_text("# Execution plan\n", encoding="utf-8")
    _write_item(tmp_path, "docs/backlog/active/item.md", plan_path=plan_path)

    payload, status = _run_recovery(
        tmp_path,
        selection_mode="ACTIVE_SELECTION",
        item_path="docs/backlog/active/item.md",
    )

    assert status == "MISSING"
    assert payload == {"status": "MISSING", "source": "NONE"}


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

        payload, status = _run_recovery(
            tmp_path,
            selection_mode="RECOVERED_IN_PROGRESS",
            item_path=item_path,
        )

        assert status == "MISSING"
        assert payload == {"status": "MISSING", "source": "NONE"}


def test_plan_gate_recovery_resume_validator_distinguishes_start_from_hard_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    payload_path = _plan_gate_payload_path(tmp_path, resume_from="state/item/plan-gate/final_plan_gate.json")

    missing_exit = validate_reusable_phase_state.main(
        ["validate_reusable_phase_state", payload_path.as_posix()]
    )
    missing = json.loads(capsys.readouterr().out)

    blocked_bundle_path = _write_json(
        tmp_path / "state" / "item" / "plan-gate" / "final_plan_gate.json",
        {
            "variant": "BLOCKED",
            "shared_report_path": "artifacts/work/shared-blocked.md",
            "progress_report_path": "artifacts/work/blocked.md",
            "blocker_class": "user_decision_required",
        },
    )
    blocked_exit = validate_reusable_phase_state.main(
        ["validate_reusable_phase_state", payload_path.as_posix()]
    )
    blocked = json.loads(capsys.readouterr().out)

    shared_report = tmp_path / "artifacts" / "work" / "shared-approved.md"
    execution_report = tmp_path / "artifacts" / "work" / "execution-approved.md"
    shared_report.parent.mkdir(parents=True, exist_ok=True)
    shared_report.write_text("shared", encoding="utf-8")
    execution_report.write_text("execution", encoding="utf-8")
    _write_json(
        tmp_path / "state" / "item" / "plan-gate" / "final_plan_gate.json",
        {
            "variant": "APPROVED",
            "shared_report_path": "artifacts/work/shared-approved.md",
            "execution_report_path": "artifacts/work/execution-approved.md",
        },
    )
    assert write_reusable_phase_state_v1.main(["write_reusable_phase_state_v1", payload_path.as_posix()]) == 0
    capsys.readouterr()
    blocked_bundle_path.write_text("state/item/plan-gate/pointer.txt\n", encoding="utf-8")
    invalid_exit = validate_reusable_phase_state.main(
        ["validate_reusable_phase_state", payload_path.as_posix()]
    )
    invalid = json.loads(capsys.readouterr().out)

    assert missing_exit == 0
    assert missing == {"variant": "START"}
    assert blocked_exit == 0
    assert blocked == {"variant": "FAILED_PRIOR_STATE"}
    assert invalid_exit == 1
    assert invalid == {"error": {"type": "resume_state_pointer_authority_forbidden"}}


def test_plan_gate_recovery_resume_validator_reports_missing_required_shared_artifact_for_reusable_variant(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    payload_path = _plan_gate_payload_path(tmp_path, resume_from="state/item/plan-gate/final_plan_gate.json")
    shared_report = tmp_path / "artifacts" / "work" / "shared.md"
    execution_report = tmp_path / "artifacts" / "work" / "execution.md"
    execution_report.parent.mkdir(parents=True, exist_ok=True)
    shared_report.write_text("shared", encoding="utf-8")
    execution_report.write_text("execution", encoding="utf-8")
    _write_json(
        tmp_path / "state" / "item" / "plan-gate" / "final_plan_gate.json",
        {
            "variant": "APPROVED",
            "shared_report_path": "artifacts/work/shared.md",
            "execution_report_path": "artifacts/work/execution.md",
        },
    )
    assert write_reusable_phase_state_v1.main(["write_reusable_phase_state_v1", payload_path.as_posix()]) == 0
    capsys.readouterr()
    shared_report.unlink()

    exit_code = validate_reusable_phase_state.main(
        ["validate_reusable_phase_state", payload_path.as_posix()]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {"variant": "MISSING_ARTIFACT"}


def test_plan_gate_recovery_loader_preserves_plan_gate_result_shape(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    shared_report = tmp_path / "artifacts" / "work" / "shared.md"
    execution_report = tmp_path / "artifacts" / "work" / "execution.md"
    execution_report.parent.mkdir(parents=True, exist_ok=True)
    shared_report.write_text("shared", encoding="utf-8")
    execution_report.write_text("report", encoding="utf-8")
    bundle_path = _write_json(
        tmp_path / "state" / "item" / "plan-gate" / "final_plan_gate.json",
        {
            "variant": "APPROVED",
            "shared_report_path": "artifacts/work/shared.md",
            "execution_report_path": "artifacts/work/execution.md",
        },
    )
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    structured_contract = {
        "discriminant": {
            "name": "variant",
            "json_pointer": "/variant",
            "type": "enum",
            "allowed": ["APPROVED", "BLOCKED"],
        },
        "shared_fields": [
            {
                "name": "shared_report_path",
                "json_pointer": "/shared_report_path",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ],
        "variants": {
            "APPROVED": {
                "fields": [
                    {
                        "name": "execution_report_path",
                        "json_pointer": "/execution_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    }
                ]
            },
            "BLOCKED": {
                "fields": [
                    {
                        "name": "progress_report_path",
                        "json_pointer": "/progress_report_path",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    },
                    {
                        "name": "blocker_class",
                        "json_pointer": "/blocker_class",
                        "type": "string",
                    },
                ]
            },
        },
    }

    exit_code = load_canonical_phase_result.main(
        [
            "load_canonical_phase_result",
            json.dumps(
                {
                    "bundle_path": "state/item/plan-gate/final_plan_gate.json",
                    "target_dsl_version": "2.14",
                    "return_type_name": "PlanGateResult",
                    "expected_contract_fingerprint": _structured_contract_fingerprint(
                        structured_contract_kind="union",
                        structured_contract=structured_contract,
                        return_type_name="PlanGateResult",
                    ),
                    "structured_contract_kind": "union",
                    "structured_contract": structured_contract,
                    "source_bundle_sha256": bundle_sha256,
                }
            ),
        ]
    )
    loaded = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert loaded == {
        "variant": "APPROVED",
        "shared_report_path": "artifacts/work/shared.md",
        "execution_report_path": "artifacts/work/execution.md",
    }
