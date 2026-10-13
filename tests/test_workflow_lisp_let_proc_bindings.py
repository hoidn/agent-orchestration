"""Structural and creator-scope capture contracts for W3 local procedures."""

import pytest

from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.contracts.closed_program.program import strip_provenance
from orchestrator.workflow_lisp.expressions import BindProcExpr, LetStarExpr
from tests.test_workflow_lisp_command_scopes import _walk

from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.procedures import GeneratedLocalProcedure
from tests.test_workflow_lisp_procedures import _write_module


W3_TARGET = "2.36"
PRE_W3_TARGET = "2.35"
MODULE = "w3/local_hooks"
DECLARATIONS = """\
(defrecord HookContext (left Int) (right Int))
(defproc apply-int
  ((hook ProcRef[Int -> Int]) (value Int)) -> Int
  :effects () :lowering inline (hook value))
(defproc apply-pair
  ((left ProcRef[Int -> Int]) (right ProcRef[Int -> Int]) (value Int)) -> Int
  :effects () :lowering inline (+ (left value) (right value)))
(defproc increment ((value Int)) -> Int
  :effects () :lowering inline (+ value 1))
"""


def _write_case(
    root,
    body,
    *,
    target=W3_TARGET,
    params="((ctx HookContext) (n Int))",
    declarations=DECLARATIONS,
):
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target}")
  (defmodule {MODULE})
  (export run)
  {declarations}
  (defworkflow run {params} -> Int
    {body}))
'''
    return _write_module(root / "w3" / "local_hooks.orc", source.splitlines())


def _compile_evaluated(
    root,
    body,
    *,
    target=W3_TARGET,
    params="((ctx HookContext) (n Int))",
    declarations=DECLARATIONS,
):
    path = _write_case(root, body, target=target, params=params, declarations=declarations)
    return compile_typed_program(
        path,
        entry_workflow=f"{MODULE}::run",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries={},
    )


def _local_bases(typed):
    return [
        procedure
        for procedure in typed.procedures.values()
        if procedure.specialization is None
        and isinstance(procedure.definition.generated_local_procedure, GeneratedLocalProcedure)
    ]


def test_declared_extern_root_precedence_and_lexical_shadow_retyping(tmp_path):
    body = '''(let* ((reviewer 10))
      (let-proc ((hook ((x Int)) -> Int (+ x reviewer)))
        (apply-int (proc-ref hook) n)))'''
    path = _write_case(tmp_path, body, params="((reviewer String) (n Int))")
    typed = compile_typed_program(path, entry_workflow=f"{MODULE}::run", source_roots=(tmp_path,),
                                  workspace_root=tmp_path, command_boundaries={},
                                  provider_externs={"reviewer": "codex"})
    locals_ = _local_bases(typed)
    assert locals_
    assert all(local.definition.generated_local_procedure.capture_names == ("reviewer",) for local in locals_)
    assert all(local.signature.params[0][1].name == "Int" for local in locals_)
    specialized = [procedure for procedure in typed.procedures.values()
                   if procedure.specialization is not None and procedure.definition.generated_local_procedure]
    assert specialized
    assert all(procedure.typed_body.type_ref.name == "Int" for procedure in specialized)
    build_closed_program(typed)


def _assert_located_refusal(excinfo, path, marker, *, expected_code=None):
    diagnostic = excinfo.value.diagnostics[0]
    lines = path.read_text(encoding="utf-8").splitlines()
    expected_line = next(index for index, line in enumerate(lines, start=1) if marker in line)
    assert diagnostic.code not in {"compiler_defect", "target_dsl_unsupported"}
    if expected_code is not None:
        assert diagnostic.code == expected_code
    assert diagnostic.span.start.path == str(path)
    assert diagnostic.span.start.line == expected_line


def test_multiple_fully_typed_hooks_use_existing_generated_procedures(tmp_path):
    body = '''(let-proc
      ((left ((x Int)) -> Int :captures (ctx) (+ x ctx.left))
       (right ((x Int)) -> Int :captures (ctx) (+ x ctx.right)))
      (apply-pair (proc-ref left) (proc-ref right) n))'''
    result = _compile_evaluated(tmp_path, body)

    generated = [
        procedure
        for procedure in result.procedures.values()
        if procedure.specialization is None
        and isinstance(procedure.definition.generated_local_procedure, GeneratedLocalProcedure)
    ]
    assert [procedure.definition.generated_local_procedure.authored_local_name for procedure in generated] == [
        "left",
        "right",
    ]
    assert [procedure.definition.generated_local_procedure.capture_names for procedure in generated] == [
        ("ctx",),
        ("ctx",),
    ]


@pytest.mark.parametrize("target", [PRE_W3_TARGET, W3_TARGET])
def test_original_single_binding_spelling_remains_valid(tmp_path, target):
    result = _compile_evaluated(
        tmp_path,
        "(let-proc (local-increment ((x Int)) -> Int :captures () (+ x 1)) "
        "(apply-int (proc-ref local-increment) n))",
        target=target,
    )
    assert len(
        [
            procedure
            for procedure in result.procedures.values()
            if procedure.specialization is None
            and isinstance(procedure.definition.generated_local_procedure, GeneratedLocalProcedure)
        ]
    ) == 1


@pytest.mark.parametrize(
    ("target", "body", "marker", "expected_code"),
    [
        (W3_TARGET, "(let-proc () (apply-int (proc-ref increment) n))", "let-proc", "let_proc_syntax_invalid"),
        (
            W3_TARGET,
            "(let-proc ((same ((x Int)) -> Int :captures () x) "
            "(same ((y Int)) -> Int :captures () y)) (apply-int (proc-ref same) n))",
            "same ((y Int))",
            "let_proc_syntax_invalid",
        ),
        (
            W3_TARGET,
            "(let-proc ((bad ((x Int)) :captures () -> Int x)) "
            "(apply-int (proc-ref bad) n))",
            "bad ((x Int))",
            "let_proc_syntax_invalid",
        ),
        (
            W3_TARGET,
            "(let-proc ((bad ((x Int) (x Int)) -> Int :captures () x)) "
            "(apply-int (proc-ref bad) n))",
            "bad ((x Int)",
            "let_proc_syntax_invalid",
        ),
        (
            PRE_W3_TARGET,
            "(let-proc ((left ((x Int)) -> Int :captures () x) "
            "(right ((x Int)) -> Int :captures () x)) "
            "(apply-pair (proc-ref left) (proc-ref right) n))",
            "let-proc",
            "let_proc_multiple_bindings_unsupported",
        ),
    ],
    ids=["empty", "duplicate-local", "malformed-clauses", "duplicate-parameter", "old-target-list-spelling"],
)
def test_invalid_binding_lists_are_located(tmp_path, target, body, marker, expected_code):
    path = _write_case(tmp_path, body, target=target)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body, target=target)
    _assert_located_refusal(excinfo, path, marker, expected_code=expected_code)


@pytest.mark.parametrize(
    ("body", "marker", "expected_code"),
    [
        (
            "(let-proc\n"
            "  ((first ((x Int)) -> Int :captures () "
            "(apply-int (proc-ref second) x))\n"
            "   (second ((x Int)) -> Int :captures () (+ x 1)))\n"
            "  (apply-int (proc-ref first) n))",
            "proc-ref second",
            "proc_ref_unknown",
        ),
        (
            "(let-proc\n"
            "  ((self ((x Int)) -> Int :captures () "
            "(apply-int (proc-ref self) x)))\n"
            "  (apply-int (proc-ref self) n))",
            "proc-ref self",
            "let_proc_recursive_unsupported",
        ),
        (
            "(let-proc ((outer ((x Int)) -> Int :captures ()\n"
            "    (let-proc (inner ((y Int)) -> Int :captures () (+ y 1))\n"
            "      (apply-int (proc-ref inner) x))))\n"
            "  (apply-int (proc-ref outer) n))",
            "(let-proc (inner",
            "let_proc_nested_unsupported",
        ),
    ],
    ids=["sibling-reference", "self-reference", "nested-definition"],
)
def test_local_binding_topology_refusals_are_located(tmp_path, body, marker, expected_code):
    path = _write_case(tmp_path, body)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)
    _assert_located_refusal(excinfo, path, marker, expected_code=expected_code)


def test_local_binding_cannot_escape_through_its_consumer(tmp_path):
    declarations = DECLARATIONS + '''\
(defproc leak ((n Int)) -> ProcRef[Int -> Int]
  :effects () :lowering inline
  (let-proc ((hook ((x Int)) -> Int :captures () (+ x 1)))
    (proc-ref hook)))
'''
    path = _write_case(
        tmp_path,
        "(apply-int (proc-ref increment) n)",
        declarations=declarations,
    )
    # The refusal is attached to the local reference inside `leak`.
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, "(apply-int (proc-ref increment) n)", declarations=declarations)
    _assert_located_refusal(
        excinfo,
        path,
        "(proc-ref hook)",
        expected_code="let_proc_scope_escape",
    )



@pytest.mark.parametrize(
    "consumer",
    [
        "(let* ((first (apply-int (proc-ref left) n)) "
        "(again (apply-int (proc-ref left) first))) "
        "(+ again (apply-int (proc-ref right) n)))",
        "(let* ((alias (proc-ref left))) "
        "(+ (forward-int alias n) (forward-int (proc-ref right) n)))",
        "(if true (apply-int (proc-ref left) n) (apply-int (proc-ref right) n))",
        "(+ n 1)",
    ],
    ids=["ordinary-reuse", "forwarded-alias", "conditional", "unused-complete"],
)
def test_complete_local_group_accepts_ordinary_reused_and_forwarded_consumers(tmp_path, consumer):
    declarations = DECLARATIONS + """\
(defproc forward-int ((hook ProcRef[Int -> Int]) (value Int)) -> Int
  :effects () :lowering inline (apply-int hook value))
"""
    body = """(let-proc
      ((left ((x Int)) -> Int :captures (ctx) (+ x ctx.left))
       (right ((x Int)) -> Int :captures (ctx) (+ x ctx.right)))
      CONSUMER)""".replace("CONSUMER", consumer)
    typed = _compile_evaluated(tmp_path, body, declarations=declarations)
    bases = _local_bases(typed)
    assert {p.definition.generated_local_procedure.authored_local_name for p in bases} == {"left", "right"}
    for procedure in bases:
        name = procedure.definition.name
        assert name in typed.local_definition_keys
        did = typed.local_definition_dids[name]
        assert did[:2] == (MODULE, "procedure")
        assert did[2]["owner"] == [MODULE, "workflow", "run"]
        assert did[2]["name"] == procedure.definition.generated_local_procedure.authored_local_name


@pytest.mark.parametrize("escaped_name", ["left", "right"])
def test_each_binding_in_complete_local_group_cannot_escape(tmp_path, escaped_name):
    declarations = DECLARATIONS + f"""\
(defproc leak ((n Int)) -> ProcRef[Int -> Int]
  :effects () :lowering inline
  (let-proc
    ((left ((x Int)) -> Int :captures () x)
     (right ((x Int)) -> Int :captures () (+ x 1)))
    (proc-ref {escaped_name})))
"""
    body = "(apply-int (proc-ref increment) n)"
    path = _write_case(tmp_path, body, declarations=declarations)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body, declarations=declarations)
    _assert_located_refusal(
        excinfo, path, f"(proc-ref {escaped_name})", expected_code="let_proc_scope_escape"
    )

def _capture_body(capture_clause, *, list_spelling=False):
    clause = f" {capture_clause}" if capture_clause else ""
    binding = f"""(hook ((x Int)) -> Int{clause}
          (if true
            (runner (+ x ctx.left))
            (runner (+ x ctx.right))))"""
    if list_spelling:
        binding = f"({binding})"
    return f"""(let*
      ((runner (proc-ref increment)))
      (let-proc {binding}
        (let* ((alias (proc-ref hook))
               (ctx (record HookContext :left 100 :right 200)))
          (alias n))))"""


@pytest.mark.parametrize(
    "capture_clause",
    [None, ":captures (ctx runner)", ":captures (runner ctx)", ":captures (unused runner ctx)"],
    ids=["inferred", "explicit", "reordered", "unused-superset"],
)
def test_inferred_capture_equivalence_and_field_proc_ref_topology(tmp_path, capture_clause):
    typed = _compile_evaluated(
        tmp_path,
        _capture_body(capture_clause),
        params="((ctx HookContext) (unused Int) (n Int))",
    )
    local, = _local_bases(typed)
    metadata = local.definition.generated_local_procedure

    assert metadata.capture_names == ("ctx", "runner")
    assert tuple(name for name, _ in typed.local_definition_keys[local.definition.name][3]) == (
        "ctx",
        "runner",
    )


def test_explicit_capture_spellings_have_same_canonical_closed_program(tmp_path):
    programs = []
    for list_spelling in (False, True):
        for index, clause in enumerate(
            (None, ":captures (ctx runner)", ":captures (runner ctx)", ":captures (unused runner ctx)")
        ):
            root = tmp_path / str(list_spelling) / str(index)
            typed = _compile_evaluated(
                root,
                _capture_body(clause, list_spelling=list_spelling),
                params="((ctx HookContext) (unused Int) (n Int))",
            )
            programs.append(build_closed_program(typed))

    baseline = programs[0]
    assert all(program.digest == baseline.digest for program in programs[1:])
    canonical_definitions = strip_provenance(baseline.tree)["definitions"]
    assert all(
        strip_provenance(program.tree)["definitions"] == canonical_definitions
        for program in programs[1:]
    )


@pytest.mark.parametrize(
    ("capture_clause", "expected_code"),
    [
        (":captures ()", "let_proc_capture_missing"),
        (":captures (missing)", "let_proc_capture_unknown"),
        (":captures (ctx ctx)", "let_proc_capture_duplicate"),
    ],
    ids=["missing-used-capture", "unknown-capture", "duplicate-capture"],
)
def test_invalid_explicit_capture_bounds_are_located(tmp_path, capture_clause, expected_code):
    body = f'''(let-proc (hook ((x Int)) -> Int {capture_clause} (+ x ctx.left))
      (apply-int (proc-ref hook) n))'''
    path = _write_case(tmp_path, body)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)
    _assert_located_refusal(excinfo, path, "let-proc", expected_code=expected_code)


def test_parameter_and_local_binders_shadow_creator_names(tmp_path):
    body = '''(let-proc
      ((parameter-shadow ((ctx Int)) -> Int (+ ctx 1))
       (let-shadow ((x Int)) -> Int (let* ((ctx (+ x 1))) ctx)))
      (apply-pair
        (proc-ref parameter-shadow)
        (proc-ref let-shadow)
        n))'''
    typed = _compile_evaluated(tmp_path, body)

    assert {
        row.definition.generated_local_procedure.authored_local_name:
        row.definition.generated_local_procedure.capture_names
        for row in _local_bases(typed)
    } == {"parameter-shadow": (), "let-shadow": ()}


def _hook_ref_specializations(typed):
    return [
        procedure.specialization.proc_ref_bindings["hook"]
        for procedure in typed.procedures.values()
        if procedure.specialization is not None
        and "hook" in procedure.specialization.proc_ref_bindings
    ]


def test_creator_capture_identity_survives_later_call_site_shadowing(tmp_path):
    typed = _compile_evaluated(
        tmp_path,
        _capture_body(None),
        params="((ctx HookContext) (unused Int) (n Int))",
    )
    ctx_captures = [
        binding
        for node in _walk(typed.entry.typed_body.expr)
        if isinstance(node, BindProcExpr)
        for binding in node.bindings
        if binding.name == "ctx"
    ]
    outer_identity = typed.entry.typed_body.binding_environment["ctx"]
    shadow_identities = [
        identity
        for node in _walk(typed.entry.typed_body.expr)
        if isinstance(node, LetStarExpr)
        for (name, _), identity in zip(node.bindings, node.binding_identities)
        if name == "ctx" and identity is not None
    ]

    assert ctx_captures
    assert {capture.source_binding_identity for capture in ctx_captures} == {outer_identity}
    assert outer_identity not in shadow_identities


def test_same_named_captures_from_two_creator_scopes_keep_distinct_bindings(tmp_path):
    body = '''(let*
      ((first
        (let-proc (hook ((x Int)) -> Int (+ x ctx.left))
          (apply-int (proc-ref hook) n)))
       (ctx (record HookContext :left 10 :right 20))
       (second
        (let-proc (hook ((x Int)) -> Int (+ x ctx.left))
          (apply-int (proc-ref hook) n)))
       (total (+ first second)))
      total)'''
    typed = _compile_evaluated(tmp_path, body)
    references = _hook_ref_specializations(typed)
    identities = [
        next(argument.source_binding_identity for argument in reference.bound_args if argument.name == "ctx")
        for reference in references
    ]
    outer_identity = typed.entry.typed_body.binding_environment["ctx"]
    shadow_identity = next(
        identity
        for node in _walk(typed.entry.typed_body.expr)
        if isinstance(node, LetStarExpr)
        for (name, _), identity in zip(node.bindings, node.binding_identities)
        if name == "ctx" and identity is not None
    )

    assert len(identities) == 2
    assert len(set(identities)) == 2
    assert set(identities) == {outer_identity, shadow_identity}


def test_pre_w3_capture_list_keeps_authored_order(tmp_path):
    typed = _compile_evaluated(
        tmp_path,
        _capture_body(":captures (runner ctx)"),
        target=PRE_W3_TARGET,
        params="((ctx HookContext) (unused Int) (n Int))",
    )
    local, = _local_bases(typed)

    assert local.definition.generated_local_procedure.capture_names == ("runner", "ctx")


@pytest.mark.parametrize("capture_clause", ["", ":captures ()"])
def test_local_callable_binder_shadows_unused_creator_capture(tmp_path, capture_clause):
    body = f"""(let-proc (hook ((x Int)) -> Int {capture_clause}
      (let* ((runner (proc-ref increment))) (runner x)))
      (apply-int (proc-ref hook) n))"""
    typed = _compile_evaluated(
        tmp_path, body, params="((ctx HookContext) (runner Int) (n Int))"
    )
    local, = _local_bases(typed)
    assert local.definition.generated_local_procedure.capture_names == ()


@pytest.mark.parametrize("capture_clause", ["", ":captures ()"])
def test_callable_parameter_shadows_unused_creator_capture(tmp_path, capture_clause):
    body = f"""(let-proc
      (hook ((runner ProcRef[Int -> Int]) (x Int)) -> Int {capture_clause} (runner x))
      (+ n 1))"""
    typed = _compile_evaluated(
        tmp_path, body, params="((ctx HookContext) (runner Int) (n Int))"
    )
    local, = _local_bases(typed)
    assert local.definition.generated_local_procedure.capture_names == ()


@pytest.mark.parametrize(
    ("capture_clause", "expected_code"),
    [
        (":captures (ctx missing)", "let_proc_capture_unknown"),
        (":captures (ctx unused unused)", "let_proc_capture_duplicate"),
    ],
)
def test_invalid_unused_entries_in_capture_superset_are_located(tmp_path, capture_clause, expected_code):
    body = f"""(let-proc (hook ((x Int)) -> Int {capture_clause} (+ x ctx.left))
      (apply-int (proc-ref hook) n))"""
    params = "((ctx HookContext) (unused Int) (n Int))"
    path = _write_case(tmp_path, body, params=params)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body, params=params)
    _assert_located_refusal(excinfo, path, "let-proc", expected_code=expected_code)


@pytest.mark.parametrize("capture_clause", [":captures (ctx.left)", ":captures (7)"])
def test_capture_bounds_require_plain_identifiers(tmp_path, capture_clause):
    body = f"""(let-proc (hook ((x Int)) -> Int {capture_clause} (+ x ctx.left))
      (apply-int (proc-ref hook) n))"""
    path = _write_case(tmp_path, body)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)
    _assert_located_refusal(
        excinfo, path, "let-proc", expected_code="let_proc_capture_not_identifier"
    )


def test_capture_analysis_excludes_field_labels_and_type_names(tmp_path):
    body = """(let-proc (hook ((x Int)) -> HookContext
      (record HookContext :left x :right ctx.left)) (+ n 1))"""
    typed = _compile_evaluated(
        tmp_path, body,
        params="((ctx HookContext) (left Int) (right Int) (n Int))",
    )
    local, = _local_bases(typed)
    assert local.definition.generated_local_procedure.capture_names == ("ctx",)


def test_inferred_captures_keep_complete_hooks_reusable_and_forwardable(tmp_path):
    declarations = DECLARATIONS + """\
(defproc forward-int ((hook ProcRef[Int -> Int]) (value Int)) -> Int
  :effects () :lowering inline (apply-int hook value))
"""
    body = """(let-proc
      ((left ((x Int)) -> Int (+ x ctx.left))
       (right ((x Int)) -> Int (+ x ctx.right)))
      (let* ((alias (proc-ref left)) (first (forward-int alias n)))
        (+ (apply-int (proc-ref left) first) (forward-int (proc-ref right) n))))"""
    typed = _compile_evaluated(tmp_path, body, declarations=declarations)
    assert {
        p.definition.generated_local_procedure.authored_local_name:
        p.definition.generated_local_procedure.capture_names
        for p in _local_bases(typed)
    } == {"left": ("ctx",), "right": ("ctx",)}


def _extern_expression(source, *, bound=(), extern=(), **options):
    from orchestrator.workflow_lisp.expressions import elaborate_expression
    from orchestrator.workflow_lisp.reader import read_sexpr_text
    from orchestrator.workflow_lisp.syntax import SyntaxNode

    [datum] = read_sexpr_text(source, source_path="extern_scope.orc").items
    node = SyntaxNode(datum=datum, span=datum.span, module_path="extern_scope.orc", form_path=("extern-scope",))
    return elaborate_expression(node, bound_names=frozenset(bound), extern_names=frozenset(extern),
                                target_dsl_version=W3_TARGET, **options)


@pytest.mark.parametrize("source,kind", [
    ("providers.reviewer", "NameExpr"),
    ("prompts.proposal.long.review", "NameExpr"),
    ("root.field", "FieldAccessExpr"),
    ("Status.READY", "EnumMemberExpr"),
])
def test_extern_availability_preserves_symbol_precedence(source, kind):
    expr = _extern_expression(source, bound=("root", "providers"),
                              extern=("providers.reviewer", "prompts.proposal.long.review"))
    assert type(expr).__name__ == kind
    if kind == "NameExpr":
        assert expr.name == source


@pytest.mark.parametrize("source,code", [
    ("(list/map ((reviewer (list 1))) reviewer)", "list_map_binder_invalid"),
    ("(list/map-effect ((reviewer (list 1))) :max 1 reviewer)", "list_map_binder_invalid"),
    ("(let-proc ((reviewer ((x Int)) -> Int x)) 0)", "let_proc_syntax_invalid"),
    ("(let-proc ((hook ((x Int)) -> Int :captures (reviewer) x)) 0)", "let_proc_capture_unknown"),
])
def test_extern_availability_preserves_collisions_and_lexical_capture_bounds(source, code):
    with pytest.raises(LispFrontendCompileError) as exc:
        _extern_expression(source, extern=("reviewer",))
    assert exc.value.diagnostics[0].code == code
    assert exc.value.diagnostics[0].span.start.path == "extern_scope.orc"


@pytest.mark.parametrize("source", ["(reviewer 1)", "(call reviewer :value 1)"])
def test_extern_available_callees_bypass_import_resolvers(source):
    def forbidden(*args):
        pytest.fail("available names must bypass imported-name resolution")

    expr = _extern_expression(source, extern=("reviewer",),
                              procedure_name_resolver=forbidden, workflow_name_resolver=forbidden)
    assert expr.callee_name == "reviewer"


def test_extern_prompt_is_distinct_from_unapplied_prompt_declaration():
    from orchestrator.workflow_lisp.prompts import PromptCatalog

    catalog = PromptCatalog(definitions_by_name={"review_prompt": object()})
    source = "(provider-result reviewer :prompt review_prompt :inputs () :returns Int)"
    expr = _extern_expression(source, extern=("reviewer", "review_prompt"), prompt_catalog=catalog)
    assert expr.prompt.name == "review_prompt"
    with pytest.raises(LispFrontendCompileError) as exc:
        _extern_expression(source, extern=("reviewer",), prompt_catalog=catalog)
    assert exc.value.diagnostics[0].code == "prompt_partial_application_unsupported"


@pytest.mark.parametrize("pending", [False, True])
def test_lexical_provider_prompt_aliases_and_residual_shadow_remain_capturable(tmp_path, pending):
    signature = "(reviewer)" if pending else "((reviewer Int)) -> Int"
    body = f'''(let-proc ((hook {signature}
      (let* ((provider-alias provider-param) (prompt-alias prompt-param)) reviewer)))
      (apply-int (proc-ref hook) n))'''
    declarations = DECLARATIONS + f'''(defproc wrapper
      ((provider-param Provider) (prompt-param Prompt) (n Int)) -> Int
      :effects () :lowering inline {body})'''
    path = _write_case(tmp_path, "0", params="()", declarations=declarations)
    typed = compile_typed_program(path, entry_workflow=f"{MODULE}::run", source_roots=(tmp_path,),
                                  workspace_root=tmp_path, command_boundaries={},
                                  provider_externs={"reviewer": "codex"})
    locals_ = _local_bases(typed)
    assert locals_
    assert all(local.definition.generated_local_procedure.capture_names == ("prompt-param", "provider-param")
               for local in locals_)
    assert all(tuple(typ.name for _, typ in local.signature.params) == ("Prompt", "Provider", "Int")
               for local in locals_)
    assert all(local.typed_body.type_ref.name == "Int" for local in locals_)


@pytest.mark.parametrize("pending", [False, True])
def test_extern_explicit_inferred_capture_equivalence_and_root_precedence(tmp_path, pending):
    programs = []
    for explicit in (False, True):
        signature = "(x)" if pending else "((x Int)) -> Int"
        capture = ":captures (offset)" if explicit else ""
        body = f'''(let-proc ((hook {signature} {capture}
          (provider-result reviewer :prompt review_prompt :inputs (x offset) :returns Int)))
          (apply-int (proc-ref hook) offset))'''
        path = _write_case(tmp_path, body, params="((offset Int) (reviewer String) (review_prompt String))")
        (tmp_path / "review.md").write_text("Review inputs.\n")
        typed = compile_typed_program(path, entry_workflow=f"{MODULE}::run", source_roots=(tmp_path,),
                                      workspace_root=tmp_path, command_boundaries={},
                                      provider_externs={"reviewer": "codex"},
                                      prompt_externs={"review_prompt": "review.md"})
        assert all(local.definition.generated_local_procedure.capture_names == ("offset",)
                   for local in _local_bases(typed))
        programs.append(build_closed_program(typed))
    assert programs[0].digest == programs[1].digest
    assert strip_provenance(programs[0].tree) == strip_provenance(programs[1].tree)
