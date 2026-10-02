from __future__ import annotations

from dataclasses import fields
from dataclasses import is_dataclass
from pathlib import Path
import reprlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed import build as closed_build
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.names import canonical_type_descriptor
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.closed.sites import _ast_nodes
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import (
    LetStarExpr,
    ListMapEffectExpr,
    ListMapExpr,
    LoopRecurExpr,
    MatchExpr,
)
from tests.workflow_lisp_closed_program_helpers import BOUNDARIES, build, fixture, install
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
from orchestrator.workflow_lisp.wcc.model import (
    WCC_M4_ROUTE_SCHEMA_VERSION,
    WccPureOp,
    WccSpecializationCapture,
)


def test_authored_let_binding_label_survives_typechecking_as_transient_origin(tmp_path: Path) -> None:
    source = '''(workflow-lisp
      (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/origin) (export run)
      (defworkflow run ((input Int)) -> Int
        (let* ((authored input)) authored)))'''
    path = install(tmp_path, source)
    typed = compile_typed_program(
        path,
        entry_workflow="cp/origin::run",
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
    )
    (binding,) = [node for node in walk_expr(typed.entry.typed_body.expr) if isinstance(node, LetStarExpr)]

    assert binding.binding_labels == ("authored",)
    field = next(item for item in fields(binding) if item.name == "binding_labels")
    assert not field.repr and not field.compare and not field.hash
    assert field.metadata["json_omit_always"] is True
    assert field.metadata["semantic_identity_omit"] is True
    assert "binding_labels" not in reprlib.repr(binding)
    closed = build_closed_program(typed)
    (closed_binding,) = [
        node
        for node in _walk_dataclasses(closed.tree["body"])
        if isinstance(node, dict) and node.get("k") == "let" and node.get("label") == "authored"
    ]
    assert closed_binding["name"] == "authored"


def _walk_dataclasses(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_dataclasses(value)
    elif isinstance(node, (tuple, list)):
        for value in node:
            yield from _walk_dataclasses(value)
    elif is_dataclass(node) and not isinstance(node, type):
        yield node
        for item in fields(node):
            if item.name != "metadata":
                yield from _walk_dataclasses(getattr(node, item.name))


def _resolve_closed_value(value, bindings, before=None):
    """Follow names only through bindings already in lexical scope."""

    before = len(bindings) if before is None else before
    if value.get("k") == "name":
        for index in range(before - 1, -1, -1):
            name, bound = bindings[index]
            if name == value["n"]:
                return _resolve_closed_value(bound, bindings, index)
    elif value.get("k") == "block":
        nested = list(bindings[:before])
        body = value["body"]
        while body.get("k") == "let":
            nested.append((body["name"], body["value"]))
            body = body["body"]
        assert body.get("k") == "halt"
        return _resolve_closed_value(body["value"], nested)
    return value, bindings, before


def test_authored_match_and_loop_labels_reach_closed_control_nodes(tmp_path: Path) -> None:
    match_source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/match_origin)
      (export run)
      (defunion Choice (YES (n Int)) (NO (n Int)))
      (defworkflow run ((choice Choice)) -> Int
        (match choice ((YES yes_value) yes_value.n) ((NO no_value) no_value.n))))'''
    match_path = install(tmp_path / "match", match_source)
    match_typed = compile_typed_program(
        match_path,
        entry_workflow="cp/match_origin::run",
        source_roots=(tmp_path / "match",),
        command_boundaries={},
    )
    match_tree = build_closed_program(match_typed).tree
    (closed_match,) = [
        node for node in _walk_dataclasses(match_tree["body"])
        if isinstance(node, dict) and node.get("k") == "case"
    ]
    assert [arm["bind"] for arm in closed_match["arms"]] == ["yes_value", "no_value"]

    loop_source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/loop_origin)
      (export run)
      (defworkflow run () -> Int
        (loop/recur :max 2 :state 0
          (fn (iteration)
            (if (< iteration 1)
                  (continue (+ iteration 1))
                  (done iteration))))))'''
    loop_path = install(tmp_path / "loop", loop_source)
    loop_typed = compile_typed_program(
        loop_path,
        entry_workflow="cp/loop_origin::run",
        source_roots=(tmp_path / "loop",),
        command_boundaries={},
    )
    loop_tree = build_closed_program(loop_typed).tree
    (closed_loop,) = [
        node for node in _walk_dataclasses(loop_tree["body"])
        if isinstance(node, dict) and node.get("k") == "loop"
    ]
    assert closed_loop["label"] == "iteration"


def test_macro_parameter_origins_use_the_declaration_identifier(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/parameter_origin)
      (export run)
      (defmacro make-workflow (workflow-name parameter-name)
        (defworkflow workflow-name ((parameter-name Int) (generated_unused Int)) -> Int
          (+ parameter-name 1)))
      (defmacro make-procedure (procedure-name parameter-name)
        (defproc procedure-name ((parameter-name Int)) -> Int
          :effects () :lowering inline (+ parameter-name 1)))
      (make-workflow run authored)
      (make-procedure helper proc_authored))'''
    path = install(tmp_path, source)
    typed = compile_typed_program(
        path,
        entry_workflow="cp/parameter_origin::run",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    parameters = typed.entry.definition.params
    assert [parameter.binding_label for parameter in parameters] == ["authored", None]
    for parameter in (*parameters, *next(iter(typed.procedures.values())).definition.params):
        field = next(item for item in fields(parameter) if item.name == "binding_label")
        assert not field.repr and not field.compare and not field.hash
        assert field.metadata["json_omit_always"] is True
        assert field.metadata["semantic_identity_omit"] is True
    (procedure,) = typed.procedures.values()
    assert [parameter.binding_label for parameter in procedure.definition.params] == [
        "proc_authored"
    ]

    shifted_source = source.replace(
        "(make-workflow run authored)",
        "(make-workflow other other_input)\n      (make-workflow run authored)",
    )
    shifted_path = install(tmp_path / "shifted", shifted_source)
    shifted = compile_typed_program(
        shifted_path,
        entry_workflow="cp/parameter_origin::run",
        source_roots=(tmp_path / "shifted",),
        command_boundaries={},
    )
    assert [parameter.binding_label for parameter in shifted.entry.definition.params] == [
        "authored",
        None,
    ]
    assert parameters[1].name != shifted.entry.definition.params[1].name


def test_authored_match_and_list_binders_retain_only_syntax_origins(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/origins)
      (export run)
      (defunion Choice (YES (n Int)) (NO (n Int)))
      (defworkflow child ((value Int)) -> Int value)
      (defworkflow run ((values List[Int]) (choice Choice)) -> List[Int]
        (let* ((mapped (list/map ((mapper values)) (+ mapper 1)))
               (selected (match choice
                 ((YES yes_value) yes_value.n)
                 ((NO no_value) no_value.n))))
          (list/map-effect ((item mapped)) :max 3
            (call child :value (+ item selected))))))'''
    path = install(tmp_path, source)
    typed = compile_typed_program(
        path,
        entry_workflow="cp/origins::run",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    nodes = list(walk_expr(typed.entry.typed_body.expr))
    (mapping,) = [node for node in nodes if isinstance(node, ListMapExpr)]
    (matched,) = [node for node in nodes if isinstance(node, MatchExpr)]
    effect_maps = [node for node in nodes if isinstance(node, ListMapEffectExpr)]
    lowered_item_bindings = [
        node
        for node in nodes
        if isinstance(node, LetStarExpr)
        and node.bindings
        and node.bindings[0][0] == "item"
    ]
    synthetic_loops = [node for node in nodes if isinstance(node, LoopRecurExpr)]

    assert mapping.binding_label == "mapper"
    assert effect_maps == []
    (item_binding,) = lowered_item_bindings
    assert item_binding.binding_labels == ("item", None, None, None, None)
    assert synthetic_loops
    assert all(loop.binding_label is None for loop in synthetic_loops)
    assert [arm.binding_label for arm in matched.arms] == ["yes_value", "no_value"]


def test_three_call_sites_of_one_procedure_are_one_definition_and_three_frames(tmp_path: Path) -> None:
    closed = build(tmp_path, fixture("three_call_sites"))
    callee = "procedure:cp/three_call_sites::fetch"
    calls = []
    body = closed.tree["body"]
    while body["k"] == "let":
        if body["value"]["k"] == "call":
            calls.append(body["value"])
        body = body["body"]

    assert sorted(closed.tree["definitions"]) == [callee]
    assert closed.sites == ((callee, "#1"),)
    assert [call["frame"] for call in calls] == [f"{name}={callee}" for name in ("a", "b", "c")]
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        closed.tree,
        closed.sites,
        closed.digest,
    )


@pytest.mark.parametrize(
    "name",
    ("arms_in_loop", "if_in_hook", "if_over_lists", "loop_in_branch", "loop_in_loop"),
)
def test_control_fixtures_build_and_read_back_after_source_removal(tmp_path: Path, name: str) -> None:
    root = tmp_path / name
    path = install(root, fixture(name))
    typed = compile_typed_program(
        path,
        entry_workflow=f"cp/{name}::run",
        source_roots=(root,),
        command_boundaries=BOUNDARIES,
        workspace_root=root,
    )
    path.unlink()

    with patch("pathlib.Path.open", side_effect=AssertionError("closed builder reread source")):
        program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (program.tree, program.sites, program.digest) == (
        restored.tree,
        restored.sites,
        restored.digest,
    )
    if name == "arms_in_loop":
        callee = "procedure:cp/arms_in_loop::fetch"
        effects = [
            node
            for definition in {"entry": restored.tree["body"], **{
                key: row["body"] for key, row in restored.tree["definitions"].items()
            }}.values()
            for node in _ast_nodes(definition)
            if node.get("k") == "perform"
        ]
        assert restored.sites == ((callee, "#1"),)
        assert len(effects) == 1 and effects[0]["site"] == "#1"
        calls = [node for node in _ast_nodes(restored.tree["body"]) if node.get("k") == "call"]
        assert len(calls) == 3
        assert [call["frame"] for call in calls] == [
            f"loop:state[*] / got / body / {variant} / #1={callee}"
            for variant in ("FIRST", "SECOND", "THIRD")
        ]

        source = fixture("arms_in_loop").replace("(export run)", "(export run helper)", 1)
        helper_source = source.replace(
            "(defworkflow run () -> Int", "(defworkflow helper () -> Int", 1
        ).rstrip()
        helper_source = (
            helper_source[:-1]
            + "\n(defworkflow run () -> Int (call helper))\n)\n"
        )
        helper_root = tmp_path / "arms-in-loop-helper"
        helper_path = install(helper_root, helper_source)
        helper_typed = compile_typed_program(
            helper_path,
            entry_workflow="cp/arms_in_loop::run",
            source_roots=(helper_root,),
            command_boundaries=BOUNDARIES,
            workspace_root=helper_root,
        )
        helper_path.unlink()
        helper_program = build_closed_program(helper_typed)
        helper_restored = ClosedProgram.from_artifact(helper_program.artifact())
        assert (helper_restored.tree, helper_restored.sites, helper_restored.digest) == (
            helper_program.tree,
            helper_program.sites,
            helper_program.digest,
        )
        helper_definition = helper_restored.tree["definitions"]["workflow:cp/arms_in_loop::helper"]
        helper_calls = [
            node
            for node in _ast_nodes(helper_definition["body"])
            if node.get("k") == "call" and node.get("callee") == callee
        ]
        assert helper_restored.sites == ((callee, "#1"),)
        assert len(helper_calls) == 3
        assert [call["frame"] for call in helper_calls] == [
            f"loop:state[*] / got / body / {variant} / #1={callee}"
            for variant in ("FIRST", "SECOND", "THIRD")
        ]
        entry_calls = [
            node for node in _ast_nodes(helper_restored.tree["body"])
            if node.get("k") == "call"
            and node.get("callee") == "workflow:cp/arms_in_loop::helper"
        ]
        assert len(entry_calls) == 1


def test_public_source_deleted_command_build_roundtrips_strictly(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/source_deleted) (export run)
      (defworkflow run ((value Int)) -> Int
        (command-result fetch :argv ("python" "probe.py" value) :returns Int)))'''
    path = install(tmp_path, source)
    typed = compile_typed_program(
        path,
        entry_workflow="cp/source_deleted::run",
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
        workspace_root=tmp_path,
    )
    path.unlink()

    with patch("pathlib.Path.open", side_effect=AssertionError("closed builder reread source")):
        program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())

    assert (program.tree, program.sites, program.digest) == (
        restored.tree,
        restored.sites,
        restored.digest,
    )
    effect = program.tree["body"]["value"]
    assert effect["k"] == "perform"
    assert effect["closure"] == [{"base": "workspace", "path": "probe.py"}]
    assert len(program.sites) == 1
    assert program.tree["configuration"]["commands"]["fetch"]["stable_command"] == [
        "python",
        "probe.py",
    ]


def test_all_supplied_command_closures_are_checked_and_empty_is_explicit(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/unused_boundary) (export run)
      (defworkflow run () -> Int 1))'''
    path = install(tmp_path, source)
    typed = compile_typed_program(
        path,
        entry_workflow="cp/unused_boundary::run",
        source_roots=(tmp_path,),
        command_boundaries={
            "fetch": ExternalToolBinding(
                name="fetch", stable_command=("python", "probe.py"), closure=None
            )
        },
        workspace_root=tmp_path,
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_closed_program(typed)
    assert any(
        diagnostic.code == "command_boundary_closure_missing"
        for diagnostic in excinfo.value.diagnostics
    )

    explicit_empty = compile_typed_program(
        path,
        entry_workflow="cp/unused_boundary::run",
        source_roots=(tmp_path,),
        command_boundaries={
            "fetch": ExternalToolBinding(
                name="fetch", stable_command=("python", "probe.py"), closure=()
            )
        },
        workspace_root=tmp_path,
    )
    closed = build_closed_program(explicit_empty)
    assert closed.tree["configuration"]["commands"]["fetch"]["closure"] == []


def test_captured_runtime_value_keeps_its_lexical_owner_after_shadowing(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/capture_owner) (export run)
      (defproc invoke ((runner ProcRef[Int -> Int]) (n Int)) -> Int
        :effects () :lowering inline (runner n))
      (defproc forward ((runner ProcRef[Int -> Int]) (n Int)) -> Int
        :effects () :lowering inline (invoke runner n))
      (defworkflow run ((input Int)) -> Int
        (let* ((first (command-result fetch :argv ("python" "probe.py" input) :returns Int)))
          (let-proc (saved ((n Int)) -> Int :captures (first)
                      (command-result fetch :argv ("python" "probe.py" first n) :returns Int))
            (let* ((first 100)
                   (hook (proc-ref saved))
                   (answer (forward hook 5)))
              answer)))))'''
    root = tmp_path / "shadowed"
    path = install(root, source)
    typed = compile_typed_program(
        path,
        entry_workflow="cp/capture_owner::run",
        source_roots=(root,),
        command_boundaries=BOUNDARIES,
        workspace_root=root,
    )
    path.unlink()

    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (program.tree, program.sites, program.digest) == (
        restored.tree,
        restored.sites,
        restored.digest,
    )
    effects = [node for node in _walk_dataclasses(program.tree) if isinstance(node, dict) and node.get("k") == "perform"]
    calls = [node for node in _walk_dataclasses(program.tree) if isinstance(node, dict) and node.get("k") == "call"]
    assert len(effects) == 2
    assert calls
    saved = next(
        definition
        for name, definition in program.tree["definitions"].items()
        if name.startswith("procedure:cp/capture_owner::saved[")
    )
    saved_effect = next(
        node for node in _walk_dataclasses(saved["body"])
        if isinstance(node, dict) and node.get("k") == "perform"
    )
    captured_name = saved_effect["argv"][0]["n"]
    bindings = []
    body = program.tree["body"]
    while body["k"] == "let":
        bindings.append((body["name"], body["value"]))
        body = body["body"]
    original = next(index for index, (name, value) in enumerate(bindings) if name == "first" and value["k"] == "perform")
    shadow = next(
        index
        for index, (name, value) in enumerate(bindings)
        if name == "first" and value.get("k") == "lit" and value.get("v") == 100
    )
    alias = next(
        index for index, (name, value) in enumerate(bindings)
        if name == captured_name and value["k"] == "name" and value["n"] == "first"
    )
    assert original < alias < shadow
    # One effect creates the original `first`; both calls forward its frozen
    # alias even after the authored name is shadowed.
    forwarding_call = next(
        node for node in calls
        if node["callee"].startswith("procedure:cp/capture_owner::forward[")
    )
    assert forwarding_call["args"][0] == {"k": "name", "n": captured_name}


def test_captured_entry_parameter_is_frozen_before_a_same_name_shadow(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/parameter_capture) (export run)
      (defproc forward ((runner ProcRef[Int -> Int]) (n Int)) -> Int
        :effects () :lowering inline (runner n))
      (defworkflow run ((input Int)) -> Int
        (let* ((first input))
          (let-proc (saved ((n Int)) -> Int :captures (input)
                      (command-result fetch :argv ("python" "probe.py" input n) :returns Int))
                (let* ((first 100) (input 200) (hook (proc-ref saved))
                       (answer (forward hook 5)))
                  answer)))))'''
    root = tmp_path / "parameter_capture"
    path = install(root, source)
    typed = compile_typed_program(
        path,
        entry_workflow="cp/parameter_capture::run",
        source_roots=(root,),
        command_boundaries=BOUNDARIES,
        workspace_root=root,
    )
    path.unlink()

    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (program.tree, program.sites, program.digest) == (
        restored.tree,
        restored.sites,
        restored.digest,
    )
    saved = next(
        definition
        for name, definition in program.tree["definitions"].items()
        if name.startswith("procedure:cp/parameter_capture::saved[")
    )
    saved_effect = next(
        node for node in _walk_dataclasses(saved["body"])
        if isinstance(node, dict) and node.get("k") == "perform"
    )
    captured_name = saved_effect["argv"][0]["n"]
    bindings = []
    body = program.tree["body"]
    while body["k"] == "let":
        bindings.append((body["name"], body["value"]))
        body = body["body"]
    alias = next(
        index for index, (name, value) in enumerate(bindings)
        if name == captured_name and value.get("k") == "name" and value.get("n") == "input"
    )
    shadow = next(
        index for index, (name, value) in enumerate(bindings)
        if name == "input" and value.get("k") == "lit" and value.get("v") == 200
    )
    assert alias < shadow
    forwarding = next(
        node for node in _walk_dataclasses(program.tree["body"])
        if isinstance(node, dict)
        and node.get("k") == "call"
        and node.get("callee", "").startswith("procedure:cp/parameter_capture::forward[")
    )
    assert forwarding["args"][0] == {"k": "name", "n": captured_name}


@pytest.mark.parametrize(
    ("body", "expected_ops", "expected_calls"),
    (
        (
            "(let* ((z (+ x 1))) (invoke (bind-proc (proc-ref helper) :fixed z) x))",
            1,
            2,
        ),
        (
            "(invoke (bind-proc (proc-ref helper) :fixed (+ x 1)) x)",
            1,
            2,
        ),
        (
            "(let* ((hook (bind-proc (proc-ref helper) :fixed (+ x 1)))) "
            "(let* ((x 100) (first (invoke hook 2)) (second (invoke hook 3))) "
            "(+ first second)))",
            2,
            3,
        ),
    ),
    ids=("hoisted-control", "direct-computed", "stored-after-shadow"),
)
def test_computed_proc_ref_argument_is_evaluated_at_its_binding_region(
    tmp_path: Path,
    body: str,
    expected_ops: int,
    expected_calls: int,
) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/computed_ref_capture) (export run)
      (defproc helper ((fixed Int) (y Int)) -> Int
        :effects ((uses-command fetch)) :lowering inline
        (command-result fetch :argv ("python" "probe.py" fixed y) :returns Int))
      (defproc invoke ((runner ProcRef[Int -> Int]) (y Int)) -> Int
        :effects () :lowering inline (runner y))
      (defworkflow run ((x Int)) -> Int BODY))'''
    root = tmp_path / "computed_ref_capture"
    path = install(root, source.replace("BODY", body))
    typed = compile_typed_program(
        path,
        entry_workflow="cp/computed_ref_capture::run",
        source_roots=(root,),
        command_boundaries=BOUNDARIES,
        workspace_root=root,
    )
    path.unlink()

    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (program.tree, program.sites, program.digest) == (
        restored.tree,
        restored.sites,
        restored.digest,
    )
    nodes = [
        node
        for node in _walk_dataclasses(program.tree)
        if isinstance(node, dict) and "k" in node
    ]
    assert len([node for node in nodes if node["k"] == "op"]) == expected_ops
    assert len([node for node in nodes if node["k"] == "perform"]) == 1
    assert len([node for node in nodes if node["k"] == "call"]) == expected_calls
    bindings = []
    body = program.tree["body"]
    checked_calls = 0
    while body["k"] == "let":
        value = body["value"]
        if (
            value["k"] == "call"
            and program.tree["definitions"][value["callee"]]["key"][2] == "invoke"
        ):
            captured, scope, before = _resolve_closed_value(value["args"][0], bindings)
            assert captured["k"] == "op"
            assert captured["payload"]["expr"]["operator"] == "+"
            left, _, _ = _resolve_closed_value(captured["args"][0], scope, before)
            right, _, _ = _resolve_closed_value(captured["args"][1], scope, before)
            assert left.get("k") == "name" and left.get("n") == "x"
            assert right.get("k") == "lit" and right.get("v") == 1
            checked_calls += 1
        bindings.append((body["name"], value))
        body = body["body"]
    assert checked_calls == (2 if expected_calls == 3 else 1)
    for definition in program.tree["definitions"].values():
        if definition["key"][2] == "invoke":
            nested_call = next(
                node
                for node in _walk_dataclasses(definition["body"])
                if isinstance(node, dict) and node.get("k") == "call"
            )
            assert nested_call["args"][0].get("k") == "name"
            assert nested_call["args"][0].get("n") == definition["params"][0][0]
        elif definition["key"][2] == "helper":
            effect = next(
                node
                for node in _walk_dataclasses(definition["body"])
                if isinstance(node, dict) and node.get("k") == "perform"
            )
            assert effect["argv"][0].get("k") == "name"
            assert effect["argv"][0].get("n") == definition["params"][0][0]


def test_computed_closed_proc_ref_argument_stays_a_closed_value(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/computed_closed_ref) (export run)
      (defproc helper ((fixed Int) (y Int)) -> Int
        :effects ((uses-command fetch)) :lowering inline
        (command-result fetch :argv ("python" "probe.py" fixed y) :returns Int))
      (defproc invoke ((runner ProcRef[Int -> Int]) (y Int)) -> Int
        :effects () :lowering inline (runner y))
      (defworkflow run ((x Int)) -> Int
        (invoke (bind-proc (proc-ref helper) :fixed (+ 2 3)) x)))'''
    root = tmp_path / "computed_closed_ref"
    path = install(root, source)
    typed = compile_typed_program(
        path,
        entry_workflow="cp/computed_closed_ref::run",
        source_roots=(root,),
        command_boundaries=BOUNDARIES,
        workspace_root=root,
    )
    path.unlink()

    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (program.tree, program.sites, program.digest) == (
        restored.tree,
        restored.sites,
        restored.digest,
    )
    helper = next(
        definition
        for definition in program.tree["definitions"].values()
        if definition["key"][2] == "helper"
    )
    assert len(helper["params"]) == 1

    bindings = []
    body = helper["body"]
    while body["k"] == "let":
        bindings.append((body["name"], body["value"]))
        body = body["body"]
    effect = next(
        node
        for node in _walk_dataclasses(helper["body"])
        if isinstance(node, dict) and node.get("k") == "perform"
    )
    fixed = effect["argv"][0]
    if fixed["k"] == "name":
        fixed = next(value for name, value in reversed(bindings) if name == fixed["n"])
    assert fixed["k"] == "op"
    assert fixed["payload"]["expr"]["operator"] == "+"
    assert [(arg["k"], arg.get("v")) for arg in fixed["args"]] == [
        ("lit", 2),
        ("lit", 3),
    ]


def test_one_bound_effect_creation_is_shared_by_direct_and_reference_calls(
    tmp_path: Path,
) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/mixed_ref_creation) (export run)
      (defproc helper ((fixed Int) (y Int)) -> Int
        :effects ((uses-command fetch)) :lowering inline
        (command-result fetch :argv ("python" "probe.py" fixed y) :returns Int))
      (defproc invoke ((runner ProcRef[Int -> Int]) (y Int)) -> Int
        :effects () :lowering inline (runner y))
      (defworkflow run ((x Int)) -> Int
        (let* ((hook (bind-proc (proc-ref helper) :fixed
                      (command-result fetch :argv ("python" "probe.py" x) :returns Int))))
              (let* ((x 100) (direct (hook 2)) (through_ref (invoke hook 3)))
                (+ direct through_ref)))))'''
    root = tmp_path / "mixed_ref_creation"
    path = install(root, source)
    typed = compile_typed_program(
        path,
        entry_workflow="cp/mixed_ref_creation::run",
        source_roots=(root,),
        command_boundaries=BOUNDARIES,
        workspace_root=root,
    )
    path.unlink()

    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (program.tree, program.sites, program.digest) == (
        restored.tree,
        restored.sites,
        restored.digest,
    )
    entry_effects = [
        node for node in _walk_dataclasses(program.tree["body"])
        if isinstance(node, dict) and node.get("k") == "perform"
    ]
    assert len(entry_effects) == 1

    bindings = []
    body = program.tree["body"]
    checked_calls = 0
    while body["k"] == "let":
        value = body["value"]
        if (
            value["k"] == "call"
            and program.tree["definitions"][value["callee"]]["key"][2]
            in {"invoke", "helper"}
        ):
            capture, scope, before = _resolve_closed_value(value["args"][0], bindings)
            assert capture["k"] == "perform"
            assert capture["site"] == entry_effects[0]["site"]
            original_input, _, _ = _resolve_closed_value(capture["argv"][0], scope, before)
            assert original_input.get("k") == "name"
            assert original_input.get("n") == "x"
            checked_calls += 1
        bindings.append((body["name"], value))
        body = body["body"]
    assert checked_calls == 2


def test_zero_input_effectful_bound_value_runs_at_creation_once(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/zero_input_bound_effect) (export run)
      (defproc helper ((fixed Int) (y Int)) -> Int
        :effects ((uses-command fetch)) :lowering inline
        (command-result fetch :argv ("python" "probe.py" fixed y) :returns Int))
      (defproc invoke ((runner ProcRef[Int -> Int]) (y Int)) -> Int
        :effects () :lowering inline (runner y))
      (defworkflow run ((x Int)) -> Int
        (let* ((hook (bind-proc (proc-ref helper) :fixed
                      (command-result fetch :argv ("python" "probe.py") :returns Int))))
          (let* ((x 100)
                 (middle (command-result fetch :argv ("python" "probe.py" 99) :returns Int))
                 (direct (hook 2))
                 (through_ref (invoke hook 3)))
            (+ direct through_ref)))))'''
    root = tmp_path / "zero_input_bound_effect"
    path = install(root, source)
    typed = compile_typed_program(
        path,
        entry_workflow="cp/zero_input_bound_effect::run",
        source_roots=(root,),
        command_boundaries=BOUNDARIES,
        workspace_root=root,
    )
    path.unlink()

    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (program.tree, program.sites, program.digest) == (
        restored.tree,
        restored.sites,
        restored.digest,
    )
    assert sum(
        node.get("k") == "perform" for node in _walk_dataclasses(program.tree)
        if isinstance(node, dict)
    ) == 3

    creation_effects = []
    bindings = []
    checked_calls = 0
    body = program.tree["body"]
    while body["k"] == "let":
        value = body["value"]
        if value["k"] == "perform":
            creation_effects.append(value)
        if (
            value["k"] == "call"
            and program.tree["definitions"][value["callee"]]["key"][2]
            in {"invoke", "helper"}
        ):
            capture, _, _ = _resolve_closed_value(value["args"][0], bindings)
            assert capture["k"] == "perform"
            assert capture["site"] == creation_effects[0]["site"]
            assert capture["argv"] == []
            checked_calls += 1
        bindings.append((body["name"], value))
        body = body["body"]
    assert len(creation_effects) == 2
    assert creation_effects[0]["argv"] == []
    assert [(arg["k"], arg.get("v")) for arg in creation_effects[1]["argv"]] == [
        ("lit", 99),
    ]
    assert checked_calls == 2


@pytest.mark.parametrize(
    ("callee", "body", "expected_argv"),
    (
        (
            "invoke",
            '(invoke (bind-proc (proc-ref helper) :fixed '
            '(command-result fetch :argv ("python" "probe.py") :returns Int)) '
            '(command-result fetch :argv ("python" "probe.py" 99) :returns Int))',
            ((), (("lit", 99),)),
        ),
        (
            "invoke-last",
            '(invoke-last (command-result fetch :argv ("python" "probe.py" 99) :returns Int) '
            '(bind-proc (proc-ref helper) :fixed '
            '(command-result fetch :argv ("python" "probe.py") :returns Int)))',
            ((("lit", 99),), ()),
        ),
        (
            "invoke",
            '(let* ((answer (invoke (bind-proc (proc-ref helper) :fixed '
            '(command-result fetch :argv ("python" "probe.py") :returns Int)) '
            '(command-result fetch :argv ("python" "probe.py" 99) :returns Int)))) answer)',
            ((), (("lit", 99),)),
        ),
        (
            "invoke-last",
            '(let* ((answer (invoke-last (command-result fetch :argv ("python" "probe.py" 99) :returns Int) '
            '(bind-proc (proc-ref helper) :fixed '
            '(command-result fetch :argv ("python" "probe.py") :returns Int))))) answer)',
            ((("lit", 99),), ()),
        ),
    ),
    ids=("capture-first", "capture-last", "capture-first-let-bound", "capture-last-let-bound"),
)
def test_inline_zero_input_capture_preserves_effect_argument_order(
    tmp_path: Path,
    callee: str,
    body: str,
    expected_argv: tuple[tuple[tuple[str, object], ...], ...],
) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/inline_zero_input_capture) (export run)
      (defproc helper ((fixed Int) (y Int)) -> Int
        :effects ((uses-command fetch)) :lowering inline
        (command-result fetch :argv ("python" "probe.py" fixed y) :returns Int))
      (defproc invoke ((runner ProcRef[Int -> Int]) (y Int)) -> Int
        :effects () :lowering inline (runner y))
      (defproc invoke-last ((y Int) (runner ProcRef[Int -> Int])) -> Int
        :effects () :lowering inline (runner y))
      (defworkflow run () -> Int BODY))'''
    root = tmp_path / callee
    path = install(root, source.replace("BODY", body))
    typed = compile_typed_program(
        path,
        entry_workflow="cp/inline_zero_input_capture::run",
        source_roots=(root,),
        command_boundaries=BOUNDARIES,
        workspace_root=root,
    )
    path.unlink()

    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (program.tree, program.sites, program.digest) == (
        restored.tree,
        restored.sites,
        restored.digest,
    )
    bindings = []
    calls = []
    effects = []
    body = program.tree["body"]
    while body["k"] == "let":
        value = body["value"]
        if value["k"] == "perform":
            effects.append(value)
        if (
            value["k"] == "call"
            and program.tree["definitions"][value["callee"]]["key"][2] == callee
        ):
            calls.append(
                [
                    _resolve_closed_value(argument, bindings)[0]
                    for argument in value["args"]
                ]
            )
        bindings.append((body["name"], value))
        body = body["body"]
    assert len(effects) == 2
    assert [
        tuple((argument["k"], argument.get("v")) for argument in effect["argv"])
        for effect in effects
    ] == list(expected_argv)
    assert len(calls) == 1 and len(calls[0]) == 2
    effect_by_argv = {
        tuple((argument["k"], argument.get("v")) for argument in effect["argv"]): effect
        for effect in effects
    }
    assert calls[0][0]["k"] == "perform"
    assert calls[0][0]["site"] == effect_by_argv[()]["site"]
    assert calls[0][1]["k"] == "perform"
    assert calls[0][1]["site"] == effect_by_argv[(("lit", 99),)]["site"]
    assert sum(
        node.get("k") == "perform" for node in _walk_dataclasses(program.tree)
        if isinstance(node, dict)
    ) == 3


def test_nested_zero_input_effectful_bound_value_runs_before_later_effects(
    tmp_path: Path,
) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/nested_zero_input_effect) (export run)
      (defproc helper ((fixed Int) (y Int)) -> Int
        :effects ((uses-command fetch)) :lowering inline
        (command-result fetch :argv ("python" "probe.py" fixed y) :returns Int))
      (defproc apply-one ((callback ProcRef[Int -> Int]) (y Int)) -> Int
        :effects () :lowering inline (callback y))
      (defproc invoke ((runner ProcRef[Int -> Int]) (y Int)) -> Int
        :effects () :lowering inline (runner y))
      (defworkflow run ((x Int)) -> Int
        (let* ((hook (bind-proc (proc-ref apply-one) :callback
                      (bind-proc (proc-ref helper) :fixed
                        (command-result fetch :argv ("python" "probe.py") :returns Int)))))
          (let* ((x 100)
                 (middle (command-result fetch :argv ("python" "probe.py" 99) :returns Int))
                 (direct (hook 2))
                 (through-ref (invoke hook 3)))
            (+ direct through-ref)))))'''
    root = tmp_path / "nested_zero_input_effect"
    path = install(root, source)
    typed = compile_typed_program(
        path,
        entry_workflow="cp/nested_zero_input_effect::run",
        source_roots=(root,),
        command_boundaries=BOUNDARIES,
        workspace_root=root,
    )
    path.unlink()

    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (program.tree, program.sites, program.digest) == (
        restored.tree,
        restored.sites,
        restored.digest,
    )
    assert sum(
        node.get("k") == "perform" for node in _walk_dataclasses(program.tree)
        if isinstance(node, dict)
    ) == 3
    creation_effects = []
    bindings = []
    checked_calls = 0
    body = program.tree["body"]
    while body["k"] == "let":
        value = body["value"]
        if value["k"] == "perform":
            creation_effects.append(value)
        if (
            value["k"] == "call"
            and program.tree["definitions"][value["callee"]]["key"][2]
            in {"invoke", "apply-one"}
        ):
            capture, _, _ = _resolve_closed_value(value["args"][0], bindings)
            assert capture["k"] == "perform"
            assert capture["site"] == creation_effects[0]["site"]
            assert capture["argv"] == []
            checked_calls += 1
        bindings.append((body["name"], value))
        body = body["body"]
    assert len(creation_effects) == 2
    assert creation_effects[0]["argv"] == []
    assert [(arg["k"], arg.get("v")) for arg in creation_effects[1]["argv"]] == [
        ("lit", 99),
    ]
    assert checked_calls == 2


def test_inherited_name_captures_keep_their_distinct_creation_regions(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/inherited_name_capture) (export run)
      (defproc helper ((fixed Int) (offset Int) (y Int)) -> Int
        :effects ((uses-command fetch)) :lowering inline
        (command-result fetch :argv ("python" "probe.py" fixed offset y) :returns Int))
      (defproc invoke ((runner ProcRef[Int -> Int]) (y Int)) -> Int
        :effects () :lowering inline (runner y))
      (defworkflow run ((x Int)) -> Int
        (let* ((inner (bind-proc (proc-ref helper) :fixed x)))
          (let* ((x 100) (outer (bind-proc inner :offset x)))
            (invoke outer 2)))))'''
    root = tmp_path / "inherited_name_capture"
    path = install(root, source)
    typed = compile_typed_program(
        path,
        entry_workflow="cp/inherited_name_capture::run",
        source_roots=(root,),
        command_boundaries=BOUNDARIES,
        workspace_root=root,
    )
    path.unlink()

    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (program.tree, program.sites, program.digest) == (
        restored.tree,
        restored.sites,
        restored.digest,
    )
    bindings = []
    body = program.tree["body"]
    while body["k"] == "let":
        bindings.append((body["name"], body["value"]))
        body = body["body"]
    shadow = next(
        index
        for index, (name, value) in enumerate(bindings)
        if name == "x" and value.get("k") == "lit" and value.get("v") == 100
    )
    original_alias = next(
        binding_name
        for index, (binding_name, value) in enumerate(bindings)
        if index < shadow
        and value.get("k") == "name"
        and value.get("n") == "x"
    )
    shadow_alias = next(
        binding_name
        for index, (binding_name, value) in enumerate(bindings)
        if index > shadow
        and value.get("k") == "name"
        and value.get("n") == "x"
    )
    invoke = next(
        node
        for node in _walk_dataclasses(program.tree["body"])
        if isinstance(node, dict)
        and node.get("k") == "call"
        and node.get("callee", "").startswith("procedure:cp/inherited_name_capture::invoke[")
    )
    assert invoke["args"][:2] == [
        {"k": "name", "n": original_alias},
        {"k": "name", "n": shadow_alias},
    ]


def test_capture_origin_is_opaque_to_artifacts_and_wcc_identity() -> None:
    field = next(
        item for item in fields(WccSpecializationCapture) if item.name == "source_binding"
    )
    assert not field.repr and not field.compare and not field.hash
    assert field.metadata["json_omit_always"] is True
    assert field.metadata["semantic_identity_omit"] is True
    left = WccSpecializationCapture("argument", 0, "x", None, source_binding=object())
    right = WccSpecializationCapture("argument", 0, "x", None, source_binding=object())
    assert left == right and hash(left) == hash(right)
    assert "source_binding" not in repr(left)


def test_generated_boundary_requires_whole_d_equal_signature_and_counts_capture_changes(monkeypatch) -> None:
    class Projection:
        def key_type(self, type_ref):
            return type_ref.key_type

    def project_type(type_ref, *, typed):
        return type_ref.descriptor

    monkeypatch.setattr(closed_build, "_run_ref_signatures", lambda _typed: Projection())
    monkeypatch.setattr(closed_build, "canonical_type_descriptor", project_type)
    source = object()
    route = ["parameter", "captured"]
    projected = {"kind": "generated", "signature": ["same-S"]}
    caller = SimpleNamespace(key_type=projected, descriptor={"kind": "record", "name": "generated::CaptureA"})
    native = {"kind": "record", "name": "generated::CaptureB"}
    key = [
        "sample",
        "workflow",
        "target",
        [],
        [],
        [],
        [],
        [{"type": projected, "routes": [route]}],
        {"params": [], "result": {"kind": "primitive", "name": "Int"}},
    ]
    common = {
        "caller_types": [caller],
        "caller_type_scopes": [source],
        "caller_result_ref": SimpleNamespace(
            key_type={"kind": "primitive", "name": "Int"},
            descriptor={"kind": "primitive", "name": "Int"},
        ),
        "caller_scope": source,
        "caller_params": [["capture0", caller.descriptor]],
        "capture_routes": [[route]],
        "native_params": [["capture0", native]],
        "native_result": {"kind": "primitive", "name": "Int"},
        "key": key,
    }

    assert closed_build.Builder._ordinary_generated_signature_boundary(**common)

    caller.key_type = {"kind": "record", "owner": "authored::DifferentNominal"}
    assert not closed_build.Builder._ordinary_generated_signature_boundary(**common)


def test_discriminant_operator_keeps_its_declared_enum_descriptor_after_source_removal(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule choice) (export run)
      (defunion Choice (YES) (NO))
      (defworkflow run ((choice Choice) (other Choice)) -> Bool
        (= choice.variant other.variant)))'''
    path = install(tmp_path, source)
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        workspace_root=tmp_path,
    )
    path.unlink()
    entry = typed.entry
    wcc = normalize_wcc_body_to_anf(
        elaborate_typed_workflow_body(
            entry.typed_body,
            owner_name=entry.definition.name,
            type_env=typed.workflow_type_env(entry.definition.name),
            value_env=dict(entry.signature.params),
            workflow_return_types={
                name: workflow.signature.return_type_ref
                for name, workflow in typed.workflows.items()
            },
            procedure_return_types={},
            resolved_procedures_by_name=typed.procedures,
            procedure_type_envs=typed.procedure_type_envs,
            route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
            closed_program=True,
        )
    )

    def walk(node):
        if isinstance(node, (tuple, list)):
            for value in node:
                yield from walk(value)
        elif is_dataclass(node) and not isinstance(node, type):
            yield node
            for item in fields(node):
                if item.name != "metadata":
                    yield from walk(getattr(node, item.name))

    (operator,) = [node for node in walk(wcc) if isinstance(node, WccPureOp)]
    assert [canonical_type_descriptor(arg.metadata.type_ref, typed=typed) for arg in operator.args] == [
        {"kind": "enum", "name": "choice::Choice.variant", "allowed": ["YES", "NO"]},
        {"kind": "enum", "name": "choice::Choice.variant", "allowed": ["YES", "NO"]},
    ]
