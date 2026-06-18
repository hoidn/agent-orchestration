from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from textwrap import dedent

import pytest

from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.command_boundaries import (
    CommandBoundaryEnvironment,
    build_command_boundary_environment,
)
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import CommandResultExpr, elaborate_expression
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.source_map import build_source_map_document
from orchestrator.workflow_lisp.syntax import SyntaxNode
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from orchestrator.variables.substitution import VariableSubstitutor


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


def _typed_adapter_manifest_payload() -> dict[str, object]:
    return {
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
        },
        "apply_resource_transition": {
            "kind": "certified_adapter",
            "stable_command": [
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.apply_resource_transition",
            ],
            "input_contract": {"type": "object"},
            "output_type_name": "ResourceTransitionResult",
            "effects": ["resource_transition", "ledger_update"],
            "path_safety": {"kind": "workspace_relpath"},
            "source_map_behavior": "step",
            "fixture_ids": ["resource_transition_ok"],
            "negative_fixture_ids": ["resource_transition_bad"],
            "behavior_class": "resource_transition",
            "input_signature": [
                {
                    "name": "resource_id",
                    "type_name": "String",
                    "required": True,
                    "transport_key": "resource_id",
                },
                {
                    "name": "from",
                    "type_name": "Queue",
                    "required": True,
                    "transport_key": "from",
                },
                {
                    "name": "to",
                    "type_name": "Queue",
                    "required": True,
                    "transport_key": "to",
                },
                {
                    "name": "new_path",
                    "type_name": "BacklogInProgressPath",
                    "required": True,
                    "transport_key": "new_path",
                },
                {
                    "name": "transition_id",
                    "type_name": "String",
                    "required": True,
                    "transport_key": "transition_id",
                },
            ],
            "artifact_contracts": ["resource_transition_result"],
            "state_writes": ["state/resource-ledger.json"],
            "error_codes": ["resource_transition_invalid"],
            "owner_module": "std/resource",
            "replacement_path": "resource-transition",
            "invocation_protocol": "json_object_positional_arg",
        },
    }


def _command_boundaries():
    return _parse_command_boundaries_manifest(
        _typed_adapter_manifest_payload(),
        manifest_path=None,
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
              (:target-dsl "2.14")
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


def _compile_fixture(path: Path, *, tmp_path: Path):
    return compile_stage3_module(
        path,
        command_boundaries=_command_boundaries(),
        validate_shared=False,
        workspace_root=tmp_path,
    )


def _declared_transition_runtime_module_source(*, backend: str = "write_drain_status_adapter") -> str:
    return (
        dedent(
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.14")
              (defmodule declared/runtime)
              (defpath StateFile
                :kind relpath
                :under "state"
                :must-exist false)
              (defrecord DrainRunState
                (drain_status String)
                (drain_status_reason String))
              (defrecord DrainStatusRequest
                (status String)
                (reason String))
              (defrecord DrainStatusResult
                (status String))
              (defrecord DrainStatusAudit
                (status String))
              (defrecord Output
                (status String))
              (defresource drain-run-state
                :state-type DrainRunState
                :backing (bridge run_state_path))
              (deftransition write-drain-status
                :resource drain-run-state
                :request-type DrainStatusRequest
                :result-type DrainStatusResult
                :preconditions ((!= request.status ""))
                :updates ((set-field drain_status request.status)
                          (set-field drain_status_reason request.reason))
                :write-set (drain_status drain_status_reason)
                :idempotency-fields (status reason)
                :result (record DrainStatusResult
                  :status request.status)
                :audit (record DrainStatusAudit
                  :status request.status)
                :conflict-policy fail_closed
                :backend {backend})
              (defworkflow orchestrate
                ((run_state_path StateFile)
                 (status String)
                 (reason String))
                -> Output
                (let* ((result
                         (resource-transition
                           :transition write-drain-status
                           :resource drain-run-state
                           :request (record DrainStatusRequest
                             :status status
                             :reason reason))))
                  (record Output
                    :status result.status))))
            """
        ).strip()
        + "\n"
    )


def test_command_result_adapter_manifest_supports_typed_metadata() -> None:
    bindings = _command_boundaries()
    binding = bindings["normalize_result"]

    assert binding.behavior_class == "structured_result"
    assert binding.invocation_protocol == "json_object_positional_arg"
    assert tuple(
        (field.name, field.type_name, field.required, field.transport_key)
        for field in binding.input_signature
    ) == (
        ("execution_report", "WorkReport", True, "execution_report"),
        ("review_report", "WorkReport", True, "review_report"),
    )
    assert binding.owner_module == "std/phase"
    assert binding.replacement_path is None


def test_command_result_adapter_manifest_preserves_transition_binding_metadata() -> None:
    payload = _typed_adapter_manifest_payload()
    payload["apply_resource_transition"]["transition_binding"] = {
        "transition_name": "write-drain-status",
        "resource_kind": "drain-run-state",
        "contract_role": "migration_backend",
        "backend_selector": "apply_resource_transition",
    }

    bindings = _validated_command_boundaries(payload).bindings_by_name
    binding = bindings["apply_resource_transition"]

    assert getattr(binding, "transition_binding").transition_name == "write-drain-status"
    assert getattr(binding, "transition_binding").resource_kind == "drain-run-state"
    assert getattr(binding, "transition_binding").contract_role == "migration_backend"
    assert getattr(binding, "transition_binding").backend_selector == "apply_resource_transition"


def test_command_result_adapter_manifest_rejects_invalid_transition_binding_role() -> None:
    payload = _typed_adapter_manifest_payload()
    payload["apply_resource_transition"]["transition_binding"] = {
        "transition_name": "write-drain-status",
        "resource_kind": "drain-run-state",
        "contract_role": "typed_projection",
        "backend_selector": "apply_resource_transition",
    }

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _validated_command_boundaries(payload)

    assert excinfo.value.diagnostics[0].code == "command_adapter_missing_contract"
    assert "migration_backend" in excinfo.value.diagnostics[0].message


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


def test_compile_stage3_module_preserves_certified_transition_backend_metadata_for_runtime_step(
    tmp_path: Path,
) -> None:
    path = tmp_path / "declared" / "runtime.orc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_declared_transition_runtime_module_source(), encoding="utf-8")
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
                "transition_name": "declared/runtime::write-drain-status",
                "resource_kind": "drain-run-state",
                "contract_role": "migration_backend",
                "backend_selector": "write_drain_status_adapter",
            },
        }
    }

    result = compile_stage3_entrypoint(
        path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries=_parse_command_boundaries_manifest(
            payload,
            manifest_path=None,
        ),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles_by_name["declared/runtime::orchestrate"]
    backend = bundle.surface.steps[0].resource_transition["declaration"].transition.backend

    assert backend["kind"] == "write_drain_status_adapter"
    assert backend["stable_command"] == ["python", "scripts/write_drain_status.py"]
    assert backend["invocation_protocol"] == "json_object_positional_arg"


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


def test_non_family_command_boundary_manifest_remains_compatible_without_retirement_metadata() -> None:
    environment = _validated_command_boundaries(_typed_adapter_manifest_payload())

    assert "normalize_result" in environment.bindings_by_name
    assert "apply_resource_transition" in environment.bindings_by_name


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


def test_command_result_adapter_missing_input_fails(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_fixture(INVALID_MISSING_INPUT_FIXTURE, tmp_path=tmp_path)

    assert excinfo.value.diagnostics[0].code == "command_result_adapter_invalid"


def test_command_result_adapter_extra_input_fails(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_fixture(INVALID_EXTRA_INPUT_FIXTURE, tmp_path=tmp_path)

    assert excinfo.value.diagnostics[0].code == "command_result_adapter_invalid"


def test_command_result_adapter_type_mismatch_fails(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_fixture(INVALID_TYPE_MISMATCH_FIXTURE, tmp_path=tmp_path)

    assert excinfo.value.diagnostics[0].code == "type_mismatch"


def test_command_result_adapter_non_projectable_input_fails(tmp_path: Path) -> None:
    path = tmp_path / "certified_adapter_non_projectable.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
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

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
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

    assert excinfo.value.diagnostics[0].code == "command_adapter_input_not_projectable"


def test_command_result_adapter_semantic_bypass_fails(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_fixture(INVALID_SEMANTIC_BYPASS_FIXTURE, tmp_path=tmp_path)

    assert excinfo.value.diagnostics[0].code == "resource_move_without_transition"


def test_command_result_adapter_lowers_to_stable_command_plus_json_payload(tmp_path: Path) -> None:
    result = _compile_fixture(VALID_FIXTURE, tmp_path=tmp_path)

    lowered = result.lowered_workflows[0].authored_mapping
    step = lowered["steps"][0]

    assert step["command"][:2] == ["python", "scripts/normalize_result.py"]
    assert len(step["command"]) == 3
    assert step["command"][2] == (
        '{"execution_report":${inputs.completed__execution_report|json},'
        '"review_report":${inputs.approved__review_report|json}}'
    )


def test_command_result_adapter_preserves_typed_json_scalar_payloads(tmp_path: Path) -> None:
    path = tmp_path / "certified_adapter_typed_payload.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord AdapterInputs",
                "    (count Int)",
                "    (flag Bool)",
                "    (name String))",
                "  (defrecord NormalizedPayload",
                "    (summary String))",
                "  (defworkflow normalize-scalars",
                "    ((inputs AdapterInputs))",
                "    -> NormalizedPayload",
                "    (command-result normalize_scalars",
                "      :adapter normalize_scalars",
                "      :inputs",
                "        ((count inputs.count)",
                "         (flag inputs.flag)",
                "         (name inputs.name))",
                "      :returns NormalizedPayload)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    command_boundaries = _parse_command_boundaries_manifest(
        {
            "normalize_scalars": {
                "kind": "certified_adapter",
                "stable_command": ["python", "scripts/normalize_scalars.py"],
                "input_contract": {"type": "object"},
                "output_type_name": "NormalizedPayload",
                "effects": ["structured_result"],
                "path_safety": {"kind": "workspace_relpath"},
                "source_map_behavior": "step",
                "fixture_ids": ["normalize_scalars_ok"],
                "negative_fixture_ids": ["normalize_scalars_bad"],
                "behavior_class": "structured_result",
                "input_signature": [
                    {
                        "name": "count",
                        "type_name": "Int",
                        "required": True,
                        "transport_key": "count",
                    },
                    {
                        "name": "flag",
                        "type_name": "Bool",
                        "required": True,
                        "transport_key": "flag",
                    },
                    {
                        "name": "name",
                        "type_name": "String",
                        "required": True,
                        "transport_key": "name",
                    },
                ],
                "artifact_contracts": ["normalized_payload_bundle"],
                "state_writes": [],
                "error_codes": ["normalize_scalars_invalid_payload"],
                "owner_module": "std/phase",
                "replacement_path": None,
                "invocation_protocol": "json_object_positional_arg",
            }
        },
        manifest_path=None,
    )

    result = compile_stage3_module(
        path,
        command_boundaries=command_boundaries,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered = result.lowered_workflows[0].authored_mapping
    step = lowered["steps"][0]

    assert step["command"][:2] == ["python", "scripts/normalize_scalars.py"]
    assert step["command"][2] == (
        '{"count":${inputs.inputs__count|json},"flag":${inputs.inputs__flag|json},'
        '"name":${inputs.inputs__name|json}}'
    )


def test_command_result_adapter_preserves_enum_member_strings_for_json_object_payloads(
    tmp_path: Path,
) -> None:
    path = tmp_path / "certified_adapter_enum_payload.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defenum WorkItemSource",
                "    BACKLOG_ITEM",
                "    DESIGN_GAP)",
                "  (defrecord AdapterInputs",
                "    (work_item_source WorkItemSource))",
                "  (defrecord NormalizedPayload",
                "    (summary String))",
                "  (defworkflow normalize-enum",
                "    ((inputs AdapterInputs))",
                "    -> NormalizedPayload",
                "    (command-result normalize_enum",
                "      :adapter normalize_enum",
                "      :inputs",
                "        ((work_item_source inputs.work_item_source))",
                "      :returns NormalizedPayload)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    command_boundaries = _parse_command_boundaries_manifest(
        {
            "normalize_enum": {
                "kind": "certified_adapter",
                "stable_command": ["python", "scripts/normalize_enum.py"],
                "input_contract": {"type": "object"},
                "output_type_name": "NormalizedPayload",
                "effects": ["structured_result"],
                "path_safety": {"kind": "workspace_relpath"},
                "source_map_behavior": "step",
                "fixture_ids": ["normalize_enum_ok"],
                "negative_fixture_ids": ["normalize_enum_bad"],
                "behavior_class": "structured_result",
                "input_signature": [
                    {
                        "name": "work_item_source",
                        "type_name": "WorkItemSource",
                        "required": True,
                        "transport_key": "work_item_source",
                    }
                ],
                "artifact_contracts": ["normalized_payload_bundle"],
                "state_writes": [],
                "error_codes": ["normalize_enum_invalid_payload"],
                "owner_module": "std/phase",
                "replacement_path": None,
                "invocation_protocol": "json_object_positional_arg",
            }
        },
        manifest_path=None,
    )

    result = compile_stage3_module(
        path,
        command_boundaries=command_boundaries,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered = result.lowered_workflows[0].authored_mapping
    step = lowered["steps"][0]

    assert step["command"][:2] == ["python", "scripts/normalize_enum.py"]
    assert step["command"][2] == (
        '{"work_item_source":${inputs.inputs__work_item_source|json}}'
    )


def test_command_result_adapter_payload_substitution_preserves_json_string_content(tmp_path: Path) -> None:
    path = tmp_path / "certified_adapter_json_safe_payload.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord AdapterInputs",
                "    (name String))",
                "  (defrecord NormalizedPayload",
                "    (summary String))",
                "  (defworkflow normalize-json-string",
                "    ((inputs AdapterInputs))",
                "    -> NormalizedPayload",
                "    (command-result normalize_json_string",
                "      :adapter normalize_json_string",
                "      :inputs",
                "        ((name inputs.name))",
                "      :returns NormalizedPayload)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    command_boundaries = _parse_command_boundaries_manifest(
        {
            "normalize_json_string": {
                "kind": "certified_adapter",
                "stable_command": ["python", "scripts/normalize_json_string.py"],
                "input_contract": {"type": "object"},
                "output_type_name": "NormalizedPayload",
                "effects": ["structured_result"],
                "path_safety": {"kind": "workspace_relpath"},
                "source_map_behavior": "step",
                "fixture_ids": ["normalize_json_string_ok"],
                "negative_fixture_ids": ["normalize_json_string_bad"],
                "behavior_class": "structured_result",
                "input_signature": [
                    {
                        "name": "name",
                        "type_name": "String",
                        "required": True,
                        "transport_key": "name",
                    }
                ],
                "artifact_contracts": ["normalized_payload_bundle"],
                "state_writes": [],
                "error_codes": ["normalize_json_string_invalid_payload"],
                "owner_module": "std/phase",
                "replacement_path": None,
                "invocation_protocol": "json_object_positional_arg",
            }
        },
        manifest_path=None,
    )

    result = compile_stage3_module(
        path,
        command_boundaries=command_boundaries,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered = result.lowered_workflows[0].authored_mapping
    step = lowered["steps"][0]
    substitutor = VariableSubstitutor()

    substituted_payload = substitutor.substitute(
        step["command"][2],
        {"inputs": {"inputs__name": 'a"b\\c'}},
    )

    assert json.loads(substituted_payload) == {"name": 'a"b\\c'}


def test_command_result_adapter_preserves_source_map_lineage(tmp_path: Path) -> None:
    result = _compile_fixture(VALID_FIXTURE, tmp_path=tmp_path)
    document = build_source_map_document(
        SimpleNamespace(
            compiled_results_by_name={"__main__": result},
            validated_bundles_by_name=result.validated_bundles,
        ),
        selected_name="normalize-summary",
        display_name_resolver=lambda workflow_name: workflow_name,
    )
    workflow = document.workflows["normalize-summary"]
    boundary = workflow.command_boundaries[0]

    assert boundary.boundary_kind == "certified_adapter"
    assert boundary.command_name == "normalize_result"
    assert boundary.adapter_name == "normalize_result"
    assert boundary.source_map_behavior == "step"
    assert boundary.declared_effects == ("structured_result",)
