"""Task 0b of the staged-workflow authoring plan: the defects the seeds meet (design §2, D1 to D5).

Programs are workflow `run` of module `m` at target 2.40, run through the public command line beside the
stand-in command `c LABEL VALUE`, which logs LABEL and returns VALUE (`tests/workflow_lisp_cli_run_helpers.py`).
A program these fixes admit is compared with its `let*`-bound spelling, which built before them. The kill
tests stop a run inside one command, kill its process group and resume it; the resumed run ends with the
value and the committed effect identities of a clean run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from tests.agent_session_shims import closed_path
from tests.workflow_lisp_cli_run_helpers import A_3, COMMAND, REPO, U, command_log, run_workflow
from tests.workflow_lisp_closed_program_helpers import build_outcome

VERDICT = "(defunion Verdict (MET (evidence List[String])) (NOT_MET (reasons List[String])))"
HAS = "(defunion V (HAS (xs List[Int])) (NO (k Int)))"


def outcome(root: Path, run: str, *definitions: str) -> tuple:
    """The public build of `run` beside `definitions`: `("builds",)`, `("refused", codes...)` or a crash."""
    source = "\n  ".join((*definitions, f"(defworkflow run {run})"))
    (root / "m.orc").write_text(f'(workflow-lisp (:language "0.1") (:target-dsl "2.40")\n  (defmodule m) '
                                f"(export run)\n  {source})\n", encoding="utf-8")
    (root / "commands.json").write_text(json.dumps({"c": {"stable_command": ["python", "c.py"], "closure": ["c.py"]}}))
    (root / "c.py").write_text("", encoding="utf-8")
    return build_outcome(lambda: build_closed_program_bundle(FrontendBuildRequest(
        source_path=root / "m.orc", source_roots=(root,), entry_workflow="m::run",
        command_boundaries_path=root / "commands.json", workspace_root=root)))


def same_run(tmp_path: Path, run: str, bound: str, *inputs: str, definitions: tuple[str, ...] = (U,)):
    """The value and command log of `run` and of its `let*`-bound spelling `bound`."""
    (tmp_path / "run").mkdir()
    (tmp_path / "bound").mkdir()
    return (run_workflow(tmp_path / "run", run, *inputs, definitions=definitions),
            run_workflow(tmp_path / "bound", bound, *inputs, definitions=definitions))


# ---------------------------------------------------------------------------------------------
# D1: a `list/map` whose body is a `match`, in a condition inside a loop body. The map's binder was not in
# the loop's command scope, so a `let*` the condition normalisation writes into the map body could not be typed.

MAP = "(list/map ((v vs)) (match v ((A a) (> s a.n)) ((B b) true)))"
HEAD = "(or-else (list/head MAP) false)"
D1_RUN = "((u U)) -> Int (let* ((vs (list u u))) (loop/recur ((s 0)) :max 6 :on-exhausted 99 BODY))"
D1_CONDITIONS = {
    "if": ("(if HEAD (done s) (continue (+ s 1)))", "(if ok (done s) (continue (+ s 1)))"),
    "cond": ("(cond (HEAD (done s)) (else (continue (+ s 1))))", "(cond (ok (done s)) (else (continue (+ s 1))))"),
    "and": ("(if (and (> s 0) HEAD) (done s) (continue (+ s 1)))",
            "(if (and (> s 0) ok) (done s) (continue (+ s 1)))"),
}


def d1(body: str) -> str:
    return D1_RUN.replace("BODY", body).replace("HEAD", HEAD).replace("MAP", MAP)


@pytest.mark.parametrize("form", sorted(D1_CONDITIONS))
def test_map_with_a_match_body_is_a_condition_inside_a_loop(tmp_path, form):
    written, bound = D1_CONDITIONS[form]

    ran, ran_bound = same_run(tmp_path, d1(written), d1(f"(let* ((ok HEAD)) {bound})"), f"u={A_3}")

    assert ran == ran_bound == (4, [])


def test_let_in_a_map_body_reading_the_binder_inside_a_loop(tmp_path):
    body = "(done (list/length (list/map ((v vs)) (let* ((k (match v ((A a) a.n) ((B b) 0)))) (+ k s)))))"

    assert run_workflow(tmp_path, D1_RUN.replace("BODY", body), f"u={A_3}") == (2, [])


def test_local_capturing_the_binder_in_a_map_body_inside_a_loop(tmp_path):
    """The map's binder is in the loop's command scope from the start, so a local that captures it is typed
    there too. Compared with a procedure the binder is passed to."""
    condition = D1_CONDITIONS["if"][0].replace("HEAD", "(or-else (list/head (list/map ((v vs)) CALL)) false)")
    captures = "(let-proc ((g ((k Int)) -> Bool (match v ((A a) (> k a.n)) ((B b) true)))) (g s))"
    procedure = "(defproc gp ((w U) (k Int)) -> Bool (match w ((A a) (> k a.n)) ((B b) true)))"

    ran, ran_passed = same_run(tmp_path, D1_RUN.replace("BODY", condition.replace("CALL", captures)),
                               D1_RUN.replace("BODY", condition.replace("CALL", "(gp v s)")), f"u={A_3}",
                               definitions=(U, procedure))

    assert ran == ran_passed == (4, [])


# ---------------------------------------------------------------------------------------------
# D2 (finding T8.1 of the corpus rule ledger): a `match` subject written with a list in it. The `match` kept
# the subject as written, whose lists carry no item types, so elaboration could not lower it; it now carries
# the typechecked subject, as the same subject bound with `let*` does.

@pytest.mark.parametrize(("subject", "wanted"), [
    ('(variant Verdict MET :evidence (list "e"))', []),
    ('(variant Verdict NOT_MET :reasons (list "r" "s"))', ["r", "s"]),
])
def test_empty_list_in_a_match_arm_is_typed_by_the_workflow_result(tmp_path, subject, wanted):
    run = f"() -> List[String] (match {subject} ((MET m) (list)) ((NOT_MET g) g.reasons))"

    assert run_workflow(tmp_path, run, definitions=(VERDICT,)) == (wanted, [])


# A list in the call of a `let-proc` local in a subject was lowered from the local's typecheck rewrite, so such
# a subject built as written; it still does, also beside an `and` or an `or` (B1 of the review of Task 0b).
LOCAL_CALL = "(let-proc ((f ((ys List[Int])) -> V (variant V HAS :xs ys))) (f (list 1)))"


@pytest.mark.parametrize("condition", ["(and (> n 0) (> n -1))", "(or (> n 5) (> n 0))"])
def test_list_in_a_local_call_in_a_match_subject_beside_an_and_or_an_or(tmp_path, condition):
    subject = f"(if {condition} {LOCAL_CALL} (variant V NO :k 0))"
    arms = "((HAS h) (list/length h.xs)) ((NO o) o.k)"

    ran, ran_bound = same_run(tmp_path, f"((n Int)) -> Int (match {subject} {arms})",
                              f"((n Int)) -> Int (let* ((w {subject})) (match w {arms}))", "n=1",
                              definitions=(HAS,))

    assert ran == ran_bound == (1, [])


@pytest.mark.parametrize("subject", ["(variant V HAS :xs (list 1 2))", "(variant V HAS :xs (list))",
                                     "(variant V NO :k (list/length (list 1 2 3)))"])
def test_match_subject_with_a_list_in_it_runs_like_its_let_bound_spelling(tmp_path, subject):
    arms = "((HAS h) (list/length h.xs)) ((NO o) (+ o.k 10))"

    ran, ran_bound = same_run(tmp_path, f"() -> Int (match {subject} {arms})",
                              f"() -> Int (let* ((w {subject})) (match w {arms}))", definitions=(HAS,))

    assert ran == ran_bound


# ---------------------------------------------------------------------------------------------
# D3: a generic procedure called in a serial `list/map-effect` body. The body is typed once as written and
# again inside the map's loop, where the call already names the specialization requested by the first.

KEEP = ('(defproc keep :forall (T) ((x T)) -> T '
        '(let* ((seen (command-result c :argv ("python" "c.py" x "1") :returns Int))) x))')
MAP_KEEP = '(list/map-effect ((s (list "a" "b"))) :max 4 CALL)'


@pytest.mark.parametrize(("call", "log"), [("(keep s)", ["a", "b"]), ("(keep (keep s))", ["a", "a", "b", "b"])])
def test_generic_procedure_called_in_a_map_body_runs_once_per_item(tmp_path, call, log):
    run = "() -> List[String] " + MAP_KEEP.replace("CALL", call)

    assert run_workflow(tmp_path, run, definitions=(KEEP,)) == (["a", "b"], log)


def test_generic_procedure_in_a_parallel_map_body_runs_once_per_item(tmp_path):
    for workspace in ("a", "b"):
        (tmp_path / workspace).mkdir()
        (tmp_path / workspace / "c.py").write_text(COMMAND, encoding="utf-8")
    run = '() -> List[String] (list/map-effect ((s (list "a" "b"))) :max 4 :parallel 2 :workspace s (keep s))'

    value, _log = run_workflow(tmp_path, run, definitions=(KEEP,))

    assert (value, command_log(tmp_path / "a"), command_log(tmp_path / "b")) == (["a", "b"], ["a"], ["b"])


def test_generic_procedure_in_a_local_called_in_a_map_body_runs_once_per_item(tmp_path):
    run = "() -> List[String] (let-proc ((h ((t String)) -> String (keep t))) MAP)".replace(
        "MAP", MAP_KEEP.replace("CALL", "(h s)"))

    assert run_workflow(tmp_path, run, definitions=(KEEP,)) == (["a", "b"], ["a", "b"])


# Only the second typing of a serial map's own loop takes a call already renamed to its specialization: a
# local that captures a name bound to a generic call is refused as before (M1 of the review of Task 0b; row
# let-proc-generic-capture of the defect record).
KEEP_INT = ('(defproc keepg :forall (T) ((x T)) -> T '
            '(let* ((seen (command-result c :argv ("python" "c.py" "g" "1") :returns Int))) x))')


@pytest.mark.parametrize("consumer", ["(h 1)", "(+ (h 1) (h 2))",
                                      "(list/length (list/map-effect ((y (list 1 2))) :max 2 (h y)))"])
def test_local_capturing_a_generic_call_result_is_refused_as_before(tmp_path, consumer):
    run = f"((n Int)) -> Int (let* ((a (keepg 5))) (let-proc ((h ((x Int)) -> Int (+ a x))) {consumer}))"

    assert outcome(tmp_path, run, KEEP_INT) == ("refused", "procedure_call_unknown")


# ---------------------------------------------------------------------------------------------
# D4: pinned since surface coherence C1.

@pytest.mark.parametrize("reference", ["(proc-ref inc)", "(bind-proc (proc-ref pick) :n 1)"])
def test_reference_chosen_by_if_refuses_with_one_diagnostic(tmp_path, reference):
    run = f"((n Int)) -> Int (let* ((g (if (> n 0) {reference} {reference}))) (g 1))"

    assert outcome(tmp_path, run, "(defproc inc ((v Int)) -> Int (+ v 1))",
                   "(defproc pick :forall (T) ((n Int) (x T)) -> T x)") == ("refused", "proc_ref_literal_required")


# ---------------------------------------------------------------------------------------------
# D5: a `bind-proc` over a parameter of a pure procedure, passed on to a `ProcRef` parameter. The procedure
# is expanded where it is called and its parameters renamed; the reference over the renamed parameter
# matches no specialization made from the definition. Not fixed (the bound-reference path): a named
# refusal that says to bind the reference in the caller.

D5_PROCEDURES = ("(defproc add ((n Int) (x Int)) -> Int (+ n x))",
                 "(defproc apply1 ((f ProcRef[Int -> Int]) (v Int)) -> Int (f v))")


@pytest.mark.parametrize("body", ["(apply1 (bind-proc (proc-ref add) :n k) 1)",
                                  "(let* ((g (bind-proc (proc-ref add) :n k))) (apply1 g 1))",
                                  "(apply1 (bind-proc (proc-ref add) :n (+ k 0)) 1)"])
def test_bound_reference_over_a_parameter_passed_on(tmp_path, body):
    outer = f"(defproc outer ((k Int)) -> Int {body})"

    assert outcome(tmp_path, "() -> Int (outer 2)", *D5_PROCEDURES, outer) == (
        "refused", "proc_ref_binding_parameter_unsupported")


def test_reference_bound_in_the_caller_and_passed_on_runs(tmp_path):
    outer = "(defproc outer ((g ProcRef[Int -> Int])) -> Int (apply1 g 1))"
    run = "() -> Int (let* ((k 2) (g (bind-proc (proc-ref add) :n k))) (outer g))"

    assert run_workflow(tmp_path, run, definitions=(*D5_PROCEDURES, outer)) == (3, [])


# ---------------------------------------------------------------------------------------------
# One shape of each of D1, D2 and D3 with command steps, killed inside a command and resumed.

STOPPING = '''import os, sys, time
from pathlib import Path
open("log.txt", "a").write(sys.argv[1] + "\\n")
stop = Path("stop-at")
if stop.exists() and stop.read_text() == sys.argv[1]:
    stop.unlink()
    Path("stopped").write_text(sys.argv[1])
    time.sleep(600)
open(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"], "w").write(sys.argv[2])
'''


def _orchestrator(root: Path, *args: str) -> list[str]:
    return [sys.executable, "-B", "-m", "orchestrator", *args]


def _install(root: Path, run: str, definitions: tuple[str, ...]) -> list[str]:
    root.mkdir()
    forms = "\n  ".join((*definitions, f"(defworkflow run {run})"))
    (root / "m.orc").write_text(f'(workflow-lisp (:language "0.1") (:target-dsl "2.40")\n  (defmodule m) '
                                f"(export run)\n  {forms})\n", encoding="utf-8")
    (root / "c.py").write_text(STOPPING, encoding="utf-8")
    (root / "commands.json").write_text(json.dumps({"c": {"stable_command": ["python", "c.py"], "closure": ["c.py"]}}))
    return _orchestrator(root, "run", "m.orc", "--entry-workflow", "m::run", "--source-root", ".",
                         "--command-boundaries-file", "commands.json")


def _env() -> dict[str, str]:
    return {**os.environ, "PATH": closed_path(REPO / "experiments" / "thread_m" / "no_provider"),
            "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}


def _finished(root: Path, done: subprocess.CompletedProcess) -> tuple[object, list[str]]:
    """The value a finished run printed and the identities of its committed effects."""
    assert done.returncode == 0, done.stderr
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    records = [json.loads(line) for line in (run_root / "memo.jsonl").read_text(encoding="utf-8").splitlines()]
    return json.loads(done.stdout.splitlines()[-1]), sorted(r["identity"] for r in records if r["record"] == "committed")


def _killed_then_resumed(root: Path, argv: list[str], stop_label: str) -> tuple[object, list[str]]:
    (root / "stop-at").write_text(stop_label, encoding="utf-8")
    process = subprocess.Popen(argv, cwd=root, env=_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    deadline = time.monotonic() + 120
    while not (root / "stopped").exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    os.killpg(process.pid, signal.SIGKILL)
    _out, err = process.communicate(timeout=30)
    assert (root / "stopped").exists(), err.decode(errors="replace")
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    resumed = subprocess.run(_orchestrator(root, "resume", run_root.name), cwd=root, env=_env(),
                             capture_output=True, text=True, check=False)
    return _finished(root, resumed)


KILLED_SHAPES = {
    "d1": (d1("(let* ((r (command-result c :argv (\"python\" \"c.py\" s s) :returns Int))) "
              "(if HEAD (done (+ s r)) (continue (+ s 1))))"), (U,), (f"u={A_3}",), "2"),
    "d2": ("() -> List[Int] (match (variant V HAS :xs (list 1 2)) ((HAS h) (list/map-effect ((x h.xs)) :max 2 "
           '(command-result c :argv ("python" "c.py" x x) :returns Int))) ((NO o) (list)))', (HAS,), (), "2"),
    "d3": ("() -> List[String] " + MAP_KEEP.replace("CALL", "(keep s)"), (KEEP,), (), "b"),
}


@pytest.mark.parametrize("shape", sorted(KILLED_SHAPES))
def test_run_killed_inside_a_command_resumes_to_the_clean_run(tmp_path, shape):
    run, definitions, inputs, stop_label = KILLED_SHAPES[shape]
    flags = [flag for item in inputs for flag in ("--input", item)]
    clean_argv = _install(tmp_path / "clean", run, definitions) + flags
    killed_argv = _install(tmp_path / "killed", run, definitions) + flags

    clean = _finished(tmp_path / "clean", subprocess.run(clean_argv, cwd=tmp_path / "clean", env=_env(),
                                                         capture_output=True, text=True, check=False))

    assert _killed_then_resumed(tmp_path / "killed", killed_argv, stop_label) == clean
