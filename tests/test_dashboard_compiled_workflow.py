"""Dashboard coverage for the persisted Workflow Lisp surface read model."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.dashboard.projection import RunProjector
from orchestrator.dashboard.scanner import RunScanner
from orchestrator.dashboard.server import DashboardApp
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


def _write_compiled_run(
    workspace: Path,
    *,
    run_id: str = "run1",
) -> tuple[Path, dict[str, object]]:
    source_path = workspace / "workflows" / "dashboard_fixture.orc"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"historical reader fixture source placeholder\n")
    build_root = workspace / ".orchestrate" / "build" / FINGERPRINT
    state = {
        "run_id": run_id,
        "status": "completed",
        "workflow_file": str(source_path.relative_to(workspace)),
        "runtime_observability": {
            "compiled_frontend": {
                "frontend_kind": "workflow_lisp",
                "frontend_build_root": f".orchestrate/build/{FINGERPRINT}/",
                "frontend_entry_workflow": ENTRY_WORKFLOW,
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
    return build_root, state


def _scan_one(workspace: Path):
    return RunScanner([workspace]).scan().runs[0]


def _write_reanchored_surface(
    workspace: Path,
    result,
    state: dict[str, object],
    payload: bytes,
) -> None:
    surface_path = result.artifact_paths["persisted_workflow_surface"]
    surface_path.write_bytes(payload)
    digest = persisted_surface_sha256(payload)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest["persisted_workflow_surface"]["sha256"] = digest
    result.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    compiled = state["runtime_observability"]["compiled_frontend"]
    compiled["persisted_workflow_surface"]["sha256"] = digest
    run_root = workspace / ".orchestrate" / "runs" / "run1"
    (run_root / "state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_projector_decodes_real_persisted_surface_with_external_import_closure(
    tmp_path: Path,
):
    _write_real_imported_bundle_mix_run(tmp_path)

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    structure = detail.workflow_structure
    assert structure is not None
    assert structure.entry_workflow == "neurips/entry::orchestrate"
    assert [node.workflow_name for node in structure.nodes.values()].count(
        "imported_selector::selector-run"
    ) == 1
    assert set(structure.nodes) == {
        "imported_selector::selector-run",
        "neurips/entry::orchestrate",
        "neurips/helper::provider-attempt",
    }


def test_projector_rejects_valid_json_persisted_surface_tampering(tmp_path: Path):
    result, _source_path, _state = _write_real_imported_bundle_mix_run(tmp_path)
    graph_path = result.artifact_paths["persisted_workflow_surface"]
    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    entry = payload["nodes"][payload["entry_workflow"]]
    entry["steps"][0]["name"] = "TamperedButValidJson"
    graph_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.workflow_structure is None
    assert any("digest" in warning for warning in detail.warnings)


@pytest.mark.parametrize("record_absolute_path", [False, True])
def test_projector_reads_persisted_surface_after_orc_source_is_deleted(
    tmp_path: Path,
    record_absolute_path: bool,
):
    _result, source_path, state = _write_real_imported_bundle_mix_run(tmp_path)
    if record_absolute_path:
        state["workflow_file"] = str(source_path.resolve())
        state_path = tmp_path / ".orchestrate" / "runs" / "run1" / "state.json"
        state_path.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    source_path.unlink()

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.workflow_structure is not None
    assert detail.workflow_structure.entry_workflow == "neurips/entry::orchestrate"


def test_projector_reads_bound_surface_without_parsing_edited_orc_source(tmp_path: Path):
    _result, source_path, _state = _write_real_imported_bundle_mix_run(tmp_path)
    source_path.write_text("this is no longer valid Workflow Lisp\n", encoding="utf-8")

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.workflow_structure is not None
    assert detail.workflow_structure.entry_workflow == "neurips/entry::orchestrate"


def test_projector_rejects_duplicate_key_surface_with_matching_binding(tmp_path: Path):
    result, _source_path, state = _write_real_imported_bundle_mix_run(tmp_path)
    canonical = result.artifact_paths["persisted_workflow_surface"].read_bytes()
    duplicate = canonical[:-2] + (
        b',"schema_version":"persisted_workflow_surface_graph.v1"}\n'
    )
    _write_reanchored_surface(tmp_path, result, state, duplicate)

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.workflow_structure is None
    assert any("duplicate JSON key" in warning for warning in detail.warnings)


@pytest.mark.parametrize("digest", ["sha256:" + "a" * 63, "sha256:" + "A" * 64])
def test_projector_rejects_malformed_surface_binding_digest(
    tmp_path: Path,
    digest: str,
):
    _result, _source_path, state = _write_real_imported_bundle_mix_run(tmp_path)
    compiled = state["runtime_observability"]["compiled_frontend"]
    compiled["persisted_workflow_surface"]["sha256"] = digest
    state_path = tmp_path / ".orchestrate" / "runs" / "run1" / "state.json"
    state_path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.workflow_structure is None
    assert any("digest syntax" in warning for warning in detail.warnings)


def test_projector_rejects_orc_source_path_traversal(tmp_path: Path):
    _result, _source_path, state = _write_real_imported_bundle_mix_run(tmp_path)
    state["workflow_file"] = "../outside.orc"
    state_path = tmp_path / ".orchestrate" / "runs" / "run1" / "state.json"
    state_path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.workflow_structure is None
    assert any("outside workspace" in warning for warning in detail.warnings)


def test_projector_rejects_orc_source_symlink_ancestor_escape(tmp_path: Path):
    _result, source_path, _state = _write_real_imported_bundle_mix_run(tmp_path)
    source_parent = source_path.parent
    outside = tmp_path.parent / f"{tmp_path.name}-outside-source"
    source_parent.rename(outside)
    source_parent.symlink_to(outside, target_is_directory=True)

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.workflow_structure is None
    assert any("outside workspace" in warning for warning in detail.warnings)


def test_projector_rejects_persisted_surface_symlink_escape(tmp_path: Path):
    result, _source_path, _state = _write_real_imported_bundle_mix_run(tmp_path)
    surface_path = result.artifact_paths["persisted_workflow_surface"]
    outside = tmp_path.parent / f"{tmp_path.name}-outside-surface.json"
    outside.write_bytes(surface_path.read_bytes())
    surface_path.unlink()
    surface_path.symlink_to(outside)

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.workflow_structure is None
    assert any("escapes" in warning for warning in detail.warnings)


def test_projector_rejects_persisted_manifest_symlink_escape(tmp_path: Path):
    result, _source_path, _state = _write_real_imported_bundle_mix_run(tmp_path)
    manifest_path = result.manifest_path
    outside = tmp_path.parent / f"{tmp_path.name}-outside-manifest.json"
    outside.write_bytes(manifest_path.read_bytes())
    manifest_path.unlink()
    manifest_path.symlink_to(outside)

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.workflow_structure is None
    assert any("manifest" in warning and "unsafe" in warning for warning in detail.warnings)


@pytest.mark.parametrize(
    "tamper",
    ["state_entry_only", "manifest_entry_only", "both_top_level_entries"],
)
def test_projector_rejects_top_level_entry_binding_tamper(
    tmp_path: Path,
    tamper: str,
):
    result, _source_path, state = _write_real_imported_bundle_mix_run(tmp_path)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    if tamper in {"state_entry_only", "both_top_level_entries"}:
        compiled = state["runtime_observability"]["compiled_frontend"]
        compiled["frontend_entry_workflow"] = "tampered::entry"
        state_path = tmp_path / ".orchestrate" / "runs" / "run1" / "state.json"
        state_path.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if tamper in {"manifest_entry_only", "both_top_level_entries"}:
        manifest["entry_workflow"] = "tampered::entry"
        result.manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.workflow_structure is None
    assert any("entry workflow" in warning for warning in detail.warnings)


def test_projector_rejects_reanchored_graph_entry_source_path_mismatch(
    tmp_path: Path,
):
    result, _source_path, state = _write_real_imported_bundle_mix_run(tmp_path)
    payload = json.loads(
        result.artifact_paths["persisted_workflow_surface"].read_text(encoding="utf-8")
    )
    payload["nodes"][payload["entry_workflow"]]["workflow_path"] = str(
        tmp_path / "other" / "entry.orc"
    )
    _write_reanchored_surface(
        tmp_path,
        result,
        state,
        canonical_persisted_surface_bytes(payload),
    )

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.workflow_structure is None
    assert any("entry source path" in warning for warning in detail.warnings)


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


def test_projector_does_not_enter_frontend_or_lowering_for_persisted_orc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _write_real_imported_bundle_mix_run(tmp_path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("fresh frontend or lowering was entered")

    for target in (
        "orchestrator.workflow_lisp.compiler.compile_stage3_entrypoint",
        "orchestrator.workflow_lisp.reader.read_sexpr_file",
        "orchestrator.workflow_lisp.syntax.build_syntax_module",
        "orchestrator.workflow_lisp.workflows.elaborate_workflow_definitions",
    ):
        monkeypatch.setattr(target, forbidden)

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.workflow_structure is not None


def test_old_orc_run_without_surface_anchor_degrades_to_observed_summaries(
    tmp_path: Path,
):
    _write_compiled_run(tmp_path)

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.workflow_structure is None
    assert any(
        "legacy persisted compiled frontend has no persisted workflow surface anchor"
        in warning
        for warning in detail.warnings
    )
    assert not any(
        term in warning
        for warning in detail.warnings
        for term in ("partial or malformed", "digest does not match", "graph is invalid")
    )


def test_projector_decodes_orc_persisted_typed_surface_graph(tmp_path: Path):
    _write_real_imported_bundle_mix_run(tmp_path)

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    structure = detail.workflow_structure
    assert structure is not None
    entry = structure.entry_node
    assert entry.name == "neurips/entry::orchestrate"
    assert [step.kind for step in entry.steps] == [
        SurfaceStepKind.CALL,
        SurfaceStepKind.CALL,
    ]
    assert structure.imported_node(entry, entry.steps[0].call_alias).steps[0].kind \
        is SurfaceStepKind.PROVIDER
    assert structure.imported_node(entry, entry.steps[1].call_alias).steps[0].kind \
        is SurfaceStepKind.MATERIALIZE_ARTIFACTS


def test_projector_preserves_three_node_persisted_import_closure(tmp_path: Path):
    _write_real_imported_bundle_mix_run(tmp_path)

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    structure = detail.workflow_structure
    assert structure is not None
    assert tuple(structure.nodes).count("imported_selector::selector-run") == 1
    assert len(structure.nodes) == 3


def test_summary_endpoint_renders_orc_typed_structure_and_imported_call(tmp_path: Path):
    _write_real_imported_bundle_mix_run(tmp_path)

    response = DashboardApp(RunScanner([tmp_path])).handle(
        "GET", "/runs/w0/run1/summaries"
    )

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "Workflow: neurips/entry::orchestrate" in body
    assert '<span class="workflow-kind">call neurips/helper::provider-attempt</span>' in body
    assert '<span class="workflow-name">neurips/helper::provider-attempt__result</span>' in body
    assert '<span class="workflow-kind">call selector-run</span>' in body
    assert (
        '<span class="workflow-name">'
        "imported_selector::selector-run__return"
        "</span>"
    ) in body
    assert '<span class="workflow-kind">materialize_artifacts</span>' in body


def test_summary_endpoint_renders_persisted_finalization_and_adjudicated_links(
    tmp_path: Path,
):
    result, source_path, state = _write_real_imported_bundle_mix_run(tmp_path)
    for relative in (
        "candidate-asset.md",
        "evaluator-asset.md",
        "rubric-asset.md",
    ):
        (source_path.parent / relative).write_text(relative + "\n", encoding="utf-8")
    for relative in (
        "inputs/candidate.md",
        "inputs/evaluator.md",
        "inputs/rubric.md",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative + "\n", encoding="utf-8")
    surface_path = result.artifact_paths["persisted_workflow_surface"]
    payload = json.loads(surface_path.read_text(encoding="utf-8"))
    final_step = json.loads(
        json.dumps(payload["nodes"]["neurips/helper::provider-attempt"]["steps"][0])
    )
    final_step.update(
        name="FinalAdjudication",
        step_id="final_adjudication",
        kind="adjudicated_provider",
        adjudicated_provider={
            "candidates": [
                {
                    "id": "candidate-a",
                    "asset_file": "candidate-asset.md",
                    "input_file": "inputs/candidate.md",
                }
            ],
            "evaluator": {
                "asset_file": "evaluator-asset.md",
                "input_file": "inputs/evaluator.md",
                "rubric_asset_file": "rubric-asset.md",
                "rubric_input_file": "inputs/rubric.md",
            },
        },
    )
    payload["nodes"][payload["entry_workflow"]]["finalization_steps"] = [final_step]
    _write_reanchored_surface(
        tmp_path,
        result,
        state,
        canonical_persisted_surface_bytes(payload),
    )

    response = DashboardApp(RunScanner([tmp_path])).handle(
        "GET", "/runs/w0/run1/summaries"
    )

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert '<span class="workflow-name">finally</span>' in body
    assert '<span class="workflow-name">FinalAdjudication</span>' in body
    assert "candidate-asset.md" in body
    assert "inputs/candidate.md" in body
    assert "evaluator-asset.md" in body
    assert "inputs/evaluator.md" in body
    assert "rubric-asset.md" in body
    assert "inputs/rubric.md" in body


@pytest.mark.parametrize(
    ("damage", "expected_warning"),
    [
        ("missing_manifest", "manifest is missing or unsafe"),
        ("malformed_partial_anchor", "partial or malformed"),
        ("state_manifest_anchor_mismatch", "anchors do not match"),
        ("noncanonical_surface", "bytes are not canonical"),
    ],
)
def test_orc_persisted_build_damage_falls_back_to_observed_summaries(
    tmp_path: Path,
    damage: str,
    expected_warning: str,
):
    result, _source_path, state = _write_real_imported_bundle_mix_run(tmp_path)
    build_root = result.build_root
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    if damage == "missing_manifest":
        (build_root / "manifest.json").unlink()
    elif damage == "malformed_partial_anchor":
        compiled = state["runtime_observability"]["compiled_frontend"]
        compiled["persisted_workflow_surface"].pop("sha256")
        (run_root / "state.json").write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    elif damage == "state_manifest_anchor_mismatch":
        compiled = state["runtime_observability"]["compiled_frontend"]
        compiled["persisted_workflow_surface"]["entry_workflow"] = "other"
        (run_root / "state.json").write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        surface_path = result.artifact_paths["persisted_workflow_surface"]
        surface = json.loads(surface_path.read_text(encoding="utf-8"))
        payload = (json.dumps(surface, indent=2, sort_keys=True) + "\n").encode()
        surface_path.write_bytes(payload)
        digest = persisted_surface_sha256(payload)
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        manifest["persisted_workflow_surface"]["sha256"] = digest
        result.manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        compiled = state["runtime_observability"]["compiled_frontend"]
        compiled["persisted_workflow_surface"]["sha256"] = digest
        (run_root / "state.json").write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    summaries = build_root.parents[1] / "runs" / "run1" / "summaries"
    (summaries / "index.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_summary_index/v1",
                "entries": [{"step_name": "ObservedOnly", "kind": "provider"}],
            }
        ),
        encoding="utf-8",
    )

    detail = RunProjector().project_detail(_scan_one(tmp_path))
    response = DashboardApp(RunScanner([tmp_path])).handle(
        "GET", "/runs/w0/run1/summaries"
    )

    body = response.body.decode("utf-8")
    assert detail.workflow_structure is None
    assert any(expected_warning in warning for warning in detail.warnings)
    assert not any("legacy persisted compiled frontend" in warning for warning in detail.warnings)
    assert "Observed summary sequence" in body
    assert "ObservedOnly" in body
    assert "VisitItems" not in body
