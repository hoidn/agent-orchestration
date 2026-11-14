"""One call has one target, whatever the hash seed, the source directory or the macro expansion.

Elaboration picks each procedure call's target from the call edges recorded at its site: span, form path
and expansion stack together. Calls once shared a site, and so a target, in four ways: a procedure
specialized more than once in one call chain (from target 2.39 a procedure's typed body carried its
callees' edges); two expansions of one macro template in one owner (every expansion carries the template's
span); two calls in the body of an inlined pure procedure (the clone gave every node the call's span); and,
from 2.39, two expansions of a macro over a procedure specialized by a `WorkflowRef` (the reference calls
were keyed without the expansion stack). The edges are a hashed set, so in the first three the winner
depended on `PYTHONHASHSEED` and on the absolute source path; in the fourth the last expansion always won.

The in-process tests hold under any seed. The subprocess test builds every program of `SWEEP` under several
fixed seeds, each from two source directories of different depth, and requires one outcome, one program
digest and the value the source means.
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.agent_session_shims import closed_path
from tests.workflow_lisp_closed_program_helpers import build_outcome, crash_signature

REPO = Path(__file__).resolve().parents[1]
CONFIG = {"provider_externs": {"provider": "provider-id"},
          "prompt_externs": {"prompt": {"asset_file": "prompt.md"}}, "command_boundaries": {}}

HEAD = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run) (defrecord Box (n Int))
'''
FOO = "  (defproc foo ((runner WorkflowRef[Box -> Box]) (input Box)) -> Box (call runner :input input))\n"
INVOKE = "  (defproc invoke ((hook ProcRef[Box -> Box]) (input Box)) -> Box (hook input))\n"
INVOKE_ADDS_ONE = ("  (defproc invoke ((hook ProcRef[Box -> Box]) (input Box)) -> Box"
                   " (hook (record Box :n (+ input.n 1))))\n")
PROVIDER = "(provider-result provider :prompt prompt :inputs (input.n) :returns Box)"
LOCAL = "(let-proc ((h ((v Int)) -> Int (loop/recur ((s k)) :max 1 :on-exhausted s (done s)))) (h x))"
INT_HEAD = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
  (defmodule main) (export run)
'''
TWICE = "  (defworkflow run ((n Int)) -> Int (+ (with-loop n 5) (* 100 (with-loop n 7)))))\n"
ADDS_ONE = "((v Int)) -> Int (loop/recur ((s v)) :max 1 :on-exhausted s (done (+ s 1)))"
WORKFLOWS = ('  (defworkflow c1 ((input Box)) -> Box (record Box :n (+ input.n 100)))\n'
             '  (defworkflow c2 ((input Box)) -> Box (record Box :n (+ input.n 200)))\n'
             '  (defworkflow c3 ((input Box)) -> Box (record Box :n (+ input.n 300)))\n'
             '  (defproc runw ((w WorkflowRef[Box -> Box]) (input Box)) -> Box (call w :input input))\n'
             '  (defmacro cw (w v) (runw (workflow-ref w) v))\n')


def _chain(workflow: str, depth: int = 2) -> str:
    """`invoke` bound over `invoke` ... over `foo` bound to `workflow`: `depth - 1` levels of `invoke`."""
    bound = f"(bind-proc (proc-ref foo) :runner (workflow-ref {workflow}))"
    for _ in range(depth - 1):
        bound = f"(bind-proc (proc-ref invoke) :hook {bound})"
    return bound


def _one_chain(invoke: str, depth: int = 2) -> str:
    return (HEAD + "  (defworkflow left ((input Box)) -> Box input)\n" + FOO + invoke
            + f"  (defworkflow run ((input Box)) -> Box\n    (invoke {_chain('left', depth)} input)))\n")


def _workflow_ref_macro(body: str, target: str = "2.40", definitions: str = "") -> str:
    head = HEAD.replace('"2.40"', f'"{target}"')
    return (head + WORKFLOWS + definitions
            + f"  (defworkflow run ((n Int)) -> {'List[Int]' if 'list/map' in body else 'Int'}\n"
            f"    (let* ((input (record Box :n n))) {body})))\n")


def _pure(definitions: str, body: str) -> str:
    return INT_HEAD.replace("TARGET", "2.40") + definitions + f"  (defworkflow run ((n Int)) -> Int {body}))\n"


A_THEN_B = "(let* ((a (cw c1 input)) (b (cw c2 input))) (+ a.n (* 1000 b.n)))"
BOUND_RUNW = ("  (defproc ap ((hook ProcRef[Box -> Box]) (input Box)) -> Box (hook input))\n"
              "  (defmacro ba (w v) (ap (bind-proc (proc-ref runw) :w (workflow-ref w)) v))\n")

# name: (source, (inputs, value) or None when the program calls a provider)
PROGRAMS = {
    "two-provider-chains": (HEAD + f"  (defworkflow left ((input Box)) -> Box\n    {PROVIDER})\n"
        f"  (defworkflow right ((input Box)) -> Box\n    {PROVIDER})\n" + FOO + INVOKE
        + f"  (defworkflow run ((input Box)) -> Box\n    (let* ((a (invoke {_chain('left')} input))\n"
        f"           (b (invoke {_chain('right')} a))) b)))\n", None),
    "one-chain": (_one_chain(INVOKE), ({"input": {"n": 4}}, {"n": 4})),
    "one-chain-adding": (_one_chain(INVOKE_ADDS_ONE), ({"input": {"n": 4}}, {"n": 6})),
    "three-levels-adding": (_one_chain(INVOKE_ADDS_ONE, 3), ({"input": {"n": 4}}, {"n": 7})),
    "two-chains-adding": (HEAD + "  (defworkflow left ((input Box)) -> Box (record Box :n (* input.n 2)))\n"
        "  (defworkflow right ((input Box)) -> Box (record Box :n (+ input.n 10)))\n" + FOO + INVOKE_ADDS_ONE
        + f"  (defworkflow run ((input Box)) -> Box\n    (let* ((a (invoke {_chain('left')} input))\n"
        f"           (b (invoke {_chain('right')} a))) b)))\n", ({"input": {"n": 4}}, {"n": 24})),
    "macro-local": (INT_HEAD.replace("TARGET", "2.40") + f"  (defmacro with-loop (x k)\n    {LOCAL})\n" + TWICE,
        ({"n": 3}, 705)),
    "macro-local-captured": (INT_HEAD.replace("TARGET", "2.40")
        + f"  (defmacro with-loop (x kk)\n    (let* ((k kk)) {LOCAL}))\n" + TWICE, ({"n": 3}, 705)),
    "macro-proc-ref": (_pure("  (defproc one () -> Int 1)\n  (defproc two () -> Int 2)\n"
        "  (defproc apply ((hook ProcRef[() -> Int])) -> Int (hook))\n  (defmacro invoke (h) (apply (proc-ref h)))\n",
        "(+ (invoke one) (* 10 (invoke two)))").replace("((n Int)) -> Int", "() -> Int"), ({}, 21)),
    "macro-generic": (_pure("  (defproc ident :forall (T) ((x T)) -> T x)\n  (defmacro same (x) (ident x))\n",
        '(let* ((s (same "text")) (a (same n))) (+ a 1))'), ({"n": 3}, 4)),
    # A macro over a procedure specialized by a `WorkflowRef` (2.39 and later): each expansion keeps its workflow.
    "workflow-ref-macro-2.39": (_workflow_ref_macro(A_THEN_B, "2.39"), ({"n": 3}, 203103)),
    "workflow-ref-macro": (_workflow_ref_macro(A_THEN_B), ({"n": 3}, 203103)),
    "workflow-ref-macro-reversed": (_workflow_ref_macro(
        "(let* ((b (cw c2 input)) (a (cw c1 input))) (+ a.n (* 1000 b.n)))"), ({"n": 3}, 203103)),
    "workflow-ref-macro-three": (_workflow_ref_macro("(let* ((a (cw c1 input)) (b (cw c2 input)) (c (cw c3 input))) "
        "(+ a.n (* 1000 b.n) (* 1000000 c.n)))"), ({"n": 3}, 303203103)),
    "workflow-ref-macro-in-procedure": (_workflow_ref_macro("(both input)",
        definitions=f"  (defproc both ((input Box)) -> Int {A_THEN_B})\n"), ({"n": 3}, 203103)),
    "workflow-ref-macro-in-map": (_workflow_ref_macro("(list/map-effect ((i (list 1 2))) :max 2 (let* ((x (record Box :n i)) "
        "(a (cw c1 x)) (b (cw c2 x))) (+ a.n (* 1000 b.n))))"), ({"n": 3}, [201101, 202102])),
    # An inlined pure procedure: its call nodes keep their own sites.
    "inlined-two-equal-locals": (_pure(f"  (defproc both ((n Int)) -> Int (let-proc ((f {ADDS_ONE}) (g {ADDS_ONE}))"
        " (+ (f n) (* 100 (g n)))))\n", "(both n)"), ({"n": 3}, 404)),
    "inlined-macro-same-arguments": (_pure(f"  (defmacro lk (x) (let-proc ((h {ADDS_ONE})) (h x)))\n"
        "  (defproc both ((n Int)) -> Int (+ (lk n) (* 100 (lk n)) (* 10000 (lk n))))\n", "(both n)"), ({"n": 3}, 40404)),
    "inlined-two-locals": (_pure(f"  (defproc both ((n Int)) -> Int (let-proc ((f {ADDS_ONE}) "
        f"(g {ADDS_ONE.replace('(+ s 1)', '(* s 10)')})) (+ (f n) (g n))))\n",
        "(+ (both n) (* 1000 (both (+ n 1))))"), ({"n": 3}, 34 + 1000 * 45)),
    # A value bound by `bind-proc` is identified by its content: expansions binding different values get their own
    # specialization, and two equal bindings written at two sites share one.
    "bound-value-macro": (_pure("  (defproc helper ((fixed Int) (y Int)) -> Int (+ fixed y))\n"
        "  (defproc applyi ((hook ProcRef[Int -> Int]) (x Int)) -> Int (hook x))\n"
        "  (defmacro bf (k x) (applyi (bind-proc (proc-ref helper) :fixed (+ k 0)) x))\n",
        "(+ (bf 1 n) (* 100 (bf 7 n)))"), ({"n": 3}, 1004)),
    "bound-workflow-ref-macro": (_workflow_ref_macro("(let* ((a (ba c1 input)) (b (ba c2 input))) (+ a.n (* 1000 b.n)))",
        definitions=BOUND_RUNW), ({"n": 3}, 203103)),
    "bound-workflow-ref-equal-written": (_workflow_ref_macro("(let* ((a (ap (bind-proc (proc-ref runw) :w (workflow-ref c1)) "
        "input)) (b (ap (bind-proc (proc-ref runw) :w (workflow-ref c1)) input))) (+ a.n (* 1000 b.n)))",
        definitions=BOUND_RUNW), ({"n": 3}, 103103)),
}
SWEEP = ("two-provider-chains", "one-chain", "one-chain-adding", "three-levels-adding", "two-chains-adding",
         "macro-local", "macro-local-captured", "macro-proc-ref", "macro-generic", "workflow-ref-macro-2.39",
         "workflow-ref-macro-three", "workflow-ref-macro-in-procedure", "inlined-two-equal-locals",
         "inlined-macro-same-arguments", "inlined-two-locals", "bound-value-macro", "bound-workflow-ref-macro",
         "bound-workflow-ref-equal-written")
IN_PROCESS = ("macro-local", "macro-local-captured", "workflow-ref-macro", "workflow-ref-macro-reversed",
              "workflow-ref-macro-in-map", "inlined-two-equal-locals", "inlined-macro-same-arguments",
              "inlined-two-locals", "bound-value-macro", "bound-workflow-ref-macro", "bound-workflow-ref-equal-written")


def _install(root: Path, name: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "prompt.md").write_text("text\n")
    path = root / "main.orc"
    path.write_text(PROGRAMS[name][0])
    return path


def _typed(root: Path, name: str):
    return compile_typed_program(_install(root, name), entry_workflow="run", source_roots=(root,),
        workspace_root=root, **CONFIG)


def _closed(program) -> ClosedProgram:
    return ClosedProgram.from_artifact(program.artifact())


def _value(program: ClosedProgram, inputs: dict):
    return evaluate_closed_program(program, inputs).json_value()


def _harness(root: Path) -> ClosedProgram:
    """The provider I/O module's `nested-bound` shape at 2.40: two imports of one producer program, each
    reached through `invoke` bound over `foo`, so the two outer specializations share one closed key."""
    from tests import test_workflow_evaluated_provider_io as provider_io

    producer = provider_io.PRODUCER.replace('"2.35"', '"2.40"')
    _, imports = provider_io._stages(root, sources={"cp/producer.orc": producer, "cp/prompt.md": "TARGET LEFT\n"})
    source = provider_io.WREF.replace('"2.35"', '"2.40"').replace(
        ":effects ((uses-provider provider) (calls-workflow runner)) :lowering inline", "")
    source = source.replace("(defworkflow run", INVOKE.strip() + "\n  (defworkflow run")
    for side in ("left", "right"):
        source = source.replace(f"(foo (workflow-ref {side})", f"(invoke {_chain(side)}")
    return provider_io._checked(provider_io._typed(root, source, imports))[0]


def _build_all(base: Path) -> dict:
    """{program: [outcome, digest, value]} for every program of `SWEEP` and the harness, built in this process."""
    rows = {}
    for name in SWEEP:
        built, run = {}, PROGRAMS[name][1]
        outcome = build_outcome(lambda: built.update(program=_closed(build_closed_program(_typed(base / name, name)))))
        program = built.get("program")
        value = _value(program, run[0]) if program is not None and run is not None else None
        rows[name] = [list(outcome), getattr(program, "digest", None), value]
    built = {}
    outcome = build_outcome(lambda: built.update(program=_harness(base / "harness")))
    rows["harness"] = [list(outcome), getattr(built.get("program"), "digest", None), None]
    return rows


# ---------------------------------------------------------------------------------------------
# In process: hold under any hash seed.

def test_procedure_typed_body_records_only_its_own_call_edges(tmp_path):
    """The outer `invoke` specialization once carried the inner one's edge at the same `(hook input)` site."""
    typed = _typed(tmp_path, "one-chain")
    for procedure in typed.procedures.values():
        sites = {}
        for edge in procedure.typed_body.effect_summary.procedure_edges:
            sites.setdefault((edge.span, edge.form_path, edge.expansion_stack), set()).add(edge.callee_name)
        assert all(len(callees) == 1 for callees in sites.values()), procedure.definition.name


def test_nested_specializations_keep_every_level(tmp_path):
    """Each `invoke` level's body records only its own call, so elaboration never reads a deeper level's edge
    at the shared `(hook ...)` site, and the program has three `invoke` definitions and adds 3."""
    typed = _typed(tmp_path, "three-levels-adding")
    for procedure in typed.procedures.values():
        assert procedure.typed_body.effect_summary.procedure_edges == procedure.direct_effect_summary.procedure_edges
    program = _closed(build_closed_program(typed))
    names = [name.split("[")[0] for name in program.tree["definitions"]]
    assert sorted(names) == ["procedure:main::foo", *["procedure:main::invoke"] * 3, "workflow:main::left"]
    assert _value(program, {"input": {"n": 4}}) == {"n": 7}


@pytest.mark.parametrize("name", IN_PROCESS)
def test_each_call_reaches_the_target_its_source_means(tmp_path, name):
    inputs, meant = PROGRAMS[name][1]
    assert _value(_closed(build_closed_program(_typed(tmp_path, name))), inputs) == meant


def test_two_callees_at_one_call_site_stop_as_compiler_defect(tmp_path):
    typed = _typed(tmp_path, "one-chain")
    procedures = dict(typed.procedures)
    injected = set()
    for name, procedure in typed.procedures.items():
        edges = procedure.typed_body.effect_summary.procedure_edges
        for edge in edges:
            other = next(callee for callee in procedures if callee not in {name, edge.callee_name})
            edges = edges | {replace(edge, callee_name=other)}
            injected.add(f"{edge.span.start.path}:{edge.span.start.line}:{edge.span.start.column}")
        summary = replace(procedure.typed_body.effect_summary, procedure_edges=edges)
        procedures[name] = replace(procedure, typed_body=replace(procedure.typed_body, effect_summary=summary))
    with pytest.raises(LispFrontendCompileError) as stopped:
        build_closed_program(replace(typed, procedures=procedures))
    diagnostic, = stopped.value.diagnostics
    assert diagnostic.code == "compiler_defect"
    assert crash_signature(diagnostic.cause) == ("ValueError", "workflow_lisp/wcc/elaborate.py:_site_callee")
    assert any(site in diagnostic.message for site in injected)


def test_a_site_with_two_callees_is_never_read(tmp_path):
    """A lookup refuses a site recorded with two callees; it never falls back to the default name."""
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import ProcedureCallExpr
    from orchestrator.workflow_lisp.wcc.elaborate import _AmbiguousSite, _site_callee

    typed = _typed(tmp_path, "one-chain")
    call = next(node for procedure in typed.procedures.values() for node in walk_expr(procedure.typed_body.expr)
                if isinstance(node, ProcedureCallExpr))
    sites = {(call.span, call.form_path, call.expansion_stack): _AmbiguousSite(("a", "b"))}
    with pytest.raises(ValueError):
        _site_callee(sites, call, call.callee_name)


# ---------------------------------------------------------------------------------------------
# Subprocesses: one outcome, one digest and the meant value under every seed and directory.

SEEDS = (0, 3, 4, 11)
DIRECTORIES = ("a", "second/deeper/directory")


def test_every_seed_and_directory_builds_one_program(tmp_path):
    env = {**os.environ, "PATH": closed_path(REPO / "experiments" / "thread_m" / "no_provider"),
           "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}

    def build(run):
        seed, directory = run
        root = tmp_path / directory / str(seed)
        root.mkdir(parents=True)
        done = subprocess.run([sys.executable, "-m", "tests.test_workflow_lisp_call_site_determinism", str(root)],
            cwd=root, env={**env, "PYTHONHASHSEED": str(seed)}, capture_output=True, text=True, timeout=300)
        assert done.returncode == 0, done.stderr
        return run, json.loads(done.stdout)

    with concurrent.futures.ThreadPoolExecutor(len(SEEDS) * len(DIRECTORIES)) as pool:
        runs = dict(pool.map(build, [(seed, directory) for seed in SEEDS for directory in DIRECTORIES]))
    wrong = {}
    for name in (*SWEEP, "harness"):
        rows = {(tuple(outcome), digest, json.dumps(value)) for outcome, digest, value in
                (built[name] for built in runs.values())}
        meant = PROGRAMS[name][1][1] if name in PROGRAMS and PROGRAMS[name][1] is not None else None
        (outcome, _, value), *others = rows
        if others or outcome != ("builds",) or (meant is not None and json.loads(value) != meant):
            wrong[name] = rows
    assert not wrong


if __name__ == "__main__":
    print(json.dumps(_build_all(Path(sys.argv[1]))))
