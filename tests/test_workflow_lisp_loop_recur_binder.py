"""The binder form of `loop/recur` builds the same closed program as the `fn` form (surface coherence I2a)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.agent_session_shims import closed_path
from tests.workflow_lisp_closed_program_helpers import build


COMMANDS = ("seed", "budget", "step", "check", "give-up")
BOUNDARIES = {
    name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"), closure=())
    for name in COMMANDS
}
PROCEDURES = "\n".join(
    f'(defproc {name} ((n Int)) -> {"Bool" if name == "check" else "Int"} '
    f'(command-result {name} :argv ("python" "probe.py" n) :returns {"Bool" if name == "check" else "Int"}))'
    for name in COMMANDS
)


def _module(body: str, *, extra: str = "", params: str = "") -> str:
    return f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule probe) (export run)
  {PROCEDURES}
  {extra}
  (defworkflow run ({params}) -> Int {body}))'''


# Each case: (fn-form source, binder-form source) of the same loop.
CASES = {
    "int_state": (
        _module("(loop/recur :max 3 :state 0 (fn (n) (if (check n) (done n) (continue (step n)))))"),
        _module("(loop/recur ((n 0)) :max 3 (if (check n) (done n) (continue (step n))))"),
    ),
    "state_record": (
        _module("""(loop/recur :max 4 :state (loop-state (i Int 0) (total Int 1))
              :on-exhausted state.total
              (fn (state) (if (check state.i) (done state.total)
                (continue (loop-state :like state :i (step state.i) :total (+ state.total 1))))))"""),
        _module("""(loop/recur ((state (loop-state (i Int 0) (total Int 1)))) :max 4
              :on-exhausted state.total
              (if (check state.i) (done state.total)
                (continue (loop-state :like state :i (step state.i) :total (+ state.total 1)))))"""),
    ),
    "on_exhausted_uses_state": (
        _module("(loop/recur :max 2 :state 5 :on-exhausted (+ pads 1) (fn (pads) (if (check pads) (done pads) (continue (step pads)))))"),
        _module("(loop/recur ((pads 5)) :on-exhausted (+ pads 1) :max 2 (if (check pads) (done pads) (continue (step pads))))"),
    ),
    "effect_in_init": (
        _module("(loop/recur :max 3 :state (seed 1) (fn (s) (done (step s))))"),
        _module("(loop/recur ((s (seed 1))) :max 3 (done (step s)))"),
    ),
    "effect_in_max": (
        _module("(loop/recur :max (budget 3) :state 0 :on-exhausted s (fn (s) (if (check s) (done s) (continue (step s)))))"),
        _module("(loop/recur ((s 0)) :max (budget 3) :on-exhausted s (if (check s) (done s) (continue (step s))))"),
    ),
    "effects_in_state_then_max": (
        _module("(loop/recur :state (seed 0) :max (budget 3) :on-exhausted s (fn (s) (if (check s) (done s) (continue (step s)))))"),
        _module("(loop/recur ((s (seed 0))) :max (budget 3) :on-exhausted s (if (check s) (done s) (continue (step s))))"),
    ),
    "variable_max": (
        _module("(loop/recur :max limit :state 0 :on-exhausted s (fn (s) (if (check s) (done s) (continue (step s)))))", params="(limit Int)"),
        _module("(loop/recur ((s 0)) :max limit :on-exhausted s (if (check s) (done s) (continue (step s))))", params="(limit Int)"),
    ),
    "nested_loops": (
        _module("""(loop/recur :max 2 :state 0 :on-exhausted outer
              (fn (outer) (if (check outer) (done outer) (continue (loop/recur :max 3 :state (seed outer) :on-exhausted inner
                (fn (inner) (if (check inner) (done (+ inner outer)) (continue (step inner)))))))))"""),
        _module("""(loop/recur ((outer 0)) :max 2 :on-exhausted outer
              (if (check outer) (done outer) (continue (loop/recur ((inner (seed outer))) :max 3 :on-exhausted inner
                (if (check inner) (done (+ inner outer)) (continue (step inner)))))))"""),
    ),
    "inside_procedure": (
        _module("(grow 4)", extra="""(defproc grow ((limit Int)) -> Int
              (loop/recur :max limit :state 0 :on-exhausted k (fn (k) (if (check k) (done k) (continue (step k))))))"""),
        _module("(grow 4)", extra="""(defproc grow ((limit Int)) -> Int
              (loop/recur ((k 0)) :max limit :on-exhausted k (if (check k) (done k) (continue (step k)))))"""),
    ),
    "inside_map_body": (
        _module("(list/length (list/map-effect ((x (list 1 2))) :max 2 (grow x)))", extra="""(defproc grow ((x Int)) -> Int
              (loop/recur :max 2 :state x :on-exhausted k (fn (k) (if (< k 3) (continue (+ k 1)) (done (step k))))))"""),
        _module("(list/length (list/map-effect ((x (list 1 2))) :max 2 (grow x)))", extra="""(defproc grow ((x Int)) -> Int
              (loop/recur ((k x)) :max 2 :on-exhausted k (if (< k 3) (continue (+ k 1)) (done (step k)))))"""),
    ),
    "inside_match": (
        _module("""(match (variant Shape CIRCLE :r 2)
              ((CIRCLE c) (loop/recur :max c.r :state 0 :on-exhausted k (fn (k) (if (check k) (done k) (continue (step k))))))
              ((SQUARE s) 0))""", extra="(defunion Shape (CIRCLE (r Int)) (SQUARE (side Int)))"),
        _module("""(match (variant Shape CIRCLE :r 2)
              ((CIRCLE c) (loop/recur ((k 0)) :max c.r :on-exhausted k (if (check k) (done k) (continue (step k)))))
              ((SQUARE s) 0))""", extra="(defunion Shape (CIRCLE (r Int)) (SQUARE (side Int)))"),
    ),
    "inside_let_star": (
        _module("(let* ((start (seed 0))) (loop/recur :max 2 :state start (fn (v) (done (step v)))))"),
        _module("(let* ((start (seed 0))) (loop/recur ((v start)) :max 2 (done (step v))))"),
    ),
}


def _program(root: Path, source: str) -> ClosedProgram:
    return ClosedProgram.from_artifact(build(root, source, boundaries=BOUNDARIES).artifact())


@pytest.mark.parametrize("case", sorted(CASES))
def test_binder_form_builds_the_fn_form_program(tmp_path: Path, case: str) -> None:
    fn_source, binder_source = CASES[case]
    fn_program = _program(tmp_path / "fn", fn_source)
    binder_program = _program(tmp_path / "binder", binder_source)

    assert (binder_program.digest, binder_program.sites) == (fn_program.digest, fn_program.sites)


# Inside a `defmacro` template (B1 and N4 of the I2a reviews): the initial state is read in the
# enclosing scope and the state name binds in the body and `:on-exhausted`, in both forms, so the two
# templates expand to one program.
SEEDED_FN = "(let* ((tmp (seed x))) (loop/recur :max 2 :state tmp :on-exhausted s (fn (s) (if (check s) (done s) (continue (step s))))))"
SEEDED_BINDER = "(let* ((tmp (seed x))) (loop/recur ((s tmp)) :max 2 :on-exhausted s (if (check s) (done s) (continue (step s)))))"
NESTED_FN_TEMPLATE = ("(let* ((tmp (seed x))) (loop/recur :max 2 :state tmp :on-exhausted s (fn (s) (if (check s) (done s) "
                      "(continue (loop/recur :max 1 :state (+ s tmp) :on-exhausted u (fn (u) (done (step u)))))))))")
NESTED_BINDER_TEMPLATE = ("(let* ((tmp (seed x))) (loop/recur ((s tmp)) :max 2 :on-exhausted s (if (check s) (done s) "
                          "(continue (loop/recur ((u (+ s tmp))) :max 1 :on-exhausted u (done (step u)))))))")


def _macro_module(template: str, body: str, *, outer: bool = False) -> str:
    extra = f"(defmacro grow (x) {template})"
    if outer:
        extra += " (defmacro twice (y) (let* ((tmp (budget y))) (+ tmp (grow tmp))))"
    return _module(body, extra=extra)


MACRO_CASES = {
    "template_local_initial_state": (SEEDED_FN, SEEDED_BINDER, "(grow 1)", False),
    "caller_name_equal_to_template_name": (SEEDED_FN, SEEDED_BINDER, "(let* ((tmp (budget 100))) (+ tmp (grow 1)))", False),
    "caller_name_equal_to_binder_name": (SEEDED_FN, SEEDED_BINDER, "(let* ((s (budget 7))) (+ s (grow 1)))", False),
    # A nested loop expanded straight into an operand, `(+ tmp (grow 1))`, is a compiler_defect in both
    # forms on `main` too (KeyError on the inner binder); bound by `let*`, it builds.
    "nested_loops_in_template": (NESTED_FN_TEMPLATE, NESTED_BINDER_TEMPLATE, "(let* ((tmp (budget 3)) (r (grow 1))) (+ tmp r))", False),
    "template_used_by_another_template": (SEEDED_FN, SEEDED_BINDER, "(twice 2)", True),
}


@pytest.mark.parametrize("case", sorted(MACRO_CASES))
def test_binder_form_in_a_macro_template_builds_the_fn_form_program(tmp_path: Path, case: str) -> None:
    fn_template, binder_template, body, outer = MACRO_CASES[case]
    fn_program = _program(tmp_path / "fn", _macro_module(fn_template, body, outer=outer))
    binder_program = _program(tmp_path / "binder", _macro_module(binder_template, body, outer=outer))

    assert (binder_program.digest, binder_program.sites) == (fn_program.digest, fn_program.sites)


def test_template_cond_test_is_hygienic(tmp_path: Path) -> None:
    """A `cond` clause test is the first item of its clause, as the binder pair is (same root cause)."""
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program

    extra = "(defmacro pick (x) (let* ((tmp 5)) (cond ((= tmp 5) 1) (true 0))))"
    program = _program(tmp_path, _module("(let* ((tmp 100)) (pick 1))", extra=extra))

    assert evaluate_closed_program(program, {}).value == 1


def test_binder_form_runs_the_source_before_max(tmp_path: Path) -> None:
    """With an effect in both, the fn form written `:max` first runs the budget first; the binder form the seed."""
    fn_program = _program(tmp_path / "fn", _module(
        "(loop/recur :max (budget 3) :state (seed 0) :on-exhausted s (fn (s) (if (check s) (done s) (continue (step s)))))"))
    binder_program = _program(tmp_path / "binder", _module(
        "(loop/recur ((s (seed 0))) :max (budget 3) :on-exhausted s (if (check s) (done s) (continue (step s))))"))
    state_first = _program(tmp_path / "state-first", _module(
        "(loop/recur :state (seed 0) :max (budget 3) :on-exhausted s (fn (s) (if (check s) (done s) (continue (step s)))))"))

    assert binder_program.digest != fn_program.digest
    assert binder_program.digest == state_first.digest


REFUSALS = {
    "binder_and_state": (
        "(loop/recur ((s 0)) :max 3 :state 0 (done s))", "loop_recur_contract_invalid", "drop `:state`",
    ),
    "binder_and_fn": (
        "(loop/recur ((s 0)) :max 3 (fn (s) (done s)))", "loop_recur_fn_invalid", "without `fn`",
    ),
    "two_binders": (
        "(loop/recur ((s 0) (t 1)) :max 3 (done s))", "loop_recur_contract_invalid", "one binder",
    ),
    "binder_not_a_pair": (
        "(loop/recur (s 0) :max 3 (done s))", "loop_recur_contract_invalid", "((name initial-state))",
    ),
    "binder_name_not_a_symbol": (
        "(loop/recur ((1 0)) :max 3 (done 1))", "loop_recur_contract_invalid", "((name initial-state))",
    ),
    "binder_without_max": (
        "(loop/recur ((s 0)) (done s))", "loop_recur_contract_invalid", "(loop/recur ((state init)) :max n body)",
    ),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_binder_form_refuses_mixtures(tmp_path: Path, case: str) -> None:
    body, code, named = REFUSALS[case]
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build(tmp_path, _module(body), boundaries=BOUNDARIES)

    (diagnostic,) = excinfo.value.diagnostics
    assert (diagnostic.code, named in diagnostic.message) == (code, True)


RESUME_FN = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule count) (export run)
  (defworkflow run () -> Int
    (loop/recur :max 4 :state 0 :on-exhausted n
      (fn (n) (if (< 2 n) (done n)
        (continue (command-result step :argv ("python" "step.py" n) :returns Int)))))))
'''
RESUME_BINDER = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule count) (export run)
  (defworkflow run () -> Int
    (loop/recur ((n 0)) :max 4 :on-exhausted n
      (if (< 2 n) (done n)
        (continue (command-result step :argv ("python" "step.py" n) :returns Int))))))
'''
STEP_PY = '''import os, sys
from pathlib import Path
with open("calls.txt", "a") as log:
    log.write(sys.argv[1] + "\\n")
if sys.argv[1] == "1" and Path("fail").exists():
    sys.exit("step 1 fails while ./fail exists")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(str(int(sys.argv[1]) + 1))
'''


def _orchestrator(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1]), "PYTHONDONTWRITEBYTECODE": "1",
           "PATH": closed_path()}
    return subprocess.run([sys.executable, "-m", "orchestrator", *args], cwd=root, env=env,
                          capture_output=True, text=True, check=False, timeout=120)


def test_run_started_under_fn_form_resumes_from_binder_source(tmp_path: Path) -> None:
    (tmp_path / "count.orc").write_text(RESUME_FN, encoding="utf-8")
    (tmp_path / "step.py").write_text(STEP_PY, encoding="utf-8")
    (tmp_path / "commands.json").write_text(
        json.dumps({"step": {"stable_command": ["python", "step.py"], "closure": ["step.py"]}}), encoding="utf-8")
    (tmp_path / "fail").write_text("", encoding="utf-8")
    failed = _orchestrator(tmp_path, "run", "count.orc")
    assert failed.returncode == 1, failed.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()

    (tmp_path / "count.orc").write_text(RESUME_BINDER, encoding="utf-8")
    (tmp_path / "fail").unlink()
    resumed = _orchestrator(tmp_path, "resume", run_root.name)

    calls = (tmp_path / "calls.txt").read_text(encoding="utf-8").split()
    assert (resumed.returncode, resumed.stdout.splitlines()[-1:], calls) == (0, ["3"], ["0", "1", "1", "2"]), resumed.stderr


# A frozen Python build compares its pin with the hash of the emitted `.orc` text, so the emitter
# keeps the `fn` form until the release that removes it (surface coherence I2b). This pins the text
# `main`'s emitter wrote for this program when I2a was made: an emitter change fails the text
# assertion here, as it would fail `python_frozen_changed` for a pin made before it.
PINNED_PYTHON_LOOP = '''from __future__ import annotations
from orchestrator.py import *


@workflow
def run() -> int:
    return loop(state=0, max=3,
        body=lambda n: when(n == 2, then=lambda: done(n), else_=lambda: cont(n + 1)),
        on_exhausted=lambda n: n)
'''
PINNED_EMITTED_TEXT = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule py/count)
  (import std/host :as _import0)
  (export run)
  (defworkflow run () -> Int
    (let* ((_loop (loop/recur :max 3 :state 0 :on-exhausted (let* ((_exhausted0 _loop0)) _exhausted0) (fn (_loop0) (if (= _loop0 2) (done _loop0) (continue (+ _loop0 1)))))))
      _loop))
)
'''


def test_python_frontend_keeps_the_fn_form_text_a_frozen_pin_hashes(tmp_path: Path) -> None:
    from orchestrator.py.build import build as build_python

    source = tmp_path / "count.py"
    source.write_text(PINNED_PYTHON_LOOP, encoding="utf-8")
    pinned = build_python(source, workspace_root=tmp_path)
    (emitted,) = pinned.snapshot_path.glob("generated/**/count.orc")

    frozen = build_python(source, workspace_root=tmp_path, frozen=True)

    assert (emitted.read_text(encoding="utf-8"), frozen.snapshot_path) == (PINNED_EMITTED_TEXT, pinned.snapshot_path)
