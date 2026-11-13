"""Callables, surface coherence change C1 (docs/design/workflow_lisp_surface_coherence.md §6).

A `let-proc` local with a signature is called by name and builds the program of
its alias call; the misuses of the two calling conventions, a local calling a
sibling or itself, and a workflow reaching itself each get one diagnostic
through the public compile command.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.cli.commands.compile import compile_workflow
from orchestrator.cli.main import create_parser
from tests.test_workflow_evaluated_resume_kills import (
    _cli,
    _env,
    _kill_after_first_commit,
    _rows,
    _run_root,
    _snapshot,
)


def _source(definitions: str, body: str, returns: str = "Int") -> str:
    return f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule m)
  (export run)
  {definitions}
  (defworkflow run ((n Int)) -> {returns}
    {body}))
'''


EMIT = '(command-result emit :argv ("python" "emit.py" x) :returns Int)'
COMMANDS = {"emit": {"stable_command": ["python", "emit.py"], "closure": ["emit.py"]}}
EMIT_PY = (
    "import json, os, sys\nfrom pathlib import Path\n"
    'Path("calls.log").open("a", encoding="utf-8").write(sys.argv[1] + "\\n")\n'
    'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(sys.argv[1], encoding="utf-8")\n'
)


def _compile(root: Path, source: str, monkeypatch, capsys) -> tuple[int, dict]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "m.orc").write_text(source, encoding="utf-8")
    (root / "commands.json").write_text(json.dumps(COMMANDS), encoding="utf-8")
    (root / "emit.py").write_text(EMIT_PY, encoding="utf-8")
    monkeypatch.chdir(root)
    args = create_parser().parse_args(
        ["compile", "m.orc", "--command-boundaries-file", "commands.json", "--diagnostics-json"]
    )
    status = compile_workflow(args)
    return status, json.loads(capsys.readouterr().out)


def _program(root: Path, source: str, monkeypatch, capsys) -> tuple[str, list]:
    status, payload = _compile(root, source, monkeypatch, capsys)
    assert status == 0, payload
    program = root / ".orchestrate" / "build" / payload["build_key"] / "closed_program.json"
    return payload["program_digest"], json.loads(program.read_text(encoding="utf-8"))["sites"]


APPLY = (
    "(defproc apply1 ((f ProcRef[(Int) -> Int]) (x Int)) -> Int (f x)) "
    "(defproc apply-one ((x Int)) -> Int (+ x 1))"
)
IDENT = "(defproc ident :forall (T) ((x T)) -> T x)"
WRAP = "(defproc wrap :forall (T) ((x T) (k Int)) -> Int (let-proc ((b ((y Int)) -> Int (+ y 1))) {}))"
BUMP = "(defmacro with-bump (k body) (let-proc ((bump ((x Int)) -> Int (+ x k))) body))"
EFFECTFUL = f"(let-proc ((f ((x Int)) -> Int {EMIT})) "

# (definitions, or a pair (by name, alias); called by name; the same calls through
# `(let* ((g (proc-ref f))) (g …))`)
SAME_PROGRAM = {
    "effectful-twice": (
        "",
        EFFECTFUL + "(+ (f 1) (f 2)))",
        EFFECTFUL + "(+ (let* ((g (proc-ref f))) (g 1)) (let* ((g (proc-ref f))) (g 2))))",
    ),
    "statement-binding": (
        "",
        EFFECTFUL + "(let* ((a (f 1))) (+ a 1)))",
        EFFECTFUL + "(let* ((a (let* ((g (proc-ref f))) (g 1)))) (+ a 1)))",
    ),
    "single-binding-form": (
        "",
        f"(let-proc (f ((x Int)) -> Int :captures () {EMIT}) (f 1))",
        f"(let-proc (f ((x Int)) -> Int :captures () {EMIT}) (let* ((g (proc-ref f))) (g 1)))",
    ),
    "capture": (
        "",
        "(let-proc ((f ((x Int)) -> Int (+ x n))) (f 1))",
        "(let-proc ((f ((x Int)) -> Int (+ x n))) (let* ((g (proc-ref f))) (g 1)))",
    ),
    "procedure-parameter": (
        APPLY,
        "(let-proc ((f ((p ProcRef[(Int) -> Int]) (x Int)) -> Int (p x))) (f (proc-ref apply-one) n))",
        "(let-proc ((f ((p ProcRef[(Int) -> Int]) (x Int)) -> Int (p x))) "
        "(let* ((g (proc-ref f))) (g (proc-ref apply-one) n)))",
    ),
    "called-and-passed": (
        APPLY,
        "(let-proc ((f ((x Int)) -> Int (+ x n))) (+ (f 1) (apply1 (proc-ref f) 2)))",
        "(let-proc ((f ((x Int)) -> Int (+ x n))) (+ (let* ((g (proc-ref f))) (g 1)) (apply1 (proc-ref f) 2)))",
    ),
    "inside-generic-procedure": (
        (WRAP.format("(b k)"), WRAP.format("(let* ((g (proc-ref b))) (g k))")),
        '(wrap "s" n)',
        '(wrap "s" n)',
    ),
    "into-generic-procedure": (
        IDENT,
        "(let-proc ((f ((x Int)) -> Int (+ x n))) (ident (f 1)))",
        "(let-proc ((f ((x Int)) -> Int (+ x n))) (ident (let* ((g (proc-ref f))) (g 1))))",
    ),
    "macro-expansion": (
        BUMP,
        "(with-bump 5 (bump n))",
        "(with-bump 5 (let* ((g (proc-ref bump))) (g n)))",
    ),
}


@pytest.mark.parametrize("case", sorted(SAME_PROGRAM))
def test_local_called_by_name_builds_the_program_of_its_alias_call(case, tmp_path, monkeypatch, capsys):
    definitions, by_name, alias = SAME_PROGRAM[case]
    named_definitions, alias_definitions = definitions if isinstance(definitions, tuple) else (definitions,) * 2
    named = _program(tmp_path / "named", _source(named_definitions, by_name), monkeypatch, capsys)
    aliased = _program(tmp_path / "alias", _source(alias_definitions, alias), monkeypatch, capsys)

    assert named == aliased


def test_effectful_local_called_twice_runs_in_two_frames(tmp_path, monkeypatch, capsys):
    _, sites = _program(tmp_path, _source("", EFFECTFUL + "(+ (f 1) (f 2)))"), monkeypatch, capsys)

    assert len({json.dumps(site) for site in sites}) == 2


def _refusal(tmp_path, monkeypatch, capsys, definitions: str, body: str, returns: str = "Int") -> dict:
    status, payload = _compile(tmp_path, _source(definitions, body, returns), monkeypatch, capsys)
    assert status == 2, payload
    (diagnostic,) = payload["diagnostics"]
    return diagnostic


DECLARED = (
    "(defun inc ((x Int)) -> Int (+ x 1)) (defproc add ((x Int) (y Int)) -> Int (+ x y)) "
    "(defproc ident :forall (T) ((x T)) -> T x) (defworkflow child ((x Int)) -> Int (+ x 100))"
)

# (definitions, body, code, a fragment of the message that names the fix)
REFUSALS = {
    "local-without-signature": (
        DECLARED, "(let-proc ((f (x) (+ x n))) (f 1))",
        "let_proc_signature_required", "give `f` a signature",
    ),
    "local-calls-earlier-sibling": (
        DECLARED, "(let-proc ((f ((x Int)) -> Int (+ x 1)) (g ((x Int)) -> Int (f x))) (g 1))",
        "let_proc_sibling_call_unsupported", "define `f` with `defproc`",
    ),
    "local-calls-later-sibling": (
        DECLARED, "(let-proc ((g ((x Int)) -> Int (f x)) (f ((x Int)) -> Int (+ x 1))) (g 1))",
        "let_proc_sibling_call_unsupported", "do not see each other",
    ),
    "local-calls-itself": (
        DECLARED, "(let-proc ((f ((x Int)) -> Int (f x))) (f 1))",
        "let_proc_recursive_unsupported", "cannot call itself",
    ),
    "single-binding-local-calls-itself": (
        DECLARED, "(let-proc (f ((x Int)) -> Int :captures () (f x)) (f 1))",
        "let_proc_recursive_unsupported", "cannot call itself",
    ),
    "workflow-called-positionally": (
        DECLARED, "(child n)", "procedure_call_unknown", "`(call child :x …)`",
    ),
    "procedure-called-with-call": (
        DECLARED, "(call add :x n :y 1)", "workflow_call_unknown", "`(add …)`",
    ),
    "function-called-with-call": (
        DECLARED, "(call inc :x n)", "workflow_call_unknown", "`(inc …)`",
    ),
    "local-called-with-call": (
        DECLARED, "(let-proc ((f ((x Int)) -> Int (+ x 1))) (call f :x n))", "workflow_call_unknown", "`(f …)`",
    ),
    "keyword-to-function": (DECLARED, "(inc :x n)", "keyword_argument_invalid", "`(inc …)`"),
    "keyword-to-procedure": (DECLARED, "(add :x n :y 2)", "keyword_argument_invalid", "`(add …)`"),
    "keyword-to-generic-procedure": (DECLARED, "(ident :x n)", "keyword_argument_invalid", "`(ident …)`"),
    "keyword-to-local": (
        DECLARED, "(let-proc ((f ((x Int)) -> Int (+ x 1))) (f :x n))", "keyword_argument_invalid", "`(f …)`",
    ),
    "keyword-to-procedure-parameter": (
        "(defproc apply1 ((f ProcRef[(Int) -> Int]) (x Int)) -> Int (f :x x)) "
        "(defproc inc2 ((x Int)) -> Int (+ x 1))",
        "(apply1 (proc-ref inc2) n)", "keyword_argument_invalid", "`(f …)`",
    ),
    "keyword-as-operand": (DECLARED, "(+ n :x)", "keyword_argument_invalid", "keyword `:x`"),
    "workflow-calls-itself": (
        "(defworkflow rec ((x Int)) -> Int (if (> x 0) (call rec :x (- x 1)) 0))",
        "(call rec :x n)", "workflow_call_cycle", "m::rec -> m::rec",
    ),
    "entry-workflow-calls-itself": (
        "", "(if (> n 0) (call run :n (- n 1)) 0)", "workflow_call_cycle", "m::run -> m::run",
    ),
    "two-workflow-cycle": (
        "(defworkflow a ((x Int)) -> Int (call b :x x)) (defworkflow b ((x Int)) -> Int (call a :x x))",
        "(call a :x n)", "workflow_call_cycle", "m::a -> m::b -> m::a",
    ),
    "three-workflow-cycle": (
        "(defworkflow a ((x Int)) -> Int (call b :x x)) (defworkflow b ((x Int)) -> Int (call c :x x)) "
        "(defworkflow c ((x Int)) -> Int (call a :x x))",
        "(call a :x n)", "workflow_call_cycle", "m::a -> m::b -> m::c -> m::a",
    ),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_callable_misuse_is_one_diagnostic_that_names_the_fix(case, tmp_path, monkeypatch, capsys):
    definitions, body, code, fix = REFUSALS[case]
    diagnostic = _refusal(tmp_path, monkeypatch, capsys, definitions, body)

    assert (diagnostic["code"], fix in diagnostic["message"]) == (code, True), diagnostic


LOCAL = "(let-proc ((f ((x Int)) -> Int (+ x n))) "
HOLDER = "(defrecord Holder (h ProcRef[(Int) -> Int]))"

# The closures boundary: a reference, a local's included, is not a runtime value.
BOUNDARY = {
    "stored-in-record": (HOLDER, LOCAL + "(let* ((r (record Holder :h (proc-ref f)))) 0))",
                         "proc_ref_runtime_transport_forbidden"),
    "stored-in-list": ("", LOCAL + "(let* ((r (list (proc-ref f)))) 0))", "list_collection_contract_unsupported"),
    "returned-from-consumer": ("", LOCAL + "(proc-ref f))", "let_proc_scope_escape"),
    "returned-from-procedure": (
        "(defproc give ((x Int)) -> ProcRef[(Int) -> Int] (let-proc ((f ((y Int)) -> Int (+ y x))) (proc-ref f)))",
        "(let* ((g (give 1))) (g 2))", "let_proc_scope_escape",
    ),
    "passed-to-a-workflow": (
        "(defworkflow takes ((h ProcRef[(Int) -> Int])) -> Int 0)",
        LOCAL + "(call takes :h (proc-ref f)))", "proc_ref_runtime_transport_forbidden",
    ),
}


@pytest.mark.parametrize("case", sorted(BOUNDARY))
def test_local_reference_stays_a_compile_time_name(case, tmp_path, monkeypatch, capsys):
    definitions, body, code = BOUNDARY[case]

    assert _refusal(tmp_path, monkeypatch, capsys, definitions, body)["code"] == code


@pytest.mark.xfail(strict=True, reason="defect on main: a ProcRef chosen by `if` is refused as compiler_defect (KeyError)")
def test_local_reference_chosen_by_if_is_refused_without_a_defect(tmp_path, monkeypatch, capsys):
    body = LOCAL + "(let* ((g (if (> n 0) (proc-ref f) (proc-ref f)))) (g 1)))"

    assert _refusal(tmp_path, monkeypatch, capsys, "", body)["code"] != "compiler_defect"


def _write_run(root: Path, body: str) -> list[str]:
    root.mkdir(parents=True)
    (root / "m.orc").write_text(_source("", body), encoding="utf-8")
    (root / "commands.json").write_text(json.dumps(COMMANDS), encoding="utf-8")
    (root / "emit.py").write_text(EMIT_PY, encoding="utf-8")
    return ["run", "m.orc", "--input", "n=0"]


def _committed(root: Path) -> list[str]:
    return [row["identity"] for row in _rows(_snapshot(_run_root(root)), "committed")]


def test_local_called_by_name_resumes_after_a_kill_with_the_alias_identities(tmp_path):
    alias_root, killed = tmp_path / "alias", tmp_path / "killed"
    alias_args = _write_run(alias_root, EFFECTFUL + "(+ (let* ((g (proc-ref f))) (g 1)) (let* ((g (proc-ref f))) (g 2))))")
    alias = _cli(alias_root, alias_args, _env(alias_root))
    assert alias.returncode == 0, alias.stderr

    args = _write_run(killed, EFFECTFUL + "(+ (f 1) (f 2)))")
    first = _kill_after_first_commit(killed, args, _env(killed))
    resumed = _cli(killed, ["resume", _run_root(killed).name], _env(killed))
    assert resumed.returncode == 0, resumed.stderr

    calls = (killed / "calls.log").read_text(encoding="utf-8").split()
    assert (calls, _committed(killed)[0], _committed(killed), _snapshot(_run_root(killed)).terminal.data["value"]) == (
        ["1", "2"], first, _committed(alias_root), 3,
    )
