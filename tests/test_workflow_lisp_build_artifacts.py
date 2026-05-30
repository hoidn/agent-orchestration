from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.workflow.loaded_bundle import workflow_managed_write_root_inputs
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
CLI_FIXTURES = FIXTURES / "cli"
ENTRYPOINT = FIXTURES / "modules" / "valid" / "imported_bundle_mix" / "neurips" / "entry.orc"
SOURCE_ROOT = FIXTURES / "modules" / "valid" / "imported_bundle_mix"


def _build_module():
    return importlib.import_module("orchestrator.workflow_lisp.build")


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


def test_build_accepts_compiled_imported_bundle_manifests(tmp_path: Path) -> None:
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
    assert workflow_managed_write_root_inputs(result.imported_workflow_bundles[0].bundle) == (
        "__write_root__compiled_selector_selector_run__result__result_bundle",
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
            "prompt externs manifest entries must map non-empty string names to string values",
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
    assert result.artifact_paths["core_workflow_ast"].name == "core_workflow_ast.json"
    assert result.artifact_paths["semantic_ir"].name == "semantic_ir.json"
    assert result.artifact_paths["runtime_plan"].name == "runtime_plan.json"
    assert result.manifest.artifact_paths["runtime_plan"].endswith("/runtime_plan.json")
    assert result.manifest.artifact_status["core_workflow_ast"] == "emitted"
    assert result.manifest.artifact_status["semantic_ir"] == "emitted"


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
    runtime_plan = json.loads(result.artifact_paths["runtime_plan"].read_text(encoding="utf-8"))
    semantic_ir = json.loads(result.artifact_paths["semantic_ir"].read_text(encoding="utf-8"))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    selected_workflow = result.validated_bundle.surface.name
    runtime_plan_node_ids = set(runtime_plan["nodes"])
    source_map_node_ids = {
        node["node_id"]
        for node in source_map["workflows"][selected_workflow]["executable_nodes"]
    }

    assert runtime_plan["schema_version"] == "workflow_runtime_plan.v1"
    assert runtime_plan["workflow_name"] == selected_workflow
    assert semantic_ir["schema_version"] == "workflow_semantic_ir.v1"
    assert semantic_ir["workflows"][selected_workflow]["workflow_name"] == selected_workflow
    assert json.loads(result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8"))["schema_version"] == (
        "core_workflow_ast.v1"
    )
    assert runtime_plan_node_ids == source_map_node_ids
    assert result.manifest.artifact_paths["runtime_plan"].endswith("/runtime_plan.json")
    assert result.manifest.artifact_status["core_workflow_ast"] == "emitted"
    assert result.manifest.artifact_status["semantic_ir"] == "emitted"


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
            "core_workflow_ast": [None],
            "semantic_ir": ["exports/semantic_ir.snapshot.json"],
            "source_map": [None],
        },
        cwd=tmp_path,
        source_path=ENTRYPOINT,
    )

    assert requests["core_workflow_ast"].destination == (tmp_path / "core_workflow_ast.json").resolve()
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
            "core_workflow_ast": ["exports/core/core_workflow_ast.json"],
            "semantic_ir": ["exports/semantic/semantic_ir.json"],
            "source_map": ["exports/maps/source_map.json"],
            "expanded_debug_yaml": ["exports/debug/expanded.debug.yaml"],
        },
        cwd=tmp_path,
        source_path=ENTRYPOINT,
    )

    exported = emit_exports(result=result, export_requests=export_requests)

    assert exported["core_workflow_ast"].read_bytes() == result.artifact_paths["core_workflow_ast"].read_bytes()
    assert exported["semantic_ir"].read_bytes() == result.artifact_paths["semantic_ir"].read_bytes()
    assert exported["source_map"].read_bytes() == result.artifact_paths["source_map"].read_bytes()
    assert exported["expanded_debug_yaml"].read_bytes() == result.artifact_paths["expanded_debug_yaml"].read_bytes()
    assert result.manifest.artifact_paths == original_manifest_paths
    assert dict(result.artifact_paths) == original_artifact_paths


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
