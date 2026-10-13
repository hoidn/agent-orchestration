from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.closed.build import Builder
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.wcc.analysis import analyze_wcc_body, _free_wcc_names_in_body
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.defunctionalize import _wcc_body_nodes
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
from orchestrator.workflow_lisp.wcc.hygiene import _free_names, _renamed
from orchestrator.workflow_lisp.wcc.use_site_scope import rename_capturing_binders
from orchestrator.workflow_lisp.wcc.model import WccLet, WccNameAtom, WccJoin, WccCall, WccRecJoin
from orchestrator.workflow_lisp.closed.command_templates import _wcc_continuation_binding_demands
from tests.workflow_lisp_closed_program_helpers import BOUNDARIES, install


def source(body, *, declarations="", result="List[Box]", params="", imports=""):
    return f'''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
      (defmodule parallel) {imports} (export run) (defrecord Box (n Int))
      {declarations}
      (defworkflow run ({params}) -> {result} {body}))'''


COMMAND = '(command-result fetch :argv ("python" "probe.py" "fetch" repo) :returns Box)'
MAP = f'(list/map-effect ((repo (list "a" "b"))) :max 4 :parallel 2 :workspace repo {COMMAND})'


def prepare(tmp_path: Path, sources, *, entry_path=None):
    path = install(tmp_path, sources, entry_path=entry_path)
    typed = compile_typed_program(path, entry_workflow="parallel::run",
        source_roots=(tmp_path,), command_boundaries=BOUNDARIES)
    builder = Builder(typed)
    body = builder._workflow_wcc_body(typed.entry, typed)
    analyze_wcc_body(body)
    return typed, builder, body


def parallel_nodes(body):
    return [node for node in _wcc_body_nodes(body) if type(node).__name__ == "WccParallelMap"]


def test_production_wcc_preparation_retains_parallel_control(tmp_path):
    typed, _, body = prepare(tmp_path, source(MAP))
    node, = parallel_nodes(body)
    assert node.metadata.type_ref == typed.entry.typed_body.type_ref
    assert (node.max_count, node.parallel_count) == (4, 2)
    assert node.binder_name == "repo"
    assert node.binder_type_ref.name == "String"
    assert node.body.metadata.type_ref.name == "Box"
    assert node.workspace_body.metadata.type_ref.name == "String"
    assert node.binding_identity == typed.entry.typed_body.expr.binding_identity
    assert node.metadata.source_span == typed.entry.typed_body.expr.span
    assert len([n for n in _wcc_body_nodes(node.body) if type(n).__name__ == "WccLet"]) == 1


def test_map_joins_outer_continuation_without_retargeting_items(tmp_path):
    _, _, body = prepare(tmp_path, source(f'(let* ((batch {MAP})) (list/length batch))', result="Int"))
    node, = parallel_nodes(body)
    assert isinstance(body, WccJoin)
    assert any(type(n).__name__ == "WccHalt" for n in _wcc_body_nodes(node.body))
    assert not any(type(n).__name__ == "WccJump" for n in _wcc_body_nodes(node.body))
    demands = _wcc_continuation_binding_demands(body)
    assert {id(n) for n in _wcc_body_nodes(body)} <= demands.keys()


def test_pure_inline_workspace_and_body_keep_item_scope_and_provenance(tmp_path):
    declarations = '''(defproc cwd ((value String)) -> String :effects () :lowering inline
        (let* ((copy value)) (string/concat copy "/work")))
      (defproc identity ((value String)) -> String :effects () :lowering inline value)'''
    mapped = MAP.replace(":workspace repo", ":workspace (cwd repo)").replace(COMMAND, "(identity repo)")
    _, _, body = prepare(tmp_path, source(mapped, declarations=declarations, result="List[String]"))
    node, = parallel_nodes(body)
    assert isinstance(node.workspace_body, WccLet)
    assert _free_wcc_names_in_body(node.workspace_body) == {node.binder_name}
    assert _free_wcc_names_in_body(node.body) == {node.binder_name}
    assert _free_names(node) == set()
    assert any(n.metadata.expansion_stack for n in _wcc_body_nodes(node.workspace_body))
    assert any(n.metadata.expansion_stack for n in _wcc_body_nodes(node.body))


def test_source_is_outside_binder_and_hygiene_keeps_item_reads(tmp_path):
    mapped = MAP.replace('(list "a" "b")', 'repos').replace(":workspace repo", ':workspace (string/concat root repo)')
    _, _, body = prepare(tmp_path, source(mapped, params="(repos List[String]) (root String)"))
    node, = parallel_nodes(body)
    assert _free_wcc_names_in_body(node) == {"repos", "root"}
    assert _free_names(node) == {"repos", "root"}
    moved = _renamed(node, {"repos": "items", "root": "base", "repo": "wrong"})
    assert moved.source.name == "items"
    assert _free_wcc_names_in_body(moved.workspace_body) == {"repo", "base"}
    assert _free_wcc_names_in_body(moved.body) == {"repo"}


def test_use_site_rename_reaches_item_regions_but_preserves_source(tmp_path):
    _, _, body = prepare(tmp_path, source(MAP.replace('(list "a" "b")', "repos"),
        params="(repos List[String])"))
    node, = parallel_nodes(body)
    moved, params = rename_capturing_binders(node, live=frozenset({"repo"}))
    assert params == {}
    assert moved.binder_name != "repo"
    assert moved.source is node.source
    assert _free_wcc_names_in_body(moved.workspace_body) == {moved.binder_name}
    assert _free_wcc_names_in_body(moved.body) == {moved.binder_name}
    assert moved.binding_identity == node.binding_identity
    assert moved.binding_label == node.binding_label


def test_source_let_is_evaluated_once_before_item_scope(tmp_path):
    mapped = MAP.replace('(list "a" "b")', '(let* ((one root)) (list one one))')
    _, _, body = prepare(tmp_path, source(mapped, params="(root String)"))
    node, = parallel_nodes(body)
    outside = [n for n in _wcc_body_nodes(body) if isinstance(n, WccLet) and n not in tuple(_wcc_body_nodes(node.body))]
    assert len([n for n in outside if isinstance(n.bound_value, WccNameAtom) and n.bound_value.name == "root"]) == 1
    assert _free_wcc_names_in_body(body) == {"root"}


@pytest.mark.parametrize("kind", ["workflow", "procedure", "imported-workflow"])
def test_helper_bodies_use_real_wcc_preparation(tmp_path, kind):
    loop = f'''(loop/recur :max 2 :state (loop-state (n Int 0))
        :on-exhausted (record Box :n 0) (fn (state) (done {COMMAND})))'''
    workflow = f'(defworkflow worker ((repo String)) -> Box {loop})'
    call = '(call worker :repo repo)'
    declarations = workflow
    if kind == "procedure":
        declarations = f'(defproc worker ((repo String)) -> Box :effects ((uses-command fetch)) :lowering inline {loop})'
        call = '(worker repo)'
    sources = source(MAP.replace(COMMAND, call), declarations=declarations)
    if kind == "imported-workflow":
        sources = {"parallel.orc": source(MAP.replace(COMMAND, '(call helper.worker :repo repo)'),
            imports='(import helper :as helper :only (worker Box))', result="List[helper.Box]"),
            "helper.orc": f'''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
              (defmodule helper) (export worker Box) (defrecord Box (n Int)) {workflow})'''}
    typed, builder, body = prepare(tmp_path, sources, entry_path="parallel.orc" if isinstance(sources, dict) else None)
    node, = parallel_nodes(body)
    assert any(isinstance(n, WccLet) for n in _wcc_body_nodes(node.body))
    if kind == "procedure":
        procedure = next(p for p in typed.procedures.values() if p.definition.name.endswith("::worker"))
        prepared = elaborate_typed_workflow_body(procedure.typed_body, owner_name=procedure.definition.name,
            type_env=typed.procedure_type_envs[procedure.definition.name], value_env=dict(procedure.signature.params),
            procedure_return_types=builder.procedure_return_types, resolved_procedures_by_name=typed.procedures,
            closed_program=True)
        prepared = normalize_wcc_body_to_anf(prepared)
    else:
        helper = next(row for row in typed.workflows.values() if row.definition.name.endswith("::worker"))
        prepared = builder._workflow_wcc_body(helper, typed)
    assert any(isinstance(n, WccRecJoin) for n in _wcc_body_nodes(prepared))
    analyze_wcc_body(prepared)


def test_nested_map_in_workflow_helper_remains_control(tmp_path):
    helper = f'(defworkflow worker ((root String)) -> List[Box] {MAP.replace(":workspace repo", ":workspace (string/concat root repo)")})'
    mapped = MAP.replace(COMMAND, '(call worker :root repo)')
    typed, builder, body = prepare(tmp_path, source(mapped, declarations=helper, result="List[List[Box]]"))
    outer, = parallel_nodes(body)
    worker = next(row for row in typed.workflows.values() if row.definition.name.endswith("::worker"))
    inner, = parallel_nodes(builder._workflow_wcc_body(worker, typed))
    assert outer.body.metadata.type_ref.name == "List[Box]"
    assert _free_wcc_names_in_body(inner) == {"root"}
    assert inner.parallel_count == outer.parallel_count == 2


def test_inline_capture_survives_homonymous_item_binder(tmp_path):
    mapped = MAP.replace(COMMAND, '(hook repo)')
    declarations = f'''(defproc apply ((hook ProcRef[String -> String])) -> List[String]
        :effects () :lowering inline {mapped})'''
    body_source = f'''(let* ((repo "creation"))
      (let-proc (remember ((value String)) -> String :captures (repo) repo)
        (apply (proc-ref remember))))'''
    typed, _, body = prepare(tmp_path, source(body_source, declarations=declarations, result="List[String]"))
    node, = parallel_nodes(body)
    captures = [n.bound_value for n in _wcc_body_nodes(node.body)
        if isinstance(n, WccLet) and isinstance(n.bound_value, WccNameAtom) and n.bound_value.is_capture_read]
    assert len(captures) == 1
    assert captures[0].metadata.binding_identity != node.binding_identity
    assert captures[0].name == "repo"
    assert typed.entry.typed_body.type_ref.name == "List[String]"
