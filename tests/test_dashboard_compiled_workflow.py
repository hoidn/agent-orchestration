"""Dashboard coverage for the persisted Workflow Lisp surface read model."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from orchestrator.dashboard.projection import RunProjector
from orchestrator.dashboard.scanner import RunScanner
from orchestrator.dashboard.server import DashboardApp
from orchestrator.runtime_observability import record_compiled_frontend_provenance
from orchestrator.workflow.persisted_surface import (
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    persisted_surface_sha256,
)
from orchestrator.workflow.surface_ast import SurfaceStepKind
from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle


FINGERPRINT = "0123456789abcdef"
ENTRY_WORKFLOW = "dashboard_fixture::entry"
CHILD_WORKFLOW = "dashboard_fixture::child"
REPO_ROOT = Path(__file__).resolve().parent.parent
LISP_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"


def _write_real_imported_bundle_mix_run(
    workspace: Path,
    *,
    run_id: str = "run1",
):
    fixture_root = workspace / "tests" / "fixtures" / "workflow_lisp"
    source_root = fixture_root / "modules" / "valid" / "imported_bundle_mix"
    cli_root = fixture_root / "cli"
    shutil.copytree(
        LISP_FIXTURES / "modules" / "valid" / "imported_bundle_mix",
        source_root,
    )
    shutil.copytree(LISP_FIXTURES / "cli", cli_root)
    prompt = fixture_root / "valid" / "prompts" / "implementation" / "execute.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        LISP_FIXTURES / "valid" / "prompts" / "implementation" / "execute.md",
        prompt,
    )
    source_path = source_root / "neurips" / "entry.orc"
    result = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(source_root,),
            entry_workflow="orchestrate",
            provider_externs_path=cli_root / "providers.json",
            prompt_externs_path=cli_root / "prompts.json",
            imported_workflow_bundles_path=cli_root
            / "imported_workflow_bundles.json",
            command_boundaries_path=cli_root / "commands.json",
            workspace_root=workspace,
        )
    )
    state: dict[str, object] = {
        "run_id": run_id,
        "status": "completed",
        "workflow_file": str(source_path.relative_to(workspace)),
    }
    record_compiled_frontend_provenance(state, result.validated_bundle.provenance)
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
    return result, source_path, state


def _write_compiled_run(
    workspace: Path,
    *,
    run_id: str = "run1",
) -> tuple[Path, dict[str, object]]:
    source_path = workspace / "workflows" / "dashboard_fixture.orc"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("(module dashboard_fixture)\n", encoding="utf-8")

    build_root = workspace / ".orchestrate" / "build" / FINGERPRINT
    build_root.mkdir(parents=True, exist_ok=True)
    source_map_path = build_root / "source_map.json"
    source_map_path.write_text("{}\n", encoding="utf-8")
    lowered_path = build_root / "lowered_workflows.json"
    lowered_path.write_text(
        json.dumps(
            {
                "modules": {
                    "dashboard_fixture": {
                        "workflows": [
                            {
                                "workflow_name": ENTRY_WORKFLOW,
                                "display_name": "entry",
                                "step_ids": ["visit_items", "call_child"],
                                "authored_mapping": {
                                    "version": "2.14",
                                    "name": ENTRY_WORKFLOW,
                                    "steps": [
                                        {
                                            "name": "VisitItems",
                                            "id": "visit_items",
                                            "for_each": {
                                                "items": ["one"],
                                                "as": "item",
                                                "steps": [
                                                    {
                                                        "name": "ReviewItem",
                                                        "provider": "reviewer",
                                                    }
                                                ],
                                            },
                                        },
                                        {
                                            "name": "CallChild",
                                            "id": "call_child",
                                            "call": CHILD_WORKFLOW,
                                        },
                                    ],
                                },
                            },
                            {
                                "workflow_name": CHILD_WORKFLOW,
                                "display_name": "child",
                                "step_ids": ["child_command"],
                                "authored_mapping": {
                                    "version": "2.14",
                                    "name": CHILD_WORKFLOW,
                                    "steps": [
                                        {
                                            "name": "ChildCommand",
                                            "id": "child_command",
                                            "command": ["python", "child.py"],
                                        }
                                    ],
                                },
                            },
                        ]
                    }
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "workflow_lisp_build.v1",
        "fingerprint": FINGERPRINT,
        "source_path": str(source_path.resolve()),
        "entry_workflow": ENTRY_WORKFLOW,
        "entry_module": "dashboard_fixture",
        "compiled_module_names": ["dashboard_fixture"],
        "validated_bundle_names": [CHILD_WORKFLOW, ENTRY_WORKFLOW],
        "artifact_paths": {
            "lowered_workflows": f"build/{FINGERPRINT}/lowered_workflows.json",
            "source_map": f"build/{FINGERPRINT}/source_map.json",
        },
        "artifact_status": {
            "lowered_workflows": "emitted",
            "source_map": "emitted",
        },
        "diagnostic_count": 0,
        "shared_validation_status": "validated",
        "source_map_schema_version": "workflow_lisp_source_map.v1",
    }
    (build_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    state = {
        "run_id": run_id,
        "status": "completed",
        "workflow_file": str(source_path.relative_to(workspace)),
        "runtime_observability": {
            "compiled_frontend": {
                "frontend_kind": "workflow_lisp",
                "frontend_build_root": f"{build_root.resolve().as_posix()}/",
                "frontend_source_trace_path": str(source_map_path.resolve()),
                "frontend_entry_workflow": ENTRY_WORKFLOW,
                "source_map_schema_version": "workflow_lisp_source_map.v1",
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
        "selector-run"
    ) == 1
    assert set(structure.nodes) == {
        "neurips/entry::orchestrate",
        "neurips/helper::provider-attempt",
        "selector-run",
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
    step = payload["nodes"]["selector-run"]["steps"][0]
    step["asset_depends_on"] = [{"nested": ["asset"]}]
    step["common"]["publishes"] = [{"nested": ["publish"]}]
    step["common"]["consumes"] = [{"nested": ["consume"]}]
    step["common"]["expected_outputs"] = [{"nested": ["output"]}]

    graph = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(payload)
    )
    decoded = graph.nodes["selector-run"].steps[0]

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
        "orchestrator.loader.WorkflowLoader.load_bundle",
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
        is SurfaceStepKind.COMMAND


def test_projector_deduplicates_identical_linker_workflow_closures(tmp_path: Path):
    _write_real_imported_bundle_mix_run(tmp_path)

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    structure = detail.workflow_structure
    assert structure is not None
    assert tuple(structure.nodes).count("selector-run") == 1
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
    assert '<span class="workflow-name">EmitImportedReport</span>' in body
    assert '<span class="workflow-kind">command</span>' in body


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
