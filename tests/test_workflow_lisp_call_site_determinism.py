"""One call site has one callee, whatever the hash seed and the source directory.

Elaboration picks each procedure call's target from the call edges recorded at its site (span, form
path and expansion stack). Two edges once shared a site in two cases: a procedure specialized more
than once in one call chain (from target 2.39 a procedure's typed body carried its callees' edges),
and a macro expanded more than once in one owner (every expansion carries the template's span). The
edges are a hashed set, so which one won depended on `PYTHONHASHSEED` and on the absolute source path:
the same source built a different program, computed a different value or crashed from run to run.

The in-process tests below hold under any seed. The subprocess tests build every program under
several fixed seeds, each from two source directories, and require one outcome, one program digest
and the value the source means.
"""

from __future__ import annotations

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
MACRO_HEAD = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
'''
TWICE = "  (defworkflow run ((n Int)) -> Int (+ (with-loop n 5) (* 100 (with-loop n 7)))))\n"


def _chain(workflow: str, depth: int = 2) -> str:
    """`invoke` bound over `invoke` ... over `foo` bound to `workflow`: `depth - 1` levels of `invoke`."""
    bound = f"(bind-proc (proc-ref foo) :runner (workflow-ref {workflow}))"
    for _ in range(depth - 1):
        bound = f"(bind-proc (proc-ref invoke) :hook {bound})"
    return bound


def _one_chain(invoke: str, depth: int = 2) -> str:
    return (HEAD + "  (defworkflow left ((input Box)) -> Box input)\n" + FOO + invoke
            + f"  (defworkflow run ((input Box)) -> Box\n    (invoke {_chain('left', depth)} input)))\n")


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
    "macro-local": (MACRO_HEAD + f"  (defmacro with-loop (x k)\n    {LOCAL})\n" + TWICE, ({"n": 3}, 705)),
    "macro-local-captured": (MACRO_HEAD + f"  (defmacro with-loop (x kk)\n    (let* ((k kk)) {LOCAL}))\n" + TWICE,
        ({"n": 3}, 705)),
    "macro-proc-ref": (MACRO_HEAD + "  (defproc one () -> Int 1)\n  (defproc two () -> Int 2)\n"
        "  (defproc apply ((hook ProcRef[() -> Int])) -> Int (hook))\n"
        "  (defmacro invoke (h) (apply (proc-ref h)))\n"
        "  (defworkflow run () -> Int (+ (invoke one) (* 10 (invoke two)))))\n", ({}, 21)),
    "macro-generic": (MACRO_HEAD + "  (defproc ident :forall (T) ((x T)) -> T x)\n"
        "  (defmacro same (x) (ident x))\n"
        '  (defworkflow run ((n Int)) -> Int (let* ((s (same "text")) (a (same n))) (+ a 1))))\n', ({"n": 3}, 4)),
}


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
    """{program: [outcome, digest, value]} for every program and the harness, built in this process."""
    rows = {}
    for name, (_, run) in PROGRAMS.items():
        built = {}
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
    program = _closed(build_closed_program(_typed(tmp_path, "three-levels-adding")))
    names = [name.split("[")[0] for name in program.tree["definitions"]]
    assert sorted(names) == ["procedure:main::foo", *["procedure:main::invoke"] * 3, "workflow:main::left"]
    assert _value(program, {"input": {"n": 4}}) == {"n": 7}


@pytest.mark.parametrize("name", ("macro-local", "macro-local-captured"))
def test_each_macro_expansion_calls_its_own_local(tmp_path, name):
    """Both expansions of `(h x)` share the template's span and form path; their expansion stacks differ."""
    program = _closed(build_closed_program(_typed(tmp_path, name)))
    assert _value(program, {"n": 3}) == 705


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
    assert crash_signature(diagnostic.cause) == ("ValueError", "workflow_lisp/wcc/elaborate.py:_procedure_edges_by_site")
    assert any(site in diagnostic.message for site in injected)


# ---------------------------------------------------------------------------------------------
# Subprocesses: one outcome, one digest and the meant value under every seed and directory.

SEEDS = (0, 1, 3, 4, 7, 11)


@pytest.fixture(scope="module")
def builds(tmp_path_factory) -> dict:
    """{program: {(seed, directory): (outcome, digest, value)}}; the processes run concurrently."""
    base = tmp_path_factory.mktemp("seeds")
    env = {**os.environ, "PATH": closed_path(REPO / "experiments" / "thread_m" / "no_provider"),
           "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
    runs = {}
    for seed in SEEDS:
        for directory in ("a", "second-directory"):
            root = base / directory / str(seed)
            root.mkdir(parents=True)
            runs[seed, directory] = subprocess.Popen(
                [sys.executable, "-m", "tests.test_workflow_lisp_call_site_determinism", str(root)],
                cwd=root, env={**env, "PYTHONHASHSEED": str(seed)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True)
    table: dict = {}
    for run, process in runs.items():
        stdout, stderr = process.communicate(timeout=300)
        assert process.returncode == 0, stderr
        for name, (outcome, digest, value) in json.loads(stdout).items():
            table.setdefault(name, {})[run] = (tuple(outcome), digest, json.dumps(value))
    return table


@pytest.mark.parametrize("name", (*PROGRAMS, "harness"))
def test_every_seed_and_directory_builds_one_program(builds, name):
    assert len(set(builds[name].values())) == 1, builds[name]
    (outcome, _, value), = set(builds[name].values())
    assert outcome == ("builds",)
    if name in PROGRAMS and PROGRAMS[name][1] is not None:
        assert json.loads(value) == PROGRAMS[name][1][1]


if __name__ == "__main__":
    print(json.dumps(_build_all(Path(sys.argv[1]))))
