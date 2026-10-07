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
from orchestrator.workflow_lisp.closed.sites import _ast_nodes, _value_nodes
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


def test_macro_reference_calls_keep_their_exact_return_types(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/macro_returns) (export run)
      (defproc integer () -> Int :effects ((uses-command fetch)) :lowering inline
        (command-result fetch :argv ("python" "probe.py") :returns Int))
      (defproc text () -> String :effects ((uses-command fetch)) :lowering inline
        (command-result fetch :argv ("python" "probe.py") :returns String))
      (defproc apply :forall (T) ((hook ProcRef[() -> T])) -> T
        :effects () :lowering inline (hook))
      (defmacro invoke (hook) (apply (proc-ref hook)))
      (defworkflow run () -> String
        (let* ((number (invoke integer)) (answer (invoke text))) answer)))'''
    program = build(tmp_path, source)
    tree = program.tree
    rows = [row for row in tree['definitions'].values()
        if row['key'][:3] == ['cp/macro_returns', 'procedure', 'apply']]
    assert len(rows) == 2
    calls = [node for node in _ast_nodes(tree['body']) if node['k'] == 'call']
    assert [tree['definitions'][call['callee']]['result']['name'] for call in calls] == ['Int', 'String']
    assert ClosedProgram.from_artifact(program.artifact()).tree == tree


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


def test_three_static_call_sites_retain_exact_value_keys_and_three_frames(tmp_path: Path) -> None:
    closed = build(tmp_path, fixture("three_call_sites"))
    calls = []
    body = closed.tree["body"]
    while body["k"] == "let":
        if body["value"]["k"] == "call":
            calls.append(body["value"])
        body = body["body"]

    assert len(calls) == len(closed.tree["definitions"]) == 3
    first_key = closed.tree["definitions"][calls[0]["callee"]]["key"]
    for value, call, name in zip((1, 2, 3), calls, ("a", "b", "c"), strict=True):
        _assert_static_call_site_key(closed, first_key, value, call, name)
    assert closed.sites == tuple((call["callee"], "#1") for call in calls)
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
        (callee,) = [name for name, row in restored.tree['definitions'].items()
            if row['key'][:3] == ['cp/arms_in_loop', 'procedure', 'fetch']]
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
        (helper_name, helper_definition), = [(name, row)
            for name, row in helper_restored.tree['definitions'].items()
            if row['key'][:3] == ['cp/arms_in_loop', 'workflow', 'helper']]
        (helper_callee,) = [name for name, row in helper_restored.tree['definitions'].items()
            if row['key'][:3] == ['cp/arms_in_loop', 'procedure', 'fetch']]
        helper_calls = [
            node
            for node in _ast_nodes(helper_definition["body"])
            if node.get("k") == "call" and node.get("callee") == helper_callee
        ]
        assert helper_restored.sites == ((helper_callee, "#1"),)
        assert len(helper_calls) == 3
        assert [call["frame"] for call in helper_calls] == [
            f"loop:state[*] / got / body / {variant} / #1={helper_callee}"
            for variant in ("FIRST", "SECOND", "THIRD")
        ]
        entry_calls = [
            node for node in _ast_nodes(helper_restored.tree["body"])
            if node.get("k") == "call"
            and node.get("callee") == helper_name
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


def _assert_shared_ref_static_variants(definitions):
    invokes = [row for row in definitions.values() if row["key"][2] == "invoke"]
    helpers = [row for row in definitions.values() if row["key"][2] == "helper"]
    assert len(invokes) == len(helpers) == 2
    assert invokes[0]["key"][4] == invokes[1]["key"][4]
    integer = _assert_shared_reference_binding(invokes)
    for variants in (invokes, helpers):
        ordered = sorted(variants, key=lambda row: row["key"][6][0][2]["v"])
        for row, value in zip(ordered, (2, 3), strict=True):
            _assert_static_reference_capture_variant(row, value, integer)


@pytest.mark.parametrize(
    ("body", "expected_ops", "expected_calls", "expected_performs", "expected_reached_calls"),
    (
        (
            "(let* ((z (+ x 1))) (invoke (bind-proc (proc-ref helper) :fixed z) x))",
            1,
            2,
            1,
            1,
        ),
        (
            "(invoke (bind-proc (proc-ref helper) :fixed (+ x 1)) x)",
            1,
            2,
            1,
            1,
        ),
        (
            "(let* ((hook (bind-proc (proc-ref helper) :fixed (+ x 1)))) "
            "(let* ((x 100) (first (invoke hook 2)) (second (invoke hook 3))) "
            "(+ first second)))",
            2,
            4,
            2,
            2,
        ),
    ),
    ids=("hoisted-control", "direct-computed", "stored-after-shadow"),
)
def test_computed_proc_ref_argument_is_evaluated_at_its_binding_region(
    tmp_path: Path,
    body: str,
    expected_ops: int,
    expected_calls: int,
    expected_performs: int,
    expected_reached_calls: int,
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
    assert len([node for node in nodes if node["k"] == "perform"]) == expected_performs
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
    assert checked_calls == expected_reached_calls
    if expected_performs == 2:
        _assert_shared_ref_static_variants(program.tree["definitions"])
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


def _assert_created_ref_variants(definitions, *, nested=False):
    integer = {"kind": "primitive", "name": "Int"}
    helpers = [row for row in definitions.values() if row["key"][2] == "helper"]
    assert len(helpers) == 2
    ordered = sorted(helpers, key=lambda row: row["key"][6][0][2]["v"])
    for row, value in zip(ordered, (2, 3), strict=True):
        _assert_static_reference_capture_variant(row, value, integer)
    if nested:
        _assert_created_callback_binding(definitions, integer)


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
    ) == 4
    _assert_created_ref_variants(program.tree["definitions"])

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
    ) == 4
    _assert_created_ref_variants(program.tree["definitions"], nested=True)
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


def test_retained_nested_match_cannot_read_same_typed_outer_binder(tmp_path, monkeypatch):
    from dataclasses import replace
    from tests.test_workflow_lisp_closed_command_transport import _compile
    from tests.test_workflow_lisp_closed_command_requests import _prepared_entry
    from tests.test_workflow_lisp_closed_preparation_integrity import _opaque_map_body, _prepare_other_owner, _registrations, _forbid_emission
    from orchestrator.workflow_lisp.expressions import MatchExpr

    declaration = '(defunion Choice (A (n Int)) (B (n Int)))'
    declaration += '(defproc helper ((values List[Choice])) -> List[Int] :effects ((uses-command echo)) :lowering inline '
    declaration += '(let* ((out (command-result echo :argv ("python" "probe.py") :returns Int))) '
    declaration += '(list/map ((item values)) (match item ((A outer) '
    declaration += '(match item ((A inner) inner.n) ((B fallback) fallback.n))) ((B other) other.n)))))'
    first = _compile(tmp_path / 'first', '(helper values)', params='(values List[Choice])', declarations=declaration, returns='List[Int]')
    _, _, builder = _prepared_entry(first)
    second = _compile(tmp_path / 'second', '(helper values)', params='(values List[Choice])', declarations=declaration, returns='List[Int]')
    registrations = _registrations(builder)
    _forbid_emission(monkeypatch, builder)

    def retarget(expr):
        assert isinstance(expr, MatchExpr)
        outer = expr.arms[0]
        assert isinstance(outer.body, MatchExpr)
        inner = outer.body.arms[0]
        assert outer.variant_name == inner.variant_name == 'A'
        assert outer.binding_identity != inner.binding_identity
        changed = replace(inner.body, base=replace(inner.body.base, name=outer.binding_name))
        nested = replace(outer.body, arms=(replace(inner, body=changed), outer.body.arms[1]))
        return replace(expr, arms=(replace(outer, body=nested), expr.arms[1]))

    def mutate(body, call, source):
        return _opaque_map_body(body, retarget) if call.definition.name.endswith('helper') else body

    with pytest.raises(ValueError, match=r'contradictory prepared.*\.base'):
        _prepare_other_owner(second, builder, monkeypatch, mutate)
    assert _registrations(builder) == registrations


@pytest.mark.parametrize('formal,type_name,declaration,wire,suffix,active,inactive', [
    ('pair', 'Pair', '(defrecord Pair (x Int))', 'pair__x', (), {'x': 7}, None),
    ('payload', 'Value', '', 'payload', ('z', 'nested'), {'z': {'nested': 7}}, {'z': None}),
    ('choice', 'Choice', '(defunion Choice (A (x Int)) (B))', 'choice__x', (),
        {'variant': 'A', 'x': 7}, {'variant': 'B'}),
])
def test_source_owned_command_rows_preserve_native_projection_and_dynamic_suffix(
    tmp_path, formal, type_name, declaration, wire, suffix, active, inactive,
):
    from orchestrator.workflow_lisp.closed.program import ClosedProgram
    from tests.test_workflow_lisp_closed_command_transport import _compile, _command, _commands

    expression = 'inputs.' + wire + ''.join('.' + part for part in suffix)
    body = _command('"${' + expression + '}" "${inputs.' + formal + '.x}"')
    closed = build_closed_program(_compile(tmp_path, body,
        params='(' + formal + ' ' + type_name + ')', declarations=declaration))
    (command,) = _commands(closed.tree)
    slot = command['argv_transport'][0]['parts'][0]
    assert slot['name'] == ['input', formal, wire]
    assert slot['path'] == list(suffix)
    native_wire, descriptor = closed.tree['params'][0]
    assert slot['value']['n'] == native_wire
    assert closed.tree['command_params'] == [[formal, 0]]
    _assert_command_boundary_suffix(formal, descriptor, wire, active, inactive, suffix)
    if formal != 'payload':
        assert command['argv_transport'][1] == {'kind': 'template', 'parts': [
            {'kind': 'missing', 'expression': 'inputs.' + formal + '.x'}]}
    assert ClosedProgram.from_artifact(closed.artifact()).tree == closed.tree


def test_reference_and_command_captures_keep_their_distinct_binding_owners(tmp_path):
    from tests.test_workflow_lisp_closed_command_transport import _compile, _command, _commands

    declarations = '(defproc helper ((fixed Int) (n Int)) -> Int '
    declarations += ':effects ((uses-command echo)) :lowering inline '
    declarations += _command('"${inputs.input}" fixed n') + ')'
    declarations += '(defproc invoke ((runner ProcRef[Int -> Int]) (n Int)) -> Int '
    declarations += ':effects () :lowering inline (runner n))'
    source = '(let* ((hook (bind-proc (proc-ref helper) :fixed input))) (invoke hook 1))'
    closed = build_closed_program(_compile(tmp_path, source, params='(input Int)',
        declarations=declarations))
    (invoke,) = [row for row in closed.tree['definitions'].values() if row['key'][2] == 'invoke']
    assert [capture['routes'] for capture in invoke['key'][7]] == [
        [['reference', ['runner'], ['parameter', 'fixed']]], [['command-input', 'input']]]
    assert len(invoke['params']) == 2
    (call,) = [node for node in _ast_nodes(closed.tree['body']) if node['k'] == 'call']
    assert len(call['args']) == len(invoke['params'])
    _assert_distinct_capture_binding_roots(closed, call)
    (command,) = _commands(closed.tree)
    assert command['argv_transport'][0]['parts'][0]['name'] == ['input', 'input', 'input']
    assert ClosedProgram.from_artifact(closed.artifact()).tree == closed.tree


def _opaque_command_program(tmp_path, argument='"${inputs.root}:${loop.index}"', *, local_command=False):
    from tests.test_workflow_lisp_closed_command_transport import _compile, _command

    declarations = '(defun make-block ((value Int)) -> Int (let* ((inside (+ value 1))) inside))'
    declarations += '(defproc child ((n Int)) -> Int :effects ((uses-command echo)) :lowering inline '
    declarations += _command(argument) + ')'
    body = '(loop/recur :max 1 :state 0 :on-exhausted 0 (fn (state) '
    local = _command('"${inputs.root}:${loop.index}"') if local_command else '1'
    body += '(let* ((held (make-block (+ (child state) ' + local + ')))) (done held))))'
    return _compile(tmp_path, body, declarations=declarations, params='(root Int)')


def _assert_opaque_body_continuity(program, body, builder):
    from dataclasses import replace
    from orchestrator.workflow_lisp.build_manifest_io import _json_data
    from orchestrator.workflow_lisp.wcc.hygiene import _free_names, _renamed
    from orchestrator.workflow_lisp.wcc.model import WccNameAtom, WccOpaqueFrontendValue
    from tests.test_workflow_lisp_closed_command_transport import (
        _walk_wcc,
    )

    (opaque,) = [node for node in _walk_wcc(body) if isinstance(node, WccOpaqueFrontendValue) and node.normalized_body is not None]
    assert opaque.expr is None and normalize_wcc_body_to_anf(body) == body
    _assert_opaque_planning_continuity(program, builder)
    state = next(node for node in _walk_wcc(opaque.normalized_body) if isinstance(node, WccNameAtom) and node.name == 'state')
    renamed = _renamed(opaque, {'state': replace(state, name='retained-state')})
    assert 'retained-state' in _free_names(renamed) and 'state' not in _free_names(renamed)
    assert 'normalized_body' not in _json_data(replace(opaque, expr=program.entry.typed_body, normalized_body=None))


def test_opaque_normalized_child_inherits_loop_inputs_and_survives_anf_hygiene(tmp_path):
    from orchestrator.workflow_lisp.closed.command_templates import _wcc_call_nodes
    from tests.test_workflow_lisp_closed_command_requests import _prepared_entry
    from tests.test_workflow_lisp_closed_command_transport import _commands

    program = _opaque_command_program(tmp_path, local_command=True)
    body, children, builder = _prepared_entry(program)
    (child,) = children.values()
    assert builder.definitions == {} and builder.run_ref_producers == []
    assert len(list(_wcc_call_nodes(body))) == len(children) == 1
    _assert_opaque_body_continuity(program, body, builder)
    assert child.command_interface['decisions']
    closed = build_closed_program(program)
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (closed.tree, closed.sites, closed.digest)
    commands = _commands(closed.tree)
    assert len(commands) == 2
    slots = [[part['name'] for part in command['argv_transport'][0]['parts'] if part['kind'] == 'slot'] for command in commands]
    assert slots == [[['input', 'root', 'root'], ['loop-index']], []]


def test_opaque_child_decisions_and_body_integrity_are_prepared_before_parent_key(tmp_path, monkeypatch):
    from tests.test_workflow_lisp_closed_command_requests import _prepared_entry
    from tests.test_workflow_lisp_closed_preparation_integrity import (
        _forbid_emission, _prepare_other_owner, _registrations,
    )

    first = _opaque_command_program(tmp_path / 'first', '"first-${loop.index}"')
    body, children, builder = _prepared_entry(first)
    (request,) = children.values()
    second = _opaque_command_program(tmp_path / 'second', '"second-${loop.index}"')
    registrations = _registrations(builder)
    _forbid_emission(monkeypatch, builder)
    with pytest.raises(ValueError, match='contradictory prepared'):
        _prepare_other_owner(second, builder, monkeypatch)
    assert _registrations(builder) == registrations
    assert request.canonical not in builder.definitions
    changed = _opaque_command_program(tmp_path / 'value', 'n')
    other_body, other_children, other_builder = _prepared_entry(changed)
    (other,) = other_children.values()
    assert request.key[:3] == other.key[:3]
    assert request.command_interface['decisions'] != other.command_interface['decisions']
    from orchestrator.workflow_lisp.closed.command_interfaces import command_interface

    def interface(root, requests, owner, source):
        return command_interface(root, native_rows=None, command_capture_rows=[],
            child_interfaces={key: row.command_interface for key, row in requests.items()},
            child_bearings={key: row.command_bearing for key, row in requests.items()},
            call_declaration_identity=lambda call: owner._command_declaration_identity(call, source, source.entry.definition.name))

    assert interface(body, children, builder, first)['decisions'] != interface(other_body, other_children, other_builder, changed)['decisions']


def _assert_runtime_proof_frames(before, after):
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import RUNTIME_REFERENCE
    from orchestrator.workflow_lisp.type_env import VariantCaseTypeRef

    assert before.values['choice'] == {'variant': RUNTIME_REFERENCE}
    name = 'choice' if 'choice' in after.values and isinstance(after.control.local_type_bindings.get('choice'), VariantCaseTypeRef) else next(name for name in ('scalar', 'record') if name in after.values)
    variant = after.control.local_type_bindings[name].variant_name
    expected = {'value': RUNTIME_REFERENCE} if variant == 'SCALAR' else {'value': {'text': RUNTIME_REFERENCE}}
    assert after.values[name] == expected
    if name == 'choice':
        _assert_retained_runtime_proof_binding(before, after, name, expected)


def test_compound_union_runtime_fact_uses_its_actual_proven_payload(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp.closed.command_templates import CommandScopeContext
    from tests.test_workflow_lisp_closed_command_transport import _compile, _command, _commands

    declarations = '(defrecord Payload (text String)) (defunion Choice (SCALAR (value Int)) (RECORD (value Payload)))'
    body = '(match choice ((SCALAR scalar) ' + _command('scalar.value') + ') ((RECORD record) ' + _command('record.value.text') + '))'
    transitions = []
    actual = CommandScopeContext.arm

    def observe(context, *args, **kwargs):
        result = actual(context, *args, **kwargs)
        child = result[1]
        if child.values != context.values:
            transitions.append((context, child))
        return result

    monkeypatch.setattr(CommandScopeContext, 'arm', observe)
    program = _compile(tmp_path, body, params='(choice Choice)', declarations=declarations)
    closed = build_closed_program(program)
    assert len(transitions) == 2
    for before, after in transitions:
        _assert_runtime_proof_frames(before, after)
    commands = _commands(closed.tree)
    assert len(commands) == 2
    assert [row['argv_transport'] for row in commands] == [[{'kind': 'value'}]] * 2
    assert sorted(row['argv'][0]['path'] for row in commands) == [['value'], ['value', 'text']]
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (closed.tree, closed.sites, closed.digest) == (restored.tree, restored.sites, restored.digest)


def test_compound_union_if_proof_updates_actual_elaboration_frames(tmp_path, monkeypatch):
    """Isolate typed-expression transport; Stage3 retypecheck rejects this source."""
    from orchestrator.workflow_lisp.closed.command_templates import CommandScopeContext, elaborate_command_scopes
    from orchestrator.workflow_lisp.expressions import elaborate_expression
    from orchestrator.workflow_lisp.typecheck import typecheck_expression
    from tests.test_workflow_lisp_closed_command_transport import _compile, _command, _scope_inputs
    from tests.test_workflow_lisp_command_scopes import _without_scopes
    from tests.test_workflow_lisp_strict_boolean_control_flow import _expression_syntax

    program = _compile(tmp_path, '0', params='(choice Choice)', declarations='(defrecord Payload (text String)) (defunion Choice (SCALAR (value Int)) (RECORD (value Payload)))')
    inputs, facts = _scope_inputs(program, closed_build.Builder(program))
    source = '(if (= choice.variant RECORD) ' + _command('choice.value.text') + ' ' + _command('choice.value') + ')'
    expr = elaborate_expression(_expression_syntax(source), bound_names=frozenset(inputs['value_env']), target_dsl_version='2.35')
    typed = typecheck_expression(expr, type_env=inputs['type_env'], value_env=inputs['value_env'])
    assert typed.expr.true_proof_context and typed.expr.false_proof_context
    transitions = []
    actual = CommandScopeContext.narrow

    def observe(context, *args, **kwargs):
        child = actual(context, *args, **kwargs)
        if child.values != context.values:
            transitions.append((context, child))
        return child

    monkeypatch.setattr(CommandScopeContext, 'narrow', observe)
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(typed, **inputs))
    scoped = elaborate_command_scopes(typed, **inputs, incoming_command_facts=facts, producer_lowering_schema=program.producer_lowering_schema)
    assert len(transitions) == 2
    for before, after in transitions:
        _assert_runtime_proof_frames(before, after)
    assert _without_scopes(neutral) == _without_scopes(scoped)
    assert normalize_wcc_body_to_anf(scoped) == scoped


def _constructor_memo_source(kind):
    from tests.test_workflow_lisp_closed_command_transport import _command

    payload = '(record Payload :n seed :flag true :text "same")'
    constructor = payload if kind == 'record' else '(variant Choice BOX :value ' + payload + ')'
    declarations = '(defrecord Payload (n Int) (flag Bool) (text String)) (defunion Choice (BOX (value Payload)) (EMPTY))'
    declarations += '(defproc carry ((value ' + ('Payload' if kind == 'record' else 'Choice') + ')) -> Int :effects ((uses-command echo)) :lowering inline ' + _command('"${inputs.root}"') + ')'
    body = '(let* ((seed 7) (saved ' + constructor + ') (alias saved) (first (carry saved)) (second (carry alias))) (let* ((seed 9) (last ' + constructor + ') (third (carry last)) (old (carry saved))) old))'
    return declarations, body


@pytest.mark.parametrize('kind', ['record', 'union'])
def test_constructor_alias_memo_retains_nested_tags_and_original_shadowed_fact(tmp_path, monkeypatch, kind):
    import json
    from collections import Counter
    from tests.test_workflow_lisp_closed_command_transport import _compile

    declarations, body = _constructor_memo_source(kind)
    program = _compile(tmp_path, body, params='(root Int)', declarations=declarations)
    actual_inputs = closed_build.Builder._preparation_inputs
    actual_prepare = closed_build.Builder._prepare_command_procedure
    observed, prepared = [], []

    def inputs(builder, procedure, source, captures, facts, actual_values, context):
        result = actual_inputs(builder, procedure, source, captures, facts, actual_values, context)
        observed.append(json.loads(result[-1])[0])
        return result

    def prepare(builder, procedure, *args, **kwargs):
        prepared.append(procedure.definition.name)
        return actual_prepare(builder, procedure, *args, **kwargs)

    monkeypatch.setattr(closed_build.Builder, '_preparation_inputs', inputs)
    monkeypatch.setattr(closed_build.Builder, '_prepare_command_procedure', prepare)
    closed = build_closed_program(program)
    payloads = []
    for fact in observed:
        payloads.append(_assert_constructor_memo_fact(fact, kind))
    assert Counter(payloads) == Counter({7: 3, 9: 1})
    assert prepared == ['cp/transport::carry'] * 2
    definitions = list(closed.tree['definitions'].values())
    assert len(definitions) == 2
    constants = []
    for row in definitions:
        _assert_constructor_memo_definition(row, kind, constants)
    assert sorted(constants) == [7, 9]
    assert len({json.dumps(row['key'], sort_keys=True) for row in definitions}) == 2
    assert ClosedProgram.from_artifact(closed.artifact()).tree == closed.tree


@pytest.mark.parametrize('kind', ['record', 'union'])
def test_constructor_field_order_keeps_one_typed_memo_preparation(tmp_path, monkeypatch, kind):
    from tests.test_workflow_lisp_closed_command_transport import _compile

    declarations, _ = _constructor_memo_source(kind)
    first = '(record Payload :n 7 :flag true :text "same")'
    second = '(record Payload :text "same" :flag true :n 7)'
    if kind == 'union':
        first = '(variant Choice BOX :value ' + first + ')'
        second = '(variant Choice BOX :value ' + second + ')'
    program = _compile(tmp_path, '(let* ((a ' + first + ') (b ' + second + ') (x (carry a)) (y (carry b))) y)',
        params='(root Int)', declarations=declarations)
    prepared = []
    original = closed_build.Builder._prepare_command_procedure

    def prepare(builder, procedure, *args, **kwargs):
        prepared.append(procedure.definition.name)
        return original(builder, procedure, *args, **kwargs)

    monkeypatch.setattr(closed_build.Builder, '_prepare_command_procedure', prepare)
    closed = build_closed_program(program)
    assert prepared == ['cp/transport::carry']
    assert len(closed.tree['definitions']) == 1
    records = [node for node in _ast_nodes(closed.tree['body']) if node['k'] == 'record']
    assert [[name for name, _ in node['fields']] for node in records] == [
        ['n', 'flag', 'text'], ['text', 'flag', 'n']]
    assert ClosedProgram.from_artifact(closed.artifact()).tree == closed.tree


def _closed_alias_payload(row):
    key = row['key']
    projections = {tuple(selector[3]['path']): (selector, descriptor, value)
        for selector, descriptor, value in key[6]}
    assert set(projections) == {('n',), ('variant',)}
    assert all(selector[:3] == ['projection', 'value', 0]
        for selector, _, _ in projections.values())
    assert projections[('variant',)][2]['v'] == 'YES'
    assert key[8]['params'] == [row['params'][0][1]]
    assert len(row['params']) == 1
    selector, descriptor, literal = projections[('n',)]
    assert descriptor == literal['type'] == {'kind': 'primitive', 'name': 'Int'}
    assert literal['k'] == 'lit'
    return literal['v']


def _assert_alias_entry_operands(closed):
    calls = [node for node in _ast_nodes(closed.tree['body']) if node['k'] == 'call']
    assert len(calls) == 2 and all(len(call['args']) == 1 for call in calls)
    assert [call['args'][0]['n'] for call in calls] == ['seven', 'nine']
    creations = [node for node in _ast_nodes(closed.tree['body']) if node['k'] == 'inject']
    assert [node['fields'][0][1]['v'] for node in creations] == [7, 9]
    assert set(call['callee'] for call in calls) == set(closed.tree['definitions'])


def test_retained_closed_union_aliases_keep_distinct_payload_keys_and_plans(tmp_path):
    from tests.test_workflow_lisp_closed_command_transport import _commands
    from tests.test_workflow_lisp_closed_shared_union_field import INT_SOURCE
    source = INT_SOURCE.replace('(extract (variant Choice YES :n 7))', '(let* ((seven (variant Choice YES :n 7)) (nine (variant Choice YES :n 9)) (a (extract seven)) (b (extract nine))) b)')
    path = install(tmp_path, source)
    program = compile_typed_program(path, entry_workflow='probe/shared_int::run', source_roots=(tmp_path,), workspace_root=tmp_path, command_boundaries={'probe': ExternalToolBinding(name='probe', stable_command=('python', 'probe.py'), closure=('probe.py',))})
    closed = build_closed_program(program)
    definitions = list(closed.tree['definitions'].values())
    assert len(definitions) == 2
    assert all(row['key'][:3] == ['probe/shared_int', 'procedure', 'extract'] for row in definitions)
    assert definitions[0]['key'][9] == definitions[1]['key'][9]
    values = [_closed_alias_payload(row) for row in definitions]
    assert sorted(values) == [7, 9]
    assert sorted(row['argv_transport'][0]['parts'][0]['text'] for row in _commands(closed.tree)) == ['7', '9']
    _assert_alias_entry_operands(closed)
    path.unlink()
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (closed.tree, closed.sites, closed.digest) == (restored.tree, restored.sites, restored.digest)


def _assert_retained_union_seed(value, expected):
    from orchestrator.workflow_lisp.expressions import LiteralExpr
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import RetainedExpressionFact

    assert isinstance(value, RetainedExpressionFact) and value.form == 'union'
    assert value.tag.value == 'BOX'
    payload = dict(value.fields)['value']
    seed = payload['n']
    assert isinstance(seed, LiteralExpr)
    assert (seed.literal_kind, type(seed.value), seed.value) == ('int', int, expected)


def test_wrapper_mapping_keeps_old_constructor_beside_new_creation_fact(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp.closed.command_templates import CommandScopeContext
    from tests.test_workflow_lisp_closed_command_transport import _compile, _command

    payload = '(record Payload :n seed :flag true :text "same")'
    constructor = '(variant Choice BOX :value ' + payload + ')'
    declarations, _ = _constructor_memo_source('union')
    declarations += '(defrecord Wrapper (u Choice)) (defrecord Duo (old Choice) (fresh Choice))'
    declarations += '(defproc consume ((value Duo)) -> Int :effects ((uses-command echo)) :lowering inline ' + _command('"${inputs.root}"') + ')'
    body = '(let* ((seed 7) (saved ' + constructor + ') (wrapped (record Wrapper :u ' + constructor + '))) (let* ((seed 9) (combined (record Duo :old saved :fresh ' + constructor + '))) (consume combined)))'
    retained = {}
    actual = CommandScopeContext.bind

    def observe(context, expr, **kwargs):
        child = actual(context, expr, **kwargs)
        if kwargs['name'] in ('wrapped', 'combined'):
            retained[kwargs['name']] = child.values[kwargs['name']]
        return child

    monkeypatch.setattr(CommandScopeContext, 'bind', observe)
    program = _compile(tmp_path, body, params='(root Int)', declarations=declarations)
    closed = build_closed_program(program)
    _assert_retained_union_seed(retained['wrapped']['u'], 7)
    _assert_retained_union_seed(retained['combined']['old'], 7)
    _assert_retained_union_seed(retained['combined']['fresh'], 9)
    assert ClosedProgram.from_artifact(closed.artifact()).tree == closed.tree


def test_partial_union_constructor_labels_get_projected_keys_while_preserving_runtime_input(tmp_path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule probe/partial_owner) (export run)
      (defrecord Output (n Int))
      (defunion Choice (YES (n Int) (label String)) (NO (n Int) (label String)))
      (defproc extract :forall (T) ((value T))
        :where ((T has-shared-union-field n Int)
                (T has-shared-union-field label String)) -> Output
        :effects ((uses-command probe)) :lowering inline
        (command-result probe
          :argv ("python" "probe.py" value.n value.label) :returns Output))
      (defworkflow run ((input Int)) -> Output
        (let* ((saved (variant Choice YES :n input :label "before"))
               (other (variant Choice YES :n input :label "after")))
          (let* ((input 9) (a (extract saved)) (b (extract other))) b))))'''
    path = install(tmp_path, source)
    program = compile_typed_program(
        path, entry_workflow='probe/partial_owner::run',
        source_roots=(tmp_path,), workspace_root=tmp_path,
        command_boundaries={'probe': ExternalToolBinding(
            name='probe', stable_command=('python', 'probe.py'), closure=('probe.py',),
        )},
    )
    path.unlink()
    closed = build_closed_program(program)

    definitions = [row for row in closed.tree['definitions'].values()
        if row['key'][:3] == ['probe/partial_owner', 'procedure', 'extract']]
    assert len(definitions) == 2
    by_label = {}
    projected_by_label = {}
    for definition in definitions:
        label, projected = _assert_partial_union_projections(definition)
        by_label[label] = definition
        projected_by_label[label] = projected
        _assert_partial_command(definition, label)

        _assert_partial_union_residual(definition)

    _assert_partial_union_variant_keys(by_label, projected_by_label)

    _assert_partial_operands(closed)

    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (closed.tree, closed.sites, closed.digest) == (restored.tree, restored.sites, restored.digest)


def _assert_partial_operands(closed):
    bindings, body = [], closed.tree['body']
    while body['k'] == 'let':
        bindings.append((body['name'], body['value']))
        body = body['body']
    input_wire = closed.tree['params'][0][0]
    _assert_partial_constructors(bindings, input_wire)
    calls = [node for node in _ast_nodes(closed.tree['body'])
        if node.get('k') == 'call'
        and closed.tree['definitions'][node['callee']]['key'][2] == 'extract']
    assert len(calls) == 2
    assert all(len(call['args']) == 1 and call['args'][0]['k'] == 'name' for call in calls)
    assert {call['args'][0]['n'] for call in calls} == {'saved', 'other'}



def _assert_partial_command(definition, label):
    (command,) = [node for node in _ast_nodes(definition['body'])
        if node.get('k') == 'perform' and node.get('class') == 'command']
    assert [row['kind'] for row in command['argv_transport']] == ['value', 'template']
    assert command['argv_transport'][1]['parts'][0]['text'] == label
    _assert_partial_command_field_operands(command)


def test_retained_record_variant_field_is_distinct_from_union_tag(tmp_path):
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import RecordExpr, UnionVariantExpr
    from orchestrator.workflow_lisp.lowering.values import _resolve_inline_expr_value, _resolve_inline_field_value
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import RetainedExpressionFact
    from tests.test_workflow_lisp_closed_command_transport import _compile

    program = _compile(tmp_path, '(let* ((record (record Payload :variant "ordinary" :n input)) (union (variant Choice YES :n input))) 0)',
        params='(input Int)', declarations='(defrecord Payload (variant String) (n Int)) (defunion Choice (YES (n Int)) (NO))')
    constructors = [node for node in walk_expr(program.entry.typed_body.expr)
        if isinstance(node, (RecordExpr, UnionVariantExpr))]
    assert len(constructors) == 2
    selected = [_resolve_inline_expr_value(expr, local_values={}, retain_expression_facts=True)
        for expr in constructors]
    assert all(isinstance(fact, RetainedExpressionFact) for fact in selected)
    values = [_resolve_inline_field_value(fact, field_path=('variant',), local_values={},
        retain_expression_facts=True) for fact in selected]
    assert [value.value for value in values] == ['ordinary', 'YES']
    assert dict(selected[0].fields)['n'] is dict(selected[1].fields)['n'] is None


def _assert_partial_constructors(bindings, input_wire):
    constructor_indices = []
    for name, label in (('saved', 'before'), ('other', 'after')):
        index, value = next((i, value) for i, (bound, value) in enumerate(bindings)
            if bound == name)
        constructor_indices.append(index)
        assert value['k'] == 'inject' and value['variant'] == 'YES'
        fields = dict(value['fields'])
        assert fields['n']['k'] == 'name' and fields['n']['n'] == input_wire
        assert fields['label']['k'] == 'lit' and fields['label']['v'] == label
    shadow_index = next(i for i, (_, value) in enumerate(bindings)
        if value.get('k') == 'lit' and value.get('v') == 9)
    assert max(constructor_indices) < shadow_index



def test_constructor_memo_distinguishes_creation_runtime_from_shadow_literal_and_reuses_aliases(tmp_path, monkeypatch):
    import json
    from collections import Counter
    from tests.test_workflow_lisp_closed_command_transport import _compile, _command

    declarations = '(defunion Choice (YES (n Int) (label String)) (NO (n Int) (label String)))'
    declarations += '(defproc extract :forall (T) ((value T)) :where ((T has-shared-union-field n Int) (T has-shared-union-field label String)) -> Int :effects ((uses-command echo)) :lowering inline ' + _command('value.n value.label') + ')'
    body = '(let* ((saved (variant Choice YES :n input :label "same")) (other (variant Choice YES :n renamed :label "same")) (alias saved)) (let* ((input 9) (literal (variant Choice YES :n input :label "same")) (a (extract saved)) (b (extract other)) (c (extract alias)) (d (extract literal))) d))'
    program = _compile(tmp_path, body, params='(input Int) (renamed Int)', declarations=declarations)
    original_inputs = closed_build.Builder._preparation_inputs
    original_prepare = closed_build.Builder._prepare_command_procedure
    facts, preparations = [], []

    def inputs(builder, *args):
        result = original_inputs(builder, *args)
        facts.append(json.loads(result[-1])[0])
        return result

    def prepare(builder, procedure, *args, **kwargs):
        preparations.append(procedure.definition.name)
        return original_prepare(builder, procedure, *args, **kwargs)

    monkeypatch.setattr(closed_build.Builder, '_preparation_inputs', inputs)
    monkeypatch.setattr(closed_build.Builder, '_prepare_command_procedure', prepare)
    closed = build_closed_program(program)
    assert len(facts) == 4
    payloads = [dict(fact[4])['n'] for fact in facts]
    assert Counter(json.dumps(value) for value in payloads) == Counter({json.dumps(['runtime']): 3, json.dumps(['literal', 'int', 'int', 9]): 1})
    runtime_facts = [fact for fact in facts if dict(fact[4])['n'] == ['runtime']]
    literal_facts = [fact for fact in facts if dict(fact[4])['n'] != ['runtime']]
    assert runtime_facts[0] == runtime_facts[1] == runtime_facts[2] != literal_facts[0]
    assert len(preparations) == 2 and len(set(preparations)) == 1
    _assert_runtime_literal_variants(closed)
    assert ClosedProgram.from_artifact(closed.artifact()).tree == closed.tree


def _assert_runtime_literal_variants(closed):
    definitions = list(closed.tree['definitions'].values())
    assert len(definitions) == 2
    paths = [set(tuple(selector[3]['path']) for selector, _, _ in row['key'][6]) for row in definitions]
    assert {frozenset(path) for path in paths} == {frozenset({('variant',), ('label',)}), frozenset({('variant',), ('label',), ('n',)})}
    assert all(len(row['key'][8]['params']) == len(row['params']) == 1 for row in definitions)
    commands = [node for row in definitions for node in _ast_nodes(row['body']) if node.get('k') == 'perform']
    assert sorted([plan['kind'] for plan in node['argv_transport']] for node in commands) == [['template', 'template'], ['value', 'template']]
    _assert_shadow_constructor_operands(closed)


def _assert_shadow_constructor_operands(closed):
    bindings, body = [], closed.tree['body']
    while body['k'] == 'let':
        bindings.append((body['name'], body['value']))
        body = body['body']
    constructors = [(index, value) for index, (_, value) in enumerate(bindings) if value['k'] == 'inject']
    _assert_shadow_constructor_binding_order(closed, bindings, constructors)


def test_retained_constructor_internal_let_and_if_freeze_selected_creation_facts(tmp_path):
    from orchestrator.workflow_lisp.expressions import elaborate_expression
    from orchestrator.workflow_lisp.lowering.values import _resolve_inline_expr_value
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import RUNTIME_REFERENCE, RetainedExpressionFact
    from orchestrator.workflow_lisp.typecheck import typecheck_expression
    from tests.test_workflow_lisp_closed_command_transport import _compile
    from tests.test_workflow_lisp_strict_boolean_control_flow import _expression_syntax

    program = _compile(tmp_path, '0', declarations='(defunion Choice (YES (n Int) (label String)) (NO))')
    env = program.workflow_type_env(program.entry.definition.name)
    source = '(let* ((label "before") (saved (variant Choice YES :n runtime :label label))) (let* ((label "after")) (if true saved (variant Choice NO))))'
    expr = elaborate_expression(_expression_syntax(source), bound_names=frozenset({'runtime'}), target_dsl_version='2.35')
    typed = typecheck_expression(expr, type_env=env, value_env={'runtime': env.resolve_type('Int', span=expr.span, form_path=expr.form_path)})
    fact = _resolve_inline_expr_value(typed.expr, local_values={'runtime': RUNTIME_REFERENCE}, retain_expression_facts=True)
    assert isinstance(fact, RetainedExpressionFact) and fact.form == 'union'
    assert fact.tag.value == 'YES'
    assert dict(fact.fields)['n'] is RUNTIME_REFERENCE
    assert dict(fact.fields)['label'].value == 'before'


def _assert_static_call_site_key(closed, first_key, value, call, name):
    definition = closed.tree["definitions"][call["callee"]]
    key = definition["key"]
    assert key[:3] == ["cp/three_call_sites", "procedure", "fetch"]
    int_type = {"kind": "primitive", "name": "Int"}
    assert key[6] == [["n", int_type, {"k": "lit", "v": value, "type": int_type}]]
    assert key[:6] + key[7:] == first_key[:6] + first_key[7:]
    assert key[8]["params"] == definition["params"] == call["args"] == []
    assert call["frame"] == f"{name}={call['callee']}"


def _assert_shared_reference_binding(invokes):
    (binding,) = invokes[0]["key"][4]
    assert binding[0] == "runner"
    integer = {"kind": "primitive", "name": "Int"}
    assert binding[1]["bound"] == [["fixed", integer, {"capture": 0}]]
    assert binding[1]["residual"] == {"params": [integer], "result": integer}
    assert binding[1]["target"][6] == []
    return integer


def _assert_static_reference_capture_variant(row, value, integer):
    assert row["key"][6] == [["y", integer, {"k": "lit", "type": integer, "v": value}]]
    assert row["key"][8] == {"params": [], "result": integer}
    assert len(row["params"]) == len(row["key"][7]) == 1
    assert row["params"][0][1] == integer


def _assert_created_callback_binding(definitions, integer):
    references = [row for row in definitions.values() if row["key"][2] == "apply-one"]
    assert len(references) == 2
    assert references[0]["key"][4] == references[1]["key"][4]
    (binding,) = references[0]["key"][4]
    assert binding[0] == "callback"
    assert binding[1]["bound"] == [["fixed", integer, {"capture": 0}]]
    assert binding[1]["residual"] == {"params": [integer], "result": integer}
    assert binding[1]["target"][6] == []


def _assert_command_boundary_suffix(formal, descriptor, wire, active, inactive, suffix):
    from orchestrator.variables.substitution import resolve_dictionary_suffix
    from orchestrator.workflow.type_descriptor import command_boundary_row, command_boundary_value

    row = command_boundary_row(formal, descriptor, wire)
    assert row is not None
    assert resolve_dictionary_suffix(command_boundary_value(active, descriptor, row), suffix) == 7
    if inactive is not None:
        assert resolve_dictionary_suffix(command_boundary_value(inactive, descriptor, row), suffix) is None


def _assert_distinct_capture_binding_roots(closed, call):
    bindings, body = [], closed.tree['body']
    while body['k'] == 'let' and body['value'] is not call:
        bindings.append((body['name'], body['value']))
        body = body['body']
    roots = [_resolve_closed_value(argument, bindings)[0] for argument in call['args']]
    assert roots[0]['k'] == roots[1]['k'] == 'name'
    assert roots[0]['n'] == roots[1]['n'] == closed.tree['params'][0][0]
    assert call['args'][0]['n'] != call['args'][1]['n']


def _assert_opaque_planning_continuity(program, builder):
    from orchestrator.workflow_lisp.closed.command_templates import _wcc_call_nodes
    from tests.test_workflow_lisp_closed_command_transport import (
        _planned, _scope_inputs, _without_authorized_annotations,
    )

    inputs, _ = _scope_inputs(program, builder)
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    planned, _ = _planned(program)
    assert _without_authorized_annotations(neutral) == _without_authorized_annotations(planned)
    assert len(list(_wcc_call_nodes(neutral))) == len(list(_wcc_call_nodes(planned))) == 1


def _assert_retained_runtime_proof_binding(before, after, name, expected):
    original = before.operands[name]
    current = after.operands[name]
    assert original.metadata.binding_identity == current.metadata.binding_identity
    assert before.retained_bindings[-1] in after.retained_bindings
    assert after.retained_bindings[-1][3] == expected


def _assert_constructor_memo_fact(fact, kind):
    if kind == 'union':
        assert fact[:4] == ['retained-expression', 'union', True, ['literal', 'string', 'str', 'BOX']]
        fact = dict(fact[4])['value']
    assert fact[0] == 'fields'
    fields = dict(fact[1])
    assert fields['flag'] == ['literal', 'bool', 'bool', True]
    assert fields['text'] == ['literal', 'string', 'str', 'same']
    assert fields['n'][:3] == ['literal', 'int', 'int']
    return fields['n'][3]


def _assert_constructor_memo_definition(row, kind, constants):
    assert len(row['key'][8]['params']) == len(row['key'][7]) == 1
    assert len(row['params']) == 2
    assert row['params'][-1][1] == row['key'][8]['params'][0]
    rows = {tuple(selector[3]['path']): value for selector, descriptor, value in row['key'][6]}
    prefix = ('value',) if kind == 'union' else ()
    constants.append(rows[(*prefix, 'n')]['v'])
    assert rows[(*prefix, 'flag')]['v'] is True
    assert rows[(*prefix, 'text')]['v'] == 'same'


def _assert_partial_union_projections(definition):
    projected = {
        tuple(selector[3]['path']): (selector, descriptor, literal)
        for selector, descriptor, literal in definition['key'][6]
        if isinstance(selector, list) and len(selector) == 4
        and selector[0] == 'projection'
    }
    assert set(projected) == {('label',), ('variant',)}
    assert all(row[0][:3] == ['projection', 'value', 0] for row in projected.values())
    assert projected[('variant',)][2]['v'] == 'YES'
    selector, descriptor, literal = projected[('label',)]
    assert descriptor == {'kind': 'primitive', 'name': 'String'}
    assert literal['k'] == 'lit' and literal['type'] == descriptor
    label = literal['v']
    assert label in {'before', 'after'}
    return label, projected


def _assert_partial_union_residual(definition):
    # K8 keeps the original Choice argument as a residual parameter.
    assert len(definition['params']) == 1
    assert definition['params'][0][1]['kind'] == 'union'
    assert definition['params'][0][1]['name'] == 'probe/partial_owner::Choice'
    assert definition['key'][8]['params'] == [definition['params'][0][1]]


def _assert_partial_union_variant_keys(by_label, projected_by_label):
    assert set(by_label) == {'before', 'after'}
    before, after = by_label['before'], by_label['after']
    assert before['key'][6] != after['key'][6]
    assert before['key'][:6] + before['key'][7:] == after['key'][:6] + after['key'][7:]
    assert projected_by_label['before'][('variant',)] == projected_by_label['after'][('variant',)]
    assert projected_by_label['before'][('label',)][:2] == projected_by_label['after'][('label',)][:2]


def _assert_partial_command_field_operands(command):
    assert command['argv'][0]['k'] == command['argv'][1]['k'] == 'field'
    assert command['argv'][0]['base']['n'] == command['argv'][1]['base']['n'] == 'value'
    assert command['argv'][0]['path'] == ['n']
    assert command['argv'][0]['shared'] == [{'kind': 'primitive', 'name': 'Int'}]
    assert command['argv'][1]['path'] == ['label']
    assert command['argv'][1]['shared'] == [{'kind': 'primitive', 'name': 'String'}]


def _assert_shadow_constructor_binding_order(closed, bindings, constructors):
    shadow_index, shadow_name = next((index, name) for index, (name, value) in enumerate(bindings)
        if value.get('k') == 'lit' and value.get('v') == 9)
    assert len(constructors) == 3
    names = [value['fields'][0][1]['n'] for _, value in constructors]
    assert names[:2] == [row[0] for row in closed.tree['params']]
    assert names[2] == shadow_name
    assert constructors[1][0] < shadow_index < constructors[2][0]
