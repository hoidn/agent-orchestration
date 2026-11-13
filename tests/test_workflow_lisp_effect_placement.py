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
from tests.test_workflow_evaluated_resume_kills import _kill_after_first_commit

HEADER = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defrecord Pair (a Int) (b Int))
  (defrecord Wrap (v Bool))
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
    _kill_after_first_commit(root, ["run", "main.orc", "--input", "n=1"], env())

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
