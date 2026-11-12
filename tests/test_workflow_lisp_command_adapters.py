from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.command_boundaries import (
    CommandBoundaryEnvironment,
    build_command_boundary_environment,
)
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import CommandResultExpr, elaborate_expression
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.test_cli_run_output import cli


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_FIXTURE = FIXTURES / "valid" / "certified_adapter_call.orc"
INVALID_MISSING_INPUT_FIXTURE = FIXTURES / "invalid" / "certified_adapter_missing_input.orc"
INVALID_EXTRA_INPUT_FIXTURE = FIXTURES / "invalid" / "certified_adapter_extra_input.orc"
INVALID_TYPE_MISMATCH_FIXTURE = FIXTURES / "invalid" / "certified_adapter_type_mismatch.orc"


def _validated_command_boundaries(
    payload: dict[str, object],
    *,
    manifest_path: Path | None = None,
) -> CommandBoundaryEnvironment:
    return build_command_boundary_environment(
        _parse_command_boundaries_manifest(
            payload,
            manifest_path=manifest_path,
        )
    )


def _design_delta_retirement_row(
    *,
    kind: str,
    name: str,
    stable_command: list[str] | None = None,
    behavior_class: str | None = None,
    retirement_class: str = "typed_projection",
    retirement_label: str = "retire_to_projection",
    replacement_surface: str = "typed projection",
    bridge_owner: str = "workflow-lisp",
    expiry_condition: str = "g2-typed-projection",
    evidence_refs: list[str] | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "kind": kind,
        "stable_command": stable_command or ["python", f"scripts/{name}.py"],
        "retirement_class": retirement_class,
        "retirement_label": retirement_label,
        "replacement_surface": replacement_surface,
        "bridge_owner": bridge_owner,
        "expiry_condition": expiry_condition,
        "evidence_refs": evidence_refs or [f"{name}_ok"],
    }
    if kind == "certified_adapter":
        row.update(
            {
                "input_contract": {"type": "object"},
                "output_type_name": "SelectionAction",
                "effects": ["structured_result"],
                "path_safety": {"kind": "workspace_relpath"},
                "source_map_behavior": "step",
                "fixture_ids": [f"{name}_ok"],
                "negative_fixture_ids": [f"{name}_bad"],
                "behavior_class": behavior_class or "structured_result",
                "input_signature": [
                    {
                        "name": "selection_status",
                        "type_name": "SelectionStatus",
                        "required": True,
                        "transport_key": "selection_status",
                    }
                ],
                "artifact_contracts": [f"{name}_bundle"],
                "state_writes": [],
                "error_codes": [f"{name}_invalid"],
                "owner_module": "lisp_frontend_design_delta/drain",
                "replacement_path": "typed projection",
                "invocation_protocol": "json_object_positional_arg",
            }
        )
    return row


def _expression_syntax(source: str) -> SyntaxNode:
    parse_tree = read_sexpr_text(source, source_path="inline_command_adapter.orc")
    assert len(parse_tree.items) == 1
    datum = parse_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_command_adapter.orc",
        form_path=("workflow-lisp", "command-adapter-test"),
    )


def test_design_delta_g0_helper_without_retirement_metadata_is_rejected() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_command_boundary_environment(
            {
                "validate_review_findings_v1": ExternalToolBinding(
                    name="validate_review_findings_v1",
                    stable_command=(
                        "python",
                        "-m",
                        "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
                    ),
                )
            }
        )

    assert excinfo.value.diagnostics[0].code == "command_adapter_missing_contract"


def test_design_delta_parent_drain_manifest_rejects_unknown_retirement_class() -> None:
    payload = {
        "project_lisp_frontend_selector_action": _design_delta_retirement_row(
            kind="certified_adapter",
            name="project_lisp_frontend_selector_action",
            retirement_class="not_a_real_class",
        )
    }

    with pytest.raises(LispFrontendCompileError):
        _validated_command_boundaries(payload)


def test_design_delta_parent_drain_manifest_rejects_unknown_retirement_label() -> None:
    payload = {
        "project_lisp_frontend_selector_action": _design_delta_retirement_row(
            kind="certified_adapter",
            name="project_lisp_frontend_selector_action",
            retirement_label="not_a_real_label",
        )
    }

    with pytest.raises(LispFrontendCompileError):
        _validated_command_boundaries(payload)


def test_design_delta_parent_drain_certified_adapter_requires_full_retirement_metadata() -> None:
    payload = {
        "project_lisp_frontend_selector_action": _design_delta_retirement_row(
            kind="certified_adapter",
            name="project_lisp_frontend_selector_action",
        )
    }
    payload["project_lisp_frontend_selector_action"].pop("expiry_condition")

    with pytest.raises(LispFrontendCompileError):
        _validated_command_boundaries(payload)


def test_design_delta_parent_drain_external_tool_requires_full_retirement_metadata() -> None:
    payload = {
        "run_neurips_backlog_checks": _design_delta_retirement_row(
            kind="external_tool",
            name="run_neurips_backlog_checks",
            retirement_class="genuine_system",
            retirement_label="keep_certified_system",
            replacement_surface="certified external tool",
        )
    }
    payload["run_neurips_backlog_checks"].pop("evidence_refs")

    with pytest.raises(LispFrontendCompileError):
        _validated_command_boundaries(payload)


def test_design_delta_parent_drain_validate_review_findings_requires_full_retirement_metadata() -> None:
    payload = {
        "validate_review_findings_v1": {
            "kind": "external_tool",
            "stable_command": [
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
            ],
        }
    }

    with pytest.raises(LispFrontendCompileError):
        _validated_command_boundaries(payload)


def test_command_result_adapter_requires_full_promoted_metadata(tmp_path: Path) -> None:
    incomplete_boundaries = _parse_command_boundaries_manifest(
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
                "owner_module": "std/phase",
                "invocation_protocol": "json_object_positional_arg",
            }
        },
        manifest_path=None,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            VALID_FIXTURE,
            command_boundaries=incomplete_boundaries,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "command_adapter_missing_contract"


def test_command_result_adapter_elaboration_accepts_adapter_and_inputs() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            """
            (command-result normalize_result
              :adapter normalize_result
              :inputs
                ((execution_report completed.execution_report)
                 (review_report approved.review_report))
              :returns ImplementationSummary)
            """
        ),
        bound_names=frozenset({"completed", "approved"}),
    )

    assert isinstance(expr, CommandResultExpr)
    assert expr.adapter_name == "normalize_result"
    assert expr.argv == ()
    assert tuple(name for name, _ in expr.adapter_inputs) == (
        "execution_report",
        "review_report",
    )


def test_command_result_adapter_requires_exclusive_adapter_mode() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax(
                """
                (command-result normalize_result
                  :argv ("python" "scripts/normalize_result.py" report_path)
                  :adapter normalize_result
                  :inputs ((execution_report report_path))
                  :returns ImplementationSummary)
                """
            ),
            bound_names=frozenset({"report_path"}),
        )

    assert excinfo.value.diagnostics[0].code == "command_result_adapter_invalid"


def test_command_result_adapter_accepts_recursive_record_input(tmp_path: Path) -> None:
    path = tmp_path / "certified_adapter_non_projectable.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.40")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord Wrapper",
                "    (payload WorkReport))",
                "  (defrecord ApprovedResult",
                "    (review_report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow normalize-summary",
                "    ((completed Wrapper)",
                "     (approved ApprovedResult))",
                "    -> ImplementationSummary",
                "    (command-result wrap_result",
                "      :adapter wrap_result",
                "      :inputs",
                "        ((completed completed)",
                "         (review_report approved.review_report))",
                "      :returns ImplementationSummary)))",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        command_boundaries=_parse_command_boundaries_manifest(
            {
                "wrap_result": {
                    "kind": "certified_adapter",
                    "stable_command": ["python", "scripts/wrap_result.py"],
                    "input_contract": {"type": "object"},
                    "output_type_name": "ImplementationSummary",
                    "effects": ["structured_result"],
                    "path_safety": {"kind": "workspace_relpath"},
                    "source_map_behavior": "step",
                    "fixture_ids": ["wrap_result_ok"],
                    "negative_fixture_ids": ["wrap_result_bad"],
                    "behavior_class": "structured_result",
                    "input_signature": [
                        {
                            "name": "completed",
                            "type_name": "Wrapper",
                            "required": True,
                            "transport_key": "completed",
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
                    "error_codes": ["wrap_result_invalid_payload"],
                    "owner_module": "std/phase",
                    "replacement_path": None,
                    "invocation_protocol": "json_object_positional_arg",
                }
            },
            manifest_path=None,
        ),
        validate_shared=False,
        workspace_root=tmp_path,
    )

    typed = result.typed_workflows[0]
    assert typed.typed_body.type_ref.name.endswith("ImplementationSummary")
    completed = dict(typed.signature.params)["completed"]
    assert completed.name.endswith("Wrapper")
    assert completed.field_types["payload"].name.endswith("WorkReport")


@pytest.mark.parametrize("body,code", [
    ('(command-result emit :returns String)', "command_adapter_missing_contract"),
    ('(command-result emit :inputs () :returns String)', "command_adapter_missing_contract"),
    ('(command-result emit :argv () :returns String)', "command_result_argv_invalid"),
    ('(command-result emit :argv () :inputs () :returns String)', "command_result_argv_invalid"),
    ('(command-result emit :inputs ())', "frontend_parse_error"),
])
def test_omitted_command_argv_preserves_refusals(tmp_path, body, code):
    from tests.test_workflow_lisp_command_input_documents import _compile_current_source, _source

    with pytest.raises(LispFrontendCompileError) as caught:
        _compile_current_source(tmp_path, source=_source(body), commands={})
    assert caught.value.diagnostics[0].code == code


@pytest.mark.parametrize("stable,code", [
    ((), "command_adapter_missing_contract"),
    (("python", ""), "command_adapter_missing_contract"),
    (("python", "-c", "print(1)"), "inline_python_command_in_workflow"),
    (("sh", "-c", "true"), "inline_shell_command_in_workflow"),
    (("sh -c true",), "command_result_argv_invalid"),
])
def test_omitted_command_argv_uses_existing_boundary_checks(tmp_path, stable, code):
    from tests.test_workflow_lisp_command_input_documents import _compile_current_source, _source

    with pytest.raises(LispFrontendCompileError) as caught:
        _compile_current_source(tmp_path, source=_source('(command-result emit :returns String)'),
            commands={"emit": ExternalToolBinding(name="emit", stable_command=stable)})
    assert caught.value.diagnostics[0].code == code


def test_omitted_command_argv_keeps_hidden_effect_refusal(tmp_path):
    path = tmp_path / "hidden.orc"
    source = (FIXTURES / "invalid" / "macro_hidden_command_effect.orc").read_text()
    path.write_text(source.replace(':argv ("python" "scripts/run_checks.py" report_path)', ''))
    with pytest.raises(LispFrontendCompileError) as caught:
        compile_stage3_module(path, validate_shared=False, workspace_root=tmp_path,
            command_boundaries={"run_checks": ExternalToolBinding(name="run_checks",
                stable_command=("python", "scripts/run_checks.py"))})
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "macro_hidden_effect"
    assert diagnostic.expansion_stack


MOVE_SOURCE = """(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defrecord Moved (item String))
  (defworkflow run ((item String)) -> Moved
    (command-result move :adapter move :inputs ((item item)) :returns Moved)))
"""


def _move_adapter(**extra: object) -> dict[str, object]:
    return {
        "kind": "certified_adapter",
        "stable_command": ["python", "move.py"],
        "closure": [],
        "input_contract": {"type": "object"},
        "output_type_name": "Moved",
        "effects": ["structured_result"],
        "path_safety": {"kind": "workspace_relpath"},
        "source_map_behavior": "step",
        "fixture_ids": ["move_ok"],
        "negative_fixture_ids": ["move_bad"],
        "input_signature": [
            {"name": "item", "type_name": "String", "required": True, "transport_key": "item"}
        ],
        "behavior_class": "structured_result",
        "artifact_contracts": ["moved"],
        "state_writes": [],
        "error_codes": ["move_invalid"],
        "owner_module": "main",
        "replacement_path": None,
        "invocation_protocol": "json_object_positional_arg",
        **extra,
    }


def _compile_move(tmp_path: Path, adapter: dict[str, object]):
    (tmp_path / "main.orc").write_text(MOVE_SOURCE, encoding="utf-8")
    (tmp_path / "commands.json").write_text(json.dumps({"move": adapter}), encoding="utf-8")
    return cli(tmp_path, "compile", "main.orc", "--command-boundaries-file", "commands.json")


def test_move_adapter_without_resource_effects_compiles(tmp_path: Path) -> None:
    result = _compile_move(tmp_path, _move_adapter())

    assert result.returncode == 0, result.stderr


def test_certified_adapter_declaring_resource_movement_is_refused(tmp_path: Path) -> None:
    result = _compile_move(
        tmp_path, _move_adapter(effects=["resource_transition", "ledger_update"])
    )

    assert (result.returncode, "[resource_move_without_transition]" in result.stderr) == (2, True), result.stderr


def test_manifest_transition_binding_is_refused(tmp_path: Path) -> None:
    binding = {
        "transition_name": "t",
        "resource_kind": "r",
        "contract_role": "migration_backend",
        "backend_selector": "move",
    }

    result = _compile_move(tmp_path, _move_adapter(transition_binding=binding))

    lines = [line for line in result.stderr.splitlines() if "[command_adapter_missing_contract]" in line]
    assert (result.returncode, len(lines), "`transition_binding`" in "".join(lines)) == (2, 1, True), result.stderr
