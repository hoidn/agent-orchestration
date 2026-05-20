from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


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
        "source_map.json",
        "workflow_boundary_projection.json",
        "diagnostics.json",
    }

    assert expected_artifacts.issubset({path.name for path in result.artifact_paths.values()})
    assert result.manifest.artifact_status["core_workflow_ast"] == "deferred_shared_contract"
    assert result.manifest.artifact_status["semantic_ir"] == "deferred_shared_contract"


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


def test_source_map_covers_generated_steps_inputs_outputs_and_paths(tmp_path: Path) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    result = build_frontend_bundle(_build_request(tmp_path))
    source_map = json.loads(result.artifact_paths["source_map"].read_text(encoding="utf-8"))
    boundary_projection = json.loads(
        result.artifact_paths["workflow_boundary_projection"].read_text(encoding="utf-8")
    )

    entry_workflow = next(
        workflow
        for workflow in source_map["workflows"].values()
        if workflow["selected_entry_workflow"]
    )
    assert entry_workflow["workflow_name"] == "neurips/entry::orchestrate"
    assert entry_workflow["step_ids"]
    assert set(entry_workflow["generated_inputs"]) == {
        "input__report",
        "input__status",
        "report_path",
    }
    assert set(entry_workflow["generated_outputs"]) == {"return__report"}
    assert any(workflow["generated_paths"] for workflow in source_map["workflows"].values())
    assert "contract_definition" not in json.dumps(source_map, sort_keys=True)
    assert boundary_projection["schema_version"] == "workflow_lisp_boundary_projection.v1"
    assert boundary_projection["entry_workflow"] == "neurips/entry::orchestrate"
    projection_entry = next(
        workflow
        for workflow in boundary_projection["workflows"]
        if workflow["workflow_name"] == "neurips/entry::orchestrate"
    )
    assert projection_entry["params"] == [
        {"name": "input", "type_kind": "record"},
        {"name": "report_path", "type_kind": "relpath"},
    ]
    assert projection_entry["return_kind"] == "record"
    assert [field["generated_name"] for field in projection_entry["flattened_inputs"]] == [
        "input__report",
        "input__status",
        "report_path",
    ]
    assert [field["generated_name"] for field in projection_entry["flattened_outputs"]] == ["return__report"]
    assert projection_entry["generated_internal_inputs"] == []


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

    assert set(source_map["workflows"]) >= {"pkg/entry::run", "pkg/helper::run"}
    assert source_map["workflows"]["pkg/entry::run"]["selected_entry_workflow"] is True
    assert source_map["workflows"]["pkg/helper::run"]["selected_entry_workflow"] is False
