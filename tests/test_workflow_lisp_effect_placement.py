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


# Each admitted placement: (returns, body, declarations, value, ordered command log). A record or variant
# field, a list element, a path child, a map source and `:on-exhausted` take an effect in a simple value:
# the effect forms (a command, a provider, an agent, a workflow call, a run reference) and operators over
# literals, names, field reads and other simple values (frontend specification 16.3). A procedure call is
# not simple, whatever it holds.
FETCH = f"(defproc fetch ((k Int)) -> Int {E(6)})"
ADDL = "(defproc addL ((xs List[Int])) -> List[Int] xs)"
TOTAL = "(defproc total ((xs List[Int])) -> Int (list/length xs))"
KID = f"(defworkflow kid ((t Int)) -> Int {E(8)})"
SAME = "(defworkflow same ((t Int)) -> Int t)"
PLACEMENTS = {
    "record-fields-in-written-order": ("Pair", f"(record Pair :b {E(2)} :a {E(1)})", "", {"a": 1, "b": 2}, ["2", "1"]),
    "variant-field": ("Int", f"(match (variant Shape CIRCLE :r {E(4)}) ((CIRCLE c) c.r) ((SQUARE s) 0))", "", 4, ["4"]),
    "list-elements": ("List[Int]", f"(list {E(1)} {E(2)} 3)", "", [1, 2, 3], ["1", "2"]),
    "operator-over-two-effects-in-a-field": ("Pair", f"(record Pair :a (+ {E(1)} {E(2)}) :b n)", "", {"a": 3, "b": 1}, ["1", "2"]),
    "workflow-call-field": ("Pair", "(record Pair :a (call kid :t n) :b 9)", KID, {"a": 8, "b": 9}, ["8"]),
    "workflow-call-element": ("List[Int]", "(list (call kid :t n) 9)", KID, [8, 9], ["8"]),
    "effect-argument-of-a-workflow-call-in-a-field": (
        "Pair", f"(record Pair :a (call kid :t {E(1)}) :b 9)", KID, {"a": 8, "b": 9}, ["1", "8"]),
    "top-level-procedure-body": ("Pair", "(mk 3)", f"(defproc mk ((y Int)) -> Pair (record Pair :a {E(1)} :b y))",
                                 {"a": 1, "b": 3}, ["1"]),
    "workflow-argument-holding-a-list": (
        "Int", f"(call kid :t (list/length (list {E(1)} 2)))", KID, 8, ["1", "8"]),
    "nested-constructor-subject": (
        "Int", f"(match (variant Held HELD :p (record Pair :a {E(3)} :b 1)) ((HELD h) (+ h.p.a h.p.b)) ((EMPTY z) 0))",
        "(defunion Held (HELD (p Pair)) (EMPTY (z Int)))", 4, ["3"]),
    "on-exhausted": (
        "Int", f"(loop/recur :max 1 :state 0 :on-exhausted (+ s {E(9)}) (fn (s) (if (> s 5) (done s) (continue (+ s 1)))))",
        "", 10, ["9"]),
    "on-exhausted-not-run-on-done": (
        "Int", f"(loop/recur :max 3 :state 0 :on-exhausted (+ s {E(9)}) (fn (s) (if (> s 0) (done s) (continue (+ s 1)))))",
        "", 1, []),
    "on-exhausted-workflow-call": (
        "Int", "(loop/recur :max 1 :state 0 :on-exhausted (call kid :t s) (fn (s) (if (> s 5) (done s) (continue (+ s 1)))))",
        KID, 8, ["8"]),
    "on-exhausted-pure-procedure-call": (
        "Int", "(loop/recur :max 1 :state 0 :on-exhausted (add s 4) (fn (s) (if (> s 5) (done s) (continue (+ s 1)))))",
        "", 5, []),
    "serial-map-source": (
        "List[Int]", f'(list/map-effect ((x {E("[1,2]", "List[Int]")})) :max 5 {ITEM})', "", [1, 2], ["[1,2]", "1", "2"]),
    "serial-map-source-list": (
        "List[Int]", f"(list/map-effect ((x (list {E(1)} {E(2)}))) :max 5 {ITEM})", "", [1, 2], ["1", "2", "1", "2"]),
    "pure-map-source": ("List[Int]", f'(list/map ((x {E("[1,2,3]", "List[Int]")})) (+ x 1))', "", [2, 3, 4], ["[1,2,3]"]),
    "pure-map-source-operator": ("List[Int]", f"(list/map ((x (list/append (list 4) {E(1)}))) (+ x 1))", "", [5, 2], ["1"]),
    "parallel-map-source": (
        "List[Int]", f'(list/map-effect ((x {E("[4]", "List[Int]")})) :max 1 :parallel 1 :workspace "ws/w" {ITEM})', "",
        [4], ["[4]", "4"]),
    "path-child": ("Report", f'(path/join-under Report {E("s", "String")})', "", "artifacts/work/s", ["s"]),
    "path-child-operator": (
        "Report", f'(path/join-under Report (string/concat {E("s", "String")} "x"))', "", "artifacts/work/sx", ["s"]),
    "list-in-continue": (
        "Int", f"(loop/recur :max 3 :state (list 0) :on-exhausted 0 (fn (s) (if (> (list/length s) 1) (done (list/length s)) (continue (list {E(1)} {E(2)})))))",
        "", 2, ["1", "2"]),
    "path-in-continue": (
        "Report", f'(loop/recur :max 2 :state (path/join-under Report "a") :on-exhausted s (fn (s) (if (= n 2) (done s) (continue (path/join-under Report {E("s", "String")})))))',
        "", "artifacts/work/s", ["s", "s"]),
    "pure-map-in-continue": (
        "Int", f'(loop/recur :max 3 :state (list 0) :on-exhausted 0 (fn (s) (if (> (list/length s) 1) (done (list/length s)) (continue (list/map ((x {E("[1,2]", "List[Int]")})) x)))))',
        "", 2, ["[1,2]"]),
    "field-in-operand-in-if-condition": (
        "Int", f"(if (> (+ (let* ((p (record Pair :a {E(1)} :b {E(2)}))) p.a) 0) 0) {E(3)} {E(4)})", "", 3, ["1", "2", "3"]),
    "match-operand-runs-one-arm": (
        "Int", f"(+ 1 (match (variant Shape CIRCLE :r n) ((CIRCLE c) {E(5)}) ((SQUARE s) {E(6)})))", "", 6, ["5"]),
    "pure-match-operand": ("Int", f"(+ 1 {M})", "", 2, []),
    "pure-match-operands": ("Int", f"(+ {M} (* 2 {M}))", "", 3, []),
}


@pytest.mark.parametrize("case", PLACEMENTS)
def test_admitted_placement_runs_each_effect_once_in_written_order(tmp_path: Path, case: str) -> None:
    returns, body, decls, expected, log = PLACEMENTS[case]
    (tmp_path / "ws" / "w").mkdir(parents=True)
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


def test_exhaustion_effect_identity_names_its_path(tmp_path: Path) -> None:
    write(tmp_path, "Int", PLACEMENTS["on-exhausted"][1])

    assert started(run(tmp_path).stderr) == ["loop:s / exhausted / #1"]


def test_compiled_program_digest_is_stable(tmp_path: Path) -> None:
    write(tmp_path, "List[Int]", f"(list {E(1)} (+ 1 n) {E(2)})")
    digests = []
    for _ in range(2):
        compiled = cli(tmp_path, "compile", "main.orc")
        assert compiled.returncode == 0, compiled.stderr
        digests.append(json.loads(compiled.stdout)["program_digest"])

    assert digests[0] == digests[1]


def refused_at(root: Path, part: str, code: str = "effect_not_permitted") -> str:
    """`main.orc:<line>:<column>: [<code>]` at `part` in the written program."""

    source = (root / "main.orc").read_text(encoding="utf-8")
    offset = source.index(part.replace("{probe}", (root / "probe.py").as_posix()))
    line = source.count("\n", 0, offset) + 1
    return f"main.orc:{line}:{offset - source.rfind(chr(10), 0, offset)}: [{code}]"


# What stays refused (frontend specification 16.3): in a place E1 opened, a value that holds an effect and
# a part that is not simple, be it the part with the effect or one beside it. Each row is refused with the
# code the place gave before E1, at the part to bind first: (returns, body, declarations, code, that part).
IFE = f"(if (> n 0) {E(1)} {E(2)})"
W = E("w", "String")
MATCH_E = f"(match (variant Shape CIRCLE :r n) ((CIRCLE c) {E(2)}) ((SQUARE s) 0))"
PURE_IF, PURE_LET, PURE_COND = "(if (> n 0) 1 2)", "(let* ((q 3)) q)", "(cond ((> n 5) 0) (else 1))"
PURE_MAP = "(list/length (list/map ((x (list 1 2))) x))"
INC = "(defun inc ((x Int)) -> Int (+ x 1))"
INVOKE = "(defproc invoke ((runner ProcRef[Int -> Int]) (x Int)) -> Int (runner x))"
COND_SUBJECT = f"(match (variant Shape CIRCLE :r (cond ((> n 5) 6) (else 1))) ((CIRCLE c) {E(1)}) ((SQUARE q) 0))"
EXHAUSTED = "(loop/recur :max 1 :state 0 :on-exhausted {v} (fn (s) (if (= n 7) (done s) (continue s))))"
PARALLEL = '(list/map-effect ((x {v})) :max 2 :parallel 1 :workspace (string/concat "ws/" x) (command-result e :argv ("python" "{probe}" x) :returns String))'
NOT_SIMPLE = {
    # The part that holds the effect is not simple (a `cond` is reported at its first clause).
    "if-field": ("Pair", f"(record Pair :a {IFE} :b 9)", "", "effect_not_permitted", IFE),
    "cond-field": ("Pair", f"(record Pair :a (cond ((> n 0) {E(1)}) (else 0)) :b 9)", "", "effect_not_permitted", "((> n 0)"),
    "match-field": ("Pair", f"(record Pair :a {E(1)} :b {MATCH_E})", "", "effect_not_permitted", MATCH_E),
    "and-field": ("Wrap", f"(record Wrap :v (and (> {E(0)} 0) (> {E(2)} 0)))", "", "effect_not_permitted", "(and"),
    "or-element": ("List[Bool]", f"(list (or (> n 5) (> {E(1)} 0)))", "", "effect_not_permitted", "(or"),
    "not-field": ("Wrap", f"(record Wrap :v (not (> {E(1)} 5)))", "", "effect_not_permitted", "(not"),
    "let-field": ("Pair", f"(record Pair :a (let* ((y {E(7)})) y) :b 0)", "", "effect_not_permitted", "(let*"),
    "let-element": ("List[Int]", f"(list (let* ((y {E(7)})) y) 2)", "", "effect_not_permitted", "(let*"),
    "if-variant-field-of-a-subject": (
        "Int", f"(match (variant Shape CIRCLE :r {IFE}) ((CIRCLE c) c.r) ((SQUARE q) 0))", "", "effect_not_permitted", IFE),
    "if-field-in-a-nested-constructor": (
        "Nest", f"(record Nest :xs (list 0) :p (record Pair :a {IFE} :b 9))", "", "effect_not_permitted", IFE),
    "if-path-child": (
        "Report", f'(path/join-under Report (if (> n 0) {E("x", "String")} "y"))', "", "effect_not_permitted", "(if"),
    "if-field-in-continue": (
        "Pair", f"(loop/recur :max 1 :state (record Pair :a 0 :b 0) :on-exhausted s (fn (s) (continue (record Pair :a {IFE} :b 9))))",
        "", "effect_not_permitted", IFE),
    "pure-procedure-over-an-effect": ("Pair", f"(record Pair :a (add {E(1)} 1) :b 9)", "", "effect_not_permitted", "(add"),
    "function-over-an-effect": ("Pair", f"(record Pair :a (inc {E(1)}) :b 9)", INC, "effect_not_permitted", "(inc"),
    "match-among-the-operands-of-the-effect": ("Pair", f"(record Pair :a (+ {E(1)} {M}) :b 9)", "", "effect_not_permitted", f"(+ {E(1)}"),
    "match-argument-of-the-call": ("Pair", f"(record Pair :a (call kid :t {M}) :b 9)", KID, "effect_not_permitted", "(call"),
    "loop-element": (
        "List[Int]", f"(list (loop/recur :max 1 :state 0 :on-exhausted s (fn (s) (done {E(1)}))))", "",
        "effect_not_permitted", "(loop/recur"),
    # No procedure call is simple, whatever the procedure holds.
    "effectful-procedure-call-field": ("Pair", "(record Pair :a (fetch n) :b 9)", FETCH, "effect_not_permitted", "(fetch n)"),
    "effectful-procedure-call-element": ("List[Int]", "(list (fetch 1) (fetch 2))", FETCH, "effect_not_permitted", "(fetch 1)"),
    "procedure-call-over-an-effect": (
        "Pair", f"(record Pair :a (fetch {E(1)}) :b 9)", FETCH, "effect_not_permitted", f"(fetch {E(1)}"),
    "effectful-procedure-call-on-exhausted": (
        "Int", EXHAUSTED.replace("{v}", "(fetch s)"), FETCH, "loop_recur_contract_invalid", "(fetch s)"),
    "let-proc-local-call-field": (
        "Pair", f"(let-proc ((f () -> Int {E(1)})) (record Pair :a (f) :b 0))", "", "effect_not_permitted", "(f)"),
    "pure-procedure-call-as-a-pure-map-source": (
        "List[Int]", f'(list/map ((x (addL {E("[1,2]", "List[Int]")}))) (+ x 1))', ADDL, "list_map_body_effect_forbidden", "(addL"),
    "pure-procedure-call-as-a-serial-map-source": (
        "List[Int]", f'(list/map-effect ((x (addL {E("[1,2]", "List[Int]")}))) :max 3 {ITEM})', ADDL,
        "list_map_effect_body_unsupported", "(addL"),
    "effectful-procedure-call-as-a-serial-map-source": (
        "List[Int]", f"(list/map-effect ((x (fetchl))) :max 3 {ITEM})",
        f'(defproc fetchl () -> List[Int] {E("[1,2]", "List[Int]")})', "list_map_effect_body_unsupported", "(fetchl)"),
    # A procedure or function call's arguments admit nothing new: the place inside keeps its refusal.
    "list-in-a-pure-procedure-argument": (
        "List[Int]", f"(let* ((v (addL (list {E(1)} 2)))) v)", ADDL, "effect_not_permitted", f"(list {E(1)} 2)"),
    "list-in-a-pure-procedure-argument-of-a-whole-result": (
        "Int", f"(total (list {E(1)} 2))", TOTAL, "effect_not_permitted", f"(list {E(1)} 2)"),
    "list-in-a-pure-procedure-argument-of-a-serial-map-source": (
        "List[Int]", f"(list/map-effect ((x (addL (list {E(1)} 2)))) :max 3 {ITEM})", ADDL,
        "effect_not_permitted", f"(list {E(1)} 2)"),
    "record-in-an-effectful-procedure-argument": (
        "Int", f"(sum (record Pair :a {E(1)} :b 2))", f"(defproc sum ((p Pair)) -> Int (+ p.a {E(8)}))",
        "effect_not_permitted", f"(record Pair :a {E(1)}"),
    "list-in-a-function-argument": (
        "Int", f"(inc (list/length (list {E(1)} 2)))", INC, "effect_not_permitted", f"(list {E(1)} 2)"),
    "field-in-a-procedure-argument-in-an-if-condition": (
        "Int", f"(if (> (add (let* ((p (record Pair :a {E(1)} :b {E(2)}))) p.a) 0) 0) {E(3)} {E(4)})", "",
        "effect_not_permitted", f"(record Pair :a {E(1)}"),
    # The body of a `let-proc` local admits nothing new, however the local is used.
    "local-called-by-name": (
        "Pair", f"(let-proc ((f ((y Int)) -> Pair (record Pair :a {E(1)} :b y))) (f 3))", "",
        "effect_not_permitted", f"(record Pair :a {E(1)}"),
    "local-passed-by-reference": (
        "Int", f"(let-proc ((f ((y Int)) -> Int (list/length (list {E(1)} y)))) (invoke (proc-ref f) 3))", INVOKE,
        "effect_not_permitted", f"(list {E(1)} y)"),
    "local-as-a-map-body": (
        "List[Int]", f"(let-proc ((f ((y Int)) -> Int (list/length (list {E(1)} y)))) (list/map-effect ((x (list 1 2))) :max 2 (f x)))",
        "", "effect_not_permitted", f"(list {E(1)} y)"),
    "local-in-a-macro-template": (
        "Pair", f"(with-local {E(1)})", "(defmacro with-local (v) (let-proc ((f ((y Int)) -> Pair (record Pair :a v :b y))) (f 3)))",
        "effect_not_permitted", "(record Pair :a v :b y)"),
    "local-reading-an-outer-effect-and-holding-a-list": (
        "List[Int]", f"(let* ((h {E(2)})) (let-proc ((f ((y Int)) -> List[Int] (list h {E(1)}))) (f 3)))", "",
        "effect_not_permitted", f"(list h {E(1)}"),
    "local-reading-an-outer-effect-and-holding-a-record": (
        "Pair", f"(let* ((h {E(2)})) (let-proc ((f ((y Int)) -> Pair (record Pair :a (+ h {E(1)}) :b y))) (f 3)))", "",
        "effect_not_permitted", "(record Pair :a (+ h"),
    "local-reading-an-outer-effect-and-holding-a-path": (
        "Report", f'(let* ((h {W})) (let-proc ((f ((y Int)) -> Report (path/join-under Report (string/concat h {E("q", "String")})))) (f 3)))',
        "", "effect_not_permitted", "(path/join-under Report (string/concat h"),
    "local-reading-an-outer-record-and-holding-a-record": (
        "Pair", f"(let* ((h (pair))) (let-proc ((f ((y Int)) -> Pair (record Pair :a (+ h.a {E(1)}) :b y))) (f 3)))",
        f"(defproc pair () -> Pair (let* ((b {E(6)})) (record Pair :a 4 :b b)))", "effect_not_permitted", "(record Pair :a (+ h.a"),
    "local-reading-an-outer-literal-and-holding-a-record": (
        "Pair", f"(let* ((h 2)) (let-proc ((f ((y Int)) -> Pair (record Pair :a (+ h {E(1)}) :b y))) (f 3)))", "",
        "effect_not_permitted", "(record Pair :a (+ h"),
    "local-with-a-serial-map-over-an-effect": (
        "List[Int]", f'(let-proc ((f ((y Int)) -> List[Int] (list/map-effect ((x {E("[1,2]", "List[Int]")})) :max 3 {ITEM}))) (f 0))',
        "", "list_map_effect_body_unsupported", "(list/map-effect ((x"),
    "local-with-a-serial-map-over-an-effect-under-an-operator": (
        "Int", f'(let-proc ((f ((y Int)) -> Int (+ y (list/length (list/map-effect ((x {E("[1,2]", "List[Int]")})) :max 3 {ITEM}))))) (f 0))',
        "", "list_map_effect_body_unsupported", "(list/map-effect ((x"),
    "local-with-an-effectful-exhaustion": (
        "Int", f"(let-proc ((f ((y Int)) -> Int (loop/recur ((s 0)) :max 1 :on-exhausted (+ s {E(1)}) (if (> s 5) (done s) (continue (+ s 1)))))) (f 3))",
        "", "loop_recur_contract_invalid", "(loop/recur ((s 0))"),
    # A part beside the effect is not simple.
    "match-sibling": ("Tri", f"(record Tri :a {E(7)} :b 1 :c {M})", "", "effect_not_permitted", M),
    "match-sibling-written-first": ("Tri", f"(record Tri :c {M} :a {E(7)} :b 1)", "", "effect_not_permitted", M),
    "if-sibling": ("Tri", f"(record Tri :a {E(7)} :b 1 :c {PURE_IF})", "", "effect_not_permitted", PURE_IF),
    "let-sibling": ("Tri", f"(record Tri :a {E(7)} :b 1 :c {PURE_LET})", "", "effect_not_permitted", PURE_LET),
    "cond-sibling-element": ("List[Int]", f"(list {E(7)} {PURE_COND})", "", "effect_not_permitted", "((> n 5) 0)"),
    "map-sibling-of-a-variant": (
        "Box", f"(variant Box RECT :w {E(7)} :h 0 :k {PURE_MAP})", "", "effect_not_permitted", PURE_MAP),
    "pure-procedure-sibling": ("Pair", f"(record Pair :a {E(7)} :b (add n 1))", "", "effect_not_permitted", "(add n 1)"),
    "function-sibling": ("Pair", f"(record Pair :a {E(7)} :b (inc n))", INC, "effect_not_permitted", "(inc n)"),
    "match-sibling-in-an-inner-list": (
        "Nest", f"(record Nest :xs (list {M}) :p (record Pair :a {E(7)} :b 9))", "", "effect_not_permitted", f"(list {M})"),
    # A map source.
    "conditional-pure-map-source": (
        "List[Int]", f"(list/map ((x (if (> {E(1)} 0) (list 4) (list 6)))) x)", "", "list_map_body_effect_forbidden", "(if"),
    "let-pure-map-source": (
        "List[Int]", f"(list/map ((x (let* ((y {E(1)})) (list y)))) x)", "", "list_map_body_effect_forbidden", "(let*"),
    "conditional-pure-map-source-holding-a-list": (
        "List[Int]", f"(list/map ((x (if (> n 0) (list {E(1)}) (list 2)))) x)", "", "effect_not_permitted", "(if"),
    "conditional-serial-map-source": (
        "List[Int]", f"(list/map-effect ((x (if (> {E(1)} 0) (list 4) (list 6)))) :max 1 {ITEM})", "",
        "list_map_effect_body_unsupported", "(if"),
    "conditional-parallel-map-source": (
        "List[String]", PARALLEL.replace("{v}", f'(if (> n 0) (list {W}) (list "q"))'), "", "effect_not_permitted", "(if"),
    "match-parallel-map-source": (
        "List[String]", PARALLEL.replace("{v}", f'(match (variant Shape CIRCLE :r n) ((CIRCLE c) (list {W})) ((SQUARE q) (list "q")))'),
        "", "effect_not_permitted", "(match"),
    "cond-element-of-a-parallel-map-source": (
        "List[String]", PARALLEL.replace("{v}", f'(list (cond ((> n 5) "q") (else {W})))'), "", "effect_not_permitted", '((> n 5) "q")'),
    "parallel-map-as-a-parallel-map-source": (
        "List[String]", PARALLEL.replace(
            "{v}", f'(list/map-effect ((y (list "w"))) :max 1 :parallel 1 :workspace (string/concat "ws/" y) {W})'),
        "", "list_map_effect_body_unsupported", "(list/map-effect ((y"),
    # A place inside the part that is not simple keeps its own code, as it had; a place refused after
    # one that is admitted reports its own (before E1 the program stopped at the first).
    "pure-map-holding-an-effect-as-a-field": (
        "Nest", f'(record Nest :xs (list/map ((x {E("[1,2]", "List[Int]")})) (+ x 1)) :p (record Pair :a 1 :b 2))', "",
        "list_map_body_effect_forbidden", "(list/map"),
    "field-refused-after-an-admitted-map-source": (
        "Pair", f'(let* ((xs (list/map ((x {E("[1,2]", "List[Int]")})) (+ x 1)))) (record Pair :a {IFE} :b (list/length xs)))',
        "", "effect_not_permitted", IFE),
    # `:on-exhausted`.
    "conditional-on-exhausted": ("Int", EXHAUSTED.replace("{v}", IFE), "", "loop_recur_contract_invalid", IFE),
    "let-on-exhausted": (
        "Int", EXHAUSTED.replace("{v}", f"(let* ((y {E(1)})) (+ y s))"), "", "loop_recur_contract_invalid", "(let*"),
    "match-on-exhausted": ("Int", EXHAUSTED.replace("{v}", MATCH_E), "", "loop_recur_contract_invalid", MATCH_E),
    "record-holding-an-if-on-exhausted": (
        "Int", EXHAUSTED.replace("{v}", f"(+ 0 (let* ((r (record Pair :a {IFE} :b 0))) r.a))"), "", "effect_not_permitted", IFE),
    # A `match` over a variant with a pure `cond` field, an arm holding the effect: an older defect outside these places.
    "match-over-a-cond-field-subject-in-a-field": (
        "Pair", f"(record Pair :a {COND_SUBJECT} :b {E(3)})", "", "effect_not_permitted", COND_SUBJECT),
    "match-over-a-cond-field-subject-in-on-exhausted": (
        "Int", EXHAUSTED.replace("{v}", COND_SUBJECT), "", "loop_recur_contract_invalid", COND_SUBJECT),
}


@pytest.mark.parametrize("case", NOT_SIMPLE)
def test_effect_in_a_value_that_is_not_simple_is_refused_at_the_part_to_bind(tmp_path: Path, case: str) -> None:
    returns, body, decls, code, part = NOT_SIMPLE[case]
    write(tmp_path, returns, body, decls)

    compiled = cli(tmp_path, "compile", "main.orc")

    assert (compiled.returncode, refused_at(tmp_path, part, code) in compiled.stderr, "Traceback" in compiled.stderr) == (
        2, True, False), compiled.stderr
    assert calls(tmp_path) == []


# The rewrite the refusal asks for runs: (returns, body, declarations, value, ordered command log).
BOUND_FIRST = {
    "if-field": ("Pair", f"(let* ((a {IFE})) (record Pair :a a :b 9))", "", {"a": 1, "b": 9}, ["1"]),
    "match-sibling": ("Tri", f"(let* ((c {M})) (record Tri :a {E(7)} :b 1 :c c))", "", {"a": 7, "b": 1, "c": 1}, ["7"]),
    "conditional-pure-map-source": (
        "List[Int]", f"(let* ((src (if (> n 0) (list {E(1)}) (list 2)))) (list/map ((x src)) x))", "", [1], ["1"]),
    "conditional-on-exhausted": (
        "Int", EXHAUSTED.replace("{v}", "(call give-up :s s)"), f"(defworkflow give-up ((s Int)) -> Int (if (> s 5) s {E(1)}))", 1, ["1"]),
    "effectful-procedure-call-field": ("Pair", "(let* ((a (fetch n))) (record Pair :a a :b 9))", FETCH, {"a": 6, "b": 9}, ["6"]),
    "list-in-a-pure-procedure-argument": (
        "List[Int]", f"(let* ((l (list {E(1)} 2))) (let* ((v (addL l))) v))", ADDL, [1, 2], ["1"]),
    "effect-in-a-local-body": (
        "Pair", f"(let-proc ((f ((y Int)) -> Pair (let* ((a {E(1)})) (record Pair :a a :b y)))) (f 3))", "", {"a": 1, "b": 3}, ["1"]),
    # In a `continue` value the source and the value are both bound, as the source's refusal says.
    "conditional-parallel-map-source-in-continue": (
        "Int", "(loop/recur ((s 0)) :max 1 :on-exhausted s (if (= n 7) (done s) "
        f'(let* ((src (if (> n 0) (list {W}) (list "q")))'
        ' (next (list/length (list/map-effect ((x src)) :max 2 :parallel 1 :workspace (string/concat "ws/" x)'
        ' (command-result e :argv ("python" "{probe}" x) :returns String)))))'
        " (continue next))))", "", 1, ["w", "w"]),
    # The open defect of a `continue` value that is an `if` whose branch is an `if` holding an effect.
    "nested-if-continue-value": (
        "Int", "(loop/recur :max 1 :state 0 :on-exhausted s (fn (s) (if (= n 7) (done s) "
        f"(let* ((next (if (> n 0) (if (> n 0) {E(1)} 0) 0))) (continue next)))))", "", 1, ["1"]),
}


@pytest.mark.parametrize("case", BOUND_FIRST)
def test_value_that_is_not_simple_runs_once_its_part_is_bound_first(tmp_path: Path, case: str) -> None:
    returns, body, decls, expected, log = BOUND_FIRST[case]
    (tmp_path / "ws" / "w").mkdir(parents=True)
    write(tmp_path, returns, body, decls)

    result = run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (value(result), calls(tmp_path)) == (expected, log)


# Effect names (frontend specification 16.3): the effects of a simple value are named the same when an
# authored `let*` binds the value first, and under a pure edit beside the effect: another simple sibling,
# or the sibling written first. A holder: (returns, the value over the effect part `{a}` and a pure sibling
# `{s}`, the same with the sibling written first, the same value bound by `let*` first or None).
ONE_ROUND = "(loop/recur :max 1 :state {seed} :on-exhausted s (fn (s) (if (= n 7) (done s) {step})))"
BOX_ARMS = "((RECT r) (+ r.w r.h)) ((NONE z) 0)"
PAIR_SEED = "(record Pair :a 0 :b 0)"
PARALLEL_ONCE = '(list/map-effect ((x {source})) :max 1 :parallel 1 :workspace "ws/w" ' + E(5) + ")"
EFFECT_PARTS = {
    "command": E(1), "operator": f"(+ {E(1)} {E(2)})", "workflow": "(call kid :t n)",
    "effect-argument": f"(call kid :t {E(1)})",
}
HOLDERS = {
    "record": ("Pair", "(record Pair :a {a} :b {s})", "(record Pair :b {s} :a {a})",
               "(let* ((r (record Pair :a {a} :b {s}))) r)"),
    "variant": ("Box", "(variant Box RECT :w {a} :h {s} :k 0)", "(variant Box RECT :h {s} :w {a} :k 0)",
                "(let* ((v (variant Box RECT :w {a} :h {s} :k 0))) v)"),
    "list": ("List[Int]", "(list {a} {s})", "(list {s} {a})", "(let* ((l (list {a} {s}))) l)"),
    "nested-constructor": (
        "Nest", "(record Nest :xs (list {s}) :p (record Pair :a {a} :b 9))",
        "(record Nest :p (record Pair :b 9 :a {a}) :xs (list {s}))",
        "(let* ((r (record Nest :xs (list {s}) :p (record Pair :a {a} :b 9)))) r)"),
    "match-subject": (
        "Int", f"(match (variant Box RECT :w {{a}} :h {{s}} :k 0) {BOX_ARMS})",
        f"(match (variant Box RECT :h {{s}} :w {{a}} :k 0) {BOX_ARMS})",
        f"(let* ((v (variant Box RECT :w {{a}} :h {{s}} :k 0))) (match v {BOX_ARMS}))"),
    "continue": (
        "Pair", ONE_ROUND.format(seed=PAIR_SEED, step="(continue (record Pair :a {a} :b {s}))"),
        ONE_ROUND.format(seed=PAIR_SEED, step="(continue (record Pair :b {s} :a {a}))"),
        ONE_ROUND.format(seed=PAIR_SEED, step="(let* ((next (record Pair :a {a} :b {s}))) (continue next))")),
    "pure-map-source": (
        "List[Int]", "(list/map ((x (list {a} {s}))) (+ x 1))", "(list/map ((x (list {s} {a}))) (+ x 1))",
        "(let* ((src (list {a} {s}))) (list/map ((x src)) (+ x 1)))"),
    "serial-map-source": (
        "List[Int]", f"(list/map-effect ((x (list {{a}} {{s}}))) :max 2 {E(5)})",
        f"(list/map-effect ((x (list {{s}} {{a}}))) :max 2 {E(5)})",
        f"(let* ((src (list {{a}} {{s}}))) (list/map-effect ((x src)) :max 2 {E(5)}))"),
    "parallel-map-source": (
        "List[Int]", PARALLEL_ONCE.replace("{source}", "(list (record Pair :a {a} :b {s}))"),
        PARALLEL_ONCE.replace("{source}", "(list (record Pair :b {s} :a {a}))"),
        "(let* ((src (list (record Pair :a {a} :b {s})))) " + PARALLEL_ONCE.replace("{source}", "src") + ")"),
    # `:on-exhausted` is evaluated where it stands: there is no place to bind it first.
    "on-exhausted": ("Int", EXHAUSTED.replace("{v}", "(+ {a} {s})"), EXHAUSTED.replace("{v}", "(+ {s} {a})"), None),
}
STABLE_NAMES = [(holder, part) for holder in HOLDERS for part in ("command", "operator", "workflow")] + [
    ("record", "effect-argument"), ("pure-map-source", "effect-argument")]


@pytest.mark.parametrize(("holder", "part"), STABLE_NAMES)
def test_effects_of_a_simple_value_are_named_the_same_bound_or_not_and_under_a_pure_edit(
        tmp_path: Path, holder: str, part: str) -> None:
    returns, written, sibling_first, bound = HOLDERS[holder]
    programs = {"written": (written, "9"), "another-sibling": (written, "(+ n 1)"), "sibling-first": (sibling_first, "9")}
    if bound is not None:
        programs["bound"] = (bound, "9")
    names = {}
    for label, (template, sibling) in programs.items():
        (tmp_path / label / "ws" / "w").mkdir(parents=True)
        body = template.replace("{a}", EFFECT_PARTS[part]).replace("{s}", sibling)
        result = run(write(tmp_path / label, returns, body, KID))
        assert result.returncode == 0, result.stderr
        names[label] = started(result.stderr)

    assert names["written"] and all(found == names["written"] for found in names.values()), names


# A place bound before a call names its effects as the place written alone does: by ordinal. Written inside
# the call's argument it is refused (the rows of `NOT_SIMPLE`), since a pure callee is inlined and the
# effect then took the name of the binding the call stood in.
BOUND_BEFORE_A_CALL = {
    "pure-procedure-whole-result": ("List[Int]", "(let* ((l {place})) (addL l))", "(list {e1} 2)"),
    "pure-procedure-let-binding": ("List[Int]", "(let* ((l {place})) (let* ((v (addL l))) v))", "(list {e1} 2)"),
    "pure-procedure-under-an-operator": ("Int", "(let* ((l {place})) (list/length (addL l)))", "(list {e1} 2)"),
    "pure-procedure-in-a-continue-value": (
        "Int", "(loop/recur ((s 0)) :max 1 :on-exhausted s (if (= n 7) (done s)"
        " (let* ((l {place})) (continue (list/length (addL l))))))", "(list {e1} 2)"),
    "pure-procedure-result-as-a-serial-map-source": (
        "List[Int]", "(let* ((l {place})) (let* ((src (addL l))) (list/map-effect ((x src)) :max 3 {item})))", "(list {e1} 2)"),
    "record-through-a-pure-procedure": ("Pair", "(let* ((r {place})) (let* ((v (same-pair r))) v))", "(record Pair :a {e1} :b 2)"),
}
SAME_PAIR = "(defproc same-pair ((p Pair)) -> Pair p)"


@pytest.mark.parametrize("case", BOUND_BEFORE_A_CALL)
def test_place_bound_before_a_procedure_call_names_its_effect_by_ordinal(tmp_path: Path, case: str) -> None:
    returns, body, place = BOUND_BEFORE_A_CALL[case]
    alone = run(write(tmp_path / "alone", "Int", f"(let* ((v {place})) 0)".replace("{e1}", E(1))))
    bound = run(write(tmp_path / "bound", returns,
                      body.replace("{place}", place).replace("{e1}", E(1)).replace("{item}", ITEM), ADDL + SAME_PAIR))

    assert (alone.returncode, bound.returncode) == (0, 0), alone.stderr + bound.stderr
    assert started(bound.stderr)[0].rsplit(" / ", 1)[-1] == started(alone.stderr)[0] == "#1"


def test_path_child_effect_is_named_the_same_bound_or_not(tmp_path: Path) -> None:
    child = f'(path/join-under Report (string/concat {W} "x"))'
    names = [started(run(write(tmp_path / label, "Report", body)).stderr)
             for label, body in (("written", child), ("bound", f"(let* ((p {child})) p)"))]

    assert names == [["#1"], ["#1"]]


def test_effect_bound_by_a_name_takes_that_name(tmp_path: Path) -> None:
    source = E("[1,2]", "List[Int]")
    names = [started(run(write(tmp_path / label, "List[Int]", body)).stderr) for label, body in (
        ("written", f"(list/map ((x {source})) (+ x 1))"), ("bound", f"(let* ((src {source})) (list/map ((x src)) (+ x 1)))"))]

    assert names == [["#1"], ["src"]]


def test_map_bound_by_let_names_its_steps_under_the_binding_whatever_its_source_holds(tmp_path: Path) -> None:
    names = {}
    for label, source in (("pure-source", '(list "w")'), ("source-holding-an-effect", f"(list {W})")):
        (tmp_path / label / "ws" / "w").mkdir(parents=True)
        body = f"(let* ((m {PARALLEL_ONCE.replace('{source}', source)})) m)"
        names[label] = started(run(write(tmp_path / label, "List[Int]", body)).stderr)

    assert names == {"pure-source": ["m / body / par-map:x[0] / #1"],
                     "source-holding-an-effect": ["m / body / #1", "m / body / par-map:x[0] / #1"]}


# Outside the places E1 opened, two older cases move an effect's name under a pure edit (frontend
# specification 16.3), and `main` before E1 gives the same names. Each row: (whether the names move, the
# program over `{x}`, `{x}` before the edit, `{x}` after it).
OPERATOR, PROCEDURE = "(+ {e1} {x})", "(add {e1} {x})"
ONE_ROUND_DONE = "(loop/recur :max 1 :state 0 :on-exhausted s (fn (s) (if (= n 7) (done s) (done {v}))))"
LET_BOUND = "(let* ((w {v})) (+ w {e3}))"
# 1. A pure `match` inside another operand of an operator or pure-procedure application that holds an effect.
MATCH_IN_AN_APPLICATION = {
    "let-binding": (True, LET_BOUND.replace("{v}", OPERATOR), "1", M),
    "let-binding-of-a-procedure-application": (True, LET_BOUND.replace("{v}", PROCEDURE), "1", M),
    "let-binding-match-under-a-pure-if": (True, LET_BOUND.replace("{v}", OPERATOR), "1", f"(if (> n 0) {M} 0)"),
    "let-binding-match-under-a-pure-let": (True, LET_BOUND.replace("{v}", OPERATOR), "1", f"(let* ((q {M})) q)"),
    "let-binding-match-in-a-procedure-argument": (True, LET_BOUND.replace("{v}", OPERATOR), "1", f"(add {M} 0)"),
    "let-binding-match-under-an-operator": (True, LET_BOUND.replace("{v}", OPERATOR), "1", f"(* 2 {M})"),
    "let-binding-of-a-procedure-application-match-under-an-operator": (
        False, LET_BOUND.replace("{v}", PROCEDURE), "1", f"(* 2 {M})"),
    "let-binding-application-in-a-record-update-field": (
        True, "(let* ((p (record Pair :a 0 :b 0))) (+ 0 (let* ((q (record-update p :a " + OPERATOR + "))) q.a)))", "1", M),
    "let-binding-application-under-an-operator": (True, LET_BOUND.replace("{v}", f"(* 2 {OPERATOR})"), "1", M),
    "loop-state": (True, f"(loop/recur :max 1 :state {OPERATOR} :on-exhausted s (fn (s) (done s)))", "1", M),
    "loop-max": (True, f"(loop/recur :max {OPERATOR} :state 0 :on-exhausted s (fn (s) (if (= n 7) (done s) (continue (+ s 1)))))", "1", M),
    "done-value": (True, ONE_ROUND_DONE.replace("{v}", OPERATOR), "1", M),
    "procedure-argument": (True, f"(add {OPERATOR} 0)", "1", M),
    "workflow-argument": (True, f"(call same :t {OPERATOR})", "1", M),
    "command-argument": (True, '(command-result e :argv ("python" "{probe}" ' + OPERATOR + ") :returns Int)", "1", M),
    "procedure-application-as-an-operator-operand": (True, f"(* 2 {PROCEDURE})", "1", M),
    "procedure-application-in-an-if-condition": (True, f"(if (> {PROCEDURE} 0) 7 8)", "1", M),
    "operator-application-as-an-operator-operand": (False, f"(* 2 {OPERATOR})", "1", M),
    "operator-application-in-an-if-condition": (False, f"(if (> {OPERATOR} 0) 7 8)", "1", M),
    "whole-result": (False, OPERATOR, "1", M),
    "whole-result-of-a-procedure-application": (False, PROCEDURE, "1", M),
    "let-body": (False, f"(let* ((p 5)) {OPERATOR})", "1", M),
    "if-branch": (False, f"(if (> n 0) {OPERATOR} 0)", "1", M),
    "match-arm": (False, f"(match (variant Shape CIRCLE :r n) ((CIRCLE c) {OPERATOR}) ((SQUARE q) 0))", "1", M),
    "let-proc-local-argument": (True, "(let-proc ((f ((y Int)) -> Int (+ y 1))) (f " + OPERATOR + "))", "1", M),
    "first-and-operand": (True, f"(and (> {OPERATOR} 0) true)", "1", M),
    "later-and-operand": (False, f"(and (> n 0) (> {OPERATOR} 0))", "1", M),
    "continue-value": (False, "(loop/recur ((s 0)) :max 1 :on-exhausted s (if (= n 7) (done s) (continue " + OPERATOR + ")))", "1", M),
    "list-append-operand": (False, f"(list/length (list/append (list 1) {OPERATOR}))", "1", M),
    "cond-branch": (False, f"(cond ((> n 0) {OPERATOR}) (else 0))", "1", M),
    "let-binding-pure-if-without-a-match": (False, LET_BOUND.replace("{v}", OPERATOR), "1", "(if (> n 0) 1 0)"),
    "let-binding-pure-procedure-without-a-match": (False, LET_BOUND.replace("{v}", OPERATOR), "1", "(add 1 0)"),
}
# 2. An `if` or `cond` with an effect in a branch, an operand of an operator, whose condition holds more
# than names, literals and operators.
IF_E = "(if (= {x} 1) {e1} 0)"
CONDITION_OF_AN_OPERAND_IF = {
    "pure-procedure-call": (True, f"(* 2 {IF_E})", "n", "(add n 0)"),
    "pure-if": (True, f"(* 2 {IF_E})", "n", "(if (> n 0) n 0)"),
    "pure-let": (True, f"(* 2 {IF_E})", "n", "(let* ((q n)) q)"),
    "pure-cond": (True, f"(* 2 {IF_E})", "n", "(cond ((> n 5) 0) (else n))"),
    "pure-match": (True, f"(* 2 {IF_E})", "n", M),
    "function-application": (True, f"(* 2 {IF_E})", "n", "(same-int n)"),
    "and-of-plain-comparisons": (True, "(* 2 (if {x} {e1} 0))", "(= n 1)", "(and (= n 1) true)"),
    "not": (False, "(* 2 (if {x} {e1} 0))", "(= n 1)", "(not (= n 2))"),
    "cond-operand": (True, "(* 2 (cond ((= {x} 1) {e1}) (else 0)))", "n", "(add n 0)"),
    "operator-application-let-bound": (True, LET_BOUND.replace("{v}", f"(* 2 {IF_E})"), "n", "(add n 0)"),
    "operator": (False, f"(* 2 {IF_E})", "n", "(+ n 0)"),
    "list-length": (False, f"(* 2 {IF_E})", "n", "(list/length (list n))"),
    "operator-application-in-an-if-condition": (False, f"(if (> (* 2 {IF_E}) 0) 7 8)", "n", "(add n 0)"),
    "if-as-the-whole-result": (False, IF_E, "n", "(add n 0)"),
    "if-as-a-let-binding": (False, LET_BOUND.replace("{v}", IF_E), "n", "(add n 0)"),
    "if-as-a-procedure-argument": (False, f"(add {IF_E} 0)", "n", "(add n 0)"),
    "if-as-a-workflow-argument": (False, f"(call same :t {IF_E})", "n", "(add n 0)"),
    "if-as-a-loop-state": (False, f"(loop/recur :max 1 :state {IF_E} :on-exhausted s (fn (s) (done s)))", "n", "(add n 0)"),
    "if-as-a-done-value": (False, ONE_ROUND_DONE.replace("{v}", IF_E), "n", "(add n 0)"),
}
SAME_INT = "(defun same-int ((x Int)) -> Int x)"
PURE_EDIT_RETURNS = {"match/first-and-operand": "Bool", "match/later-and-operand": "Bool"}
PURE_EDITS = {f"{family}/{case}": row for family, rows in (
    ("match", MATCH_IN_AN_APPLICATION), ("condition", CONDITION_OF_AN_OPERAND_IF)) for case, row in rows.items()}


@pytest.mark.parametrize("case", PURE_EDITS)
def test_pure_edit_outside_the_opened_places_moves_effect_names_only_as_stated(tmp_path: Path, case: str) -> None:
    moves, body, before, after = PURE_EDITS[case]
    names = []
    for label, x in (("before", before), ("after", after)):
        result = run(write(tmp_path / label, PURE_EDIT_RETURNS.get(case, "Int"),
                           body.replace("{e1}", E(1)).replace("{e3}", E(3)).replace("{x}", x), SAME + SAME_INT))
        assert result.returncode == 0, result.stderr
        names.append(started(result.stderr))

    assert (names[0] != names[1]) == moves, names


# A `continue` value that is a simple value holding an effect is bound first and runs; so does a value
# whose inner `if` calls a workflow that holds no effect, as before E1. One that holds an effect under
# control below its top (an operator, a `record-update`, a `let*` value) is refused with the rewrite to
# bind it first. Every one runs in every other value position; `:on-exhausted` takes the simple ones.
CONTINUE_SHAPES = {
    "record-effects": ("Pair", PAIR_SEED, f"(record Pair :a {E(1)} :b {E(2)})", {"a": 1, "b": 2}, ["1", "2"], ""),
    "list-effects": ("List[Int]", "(list 0)", f"(list {E(1)} {E(2)})", [1, 2], ["1", "2"], ""),
    "path-effect": ("Report", '(path/join-under Report "z")', f'(path/join-under Report {E("x", "String")})',
                    "artifacts/work/x", ["x"], ""),
    "map-source-effect": ("List[Int]", "(list 0)", f"(list/map ((x (list {E(1)}))) x)", [1], ["1"], ""),
    "record-workflow-call": ("Pair", PAIR_SEED, "(record Pair :a (call kid :t n) :b 9)", {"a": 8, "b": 9}, ["8"], KID),
    "record-update-effect": ("Pair", PAIR_SEED, f"(record-update (record Pair :a 0 :b 9) :a {E(1)})",
                             {"a": 1, "b": 9}, ["1"], ""),
    "match-arm-if": ("Int", "0", f"(match (variant Shape CIRCLE :r n) ((CIRCLE c) {IFE}) ((SQUARE q) 0))", 1, ["1"], ""),
    "nested-if-pure-procedure": ("Int", "0", "(if (> n 0) (if (> n 0) (add n 0) 0) 0)", 1, [], ""),
    "nested-if-pure-workflow": ("Int", "0", "(if (> n 0) (if (> n 0) (call same :t 1) 0) 0)", 1, [], SAME),
    "cond-pure-workflow": ("Int", "0", "(cond ((> n 5) 0) ((> n 0) (call same :t 1)) (else 2))", 1, [], SAME),
    "nested-if-operator-over-pure-workflow": (
        "Int", "0", "(if (> n 0) (if (> n 0) (+ 1 (call same :t 1)) 0) 0)", 2, [], SAME),
    # Refused: a `compiler_defect` before effects were admitted in fields.
    "operator-if": ("Int", "0", f"(+ {IFE} 9)", 10, ["1"], ""),
    "record-update-if": ("Pair", PAIR_SEED, f"(record-update (record Pair :a 0 :b 9) :a {IFE})",
                         {"a": 1, "b": 9}, ["1"], ""),
    "let-then-record": ("Pair", PAIR_SEED, f"(let* ((v {IFE})) (record Pair :a v :b 9))",
                        {"a": 1, "b": 9}, ["1"], ""),
}
REFUSED_IN_CONTINUE = ("operator-if", "record-update-if", "let-then-record")
# `:on-exhausted` takes these: the simple values, and the value that holds no effect at all.
SIMPLE_CONTINUE_SHAPES = ("record-effects", "list-effects", "path-effect", "record-workflow-call")
# `:on-exhausted` refuses the others under its own code, or under that of a place inside the value.
ON_EXHAUSTED_CODE = {"map-source-effect": "effect_not_permitted"}
VALUE_POSITIONS = {
    "let-then-continue": ONE_ROUND.replace("{step}", "(let* ((next {v})) (continue next))"),
    "done": "(loop/recur :max 1 :state {seed} :on-exhausted s (fn (s) (done {v})))",
    "state": "(loop/recur :max 1 :state {v} :on-exhausted s (fn (s) (done s)))",
    "on-exhausted": "(loop/recur :max 1 :state {seed} :on-exhausted {v} (fn (s) (if (= n 7) (done s) (continue s))))",
    "workflow-return": "{v}",
    "procedure-return": "(mk n)",
    "let-binding": "(let* ((v {v})) v)",
}


@pytest.mark.parametrize("shape", [shape for shape in CONTINUE_SHAPES if shape not in REFUSED_IN_CONTINUE])
def test_continue_value_holding_an_effect_in_a_value_runs(tmp_path: Path, shape: str) -> None:
    returns, seed, value_expr, expected, log, decls = CONTINUE_SHAPES[shape]
    write(tmp_path, returns, ONE_ROUND.format(seed=seed, step=f"(continue {value_expr})"), decls)

    result = run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (value(result), calls(tmp_path)) == (expected, log)


def test_binder_form_continue_value_whose_inner_if_calls_a_pure_workflow_runs(tmp_path: Path) -> None:
    write(tmp_path, "Int", "(loop/recur ((s 0)) :max 1 :on-exhausted s (if (= n 7) (done s) "
          "(continue (if (> n 0) (if (> n 0) (call same :t 1) 0) 0))))", SAME)

    result = run(tmp_path)

    assert (result.returncode, value(result), calls(tmp_path)) == (0, 1, []), result.stderr


@pytest.mark.parametrize("shape", REFUSED_IN_CONTINUE)
def test_continue_value_with_an_effect_under_control_below_its_top_is_refused(tmp_path: Path, shape: str) -> None:
    returns, seed, value_expr, _, _, decls = CONTINUE_SHAPES[shape]
    write(tmp_path, returns, ONE_ROUND.format(seed=seed, step=f"(continue {value_expr})"), decls)

    compiled = cli(tmp_path, "compile", "main.orc")

    assert (compiled.returncode, compiled.stderr.count("[effect_not_permitted]"),
            refused_at(tmp_path, value_expr) in compiled.stderr) == (2, 1, True), compiled.stderr


def test_inner_loop_continue_value_with_an_effect_under_control_is_refused(tmp_path: Path) -> None:
    inner = ONE_ROUND.format(seed="0", step=f"(continue (+ {IFE} 9))")
    outer = f"(loop/recur :max 1 :state 0 :on-exhausted t (fn (t) (if (= n 7) (done {inner}) (continue t))))"
    write(tmp_path, "Int", outer)

    compiled = cli(tmp_path, "compile", "main.orc")

    assert (compiled.returncode, "[effect_not_permitted]" in compiled.stderr) == (2, True), compiled.stderr


@pytest.mark.parametrize("position", VALUE_POSITIONS)
@pytest.mark.parametrize("shape", CONTINUE_SHAPES)
def test_continue_value_runs_in_every_other_value_position(tmp_path: Path, shape: str, position: str) -> None:
    returns, seed, value_expr, expected, log, decls = CONTINUE_SHAPES[shape]
    if position == "procedure-return":
        decls += f"(defproc mk ((n Int)) -> {returns} {value_expr})"
    write(tmp_path, returns, VALUE_POSITIONS[position].format(seed=seed, v=value_expr), decls)

    result = run(tmp_path)

    if position == "on-exhausted" and shape not in (*SIMPLE_CONTINUE_SHAPES, "nested-if-pure-procedure"):
        code = ON_EXHAUSTED_CODE.get(shape, "loop_recur_contract_invalid")
        assert (result.returncode, f"[{code}]" in result.stderr) == (2, True), result.stderr
        return
    assert result.returncode == 0, result.stderr
    assert (value(result), calls(tmp_path)) == (expected, log)


RECORD_UPDATE_OF_STATE = {"bare-effect": (E(1), 0), "effect-under-if": (IFE, 2)}


@pytest.mark.parametrize("case", RECORD_UPDATE_OF_STATE)
def test_continue_record_update_of_the_state_runs_with_a_bare_effect_and_is_refused_under_if(
        tmp_path: Path, case: str) -> None:
    field, exit_code = RECORD_UPDATE_OF_STATE[case]
    write(tmp_path, "Pair", ONE_ROUND.format(seed="(record Pair :a 0 :b 9)", step=f"(continue (record-update s :a {field}))"))

    result = run(tmp_path)

    assert (result.returncode, "[effect_not_permitted]" in result.stderr) == (exit_code, exit_code == 2), result.stderr


# A parallel map whose source holds an effect, inside a loop body (N3).
PAR_IN_LOOP = (f'(list/map-effect ((x (list {W} "q"))) :max 2 :parallel 1 :workspace (string/concat "ws/" x) '
               '(command-result e :argv ("python" "{probe}" (string/concat "b" x)) :returns String))')
LOOP_BODIES = {
    "continue-length": ("Int", f"(if (= n 7) (done s) (continue (list/length {PAR_IN_LOOP})))", 2),
    "done-whole": ("List[String]", f"(done {PAR_IN_LOOP})", ["bw", "bq"]),
    "let-statement": ("Int", f"(let* ((m {PAR_IN_LOOP})) (done (list/length m)))", 2),
    "done-in-branch": ("Int", f"(if (> n 0) (done (list/length {PAR_IN_LOOP})) (continue s))", 2),
}


@pytest.mark.parametrize("case", LOOP_BODIES)
def test_parallel_map_with_an_effectful_source_in_a_loop_body_runs(tmp_path: Path, case: str) -> None:
    for name in ("w", "q"):
        (tmp_path / "ws" / name).mkdir(parents=True)
    returns, body, expected = LOOP_BODIES[case]
    seed = '(list "a")' if returns == "List[String]" else "0"
    write(tmp_path, returns, f"(loop/recur :max 1 :state {seed} :on-exhausted s (fn (s) {body}))")

    result = run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (value(result), calls(tmp_path)) == (expected, ["w", "bw", "bq"])


# A parallel map whose binder a macro template introduces has no authored label (an older defect: with a
# pure source it does not build). With an effect in its source it stays refused, under the code it had.
ITEM_PROC = ('(defproc item ((x String)) -> String (command-result e :argv ("python" "{probe}" (string/concat "b" x))'
             " :returns String))")
PAR_LEN = ("(defmacro par-len (f src) (list/length (list/map-effect ((x src)) :max 2 :parallel 1"
           ' :workspace (string/concat "ws/" x) (f x))))')
PAR_NAMED = ("(defmacro par-named (nm f src) (list/length (list/map-effect ((nm src)) :max 2 :parallel 1"
             ' :workspace (string/concat "ws/" nm) (f nm))))')
TEMPLATE_BINDER = {
    "workflow-body": (f'(par-len item (list {W} "q"))', "effect_not_permitted"),
    "continue": (ONE_ROUND.format(seed="0", step=f'(continue (par-len item (list {W} "q")))'), "effect_not_permitted"),
    "done": (f'(loop/recur :max 1 :state 0 :on-exhausted s (fn (s) (done (par-len item (list {W} "q")))))',
             "effect_not_permitted"),
    "source-is-the-effect": (
        f'''(par-len item {E('[\\"w\\",\\"q\\"]', "List[String]")})''', "list_map_effect_body_unsupported"),
}


@pytest.mark.parametrize("case", TEMPLATE_BINDER)
def test_parallel_map_with_a_template_binder_and_an_effectful_source_stays_refused(tmp_path: Path, case: str) -> None:
    body, code = TEMPLATE_BINDER[case]
    write(tmp_path, "Int", body, ITEM_PROC + PAR_LEN)

    compiled = cli(tmp_path, "compile", "main.orc")

    assert (compiled.returncode, f"[{code}]" in compiled.stderr, "Traceback" in compiled.stderr) == (2, True, False), compiled.stderr


def test_parallel_map_whose_binder_is_a_macro_argument_takes_an_effectful_source(tmp_path: Path) -> None:
    for name in ("w", "q"):
        (tmp_path / "ws" / name).mkdir(parents=True)
    write(tmp_path, "Int", ONE_ROUND.format(seed="0", step=f'(continue (par-named y item (list {W} "q")))'),
          ITEM_PROC + PAR_NAMED)

    result = run(tmp_path)

    assert (result.returncode, value(result), calls(tmp_path)) == (0, 2, ["w", "bw", "bq"]), result.stderr


def test_parallel_map_with_a_pure_conditional_source_runs(tmp_path: Path) -> None:
    (tmp_path / "ws" / "w").mkdir(parents=True)
    item = '(command-result e :argv ("python" "{probe}" x) :returns String)'
    write(tmp_path, "List[String]", '(list/map-effect ((x (if (> n 0) (list "w") (list "q")))) :max 2 :parallel 1 '
          f':workspace (string/concat "ws/" x) {item})')

    result = run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (value(result), calls(tmp_path)) == (["w"], ["w"])


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
    # The parallel map's body is pure; only its source's command exceeds the procedure's declared effects.
    "parallel-source-effect-beyond-declared-effects": (
        "Int", "(bad n)",
        f'(defproc bad ((k Int)) -> Int :effects () (list/length (list/map-effect ((x (list {E(1)}))) :max 1'
        f' :parallel 1 :workspace "ws/w" (add x k))))',
        "procedure_effect_ceiling_exceeded"),
    "defun-body": ("Pair", "(bad n)", f"(defun bad ((x Int)) -> Pair (record Pair :a {E(1)} :b x))",
                   "pure_function_has_effect"),
    # A record or list holding an effect in a pure body keeps the code it had before these places took effects.
    "list-map-body": ("List[Pair]", f"(list/map ((x (list 1 2))) (record Pair :a {E(1)} :b x))", "",
                      "effect_not_permitted"),
    "list-map-body-list": ("List[List[Int]]", f"(list/map ((x (list 1 2))) (list x {E(1)}))", "",
                           "effect_not_permitted"),
    "list-map-body-operator": ("List[Int]", f"(list/map ((x (list 1 2))) (+ x {E(1)}))", "",
                               "list_map_body_effect_forbidden"),
    "on-exhausted-in-list-map-body": (
        "List[Int]", f"(list/map ((x (list 1 2))) (loop/recur :max 1 :state 0 :on-exhausted (+ s {E(1)}) (fn (s) (if (> s 5) (done s) (continue (+ s 1))))))",
        "", "loop_recur_contract_invalid"),
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


def test_defect_inside_a_continue_value_is_not_reported_as_a_refusal_to_bind(tmp_path: Path) -> None:
    """Only a value whose own body branches is refused with the advice to bind it; another failure inside
    the value (here the open defect of defect backlog row D5-binder-hidden, a read of the subject where a binding
    in the arm hides the arm's binder) keeps its own report."""

    value = f"(match u ((A a) (let* ((a 5)) (variant U A :n (+ a u.n {E(1)})))) ((B b) u))"
    write(tmp_path, "U", "(loop/recur ((u (variant U A :n n))) :max 1 :on-exhausted u "
          f"(if (= n 7) (done u) (continue {value})))", "(defunion U (A (n Int)) (B (why String)))")

    compiled = cli(tmp_path, "compile", "main.orc")

    assert (compiled.returncode != 0, "[effect_not_permitted]" in compiled.stderr, "[compiler_defect]" in compiled.stderr) == (
        True, False, True), compiled.stderr


def test_serial_map_in_a_continue_value_keeps_the_code_of_its_source(tmp_path: Path) -> None:
    source = E("[1,2]", "List[Int]")
    write(tmp_path, "Int", "(loop/recur ((s 0)) :max 1 :on-exhausted s (if (= n 7) (done s) "
          f"(continue (list/length (list/map-effect ((x {source})) :max 3 {ITEM})))))")

    compiled = cli(tmp_path, "compile", "main.orc")

    assert (compiled.returncode, "[list_map_effect_body_unsupported]" in compiled.stderr) == (2, True), compiled.stderr


# The examples of the design's section 4 (docs/design/workflow_lisp_surface_coherence.md), as programs.
DESIGN_DECLS = (f"(defworkflow fetch ((key Int)) -> Int (+ key {E(7)}))"
                f"(defworkflow give-up ((s Int)) -> Int (+ s {E(77)}))"
                "(defworkflow step ((s Int)) -> Int (+ s 6))")
DESIGN_EXAMPLES = {
    "command-in-a-field": ("Pair", f"(record Pair :a {E(1)} :b 0)", {"a": 1, "b": 0}, ["1"]),
    "workflow-calls-in-a-list": ("List[Int]", "(list (call fetch :key 1) (call fetch :key 2))", [8, 9], ["7", "7"]),
    "exhaustion-calls-a-workflow": (
        "Int", "(loop/recur ((s 0)) :max 1 :on-exhausted (call give-up :s s) (if (> s 9) (done s) (continue (call step :s s))))",
        83, ["77"]),
    "exhaustion-not-reached": (
        "Int", "(loop/recur ((s 0)) :max 3 :on-exhausted (call give-up :s s) (if (> s 5) (done s) (continue (call step :s s))))",
        6, []),
    "match-as-an-operand": ("Int", f"(+ 1 {M})", 2, []),
}


@pytest.mark.parametrize("case", DESIGN_EXAMPLES)
def test_design_example_runs(tmp_path: Path, case: str) -> None:
    returns, body, expected, log = DESIGN_EXAMPLES[case]
    write(tmp_path, returns, body, DESIGN_DECLS)

    result = run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (value(result), calls(tmp_path)) == (expected, log)
