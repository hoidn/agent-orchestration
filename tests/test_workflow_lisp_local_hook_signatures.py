"""W3 local-hook expected signatures and authored consumer sites."""

import pytest

from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.procedures import GeneratedLocalProcedure
from tests.test_workflow_lisp_procedures import _write_module


W3_TARGET = "2.36"
MODULE = "w3/local_hook_signatures"

DECLARATIONS = """\
(defproc need
  :forall (T)
  ((hook ProcRef[(T) -> T])) -> Int
  :effects () :lowering inline 0)
(defproc seed
  :forall (T)
  ((value T) (hook ProcRef[(T) -> T])) -> Int
  :effects () :lowering inline 0)
(defproc apply-hook
  ((hook ProcRef[(Int) -> Int])) -> Int
  :effects () :lowering inline (hook 1))
(defproc use-two-compatible
  ((left ProcRef[(Int) -> Int]) (right ProcRef[(Int) -> Int])) -> Int
  :effects () :lowering inline (+ (left 1) (right 2)))
(defproc use-two-conflicting
  ((left ProcRef[(Int) -> Int]) (right ProcRef[(String) -> String])) -> Int
  :effects () :lowering inline (+ (left 1) (if true 0 1)))
(defproc use-two-conflicting-return
  ((left ProcRef[(Int) -> Int]) (right ProcRef[(Int) -> String])) -> Int
  :effects () :lowering inline (left 1))
(defproc improve
  :forall (S F)
  ((initial S) (review ProcRef[(S) -> F]) (revise ProcRef[(S F) -> S])) -> S
  :effects () :lowering inline (revise initial (review initial)))
(defproc improve-reversed
  :forall (S F)
  ((initial S) (revise ProcRef[(S F) -> S]) (review ProcRef[(S) -> F])) -> S
  :effects () :lowering inline (revise initial (review initial)))
(defrecord Candidate (value Int))
(defrecord ReviewFeedback (notes String))
(defrecord ReviewBlocker (issue String))
(defunion Decision :forall (F B)
  (APPROVE (evidence F))
  (REVISE (feedback F))
  (BLOCKED (reason B)))
(defunion Improvement :forall (S F B)
  (APPROVED (value S) (evidence F))
  (BLOCKED (value S) (reason B))
  (EXHAUSTED (value S)))
(defproc improve-decision
  :forall (S F B)
  ((initial S)
   (review ProcRef[(S) -> Decision[F B]])
   (revise ProcRef[(S F) -> S])
   (limit Int))
  :where ((S is-record))
  -> Improvement[S F B]
  :effects ()
  :lowering inline
  (loop/recur :max limit
    :state (loop-state (current S initial))
    :on-exhausted (variant Improvement[S F B] EXHAUSTED :value state.current)
    (fn (state)
      (let* ((decision (review state.current)))
        (match decision
          ((APPROVE approved)
           (done (variant Improvement[S F B] APPROVED
                   :value state.current :evidence approved.evidence)))
          ((BLOCKED blocked)
           (done (variant Improvement[S F B] BLOCKED
                   :value state.current :reason blocked.reason)))
          ((REVISE revised)
           (let* ((next (revise state.current revised.feedback)))
             (continue (loop-state :like state :current next)))))))))
(defproc repeat-hook
  ((count Int) (hook ProcRef[(Int) -> Int])) -> Int
  :effects () :lowering inline
  (loop/recur
    :max count
    :state (loop-state (i Int 0) (total Int 0))
    :on-exhausted state.total
    (fn (state)
      (if (< state.i count)
        (continue
          (loop-state :like state
            :i (+ state.i 1)
            :total (+ state.total (hook state.i))))
        (done state.total)))))
(defmacro duplicate-call (call)
  (let* ((first call)
         (second call))
    second))
"""


def _write_case(
    root,
    body,
    *,
    params="()",
    result="Int",
    declarations=DECLARATIONS,
    imports="",
):
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{W3_TARGET}")
  (defmodule {MODULE})
  {imports}
  (export run)
  {declarations}
  (defworkflow run {params} -> {result}
    {body}))
'''
    return _write_module(root / "w3" / "local_hook_signatures.orc", source.splitlines())


def _compile_evaluated(root, body, **options):
    path = _write_case(root, body, **options)
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


@pytest.mark.parametrize("root", ["workflow", "procedure"])
@pytest.mark.parametrize("pending", [False, True], ids=["full", "pending"])
@pytest.mark.parametrize("explicit", [False, True], ids=["inferred-captures", "explicit-captures"])
@pytest.mark.parametrize("provider,prompt", [
    ("providers.reviewer", "prompts.proposal.long.review"), ("reviewer", "review_prompt"),
])
def test_local_hooks_exclude_declared_externs_but_type_their_bodies(
    tmp_path, root, pending, explicit, provider, prompt,
):
    params = "(x)" if pending else "((x Int)) -> Int"
    captures = ":captures (offset)" if explicit else ""
    body = f'''(let-proc ((hook {params} {captures}
      (provider-result {provider} :prompt {prompt} :inputs (offset x) :returns Int)))
      (apply-hook (proc-ref hook)))'''
    declarations = DECLARATIONS
    if root == "procedure":
        declarations += f'''(defproc wrapper ((offset Int)) -> Int
          :effects ((uses-provider {provider})) :lowering inline {body})'''
        body = "(wrapper offset)"
    path = _write_case(tmp_path, body, params="((offset Int))", declarations=declarations)
    (tmp_path / "review.md").write_text("Review the integer inputs.\n")
    typed = compile_typed_program(path, entry_workflow=f"{MODULE}::run", source_roots=(tmp_path,),
                                  workspace_root=tmp_path, command_boundaries={},
                                  provider_externs={provider: "codex"}, prompt_externs={prompt: "review.md"})
    locals_ = _local_bases(typed)
    assert locals_
    assert all(local.definition.generated_local_procedure.capture_names == ("offset",) for local in locals_)
    assert all(tuple(name for name, _ in local.signature.params) == ("offset", "x") for local in locals_)
    captured = [argument
                for procedure in typed.procedures.values() if procedure.specialization is not None
                for reference in procedure.specialization.proc_ref_bindings.values()
                for argument in reference.bound_args]
    assert captured
    assert {argument.name for argument in captured} == {"offset"}
    assert all(argument.source_binding_identity is not None for argument in captured)
    from orchestrator.workflow_lisp.closed.build import build_closed_program
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes
    closed = build_closed_program(typed)
    bodies = [closed.tree["body"], *[definition["body"] for definition in closed.tree["definitions"].values()]]
    assert any(node.get("k") == "perform" and node.get("class") == "provider"
               for body in bodies for node in _ast_nodes(body))


def _assert_inferred_local(typed, name, *, params, result):
    procedure = next(
        procedure
        for procedure in _local_bases(typed)
        if procedure.definition.generated_local_procedure.authored_local_name == name
    )
    local = procedure.definition.generated_local_procedure
    assert local.residual_params == params
    assert local.return_type_name == result


def _assert_located_signature_refusal(excinfo, path, marker, *, expected_code):
    # Source-owned diagnostic codes and locations are checked after qualification.
    diagnostic = excinfo.value.diagnostics[0]
    expected_line = next(
        index
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if marker in line
    )
    assert diagnostic.code not in {"compiler_defect", "target_dsl_unsupported"}
    assert diagnostic.code == expected_code
    assert diagnostic.span.start.path == str(path)
    assert diagnostic.span.start.line == expected_line


REVIEW_INCOMPLETE = '(review (candidate) "feedback")'
REVISE_INCOMPLETE = "(revise (candidate feedback) candidate)"
REVIEW_ANNOTATED = '(review ((candidate Int)) -> String "feedback")'
REVISE_ANNOTATED = "(revise ((candidate Int) (feedback String)) -> Int candidate)"


def _review_revise_forms(declaration_order, review_form, revise_form):
    forms = {"review": review_form, "revise": revise_form}
    names = ("review", "revise") if declaration_order == "review-first" else ("revise", "review")
    return " ".join(forms[name] for name in names)


def _review_revise_call(argument_order):
    if argument_order == "review-first":
        return "improve initial (proc-ref review) (proc-ref revise)"
    return "improve-reversed initial (proc-ref revise) (proc-ref review)"


@pytest.mark.parametrize("signature_form", ["omitted", "partial", "authored-return"])
@pytest.mark.parametrize("declaration_order", ["review-first", "revise-first"])
@pytest.mark.parametrize("argument_order", ["review-first", "revise-first"])
def test_review_result_resolves_revise_signature_independent_of_order(
    tmp_path, declaration_order, argument_order, signature_form
):
    review, revise = REVIEW_INCOMPLETE, REVISE_INCOMPLETE
    if signature_form == "partial":
        review = '(review ((candidate Int)) "feedback")'
        revise = "(revise (candidate (feedback String)) candidate)"
    elif signature_form == "authored-return":
        review = '(review (candidate) -> String "feedback")'
        revise = "(revise ((candidate Int) feedback) -> Int candidate)"
    forms = _review_revise_forms(declaration_order, review, revise)
    typed = _compile_evaluated(
        tmp_path,
        f"(let-proc ({forms}) ({_review_revise_call(argument_order)}))",
        params="((initial Int))",
    )

    assert typed.entry is not None
    assert typed.entry.signature.return_type_ref.name == "Int"
    _assert_inferred_local(typed, "review", params=(("candidate", "Int"),), result="String")
    _assert_inferred_local(
        typed,
        "revise",
        params=(("candidate", "Int"), ("feedback", "String")),
        result="Int",
    )


@pytest.mark.parametrize("declaration_order", ["review-first", "revise-first"])
@pytest.mark.parametrize("argument_order", ["review-first", "revise-first"])
def test_fully_annotated_review_revise_hooks_work_independent_of_order(
    tmp_path, declaration_order, argument_order
):
    forms = _review_revise_forms(
        declaration_order, REVIEW_ANNOTATED, REVISE_ANNOTATED
    )
    typed = _compile_evaluated(
        tmp_path,
        f"(let-proc ({forms}) ({_review_revise_call(argument_order)}))",
        params="((initial Int))",
    )

    assert typed.entry is not None
    assert typed.entry.signature.return_type_ref.name == "Int"
    _assert_inferred_local(typed, "review", params=(("candidate", "Int"),), result="String")
    _assert_inferred_local(
        typed,
        "revise",
        params=(("candidate", "Int"), ("feedback", "String")),
        result="Int",
    )


@pytest.mark.parametrize("argument_order", ["review-first", "revise-first"])
@pytest.mark.parametrize("declaration_order", ["review-first", "revise-first"])
def test_qualified_decision_feedback_resolves_revise_parameter(tmp_path, declaration_order, argument_order):
    review = (
        "(review (candidate) "
        "(variant Decision[ReviewFeedback ReviewBlocker] REVISE "
        ':feedback (record ReviewFeedback :notes "change")))'
    )
    revise = "(revise (candidate feedback) candidate)"
    forms = _review_revise_forms(declaration_order, review, revise)
    helper = DECLARATIONS[DECLARATIONS.index("(defproc improve-decision"):DECLARATIONS.index("(defproc repeat-hook")]
    reversed_helper = helper.replace("(defproc improve-decision", "(defproc improve-decision-reversed").replace(
        "   (review ProcRef[(S) -> Decision[F B]])\n   (revise ProcRef[(S F) -> S])",
        "   (revise ProcRef[(S F) -> S])\n   (review ProcRef[(S) -> Decision[F B]])")
    call = "improve-decision initial (proc-ref review) (proc-ref revise) 2" if argument_order == "review-first" else "improve-decision-reversed initial (proc-ref revise) (proc-ref review) 2"
    body = f"(let-proc ({forms}) (let* ((result ({call}))) 0))"
    typed = _compile_evaluated(
        tmp_path,
        body,
        params="((initial Candidate))",
        declarations=DECLARATIONS + reversed_helper,
    )

    revise_local = next(
        procedure.definition.generated_local_procedure
        for procedure in _local_bases(typed)
        if procedure.definition.generated_local_procedure.authored_local_name == "revise"
    )
    assert revise_local.residual_params == (
        ("candidate", "Candidate"),
        ("feedback", "ReviewFeedback"),
    )
    assert revise_local.return_type_name == "Candidate"


@pytest.mark.parametrize(
    "calls",
    [
        "(let* ((first (need (proc-ref h))) (second (seed 1 (proc-ref h)))) second)",
        "(let* ((first (seed 1 (proc-ref h))) (second (need (proc-ref h)))) second)",
        "(let* ((first (seed 1 (proc-ref h))) (second (seed 2 (proc-ref h)))) second)",
        "(let* ((first (seed 2 (proc-ref h))) (second (seed 1 (proc-ref h)))) second)",
    ],
    ids=("need-then-seed", "seed-then-need", "two-seeds", "reversed-two-seeds"),
)
def test_incomplete_local_requires_one_authored_site(tmp_path, calls):
    body = f"(let-proc ((h (x) x)) {calls})"
    path = _write_case(tmp_path, body)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)

    _assert_located_signature_refusal(excinfo, path, "(let-proc ((h", expected_code="let_proc_consumer_site_invalid")


def test_incomplete_local_requires_one_direct_site_across_both_branch_arms(tmp_path):
    body = "(let-proc ((h (x) x)) (if true (need (proc-ref h)) (seed 1 (proc-ref h))))"
    path = _write_case(tmp_path, body)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)

    _assert_located_signature_refusal(excinfo, path, "(let-proc ((h", expected_code="let_proc_consumer_site_invalid")


def test_incomplete_unused_local_has_no_consumer_site(tmp_path):
    body = "(let-proc ((h (x) x)) 0)"
    path = _write_case(tmp_path, body)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)

    _assert_located_signature_refusal(excinfo, path, "(let-proc ((h", expected_code="let_proc_consumer_site_invalid")


@pytest.mark.parametrize(
    "forwarding",
    [
        "(let* ((alias (proc-ref h))) (seed 1 alias))",
        "(let* ((bound (bind-proc (proc-ref apply-hook) :hook (proc-ref h)))) (bound))",
        "(seed 1 (if true (proc-ref h) (proc-ref fixed)))",
    ],
    ids=("alias", "bind-proc", "conditional"),
)
def test_incomplete_local_refuses_indirect_forwarding_as_inference_site(tmp_path, forwarding):
    declarations = DECLARATIONS + """\
(defproc relay
  ((hook ProcRef[(Int) -> Int])) -> ProcRef[(Int) -> Int]
  :effects () :lowering inline hook)
(defproc fixed ((x Int)) -> Int :effects () :lowering inline x)
"""
    body = f"(let-proc ((h (x) x)) {forwarding})"
    path = _write_case(tmp_path, body, declarations=declarations)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body, declarations=declarations)

    _assert_located_signature_refusal(excinfo, path, "(let-proc ((h", expected_code="let_proc_indirect_reference_unsupported")


def test_need_without_grounding_stops_at_located_no_progress(tmp_path):
    body = "(let-proc ((h (x) x)) (need (proc-ref h)))"
    path = _write_case(tmp_path, body)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)

    _assert_located_signature_refusal(excinfo, path, "(let-proc ((h", expected_code="let_proc_expected_signature_missing")


def test_seed_ordinary_argument_grounds_the_single_site_signature(tmp_path):
    body = "(let-proc ((h (x) x)) (seed 1 (proc-ref h)))"
    typed = _compile_evaluated(tmp_path, body)

    _assert_inferred_local(typed, "h", params=(("x", "Int"),), result="Int")


@pytest.mark.parametrize(
    ("body", "params"),
    [
        (
            "(let-proc ((h (x) x)) "
            "(let* ((result (seed 1 (proc-ref h)))) result))",
            "()",
        ),
        (
            "(let-proc ((h (x) x)) "
            "(if enabled (seed 1 (proc-ref h)) 0))",
            "((enabled Bool))",
        ),
    ],
    ids=("direct-site-in-let-star", "direct-site-in-one-branch"),
)
def test_one_incomplete_hook_site_is_valid_inside_ordinary_consumer(tmp_path, body, params):
    typed = _compile_evaluated(tmp_path, body, params=params)

    _assert_inferred_local(typed, "h", params=(("x", "Int"),), result="Int")


def test_disjoint_same_named_incomplete_locals_have_independent_sites(tmp_path):
    body = """(if true
      (let-proc ((h (x) x)) (seed 1 (proc-ref h)))
      (let-proc ((h (x) x)) (seed 2 (proc-ref h))))"""
    typed = _compile_evaluated(tmp_path, body)

    assert typed.entry is not None
    assert typed.entry.signature.return_type_ref.name == "Int"
    assert len([p for p in _local_bases(typed) if p.definition.generated_local_procedure.authored_local_name == "h"]) == 2


@pytest.mark.parametrize("reverse", [False, True], ids=("need-then-seed", "seed-then-need"))
def test_fully_annotated_local_remains_reusable_and_forwardable_with_inferred_capture(tmp_path, reverse):
    if reverse:
        uses = "(let* ((first (seed 1 alias)) (second (need (proc-ref h)))) (+ first second))"
    else:
        uses = "(let* ((first (need alias)) (second (seed 1 (proc-ref h)))) (+ first second))"
    body = f"""(let-proc ((h ((x Int)) -> Int (+ x offset)))
      (let* ((alias (proc-ref h))) {uses}))"""
    typed = _compile_evaluated(tmp_path, body, params="((offset Int))")

    assert typed.entry is not None
    assert typed.entry.signature.return_type_ref.name == "Int"
    assert len(_local_bases(typed)) == 1


def test_incomplete_and_complete_locals_share_a_group_with_separate_rules(tmp_path):
    body = """(let-proc
      ((incomplete (x) (+ x 1))
       (complete ((x Int)) -> Int (+ x offset)))
      (let* ((complete-alias (proc-ref complete))
             (inferred-use (seed 1 (proc-ref incomplete)))
             (forwarded-use (need complete-alias))
             (reused-use (seed 2 (proc-ref complete))))
        (+ inferred-use forwarded-use reused-use)))"""
    typed = _compile_evaluated(tmp_path, body, params="((offset Int))")

    _assert_inferred_local(typed, "incomplete", params=(("x", "Int"),), result="Int")
    complete = next(
        procedure.definition.generated_local_procedure
        for procedure in _local_bases(typed)
        if procedure.definition.generated_local_procedure.authored_local_name == "complete"
    )
    assert complete.residual_params == (("x", "Int"),)
    assert complete.return_type_name == "Int"


def test_incomplete_hook_captures_creator_value_before_consumer_shadow(tmp_path):
    body = """(let-proc ((h (x) (+ x offset)))
      (let* ((offset 100)
             (result (apply-hook (proc-ref h))))
        result))"""
    typed = _compile_evaluated(tmp_path, body, params="((offset Int))")

    local = next(
        procedure.definition.generated_local_procedure
        for procedure in _local_bases(typed)
        if procedure.definition.generated_local_procedure.authored_local_name == "h"
    )
    assert local.capture_names == ("offset",)
    assert local.residual_params == (("x", "Int"),)
    assert local.return_type_name == "Int"


def test_incomplete_local_with_one_direct_site_still_rejects_alias_use(tmp_path):
    body = """(let-proc
      ((h (x) x))
      (let* ((direct (seed 1 (proc-ref h)))
             (alias (proc-ref h)))
        (need alias)))"""
    path = _write_case(tmp_path, body)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)

    _assert_located_signature_refusal(excinfo, path, "(alias (proc-ref h))", expected_code="let_proc_indirect_reference_unsupported")


def test_same_call_site_repeated_hook_arguments_unify_compatible_expectations(tmp_path):
    body = "(let-proc ((h (x) (+ x 1))) (use-two-compatible (proc-ref h) (proc-ref h)))"
    typed = _compile_evaluated(tmp_path, body)

    _assert_inferred_local(typed, "h", params=(("x", "Int"),), result="Int")


def test_same_call_site_repeated_hook_arguments_reject_conflicting_expectations(tmp_path):
    body = "(let-proc ((h (x) x)) (use-two-conflicting (proc-ref h) (proc-ref h)))"
    path = _write_case(tmp_path, body)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)

    _assert_located_signature_refusal(excinfo, path, "(let-proc ((h", expected_code="type_mismatch")


def test_same_call_site_conflicting_return_expectations_are_refused(tmp_path):
    body = """(let-proc
      ((h ((x Int)) x))
      (use-two-conflicting-return (proc-ref h) (proc-ref h)))"""
    path = _write_case(tmp_path, body)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)

    _assert_located_signature_refusal(
        excinfo, path, "((h ((x Int))", expected_code="type_mismatch"
    )


def test_authored_return_annotation_conflicts_with_inferred_body(tmp_path):
    body = """(let-proc
      ((h (x) -> String x))
      (seed 1 (proc-ref h)))"""
    path = _write_case(tmp_path, body)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)

    _assert_located_signature_refusal(excinfo, path, "((h (x) -> String", expected_code="type_mismatch")


def test_one_authored_hook_call_inside_loop_is_a_single_inference_site(tmp_path):
    body = "(let-proc ((h (x) (+ x 1))) (repeat-hook count (proc-ref h)))"
    typed = _compile_evaluated(tmp_path, body, params="((count Int))")

    _assert_inferred_local(typed, "h", params=(("x", "Int"),), result="Int")


def test_identical_span_macro_copies_are_distinct_structural_consumer_sites(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp import procedure_typecheck as owner
    from orchestrator.workflow_lisp.expression_traversal import iter_child_exprs
    from orchestrator.workflow_lisp.expressions import ProcedureCallExpr
    original = owner._validate_local_hook_sites
    observations = []
    def validate(consumer, bindings):
        calls = []
        def visit(node, path):
            if isinstance(node, ProcedureCallExpr) and node.callee_name.endswith("::seed"):
                calls.append((path, node.span))
            for index, child in enumerate(iter_child_exprs(node)):
                visit(child, path + (index,))
        visit(consumer, ())
        assert len(calls) == 2
        assert calls[0][0] != calls[1][0]
        assert calls[0][1] == calls[1][1]
        observations.append(calls)
        return original(consumer, bindings)
    monkeypatch.setattr(owner, "_validate_local_hook_sites", validate)
    # The macro argument text (including its source span) is copied into two
    # different expression paths; both expanded calls are authored occurrences.
    body = "(let-proc ((h (x) x)) (duplicate-call (seed 1 (proc-ref h))))"
    path = _write_case(tmp_path, body)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)

    assert observations
    _assert_located_signature_refusal(excinfo, path, "(let-proc ((h", expected_code="let_proc_consumer_site_invalid")


def test_incompatible_inferred_body_reports_its_source_location(tmp_path):
    body = '''(let-proc
      ((h (x)
         (+ x 1)))
      (seed "text" (proc-ref h)))'''
    path = _write_case(tmp_path, body)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)

    _assert_located_signature_refusal(
        excinfo,
        path,
        "(+ x 1)",
        expected_code="pure_expr_operand_type_mismatch",
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_all_return_positions_supply_concrete_context_before_body(tmp_path, reverse):
    params = "(concrete ProcRef[() -> List[Int]]) (generic ProcRef[() -> List[T]])" if reverse else "(generic ProcRef[() -> List[T]]) (concrete ProcRef[() -> List[Int]])"
    declarations = DECLARATIONS + f"""(defproc consume-lists :forall (T)
      ({params}) -> Int :effects () :lowering inline 0)
"""
    typed = _compile_evaluated(tmp_path,
      "(let-proc ((h () (list))) (consume-lists (proc-ref h) (proc-ref h)))",
      declarations=declarations)
    _assert_inferred_local(typed, "h", params=(), result="List[Int]")


@pytest.mark.parametrize("consumer,expected_code", [
    ("0", "let_proc_consumer_site_invalid"),
    ("(let* ((one (seed 1 (proc-ref h))) (two (seed 2 (proc-ref h)))) two)", "let_proc_consumer_site_invalid"),
    ("(let* ((one (seed 1 (proc-ref h))) (alias (proc-ref h))) (need alias))", "let_proc_indirect_reference_unsupported"),
])
def test_invalid_sites_refuse_before_any_local_body_check(tmp_path, monkeypatch, consumer, expected_code):
    from orchestrator.workflow_lisp import procedure_typecheck as owner
    preparations = []
    original = owner._prepare_local_hook_call
    def prepare(*args, **kwargs):
        preparations.append(args[0])
        return original(*args, **kwargs)
    monkeypatch.setattr(owner, "_prepare_local_hook_call", prepare)
    body = f'(let-proc ((h (x) (+ "invalid" 1))) {consumer})'
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body)
    assert not preparations
    assert excinfo.value.diagnostics[0].code in {
        "let_proc_consumer_site_invalid", "let_proc_indirect_reference_unsupported"
    }


@pytest.mark.parametrize("consumer_loop", [False, True], ids=["helper-activation", "consumer-loop-site"])
def test_repeated_activation_uses_creator_capture_at_one_authored_site(tmp_path, consumer_loop):
    from orchestrator.workflow_lisp.closed.build import build_closed_program
    from orchestrator.workflow_lisp.closed.program import ClosedProgram
    from tests.test_workflow_evaluated_control import _machine_api, INT
    from orchestrator.workflow.evaluated.values import EvaluatedValue
    consumer = "(let* ((offset 100)) (repeat-hook count (proc-ref h)))"
    if consumer_loop:
        consumer = """(loop/recur :max count
          :state (loop-state (i Int 0) (total Int 0))
          :on-exhausted state.total
          (fn (state)
            (let* ((offset 100) (value (apply-hook (proc-ref h))))
              (if (< state.i count)
                (continue (loop-state :like state :i (+ state.i 1)
                  :total (+ state.total value)))
                (done state.total)))))"""
    typed = _compile_evaluated(tmp_path,
        f"(let-proc ((h (x) (+ x offset))) {consumer})",
        params="((offset Int) (count Int))")
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())
    result = _machine_api().evaluate_closed_program(program,
        {"offset":EvaluatedValue(7, INT), "count":EvaluatedValue(3, INT)})
    assert result.value == 24


@pytest.mark.parametrize("declaration_order", ["review-first", "revise-first"])
def test_each_ready_body_checked_once_per_preparation(tmp_path, monkeypatch, declaration_order):
    import inspect
    from orchestrator.workflow_lisp import procedure_typecheck as owner
    preparations = []
    active = []
    original_prepare, original_check = owner._prepare_local_hook_call, owner._typecheck_owner
    def prepare(*args, **kwargs):
        counts = {};preparations.append(counts);active.append(counts)
        try:return original_prepare(*args, **kwargs)
        finally:active.pop()
    def check(expr, **kwargs):
        caller = inspect.currentframe().f_back
        binding = caller.f_locals.get("binding")
        if active and caller.f_code.co_name == "_prepare_local_hook_call" and binding is not None and expr is binding.local_body:
            active[-1][binding.local_name] = active[-1].get(binding.local_name, 0) + 1
        return original_check(expr, **kwargs)
    monkeypatch.setattr(owner, "_prepare_local_hook_call", prepare)
    monkeypatch.setattr(owner, "_typecheck_owner", check)
    forms = _review_revise_forms(declaration_order, REVIEW_INCOMPLETE, REVISE_INCOMPLETE)
    _compile_evaluated(tmp_path, f"(let-proc ({forms}) (let* ((value (improve initial (proc-ref review) (proc-ref revise)))) value))", params="((initial Int))")
    assert preparations
    assert all(counts == {"review":1,"revise":1} for counts in preparations)


@pytest.mark.parametrize("body_error", [False, True], ids=["constraint-error", "body-error"])
def test_pending_and_creator_state_restored_after_error_then_success(tmp_path, monkeypatch, body_error):
    from orchestrator.workflow_lisp import procedure_typecheck as owner
    original = owner._typecheck_local_hook_group
    failures = []
    def group(expr, **creator):
        session = creator["session_state"]
        before = (getattr(session, "pending_local_hook_preparer", None), session.proc_ref_value_env, session.value_expr_env, session.workflow_signature, session.procedure_hidden_context_signature)
        try:return original(expr, **creator)
        except LispFrontendCompileError:
            after = (getattr(session, "pending_local_hook_preparer", None), session.proc_ref_value_env, session.value_expr_env, session.workflow_signature, session.procedure_hidden_context_signature)
            assert all(a is b for a,b in zip(before,after,strict=True))
            failures.append(True)
            raise
    monkeypatch.setattr(owner, "_typecheck_local_hook_group", group)
    import inspect
    body_checks = []
    original_check = owner._typecheck_owner
    def check(expr, **options):
        frame = inspect.currentframe().f_back
        binding = frame.f_locals.get("binding")
        if frame.f_code.co_name == "_prepare_local_hook_call" and binding is not None and expr is binding.local_body:
            body_checks.append(expr)
        return original_check(expr, **options)
    monkeypatch.setattr(owner, "_typecheck_owner", check)
    bad = '(let-proc ((h (x) -> String x)) (let* ((value (seed 1 (proc-ref h)))) value))'
    options = {}
    if body_error:
        bad = '(let* ((runner (proc-ref increment))) (let-proc ((h (x) (runner (+ x offset)))) (let* ((value (seed "text" (proc-ref h)))) value)))'
        options = {"params":"((offset Int))", "declarations":DECLARATIONS + '(defproc increment ((x Int)) -> Int :effects () :lowering inline (+ x 1))'}
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path/'bad', bad, **options)
    assert excinfo.value.diagnostics[0].code == ("pure_expr_operand_type_mismatch" if body_error else "type_mismatch")
    assert bool(body_checks) == body_error
    assert failures
    typed = _compile_evaluated(tmp_path/'good', '(let-proc ((h (x) x)) (let* ((value (seed 1 (proc-ref h)))) value))')
    _assert_inferred_local(typed, "h", params=(("x", "Int"),), result="Int")


@pytest.mark.parametrize("local,helper,params", [
    ("(h (x) -> Int x)", "need", (("x", "Int"),)),
    ("(h (x (y Int)) x)", "need-pair", (("x", "Int"), ("y", "Int"))),
    ("(h ((x Int) y) y)", "need-pair", (("x", "Int"), ("y", "Int"))),
])
def test_authored_constraints_ground_all_shared_positions_before_readiness(tmp_path, local, helper, params):
    declarations = DECLARATIONS + """(defproc need-pair :forall (T)
      ((hook ProcRef[(T T) -> T])) -> Int :effects () :lowering inline 0)"""
    typed = _compile_evaluated(tmp_path, f"(let-proc ({local}) ({helper} (proc-ref h)))", declarations=declarations)
    _assert_inferred_local(typed, "h", params=params, result="Int")


def test_incomplete_hook_cannot_escape_through_direct_identity_consumer(tmp_path):
    declarations = DECLARATIONS + """(defproc relay
      ((hook ProcRef[(Int) -> Int])) -> ProcRef[(Int) -> Int]
      :effects () :lowering inline hook)"""
    body = "(let* ((escaped (let-proc ((h (x) x)) (relay (proc-ref h))))) (apply-hook escaped))"
    path = _write_case(tmp_path, body, declarations=declarations)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body, declarations=declarations)
    _assert_located_signature_refusal(excinfo, path, "(let* ((escaped", expected_code="let_proc_scope_escape")


@pytest.mark.parametrize("full", [False, True])
@pytest.mark.parametrize("consumer", ["(proc-ref apply-hook)", "(bind-proc (proc-ref consume-with-offset) :offset 5)"])
def test_resolved_lexical_consumer_supplies_the_direct_expected_signature(tmp_path, consumer, full):
    declarations = DECLARATIONS + """(defproc consume-with-offset
      ((offset Int) (hook ProcRef[(Int) -> Int])) -> Int
      :effects () :lowering inline (+ offset (hook 1)))"""
    local = "(h ((x Int)) -> Int (+ x 1))" if full else "(h (x) (+ x 1))"
    body = f"(let* ((consumer {consumer})) (let-proc ({local}) (consumer (proc-ref h))))"
    typed = _compile_evaluated(tmp_path, body, declarations=declarations)
    _assert_inferred_local(typed, "h", params=(("x", "Int"),), result="Int")
    from orchestrator.workflow_lisp.closed.build import build_closed_program
    from orchestrator.workflow_lisp.closed.program import ClosedProgram
    from tests.test_workflow_evaluated_control import _machine_api
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())
    assert _machine_api().evaluate_closed_program(program, {}).value == (7 if "bind-proc" in consumer else 2)


def test_lexical_consumer_has_priority_over_same_named_catalog_procedure(tmp_path):
    body = "(let* ((use-two-compatible (proc-ref apply-hook))) (let-proc ((h (x) (+ x 1))) (use-two-compatible (proc-ref h))))"
    typed = _compile_evaluated(tmp_path, body)
    _assert_inferred_local(typed, "h", params=(("x", "Int"),), result="Int")


def test_disjoint_scopes_with_same_local_name_have_separate_sites(tmp_path):
    body = """(let* ((first (let-proc ((h (x) (+ x 1))) (seed 1 (proc-ref h))))
                     (second (let-proc ((h (x) (+ x 2))) (seed 2 (proc-ref h)))))
                (+ first second))"""
    typed = _compile_evaluated(tmp_path, body)
    assert len(_local_bases(typed)) == 2


def test_w3_bound_lexical_consumer_keeps_static_facts_from_older_module(tmp_path):
    _write_module(tmp_path / "compat" / "consumer.orc", [
        '(workflow-lisp (:language "0.1") (:target-dsl "2.35")',
        ' (defmodule compat/consumer) (export consume)',
        ' (defproc consume ((offset Int) (hook ProcRef[(Int) -> Int])) -> Int',
        '  :effects () :lowering inline (+ offset (hook 1))))',
    ])
    declarations = DECLARATIONS
    body = '(let* ((consumer (bind-proc (proc-ref old.consume) :offset 5))) (let-proc ((h (x) (+ x 1))) (consumer (proc-ref h))))'
    typed = _compile_evaluated(tmp_path, body, declarations=declarations, imports="(import compat/consumer :as old)")
    from orchestrator.workflow_lisp.closed.build import build_closed_program
    from orchestrator.workflow_lisp.closed.program import ClosedProgram
    from tests.test_workflow_evaluated_control import _machine_api
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())
    assert _machine_api().evaluate_closed_program(program, {}).value == 7


def test_generic_relay_without_concrete_constraint_stops_before_body(tmp_path, monkeypatch):
    import inspect
    from orchestrator.workflow_lisp import procedure_typecheck as owner
    body_checks = []
    original = owner._typecheck_owner
    def check(expr, **options):
        caller = inspect.currentframe().f_back
        binding = caller.f_locals.get("binding")
        if caller.f_code.co_name == "_prepare_local_hook_call" and binding is not None and expr is binding.local_body:
            body_checks.append(expr)
        return original(expr, **options)
    monkeypatch.setattr(owner, "_typecheck_owner", check)
    declarations = DECLARATIONS + """(defproc relay-generic :forall (T)
        ((hook ProcRef[(T) -> T])) -> ProcRef[(T) -> T]
        :effects () :lowering inline hook)"""
    body = '(let-proc ((h (x) x)) (seed 1 (relay-generic (proc-ref h))))'
    path = _write_case(tmp_path, body, declarations=declarations)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body, declarations=declarations)
    _assert_located_signature_refusal(excinfo, path, '(let-proc ((h', expected_code='let_proc_expected_signature_missing')
    assert not body_checks


@pytest.mark.parametrize("full", [False, True], ids=["inferred", "complete"])
@pytest.mark.parametrize("consumer_site", ["creator", "body"])
@pytest.mark.parametrize("bound", [False, True], ids=["alias", "bound"])
def test_resolved_lexical_relay_cannot_return_local_from_its_scope(tmp_path, full, consumer_site, bound):
    declarations = DECLARATIONS + """(defproc relay
      ((hook ProcRef[(Int) -> Int])) -> ProcRef[(Int) -> Int]
      :effects () :lowering inline hook)
    (defproc relay-bound
      ((marker Int) (hook ProcRef[(Int) -> Int])) -> ProcRef[(Int) -> Int]
      :effects () :lowering inline hook)"""
    consumer = "(bind-proc (proc-ref relay-bound) :marker 5)" if bound else "(proc-ref relay)"
    local = "(h ((x Int)) -> Int x)" if full else "(h (x) x)"
    if consumer_site == "creator":
        body = f"""(let* ((consumer {consumer}))
          (let-proc ({local})
            (consumer (proc-ref h))))"""
        marker = "(consumer (proc-ref h))"
    else:
        body = f"""(let-proc ({local})
          (let* ((consumer {consumer}))
            (consumer (proc-ref h))))"""
        marker = "(let* ((consumer"
    path = _write_case(tmp_path, body, declarations=declarations)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_evaluated(tmp_path, body, declarations=declarations)
    _assert_located_signature_refusal(excinfo, path, marker, expected_code="let_proc_scope_escape")


def test_consumer_shadow_and_forwarded_alias_use_the_inner_resolved_fact(tmp_path):
    declarations = DECLARATIONS + """(defproc relay
      ((hook ProcRef[(Int) -> Int])) -> ProcRef[(Int) -> Int]
      :effects () :lowering inline hook)"""
    body = """(let* ((consumer (proc-ref relay)))
      (let-proc ((h (x) (+ x 1)))
        (let* ((consumer (proc-ref apply-hook)) (forwarded consumer))
          (forwarded (proc-ref h)))))"""
    typed = _compile_evaluated(tmp_path, body, declarations=declarations)
    from orchestrator.workflow_lisp.closed.build import build_closed_program
    from orchestrator.workflow_lisp.closed.program import ClosedProgram
    from tests.test_workflow_evaluated_control import _machine_api
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())
    assert _machine_api().evaluate_closed_program(program, {}).value == 2
