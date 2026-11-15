"""Surface coherence I1: in a program that holds a run reference anywhere, every `list/map-effect` body is
exactly one call with pure arguments, as before I1, whatever route reaches the run reference: a procedure-reference
argument, a `bind-proc` value, a `let-proc` local, a generic procedure, a macro, a workflow call (local or
imported), a nested loop, a nested parallel map, several calls deep, or no route at all. A program with no run
reference admits any body, through every route.

Every program is a controller built by `_public_fixture` around a path-mode run reference (`CALL`) to a committed
candidate, optionally importing `lib.orc`; each goes through `orchestrator run`, so an accepted one is also
evaluated. Definitions no program calls are not part of its closed program. No provider.
"""

from __future__ import annotations

import re

import pytest

from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_run_ref import _public_fixture
from tests.source_edits import replace_exact

DEFINITIONS = '''
  (defrecord Tag (n Int))
  (defproc no-ref ((n Int)) -> Bool (= n 1))
  (defproc one-ref ((n Int)) -> Bool (let* ((attempt CALL)) attempt.value))
  (defproc two-refs ((n Int)) -> Bool (let* ((a CALL) (b CALL)) b.value))
  (defproc one-ref-k ((k Int) (n Int)) -> Bool (let* ((attempt CALL)) attempt.value))
  (defproc two-refs-k ((k Int) (n Int)) -> Bool (let* ((a CALL) (b CALL)) b.value))
  (defworkflow w1 ((n Int)) -> Bool (let* ((a CALL)) a.value))
  (defworkflow w2 ((n Int)) -> Bool (let* ((a CALL) (b CALL)) b.value))
  (defproc hidew1 ((n Int)) -> Bool (call w1 :n n))
  (defproc hidew2 ((n Int)) -> Bool (let* ((a (call w1 :n n)) (b (call w1 :n n))) b))
  (defproc hidew2b ((n Int)) -> Bool (call w2 :n n))
  (defproc via ((f ProcRef[Int -> Bool]) (xs List[Int])) -> Int
    (list/length (list/map-effect ((x xs)) :max 2 (f x))))
  (defproc via-let ((f ProcRef[Int -> Bool]) (xs List[Int])) -> Int
    (list/length (list/map-effect ((x xs)) :max 2 (let* ((a (f x))) (if a 1 0)))))
  (defproc via-if ((f ProcRef[Int -> Bool]) (xs List[Int])) -> Int
    (list/length (list/map-effect ((x xs)) :max 2 (if (= x 1) (f x) (f x)))))
  (defproc via-loop-in-body ((f ProcRef[Int -> Bool]) (xs List[Int])) -> Int
    (list/length (list/map-effect ((x xs)) :max 2
      (loop/recur :max 1 :state 0 :on-exhausted false (fn (s) (done (f x)))))))
  (defproc via-map-in-loop ((f ProcRef[Int -> Bool]) (xs List[Int])) -> Int
    (loop/recur :max 1 :state 0 :on-exhausted 0
      (fn (s) (done (list/length (list/map-effect ((x xs)) :max 2 (let* ((a (f x))) (if a 1 0))))))))
  (defproc via-par-in-serial ((f ProcRef[Int -> Bool]) (xs List[Int])) -> Int
    (list/length (list/map-effect ((x xs)) :max 2
      (let* ((n (list/length (list/map-effect ((r (list "a"))) :max 1 :parallel 1 :workspace r (f 1))))) (+ n 1)))))
  (defproc via-par ((f ProcRef[Int -> Bool])) -> Int
    (list/length (list/map-effect ((r (list "a" "b"))) :max 2 :parallel 2 :workspace r (f 1))))
  (defproc via2 ((f ProcRef[Int -> Bool]) (xs List[Int])) -> Int (via-let f xs))
  (defproc via3 ((f ProcRef[Int -> Bool])) -> Int (via2 f (list 1 2)))
  (defproc outer ((f ProcRef[Int -> Bool])) -> Int (via f (list 1 2)))
  (defworkflow w0 ((n Int)) -> Bool (= n 1))
  (defproc hidew0 ((n Int)) -> Bool (call w0 :n n))
  (defproc hidew0-twice ((n Int)) -> Bool (let* ((a (call w0 :n n)) (b (call w0 :n n))) b))
  (defproc no-ref-k ((k Int) (n Int)) -> Bool (= n k))
  (defproc via-two-let ((f ProcRef[Int -> Bool]) (xs List[Int])) -> Int
    (list/length (list/map-effect ((x xs)) :max 2 (let* ((a (f x)) (b (f x))) (if b 1 0)))))
  (defproc via-if-two ((f ProcRef[Int -> Bool]) (xs List[Int])) -> Int
    (list/length (list/map-effect ((x xs)) :max 2 (if (= x 1) (let* ((a (f x)) (b (f x))) (if b 1 0)) 0))))
  (defproc hidel ((n Int)) -> Bool (call lib-w1 :n n))
  (defproc hidel-twice ((n Int)) -> Bool (let* ((a (call lib-w1 :n n)) (b (call lib-w1 :n n))) b))
  (defproc hidel0 ((n Int)) -> Bool (call lib-w0 :n n))
  (defmacro map-let (f xs) (list/length (list/map-effect ((x xs)) :max 2 (let* ((a (f x))) (if a 1 0)))))
  (defproc via-macro ((f ProcRef[Int -> Bool]) (xs List[Int])) -> Int (map-let f xs))
  (defproc via-generic :forall (S) ((s S) (f ProcRef[Int -> Bool]) (xs List[Int])) :where ((S is-record)) -> Int
    (list/length (list/map-effect ((x xs)) :max 2 (f x))))
'''
LIB = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40") (defmodule lib) (export lib-w0 lib-w1)
  (defworkflow lib-w0 ((n Int)) -> Bool (= n 1))
  (defworkflow lib-w1 ((n Int)) -> Bool (let* ((a CALL)) a.value)))'''
TWO_REFS_LOCAL = "(let-proc ((h ((n Int)) -> Bool (let* ((a CALL) (b CALL)) b.value))) {})"
ONE_REF_LOCAL = "(let-proc ((h ((n Int)) -> Bool (let* ((a CALL)) a.value))) {})"
TAG = "(record Tag :n 1)"
LISTED = "(list 1 2)"

# The run reference reaches the map body only after specialization, or through a call or a nested form.
REFUSED = {
    "procref_one_call_two_refs": f"(via (proc-ref two-refs) {LISTED})",
    "procref_let_body": f"(via-let (proc-ref one-ref) {LISTED})",
    "bind_proc_two_refs": f"(via (bind-proc (proc-ref two-refs-k) :k 1) {LISTED})",
    "bind_proc_let_body": f"(via-let (bind-proc (proc-ref one-ref-k) :k 1) {LISTED})",
    "let_proc_two_refs": TWO_REFS_LOCAL.format(f"(via (proc-ref h) {LISTED})"),
    "let_proc_let_body": ONE_REF_LOCAL.format(f"(via-let (proc-ref h) {LISTED})"),
    "generic_two_refs": f"(via-generic {TAG} (proc-ref two-refs) {LISTED})",
    "macro_let_body": f"(via-macro (proc-ref one-ref) {LISTED})",
    "two_calls_deep": "(outer (proc-ref two-refs))",
    "workflow_calls_one_call_two": f"(via (proc-ref hidew2) {LISTED})",
    "workflow_call_let_body": f"(via-let (proc-ref hidew1) {LISTED})",
    "workflow_call_if_body": f"(via-if (proc-ref hidew1) {LISTED})",
    "workflow_call_three_levels": "(via3 (proc-ref hidew1))",
    "loop_in_body_run_ref": f"(via-loop-in-body (proc-ref one-ref) {LISTED})",
    "loop_in_body_workflow_call": f"(via-loop-in-body (proc-ref hidew1) {LISTED})",
    "map_in_loop_run_ref": f"(via-map-in-loop (proc-ref one-ref) {LISTED})",
    "map_in_loop_workflow_call": f"(via-map-in-loop (proc-ref hidew1) {LISTED})",
    "parallel_in_serial_run_ref": f"(via-par-in-serial (proc-ref one-ref) {LISTED})",
    "parallel_in_serial_workflow_call": f"(via-par-in-serial (proc-ref hidew1) {LISTED})",
    # A run reference behind a workflow imported from another module.
    "imported_workflow_two_calls": f"(via-two-let (proc-ref hidel) {LISTED})",
    "imported_workflow_one_call_two": f"(via (proc-ref hidel-twice) {LISTED})",
    "imported_workflow_let_body": f"(via-let (proc-ref hidel) {LISTED})",
    "imported_workflow_if_body": f"(via-if-two (proc-ref hidel) {LISTED})",
    "imported_workflow_parallel_in_serial": f"(via-par-in-serial (proc-ref hidel) {LISTED})",
}
# The map body reaches no run reference, but the program holds one elsewhere.
REFUSED_BESIDE_A_RUN_REFERENCE = {
    "same_definition": f"(if (one-ref 0) (via-let (proc-ref no-ref) {LISTED}) 0)",
    "direct_body_same_definition": (f"(if (one-ref 0) (list/length (list/map-effect ((x {LISTED})) :max 2 "
                                    "(let* ((a (call w0 :n x)) (b (call w0 :n x))) (if b 1 0)))) 0)"),
    "other_definition": f"(+ (via-let (proc-ref no-ref) {LISTED}) (if (one-ref 0) 0 1))",
    "imported_workflow_elsewhere": f"(+ (via-let (proc-ref no-ref) {LISTED}) (if (hidel 0) 0 1))",
    "one_call_two_plain_effects": f"(if (one-ref 0) (via (proc-ref hidew0-twice) {LISTED}) 0)",
    "parallel_let_body": ("(if (one-ref 0) (list/length (list/map-effect ((r (list \"a\" \"b\"))) :max 2 :parallel 2 "
                          ":workspace r (let* ((a (call w0 :n 1))) (if a 1 0)))) 0)"),
}
# Exactly one call with pure arguments, whatever its callee runs; or a body that reaches no run reference.
# case -> (program, child runs launched)
ACCEPTED = {
    "procref_one_call": (f"(via (proc-ref one-ref) {LISTED})", 2),
    "bind_proc_one_call": (f"(via (bind-proc (proc-ref one-ref-k) :k 1) {LISTED})", 2),
    "let_proc_one_call": (ONE_REF_LOCAL.format(f"(via (proc-ref h) {LISTED})"), 2),
    "generic_one_call": (f"(via-generic {TAG} (proc-ref one-ref) {LISTED})", 2),
    "two_calls_deep_one_call": ("(outer (proc-ref one-ref))", 2),
    "workflow_call_one_call": (f"(via (proc-ref hidew1) {LISTED})", 2),
    "workflow_call_one_call_two_refs": (f"(via (proc-ref hidew2b) {LISTED})", 4),
    "direct_workflow_call_two_refs": (f"(list/length (list/map-effect ((x {LISTED})) :max 2 (call w2 :n x)))", 4),
    "parallel_one_call_two_refs": ("(via-par (proc-ref two-refs))", 4),
    "imported_workflow_one_call": (f"(via (proc-ref hidel) {LISTED})", 2),
}
# No run reference in the program: any body, through every route; no child run.
FREE = {
    "procref_let_body": f"(via-let (proc-ref no-ref) {LISTED})",
    "procref_one_call_two_effects": f"(via (proc-ref hidew0-twice) {LISTED})",
    "bind_proc_let_body": f"(via-let (bind-proc (proc-ref no-ref-k) :k 1) {LISTED})",
    "let_proc_let_body": f"(let-proc ((h ((n Int)) -> Bool (= n 1))) (via-let (proc-ref h) {LISTED}))",
    "generic_let_body": f"(via-generic {TAG} (proc-ref hidew0-twice) {LISTED})",
    "macro_let_body": f"(via-macro (proc-ref no-ref) {LISTED})",
    "workflow_call_two_calls": f"(via-two-let (proc-ref hidew0) {LISTED})",
    "workflow_call_if_body": f"(via-if-two (proc-ref hidew0) {LISTED})",
    "workflow_call_three_levels": "(via3 (proc-ref hidew0))",
    "imported_workflow_two_calls": f"(via-two-let (proc-ref hidel0) {LISTED})",
    "loop_in_body": f"(via-loop-in-body (proc-ref hidew0) {LISTED})",
    "map_in_loop": f"(via-map-in-loop (proc-ref hidew0) {LISTED})",
    "parallel_in_serial": f"(via-par-in-serial (proc-ref hidew0) {LISTED})",
    "parallel_let_body": ("(list/length (list/map-effect ((r (list \"a\" \"b\"))) :max 2 :parallel 2 "
                          ":workspace r (let* ((a (call w0 :n 1))) (if a 1 0))))"),
}


def run(tmp_path, count: str):
    calls = []
    parent, source, refs = _public_fixture(
        tmp_path, parent_target="2.40", imports="(import lib :only (lib-w0 lib-w1))",
        definitions=lambda call: calls.append(call) or replace_exact(DEFINITIONS, "CALL", call, count=9),
        body=lambda call: f"(= {count.replace('CALL', call)} 2)")  # a body may hold the call or not
    (parent / "lib.orc").write_text(replace_exact(LIB, "CALL", calls[0]))
    for item in ("a", "b"):
        (parent / item).mkdir()
    return _run_cli(parent, str(source), "--run-ref-root", str(refs)), refs, source


@pytest.mark.parametrize("case", sorted(REFUSED))
def test_body_reaching_a_run_reference_by_any_route_keeps_the_one_call_rule(tmp_path, case):
    result, refs, _source = run(tmp_path, REFUSED[case])

    assert result.returncode == 2, result.stdout + result.stderr
    assert "[list_map_effect_body_unsupported]" in result.stderr
    assert not list(refs.rglob("child-request.json"))


@pytest.mark.parametrize("case", sorted(REFUSED_BESIDE_A_RUN_REFERENCE))
def test_program_holding_a_run_reference_refuses_a_map_body_that_is_not_one_call_even_reaching_none(tmp_path, case):
    result, refs, _source = run(tmp_path, REFUSED_BESIDE_A_RUN_REFERENCE[case])

    assert result.returncode == 2, result.stdout + result.stderr
    assert "[list_map_effect_body_unsupported]" in result.stderr
    assert not list(refs.rglob("child-request.json"))


@pytest.mark.parametrize("case", sorted(ACCEPTED))
def test_one_call_body_with_pure_arguments_runs_in_a_program_holding_a_run_reference(tmp_path, case):
    program, children = ACCEPTED[case]
    result, refs, _source = run(tmp_path, program)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "true"
    assert len(list(refs.rglob("child-request.json"))) == children


@pytest.mark.parametrize("case", sorted(FREE))
def test_program_without_a_run_reference_runs_any_map_body_through_every_route(tmp_path, case):
    result, refs, _source = run(tmp_path, FREE[case])

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "true"
    assert not list(refs.rglob("child-request.json"))


# Each of the two typing-time checks of a run-reference body, alone: the other one, or the closed build, would
# refuse the same program at another place, so each test asserts where the refusal points.

def refused_at(tmp_path, body: str) -> str:
    """The source text from the refusal's line and column on."""
    result, _refs, source = run(tmp_path, f"(list/length (list/map-effect ((x (list 1 2))) :max 2 {body}))")
    assert result.returncode == 2 and "[list_map_effect_body_unsupported]" in result.stderr, result.stderr
    line, column = map(int, re.search(r"controller\.orc:(\d+):(\d+): \[list_map_effect_body_unsupported\]",
                                      result.stderr).groups())
    return source.read_text().splitlines()[line - 1][column - 1:]


def test_run_reference_body_that_is_not_one_call_is_refused_at_the_body(tmp_path):
    assert refused_at(tmp_path, "(let* ((n x)) (one-ref n))").startswith("(let* ((n x))")


def test_run_reference_call_with_an_effectful_argument_is_refused_at_the_argument(tmp_path):
    assert refused_at(tmp_path, "(one-ref (if (one-ref x) 1 2))").startswith("(if (one-ref x)")


def test_run_reference_in_a_serial_max_runs_once(tmp_path):
    """Like a loop's `:max`, a serial map's `:max` may hold a run reference; it is not an item frame (the program
    holds a run reference, so the body is one call)."""
    result, refs, _source = run(tmp_path, "(list/length (list/map-effect ((x (list 1 2))) :max (if (one-ref 0) 2 0) (call w0 :n x)))")

    assert result.returncode == 0, result.stdout + result.stderr
    assert len(list(refs.rglob("child-request.json"))) == 1


def test_run_reference_one_call_body_of_a_parallel_map_in_an_inline_helper_runs(tmp_path):
    """A parallel map whose one call holds a run reference, inside an inline helper that an outer
    parallel map calls, is admitted and runs both items."""
    definitions = (
        "(defproc one-ref ((n Int)) -> Bool "
        "(let* ((attempt CALL)) attempt.value)) "
        "(defproc pmap ((xs List[String])) -> Int "
        "(list/length (list/map-effect ((repo xs)) :max 2 :parallel 2 :workspace repo (one-ref 1))))")
    parent, source, refs = _public_fixture(
        tmp_path, definitions=lambda call: replace_exact(definitions, "CALL", call),
        body=lambda _call: ('(= (list/length (list/map-effect ((outer (list "o"))) :max 1 :parallel 1 '
                            ':workspace outer (pmap (list "a" "b")))) 1)'))
    for item in ("o", "a", "b", "o/a", "o/b"):
        (parent / item).mkdir()

    result = _run_cli(parent, str(source), "--run-ref-root", str(refs))

    assert result.returncode == 0, result.stdout + result.stderr
    assert len(list(refs.rglob("child-request.json"))) == 2
