"""Dashboard coverage for the persisted Workflow Lisp surface read model."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.dashboard.compiled_workflow import (
    PersistedCompiledWorkflowError,
    _closed_anchor,
    load_persisted_compiled_workflow_surface,
    traverse_persisted_compiled_workflow_call_frames,
)
from orchestrator.workflow.persisted_surface import (
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    persisted_surface_sha256,
)
from orchestrator.workflow.surface_ast import SurfaceStep, SurfaceStepKind
from tests.test_persisted_workflow_surface import (
    _bundle,
    _call,
    _canonical_payload,
)


FINGERPRINT = "0123456789abcdef"
ENTRY_WORKFLOW = "dashboard_fixture::entry"
IMPORTED_ENTRY_WORKFLOW = "neurips/entry::orchestrate"
IMPORTED_PROVIDER_WORKFLOW = "neurips/helper::provider-attempt"
IMPORTED_SELECTOR_WORKFLOW = "imported_selector::selector-run"


@pytest.mark.parametrize(
    "schema",
    (
        "persisted_workflow_surface_graph.v1",
        "persisted_workflow_surface_graph.v2",
        "persisted_workflow_surface_graph.v3",
        "persisted_workflow_surface_graph.v4",
        "persisted_workflow_surface_graph.v5",
    ),
)
def test_persisted_surface_anchor_accepts_each_supported_schema(
    schema: str,
) -> None:
    anchor = {
        "schema_version": schema,
        "path": f"build/{FINGERPRINT}/persisted_workflow_surface.json",
        "entry_workflow": ENTRY_WORKFLOW,
        "sha256": "sha256:" + "a" * 64,
    }

    assert _closed_anchor(anchor, label="test anchor") == anchor


def test_persisted_surface_anchor_rejects_unknown_schema() -> None:
    with pytest.raises(PersistedCompiledWorkflowError, match="unsupported"):
        _closed_anchor(
            {
                "schema_version": "unsupported.v1",
                "path": f"build/{FINGERPRINT}/persisted_workflow_surface.json",
                "entry_workflow": ENTRY_WORKFLOW,
                "sha256": "sha256:" + "a" * 64,
            },
            label="test anchor",
        )


def _write_real_imported_bundle_mix_run(
    workspace: Path,
    *,
    run_id: str = "run1",
):
    provider = _bundle(
        IMPORTED_PROVIDER_WORKFLOW,
        steps=(
            SurfaceStep(
                name="ProviderAttempt",
                step_id="provider_attempt",
                kind=SurfaceStepKind.PROVIDER,
                provider="provider",
            ),
        ),
    )
    selector = _bundle(
        IMPORTED_SELECTOR_WORKFLOW,
        steps=(
            SurfaceStep(
                name="SelectorReturn",
                step_id="selector_return",
                kind=SurfaceStepKind.MATERIALIZE_ARTIFACTS,
            ),
        ),
    )
    entry = _bundle(
        IMPORTED_ENTRY_WORKFLOW,
        steps=(
            _call(
                "neurips/helper::provider-attempt__result",
                IMPORTED_PROVIDER_WORKFLOW,
            ),
            _call("imported_selector::selector-run__return", "selector-run"),
        ),
        imports={
            IMPORTED_PROVIDER_WORKFLOW: provider,
            "selector-run": selector,
        },
    )
    surface, _payload = _canonical_payload(entry)
    for workflow_name, workflow_path in {
        IMPORTED_ENTRY_WORKFLOW: (
            "tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/"
            "neurips/entry.orc"
        ),
        IMPORTED_PROVIDER_WORKFLOW: "workflows/neurips/helper/provider-attempt.orc",
        IMPORTED_SELECTOR_WORKFLOW: "workflows/imported_selector/selector-run.orc",
    }.items():
        surface["nodes"][workflow_name]["version"] = "2.14"
        surface["nodes"][workflow_name]["workflow_path"] = workflow_path
    payload = canonical_persisted_surface_bytes(surface)
    source_path = (
        workspace
        / "tests"
        / "fixtures"
        / "workflow_lisp"
        / "modules"
        / "valid"
        / "imported_bundle_mix"
        / "neurips"
        / "entry.orc"
    )
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = b"historical reader fixture source placeholder\n"
    source_path.write_bytes(source_bytes)

    build_root = workspace / ".orchestrate" / "build" / FINGERPRINT
    build_root.mkdir(parents=True, exist_ok=True)
    surface_path = build_root / "persisted_workflow_surface.json"
    surface_path.write_bytes(payload)
    surface_digest = persisted_surface_sha256(payload)
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    manifest_path = build_root / "manifest.json"
    anchor = {
        "schema_version": surface["schema_version"],
        "path": f"build/{FINGERPRINT}/persisted_workflow_surface.json",
        "entry_workflow": IMPORTED_ENTRY_WORKFLOW,
        "sha256": surface_digest,
    }
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "workflow_lisp_build.v2",
                "fingerprint": FINGERPRINT,
                "entry_workflow": IMPORTED_ENTRY_WORKFLOW,
                "source_path": source_path.relative_to(workspace).as_posix(),
                "source_sha256": source_digest,
                "shared_validation_status": "validated",
                "persisted_workflow_surface": anchor,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    state: dict[str, object] = {
        "run_id": run_id,
        "status": "completed",
        "workflow_file": str(source_path.relative_to(workspace)),
        "workflow_checksum": f"sha256:{source_digest}",
        "runtime_observability": {
            "compiled_frontend": {
                "frontend_kind": "workflow_lisp",
                "frontend_build_root": f".orchestrate/build/{FINGERPRINT}/",
                "frontend_entry_workflow": IMPORTED_ENTRY_WORKFLOW,
                "persisted_workflow_surface": anchor.copy(),
            }
        },
    }
    run_root = workspace / ".orchestrate" / "runs" / run_id
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True, exist_ok=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = SimpleNamespace(
        build_root=build_root,
        manifest_path=manifest_path,
        artifact_paths={"persisted_workflow_surface": surface_path},
    )
    return result, source_path, state


def test_persisted_surface_traverses_exact_nested_import_alias(
    tmp_path: Path,
) -> None:
    result, source_path, state = _write_real_imported_bundle_mix_run(tmp_path)
    graph = load_persisted_compiled_workflow_surface(
        workspace_root=tmp_path,
        workflow_path=source_path,
        state=state,
    )
    call = graph.entry_node.steps[0]
    assert call.call_alias is not None
    frame_id = f"{call.step_id}::visit::1"
    child_state = {"steps": {}, "call_frames": {}}
    state["call_frames"] = {
        frame_id: {
            "call_frame_id": frame_id,
            "call_step_id": call.step_id,
            "import_alias": call.call_alias,
            "state": child_state,
        }
    }

    traversed = traverse_persisted_compiled_workflow_call_frames(
        graph,
        state=state,
        call_frame_ids=(frame_id,),
    )

    assert traversed.node is graph.imported_node(
        graph.entry_node,
        call.call_alias,
    )
    assert traversed.state is child_state


@pytest.mark.parametrize(
    "damage",
    (
        "frame_identity",
        "unknown_alias",
        "valid_wrong_alias",
        "missing_nested_state",
    ),
)
def test_persisted_surface_rejects_contradictory_call_frame_traversal(
    tmp_path: Path,
    damage: str,
) -> None:
    result, source_path, state = _write_real_imported_bundle_mix_run(tmp_path)
    graph = load_persisted_compiled_workflow_surface(
        workspace_root=tmp_path,
        workflow_path=source_path,
        state=state,
    )
    call = graph.entry_node.steps[0]
    frame_id = f"{call.step_id}::visit::1"
    frame: dict[str, object] = {
        "call_frame_id": frame_id,
        "call_step_id": call.step_id,
        "import_alias": call.call_alias,
        "state": {"steps": {}, "call_frames": {}},
    }
    if damage == "frame_identity":
        frame["call_frame_id"] = "different"
    elif damage == "unknown_alias":
        frame["import_alias"] = "missing"
    elif damage == "valid_wrong_alias":
        frame["import_alias"] = graph.entry_node.steps[1].call_alias
    else:
        frame.pop("state")
    state["call_frames"] = {frame_id: frame}

    with pytest.raises(PersistedCompiledWorkflowError):
        traverse_persisted_compiled_workflow_call_frames(
            graph,
            state=state,
            call_frame_ids=(frame_id,),
        )


def test_persisted_surface_decoder_deeply_freezes_metadata(tmp_path: Path):
    result, _source_path, _state = _write_real_imported_bundle_mix_run(tmp_path)
    surface_path = result.artifact_paths["persisted_workflow_surface"]
    payload = json.loads(surface_path.read_text(encoding="utf-8"))
    step = payload["nodes"]["imported_selector::selector-run"]["steps"][0]
    step["asset_depends_on"] = [{"nested": ["asset"]}]
    step["common"]["publishes"] = [{"nested": ["publish"]}]
    step["common"]["consumes"] = [{"nested": ["consume"]}]
    step["common"]["expected_outputs"] = [{"nested": ["output"]}]

    graph = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(payload)
    )
    decoded = graph.nodes["imported_selector::selector-run"].steps[0]

    for value in (
        decoded.asset_depends_on[0],
        decoded.common.publishes[0],
        decoded.common.consumes[0],
        decoded.common.expected_outputs[0],
    ):
        assert value["nested"] == (value["nested"][0],)
        with pytest.raises(TypeError):
            value["nested"] = ()
