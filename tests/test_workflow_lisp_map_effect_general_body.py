"""Surface coherence I1: a `list/map-effect` body is any expression, and a serial `:max` any `Int` expression.

A body that holds a run reference stays exactly one call; a parallel map's `:max` and `:parallel` stay
literals; the cap behaviour does not change. Every run goes through the public command line with the
stand-in `STEP` of `workflow_evaluated_parallel_kill_helpers` (it logs `(item, stage)` per dispatch); no
provider is called.
"""

from __future__ import annotations

from collections import Counter
import json
import shutil
from pathlib import Path

import pytest

from tests.test_cli_run_output import cli, effect_rows
from tests.workflow_evaluated_parallel_kill_helpers import Batch, committed
from tests.workflow_evaluated_recovery_helpers import resume

FIXTURE = Path(__file__).parent / "fixtures" / "map_effect_cap_pre_change"
ITEMS = ("a", "b", "c")
PROGRAM = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defunion Pick (ONE (n Int)) (TWO))
  (defproc fetch ((repo String)) -> Int
    (command-result step :argv ("python" "step.py" repo "first") :returns Int))
  (defworkflow run ((n Int)) -> List[Int]
    (list/map-effect ((repo (list "a" "b" "c"))) OPTIONS
      BODY)))
'''
FIRST = '(command-result step :argv ("python" "step.py" repo "first") :returns Int)'


def second(after: str) -> str:
    return f'(command-result step :argv ("python" "step.py" repo "second" {after}) :returns Int)'


# shape -> (body, the stages each item dispatches in order, the map's value)
SHAPES = {
    "let_two_commands": (
        f"(let* ((first {FIRST}) (second {second('first')})) second)",
        {"a": ["first", "second"], "b": ["first", "second"], "c": ["first", "second"]}, [2, 21, 4]),
    "if_between_effects": (
        f'(if (= repo "b") (let* ((f {FIRST})) {second("f")}) {FIRST})',
        {"a": ["first"], "b": ["first", "second"], "c": ["first"]}, [1, 21, 3]),
    "match": (
        f'(match (if (= repo "b") (variant Pick TWO) (variant Pick ONE :n 0)) ((ONE o) {FIRST}) ((TWO t) {second(19)}))',
        {"a": ["first"], "b": ["second"], "c": ["first"]}, [1, 20, 3]),
    "nested_map": (
        '(list/length (list/map-effect ((stage (list "first" "first"))) :max 2 '
        '(command-result step :argv ("python" "step.py" repo stage) :returns Int)))',
        {"a": ["first", "first"], "b": ["first", "first"], "c": ["first", "first"]}, [2, 2, 2]),
    "procedure_call_plus_command": (
        f"(let* ((f (fetch repo))) {second('f')})",
        {"a": ["first", "second"], "b": ["first", "second"], "c": ["first", "second"]}, [2, 21, 4]),
}
MODES = {"serial": ":max 3", "parallel": ":max 3 :parallel 2 :workspace repo"}


def program(body: str, options: str) -> str:
    return PROGRAM.replace("OPTIONS", options).replace("BODY", body)


def batch(tmp_path: Path, body: str, mode: str = "serial", options: str | None = None) -> Batch:
    """A workspace for `body`. A serial map runs its commands in the workspace root, a parallel one in
    the item's directory; only the parallel workspace has no `step.py` at its root."""
    made = Batch(tmp_path, source=program(body, options or MODES[mode]), items=ITEMS)
    if mode == "serial":
        shutil.copy(made.ws / "a" / "step.py", made.ws / "step.py")
    return made


def stages_by_item(made: Batch) -> dict[str, list[str]]:
    by_item: dict[str, list[str]] = {}
    for item, stage in made.dispatches():
        by_item.setdefault(item, []).append(stage)
    return by_item


def report_steps(made: Batch) -> list[dict]:
    result = cli(made.ws, "report", "--run-id", made.run_root().name, "--format", "json")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["steps"]


@pytest.mark.parametrize("mode", sorted(MODES))
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_body_of_several_effects_runs_each_in_written_order(tmp_path, shape, mode):
    body, stages, value = SHAPES[shape]
    made = batch(tmp_path, body, mode)

    result = made.run("--input", "n=3")

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == value
    assert stages_by_item(made) == stages


@pytest.mark.parametrize("mode", sorted(MODES))
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_effect_of_every_item_has_its_own_identity_and_report_row(tmp_path, shape, mode):
    body, _stages, _value = SHAPES[shape]
    made = batch(tmp_path, body, mode)
    assert made.run("--input", "n=3").returncode == 0

    identities = [row["identity"] for row in committed(made.snapshot())]
    steps = report_steps(made)

    assert len(set(identities)) == len(identities) == len(made.dispatches())
    assert sorted((step["identity"], step["status"]) for step in steps) == sorted(
        (identity, "completed") for identity in identities)


def test_parallel_item_runs_every_effect_in_its_item_workspace(tmp_path):
    made = batch(tmp_path, SHAPES["let_two_commands"][0], "parallel")

    result = made.run("--input", "n=3")

    # `python step.py` resolves only in an item's directory: the workspace root holds no `step.py`.
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (made.ws / "step.py").exists()
    assert sorted({row["identity"].split(" / ")[1] for row in committed(made.snapshot())}) == [
        f"par-map:repo[{index}]" for index in range(3)]


@pytest.mark.parametrize("mode", sorted(MODES))
def test_kill_between_two_effects_of_one_item_reuses_the_first(tmp_path, mode):
    made = batch(tmp_path, SHAPES["let_two_commands"][0], mode)
    made.kill((("b", "second"),), extra=("--input", "n=3"))
    before = committed(made.snapshot())

    result = resume(made.ws, made.run_root().name)

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == [2, 21, 4]
    assert committed(made.snapshot())[:len(before)] == before
    counts = Counter(made.dispatches())
    assert (counts[("b", "first")], counts[("b", "second")]) == (1, 2)
    if mode == "serial":
        assert counts == {("a", "first"): 1, ("a", "second"): 1, ("b", "first"): 1, ("b", "second"): 2,
                          ("c", "first"): 1, ("c", "second"): 1}


# ---- the cap, and a computed serial `:max` -------------------------------------------------------------------------

def run_serial(tmp_path: Path, options: str, n: int, body: str = FIRST):
    made = batch(tmp_path, body, "serial", options)
    return made, made.run("--input", f"n={n}")


@pytest.mark.parametrize("options", [":max 2", ":max n", ":max (- n 1)"])
def test_serial_map_longer_than_max_runs_max_items_then_fails(tmp_path, options):
    made, result = run_serial(tmp_path, options, 3 if "-" in options else 2)

    assert result.returncode != 0
    assert "[list_map_effect_cap_exceeded]" in result.stderr
    assert "list has 3 items, more than its `:max` of 2" in result.stderr
    assert made.dispatches() == [("a", "first"), ("b", "first")]


def test_parallel_map_longer_than_max_fails_before_any_item(tmp_path):
    made = batch(tmp_path, FIRST, "parallel", ":max 2 :parallel 2 :workspace repo")
    result = made.run("--input", "n=3")

    assert "[list_map_effect_cap_exceeded]" in result.stderr
    assert made.dispatches() == []


@pytest.mark.parametrize("options", [":max n", ":max (+ n 1)"])
def test_computed_serial_max_runs_every_item(tmp_path, options):
    made, result = run_serial(tmp_path, options, 3)

    assert result.returncode == 0, result.stderr
    assert made.dispatches() == [(item, "first") for item in ITEMS]


def test_effect_in_serial_max_runs_once_before_the_first_item(tmp_path):
    options = ':max (command-result step :argv ("python" "step.py" "c" "first") :returns Int)'
    made, result = run_serial(tmp_path, options, 0)

    assert result.returncode == 0, result.stderr
    assert made.dispatches() == [("c", "first"), *((item, "first") for item in ITEMS)]


def test_serial_max_from_a_procedure_parameter(tmp_path):
    source = program(FIRST, ":max n").replace("(defworkflow run ((n Int)) -> List[Int]", "(defproc each ((n Int)) -> List[Int]")
    source = source.rstrip()[:-1] + "\n  (defworkflow run ((n Int)) -> List[Int] (each n)))\n"
    made = Batch(tmp_path, source=source, items=ITEMS)
    shutil.copy(made.ws / "a" / "step.py", made.ws / "step.py")

    result = made.run("--input", "n=3")

    assert result.returncode == 0, result.stdout + result.stderr
    assert made.dispatches() == [(item, "first") for item in ITEMS]


@pytest.mark.parametrize("n", [0, -2])
def test_non_positive_computed_serial_max_fails_before_any_item(tmp_path, n):
    made, result = run_serial(tmp_path, ":max n", n)

    assert "[list_map_effect_cap_exceeded]" in result.stderr
    assert f"`:max` evaluated to {n}, which is below 1" in result.stderr
    assert made.dispatches() == []


@pytest.mark.parametrize("options", [":max 1", ":max n", ":max (list/length xs)"])
def test_serial_map_over_an_empty_list_succeeds_whatever_its_max(tmp_path, options):
    """As a literal `:max 1` over an empty list: no item is needed, so a computed `:max` below 1 does not fail."""
    source = program(FIRST, options).replace('(list "a" "b" "c")', "xs").replace(
        "((n Int)) -> List[Int]", "((n Int) (xs List[String])) -> List[Int]")
    made = Batch(tmp_path, source=source, items=ITEMS)

    result = made.run("--input", "n=0", "--input", "xs=[]")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "[]"


@pytest.mark.parametrize("options", [':max "three"', ":max (= n 1)", ":max 0", ":max -1",
                                     ":max n :parallel 2 :workspace repo",
                                     ":max (+ 1 2) :parallel 2 :workspace repo"])
def test_invalid_max_is_refused_as_the_map_form(tmp_path, options):
    made = batch(tmp_path, FIRST, "serial", options)
    result = cli(made.ws, "compile", "main.orc", "--command-boundaries-file", "commands.json")

    assert result.returncode != 0
    assert "[list_map_effect_max_invalid]" in result.stdout + result.stderr


def test_run_recorded_before_the_change_resumes_to_the_same_cap_failure(tmp_path):
    ws = tmp_path / "ws"
    shutil.copytree(FIXTURE, ws, ignore=shutil.ignore_patterns("runs", "README.md"))
    shutil.copytree(FIXTURE / "runs", ws / ".orchestrate" / "runs")
    (run_root,) = (ws / ".orchestrate" / "runs").iterdir()
    memo = (run_root / "memo.jsonl").read_bytes()

    result = cli(ws, "resume", run_root.name)

    assert "[list_map_effect_cap_exceeded]" in result.stderr, result.stderr
    assert effect_rows(result.stderr) == []
    assert (run_root / "memo.jsonl").read_bytes() == memo
    assert not (ws / "dispatches.log").exists()


# ---- Phase 3a: every parallel item is unproven, also with several effects ------------------------------------------

TWO_STEP_PARALLEL = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defworkflow run () -> List[Int]
    (list/map-effect ((repo (list "alpha" "beta" "gamma"))) :max 3 :parallel 2
      :workspace (string/concat repo "/work")
      (let* ((f (command-result first :argv ("python" "first.py") :returns Int))
             (g (command-result second :argv ("python" "second.py" f) :returns Int)))
        g))))
'''
FIRST_PY = 'import os\nfrom pathlib import Path\nPath(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("1")\n'
SECOND_PY = ('import os, sys\nfrom pathlib import Path\n'
             'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(str(int(sys.argv[1]) + 10))\n')


def test_failed_second_effect_of_a_parallel_item_is_retried_only_with_accept_changes(tmp_path):
    from tests.test_workflow_evaluated_script_fix_retry import refuses_without_writes, run_id, started

    (tmp_path / "main.orc").write_text(TWO_STEP_PARALLEL)
    for item in ("alpha", "beta", "gamma"):
        (tmp_path / item / "work").mkdir(parents=True)
        (tmp_path / item / "work" / "first.py").write_text(FIRST_PY)
        (tmp_path / item / "work" / "second.py").write_text("import sys\nsys.exit(3)\n" if item == "beta" else SECOND_PY)
    (tmp_path / "commands.json").write_text(json.dumps({
        name: {"stable_command": ["python", f"{name}.py"], "closure": []} for name in ("first", "second")}))
    assert cli(tmp_path, "run", "main.orc", "--command-boundaries-file", "commands.json").returncode == 1
    (tmp_path / "beta" / "work" / "second.py").write_text(SECOND_PY)

    refuses_without_writes(tmp_path, "effect_input_diverged")
    accepted = cli(tmp_path, "resume", run_id(tmp_path), "--accept-changes")

    assert accepted.returncode == 0, accepted.stderr
    assert started(accepted.stderr) == ["workflow:main::run / par-map:repo[1] / g"]
    assert accepted.stdout.splitlines()[-1] == "[11,11,11]"


# ---- a parallel map written directly in a serial map body or a loop body ------------------------------------------

INNER_PARALLEL = ('(list/length (list/map-effect ((s (list "a" "b"))) :max 2 :parallel 2 :workspace s '
                  '(command-result step :argv ("python" "step.py" s "first") :returns Int)))')


@pytest.mark.parametrize("body, value, runs", [
    (INNER_PARALLEL, [2, 2, 2], 3),
    (f"(let* ((n {INNER_PARALLEL})) n)", [2, 2, 2], 3),
    (f'(if (= repo "b") {INNER_PARALLEL} 0)', [0, 2, 0], 1),
], ids=["direct", "under_let", "under_if"])
def test_parallel_map_in_a_serial_map_body_runs(tmp_path, body, value, runs):
    made = batch(tmp_path, body, "serial")

    result = made.run("--input", "n=3")

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == value
    assert Counter(made.dispatches()) == {("a", "first"): runs, ("b", "first"): runs}


def test_parallel_map_in_a_loop_body_runs(tmp_path):
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defworkflow run () -> Int
    (loop/recur :max 3 :state 0 :on-exhausted 0
      (fn (i) (if (= i 2) (done i) (let* ((k {INNER_PARALLEL})) (continue (+ i k -1))))))))
'''
    made = Batch(tmp_path, source=source, items=ITEMS)

    result = made.run()

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "2"
    assert Counter(made.dispatches()) == {("a", "first"): 2, ("b", "first"): 2}


def test_computed_max_in_a_procedure_used_twice_and_through_bind_proc(tmp_path):
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defproc each ((n Int) (xs List[String])) -> List[Int] (list/map-effect ((repo xs)) :max n {FIRST}))
  (defproc apply-it ((f ProcRef[(List[String]) -> List[Int]]) (xs List[String])) -> List[Int] (f xs))
  (defworkflow run ((n Int)) -> Int
    (let* ((p (each n (list "a"))) (q (each (+ n 1) (list "b" "c")))
           (r (apply-it (bind-proc (proc-ref each) :n n) (list "a"))))
      (+ (list/length p) (list/length q) (list/length r)))))
'''
    made = Batch(tmp_path, source=source, items=ITEMS)
    shutil.copy(made.ws / "a" / "step.py", made.ws / "step.py")
    digests = {json.loads(cli(made.ws, "compile", "main.orc", "--command-boundaries-file", "commands.json")
                          .stdout)["program_digest"] for _ in range(2)}

    result = made.run("--input", "n=1")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "4"
    assert made.dispatches() == [("a", "first"), ("b", "first"), ("c", "first"), ("a", "first")]
    identities = [row["identity"] for row in committed(made.snapshot())]
    assert (len(digests), len(set(identities))) == (1, 4)
