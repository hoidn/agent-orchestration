"""An effect may be written wherever a value is expected (surface coherence E1).

Contract: docs/design/workflow_lisp_surface_coherence.md §4 and §9 (row E1); the
frontend specification §16.3. Every program goes through the public CLI with
stand-in commands that log their argument; no provider is called.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_cli_run_output import cli, effect_rows, env
from tests.workflow_evaluated_commit_kill import kill_after_first_commit

HEADER = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defrecord Pair (a Int) (b Int))
  (defrecord Tri (a Int) (b Int) (c Int))
  (defrecord Wrap (v Bool))
  (defrecord Flag (v Bool) (k Int))
  (defrecord Nest (xs List[Int]) (p Pair))
  (defunion Box (RECT (w Int) (h Int) (k Int)) (NONE (z Int)))
  (defunion Shape (CIRCLE (r Int)) (SQUARE (s Int)))
  (defpath Report :kind relpath :under "artifacts/work" :must-exist false)
  (defproc add ((x Int) (y Int)) -> Int (+ x y))
'''
PROBE = '''import json, os, sys
from pathlib import Path
arg = sys.argv[1]
with open(Path(__file__).with_name("calls.log"), "a", encoding="utf-8") as log:
    log.write(arg + "\\n")
if Path(__file__).with_name("fail-" + arg).exists():
    sys.exit(3)
try:
    value = json.loads(arg)
except ValueError:
    value = arg
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(value))
'''
M = "(match (variant Shape CIRCLE :r n) ((CIRCLE c) c.r) ((SQUARE s) 0))"
ITEM = '(command-result e :argv ("python" "{probe}" x) :returns Int)'


def E(arg: str, returns: str = "Int", command: str = "e") -> str:
    return f'(command-result {command} :argv ("python" "{{probe}}" "{arg}") :returns {returns})'


def write(root: Path, returns: str, body: str, decls: str = "", commands: dict | None = None) -> Path:
    """Write main.orc, the logging stand-in and its command manifest under `root`."""

    root.mkdir(parents=True, exist_ok=True)
    probe = root / "probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    source = HEADER + decls + f"\n  (defworkflow run ((n Int)) -> {returns}\n    {body}))\n"
    (root / "main.orc").write_text(source.replace("{probe}", probe.as_posix()), encoding="utf-8")
    manifest = {"e": {"stable_command": ["python", probe.as_posix()], "closure": []}}
    (root / "commands.json").write_text(json.dumps({**manifest, **(commands or {})}), encoding="utf-8")
    return root


def run(root: Path, *extra: str):
    return cli(root, "run", "main.orc", "--input", "n=1", *extra)


def calls(root: Path) -> list[str]:
    log = root / "calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def value(result) -> object:
    return json.loads(result.stdout.splitlines()[-1])


def started(stderr: str) -> list[str]:
    return [identity.split(" / ", 1)[1] for word, identity in effect_rows(stderr) if word == "start"]


# Each newly admitted placement: (returns, body, declarations, value, ordered command log).
PLACEMENTS = {
    "record-fields-in-written-order": ("Pair", f"(record Pair :b {E(2)} :a {E(1)})", "", {"a": 1, "b": 2}, ["2", "1"]),
    "variant-field": ("Int", f"(match (variant Shape CIRCLE :r {E(4)}) ((CIRCLE c) c.r) ((SQUARE s) 0))", "", 4, ["4"]),
    "field-and-skips-its-second-effect": (
        "Bool", f"(let* ((w (record Wrap :v (and (> {E(0)} 0) (> {E(2)} 0))))) w.v)", "", False, ["0"]),
    "list-elements": ("List[Int]", f"(list {E(1)} {E(2)} 3)", "", [1, 2, 3], ["1", "2"]),
    "on-exhausted": (
        "Int", f"(loop/recur :max 1 :state 0 :on-exhausted (+ s {E(9)}) (fn (s) (if (> s 5) (done s) (continue (+ s 1)))))",
        "", 10, ["9"]),
    "on-exhausted-not-run-on-done": (
        "Int", f"(loop/recur :max 3 :state 0 :on-exhausted (+ s {E(9)}) (fn (s) (if (> s 0) (done s) (continue (+ s 1)))))",
        "", 1, []),
    "serial-map-source": (
        "List[Int]", f'(list/map-effect ((x {E("[1,2]", "List[Int]")})) :max 5 {ITEM})', "", [1, 2], ["[1,2]", "1", "2"]),
    "serial-map-source-list": (
        "List[Int]", f"(list/map-effect ((x (list {E(1)} {E(2)}))) :max 5 {ITEM})", "", [1, 2], ["1", "2", "1", "2"]),
    "pure-map-source": ("List[Int]", f'(list/map ((x {E("[1,2,3]", "List[Int]")})) (+ x 1))', "", [2, 3, 4], ["[1,2,3]"]),
    "path-child": ("Report", f'(path/join-under Report {E("s", "String")})', "", "artifacts/work/s", ["s"]),
    "list-in-continue": (
        "Int", f"(loop/recur :max 3 :state (list 0) :on-exhausted 0 (fn (s) (if (> (list/length s) 1) (done (list/length s)) (continue (list {E(1)} {E(2)})))))",
        "", 2, ["1", "2"]),
    "path-in-continue": (
        "Report", f'(loop/recur :max 2 :state (path/join-under Report "a") :on-exhausted s (fn (s) (if (= n 2) (done s) (continue (path/join-under Report {E("s", "String")})))))',
        "", "artifacts/work/s", ["s", "s"]),
    "pure-map-in-continue": (
        "Int", f'(loop/recur :max 3 :state (list 0) :on-exhausted 0 (fn (s) (if (> (list/length s) 1) (done (list/length s)) (continue (list/map ((x {E("[1,2]", "List[Int]")})) x)))))',
        "", 2, ["[1,2]"]),
    "field-in-argument-in-if-condition": (
        "Int", f"(if (> (add (let* ((p (record Pair :a {E(1)} :b {E(2)}))) p.a) 0) 0) {E(3)} {E(4)})", "", 3, ["1", "2", "3"]),
    "field-beside-match-field": (
        "Pair", f"(record Pair :a {E(1)} :b (match (variant Shape CIRCLE :r n) ((CIRCLE c) {E(2)}) ((SQUARE s) 0)))",
        "", {"a": 1, "b": 2}, ["1", "2"]),
    "match-field-written-first": (
        "Pair", f"(record Pair :b (match (variant Shape CIRCLE :r n) ((CIRCLE c) {E(2)}) ((SQUARE s) 0)) :a {E(1)})",
        "", {"a": 1, "b": 2}, ["2", "1"]),
    "match-operand-runs-one-arm": (
        "Int", f"(+ 1 (match (variant Shape CIRCLE :r n) ((CIRCLE c) {E(5)}) ((SQUARE s) {E(6)})))", "", 6, ["5"]),
    "if-field-beside-match-field": ("Tri", f"(record Tri :a (if (> n 0) {E(7)} 0) :b 1 :c {M})", "",
                                    {"a": 7, "b": 1, "c": 1}, ["7"]),
    "if-field-after-match-field": ("Tri", f"(record Tri :c {M} :a (if (> n 0) {E(7)} 0) :b 1)", "",
                                   {"a": 7, "b": 1, "c": 1}, ["7"]),
    "if-variant-field-beside-match-field": (
        "Int", f"(let* ((v (variant Box RECT :w (if (> n 0) {E(7)} 0) :h 1 :k {M}))) (match v ((RECT r) (+ r.w r.k)) ((NONE z) 0)))",
        "", 8, ["7"]),
    "cond-field-beside-match-field": ("Tri", f"(record Tri :a (cond ((> n 0) {E(7)}) (else 0)) :b 1 :c {M})", "",
                                      {"a": 7, "b": 1, "c": 1}, ["7"]),
    "and-field-beside-match-field": ("Bool", f"(let* ((w (record Flag :v (and (> n 0) (> {E(1)} 0)) :k {M}))) w.v)", "",
                                     True, ["1"]),
    "pure-match-operand": ("Int", f"(+ 1 {M})", "", 2, []),
    "pure-match-operands": ("Int", f"(+ {M} (* 2 {M}))", "", 3, []),
}


@pytest.mark.parametrize("case", PLACEMENTS)
def test_admitted_placement_runs_each_effect_once_in_written_order(tmp_path: Path, case: str) -> None:
    returns, body, decls, expected, log = PLACEMENTS[case]
    write(tmp_path, returns, body, decls)

    result = run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (value(result), calls(tmp_path)) == (expected, log)


def test_parallel_map_source_runs_once_before_any_item(tmp_path: Path) -> None:
    for name in ("a", "b"):
        (tmp_path / "ws" / name).mkdir(parents=True)
    source = E('[\\"a\\",\\"b\\"]', "List[String]")
    body = (f'(list/map-effect ((x {source})) :max 2 :parallel 1 '
            f'''  :workspace (string/concat "ws/" x) (command-result e :argv ("python" "{{probe}}" x) :returns String))''')
    write(tmp_path, "List[String]", body)

    result = run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (value(result), calls(tmp_path)) == (["a", "b"], ['["a","b"]', "a", "b"])


def test_field_effects_have_stable_distinct_identities(tmp_path: Path) -> None:
    body = f"(record Pair :a {E(1)} :b {E(2)})"
    first, second = write(tmp_path / "one", "Pair", body), write(tmp_path / "two", "Pair", body)

    runs = [run(first), run(second)]

    assert [started(result.stderr) for result in runs] == [["#1", "#2"], ["#1", "#2"]]


def test_field_effect_identity_does_not_depend_on_a_match_sibling(tmp_path: Path) -> None:
    with_match = write(tmp_path / "match", "Pair", f"(record Pair :a {E(1)} :b {M})")
    without = write(tmp_path / "plain", "Pair", f"(record Pair :a {E(1)} :b 3)")

    assert started(run(with_match).stderr) == started(run(without).stderr) == ["#1"]


def test_exhaustion_effect_identity_names_its_path(tmp_path: Path) -> None:
    write(tmp_path, "Int", PLACEMENTS["on-exhausted"][1])

    assert started(run(tmp_path).stderr) == ["loop:s / exhausted / #1"]


def test_compiled_program_digest_is_stable(tmp_path: Path) -> None:
    write(tmp_path, "List[Int]", f"(list {E(1)} (+ 1 {M}) {E(2)})")
    digests = []
    for _ in range(2):
        compiled = cli(tmp_path, "compile", "main.orc")
        assert compiled.returncode == 0, compiled.stderr
        digests.append(json.loads(compiled.stdout)["program_digest"])

    assert digests[0] == digests[1]


# An effect's name does not depend on its effect-free sibling fields, a `match` among them (design §4, §12.1).
SIBLING_MATCH = {
    "record": "(record Tri :a (let* ((y {e7})) y) :b {e8} :c {third})",
    "record-match-written-first": "(record Tri :c {third} :a (let* ((y {e7})) y) :b {e8})",
    "variant": "(match (variant Box RECT :w (let* ((y {e7})) y) :h {e8} :k {third}) ((RECT r) r.w) ((NONE z) 0))",
    "variant-in-let": "(let* ((v (variant Box RECT :w (let* ((y {e7})) y) :h {e8} :k {third}))) (match v ((RECT r) r.w) ((NONE z) 0)))",
    "nested-record": "(record Nest :xs (list {third}) :p (record Pair :a (let* ((y {e7})) y) :b {e8}))",
    "record-update": "(record-update (record Tri :a 0 :b 0 :c 0) :a (let* ((y {e7})) y) :b {e8} :c {third})",
    "if-field-variant-in-let": "(let* ((v (variant Box RECT :w (if (> n 0) {e7} 0) :h {e8} :k {third}))) (match v ((RECT r) r.w) ((NONE z) 0)))",
}
SIBLING_RETURNS = {"record": "Tri", "record-match-written-first": "Tri", "variant": "Int", "variant-in-let": "Int",
                   "nested-record": "Nest", "record-update": "Tri", "if-field-variant-in-let": "Int"}


SIBLINGS = {"match": M, "plain": "0", "pure-if": "(if (> n 0) 1 2)", "pure-let": "(let* ((q 3)) q)"}


@pytest.mark.parametrize("case", SIBLING_MATCH)
def test_field_effect_names_do_not_depend_on_an_effect_free_sibling(tmp_path: Path, case: str) -> None:
    names = {}
    for name, third in SIBLINGS.items():
        body = SIBLING_MATCH[case].format(e7=E(7), e8=E(8), third=third)
        result = run(write(tmp_path / name, SIBLING_RETURNS[case], body))
        assert (result.returncode, calls(tmp_path / name)) == (0, ["7", "8"]), result.stderr
        names[name] = started(result.stderr)

    assert len(set(map(tuple, names.values()))) == 1, names


# A `continue` value that holds an effect under a conditional inside a larger value is refused, with the
# rewrite to bind it first; the same value runs in every other value position and through that rewrite.
IFE = f"(if (> n 0) {E(1)} {E(2)})"
ONE = f"(defproc one ((x Int)) -> Int {E(5)})"
CONTINUE_SHAPES = {
    "record-if": ("Pair", "(record Pair :a 0 :b 0)", f"(record Pair :a {IFE} :b 9)", {"a": 1, "b": 9}, ["1"], ""),
    "list-if": ("List[Int]", "(list 0)", f"(list {IFE} 9)", [1, 9], ["1"], ""),
    "record-match": ("Pair", "(record Pair :a 0 :b 0)",
                     f"(record Pair :a (match (variant Shape CIRCLE :r n) ((CIRCLE c) {E(1)}) ((SQUARE q) 0)) :b 9)",
                     {"a": 1, "b": 9}, ["1"], ""),
    "record-cond": ("Pair", "(record Pair :a 0 :b 0)", f"(record Pair :a (cond ((> n 0) {E(1)}) (else 0)) :b 9)",
                    {"a": 1, "b": 9}, ["1"], ""),
    "record-or": ("Wrap", "(record Wrap :v false)", f"(record Wrap :v (or (> n 5) (> {E(1)} 0)))", {"v": True}, ["1"], ""),
    "list-and": ("List[Bool]", "(list false)", f"(list (and (> n 0) (> {E(1)} 0)))", [True], ["1"], ""),
    "path-if": ("Report", '(path/join-under Report "z")',
                f'(path/join-under Report (if (> n 0) {E("x", "String")} "y"))', "artifacts/work/x", ["x"], ""),
    "map-source-if": ("List[Int]", "(list 0)", f"(list/map ((x (list {IFE}))) x)", [1], ["1"], ""),
    "list-if-procedure": ("List[Int]", "(list 0)", "(list (if (> n 0) (one 1) 0))", [5], ["5"], ONE),
    "record-if-procedure": ("Pair", "(record Pair :a 0 :b 0)", "(record Pair :a (if (> n 0) (one 1) 0) :b 9)",
                            {"a": 5, "b": 9}, ["5"], ONE),
    "record-if-beside-match": ("Tri", "(record Tri :a 0 :b 0 :c 0)", f"(record Tri :a {IFE} :b 1 :c {M})",
                               {"a": 1, "b": 1, "c": 1}, ["1"], ""),
    # A `compiler_defect` before effects were admitted in fields, too.
    "operator-if": ("Int", "0", f"(+ {IFE} 9)", 10, ["1"], ""),
    "record-update-if": ("Pair", "(record Pair :a 0 :b 0)", f"(record-update (record Pair :a 0 :b 9) :a {IFE})",
                         {"a": 1, "b": 9}, ["1"], ""),
    "let-then-record": ("Pair", "(record Pair :a 0 :b 0)", f"(let* ((v {IFE})) (record Pair :a v :b 9))",
                        {"a": 1, "b": 9}, ["1"], ""),
}
ONE_ROUND = "(loop/recur :max 1 :state {seed} :on-exhausted s (fn (s) (if (= n 7) (done s) {step})))"
VALUE_POSITIONS = {
    "let-then-continue": ONE_ROUND.replace("{step}", "(let* ((next {v})) (continue next))"),
    "done": "(loop/recur :max 1 :state {seed} :on-exhausted s (fn (s) (done {v})))",
    "state": "(loop/recur :max 1 :state {v} :on-exhausted s (fn (s) (done s)))",
    "on-exhausted": "(loop/recur :max 1 :state {seed} :on-exhausted {v} (fn (s) (if (= n 7) (done s) (continue s))))",
    "workflow-return": "{v}",
    "procedure-return": "(mk n)",
    "let-binding": "(let* ((v {v})) v)",
}


@pytest.mark.parametrize("shape", CONTINUE_SHAPES)
def test_continue_value_with_a_nested_conditional_effect_is_refused(tmp_path: Path, shape: str) -> None:
    returns, seed, value_expr, _, _, decls = CONTINUE_SHAPES[shape]
    write(tmp_path, returns, ONE_ROUND.format(seed=seed, step=f"(continue {value_expr})"), decls)

    compiled = cli(tmp_path, "compile", "main.orc")

    assert (compiled.returncode, compiled.stderr.count("[effect_not_permitted]"), "(continue next)" in compiled.stderr,
            "Traceback" in compiled.stderr) == (2, 1, True, False), compiled.stderr


def test_inner_loop_continue_value_with_a_nested_conditional_effect_is_refused(tmp_path: Path) -> None:
    inner = ONE_ROUND.format(seed="(record Pair :a 0 :b 0)", step=f"(continue (record Pair :a {IFE} :b 9))")
    outer = f"(loop/recur :max 1 :state 0 :on-exhausted {inner} (fn (t) (if (= n 7) (done {inner}) (continue t))))"
    write(tmp_path, "Pair", outer)

    compiled = cli(tmp_path, "compile", "main.orc")

    assert (compiled.returncode, "[effect_not_permitted]" in compiled.stderr) == (2, True), compiled.stderr


@pytest.mark.parametrize("position", VALUE_POSITIONS)
@pytest.mark.parametrize("shape", CONTINUE_SHAPES)
def test_refused_continue_value_runs_in_every_other_value_position(tmp_path: Path, shape: str, position: str) -> None:
    returns, seed, value_expr, expected, log, decls = CONTINUE_SHAPES[shape]
    if position == "procedure-return":
        decls += f"(defproc mk ((n Int)) -> {returns} {value_expr})"
    write(tmp_path, returns, VALUE_POSITIONS[position].format(seed=seed, v=value_expr), decls)

    result = run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (value(result), calls(tmp_path)) == (expected, log)


def test_parallel_map_with_a_pure_conditional_source_runs(tmp_path: Path) -> None:
    (tmp_path / "ws" / "w").mkdir(parents=True)
    item = '(command-result e :argv ("python" "{probe}" x) :returns String)'
    write(tmp_path, "List[String]", '(list/map-effect ((x (if (> n 0) (list "w") (list "q")))) :max 2 :parallel 1 '
          f':workspace (string/concat "ws/" x) {item})')

    result = run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (value(result), calls(tmp_path)) == (["w"], ["w"])


def test_effectful_map_source_bindings_do_not_capture_body_names(tmp_path: Path) -> None:
    write(tmp_path, "List[Int]", f"(let* ((y 5)) (list/map ((x (let* ((y {E(1)})) (list y)))) (+ x y)))")

    result = run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (value(result), calls(tmp_path)) == ([6], ["1"])


# Kill, failure and `must_not_repeat`: each newly admitted form beside the equivalent `let*`.
def F(command: str, arg: str) -> str:
    return f'(command-result {command} :argv ("python" "{command}.py" "{arg}") :returns Int)'


TWO_EFFECTS = {
    "let": ("Pair", f"(let* ((a {F('first', '1')}) (b {F('second', '2')})) (record Pair :a a :b b))",
            {"a": 1, "b": 2}, ["b"]),
    "record": ("Pair", f"(record Pair :a {F('first', '1')} :b {F('second', '2')})", {"a": 1, "b": 2}, ["#2"]),
    "list": ("List[Int]", f"(list {F('first', '1')} {F('second', '2')})", [1, 2], ["#2"]),
    "on-exhausted": (
        "Pair", f"(loop/recur :max 1 :state 0 :on-exhausted (record Pair :a {F('first', '1')} :b {F('second', '2')})"
        " (fn (s) (if (> s 5) (done (record Pair :a 0 :b 0)) (continue (+ s 1)))))",
        {"a": 1, "b": 2}, ["loop:s / exhausted / #2"]),
}
STEP = PROBE.replace('Path(__file__).with_name("fail-" + arg)', 'Path(__file__).with_name("fail-" + Path(__file__).stem)')


def write_two(root: Path, form: str, *, must_not_repeat: bool = False) -> Path:
    returns, body, _, _ = TWO_EFFECTS[form]
    commands = {name: {"stable_command": ["python", f"{name}.py"], "closure": [f"{name}.py"]}
                for name in ("first", "second")}
    commands["second"]["must_not_repeat"] = must_not_repeat
    write(root, returns, body, commands=commands)
    for name in ("first", "second"):
        (root / f"{name}.py").write_text(STEP, encoding="utf-8")
    return root


def resume(root: Path, *flags: str):
    (run_id,) = (path.name for path in (root / ".orchestrate" / "runs").iterdir())
    return cli(root, "resume", run_id, *flags)


@pytest.mark.parametrize("form", TWO_EFFECTS)
def test_kill_between_two_effects_reuses_the_first_and_runs_the_second_once(tmp_path: Path, form: str) -> None:
    root = write_two(tmp_path, form)
    kill_after_first_commit(root, ["run", "main.orc", "--input", "n=1"], env())

    resumed = resume(root)

    assert resumed.returncode == 0, resumed.stderr
    _, _, expected, second = TWO_EFFECTS[form]
    assert (value(resumed), calls(root), started(resumed.stderr)) == (expected, ["1", "2"], second)


@pytest.mark.parametrize("form", TWO_EFFECTS)
def test_failed_second_effect_retries_alone(tmp_path: Path, form: str) -> None:
    root = write_two(tmp_path, form)
    (root / "fail-second").write_text("", encoding="utf-8")
    assert run(root).returncode == 1
    (root / "fail-second").unlink()

    resumed = resume(root)

    assert resumed.returncode == 0, resumed.stderr
    _, _, expected, second = TWO_EFFECTS[form]
    assert (value(resumed), calls(root), started(resumed.stderr)) == (expected, ["1", "2", "2"], second)


@pytest.mark.parametrize("form", TWO_EFFECTS)
def test_failed_second_effect_retries_after_its_script_is_fixed(tmp_path: Path, form: str) -> None:
    root = write_two(tmp_path, form)
    (root / "second.py").write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    assert run(root).returncode == 1
    (root / "second.py").write_text(STEP, encoding="utf-8")

    resumed = resume(root)

    assert resumed.returncode == 0, resumed.stderr
    _, _, expected, second = TWO_EFFECTS[form]
    assert (value(resumed), calls(root), started(resumed.stderr)) == (expected, ["1", "2"], second)


@pytest.mark.parametrize("form", TWO_EFFECTS)
def test_failed_must_not_repeat_effect_is_not_dispatched_again(tmp_path: Path, form: str) -> None:
    root = write_two(tmp_path, form, must_not_repeat=True)
    (root / "fail-second").write_text("", encoding="utf-8")
    assert run(root).returncode == 1
    (root / "fail-second").unlink()

    resumed = resume(root)

    assert resumed.returncode == 2, resumed.stderr
    assert (resumed.stderr.split("]", 1)[0], calls(root)) == ("[lexical_restore_pending_effect_unsafe", ["1", "2"])


# The pure places keep one clear refusal for an effect in a newly admitted position.
REFUSALS = {
    "defun-body": ("Pair", "(bad n)", f"(defun bad ((x Int)) -> Pair (record Pair :a {E(1)} :b x))",
                   "pure_function_has_effect"),
    "list-map-body": ("List[Pair]", f"(list/map ((x (list 1 2))) (record Pair :a {E(1)} :b x))", "",
                      "list_map_body_effect_forbidden"),
    "list-map-body-list": ("List[List[Int]]", f"(list/map ((x (list 1 2))) (list x {E(1)}))", "",
                           "list_map_body_effect_forbidden"),
    "on-exhausted-in-list-map-body": (
        "List[Int]", f"(list/map ((x (list 1 2))) (loop/recur :max 1 :state 0 :on-exhausted (+ s {E(1)}) (fn (s) (if (> s 5) (done s) (continue (+ s 1))))))",
        "", "list_map_body_effect_forbidden"),
    "on-exhausted-in-defun-body": (
        "Int", "(bad n)", f"(defun bad ((n Int)) -> Int (loop/recur :max 1 :state 0 :on-exhausted (+ s {E(1)}) (fn (s) (if (> s 5) (done s) (continue (+ s 1))))))",
        "pure_function_has_effect"),
    "on-exhausted-in-parallel-workspace": (
        "List[Int]", f'(list/map-effect ((x (list "w"))) :max 1 :parallel 1 :workspace (loop/recur :max 1 :state "w" :on-exhausted (string/concat "ws/" {E("w", "String")}) (fn (s) (if (= s "z") (done s) (continue s)))) {E(1)})',
        "", "list_map_effect_workspace_invalid"),
    "parallel-workspace": (
        "List[Int]", f'(list/map-effect ((x (list "a"))) :max 1 :parallel 1 :workspace (path/join-under Report {E("s", "String")}) {E(1)})',
        "", "list_map_effect_workspace_invalid"),
}


@pytest.mark.parametrize("case", REFUSALS)
def test_pure_place_keeps_one_clear_refusal(tmp_path: Path, case: str) -> None:
    returns, body, decls, code = REFUSALS[case]
    write(tmp_path, returns, body, decls)

    compiled = cli(tmp_path, "compile", "main.orc")

    assert (compiled.returncode, f"[{code}]" in compiled.stderr, "Traceback" in compiled.stderr) == (2, True, False)
    assert calls(tmp_path) == []


def test_list_map_body_refusal_points_at_the_effect(tmp_path: Path) -> None:
    write(tmp_path, "List[Pair]", f"(list/map ((x (list 1 2))) (record Pair :a {E(1)} :b x))")
    lines = (tmp_path / "main.orc").read_text(encoding="utf-8").splitlines()
    (line,) = [number for number, text in enumerate(lines, 1) if "(command-result" in text]

    compiled = cli(tmp_path, "compile", "main.orc")

    assert f"main.orc:{line}:{lines[line - 1].index('(command-result') + 1}: [list_map_body_effect_forbidden]" in compiled.stderr
