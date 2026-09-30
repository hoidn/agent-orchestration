"""Spike of evaluated execution: the closed program, its sites, identity, evaluation and parity.

Throwaway (decision 4 of docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md,
Tasks 8 and 9). Contract: docs/design/workflow_lisp_evaluated_execution.md sections 4 to 6.
Resume and the crash windows of section 8 are tested in `test_evaluated_execution_spike_resume.py`.

Every effect is a command-backed procedure running the probe of the totality matrix,
which appends `<command> <n>` to `probe.log`, or a stand-in provider. Programs live in
`fixtures/evaluated_execution_spike/` or are cells of the totality matrix. Real programs,
the search controller among them, are in `test_evaluated_execution_spike_programs.py`.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.evaluated_execution_spike.closed import build_closed_program
from experiments.evaluated_execution_spike.evaluator import evaluate
from experiments.evaluated_execution_spike.frontend import typecheck_program
from experiments.evaluated_execution_spike.memo import read_records
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.test_workflow_lisp_generic_union_provider_results import _Provider
from tests.test_workflow_lisp_generic_unions_runtime import _log, _public_run, _public_run_files, _write_sources
from tests.test_workflow_lisp_totality_matrix import _DIAGNOSTIC_CODE
from tests.workflow_lisp_improve_stdlib_sources import REVIEW_PROBE, REVISE_PROBE, entry_source
from tests.workflow_lisp_totality_matrix_sources import (
    COMMANDS,
    KNOWN_DEFECTS,
    PROBE,
    RULES,
    SKIPPED,
    _flatten,
    cells,
    expected,
    program,
)

FIXTURES = Path(__file__).parent / "fixtures" / "evaluated_execution_spike"
BOUNDARIES = {name: ExternalToolBinding(name=name, stable_command=("python", "probe.py")) for name in COMMANDS}
PROVIDERS = {"providers.review": "codex"}
PROMPTS = {"prompts.review": "review.md"}


def fixture(name: str) -> dict[str, str]:
    return {f"spk/{name}.orc": (FIXTURES / f"{name}.orc").read_text(encoding="utf-8")}


def matrix(form: str, position: str) -> dict[str, str]:
    return program(form, position, "probe.py")


def install(root: Path, sources: dict[str, str]) -> Path:
    """Write the sources, the probe and the prompt under `root`; return the entry module's path."""

    _write_sources(root, sources)
    (root / "probe.py").write_text(PROBE, encoding="utf-8")
    entry = root / next(iter(sources))
    (entry.parent / "review.md").write_text("Review the draft.\n", encoding="utf-8")
    return entry


def entry_workflow(sources: dict[str, str]) -> str:
    return next(iter(sources)).removesuffix(".orc") + "::run"


def build(root: Path, sources: dict[str, str], *, boundaries=BOUNDARIES, workflow=None, providers=PROVIDERS,
          prompts=PROMPTS, **options):
    entry = install(root, sources)
    options.setdefault("closures", {name: [] for name in boundaries})  # `strict`: every boundary declares one
    typed = typecheck_program(
        entry,
        entry_workflow=workflow or entry_workflow(sources),
        source_roots=(root,),
        command_boundaries=boundaries,
        provider_externs=providers,
        prompt_externs=prompts,
    )
    return build_closed_program(typed, **options)


def run_root(root: Path, run_id: str = "run") -> Path:
    return root / ".orchestrate" / "spike" / run_id


def records(root: Path, kind: str = "committed", run_id: str = "run") -> list[dict]:
    return [record for record in read_records(run_root(root, run_id)) if record["record"] == kind]


def spike(root: Path, sources: dict[str, str], *, inputs=None, run_id="run", hook=None, closed=None, **options):
    """Evaluate on the spike; every identity in the memo must be an instance of a site listed before the run."""

    closed = closed or build(root, sources, **options)
    try:
        return closed, evaluate(closed, inputs=inputs or {}, workspace=root, run_root=run_root(root, run_id), hook=hook)
    finally:
        for record in (r for r in read_records(run_root(root, run_id)) if "identity" in r):
            assert re.sub(r"\[\d+\]", "[*]", record["identity"]) in closed.sites


def calls(root: Path) -> list[str]:
    return _log(root / "probe.py")


def outputs(value) -> dict:
    """The value as the flat route's workflow outputs flatten it."""

    return _flatten("return", value) if isinstance(value, dict) else {"__result__": value}


def flat(root: Path, sources: dict[str, str], monkeypatch: pytest.MonkeyPatch, *, inputs=None, probes=None):
    """Run on the flat route through the public run entry: (exit code, workflow outputs, command log)."""

    entry = install(root, sources)
    files = {**_public_run_files(root, probes or {name: Path("probe.py") for name in COMMANDS}), "source": entry}
    files["providers"].write_text(json.dumps(PROVIDERS), encoding="utf-8")
    files["prompts"].write_text(json.dumps(PROMPTS), encoding="utf-8")
    input_file = None
    if inputs:
        input_file = root / "inputs.json"
        input_file.write_text(json.dumps(inputs), encoding="utf-8")
    monkeypatch.chdir(root)
    result = _public_run(files, input_file=input_file)
    return result.exit_code, dict(result.workflow_outputs), calls(root)


def stand_in_provider(monkeypatch: pytest.MonkeyPatch, payload: dict) -> _Provider:
    provider = _Provider(payload)
    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", provider.prepare_invocation)
    monkeypatch.setattr(ProviderExecutor, "execute", in_cwd(provider.execute))
    return provider


def in_cwd(execute):
    """A stand-in provider's `execute` that writes where a real provider process would: a relative result path
    is relative to the `cwd` the caller names (the spike names the workspace; the flat route names none)."""

    def run(*args, **kwargs):  # `(invocation)`, or `(executor, invocation)` once installed on the executor class
        invocation = args[-1]
        bundle = invocation.env.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
        if kwargs.get("cwd") is not None and bundle:
            invocation.env = {**invocation.env, "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(Path(kwargs["cwd"]) / bundle)}
        return execute(invocation, **kwargs)

    return run


def with_blank_lines(text: str) -> str:
    """Two blank lines and a comment before every definition."""

    return text.replace("\n  (def", "\n\n\n  ;; moved down\n  (def")


# Task 8: sites -------------------------------------------------------------


def test_three_call_sites_of_one_procedure_are_three_sites(tmp_path: Path) -> None:
    closed = build(tmp_path, fixture("three_call_sites"))

    callee = "spk/three_call_sites::fetch"
    assert closed.sites == tuple(
        f"spk/three_call_sites::run / {binder}={callee} / #1" for binder in ("a", "b", "c")
    )


def test_one_procedure_in_three_arms_of_a_match_in_a_loop_is_three_sites(tmp_path: Path) -> None:
    closed = build(tmp_path, fixture("arms_in_loop"))

    callee = "spk/arms_in_loop::fetch"
    assert closed.sites == tuple(
        f"spk/arms_in_loop::run / loop:state[*] / got / {arm} / #1={callee} / #1"
        for arm in ("FIRST", "SECOND", "THIRD")
    )


def test_a_specialized_hook_is_named_by_its_base_and_its_canonical_arguments(tmp_path: Path) -> None:
    closed = build(tmp_path, fixture("if_in_hook"))

    improve = (
        "std/improve::improve[B=spk/if_in_hook::Note, F=spk/if_in_hook::Note, I=spk/if_in_hook::Brief, "
        "S=spk/if_in_hook::Candidate, review=spk/if_in_hook::review, revise=spk/if_in_hook::revise]"
    )
    prefix = f"spk/if_in_hook::run / result={improve} / loop:state[*]"
    assert closed.sites == (
        f"{prefix} / decision=spk/if_in_hook::review / b=spk/if_in_hook::fetch / #1",
        f"{prefix} / REVISE / next=spk/if_in_hook::revise / b=spk/if_in_hook::fetch / #1",
    )


@pytest.mark.parametrize("name", ["three_call_sites", "arms_in_loop", "if_in_hook", "loop_in_loop"])
def test_blank_lines_and_comments_change_no_site_and_not_the_program_digest(tmp_path: Path, name: str) -> None:
    sources = fixture(name)
    edited = {path: with_blank_lines(text) for path, text in sources.items()}

    original, spaced = build(tmp_path / "a", sources), build(tmp_path / "b", edited)

    assert edited != sources
    assert (spaced.sites, spaced.digest) == (original.sites, original.digest)


@pytest.mark.parametrize("name", ["three_call_sites", "if_in_hook", "loop_in_loop"])
def test_moving_the_program_changes_no_site_and_not_the_program_digest(tmp_path: Path, name: str) -> None:
    here = build(tmp_path / "here", fixture(name))
    there = build(tmp_path / "elsewhere" / "deeper", fixture(name))

    assert (there.sites, there.digest) == (here.sites, here.digest)


def test_no_site_and_no_part_of_the_digested_program_holds_a_path_a_position_or_a_type_text(
    tmp_path: Path,
) -> None:
    from experiments.evaluated_execution_spike.sites import strip_provenance

    closed = build(tmp_path, fixture("if_in_hook"))
    digested = json.dumps(strip_provenance(closed.tree))

    for text in (*closed.sites, digested):
        assert str(tmp_path) not in text
        assert "stdlib_modules" not in text
        assert re.search(r"TypeRef|SourceSpan|line=|\.orc:\d+", text) is None
    assert str(tmp_path) in closed.artifact()  # provenance is kept, outside the digest


def test_the_closed_program_holds_no_surface_object_and_is_canonical_json(tmp_path: Path) -> None:
    closed = build(tmp_path, matrix("pure-match", "loop-state-field"))

    reparsed = json.loads(closed.artifact())

    assert reparsed == closed.tree
    assert '"opaque' not in closed.artifact() and "Expr" not in closed.artifact()


def test_moving_the_package_changes_no_site_and_not_the_program_digest(tmp_path: Path) -> None:
    """The orchestrator package, `std/improve` included, and the spike, copied to another root."""

    repo = Path(__file__).resolve().parents[2]
    package = tmp_path / "package"
    for part in ("orchestrator", "experiments/evaluated_execution_spike"):
        shutil.copytree(repo / part, package / part, ignore=shutil.ignore_patterns("__pycache__"))
    entry = install(tmp_path / "program", fixture("if_in_hook"))
    script = (
        "import json, sys; from pathlib import Path\n"
        "from experiments.evaluated_execution_spike.closed import build_closed_program\n"
        "from experiments.evaluated_execution_spike.frontend import typecheck_program\n"
        "from orchestrator.workflow_lisp.workflows import ExternalToolBinding\n"
        "entry = Path(sys.argv[1])\n"
        "typed = typecheck_program(entry, entry_workflow='spk/if_in_hook::run', source_roots=(entry.parents[1],),\n"
        "    command_boundaries={'fetch': ExternalToolBinding(name='fetch', stable_command=('python', 'probe.py'))})\n"
        "closed = build_closed_program(typed, closures={'fetch': []})\n"
        "print(json.dumps([closed.sites, closed.digest]))\n"
    )
    moved = subprocess.run(
        [sys.executable, "-c", script, str(entry)],
        cwd=package, env={"PYTHONPATH": str(package), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, check=True,
    )
    here = build(tmp_path / "here", fixture("if_in_hook"))

    assert json.loads(moved.stdout.splitlines()[-1]) == [list(here.sites), here.digest]


# Task 9: evaluation ---------------------------------------------------------


def _refused_by_typecheck(cell: tuple[str, str]) -> bool:
    defect = KNOWN_DEFECTS.get(cell)
    return defect is not None and defect.stage in ("typecheck", "specialization")


def _typechecked_cells() -> list:
    return [
        pytest.param(form, position, id=f"{form}/{position}")
        for form, position in cells()
        if (form, position) not in SKIPPED and (form, position) not in RULES and not _refused_by_typecheck((form, position))
    ]


@pytest.mark.parametrize(
    ("form", "position"), [pytest.param(*cell, id="/".join(cell)) for cell in KNOWN_DEFECTS if _refused_by_typecheck(cell)]
)
def test_matrix_cells_that_typecheck_refuses_never_reach_the_spike(tmp_path: Path, form: str, position: str) -> None:
    with pytest.raises(LispFrontendCompileError) as refused:
        build(tmp_path, matrix(form, position))

    assert refused.value.diagnostics[0].code == KNOWN_DEFECTS[(form, position)].kind


@pytest.mark.parametrize(("form", "position"), _typechecked_cells())
def test_every_matrix_cell_that_typechecks_evaluates_to_its_value_and_command_log(
    tmp_path: Path, form: str, position: str
) -> None:
    _, result = spike(tmp_path, matrix(form, position))

    assert (outputs(result.value), calls(tmp_path)) == expected(form, position)


def _case(sources, value, log, inputs=None, flat=None):
    """A program, its inputs, its value and command log, and the flat route's refusal code (None: it runs)."""

    return sources, inputs or {}, value, log, flat


def _cell(form: str, position: str):
    defect = KNOWN_DEFECTS.get((form, position))
    # A known defect that compiles and fails at run time (exit 1) is checked against the run's state.
    refusal = None if defect is None else defect.kind if defect.exit_code == 2 else f"exit 1: {defect.kind}"
    return _case(matrix(form, position), *expected(form, position), flat=refusal)


DECISION_BRIEF = {
    "a-match-subject": _cell("imported-wrapper-call", "match-subject"),
    "a-let-binding": _cell("imported-wrapper-call", "let-binding"),
    "b": _cell("command-call", "loop-state-field"),
    "c": _cell("generic-hook-call", "match-subject"),
    "d": _cell("pure-match", "variant-field"),
    "e": _case(fixture("e_generic_constructor"), {"__result__": 7}, ["fetch 7"], flat="compiler_defect"),
    "f": _case(fixture("f_variant_and_loop"), {"__result__": 3}, ["gate 1", "fetch 2", "fetch 3"],
               flat="workflow_signature_mismatch"),
}

NESTING = {
    "if-in-if": _case(fixture("d1_if_in_if"), {"return__n": 5}, ["fetch 5"], {"a": True, "b": True},
                      flat="workflow_boundary_type_invalid"),
    "match-in-if": _case(fixture("d2_match_in_if"), {"return__n": 4}, ["gate 3", "fetch 4"], {"a": True},
                         flat="workflow_boundary_type_invalid"),
    "loop-in-if": _case(fixture("d3_loop_in_if"), {"return__n": 2}, ["fetch 2"], {"go": True},
                        flat="workflow_boundary_type_invalid"),
    "loop-in-branch": _case(fixture("loop_in_branch"), {"return__n": 3}, ["fetch 1", "fetch 2", "fetch 3"], {"go": True},
                            flat="workflow_signature_mismatch"),
    "loop-in-branch-not-taken": _case(fixture("loop_in_branch"), {"return__n": 0}, [], {"go": False},
                                      flat="workflow_signature_mismatch"),
    "loop-in-loop": _case(fixture("loop_in_loop"), {"return__n": 12}, ["fetch 0", "fetch 1", "fetch 10", "fetch 11"],
                          flat="compiler_defect"),
    "if-in-hook": _case(fixture("if_in_hook"), {"__result__": 5},
                        ["fetch 0", "fetch 1", "fetch 1", "fetch 3", "fetch 3", "fetch 5", "fetch 5"],
                        flat="workflow_return_not_exportable"),
    "match-in-hook": _case(fixture("match_in_hook"), {"__result__": 3},
                           ["gate 0", "fetch 1", "gate 1", "fetch 2", "gate 2", "fetch 3", "gate 3"], flat="workflow_return_not_exportable"),
    "match-on-pure-call": _cell("pure-proc-call", "match-subject"),
    "match-on-defun-call": _cell("defun-call", "match-subject"),
    "union-loop-state-field": _cell("plain-variant", "loop-state-field"),
    "effectful-done-value": _cell("command-call", "done-value"),
    "three-arms-in-a-loop": _case(fixture("arms_in_loop"), {"__result__": 10}, ["fetch 1", "fetch 2", "fetch 3", "fetch 4"],
                                  flat="compiler_defect_loop_control_value"),
    "three-call-sites": _case(fixture("three_call_sites"), {"return__n": 6}, ["fetch 1", "fetch 2", "fetch 3"]),
    # An `if` over two records bound by `let*` in a procedure called in a loop: the flat route compiles it and
    # fails at run time. Over two lists, the form of the compact search controller, it refuses it.
    "if-over-records-in-a-procedure": _case(fixture("if_over_records"), {"return__n": 4}, ["fetch 2"], {"branch": "B"},
                                            flat="exit 1: pure_expr_payload_invalid"),
    "if-over-lists-in-a-procedure": _case(fixture("if_over_lists"), {"return__n": 2, "return__parents": [{"n": 2}]},
                                          ["fetch 2"], {"branch": "B"}, flat="workflow_return_not_exportable"),
}

PROGRAMS = {**{f"brief-{k}": v for k, v in DECISION_BRIEF.items()}, **NESTING}


@pytest.mark.parametrize("name", list(PROGRAMS))
def test_program_evaluates_to_its_value_and_command_log(tmp_path: Path, name: str) -> None:
    sources, inputs, value, log, _ = PROGRAMS[name]

    _, result = spike(tmp_path, sources, inputs=inputs)

    assert (outputs(result.value), calls(tmp_path)) == (value, log)


def test_one_call_site_reached_in_three_iterations_has_three_identities(tmp_path: Path) -> None:
    spike(tmp_path, fixture("loop_in_branch"), inputs={"go": True})

    assert [r["identity"] for r in records(tmp_path)] == [
        f"spk/loop_in_branch::run / then / loop:state[{i}] / b=spk/loop_in_branch::fetch / #1" for i in (1, 2, 3)
    ]


def test_one_procedure_in_three_arms_in_a_loop_has_one_identity_per_arm_and_iteration(tmp_path: Path) -> None:
    spike(tmp_path, fixture("arms_in_loop"))

    assert [r["identity"] for r in records(tmp_path)] == [
        f"spk/arms_in_loop::run / loop:state[{i}] / got / {arm} / #1=spk/arms_in_loop::fetch / #1"
        for i, arm in ((1, "FIRST"), (2, "SECOND"), (3, "THIRD"), (4, "FIRST"))
    ]


def test_a_loop_in_a_loop_names_both_iterations(tmp_path: Path) -> None:
    spike(tmp_path, fixture("loop_in_loop"))

    assert [r["identity"] for r in records(tmp_path)] == [
        f"spk/loop_in_loop::run / loop:outer[{i}] / inner / loop:st[{j}] / b=spk/loop_in_loop::fetch / #1"
        for i, j in ((1, 1), (1, 2), (2, 1), (2, 2))
    ]


def test_blank_lines_and_a_move_change_no_identity_and_no_input_digest(tmp_path: Path) -> None:
    sources = fixture("if_in_hook")
    spaced = {path: with_blank_lines(text) for path, text in sources.items()}
    for root, program_sources in ((tmp_path / "a", sources), (tmp_path / "b" / "c", sources), (tmp_path / "d", spaced)):
        spike(root, program_sources)

    memos = [[(r["identity"], r["input_digest"]) for r in records(root)] for root in
             (tmp_path / "a", tmp_path / "b" / "c", tmp_path / "d")]
    assert memos[0] == memos[1] == memos[2] and len(memos[0]) == 7


# Parity with the flat route --------------------------------------------------


@pytest.mark.parametrize(
    ("sources", "inputs", "refusal"),
    [
        *(pytest.param(*_cell(*cell)[:2], _cell(*cell)[4], id="/".join(cell))
          for cell in cells() if cell not in SKIPPED and cell not in RULES and not _refused_by_typecheck(cell)),
        *(pytest.param(case[0], case[1], case[4], id=name) for name, case in PROGRAMS.items()),
    ],
)
def test_the_flat_route_refuses_with_its_code_or_agrees_with_the_spike(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, sources, inputs, refusal
) -> None:
    """Equal final value and equal ordered commands with their inputs, where the flat route runs."""

    with caplog.at_level(logging.ERROR):
        exit_code, flat_outputs, flat_calls = flat(tmp_path / "flat", sources, monkeypatch, inputs=inputs)
    if refusal is not None and refusal.startswith("exit 1: "):  # compiled, then failed at run time
        # A failure inside a run is recorded in its state; a crash before the run has one is only logged.
        states = list((tmp_path / "flat" / ".orchestrate" / "runs").glob("*/state.json"))
        evidence = states[0].read_text(encoding="utf-8") if states else caplog.text
        assert (exit_code, refusal.removeprefix("exit 1: ") in evidence) == (1, True)
        return
    if refusal is not None:
        assert (exit_code, _DIAGNOSTIC_CODE.findall(caplog.text)[:1]) == (2, [refusal])
        return
    _, result = spike(tmp_path / "spike", sources, inputs=inputs)

    assert exit_code == 0
    assert (outputs(result.value), calls(tmp_path / "spike")) == (flat_outputs, flat_calls)


@pytest.mark.parametrize("seed", ["approve", "block", "draft"])
def test_std_improve_agrees_with_the_flat_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seed: str) -> None:
    logs = {}
    for route in ("flat", "spike"):
        root = tmp_path / route
        root.mkdir()
        probes = {}
        for name, text in (("probe_review", REVIEW_PROBE), ("probe_revise", REVISE_PROBE)):
            (root / f"{name}.py").write_text(text, encoding="utf-8")
            probes[name] = Path(f"{name}.py")
        sources = {"grt/entry.orc": entry_source(seed=seed, limit=3, probes=probes, target="2.33")}
        if route == "flat":
            exit_code, value, _ = flat(root, sources, monkeypatch, probes=probes)
            assert exit_code == 0
        else:
            boundaries = {n: ExternalToolBinding(name=n, stable_command=("python", p.as_posix())) for n, p in probes.items()}
            value = outputs(spike(root, sources, boundaries=boundaries)[1].value)
        logs[route] = (value, _log(root / "probe_review.py"), _log(root / "probe_revise.py"))

    assert logs["spike"] == logs["flat"]


@pytest.mark.parametrize(
    "payload",
    [
        {"variant": "APPROVE", "evidence": {"notes": "fine"}},
        {"variant": "REVISE", "feedback": {"notes": "again"}},
        {"variant": "BLOCKED", "reason": {"issue": "no", "severity": 4}},
    ],
    ids=["approve", "revise", "blocked"],
)
def test_a_stand_in_provider_agrees_with_the_flat_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    flat_provider = stand_in_provider(monkeypatch, payload)
    exit_code, flat_outputs, flat_calls = flat(tmp_path / "flat", fixture("provider_review"), monkeypatch, inputs={"draft": "d1"})
    spike_provider = stand_in_provider(monkeypatch, payload)
    _, result = spike(tmp_path / "spike", fixture("provider_review"), inputs={"draft": "d1"})

    assert exit_code == 0
    assert (outputs(result.value), calls(tmp_path / "spike"), spike_provider.calls) == (flat_outputs, flat_calls, flat_provider.calls)
