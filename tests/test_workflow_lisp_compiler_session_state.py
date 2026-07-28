from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
import subprocess
import sys
from typing import TYPE_CHECKING, cast

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError

if TYPE_CHECKING:
    from orchestrator.workflow_lisp.compiler_session import (
        CompilerSession,
        NameResolver,
    )
    from orchestrator.workflow_lisp.expressions import ExprNode
    from orchestrator.workflow_lisp.functions import FunctionCatalog
    from orchestrator.workflow_lisp.loop_state import LoopStateCarrierMetadata
    from orchestrator.workflow_lisp.parametric_constraints import (
        SharedUnionFieldCapability,
    )
    from orchestrator.workflow_lisp.procedure_refs import ResolvedProcRefValue
    from orchestrator.workflow_lisp.procedure_typecheck import (
        PendingParametricProcedureSpecialization,
    )
    from orchestrator.workflow_lisp.procedures import (
        ProcedureSignature,
        TypedProcedureDef,
    )
    from orchestrator.workflow_lisp.prompts import PromptCatalog
    from orchestrator.workflow_lisp.typecheck_context import LoopTypecheckContext
    from orchestrator.workflow_lisp.workflows import WorkflowSignature


def _write_module(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")


def _session_expression(source: str, compiler_session: CompilerSession):
    from orchestrator.workflow_lisp.expressions import elaborate_expression
    from orchestrator.workflow_lisp.reader import read_sexpr_text
    from orchestrator.workflow_lisp.syntax import SyntaxNode

    [datum] = read_sexpr_text(source, source_path="session.orc").items
    syntax = SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="session.orc",
        form_path=("workflow-lisp", "session"),
    )
    return elaborate_expression(
        syntax,
        bound_names=frozenset(),
        session_state=compiler_session.elaboration,
    )


def _session_type_env(compiler_session: CompilerSession):
    from orchestrator.workflow_lisp.type_env import (
        FrontendTypeEnvironment,
        PrimitiveTypeRef,
    )

    return FrontendTypeEnvironment(
        {"String": PrimitiveTypeRef(name="String")},
        session_state=compiler_session.typecheck,
    )


def _final_application_source(*, value: str = "final") -> str:
    return f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule final_application)
  (export FinalResult final-output)
  (defrecord FinalResult (value String))
  (defworkflow final-output () -> FinalResult
    (command-result final-command
      :argv ("python" "scripts/final.py" "{value}")
      :returns FinalResult)))
"""


def _compiled_artifact_snapshot(
    source_path: Path,
    workspace_root: Path,
    lowering_route: str,
) -> dict[str, object]:
    """Return every serialized compiler surface covered by MR-4 parity."""

    from orchestrator.workflow_lisp import build

    command_boundaries_path = source_path.parent / "final_commands.json"
    result = build.build_frontend_bundle_in_memory(
        build.FrontendBuildRequest(
            source_path=source_path,
            source_roots=(source_path.parent,),
            entry_workflow="final-output",
            workspace_root=workspace_root,
            lowering_route=lowering_route,
            command_boundaries_path=(
                command_boundaries_path
                if command_boundaries_path.exists()
                else None
            ),
        )
    )
    assert result.entry_selection is not None
    return {
        "diagnostics": [
            build._json_data(diagnostic)
            for diagnostic in result.diagnostics
        ],
        "typed_artifacts": build._serialize_typed_frontend_ast(
            result.compile_result
        ),
        "lowered_json": build._serialize_lowered_workflows(
            result.compile_result
        ),
        "source_map": result.source_map_payload,
        "executable_ir": result.executable_ir_payload,
        "runtime_plan": result.runtime_plan_payload,
    }


def _isolated_compiled_artifact_snapshot(
    source_path: Path,
    workspace_root: Path,
    lowering_route: str,
) -> dict[str, object]:
    script = "\n".join(
        (
            "import json",
            "from pathlib import Path",
            "import sys",
            "from tests.test_workflow_lisp_compiler_session_state import (",
            "    _compiled_artifact_snapshot,",
            ")",
            "print(json.dumps(_compiled_artifact_snapshot(",
            "    Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]",
            "), sort_keys=True))",
        )
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(source_path),
            str(workspace_root),
            lowering_route,
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=True,
    )
    return cast("dict[str, object]", json.loads(completed.stdout))


def test_compiler_session_owns_distinct_compile_phase_state() -> None:
    from orchestrator.workflow_lisp.compiler_session import (
        CompilerSession,
        ElaborationSessionState,
        TypecheckSessionState,
    )

    first = CompilerSession()
    second = CompilerSession()

    assert first.elaboration is not first.typecheck
    assert first.typecheck is not first.lowering
    assert first.elaboration is not second.elaboration
    assert first.typecheck is not second.typecheck
    assert first.lowering is not second.lowering
    assert first.elaboration == ElaborationSessionState()
    assert first.typecheck == TypecheckSessionState()


def test_entrypoint_module_graph_threads_one_compiler_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp import compiler

    source_root = (
        Path(__file__).parent
        / "fixtures"
        / "workflow_lisp"
        / "modules"
        / "valid"
        / "imported_defun"
    )
    seen_sessions: list[object] = []
    typecheck_functions = compiler.typecheck_function_definitions

    def capture_session(*args, **kwargs):
        seen_sessions.append(kwargs["compiler_session"])
        return typecheck_functions(*args, **kwargs)

    monkeypatch.setattr(
        compiler,
        "typecheck_function_definitions",
        capture_session,
    )

    compiler.compile_stage3_entrypoint(
        source_root / "entry.orc",
        source_roots=(source_root,),
        command_boundaries={
            "run_checks": compiler.ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )
    compiler.compile_stage3_entrypoint(
        source_root / "entry.orc",
        source_roots=(source_root,),
        command_boundaries={
            "run_checks": compiler.ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )

    assert len(seen_sessions) == 6
    first_graph_sessions = seen_sessions[:3]
    second_graph_sessions = seen_sessions[3:]
    assert len({id(session) for session in first_graph_sessions}) == 1
    assert len({id(session) for session in second_graph_sessions}) == 1
    assert first_graph_sessions[0] is not second_graph_sessions[0]


def test_elaboration_session_covers_all_fields_and_restores_nested_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp import expressions
    from orchestrator.workflow_lisp.compiler_session import CompilerSession
    from orchestrator.workflow_lisp.reader import read_sexpr_text
    from orchestrator.workflow_lisp.syntax import SyntaxNode

    compiler_session = CompilerSession()
    state = compiler_session.elaboration
    outer_procedure_resolver = cast("NameResolver", object())
    outer_function_resolver = cast("NameResolver", object())
    outer_workflow_resolver = cast("NameResolver", object())
    outer_prompt_catalog = cast("PromptCatalog", object())
    inner_procedure_resolver = cast("NameResolver", object())
    inner_function_resolver = cast("NameResolver", object())
    inner_workflow_resolver = cast("NameResolver", object())
    inner_prompt_catalog = cast("PromptCatalog", object())
    state.procedure_name_resolver = cast("NameResolver", object())
    state.function_name_resolver = cast("NameResolver", object())
    state.workflow_name_resolver = cast("NameResolver", object())
    state.function_names = frozenset({"outer"})
    state.local_proc_names = frozenset({"local"})
    state.loop_body_depth = 4
    state.let_proc_depth = 2
    state.guidance_example = True
    state.target_dsl_version = "2.21"
    state.prompt_catalog = cast("PromptCatalog", object())
    baseline = state.__dict__.copy()

    def syntax(source: str) -> SyntaxNode:
        [datum] = read_sexpr_text(source, source_path="session.orc").items
        return SyntaxNode(
            datum=datum,
            span=datum.span,
            module_path="session.orc",
            form_path=("workflow-lisp", "session"),
        )

    outer_expected = {
        "procedure_name_resolver": outer_procedure_resolver,
        "function_name_resolver": outer_function_resolver,
        "workflow_name_resolver": outer_workflow_resolver,
        "function_names": frozenset({"outer-call"}),
        "local_proc_names": frozenset(),
        "loop_body_depth": 4,
        "let_proc_depth": 0,
        "guidance_example": False,
        "target_dsl_version": "2.15",
        "prompt_catalog": outer_prompt_catalog,
    }
    inner_expected = {
        "procedure_name_resolver": inner_procedure_resolver,
        "function_name_resolver": inner_function_resolver,
        "workflow_name_resolver": inner_workflow_resolver,
        "function_names": frozenset({"inner-call"}),
        "local_proc_names": frozenset(),
        "loop_body_depth": 4,
        "let_proc_depth": 0,
        "guidance_example": True,
        "target_dsl_version": "2.21",
        "prompt_catalog": inner_prompt_catalog,
    }
    original_elaborate = expressions._elaborate
    depth = 0
    observed_states: list[dict[str, object]] = []

    def nested_probe(*args, **kwargs):
        nonlocal depth
        observed_states.append(kwargs["session_state"].__dict__.copy())
        if depth == 0:
            outer_snapshot = state.__dict__.copy()
            depth = 1
            try:
                def elaborate_inner(source: str):
                    return expressions.elaborate_expression(
                        syntax(source),
                        bound_names=frozenset(),
                        procedure_names=frozenset({"inner-proc"}),
                        function_names=frozenset({"inner-call"}),
                        function_name_resolver=inner_function_resolver,
                        procedure_name_resolver=inner_procedure_resolver,
                        workflow_name_resolver=inner_workflow_resolver,
                        guidance_example=True,
                        target_dsl_version="2.21",
                        prompt_catalog=inner_prompt_catalog,
                        session_state=state,
                    )

                elaborate_inner('"inner"')
                assert state.__dict__ == outer_snapshot
                with pytest.raises(LispFrontendCompileError):
                    elaborate_inner("(unknown-inner-form)")
            finally:
                depth = 0
            assert state.__dict__ == outer_snapshot
        return original_elaborate(*args, **kwargs)

    monkeypatch.setattr(expressions, "_elaborate", nested_probe)
    expressions.elaborate_expression(
        syntax('"ok"'),
        bound_names=frozenset(),
        procedure_names=frozenset({"outer-proc"}),
        function_names=frozenset({"outer-call"}),
        function_name_resolver=outer_function_resolver,
        procedure_name_resolver=outer_procedure_resolver,
        workflow_name_resolver=outer_workflow_resolver,
        guidance_example=False,
        target_dsl_version="2.15",
        prompt_catalog=outer_prompt_catalog,
        session_state=state,
    )
    assert observed_states[:3] == [
        outer_expected,
        inner_expected,
        inner_expected,
    ]
    assert state.__dict__ == baseline

    with pytest.raises(LispFrontendCompileError):
        expressions.elaborate_expression(
            syntax("(unknown-form)"),
            bound_names=frozenset(),
            procedure_names=frozenset({"outer-proc"}),
            function_names=frozenset({"outer-call"}),
            function_name_resolver=outer_function_resolver,
            procedure_name_resolver=outer_procedure_resolver,
            workflow_name_resolver=outer_workflow_resolver,
            guidance_example=False,
            target_dsl_version="2.15",
            prompt_catalog=outer_prompt_catalog,
            session_state=state,
        )
    assert state.__dict__ == baseline
    assert CompilerSession().elaboration.__dict__ == {
        "procedure_name_resolver": None,
        "function_name_resolver": None,
        "workflow_name_resolver": None,
        "function_names": frozenset(),
        "local_proc_names": frozenset(),
        "loop_body_depth": 0,
        "let_proc_depth": 0,
        "guidance_example": False,
        "target_dsl_version": None,
        "prompt_catalog": None,
    }


def test_typecheck_session_covers_all_fields_and_restores_nested_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp import typecheck_dispatch
    from orchestrator.workflow_lisp.compiler_session import CompilerSession
    from orchestrator.workflow_lisp.expressions import elaborate_expression
    from orchestrator.workflow_lisp.reader import read_sexpr_text
    from orchestrator.workflow_lisp.syntax import SyntaxNode
    from orchestrator.workflow_lisp.type_env import (
        FrontendTypeEnvironment,
        PrimitiveTypeRef,
    )
    from orchestrator.workflow_lisp.typecheck_dispatch import typecheck_expression

    compiler_session = CompilerSession()
    state = compiler_session.typecheck
    state.function_catalog = cast("FunctionCatalog", object())
    state.proc_ref_value_env = {
        "outer": cast("ResolvedProcRefValue", object())
    }
    state.value_expr_env = {"outer": cast("ExprNode", object())}
    state.loop_context = [cast("LoopTypecheckContext", object())]
    state.generated_local_procedures = {
        "outer": cast("TypedProcedureDef", object())
    }
    state.let_proc_rewrite_results = {1: cast("ExprNode", object())}
    state.workflow_signature = cast("WorkflowSignature", object())
    state.procedure_hidden_context_signature = cast(
        "ProcedureSignature", object()
    )
    state.reusable_state_producer_context = {"outer": object()}
    state.shared_union_field_capabilities = (
        cast("SharedUnionFieldCapability", object()),
    )
    state.loop_carrier_metadata_by_name = {
        "carrier": cast("LoopStateCarrierMetadata", object())
    }
    state.loop_carrier_metadata_by_expr_key = {
        ("expr", 1, 1, ("form",)): {
            (("value", "String"),): cast(
                "LoopStateCarrierMetadata", object()
            )
        }
    }
    state.parametric_specialization_requests = {
        "specialization": cast(
            "PendingParametricProcedureSpecialization", object()
        )
    }

    def state_snapshot() -> dict[str, object]:
        return {
            "function_catalog": state.function_catalog,
            "proc_ref_value_env": dict(state.proc_ref_value_env),
            "value_expr_env": dict(state.value_expr_env),
            "loop_context": list(state.loop_context),
            "generated_local_procedures": dict(state.generated_local_procedures),
            "let_proc_rewrite_results": dict(state.let_proc_rewrite_results),
            "workflow_signature": state.workflow_signature,
            "procedure_hidden_context_signature": (
                state.procedure_hidden_context_signature
            ),
            "reusable_state_producer_context": dict(
                state.reusable_state_producer_context or {}
            ),
            "shared_union_field_capabilities": tuple(
                state.shared_union_field_capabilities
            ),
            "loop_carrier_metadata_by_name": dict(
                state.loop_carrier_metadata_by_name
            ),
            "loop_carrier_metadata_by_expr_key": {
                key: dict(value)
                for key, value in state.loop_carrier_metadata_by_expr_key.items()
            },
            "parametric_specialization_requests": dict(
                state.parametric_specialization_requests
            ),
        }

    baseline = state_snapshot()
    type_env = FrontendTypeEnvironment(
        {"String": PrimitiveTypeRef(name="String")},
        session_state=state,
    )

    def expression(source: str):
        [datum] = read_sexpr_text(source, source_path="session.orc").items
        syntax = SyntaxNode(
            datum=datum,
            span=datum.span,
            module_path="session.orc",
            form_path=("workflow-lisp", "session"),
        )
        return elaborate_expression(
            syntax,
            bound_names=frozenset(),
            session_state=compiler_session.elaboration,
        )

    original_typecheck = typecheck_dispatch._typecheck
    depth = 0
    seen_state_ids: list[int] = []

    def nested_probe(*args, **kwargs):
        nonlocal depth
        assert kwargs["compiler_session"] is compiler_session
        assert kwargs["session_state"] is compiler_session.typecheck
        seen_state_ids.append(id(kwargs["session_state"]))
        if depth == 0:
            outer_snapshot = state_snapshot()
            depth = 1
            try:
                typecheck_expression(
                    expression('"nested"'),
                    type_env=type_env,
                    value_env={},
                    compiler_session=compiler_session,
                )
                assert state_snapshot() == outer_snapshot
                with pytest.raises(LispFrontendCompileError):
                    typecheck_expression(
                        expression("missing-nested"),
                        type_env=type_env,
                        value_env={},
                        compiler_session=compiler_session,
                    )
            finally:
                depth = 0
            assert state_snapshot() == outer_snapshot
        return original_typecheck(*args, **kwargs)

    monkeypatch.setattr(typecheck_dispatch, "_typecheck", nested_probe)
    typecheck_expression(
        expression('"ok"'),
        type_env=type_env,
        value_env={},
        compiler_session=compiler_session,
    )
    assert state_snapshot() == baseline

    with pytest.raises(LispFrontendCompileError):
        typecheck_expression(
            expression("missing"),
            type_env=type_env,
            value_env={},
            compiler_session=compiler_session,
        )
    assert state_snapshot() == baseline
    assert set(seen_state_ids) == {id(state)}

    fresh = CompilerSession().typecheck
    assert fresh.__dict__ == {
        "function_catalog": None,
        "proc_ref_value_env": {},
        "value_expr_env": {},
        "loop_context": [],
        "generated_local_procedures": {},
        "let_proc_rewrite_results": {},
        "workflow_signature": None,
        "procedure_hidden_context_signature": None,
        "reusable_state_producer_context": None,
        "shared_union_field_capabilities": (),
        "loop_carrier_metadata_by_name": {},
        "loop_carrier_metadata_by_expr_key": {},
        "parametric_specialization_requests": {},
    }


def test_typecheck_snapshot_and_restore_cover_every_session_root() -> None:
    from orchestrator.workflow_lisp.compiler_session import CompilerSession
    from orchestrator.workflow_lisp.typecheck_context import (
        restore_session_state,
        snapshot_session_state,
    )

    state = CompilerSession().typecheck
    state.generated_local_procedures = {
        "outer": cast("TypedProcedureDef", object())
    }
    state.loop_carrier_metadata_by_name = {
        "carrier": cast("LoopStateCarrierMetadata", object())
    }
    state.loop_carrier_metadata_by_expr_key = {
        ("source", 1, 1, ("form",)): {
            (("value", "String"),): cast(
                "LoopStateCarrierMetadata", object()
            )
        }
    }
    state.parametric_specialization_requests = {
        "specialized": cast(
            "PendingParametricProcedureSpecialization", object()
        )
    }
    snapshot = snapshot_session_state(state)

    state.generated_local_procedures["nested"] = cast(
        "TypedProcedureDef", object()
    )
    state.loop_carrier_metadata_by_name["nested"] = cast(
        "LoopStateCarrierMetadata", object()
    )
    state.loop_carrier_metadata_by_expr_key[("nested", 2, 1, ("form",))] = {
        (("value", "Bool"),): cast("LoopStateCarrierMetadata", object())
    }
    state.parametric_specialization_requests["nested"] = cast(
        "PendingParametricProcedureSpecialization", object()
    )
    restore_session_state(state, snapshot)

    assert state.generated_local_procedures == snapshot.generated_local_procedures
    assert (
        state.loop_carrier_metadata_by_name
        == snapshot.loop_carrier_metadata_by_name
    )
    assert (
        state.loop_carrier_metadata_by_expr_key
        == snapshot.loop_carrier_metadata_by_expr_key
    )
    assert (
        state.parametric_specialization_requests
        == snapshot.parametric_specialization_requests
    )


def test_nested_typecheck_merges_success_outputs_and_discards_failure_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp import typecheck_dispatch
    from orchestrator.workflow_lisp.compiler_session import CompilerSession
    from orchestrator.workflow_lisp.typecheck_dispatch import typecheck_expression

    compiler_session = CompilerSession()
    state = compiler_session.typecheck
    type_env = _session_type_env(compiler_session)
    outer_values = {
        "generated": object(),
        "loop_name": object(),
        "loop_expr": object(),
        "specialization": object(),
    }
    success_values = {name: object() for name in outer_values}
    failure_values = {name: object() for name in outer_values}
    outer_expr_key = ("outer", 1, 1, ("outer",))
    success_expr_key = ("success", 1, 1, ("success",))
    failure_expr_key = ("failure", 1, 1, ("failure",))
    signature = (("value", "String"),)
    state.generated_local_procedures = {
        "outer": cast("TypedProcedureDef", outer_values["generated"])
    }
    state.loop_carrier_metadata_by_name = {
        "outer": cast(
            "LoopStateCarrierMetadata", outer_values["loop_name"]
        )
    }
    state.loop_carrier_metadata_by_expr_key = {
        outer_expr_key: {
            signature: cast(
                "LoopStateCarrierMetadata", outer_values["loop_expr"]
            )
        }
    }
    state.parametric_specialization_requests = {
        "outer": cast(
            "PendingParametricProcedureSpecialization",
            outer_values["specialization"],
        )
    }
    original_typecheck = typecheck_dispatch._typecheck
    depth = 0
    mutation = ""

    def mutate_roots(prefix: str, values: dict[str, object], expr_key) -> None:
        state.generated_local_procedures[prefix] = cast(
            "TypedProcedureDef", values["generated"]
        )
        state.loop_carrier_metadata_by_name[prefix] = cast(
            "LoopStateCarrierMetadata", values["loop_name"]
        )
        state.loop_carrier_metadata_by_expr_key.setdefault(expr_key, {})[
            signature
        ] = cast("LoopStateCarrierMetadata", values["loop_expr"])
        state.parametric_specialization_requests[prefix] = cast(
            "PendingParametricProcedureSpecialization",
            values["specialization"],
        )

    def nested_probe(*args, **kwargs):
        nonlocal depth, mutation
        if depth == 0:
            depth = 1
            try:
                mutation = "success"
                typecheck_expression(
                    _session_expression('"nested"', compiler_session),
                    type_env=type_env,
                    value_env={},
                    compiler_session=compiler_session,
                )
                assert set(state.generated_local_procedures) == {
                    "outer",
                    "success",
                }
                assert set(state.loop_carrier_metadata_by_name) == {
                    "outer",
                    "success",
                }
                assert set(state.loop_carrier_metadata_by_expr_key) == {
                    outer_expr_key,
                    success_expr_key,
                }
                assert set(state.parametric_specialization_requests) == {
                    "outer",
                    "success",
                }

                mutation = "failure"
                with pytest.raises(LispFrontendCompileError):
                    typecheck_expression(
                        _session_expression("missing-nested", compiler_session),
                        type_env=type_env,
                        value_env={},
                        compiler_session=compiler_session,
                    )
            finally:
                mutation = ""
                depth = 0
            assert "failure" not in state.generated_local_procedures
            assert "failure" not in state.loop_carrier_metadata_by_name
            assert failure_expr_key not in state.loop_carrier_metadata_by_expr_key
            assert "failure" not in state.parametric_specialization_requests
        elif mutation == "success":
            mutate_roots("success", success_values, success_expr_key)
        elif mutation == "failure":
            mutate_roots("failure", failure_values, failure_expr_key)
        return original_typecheck(*args, **kwargs)

    monkeypatch.setattr(typecheck_dispatch, "_typecheck", nested_probe)
    typecheck_expression(
        _session_expression('"outer"', compiler_session),
        type_env=type_env,
        value_env={},
        compiler_session=compiler_session,
    )

    assert state.generated_local_procedures["success"] is success_values[
        "generated"
    ]
    assert state.loop_carrier_metadata_by_name["success"] is success_values[
        "loop_name"
    ]
    assert (
        state.loop_carrier_metadata_by_expr_key[success_expr_key][signature]
        is success_values["loop_expr"]
    )
    assert (
        state.parametric_specialization_requests["success"]
        is success_values["specialization"]
    )


@pytest.mark.parametrize(
    "root_name",
    [
        "generated_local_procedures",
        "loop_carrier_metadata_by_name",
        "loop_carrier_metadata_by_expr_key",
        "parametric_specialization_requests",
    ],
)
def test_nested_typecheck_rejects_ambiguous_output_collisions(
    root_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp import typecheck_dispatch
    from orchestrator.workflow_lisp.compiler_session import CompilerSession
    from orchestrator.workflow_lisp.typecheck_dispatch import typecheck_expression

    compiler_session = CompilerSession()
    state = compiler_session.typecheck
    type_env = _session_type_env(compiler_session)
    old_value = object()
    new_value = object()
    expr_key = ("collision", 1, 1, ("collision",))
    signature = (("value", "String"),)
    if root_name == "loop_carrier_metadata_by_expr_key":
        state.loop_carrier_metadata_by_expr_key = {
            expr_key: {
                signature: cast("LoopStateCarrierMetadata", old_value)
            }
        }
    else:
        setattr(state, root_name, {"collision": old_value})
    original_typecheck = typecheck_dispatch._typecheck

    def collide(*args, **kwargs):
        if root_name == "loop_carrier_metadata_by_expr_key":
            state.loop_carrier_metadata_by_expr_key[expr_key][
                signature
            ] = cast("LoopStateCarrierMetadata", new_value)
        else:
            getattr(state, root_name)["collision"] = new_value
        return original_typecheck(*args, **kwargs)

    monkeypatch.setattr(typecheck_dispatch, "_typecheck", collide)
    with pytest.raises(
        RuntimeError,
        match=f"typecheck session output collision.*{root_name}",
    ):
        typecheck_expression(
            _session_expression('"collision"', compiler_session),
            type_env=type_env,
            value_env={},
            compiler_session=compiler_session,
        )

    if root_name == "loop_carrier_metadata_by_expr_key":
        assert (
            state.loop_carrier_metadata_by_expr_key[expr_key][signature]
            is old_value
        )
    else:
        assert getattr(state, root_name)["collision"] is old_value


def test_nested_typecheck_accepts_same_specialization_from_new_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    from orchestrator.workflow_lisp import typecheck_dispatch
    from orchestrator.workflow_lisp.compiler_session import CompilerSession
    from orchestrator.workflow_lisp.procedure_typecheck import (
        PendingParametricProcedureSpecialization,
    )
    from orchestrator.workflow_lisp.typecheck_dispatch import typecheck_expression

    compiler_session = CompilerSession()
    state = compiler_session.typecheck
    type_env = _session_type_env(compiler_session)
    original_request = PendingParametricProcedureSpecialization(
        base_name="base",
        specialized_name="specialized",
        type_bindings={},
        proc_ref_bindings={},
        shared_union_field_capabilities=(),
        remaining_params=(),
        origin_span=object(),
        origin_form_path=("first",),
    )
    completed_request = replace(
        original_request,
        origin_span=object(),
        origin_form_path=("second",),
    )
    state.parametric_specialization_requests = {
        "specialized": original_request
    }
    original_typecheck = typecheck_dispatch._typecheck

    def request_again(*args, **kwargs):
        state.parametric_specialization_requests[
            "specialized"
        ] = completed_request
        return original_typecheck(*args, **kwargs)

    monkeypatch.setattr(typecheck_dispatch, "_typecheck", request_again)
    typecheck_expression(
        _session_expression('"ok"', compiler_session),
        type_env=type_env,
        value_env={},
        compiler_session=compiler_session,
    )

    assert (
        state.parametric_specialization_requests["specialized"]
        is completed_request
    )


def test_typecheck_expression_has_one_compiler_session_owner() -> None:
    from orchestrator.workflow_lisp.typecheck_dispatch import typecheck_expression

    assert "session_state" not in inspect.signature(typecheck_expression).parameters


def test_procedure_typecheck_entrypoints_have_one_compiler_session_owner() -> None:
    from orchestrator.workflow_lisp.compiler import (
        _typecheck_procedure_definitions,
    )
    from orchestrator.workflow_lisp.procedure_typecheck import (
        typecheck_procedure_definitions,
    )

    assert (
        "session_state"
        not in inspect.signature(typecheck_procedure_definitions).parameters
    )
    assert (
        "session_state"
        not in inspect.signature(_typecheck_procedure_definitions).parameters
    )


def test_procedure_typecheck_recursion_uses_its_compiler_session_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp import typecheck_dispatch

    source_path = tmp_path / "procedure-session.orc"
    _write_module(
        source_path,
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defproc echo
    ((value String))
    -> String
    :effects ()
    :lowering inline
    (let* ((copy value)) copy))
  (defworkflow run () -> String (echo "ok")))
""",
    )
    original_typecheck = typecheck_dispatch._typecheck
    seen_owners: list[object] = []
    seen_states: list[object] = []

    def capture_identity(*args, **kwargs):
        seen_owners.append(kwargs["compiler_session"])
        seen_states.append(kwargs["session_state"])
        assert kwargs["session_state"] is kwargs["compiler_session"].typecheck
        return original_typecheck(*args, **kwargs)

    monkeypatch.setattr(typecheck_dispatch, "_typecheck", capture_identity)
    compile_stage3_module(
        source_path,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert seen_owners
    assert len({id(owner) for owner in seen_owners}) == 1
    assert len({id(state) for state in seen_states}) == 1


def test_generated_and_specialization_operations_require_active_session() -> None:
    from orchestrator.workflow_lisp.compiler_session import CompilerSession
    from orchestrator.workflow_lisp.procedure_typecheck import (
        consume_parametric_specialization_requests,
        reset_parametric_specialization_requests,
    )
    from orchestrator.workflow_lisp.typecheck_context import (
        consume_generated_local_procedures,
        reset_generated_local_procedure_state,
    )

    for operation in (
        consume_parametric_specialization_requests,
        reset_parametric_specialization_requests,
        consume_generated_local_procedures,
        reset_generated_local_procedure_state,
    ):
        parameters = inspect.signature(operation).parameters
        parameter_name = "state" if "state" in parameters else "session_state"
        parameter = parameters[parameter_name]
        assert parameter.default is inspect.Parameter.empty

    state = CompilerSession().typecheck
    request = cast("PendingParametricProcedureSpecialization", object())
    state.parametric_specialization_requests = {"request": request}
    assert consume_parametric_specialization_requests(state) == (request,)
    assert state.parametric_specialization_requests == {}
    state.parametric_specialization_requests = {"request": request}
    reset_parametric_specialization_requests(state)
    assert state.parametric_specialization_requests == {}


def test_compiler_session_annotations_use_stable_concrete_types() -> None:
    from orchestrator.workflow_lisp.compiler_session import (
        ElaborationSessionState,
        TypecheckSessionState,
    )

    annotations = {
        **ElaborationSessionState.__annotations__,
        **TypecheckSessionState.__annotations__,
    }
    assert all("Any" not in annotation for annotation in annotations.values())
    for field_name, type_name in {
        "prompt_catalog": "PromptCatalog",
        "function_catalog": "FunctionCatalog",
        "proc_ref_value_env": "ResolvedProcRefValue",
        "value_expr_env": "ExprNode",
        "loop_context": "LoopTypecheckContext",
        "generated_local_procedures": "TypedProcedureDef",
        "let_proc_rewrite_results": "ExprNode",
        "workflow_signature": "WorkflowSignature",
        "procedure_hidden_context_signature": "ProcedureSignature",
        "shared_union_field_capabilities": "SharedUnionFieldCapability",
        "loop_carrier_metadata_by_name": "LoopStateCarrierMetadata",
        "parametric_specialization_requests": (
            "PendingParametricProcedureSpecialization"
        ),
    }.items():
        assert type_name in annotations[field_name]


@pytest.mark.parametrize(
    ("relative_path", "forbidden_names"),
    [
        (
            "orchestrator/workflow_lisp/expressions.py",
            {
                "_ACTIVE_PROCEDURE_NAME_RESOLVER",
                "_ACTIVE_FUNCTION_NAME_RESOLVER",
                "_ACTIVE_WORKFLOW_NAME_RESOLVER",
                "_ACTIVE_FUNCTION_NAMES",
                "_ACTIVE_LOCAL_PROC_NAMES",
                "_ACTIVE_LOOP_BODY_DEPTH",
                "_ACTIVE_LET_PROC_DEPTH",
                "_ACTIVE_GUIDANCE_EXAMPLE",
                "_ACTIVE_TARGET_DSL_VERSION",
                "_ACTIVE_PROMPT_CATALOG",
            },
        ),
        (
            "orchestrator/workflow_lisp/typecheck_context.py",
            {"_SESSION_STATE"},
        ),
        (
            "orchestrator/workflow_lisp/loop_state.py",
            {
                "_CARRIER_METADATA_BY_NAME",
                "_CARRIER_METADATA_BY_EXPR_KEY",
            },
        ),
        (
            "orchestrator/workflow_lisp/procedure_typecheck.py",
            {"_ACTIVE_PARAMETRIC_SPECIALIZATION_REQUESTS"},
        ),
        (
            "orchestrator/workflow_lisp/lowering/control_dispatch.py",
            {"_INTRINSIC_FORM_LOWERING_COUNTS"},
        ),
    ],
)
def test_task1_owners_have_no_module_level_mutable_phase_roots(
    relative_path: str,
    forbidden_names: set[str],
) -> None:
    tree = ast.parse(Path(relative_path).read_text(encoding="utf-8"))
    assigned_names = {
        target.id
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (
            node.targets if isinstance(node, ast.Assign) else (node.target,)
        )
        if isinstance(target, ast.Name)
    }

    assert assigned_names.isdisjoint(forbidden_names)


def test_direct_module_sequential_edit_does_not_reuse_loop_carrier_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp import loop_state

    generated_names: list[str] = []
    register_generated_record_type = loop_state._register_generated_record_type

    def capture_generated_name(*args, **kwargs) -> None:
        generated_names.append(kwargs["name"])
        register_generated_record_type(*args, **kwargs)

    monkeypatch.setattr(
        loop_state,
        "_register_generated_record_type",
        capture_generated_name,
    )
    workflow_path = tmp_path / "sequential.orc"
    _write_module(
        workflow_path,
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defworkflow first () -> String
    (let* ((state (loop-state (value String "first"))))
      state.value)))
""",
    )

    compile_stage3_module(
        workflow_path,
        validate_shared=False,
        workspace_root=tmp_path,
    )
    [old_carrier_name] = sorted(set(generated_names))

    _write_module(
        workflow_path,
        f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defworkflow second ((state {old_carrier_name})) -> String "second"))
""",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            workflow_path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "type_unknown"


def test_pure_projection_only_labels_registered_loop_carriers_private() -> None:
    from orchestrator.workflow_lisp.compiler_session import CompilerSession
    from orchestrator.workflow_lisp.definitions import RecordDef
    from orchestrator.workflow_lisp.loop_state import LoopStateCarrierMetadata
    from orchestrator.workflow_lisp.lowering.pure_projection import (
        _nominal_descriptor_name,
    )
    from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
    from orchestrator.workflow_lisp.type_env import (
        FrontendTypeEnvironment,
        RecordTypeRef,
    )

    position = SourcePosition(
        path="<prelude:test-loop-carrier>",
        line=1,
        column=1,
        offset=0,
    )
    definition = RecordDef(
        name="%loop-state.shape",
        fields=(),
        span=SourceSpan(start=position, end=position),
    )
    type_ref = RecordTypeRef(
        name=definition.name,
        definition=definition,
        field_types={},
    )
    compiler_session = CompilerSession()
    type_env = FrontendTypeEnvironment(
        {type_ref.name: type_ref},
        session_state=compiler_session.typecheck,
    )

    assert (
        _nominal_descriptor_name(type_ref, type_env=type_env)
        == type_ref.name
    )

    compiler_session.typecheck.loop_carrier_metadata_by_name[type_ref.name] = (
        LoopStateCarrierMetadata(
            generated_type_name=type_ref.name,
            field_names=(),
            field_types=(),
            type_ref=type_ref,
            source_kind="seed",
        )
    )
    assert (
        _nominal_descriptor_name(type_ref, type_env=type_env)
        == "workflow_lisp/private::loop-state-carrier"
    )


def test_lowering_contexts_preserve_explicit_session_in_legacy_and_wcc_m4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp.compiler import ExternalToolBinding
    from orchestrator.workflow_lisp.compiler_session import CompilerSession
    from orchestrator.workflow_lisp.lowering import core as lowering_core
    from orchestrator.workflow_lisp.wcc import defunctionalize

    workflow_path = tmp_path / "lowering_session.orc"
    _write_module(
        workflow_path,
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defrecord Result (value String))
  (defproc echo () -> Result
    :effects ((uses-command run_echo))
    :lowering inline
    (command-result run_echo
      :argv ("python" "scripts/echo.py")
      :returns Result))
  (defworkflow run () -> Result (echo)))
""",
    )
    seen_contexts: dict[int, list[object]] = {}
    active_compile: list[int] = []
    lower_expression = lowering_core._lower_expression
    defunctionalize_body = defunctionalize._defunctionalize_body

    def capture_context(*args, **kwargs):
        [compile_index] = active_compile
        seen_contexts.setdefault(compile_index, []).append(kwargs["context"])
        return lower_expression(*args, **kwargs)

    def capture_wcc_context(*args, **kwargs):
        [compile_index] = active_compile
        seen_contexts.setdefault(compile_index, []).append(kwargs["context"])
        return defunctionalize_body(*args, **kwargs)

    monkeypatch.setattr(lowering_core, "_lower_expression", capture_context)
    monkeypatch.setattr(
        defunctionalize,
        "_defunctionalize_body",
        capture_wcc_context,
    )
    sessions = [CompilerSession() for _ in range(4)]
    routes = ("legacy", "wcc_m4", "legacy", "wcc_m4")

    for compile_index, (route, compiler_session) in enumerate(
        zip(routes, sessions, strict=True)
    ):
        active_compile[:] = [compile_index]
        compile_stage3_module(
            workflow_path,
            command_boundaries={
                "run_echo": ExternalToolBinding(
                    name="run_echo",
                    stable_command=("python", "scripts/echo.py"),
                )
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route=route,
            compiler_session=compiler_session,
        )

    assert set(seen_contexts) == {0, 1, 2, 3}
    for compile_index, compiler_session in enumerate(sessions):
        contexts = seen_contexts[compile_index]
        assert contexts
        assert len({id(context) for context in contexts}) >= 2
        assert {
            id(context.lowering_session)
            for context in contexts
        } == {id(compiler_session.lowering)}
    assert len({id(session.lowering) for session in sessions}) == 4


def test_intrinsic_counts_are_session_local_and_do_not_change_artifacts(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.compiler_session import CompilerSession
    from orchestrator.workflow_lisp.lowering.control_dispatch import (
        intrinsic_form_lowering_counts,
    )

    workflow_path = tmp_path / "intrinsic_artifact.orc"
    _write_module(
        workflow_path,
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule intrinsic_artifact)
  (import std/context :only (PhaseCtx))
  (defrecord Result
    (phase_name Symbol)
    (state_root Path.state-root))
  (defworkflow run
    ((phase-ctx PhaseCtx))
    -> Result
    (with-phase phase-ctx session-phase
      (record Result
        :phase_name phase-ctx.phase-name
        :state_root phase-ctx.state-root))))
""",
    )
    first_session = CompilerSession()
    second_session = CompilerSession()

    first = compile_stage3_module(
        workflow_path,
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="legacy",
        compiler_session=first_session,
    )
    assert intrinsic_form_lowering_counts(first_session.lowering) == {
        "with-phase": 1
    }
    assert intrinsic_form_lowering_counts(second_session.lowering) == {}

    second = compile_stage3_module(
        workflow_path,
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="legacy",
        compiler_session=second_session,
    )

    assert intrinsic_form_lowering_counts(first_session.lowering) == {
        "with-phase": 1
    }
    assert intrinsic_form_lowering_counts(second_session.lowering) == {
        "with-phase": 1
    }
    assert [
        lowered.authored_mapping for lowered in first.lowered_workflows
    ] == [
        lowered.authored_mapping for lowered in second.lowered_workflows
    ]


def test_direct_module_compile_uses_fresh_lowering_session_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp import compiler
    from orchestrator.workflow_lisp.compiler import ExternalToolBinding
    from orchestrator.workflow_lisp.compiler_session import CompilerSession

    class InjectedLoweringFailure(Exception):
        pass

    workflow_path = tmp_path / "direct_fresh_lowering.orc"
    _write_module(
        workflow_path,
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defrecord Result (value String))
  (defworkflow run () -> Result
    (command-result run_value
      :argv ("python" "scripts/value.py")
      :returns Result)))
""",
    )
    seen_sessions: list[CompilerSession] = []
    lower_workflows_for_route = compiler._lower_workflows_for_route

    def capture_session(*, compiler_session: CompilerSession, **kwargs):
        seen_sessions.append(compiler_session)
        if len(seen_sessions) == 1:
            raise InjectedLoweringFailure
        return lower_workflows_for_route(
            compiler_session=compiler_session,
            **kwargs,
        )

    monkeypatch.setattr(
        compiler,
        "_lower_workflows_for_route",
        capture_session,
    )

    with pytest.raises(InjectedLoweringFailure):
        compile_stage3_module(
            workflow_path,
            command_boundaries={
                "run_value": ExternalToolBinding(
                    name="run_value",
                    stable_command=("python", "scripts/value.py"),
                )
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="legacy",
        )
    compile_stage3_module(
        workflow_path,
        command_boundaries={
            "run_value": ExternalToolBinding(
                name="run_value",
                stable_command=("python", "scripts/value.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )

    assert len(seen_sessions) == 2
    assert seen_sessions[0] is not seen_sessions[1]
    assert seen_sessions[0].lowering is not seen_sessions[1].lowering


def test_build_compile_entry_uses_fresh_session_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from orchestrator.workflow_lisp import build
    from orchestrator.workflow_lisp.compiler import Stage3ValidationProfile
    from orchestrator.workflow_lisp.compiler_session import CompilerSession
    from orchestrator.workflow_lisp.wcc.route import LoweringRoute

    class InjectedBuildCompileFailure(Exception):
        pass

    capture = build.FrontendCompileRequestCapture(
        source_path=tmp_path / "entry.orc",
        workspace_root=tmp_path,
        source_roots=(tmp_path,),
        entry_workflow=None,
        validation_profile=Stage3ValidationProfile.FRONTEND_ONLY,
        lint_profile="default",
        lowering_route=LoweringRoute.LEGACY,
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        imported_workflow_bundles={},
    )
    seen_sessions: list[CompilerSession | None] = []

    def capture_compile(*args, **kwargs):
        seen_sessions.append(kwargs.get("compiler_session"))
        if len(seen_sessions) == 1:
            raise InjectedBuildCompileFailure
        return SimpleNamespace(
            graph=SimpleNamespace(
                entry_module_name="entry",
                export_surfaces_by_name={
                    "entry": SimpleNamespace(workflows_by_name={})
                },
            )
        )

    monkeypatch.setattr(build, "compile_stage3_entrypoint", capture_compile)

    with pytest.raises(InjectedBuildCompileFailure):
        build._compile_entry(capture)
    _, entry_selection = build._compile_entry(capture)

    assert all(isinstance(session, CompilerSession) for session in seen_sessions)
    assert seen_sessions[0] is not seen_sessions[1]
    assert entry_selection is None


class _InjectedPostLoweringFailure(RuntimeError):
    pass


def _assert_failure_then_success_matches_isolated_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    lowering_route: str,
) -> None:
    from orchestrator.workflow_lisp import (
        compiler,
        expressions,
        procedure_typecheck,
    )
    from orchestrator.workflow_lisp.compiler_session import CompilerSession
    from tests.workflow_lisp_command_boundaries import (
        validate_review_findings_v1_binding,
    )

    failed_source = (
        Path("tests")
        / "fixtures"
        / "workflow_lisp"
        / "valid"
        / "phase_stdlib_review_loop.orc"
    )
    final_source = tmp_path / "final_application.orc"
    _write_module(final_source, _final_application_source())
    _write_module(
        tmp_path / "final_commands.json",
        json.dumps(
            {
                "final-command": {
                    "kind": "external_tool",
                    "stable_command": ["python", "scripts/final.py"],
                }
            },
            sort_keys=True,
        )
        + "\n",
    )
    elaboration_state_ids: set[int] = set()
    specialization_names: set[str] = set()
    original_elaborate = expressions._elaborate
    original_consume = (
        procedure_typecheck.consume_parametric_specialization_requests
    )
    original_lower = compiler._lower_workflows_for_route
    failed_session: CompilerSession | None = None

    def observe_elaboration(*args, **kwargs):
        state = kwargs["session_state"]
        elaboration_state_ids.add(id(state))
        assert state.prompt_catalog is not None
        return original_elaborate(*args, **kwargs)

    def observe_specializations(session_state):
        specialization_names.update(
            session_state.parametric_specialization_requests
        )
        return original_consume(session_state)

    def fail_after_stateful_lowering(**kwargs):
        nonlocal failed_session
        lowered = original_lower(**kwargs)
        if not kwargs["typed_workflows"]:
            return lowered
        failed_session = kwargs["compiler_session"]
        assert failed_session.typecheck.loop_carrier_metadata_by_name
        assert failed_session.typecheck.loop_carrier_metadata_by_expr_key
        assert any(
            procedure.specialization is not None
            for procedure in kwargs["typed_procedures"]
        )
        if lowering_route == "legacy":
            assert (
                failed_session.lowering.intrinsic_form_lowering_counts[
                    "with-phase"
                ]
                == 1
            )
        else:
            assert (
                failed_session.lowering.intrinsic_form_lowering_counts == {}
            )
        assert lowered
        raise _InjectedPostLoweringFailure(lowering_route)

    monkeypatch.setattr(expressions, "_elaborate", observe_elaboration)
    monkeypatch.setattr(
        procedure_typecheck,
        "consume_parametric_specialization_requests",
        observe_specializations,
    )
    monkeypatch.setattr(
        compiler,
        "_lower_workflows_for_route",
        fail_after_stateful_lowering,
    )

    with pytest.raises(_InjectedPostLoweringFailure):
        compile_stage3_module(
            failed_source,
            provider_externs={
                "providers.review": "fake-review",
                "providers.fix": "fake-fix",
            },
            prompt_externs={
                "prompts.implementation.review": (
                    "prompts/implementation/review.md"
                ),
                "prompts.implementation.fix": (
                    "prompts/implementation/fix.md"
                ),
            },
            command_boundaries={
                "validate_review_findings_v1": (
                    validate_review_findings_v1_binding()
                )
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route=lowering_route,
        )

    assert failed_session is not None
    assert len(elaboration_state_ids) == 1
    assert specialization_names

    # Restore the injected failure seam, but deliberately retain no compiler
    # state cleanup between the failed compile and the next public build.
    monkeypatch.setattr(
        compiler,
        "_lower_workflows_for_route",
        original_lower,
    )
    actual = _compiled_artifact_snapshot(
        final_source,
        tmp_path,
        lowering_route,
    )
    isolated = _isolated_compiled_artifact_snapshot(
        final_source,
        tmp_path,
        lowering_route,
    )

    assert actual == isolated
    serialized = json.dumps(actual, sort_keys=True)
    assert "phase_stdlib_review_loop" not in serialized
    assert "review-revise-loop" not in serialized
    assert "%loop-state." not in serialized
    assert "%parametric_call." not in serialized
    assert "with-phase" not in serialized
    assert "CompilerSession" not in serialized
    assert "intrinsic_form_lowering_counts" not in serialized
    assert (
        failed_session.lowering.intrinsic_form_lowering_counts
        == (
            {"with-phase": 1}
            if lowering_route == "legacy"
            else {}
        )
    )


def test_legacy_failure_reentrancy_matches_isolated_success_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_failure_then_success_matches_isolated_control(
        tmp_path,
        monkeypatch,
        lowering_route="legacy",
    )


def test_wcc_m4_failure_reentrancy_matches_isolated_success_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_failure_then_success_matches_isolated_control(
        tmp_path,
        monkeypatch,
        lowering_route="wcc_m4",
    )


def _library_only_source(procedure_name: str) -> str:
    return f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule library_only)
  (export {procedure_name})
  (defproc {procedure_name}
    ((value String))
    -> String
    :effects ()
    :lowering inline
    value))
"""


def _multi_export_application_source() -> str:
    return """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule multi_export)
  (export first selected)
  (defworkflow first () -> String "first")
  (defworkflow selected () -> String "selected"))
"""


def test_application_selection_reentrancy_does_not_bleed_into_library_build(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp import build

    application_path = tmp_path / "multi_export.orc"
    library_path = tmp_path / "library_only.orc"
    _write_module(application_path, _multi_export_application_source())
    _write_module(library_path, _library_only_source("library-helper"))
    application_request = build.FrontendBuildRequest(
        source_path=application_path,
        source_roots=(tmp_path,),
        entry_workflow="selected",
        workspace_root=tmp_path,
    )
    library_request = build.FrontendBuildRequest(
        source_path=library_path,
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
    )

    library_reverse_control = build.build_frontend_bundle_in_memory(
        library_request
    )
    application_after_library = build.build_frontend_bundle_in_memory(
        application_request
    )
    application = build.build_frontend_bundle_in_memory(application_request)
    library_after_application = build.build_frontend_bundle_in_memory(
        library_request
    )

    assert application.entry_selection is not None
    assert application.entry_selection.requested_name == "selected"
    assert application.entry_selection.selected_name == (
        "multi_export::selected"
    )
    assert application.selected_workflow_name == "multi_export::selected"
    for library in (library_after_application, library_reverse_control):
        assert library.entry_selection is None
        assert library.selected_workflow_name is None
        assert library.validated_bundle is None
        assert library.fingerprint is None
        assert library.source_map_payload is None
        assert library.semantic_ir_payload is None
        assert library.executable_ir_payload is None
        assert library.runtime_plan_payload is None
        assert library.diagnostics == ()
        assert set(library.compile_result.compiled_results_by_name) == {
            "library_only"
        }
        assert set(
            library.compile_result.entry_result
            .procedure_catalog.signatures_by_name
        ) == {
            "library-helper",
            "library_only::library-helper",
        }
        assert (
            library.compile_result.entry_result
            .workflow_catalog.signatures_by_name
            == {}
        )
    assert (
        build._serialize_typed_frontend_ast(
            library_after_application.compile_result
        )
        == build._serialize_typed_frontend_ast(
            library_reverse_control.compile_result
        )
    )
    assert application_after_library.entry_selection == (
        application.entry_selection
    )
    assert application_after_library.selected_workflow_name == (
        "multi_export::selected"
    )
