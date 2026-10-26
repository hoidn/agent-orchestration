from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

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


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_FIXTURE = FIXTURES / "valid" / "certified_adapter_call.orc"
INVALID_MISSING_INPUT_FIXTURE = FIXTURES / "invalid" / "certified_adapter_missing_input.orc"
INVALID_EXTRA_INPUT_FIXTURE = FIXTURES / "invalid" / "certified_adapter_extra_input.orc"
INVALID_TYPE_MISMATCH_FIXTURE = FIXTURES / "invalid" / "certified_adapter_type_mismatch.orc"
INVALID_SEMANTIC_BYPASS_FIXTURE = FIXTURES / "invalid" / "certified_adapter_semantic_bypass.orc"
REPO_ROOT = Path(__file__).resolve().parent.parent
DESIGN_DELTA_PARENT_DRAIN_COMMANDS = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.commands.json"
)






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


def _declared_transition_module_source(*, backend: str = "write_drain_status_adapter") -> str:
    return (
        dedent(
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.35")
              (defpath StateFile
                :kind relpath
                :under "state"
                :must-exist false)
              (defrecord DrainRunState
                (drain_status String))
              (defrecord DrainStatusRequest
                (status String))
              (defrecord DrainStatusResult
                (status String))
              (defrecord DrainStatusAudit
                (status String))
              (defrecord Output
                (status String))
              (defresource drain-run-state
                :state-type DrainRunState
                :backing state-layout)
              (deftransition write-drain-status
                :resource drain-run-state
                :request-type DrainStatusRequest
                :result-type DrainStatusResult
                :preconditions ((!= request.status ""))
                :updates ((set-field drain_status request.status))
                :write-set (drain_status)
                :idempotency-fields (status)
                :result (record DrainStatusResult
                  :status request.status)
                :audit (record DrainStatusAudit
                  :status request.status)
                :conflict-policy fail_closed
                :backend {backend})
              (defworkflow orchestrate
                ((status String))
                -> Output
                (record Output
                  :status status)))
            """
        ).strip()
        + "\n"
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


def test_compile_stage3_module_rejects_transition_binding_backend_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "transition_binding_backend_mismatch.orc"
    path.write_text(_declared_transition_module_source(), encoding="utf-8")
    payload = {
        "write_drain_status_adapter": {
            "kind": "certified_adapter",
            "stable_command": ["python", "scripts/write_drain_status.py"],
            "input_contract": {"type": "object"},
            "output_type_name": "DrainStatusResult",
            "effects": ["resource_transition", "ledger_update"],
            "path_safety": {"kind": "workspace_relpath"},
            "source_map_behavior": "step",
            "fixture_ids": ["write_drain_status_ok"],
            "negative_fixture_ids": ["write_drain_status_bad"],
            "behavior_class": "resource_transition",
            "input_signature": [
                {
                    "name": "run_state_path",
                    "type_name": "StateFile",
                    "required": True,
                    "transport_key": "run_state_path",
                }
            ],
            "artifact_contracts": ["write_drain_status_bundle"],
            "state_writes": ["state/run-state.json"],
            "error_codes": ["write_drain_status_invalid"],
            "owner_module": "declared/runtime",
            "replacement_path": "resource-transition",
            "invocation_protocol": "json_object_positional_arg",
            "transition_binding": {
                "transition_name": "write-drain-status",
                "resource_kind": "drain-run-state",
                "contract_role": "migration_backend",
                "backend_selector": "different_adapter",
            },
        }
    }

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            command_boundaries=_parse_command_boundaries_manifest(
                payload,
                manifest_path=None,
            ),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "command_adapter_missing_contract"
    assert "backend" in excinfo.value.diagnostics[0].message


def test_compile_stage3_module_rejects_transition_binding_for_runtime_native_transition(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transition_binding_runtime_native_backend.orc"
    path.write_text(
        _declared_transition_module_source(backend="runtime_native"),
        encoding="utf-8",
    )
    payload = {
        "write_drain_status_adapter": {
            "kind": "certified_adapter",
            "stable_command": ["python", "scripts/write_drain_status.py"],
            "input_contract": {"type": "object"},
            "output_type_name": "DrainStatusResult",
            "effects": ["resource_transition", "ledger_update"],
            "path_safety": {"kind": "workspace_relpath"},
            "source_map_behavior": "step",
            "fixture_ids": ["write_drain_status_ok"],
            "negative_fixture_ids": ["write_drain_status_bad"],
            "behavior_class": "resource_transition",
            "input_signature": [
                {
                    "name": "run_state_path",
                    "type_name": "StateFile",
                    "required": True,
                    "transport_key": "run_state_path",
                }
            ],
            "artifact_contracts": ["write_drain_status_bundle"],
            "state_writes": ["state/run-state.json"],
            "error_codes": ["write_drain_status_invalid"],
            "owner_module": "declared/runtime",
            "replacement_path": "resource-transition",
            "invocation_protocol": "json_object_positional_arg",
            "transition_binding": {
                "transition_name": "write-drain-status",
                "resource_kind": "drain-run-state",
                "contract_role": "migration_backend",
                "backend_selector": "write_drain_status_adapter",
            },
        }
    }

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            command_boundaries=_parse_command_boundaries_manifest(
                payload,
                manifest_path=None,
            ),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "command_adapter_missing_contract"
    assert "runtime_native" in excinfo.value.diagnostics[0].message




def test_design_delta_parent_drain_manifest_keeps_only_retained_g8_rows_and_contract_metadata() -> None:
    payload = json.loads(DESIGN_DELTA_PARENT_DRAIN_COMMANDS.read_text(encoding="utf-8"))

    bindings = _parse_command_boundaries_manifest(
        payload,
        manifest_path=DESIGN_DELTA_PARENT_DRAIN_COMMANDS,
    )

    projection = bindings["project_lisp_frontend_selector_action"]
    assert projection.behavior_class == "structured_result"
    assert getattr(projection, "retirement_class") == "typed_projection"
    assert getattr(projection, "retirement_label") == "retire_to_projection"
    assert getattr(projection, "replacement_surface")
    assert getattr(projection, "bridge_owner")
    assert getattr(projection, "expiry_condition")
    assert getattr(projection, "evidence_refs")

    for deleted_binding in (
        "classify_lisp_frontend_work_item_terminal",
        "select_lisp_frontend_blocked_recovery_route",
        "record_terminal_work_item",
        "record_blocked_recovery_outcome",
        "write_lisp_frontend_drain_status",
        "finalize_lisp_frontend_drain_summary",
    ):
        assert deleted_binding not in bindings

    backlog_checks = bindings["run_neurips_backlog_checks"]
    assert getattr(backlog_checks, "retirement_class") == "genuine_system"
    assert getattr(backlog_checks, "retirement_label") == "keep_certified_system"

    review_findings = bindings["validate_review_findings_v1"]
    assert getattr(review_findings, "retirement_class") == "validation"
    assert getattr(review_findings, "retirement_label") == "keep_bridge"
    assert getattr(review_findings, "replacement_surface")
    assert getattr(review_findings, "bridge_owner")
    assert getattr(review_findings, "expiry_condition")
    assert getattr(review_findings, "evidence_refs")

    work_item_bootstrap = bindings["materialize_lisp_frontend_work_item_inputs"]
    assert getattr(work_item_bootstrap, "retirement_label") == "retire_to_projection"
    assert getattr(work_item_bootstrap, "retirement_status") == "retired"
    assert getattr(work_item_bootstrap, "replacement_surface")
    assert getattr(work_item_bootstrap, "bridge_owner")
    assert getattr(work_item_bootstrap, "expiry_condition")
    assert getattr(work_item_bootstrap, "evidence_refs")


def test_design_delta_parent_drain_command_manifest_excludes_internal_finalizer_carrier_helpers() -> None:
    manifest_text = DESIGN_DELTA_PARENT_DRAIN_COMMANDS.read_text(encoding="utf-8")

    for retired_name in (
        "SelectedItemStdlibCompat",
        "QueueTransitionCompat",
        "RoadmapCompat",
        "SelectedItemPlanCompat",
        "SelectedItemImplementationCompat",
        "build-finalizer-",
        "call-imported-finalize-selected-item",
        "project-selected-compat",
        "BranchingSelectedCompat",
    ):
        assert retired_name not in manifest_text


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
                '  (:target-dsl "2.35")',
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
