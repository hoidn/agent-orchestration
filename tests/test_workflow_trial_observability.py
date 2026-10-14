from __future__ import annotations

import builtins

from copy import deepcopy
from types import SimpleNamespace, MappingProxyType
from orchestrator.observability.report import build_status_snapshot, render_status_markdown
from orchestrator.workflow.run_ref.contracts import canonical_sha256, canonical_json_bytes
from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
from orchestrator.workflow.trial.config import build_trial_runtime_request
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.executable_ir import ExecutableWorkflow, ExecutableNodeKind, LeafExecutableNode, WorkflowRegion
from orchestrator.workflow.state_projection import WorkflowStateProjection, CompatibilityNodeProjection, CompatibilityStepDefinition
from orchestrator.workflow.surface_ast import SurfaceWorkflow, WorkflowProvenance
from tests.test_workflow_trial_ledger import _captured_trial_config
import json
from pathlib import Path

import pytest

from orchestrator.cli.commands.report import _state_only_snapshot

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
    imported: list[str] = []
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "orchestrator.workflow.trial.observability":
            imported.append(name)
            raise AssertionError("ordinary report imported trial observability")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    snapshot = _state_only_snapshot(
        {
            "run_id": "ordinary",
            "status": "running",
            "steps": {},
            "current_step": None,
        },
        ordinary_root,
    )

    assert snapshot["progress"]["total"] == 0
    assert imported == []
    assert not (ordinary_root / "trials").exists()


def _trial_authority(tmp_path: Path, variant="active") -> SimpleNamespace:
    fixture_path = Path(__file__).parent / "fixtures" / "historical_trial_observability.json"
    captured = json.loads(fixture_path.read_text())
    active = captured["variants"][variant]
    # Rebase reader locations and allocation paths bound to the ledger location.
    # Execution results and verdict bytes retain the historical capture.
    metadata = {key: value for key, value in active.items() if key != "files"}
    metadata = json.loads(json.dumps(metadata).replace("@WORKSPACE@", str(tmp_path)))
    config = _captured_trial_config(metadata["config"])
    info = metadata["bundle"]
    provenance = WorkflowProvenance(
        workflow_path=Path(info["workflow_path"]), source_root=Path(info["source_root"]),
    )
    node = LeafExecutableNode(
        node_id=info["node_id"], step_id=info["step_id"],
        presentation_name=info["display_name"], kind=ExecutableNodeKind.TRIAL,
        region=WorkflowRegion(info["region"]), lexical_scope=tuple(info["lexical_scope"]),
        execution_config=config,
    )
    entry = CompatibilityNodeProjection(
        node_id=node.node_id, step_id=node.step_id,
        presentation_key=info["step_name"], display_name=info["display_name"],
        region=node.region, compatibility_index=info["compatibility_index"],
        step_definition=CompatibilityStepDefinition(report_kind="trial"),
    )
    bundle = LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version=info["version"], name=info["name"], steps=(), provenance=provenance,
        ),
        core_workflow_ast=None, semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version="workflow_executable_ir.v1", version=info["version"],
            name=info["name"], provenance=provenance, body_region=(node.node_id,),
            finalization_region=(), finalization_entry_node_id=None,
            nodes=MappingProxyType({node.node_id: node}),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType({node.node_id: entry}),
            node_id_by_compatibility_index=MappingProxyType({entry.compatibility_index: node.node_id}),
            compatibility_index_by_node_id=MappingProxyType({node.node_id: entry.compatibility_index}),
            presentation_key_by_node_id=MappingProxyType({node.node_id: entry.presentation_key}),
            node_id_by_step_id=MappingProxyType({node.step_id: node.node_id}),
        ),
        runtime_plan=None, imports=MappingProxyType({}), provenance=provenance,
    )
    request = build_trial_runtime_request(
        step_config=config, visit=RunRefVisitKey("parent-run", "root", None, node.step_id, 1),
        resolved_inputs_by_arm={"direct": {"payload": "fixed"}, "orc": {"payload": "fixed"}},
    )
    for key in ("workspace", "run_root", "run_ref_root"):
        Path(metadata[key]).mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        bundle=bundle, step_name=info["step_name"], step_id=node.step_id,
        state=metadata["state"], workspace=Path(metadata["workspace"]),
        run_root=Path(metadata["run_root"]), run_ref_root=Path(metadata["run_ref_root"]),
        request=request, captured=captured, fixture_root=tmp_path,
    )

def _rebase_captured_ledger(content, path):
    rows = [json.loads(line) for line in content.splitlines()]
    replacements = {}
    rewritten = []
    for original in rows:
        encoded = json.dumps(original)
        for old, new in replacements.items():
            encoded = encoded.replace(old, new)
        row = json.loads(encoded)
        payload = row["payload"]
        if row["kind"] == "cell_allocated":
            cell = payload["cell"]
            domain = rows[0]["payload"]["cell_domain"]
            effect_root = path.parent / f"cell-{domain.index(cell) + 1:04d}" / "e1"
            payload["effect_instance_root"] = str(effect_root)
            payload["e1_ledger_path"] = str(effect_root / "run-ref-attempts.jsonl")
        if row["kind"] == "evidence_frozen":
            old = original["payload"]["evidence_set_digest"]
            payload["evidence_set_digest"] = canonical_sha256(payload["cell_evidence"])
            replacements[old] = payload["evidence_set_digest"]
        if row["kind"] == "scores_frozen":
            old = original["payload"]["score_set_digest"]
            payload["score_set_digest"] = canonical_sha256(payload["scores"])
            replacements[old] = payload["score_set_digest"]
        if row["kind"] == "aggregation_frozen":
            header = rows[0]["payload"]
            scores = next(r for r in rewritten if r["kind"] == "scores_frozen")
            authority = {key: payload[key] for key in (
                "scores_frozen_row_digest", "sealed_opaque_label_map_digest",
                "final_outcomes_digest",
            )}
            authority.update(
                evaluation_digest=header["evaluation_digest"],
                score_set_digest=scores["payload"]["score_set_digest"],
            )
            payload["aggregation_input_digest"] = canonical_sha256(authority)
        row.pop("row_digest")
        row["row_digest"] = canonical_sha256(row)
        replacements[original["row_digest"]] = row["row_digest"]
        rewritten.append(row)
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rewritten).decode()

def _write_captured_trial(authority, variant):
    captured = authority.captured["variants"][variant]
    for relative, content in captured["files"].items():
        path = authority.fixture_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.name == "trial-events.jsonl":
            content = _rebase_captured_ledger(content, path)
        path.write_text(content)
    metadata = {k: v for k, v in captured.items() if k != "files"}
    metadata = json.loads(json.dumps(metadata).replace("@WORKSPACE@", str(authority.fixture_root)))
    return metadata["state"], Path(metadata["ledger_path"])

def _initialize_active_trial(authority):
    _state, path = _write_captured_trial(authority, "active")
    return path

def _terminal_trial(authority, *, commit_parent):
    variant = "committed" if commit_parent else "prepared"
    authority.__dict__.update(_trial_authority(authority.fixture_root, variant).__dict__)
    return _write_captured_trial(authority, variant)

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
