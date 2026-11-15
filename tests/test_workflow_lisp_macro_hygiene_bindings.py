"""Macro hygiene knows the binding positions of a template (surface coherence I2a, reviews N1, N2, N4).

A name a template binds (a `let*` local, a `let-proc` parameter, a loop state) and a `cond` test that
reads a local mean inside the expansion what they mean written inline, whatever names the call site
binds. Each case pins the value of the expanded program and of the same program written inline. The
digests differ from the inline program's: hygiene renames template locals, and local names are part
of the program. A call head is never renamed (as on `main`): what a head names needs the resolver
(forms, macros, `defun`, `defproc`, locals), which hygiene does not have; that is a recorded defect.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from tests.workflow_lisp_closed_program_helpers import build


DECLARATIONS = """(defproc apply-int ((hook ProcRef[Int -> Int]) (value Int)) -> Int (hook value))
  (defproc increment ((value Int)) -> Int (+ value 1))
  (defproc dbl ((value Int)) -> Int (* value 2))"""


def _program(root: Path, body: str, *, template: str = "", extra: str = "") -> ClosedProgram:
    macro = f"{extra} (defmacro m (x) {template})" if template else extra
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule probe) (export run)
  {DECLARATIONS}
  {macro}
  (defworkflow run () -> Int {body}))'''
    return ClosedProgram.from_artifact(build(root, source).artifact())


def _value(root: Path, body: str, *, template: str = "", extra: str = "") -> object:
    return evaluate_closed_program(_program(root, body, template=template, extra=extra), {}).value


HOOK = "(let-proc ((hook ((y Int)) -> Int (+ y 1))) (+ y (apply-int (proc-ref hook) {x})))"
TWO_HOOKS = "(let-proc ((a ((z Int)) -> Int (+ z 0)) (hook ((y Int)) -> Int (+ y 1))) (+ y (apply-int (proc-ref hook) {x})))"
CAPTURE = "(let-proc ((hook ((v Int)) -> Int (+ v tmp))) (apply-int (proc-ref hook) {x}))"
EXPLICIT = "(let-proc (hook ((v Int)) -> Int :captures (tmp) (+ v tmp)) (apply-int (proc-ref hook) {x}))"
EMPTY_CAPTURES = "(let-proc (hook ((y Int)) -> Int :captures () (+ y 1)) (+ y (apply-int (proc-ref hook) {x})))"

# case: (template, call site, the same program written inline, value)
CASES = {
    "let_proc_parameter_named_like_a_template_local": (
        f"(let* ((y 5)) {HOOK.format(x='x')})", "(m 1)", f"(let* ((y 5)) {HOOK.format(x='1')})", 7),
    "second_let_proc_binding_parameter_named_like_a_template_local": (
        f"(let* ((y 5)) {TWO_HOOKS.format(x='x')})", "(m 1)", f"(let* ((y 5)) {TWO_HOOKS.format(x='1')})", 7),
    "explicit_empty_captures_and_a_parameter_named_like_a_template_local": (
        f"(let* ((y 5)) {EMPTY_CAPTURES.format(x='x')})", "(m 1)", f"(let* ((y 5)) {EMPTY_CAPTURES.format(x='1')})", 7),
    "let_proc_captures_a_template_local_beside_a_caller_local_of_that_name": (
        f"(let* ((tmp 3)) {CAPTURE.format(x='x')})", "(let* ((tmp 100)) (+ tmp (m 0)))",
        f"(let* ((tmp 100)) (+ tmp (let* ((tmp2 3)) {CAPTURE.replace('tmp', 'tmp2').format(x='0')})))", 103),
    "explicit_capture_of_a_template_local": (
        f"(let* ((tmp 3)) {EXPLICIT.format(x='x')})", "(let* ((tmp 100)) (+ tmp (m 0)))",
        f"(let* ((tmp 100)) (+ tmp (let* ((tmp2 3)) {EXPLICIT.replace('tmp', 'tmp2').format(x='0')})))", 103),
    "cond_test_that_is_a_template_local": (
        "(let* ((flag true)) (cond (flag 1) (true 0)))", "(let* ((flag false)) (m 1))",
        "(let* ((flag false)) (let* ((flag2 true)) (cond (flag2 1) (true 0))))", 1),
    "cond_test_that_is_a_template_local_without_a_caller_binding": (
        "(let* ((flag true)) (cond (flag 1) (true 0)))", "(m 1)", "(let* ((flag true)) (cond (flag 1) (true 0)))", 1),
    "template_local_named_like_a_procedure_keeps_the_procedure_head": (
        "(let* ((increment 3)) (+ increment (increment x)))", "(m 1)",
        "(let* ((increment 3)) (+ increment (increment 1)))", 5),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_template_binding_means_what_it_means_inline(tmp_path: Path, case: str) -> None:
    template, call, inline, value = CASES[case]

    assert (_value(tmp_path / "macro", call, template=template), _value(tmp_path / "inline", inline)) == (value, value)


# N4: a loop state that shadows a template local, in both forms; and a caller argument named like the
# template's loop state (the state must not capture it).
LOOP_CASES = {
    "loop_state_shadows_a_template_local": (
        "(let* ((s (+ x 4))) (loop/recur ((s s)) :max 5 :on-exhausted s (if (< s 7) (continue (+ s 1)) (done s))))",
        "(let* ((s (+ x 4))) (loop/recur ((s s)) :max 5 :on-exhausted s (if (< s 7) (continue (+ s 1)) (done s))))",
        "(m 1)",
        "(let* ((s 5)) (loop/recur ((t s)) :max 5 :on-exhausted t (if (< t 7) (continue (+ t 1)) (done t))))", 7),
    "on_exhausted_reads_the_loop_state_not_the_template_local": (
        "(let* ((s 10)) (loop/recur ((s (+ x 0))) :max 1 :on-exhausted (+ s 100) (if (< s 0) (done s) (continue (+ s 1)))))",
        "(let* ((s 10)) (loop/recur ((s (+ x 0))) :max 1 :on-exhausted (+ s 100) (if (< s 0) (done s) (continue (+ s 1)))))",
        "(m 1)",
        "(loop/recur ((t 1)) :max 1 :on-exhausted (+ t 100) (if (< t 0) (done t) (continue (+ t 1))))", 102),
    "caller_argument_named_like_the_loop_state": (
        "(loop/recur ((s 0)) :max 5 :on-exhausted s (if (< s x) (continue (+ s 1)) (done s)))",
        "(loop/recur ((s 0)) :max 5 :on-exhausted s (if (< s x) (continue (+ s 1)) (done s)))",
        "(let* ((s 2)) (m s))",
        "(let* ((s 2)) (loop/recur ((t 0)) :max 5 :on-exhausted t (if (< t s) (continue (+ t 1)) (done t))))", 2),
}


@pytest.mark.parametrize("form", ["binder", "fn"])
@pytest.mark.parametrize("case", sorted(LOOP_CASES))
def test_template_loop_state_means_what_it_means_inline(tmp_path: Path, case: str, form: str) -> None:
    binder, fn, call, inline, value = LOOP_CASES[case]
    template = binder if form == "binder" else fn

    assert (_value(tmp_path / "macro", call, template=template), _value(tmp_path / "inline", inline)) == (value, value)


@pytest.mark.parametrize("case", sorted(LOOP_CASES))
def test_template_loop_state_builds_one_program_in_both_forms(tmp_path: Path, case: str) -> None:
    binder, fn, call, _, _ = LOOP_CASES[case]

    assert _program(tmp_path / "binder", call, template=binder).digest == _program(tmp_path / "fn", call, template=fn).digest


# A head named like a template local keeps its name, so it names what it names on `main`: the `defun`,
# the user macro or the form, never the local proc-ref.
HEAD_CASES = {
    "defun": ("(defun f ((n Int)) -> Int (* n 100))", "(let* ((f (proc-ref increment))) (f x))", 500),
    "user_macro": ("(defmacro g (y) (* y 100))", "(let* ((g (proc-ref increment))) (g x))", 500),
    "form": ("(defproc pick3 ((c Bool) (a Int) (b Int)) -> Int (+ a (+ b 100)))",
             "(let* ((if (proc-ref pick3))) (if (= x 5) 1 2))", 1),
}


@pytest.mark.parametrize("case", sorted(HEAD_CASES))
def test_a_head_named_like_a_template_local_is_not_renamed(tmp_path: Path, case: str) -> None:
    extra, template, value = HEAD_CASES[case]

    assert _value(tmp_path, "(m 5)", template=template, extra=extra) == value
