from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.build_manifest_io import _json_data
from orchestrator.workflow_lisp.command_boundaries import (
    PROMOTED_CALL_REQUIRED_METADATA_FIELDS,
    CertifiedAdapterBinding,
    CertifiedAdapterInputField,
)
from orchestrator.workflow_lisp.conditionals import (
    BoolRefCondition,
    LiteralBoolCondition,
    PureExprCondition,
    _contains_effect,
    _normalize_loop_body,
    _normalize_operand,
    prepare_closed_condition_expr,
)
from orchestrator.workflow_lisp.expression_traversal import iter_child_exprs, map_expr, walk_expr
from orchestrator.workflow_lisp.functions import _normalize_expr
from orchestrator.workflow_lisp.expressions import (
    CallExpr,
    FunctionCallExpr,
    IfExpr,
    LetStarExpr,
    LoopRecurExpr,
    LiteralExpr,
    NameExpr,
    ProcRefLiteralExpr,
    PureOpExpr,
    RecordExpr,
)
from orchestrator.workflow_lisp.procedure_typecheck import (
    _collect_proc_ref_use_spans,
    _semantic_identity,
)
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
from orchestrator.workflow_lisp.wcc.hygiene import _strings
from orchestrator.workflow_lisp.wcc.model import (
    WCC_M4_ROUTE_SCHEMA_VERSION,
    WccCase,
    WccCall,
    WccJoin,
    WccIf,
    WccLoopContinue,
    WccLoopDone,
    WccLet,
    WccFieldAccessAtom,
    WccLiteralAtom,
    WccNameAtom,
    WccOpaqueFrontendValue,
    WccPhaseTargetAtom,
    WccPerform,
    WccPureOp,
    WccRecordAtom,
    WccRecJoin,
    WccSelect,
    WccIdentityFactory,
)
from orchestrator.workflow_lisp.wcc.use_site_scope import rename_capturing_binders
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


_SOURCE = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/closed_elaboration)
  (export run)
  (defrecord Box (n Int))
  (defproc inc ((n Int)) -> Int
    :effects ((uses-command inc))
    :lowering inline
    (command-result inc :argv ("python" "probe.py" n) :returns Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "probe.py" n) :returns Box))
  (defworkflow run () -> Box
    (fetch (inc 4))))
'''
_COMMANDS = {
    name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
    for name in ("inc", "fetch")
}


def _compile_and_elaborate(
    tmp_path: Path,
    *,
    source: str = _SOURCE,
    module: str = "cp/closed_elaboration",
    commands: dict[str, ExternalToolBinding] = _COMMANDS,
    entry_workflow: str = "run",
    closed_program: bool = True,
):
    source = source.replace("TARGET", EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION)
    path = (tmp_path / Path(*module.split("/"))).with_suffix(".orc")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    typed = compile_typed_program(
        path,
        entry_workflow=entry_workflow,
        source_roots=(tmp_path,),
        command_boundaries=commands,
        workspace_root=tmp_path,
    )
    path.unlink()
    entry = typed.entry
    body = elaborate_typed_workflow_body(
        entry.typed_body,
        owner_name=entry.definition.name,
        type_env=typed.workflow_type_env(entry.definition.name),
        value_env=dict(entry.signature.params),
        workflow_return_types={
            name: workflow.signature.return_type_ref
            for name, workflow in typed.workflows.items()
        },
        procedure_return_types={
            name: procedure.signature.return_type_ref
            for name, procedure in typed.procedures.items()
        },
        resolved_procedures_by_name=typed.procedures,
        procedure_type_envs=typed.procedure_type_envs,
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
        closed_program=closed_program,
    )
    return normalize_wcc_body_to_anf(body)


def _let_chain(body):
    lets = []
    while isinstance(body, WccLet):
        lets.append(body)
        body = body.body
    return lets


def _walk_wcc(node):
    if isinstance(node, (tuple, list)):
        for item in node:
            yield from _walk_wcc(item)
    elif is_dataclass(node) and not isinstance(node, type):
        yield node
        for field in fields(node):
            if field.name != "metadata":
                yield from _walk_wcc(getattr(node, field.name))


def _continues_owned_by(loop):
    def visit(node):
        if isinstance(node, WccRecJoin):
            return
        if isinstance(node, WccLoopContinue):
            yield node
            return
        if isinstance(node, (tuple, list)):
            for item in node:
                yield from visit(item)
        elif is_dataclass(node) and not isinstance(node, type):
            for field in fields(node):
                if field.name != "metadata":
                    yield from visit(getattr(node, field.name))

    yield from visit(loop.body)


def test_effectful_procedure_argument_is_bound_before_its_call_in_source_order(
    tmp_path: Path,
) -> None:
    body = _compile_and_elaborate(tmp_path)

    lets = _let_chain(body)
    calls = [let for let in lets if isinstance(let.bound_value, WccCall)]
    assert [let.bound_value.callee_name for let in calls] == [
        "cp/closed_elaboration::inc",
        "cp/closed_elaboration::fetch",
    ]
    assert isinstance(calls[1].bound_value.args[0], WccNameAtom)
    argument_binding = next(
        let
        for let in lets
        if let.bound_name == calls[1].bound_value.args[0].name
    )
    assert isinstance(argument_binding.bound_value, WccNameAtom)
    assert argument_binding.bound_value.name == calls[0].bound_name


def test_closed_command_adapter_inputs_bind_effectful_values_before_perform(
    tmp_path: Path,
) -> None:
    source = '''(workflow-lisp
      (:language "0.1")
      (:target-dsl "TARGET")
      (defmodule cp/closed_elaboration)
      (export run)
      (defpath WorkReport :kind relpath :under "artifacts/work" :must-exist true)
      (defrecord ImplementationSummary (report WorkReport))
      (defproc make-report ((n Int)) -> WorkReport
        :effects ((uses-command report))
        :lowering inline
        (command-result report :argv ("python" "report.py" n) :returns WorkReport))
      (defworkflow run ((review WorkReport)) -> ImplementationSummary
        (command-result normalize_result
          :adapter normalize_result
          :inputs ((execution_report (make-report 7)) (review_report review))
          :returns ImplementationSummary)))'''
    commands = {
        "report": ExternalToolBinding(
            name="report",
            stable_command=("python", "report.py"),
        ),
        "normalize_result": CertifiedAdapterBinding(
            name="normalize_result",
            stable_command=("python", "scripts/normalize_result.py"),
            input_contract={"type": "object"},
            output_type_name="ImplementationSummary",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("normalize_result_ok",),
            negative_fixture_ids=("normalize_result_bad",),
            behavior_class="structured_result",
            input_signature=(
                CertifiedAdapterInputField(
                    name="execution_report",
                    type_name="WorkReport",
                    required=True,
                    transport_key="execution_report",
                ),
                CertifiedAdapterInputField(
                    name="review_report",
                    type_name="WorkReport",
                    required=True,
                    transport_key="review_report",
                ),
            ),
            artifact_contracts=("implementation_summary_report",),
            error_codes=("normalize_result_invalid_payload",),
            owner_module="std/phase",
            invocation_protocol="json_object_positional_arg",
            declared_promoted_fields=PROMOTED_CALL_REQUIRED_METADATA_FIELDS,
        ),
    }
    body = _compile_and_elaborate(
        tmp_path,
        source=source,
        commands=commands,
    )

    lets = _let_chain(body)
    argument_binding = next(
        let
        for let in lets
        if isinstance(let.bound_value, WccCall)
        and let.bound_value.callee_name == "cp/closed_elaboration::make-report"
    )
    adapter_binding = next(
        let for let in lets if isinstance(let.bound_value, WccPerform)
    )
    assert adapter_binding.bound_value.perform_kind == "command_result"
    inputs = dict(adapter_binding.bound_value.operation_payload["adapter_inputs"])
    input_value = inputs["execution_report"]
    assert isinstance(input_value, WccNameAtom)
    input_binding = next(let for let in lets if let.bound_name == input_value.name)
    assert isinstance(input_binding.bound_value, WccNameAtom)
    assert input_binding.bound_value.name == argument_binding.bound_name
    assert lets.index(argument_binding) < lets.index(input_binding) < lets.index(
        adapter_binding
    )

    with pytest.raises(
        TypeError,
        match="unsupported WCC elaboration node: ProcedureCallExpr",
    ):
        _compile_and_elaborate(
            tmp_path,
            source=source,
            commands=commands,
            closed_program=False,
        )


def test_closed_run_ref_inputs_bind_effectful_values_before_perform(
    tmp_path: Path,
) -> None:
    source = '''(workflow-lisp
      (:language "0.1")
      (:target-dsl "TARGET")
      (defmodule cp/closed_elaboration)
      (export run)
      (defpath WorkReport :kind relpath :under "artifacts/work" :must-exist true)
      (defproc make-report ((n Int)) -> WorkReport
        :effects ((uses-command report))
        :lowering inline
        (command-result report :argv ("python" "report.py" n) :returns WorkReport))
      (defworkflow child ((payload WorkReport)) -> WorkReport payload)
      (defworkflow run ((n Int)) -> WorkReport
        (let* ((trial
                 (run-ref
                   :source (:repo "file:///workspace"
                            :commit "0123456789abcdef0123456789abcdef01234567")
                   :program (:bundle child)
                   :inputs (:payload (make-report n))
                   :policy (:setup ()))))
          trial.value)))'''
    body = _compile_and_elaborate(
        tmp_path,
        source=source,
        commands={
            "report": ExternalToolBinding(
                name="report",
                stable_command=("python", "report.py"),
            )
        },
    )

    lets = _let_chain(body)
    argument_binding = next(
        let
        for let in lets
        if isinstance(let.bound_value, WccCall)
        and let.bound_value.callee_name == "cp/closed_elaboration::make-report"
    )
    run_ref_binding = next(
        let
        for let in lets
        if isinstance(let.bound_value, WccPerform)
        and let.bound_value.perform_kind == "run_ref"
    )
    assert lets.index(argument_binding) < lets.index(run_ref_binding)
    payload = dict(run_ref_binding.bound_value.keyword_args)["payload"]
    assert isinstance(payload, WccNameAtom)
    input_binding = next(let for let in lets if let.bound_name == payload.name)
    assert isinstance(input_binding.bound_value, WccNameAtom)
    assert input_binding.bound_value.name == argument_binding.bound_name
    assert lets.index(argument_binding) < lets.index(input_binding) < lets.index(
        run_ref_binding
    )


_DONE_SOURCE = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/closed_elaboration)
  (export run)
  (defproc inc ((n Int)) -> Int
    :effects ((uses-command inc))
    :lowering inline
    (command-result inc :argv ("python" "probe.py" n) :returns Int))
  (defworkflow run () -> Int
    (loop/recur :max 3
      :state (loop-state (i Int 0))
      :on-exhausted state.i
      (fn (state) (done (inc state.i))))))
'''


def test_effectful_done_result_is_bound_before_the_loop_done_node(tmp_path: Path) -> None:
    body = _compile_and_elaborate(tmp_path, source=_DONE_SOURCE)

    loop = next(node for node in _walk_wcc(body) if isinstance(node, WccRecJoin))
    done = next(node for node in _walk_wcc(loop.body) if isinstance(node, WccLoopDone))
    assert isinstance(done.result, WccNameAtom)
    result_binding = next(
        let
        for let in _let_chain(loop.body)
        if let.bound_name == done.result.name
    )
    assert isinstance(result_binding.bound_value, WccCall)
    assert result_binding.bound_value.callee_name == "cp/closed_elaboration::inc"


_DONE_MATCH_SOURCE = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/closed_elaboration)
  (export run)
  (defunion Outcome (SMALL (n Int)) (LARGE (n Int)))
  (defworkflow run ((item Outcome)) -> Int
    (loop/recur :max 3
      :state (loop-state (i Int 0))
      :on-exhausted state.i
      (fn (state)
        (done (match item
                ((SMALL small) small.n)
                ((LARGE large) large.n)))))))
'''


def test_match_done_result_is_bound_before_the_loop_done_node(tmp_path: Path) -> None:
    body = _compile_and_elaborate(tmp_path, source=_DONE_MATCH_SOURCE)

    loop = next(node for node in _walk_wcc(body) if isinstance(node, WccRecJoin))
    done = next(node for node in _walk_wcc(loop.body) if isinstance(node, WccLoopDone))
    assert isinstance(done.result, WccNameAtom)
    join = next(node for node in _walk_wcc(loop.body) if isinstance(node, WccJoin))
    assert [param.name for param in join.params] == [done.result.name]
    assert any(isinstance(node, WccCase) for node in _walk_wcc(join.body))


def test_closed_entry_elaborates_admitted_older_target_imported_helper(
    tmp_path: Path,
) -> None:
    helper = tmp_path / "older.orc"
    helper.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.24")
          (defmodule older) (export get Box)
          (defrecord Box (n Int))
          (defunion Choice (Ready (value Box)) (Empty))
          (defproc fetch ((n Int)) -> Box
            :effects ((uses-command fetch))
            :lowering inline
            (command-result fetch :argv ("python" "probe.py" n) :returns Box))
          (defproc get ((n Int)) -> Box
            :effects ((uses-command fetch))
            :lowering inline
            (match (let* ((v (fetch n))) (variant Choice Ready :value v))
              ((Ready r) r.value)
              ((Empty e) (record Box :n 0)))))''',
        encoding="utf-8",
    )
    entry = tmp_path / "entry.orc"
    entry.write_text(
        f'''(workflow-lisp (:language "0.1")
          (:target-dsl "{EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")
          (defmodule entry)
          (import older :only (get Box))
          (export run)
          (defworkflow run () -> Box (get 1)))''',
        encoding="utf-8",
    )
    typed = compile_typed_program(
        entry,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={
            "fetch": ExternalToolBinding(
                name="fetch",
                stable_command=("python", "probe.py"),
            )
        },
        workspace_root=tmp_path,
    )
    procedure = typed.procedures["older::get"]
    arguments = dict(
        owner_name=procedure.definition.name,
        type_env=typed.procedure_type_env(procedure),
        value_env=dict(procedure.signature.params),
        workflow_return_types={
            name: workflow.signature.return_type_ref
            for name, workflow in typed.workflows.items()
        },
        procedure_return_types={
            name: item.signature.return_type_ref
            for name, item in typed.procedures.items()
            if not item.signature.type_params
        },
        resolved_procedures_by_name=typed.procedures,
        procedure_type_envs=typed.procedure_type_envs,
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )

    with pytest.raises(TypeError, match="unsupported nested WCC M2 prefix"):
        elaborate_typed_workflow_body(procedure.typed_body, **arguments)

    body = normalize_wcc_body_to_anf(
        elaborate_typed_workflow_body(
            procedure.typed_body,
            closed_program=True,
            **arguments,
        )
    )
    assert any(isinstance(node, WccCase) for node in _walk_wcc(body))
    assert any(
        isinstance(node, WccLet) and isinstance(node.bound_value, WccCall)
        for node in _walk_wcc(body)
    )
    assert not any(
        isinstance(node, WccOpaqueFrontendValue) and _contains_effect(node.expr)
        for node in _walk_wcc(body)
    )


_CLOSED_FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "closed_program"


def test_loop_continues_under_join_name_their_loop(tmp_path: Path) -> None:
    source = (_CLOSED_FIXTURES / "arms_in_loop.orc").read_text(encoding="utf-8")
    body = _compile_and_elaborate(
        tmp_path,
        source=source,
        module="cp/arms_in_loop",
        commands={"fetch": _COMMANDS["fetch"]},
    )

    loop = next(node for node in _walk_wcc(body) if isinstance(node, WccRecJoin))
    continues = tuple(_continues_owned_by(loop))
    assert any(isinstance(node, WccJoin) for node in _walk_wcc(loop.body))
    assert continues
    assert {node.target_name for node in continues} == {loop.loop_name}


def test_nested_loop_continues_keep_the_nearest_loop_target(tmp_path: Path) -> None:
    source = (_CLOSED_FIXTURES / "loop_in_loop.orc").read_text(encoding="utf-8")
    body = _compile_and_elaborate(
        tmp_path,
        source=source,
        module="cp/loop_in_loop",
        commands={"fetch": _COMMANDS["fetch"]},
    )

    loops = tuple(node for node in _walk_wcc(body) if isinstance(node, WccRecJoin))
    assert len(loops) == 2
    for loop in loops:
        continues = tuple(_continues_owned_by(loop))
        assert continues
        assert {node.target_name for node in continues} == {loop.loop_name}


_PHASE_TARGET_SOURCE = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/closed_elaboration)
  (export run)
  (defpath WorkReportTarget
    :kind relpath :under "artifacts/work" :must-exist false)
  (defpath ImplementationStateBundlePath
    :kind relpath :under "artifacts/work" :must-exist false)
  (defrecord ImplementationAttemptPhaseCtx
    (implementation_state_bundle_path ImplementationStateBundlePath)
    (execution_report_target WorkReportTarget)
    (progress_report_target WorkReportTarget))
  (defworkflow run ((ctx ImplementationAttemptPhaseCtx)) -> WorkReportTarget
    (with-phase ctx implementation (phase-target execution-report))))
'''


def test_closed_implementation_phase_target_uses_context_target_field(tmp_path: Path) -> None:
    body = _compile_and_elaborate(tmp_path, source=_PHASE_TARGET_SOURCE)

    target = next(node for node in _walk_wcc(body) if isinstance(node, WccFieldAccessAtom))
    assert target.fields == ("execution_report_target",)
    assert isinstance(target.base, WccNameAtom)
    assert target.base.name == "ctx"


_GENERIC_PHASE_TARGET_SOURCE = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/closed_elaboration)
  (import std/phase :only (with-phase))
  (export run)
  (defpath WorkReportTarget
    :kind relpath :under "artifacts/work" :must-exist false)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defworkflow run ((ctx PhaseCtx)) -> WorkReportTarget
    (with-phase ctx implementation (phase-target execution-report))))
'''


def test_closed_generic_phase_target_joins_artifact_root_and_phase_path(tmp_path: Path) -> None:
    body = _compile_and_elaborate(tmp_path, source=_GENERIC_PHASE_TARGET_SOURCE)

    target = next(node for node in _walk_wcc(body) if isinstance(node, WccPureOp))
    assert target.operator == "path/join"
    assert target.field_names == ()
    assert isinstance(target.args[0], WccFieldAccessAtom)
    assert target.args[0].fields == ("artifact-root",)
    assert isinstance(target.args[1], WccLiteralAtom)
    assert target.args[1].value == "implementation/execution-report.md"


_COMPOUND_PHASE_CONTEXT_SOURCE = _GENERIC_PHASE_TARGET_SOURCE.replace(
    "(with-phase ctx implementation (phase-target execution-report))",
    """(with-phase
      (record PhaseCtx
        :run ctx.run
        :phase-name ctx.phase-name
        :state-root ctx.state-root
        :artifact-root ctx.artifact-root)
      implementation
      (phase-target execution-report))""",
)


def test_closed_with_phase_binds_compound_context_once_before_target_use(
    tmp_path: Path,
) -> None:
    body = _compile_and_elaborate(tmp_path, source=_COMPOUND_PHASE_CONTEXT_SOURCE)

    context = next(
        node
        for node in _walk_wcc(body)
        if isinstance(node, WccLet) and isinstance(node.bound_value, WccRecordAtom)
    )
    assert context.bound_name.startswith("__wcc_effect_ctx_")
    target = next(node for node in _walk_wcc(body) if isinstance(node, WccPureOp))
    assert isinstance(target.args[0], WccFieldAccessAtom)
    assert isinstance(target.args[0].base, WccNameAtom)
    assert target.args[0].base.name == context.bound_name


def test_flag_off_keeps_the_legacy_phase_target_atom(tmp_path: Path) -> None:
    body = _compile_and_elaborate(
        tmp_path,
        source=_PHASE_TARGET_SOURCE,
        closed_program=False,
    )

    assert any(isinstance(node, WccPhaseTargetAtom) for node in _walk_wcc(body))


_SHORT_CIRCUIT_SOURCE = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/closed_elaboration)
  (export run)
  (defproc check ((n Int)) -> Bool
    :effects ((uses-command check))
    :lowering inline
    (command-result check :argv ("python" "probe.py" n) :returns Bool))
  (defworkflow run () -> Bool
    (and false (check 1))))
'''


_AND_MATCH_SHORT_CIRCUIT_SOURCE = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/closed_elaboration)
  (export run)
  (defunion Choice (A (n Int)) (B (n Int)))
  (defproc check ((n Int)) -> Bool
    :effects ((uses-command check))
    :lowering inline
    (command-result check :argv ("python" "probe.py" n) :returns Bool))
  (defworkflow run ((item Choice)) -> Bool
    (and true
      (match item
        ((A a) (check a.n))
        ((B b) (check b.n))))))
'''


def test_closed_short_circuit_uses_a_join_for_an_effectful_match_result(
    tmp_path: Path,
) -> None:
    body = _compile_and_elaborate(
        tmp_path,
        source=_AND_MATCH_SHORT_CIRCUIT_SOURCE,
        commands={
            "check": ExternalToolBinding(
                name="check",
                stable_command=("python", "probe.py"),
            )
        },
    )

    join = next(
        node
        for node in _walk_wcc(body)
        if isinstance(node, WccJoin) and isinstance(node.body, WccCase)
    )
    assert isinstance(join.continuation, WccIf)
    calls = [
        node
        for node in _walk_wcc(join.body)
        if isinstance(node, WccCall)
        and node.callee_name == "cp/closed_elaboration::check"
    ]
    assert len(calls) == 2


def test_closed_short_circuit_match_survives_let_call_done_and_loop_bindings(
    tmp_path: Path,
) -> None:
    match_expr = "(match item ((A a) (check a.n)) ((B b) (check b.n)))"
    and_expr = f"(and true {match_expr})"
    relay_source = _AND_MATCH_SHORT_CIRCUIT_SOURCE.replace(
        "  (defworkflow run",
        """  (defproc relay ((flag Bool)) -> Bool
    :effects ((uses-command relay))
    :lowering inline
    (command-result relay :argv ("python" "probe.py" flag) :returns Bool))
  (defworkflow run""",
    )
    cases = (
        (
            "let",
            _AND_MATCH_SHORT_CIRCUIT_SOURCE,
            f"(let* ((flag {and_expr})) flag)",
        ),
        (
            "call_argument",
            relay_source,
            f"(relay {and_expr})",
        ),
        (
            "done_result",
            _AND_MATCH_SHORT_CIRCUIT_SOURCE,
            "(loop/recur :max 1 :state (loop-state (v Bool false)) "
            f":on-exhausted state.v (fn (state) (done {and_expr})))",
        ),
        (
            "loop_seed",
            _AND_MATCH_SHORT_CIRCUIT_SOURCE,
            "(loop/recur :max 1 :state (loop-state (flag Bool "
            f"{and_expr})) :on-exhausted state.flag "
            "(fn (state) (done state.flag)))",
        ),
    )
    commands = {
        name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
        for name in ("check", "relay")
    }

    for name, source, body_source in cases:
        source = source.replace(
            "(and true\n      (match item\n        ((A a) (check a.n))\n        ((B b) (check b.n))))",
            body_source,
        )
        body = _compile_and_elaborate(
            tmp_path / name,
            source=source,
            commands=commands,
        )
        calls = [
            node
            for node in _walk_wcc(body)
            if isinstance(node, WccCall)
            and node.callee_name.endswith("::check")
        ]
        assert len(calls) == 2, name
        assert any(
            isinstance(node, WccJoin)
            and any(isinstance(child, WccCase) for child in _walk_wcc(node.body))
            for node in _walk_wcc(body)
        ), name
        if name == "call_argument":
            assert any(
                isinstance(node, WccCall)
                and node.callee_name.endswith("::relay")
                for node in _walk_wcc(body)
            )
        if name == "done_result":
            assert any(
                isinstance(node, WccLoopDone)
                and isinstance(node.result, WccNameAtom)
                for node in _walk_wcc(body)
            )
        if name == "loop_seed":
            loop = next(
                node for node in _walk_wcc(body) if isinstance(node, WccRecJoin)
            )
            assert not (
                isinstance(loop.initial_state, WccOpaqueFrontendValue)
                and _contains_effect(loop.initial_state.expr)
            )


def test_closed_effectful_and_keeps_right_operand_inside_lazy_arm(tmp_path: Path) -> None:
    body = _compile_and_elaborate(
        tmp_path,
        source=_SHORT_CIRCUIT_SOURCE,
        commands={"check": ExternalToolBinding(name="check", stable_command=("python", "probe.py"))},
    )

    conditional = next(node for node in _walk_wcc(body) if isinstance(node, WccIf))
    assert not any(
        isinstance(node, WccLet) and isinstance(node.bound_value, WccCall)
        for node in _let_chain(body)
    )
    assert any(
        isinstance(node, WccLet)
        and isinstance(node.bound_value, WccCall)
        and node.bound_value.callee_name == "cp/closed_elaboration::check"
        for node in _walk_wcc(conditional.then_body)
            )


_AND_LOOP_SHORT_CIRCUIT_SOURCE = _SHORT_CIRCUIT_SOURCE.replace(
    "(defworkflow run () -> Bool\n    (and false (check 1)))",
    """(defworkflow run () -> Bool
    (and true
      (loop/recur :max 2
        :state (loop-state (v Bool false))
        :on-exhausted state.v
        (fn (state) (done (check 1))))))""",
)


def test_closed_short_circuit_uses_a_join_for_a_loop_operand(tmp_path: Path) -> None:
    body = _compile_and_elaborate(
        tmp_path,
        source=_AND_LOOP_SHORT_CIRCUIT_SOURCE,
        commands={
            "check": ExternalToolBinding(
                name="check",
                stable_command=("python", "probe.py"),
            )
        },
    )

    join = next(
        node
        for node in _walk_wcc(body)
        if isinstance(node, WccJoin)
        and any(isinstance(child, WccRecJoin) for child in _walk_wcc(node.body))
    )
    assert isinstance(join.continuation, WccIf)


_CONTROL_SHORT_CIRCUIT_SOURCE = _SHORT_CIRCUIT_SOURCE.replace(
    "(defworkflow run () -> Bool\n    (and false (check 1)))",
    """(defworkflow run ((go Bool)) -> Bool
    (and (if go (check 1) (check 2)) (check 3)))""",
)


def test_closed_short_circuit_keeps_effectful_select_in_condition_position_lazy(
    tmp_path: Path,
) -> None:
    body = _compile_and_elaborate(
        tmp_path,
        source=_CONTROL_SHORT_CIRCUIT_SOURCE,
        commands={"check": ExternalToolBinding(name="check", stable_command=("python", "probe.py"))},
    )

    top_level_calls = [
        node
        for node in _let_chain(body)
        if isinstance(node.bound_value, WccCall)
    ]
    assert not top_level_calls
    control_join = next(
        node
        for node in _walk_wcc(body)
        if isinstance(node, WccJoin)
        and isinstance(node.body, WccIf)
        and isinstance(node.continuation, WccIf)
    )
    assert sum(
        isinstance(node, WccCall)
        and node.callee_name == "cp/closed_elaboration::check"
        for node in _walk_wcc(control_join.body)
    ) == 2
    assert sum(
        isinstance(node, WccCall)
        and node.callee_name == "cp/closed_elaboration::check"
        for node in _walk_wcc(control_join.continuation.then_body)
    ) == 1
    assert not any(
        isinstance(node, WccCall)
        and node.callee_name == "cp/closed_elaboration::check"
        for node in _walk_wcc(control_join.continuation.else_body)
    )
    assert sum(
        isinstance(node, WccCall)
        and node.callee_name == "cp/closed_elaboration::check"
        for node in _walk_wcc(body)
    ) == 3
    assert any(isinstance(node, WccIf) for node in _walk_wcc(body))


_SHADOWED_SHORT_CIRCUIT_SOURCE = _SHORT_CIRCUIT_SOURCE.replace(
    "(defworkflow run () -> Bool\n    (and false (check 1)))",
    """(defworkflow run () -> Bool
    (let* ((x false)) (and (let* ((x (check 1))) x) x)))""",
)


def test_closed_short_circuit_renames_condition_prefix_over_later_shadowed_operand(
    tmp_path: Path,
) -> None:
    body = _compile_and_elaborate(
        tmp_path,
        source=_SHADOWED_SHORT_CIRCUIT_SOURCE,
        commands={"check": ExternalToolBinding(name="check", stable_command=("python", "probe.py"))},
    )

    lets = _let_chain(body)
    authored_x_bindings = [let for let in lets if let.bound_name == "x"]
    check_binding = next(
        let
        for let in lets
        if isinstance(let.bound_value, WccCall)
        and let.bound_value.callee_name == "cp/closed_elaboration::check"
    )
    assert len(authored_x_bindings) == 1
    assert check_binding.bound_name != "x"
    assert any(
        isinstance(node, WccIf)
        and isinstance(node.condition, WccNameAtom)
        and node.condition.name == check_binding.bound_name
        for node in _walk_wcc(body)
    )
    selected = next(
        node for node in _walk_wcc(body) if isinstance(node, WccSelect)
    )
    assert isinstance(selected.condition, WccNameAtom)
    assert selected.condition.name == "x"


@pytest.mark.parametrize(
    ("body_source", "condition_shape_type", "expected"),
    (
        (
            "(and (let* ((ignored (check-bool 1))) false) true)",
            LiteralBoolCondition,
            False,
        ),
        (
            "(and (let* ((gate (check-gate 1))) gate.enabled) true)",
            BoolRefCondition,
            ("gate", ("enabled",)),
        ),
        (
            "(and (let* ((flag (check-bool 1))) (not flag)) true)",
            PureExprCondition,
            None,
        ),
    ),
)
def test_closed_short_circuit_classifies_the_materialized_condition_value(
    tmp_path: Path,
    body_source: str,
    condition_shape_type: type,
    expected: object,
) -> None:
    source = f'''(workflow-lisp
      (:language "0.1")
      (:target-dsl "TARGET")
      (defmodule cp/closed_elaboration)
      (export run)
      (defrecord Gate (enabled Bool))
      (defproc check-bool ((n Int)) -> Bool
        :effects ((uses-command check-bool))
        :lowering inline
        (command-result check-bool :argv ("python" "probe.py" n) :returns Bool))
      (defproc check-gate ((n Int)) -> Gate
        :effects ((uses-command check-gate))
        :lowering inline
        (command-result check-gate :argv ("python" "probe.py" n) :returns Gate))
      (defworkflow run () -> Bool {body_source}))'''
    body = _compile_and_elaborate(
        tmp_path,
        source=source,
        commands={
            name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
            for name in ("check-bool", "check-gate")
        },
    )

    conditional = next(node for node in _walk_wcc(body) if isinstance(node, WccIf))
    shape = conditional.condition_shape
    assert isinstance(shape, condition_shape_type)
    if isinstance(shape, LiteralBoolCondition):
        assert shape.value is expected
    elif isinstance(shape, BoolRefCondition):
        assert (shape.base_name, shape.fields) == expected


_BIND_PROC_CAPTURE_SOURCE = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/bind_proc_capture)
  (export run)
  (defproc add-leading ((leading Int) (value Int)) -> Int
    :effects ((uses-command add))
    :lowering inline
    (command-result add :argv ("python" "add.py" leading value) :returns Int))
  (defworkflow run () -> Int
    (let* ((b 1)
           (hook (bind-proc (proc-ref add-leading) :leading (+ b 1))))
      (let* ((b 7)) (hook 5)))))
'''


def test_closed_bind_proc_captures_effectful_outer_alias_before_shadowing(tmp_path: Path) -> None:
    body = _compile_and_elaborate(
        tmp_path,
        source=_BIND_PROC_CAPTURE_SOURCE,
        module="cp/bind_proc_capture",
        commands={"add": ExternalToolBinding(name="add", stable_command=("python", "add.py"))},
    )

    lets = _let_chain(body)
    call = next(
        let.bound_value
        for let in lets
        if isinstance(let.bound_value, WccCall)
        and let.bound_value.callee_name == "hook"
    )
    capture = next(
        capture
        for capture in call.specialization_captures
        if capture.owner_kind == "callee" and capture.source_name == "b"
    )
    alias = next(
        let
        for let in lets
        if let.bound_name == capture.value.name
    )
    first_b = next(let for let in lets if let.bound_name == "b")
    shadow_b = next(let for let in lets if let.bound_name == "b" and let is not first_b)
    assert isinstance(alias.bound_value, WccNameAtom)
    assert alias.bound_value.name == first_b.bound_name
    assert lets.index(alias) < lets.index(shadow_b)


def test_closed_program_flag_does_not_change_wcc_semantic_identity() -> None:
    from dataclasses import replace

    flat = WccIdentityFactory(owner_name="demo")
    closed = replace(flat, closed_program=True)
    position = SourcePosition(path="test.orc", line=1, column=1, offset=0)
    span = SourceSpan(start=position, end=position)

    assert flat.scope_id == closed.scope_id
    assert flat.atom_metadata(
        role="value",
        type_ref=PrimitiveTypeRef(name="Int"),
        source_span=span,
        form_path=("test",),
    ).node_id == closed.atom_metadata(
        role="value",
        type_ref=PrimitiveTypeRef(name="Int"),
        source_span=span,
        form_path=("test",),
    ).node_id
    assert closed.child_scope("child").closed_program


_LOOP_SEED_BUDGET_SOURCE = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/closed_elaboration)
  (export run)
  (defproc budget ((n Int)) -> Int
    :effects ((uses-command budget))
    :lowering inline
    (command-result budget :argv ("python" "probe.py" n) :returns Int))
  (defproc seed ((n Int)) -> Int
    :effects ((uses-command seed))
    :lowering inline
    (command-result seed :argv ("python" "probe.py" n) :returns Int))
  (defworkflow run () -> Int
    (loop/recur :max (budget 3)
      :state (loop-state (i Int (seed 0)))
      :on-exhausted state.i
      (fn (state) (done state.i)))))
'''


_MACRO_LOOP_SEED_BUDGET_SOURCE = _LOOP_SEED_BUDGET_SOURCE.replace(
    "  (defworkflow run () -> Int\n    (loop/recur :max (budget 3)\n      :state (loop-state (i Int (seed 0)))\n      :on-exhausted state.i\n      (fn (state) (done state.i))))",
    """  (defmacro loop-with-budget (initial maximum)
    (loop/recur :max maximum
      :state initial
      :on-exhausted state.i
      (fn (state) (done state.i))))
  (defworkflow run () -> Int
    (loop-with-budget
      (loop-state (i Int (seed 0)))
      (budget 3)))""",
)


def test_closed_loop_seed_and_budget_effects_are_bound_in_authored_order(
    tmp_path: Path,
) -> None:
    body = _compile_and_elaborate(
        tmp_path,
        source=_LOOP_SEED_BUDGET_SOURCE,
        commands={
            name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
            for name in ("budget", "seed")
        },
    )

    call_names = [
        node.bound_value.callee_name
        for node in _let_chain(body)
        if isinstance(node.bound_value, WccCall)
    ]
    assert call_names == [
        "cp/closed_elaboration::budget",
        "cp/closed_elaboration::seed",
    ]
    loop = next(node for node in _walk_wcc(body) if isinstance(node, WccRecJoin))
    assert not any(
        isinstance(node, WccOpaqueFrontendValue) and _contains_effect(node.expr)
        for node in _walk_wcc(loop)
    )


def test_closed_macro_loop_uses_expanded_keyword_order_over_argument_spans(
    tmp_path: Path,
) -> None:
    source = _MACRO_LOOP_SEED_BUDGET_SOURCE.replace(
        "TARGET",
        EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION,
    )
    path = (tmp_path / "cp" / "closed_elaboration.orc")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={
            name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
            for name in ("budget", "seed")
        },
        workspace_root=tmp_path,
    )
    loop = next(
        node
        for node in walk_expr(typed.entry.typed_body.expr)
        if isinstance(node, LoopRecurExpr)
    )
    assert loop.operand_evaluation_order == (":max", ":state")
    assert loop.max_iterations_expr.span.start.offset > loop.initial_state_expr.span.start.offset
    assert "operand_evaluation_order" not in repr(loop)
    assert "operand_evaluation_order" not in _json_data(loop)
    same_loop = replace(loop, operand_evaluation_order=())
    assert loop == same_loop
    assert hash(loop) == hash(same_loop)

    body = _compile_and_elaborate(
        tmp_path,
        source=_MACRO_LOOP_SEED_BUDGET_SOURCE,
        commands={
            name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
            for name in ("budget", "seed")
        },
    )

    call_names = [
        node.bound_value.callee_name
        for node in _let_chain(body)
        if isinstance(node.bound_value, WccCall)
    ]
    assert call_names == [
        "cp/closed_elaboration::budget",
        "cp/closed_elaboration::seed",
    ]


def test_condition_retained_input_stays_out_of_legacy_ast_views_and_identities(
    tmp_path: Path,
) -> None:
    source = _LOOP_IN_IF_CONDITION_SOURCE.replace(
        "TARGET",
        EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION,
    )
    path = tmp_path / "cp" / "closed_elaboration.orc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries=_COMMANDS | {
            name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
            for name in ("budget", "seed")
        },
        workspace_root=tmp_path,
    )
    ordered_let = next(
        node
        for node in walk_expr(typed.entry.typed_body.expr)
        if isinstance(node, LetStarExpr)
        and node.condition_normalization_input is not None
    )
    retained = ordered_let.condition_normalization_input
    without_input = replace(ordered_let, condition_normalization_input=None)

    assert isinstance(retained, IfExpr)
    assert any(isinstance(node, LoopRecurExpr) for node in walk_expr(retained.condition_expr))
    assert retained not in iter_child_exprs(ordered_let)
    assert repr(ordered_let) == repr(without_input)
    assert _json_data(ordered_let) == _json_data(without_input)
    assert ordered_let == without_input
    assert hash(ordered_let) == hash(without_input)
    assert _semantic_identity(ordered_let) == _semantic_identity(without_input)


def test_condition_retained_input_uses_an_isolated_hygiene_allocator() -> None:
    position = SourcePosition(path="test.orc", line=1, column=1, offset=0)
    span = SourceSpan(start=position, end=position)
    nested_retained = LetStarExpr(
        bindings=(),
        body=NameExpr(
            name="ordinary_name",
            span=span,
            form_path=("nested",),
        ),
        span=span,
        form_path=("nested",),
        condition_normalization_input=NameExpr(
            name="captured_1",
            span=span,
            form_path=("nested", "retained"),
        ),
    )
    retained = LetStarExpr(
        bindings=((
            "captured",
            NameExpr(name="captured", span=span, form_path=("retained",)),
        ),),
        body=nested_retained,
        span=span,
        form_path=("retained",),
    )
    legacy = LetStarExpr(
        bindings=((
            "captured",
            NameExpr(name="captured", span=span, form_path=("legacy",)),
        ),),
        body=NameExpr(name="captured", span=span, form_path=("legacy",)),
        span=span,
        form_path=("legacy",),
    )
    with_retained = replace(
        legacy,
        condition_normalization_input=retained,
    )
    legacy_only = replace(with_retained, condition_normalization_input=None)

    rewritten_with, _ = rename_capturing_binders(
        with_retained,
        live=frozenset({"captured"}),
    )
    rewritten_without, _ = rename_capturing_binders(
        legacy_only,
        live=frozenset({"captured"}),
    )

    assert rewritten_with.bindings[0][0] == "captured_1"
    assert rewritten_with.bindings[0][0] == rewritten_without.bindings[0][0]
    assert rewritten_with.condition_normalization_input.bindings[0][0] == "captured_2"
    assert _strings(with_retained) == _strings(legacy_only)
    assert "captured_1" in _strings(
        with_retained,
        include_condition_input=True,
    )


def test_local_proc_use_collection_observes_only_the_legacy_ast_view() -> None:
    position = SourcePosition(path="test.orc", line=1, column=1, offset=0)
    span = SourceSpan(start=position, end=position)
    legacy_reference = ProcRefLiteralExpr(
        target_name="generated/local",
        authored_name="local",
        span=span,
        form_path=("legacy",),
    )
    retained_reference = replace(legacy_reference, form_path=("retained",))
    node = LetStarExpr(
        bindings=(),
        body=legacy_reference,
        span=span,
        form_path=("let",),
        condition_normalization_input=retained_reference,
    )

    assert _collect_proc_ref_use_spans(node, authored_name="local") == (span,)


def test_retained_input_survives_repeated_let_normalization() -> None:
    position = SourcePosition(path="test.orc", line=1, column=1, offset=0)
    span = SourceSpan(start=position, end=position)
    retained = IfExpr(
        condition_expr=LiteralExpr(
            value=True,
            literal_kind="bool",
            span=span,
            form_path=("retained",),
        ),
        then_expr=LiteralExpr(
            value=True,
            literal_kind="bool",
            span=span,
            form_path=("retained", "then"),
        ),
        else_expr=LiteralExpr(
            value=False,
            literal_kind="bool",
            span=span,
            form_path=("retained", "else"),
        ),
        span=span,
        form_path=("retained",),
    )
    source = LetStarExpr(
        bindings=((
            "value",
            LiteralExpr(
                value=True,
                literal_kind="bool",
                span=span,
                form_path=("value",),
            ),
        ),),
        body=NameExpr(name="value", span=span, form_path=("body",)),
        span=span,
        form_path=("source",),
        condition_normalization_input=retained,
    )

    prefix, _ = _normalize_operand(
        source,
        path=(),
        closed_program=True,
    )
    rebuilt_once = prefix[0][1]
    _, rebuilt_twice = _normalize_loop_body(
        rebuilt_once,
        path=(),
        closed_program=True,
    )

    assert isinstance(rebuilt_once, LetStarExpr)
    assert isinstance(rebuilt_twice, LetStarExpr)
    assert rebuilt_once.condition_normalization_input is retained
    assert rebuilt_twice.condition_normalization_input is retained


def test_retained_input_maps_and_expands_helpers_in_its_incoming_scope() -> None:
    position = SourcePosition(path="caller.orc", line=1, column=1, offset=0)
    span = SourceSpan(start=position, end=position)
    helper_body = LetStarExpr(
        bindings=(),
        body=LiteralExpr(
            value=True,
            literal_kind="bool",
            span=span,
            form_path=("helper", "body"),
        ),
        span=span,
        form_path=("helper",),
        condition_normalization_input=NameExpr(
            name="helper_capture",
            span=span,
            form_path=("helper", "retained"),
        ),
    )
    function_call = FunctionCallExpr(
        callee_name="helper",
        args=(),
        span=span,
        form_path=("caller", "call"),
    )
    retained_if = IfExpr(
        condition_expr=function_call,
        then_expr=LiteralExpr(
            value=True,
            literal_kind="bool",
            span=span,
            form_path=("caller", "then"),
        ),
        else_expr=LiteralExpr(
            value=False,
            literal_kind="bool",
            span=span,
            form_path=("caller", "else"),
        ),
        span=span,
        form_path=("caller",),
    )
    source = LetStarExpr(
        bindings=((
            "helper_capture",
            LiteralExpr(
                value=True,
                literal_kind="bool",
                span=span,
                form_path=("legacy",),
            ),
        ),),
        body=NameExpr(name="helper_capture", span=span, form_path=("legacy", "body")),
        span=span,
        form_path=("legacy",),
        condition_normalization_input=retained_if,
    )

    mapper_source = replace(
        source,
        condition_normalization_input=replace(
            retained_if,
            condition_expr=NameExpr(
                name="helper_capture",
                span=span,
                form_path=("caller", "retained-name"),
            ),
        ),
    )
    mapped = map_expr(
        mapper_source,
        lambda node: LiteralExpr(
            value=False,
            literal_kind="bool",
            span=node.span,
            form_path=node.form_path,
        ),
    )
    helper = SimpleNamespace(
        definition=SimpleNamespace(name="helper", span=span),
        signature=SimpleNamespace(params=()),
        typed_body=SimpleNamespace(expr=helper_body),
    )
    expanded = _normalize_expr(
        source,
        typed_functions_by_name={"helper": helper},
        expand_admitted_containers=False,
    )

    assert isinstance(mapped, LetStarExpr)
    assert mapped.body is source.body
    assert isinstance(mapped.condition_normalization_input, IfExpr)
    assert isinstance(mapped.condition_normalization_input.condition_expr, LiteralExpr)
    assert not any(
        isinstance(node, FunctionCallExpr)
        for node in walk_expr(expanded.condition_normalization_input)
    )
    cloned_call = expanded.condition_normalization_input.condition_expr
    assert isinstance(cloned_call, LetStarExpr)
    cloned_body = cloned_call.body
    assert isinstance(cloned_body, LetStarExpr)
    assert cloned_body.condition_normalization_input.span == function_call.span
    assert cloned_body.condition_normalization_input.form_path == function_call.form_path
    assert cloned_body.condition_normalization_input.expansion_stack


def test_cross_module_inline_constructor_survives_retention_and_source_deletion(
    tmp_path: Path,
) -> None:
    target = EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
    library_path = tmp_path / "cp" / "library.orc"
    consumer_path = tmp_path / "cp" / "consumer.orc"
    library_path.parent.mkdir(parents=True, exist_ok=True)
    library_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target}")
  (defmodule cp/library)
  (export ready)
  (defrecord HiddenFlag (enabled Bool))
  (defproc ready ((value Bool)) -> Bool
    :effects ()
    :lowering inline
    (if (let* ((flag (record HiddenFlag :enabled value))) flag.enabled)
      true false)))''',
        encoding="utf-8",
    )
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target}")
  (defmodule cp/consumer)
  (import cp/library :only (ready))
  (export run)
  (defproc check ((n Int)) -> Bool
    :effects ((uses-command check))
    :lowering inline
    (command-result check :argv ("python" "probe.py" n) :returns Bool))
  (defworkflow run ((input Bool)) -> Bool
    (if (and (ready input) (check 1)) true false)))''',
        encoding="utf-8",
    )
    commands = {
        "check": ExternalToolBinding(
            name="check",
            stable_command=("python", "probe.py"),
        )
    }
    typed = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries=commands,
        workspace_root=tmp_path,
    )
    consumer_carriers = [
        node
        for node in walk_expr(typed.entry.typed_body.expr)
        if isinstance(node, LetStarExpr)
        and node.condition_normalization_input is not None
        and isinstance(node.condition_normalization_input, IfExpr)
        and isinstance(node.condition_normalization_input.condition_expr, PureOpExpr)
        and node.condition_normalization_input.condition_expr.operator == "and"
    ]
    assert len(consumer_carriers) == 1
    retained = consumer_carriers[0].condition_normalization_input

    def walk_retained(expr, *, inside_retained_input: bool = False):
        yield expr, inside_retained_input
        for child in iter_child_exprs(expr):
            yield from walk_retained(
                child,
                inside_retained_input=inside_retained_input,
            )
        if isinstance(expr, LetStarExpr) and expr.condition_normalization_input is not None:
            yield from walk_retained(
                expr.condition_normalization_input,
                inside_retained_input=True,
            )

    retained_constructors = [
        node
        for node, inside_retained_input in walk_retained(retained)
        if inside_retained_input and isinstance(node, RecordExpr)
    ]
    assert len(retained_constructors) == 1
    assert retained_constructors[0].type_name == "HiddenFlag"
    assert retained_constructors[0].resolved_type is not None
    assert retained_constructors[0].span.start.path == str(consumer_path)
    assert retained_constructors[0].expansion_stack

    selected = prepare_closed_condition_expr(typed.entry.typed_body.expr)
    assert prepare_closed_condition_expr(selected) == selected
    assert not any(
        isinstance(node, LetStarExpr)
        and node.condition_normalization_input is not None
        for node in walk_expr(selected)
    )
    library_path.unlink()
    consumer_path.unlink()

    entry = typed.entry
    body = normalize_wcc_body_to_anf(
        elaborate_typed_workflow_body(
            entry.typed_body,
            owner_name=entry.definition.name,
            type_env=typed.workflow_type_env(entry.definition.name),
            value_env=dict(entry.signature.params),
            workflow_return_types={
                name: workflow.signature.return_type_ref
                for name, workflow in typed.workflows.items()
            },
            procedure_return_types={
                name: procedure.signature.return_type_ref
                for name, procedure in typed.procedures.items()
                if not procedure.signature.type_params
            },
            resolved_procedures_by_name=typed.procedures,
            procedure_type_envs=typed.procedure_type_envs,
            route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
            closed_program=True,
        )
    )
    assert [
        node.callee_name
        for node in _walk_wcc(body)
        if isinstance(node, WccCall)
    ] == ["cp/consumer::check"]


def test_closed_procedure_argument_prebinds_a_pure_loop_under_not(
    tmp_path: Path,
) -> None:
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")
  (defmodule cp/closed_elaboration)
  (export run)
  (defproc relay ((value Bool)) -> Bool
    :effects ((uses-command relay))
    :lowering inline
    (command-result relay :argv ("python" "probe.py" value) :returns Bool))
  (defworkflow run () -> Bool
    (relay (not
      (loop/recur :max 0
        :state (loop-state (value Bool false))
        :on-exhausted false
        (fn (state) (done true)))))))'''
    body = _compile_and_elaborate(
        tmp_path,
        source=source,
        commands={
            "relay": ExternalToolBinding(
                name="relay",
                stable_command=("python", "probe.py"),
            )
        },
    )

    relay_calls = [
        node
        for node in _walk_wcc(body)
        if isinstance(node, WccCall)
        and node.callee_name == "cp/closed_elaboration::relay"
    ]
    loops = [node for node in _walk_wcc(body) if isinstance(node, WccRecJoin)]

    assert len(relay_calls) == 1
    assert len(loops) == 1
    assert isinstance(body, WccJoin)


def test_closed_procedure_argument_prebinds_a_loop_inside_record_field(
    tmp_path: Path,
) -> None:
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")
  (defmodule cp/closed_elaboration)
  (export run)
  (defrecord Box (value Bool))
  (defproc relay_box ((box Box)) -> Bool
    :effects ((uses-command relay_box))
    :lowering inline
    (command-result relay_box :argv ("python" "probe.py" box.value) :returns Bool))
  (defworkflow run () -> Bool
    (relay_box (record Box :value
      (loop/recur :max 0
        :state (loop-state (value Bool false))
        :on-exhausted false
        (fn (state) (done true)))))))'''
    body = _compile_and_elaborate(
        tmp_path,
        source=source,
        commands={
            "relay_box": ExternalToolBinding(
                name="relay_box",
                stable_command=("python", "probe.py"),
            )
        },
    )

    relay_calls = [
        node
        for node in _walk_wcc(body)
        if isinstance(node, WccCall)
        and node.callee_name == "cp/closed_elaboration::relay_box"
    ]
    loops = [node for node in _walk_wcc(body) if isinstance(node, WccRecJoin)]

    assert len(relay_calls) == 1
    assert len(loops) == 1
    assert isinstance(body, WccJoin)


_REVERSED_LOOP_SEED_BUDGET_SOURCE = _LOOP_SEED_BUDGET_SOURCE.replace(
    "(loop/recur :max (budget 3)\n      :state (loop-state (i Int (seed 0)))",
    "(loop/recur :state (loop-state (i Int (seed 0)))\n      :max (budget 3)",
)


def test_closed_loop_preserves_state_before_budget_keyword_order(
    tmp_path: Path,
) -> None:
    body = _compile_and_elaborate(
        tmp_path,
        source=_REVERSED_LOOP_SEED_BUDGET_SOURCE,
        commands={
            name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
            for name in ("budget", "seed")
        },
    )

    call_names = [
        node.bound_value.callee_name
        for node in _let_chain(body)
        if isinstance(node.bound_value, WccCall)
    ]
    assert call_names == [
        "cp/closed_elaboration::seed",
        "cp/closed_elaboration::budget",
    ]


def test_flat_loop_route_retains_its_unsupported_effectful_budget_behavior(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        TypeError,
        match="unsupported WCC elaboration node: ProcedureCallExpr",
    ):
        _compile_and_elaborate(
            tmp_path,
            source=_LOOP_SEED_BUDGET_SOURCE,
            commands={
                name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
                for name in ("budget", "seed")
            },
            closed_program=False,
        )


_LOOP_IN_IF_CONDITION_SOURCE = _LOOP_SEED_BUDGET_SOURCE.replace(
    """(defworkflow run () -> Int
    (loop/recur :max (budget 3)
      :state (loop-state (i Int (seed 0)))
      :on-exhausted state.i
      (fn (state) (done state.i))))""",
    """(defworkflow run () -> Bool
    (if (loop/recur :state (loop-state (i Int (seed 0)))
          :max (budget 3)
          :on-exhausted false
          (fn (state) (done true)))
      true
      false))""",
)


def test_closed_loop_keyword_order_survives_condition_normalization(
    tmp_path: Path,
) -> None:
    body = _compile_and_elaborate(
        tmp_path,
        source=_LOOP_IN_IF_CONDITION_SOURCE,
        commands={
            name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
            for name in ("budget", "seed")
        },
    )

    call_names = [
        node.bound_value.callee_name
        for node in _let_chain(body)
        if isinstance(node.bound_value, WccCall)
    ]
    assert call_names == [
        "cp/closed_elaboration::seed",
        "cp/closed_elaboration::budget",
    ]


@pytest.mark.parametrize("form", ["if", "cond"])
@pytest.mark.parametrize(
    ("operand_order", "expected_calls"),
    [
        ("max-first", ["cp/closed_elaboration::budget", "cp/closed_elaboration::seed"]),
        ("state-first", ["cp/closed_elaboration::seed", "cp/closed_elaboration::budget"]),
    ],
)
def test_closed_loop_operand_order_survives_if_and_cond_prefixes(
    tmp_path: Path,
    form: str,
    operand_order: str,
    expected_calls: list[str],
) -> None:
    if operand_order == "max-first":
        loop = """(loop/recur :max (budget 3)
          :state (loop-state (i Int (seed 0)))
          :on-exhausted false
          (fn (state) (done true)))"""
    else:
        loop = """(loop/recur :state (loop-state (i Int (seed 0)))
          :max (budget 3)
          :on-exhausted false
          (fn (state) (done true)))"""
    condition = f"({form} {loop} true false)" if form == "if" else f"(cond ({loop} true) (else false))"
    source = _LOOP_SEED_BUDGET_SOURCE.replace(
        "(loop/recur :max (budget 3)\n      :state (loop-state (i Int (seed 0)))\n      :on-exhausted state.i\n      (fn (state) (done state.i)))",
        condition,
    )
    source = source.replace("(defworkflow run () -> Int", "(defworkflow run () -> Bool")

    body = _compile_and_elaborate(
        tmp_path,
        source=source,
        commands={
            name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
            for name in ("budget", "seed")
        },
    )

    call_names = [
        node.bound_value.callee_name
        for node in _let_chain(body)
        if isinstance(node.bound_value, WccCall)
    ]
    assert call_names == expected_calls


@pytest.mark.parametrize(
    "condition_template",
    [
        "(if {loop} true false)",
        "(cond ({loop} true) (else false))",
    ],
)
def test_closed_loop_order_survives_repeated_condition_normalization(
    tmp_path: Path,
    condition_template: str,
) -> None:
    loop = """(loop/recur :state (loop-state (i Int (seed 0)))
      :max (budget 3)
      :on-exhausted false
      (fn (state) (done true)))"""
    inner = condition_template.format(loop=loop)
    source = _LOOP_SEED_BUDGET_SOURCE.replace(
        "(loop/recur :max (budget 3)\n      :state (loop-state (i Int (seed 0)))\n      :on-exhausted state.i\n      (fn (state) (done state.i)))",
        f"(if {inner} true false)",
    )
    source = source.replace("(defworkflow run () -> Int", "(defworkflow run () -> Bool")

    body = _compile_and_elaborate(
        tmp_path,
        source=source,
        commands={
            name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
            for name in ("budget", "seed")
        },
    )

    calls = [node for node in _walk_wcc(body) if isinstance(node, WccCall)]
    assert [node.callee_name for node in calls] == [
        "cp/closed_elaboration::seed",
        "cp/closed_elaboration::budget",
    ]


def test_closed_nested_loop_done_head_keeps_authored_order_in_body_prefix(
    tmp_path: Path,
) -> None:
    source = _LOOP_SEED_BUDGET_SOURCE.replace(
        "(defworkflow run () -> Int\n    (loop/recur :max (budget 3)\n      :state (loop-state (i Int (seed 0)))\n      :on-exhausted state.i\n      (fn (state) (done state.i))))",
        """(defworkflow run () -> Bool
      (if (loop/recur :max 1
          :state (loop-state (i Int 0))
          :on-exhausted false
          (fn (outer) (done
            (loop/recur :state (loop-state (i Int (seed 0)))
              :max (budget 3)
              :on-exhausted false
              (fn (inner) (done true))))))
      true
      false))""",
    )

    body = _compile_and_elaborate(
        tmp_path,
        source=source,
        commands={
            name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
            for name in ("budget", "seed")
        },
    )

    outer_loop = next(node for node in _walk_wcc(body) if isinstance(node, WccRecJoin))
    body_prefix_calls = [
        node.bound_value.callee_name
        for node in _let_chain(outer_loop.body)
        if isinstance(node.bound_value, WccCall)
    ]
    assert body_prefix_calls == [
        "cp/closed_elaboration::seed",
        "cp/closed_elaboration::budget",
    ]


def test_closed_nested_operand_prefixes_keep_group_offsets_and_order(
    tmp_path: Path,
) -> None:
    source = _LOOP_SEED_BUDGET_SOURCE.replace(
        "  (defworkflow run () -> Int\n    (loop/recur :max (budget 3)\n      :state (loop-state (i Int (seed 0)))\n      :on-exhausted state.i\n      (fn (state) (done state.i))))",
        """  (defproc budget-arg ((n Int)) -> Int
    :effects ((uses-command budget-arg))
    :lowering inline
    (command-result budget-arg :argv ("python" "probe.py" n) :returns Int))
  (defproc seed-arg ((n Int)) -> Int
    :effects ((uses-command seed-arg))
    :lowering inline
    (command-result seed-arg :argv ("python" "probe.py" n) :returns Int))
  (defworkflow run () -> Bool
    (if (loop/recur :state (loop-state (i Int (seed (seed-arg 0))))
          :max (budget (budget-arg 3))
          :on-exhausted false
          (fn (state) (done true)))
      true
      false))""",
    )
    commands = {
        name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
        for name in ("budget", "seed", "budget-arg", "seed-arg")
    }

    body = _compile_and_elaborate(tmp_path, source=source, commands=commands)

    assert [node.callee_name for node in _walk_wcc(body) if isinstance(node, WccCall)] == [
        "cp/closed_elaboration::seed-arg",
        "cp/closed_elaboration::seed",
        "cp/closed_elaboration::budget-arg",
        "cp/closed_elaboration::budget",
    ]


def test_closed_imported_old_snapshot_survives_source_deletion_and_is_reachable(
    tmp_path: Path,
) -> None:
    producer_path = tmp_path / "cp" / "producer.orc"
    producer_path.parent.mkdir(parents=True, exist_ok=True)
    producer_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/producer)
  (export get)
  (defproc seed ((n Int)) -> Int
    :effects ((uses-command seed))
    :lowering inline
    (command-result seed :argv ("python" "probe.py" n) :returns Int))
  (defworkflow get () -> Bool
    (if (loop/recur :state (loop-state (i Int (seed 0)))
          :max 3
          :on-exhausted false
          (fn (state) (done true)))
      true
      false)))''',
        encoding="utf-8",
    )
    commands = {
        name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
        for name in ("seed",)
    }
    producer = compile_stage3_entrypoint(
        producer_path,
        source_roots=(tmp_path,),
        command_boundaries=commands,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=None,
    )
    snapshot = producer.validated_bundles_by_name[
        "cp/producer::get"
    ].typed_program
    assert snapshot is not None
    producer_path.unlink()

    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")
  (defmodule cp/consumer)
  (export run)
  (defworkflow run () -> Bool (call dep)))''',
        encoding="utf-8",
    )
    typed = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries=commands,
        imported_programs={"dep": snapshot},
        workspace_root=tmp_path,
    )
    assert isinstance(typed.entry.typed_body.expr, CallExpr)
    assert typed.entry.typed_body.expr.callee_name == "dep"
    imported = typed.workflows["cp/producer::get"]
    imported_loop = next(
        node
        for node in walk_expr(imported.typed_body.expr)
        if isinstance(node, LoopRecurExpr)
    )
    assert imported_loop.operand_evaluation_order == (":state", ":max")
    body = normalize_wcc_body_to_anf(
        elaborate_typed_workflow_body(
            imported.typed_body,
            owner_name=imported.definition.name,
            type_env=typed.workflow_type_env(imported.definition.name),
            value_env=dict(imported.signature.params),
            workflow_return_types={
                name: workflow.signature.return_type_ref
                for name, workflow in typed.workflows.items()
            },
            procedure_return_types={
                name: procedure.signature.return_type_ref
                for name, procedure in typed.procedures.items()
                if not procedure.signature.type_params
            },
            resolved_procedures_by_name=typed.procedures,
            procedure_type_envs=typed.procedure_type_envs,
            route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
            closed_program=True,
        )
    )

    assert [node.callee_name for node in _walk_wcc(body) if isinstance(node, WccCall)] == [
        "cp/producer::seed",
    ]


def test_closed_nested_zero_budget_keeps_done_effect_inside_inner_iteration(
    tmp_path: Path,
) -> None:
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")
  (defmodule cp/closed_elaboration)
  (export run)
  (defproc budget ((n Int)) -> Int
    :effects ((uses-command budget))
    :lowering inline
    (command-result budget :argv ("python" "probe.py" n) :returns Int))
  (defproc seed ((n Int)) -> Int
    :effects ((uses-command seed))
    :lowering inline
    (command-result seed :argv ("python" "probe.py" n) :returns Int))
  (defproc check ((n Int)) -> Bool
    :effects ((uses-command check))
    :lowering inline
    (command-result check :argv ("python" "probe.py" n) :returns Bool))
  (defworkflow run () -> Bool
    (if (loop/recur :max 1
          :state (loop-state (outer Int 0))
          :on-exhausted false
          (fn (outer) (done
            (loop/recur :state (loop-state (inner Int (seed 0)))
              :max (budget 0)
              :on-exhausted false
              (fn (inner) (done (check 1)))))))
      true
      false)))'''
    path = tmp_path / "cp" / "closed_elaboration.orc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    commands = {
        name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
        for name in ("budget", "seed", "check")
    }
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries=commands,
        workspace_root=tmp_path,
    )
    path.unlink()
    entry = typed.entry
    body = normalize_wcc_body_to_anf(
        elaborate_typed_workflow_body(
            entry.typed_body,
            owner_name=entry.definition.name,
            type_env=typed.workflow_type_env(entry.definition.name),
            value_env=dict(entry.signature.params),
            workflow_return_types={
                name: workflow.signature.return_type_ref
                for name, workflow in typed.workflows.items()
            },
            procedure_return_types={
                name: procedure.signature.return_type_ref
                for name, procedure in typed.procedures.items()
                if not procedure.signature.type_params
            },
            resolved_procedures_by_name=typed.procedures,
            procedure_type_envs=typed.procedure_type_envs,
            route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
            closed_program=True,
        )
    )
    loops = [node for node in _walk_wcc(body) if isinstance(node, WccRecJoin)]
    outer_loop, inner_loop = loops
    outer_iteration_calls = [
        node.bound_value.callee_name
        for node in _let_chain(outer_loop.body)
        if isinstance(node.bound_value, WccCall)
    ]
    inner_iteration_calls = [
        node.bound_value.callee_name
        for node in _let_chain(inner_loop.body)
        if isinstance(node.bound_value, WccCall)
    ]

    assert outer_iteration_calls == [
        "cp/closed_elaboration::seed",
        "cp/closed_elaboration::budget",
    ]
    assert inner_iteration_calls == ["cp/closed_elaboration::check"]


@pytest.mark.parametrize(
    ("condition", "has_nested_check"),
    [
        (
            "(not (loop/recur :max 1 :state (loop-state (outer Int 0)) "
            ":on-exhausted false (fn (state) (done "
            "(loop/recur :state (loop-state (inner Int (seed 0))) "
            ":max (budget 0) :on-exhausted false "
            "(fn (inner) (done (check 1))))))))",
            True,
        ),
        (
            "(= (loop/recur :max 1 :state (loop-state (outer Int 0)) "
            ":on-exhausted false (fn (state) (done "
            "(loop/recur :state (loop-state (inner Int (seed 0))) "
            ":max (budget 0) :on-exhausted false "
            "(fn (inner) (done (check 1))))))) true)",
            True,
        ),
        (
            "(not (loop/recur :max 0 :state (loop-state (inner Int 0)) "
            ":on-exhausted false (fn (inner) (done true))))",
            False,
        ),
        (
            "(= (list/length (list (loop/recur :max 0 "
            ":state (loop-state (inner Int 0)) :on-exhausted false "
            "(fn (inner) (done true))))) 1)",
            False,
        ),
    ],
    ids=("not-effectful-loop", "equality-effectful-loop", "not-pure-loop", "pure-loop-aggregate"),
)
def test_closed_value_operands_normalize_loops_without_losing_locality(
    tmp_path: Path,
    condition: str,
    has_nested_check: bool,
) -> None:
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")
  (defmodule cp/closed_elaboration)
  (export run)
  (defproc budget ((n Int)) -> Int
    :effects ((uses-command budget))
    :lowering inline
    (command-result budget :argv ("python" "probe.py" n) :returns Int))
  (defproc seed ((n Int)) -> Int
    :effects ((uses-command seed))
    :lowering inline
    (command-result seed :argv ("python" "probe.py" n) :returns Int))
  (defproc check ((n Int)) -> Bool
    :effects ((uses-command check))
    :lowering inline
    (command-result check :argv ("python" "probe.py" n) :returns Bool))
  (defworkflow run () -> Bool
    (if {condition} true false)))'''
    path = tmp_path / "cp" / "closed_elaboration.orc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={
            name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"))
            for name in ("budget", "seed", "check")
        },
        workspace_root=tmp_path,
    )
    path.unlink()
    entry = typed.entry
    body = normalize_wcc_body_to_anf(
        elaborate_typed_workflow_body(
            entry.typed_body,
            owner_name=entry.definition.name,
            type_env=typed.workflow_type_env(entry.definition.name),
            value_env=dict(entry.signature.params),
            workflow_return_types={
                name: workflow.signature.return_type_ref
                for name, workflow in typed.workflows.items()
            },
            procedure_return_types={
                name: procedure.signature.return_type_ref
                for name, procedure in typed.procedures.items()
                if not procedure.signature.type_params
            },
            resolved_procedures_by_name=typed.procedures,
            procedure_type_envs=typed.procedure_type_envs,
            route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
            closed_program=True,
        )
    )
    loops = [node for node in _walk_wcc(body) if isinstance(node, WccRecJoin)]
    calls = [node for node in _walk_wcc(body) if isinstance(node, WccCall)]

    if has_nested_check:
        outer_loop, inner_loop = loops
        outer_calls = [
            node.bound_value.callee_name
            for node in _let_chain(outer_loop.body)
            if isinstance(node.bound_value, WccCall)
        ]
        inner_calls = [
            node.bound_value.callee_name
            for node in _let_chain(inner_loop.body)
            if isinstance(node.bound_value, WccCall)
        ]
        assert "cp/closed_elaboration::check" not in outer_calls
        assert "cp/closed_elaboration::check" in inner_calls
    else:
        assert len(loops) == 1
        assert calls == []


def test_closed_exhaustive_effectful_terminal_cond_evaluates_condition_once(
    tmp_path: Path,
) -> None:
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")
  (defmodule cp/closed_elaboration)
  (export run)
  (defproc check ((n Int)) -> Bool
    :effects ((uses-command check))
    :lowering inline
    (command-result check :argv ("python" "probe.py" n) :returns Bool))
  (defworkflow run () -> Int
    (cond ((or (check 1) true) 7))))'''

    body = _compile_and_elaborate(
        tmp_path,
        source=source,
        commands={
            "check": ExternalToolBinding(
                name="check",
                stable_command=("python", "probe.py"),
            )
        },
    )

    calls = [node for node in _walk_wcc(body) if isinstance(node, WccCall)]
    assert [node.callee_name for node in calls] == ["cp/closed_elaboration::check"]
    assert not any(
        isinstance(node, WccOpaqueFrontendValue) and _contains_effect(node.expr)
        for node in _walk_wcc(body)
    )
