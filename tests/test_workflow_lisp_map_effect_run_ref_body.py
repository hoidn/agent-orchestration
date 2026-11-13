"""Surface coherence I1: a `list/map-effect` body that holds a run reference stays exactly one call with pure
arguments, also when the run reference is reached only after specialization (a procedure-reference argument, a
`bind-proc` value, a `let-proc` local, a generic procedure, a macro, two calls deep).

Every program is a controller around a path-mode run reference (`CALL`) to a committed candidate, built by
`_public_fixture`; each goes through `orchestrator run`, so an accepted one is also evaluated. No provider.
"""

from __future__ import annotations

import pytest

from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_run_ref import _public_fixture

DEFINITIONS = '''
  (defrecord Tag (n Int))
  (defproc one-ref ((n Int)) -> Bool (let* ((attempt CALL)) attempt.value))
  (defproc two-refs ((n Int)) -> Bool (let* ((a CALL) (b CALL)) b.value))
  (defproc one-ref-k ((k Int) (n Int)) -> Bool (let* ((attempt CALL)) attempt.value))
  (defproc two-refs-k ((k Int) (n Int)) -> Bool (let* ((a CALL) (b CALL)) b.value))
  (defproc via ((f ProcRef[Int -> Bool]) (xs List[Int])) -> Int
    (list/length (list/map-effect ((x xs)) :max 2 (f x))))
  (defproc via-let ((f ProcRef[Int -> Bool]) (xs List[Int])) -> Int
    (list/length (list/map-effect ((x xs)) :max 2 (let* ((a (f x))) (if a 1 0)))))
  (defproc outer ((f ProcRef[Int -> Bool])) -> Int (via f (list 1 2)))
  (defmacro map-let (f xs) (list/length (list/map-effect ((x xs)) :max 2 (let* ((a (f x))) (if a 1 0)))))
  (defproc via-macro ((f ProcRef[Int -> Bool]) (xs List[Int])) -> Int (map-let f xs))
  (defproc via-generic :forall (S) ((s S) (f ProcRef[Int -> Bool]) (xs List[Int])) :where ((S is-record)) -> Int
    (list/length (list/map-effect ((x xs)) :max 2 (f x))))
'''
TWO_REFS_LOCAL = "(let-proc ((h ((n Int)) -> Bool (let* ((a CALL) (b CALL)) b.value))) {})"
ONE_REF_LOCAL = "(let-proc ((h ((n Int)) -> Bool (let* ((a CALL)) a.value))) {})"
TAG = "(record Tag :n 1)"

# The run reference reaches the map body only after specialization.
REFUSED = {
    "procref_one_call_two_refs": "(via (proc-ref two-refs) (list 1 2))",
    "procref_let_body": "(via-let (proc-ref one-ref) (list 1 2))",
    "bind_proc_two_refs": "(via (bind-proc (proc-ref two-refs-k) :k 1) (list 1 2))",
    "bind_proc_let_body": "(via-let (bind-proc (proc-ref one-ref-k) :k 1) (list 1 2))",
    "let_proc_two_refs": TWO_REFS_LOCAL.format("(via (proc-ref h) (list 1 2))"),
    "let_proc_let_body": ONE_REF_LOCAL.format("(via-let (proc-ref h) (list 1 2))"),
    "generic_two_refs": f"(via-generic {TAG} (proc-ref two-refs) (list 1 2))",
    "macro_let_body": "(via-macro (proc-ref one-ref) (list 1 2))",
    "two_calls_deep": "(outer (proc-ref two-refs))",
}
# Exactly one call with pure arguments, whose callee runs one run reference: still admitted.
ACCEPTED = {
    "procref_one_call": "(via (proc-ref one-ref) (list 1 2))",
    "bind_proc_one_call": "(via (bind-proc (proc-ref one-ref-k) :k 1) (list 1 2))",
    "let_proc_one_call": ONE_REF_LOCAL.format("(via (proc-ref h) (list 1 2))"),
    "generic_one_call": f"(via-generic {TAG} (proc-ref one-ref) (list 1 2))",
    "two_calls_deep_one_call": "(outer (proc-ref one-ref))",
}


def run(tmp_path, count: str):
    parent, source, refs = _public_fixture(
        tmp_path, parent_target="2.40", definitions=lambda call: DEFINITIONS.replace("CALL", call),
        body=lambda call: f"(= {count.replace('CALL', call)} 2)")
    return _run_cli(parent, str(source), "--run-ref-root", str(refs)), refs


@pytest.mark.parametrize("case", sorted(REFUSED))
def test_run_reference_reached_after_specialization_keeps_the_one_call_rule(tmp_path, case):
    result, refs = run(tmp_path, REFUSED[case])

    assert result.returncode == 2, result.stdout + result.stderr
    assert "[list_map_effect_body_unsupported]" in result.stderr
    assert not list(refs.rglob("child-request.json"))


@pytest.mark.parametrize("case", sorted(ACCEPTED))
def test_one_call_body_whose_callee_runs_one_run_reference_runs(tmp_path, case):
    result, refs = run(tmp_path, ACCEPTED[case])

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "true"
    assert len(list(refs.rglob("child-request.json"))) == 2


# Each of the two typing-time checks of a run-reference body, alone: the other one would refuse the same
# program, so each test names its cause.

def refusal(tmp_path, body: str) -> str:
    result, _refs = run(tmp_path, f"(list/length (list/map-effect ((x (list 1 2))) :max 2 {body}))")
    assert result.returncode == 2 and "[list_map_effect_body_unsupported]" in result.stderr, result.stderr
    return result.stderr


def test_run_reference_body_that_is_not_one_call_is_refused_for_its_shape(tmp_path):
    assert "body must be one provider, command, workflow, or procedure call" in refusal(
        tmp_path, "(let* ((n x)) (one-ref n))")


def test_run_reference_call_with_an_effectful_argument_is_refused_for_its_argument(tmp_path):
    assert "call arguments must be pure" in refusal(tmp_path, "(one-ref (if (one-ref x) 1 2))")


def test_run_reference_in_a_serial_max_runs_once(tmp_path):
    """Like a loop's `:max`, a serial map's `:max` may hold a run reference; it is not an item frame."""
    result, refs = run(tmp_path, "(list/length (list/map-effect ((x (list 1 2))) :max (if (one-ref 0) 2 0) x))")

    assert result.returncode == 0, result.stdout + result.stderr
    assert len(list(refs.rglob("child-request.json"))) == 1


def test_run_reference_one_call_body_of_a_parallel_map_in_an_inline_helper_runs(tmp_path):
    """Target 2.37: a parallel map whose one call holds a run reference, inside an inline helper that an outer
    parallel map calls, is admitted and runs both items."""
    definitions = (
        "(defproc one-ref ((n Int)) -> Bool :effects ((runs-ref run)) :lowering inline (let* ((attempt CALL)) attempt.value)) "
        "(defproc pmap ((xs List[String])) -> Int :effects ((runs-ref run)) :lowering inline "
        "(list/length (list/map-effect ((repo xs)) :max 2 :parallel 2 :workspace repo (one-ref 1))))")
    parent, source, refs = _public_fixture(
        tmp_path, parent_target="2.37", definitions=lambda call: definitions.replace("CALL", call),
        body=lambda _call: ('(= (list/length (list/map-effect ((outer (list "o"))) :max 1 :parallel 1 '
                            ':workspace outer (pmap (list "a" "b")))) 1)'))
    for item in ("o", "a", "b", "o/a", "o/b"):
        (parent / item).mkdir()

    result = _run_cli(parent, str(source), "--run-ref-root", str(refs))

    assert result.returncode == 0, result.stdout + result.stderr
    assert len(list(refs.rglob("child-request.json"))) == 2
