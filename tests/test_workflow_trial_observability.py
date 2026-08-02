from __future__ import annotations

from copy import deepcopy
import builtins
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.cli.commands.report import _state_only_snapshot
from orchestrator.contracts.output_contract import validate_output_bundle
from orchestrator.observability.report import (
    build_status_snapshot,
    render_status_markdown,
)
from orchestrator.workflow.run_ref.bundle_transport import (
    write_bundle_capsule_directory,
)
from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
from orchestrator.workflow.run_ref.runtime import (
    resolve_run_ref_parent_input_values_for_config,
)
from orchestrator.workflow.runtime_step import RuntimeStep
from orchestrator.workflow.trial.adjudication import evaluate_trial_execution
from orchestrator.workflow.trial.config import build_trial_runtime_request
from orchestrator.workflow.trial.contracts import (
    build_sealed_opaque_label_map,
    derive_trial_cell_effect_scopes,
)
from orchestrator.workflow.trial.ledger import initialize_trial_event_ledger
from orchestrator.workflow.trial.settlement import (
    commit_trial_parent_settlement,
    prepare_trial_parent_settlement,
)
from tests.test_observability_report import (
    _load_bundle,
    _sample_workflow_payload,
)
from tests.test_workflow_lisp_trial_lowering import (
    _build_transportable_trial,
    _trial_node,
)
from tests.test_workflow_trial_adjudication import (
    _Executor,
    _blinded_cell_harnesses,
    _dependencies,
)
from tests.test_workflow_trial_runtime import _execute


def _trial_authority(tmp_path: Path) -> SimpleNamespace:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True)
    built = _build_transportable_trial(
        workspace,
        declarations="",
        type_name="String",
    )
    bundle = built.validated_bundle
    node = _trial_node(built)
    projection = bundle.projection.entries_by_node_id[node.node_id]
    step_name = projection.presentation_key
    step_id = projection.step_id
    run_id = "parent-run"
    run_root = (workspace / ".orchestrate" / "runs" / run_id).resolve()
    run_root.mkdir(parents=True)
    run_ref_root = (tmp_path / "run-ref-root").resolve()
    run_ref_root.mkdir()
    state = {
        "schema_version": "2.1",
        "run_id": run_id,
        "run_root": run_root.as_posix(),
        "run_ref_root": run_ref_root.as_posix(),
        "status": "running",
        "workflow_file": bundle.provenance.workflow_path.name,
        "bound_inputs": {"payload": "fixed"},
        "steps": {},
        "step_visits": {step_name: 1},
        "current_step": {
            "name": step_name,
            "step_id": step_id,
            "type": "trial",
            "status": "running",
            "visit_count": 1,
        },
    }
    step_config = node.execution_config
    request = build_trial_runtime_request(
        step_config=step_config,
        visit=RunRefVisitKey(
            parent_run_id=run_id,
            execution_frame_id="root",
            call_frame_id=None,
            step_id=step_id,
            visit_count=1,
        ),
        resolved_inputs_by_arm={
            arm.arm_id: resolve_run_ref_parent_input_values_for_config(
                arm.run_ref,
                state,
            )
            for arm in step_config.arms
        },
    )
    scopes = derive_trial_cell_effect_scopes(
        request=request,
        parent_run_root=run_root,
        run_ref_root=run_ref_root,
    )
    sealed = build_sealed_opaque_label_map(
        request.cell_domain,
        salt=b"trial-observability-fixture-salt-v1",
    )
    capsule_dir = (tmp_path / "capsule").resolve()
    assert built.run_ref_bundle_capsule is not None
    write_bundle_capsule_directory(capsule_dir, built.run_ref_bundle_capsule)
    return SimpleNamespace(
        bundle=bundle,
        node=node,
        step_name=step_name,
        step_id=step_id,
        state=state,
        workspace=workspace,
        run_root=run_root,
        run_ref_root=run_ref_root,
        request=request,
        scopes=scopes,
        sealed=sealed,
        capsule_dir=capsule_dir,
    )


def _initialize_active_trial(authority: SimpleNamespace) -> Path:
    initialized = initialize_trial_event_ledger(
        request=authority.request,
        sealed_opaque_labels=authority.sealed,
        cell_scopes=authority.scopes,
        recorded_at="2026-08-02T00:00:00.000000Z",
    )
    return initialized.path


def _terminal_trial(
    authority: SimpleNamespace,
    *,
    commit_parent: bool,
) -> tuple[dict[str, object], Path]:
    fixture = {
        "request": authority.request,
        "parent_state": authority.state,
        "parent_workspace": authority.workspace,
        "parent_run_root": authority.run_root,
        "run_ref_root": authority.run_ref_root,
        "capsule_dir": authority.capsule_dir,
        "scopes": authority.scopes,
        "sealed": authority.sealed,
    }
    execution = _execute(fixture, _blinded_cell_harnesses())
    dependencies, _ = _dependencies(_Executor())
    adjudicated = evaluate_trial_execution(
        authority.request,
        execution,
        parent_workspace=authority.workspace,
        dependencies=dependencies,
    )
    envelope = {
        "outcomes": list(adjudicated.authored_outcomes),
        "verdict": adjudicated.verdict,
        "verdict_artifact": adjudicated.verdict_artifact.relpath,
    }
    prepared = prepare_trial_parent_settlement(
        execution.ledger_path,
        request=authority.request,
        parent_workspace=authority.workspace,
        result_envelope=envelope,
    )
    output_path = "artifacts/compiler-generated-trial-result.json"
    output_file = authority.workspace / output_path
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_bytes(canonical_json_bytes(envelope) + b"\n")
    runtime_step = RuntimeStep(
        node=authority.node,
        name=authority.step_name,
        step_id=authority.step_id,
        target_dsl_version=authority.bundle.ir.version,
    )
    output_bundle = deepcopy(runtime_step["output_bundle"])
    output_bundle["path"] = output_path
    artifacts = validate_output_bundle(
        output_bundle,
        workspace=authority.workspace,
    )
    assert "outcomes" in artifacts
    assert "workspace_delta" in json.dumps(artifacts)
    assert "child_run_id" in json.dumps(artifacts)
    assert "evaluation_label" in json.dumps(artifacts)
    assert "scorer_identity" in json.dumps(artifacts)
    state = deepcopy(authority.state)
    state["status"] = "completed"
    state["current_step"] = None
    state["steps"] = {
        authority.step_name: {
            "status": "completed",
            "name": authority.step_name,
            "step_id": authority.step_id,
            "visit_count": 1,
            "exit_code": 0,
            "duration_ms": adjudicated.verdict["budget_accounting"]["elapsed_ms"],
            "output": "legacy-preview-secret",
            "text": "legacy-text-secret",
            "error": {"message": "legacy-error-secret"},
            "outcome": {"reason": "legacy-outcome-secret"},
            "debug": {"trace": "legacy-debug-secret"},
            "artifacts": artifacts,
            "trial": envelope,
        }
    }
    if commit_parent:
        commit_trial_parent_settlement(
            execution.ledger_path,
            request=authority.request,
            prepared=prepared,
            step_name=authority.step_name,
            expected_artifacts=artifacts,
            read_parent_state=lambda: state,
        )
    return state, execution.ledger_path


def _trial_projection(snapshot: dict[str, object]) -> dict[str, object] | None:
    [step] = snapshot["steps"]
    assert step["kind"] == "trial"
    return step["output"].get("trial_observability")


def _trial_step(snapshot: dict[str, object]) -> dict[str, object]:
    [step] = snapshot["steps"]
    assert step["kind"] == "trial"
    return step


def test_active_trial_report_projects_only_validated_opaque_progress(
    tmp_path: Path,
) -> None:
    authority = _trial_authority(tmp_path)
    ledger_path = _initialize_active_trial(authority)

    projection = _trial_projection(
        build_status_snapshot(
            authority.bundle,
            authority.state,
            authority.run_root,
        )
    )

    assert projection == {
        "schema_version": "workflow_trial_observability.v1",
        "status": "active",
        "phase": "cells",
        "cell_counts": {"frozen": 4, "completed": 0, "failed": 0},
        "active_counts": {"children": 0, "evaluators": 0},
        "concurrency": {"children": 2, "evaluators": 2},
        "budget": {
            "child_attempts": 0,
            "evaluator_attempts": 0,
            "max_evaluator_attempts": 4,
        },
        "digests": {
            "trial_request": authority.request.digest,
            "cell_domain": canonical_sha256(
                [cell.record for cell in authority.request.cell_domain]
            ),
            "ledger_head": json.loads(ledger_path.read_text())["row_digest"],
        },
        "failures": [],
    }
    rendered = json.dumps(projection, sort_keys=True)
    for forbidden in (
        "direct",
        "orc",
        "opaque-",
        "file:///",
        authority.workspace.as_posix(),
        authority.run_ref_root.as_posix(),
        "test-provider",
        "scorer",
        "prompt",
        "output",
    ):
        assert forbidden not in rendered


@pytest.mark.parametrize("failure_mode", ("missing", "tampered"))
def test_active_trial_report_omits_detail_without_valid_ledger_authority(
    tmp_path: Path,
    failure_mode: str,
) -> None:
    authority = _trial_authority(tmp_path)
    ledger_path = _initialize_active_trial(authority)
    if failure_mode == "missing":
        ledger_path.unlink()
    else:
        ledger_path.write_bytes(ledger_path.read_bytes() + b"{}\n")

    projection = _trial_projection(
        build_status_snapshot(
            authority.bundle,
            authority.state,
            authority.run_root,
        )
    )

    assert projection is None


def test_terminal_trial_report_requires_commit_and_filters_terminal_authority(
    tmp_path: Path,
) -> None:
    authority = _trial_authority(tmp_path)
    state, ledger_path = _terminal_trial(authority, commit_parent=True)
    before = ledger_path.read_bytes()

    projection = _trial_projection(
        snapshot := build_status_snapshot(
            authority.bundle,
            state,
            authority.run_root,
        )
    )

    assert projection is not None
    assert projection["schema_version"] == "workflow_trial_observability.v1"
    assert projection["status"] == "completed"
    assert projection["phase"] == "terminal"
    assert projection["cell_counts"] == {
        "frozen": 4,
        "completed": 4,
        "failed": 0,
    }
    assert projection["outcomes"] == [
        {"variant": "Completed", "arm_id": "direct", "rep": 1},
        {"variant": "Completed", "arm_id": "direct", "rep": 2},
        {"variant": "Completed", "arm_id": "orc", "rep": 1},
        {"variant": "Completed", "arm_id": "orc", "rep": 2},
    ]
    terminal = state["steps"][authority.step_name]["trial"]
    assert projection["aggregate_scores"] == terminal["verdict"][
        "aggregate_scores"
    ]
    assert projection["ranking"] == ["direct", "orc"]
    assert projection["selected_arm"] is None
    assert projection["success_rule_disposition"] == "cost_unknown"
    assert projection["verdict"] == {
        "digest": canonical_sha256(terminal["verdict"]),
        "relpath": terminal["verdict_artifact"],
    }
    assert projection["budget_accounting"] == terminal["verdict"][
        "budget_accounting"
    ]
    assert isinstance(projection["evidence_freeze_digest"], str)
    assert ledger_path.read_bytes() == before
    step = _trial_step(snapshot)
    assert step["output"] == {"trial_observability": projection}
    rendered = json.dumps(projection, sort_keys=True)
    for forbidden in (
        "candidate-output",
        "opaque-",
        "file:///",
        "workspace_delta",
        "child_run_id",
        "provider",
        "model",
        "packet_body",
        "prompt",
        "scorer_identity",
    ):
        assert forbidden not in rendered
    closed_output = json.dumps(step["output"], sort_keys=True)
    for forbidden in (
        "candidate-output",
        "workspace_delta",
        "child_run_id",
        "evaluation_label",
        "scorer_identity",
        "legacy-preview-secret",
        "legacy-text-secret",
        "legacy-error-secret",
        "legacy-outcome-secret",
        "legacy-debug-secret",
        '"artifacts"',
        '"duration_ms"',
        '"output_preview"',
        '"error"',
        '"outcome"',
        '"debug"',
        '"exit_code"',
    ):
        assert forbidden not in closed_output

    markdown = render_status_markdown(snapshot)
    assert "trial_observability" in markdown
    assert "status: `completed`" in markdown
    assert "completed_cells: `4`" in markdown
    assert "selected_arm: `None`" in markdown
    assert "success_rule_disposition: `cost_unknown`" in markdown
    assert projection["verdict"]["digest"] in markdown
    for forbidden in (
        "exit_code",
        "duration_ms",
        "candidate-output",
        "workspace_delta",
        "child_run_id",
        "evaluation_label",
        "scorer_identity",
        "legacy-preview-secret",
        "legacy-text-secret",
        "legacy-error-secret",
        "legacy-outcome-secret",
        "legacy-debug-secret",
    ):
        assert forbidden not in markdown

    tampered = deepcopy(state)
    tampered["steps"][authority.step_name]["trial"]["verdict"][
        "selected_arm"
    ] = "direct"
    tampered_snapshot = build_status_snapshot(
        authority.bundle,
        tampered,
        authority.run_root,
    )
    assert _trial_projection(tampered_snapshot) is None
    assert _trial_step(tampered_snapshot)["output"] == {}


def test_prepared_trial_is_not_reported_as_terminal_and_report_never_commits_it(
    tmp_path: Path,
) -> None:
    authority = _trial_authority(tmp_path)
    state, ledger_path = _terminal_trial(authority, commit_parent=False)
    before = ledger_path.read_bytes()

    snapshot = build_status_snapshot(authority.bundle, state, authority.run_root)
    projection = _trial_projection(snapshot)

    assert projection is None
    assert _trial_step(snapshot)["output"] == {}
    assert ledger_path.read_bytes() == before


def test_state_only_trial_report_identifies_kind_without_projecting_or_scanning(
    tmp_path: Path,
) -> None:
    run_dir = (tmp_path / "run").resolve()
    decoy = run_dir / "trials" / "should-not-be-read"
    decoy.mkdir(parents=True)
    (decoy / "authored-arm-id-direct").write_text("secret", encoding="utf-8")
    active = {
        "run_id": "run",
        "status": "running",
        "steps": {},
        "current_step": {
            "name": "Compare",
            "step_id": "root.compare",
            "type": "trial",
            "status": "running",
            "visit_count": 1,
            "duration_ms": 999,
            "output": "active-preview-secret",
            "debug": {"trace": "active-debug-secret"},
        },
    }
    terminal = {
        "run_id": "run",
        "status": "completed",
        "steps": {
            "Compare": {
                "status": "completed",
                "step_id": "root.compare",
                "trial": {"outcomes": [{"arm_id": "direct"}]},
                "duration_ms": 999,
                "output": "terminal-preview-secret",
                "artifacts": {
                    "outcomes": [
                        {
                            "value": "candidate-output-secret",
                            "evidence": {
                                "workspace_delta": {},
                                "child_run_id": "child-secret",
                                "evaluation_label": "evaluation-secret",
                                "scorer_identity": "scorer-secret",
                            },
                        }
                    ]
                },
                "error": {"message": "terminal-error-secret"},
                "outcome": {"reason": "terminal-outcome-secret"},
                "debug": {"trace": "terminal-debug-secret"},
            }
        },
        "current_step": None,
    }

    active_snapshot = _state_only_snapshot(active, run_dir)
    terminal_snapshot = _state_only_snapshot(terminal, run_dir)

    assert active_snapshot["steps"][0]["kind"] == "trial"
    assert terminal_snapshot["steps"][0]["kind"] == "trial"
    assert active_snapshot["steps"][0]["output"] == {}
    assert terminal_snapshot["steps"][0]["output"] == {}
    rendered = json.dumps(terminal_snapshot["steps"][0])
    for forbidden in (
        "direct",
        "duration_ms",
        "candidate-output-secret",
        "workspace_delta",
        "child_run_id",
        "evaluation_label",
        "scorer_identity",
        "terminal-preview-secret",
        "terminal-error-secret",
        "terminal-outcome-secret",
        "terminal-debug-secret",
    ):
        assert forbidden not in rendered


def test_ordinary_report_does_zero_trial_projection_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ordinary_root = (tmp_path / "ordinary" / "run").resolve()
    ordinary_root.mkdir(parents=True)
    bundle = _load_bundle(tmp_path / "ordinary", _sample_workflow_payload())
    imported: list[str] = []
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "orchestrator.workflow.trial.observability":
            imported.append(name)
            raise AssertionError("ordinary report imported trial observability")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    snapshot = build_status_snapshot(
        bundle,
        {
            "run_id": "ordinary",
            "status": "running",
            "steps": {},
            "current_step": None,
        },
        ordinary_root,
    )

    assert snapshot["progress"]["total"] == 2
    assert imported == []
    assert not (ordinary_root / "trials").exists()
