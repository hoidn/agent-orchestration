from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from orchestrator.workflow.prompt_fragment_contract import (
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2,
    CompilerPromptFragmentContract,
    CompilerPromptFragmentContractV2,
    CompilerPromptFragmentOutputPosition,
    CompilerPromptFragmentRenderedSlot,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
CLI_FIXTURES = FIXTURES / "cli"
DESIGN_DELTA_MIGRATION_INPUTS = (
    REPO_ROOT / "workflows" / "examples" / "inputs" / "workflow_lisp_migrations"
)
# This checked-in candidate remains the authoritative proof source for the
# imported-child prerequisite until the shipping library module lands its
# separate parent-callable `run-work-item` export.
ENTRYPOINT = FIXTURES / "modules" / "valid" / "imported_bundle_mix" / "neurips" / "entry.orc"
SOURCE_ROOT = FIXTURES / "modules" / "valid" / "imported_bundle_mix"
IMPORTED_STDLIB_HELPER_ROOT = FIXTURES / "modules" / "valid" / "imported_stdlib_macro_payload_helper_composition"
IMPORTED_STDLIB_HELPER_ENTRY = (
    IMPORTED_STDLIB_HELPER_ROOT / "imported_stdlib_macro_payload_helper_composition" / "entry.orc"
)
PURE_EXPR_SELECTOR_FIXTURE = FIXTURES / "valid" / "pure_expr_selector_action_projection.orc"
MATERIALIZE_VIEW_ALLOCATED_TARGET_FIXTURE = FIXTURES / "valid" / "materialize_view_allocated_target.orc"
LEXICAL_CHECKPOINT_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_shadow_points.orc"
LEXICAL_POLICY_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_effect_policies.orc"
LEXICAL_RESTORE_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_restore_regions.orc"
PROCEDURE_IDENTITY_FIXTURE = FIXTURES / "valid" / "procedure_lowering_identity_modes.orc"
RUNTIME_CLOSURE_MARKERS = (
    "workflow_lisp_runtime_closure",
    "closure_families",
    "InvokeClosure",
    "Closure[",
    "runtime_closure",
)


def _persisted_fragment_contracts():
    q1_slot = CompilerPromptFragmentRenderedSlot(
        name="message",
        kind="text",
        static_type={"kind": "primitive", "name": "String"},
        renderer_id="raw-utf8-string",
        value_source={
            "kind": "typed_binding_ref",
            "binding": {"ref": "inputs.message"},
        },
        placeholder_ordinals=(0,),
    )
    q1 = CompilerPromptFragmentContract(
        schema_version=COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
        template_utf8="{message}",
        rendered_slots=(q1_slot,),
        compiled_prompt_fragment_identity="sha256:" + "1" * 64,
    )
    path_slots = tuple(
        CompilerPromptFragmentRenderedSlot(
            name=name,
            kind="path",
            static_type={
                "kind": "path",
                "must_exist_target": False,
                "name": "ReportPath",
                "under": "artifacts",
            },
            renderer_id="posix-path-line",
            value_source={
                "kind": "typed_binding_ref",
                "binding": {"ref": f"inputs.{name}"},
            },
            placeholder_ordinals=(index,),
        )
        for index, name in enumerate(("first", "second"))
    )
    expected_outputs = tuple(
        {
            "name": name,
            "path": f"${{inputs.{name}}}",
            "type": "string",
            "required": True,
        }
        for name in ("first", "second")
    )
    q2 = CompilerPromptFragmentContractV2(
        schema_version=COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2,
        template_utf8="{first} {second}",
        rendered_slots=path_slots,
        output_positions=tuple(
            CompilerPromptFragmentOutputPosition(
                slot_name=row["name"],
                output_role="required_string_file",
                expected_output=row,
            )
            for row in expected_outputs
        ),
        compiled_prompt_fragment_identity="sha256:" + "2" * 64,
    )
    return q1, q2, expected_outputs


def _build_module():
    return importlib.import_module("orchestrator.workflow_lisp.build")


@pytest.mark.parametrize(
    ("entry", "expected_code"),
    [
        (
            {"path": "must-not-be-read.orc"},
            "imported_workflow_bundle_kind_invalid",
        ),
        (
            {"kind": "yaml", "path": "must-not-be-read.yaml"},
            "imported_workflow_bundle_kind_invalid",
        ),
        (
            {"kind": "compiled", "path": "must-not-be-read.yaml"},
            "imported_workflow_bundle_path_invalid",
        ),
    ],
    ids=("omitted-kind", "yaml-kind", "compiled-non-orc"),
)
def test_imported_bundle_manifest_rejects_non_compiled_orc_entries_before_source_read(
    tmp_path: Path,
    entry: dict[str, str],
    expected_code: str,
) -> None:
    manifest_path = tmp_path / "imported-workflows.json"
    manifest_path.write_text(
        json.dumps({"selector-run": entry}),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_module().load_imported_workflow_bundle_manifest(
            manifest_path,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == expected_code


def test_imported_bundle_manifest_accepts_case_insensitive_orc_suffix(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "selector_upper.ORC"
    source_path.write_text(
        (CLI_FIXTURES / "imported_selector.orc")
        .read_text(encoding="utf-8")
        .replace("(defmodule imported_selector)", "(defmodule selector_upper)", 1),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "imported-workflows.json"
    manifest_path.write_text(
        json.dumps(
            {
                "selector-run": {
                    "kind": "compiled",
                    "path": source_path.name,
                }
            }
        ),
        encoding="utf-8",
    )

    bindings = _build_module().load_imported_workflow_bundle_manifest(
        manifest_path,
        workspace_root=tmp_path,
    )

    assert bindings[0].workflow_name == "selector_upper::selector-run"


def test_compiled_imported_bundle_preserves_recursive_orc_workflow_imports(
    tmp_path: Path,
) -> None:
    module_root = tmp_path / "recursive"
    module_root.mkdir()
    (module_root / "types.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule recursive/types)",
                "  (export WorkReport ChecksResult ImplementationSummary)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (module_root / "child.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule recursive/child)",
                "  (import recursive/types",
                "    :only (ChecksResult ImplementationSummary WorkReport))",
                "  (export selector-child)",
                "  (defworkflow selector-child",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (record ImplementationSummary :report report_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    root_path = module_root / "root.orc"
    root_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule recursive/root)",
                "  (import recursive/types",
                "    :only (ChecksResult ImplementationSummary WorkReport))",
                "  (import recursive/child :as child :only (selector-child))",
                "  (export selector-run)",
                "  (defworkflow selector-run",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (call child.selector-child",
                "      :input input",
                "      :report_path report_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "imported-workflows.json"
    manifest_path.write_text(
        json.dumps(
            {
                "selector-run": {
                    "kind": "compiled",
                    "path": str(root_path),
                }
            }
        ),
        encoding="utf-8",
    )

    bindings = _build_module().load_imported_workflow_bundle_manifest(
        manifest_path,
        workspace_root=tmp_path,
        source_roots=(tmp_path,),
    )

    assert len(bindings) == 1
    assert bindings[0].load_status == "compiled"
    assert "recursive/child::selector-child" in bindings[0].typed_program.workflows


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
    manifest_path = tmp_path / "prompts.invalid-object.json"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_module()._load_prompt_extern_mapping(manifest_path)

    assert excinfo.value.diagnostics[0].code == "workflow_lisp_manifest_invalid"
    assert "prompt externs manifest entries" in excinfo.value.diagnostics[0].message







































































































































































































































































































































def test_json_data_keeps_plain_return_and_field_dataclasses_legacy_compatible() -> None:
    span = SourceSpan(
        start=SourcePosition(path="plain.orc", line=1, column=1, offset=0),
        end=SourcePosition(path="plain.orc", line=1, column=2, offset=1),
    )
    function_def = FunctionDef(
        name="approved",
        params=(),
        return_type_name="Bool",
        body=True,
        span=span,
        form_path=("workflow-lisp", "defun", "approved"),
    )
    field = RecordField(name="approved", type_name="Bool", span=span)

    function_payload = _build_module()._json_data(function_def)
    field_payload = _build_module()._json_data(field)

    assert function_payload["return_type_name"] == "Bool"
    assert "return_spec" not in function_payload
    assert field_payload == {
        "name": "approved",
        "type_name": "Bool",
        "span": _build_module()._json_data(span),
    }


from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.functions import FunctionDef
from orchestrator.workflow_lisp.definitions import RecordField
