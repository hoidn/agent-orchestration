from __future__ import annotations

import copy
import hashlib
import importlib
import json
import re
from dataclasses import asdict, is_dataclass, replace
from enum import Enum
from pathlib import Path

import pytest

import orchestrator.workflow.loaded_bundle as loaded_bundle_helpers
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
import orchestrator.workflow_lisp.compiler as workflow_lisp_compiler
from orchestrator.workflow.loaded_bundle import workflow_managed_write_root_inputs
from orchestrator.workflow_lisp.compiler import compile_stage1_entrypoint, compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from orchestrator.workflow_lisp.modules import resolve_module_graph
from orchestrator.workflow_lisp.phase_family_boundary import (
    build_design_delta_boundary_authority_expected_rows,
)
from orchestrator.workflow_lisp.source_map import build_source_map_document
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.workflows import (
    CertifiedAdapterBinding,
    ExternalToolBinding,
    build_command_boundary_environment,
)
from orchestrator.workflow_lisp.wcc.route import LoweringRoute


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
CLI_FIXTURES = FIXTURES / "cli"
DESIGN_DELTA_MIGRATION_INPUTS = (
    REPO_ROOT / "workflows" / "examples" / "inputs" / "workflow_lisp_migrations"
)
DESIGN_DELTA_BOUNDARY_AUTHORITY_PATH = (
    DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.boundary_authority.json"
)
DESIGN_DELTA_VALUE_FLOW_CENSUS_PATH = (
    DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.value_flow_census.json"
)
DESIGN_DELTA_CONSUMER_RENDERING_CENSUS_PATH = (
    DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.consumer_rendering_census.json"
)
DESIGN_DELTA_COMPATIBILITY_BRIDGES_PATH = (
    DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.compatibility_bridges.json"
)
DESIGN_DELTA_RESUME_PLUMBING_RETIREMENT_PATH = (
    DESIGN_DELTA_MIGRATION_INPUTS
    / "design_delta_parent_drain.resume_plumbing_retirement.json"
)
# This checked-in candidate remains the authoritative proof source for the
# imported-child prerequisite until the shipping library module lands its
# separate parent-callable `run-work-item` export.
DESIGN_DELTA_WORK_ITEM_CANDIDATE_ROOT = FIXTURES / "valid" / "design_delta_work_item_runtime"
ENTRYPOINT = FIXTURES / "modules" / "valid" / "imported_bundle_mix" / "neurips" / "entry.orc"
SOURCE_ROOT = FIXTURES / "modules" / "valid" / "imported_bundle_mix"
IMPORTED_STDLIB_HELPER_ROOT = FIXTURES / "modules" / "valid" / "imported_stdlib_macro_payload_helper_composition"
IMPORTED_STDLIB_HELPER_ENTRY = (
    IMPORTED_STDLIB_HELPER_ROOT / "imported_stdlib_macro_payload_helper_composition" / "entry.orc"
)
PURE_EXPR_SELECTOR_FIXTURE = FIXTURES / "valid" / "pure_expr_selector_action_projection.orc"
MATERIALIZE_VIEW_ALLOCATED_TARGET_FIXTURE = FIXTURES / "valid" / "materialize_view_allocated_target.orc"
ENTRY_PUBLICATION_RUNTIME_FIXTURE = FIXTURES / "valid" / "entry_publication_runtime.orc"
ITEM_CTX_CHILD_PHASE_REUSE_FIXTURE = (
    FIXTURES / "valid" / "design_delta_item_ctx_child_phase_reuse.orc"
)
STDLIB_HIDDEN_COMPATIBILITY_BRIDGE_FIXTURE = (
    FIXTURES / "valid" / "drain_stdlib_backlog_drain_hidden_compatibility_bridge.orc"
)
HIDDEN_COMPATIBILITY_BRIDGE_PUBLIC_BOUNDARY_FIXTURE = (
    FIXTURES
    / "invalid"
    / "backlog_drain_hidden_compatibility_bridge_public_boundary_invalid.orc"
)
HIDDEN_COMPATIBILITY_BRIDGE_REREAD_POINTER_AUTHORITY_FIXTURE = (
    FIXTURES
    / "invalid"
    / "backlog_drain_hidden_compatibility_bridge_reread_pointer_authority_invalid.json"
)
LEXICAL_CHECKPOINT_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_shadow_points.orc"
LEXICAL_POLICY_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_effect_policies.orc"
LEXICAL_RESTORE_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_restore_regions.orc"
RUNTIME_CLOSURE_MARKERS = (
    "workflow_lisp_runtime_closure",
    "closure_families",
    "InvokeClosure",
    "Closure[",
    "runtime_closure",
)


def _build_module():
    return importlib.import_module("orchestrator.workflow_lisp.build")


def _drain_command_boundaries():
    return build_command_boundary_environment(
        {
            "select_next_item": CertifiedAdapterBinding(
                name="select_next_item",
                stable_command=("python", "scripts/select_next_item.py"),
                input_contract={"type": "object"},
                output_type_name="SelectionResult",
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("select_next_item_ok",),
                negative_fixture_ids=("select_next_item_bad",),
            ),
            "execute_selected_item": CertifiedAdapterBinding(
                name="execute_selected_item",
                stable_command=("python", "scripts/execute_selected_item.py"),
                input_contract={"type": "object"},
                output_type_name="SelectedItemResult",
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("execute_selected_item_ok",),
                negative_fixture_ids=("execute_selected_item_bad",),
            ),
            "draft_gap_item": CertifiedAdapterBinding(
                name="draft_gap_item",
                stable_command=("python", "scripts/draft_gap_item.py"),
                input_contract={"type": "object"},
                output_type_name="GapResult",
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("draft_gap_item_ok",),
                negative_fixture_ids=("draft_gap_item_bad",),
            ),
        }
    )


def _link_fixture_module_into_source_root(path: Path, *, tmp_path: Path) -> Path:
    source = path.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None, f"fixture is missing defmodule: {path}"
    resolved_module_name = module_match.group(1)
    module_path = (tmp_path / Path(*resolved_module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    return module_path


def _compile_linked_hidden_compatibility_bridge_fixture(tmp_path: Path):
    module_path = _link_fixture_module_into_source_root(
        STDLIB_HIDDEN_COMPATIBILITY_BRIDGE_FIXTURE,
        tmp_path=tmp_path,
    )
    return compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        command_boundaries=_drain_command_boundaries().bindings_by_name,
        workspace_root=tmp_path,
        validate_shared=True,
    )


def _compile_linked_hidden_compatibility_bridge_public_boundary_fixture(
    tmp_path: Path,
):
    module_path = _link_fixture_module_into_source_root(
        HIDDEN_COMPATIBILITY_BRIDGE_PUBLIC_BOUNDARY_FIXTURE,
        tmp_path=tmp_path,
    )
    return compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        command_boundaries=_drain_command_boundaries().bindings_by_name,
        workspace_root=tmp_path,
        validate_shared=True,
    )


def _build_request(tmp_path: Path, *, manifest_path: Path | None = None):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return request_cls(
        source_path=ENTRYPOINT,
        source_roots=(SOURCE_ROOT, tmp_path),
        entry_workflow="orchestrate",
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=manifest_path or (CLI_FIXTURES / "imported_workflow_bundles.json"),
        command_boundaries_path=CLI_FIXTURES / "commands.json",
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _imported_stdlib_helper_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return request_cls(
        source_path=IMPORTED_STDLIB_HELPER_ENTRY,
        source_roots=(IMPORTED_STDLIB_HELPER_ROOT,),
        entry_workflow="run-drain-like",
        provider_externs_path=None,
        prompt_externs_path=None,
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _design_delta_parent_drain_request(
    tmp_path: Path,
    *,
    command_boundaries_path: Path | None = None,
):
    run_state_path = tmp_path / "state" / "run_state.json"
    run_state_path.parent.mkdir(parents=True, exist_ok=True)
    if not run_state_path.exists():
        run_state_path.write_text("{}\n", encoding="utf-8")
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return request_cls(
        source_path=REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        entry_workflow="lisp_frontend_design_delta/drain::drain",
        provider_externs_path=DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.providers.json",
        prompt_externs_path=DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.prompts.json",
        imported_workflow_bundles_path=None,
        command_boundaries_path=command_boundaries_path
        or (DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.commands.json"),
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _design_delta_fingerprint_context(
    tmp_path: Path,
    *,
    pair_manifest_path: Path | None = None,
):
    build = _build_module()
    observability = importlib.import_module(
        "orchestrator.workflow_lisp.observability_summaries"
    )
    request = _design_delta_parent_drain_request(tmp_path)
    resolved_request = build._resolve_request(request)
    provider_externs = build._load_string_mapping(
        resolved_request.provider_externs_path,
        label="provider externs manifest",
    )
    prompt_externs = build._load_prompt_extern_mapping(
        resolved_request.prompt_externs_path
    )
    command_boundary_manifest = build._load_command_boundaries_manifest_payload(
        resolved_request.command_boundaries_path,
    )
    command_boundaries = build._parse_command_boundaries_manifest(
        command_boundary_manifest,
        manifest_path=resolved_request.command_boundaries_path,
    )
    compile_result = compile_stage3_entrypoint(
        resolved_request.source_path,
        source_roots=resolved_request.source_roots,
        entry_workflow=resolved_request.entry_workflow,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        imported_workflow_bundles={},
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=resolved_request.workspace_root,
        lint_profile=resolved_request.lint_profile,
        lowering_route=resolved_request.lowering_route,
    )
    entry_selection = build._select_entry_workflow(
        compile_result,
        requested_name=resolved_request.entry_workflow,
        source_path=resolved_request.source_path,
    )
    boundary_authority_registry = build._maybe_load_design_delta_boundary_authority_registry(
        entry_workflow=entry_selection.canonical_name,
    )
    value_flow_census = build._maybe_load_design_delta_value_flow_census(
        entry_workflow=entry_selection.canonical_name,
    )
    consumer_rendering_census = build._maybe_load_design_delta_consumer_rendering_census(
        entry_workflow=entry_selection.canonical_name,
        value_flow_census=value_flow_census,
    )
    if pair_manifest_path is None:
        pair_manifest_path = (
            DESIGN_DELTA_MIGRATION_INPUTS
            / "design_delta_parent_drain.observability_old_writer_comparisons.json"
        )
    observability_pair_manifest = observability.load_old_writer_pair_manifest(
        pair_manifest_path,
        consumer_rendering_census=consumer_rendering_census,
    )
    resume_plumbing_retirement_manifest = (
        build._maybe_load_design_delta_resume_plumbing_retirement_manifest(
            entry_workflow=entry_selection.canonical_name,
        )
    )
    return {
        "build": build,
        "request": resolved_request,
        "compile_result": compile_result,
        "entry_selection": entry_selection,
        "provider_externs": provider_externs,
        "prompt_externs": prompt_externs,
        "command_boundary_manifest": command_boundary_manifest,
        "boundary_authority_registry": boundary_authority_registry,
        "value_flow_census": value_flow_census,
        "consumer_rendering_census": consumer_rendering_census,
        "observability_pair_manifest": observability_pair_manifest,
        "resume_plumbing_retirement_manifest": resume_plumbing_retirement_manifest,
    }


def _build_pure_expr_selector_projection(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return build.build_frontend_bundle(
        request_cls(
            source_path=PURE_EXPR_SELECTOR_FIXTURE,
            source_roots=(FIXTURES / "valid",),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=None,
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _build_materialize_view_allocated_target(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return build.build_frontend_bundle(
        request_cls(
            source_path=MATERIALIZE_VIEW_ALLOCATED_TARGET_FIXTURE,
            source_roots=(FIXTURES / "valid",),
            entry_workflow="orchestrate",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _build_lexical_checkpoint_fixture(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return build.build_frontend_bundle(
        request_cls(
            source_path=LEXICAL_CHECKPOINT_FIXTURE,
            source_roots=(FIXTURES / "valid",),
            entry_workflow="orchestrate",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _build_lexical_policy_fixture(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return build.build_frontend_bundle(
        request_cls(
            source_path=LEXICAL_POLICY_FIXTURE,
            source_roots=(FIXTURES / "valid",),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=None,
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _build_lexical_restore_fixture(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return build.build_frontend_bundle(
        request_cls(
            source_path=LEXICAL_RESTORE_FIXTURE,
            source_roots=(FIXTURES / "valid",),
            entry_workflow="orchestrate",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _build_entry_publication_fixture(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return build.build_frontend_bundle(
        request_cls(
            source_path=ENTRY_PUBLICATION_RUNTIME_FIXTURE,
            source_roots=(FIXTURES / "valid",),
            entry_workflow="entry-publication-runtime",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _build_item_ctx_child_phase_reuse_fixture(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return build.build_frontend_bundle(
        request_cls(
            source_path=ITEM_CTX_CHILD_PHASE_REUSE_FIXTURE,
            source_roots=(FIXTURES / "valid", REPO_ROOT / "workflows" / "library"),
            entry_workflow="design_delta_item_ctx_child_phase_reuse::run-entry",
            provider_externs_path=DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.providers.json",
            prompt_externs_path=DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.prompts.json",
            imported_workflow_bundles_path=None,
            command_boundaries_path=DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _build_item_ctx_child_phase_reuse_branching_fixture(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    return build.build_frontend_bundle(
        request_cls(
            source_path=ITEM_CTX_CHILD_PHASE_REUSE_FIXTURE,
            source_roots=(FIXTURES / "valid", REPO_ROOT / "workflows" / "library"),
            entry_workflow=(
                "design_delta_item_ctx_child_phase_reuse::run-entry-branching-terminal-reprojection"
            ),
            provider_externs_path=DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.providers.json",
            prompt_externs_path=DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.prompts.json",
            imported_workflow_bundles_path=None,
            command_boundaries_path=DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _build_design_delta_parent_drain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    registry_payload: dict[str, object] | None = None,
    value_flow_census_payload: dict[str, object] | None = None,
    consumer_rendering_census_payload: dict[str, object] | None = None,
    resume_plumbing_retirement_manifest_payload: dict[str, object] | None = None,
    command_boundaries_path: Path | None = None,
    run_state_path: Path | None = None,
    drain_summary_path: Path | None = None,
    design_gap_summary_root: Path | None = None,
    architecture_index_path: Path | None = None,
    target_design_path: Path | None = None,
    parity_report_json_path: Path | None = None,
    parity_report_markdown_path: Path | None = None,
    parity_index_path: Path | None = None,
):
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    registry_path = None
    census_path: Path | None = None
    if registry_payload is not None:
        registry_path = tmp_path / "design_delta_parent_drain.boundary_authority.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(json.dumps(registry_payload, indent=2) + "\n", encoding="utf-8")
        monkeypatch.setattr(
            build,
            "DESIGN_DELTA_PARENT_DRAIN_BOUNDARY_AUTHORITY_PATH",
            registry_path,
            raising=False,
        )
    if value_flow_census_payload is not None:
        census_path = tmp_path / "design_delta_parent_drain.value_flow_census.json"
        census_path.parent.mkdir(parents=True, exist_ok=True)
        census_path.write_text(
            json.dumps(value_flow_census_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            build,
            "DESIGN_DELTA_PARENT_DRAIN_VALUE_FLOW_CENSUS_PATH",
            census_path,
            raising=False,
        )
        if consumer_rendering_census_payload is None:
            consumer_rendering_census_payload = _load_design_delta_consumer_rendering_census()
        source_census = consumer_rendering_census_payload.setdefault("source_census", {})
        if not isinstance(source_census, dict):
            source_census = {}
            consumer_rendering_census_payload["source_census"] = source_census
        source_census["path"] = str(census_path)
        source_census.setdefault(
            "schema_version",
            "workflow_lisp_private_runtime_value_flow_census.v1",
        )
    if resume_plumbing_retirement_manifest_payload is not None or census_path is not None:
        resume_path = tmp_path / "design_delta_parent_drain.resume_plumbing_retirement.json"
        resume_payload = (
            resume_plumbing_retirement_manifest_payload
            if resume_plumbing_retirement_manifest_payload is not None
            else _aligned_design_delta_resume_plumbing_retirement_manifest(
                census_path=census_path or DESIGN_DELTA_VALUE_FLOW_CENSUS_PATH
            )
        )
        resume_path.write_text(
            json.dumps(resume_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            build,
            "DESIGN_DELTA_PARENT_DRAIN_RESUME_PLUMBING_RETIREMENT_PATH",
            resume_path,
            raising=False,
        )
    if consumer_rendering_census_payload is not None:
        consumer_path = tmp_path / "design_delta_parent_drain.consumer_rendering_census.json"
        consumer_path.parent.mkdir(parents=True, exist_ok=True)
        consumer_path.write_text(
            json.dumps(consumer_rendering_census_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            build,
            "DESIGN_DELTA_PARENT_DRAIN_CONSUMER_RENDERING_CENSUS_PATH",
            consumer_path,
            raising=False,
        )
    if run_state_path is not None:
        monkeypatch.setattr(
            build,
            "REFERENCE_FAMILY_RUN_STATE_PATH",
            run_state_path,
            raising=False,
        )
    if drain_summary_path is not None:
        monkeypatch.setattr(
            build,
            "REFERENCE_FAMILY_DRAIN_SUMMARY_PATH",
            drain_summary_path,
            raising=False,
        )
    if design_gap_summary_root is not None:
        monkeypatch.setattr(
            build,
            "REFERENCE_FAMILY_DESIGN_GAP_SUMMARY_ROOT",
            design_gap_summary_root,
            raising=False,
        )
    if architecture_index_path is not None:
        monkeypatch.setattr(
            build,
            "REFERENCE_FAMILY_ARCHITECTURE_INDEX_PATH",
            architecture_index_path,
            raising=False,
        )
    if target_design_path is not None:
        monkeypatch.setattr(
            build,
            "REFERENCE_FAMILY_TARGET_DESIGN_PATH",
            target_design_path,
            raising=False,
        )
    if parity_report_json_path is not None:
        monkeypatch.setattr(
            build,
            "REFERENCE_FAMILY_PARITY_REPORT_JSON_PATH",
            parity_report_json_path,
            raising=False,
        )
    if parity_report_markdown_path is not None:
        monkeypatch.setattr(
            build,
            "REFERENCE_FAMILY_PARITY_REPORT_MARKDOWN_PATH",
            parity_report_markdown_path,
            raising=False,
        )
    if parity_index_path is not None:
        monkeypatch.setattr(
            build,
            "REFERENCE_FAMILY_PARITY_INDEX_PATH",
            parity_index_path,
            raising=False,
        )
    return build_frontend_bundle(
        _design_delta_parent_drain_request(
            tmp_path,
            command_boundaries_path=command_boundaries_path,
        )
    )


def _load_design_delta_boundary_authority_registry() -> dict[str, object]:
    return json.loads(DESIGN_DELTA_BOUNDARY_AUTHORITY_PATH.read_text(encoding="utf-8"))


def _aligned_reference_family_drain_summary(tmp_path: Path) -> Path:
    payload = json.loads(
        (
            REPO_ROOT
            / "artifacts"
            / "work"
            / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
            / "drain-summary.json"
        ).read_text(encoding="utf-8")
    )
    run_state = json.loads(
        (
            REPO_ROOT
            / "state"
            / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
            / "drain"
            / "run_state.json"
        ).read_text(encoding="utf-8")
    )
    payload["completed_design_gaps"] = list(run_state["completed_design_gaps"])
    path = tmp_path / "reference-family-drain-summary.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _aligned_reference_family_architecture_index(tmp_path: Path) -> Path:
    source_path = (
        REPO_ROOT
        / "state"
        / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
        / "drain"
        / "iterations"
        / "10"
        / "design-gap-architect"
        / "existing-architecture-index.md"
    )
    text = source_path.read_text(encoding="utf-8").rstrip()
    run_state = json.loads(
        (
            REPO_ROOT
            / "state"
            / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
            / "drain"
            / "run_state.json"
        ).read_text(encoding="utf-8")
    )
    missing_entries: list[str] = []
    for gap_id in run_state["completed_design_gaps"]:
        relpath = (
            "docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/"
            f"{gap_id}/implementation_architecture.md"
        )
        if relpath not in text and gap_id not in text:
            missing_entries.append(f"- {relpath}")
    path = tmp_path / "reference-family-architecture-index.md"
    suffix = ("\n" + "\n".join(missing_entries)) if missing_entries else ""
    path.write_text(text + suffix + "\n", encoding="utf-8")
    return path


def _load_design_delta_value_flow_census() -> dict[str, object]:
    return json.loads(DESIGN_DELTA_VALUE_FLOW_CENSUS_PATH.read_text(encoding="utf-8"))


def _normalize_dynamic_compiled_boundary_symbol(symbol: str) -> str:
    return re.sub(r"[0-9a-f]{8,}", "<dynamic>", symbol)


def _aligned_design_delta_value_flow_census(
    tmp_path: Path | None = None,
) -> dict[str, object]:
    payload = _load_design_delta_value_flow_census()
    stale_row_id = (
        "compiled_boundary::lisp_frontend_design_delta/drain::drain::"
        "__write_root__lisp_frontend_design_delta_drain_drain__match_terminal__"
        "blocked__recorded__lisp_frontend_design_delta_transitions_"
        "record_drain_terminal_outcome_2__transition_result__result_bundle"
    )
    template_row_id = (
        "compiled_boundary::lisp_frontend_design_delta/drain::drain::"
        "__write_root__lisp_frontend_design_delta_drain_drain__match_terminal__"
        "blocked__recorded__lisp_frontend_design_delta_transitions_"
        "record_drain_terminal_outcome_2__terminal_projection__result_bundle"
    )
    replacement_row_id = (
        "compiled_boundary::lisp_frontend_design_delta/drain::drain::"
        "__write_root__lisp_frontend_design_delta_drain_drain__projected__"
        "lisp_frontend_design_delta_stdlib_adapters_project_drain_result_compat_1__"
        "match_result__blocked__condition__result_bundle"
    )
    replacement_symbol = (
        "__write_root__lisp_frontend_design_delta_drain_drain__projected__"
        "lisp_frontend_design_delta_stdlib_adapters_project_drain_result_compat_1__"
        "match_result__blocked__condition__result_bundle"
    )
    payload["rows"] = [
        row
        for row in payload["rows"]
        if row["row_id"] != stale_row_id
    ]
    existing_row_ids = {row["row_id"] for row in payload["rows"]}
    if replacement_row_id not in existing_row_ids:
        template_row = next(
            (row for row in payload["rows"] if row["row_id"] == template_row_id),
            None,
        )
        if template_row is not None:
            replacement_row = copy.deepcopy(template_row)
            replacement_row["row_id"] = replacement_row_id
            replacement_row["symbol_or_field"] = replacement_symbol
            replacement_row["path_or_contract"] = replacement_symbol
            payload["rows"].append(replacement_row)
    workflow_surfaces = set(payload["coverage"]["workflow_surfaces"])
    workflow_surfaces.add(
        "lisp_frontend_design_delta/design_gap_architect::validate-design-gap-architecture-stdlib"
    )
    payload["coverage"]["workflow_surfaces"] = sorted(workflow_surfaces)
    if tmp_path is not None:
        build = _build_module()
        request = _design_delta_parent_drain_request(tmp_path)
        command_boundary_manifest = json.loads(
            request.command_boundaries_path.read_text(encoding="utf-8")
        )
        command_boundaries = build._parse_command_boundaries_manifest(
            command_boundary_manifest,
            manifest_path=request.command_boundaries_path,
        )
        provider_externs = json.loads(
            request.provider_externs_path.read_text(encoding="utf-8")
        )
        prompt_externs = json.loads(
            request.prompt_externs_path.read_text(encoding="utf-8")
        )
        compile_result = compile_stage3_entrypoint(
            request.source_path,
            source_roots=request.source_roots,
            provider_externs=provider_externs,
            prompt_externs=prompt_externs,
            command_boundaries=command_boundaries,
            validate_shared=True,
            workspace_root=tmp_path,
        )
        source_map_payload = build._serialize_source_map(
            compile_result,
            selected_name=request.entry_workflow,
        )
        boundary_authority_registry = _aligned_design_delta_boundary_authority_registry(
            tmp_path
        )
        boundary_authority_report = _build_module()._serialize_design_delta_boundary_authority_report(
            boundary_projection_payload=build._serialize_workflow_boundary_projection(
                compile_result,
                selected_name=request.entry_workflow,
            ),
            boundary_authority_registry=boundary_authority_registry,
            source_map_payload=source_map_payload,
            value_flow_census=payload,
        )
        reconciliation = build.reconcile_value_flow_census(
            census=payload,
            checked_census_path=DESIGN_DELTA_VALUE_FLOW_CENSUS_PATH,
            checked_census_sha256=hashlib.sha256(
                DESIGN_DELTA_VALUE_FLOW_CENSUS_PATH.read_bytes()
            ).hexdigest(),
            boundary_authority_report=boundary_authority_report,
            source_map_payload=source_map_payload,
            prompt_externs=prompt_externs,
            provider_externs=provider_externs,
            command_boundary_manifest=command_boundary_manifest,
            boundary_authority_registry=boundary_authority_registry,
        )
        missing_by_key = {
                (
                    str(row["workflow_surface"]),
                    _normalize_dynamic_compiled_boundary_symbol(
                        str(row["symbol_or_field"])
                    ),
                ): row
            for row in reconciliation["missing_rows"]
        }
        stale_by_key = {
                (
                    str(row["workflow_surface"]),
                    _normalize_dynamic_compiled_boundary_symbol(
                        str(row["symbol_or_field"])
                    ),
                ): row
            for row in reconciliation["stale_rows"]
        }
        replacements_by_stale_id = {
            stale["row_id"]: missing_by_key[key]
            for key, stale in stale_by_key.items()
            if key in missing_by_key
        }
        for row in payload["rows"]:
            replacement = replacements_by_stale_id.get(row["row_id"])
            if replacement is None:
                continue
            row["row_id"] = replacement["row_id"]
            row["symbol_or_field"] = replacement["symbol_or_field"]
            row["path_or_contract"] = replacement["symbol_or_field"]
            if "source_kind" in replacement:
                row["source_kind"] = replacement["source_kind"]
            if "boundary_authority_class" in replacement:
                row["boundary_authority_class"] = replacement["boundary_authority_class"]
    payload["rows"].sort(key=lambda row: row["row_id"])
    return payload


def _load_design_delta_consumer_rendering_census() -> dict[str, object]:
    return json.loads(
        DESIGN_DELTA_CONSUMER_RENDERING_CENSUS_PATH.read_text(encoding="utf-8")
    )


def _load_design_delta_rendering_cleanup_manifest() -> dict[str, object]:
    return json.loads(
        (
            DESIGN_DELTA_MIGRATION_INPUTS
            / "design_delta_parent_drain.rendering_cleanup.json"
        ).read_text(encoding="utf-8")
    )


def _design_delta_checks_report_pair_row_ids() -> tuple[str, str]:
    return (
        "c0.implementation_phase_materialized_return_checks_report",
        "c0.implementation_phase_materialized_return_checks_report_compiled_boundary",
    )


def _write_design_delta_observability_old_writer_pair_inputs(
    tmp_path: Path,
    *,
    missing_mirror: bool = False,
) -> tuple[Path, Path]:
    legacy_payload = {
        "status": "BLOCKED",
        "progress_report": "artifacts/work/progress_report.md",
        "blocker_class": "unrecoverable_after_fix_attempt",
    }
    replacement_payload = {
        "status": "BLOCKED",
        "progress_report": "artifacts/work/progress_report.md",
        "blocker_class": "unrecoverable_after_fix_attempt",
    }
    legacy_payload_path = tmp_path / "design_delta_parent_drain.blocked_implementation_checks_report.legacy_writer_payload.json"
    legacy_payload_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_payload_path.write_text(
        json.dumps(legacy_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    primary_row_id, mirror_row_id = _design_delta_checks_report_pair_row_ids()
    manifest_payload = {
        "schema_version": "workflow_lisp_observability_old_writer_comparisons.v1",
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "row_pairs": [
            {
                "primary_row_id": primary_row_id,
                "mirror_row_id": "" if missing_mirror else mirror_row_id,
                "workflow_surface": (
                    "lisp_frontend_design_delta/implementation_phase::implementation-phase"
                ),
                "comparison_inputs": {
                    "old_writer_payload": legacy_payload,
                    "replacement_typed_summary_payload": replacement_payload,
                },
                "old_writer": {
                    "step_id_suffix": "__materialize_view__blocked_implementation_checks_report",
                    "renderer_id": "canonical-json",
                    "renderer_version": 1,
                    "payload_source": "comparison_inputs.old_writer_payload",
                },
                "replacement": {
                    "evidence_kind": "old_writer_comparison",
                    "authority_surface": "workflow_lisp_observability_summary.v1",
                    "authority_path": "RUN_ROOT/summaries/typed-terminal-summary.json",
                    "contract_profile": "terminal_value",
                    "payload_source": "comparison_inputs.replacement_typed_summary_payload",
                    "comparison_digest_kind": "sha256",
                    "typed_summary_digest": "sha256:"
                    + hashlib.sha256(
                        json.dumps(
                            replacement_payload,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=True,
                        ).encode("utf-8")
                    ).hexdigest(),
                    "old_writer_payload_digest": "sha256:"
                    + hashlib.sha256(
                        json.dumps(
                            legacy_payload,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=True,
                        ).encode("utf-8")
                    ).hexdigest(),
                },
                "status": "live_old_writer",
                "source_evidence": [
                    {
                        "kind": "legacy_writer_payload_source",
                        "side": "old_writer_payload",
                        "authority_lane": "design_delta_migration_inputs",
                        "path": str(legacy_payload_path),
                        "payload_pointer": "$",
                    },
                    {
                        "kind": "typed_summary_contract",
                        "side": "replacement_typed_summary_payload",
                        "authority_surface": "workflow_lisp_observability_summary.v1",
                        "path": "RUN_ROOT/summaries/typed-terminal-summary.json",
                        "contract_profile": "terminal_value",
                    },
                ],
            }
        ],
    }
    manifest_path = tmp_path / "design_delta_parent_drain.observability_old_writer_comparisons.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path, legacy_payload_path


def _load_design_delta_compatibility_bridges() -> dict[str, object]:
    return json.loads(
        DESIGN_DELTA_COMPATIBILITY_BRIDGES_PATH.read_text(encoding="utf-8")
    )


def _load_design_delta_resume_plumbing_retirement_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_hidden_compatibility_bridge_reread_pointer_authority_fixture() -> dict[str, object]:
    return json.loads(
        HIDDEN_COMPATIBILITY_BRIDGE_REREAD_POINTER_AUTHORITY_FIXTURE.read_text(
            encoding="utf-8"
        )
    )


def _aligned_design_delta_resume_plumbing_retirement_manifest(
    *,
    census_path: Path = DESIGN_DELTA_VALUE_FLOW_CENSUS_PATH,
) -> dict[str, object]:
    payload = _load_design_delta_resume_plumbing_retirement_manifest(
        DESIGN_DELTA_RESUME_PLUMBING_RETIREMENT_PATH
    )
    payload["source_census"] = {
        "path": str(census_path),
        "fingerprint": "sha256:" + hashlib.sha256(census_path.read_bytes()).hexdigest(),
    }
    return payload


def _aligned_design_delta_boundary_authority_registry(tmp_path: Path) -> dict[str, object]:
    build = _build_module()
    request = _design_delta_parent_drain_request(tmp_path)
    command_boundary_manifest = json.loads(
        request.command_boundaries_path.read_text(encoding="utf-8")
    )
    command_boundaries = build._parse_command_boundaries_manifest(
        command_boundary_manifest,
        manifest_path=request.command_boundaries_path,
    )
    compile_result = compile_stage3_entrypoint(
        request.source_path,
        source_roots=request.source_roots,
        provider_externs=json.loads(request.provider_externs_path.read_text(encoding="utf-8")),
        prompt_externs=json.loads(request.prompt_externs_path.read_text(encoding="utf-8")),
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    boundary_projection = build._serialize_workflow_boundary_projection(
        compile_result,
        selected_name=request.entry_workflow,
    )
    expected_rows = build_design_delta_boundary_authority_expected_rows(boundary_projection)
    checked_in_registry = _load_design_delta_boundary_authority_registry()
    checked_census = _load_design_delta_value_flow_census()
    rows_by_key = {
        (row["workflow_name"], row["field_name"], row["surface_kind"]): row
        for row in checked_in_registry["rows"]
    }
    default_authority_class = {
        "public_input": "public_authored",
        "flattened_output": "materialized_view",
        "generated_internal_input": "generated_internal",
        "compatibility_bridge_input": "compatibility_bridge",
        "managed_write_root": "generated_internal",
        "runtime_context_input": "runtime_derived",
    }
    rows = []
    for (workflow_name, field_name), expected in sorted(expected_rows.items()):
        key = (workflow_name, field_name, expected["surface_kind"])
        row = dict(rows_by_key.get(key, {}))
        if not row:
            row = {
                "workflow_name": workflow_name,
                "field_name": field_name,
                "surface_kind": expected["surface_kind"],
                "authority_class": default_authority_class[expected["surface_kind"]],
                "path_like": expected["path_like"],
                "owner": "workflow_lisp_generic_core_g0",
                "justification": (
                    "Checked compiled boundary projection row for current Design Delta parent drain evidence."
                ),
                "replacement_tranche": "G0",
                "parity_constrained": True,
            }
        else:
            row["path_like"] = expected["path_like"]
        rows.append(row)
    existing_keys = {
        (row["workflow_name"], row["field_name"], row["surface_kind"])
        for row in rows
    }
    for census_row in checked_census["rows"]:
        if (
            census_row.get("plumbing_class") != "resume_only"
            or census_row.get("current_consumer") != "runtime_resume"
            or census_row.get("boundary_authority_class") != "compatibility_bridge"
        ):
            continue
        key = (
            census_row["workflow_surface"],
            census_row["symbol_or_field"],
            "compatibility_bridge_input",
        )
        if key in existing_keys:
            continue
        checked_row = rows_by_key.get(key)
        if checked_row is None:
            continue
        rows.append(dict(checked_row))
        existing_keys.add(key)
    return {
        "schema_version": "workflow_lisp_design_delta_boundary_authority.v1",
        "rows": rows,
    }


def _validate_review_findings_retirement_metadata() -> dict[str, object]:
    return {
        "retirement_class": "validation",
        "retirement_label": "keep_bridge",
        "replacement_surface": "typed review findings validation bridge",
        "bridge_owner": "std/phase",
        "expiry_condition": (
            "retain until typed review-findings validation parity replaces the command bridge"
        ),
        "evidence_refs": ("validate_review_findings_v1",),
    }


def _stub_design_delta_auxiliary_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()

    monkeypatch.setattr(
        build,
        "reconcile_value_flow_census",
        lambda *args, **kwargs: {
            "schema_version": "workflow_lisp_private_runtime_value_flow_census_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "missing_rows": [],
            "stale_rows": [],
            "invalid_rows": [],
            "extra_compiled_rows": [],
            "workflow_rows": [],
            "required_source_kinds": [],
            "declared_workflow_surfaces": [],
        },
    )
    monkeypatch.setattr(
        build,
        "build_consumer_rendering_census_report",
        lambda *args, **kwargs: {
            "schema_version": "workflow_lisp_consumer_rendering_census_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "diagnostics": [],
            "missing_rows": [],
            "stale_rows": [],
            "invalid_rows": [],
            "materialize_view_effect_rows": [],
            "compiled_evidence": {},
        },
    )
    monkeypatch.setattr(
        build,
        "build_typed_prompt_input_report",
        lambda *args, **kwargs: {
            "schema_version": "workflow_lisp_typed_prompt_input_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "selected_rows": [],
            "missing_rows": [],
            "stale_rows": [],
            "invalid_rows": [],
        },
    )
    monkeypatch.setattr(
        build,
        "_build_design_delta_observability_summary_prerequisite_report",
        lambda **kwargs: {
            "schema_id": "workflow_lisp_observability_summary_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "selected_c0_row_ids": [],
            "diagnostics": {"errors": [], "warnings": []},
        },
    )
    monkeypatch.setattr(
        build,
        "_build_entry_publication_report",
        lambda **kwargs: {
            "schema_version": "workflow_lisp_entry_publication_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "diagnostics": [],
            "selected_c0_rows": [],
        },
    )
    monkeypatch.setattr(
        build,
        "build_compatibility_bridge_report",
        lambda **kwargs: {
            "schema_version": "workflow_lisp_compatibility_bridge_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "diagnostics": [],
            "generated_bridges": [],
            "blocked_bridges": [],
            "contract_isolation": {},
        },
    )
    monkeypatch.setattr(
        build,
        "build_rendering_cleanup_report",
        lambda **kwargs: {
            "schema_version": "workflow_lisp_rendering_cleanup_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "diagnostics": [],
            "cleanup_decisions": [],
            "blocked_compatibility_row_ids": [],
            "surviving_body_materialization_row_ids": [],
        },
    )
    monkeypatch.setattr(
        build,
        "_maybe_load_design_delta_rendering_cleanup_manifest",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        build,
        "build_rendering_ergonomics_report",
        lambda **kwargs: {
            "schema_version": "workflow_lisp_rendering_ergonomics_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "target_family": "lisp_frontend_design_delta_parent_drain",
            "status": "pass",
            "diagnostics": [],
            "provider_input_shapes": [],
        },
    )
    monkeypatch.setattr(
        build,
        "_maybe_load_design_delta_rendering_ergonomics_manifest",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        build.resume_plumbing_retirement,
        "build_resume_plumbing_retirement_report",
        lambda **kwargs: {
            "schema_version": "workflow_lisp_resume_plumbing_retirement_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "diagnostics": [],
            "decisions": [],
            "source_census": {},
            "manifest": {},
        },
    )
    monkeypatch.setattr(
        build.lexical_checkpoint_default_resume,
        "build_default_resume_report",
        lambda **kwargs: {
            "schema_version": "workflow_lisp_lexical_checkpoint_default_resume_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "diagnostics": [],
        },
    )


def _write_structured_results_module(tmp_path: Path) -> Path:
    package_dir = tmp_path / "lineage_pkg"
    package_dir.mkdir(parents=True, exist_ok=True)
    module_path = package_dir / "entry.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule lineage_pkg/entry)",
                "  (export command_checks provider_attempt orchestrate)",
                "  (defenum BlockerClass",
                "    missing_resource",
                "    unavailable_hardware)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defunion ImplementationState",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)",
                "      (blocker_class BlockerClass)))",
                "  (defworkflow command_checks",
                "    ((report_path WorkReport))",
                "    -> ChecksResult",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" report_path)',
                "      :returns ChecksResult))",
                "  (defworkflow provider_attempt",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (input report_path)",
                "               :returns ImplementationState)))",
                "      (match attempt",
                "        ((COMPLETED completed)",
                "         (record ImplementationSummary :report completed.execution_report))",
                "        ((BLOCKED blocked)",
                "         (record ImplementationSummary :report blocked.progress_report)))))",
                "  (defworkflow orchestrate",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (call provider_attempt",
                "      :input input",
                "      :report_path report_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return module_path

def _structured_results_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    module_path = _write_structured_results_module(tmp_path)
    return request_cls(
        source_path=module_path,
        source_roots=(tmp_path,),
        entry_workflow="orchestrate",
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=None,
        command_boundaries_path=CLI_FIXTURES / "commands.json",
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _selector_projection_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    providers_path = tmp_path / "selector_providers.json"
    prompts_path = tmp_path / "selector_prompts.json"
    commands_path = tmp_path / "selector_commands.json"
    providers_path.write_text(
        json.dumps({"providers.selector": "codex"}, indent=2) + "\n",
        encoding="utf-8",
    )
    prompts_path.write_text(
        json.dumps(
            {
                "prompts.selector.select-next-work": (
                    "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md"
                )
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    commands_path.write_text(
        json.dumps(
            {
                "validate_review_findings_v1": {
                    "kind": "external_tool",
                    "stable_command": [
                        "python",
                        "-m",
                        "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
                    ],
                    **_validate_review_findings_retirement_metadata(),
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return request_cls(
        source_path=REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "selector.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        entry_workflow="select-next-work",
        provider_externs_path=providers_path,
        prompt_externs_path=prompts_path,
        imported_workflow_bundles_path=None,
        command_boundaries_path=commands_path,
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _design_delta_work_item_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    providers_path = tmp_path / "design_delta_work_item_providers.json"
    prompts_path = tmp_path / "design_delta_work_item_prompts.json"
    commands_path = tmp_path / "design_delta_work_item_commands.json"
    providers_path.write_text(
        json.dumps(
            {
                "providers.plan.draft": "fake-plan-draft",
                "providers.plan.review": "fake-plan-review",
                "providers.plan.fix": "fake-plan-fix",
                "providers.architect.draft": "fake-architect-draft",
                "providers.implementation.execute": "fake-implementation-execute",
                "providers.implementation.review": "fake-implementation-review",
                "providers.implementation.fix": "fake-implementation-fix",
                "providers.selector": "fake-selector",
                "providers.work-item.recovery-classifier": "fake-work-item-recovery",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    prompts_path.write_text(
        json.dumps(
            {
                "prompts.plan.draft": (
                    "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/draft_plan.md"
                ),
                "prompts.plan.review": (
                    "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/review_plan.md"
                ),
                "prompts.plan.fix": (
                    "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/revise_plan.md"
                ),
                "prompts.architect.draft": (
                    "workflows/library/prompts/"
                    "lisp_frontend_design_delta_design_gap_architect/"
                    "draft_implementation_architecture.md"
                ),
                "prompts.implementation.execute": (
                    "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/implement_plan.md"
                ),
                "prompts.implementation.review": (
                    "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/review_implementation.md"
                ),
                "prompts.implementation.fix": (
                    "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/fix_implementation.md"
                ),
                "prompts.selector.select-next-work": (
                    "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md"
                ),
                "prompts.work-item.classify-blocked-recovery": (
                    "workflows/library/prompts/lisp_frontend_design_delta_work_item/"
                    "classify_blocked_implementation_recovery.md"
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    commands_path.write_text(
        json.dumps(
            {
                "run_neurips_backlog_checks": {
                    "kind": "external_tool",
                    "stable_command": [
                        "python",
                        "workflows/library/scripts/run_neurips_backlog_checks.py",
                    ],
                    "retirement_class": "genuine_system",
                    "retirement_label": "keep_certified_system",
                    "replacement_surface": "certified external backlog check command",
                    "bridge_owner": "lisp_frontend_design_delta/implementation_phase",
                    "expiry_condition": "retain while backlog checks remain external",
                    "evidence_refs": ["design_delta_parent_drain_smokes"],
                },
                "validate_review_findings_v1": {
                    "kind": "external_tool",
                    "stable_command": [
                        "python",
                        "-m",
                        "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
                    ],
                    **_validate_review_findings_retirement_metadata(),
                },
                "materialize_lisp_frontend_work_item_inputs": {
                    "kind": "certified_adapter",
                    "stable_command": [
                        "python",
                        "workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py",
                    ],
                    "input_contract": {"type": "object"},
                    "output_type_name": "ResolvedWorkItemInputs",
                    "effects": ["structured_result"],
                    "path_safety": {"kind": "workspace_relpath"},
                    "source_map_behavior": "step",
                    "fixture_ids": ["design_delta_work_item_inputs_ok"],
                    "negative_fixture_ids": ["design_delta_work_item_inputs_bad"],
                    "behavior_class": "structured_result",
                    "input_signature": [
                        {
                            "name": "selection_bundle_path",
                            "type_name": "SelectionBundlePath",
                            "required": True,
                            "transport_key": "selection_path",
                        },
                        {
                            "name": "manifest_path",
                            "type_name": "StateFileExisting",
                            "required": True,
                            "transport_key": "manifest_path",
                        },
                        {
                            "name": "architecture_bundle_path",
                            "type_name": "StateFile",
                            "required": True,
                            "transport_key": "architecture_bundle_path",
                        }
                    ],
                    "artifact_contracts": ["materialize_lisp_frontend_work_item_inputs_bundle"],
                    "state_writes": [],
                    "error_codes": ["materialize_lisp_frontend_work_item_inputs_invalid"],
                    "owner_module": "lisp_frontend_design_delta/work_item",
                    "replacement_path": "SelectionCtx + ItemCtx private bootstrap + typed projection",
                    "invocation_protocol": "json_object_positional_arg",
                    "retirement_class": "manifest_assembly",
                    "retirement_label": "keep_bridge",
                    "replacement_surface": (
                        "SelectionCtx + ItemCtx private bootstrap with future generated path "
                        "and materialized view retirement"
                    ),
                    "bridge_owner": "lisp_frontend_design_delta/work_item",
                    "expiry_condition": (
                        "retain until later G4/G7 context/bootstrap work replaces manifest "
                        "assembly and path materialization"
                    ),
                    "evidence_refs": ["design_delta_work_item_inputs_ok"],
                },
                "classify_lisp_frontend_work_item_terminal": {
                    "kind": "certified_adapter",
                    "stable_command": [
                        "python",
                        "workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py",
                    ],
                    "input_contract": {"type": "object"},
                    "output_type_name": "WorkItemTerminalClassification",
                    "effects": ["structured_result"],
                    "path_safety": {"kind": "workspace_relpath"},
                    "source_map_behavior": "step",
                    "fixture_ids": ["design_delta_work_item_terminal_ok"],
                    "negative_fixture_ids": ["design_delta_work_item_terminal_bad"],
                    "behavior_class": "outcome_finalization",
                    "input_signature": [
                        {
                            "name": "plan_review_decision",
                            "type_name": "String",
                            "required": True,
                            "transport_key": "plan_review_decision",
                        },
                        {
                            "name": "implementation_state",
                            "type_name": "String",
                            "required": True,
                            "transport_key": "implementation_state",
                        },
                        {
                            "name": "implementation_review_decision",
                            "type_name": "String",
                            "required": True,
                            "transport_key": "implementation_review_decision",
                        },
                        {
                            "name": "work_item_source",
                            "type_name": "String",
                            "required": True,
                            "transport_key": "work_item_source",
                        }
                    ],
                    "artifact_contracts": ["classify_lisp_frontend_work_item_terminal_bundle"],
                    "state_writes": [],
                    "error_codes": ["classify_lisp_frontend_work_item_terminal_invalid"],
                    "owner_module": "lisp_frontend_design_delta/work_item",
                    "replacement_path": "typed implementation terminal union",
                    "invocation_protocol": "json_object_positional_arg",
                    "retirement_class": "outcome_classification",
                    "retirement_label": "retire_to_projection",
                    "replacement_surface": "typed terminal classification projection",
                    "bridge_owner": "lisp_frontend_design_delta/work_item",
                    "expiry_condition": "g2 typed outcome classification replaces terminal classifier adapter",
                    "evidence_refs": ["design_delta_work_item_terminal_ok"],
                },
                "select_lisp_frontend_blocked_recovery_route": {
                    "kind": "certified_adapter",
                    "stable_command": [
                        "python",
                        "workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py",
                    ],
                    "input_contract": {"type": "object"},
                    "output_type_name": "BlockedRecoveryDecision",
                    "effects": ["structured_result"],
                    "path_safety": {"kind": "workspace_relpath"},
                    "source_map_behavior": "step",
                    "fixture_ids": ["design_delta_blocked_recovery_route_ok"],
                    "negative_fixture_ids": ["design_delta_blocked_recovery_route_bad"],
                    "behavior_class": "outcome_finalization",
                    "input_signature": [
                        {
                            "name": "terminal_route",
                            "type_name": "String",
                            "required": True,
                            "transport_key": "terminal_route",
                        },
                        {
                            "name": "work_item_source",
                            "type_name": "String",
                            "required": True,
                            "transport_key": "work_item_source",
                        },
                        {
                            "name": "blocked_recovery_route",
                            "type_name": "String",
                            "required": True,
                            "transport_key": "blocked_recovery_route",
                        },
                        {
                            "name": "reason",
                            "type_name": "String",
                            "required": True,
                            "transport_key": "reason",
                        }
                    ],
                    "artifact_contracts": ["select_lisp_frontend_blocked_recovery_route_bundle"],
                    "state_writes": [],
                    "error_codes": ["select_lisp_frontend_blocked_recovery_route_invalid"],
                    "owner_module": "lisp_frontend_design_delta/work_item",
                    "replacement_path": "typed BlockedRecoveryDecision normalization",
                    "invocation_protocol": "json_object_positional_arg",
                    "retirement_class": "outcome_classification",
                    "retirement_label": "retire_to_projection",
                    "replacement_surface": "typed blocked-recovery route classification",
                    "bridge_owner": "lisp_frontend_design_delta/work_item",
                    "expiry_condition": "g2 typed outcome classification replaces blocked-recovery router",
                    "evidence_refs": ["design_delta_blocked_recovery_route_ok"],
                },
                "record_terminal_work_item": {
                    "kind": "external_tool",
                    "stable_command": [
                        "python",
                        "workflows/library/scripts/update_lisp_frontend_run_state.py",
                    ],
                    "retirement_class": "resource_transition",
                    "retirement_label": "retire_to_transition",
                    "replacement_surface": "runtime-native selected-item resource transition",
                    "bridge_owner": "lisp_frontend_design_delta/work_item",
                    "expiry_condition": "g3 typed resource transition replaces terminal work-item recorder",
                    "evidence_refs": ["design_delta_record_terminal_ok"],
                },
                "record_blocked_recovery_outcome": {
                    "kind": "external_tool",
                    "stable_command": [
                        "python",
                        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
                    ],
                    "retirement_class": "resource_transition",
                    "retirement_label": "retire_to_transition",
                    "replacement_surface": "runtime-native blocked-recovery resource transition",
                    "bridge_owner": "lisp_frontend_design_delta/work_item",
                    "expiry_condition": "g3 typed resource transition replaces blocked-recovery recorder",
                    "evidence_refs": ["design_delta_record_blocked_recovery_ok"],
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    commands_path.write_text(
        (
            REPO_ROOT
            / "workflows"
            / "examples"
            / "inputs"
            / "workflow_lisp_migrations"
            / "design_delta_parent_drain.commands.json"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return request_cls(
        source_path=(
            DESIGN_DELTA_WORK_ITEM_CANDIDATE_ROOT
            / "lisp_frontend_design_delta"
            / "work_item.orc"
        ),
        source_roots=(DESIGN_DELTA_WORK_ITEM_CANDIDATE_ROOT,),
        entry_workflow="run-work-item",
        provider_externs_path=providers_path,
        prompt_externs_path=prompts_path,
        imported_workflow_bundles_path=None,
        command_boundaries_path=commands_path,
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _compile_design_delta_work_item_without_shared_validation(tmp_path: Path):
    build = _build_module()
    request = _design_delta_work_item_request(tmp_path)
    resolve_request = getattr(build, "_resolve_request")
    load_string_mapping = getattr(build, "_load_string_mapping")
    load_prompt_extern_mapping = getattr(build, "_load_prompt_extern_mapping")
    load_command_boundaries_manifest_payload = getattr(
        build,
        "_load_command_boundaries_manifest_payload",
    )
    parse_command_boundaries_manifest = getattr(
        build,
        "_parse_command_boundaries_manifest",
    )

    resolved_request = resolve_request(request)
    provider_externs = load_string_mapping(
        resolved_request.provider_externs_path,
        label="provider externs manifest",
    )
    prompt_externs = load_prompt_extern_mapping(
        resolved_request.prompt_externs_path,
    )
    command_boundary_manifest = load_command_boundaries_manifest_payload(
        resolved_request.command_boundaries_path,
    )
    command_boundaries = parse_command_boundaries_manifest(
        command_boundary_manifest,
        manifest_path=resolved_request.command_boundaries_path,
    )
    compile_result = compile_stage3_entrypoint(
        resolved_request.source_path,
        source_roots=resolved_request.source_roots,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        imported_workflow_bundles=None,
        command_boundaries=command_boundaries,
        validate_shared=False,
        workspace_root=resolved_request.workspace_root,
        lint_profile=resolved_request.lint_profile,
    )
    return request, command_boundary_manifest, compile_result


def _assert_design_delta_work_item_advanced_past_wcc_ifexpr(
    diagnostics: tuple[LispFrontendDiagnostic, ...],
) -> None:
    diagnostic_codes = {diagnostic.code for diagnostic in diagnostics}

    assert "union_return_variant_ambiguous" not in diagnostic_codes
    assert "union_return_variant_incompatible" not in diagnostic_codes
    assert "proc_private_workflow_boundary_invalid" not in diagnostic_codes
    assert not any("unsupported `IfExpr`" in diagnostic.message for diagnostic in diagnostics)
    assert diagnostics, "expected a distinct downstream diagnostic or successful compile"


def _walk_design_delta_work_item_steps(steps: list[dict[str, object]]):
    for step in steps:
        yield step
        match_block = step.get("match")
        if isinstance(match_block, dict):
            for case_payload in match_block.get("cases", {}).values():
                if isinstance(case_payload, dict):
                    yield from _walk_design_delta_work_item_steps(case_payload.get("steps", []))
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            yield from _walk_design_delta_work_item_steps(repeat_until.get("steps", []))
        for key in ("then", "else"):
            branch = step.get(key)
            if isinstance(branch, dict):
                yield from _walk_design_delta_work_item_steps(branch.get("steps", []))


def test_boundary_projection_serializer_preserves_hidden_compatibility_bridge_over_fixed_run_item(
    tmp_path: Path,
) -> None:
    build = _build_module()
    serialize = getattr(build, "_serialize_workflow_boundary_projection")
    result = _compile_linked_hidden_compatibility_bridge_fixture(tmp_path)

    workflow_name = "drain_stdlib_backlog_drain_hidden_compatibility_bridge::run-selected-item"
    projection_payload = serialize(result, selected_name=workflow_name)
    workflow_projection = next(
        item
        for item in projection_payload["workflows"]
        if item["workflow_name"] == workflow_name
    )
    child = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == "std/drain::backlog-drain"
    )
    run_item_call = next(
        step
        for step in _walk_design_delta_work_item_steps(child.authored_mapping["steps"])
        if step.get("call", "").endswith("::run-selected-item")
    )
    generated_internal_inputs = {
        item["generated_name"]: item
        for item in workflow_projection["generated_internal_inputs"]
    }

    assert "run_state_path" not in workflow_projection["boundary"]["public_input_names"]
    assert workflow_projection["boundary"]["private_compatibility_bridge_inputs"] == [
        "run_state_path"
    ]
    assert generated_internal_inputs["run_state_path"]["reason"] == "compatibility_bridge"
    assert run_item_call["with"]["run_state_path"] == {"ref": "inputs.run_state_path"}


def _design_delta_work_item_run_work_item_lowered(compile_result):
    return next(
        workflow
        for workflow in compile_result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == "lisp_frontend_design_delta/work_item::run-work-item"
    )


def _resume_entry_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    fixture_root = FIXTURES / "modules" / "valid" / "callables"
    fixture = fixture_root / "neurips" / "helper.orc"
    return request_cls(
        source_path=fixture,
        source_roots=(fixture_root,),
        entry_workflow="provider-attempt",
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=None,
        command_boundaries_path=CLI_FIXTURES / "commands.json",
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _write_workflow_param_default_module(tmp_path: Path) -> Path:
    package_dir = tmp_path / "defaults_pkg"
    package_dir.mkdir(parents=True, exist_ok=True)
    module_path = package_dir / "entry.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule defaults_pkg/entry)",
                "  (export defaults)",
                "  (defenum Status",
                "    ready",
                "    blocked)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord Summary",
                "    (report WorkReport))",
                "  (defworkflow defaults",
                '    ((message String :default "hello")',
                "     (count Int :default 3)",
                "     (score Float :default 0.5)",
                "     (enabled Bool :default true)",
                "     (status Status :default ready)",
                '     (report_path WorkReport :default "default.md"))',
                "    -> Summary",
                "    (record Summary :report report_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return module_path


def _workflow_param_default_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    module_path = _write_workflow_param_default_module(tmp_path)
    return request_cls(
        source_path=module_path,
        source_roots=(tmp_path,),
        entry_workflow="defaults",
        provider_externs_path=None,
        prompt_externs_path=None,
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=False,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )


def _lint_warning_variant_output_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    module_path = FIXTURES / "valid" / "lint_warning_variant_output.orc"
    return request_cls(
        source_path=module_path,
        source_roots=(FIXTURES / "valid",),
        entry_workflow="orchestrate",
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _pointer_effects_request(tmp_path: Path):
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    module_path = FIXTURES / "valid" / "pointer_materialization_effects.orc"
    return request_cls(
        source_path=module_path,
        source_roots=(FIXTURES / "valid",),
        entry_workflow="orchestrate",
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=None,
        command_boundaries_path=CLI_FIXTURES / "commands.json",
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )


def _thaw_source_map_value(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _thaw_source_map_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _thaw_source_map_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_source_map_value(item) for item in value]
    return value


def _same_file_wcc_m3_source_map_payload(
    tmp_path: Path,
    *,
    fixture_path: Path,
    module_filename: str,
    selected_name: str,
) -> dict[str, object]:
    module_path = tmp_path / module_filename
    module_path.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")
    graph = resolve_module_graph(module_path, source_roots=(tmp_path,))
    compile_result = workflow_lisp_compiler._compile_stage3_graph(
        graph,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={
            "prompts.implementation.execute": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
        },
        imported_workflow_bundles=None,
        command_boundaries=None,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=workflow_lisp_compiler.normalize_lowering_route("wcc_m3"),
    )
    source_map = build_source_map_document(
        compile_result,
        selected_name=selected_name,
        display_name_resolver=lambda workflow_name: workflow_name.split("::")[-1],
    )
    return _thaw_source_map_value(source_map)


def _route_neutral_wcc_m4_source_map_payload(tmp_path: Path) -> dict[str, object]:
    fixture_path = FIXTURES / "valid" / "loop_recur_on_exhausted_union.orc"
    module_text = fixture_path.read_text(encoding="utf-8").replace(
        '  (:target-dsl "2.14")\n',
        '  (:target-dsl "2.14")\n'
        "  (defmodule route_neutral_loop)\n"
        "  (export loop-recur-on-exhausted-union)\n",
        1,
    )
    module_path = tmp_path / "route_neutral_loop.orc"
    module_path.write_text(module_text, encoding="utf-8")
    graph = resolve_module_graph(module_path, source_roots=(tmp_path,))
    compile_result = workflow_lisp_compiler._compile_stage3_graph(
        graph,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={
            "prompts.implementation.execute": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
        },
        imported_workflow_bundles=None,
        command_boundaries=None,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=workflow_lisp_compiler.normalize_lowering_route("wcc_m4"),
    )
    source_map = build_source_map_document(
        compile_result,
        selected_name="route_neutral_loop::loop-recur-on-exhausted-union",
        display_name_resolver=lambda workflow_name: workflow_name.split("::")[-1],
    )
    return _thaw_source_map_value(source_map)


def _wcc_m4_full_fixture_source_map_payload(tmp_path: Path) -> dict[str, object]:
    fixture_path = FIXTURES / "characterization" / "sources" / "wcc_m4_implementation_phase_full_fixture.orc"
    compile_result = compile_stage3_entrypoint(
        fixture_path,
        source_roots=(fixture_path.parent,),
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "validate_review_findings_v1": ExternalToolBinding(
                name="validate_review_findings_v1",
                stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.validate_review_findings_v1"),
                **_validate_review_findings_retirement_metadata(),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )
    source_map = build_source_map_document(
        compile_result,
        selected_name="wcc_m4_implementation_phase_full_fixture::run",
        display_name_resolver=lambda workflow_name: workflow_name.split("::")[-1],
    )
    return _thaw_source_map_value(source_map)


def _workflow_public_input_contracts(bundle):
    helper = getattr(
        loaded_bundle_helpers,
        "workflow_public_input_contracts",
        loaded_bundle_helpers.workflow_input_contracts,
    )
    return helper(bundle)


def _workflow_runtime_input_contracts(bundle):
    helper = getattr(
        loaded_bundle_helpers,
        "workflow_runtime_input_contracts",
        loaded_bundle_helpers.workflow_input_contracts,
    )
    return helper(bundle)


def _workflow_runtime_context_inputs(bundle):
    helper = getattr(
        loaded_bundle_helpers,
        "workflow_runtime_context_inputs",
        lambda _: (),
    )
    return helper(bundle)


def _workflow_boundary_projection(bundle):
    helper = getattr(loaded_bundle_helpers, "workflow_boundary_projection")
    return helper(bundle)


def _workflow_payload_by_suffix(payload: dict[str, object], workflow_suffix: str) -> dict[str, object]:
    workflows = payload["workflows"]
    assert isinstance(workflows, list)
    return next(
        workflow
        for workflow in workflows
        if isinstance(workflow, dict) and str(workflow.get("workflow_name", "")).endswith(f"::{workflow_suffix}")
    )


def _allocation_payload_by_role(payload: list[dict[str, object]], semantic_role: str) -> dict[str, object]:
    return next(
        allocation
        for allocation in payload
        if isinstance(allocation, dict) and allocation.get("semantic_role") == semantic_role
    )


def _compile_resume_fixture(tmp_path: Path):
    fixture = FIXTURES / "valid" / "phase_stdlib_resume_or_start.orc"
    return compile_stage3_module(
        fixture,
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
            "load_canonical_phase_result__ChecksResult": ExternalToolBinding(
                name="load_canonical_phase_result__ChecksResult",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.load_canonical_phase_result",
                ),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )


def _assert_no_runtime_closure_markers(serialized: str) -> None:
    for marker in RUNTIME_CLOSURE_MARKERS:
        assert marker not in serialized


def test_build_fingerprint_is_stable_for_identical_inputs(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    first = build_frontend_bundle(_build_request(tmp_path))
    second = build_frontend_bundle(_build_request(tmp_path))

    assert first.manifest.fingerprint == second.manifest.fingerprint
    assert first.build_root == second.build_root


def test_build_fingerprint_changes_when_imported_bundle_manifest_changes(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    alternate_bundle = tmp_path / "selector_alt.yaml"
    alternate_bundle.write_text(
        (CLI_FIXTURES / "imported_selector.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    alternate_manifest = tmp_path / "imported_workflow_bundles.alt.json"
    alternate_manifest.write_text(
        json.dumps(
            {
                "selector-run": {
                    "kind": "yaml",
                    "path": str(alternate_bundle),
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    original = build_frontend_bundle(_build_request(tmp_path))
    alternate = build_frontend_bundle(_build_request(tmp_path, manifest_path=alternate_manifest))

    assert original.manifest.fingerprint != alternate.manifest.fingerprint


def test_build_fingerprint_normalizes_alias_and_canonical_entry_workflow(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    alias_result = build_frontend_bundle(_build_request(tmp_path))
    canonical_request = _build_request(tmp_path)
    canonical_request = type(canonical_request)(
        **{
            **canonical_request.__dict__,
            "entry_workflow": "neurips/entry::orchestrate",
        }
    )
    canonical_result = build_frontend_bundle(canonical_request)

    assert alias_result.entry_selection.canonical_name == "neurips/entry::orchestrate"
    assert canonical_result.entry_selection.canonical_name == "neurips/entry::orchestrate"
    assert alias_result.manifest.fingerprint == canonical_result.manifest.fingerprint


def test_build_fingerprint_changes_when_command_boundary_manifest_changes(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    alternate_manifest = tmp_path / "commands.alt.json"
    alternate_manifest.write_text(
        json.dumps(
            {
                "run_checks": {
                    "kind": "external_tool",
                    "stable_command": ["python", "scripts/run_checks.py"],
                    "effects": ["structured_result"],
                    "path_safety": {"kind": "workspace_relpath"},
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    original = build_frontend_bundle(_build_request(tmp_path))
    alternate_request = _build_request(tmp_path)
    alternate_request = type(alternate_request)(
        **{
            **alternate_request.__dict__,
            "command_boundaries_path": alternate_manifest,
        }
    )
    alternate = build_frontend_bundle(alternate_request)

    assert original.manifest.fingerprint != alternate.manifest.fingerprint


def test_parse_command_boundary_manifest_accepts_promoted_certified_adapter_metadata() -> None:
    build = _build_module()
    parse_manifest = getattr(build, "_parse_command_boundaries_manifest")

    bindings = parse_manifest(
        {
            "normalize_result": {
                "kind": "certified_adapter",
                "stable_command": ["python", "scripts/normalize_result.py"],
                "input_contract": {"type": "object"},
                "output_type_name": "ImplementationSummary",
                "effects": ["structured_result"],
                "path_safety": {"kind": "workspace_relpath"},
                "source_map_behavior": "step",
                "fixture_ids": ["normalize_result_ok"],
                "negative_fixture_ids": ["normalize_result_bad"],
                "behavior_class": "structured_result",
                "input_signature": [
                    {
                        "name": "execution_report",
                        "type_name": "WorkReport",
                        "required": True,
                        "transport_key": "execution_report",
                    },
                    {
                        "name": "review_report",
                        "type_name": "WorkReport",
                        "required": True,
                        "transport_key": "review_report",
                    },
                ],
                "artifact_contracts": ["implementation_summary_report"],
                "state_writes": [],
                "error_codes": ["normalize_result_invalid_payload"],
                "owner_module": "std/phase",
                "replacement_path": None,
                "invocation_protocol": "json_object_positional_arg",
            }
        },
        manifest_path=None,
    )

    binding = bindings["normalize_result"]

    assert binding.behavior_class == "structured_result"
    assert binding.invocation_protocol == "json_object_positional_arg"
    assert tuple(field.transport_key for field in binding.input_signature) == (
        "execution_report",
        "review_report",
    )


def test_parse_command_boundary_manifest_keeps_legacy_certified_adapter_argv_compatibility() -> None:
    build = _build_module()
    parse_manifest = getattr(build, "_parse_command_boundaries_manifest")

    bindings = parse_manifest(
        {
            "normalize_result": {
                "kind": "certified_adapter",
                "stable_command": ["python", "scripts/normalize_result.py"],
                "input_contract": {"type": "object"},
                "output_type_name": "ImplementationSummary",
                "effects": ["structured_result"],
                "path_safety": {"kind": "workspace_relpath"},
                "source_map_behavior": "step",
                "fixture_ids": ["normalize_result_ok"],
                "negative_fixture_ids": ["normalize_result_bad"],
            }
        },
        manifest_path=None,
    )

    binding = bindings["normalize_result"]

    assert binding.output_type_name == "ImplementationSummary"
    assert binding.stable_command == ("python", "scripts/normalize_result.py")


def test_build_fingerprint_changes_when_promoted_adapter_metadata_changes(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    first_manifest = tmp_path / "commands.promoted.first.json"
    second_manifest = tmp_path / "commands.promoted.second.json"
    first_manifest.write_text(
        json.dumps(
            {
                "run_checks": {
                    "kind": "external_tool",
                    "stable_command": ["python", "scripts/run_checks.py"],
                },
                "normalize_result": {
                    "kind": "certified_adapter",
                    "stable_command": ["python", "scripts/normalize_result.py"],
                    "input_contract": {"type": "object"},
                    "output_type_name": "ImplementationSummary",
                    "effects": ["structured_result"],
                    "path_safety": {"kind": "workspace_relpath"},
                    "source_map_behavior": "step",
                    "fixture_ids": ["normalize_result_ok"],
                    "negative_fixture_ids": ["normalize_result_bad"],
                    "behavior_class": "structured_result",
                    "input_signature": [
                        {
                            "name": "execution_report",
                            "type_name": "WorkReport",
                            "required": True,
                            "transport_key": "execution_report",
                        }
                    ],
                    "artifact_contracts": ["implementation_summary_report"],
                    "state_writes": [],
                    "error_codes": ["normalize_result_invalid_payload"],
                    "owner_module": "std/phase",
                    "replacement_path": None,
                    "invocation_protocol": "json_object_positional_arg",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    second_manifest.write_text(
        json.dumps(
            {
                "run_checks": {
                    "kind": "external_tool",
                    "stable_command": ["python", "scripts/run_checks.py"],
                },
                "normalize_result": {
                    "kind": "certified_adapter",
                    "stable_command": ["python", "scripts/normalize_result.py"],
                    "input_contract": {"type": "object"},
                    "output_type_name": "ImplementationSummary",
                    "effects": ["structured_result"],
                    "path_safety": {"kind": "workspace_relpath"},
                    "source_map_behavior": "step",
                    "fixture_ids": ["normalize_result_ok"],
                    "negative_fixture_ids": ["normalize_result_bad"],
                    "behavior_class": "structured_result",
                    "input_signature": [
                        {
                            "name": "execution_report",
                            "type_name": "WorkReport",
                            "required": True,
                            "transport_key": "execution_report_path",
                        }
                    ],
                    "artifact_contracts": ["implementation_summary_report"],
                    "state_writes": [],
                    "error_codes": ["normalize_result_invalid_payload"],
                    "owner_module": "std/phase",
                    "replacement_path": None,
                    "invocation_protocol": "json_object_positional_arg",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    first_request = _build_request(tmp_path)
    first_request = type(first_request)(
        **{
            **first_request.__dict__,
            "command_boundaries_path": first_manifest,
        }
    )
    second_request = _build_request(tmp_path)
    second_request = type(second_request)(
        **{
            **second_request.__dict__,
            "command_boundaries_path": second_manifest,
        }
    )

    first = build_frontend_bundle(first_request)
    second = build_frontend_bundle(second_request)

    assert first.manifest.fingerprint != second.manifest.fingerprint


def test_build_accepts_compiled_imported_workflow_bundles_manifest_and_public_runtime_input_projections(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    compiled_selector = tmp_path / "compiled" / "selector.orc"
    compiled_selector.parent.mkdir(parents=True, exist_ok=True)
    compiled_selector.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule compiled/selector)",
                "  (export selector-run)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow selector-run",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs (input report_path)",
                "      :returns ImplementationSummary)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    compiled_manifest = tmp_path / "imported_workflow_bundles.compiled.json"
    compiled_manifest.write_text(
        json.dumps(
            {
                "selector-run": {
                    "kind": "compiled",
                    "path": str(compiled_selector),
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_frontend_bundle(_build_request(tmp_path, manifest_path=compiled_manifest))

    assert result.imported_workflow_bundles[0].bundle_kind == "compiled"
    assert result.imported_workflow_bundles[0].workflow_name == "compiled/selector::selector-run"
    assert result.imported_workflow_bundles[0].bundle.ir.schema_version == "workflow_executable_ir.v1"
    assert result.imported_workflow_bundles[0].bundle.runtime_plan.schema_version == "workflow_runtime_plan.v1"
    bundle = result.imported_workflow_bundles[0].bundle
    assert workflow_managed_write_root_inputs(bundle) == (
        "__write_root__compiled_selector_selector_run__result__result_bundle",
    )
    assert "__write_root__compiled_selector_selector_run__result__result_bundle" not in _workflow_public_input_contracts(
        bundle
    )
    assert "__write_root__compiled_selector_selector_run__result__result_bundle" in _workflow_runtime_input_contracts(
        bundle
    )


@pytest.mark.parametrize(
    ("request_field", "file_name", "payload", "expected_message"),
    [
        (
            "provider_externs_path",
            "providers.invalid-entry.json",
            {"providers.execute": {"bad": True}},
            "provider externs manifest entries must map non-empty string names to string values",
        ),
        (
            "prompt_externs_path",
            "prompts.invalid-entry.json",
            {"prompts.implementation.execute": {"bad": True}},
            (
                "prompt externs manifest entries must map non-empty string names to string values "
                "or objects with exactly one of `asset_file` or `input_file`"
            ),
        ),
    ],
)
def test_build_rejects_non_string_extern_manifest_entries(
    tmp_path: Path,
    request_field: str,
    file_name: str,
    payload: dict[str, object],
    expected_message: str,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    manifest_path = tmp_path / file_name
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    request = _build_request(tmp_path)
    request = type(request)(**{**request.__dict__, request_field: manifest_path})

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_frontend_bundle(request)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "workflow_lisp_manifest_invalid"
    assert diagnostic.message == expected_message


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        (
            {"run_checks": 5},
            "manifest entry for `run_checks` must be a JSON object",
        ),
        (
            {"run_checks": {"kind": "external_tool", "stable_command": 5}},
            "`stable_command` for `run_checks` must be an array of strings",
        ),
    ],
)
def test_build_rejects_invalid_command_boundary_manifest_entries(
    tmp_path: Path,
    payload: dict[str, object],
    expected_message: str,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    manifest_path = tmp_path / "commands.invalid-entry.json"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    request = _build_request(tmp_path)
    request = type(request)(**{**request.__dict__, "command_boundaries_path": manifest_path})

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_frontend_bundle(request)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "command_boundary_manifest_invalid"
    assert diagnostic.message == expected_message


def test_build_emits_required_artifacts_and_deferred_status_entries(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_build_request(tmp_path))
    core_workflow_ast = json.loads(result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    executable_ir = json.loads(result.artifact_paths["executable_ir"].read_text(encoding="utf-8"))
    runtime_plan = json.loads(result.artifact_paths["runtime_plan"].read_text(encoding="utf-8"))

    expected_artifacts = {
        "manifest.json",
        "frontend_ast.json",
        "expanded_frontend_ast.json",
        "typed_frontend_ast.json",
        "lowered_workflows.json",
        "executable_ir.json",
        "core_workflow_ast.json",
        "semantic_ir.json",
        "runtime_plan.json",
        "source_map.json",
        "workflow_boundary_projection.json",
        "diagnostics.json",
    }

    assert expected_artifacts.issubset({path.name for path in result.artifact_paths.values()})
    assert executable_ir["schema_version"] == "workflow_executable_ir.v1"
    assert runtime_plan["schema_version"] == "workflow_runtime_plan.v1"
    assert result.artifact_paths["core_workflow_ast"].name == "core_workflow_ast.json"
    assert result.artifact_paths["semantic_ir"].name == "semantic_ir.json"
    assert result.artifact_paths["runtime_plan"].name == "runtime_plan.json"
    assert result.manifest.artifact_paths["runtime_plan"].endswith("/runtime_plan.json")
    assert result.manifest.artifact_status["executable_ir"] == "emitted"
    assert result.manifest.artifact_status["runtime_plan"] == "emitted"
    assert result.manifest.artifact_status["core_workflow_ast"] == "emitted"
    assert result.manifest.artifact_status["semantic_ir"] == "emitted"
    _assert_no_runtime_closure_markers(json.dumps(core_workflow_ast, sort_keys=True))
    _assert_no_runtime_closure_markers(json.dumps(semantic_ir, sort_keys=True))
    _assert_no_runtime_closure_markers(json.dumps(executable_ir, sort_keys=True))
    _assert_no_runtime_closure_markers(json.dumps(runtime_plan, sort_keys=True))


def test_build_artifacts_persist_diagnostic_validation_metadata(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    write_build_artifacts = getattr(build, "_write_build_artifacts")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    artifact_root = tmp_path / "diagnostic_artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    diagnostic = LispFrontendDiagnostic(
        code="source_map_executable_node_unmapped",
        message="executable node `run__step` does not resolve to a declared origin",
        span=SourceSpan(
            start=SourcePosition(path="lineage_pkg/entry.orc", line=24, column=3, offset=0),
            end=SourcePosition(path="lineage_pkg/entry.orc", line=24, column=18, offset=15),
        ),
        validation_pass="executable",
        authority_layer="frontend",
    )

    artifact_paths = write_build_artifacts(
        build_root=artifact_root,
        compile_result=result.compile_result,
        validated_bundle=result.validated_bundle,
        entry_selection=result.entry_selection,
        diagnostics=(diagnostic,),
        emit_debug_yaml=False,
        source_map_payload=json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8")),
        workflow_boundary_projection_payload=json.loads(
            result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
        ),
        adapter_census_payload=None,
        boundary_authority_report_payload=None,
        g8_deletion_evidence_payload=None,
        value_flow_census_report_payload=None,
    )
    payload = json.loads(artifact_paths["diagnostics"].read_text(encoding="utf-8"))

    assert payload == [
        {
            "authority_layer": "frontend",
            "code": "source_map_executable_node_unmapped",
            "column": 3,
            "diagnostic_kind": "validation",
            "expansion_stack": [],
            "form_path": [],
            "line": 24,
            "message": "executable node `run__step` does not resolve to a declared origin",
            "notes": [],
            "path": "lineage_pkg/entry.orc",
            "phase": "executable",
            "severity": "error",
            "validation_pass": "executable",
        }
    ]


def test_build_persists_warning_lints_in_diagnostics_artifact_on_success(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_lint_warning_variant_output_request(tmp_path))
    payload = json.loads(result.artifact_paths["diagnostics"].read_text(encoding="utf-8"))

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "variant_output_without_variant_specific_fields",
    ]
    assert payload == [
        {
            "authority_layer": "frontend",
            "code": "variant_output_without_variant_specific_fields",
            "column": 3,
            "diagnostic_kind": "required_lint",
            "expansion_stack": [],
            "form_path": ["workflow-lisp", "defworkflow", "orchestrate"],
            "line": 18,
            "message": "union `ImplementationAttempt` lowers without variant-specific fields; prefer a record plus enum",
            "notes": [],
            "path": str((FIXTURES / "valid" / "lint_warning_variant_output.orc").resolve()),
            "phase": "typecheck",
            "severity": "warn",
            "validation_pass": "contract",
        }
    ]


def test_build_runtime_plan_artifact_matches_selected_workflow_lineage_and_manifest(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    executable_ir = json.loads(result.artifact_paths["executable_ir"].read_text(encoding="utf-8"))
    runtime_plan = json.loads(result.artifact_paths["runtime_plan"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    selected_workflow = result.validated_bundle.surface.name
    runtime_plan_node_ids = set(runtime_plan["nodes"])
    executable_ir_node_ids = set(executable_ir["nodes"])
    source_map_node_ids = {
        node["node_id"]
        for node in source_map["workflows"][selected_workflow]["executable_nodes"]
    }

    assert executable_ir["schema_version"] == "workflow_executable_ir.v1"
    assert runtime_plan["schema_version"] == "workflow_runtime_plan.v1"
    assert runtime_plan["workflow_name"] == selected_workflow
    assert semantic_ir["schema_version"] == "workflow_semantic_ir.v1"
    assert semantic_ir["workflows"][selected_workflow]["workflow_name"] == selected_workflow
    assert json.loads(result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8"))["schema_version"] == (
        "core_workflow_ast.v1"
    )
    assert executable_ir_node_ids == runtime_plan_node_ids
    assert runtime_plan_node_ids == source_map_node_ids
    assert result.manifest.artifact_paths["runtime_plan"].endswith("/runtime_plan.json")
    assert result.manifest.artifact_status["executable_ir"] == "emitted"
    assert result.manifest.artifact_status["runtime_plan"] == "emitted"
    assert result.manifest.artifact_status["core_workflow_ast"] == "emitted"
    assert result.manifest.artifact_status["semantic_ir"] == "emitted"


def test_prompt_extern_object_entries_are_accepted_by_build_service(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    asset_result = build_frontend_bundle(
        request_cls(
            source_path=ENTRYPOINT,
            source_roots=(SOURCE_ROOT,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.asset-file-object.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path / "asset",
        )
    )
    input_result = build_frontend_bundle(
        request_cls(
            source_path=ENTRYPOINT,
            source_roots=(SOURCE_ROOT,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.input-file.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path / "input",
        )
    )

    asset_binding = asset_result.compile_result.entry_result.extern_environment.bindings_by_name[
        "prompts.implementation.execute"
    ]
    input_binding = input_result.compile_result.entry_result.extern_environment.bindings_by_name[
        "prompts.implementation.execute"
    ]

    assert asset_binding.source_kind == "asset_file"
    assert asset_binding.path == "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
    assert asset_binding.asset_file == "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
    assert input_binding.source_kind == "input_file"
    assert input_binding.path == "prompts/workspace/implementation/execute.md"
    assert input_binding.asset_file is None


def test_prompt_extern_asset_file_shorthand_normalization_in_build_service(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    shorthand = build_frontend_bundle(
        request_cls(
            source_path=ENTRYPOINT,
            source_roots=(SOURCE_ROOT,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path / "shorthand",
        )
    )
    explicit = build_frontend_bundle(
        request_cls(
            source_path=ENTRYPOINT,
            source_roots=(SOURCE_ROOT,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.asset-file-object.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path / "explicit",
        )
    )

    shorthand_binding = shorthand.compile_result.entry_result.extern_environment.bindings_by_name[
        "prompts.implementation.execute"
    ]
    explicit_binding = explicit.compile_result.entry_result.extern_environment.bindings_by_name[
        "prompts.implementation.execute"
    ]

    assert shorthand_binding.source_kind == explicit_binding.source_kind == "asset_file"
    assert shorthand_binding.path == explicit_binding.path
    assert shorthand_binding.asset_file == explicit_binding.asset_file


def test_prompt_extern_asset_file_shorthand_normalization_stabilizes_fingerprint_and_producer_context(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")
    compiler = importlib.import_module("orchestrator.workflow_lisp.compiler")
    derive_context = getattr(compiler, "_derive_reusable_state_producer_context")

    shorthand = build_frontend_bundle(
        request_cls(
            source_path=ENTRYPOINT,
            source_roots=(SOURCE_ROOT,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path / "shorthand-fingerprint",
        )
    )
    explicit = build_frontend_bundle(
        request_cls(
            source_path=ENTRYPOINT,
            source_roots=(SOURCE_ROOT,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.asset-file-object.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path / "explicit-fingerprint",
        )
    )

    stage1 = compile_stage1_entrypoint(ENTRYPOINT, source_roots=(SOURCE_ROOT,))
    command_env = build_command_boundary_environment(
        {
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        }
    )
    shorthand_context = derive_context(
        definition_module=stage1.entry_module,
        source_file_digests={"entry.orc": "abc123"},
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundary_environment=command_env,
        imported_workflow_bundles={},
    )
    explicit_context = derive_context(
        definition_module=stage1.entry_module,
        source_file_digests={"entry.orc": "abc123"},
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": {"asset_file": "prompts/implementation/execute.md"}},
        command_boundary_environment=command_env,
        imported_workflow_bundles={},
    )

    assert shorthand.manifest.fingerprint == explicit.manifest.fingerprint
    assert shorthand_context["compile_inputs_fingerprint"] == explicit_context["compile_inputs_fingerprint"]


def test_prompt_extern_object_entries_emit_source_kind_aware_reusable_state_metadata() -> None:
    compiler = importlib.import_module("orchestrator.workflow_lisp.compiler")
    derive_context = getattr(compiler, "_derive_reusable_state_producer_context")
    stage1 = compile_stage1_entrypoint(ENTRYPOINT, source_roots=(SOURCE_ROOT,))
    command_env = build_command_boundary_environment(
        {
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        }
    )

    asset_context = derive_context(
        definition_module=stage1.entry_module,
        source_file_digests={"entry.orc": "abc123"},
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": {"asset_file": "prompts/implementation/execute.md"}},
        command_boundary_environment=command_env,
        imported_workflow_bundles={},
    )
    input_context = derive_context(
        definition_module=stage1.entry_module,
        source_file_digests={"entry.orc": "abc123"},
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": {"input_file": "prompts/workspace/implementation/execute.md"}},
        command_boundary_environment=command_env,
        imported_workflow_bundles={},
    )

    assert asset_context["prompt_extern_bindings"] == {
        "prompts.implementation.execute": "prompts/implementation/execute.md"
    }
    assert asset_context["prompt_extern_source_bindings"] == {
        "prompts.implementation.execute": {"asset_file": "prompts/implementation/execute.md"}
    }
    assert input_context["prompt_extern_bindings"] == {}
    assert input_context["prompt_extern_source_bindings"] == {
        "prompts.implementation.execute": {"input_file": "prompts/workspace/implementation/execute.md"}
    }


@pytest.mark.parametrize(
    "payload",
    [
        {
            "prompts.implementation.execute": {
                "asset_file": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md",
                "input_file": "prompts/workspace/implementation/execute.md",
            }
        },
        {
            "prompts.implementation.execute": {
                "source_kind": "input_file",
                "path": "prompts/workspace/implementation/execute.md",
            }
        },
        {"prompts.implementation.execute": {"unknown": "value"}},
        {"prompts.implementation.execute": {"asset_file": 5}},
    ],
)
def test_prompt_extern_object_shape_invalid_diagnostic(tmp_path: Path, payload: dict[str, object]) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    manifest_path = tmp_path / "prompts.invalid-object.json"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_frontend_bundle(
            request_cls(
                source_path=ENTRYPOINT,
                source_roots=(SOURCE_ROOT,),
                entry_workflow="orchestrate",
                provider_externs_path=CLI_FIXTURES / "providers.json",
                prompt_externs_path=manifest_path,
                imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
                command_boundaries_path=CLI_FIXTURES / "commands.json",
                emit_debug_yaml=False,
                workspace_root=tmp_path,
            )
        )

    assert excinfo.value.diagnostics[0].code == "workflow_lisp_manifest_invalid"
    assert "prompt externs manifest entries" in excinfo.value.diagnostics[0].message


def test_build_artifacts_emit_private_artifact_catalog(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    result = build_frontend_bundle(
        request_cls(
            source_path=REPO_ROOT / "workflows" / "examples" / "review_revise_design_docs.orc",
            source_roots=(REPO_ROOT / "workflows" / "examples",),
            entry_workflow="review-revise-design-docs",
            provider_externs_path=(
                REPO_ROOT / "workflows" / "examples" / "inputs" / "review_revise_design_docs" / "providers.json"
            ),
            prompt_externs_path=(
                REPO_ROOT / "workflows" / "examples" / "inputs" / "review_revise_design_docs" / "prompts.json"
            ),
            imported_workflow_bundles_path=None,
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    executable_ir = json.loads(result.artifact_paths["executable_ir"].read_text(encoding="utf-8"))

    assert executable_ir["private_artifacts"] == {}


def test_semantic_ir_private_artifact_catalog_bridge(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    result = build_frontend_bundle(
        request_cls(
            source_path=REPO_ROOT / "workflows" / "examples" / "review_revise_design_docs.orc",
            source_roots=(REPO_ROOT / "workflows" / "examples",),
            entry_workflow="review-revise-design-docs",
            provider_externs_path=(
                REPO_ROOT / "workflows" / "examples" / "inputs" / "review_revise_design_docs" / "providers.json"
            ),
            prompt_externs_path=(
                REPO_ROOT / "workflows" / "examples" / "inputs" / "review_revise_design_docs" / "prompts.json"
            ),
            imported_workflow_bundles_path=None,
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    executable_ir = json.loads(result.artifact_paths["executable_ir"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))

    assert result.validated_bundle.ir.private_artifacts == {}
    assert executable_ir["private_artifacts"] == {}
    assert semantic_ir["workflows"][result.selected_workflow_name]["workflow_name"] == result.selected_workflow_name


def test_build_manifest_records_source_map_schema_and_coverage_for_emitted_artifacts(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))

    assert result.manifest.source_map_schema_version == "workflow_lisp_source_map.v1"
    assert result.manifest.source_map_coverage == {
        "frontend_ast": "covered",
        "lowered_surface": "covered",
        "shared_validation_subjects": "covered",
        "executable_ir": "covered",
        "runtime_logs": "covered",
        "core_workflow_ast": "covered",
        "semantic_ir": "covered",
    }


def test_build_artifacts_preserve_statement_taxonomy_facet_lineage(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    structured_result = build_frontend_bundle(_structured_results_request(tmp_path))
    structured_core = json.loads(structured_result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8"))
    structured_semantic = json.loads(structured_result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    structured_source_map = json.loads(structured_result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    structured_workflow = structured_result.entry_selection.canonical_name
    command_checks_workflow = "lineage_pkg/entry::command_checks"

    assert [statement["kind"] for statement in structured_core["body"]] == ["call"]
    assert structured_semantic["workflows"][structured_workflow]["call_edge_ids"]
    assert structured_source_map["workflows"][command_checks_workflow]["generated_internal_inputs"]

    snapshot_source = (FIXTURES / "valid" / "phase_snapshot_effects.orc").read_text(encoding="utf-8")
    snapshot_module_path = tmp_path / "phase" / "snapshot.orc"
    snapshot_module_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_module_path.write_text(
        snapshot_source.replace(
            '  (defmodule phase_snapshot_effects)\n',
            '  (defmodule phase/snapshot)\n',
            1,
        ),
        encoding="utf-8",
    )
    snapshot_result = build_frontend_bundle(
        request_cls(
            source_path=snapshot_module_path,
            source_roots=(tmp_path,),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=None,
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    snapshot_core = json.loads(snapshot_result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8"))
    snapshot_semantic = json.loads(snapshot_result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    snapshot_source_map = json.loads(snapshot_result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    snapshot_workflow = snapshot_result.entry_selection.canonical_name
    snapshot_effect_kinds = {
        effect["effect_kind"]
        for effect in snapshot_semantic["effects"].values()
    }

    assert "select_variant_output" in [statement["kind"] for statement in snapshot_core["body"]]
    assert {"pointer_materialization", "snapshot_capture"}.issubset(snapshot_effect_kinds)
    assert any(
        effect["effect_kind"] == "snapshot_capture"
        for effect in snapshot_source_map["workflows"][snapshot_workflow]["generated_semantic_effects"]
    )
    assert any(
        node["step_kind"] == "select_variant_output"
        for node in snapshot_source_map["workflows"][snapshot_workflow]["core_nodes"]
    )

    resource_source = (FIXTURES / "valid" / "resource_stdlib_transition.orc").read_text(encoding="utf-8")
    resource_module_path = tmp_path / "resource" / "module.orc"
    resource_module_path.parent.mkdir(parents=True, exist_ok=True)
    resource_module_path.write_text(
        resource_source.replace(
            '  (:target-dsl "2.14")\n',
            '  (:target-dsl "2.14")\n  (defmodule resource/module)\n  (export move-selected-item)\n',
            1,
        ),
        encoding="utf-8",
    )
    resource_result = build_frontend_bundle(
        request_cls(
            source_path=resource_module_path,
            source_roots=(tmp_path,),
            entry_workflow="move-selected-item",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.LEGACY,
        )
    )
    resource_core = json.loads(resource_result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8"))
    resource_semantic = json.loads(resource_result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    resource_source_map = json.loads(resource_result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    resource_workflow = resource_result.entry_selection.canonical_name

    assert [statement["kind"] for statement in resource_core["body"]] == ["command"]
    assert any(
        boundary["boundary_kind"] == "certified_adapter"
        and boundary["boundary_name"] == "apply_resource_transition"
        for boundary in resource_semantic["command_boundaries"].values()
    )
    assert {
        effect["effect_kind"]
        for effect in resource_semantic["effects"].values()
    } >= {"command_call", "resource_transition", "ledger_update"}
    assert resource_source_map["workflows"][resource_workflow]["command_boundaries"]


def test_build_semantic_ir_uses_current_source_map_validation_subject_bridges(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    first = build_frontend_bundle(_build_request(tmp_path))
    selected_workflow = first.entry_selection.canonical_name

    def validation_subject_names(result) -> set[tuple[str, str]]:
        source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
        return {
            (
                binding["subject_ref"]["subject_kind"],
                binding["subject_ref"]["subject_name"],
            )
            for binding in source_map["workflows"][selected_workflow]["validation_subjects"]
        }

    def semantic_ir_subject_names(result) -> set[tuple[str, str]]:
        semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
        return {
            (
                entry["subject_ref"]["subject_kind"],
                entry["subject_ref"]["subject_name"],
            )
            for entry in semantic_ir["source_map"].values()
            if entry["bridge_kind"] == "validation_subject" and entry["workflow_name"] == selected_workflow
        }

    assert semantic_ir_subject_names(first) == validation_subject_names(first)

    stale_source_map = json.loads(first.artifact_paths["source_map"].read_text(encoding="utf-8"))
    stale_source_map["workflows"][selected_workflow]["validation_subjects"] = stale_source_map["workflows"][
        selected_workflow
    ]["validation_subjects"][:1]
    first.artifact_paths["source_map"].write_text(
        json.dumps(stale_source_map, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    second = build_frontend_bundle(_build_request(tmp_path))

    assert semantic_ir_subject_names(second) == validation_subject_names(second)


def test_export_request_normalization_resolves_default_and_explicit_destinations(tmp_path: Path) -> None:
    build = _build_module()
    normalize_exports = getattr(build, "normalize_frontend_artifact_exports")

    requests = normalize_exports(
        {
            "executable_ir": [None],
            "core_workflow_ast": [None],
            "runtime_plan": ["exports/runtime/runtime_plan.snapshot.json"],
            "semantic_ir": ["exports/semantic_ir.snapshot.json"],
            "source_map": [None],
        },
        cwd=tmp_path,
        source_path=ENTRYPOINT,
    )

    assert requests["executable_ir"].destination == (tmp_path / "executable_ir.json").resolve()
    assert requests["core_workflow_ast"].destination == (tmp_path / "core_workflow_ast.json").resolve()
    assert requests["runtime_plan"].destination == (
        tmp_path / "exports" / "runtime" / "runtime_plan.snapshot.json"
    ).resolve()
    assert requests["semantic_ir"].destination == (tmp_path / "exports" / "semantic_ir.snapshot.json").resolve()
    assert requests["source_map"].destination == (tmp_path / "source_map.json").resolve()
    assert (tmp_path / "exports").is_dir()


def test_export_request_normalization_rejects_duplicate_requests(tmp_path: Path) -> None:
    build = _build_module()
    normalize_exports = getattr(build, "normalize_frontend_artifact_exports")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        normalize_exports(
            {
                "core_workflow_ast": [None, "exports/core_workflow_ast.json"],
            },
            cwd=tmp_path,
            source_path=ENTRYPOINT,
        )

    assert excinfo.value.diagnostics[0].phase == "cli_request"
    assert "requested more than once" in excinfo.value.diagnostics[0].message


def test_export_request_normalization_rejects_existing_directory_destination(tmp_path: Path) -> None:
    build = _build_module()
    normalize_exports = getattr(build, "normalize_frontend_artifact_exports")
    destination = tmp_path / "exports"
    destination.mkdir()

    with pytest.raises(LispFrontendCompileError) as excinfo:
        normalize_exports(
            {
                "semantic_ir": ["exports"],
            },
            cwd=tmp_path,
            source_path=ENTRYPOINT,
        )

    assert excinfo.value.diagnostics[0].phase == "cli_request"
    assert "existing directory" in excinfo.value.diagnostics[0].message


def test_exported_artifacts_copy_canonical_bytes_without_mutating_manifest_or_canonical_paths(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    emit_exports = getattr(build, "emit_requested_frontend_artifact_exports")
    normalize_exports = getattr(build, "normalize_frontend_artifact_exports")

    request = replace(_build_request(tmp_path), emit_debug_yaml=True)
    result = build_frontend_bundle(request)
    original_manifest_paths = dict(result.manifest.artifact_paths)
    original_artifact_paths = dict(result.artifact_paths)
    export_requests = normalize_exports(
        {
            "executable_ir": ["exports/runtime/executable_ir.json"],
            "core_workflow_ast": ["exports/core/core_workflow_ast.json"],
            "runtime_plan": ["exports/runtime/runtime_plan.json"],
            "semantic_ir": ["exports/semantic/semantic_ir.json"],
            "source_map": ["exports/maps/source_map.json"],
            "expanded_debug_yaml": ["exports/debug/expanded.debug.yaml"],
        },
        cwd=tmp_path,
        source_path=ENTRYPOINT,
    )

    exported = emit_exports(result=result, export_requests=export_requests)

    assert exported["executable_ir"].read_bytes() == result.artifact_paths["executable_ir"].read_bytes()
    assert exported["core_workflow_ast"].read_bytes() == result.artifact_paths["core_workflow_ast"].read_bytes()
    assert exported["runtime_plan"].read_bytes() == result.artifact_paths["runtime_plan"].read_bytes()
    assert exported["semantic_ir"].read_bytes() == result.artifact_paths["semantic_ir"].read_bytes()
    assert exported["source_map"].read_bytes() == result.artifact_paths["source_map"].read_bytes()
    assert exported["expanded_debug_yaml"].read_bytes() == result.artifact_paths["expanded_debug_yaml"].read_bytes()
    assert result.manifest.artifact_paths == original_manifest_paths
    assert dict(result.artifact_paths) == original_artifact_paths


def test_build_result_same_file_validated_bundles_keep_executable_and_runtime_surfaces(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    command_checks_bundle = result.compile_result.validated_bundles_by_name["lineage_pkg/entry::command_checks"]

    assert isinstance(command_checks_bundle, type(result.validated_bundle))
    assert command_checks_bundle.ir.schema_version == "workflow_executable_ir.v1"
    assert command_checks_bundle.runtime_plan.schema_version == "workflow_runtime_plan.v1"


def test_build_frontend_bundle_emits_authored_defaults_via_public_inputs_and_boundary_projection(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_workflow_param_default_request(tmp_path))
    public_inputs = _workflow_public_input_contracts(result.validated_bundle)
    projection = json.loads(result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8"))
    workflow_projection = next(
        workflow
        for workflow in projection["workflows"]
        if workflow["workflow_name"] == "defaults_pkg/entry::defaults"
    )
    flattened_inputs = {field["generated_name"]: field["contract_definition"] for field in workflow_projection["flattened_inputs"]}

    assert public_inputs["message"]["default"] == "hello"
    assert public_inputs["count"]["default"] == 3
    assert public_inputs["score"]["default"] == 0.5
    assert public_inputs["enabled"]["default"] is True
    assert public_inputs["status"]["default"] == "ready"
    assert public_inputs["report_path"]["default"] == "default.md"
    assert flattened_inputs["message"]["default"] == "hello"
    assert flattened_inputs["count"]["default"] == 3
    assert flattened_inputs["score"]["default"] == 0.5
    assert flattened_inputs["enabled"]["default"] is True
    assert flattened_inputs["status"]["default"] == "ready"
    assert flattened_inputs["report_path"]["default"] == "default.md"


def test_resume_or_start_generated_internal_inputs_keep_reusable_state_paths_runtime_only(
    tmp_path: Path,
) -> None:
    result = _compile_resume_fixture(tmp_path)

    bundle = result.validated_bundles["phase_stdlib_resume_or_start::resume-record-phase"]
    runtime_inputs = _workflow_runtime_input_contracts(bundle)
    public_inputs = _workflow_public_input_contracts(bundle)
    managed_inputs = workflow_managed_write_root_inputs(bundle)
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "phase_stdlib_resume_or_start::resume-record-phase"
    )
    branch_step = lowered.authored_mapping["steps"][1]
    start_steps = branch_step["match"]["cases"]["START"]["steps"]
    writer_step = next(
        step
        for step in start_steps
        if step.get("command", [])[:3]
        == [
            "python",
            "-m",
            "orchestrator.workflow_lisp.adapters.write_reusable_phase_state_v1",
        ]
    )
    writer_hidden_input = writer_step["output_bundle"]["path"].removeprefix("${inputs.").removesuffix("}")

    assert writer_hidden_input in managed_inputs
    assert writer_hidden_input in runtime_inputs
    assert writer_hidden_input not in public_inputs
    assert writer_step["output_bundle"]["path"] in lowered.origin_map.generated_path_spans


def test_workflow_boundary_projection_emits_generated_path_allocations(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    projection = json.loads(result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8"))
    workflow_projection = _workflow_payload_by_suffix(projection, "provider_attempt")
    allocations = workflow_projection["generated_path_allocations"]
    provider_bundle = _allocation_payload_by_role(allocations, "provider_result_bundle")
    generated_inputs = {
        entry["generated_name"]: entry
        for entry in workflow_projection["generated_internal_inputs"]
    }

    assert provider_bundle["privacy"] == "private_generated"
    assert provider_bundle["resume_scope"] == "step_visit"
    assert provider_bundle["generated_input_name"].startswith("__write_root__")
    assert provider_bundle["generated_input_name"].endswith("__result_bundle")
    assert generated_inputs[provider_bundle["generated_input_name"]]["allocation_id"] == provider_bundle["allocation_id"]


def test_source_map_emits_generated_path_allocations(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    workflow_name = next(name for name in source_map["workflows"] if name.endswith("::provider_attempt"))
    workflow = source_map["workflows"][workflow_name]
    provider_bundle = _allocation_payload_by_role(
        workflow["generated_path_allocations"],
        "provider_result_bundle",
    )
    generated_path = workflow["generated_paths"][provider_bundle["concrete_path_template"]]

    assert provider_bundle["privacy"] == "private_generated"
    assert provider_bundle["generated_input_name"].startswith("__write_root__")
    assert provider_bundle["generated_input_name"].endswith("__result_bundle")
    assert provider_bundle["origin_key"] == generated_path["origin_key"]


def test_semantic_ir_emits_generated_path_allocations(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    provider_layout = next(
        entry
        for entry in semantic_ir["state_layout"].values()
        if entry["workflow_name"].endswith("::orchestrate")
        and entry["layout_kind"] == "reusable_call_write_root"
    )

    assert provider_layout["details"]["privacy"] == "compatibility_view"
    assert provider_layout["details"]["resume_scope"] == "call_frame"
    assert provider_layout["details"]["generated_input_name"].startswith("__write_root__")
    assert provider_layout["details"]["generated_input_name"].endswith("__result_bundle")
    assert provider_layout["details"]["allocation_id"]


def test_provider_bundle_path_projection_boundary_provenance(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_selector_projection_request(tmp_path))
    projection = json.loads(result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8"))
    workflow_projection = _workflow_payload_by_suffix(projection, "select-next-work")
    flattened_outputs = {
        field["generated_name"]: field
        for field in workflow_projection["flattened_outputs"]
    }
    selection_bundle = flattened_outputs["return__selection_bundle_path"]
    provenance = selection_bundle["projection"]

    assert selection_bundle["contract_definition"]["under"] == "state"
    assert provenance["projection_class"] == "provider_bundle_path_projection"
    assert provenance["authority_class"] == "materialized_view"
    assert provenance["output_kind"] == "output_bundle"
    assert provenance["source_step_id"]


def test_provider_bundle_path_projection_semantic_ir_lineage(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_selector_projection_request(tmp_path))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    projection_effect = next(
        effect
        for effect in semantic_ir["effects"].values()
        if effect["effect_kind"] == "provider_bundle_path_projection"
    )

    assert projection_effect["details"]["projection_class"] == "provider_bundle_path_projection"
    assert projection_effect["details"]["authority_class"] == "materialized_view"
    assert projection_effect["details"]["projected_output_name"] == "return__selection_bundle_path"
    assert projection_effect["details"]["semantic_authority"] == "provider_structured_output_bundle"


def test_provider_bundle_path_projection_source_map_lineage(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_selector_projection_request(tmp_path))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    workflow_name = next(name for name in source_map["workflows"] if name.endswith("::select-next-work"))
    workflow = source_map["workflows"][workflow_name]
    projection_effect = next(
        effect
        for effect in workflow["generated_semantic_effects"]
        if effect["effect_kind"] == "provider_bundle_path_projection"
    )

    assert projection_effect["details"]["projection_class"] == "provider_bundle_path_projection"
    assert projection_effect["details"]["authority_class"] == "materialized_view"
    assert projection_effect["details"]["projected_output_name"] == "return__selection_bundle_path"
    assert projection_effect["details"]["semantic_authority"] == "provider_structured_output_bundle"
    assert projection_effect["details"].get("allocation_id") or projection_effect["details"].get("path_template")


def test_provider_bundle_path_projection_contract_metadata(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_selector_projection_request(tmp_path))
    projection = json.loads(result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8"))
    workflow_projection = _workflow_payload_by_suffix(projection, "select-next-work")
    flattened_outputs = {
        field["generated_name"]: field
        for field in workflow_projection["flattened_outputs"]
    }
    provenance = flattened_outputs["return__selection_bundle_path"]["projection"]

    assert provenance["projection_id"]
    assert provenance["projection_class"] == "provider_bundle_path_projection"
    assert provenance["authority_class"] == "materialized_view"
    assert provenance["bundle_under"] == "state"
    assert provenance["bundle_must_exist_target"] is False
    assert provenance["negative_validation_cases"] == [
        "missing_bundle",
        "stale_input",
        "schema_mismatch",
        "path_escape",
        "pointer_authority_rejected",
    ]
    assert provenance.get("path_template") or provenance.get("allocation_id")


def test_build_artifacts_emit_entrypoint_managed_write_root_allocations(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_resume_entry_request(tmp_path))
    projection = json.loads(result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8"))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))

    workflow_name = "neurips/helper::provider-attempt"
    workflow_projection = next(
        workflow
        for workflow in projection["workflows"]
        if workflow["workflow_name"] == workflow_name
    )
    entrypoint_projection = _allocation_payload_by_role(
        workflow_projection["generated_path_allocations"],
        "entrypoint_managed_write_root",
    )
    source_map_workflow = source_map["workflows"][workflow_name]
    entrypoint_source_map = _allocation_payload_by_role(
        source_map_workflow["generated_path_allocations"],
        "entrypoint_managed_write_root",
    )
    entrypoint_layout = next(
        entry
        for entry in semantic_ir["state_layout"].values()
        if entry["workflow_name"] == workflow_name
        and entry["layout_kind"] == "entrypoint_managed_write_root"
    )

    assert entrypoint_projection["privacy"] == "private_generated"
    assert entrypoint_projection["resume_scope"] == "run"
    assert entrypoint_projection["generated_input_name"].startswith("__write_root__")
    assert "${runtime.run_id}" in entrypoint_projection["concrete_path_template"]
    assert entrypoint_source_map["allocation_id"] == entrypoint_projection["allocation_id"]
    assert entrypoint_layout["details"]["allocation_id"] == entrypoint_projection["allocation_id"]


def test_design_delta_work_item_runtime_context_inputs_stay_internal(
    tmp_path: Path,
) -> None:
    _, _, compile_result = _compile_design_delta_work_item_without_shared_validation(tmp_path)
    lowered = _design_delta_work_item_run_work_item_lowered(compile_result)
    authored_inputs = set(lowered.authored_mapping["inputs"])
    flattened_input_names = {
        field.generated_name
        for field in lowered.boundary_projection.flattened_inputs
    }
    internal_inputs = {
        item.generated_name: item.reason
        for item in lowered.boundary_projection.generated_internal_inputs
    }

    assert internal_inputs
    assert set(internal_inputs).issubset(authored_inputs)
    assert {
        name
        for name, reason in internal_inputs.items()
        if reason == "managed_write_root"
    }.isdisjoint(flattened_input_names)
    assert {
        name
        for name, reason in internal_inputs.items()
        if reason == "runtime_owned_context"
    }.issubset(flattened_input_names)
    assert "progress_ledger_path" in flattened_input_names
    assert "run_state_path" not in flattened_input_names
    assert set(internal_inputs.values()) == {
        "managed_write_root",
        "runtime_owned_context",
        "compatibility_bridge",
    }
    assert all(
        name.startswith("__write_root__")
        for name, reason in internal_inputs.items()
        if reason == "managed_write_root"
    )


def test_design_delta_work_item_direct_entry_phase_context_binding_uses_runtime_bootstrap_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
    )
    bundle = built.validated_bundle.imports[
        "lisp_frontend_design_delta/work_item::run-work-item"
    ]
    boundary = _workflow_boundary_projection(bundle)

    binding = next(
        item for item in boundary.private_runtime_context_bindings if item.binding_id == "phase-ctx"
    )

    assert binding.bridge_class == "runtime_owned_context"
    assert binding.projection_hints == {
        "context_binding_schema_version": 1,
        "context_input_roles": {
            "phase-ctx__run__run-id": "run_anchor:run-id",
            "phase-ctx__run__state-root": "run_anchor:state-root",
            "phase-ctx__run__artifact-root": "run_anchor:artifact-root",
            "phase-ctx__phase-name": "compile_time_default",
            "phase-ctx__state-root": "compile_time_default",
            "phase-ctx__artifact-root": "compile_time_default",
        },
    }


def test_design_delta_plan_phase_boundary_hides_phase_context_and_bridge_inputs(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "plan_phase.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={
            "providers.plan.draft": "codex",
            "providers.plan.review": "codex",
            "providers.plan.fix": "codex",
        },
        prompt_externs={
            "prompts.plan.draft": {
                "input_file": (
                    "workflows/library/prompts/"
                    "lisp_frontend_design_delta_plan_phase/draft_plan.md"
                )
            },
            "prompts.plan.review": {
                "input_file": (
                    "workflows/library/prompts/"
                    "lisp_frontend_design_delta_plan_phase/review_plan.md"
                )
            },
            "prompts.plan.fix": {
                "input_file": (
                    "workflows/library/prompts/"
                    "lisp_frontend_design_delta_plan_phase/revise_plan.md"
                )
            },
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    assert result.entry_result.lowering_schema_version == 2
    entry_result = result.entry_result
    bundle = entry_result.validated_bundles[
        "lisp_frontend_design_delta/plan_phase::run-plan-phase"
    ]
    public_inputs = set(_workflow_public_input_contracts(bundle))
    runtime_context_inputs = set(_workflow_runtime_context_inputs(bundle))

    assert runtime_context_inputs == {
        "phase-ctx__run__run-id",
        "phase-ctx__run__state-root",
        "phase-ctx__run__artifact-root",
        "phase-ctx__phase-name",
        "phase-ctx__state-root",
        "phase-ctx__artifact-root",
    }
    assert runtime_context_inputs.isdisjoint(public_inputs)
    assert "phase-ctx__state-root" not in public_inputs

    lowered = next(
        workflow
        for workflow in entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name
        == "lisp_frontend_design_delta/plan_phase::run-plan-phase"
    )
    runtime_internal_inputs = {
        item.generated_name
        for item in lowered.boundary_projection.generated_internal_inputs
        if item.reason == "runtime_owned_context"
    }
    assert "phase-ctx__state-root" in runtime_internal_inputs
    assert runtime_internal_inputs.issubset(lowered.origin_map.internal_input_spans)
    assert runtime_internal_inputs.isdisjoint(lowered.origin_map.authored_input_spans)


def test_design_delta_work_item_boundary_labels_legacy_state_inputs_as_compatibility_bridge(
    tmp_path: Path,
) -> None:
    _, _, compile_result = _compile_design_delta_work_item_without_shared_validation(tmp_path)
    assert compile_result.entry_result.lowering_schema_version == 2
    lowered = _design_delta_work_item_run_work_item_lowered(compile_result)
    internal_inputs = {
        item.generated_name: item.reason
        for item in lowered.boundary_projection.generated_internal_inputs
    }

    expected_bridge_inputs = {
        "progress_ledger_path",
        "run_state_path",
    }
    assert expected_bridge_inputs.issubset(lowered.compatibility_bridge_inputs)
    assert {internal_inputs[name] for name in expected_bridge_inputs} == {
        "compatibility_bridge"
    }
    assert expected_bridge_inputs.issubset(lowered.origin_map.internal_input_spans)
    assert expected_bridge_inputs.isdisjoint(lowered.origin_map.authored_input_spans)


def test_design_delta_work_item_command_boundary_lineage_records_family_adapters(
    tmp_path: Path,
) -> None:
    request = _design_delta_work_item_request(tmp_path)
    build = _build_module()
    resolved_request = getattr(build, "_resolve_request")(request)
    command_boundary_manifest = getattr(build, "_load_command_boundaries_manifest_payload")(
        resolved_request.command_boundaries_path,
    )
    boundary_names = set(command_boundary_manifest)

    assert "materialize_lisp_frontend_work_item_inputs" in boundary_names
    assert "classify_lisp_frontend_work_item_terminal" not in boundary_names
    assert "select_lisp_frontend_blocked_recovery_route" not in boundary_names
    assert command_boundary_manifest["materialize_lisp_frontend_work_item_inputs"][
        "stable_command"
    ] == [
        "python",
        "workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py",
    ]

    _, _, compile_result = _compile_design_delta_work_item_without_shared_validation(tmp_path)
    command_scripts = [
        tuple(step["command"])
        for workflow in compile_result.entry_result.lowered_workflows
        for step in _walk_design_delta_work_item_steps(workflow.authored_mapping.get("steps", []))
        if isinstance(step.get("command"), list)
    ]

    assert all(
        command[:2]
        != (
            "python",
            "workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py",
        )
        for command in command_scripts
    )
    assert all(
        command[:2]
        != (
            "python",
            "workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py",
        )
        for command in command_scripts
    )
    assert all(
        command[:2]
        != (
            "python",
            "workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py",
        )
        for command in command_scripts
    )


def test_promoted_entry_runtime_context_inputs_stay_internal_and_appear_in_projection(
    tmp_path: Path,
) -> None:
    fixture = FIXTURES / "valid" / "phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc"
    result = compile_stage3_entrypoint(
        fixture,
        source_roots=(FIXTURES / "valid",),
        command_boundaries={
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    ).entry_result

    workflow_name = (
        "phase_stdlib_resume_or_start_promoted_entry_bootstrap::"
        "promoted-entry-resume-plan-gate-wrapper"
    )
    bundle = result.validated_bundles[workflow_name]
    runtime_inputs = _workflow_runtime_input_contracts(bundle)
    public_inputs = _workflow_public_input_contracts(bundle)
    runtime_context_inputs = set(_workflow_runtime_context_inputs(bundle))
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == workflow_name
    )

    assert runtime_context_inputs == {
        "phase-ctx__run__run-id",
        "phase-ctx__run__state-root",
        "phase-ctx__run__artifact-root",
        "phase-ctx__phase-name",
        "phase-ctx__state-root",
        "phase-ctx__artifact-root",
    }
    assert runtime_context_inputs.issubset(runtime_inputs)
    assert runtime_context_inputs.isdisjoint(public_inputs)
    assert {
        item.generated_name: item.reason
        for item in lowered.boundary_projection.generated_internal_inputs
        if item.reason == "runtime_owned_context"
    } == {
        "phase-ctx__run__run-id": "runtime_owned_context",
        "phase-ctx__run__state-root": "runtime_owned_context",
        "phase-ctx__run__artifact-root": "runtime_owned_context",
        "phase-ctx__phase-name": "runtime_owned_context",
        "phase-ctx__state-root": "runtime_owned_context",
        "phase-ctx__artifact-root": "runtime_owned_context",
    }


def test_promoted_entry_private_exec_context_binding_metadata_drives_boundary_projection(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")
    fixture = tmp_path / "private_exec_context_phase_entry.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule private_exec_context_phase_entry)",
                "  (import std/phase :only (with-phase))",
                "  (export entry run-phase)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord Result",
                "    (label String)",
                "    (phase_name Symbol))",
                "  (defworkflow entry",
                "    ((label String))",
                "    -> Result",
                "    (call run-phase",
                "      :label label))",
                "  (defworkflow run-phase",
                "    ((phase-ctx PhaseCtx)",
                "     (label String))",
                "    -> Result",
                "    (with-phase phase-ctx plan-gate-wrapper",
                "      (record Result",
                "        :label label",
                "        :phase_name phase-ctx.phase-name)))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    built = build_frontend_bundle(
        request_cls(
            source_path=fixture,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.LEGACY,
        )
    )
    result = built.compile_result.entry_result

    workflow_name = "private_exec_context_phase_entry::entry"
    bundle = result.validated_bundles[workflow_name]
    boundary = _workflow_boundary_projection(bundle)
    projection_payload = json.loads(
        built.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
    )
    workflow_projection = next(
        item
        for item in projection_payload["workflows"]
        if item["workflow_name"] == workflow_name
    )

    assert set(boundary.public_input_contracts) == set(_workflow_public_input_contracts(bundle))
    assert boundary.private_managed_write_root_inputs == ()
    assert boundary.private_compatibility_bridge_inputs == ()
    assert len(boundary.private_runtime_context_bindings) == 1

    binding = boundary.private_runtime_context_bindings[0]
    assert binding.binding_id == "phase-ctx"
    assert binding.source_param_name == "phase-ctx"
    assert binding.context_family == "PhaseCtx"
    assert binding.bridge_class == "runtime_owned_context"
    assert binding.required_capabilities == ("run",)
    assert binding.derived_phase_identity == "plan-gate-wrapper"
    assert set(binding.generated_input_names) == set(_workflow_runtime_context_inputs(bundle))
    assert binding.projection_hints == {
        "context_binding_schema_version": 1,
        "context_input_roles": {
            "phase-ctx__run__run-id": "run_anchor:run-id",
            "phase-ctx__run__state-root": "run_anchor:state-root",
            "phase-ctx__run__artifact-root": "run_anchor:artifact-root",
            "phase-ctx__phase-name": "compile_time_default",
            "phase-ctx__state-root": "compile_time_default",
            "phase-ctx__artifact-root": "compile_time_default",
        },
    }

    assert workflow_projection["boundary"]["public_input_names"] == sorted(
        _workflow_public_input_contracts(bundle)
    )
    assert workflow_projection["boundary"]["private_runtime_context_bindings"] == [
        {
            "binding_id": "phase-ctx",
            "source_param_name": "phase-ctx",
            "context_family": "PhaseCtx",
            "bridge_class": "runtime_owned_context",
            "derived_phase_identity": "plan-gate-wrapper",
            "generated_input_names": sorted(_workflow_runtime_context_inputs(bundle)),
        }
    ]
    assert workflow_projection["boundary"]["private_managed_write_root_inputs"] == []
    assert workflow_projection["boundary"]["private_compatibility_bridge_inputs"] == []
    assert workflow_projection["boundary"]["pure_projection_classification"] == {
        "structural": True
    }


def test_design_delta_item_ctx_child_phase_reuse_build_artifacts_record_derived_child_phase_binding(
    tmp_path: Path,
) -> None:
    built = _build_item_ctx_child_phase_reuse_fixture(tmp_path)
    bundle = built.compile_result.validated_bundles_by_name[
        "design_delta_item_ctx_child_phase_reuse::run-item-ctx-first"
    ]
    boundary = _workflow_boundary_projection(bundle)
    workflow_projection = next(
        item
        for item in json.loads(
            built.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
        )["workflows"]
        if item["workflow_name"] == "design_delta_item_ctx_child_phase_reuse::run-item-ctx-first"
    )

    public_inputs = set(_workflow_public_input_contracts(bundle))
    assert "phase-ctx__phase-name" not in public_inputs
    assert "phase-ctx__state-root" not in public_inputs
    assert "phase-ctx__artifact-root" not in public_inputs
    assert len(boundary.private_runtime_context_bindings) == 2
    assert {
        binding.derived_phase_identity
        for binding in boundary.private_runtime_context_bindings
    } == {"plan", "implementation"}
    assert {
        (
            binding.binding_id,
            binding.source_param_name,
            binding.context_family,
            binding.bridge_class,
            binding.derived_phase_identity,
            tuple(sorted(binding.generated_input_names)),
        )
        for binding in boundary.private_runtime_context_bindings
    } == {
        (
            "phase-ctx__implementation",
            "item-ctx",
            "PhaseCtx",
            "derived_private_child_context",
            "implementation",
            (
                "phase-ctx__implementation__artifact-root",
                "phase-ctx__implementation__phase-name",
                "phase-ctx__implementation__run__artifact-root",
                "phase-ctx__implementation__run__run-id",
                "phase-ctx__implementation__run__state-root",
                "phase-ctx__implementation__state-root",
            ),
        ),
        (
            "phase-ctx__plan",
            "item-ctx",
            "PhaseCtx",
            "derived_private_child_context",
            "plan",
            (
                "phase-ctx__plan__artifact-root",
                "phase-ctx__plan__phase-name",
                "phase-ctx__plan__run__artifact-root",
                "phase-ctx__plan__run__run-id",
                "phase-ctx__plan__run__state-root",
                "phase-ctx__plan__state-root",
            ),
        ),
    }

    assert {
        (
            binding["binding_id"],
            binding["source_param_name"],
            binding["bridge_class"],
            binding["derived_phase_identity"],
            tuple(binding["generated_input_names"]),
        )
        for binding in workflow_projection["boundary"]["private_runtime_context_bindings"]
    } == {
        (
            "phase-ctx__implementation",
            "item-ctx",
            "derived_private_child_context",
            "implementation",
            (
                "phase-ctx__implementation__artifact-root",
                "phase-ctx__implementation__phase-name",
                "phase-ctx__implementation__run__artifact-root",
                "phase-ctx__implementation__run__run-id",
                "phase-ctx__implementation__run__state-root",
                "phase-ctx__implementation__state-root",
            ),
        ),
        (
            "phase-ctx__plan",
            "item-ctx",
            "derived_private_child_context",
            "plan",
            (
                "phase-ctx__plan__artifact-root",
                "phase-ctx__plan__phase-name",
                "phase-ctx__plan__run__artifact-root",
                "phase-ctx__plan__run__run-id",
                "phase-ctx__plan__run__state-root",
                "phase-ctx__plan__state-root",
            ),
        ),
    }
    assert {
        binding.binding_id: binding.projection_hints
        for binding in boundary.private_runtime_context_bindings
    } == {
        "phase-ctx__implementation": {
            "context_binding_schema_version": 1,
            "context_input_roles": {
                "phase-ctx__implementation__run__run-id": "run_anchor:run-id",
                "phase-ctx__implementation__run__state-root": "run_anchor:state-root",
                "phase-ctx__implementation__run__artifact-root": "run_anchor:artifact-root",
                "phase-ctx__implementation__phase-name": "compile_time_default",
                "phase-ctx__implementation__state-root": "compile_time_default",
                "phase-ctx__implementation__artifact-root": "compile_time_default",
            },
            "carried_input_sources": {
                "phase-ctx__implementation__run__run-id": ("item-ctx", "run", "run-id"),
                "phase-ctx__implementation__run__state-root": (
                    "item-ctx",
                    "run",
                    "state-root",
                ),
                "phase-ctx__implementation__run__artifact-root": (
                    "item-ctx",
                    "run",
                    "artifact-root",
                ),
            },
        },
        "phase-ctx__plan": {
            "context_binding_schema_version": 1,
            "context_input_roles": {
                "phase-ctx__plan__run__run-id": "run_anchor:run-id",
                "phase-ctx__plan__run__state-root": "run_anchor:state-root",
                "phase-ctx__plan__run__artifact-root": "run_anchor:artifact-root",
                "phase-ctx__plan__phase-name": "compile_time_default",
                "phase-ctx__plan__state-root": "compile_time_default",
                "phase-ctx__plan__artifact-root": "compile_time_default",
            },
            "carried_input_sources": {
                "phase-ctx__plan__run__run-id": ("item-ctx", "run", "run-id"),
                "phase-ctx__plan__run__state-root": ("item-ctx", "run", "state-root"),
                "phase-ctx__plan__run__artifact-root": ("item-ctx", "run", "artifact-root"),
            },
        },
    }
    assert {
        binding["binding_id"]: binding["projection_hints"]
        for binding in workflow_projection["boundary"]["private_runtime_context_bindings"]
    } == {
        "phase-ctx__implementation": {
            "context_binding_schema_version": 1,
            "context_input_roles": {
                "phase-ctx__implementation__run__run-id": "run_anchor:run-id",
                "phase-ctx__implementation__run__state-root": "run_anchor:state-root",
                "phase-ctx__implementation__run__artifact-root": "run_anchor:artifact-root",
                "phase-ctx__implementation__phase-name": "compile_time_default",
                "phase-ctx__implementation__state-root": "compile_time_default",
                "phase-ctx__implementation__artifact-root": "compile_time_default",
            },
            "carried_input_sources": {
                "phase-ctx__implementation__run__run-id": ["item-ctx", "run", "run-id"],
                "phase-ctx__implementation__run__state-root": [
                    "item-ctx",
                    "run",
                    "state-root",
                ],
                "phase-ctx__implementation__run__artifact-root": [
                    "item-ctx",
                    "run",
                    "artifact-root",
                ],
            },
        },
        "phase-ctx__plan": {
            "context_binding_schema_version": 1,
            "context_input_roles": {
                "phase-ctx__plan__run__run-id": "run_anchor:run-id",
                "phase-ctx__plan__run__state-root": "run_anchor:state-root",
                "phase-ctx__plan__run__artifact-root": "run_anchor:artifact-root",
                "phase-ctx__plan__phase-name": "compile_time_default",
                "phase-ctx__plan__state-root": "compile_time_default",
                "phase-ctx__plan__artifact-root": "compile_time_default",
            },
            "carried_input_sources": {
                "phase-ctx__plan__run__run-id": ["item-ctx", "run", "run-id"],
                "phase-ctx__plan__run__state-root": ["item-ctx", "run", "state-root"],
                "phase-ctx__plan__run__artifact-root": ["item-ctx", "run", "artifact-root"],
            },
        },
    }
    expected_source_provenance = {
        binding.binding_id: json.loads(json.dumps(dict(binding.source_provenance)))
        for binding in boundary.private_runtime_context_bindings
    }
    assert expected_source_provenance == {
        "phase-ctx__implementation": {
            "workflow_name": "design_delta_item_ctx_child_phase_reuse::run-item-ctx-first",
            "path": str(ITEM_CTX_CHILD_PHASE_REUSE_FIXTURE),
            "line": expected_source_provenance["phase-ctx__implementation"]["line"],
            "form_path": expected_source_provenance["phase-ctx__implementation"]["form_path"],
        },
        "phase-ctx__plan": {
            "workflow_name": "design_delta_item_ctx_child_phase_reuse::run-item-ctx-first",
            "path": str(ITEM_CTX_CHILD_PHASE_REUSE_FIXTURE),
            "line": expected_source_provenance["phase-ctx__plan"]["line"],
            "form_path": expected_source_provenance["phase-ctx__plan"]["form_path"],
        },
    }
    assert {
        binding["binding_id"]: binding["source_provenance"]
        for binding in workflow_projection["boundary"]["private_runtime_context_bindings"]
    } == expected_source_provenance


def test_design_delta_item_ctx_child_phase_reuse_branching_terminal_reprojection_build_artifacts_record_derived_child_phase_binding(
    tmp_path: Path,
) -> None:
    built = _build_item_ctx_child_phase_reuse_branching_fixture(tmp_path)
    bundle = built.compile_result.validated_bundles_by_name[
        "design_delta_item_ctx_child_phase_reuse::run-item-ctx-first-branching-terminal-reprojection"
    ]
    boundary = _workflow_boundary_projection(bundle)
    workflow_projection = next(
        item
        for item in json.loads(
            built.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
        )["workflows"]
        if item["workflow_name"]
        == "design_delta_item_ctx_child_phase_reuse::run-item-ctx-first-branching-terminal-reprojection"
    )

    assert len(boundary.private_runtime_context_bindings) == 2
    assert {
        binding.derived_phase_identity
        for binding in boundary.private_runtime_context_bindings
    } == {"plan", "implementation"}
    assert {
        (
            binding["binding_id"],
            binding["source_param_name"],
            binding["bridge_class"],
            binding["derived_phase_identity"],
        )
        for binding in workflow_projection["boundary"]["private_runtime_context_bindings"]
    } == {
        (
            "phase-ctx__implementation",
            "item-ctx",
            "derived_private_child_context",
            "implementation",
        ),
        (
            "phase-ctx__plan",
            "item-ctx",
            "derived_private_child_context",
            "plan",
        ),
    }
    assert boundary.private_compatibility_bridge_inputs == ("run_state_path",)
    assert workflow_projection["boundary"]["private_compatibility_bridge_inputs"] == [
        "run_state_path"
    ]
    assert {
        binding.binding_id: json.loads(json.dumps(dict(binding.source_provenance)))["path"]
        for binding in boundary.private_runtime_context_bindings
    } == {
        "phase-ctx__implementation": str(ITEM_CTX_CHILD_PHASE_REUSE_FIXTURE),
        "phase-ctx__plan": str(ITEM_CTX_CHILD_PHASE_REUSE_FIXTURE),
    }


def test_design_delta_parent_drain_build_artifacts_record_imported_selector_carried_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
    )
    bundle = built.compile_result.validated_bundles_by_name[
        "lisp_frontend_design_delta/stdlib_adapters::select-next-work-stdlib"
    ]
    boundary = _workflow_boundary_projection(bundle)
    workflow_projection = next(
        item
        for item in json.loads(
            built.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
        )["workflows"]
        if item["workflow_name"]
        == "lisp_frontend_design_delta/stdlib_adapters::select-next-work-stdlib"
    )
    authority_report = json.loads(
        built.artifact_paths["boundary_authority_report"].read_text(encoding="utf-8")
    )
    selector_row = next(
        row
        for row in authority_report["workflows"]
        if row["workflow_name"]
        == "lisp_frontend_design_delta/stdlib_adapters::select-next-work-stdlib"
    )

    assert len(boundary.private_runtime_context_bindings) == 1
    binding = boundary.private_runtime_context_bindings[0]
    assert binding.binding_id == "ctx"
    assert binding.bridge_class == "imported_adapter_carried_context"
    assert binding.context_family == "DrainCtx"
    assert binding.projection_hints["context_input_roles"] == {
        "ctx__run__run-id": "run_anchor:run-id",
        "ctx__run__state-root": "run_anchor:state-root",
        "ctx__run__artifact-root": "run_anchor:artifact-root",
    }
    assert binding.projection_hints["carried_input_sources"] == {
        "ctx__run__run-id": ("ctx", "run", "run-id"),
        "ctx__run__state-root": ("ctx", "run", "state-root"),
        "ctx__run__artifact-root": ("ctx", "run", "artifact-root"),
        "ctx__state-root": ("ctx", "state-root"),
        "ctx__manifest": ("ctx", "manifest"),
        "ctx__ledger": ("ctx", "ledger"),
        "ctx__steering_path": ("ctx", "steering_path"),
        "ctx__target_design_path": ("ctx", "target_design_path"),
        "ctx__baseline_design_path": ("ctx", "baseline_design_path"),
        "ctx__progress_ledger_path": ("ctx", "progress_ledger_path"),
        "ctx__run_state_path": ("ctx", "run_state_path"),
        "ctx__existing_architecture_index_path": (
            "ctx",
            "existing_architecture_index_path",
        ),
    }
    serialized_binding = workflow_projection["boundary"][
        "private_runtime_context_bindings"
    ][0]
    assert serialized_binding["binding_id"] == "ctx"
    assert serialized_binding["source_param_name"] == "ctx"
    assert serialized_binding["context_family"] == "DrainCtx"
    assert serialized_binding["bridge_class"] == "imported_adapter_carried_context"
    assert serialized_binding["derived_phase_identity"] is None
    assert serialized_binding["generated_input_names"] == sorted(
        [
            "ctx__run__run-id",
            "ctx__run__state-root",
            "ctx__run__artifact-root",
            "ctx__state-root",
            "ctx__manifest",
            "ctx__ledger",
            "ctx__steering_path",
            "ctx__target_design_path",
            "ctx__baseline_design_path",
            "ctx__progress_ledger_path",
            "ctx__run_state_path",
            "ctx__existing_architecture_index_path",
        ]
    )
    assert serialized_binding["projection_hints"] == {
        "context_binding_schema_version": 1,
        "context_input_roles": {
            "ctx__run__run-id": "run_anchor:run-id",
            "ctx__run__state-root": "run_anchor:state-root",
            "ctx__run__artifact-root": "run_anchor:artifact-root",
        },
        "carried_input_sources": {
            "ctx__run__run-id": ["ctx", "run", "run-id"],
            "ctx__run__state-root": ["ctx", "run", "state-root"],
            "ctx__run__artifact-root": ["ctx", "run", "artifact-root"],
            "ctx__state-root": ["ctx", "state-root"],
            "ctx__manifest": ["ctx", "manifest"],
            "ctx__ledger": ["ctx", "ledger"],
            "ctx__steering_path": ["ctx", "steering_path"],
            "ctx__target_design_path": ["ctx", "target_design_path"],
            "ctx__baseline_design_path": ["ctx", "baseline_design_path"],
            "ctx__progress_ledger_path": ["ctx", "progress_ledger_path"],
            "ctx__run_state_path": ["ctx", "run_state_path"],
            "ctx__existing_architecture_index_path": [
                "ctx",
                "existing_architecture_index_path",
            ],
        },
    }
    assert serialized_binding["source_provenance"] == json.loads(
        json.dumps(dict(binding.source_provenance))
    )
    assert "ctx__run_state_path" not in selector_row["runtime_derived"]
    assert "ctx__run_state_path" not in selector_row["public_authored"]
    assert "ctx__run_state_path" in selector_row["compiled_evidence"][
        "private_runtime_context_bindings"
    ]


def test_design_delta_parent_drain_imported_backlog_drain_build_artifacts_record_derived_child_phase_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_design_delta_auxiliary_reports(monkeypatch)
    built = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        value_flow_census_payload=_aligned_design_delta_value_flow_census(tmp_path),
        resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
    )
    bundle = built.compile_result.validated_bundles_by_name["std/drain::backlog-drain"]
    boundary = _workflow_boundary_projection(bundle)
    workflow_projection = next(
        item
        for item in json.loads(
            built.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
        )["workflows"]
        if item["workflow_name"] == "std/drain::backlog-drain"
    )

    assert boundary.private_compatibility_bridge_inputs == ("run_state_path",)
    assert workflow_projection["boundary"]["private_compatibility_bridge_inputs"] == [
        "run_state_path"
    ]
    assert {
        (
            binding.binding_id,
            binding.source_param_name,
            binding.bridge_class,
            binding.derived_phase_identity,
            tuple(binding.generated_input_names),
        )
        for binding in boundary.private_runtime_context_bindings
    } == {
        (
            "phase-ctx__work-item",
            "ctx",
            "derived_private_child_context",
            "work-item",
            (
                "phase-ctx__work-item__phase-name",
                "phase-ctx__work-item__state-root",
                "phase-ctx__work-item__artifact-root",
            ),
        ),
    }
    assert {
        binding.binding_id: binding.projection_hints
        for binding in boundary.private_runtime_context_bindings
    } == {
        "phase-ctx__work-item": {
            "context_binding_schema_version": 1,
            "context_input_roles": {
                "phase-ctx__work-item__run__run-id": "run_anchor:run-id",
                "phase-ctx__work-item__run__state-root": "run_anchor:state-root",
                "phase-ctx__work-item__run__artifact-root": "run_anchor:artifact-root",
                "phase-ctx__work-item__phase-name": "compile_time_default",
                "phase-ctx__work-item__state-root": "compile_time_default",
                "phase-ctx__work-item__artifact-root": "compile_time_default",
            },
            "carried_input_sources": {
                "phase-ctx__work-item__run__run-id": ("ctx", "run", "run-id"),
                "phase-ctx__work-item__run__state-root": (
                    "ctx",
                    "run",
                    "state-root",
                ),
                "phase-ctx__work-item__run__artifact-root": (
                    "ctx",
                    "run",
                    "artifact-root",
                ),
            },
        },
    }
    assert {
        binding["binding_id"]: binding["projection_hints"]
        for binding in workflow_projection["boundary"]["private_runtime_context_bindings"]
    } == {
        "phase-ctx__work-item": {
            "context_binding_schema_version": 1,
            "context_input_roles": {
                "phase-ctx__work-item__run__run-id": "run_anchor:run-id",
                "phase-ctx__work-item__run__state-root": "run_anchor:state-root",
                "phase-ctx__work-item__run__artifact-root": "run_anchor:artifact-root",
                "phase-ctx__work-item__phase-name": "compile_time_default",
                "phase-ctx__work-item__state-root": "compile_time_default",
                "phase-ctx__work-item__artifact-root": "compile_time_default",
            },
            "carried_input_sources": {
                "phase-ctx__work-item__run__run-id": ["ctx", "run", "run-id"],
                "phase-ctx__work-item__run__state-root": [
                    "ctx",
                    "run",
                    "state-root",
                ],
                "phase-ctx__work-item__run__artifact-root": [
                    "ctx",
                    "run",
                    "artifact-root",
                ],
            },
        },
    }
    assert all(
        "run_state_path" not in binding.projection_hints.get("carried_input_sources", {})
        for binding in boundary.private_runtime_context_bindings
    )


def test_boundary_projection_serializer_uses_typed_bundle_compatibility_split(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    serialize = getattr(build, "_serialize_workflow_boundary_projection")
    request_cls = getattr(build, "FrontendBuildRequest")
    fixture = tmp_path / "private_exec_context_phase_entry.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule private_exec_context_phase_entry)",
                "  (import std/phase :only (with-phase))",
                "  (export entry run-phase)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord Result",
                "    (label String)",
                "    (phase_name Symbol))",
                "  (defworkflow entry",
                "    ((label String))",
                "    -> Result",
                "    (call run-phase",
                "      :label label))",
                "  (defworkflow run-phase",
                "    ((phase-ctx PhaseCtx)",
                "     (label String))",
                "    -> Result",
                "    (with-phase phase-ctx plan-gate-wrapper",
                "      (record Result",
                "        :label label",
                "        :phase_name phase-ctx.phase-name)))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    built = build_frontend_bundle(
        request_cls(
            source_path=fixture,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.LEGACY,
        )
    )

    workflow_name = "private_exec_context_phase_entry::entry"
    bundle = built.compile_result.entry_result.validated_bundles[workflow_name]
    compatibility_bundle = replace(
        bundle,
        provenance=replace(
            bundle.provenance,
            compatibility_bridge_inputs=("compatibility__legacy_state_root",),
        ),
    )
    entry_result = replace(
        built.compile_result.entry_result,
        validated_bundles={
            **dict(built.compile_result.entry_result.validated_bundles),
            workflow_name: compatibility_bundle,
        },
    )
    compile_result = replace(
        built.compile_result,
        entry_result=entry_result,
        validated_bundles_by_name={
            **dict(built.compile_result.validated_bundles_by_name),
            workflow_name: compatibility_bundle,
        },
    )

    projection_payload = serialize(
        compile_result,
        selected_name=workflow_name,
    )
    workflow_projection = next(
        item
        for item in projection_payload["workflows"]
        if item["workflow_name"] == workflow_name
    )

    assert workflow_projection["boundary"]["private_compatibility_bridge_inputs"] == [
        "compatibility__legacy_state_root"
    ]


def test_boundary_projection_serializer_preserves_lowered_compatibility_inputs_without_bundle(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")
    serialize = getattr(build, "_serialize_workflow_boundary_projection")

    fixture = tmp_path / "private_exec_context_phase_entry.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule private_exec_context_phase_entry)",
                "  (import std/phase :only (with-phase))",
                "  (export entry run-phase)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord Result",
                "    (label String)",
                "    (phase_name Symbol))",
                "  (defworkflow entry",
                "    ((label String))",
                "    -> Result",
                "    (call run-phase",
                "      :label label))",
                "  (defworkflow run-phase",
                "    ((phase-ctx PhaseCtx)",
                "     (label String))",
                "    -> Result",
                "    (with-phase phase-ctx plan-gate-wrapper",
                "      (record Result",
                "        :label label",
                "        :phase_name phase-ctx.phase-name)))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    built = build_frontend_bundle(
        request_cls(
            source_path=fixture,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.LEGACY,
        )
    )
    entry_result = built.compile_result.entry_result
    lowered = replace(
        entry_result.lowered_workflows[0],
        compatibility_bridge_inputs=("compatibility__legacy_state_root",),
    )
    linked_entry_result = replace(
        entry_result,
        lowered_workflows=(lowered, *entry_result.lowered_workflows[1:]),
        validated_bundles={},
    )
    module_name = next(iter(built.compile_result.compiled_results_by_name))
    compile_result = replace(
        built.compile_result,
        entry_result=linked_entry_result,
        compiled_results_by_name={
            **dict(built.compile_result.compiled_results_by_name),
            module_name: linked_entry_result,
        },
        validated_bundles_by_name={},
    )

    projection_payload = serialize(
        compile_result,
        selected_name=lowered.typed_workflow.definition.name,
    )
    workflow_projection = next(
        item
        for item in projection_payload["workflows"]
        if item["workflow_name"] == lowered.typed_workflow.definition.name
    )

    assert workflow_projection["boundary"]["private_compatibility_bridge_inputs"] == [
        "compatibility__legacy_state_root"
    ]


def test_build_frontend_bundle_keeps_wcc_default_schema_and_lowering_route_out_of_artifacts(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    result = build_frontend_bundle(_build_request(tmp_path))

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest_payload = json.dumps(manifest, sort_keys=True)
    source_map_payload = result.artifact_paths["source_map"].read_text(encoding="utf-8")

    assert result.manifest.shared_validation_status == "validated"
    assert manifest["lowering_schema_version"] == 2
    assert "wcc_m1" not in manifest_payload
    assert "wcc_m2" not in manifest_payload
    assert "wcc_m4" not in manifest_payload
    assert "lowering_route" not in manifest_payload
    assert "wcc_m1" not in source_map_payload
    assert "wcc_m2" not in source_map_payload
    assert "wcc_m4" not in source_map_payload
    assert "lowering_route" not in source_map_payload


def test_build_frontend_bundle_keeps_wcc_candidate_schema_and_lowering_route_out_of_artifacts(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request = _build_request(tmp_path)
    result = build_frontend_bundle(
        type(request)(
            **{
                **request.__dict__,
                "lowering_route": LoweringRoute.WCC_M4,
            }
        )
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest_text = json.dumps(manifest, sort_keys=True)
    source_map_text = result.artifact_paths["source_map"].read_text(encoding="utf-8")

    assert result.manifest.shared_validation_status == "validated"
    assert manifest["lowering_schema_version"] == 2
    assert "wcc_m4" not in manifest_text
    assert "lowering_route" not in manifest_text
    assert "wcc_m4" not in source_map_text
    assert "lowering_route" not in source_map_text
    assert "wcc-node" not in source_map_text


def test_same_file_wcc_m3_source_map_keeps_route_names_out_and_preserves_match_join_lineage(
    tmp_path: Path,
) -> None:
    source_map = _same_file_wcc_m3_source_map_payload(
        tmp_path,
        fixture_path=FIXTURES / "characterization" / "sources" / "design_delta_union_match_projection.orc",
        module_filename="union_match_probe.orc",
        selected_name="union_match_probe::summarize",
    )
    source_map_text = json.dumps(source_map, sort_keys=True).replace(str(tmp_path), "")
    workflow = source_map["workflows"]["union_match_probe::summarize"]

    assert "wcc_m1" not in source_map_text
    assert "wcc_m2" not in source_map_text
    assert "wcc_m3" not in source_map_text
    assert "lowering_route" not in source_map_text
    assert any(node["kind"] == "match_join" for node in workflow["executable_nodes"])
    assert workflow["validation_subjects"]
    assert workflow["core_nodes"]


def test_wcc_m4_source_map_keeps_route_names_out_and_preserves_repeat_until_lineage(
    tmp_path: Path,
) -> None:
    source_map = _route_neutral_wcc_m4_source_map_payload(tmp_path)
    source_map_text = json.dumps(source_map, sort_keys=True).replace(str(tmp_path), "")
    workflow = source_map["workflows"]["route_neutral_loop::loop-recur-on-exhausted-union"]

    assert "wcc_m4" not in source_map_text
    assert "lowering_route" not in source_map_text
    assert "wcc-node" not in source_map_text
    assert "Wcc" not in source_map_text
    assert any(node["step_kind"] == "repeat_until" for node in workflow["core_nodes"])
    assert any(node["kind"] == "repeat_until_frame" for node in workflow["executable_nodes"])
    assert {"return__variant", "return__reason", "return__report"}.issubset(workflow["generated_outputs"])
    assert workflow["generated_outputs"]["return__reason"]["generated_name_origin"] == "return__reason"
    assert workflow["validation_subjects"]


def test_wcc_m4_full_fixture_source_map_records_review_loop_and_command_lineage(
    tmp_path: Path,
) -> None:
    source_map = _wcc_m4_full_fixture_source_map_payload(tmp_path)
    source_map_text = json.dumps(source_map, sort_keys=True)
    workflow = source_map["workflows"]["wcc_m4_implementation_phase_full_fixture::run"]

    command_names = {boundary["command_name"] for boundary in workflow["command_boundaries"]}
    assert {"run_checks", "validate_review_findings_v1"}.issubset(command_names)
    assert any(node["step_kind"] == "repeat_until" for node in workflow["core_nodes"])
    assert any(node["kind"] == "repeat_until_frame" for node in workflow["executable_nodes"])
    assert {"return__variant", "return__review_report", "return__findings__items_path"}.issubset(
        workflow["generated_outputs"]
    )
    assert any(
        allocation["semantic_role"] == "command_result_bundle" and "run_checks" in allocation["stable_identity"]
        for allocation in workflow["generated_path_allocations"]
    )
    assert "lowering_route" not in source_map_text
    assert "wcc-node" not in source_map_text


def test_build_frontend_bundle_emits_imported_stdlib_macro_helper_provenance_across_artifacts(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    result = build_frontend_bundle(_imported_stdlib_helper_request(tmp_path))

    workflow_name = "imported_stdlib_macro_payload_helper_composition/entry::run-drain-like"
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    workflow = source_map["workflows"][workflow_name]

    assert any(
        node["step_kind"] == "match" and "__gap_payload__" in node["step_id"]
        for node in workflow["core_nodes"]
    )
    assert any(
        node["kind"] == "match_join" and "selection-result-gap-payload" in node["origin_key"]
        for node in workflow["executable_nodes"]
    )
    assert any(
        allocation["semantic_role"] == "pure_projection_bundle"
        and "__gap_payload__" in allocation["generated_input_name"]
        for allocation in workflow["generated_path_allocations"]
    )

    coverage_bridges = {
        bridge["origin_key"]
        for key, bridge in semantic_ir["source_map"].items()
        if key.startswith(f"source_map:{workflow_name}:coverage:")
    }
    assert {"core_workflow_ast", "executable_ir", "semantic_ir"}.issubset(coverage_bridges)


def test_build_emits_debug_yaml_when_requested_and_marks_manifest_status(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    request = _build_request(tmp_path)
    request = type(request)(**{**request.__dict__, "emit_debug_yaml": True})
    result = build_frontend_bundle(request)

    debug_yaml_path = result.artifact_paths["expanded_debug_yaml"]
    debug_yaml_text = debug_yaml_path.read_text(encoding="utf-8")

    assert debug_yaml_path.name == "expanded.debug.yaml"
    assert result.manifest.debug_yaml_status == "emitted"
    assert debug_yaml_path.exists()
    assert "non-authoritative" in debug_yaml_text
    assert "must not be used as execution input" in debug_yaml_text


def test_build_removes_stale_debug_yaml_when_not_requested(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    debug_request = _build_request(tmp_path)
    debug_request = type(debug_request)(**{**debug_request.__dict__, "emit_debug_yaml": True})
    debug_result = build_frontend_bundle(debug_request)

    plain_result = build_frontend_bundle(_build_request(tmp_path))

    assert plain_result.build_root == debug_result.build_root
    assert plain_result.manifest.debug_yaml_status == "not_requested"
    assert "expanded_debug_yaml" not in plain_result.artifact_paths
    assert not (plain_result.build_root / "expanded.debug.yaml").exists()


def test_source_map_emits_versioned_schema_and_runtime_lineage_sections(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    boundary_projection = json.loads(
        result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
    )

    assert source_map["schema_version"] == "workflow_lisp_source_map.v1"
    assert source_map["coverage"] == {
        "frontend_ast": "covered",
        "lowered_surface": "covered",
        "shared_validation_subjects": "covered",
        "executable_ir": "covered",
        "runtime_logs": "covered",
        "core_workflow_ast": "covered",
        "semantic_ir": "covered",
    }

    command_checks_name = "lineage_pkg/entry::command_checks"
    provider_attempt_name = "lineage_pkg/entry::provider_attempt"
    entry_name = "lineage_pkg/entry::orchestrate"
    command_checks = source_map["workflows"][command_checks_name]
    provider_attempt = source_map["workflows"][provider_attempt_name]
    entry_workflow = source_map["workflows"][entry_name]
    assert entry_workflow["selected_entry_workflow"] is True
    assert entry_workflow["workflow_name"] == entry_name
    assert set(source_map["workflows"]) == {command_checks_name, provider_attempt_name, entry_name}

    expected_sections = {
        "workflow_origin",
        "step_ids",
        "generated_inputs",
        "generated_outputs",
        "generated_paths",
        "generated_internal_inputs",
        "generated_semantic_effects",
        "core_nodes",
        "command_boundaries",
        "validation_subjects",
        "executable_nodes",
    }
    for workflow in source_map["workflows"].values():
        assert expected_sections.issubset(workflow)
        assert workflow["workflow_origin"]["origin_key"]
        assert workflow["core_nodes"]
        assert all(node["origin_key"] for node in workflow["core_nodes"])

    command_step_ids = {
        name for name in command_checks["step_ids"] if name.endswith("command_checks__run_checks")
    }
    internal_input_name = next(iter(command_checks["generated_internal_inputs"]))
    command_boundary = command_checks["command_boundaries"][0]
    core_node = command_checks["core_nodes"][0]
    assert command_step_ids
    assert internal_input_name.endswith("__result_bundle")
    assert len(command_checks["command_boundaries"]) == 1
    assert command_boundary["step_id"] in command_step_ids
    assert command_checks["step_ids"][command_boundary["step_id"]]["origin_key"]
    assert command_boundary["command_name"] == "run_checks"
    assert command_boundary["boundary_kind"] == "external_tool"
    assert command_boundary["origin_key"] == command_checks["step_ids"][command_boundary["step_id"]]["origin_key"]
    assert core_node["statement_id"]
    assert core_node["step_id"] in command_step_ids
    assert core_node["origin_key"] == command_checks["step_ids"][core_node["step_id"]]["origin_key"]
    assert {
        subject["subject_ref"]["subject_kind"]
        for subject in provider_attempt["validation_subjects"]
    } >= {"step_id", "generated_input", "generated_output", "workflow"}
    assert any(
        node["kind"] == "match_join" and node["region"] == "body"
        for node in provider_attempt["executable_nodes"]
    )
    assert "contract_definition" not in json.dumps(source_map, sort_keys=True)
    assert boundary_projection["schema_version"] == "workflow_lisp_boundary_projection.v1"
    assert boundary_projection["entry_workflow"] == entry_name
    projection_entry = next(
        workflow
        for workflow in boundary_projection["workflows"]
        if workflow["workflow_name"] == command_checks_name
    )
    assert projection_entry["params"] == [{"name": "report_path", "type_kind": "relpath"}]
    assert projection_entry["return_kind"] == "record"
    assert [field["generated_name"] for field in projection_entry["flattened_inputs"]] == ["report_path"]
    assert {field["generated_name"] for field in projection_entry["flattened_outputs"]} == {
        "return__report",
        "return__status",
    }
    assert len(projection_entry["generated_internal_inputs"]) == 1
    assert projection_entry["generated_internal_inputs"][0]["generated_name"].endswith("__result_bundle")
    assert projection_entry["generated_internal_inputs"][0]["reason"] == "managed_write_root"


def test_source_map_serializes_generated_semantic_effects_for_frontend_build(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_pointer_effects_request(tmp_path))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    workflow_name = next(name for name in source_map["workflows"] if name.endswith("::orchestrate"))
    workflow = source_map["workflows"][workflow_name]

    assert "generated_semantic_effects" in workflow
    assert any(
        effect["effect_kind"] == "pointer_materialization"
        for effect in workflow["generated_semantic_effects"]
    )


def test_build_artifacts_expose_pure_projection_effects_and_generated_paths(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp.lowering import _observed_statement_families

    result = _build_pure_expr_selector_projection(tmp_path)
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    workflow_name = next(name for name in source_map["workflows"] if name.endswith("::orchestrate"))
    workflow = source_map["workflows"][workflow_name]
    lowered = next(
        workflow_result
        for workflow_result in result.compile_result.entry_result.lowered_workflows
        if workflow_result.typed_workflow.definition.name == workflow_name
    )

    assert any(
        effect["effect_kind"] == "pure_projection"
        for effect in workflow["generated_semantic_effects"]
    )
    assert any(
        allocation["semantic_role"] == "pure_projection_bundle"
        for allocation in workflow["generated_path_allocations"]
    )
    assert any(
        effect["effect_kind"] == "pure_projection"
        for effect in semantic_ir["effects"].values()
    )
    assert "pure_projection" in _observed_statement_families(lowered.authored_mapping["steps"])
    managed_write_root_input = next(
        name
        for name in lowered.authored_mapping["inputs"]
        if name.startswith("__write_root__")
    )
    assert lowered.authored_mapping["inputs"][managed_write_root_input] == {
        "kind": "relpath",
        "type": "relpath",
    }


def test_build_artifacts_expose_materialize_view_effects_and_generated_paths(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp.lowering import _observed_statement_families

    result = _build_materialize_view_allocated_target(tmp_path)
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    workflow_name = next(name for name in source_map["workflows"] if name.endswith("::orchestrate"))
    workflow = source_map["workflows"][workflow_name]
    lowered = next(
        workflow_result
        for workflow_result in result.compile_result.entry_result.lowered_workflows
        if workflow_result.typed_workflow.definition.name == workflow_name
    )

    effect = next(
        effect
        for effect in workflow["generated_semantic_effects"]
        if effect["effect_kind"] == "materialize_view"
    )

    assert effect["details"]["renderer_id"] == "canonical-json"
    assert effect["details"]["authority_class"] == "materialized_view"
    assert any(
        allocation["semantic_role"] == "materialized_value_view"
        for allocation in workflow["generated_path_allocations"]
    )
    assert any(
        entry["effect_kind"] == "materialize_view"
        for entry in semantic_ir["effects"].values()
    )
    assert "materialize_view" in _observed_statement_families(lowered.authored_mapping["steps"])


def test_review_loop_command_boundary_surfaces_validate_review_findings_adapter(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    module_dir = tmp_path / "review_findings_build"
    module_dir.mkdir(parents=True, exist_ok=True)
    module_path = module_dir / "entry.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule review_findings_build/entry)",
                "  (import std/phase :only (ReviewFindings ReviewFindingsJsonPath))",
                "  (export validate-findings)",
                "  (defworkflow validate-findings",
                "    ((items_path ReviewFindingsJsonPath))",
                "    -> ReviewFindings",
                "    (command-result validate_review_findings_v1",
                '      :argv ("python" "-m" "orchestrator.workflow_lisp.adapters.validate_review_findings_v1" items_path)',
                "      :returns ReviewFindings)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = module_dir / "commands.json"
    manifest_path.write_text(
        json.dumps(
            {
                "validate_review_findings_v1": {
                    "kind": "certified_adapter",
                    "stable_command": [
                        "python",
                        "-m",
                        "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
                    ],
                    "input_contract": {"type": "object"},
                    "output_type_name": "ReviewFindings",
                    "effects": ["structured_result"],
                    "path_safety": {"kind": "workspace_relpath"},
                    "source_map_behavior": "step",
                    "fixture_ids": ["review_findings_valid"],
                    "negative_fixture_ids": ["review_findings_pointer_authority_forbidden"],
                    **_validate_review_findings_retirement_metadata(),
                }
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = build_frontend_bundle(
        request_cls(
            source_path=module_path,
            source_roots=(tmp_path,),
            entry_workflow="validate-findings",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=manifest_path,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    workflow_name = result.entry_selection.canonical_name

    assert any(
        boundary["boundary_kind"] == "certified_adapter"
        and boundary["boundary_name"] == "validate_review_findings_v1"
        for boundary in semantic_ir["command_boundaries"].values()
    )
    assert source_map["workflows"][workflow_name]["command_boundaries"]


def test_review_loop_bundle_preserves_distinct_review_report_and_findings_seed_paths(
    tmp_path: Path,
) -> None:
    fixture = FIXTURES / "valid" / "phase_stdlib_review_loop.orc"
    module_path = tmp_path / "phase_stdlib_review_loop.orc"
    module_path.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    for relpath in (
        "prompts/implementation/review.md",
        "prompts/implementation/fix.md",
    ):
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("prompt\n", encoding="utf-8")

    result = compile_stage3_module(
        module_path,
        provider_externs={
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "validate_review_findings_v1": ExternalToolBinding(
                name="validate_review_findings_v1",
                stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.validate_review_findings_v1"),
                **_validate_review_findings_retirement_metadata(),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "phase_stdlib_review_loop::review-revise-loop-demo"
    )
    seed_step = next(step for step in lowered.authored_mapping["steps"] if step["name"].endswith("__seed"))
    seed_values = {
        value["name"]: value
        for value in seed_step["materialize_artifacts"]["values"]
    }
    outputs = lowered.authored_mapping["outputs"]

    assert seed_values["state__last_review_report"]["source"] == {
        "literal": "artifacts/review/last-review-report.md"
    }
    assert seed_values["state__latest_findings__items_path"]["source"] == {
        "literal": "artifacts/work/review-findings-seed.json"
    }
    assert outputs["return__review_report"]["under"] == "artifacts/review"
    assert outputs["return__last_review_report"]["under"] == "artifacts/review"
    assert outputs["return__findings__items_path"]["under"] == "artifacts/work"


def test_stdlib_contract_inventory_is_compile_time_only_and_not_serialized_into_frontend_build_artifacts(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    source_map_text = result.artifact_paths["source_map"].read_text(encoding="utf-8")
    boundary_projection_text = result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
    serialized_artifacts = {
        name: path.read_text(encoding="utf-8") for name, path in result.artifact_paths.items()
    }
    combined = json.dumps(serialized_artifacts, sort_keys=True)

    forbidden_markers = (
        "StdlibLoweringContract",
        "structured_result_producer",
        "review_reuse_control",
        "resource_finalize_drain",
        "source_map_expectations",
    )

    for marker in forbidden_markers:
        assert marker not in source_map_text
        assert marker not in boundary_projection_text
        assert marker not in combined


def test_semantic_ir_artifact_serializes_promoted_effects_for_frontend_build(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_pointer_effects_request(tmp_path))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    effects = [
        effect
        for effect in semantic_ir["effects"].values()
        if effect["effect_kind"] in {"pointer_materialization", "snapshot_capture", "resource_transition", "ledger_update"}
    ]

    assert any(effect["effect_kind"] == "pointer_materialization" for effect in effects)


def test_design_delta_parent_drain_adapters_emit_resource_transition_effects(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.lowering import _observed_statement_families

    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    result = build_frontend_bundle(
        request_cls(
            source_path=REPO_ROOT
            / "workflows"
            / "library"
            / "lisp_frontend_design_delta"
            / "drain.orc",
            source_roots=(REPO_ROOT / "workflows" / "library",),
            entry_workflow="lisp_frontend_design_delta/drain::drain",
            provider_externs_path=REPO_ROOT
            / "workflows"
            / "examples"
            / "inputs"
            / "workflow_lisp_migrations"
            / "design_delta_parent_drain.providers.json",
            prompt_externs_path=REPO_ROOT
            / "workflows"
            / "examples"
            / "inputs"
            / "workflow_lisp_migrations"
            / "design_delta_parent_drain.prompts.json",
            imported_workflow_bundles_path=None,
            command_boundaries_path=REPO_ROOT
            / "workflows"
            / "examples"
            / "inputs"
            / "workflow_lisp_migrations"
            / "design_delta_parent_drain.commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow
        for compiled in result.compile_result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }

    expected_adapters = {
        "record_terminal_work_item",
        "record_blocked_recovery_outcome",
        "write_lisp_frontend_drain_status",
    }
    adapter_rows = {
        row["command_name"]: row
        for workflow in source_map["workflows"].values()
        for row in workflow.get("command_boundaries", [])
        if row.get("boundary_name") in expected_adapters
        or row.get("command_name") in expected_adapters
    }

    assert adapter_rows == {}

    effect_kinds_by_subject: dict[str, set[str]] = {}
    for effect in semantic_ir["effects"].values():
        boundary_name = effect.get("boundary_name")
        if not isinstance(boundary_name, str):
            continue
        for adapter_name in expected_adapters:
            if adapter_name in boundary_name:
                effect_kinds_by_subject.setdefault(adapter_name, set()).add(effect["effect_kind"])

    assert any(effect["effect_kind"] == "resource_transition" for effect in semantic_ir["effects"].values())
    assert any(effect["effect_kind"] == "materialize_view" for effect in semantic_ir["effects"].values())

    drain_families = _observed_statement_families(
        lowered_by_name["lisp_frontend_design_delta/drain::drain"].authored_mapping["steps"]
    )
    work_item_families = _observed_statement_families(
        lowered_by_name[
            "lisp_frontend_design_delta/work_item::run-work-item"
        ].authored_mapping["steps"]
    )
    assert "materialize_view" in drain_families
    assert "materialize_view" not in work_item_families
    assert "materialize_artifacts" in work_item_families


def test_source_trace_preserves_distinct_workflows_with_shared_display_names(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    source_root = tmp_path / "duplicate_names"
    package_dir = source_root / "pkg"
    package_dir.mkdir(parents=True)
    (package_dir / "types.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pkg/types)",
                "  (export WorkReport Out)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord Out",
                "    (report WorkReport)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "helper.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pkg/helper)",
                "  (import pkg/types :only (WorkReport Out))",
                "  (export run)",
                "  (defworkflow run",
                "    ((report_path WorkReport))",
                "    -> Out",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs (report_path)",
                "      :returns Out)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "entry.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pkg/entry)",
                "  (import pkg/types :only (WorkReport Out))",
                "  (import pkg/helper :as helper :only (run))",
                "  (export run)",
                "  (defworkflow run",
                "    ((report_path WorkReport))",
                "    -> Out",
                "    (call helper.run",
                "      :report_path report_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_frontend_bundle(
        request_cls(
            source_path=package_dir / "entry.orc",
            source_roots=(source_root,),
            entry_workflow="run",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))

    assert source_map["schema_version"] == "workflow_lisp_source_map.v1"
    assert set(source_map["workflows"]) >= {"pkg/entry::run", "pkg/helper::run"}
    assert source_map["workflows"]["pkg/entry::run"]["selected_entry_workflow"] is True
    assert source_map["workflows"]["pkg/helper::run"]["selected_entry_workflow"] is False
    assert source_map["workflows"]["pkg/entry::run"]["display_name"] == "run"
    assert source_map["workflows"]["pkg/helper::run"]["display_name"] == "run"


def test_source_map_validator_rejects_missing_required_validation_subject_bindings(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    source_map_module = importlib.import_module("orchestrator.workflow_lisp.source_map")
    build_source_map_document = getattr(source_map_module, "build_source_map_document")
    validate_source_map_document = getattr(source_map_module, "validate_source_map_document")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    document = build_source_map_document(
        result.compile_result,
        selected_name=result.entry_selection.canonical_name,
        display_name_resolver=lambda workflow_name: workflow_name.rsplit("::", 1)[-1],
    )
    workflow_name = "lineage_pkg/entry::command_checks"
    workflow = document.workflows[workflow_name]
    broken_workflow = replace(
        workflow,
        validation_subjects=tuple(
            binding
            for binding in workflow.validation_subjects
            if not (
                binding.subject_ref.subject_kind == "generated_output"
                and binding.subject_ref.subject_name == "return__report"
            )
        ),
    )
    broken_document = replace(
        document,
        workflows={**dict(document.workflows), workflow_name: broken_workflow},
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        validate_source_map_document(broken_document)

    assert excinfo.value.diagnostics[0].code == "source_map_validation_subject_missing"
    assert "generated_output:return__report" in excinfo.value.diagnostics[0].message


def test_source_map_validator_rejects_missing_core_node_lineage_when_coverage_claimed(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    source_map_module = importlib.import_module("orchestrator.workflow_lisp.source_map")
    build_source_map_document = getattr(source_map_module, "build_source_map_document")
    validate_source_map_document = getattr(source_map_module, "validate_source_map_document")

    result = build_frontend_bundle(_structured_results_request(tmp_path))
    document = build_source_map_document(
        result.compile_result,
        selected_name=result.entry_selection.canonical_name,
        display_name_resolver=lambda workflow_name: workflow_name.rsplit("::", 1)[-1],
    )
    workflow_name = "lineage_pkg/entry::command_checks"
    workflow = document.workflows[workflow_name]
    broken_workflow = replace(workflow, core_nodes=())
    broken_document = replace(
        document,
        workflows={**dict(document.workflows), workflow_name: broken_workflow},
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        validate_source_map_document(broken_document)

    assert excinfo.value.diagnostics[0].code == "source_map_core_node_missing"
    assert workflow_name in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_build_emits_adapter_census_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # This assertion is about adapter-census emission through the real build
    # surface, not the separately-owned checked-in boundary-authority registry.
    registry_payload = _aligned_design_delta_boundary_authority_registry(
        tmp_path / "aligned-registry"
    )
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=registry_payload,
        drain_summary_path=_aligned_reference_family_drain_summary(tmp_path),
        architecture_index_path=_aligned_reference_family_architecture_index(tmp_path),
    )

    assert "adapter_census" in result.artifact_paths
    assert result.manifest.artifact_status["adapter_census"] == "emitted"
    payload = json.loads(result.artifact_paths["adapter_census"].read_text(encoding="utf-8"))
    assert payload["workflow_family"] == "design_delta_parent_drain"
    rows_by_name = {row["binding_name"]: row for row in payload["rows"]}
    assert {
        "project_lisp_frontend_selector_action",
        "materialize_lisp_frontend_work_item_inputs",
        "run_neurips_backlog_checks",
        "validate_review_findings_v1",
    }.issubset(rows_by_name)
    for deleted_binding in (
        "classify_lisp_frontend_work_item_terminal",
        "select_lisp_frontend_blocked_recovery_route",
        "record_terminal_work_item",
        "record_blocked_recovery_outcome",
        "write_lisp_frontend_drain_status",
        "finalize_lisp_frontend_drain_summary",
    ):
        assert deleted_binding not in rows_by_name
    review_findings = rows_by_name["validate_review_findings_v1"]
    assert review_findings["retirement_class"] == "validation"
    assert review_findings["retirement_label"] == "keep_bridge"
    assert review_findings["replacement_surface"]
    assert review_findings["bridge_owner"]
    assert review_findings["expiry_condition"]
    assert review_findings["evidence_refs"]
    assert review_findings["liveness"] == "live"
    assert (
        rows_by_name["materialize_lisp_frontend_work_item_inputs"]["retirement_label"]
        == "retire_to_projection"
    )
    assert (
        rows_by_name["materialize_lisp_frontend_work_item_inputs"]["retirement_status"]
        == "retired"
    )
    assert rows_by_name["materialize_lisp_frontend_work_item_inputs"]["liveness"] == "unreferenced"


def test_design_delta_parent_drain_build_emits_g8_deletion_evidence_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        value_flow_census_payload=_aligned_design_delta_value_flow_census(),
        drain_summary_path=_aligned_reference_family_drain_summary(tmp_path),
        architecture_index_path=_aligned_reference_family_architecture_index(tmp_path),
    )

    assert "g8_deletion_evidence" in result.artifact_paths
    assert result.manifest.artifact_status["g8_deletion_evidence"] == "emitted"
    payload = json.loads(result.artifact_paths["g8_deletion_evidence"].read_text(encoding="utf-8"))

    assert payload["schema_version"] == "workflow_lisp_design_delta_g8_deletion_evidence.v1"
    assert payload["workflow_family"] == "design_delta_parent_drain"
    assert payload["status"] == "pass"
    assert set(payload["removed_manifest_rows"]) == {
        "classify_lisp_frontend_work_item_terminal",
        "select_lisp_frontend_blocked_recovery_route",
        "record_terminal_work_item",
        "record_blocked_recovery_outcome",
        "write_lisp_frontend_drain_status",
        "finalize_lisp_frontend_drain_summary",
    }
    assert payload["removed_registry_heads"] == [
        "with-phase",
        "finalize-selected-item",
        "backlog-drain",
    ]
    assert payload["hook_surface_delta"]["imported_only_registry_heads"] == ["with-phase"]
    assert payload["retained_bridges"] == ["materialize_lisp_frontend_work_item_inputs"]


def test_design_delta_parent_drain_build_rejects_removed_registry_heads_still_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()
    monkeypatch.setattr(
        build,
        "get_form_spec",
        lambda head_name: object() if head_name == "with-phase" else None,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        )

    diagnostics = excinfo.value.diagnostics
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.code == "design_delta_g8_removed_registry_head_present"
    assert "with-phase" in diagnostic.message
    assert diagnostic.span.start.path == str(
        DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.commands.json"
    )


def test_design_delta_parent_drain_build_emits_boundary_authority_report_for_all_target_workflows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    assert "boundary_authority_report" in result.artifact_paths
    assert result.manifest.artifact_status["boundary_authority_report"] == "emitted"

    payload = json.loads(
        result.artifact_paths["boundary_authority_report"].read_text(encoding="utf-8")
    )
    assert payload["workflow_family"] == "design_delta_parent_drain"
    assert {
        "lisp_frontend_design_delta/drain::drain",
        "lisp_frontend_design_delta/selector::select-next-work",
        "lisp_frontend_design_delta/work_item::run-work-item",
        "lisp_frontend_design_delta/plan_phase::run-plan-phase",
        "lisp_frontend_design_delta/implementation_phase::implementation-phase",
        "lisp_frontend_design_delta/design_gap_architect::draft-design-gap-architecture",
        "lisp_frontend_design_delta/design_gap_architect::validate-design-gap-architecture",
    }.issubset({row["workflow_name"] for row in payload["workflows"]})

    for row in payload["workflows"]:
        compiled_evidence = row["compiled_evidence"]
        assert compiled_evidence["workflow_boundary_projection"] == {
            "artifact": "workflow_boundary_projection.json",
            "workflow_name": row["workflow_name"],
        }
        assert compiled_evidence["generated_path_allocations"]["artifact"] == "workflow_boundary_projection.json"
        assert isinstance(compiled_evidence["generated_path_allocations"]["rows"], list)
        assert compiled_evidence["source_map_provenance"]["artifact"] == "source_map.json"
        assert row["workflow_name"] in compiled_evidence["source_map_provenance"]["workflow_names"]


def test_design_delta_parent_drain_boundary_authority_registry_covers_expected_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(tmp_path, monkeypatch)
    boundary_projection = json.loads(
        result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
    )
    expected_rows = build_design_delta_boundary_authority_expected_rows(boundary_projection)
    registry_payload = _load_design_delta_boundary_authority_registry()

    registry_keys = {
        (row["workflow_name"], row["field_name"], row["surface_kind"])
        for row in registry_payload["rows"]
    }
    expected_keys = {
        (workflow_name, field_name, row["surface_kind"])
        for (workflow_name, field_name), row in expected_rows.items()
    }
    assert registry_keys == expected_keys | {
        (
            "lisp_frontend_design_delta/work_item::run-work-item",
            "run_state_path",
            "compatibility_bridge_input",
        )
    }


def test_design_delta_parent_drain_boundary_authority_registry_uses_checkout_owned_metadata() -> None:
    registry_payload = _load_design_delta_boundary_authority_registry()

    leaked_test_rows = [
        (row["workflow_name"], row["field_name"], row["surface_kind"])
        for row in registry_payload["rows"]
        if row["owner"] == "tests" or row["replacement_tranche"] == "test"
    ]

    assert leaked_test_rows == []


def test_design_delta_parent_drain_boundary_authority_expected_rows_include_generated_and_managed_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(tmp_path, monkeypatch)
    boundary_projection = json.loads(
        result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
    )

    expected_rows = build_design_delta_boundary_authority_expected_rows(boundary_projection)
    drain_workflow = next(
        workflow
        for workflow in boundary_projection["workflows"]
        if workflow["workflow_name"] == "lisp_frontend_design_delta/drain::drain"
    )

    flattened_inputs = {
        field["generated_name"]: field
        for field in drain_workflow["flattened_inputs"]
        if isinstance(field, dict) and isinstance(field.get("generated_name"), str)
    }
    drain_generated_internal = {
        field["generated_name"]
        for field in drain_workflow["generated_internal_inputs"]
        if isinstance(field, dict)
        and isinstance(field.get("generated_name"), str)
        and (
            field.get("reason") == "managed_write_root"
            or (
                isinstance(
                    flattened_inputs.get(field["generated_name"], {}).get("contract_definition"),
                    dict,
                )
                and flattened_inputs.get(field["generated_name"], {})
                .get("contract_definition", {})
                .get("type")
                == "relpath"
                )
            )
    }
    drain_generated_internal -= set(drain_workflow["boundary"]["public_input_names"])
    drain_managed_write_roots = set(
        drain_workflow["boundary"]["private_managed_write_root_inputs"]
    )

    generated_internal_coverage = {
        field_name
        for (workflow_name, field_name), row in expected_rows.items()
        if workflow_name == "lisp_frontend_design_delta/drain::drain"
        and row["surface_kind"]
        in {
            "generated_internal_input",
            "managed_write_root",
            "runtime_context_input",
        }
    }
    compatibility_bridge_coverage = {
        field_name
        for (workflow_name, field_name), row in expected_rows.items()
        if workflow_name == "lisp_frontend_design_delta/drain::drain"
        and row["surface_kind"] == "compatibility_bridge_input"
    }
    managed_write_root_rows = {
        field_name
        for (workflow_name, field_name), row in expected_rows.items()
        if workflow_name == "lisp_frontend_design_delta/drain::drain"
        and row["surface_kind"] == "managed_write_root"
    }

    assert generated_internal_coverage == drain_generated_internal
    assert compatibility_bridge_coverage == {"run_state_path"}
    assert managed_write_root_rows == drain_managed_write_roots


def test_design_delta_parent_drain_boundary_authority_expected_rows_exclude_scalar_runtime_context_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(tmp_path, monkeypatch)
    boundary_projection = json.loads(
        result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
    )

    expected_rows = build_design_delta_boundary_authority_expected_rows(boundary_projection)

    assert (
        "lisp_frontend_design_delta/drain::drain",
        "phase-ctx__phase-name",
    ) not in expected_rows
    assert (
        "lisp_frontend_design_delta/drain::drain",
        "phase-ctx__run__run-id",
    ) not in expected_rows
    assert (
        "lisp_frontend_design_delta/drain::drain",
        "run__artifact-root",
    ) not in expected_rows
    assert (
        "lisp_frontend_design_delta/drain::drain",
        "run__state-root",
    ) not in expected_rows
    assert (
        "lisp_frontend_design_delta/drain::drain",
        "run_state_path",
    ) in expected_rows
    assert expected_rows[
        ("lisp_frontend_design_delta/drain::drain", "run_state_path")
    ]["surface_kind"] == "compatibility_bridge_input"
    assert all(
        ("lisp_frontend_design_delta/drain::drain", field_name) not in expected_rows
        for field_name in {
            "selection_bundle_report_path",
            "command_adapter_contract_path",
            "draft_bundle_target_path",
            "architecture_validation_bundle_target_path",
            "drain_summary_target_path",
        }
    )
    for field_name in {"architecture_bundle_path", "manifest_path", "progress_ledger_path"}:
        row = expected_rows[("lisp_frontend_design_delta/drain::drain", field_name)]
        assert row["surface_kind"] == "public_input"
    run_state_row = expected_rows[
        ("lisp_frontend_design_delta/drain::drain", "run_state_path")
    ]
    assert run_state_row["surface_kind"] == "compatibility_bridge_input"


def test_design_delta_parent_drain_build_rejects_unclassified_path_like_boundary_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_design_delta_boundary_authority_registry()
    payload["rows"] = [
        row
        for row in payload["rows"]
        if not (
            row["workflow_name"] == "lisp_frontend_design_delta/drain::drain"
            and row["field_name"] == "manifest_path"
        )
    ]

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(tmp_path, monkeypatch, registry_payload=payload)
    assert excinfo.value.diagnostics[0].code == "workflow_boundary_authority_unclassified"
    assert "unclassified" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_build_rejects_missing_public_or_generated_boundary_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_design_delta_boundary_authority_registry()
    payload["rows"] = [
        row
        for row in payload["rows"]
        if not (
            row["workflow_name"] == "lisp_frontend_design_delta/drain::drain"
            and row["field_name"] == "baseline_design_path"
        )
    ]

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(tmp_path, monkeypatch, registry_payload=payload)
    assert excinfo.value.diagnostics[0].code == "workflow_boundary_authority_unclassified"
    assert "unclassified" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_build_rejects_stale_boundary_authority_registry_row_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_design_delta_boundary_authority_registry()
    payload["rows"].append(
        {
            "workflow_name": "lisp_frontend_design_delta/drain::drain",
            "field_name": "no_such_boundary_value",
            "surface_kind": "public_input",
            "authority_class": "public_authored",
            "path_like": True,
            "owner": "tests",
            "justification": "intentional stale row",
            "replacement_tranche": "G0",
            "parity_constrained": True,
        }
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(tmp_path, monkeypatch, registry_payload=payload)
    assert excinfo.value.diagnostics[0].code == "workflow_boundary_authority_unclassified"
    assert "stale" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_build_rejects_boundary_authority_registry_path_like_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_design_delta_boundary_authority_registry()
    for row in payload["rows"]:
        if (
            row["workflow_name"] == "lisp_frontend_design_delta/drain::drain"
            and row["field_name"] == "baseline_design_path"
            and row["surface_kind"] == "public_input"
        ):
            row["path_like"] = False
            break
    else:
        raise AssertionError("expected baseline_design_path boundary row to exist")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(tmp_path, monkeypatch, registry_payload=payload)
    assert excinfo.value.diagnostics[0].code == "workflow_boundary_authority_unclassified"
    assert "path_like" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_build_rejects_private_authority_value_exposed_publicly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_design_delta_boundary_authority_registry()
    for row in payload["rows"]:
        if (
            row["workflow_name"] == "lisp_frontend_design_delta/drain::drain"
            and row["field_name"] == "baseline_design_path"
        ):
            row["authority_class"] = "runtime_derived"
            break
    else:
        raise AssertionError("expected baseline_design_path row in boundary registry fixture")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(tmp_path, monkeypatch, registry_payload=payload)
    assert excinfo.value.diagnostics[0].code == "workflow_boundary_private_class_exposed_publicly"
    assert "public" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_build_keeps_runtime_owned_context_mapped_to_runtime_derived(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(tmp_path, monkeypatch)
    payload = json.loads(
        result.artifact_paths["boundary_authority_report"].read_text(encoding="utf-8")
    )
    drain_row = next(
        row
        for row in payload["workflows"]
        if row["workflow_name"] == "lisp_frontend_design_delta/drain::drain"
    )

    assert {
        "run__artifact-root",
        "run__state-root",
    }.issubset(set(drain_row["runtime_derived"]))
    assert "phase-ctx__phase-name" not in drain_row["runtime_derived"]
    assert "phase-ctx__run__run-id" not in drain_row["runtime_derived"]


def test_design_delta_parent_drain_boundary_authority_report_records_generated_and_managed_path_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )
    payload = json.loads(
        result.artifact_paths["boundary_authority_report"].read_text(encoding="utf-8")
    )
    drain_row = next(
        row
        for row in payload["workflows"]
        if row["workflow_name"] == "lisp_frontend_design_delta/drain::drain"
    )

    generated_internal_inputs = set(
        drain_row["compiled_evidence"]["generated_internal_inputs"]
    )
    managed_write_root_inputs = set(
        drain_row["compiled_evidence"]["private_managed_write_root_inputs"]
    )

    assert generated_internal_inputs == set(drain_row["generated_internal"]).union(
        {"run_state_path"}
    )
    assert managed_write_root_inputs == set(drain_row["generated_internal"])
    assert drain_row["generated_internal"] != []
    assert set(drain_row["compatibility_bridge"]) == {"run_state_path"}


def test_boundary_authority_report_records_pure_projection_classification_for_fixture_local_projection_helpers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    monkeypatch.setattr(
        build,
        "_maybe_load_design_delta_boundary_authority_registry",
        lambda **_: {
            "schema_version": "workflow_lisp_design_delta_boundary_authority.v1",
            "rows": [],
            "__registry_path__": str(tmp_path / "projection.boundary_authority.json"),
            "__registry_sha256__": "test",
            "workflow_family": "pure_projection_fixture_support",
        },
    )
    result = build.build_frontend_bundle(
        request_cls(
            source_path=FIXTURES
            / "valid"
            / "design_delta_projection_runtime_support"
            / "projections.orc",
            source_roots=(FIXTURES / "valid",),
            entry_workflow="design_delta_projection_runtime_support/projections::project-selector-action",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    payload = json.loads(
        result.artifact_paths["boundary_authority_report"].read_text(encoding="utf-8")
    )
    rows_by_name = {row["workflow_name"]: row for row in payload["workflows"]}

    selector_projection_row = rows_by_name[
        "design_delta_projection_runtime_support/projections::project-selector-action"
    ]
    terminal_projection_row = rows_by_name[
        "design_delta_projection_runtime_support/projections::classify-work-item-terminal"
    ]

    assert selector_projection_row["compiled_evidence"]["pure_projection_classification"] == {
        "structural": True,
    }
    assert terminal_projection_row["compiled_evidence"]["pure_projection_classification"] == {
        "structural": True,
    }


def test_design_delta_parent_drain_boundary_registry_changes_build_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _build_design_delta_parent_drain(tmp_path / "first", monkeypatch)
    payload = _load_design_delta_boundary_authority_registry()
    payload["rows"][0]["justification"] = payload["rows"][0]["justification"] + " (mutated)"
    second = _build_design_delta_parent_drain(
        tmp_path / "second",
        monkeypatch,
        registry_payload=payload,
    )

    assert first.manifest.fingerprint != second.manifest.fingerprint


def test_design_delta_parent_drain_manifest_records_boundary_registry_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(tmp_path, monkeypatch)

    provenance = result.manifest.boundary_authority_registry
    assert provenance["workflow_family"] == "design_delta_parent_drain"
    assert provenance["path"].endswith("design_delta_parent_drain.boundary_authority.json")
    assert provenance["sha256"].startswith("sha256:")


def test_design_delta_parent_drain_build_emits_value_flow_census_report_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    assert "value_flow_census_report" in result.artifact_paths
    assert result.manifest.artifact_status["value_flow_census_report"] == "emitted"
    payload = json.loads(
        result.artifact_paths["value_flow_census_report"].read_text(encoding="utf-8")
    )
    assert payload["workflow_family"] == "design_delta_parent_drain"
    assert payload["status"] == "pass"
    assert payload["missing_rows"] == []
    assert payload["stale_rows"] == []
    assert payload["invalid_rows"] == []
    assert payload["extra_compiled_rows"] == []


def test_design_delta_parent_drain_value_flow_census_report_covers_required_source_kinds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    payload = json.loads(
        result.artifact_paths["value_flow_census_report"].read_text(encoding="utf-8")
    )
    covered_kinds = {
        row["source_kind"]
        for workflow_row in payload["workflow_rows"]
        for row in workflow_row["rows"]
    }
    checked_census = _load_design_delta_value_flow_census()
    absent_kinds = set(
        (checked_census.get("coverage", {}).get("absent_source_kinds") or {}).keys()
    )
    assert set(payload["required_source_kinds"]).issubset(covered_kinds | absent_kinds)


def test_design_delta_parent_drain_value_flow_census_report_covers_declared_workflow_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    payload = json.loads(
        result.artifact_paths["value_flow_census_report"].read_text(encoding="utf-8")
    )
    reported_surfaces = {
        row["workflow_surface"] for row in payload["workflow_rows"]
    }
    assert set(payload["declared_workflow_surfaces"]) == reported_surfaces


def test_design_delta_parent_drain_value_flow_census_report_refs_checked_path_like_boundary_inventory(
) -> None:
    payload = _load_design_delta_value_flow_census()
    covered_boundary_rows = {
        (row["workflow_surface"], row["symbol_or_field"])
        for row in payload["rows"]
        if any(
            isinstance(evidence, dict)
            and evidence.get("kind") == "boundary_authority_report"
            for evidence in row.get("source_evidence", [])
        )
    }
    expected_boundary_rows = {
        (row["workflow_name"], row["field_name"])
        for row in _load_design_delta_boundary_authority_registry()["rows"]
        if row["path_like"]
    }

    assert covered_boundary_rows == expected_boundary_rows


def test_design_delta_parent_drain_value_flow_census_rejects_missing_checked_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_design_delta_value_flow_census()
    payload["rows"] = [
        row
        for row in payload["rows"]
        if row["row_id"]
        != "compiled_boundary::lisp_frontend_design_delta/drain::drain::return__drain-summary"
    ]

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            value_flow_census_payload=payload,
        )
    assert excinfo.value.diagnostics[0].code in {
        "value_flow_census_invalid",
        "consumer_rendering_census_invalid",
    }
    assert any(
        token in excinfo.value.diagnostics[0].message for token in ("missing", "stale")
    )


def test_design_delta_parent_drain_value_flow_census_rejects_stale_compiled_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_design_delta_value_flow_census()
    payload["rows"].append(
        {
            "row_id": "stale.extra.row",
            "workflow_surface": "lisp_frontend_design_delta/drain::drain",
            "source_kind": "generated_path",
            "symbol_or_field": "__missing_generated_path__",
            "path_or_contract": "GeneratedPath.missing",
            "plumbing_class": "generated_internal",
            "boundary_authority_class": "generated_internal",
            "track_owner": "shared",
            "current_consumer": "runtime",
            "semantic_owner": "runtime",
            "source_evidence": [
                {
                    "kind": "compiled_boundary_projection",
                    "path": ".orchestrate/build/example/workflow_boundary_projection.json",
                }
            ],
            "replacement_target": None,
            "command_boundary": None,
            "bridge": None,
            "notes": "intentional stale row",
        }
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            value_flow_census_payload=payload,
        )
    assert excinfo.value.diagnostics[0].code == "value_flow_census_invalid"
    assert "stale" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_value_flow_census_rejects_unclassified_path_like_plumbing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_design_delta_value_flow_census()
    for row in payload["rows"]:
        if row["row_id"] == "drain.generated.state_root":
            row["plumbing_class"] = "public_authored"
            break
    else:
        raise AssertionError("expected generated state-root row in checked census fixture")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            value_flow_census_payload=payload,
        )
    assert excinfo.value.diagnostics[0].code == "value_flow_census_invalid"
    assert "unclassified" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_value_flow_census_rejects_pointer_path_as_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_design_delta_value_flow_census()
    payload["rows"].append(
        {
            "row_id": "synthetic.pointer.selection_bundle_path",
                "workflow_surface": "lisp_frontend_design_delta/selector::select-next-work",
                "source_kind": "pointer_path",
                "symbol_or_field": "selection_bundle_path",
                "path_or_contract": "selection_bundle_path",
                "plumbing_class": "public_authored",
                "boundary_authority_class": "public_authored",
                "track_owner": "shared",
                "current_consumer": "legacy_reader",
                "semantic_owner": "workflow_surface",
            "source_evidence": [
                {
                    "kind": "boundary_authority_report",
                    "path": "boundary_authority_report.json",
                }
                ],
                "replacement_target": "Track C entry publication policy",
                "command_boundary": None,
                "bridge": None,
                "notes": "intentional invalid pointer authority row",
        }
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            value_flow_census_payload=payload,
        )
    assert excinfo.value.diagnostics[0].code == "value_flow_census_invalid"
    assert "pointer_path" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_value_flow_census_manifest_records_input_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    provenance = result.manifest.value_flow_census
    assert provenance["workflow_family"] == "design_delta_parent_drain"
    assert provenance["path"].endswith("design_delta_parent_drain.value_flow_census.json")
    assert provenance["sha256"].startswith("sha256:")


def test_design_delta_parent_drain_value_flow_census_changes_build_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _build_design_delta_parent_drain(
        tmp_path / "first",
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path / "first"),
    )
    payload = _load_design_delta_value_flow_census()
    payload["rows"][0]["notes"] = str(payload["rows"][0].get("notes", "")) + " mutated"
    second = _build_design_delta_parent_drain(
        tmp_path / "second",
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path / "second"),
        value_flow_census_payload=payload,
    )

    assert first.manifest.fingerprint != second.manifest.fingerprint


def test_design_delta_parent_drain_build_emits_consumer_rendering_census_report_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    assert "consumer_rendering_census_report" in result.artifact_paths
    assert (
        result.manifest.artifact_status["consumer_rendering_census_report"] == "emitted"
    )
    payload = json.loads(
        result.artifact_paths["consumer_rendering_census_report"].read_text(
            encoding="utf-8"
        )
    )
    assert payload["workflow_family"] == "design_delta_parent_drain"
    assert payload["status"] == "pass"
    assert payload["missing_rows"] == []
    assert payload["stale_rows"] == []
    assert payload["invalid_rows"] == []


def test_design_delta_parent_drain_build_emits_typed_prompt_input_report_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    assert "typed_prompt_input_report" in result.artifact_paths
    assert result.manifest.artifact_status["typed_prompt_input_report"] == "emitted"
    payload = json.loads(
        result.artifact_paths["typed_prompt_input_report"].read_text(encoding="utf-8")
    )
    assert payload["workflow_family"] == "design_delta_parent_drain"
    assert payload["status"] == "pass"
    rows_by_id = {row["c0_row_id"]: row for row in payload["selected_rows"]}
    assert set(rows_by_id) == {
        "c0.design_gap_architect_prompt_draft",
        "c0.implementation_phase_prompt_execute",
        "c0.implementation_phase_prompt_fix",
        "c0.implementation_phase_prompt_review",
        "c0.plan_phase_prompt_draft",
        "c0.plan_phase_prompt_fix",
        "c0.plan_phase_prompt_review",
        "c0.selector_prompt_select_next_work",
        "c0.work_item_prompt_classify_blocked_recovery",
    }
    assert rows_by_id["c0.design_gap_architect_prompt_draft"]["binding_names"] == [
        "request"
    ]
    assert rows_by_id["c0.selector_prompt_select_next_work"]["request_fields"][
        "field_authority"
    ]["subject.run_state"] == {
        "authority_class": "compatibility_bridge",
        "source_binding": "ctx.run_state_path",
        "bridge_field_name": "run_state_path",
    }
    assert payload["consumed_artifact_prompt_rows"] == []


def test_design_delta_parent_drain_build_keeps_consume_prompt_rows_empty_without_authored_consumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    payload = json.loads(
        result.artifact_paths["typed_prompt_input_report"].read_text(encoding="utf-8")
    )

    assert payload["consumed_artifact_prompt_rows"] == []


def test_design_delta_parent_drain_build_emits_compatibility_bridge_report_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    assert "compatibility_bridge_report" in result.artifact_paths
    assert result.manifest.artifact_status["compatibility_bridge_report"] == "emitted"
    payload = json.loads(
        result.artifact_paths["compatibility_bridge_report"].read_text(
            encoding="utf-8"
        )
    )
    assert payload["workflow_family"] == "design_delta_parent_drain"
    assert payload["status"] == "pass"
    assert payload["generated_bridges"]
    assert payload["blocked_bridges"] == []
    assert payload["contract_isolation"]["typed_steps_do_not_consume_bridge_views"] is True


def test_design_delta_parent_drain_build_reclassifies_summary_rows_to_entry_publication_and_bridge_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    entry_publication_payload = json.loads(
        result.artifact_paths["entry_publication_report"].read_text(encoding="utf-8")
    )
    selected_entry_rows = {
        row["row_id"] for row in entry_publication_payload["selected_c0_rows"]
    }
    assert "c0.drain_materialized_drain_summary" in selected_entry_rows
    assert "c0.drain_materialized_drain_summary_compiled_boundary" not in selected_entry_rows
    assert (
        "c0.drain_output_return_drain_summary_run_state_path_compiled_boundary"
        not in selected_entry_rows
    )
    assert (
        "c0.drain_output_return_drain_summary_summary_target_compiled_boundary"
        not in selected_entry_rows
    )

    cleanup_payload = json.loads(
        result.artifact_paths["rendering_cleanup_report"].read_text(encoding="utf-8")
    )
    cleanup_rows = {
        row["c0_row_id"]: row for row in cleanup_payload["cleanup_decisions"]
    }
    assert cleanup_rows["c0.drain_materialized_drain_summary"]["cleanup_decision"] == "RETIRED_TO_ENTRY_PUBLICATION"
    assert "c0.drain_materialized_drain_summary_compiled_boundary" not in cleanup_rows
    assert "c0.drain_materialized_drain_summary" not in cleanup_payload[
        "surviving_body_materialization_row_ids"
    ]
    assert "c0.drain_materialized_drain_summary_compiled_boundary" not in cleanup_payload[
        "surviving_body_materialization_row_ids"
    ]


def test_design_delta_parent_drain_build_reclassifies_work_item_summary_rows_to_bridge_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    cleanup_payload = json.loads(
        result.artifact_paths["rendering_cleanup_report"].read_text(encoding="utf-8")
    )
    cleanup_rows = {
        row["c0_row_id"]: row for row in cleanup_payload["cleanup_decisions"]
    }
    compatibility_bridge_payload = json.loads(
        result.artifact_paths["compatibility_bridge_report"].read_text(
            encoding="utf-8"
        )
    )
    bridge_rows = {
        row["c0_row_id"]: row for row in compatibility_bridge_payload["selected_c0_rows"]
    }
    generated_bridge_ids = {
        row["c0_row_id"] for row in compatibility_bridge_payload["generated_bridges"]
    }
    value_flow_payload = json.loads(
        result.artifact_paths["value_flow_census_report"].read_text(encoding="utf-8")
    )
    value_flow_rows = {
        row["row_id"]: row for row in value_flow_payload["rows"]
    }

    assert cleanup_rows["c0.work_item_summary_summary_path"][
        "cleanup_decision"
    ] == "RETIRED_TO_BRIDGE_METADATA"
    assert "c0.work_item_summary_summary_path_compiled_boundary" not in cleanup_rows
    assert "c0.work_item_summary_summary_path" not in cleanup_payload[
        "surviving_body_materialization_row_ids"
    ]
    assert (
        "c0.work_item_summary_summary_path_compiled_boundary"
        not in cleanup_payload["surviving_body_materialization_row_ids"]
    )
    assert (
        "c0.work_item_stdlib_materialized_blocked_recovery_summary"
        not in cleanup_payload["surviving_body_materialization_row_ids"]
    )
    assert "c0.work_item_summary_summary_path" in generated_bridge_ids
    assert "c0.work_item_summary_summary_path_compiled_boundary" not in generated_bridge_ids
    assert bridge_rows["c0.work_item_summary_summary_path"]["target_binding"][
        "target_labels"
    ] == [
        "artifacts/work/item_summary.json",
        "artifacts/work/archive/item_summary.json",
    ]
    assert (
        bridge_rows["c0.work_item_summary_summary_path"]["consumer_lane"]
        == "retirement_candidate"
    )
    assert (
        value_flow_rows["work_item.summary.summary_path"]["path_or_contract"]
        == "artifacts/work/item_summary.json"
    )
    assert (
        value_flow_rows["work_item.summary.summary_path"][
            "boundary_authority_class"
        ]
        == "compatibility_bridge"
    )


def test_design_delta_parent_drain_checked_rendering_cleanup_keeps_typed_handoff_rows_out_of_blocked_publication_lane() -> None:
    consumer_rows = {
        row["row_id"]: row for row in _load_design_delta_consumer_rendering_census()["rows"]
    }
    cleanup_rows = {
        row["c0_row_id"]: row["decision"]
        for row in _load_design_delta_rendering_cleanup_manifest()["rows"]
    }

    for row_id in (
        "c0.design_gap_architect_validate_output_work_item_bundle_path",
        "c0.design_gap_architect_validate_output_work_item_bundle_path_compiled_boundary",
        "c0.plan_phase_output_approved_plan_path",
        "c0.plan_phase_output_approved_plan_path_compiled_boundary",
        "c0.plan_phase_output_return_blocked_plan_path",
        "c0.plan_phase_output_return_blocked_plan_path_compiled_boundary",
        "c0.plan_phase_output_return_exhausted_plan_path",
        "c0.plan_phase_output_return_exhausted_plan_path_compiled_boundary",
        "c0.plan_phase_output_return_findings_items_path",
        "c0.plan_phase_output_return_findings_items_path_compiled_boundary",
    ):
        assert consumer_rows[row_id]["consumer_lane"] == "typed_step"
        assert cleanup_rows[row_id] == "NOT_C5_TARGET"


def test_design_delta_parent_drain_build_emits_rendering_cleanup_report_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()
    entry_publication = importlib.import_module("orchestrator.workflow_lisp.entry_publication")
    monkeypatch.setattr(
        build,
        "_build_entry_publication_report",
        lambda **kwargs: {
            "schema_version": "workflow_lisp_entry_publication_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "diagnostics": [],
            "selected_c0_rows": entry_publication.select_entry_publication_rows(
                kwargs["consumer_rendering_census"]
            ),
        },
    )
    cleanup_manifest = json.loads(
        build.DESIGN_DELTA_PARENT_DRAIN_RENDERING_CLEANUP_PATH.read_text(
            encoding="utf-8"
        )
    )
    cleanup_manifest["rows"] = [
        row
        for row in cleanup_manifest["rows"]
        if row["c0_row_id"]
        in {
            "c0.implementation_phase_materialized_return_checks_report",
            "c0.implementation_phase_materialized_return_checks_report_compiled_boundary",
        }
    ]
    cleanup_manifest["__manifest_path__"] = str(
        build.DESIGN_DELTA_PARENT_DRAIN_RENDERING_CLEANUP_PATH
    )
    cleanup_manifest["__manifest_sha256__"] = hashlib.sha256(
        json.dumps(cleanup_manifest, sort_keys=True).encode("utf-8")
    ).hexdigest()
    monkeypatch.setattr(
        build,
        "_maybe_load_design_delta_rendering_cleanup_manifest",
        lambda **kwargs: cleanup_manifest,
    )
    monkeypatch.setattr(
        build,
        "_maybe_load_design_delta_rendering_ergonomics_manifest",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        build.resume_plumbing_retirement,
        "build_resume_plumbing_retirement_report",
        lambda **kwargs: {
            "schema_version": "workflow_lisp_resume_plumbing_retirement_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "diagnostics": [],
        },
    )
    monkeypatch.setattr(
        build.lexical_checkpoint_default_resume,
        "build_default_resume_report",
        lambda **kwargs: {
            "schema_version": "workflow_lisp_default_resume_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "diagnostics": [],
        },
    )
    monkeypatch.setattr(
        build,
        "build_parent_drain_census_alignment_report",
        lambda **kwargs: {
            "schema_version": "workflow_lisp_parent_drain_census_alignment_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "diagnostics": [],
        },
    )
    original_collect_effects = build._collect_materialize_view_effects
    monkeypatch.setattr(
        build,
        "_collect_materialize_view_effects",
        lambda bundles: [
            effect
            for effect in original_collect_effects(bundles)
            if "blocked_implementation_checks_report"
            in str(effect.get("effect_id", ""))
        ],
    )
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        value_flow_census_payload=_aligned_design_delta_value_flow_census(),
    )

    assert "observability_summary_report" in result.artifact_paths
    assert (
        result.manifest.artifact_status["observability_summary_report"] == "emitted"
    )
    assert "rendering_cleanup_report" in result.artifact_paths
    assert result.manifest.artifact_status["rendering_cleanup_report"] == "emitted"
    payload = json.loads(
        result.artifact_paths["rendering_cleanup_report"].read_text(
            encoding="utf-8"
        )
    )
    assert payload["workflow_family"] == "design_delta_parent_drain"
    assert payload["schema_version"] == "workflow_lisp_rendering_cleanup_report.v1"
    assert payload["status"] == "pass"
    assert payload["blocked_compatibility_row_ids"] == []
    assert set(payload["surviving_body_materialization_row_ids"]) == {
        "c0.implementation_phase_materialized_return_checks_report",
        "c0.implementation_phase_materialized_return_checks_report_compiled_boundary",
    }
    cleanup_rows = {row["c0_row_id"]: row for row in payload["cleanup_decisions"]}
    assert (
        cleanup_rows["c0.implementation_phase_materialized_return_checks_report"][
            "cleanup_decision"
        ]
        == "KEEP_TIMED_PUBLICATION"
    )
    assert (
        cleanup_rows[
            "c0.implementation_phase_materialized_return_checks_report_compiled_boundary"
        ]["cleanup_decision"]
        == "KEEP_TIMED_PUBLICATION"
    )


def test_design_delta_parent_drain_build_emits_pair_aware_observability_summary_report_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()
    pair_manifest_path, legacy_payload_path = (
        _write_design_delta_observability_old_writer_pair_inputs(tmp_path)
    )
    observability = importlib.import_module(
        "orchestrator.workflow_lisp.observability_summaries"
    )
    consumer_rendering_census = _load_design_delta_consumer_rendering_census()
    consumer_rendering_census["rows"] = [
        row
        for row in consumer_rendering_census["rows"]
        if row["row_id"] in _design_delta_checks_report_pair_row_ids()
    ]
    pair_manifest = observability.load_old_writer_pair_manifest(
        pair_manifest_path,
        consumer_rendering_census=consumer_rendering_census,
    )
    payload = build._build_design_delta_observability_summary_prerequisite_report(
        consumer_rendering_census=consumer_rendering_census,
        old_writer_pair_manifest=pair_manifest,
        materialize_view_effects=[
            {
                "authority_class": "materialized_view",
                "step_id": "implementation_phase.__materialize_view__blocked_implementation_checks_report",
                "workflow_surface": "lisp_frontend_design_delta/implementation_phase::implementation-phase",
            }
        ],
    )

    assert payload["status"] == "pass"
    assert {
        "c0.implementation_phase_materialized_return_checks_report",
        "c0.implementation_phase_materialized_return_checks_report_compiled_boundary",
    } <= set(payload["selected_c0_row_ids"])
    assert payload["pair_manifest_provenance"]["path"] == str(pair_manifest_path.resolve())


def test_design_delta_parent_drain_observability_report_warns_for_live_timed_materialization_without_pair(
    tmp_path: Path,
) -> None:
    build = _build_module()
    consumer_rendering_census = _load_design_delta_consumer_rendering_census()
    consumer_rendering_census["rows"] = [
        row
        for row in consumer_rendering_census["rows"]
        if row["row_id"]
        == "c0.implementation_phase_materialized_return_checks_report"
    ]

    payload = build._build_design_delta_observability_summary_prerequisite_report(
        consumer_rendering_census=consumer_rendering_census,
        old_writer_pair_manifest=None,
        materialize_view_effects=[
            {
                "authority_class": "materialized_view",
                "step_id": "implementation_phase.__materialize_view__blocked_implementation_checks_report",
                "workflow_surface": "lisp_frontend_design_delta/implementation_phase::implementation-phase",
            }
        ],
    )

    assert payload["status"] == "pass"
    assert payload["diagnostics"]["errors"] == []
    assert {
        diagnostic["code"]
        for diagnostic in payload["diagnostics"]["warnings"]
    } == {"observability_summary_old_writer_mechanics_not_contract"}


def test_design_delta_parent_drain_build_rejects_missing_checks_report_pair_mirror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()
    pair_manifest_path, legacy_payload_path = (
        _write_design_delta_observability_old_writer_pair_inputs(
            tmp_path,
            missing_mirror=True,
        )
    )
    monkeypatch.setattr(
        build,
        "DESIGN_DELTA_PARENT_DRAIN_OBSERVABILITY_OLD_WRITER_COMPARISONS_PATH",
        pair_manifest_path,
        raising=False,
    )
    monkeypatch.setattr(
        build,
        "DESIGN_DELTA_PARENT_DRAIN_BLOCKED_IMPLEMENTATION_CHECKS_REPORT_LEGACY_PAYLOAD_PATH",
        legacy_payload_path,
        raising=False,
    )

    with pytest.raises(LispFrontendCompileError, match="observability_summary_old_writer_mirror_missing"):
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        )


def test_design_delta_parent_drain_observability_pair_evidence_changes_build_fingerprint(
    tmp_path: Path,
) -> None:
    baseline = _design_delta_fingerprint_context(tmp_path / "baseline")
    build = baseline["build"]
    baseline_fingerprint = build._fingerprint_build(
        request=baseline["request"],
        compile_result=baseline["compile_result"],
        imported_bindings=tuple(),
        entry_selection=baseline["entry_selection"],
        provider_externs=baseline["provider_externs"],
        prompt_externs=baseline["prompt_externs"],
        command_boundary_manifest=baseline["command_boundary_manifest"],
        boundary_authority_registry=baseline["boundary_authority_registry"],
        value_flow_census=baseline["value_flow_census"],
        consumer_rendering_census=baseline["consumer_rendering_census"],
        observability_old_writer_pair_manifest=baseline["observability_pair_manifest"],
        resume_plumbing_retirement_manifest=baseline[
            "resume_plumbing_retirement_manifest"
        ],
    )

    pair_manifest_path, legacy_payload_path = (
        _write_design_delta_observability_old_writer_pair_inputs(tmp_path / "mutated")
    )
    mutated_pair_manifest = json.loads(pair_manifest_path.read_text(encoding="utf-8"))
    replacement_payload = mutated_pair_manifest["row_pairs"][0]["comparison_inputs"][
        "replacement_typed_summary_payload"
    ]
    replacement_payload["progress_report"] = "artifacts/work/changed_progress_report.md"
    mutated_pair_manifest["row_pairs"][0]["replacement"]["typed_summary_digest"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                replacement_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()
    )
    pair_manifest_path.write_text(
        json.dumps(mutated_pair_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    mutated = _design_delta_fingerprint_context(
        tmp_path / "mutated-context",
        pair_manifest_path=pair_manifest_path,
    )
    mutated_fingerprint = build._fingerprint_build(
        request=mutated["request"],
        compile_result=mutated["compile_result"],
        imported_bindings=tuple(),
        entry_selection=mutated["entry_selection"],
        provider_externs=mutated["provider_externs"],
        prompt_externs=mutated["prompt_externs"],
        command_boundary_manifest=mutated["command_boundary_manifest"],
        boundary_authority_registry=mutated["boundary_authority_registry"],
        value_flow_census=mutated["value_flow_census"],
        consumer_rendering_census=mutated["consumer_rendering_census"],
        observability_old_writer_pair_manifest=mutated["observability_pair_manifest"],
        resume_plumbing_retirement_manifest=mutated[
            "resume_plumbing_retirement_manifest"
        ],
    )

    legacy_payload_path.write_text(
        json.dumps(
            {
                "status": "APPROVED",
                "progress_report": "artifacts/work/progress_report.md",
                "blocker_class": "unrecoverable_after_fix_attempt",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="observability_summary_old_writer_evidence_stale"):
        importlib.import_module(
            "orchestrator.workflow_lisp.observability_summaries"
        ).load_old_writer_pair_manifest(
            pair_manifest_path,
            consumer_rendering_census=mutated["consumer_rendering_census"],
        )

    assert baseline_fingerprint != mutated_fingerprint


def test_design_delta_parent_drain_build_manifest_records_observability_pair_provenance(
    tmp_path: Path,
) -> None:
    context = _design_delta_fingerprint_context(tmp_path)
    build = context["build"]
    manifest = build._build_manifest(
        request=context["request"],
        compile_result=context["compile_result"],
        entry_selection=context["entry_selection"],
        imported_bindings=tuple(),
        artifact_paths={},
        fingerprint="fingerprint",
        diagnostics=context["compile_result"].diagnostics,
        build_root=tmp_path / ".orchestrate" / "build" / "fingerprint",
        emit_debug_yaml=False,
        boundary_authority_registry=context["boundary_authority_registry"],
        value_flow_census=context["value_flow_census"],
        consumer_rendering_census=context["consumer_rendering_census"],
        observability_old_writer_pair_manifest=context["observability_pair_manifest"],
        resume_plumbing_retirement_manifest=context[
            "resume_plumbing_retirement_manifest"
        ],
    )

    assert manifest.observability_old_writer_pair_evidence is not None
    assert (
        manifest.observability_old_writer_pair_evidence["path"]
        == str(
            (
                DESIGN_DELTA_MIGRATION_INPUTS
                / "design_delta_parent_drain.observability_old_writer_comparisons.json"
            ).resolve()
        )
    )
    legacy_sources = manifest.observability_old_writer_pair_evidence[
        "legacy_payload_sources"
    ]
    assert legacy_sources
    assert legacy_sources[0]["path"].endswith(
        "design_delta_parent_drain.blocked_implementation_checks_report.legacy_writer_payload.json"
    )


def test_design_delta_parent_drain_build_emits_rendering_ergonomics_report_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    assert "rendering_ergonomics_report" in result.artifact_paths
    assert (
        result.manifest.artifact_status["rendering_ergonomics_report"] == "emitted"
    )
    payload = json.loads(
        result.artifact_paths["rendering_ergonomics_report"].read_text(
            encoding="utf-8"
        )
    )
    assert payload["schema_version"] == "workflow_lisp_rendering_ergonomics_report.v1"
    assert payload["status"] == "pass"
    assert payload["target_family"] == "lisp_frontend_design_delta_parent_drain"
    provider_shapes = {row["c0_row_id"]: row for row in payload["provider_input_shapes"]}
    assert set(provider_shapes) == {
        "c0.design_gap_architect_prompt_draft",
        "c0.implementation_phase_prompt_execute",
        "c0.implementation_phase_prompt_fix",
        "c0.implementation_phase_prompt_review",
        "c0.plan_phase_prompt_draft",
        "c0.plan_phase_prompt_fix",
        "c0.plan_phase_prompt_review",
        "c0.selector_prompt_select_next_work",
        "c0.work_item_prompt_classify_blocked_recovery",
    }
    assert provider_shapes["c0.plan_phase_prompt_review"]["request_type_name"] == (
        "PlanReviewRequest"
    )
    assert provider_shapes["c0.plan_phase_prompt_review"]["subject_type_name"] == (
        "PlanReviewPromptSubject"
    )
    assert provider_shapes["c0.plan_phase_prompt_review"]["targets_type_name"] == (
        "PlanReviewProviderTargets"
    )
    assert provider_shapes["c0.plan_phase_prompt_review"]["binding_names"] == ["request"]
    assert provider_shapes["c0.plan_phase_prompt_review"]["status"] == "pass"
    assert (
        provider_shapes["c0.design_gap_architect_prompt_draft"]["request_type_name"]
        == "DesignGapArchitectureRequest"
    )
    assert (
        provider_shapes["c0.design_gap_architect_prompt_draft"]["subject_type_name"]
        == "DesignGapArchitecturePromptSubject"
    )
    assert (
        provider_shapes["c0.design_gap_architect_prompt_draft"]["targets_type_name"]
        == "DesignGapArchitectureProviderTargets"
    )
    assert provider_shapes["c0.design_gap_architect_prompt_draft"]["binding_names"] == [
        "request"
    ]
    assert provider_shapes["c0.design_gap_architect_prompt_draft"]["status"] == "pass"
    assert provider_shapes["c0.selector_prompt_select_next_work"][
        "hidden_bridge_fields"
    ] == [
        {
            "field_path": "subject.run_state",
            "authority_class": "compatibility_bridge",
            "source_binding": "ctx.run_state_path",
            "bridge_field_name": "run_state_path",
        }
    ]
    # Every C0 rendering row resolves to exactly one slot and owning lane.
    assert all(payload["contract_isolation"].values())
    assert not payload["diagnostics"]
    # The report joins all six C0-C5 prerequisite reports as passing evidence.
    assert {
        report["status"] for report in payload["prerequisite_reports"].values()
    } == {"pass"}
    # The blocked command-bound bridge stays a bridge slot (never retired).
    bridge_rows = [
        slot["c0_row_id"]
        for slot in payload["consumer_slots"]
        if slot["consumer_lane"] == "compatibility_bridge"
    ]
    assert "c0.work_item_command_selection_bundle_path" not in bridge_rows


def test_design_delta_parent_drain_rendering_ergonomics_report_fails_closed_on_missing_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()
    policy = json.loads(
        build.DESIGN_DELTA_PARENT_DRAIN_RENDERING_ERGONOMICS_PATH.read_text(
            encoding="utf-8"
        )
    )
    # Drop one selected C0 row's slot: the C6 report must fail closed.
    policy["consumer_slots"] = policy["consumer_slots"][1:]
    bad_path = tmp_path / "design_delta_parent_drain.rendering_ergonomics.json"
    bad_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        build,
        "DESIGN_DELTA_PARENT_DRAIN_RENDERING_ERGONOMICS_PATH",
        bad_path,
        raising=False,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        )
    assert excinfo.value.diagnostics[0].code == "rendering_ergonomics_consumer_slot_missing"


def test_design_delta_parent_drain_build_bridge_lineage_in_semantic_and_executable_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    semantic_ir = json.loads(
        result.artifact_paths["semantic_ir"].read_text(encoding="utf-8")
    )
    executable_ir = json.loads(
        result.artifact_paths["executable_ir"].read_text(encoding="utf-8")
    )
    lowered_workflows = json.loads(
        result.artifact_paths["lowered_workflows"].read_text(encoding="utf-8")
    )
    runtime_plan = json.loads(
        result.artifact_paths["runtime_plan"].read_text(encoding="utf-8")
    )
    source_map = json.loads(
        result.artifact_paths["source_map"].read_text(encoding="utf-8")
    )

    assert semantic_ir["generated_compatibility_bridges"]
    assert executable_ir["generated_compatibility_bridges"]
    assert any(
        step_id.startswith("compatibility_bridge__")
        for module_payload in lowered_workflows["modules"].values()
        for workflow_payload in module_payload["workflows"]
        for step_id in workflow_payload["step_ids"]
    )
    assert any(
        node["step_id"].startswith("compatibility_bridge__")
        for node in runtime_plan["nodes"].values()
    )
    generated_effects = source_map["workflows"][
        "lisp_frontend_design_delta/work_item::run-work-item"
    ]["generated_semantic_effects"]
    assert any(
        effect["effect_kind"] == "materialize_view"
        and effect["details"]["authority_class"] == "compatibility_bridge"
        for effect in generated_effects
    )


def test_design_delta_parent_drain_build_returns_real_bridge_lineage_in_loaded_bundles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    drain_semantic_ir = workflow_semantic_ir_to_json(result.validated_bundle.semantic_ir)
    drain_executable_ir = workflow_executable_ir_to_json(result.validated_bundle.ir)
    drain_bridge_nodes = [
        node
        for node in result.validated_bundle.runtime_plan.nodes.values()
        if "compatibility_bridge__" in node.step_id
    ]

    work_item_bundle = result.validated_bundle.imports[
        "lisp_frontend_design_delta/work_item::run-work-item"
    ]
    work_item_semantic_ir = workflow_semantic_ir_to_json(work_item_bundle.semantic_ir)
    work_item_executable_ir = workflow_executable_ir_to_json(work_item_bundle.ir)
    work_item_bridge_nodes = [
        node
        for node in work_item_bundle.runtime_plan.nodes.values()
        if "compatibility_bridge__" in node.step_id
    ]

    assert len(drain_semantic_ir["generated_compatibility_bridges"]) == 6
    assert len(drain_executable_ir["generated_compatibility_bridges"]) == 6
    assert len(drain_bridge_nodes) == 6
    assert len(work_item_semantic_ir["generated_compatibility_bridges"]) == 6
    assert len(work_item_executable_ir["generated_compatibility_bridges"]) == 6
    assert len(work_item_bridge_nodes) == 6


def test_compatibility_bridge_surface_step_uses_checked_target_and_value_metadata() -> None:
    build = _build_module()

    step, allocation = build._compatibility_bridge_surface_step(
        workflow_name="synthetic/runtime::emit-summary",
        row={
            "bridge_id": "bridge.synthetic.summary",
            "c0_row_id": "c0.synthetic.summary",
            "renderer": {
                "renderer_id": "canonical-json",
                "renderer_version": 1,
            },
            "typed_value_source": {
                "kind": "compatibility_value_ref",
                "ref": "synthetic.summary",
                "value_document": {
                    "summary_id": {
                        "ref": "self.outputs.return__summary__summary_id",
                    },
                    "status": {
                        "ref": "self.outputs.return__summary__status",
                    },
                },
            },
            "target": {
                "kind": "generated_materialized_view",
                "durability": "durable_bridge",
                "authority_class": "compatibility_bridge",
                "path_template": "artifacts/work/custom_summary.json",
                "runtime_target": {
                    "ref": "inputs.custom_summary_target",
                },
            },
        },
    )

    assert allocation.concrete_path_template == "artifacts/work/custom_summary.json"
    assert step.materialize_view["target_path"] == {"ref": "inputs.custom_summary_target"}
    assert step.materialize_view["value_document"]["summary_id"].ref == (
        "self.outputs.return__summary__summary_id"
    )
    assert step.materialize_view["value_document"]["status"].ref == (
        "self.outputs.return__summary__status"
    )


def test_design_delta_parent_drain_consumer_rendering_report_records_manifest_and_u0_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    payload = json.loads(
        result.artifact_paths["consumer_rendering_census_report"].read_text(
            encoding="utf-8"
        )
    )
    assert payload["manifest_provenance"]["path"].endswith(
        "design_delta_parent_drain.consumer_rendering_census.json"
    )
    assert payload["source_census_provenance"]["path"].endswith(
        "design_delta_parent_drain.value_flow_census.json"
    )
    compiled_evidence = payload["compiled_evidence"]
    assert compiled_evidence["boundary_authority_report"]["path"].endswith(
        "boundary_authority_report.json"
    )
    assert compiled_evidence["prompt_externs"]["path"].endswith(
        "design_delta_parent_drain.prompts.json"
    )
    assert compiled_evidence["provider_externs"]["path"].endswith(
        "design_delta_parent_drain.providers.json"
    )
    assert compiled_evidence["view_dual_run_vectors"]["path"].endswith(
        "design_delta_view_dual_run_vectors.json"
    )
    assert compiled_evidence["view_dual_run_report"]["path"].endswith(
        "design_delta_parent_drain_view_dual_run_report.json"
    )
    provenance = result.manifest.consumer_rendering_census
    assert provenance["workflow_family"] == "design_delta_parent_drain"
    assert provenance["sha256"].startswith("sha256:")


def test_entry_publication_build_artifacts_expose_generated_publication_lineage(
    tmp_path: Path,
) -> None:
    result = _build_entry_publication_fixture(tmp_path)
    semantic_ir = json.loads(
        result.artifact_paths["semantic_ir"].read_text(encoding="utf-8")
    )
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))

    publication_effect = next(
        effect
        for effect in semantic_ir["effects"].values()
        if effect["effect_kind"] == "materialize_view"
        and isinstance(effect.get("details", {}).get("publication"), dict)
    )
    assert publication_effect["details"]["publication"]["role"] == "drain-summary"
    assert publication_effect["details"]["publication"]["row_id"].startswith(
        "publish.entry-publication-runtime"
    )

    workflow_name = "entry_publication_runtime::entry-publication-runtime"
    generated_effects = source_map["workflows"][workflow_name]["generated_semantic_effects"]
    assert any(
        effect["effect_kind"] == "materialize_view"
        and "publish" in effect["step_id"]
        for effect in generated_effects
    )


def test_entry_publication_build_fails_closed_when_lowering_evidence_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()
    compile_result = compile_stage3_entrypoint(
        ENTRY_PUBLICATION_RUNTIME_FIXTURE,
        source_roots=(FIXTURES / "valid",),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    workflow_name = "entry_publication_runtime::entry-publication-runtime"

    monkeypatch.setattr(
        build,
        "_collect_entry_publication_lowerings",
        lambda *args, **kwargs: [],
    )

    payload = build._build_entry_publication_report(
        compile_result=compile_result,
        entry_workflow_name=workflow_name,
        workflow_boundary_projection_payload=build._serialize_workflow_boundary_projection(
            compile_result,
            selected_name=workflow_name,
        ),
        source_map_payload=build._serialize_source_map(
            compile_result,
            selected_name=workflow_name,
        ),
        consumer_rendering_census={"target_family": "entry_publication_runtime", "rows": []},
    )

    assert payload["status"] == "fail"
    assert payload["diagnostics"][0]["code"] == "entry_publication_lowering_missing"


def test_entry_publication_build_accepts_selected_later_exported_entry_workflow(
    tmp_path: Path,
) -> None:
    build = _build_module()
    source_path = tmp_path / "entry_publication_selected_entry.orc"
    source_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule entry_publication_selected_entry)",
                "  (export first second)",
                "  (defunion EntryPublicationResult",
                "    (DONE (message String))",
                "    (BLOCKED (reason String)))",
                "  (defworkflow first",
                "    ()",
                "    -> EntryPublicationResult",
                "    (variant EntryPublicationResult DONE",
                '      :message "first"))',
                "  (defworkflow second",
                "    ()",
                "    -> EntryPublicationResult",
                "    (:publish",
                "      ((DONE :as drain-summary)))",
                "    (variant EntryPublicationResult DONE",
                '      :message "second")))',
                "",
            ]
        ),
        encoding="utf-8",
    )
    request_cls = getattr(build, "FrontendBuildRequest")

    result = build.build_frontend_bundle(
        request_cls(
            source_path=source_path,
            source_roots=(tmp_path,),
            entry_workflow="second",
            workspace_root=tmp_path,
        )
    )

    assert result.selected_workflow_name == "entry_publication_selected_entry::second"
    assert result.manifest.entry_workflow == "entry_publication_selected_entry::second"


def test_entry_publication_build_fails_closed_when_selected_non_entry_keeps_materialize_view(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()
    request = _design_delta_parent_drain_request(tmp_path)

    compile_result = compile_stage3_entrypoint(
        request.source_path,
        source_roots=request.source_roots,
        provider_externs=json.loads(request.provider_externs_path.read_text(encoding="utf-8")),
        prompt_externs=json.loads(request.prompt_externs_path.read_text(encoding="utf-8")),
        command_boundaries=build._parse_command_boundaries_manifest(
            json.loads(
                request.command_boundaries_path.read_text(encoding="utf-8")
            ),
            manifest_path=request.command_boundaries_path,
        ),
        validate_shared=True,
        workspace_root=tmp_path,
    )

    original_collect = build._collect_materialize_view_effects

    def _collect_with_selected_non_entry_effect(compile_result):
        effects = list(original_collect(compile_result))
        effects.append(
            {
                "effect_id": (
                    "effect:lisp_frontend_design_delta/selector::select-next-work:"
                    "synthetic_interior_publication:materialize_view"
                ),
                "workflow_surface": "lisp_frontend_design_delta/selector::select-next-work",
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "target_path": "artifacts/work/synthetic-selected-summary.json",
                "value_type": {
                    "kind": "record",
                    "name": "lisp_frontend_design_delta/types::SelectionOutput",
                },
            }
        )
        return effects

    monkeypatch.setattr(
        build,
        "_collect_materialize_view_effects",
        _collect_with_selected_non_entry_effect,
    )

    report = build._build_entry_publication_report(
        compile_result=compile_result,
        entry_workflow_name="lisp_frontend_design_delta/drain::drain",
        workflow_boundary_projection_payload=build._serialize_workflow_boundary_projection(
            compile_result,
            selected_name="lisp_frontend_design_delta/drain::drain",
        ),
        source_map_payload=build._serialize_source_map(
            compile_result,
            selected_name="lisp_frontend_design_delta/drain::drain",
        ),
        consumer_rendering_census=_load_design_delta_consumer_rendering_census(),
    )

    assert report["status"] == "fail"
    assert any(
        diagnostic["code"] == "interior_publication"
        and diagnostic["workflow_name"] == "lisp_frontend_design_delta/selector::select-next-work"
        for diagnostic in report["diagnostics"]
    )


def test_design_delta_parent_drain_consumer_rendering_report_reconciles_materialize_view_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    payload = json.loads(
        result.artifact_paths["consumer_rendering_census_report"].read_text(
            encoding="utf-8"
        )
    )
    effect_row_ids = {
        row["u0_row_id"] for row in payload["materialize_view_effect_rows"]
    }
    assert effect_row_ids == {
        "design_gap_architect_validate.materialized.architecture_targets_view",
        "implementation_phase.materialized.check_commands_view",
    }
    assert "drain.materialized.drain_summary" not in effect_row_ids
    assert "work_item.summary.summary_path" not in effect_row_ids


def test_design_delta_parent_drain_consumer_rendering_report_rejects_unmatched_materialize_view_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()
    original_collect = build._collect_materialize_view_effects

    def _collect_with_unmatched_effect(compile_result):
        effects = list(original_collect(compile_result))
        effects.append(
            {
                "effect_id": (
                    "effect:lisp_frontend_design_delta/selector::select-next-work:"
                    "synthetic_unmatched_materialize_view:materialize_view"
                ),
                "workflow_surface": "lisp_frontend_design_delta/selector::select-next-work",
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "target_path": "root.steps.selector.synthetic.summary_path",
                "value_type": {
                    "kind": "record",
                    "name": "lisp_frontend_design_delta/types::SyntheticSelectorView",
                },
            }
        )
        return effects

    monkeypatch.setattr(
        build,
        "_collect_materialize_view_effects",
        _collect_with_unmatched_effect,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        )

    assert excinfo.value.diagnostics[0].code == "consumer_rendering_census_invalid"
    assert "consumer_rendering_census_row_missing" in excinfo.value.diagnostics[0].message
    assert "synthetic_unmatched_materialize_view" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_consumer_rendering_report_rejects_same_workflow_unmatched_materialize_view_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()
    original_collect = build._collect_materialize_view_effects

    def _collect_with_same_workflow_unmatched_effect(compile_result):
        effects = list(original_collect(compile_result))
        effects.append(
            {
                "effect_id": (
                    "effect:lisp_frontend_design_delta/drain::drain:"
                    "root.lisp_frontend_design_delta_drain_drain__match_terminal__done__"
                    "materialize_view__synthetic_extra_drain_view:materialize_view"
                ),
                "workflow_surface": "lisp_frontend_design_delta/drain::drain",
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "target_path": (
                    "root.steps.lisp_frontend_design_delta/drain::drain__match_terminal__"
                    "done__status.artifacts.synthetic_summary_path"
                ),
                "value_type": {
                    "kind": "record",
                    "name": "lisp_frontend_design_delta/types::DrainSummaryValue",
                },
            }
        )
        return effects

    monkeypatch.setattr(
        build,
        "_collect_materialize_view_effects",
        _collect_with_same_workflow_unmatched_effect,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        )

    assert excinfo.value.diagnostics[0].code == "consumer_rendering_census_invalid"
    assert "consumer_rendering_census_row_missing" in excinfo.value.diagnostics[0].message
    assert "synthetic_extra_drain_view" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_consumer_rendering_report_rejects_missing_render_only_u0_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_design_delta_consumer_rendering_census()
    payload["rows"] = [
        row for row in payload["rows"] if row["u0_row_id"] != "plan_phase.prompt.draft"
    ]

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            consumer_rendering_census_payload=payload,
        )
    assert excinfo.value.diagnostics[0].code == "consumer_rendering_census_invalid"
    assert "consumer_rendering_census_row_missing" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_consumer_rendering_report_rejects_target_dependent_renderer_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_design_delta_consumer_rendering_census()
    for row in payload["rows"]:
        if row["u0_row_id"] == "drain.summary_report_target.final_summary_view":
            row["target_binding"] = {
                "kind": "consumer_owned_target",
                "target_labels": ["artifacts/work/drain_summary.json"],
            }
            break
    else:
        raise AssertionError("expected drain summary row in checked consumer rendering census")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            consumer_rendering_census_payload=payload,
        )
    assert excinfo.value.diagnostics[0].code == "consumer_rendering_census_invalid"
    assert "consumer_rendering_target_dependent" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_consumer_rendering_report_rejects_unclassified_body_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_design_delta_consumer_rendering_census()
    for row in payload["rows"]:
        if row["u0_row_id"] == "implementation_phase.materialized.check_commands_view":
            row["track_c_decision"] = "KEEP_TYPED"
            break
    else:
        raise AssertionError("expected timed body materialization row in checked consumer rendering census")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            consumer_rendering_census_payload=payload,
        )
    assert excinfo.value.diagnostics[0].code == "consumer_rendering_census_invalid"
    assert (
        "consumer_rendering_body_materialization_unclassified"
        in excinfo.value.diagnostics[0].message
    )


def test_design_delta_parent_drain_consumer_rendering_report_rejects_missing_bridge_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_design_delta_consumer_rendering_census()
    for row in payload["rows"]:
        if (
            row["u0_row_id"]
            == "compiled_boundary::lisp_frontend_design_delta/work_item::run-selected-item-stdlib::return__summary-path"
        ):
            row["bridge"] = None
            break
    else:
        raise AssertionError("expected work-item summary bridge row in checked consumer rendering census")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            consumer_rendering_census_payload=payload,
        )
    assert excinfo.value.diagnostics[0].code == "consumer_rendering_census_invalid"
    assert "consumer_rendering_bridge_metadata_missing" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_consumer_rendering_report_changes_build_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _build_design_delta_parent_drain(
        tmp_path / "first",
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path / "first"),
    )
    payload = _load_design_delta_consumer_rendering_census()
    payload["rows"][0]["notes"] = str(payload["rows"][0].get("notes", "")) + " mutated"
    second = _build_design_delta_parent_drain(
        tmp_path / "second",
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path / "second"),
        consumer_rendering_census_payload=payload,
    )

    assert first.manifest.fingerprint != second.manifest.fingerprint


def test_design_delta_parent_drain_build_emits_resume_plumbing_retirement_report_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
    )

    assert "resume_plumbing_retirement_report" in result.artifact_paths
    assert (
        result.manifest.artifact_status["resume_plumbing_retirement_report"] == "emitted"
    )
    payload = json.loads(
        result.artifact_paths["resume_plumbing_retirement_report"].read_text(
            encoding="utf-8"
        )
    )
    assert payload["workflow_family"] == "design_delta_parent_drain"
    assert payload["status"] == "pass"


def test_design_delta_parent_drain_build_emits_parent_drain_census_alignment_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    assert "parent_drain_census_alignment_report" in result.artifact_paths
    assert (
        result.manifest.artifact_status["parent_drain_census_alignment_report"]
        == "emitted"
    )
    payload = json.loads(
        result.artifact_paths["parent_drain_census_alignment_report"].read_text(
            encoding="utf-8"
        )
    )
    assert payload["workflow_family"] == "design_delta_parent_drain"
    assert payload["status"] == "pass"


def test_design_delta_parent_drain_build_emits_reference_family_conformance_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    assert "reference_family_conformance_profile" in result.artifact_paths
    assert (
        result.manifest.artifact_status["reference_family_conformance_profile"]
        == "emitted"
    )
    payload = json.loads(
        result.artifact_paths["reference_family_conformance_profile"].read_text(
            encoding="utf-8"
        )
    )
    assert payload["schema_version"] == "workflow_lisp_reference_family_conformance_profile.v1"
    assert "schema_id" not in payload
    assert payload["profile_status"] == "pass"
    assert payload["completed_gap_reconciliation"]["missing_from_drain_summary"] == []
    assert payload["parity_surface_reconciliation"]["derived_primary_surface"] == "yaml"
    assert {
        row["surface_id"] for row in payload["conformance_surfaces"]
    } == {
        "parent_callable_orc_route",
        "public_private_boundary",
        "hidden_compatibility_bridge_carriage",
        "hidden_compatibility_bridge_evidence_alignment",
        "observability_old_writer_retirement",
        "provider_inputs",
        "provider_write_targets",
        "body_renderings",
        "compatibility_files",
        "deterministic_helpers",
        "durable_state_changes",
        "source_shape_gate",
        "completion_inventory",
        "migration_parity_surface",
    }
    surfaces_by_id = {
        row["surface_id"]: row for row in payload["conformance_surfaces"]
    }
    for surface_id in (
        "parent_callable_orc_route",
        "completion_inventory",
        "migration_parity_surface",
    ):
        assert surfaces_by_id[surface_id]["evidence_paths"] != []


def test_design_delta_parent_drain_build_rejects_reference_family_completed_gap_summary_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drain_summary_path = _aligned_reference_family_drain_summary(tmp_path)
    payload = json.loads(drain_summary_path.read_text(encoding="utf-8"))
    payload["completed_design_gaps"].remove(
        "workflow-lisp-runtime-native-drain-reference-family-conformance-profile-reconciliation"
    )
    drain_summary_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            drain_summary_path=drain_summary_path,
        )

    assert excinfo.value.diagnostics[0].code == "reference_family_conformance_invalid"
    assert (
        "reference_family_completed_gap_summary_mismatch"
        in excinfo.value.diagnostics[0].message
    )


def test_design_delta_parent_drain_build_rejects_reference_family_parity_surface_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markdown_path = tmp_path / "design_delta_parent_drain.md"
    markdown_path.write_text(
        (
            REPO_ROOT
            / "artifacts"
            / "work"
            / "review-parity-check"
            / "design_delta_parent_drain.md"
        ).read_text(encoding="utf-8").replace(
            "- Primary surface: `yaml`",
            "- Primary surface: `orc`",
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            drain_summary_path=_aligned_reference_family_drain_summary(tmp_path),
            parity_report_markdown_path=markdown_path,
        )

    assert excinfo.value.diagnostics[0].code == "reference_family_conformance_invalid"
    assert (
        "reference_family_parity_surface_mismatch"
        in excinfo.value.diagnostics[0].message
    )


def test_design_delta_parent_drain_build_rejects_reference_family_invalid_parity_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parity_json_path = tmp_path / "design_delta_parent_drain.json"
    payload = json.loads(
        (
            REPO_ROOT
            / "artifacts"
            / "work"
            / "review-parity-check"
            / "design_delta_parent_drain.json"
        ).read_text(encoding="utf-8")
    )
    del payload["target_identity"]["required_family_evidence_roles"]
    parity_json_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            drain_summary_path=_aligned_reference_family_drain_summary(tmp_path),
            parity_report_json_path=parity_json_path,
        )

    assert excinfo.value.diagnostics[0].code == "reference_family_conformance_invalid"
    assert "reference_family_parity_report_invalid" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_build_rejects_reference_family_malformed_parity_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markdown_path = tmp_path / "design_delta_parent_drain.md"
    markdown_path.write_text(
        (
            REPO_ROOT
            / "artifacts"
            / "work"
            / "review-parity-check"
            / "design_delta_parent_drain.md"
        ).read_text(encoding="utf-8").replace(
            "- Promotion eligible: `false`\n",
            "",
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            drain_summary_path=_aligned_reference_family_drain_summary(tmp_path),
            parity_report_markdown_path=markdown_path,
        )

    assert excinfo.value.diagnostics[0].code == "reference_family_conformance_invalid"
    assert "reference_family_parity_report_invalid" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_build_rejects_parent_drain_census_alignment_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command_boundaries_payload = json.loads(
        (
            DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.commands.json"
        ).read_text(encoding="utf-8")
    )
    command_boundaries_payload.pop("validate_review_findings_v1")
    command_boundaries_path = tmp_path / "design_delta_parent_drain.commands.json"
    command_boundaries_path.write_text(
        json.dumps(command_boundaries_payload, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            command_boundaries_path=command_boundaries_path,
        )

    assert excinfo.value.diagnostics[0].code == "parent_drain_census_invalid"
    assert (
        "parent_drain_census_command_boundary_missing"
        in excinfo.value.diagnostics[0].message
    )


def test_design_delta_parent_drain_resume_plumbing_retirement_report_records_census_fingerprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
    )

    payload = json.loads(
        result.artifact_paths["resume_plumbing_retirement_report"].read_text(
            encoding="utf-8"
        )
    )
    assert payload["source_census"]["path"].endswith(
        "design_delta_parent_drain.value_flow_census.json"
    )
    assert payload["source_census"]["fingerprint"].startswith("sha256:")


def test_design_delta_parent_drain_checked_inputs_keep_work_item_run_state_retirement_row() -> None:
    census = _load_design_delta_value_flow_census()
    registry = _load_design_delta_boundary_authority_registry()

    assert any(
        row["row_id"] == "work_item.loop.run_state_path"
        for row in census["rows"]
    )
    assert any(
        row["workflow_name"] == "lisp_frontend_design_delta/work_item::run-work-item"
        and row["field_name"] == "run_state_path"
        for row in registry["rows"]
    )

def test_design_delta_parent_drain_boundary_authority_report_keeps_live_work_item_run_state_bridge_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    payload = json.loads(
        result.artifact_paths["boundary_authority_report"].read_text(encoding="utf-8")
    )
    workflow_row = next(
        row
        for row in payload["workflows"]
        if row["workflow_name"] == "lisp_frontend_design_delta/work_item::run-work-item"
    )

    assert "run_state_path" in workflow_row["compatibility_bridge"]


def test_design_delta_parent_drain_build_source_map_finalizer_compat_retirement_removes_helpers_from_ordinary_work_item_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    workflow = source_map["workflows"]["lisp_frontend_design_delta/work_item::run-work-item"]
    retired_helpers = (
        "project-selected-item-compat",
        "project-plan-approved-compat",
        "project-plan-blocked-compat",
        "project-completed-implementation-compat",
        "project-blocked-implementation-compat",
    )
    executable_names = [
        str(node.get("presentation_name", ""))
        for node in workflow.get("executable_nodes", [])
    ]
    generated_paths = json.dumps(workflow.get("generated_internal_inputs", {}), sort_keys=True)

    for helper_name in retired_helpers:
        assert all(helper_name not in name for name in executable_names)
        assert helper_name not in generated_paths


def test_design_delta_parent_drain_resume_plumbing_retirement_report_records_work_item_row_as_checked_compatibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
    )

    payload = json.loads(
        result.artifact_paths["resume_plumbing_retirement_report"].read_text(
            encoding="utf-8"
        )
    )
    decision = next(
        row
        for row in payload["decisions"]
        if row["row_id"] == "work_item.loop.run_state_path"
    )
    assert decision["decision"] == "KEPT_COMPATIBILITY"
    assert decision["observed_locations"] == []
    assert payload["manifest"]["path"].endswith(
        "design_delta_parent_drain.resume_plumbing_retirement.json"
    )
    assert payload["manifest"]["fingerprint"].startswith("sha256:")


def test_design_delta_parent_drain_resume_plumbing_retirement_report_records_drain_run_state_bridge_as_checked_compatibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
    )

    payload = json.loads(
        result.artifact_paths["resume_plumbing_retirement_report"].read_text(
            encoding="utf-8"
        )
    )
    decision = next(
        row
        for row in payload["decisions"]
        if row["row_id"] == "transitions.resource.drain_run_state"
    )

    assert decision["decision"] == "KEPT_COMPATIBILITY"
    assert decision["observed_locations"] == ["resource_bridge_backing"]
    assert payload["manifest"]["path"].endswith(
        "design_delta_parent_drain.resume_plumbing_retirement.json"
    )
    assert payload["manifest"]["fingerprint"].startswith("sha256:")


def test_design_delta_parent_drain_resume_plumbing_retirement_rejects_checked_manifest_fingerprint_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mismatched_manifest = _aligned_design_delta_resume_plumbing_retirement_manifest()
    mismatched_manifest["source_census"]["fingerprint"] = "sha256:deadbeef"
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            resume_plumbing_retirement_manifest_payload=mismatched_manifest,
        )

    assert excinfo.value.diagnostics[0].code == "resume_plumbing_retirement_invalid"
    assert "resume_plumbing_retirement_census_fingerprint_mismatch" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_resume_plumbing_retirement_retained_work_item_public_boundary_exposure_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resume = importlib.import_module(
        "orchestrator.workflow_lisp.resume_plumbing_retirement"
    )
    original = resume.normalize_resume_plumbing_retirement_compiled_rows
    original_retirement_diagnostics = resume._retirement_evidence_diagnostics

    def _mutated(*args, **kwargs):
        rows = original(*args, **kwargs)
        rows["work_item.loop.run_state_path"] = {
            "row_id": "work_item.loop.run_state_path",
            "workflow_surface": "lisp_frontend_design_delta/work_item::run-work-item",
            "symbol_or_field": "run_state_path",
            "source_kind": "loop_state_field",
            "boundary_authority_class": "public_authored",
            "observed_locations": ["public_boundary"],
            "semantic_authority_source": "typed_runtime_resource",
        }
        return rows

    monkeypatch.setattr(
        resume,
        "normalize_resume_plumbing_retirement_compiled_rows",
        _mutated,
    )
    monkeypatch.setattr(
        resume,
        "_retirement_evidence_diagnostics",
        lambda row, **kwargs: []
        if row.get("row_id") == "drain.loop.run_state_path"
        else original_retirement_diagnostics(row, **kwargs),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
        )
    assert excinfo.value.diagnostics[0].code == "resume_plumbing_retirement_invalid"
    assert "resume_plumbing_retirement_public_boundary_exposed" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_rejects_hidden_compatibility_bridge_public_boundary_fixture(
    tmp_path: Path,
) -> None:
    build = _build_module()
    serialize = getattr(build, "_serialize_workflow_boundary_projection")
    validate = getattr(
        build,
        "_validate_selected_workflow_hidden_compatibility_bridge_public_boundary",
    )
    result = _compile_linked_hidden_compatibility_bridge_public_boundary_fixture(
        tmp_path
    )
    payload = serialize(
        result,
        selected_name=(
            "backlog_drain_hidden_compatibility_bridge_public_boundary_invalid::drain"
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        validate(
            payload,
            selected_name=(
                "backlog_drain_hidden_compatibility_bridge_public_boundary_invalid::drain"
            ),
            boundary_authority_registry=None,
        )

    assert excinfo.value.diagnostics[0].code == "workflow_boundary_authority_unclassified"


def test_design_delta_parent_drain_resume_plumbing_retirement_retained_work_item_loop_state_exposure_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resume = importlib.import_module(
        "orchestrator.workflow_lisp.resume_plumbing_retirement"
    )
    original = resume.normalize_resume_plumbing_retirement_compiled_rows
    original_retirement_diagnostics = resume._retirement_evidence_diagnostics

    def _mutated(*args, **kwargs):
        rows = original(*args, **kwargs)
        rows["work_item.loop.run_state_path"] = {
            "row_id": "work_item.loop.run_state_path",
            "workflow_surface": "lisp_frontend_design_delta/work_item::run-work-item",
            "symbol_or_field": "run_state_path",
            "source_kind": "loop_state_field",
            "boundary_authority_class": "compatibility_bridge",
            "observed_locations": ["loop_state_field"],
            "semantic_authority_source": "typed_runtime_resource",
        }
        return rows

    monkeypatch.setattr(
        resume,
        "normalize_resume_plumbing_retirement_compiled_rows",
        _mutated,
    )
    monkeypatch.setattr(
        resume,
        "_retirement_evidence_diagnostics",
        lambda row, **kwargs: []
        if row.get("row_id") == "drain.loop.run_state_path"
        else original_retirement_diagnostics(row, **kwargs),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
        )
    assert excinfo.value.diagnostics[0].code == "resume_plumbing_retirement_invalid"
    assert "resume_plumbing_retirement_loop_state_exposed" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_resume_plumbing_retirement_retained_work_item_call_signature_exposure_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resume = importlib.import_module(
        "orchestrator.workflow_lisp.resume_plumbing_retirement"
    )
    original = resume.normalize_resume_plumbing_retirement_compiled_rows
    original_retirement_diagnostics = resume._retirement_evidence_diagnostics

    def _mutated(*args, **kwargs):
        rows = original(*args, **kwargs)
        rows["work_item.loop.run_state_path"] = {
            "row_id": "work_item.loop.run_state_path",
            "workflow_surface": "lisp_frontend_design_delta/work_item::run-work-item",
            "symbol_or_field": "run_state_path",
            "source_kind": "loop_state_field",
            "boundary_authority_class": "compatibility_bridge",
            "observed_locations": ["call_signature"],
            "semantic_authority_source": "typed_runtime_resource",
        }
        return rows

    monkeypatch.setattr(
        resume,
        "normalize_resume_plumbing_retirement_compiled_rows",
        _mutated,
    )
    monkeypatch.setattr(
        resume,
        "_retirement_evidence_diagnostics",
        lambda row, **kwargs: []
        if row.get("row_id") == "drain.loop.run_state_path"
        else original_retirement_diagnostics(row, **kwargs),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
        )
    assert excinfo.value.diagnostics[0].code == "resume_plumbing_retirement_invalid"
    assert "resume_plumbing_retirement_call_signature_exposed" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_resume_plumbing_retirement_retained_work_item_runtime_derived_reclassification_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resume = importlib.import_module(
        "orchestrator.workflow_lisp.resume_plumbing_retirement"
    )
    original = resume.normalize_resume_plumbing_retirement_compiled_rows
    original_retirement_diagnostics = resume._retirement_evidence_diagnostics

    def _mutated(*args, **kwargs):
        rows = original(*args, **kwargs)
        rows["work_item.loop.run_state_path"] = {
            "row_id": "work_item.loop.run_state_path",
            "workflow_surface": "lisp_frontend_design_delta/work_item::run-work-item",
            "symbol_or_field": "run_state_path",
            "source_kind": "loop_state_field",
            "boundary_authority_class": "runtime_derived",
            "observed_locations": [],
            "semantic_authority_source": "typed_runtime_resource",
        }
        return rows

    monkeypatch.setattr(
        resume,
        "normalize_resume_plumbing_retirement_compiled_rows",
        _mutated,
    )
    monkeypatch.setattr(
        resume,
        "_retirement_evidence_diagnostics",
        lambda row, **kwargs: []
        if row.get("row_id") == "drain.loop.run_state_path"
        else original_retirement_diagnostics(row, **kwargs),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
        )
    assert excinfo.value.diagnostics[0].code == "resume_plumbing_retirement_invalid"
    assert "resume_plumbing_retirement_runtime_derived_reclassification" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_rejects_hidden_compatibility_bridge_reread_pointer_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resume = importlib.import_module(
        "orchestrator.workflow_lisp.resume_plumbing_retirement"
    )
    fixture_row = _load_hidden_compatibility_bridge_reread_pointer_authority_fixture()
    original = resume.normalize_resume_plumbing_retirement_compiled_rows
    original_retirement_diagnostics = resume._retirement_evidence_diagnostics

    def _mutated(*args, **kwargs):
        rows = original(*args, **kwargs)
        rows["work_item.loop.run_state_path"] = dict(fixture_row)
        return rows

    monkeypatch.setattr(
        resume,
        "normalize_resume_plumbing_retirement_compiled_rows",
        _mutated,
    )
    monkeypatch.setattr(
        resume,
        "_retirement_evidence_diagnostics",
        lambda row, **kwargs: []
        if row.get("row_id") == "drain.loop.run_state_path"
        else original_retirement_diagnostics(row, **kwargs),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
        )
    assert excinfo.value.diagnostics[0].code == "resume_plumbing_retirement_invalid"
    assert "resume_plumbing_retirement_checkpoint_used_as_authority" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_resume_plumbing_retirement_rejects_unjustified_compatibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()
    manifest_path = tmp_path / "design_delta_parent_drain.resume_plumbing_retirement.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "workflow_lisp_resume_plumbing_retirement.v1",
                "target_family": "lisp_frontend_design_delta_parent_drain",
                "source_census": {
                    "path": str(DESIGN_DELTA_VALUE_FLOW_CENSUS_PATH),
                    "fingerprint": "sha256:bad",
                },
                "decisions": [
                    {
                        "row_id": "drain.loop.run_state_path",
                        "decision": "KEPT_COMPATIBILITY",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        build,
        "DESIGN_DELTA_PARENT_DRAIN_RESUME_PLUMBING_RETIREMENT_PATH",
        manifest_path,
        raising=False,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        )
    assert excinfo.value.diagnostics[0].code == "resume_plumbing_retirement_invalid"
    assert "resume_plumbing_retirement_compatibility_unjustified" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_resume_plumbing_retirement_ignores_track_c_public_output_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
        resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
    )

    payload = json.loads(
        result.artifact_paths["resume_plumbing_retirement_report"].read_text(
            encoding="utf-8"
        )
    )
    assert all(
        row["row_id"] != "drain.output.return_run_state"
        for row in payload["decisions"]
    )


def test_design_delta_parent_drain_resume_plumbing_retirement_build_passes_checkpoint_evidence_into_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()
    resume = importlib.import_module(
        "orchestrator.workflow_lisp.resume_plumbing_retirement"
    )
    original = resume.build_resume_plumbing_retirement_report

    def _wrapped(*args, **kwargs):
        points_payload = kwargs["checkpoint_points_payload"]
        shadow_report_payload = kwargs["checkpoint_shadow_report_payload"]
        assert points_payload["schema_version"] == "workflow_lisp_lexical_checkpoint_points.v1"
        assert (
            shadow_report_payload["schema_version"]
            == "workflow_lisp_lexical_checkpoint_shadow_report.v1"
        )
        assert any(
            point.get("workflow_name")
            == "lisp_frontend_design_delta/work_item::run-work-item"
            for point in points_payload["points"]
        )
        assert any(
            "drain_runtime_owned"
            in (
                point.get("effect_boundary", {})
                .get("policy", {})
                .get("evidence_requirements", {})
                .get("workflow_call", {})
                .get("callee_workflow", "")
            )
            for point in points_payload["points"]
            if point.get("point_kind") == "effect_boundary"
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(
        resume,
        "build_resume_plumbing_retirement_report",
        _wrapped,
    )

    _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )


def test_design_delta_parent_drain_build_emits_lexical_checkpoint_default_resume_report_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    assert "lexical_checkpoint_default_resume_report" in result.artifact_paths
    assert (
        result.manifest.artifact_status["lexical_checkpoint_default_resume_report"]
        == "emitted"
    )
    payload = json.loads(
        result.artifact_paths["lexical_checkpoint_default_resume_report"].read_text(
            encoding="utf-8"
        )
    )
    assert payload["schema_version"] == "workflow_lisp_checkpoint_default_resume_report.v1"
    assert payload["route"]["default_mode"] == "LEXICAL_CHECKPOINT_DEFAULT"
    assert payload["checked_workflows"][0]["route"]["default_mode"] == "LEXICAL_CHECKPOINT_DEFAULT"
    assert payload["default_modes"][0]["mode"] == "LEXICAL_CHECKPOINT_DEFAULT"


def test_design_delta_parent_drain_default_resume_report_records_r1_to_r5_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    payload = json.loads(
        result.artifact_paths["lexical_checkpoint_default_resume_report"].read_text(
            encoding="utf-8"
        )
    )

    assert payload["evidence"]["checkpoint_points"]["schema_version"] == "workflow_lisp_lexical_checkpoint_points.v1"
    assert payload["evidence"]["checkpoint_shadow_report"]["schema_version"] == "workflow_lisp_lexical_checkpoint_shadow_report.v1"
    assert payload["evidence"]["retirement_report"]["schema_version"] == "workflow_lisp_resume_plumbing_retirement_report.v1"
    assert payload["evidence"]["restore_metadata"]["status"] == "pass"
    assert payload["evidence"]["effect_policies"]["status"] == "pass"
    assert payload["evidence"]["transition_evidence"]["status"] == "pass"
    assert payload["route"]["lowering_schema_version"] == 2
    assert payload["status"] == "pass"


def test_design_delta_parent_drain_default_resume_report_rejects_step_granular_bypass_for_eligible_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _build_module()
    original = build._serialize_lexical_checkpoint_points_for_retirement

    def _mutated(*args, **kwargs):
        payload = original(*args, **kwargs)
        payload["points"] = []
        return payload

    monkeypatch.setattr(
        build,
        "_serialize_lexical_checkpoint_points_for_retirement",
        _mutated,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_design_delta_parent_drain(
            tmp_path,
            monkeypatch,
            registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
            resume_plumbing_retirement_manifest_payload=_aligned_design_delta_resume_plumbing_retirement_manifest(),
        )

    assert excinfo.value.diagnostics[0].code == "lexical_default_resume_invalid"
    assert "lexical_default_resume_step_granular_bypass" in excinfo.value.diagnostics[0].message


def test_design_delta_parent_drain_default_resume_report_marks_live_run_state_bridges_blocked_or_historical_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    payload = json.loads(
        result.artifact_paths["lexical_checkpoint_default_resume_report"].read_text(
            encoding="utf-8"
        )
    )
    cleanup_candidates = {
        row["row_id"]: row for row in payload["cleanup_candidates"]
    }

    assert cleanup_candidates["work_item.loop.run_state_path"]["cleanup_action"] in {
        "BLOCKED",
        "KEEP_HISTORICAL_ONLY",
    }
    assert cleanup_candidates["transitions.resource.drain_run_state"]["cleanup_action"] in {
        "BLOCKED",
        "KEEP_HISTORICAL_ONLY",
    }


def test_design_delta_parent_drain_default_resume_report_keeps_track_c_rows_out_of_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    payload = json.loads(
        result.artifact_paths["lexical_checkpoint_default_resume_report"].read_text(
            encoding="utf-8"
        )
    )

    assert all(
        row["row_id"] != "drain.output.return_run_state"
        for row in payload["cleanup_candidates"]
    )


def test_design_delta_parent_drain_build_emits_transition_authoring_report_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _build_design_delta_parent_drain(
        tmp_path,
        monkeypatch,
        registry_payload=_aligned_design_delta_boundary_authority_registry(tmp_path),
    )

    assert "transition_authoring_report" in result.artifact_paths
    assert result.manifest.artifact_status["transition_authoring_report"] == "emitted"
    payload = json.loads(
        result.artifact_paths["transition_authoring_report"].read_text(
            encoding="utf-8"
        )
    )
    assert payload["schema_version"] == "workflow_lisp_transition_authoring_report.v1"
    assert payload["workflow_family"] == "design_delta_parent_drain"
    assert payload["status"] == "pass"
    assert {row["module_name"] for row in payload["compiled_origins"]} == {
        "lisp_frontend_design_delta/transitions",
        "std/resource",
    }
    assert any(
        row["matched_row_id"] == "low_level.record_design_gap_progress"
        and row["workflow_name"]
        == "lisp_frontend_design_delta/stdlib_adapters::draft-design-gap-stdlib"
        for row in payload["compiled_origins"]
    )
    assert payload["ordinary_body_violations"] == []
    assert payload["extra_origins"] == []


def test_build_emits_lexical_checkpoint_points_artifact(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)

    points_path = result.artifact_paths["lexical_checkpoint_points"]
    payload = json.loads(points_path.read_text(encoding="utf-8"))

    assert points_path.name == "lexical_checkpoint_points.json"
    assert payload["schema_version"] == "workflow_lisp_lexical_checkpoint_points.v1"
    assert payload["checkpoint_schema_version"] == "workflow_lisp_lexical_checkpoint.v1"
    assert payload["program_identity"]["source_module_digest"].startswith("sha256:")
    assert payload["program_identity"]["executable_ir_digest"].startswith("sha256:")
    assert payload["program_identity"]["semantic_ir_digest"].startswith("sha256:")
    assert payload["points"]
    assert all(
        point["wcc_identity"]["node_id_digest"].startswith("sha256:")
        and point["wcc_identity"]["scope_id_digest"].startswith("sha256:")
        and point["binding_schema"]["schema_digest"].startswith("sha256:")
        and point["storage"]["semantic_role"] == "lexical_checkpoint_record"
        for point in payload["points"]
    )


def test_build_emits_compile_time_lexical_checkpoint_shadow_report(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)

    report_path = result.artifact_paths["lexical_checkpoint_shadow_report"]
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    points_payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))

    assert report_path.name == "lexical_checkpoint_shadow_report.json"
    assert payload["schema_version"] == "workflow_lisp_lexical_checkpoint_shadow_report.v1"
    assert payload["status"] == "pass"
    assert payload["checked_points"] == len(points_payload["points"])
    assert payload["checked_records"] == 0
    assert payload["diagnostics"] == []


def test_build_manifest_records_checkpoint_artifact_paths(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)

    assert result.manifest.artifact_paths["lexical_checkpoint_points"].endswith("/lexical_checkpoint_points.json")
    assert result.manifest.artifact_paths["lexical_checkpoint_shadow_report"].endswith(
        "/lexical_checkpoint_shadow_report.json"
    )


def test_checkpoint_points_artifact_is_route_neutral_in_public_fields(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)

    payload = result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8")
    assert "wcc_m4" not in payload
    assert "lowering_route" not in payload
    assert "wcc-node:" not in payload


def test_runtime_plan_artifact_keeps_lexical_checkpoint_details_route_neutral(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)

    payload = result.artifact_paths["runtime_plan"].read_text(encoding="utf-8")
    assert "runtime_program_identity" not in payload
    assert "wcc_m4" not in payload
    assert "wcc-node:" not in payload


def test_build_emits_restore_eligibility_details_in_lexical_checkpoint_points_artifact(tmp_path: Path) -> None:
    result = _build_lexical_restore_fixture(tmp_path)
    payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))
    restore_labels = {
        label
        for point in payload["points"]
        for label in point.get("restore", {}).get("eligibility", ())
    }

    assert {"pure_binding", "let_continuation", "match_branch", "loop_frame"} <= restore_labels
    assert any(point.get("restore", {}).get("binding_descriptor_digests") for point in payload["points"])
    assert any(point.get("restore", {}).get("proof_descriptor_digests") for point in payload["points"])
    assert any(point.get("restore", {}).get("loop_frame_descriptor_digest") for point in payload["points"])
    assert all("binding_descriptors" not in point.get("restore", {}) for point in payload["points"])
    assert all("proof_descriptors" not in point.get("restore", {}) for point in payload["points"])
    assert all("loop_frame_descriptor" not in point.get("restore", {}) for point in payload["points"])
    assert "wcc-node:" not in json.dumps(payload, sort_keys=True)
    assert "wcc_m4" not in json.dumps(payload, sort_keys=True)


def test_checkpoint_points_artifact_rejects_missing_executable_node_linkage(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)
    payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))
    payload["points"][0]["executable_identity"]["node_id"] = "missing.node"
    result.artifact_paths["lexical_checkpoint_points"].write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    build = _build_module()
    with pytest.raises(Exception):
        build._validate_lexical_checkpoint_artifacts(
            payload,
            semantic_ir_payload=json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8")),
            runtime_plan_payload=json.loads(result.artifact_paths["runtime_plan"].read_text(encoding="utf-8")),
            source_map_payload=json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8")),
        )


def test_checkpoint_points_artifact_rejects_missing_source_map_origin(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)
    payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))
    payload["points"][0]["source_lineage"]["origin_key"] = "source:missing"

    build = _build_module()
    with pytest.raises(Exception):
        build._validate_lexical_checkpoint_artifacts(
            payload,
            semantic_ir_payload=json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8")),
            runtime_plan_payload=json.loads(result.artifact_paths["runtime_plan"].read_text(encoding="utf-8")),
            source_map_payload=json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8")),
        )


def test_checkpoint_points_artifact_rejects_program_identity_drift(tmp_path: Path) -> None:
    result = _build_lexical_checkpoint_fixture(tmp_path)
    payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))
    payload["program_identity"]["executable_ir_digest"] = "sha256:drifted"

    build = _build_module()
    with pytest.raises(Exception):
        build._validate_lexical_checkpoint_artifacts(
            payload,
            semantic_ir_payload=json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8")),
            runtime_plan_payload=json.loads(result.artifact_paths["runtime_plan"].read_text(encoding="utf-8")),
            source_map_payload=json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8")),
        )


def test_build_emits_r3_policy_summaries_for_lexical_checkpoint_effect_boundaries(tmp_path: Path) -> None:
    result = _build_lexical_policy_fixture(tmp_path)
    payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))

    effect_policies = {
        point["effect_boundary"]["effect_kind"]: point["effect_boundary"]["policy"]
        for point in payload["points"]
        if point["point_kind"] == "effect_boundary"
    }

    assert set(effect_policies) >= {
        "pure_projection",
        "provider",
        "command",
        "call",
        "materialize_view",
        "resource_transition",
    }
    assert all(policy["schema_version"] == "workflow_lisp_effect_resume_policy.v1" for policy in effect_policies.values())
    assert all("runtime_program_identity" not in json.dumps(policy, sort_keys=True) for policy in effect_policies.values())
    assert all("wcc-node:" not in json.dumps(policy, sort_keys=True) for policy in effect_policies.values())


def test_lexical_checkpoint_points_artifact_rejects_missing_r3_policy_envelope(tmp_path: Path) -> None:
    result = _build_lexical_policy_fixture(tmp_path)
    payload = json.loads(result.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))
    effect_boundary_point = next(point for point in payload["points"] if point["point_kind"] == "effect_boundary")
    effect_boundary_point["effect_boundary"].pop("policy", None)

    build = _build_module()
    with pytest.raises(Exception):
        build._validate_lexical_checkpoint_artifacts(
            payload,
            semantic_ir_payload=json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8")),
            runtime_plan_payload=json.loads(result.artifact_paths["runtime_plan"].read_text(encoding="utf-8")),
            source_map_payload=json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8")),
        )
