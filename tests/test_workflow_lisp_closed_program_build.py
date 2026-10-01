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
from orchestrator.workflow_lisp.wcc.model import WCC_M4_ROUTE_SCHEMA_VERSION, WccPureOp


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
