"""Phase 5 frontend admission; checked compilation belongs to later cuts."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from orchestrator.contracts.closed_program import targets
from orchestrator.workflow.run_ref import config
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.build_manifest_io import _json_data
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.names import _source_expression_identity
from orchestrator.workflow_lisp.compiler_session import CompilerSession
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.definitions import PathDef
from orchestrator.workflow_lisp.expression_traversal import free_expr_names, map_expr, iter_child_exprs, stamp_capture_origin
from orchestrator.workflow_lisp.expressions import LetStarExpr, ListMapEffectExpr, elaborate_expression
from orchestrator.workflow_lisp.functions import _clone_function_expr, _normalize_expr
from orchestrator.workflow_lisp.conditionals import _normalize_list_map
from orchestrator.workflow_lisp.procedure_typecheck import _semantic_identity
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, ListTypeRef, PathTypeRef, PrimitiveTypeRef
from orchestrator.workflow_lisp.typecheck import typecheck_expression
from orchestrator.workflow_lisp.workflows import WorkflowCatalog, WorkflowSignature
from tests.workflow_lisp_closed_program_helpers import BOUNDARIES, install


FORM = '(list/map-effect ((repo repos)) :max 4 :parallel 2 :workspace repo (call child :value repo))'


def parse(source=FORM, *, target="2.37", names=frozenset({"repos"}), procedures=frozenset()):
    tree = read_sexpr_text(source, source_path="parallel.orc")
    datum = tree.items[0]
    node = syntax.SyntaxNode(datum, datum.span, "parallel.orc", ("workflow-lisp", "parallel"))
    return elaborate_expression(node, target_dsl_version=target, bound_names=names, procedure_names=procedures)


def typed(source=FORM, *, target="2.37", values=None, expr=None):
    expr = expr or parse(source, target=target, names=frozenset(values or {"repos"}))
    string = PrimitiveTypeRef("String")
    env = FrontendTypeEnvironment({"String": string, "Int": PrimitiveTypeRef("Int")}, target_dsl_version=target)
    signature = WorkflowSignature("child", (("value", string),), string, expr.span, expr.form_path)
    return typecheck_expression(
        expr, type_env=env, value_env=values or {"repos": ListTypeRef("List[String]", string)},
        workflow_catalog=WorkflowCatalog({"child": signature}, {}, {}), compiler_session=CompilerSession(closed_program=True),
    )


def test_parallel_map_keeps_typed_control_and_binder_scope():
    result = typed()
    expr = result.expr
    assert isinstance(expr, ListMapEffectExpr)
    assert (expr.max_iterations, expr.parallel_count) == (4, 2)
    assert (expr.source_item_type_ref.name, expr.result_item_type_ref.name) == ("String", "String")
    assert result.type_ref.name == "List[String]"
    assert expr.workspace_expr.name == "repo"
    assert expr.binding_identity.kind == "map-effect"
    assert expr.workspace_expr.capture_origin is None
    assert expr.body_expr.bindings[0][1].capture_origin is None


@pytest.mark.parametrize("registry", [targets.SUPPORTED_TARGET_DSL_VERSIONS, config._SUPPORTED_TARGET_DSL_VERSIONS])
def test_target_237_is_registered(registry):
    assert "2.37" in registry


@pytest.mark.parametrize("target", ["2.18", "2.35", "2.36"])
def test_old_target_refuses_parallel_syntax(target):
    with pytest.raises(LispFrontendCompileError) as error:
        parse(target=target)
    assert error.value.diagnostics[0].code == "list_traversal_target_dsl_unsupported"


@pytest.mark.parametrize("clauses", [
    ":max 0 :parallel 2 :workspace repo", ":max -1 :parallel 2 :workspace repo",
    ":max true :parallel 2 :workspace repo", ":max 4 :parallel 0 :workspace repo",
    ":max 4 :parallel -1 :workspace repo", ":max 4 :parallel true :workspace repo",
    ":max 4 :parallel (+ 1 1) :workspace repo", ":max 4 :parallel 2",
    ":max 4 :workspace repo", ":max 4 :parallel 2 :workspace repo :workspace repo",
    ":max 4 :parallel 2 :parallel 3 :workspace repo", ":max 4 :parallel 2 :unknown repo",
])
def test_parallel_map_refuses_malformed_clauses(clauses):
    with pytest.raises(LispFrontendCompileError):
        parse(f"(list/map-effect ((repo repos)) {clauses} (call child :value repo))")


@pytest.mark.parametrize("workspace", ["1", "true", '(call child :value repo)'])
def test_parallel_map_requires_pure_string_workspace(workspace):
    with pytest.raises(LispFrontendCompileError):
        typed(FORM.replace(":workspace repo", f":workspace {workspace}"))


def test_workspace_is_in_item_scope_but_source_is_not():
    expr = parse(FORM.replace(":workspace repo", ":workspace (string/concat repo root)"), names=frozenset({"repos", "root"}))
    assert free_expr_names(expr) == {"repos", "root"}
    rewritten = map_expr(expr, lambda node: replace(node, name="moved") if node.name == "root" else node)
    assert rewritten.workspace_expr.args[1].name == "moved"
    assert rewritten.workspace_expr.args[0].name == "repo"
    assert expr.workspace_expr in iter_child_exprs(expr)
    stamped = stamp_capture_origin(expr, binding_env={"root": "root-owner", "repo": "outer-owner"}, value_env={"root": PrimitiveTypeRef("String"), "repo": PrimitiveTypeRef("String")})
    assert stamped.workspace_expr.args[1].capture_origin[0] == "root-owner"
    assert stamped.workspace_expr.args[0].capture_origin is None


@pytest.mark.parametrize("target", ["2.35", "2.36"])
def test_serial_map_preserves_rewrite_and_absent_field_identities(target, tmp_path):
    source = FORM.replace(" :parallel 2 :workspace repo", "")
    expr = parse(source, target=target)
    payload = _json_data(expr)
    assert "parallel_count" not in payload and "workspace_expr" not in payload
    assert "parallel_count" not in _semantic_identity(expr)
    assert "workspace_expr" not in _semantic_identity(expr)
    projection = _source_expression_identity(expr, typed=SimpleNamespace())
    assert "parallel_count" not in str(projection) and "workspace_expr" not in str(projection)
    path = install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
      (defmodule serial) (export run)
      (defworkflow child ((value String)) -> String value)
      (defworkflow run ((repos List[String])) -> List[String] {source}))''')
    program = compile_typed_program(path, entry_workflow="serial::run", source_roots=(tmp_path,), command_boundaries={})
    assert not isinstance(program.entry.typed_body.expr, ListMapEffectExpr)


def test_present_parallel_fields_change_both_semantic_identities():
    expr = parse()
    changed = replace(expr, parallel_count=3)
    assert _semantic_identity(expr) != _semantic_identity(changed)
    assert _source_expression_identity(expr, typed=SimpleNamespace()) != _source_expression_identity(changed, typed=SimpleNamespace())


def graph_source(target, module, body, imports=""):
    return f'(workflow-lisp (:language "0.1") (:target-dsl "{target}") (defmodule {module}) {imports} (export run) (defworkflow run () -> String {body}))'


@pytest.mark.parametrize("target", ["2.35", "2.36"])
def test_old_entry_refuses_new_source_import_even_without_parallel(target, tmp_path):
    path = install(tmp_path, {
        "entry.orc": graph_source(target, "entry", '(call h.run)', "(import helper :as h :only (run))"),
        "helper.orc": graph_source("2.37", "helper", '"ok"'),
    }, entry_path="entry.orc")
    with pytest.raises(LispFrontendCompileError) as error:
        compile_typed_program(path, entry_workflow="entry::run", source_roots=(tmp_path,), command_boundaries={})
    assert error.value.diagnostics[0].code == "evaluated_execution_target_direction_invalid"


@pytest.mark.parametrize("target", ["2.35", "2.36"])
def test_new_entry_can_call_old_source_helper(target, tmp_path):
    path = install(tmp_path, {
        "entry.orc": graph_source("2.37", "entry", '(call h.run)', "(import helper :as h :only (run))"),
        "helper.orc": graph_source(target, "helper", '"ok"'),
    }, entry_path="entry.orc")
    program = compile_typed_program(path, entry_workflow="entry::run", source_roots=(tmp_path,), command_boundaries={})
    assert program.target == "2.37"


@pytest.mark.parametrize("target", ["2.35", "2.36"])
def test_old_entry_refuses_new_snapshot_call(target, tmp_path):
    producer = install(tmp_path, graph_source("2.37", "producer", '"ok"'))
    snapshot = compile_typed_program(producer, entry_workflow="producer::run", source_roots=(tmp_path,), command_boundaries={})
    entry = install(tmp_path, graph_source(target, "consumer", "(call dep)"))
    with pytest.raises(LispFrontendCompileError) as error:
        compile_typed_program(entry, entry_workflow="consumer::run", source_roots=(tmp_path,), command_boundaries={}, imported_programs={"dep": snapshot})
    assert error.value.diagnostics[0].code == "evaluated_execution_target_direction_invalid"


@pytest.mark.parametrize("target", ["2.35", "2.36"])
def test_new_entry_can_call_old_snapshot(target, tmp_path):
    producer = install(tmp_path, graph_source(target, "producer", '"ok"'))
    snapshot = compile_typed_program(producer, entry_workflow="producer::run", source_roots=(tmp_path,), command_boundaries={})
    entry = install(tmp_path, graph_source("2.37", "consumer", "(call dep)"))
    program = compile_typed_program(entry, entry_workflow="consumer::run", source_roots=(tmp_path,), command_boundaries={}, imported_programs={"dep": snapshot})
    assert program.target == "2.37"


@pytest.mark.parametrize("source", ["1", "repo", '(call child :value "x")'])
def test_parallel_map_refuses_non_list_or_impure_source(source):
    with pytest.raises(LispFrontendCompileError):
        typed(FORM.replace("((repo repos))", f"((repo {source}))"))


def test_target_gate_does_not_change_evaluated_minimum():
    assert syntax.PARALLEL_MAP_MIN_TARGET_DSL_VERSION == "2.37"
    assert not syntax.target_dsl_supports_parallel_map("2.36")
    assert syntax.target_dsl_supports_parallel_map("2.37")
    assert syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION == "2.35"


def test_parallel_map_accepts_positive_one_and_empty_typed_source():
    expr = parse(FORM.replace("repos", "(list)").replace(":parallel 2", ":parallel 1"))
    source = replace(expr.source_expr, element_type_ref=PrimitiveTypeRef("String"))
    result = typed(expr=replace(expr, source_expr=source))
    assert result.expr.source_expr.items == ()
    assert result.expr.parallel_count == 1
    assert result.type_ref.name == "List[String]"


def test_parallel_workspace_accepts_existing_path_type():
    source = FORM.replace(":workspace repo", ":workspace root")
    span = parse().span
    root_type = PathTypeRef("Repo", PathDef("Repo", "relpath", ".", True, span))
    values = {"repos": ListTypeRef("List[String]", PrimitiveTypeRef("String")), "root": root_type}
    assert typed(source, values=values).expr.workspace_expr.name == "root"


def test_workspace_clone_retains_source_coordinates_and_captures():
    source = FORM.replace(":workspace repo", ":workspace (string/concat repo root)").replace("(call child :value repo)", "(child repo)")
    expr = parse(source, names=frozenset({"repos", "root"}), procedures=frozenset({"child"}))
    stamped = stamp_capture_origin(expr, binding_env={"root": "root-owner"}, value_env={"root": PrimitiveTypeRef("String")})
    cloned = _clone_function_expr(stamped, span=expr.span, form_path=("clone",), expansion_stack=())
    assert cloned.workspace_expr.form_path == ("clone",)
    assert cloned.workspace_expr.args[1].capture_origin[0] == "root-owner"
    assert free_expr_names(cloned) == {"repos", "root"}


def test_workspace_normalization_keeps_item_bindings_inside_map():
    source = FORM.replace(":workspace repo", ':workspace (if true repo "fallback")')
    expr = parse(source)
    prefix, terminal = _normalize_list_map(expr, path=(), closed_program=True)
    assert len(prefix) == 1
    rebuilt = prefix[0][1]
    assert terminal.name == prefix[0][0]
    assert isinstance(rebuilt.workspace_expr, LetStarExpr)
    assert free_expr_names(rebuilt) == {"repos"}
    normalized = _normalize_expr(rebuilt, typed_functions_by_name={}, expand_admitted_containers=True)
    assert normalized.workspace_expr is not rebuilt.workspace_expr
    assert free_expr_names(normalized) == {"repos"}


def inline_program(*, target="2.37", body="(child repo)", workspace="repo", impure_workspace=False):
    clauses = f":parallel 2 :workspace {workspace}" if target == "2.37" else ""
    cwd_effects = "((uses-command fetch))" if impure_workspace else "()"
    cwd_body = (
        '(let* ((output (command-result fetch :argv ("python" "probe.py") :returns Box))) value)'
        if impure_workspace else "value"
    )
    return f'''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
      (defmodule inline) (export run)
      (defrecord Box (n Int))
      (defproc child ((value String)) -> String :effects () :lowering inline value)
      (defproc cwd ((value String)) -> String :effects {cwd_effects} :lowering inline {cwd_body})
      (defworkflow worker ((value String)) -> String value)
      (defworkflow run () -> List[String]
        (list/map-effect ((repo (list "a" "b"))) :max 2 {clauses} {body})))'''


def compile_inline(tmp_path, **options):
    path = install(tmp_path, inline_program(**options))
    return compile_typed_program(
        path, entry_workflow="inline::run", source_roots=(tmp_path,), command_boundaries=BOUNDARIES,
    )


@pytest.mark.parametrize("target", ["2.36", "2.37"])
def test_real_pipeline_accepts_inline_pure_body(target, tmp_path):
    program = compile_inline(tmp_path, target=target)
    expr = program.entry.typed_body.expr
    assert isinstance(expr, ListMapEffectExpr) == (target == "2.37")
    assert program.entry.typed_body.type_ref.name == "List[String]"


def test_real_pipeline_accepts_inline_pure_workspace(tmp_path):
    program = compile_inline(tmp_path, body="(call worker :value repo)", workspace="(cwd repo)")
    expr = program.entry.typed_body.expr
    assert isinstance(expr, ListMapEffectExpr)
    assert isinstance(expr.workspace_expr, LetStarExpr)
    assert free_expr_names(expr.workspace_expr) == {expr.binder_name}


def test_real_pipeline_refuses_inline_impure_workspace(tmp_path):
    with pytest.raises(LispFrontendCompileError) as error:
        compile_inline(tmp_path, body="(call worker :value repo)", workspace="(cwd repo)", impure_workspace=True)
    assert error.value.diagnostics[0].code == "list_map_effect_workspace_invalid"


@pytest.mark.parametrize("body", [
    "(let* ((value repo)) (child value))",
    "(if true (child repo) (child repo))",
])
def test_real_pipeline_keeps_authored_single_call_body_rule(body, tmp_path):
    with pytest.raises(LispFrontendCompileError) as error:
        compile_inline(tmp_path, body=body)
    assert error.value.diagnostics[0].code == "list_map_effect_body_unsupported"
