"""CF-1b Task 5: the `std/improve` library module (target 2.33).

Contract: docs/design/workflow_lisp_composition_first.md sections 3, 4, 5, 7
and 10; Review Focus items 1, 2 and 5 of
docs/plans/2026-09-28-composition-first-master-plan.md.

Hooks are command-backed probes (the supported deterministic route, design
section 9). Every caller lives under pytest's tmp_path, outside the repository's
source roots, so each test also proves that `std/improve` resolves from the
builtin stdlib root.

`std/phase` is unchanged by this module: `review-revise-loop` and
`review-revise-loop-proc` keep their `ctx` parameter and seeds, so no existing
program loses a `ctx`-borne dependency. `tests/test_workflow_lisp_phase_stdlib.py`
remains its regression suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import UsesCommandEffect, UsesProviderEffect
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_evaluated_totality_helpers import _log, _public_run_files, _write_probe, _write_sources
from tests.workflow_evaluated_totality_helpers import _public_run
from tests.test_workflow_lisp_generic_unions_runtime import _compile
from tests.workflow_lisp_improve_stdlib_sources import BARE_IMPORT_232, REVIEW_PROBE, REVISE_PROBE, SUMMARIZE_PROBE, entry_source, inline_entry_source, provider_revise_entry_source, string_inputs_entry_source, unnamed_union_caller_sources


def _write_project(root: Path, *, seed: str, limit: int, target: str = "2.33", inline: bool = False) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    probes = {
        "probe_review": _write_probe(root, "probe_review", REVIEW_PROBE),
        "probe_revise": _write_probe(root, "probe_revise", REVISE_PROBE),
    }
    entry = entry_source(seed=seed, limit=limit, probes=probes, target=target)
    _write_sources(root, {"grt/entry.orc": inline_entry_source(entry) if inline else entry})
    return probes




def _hook_calls(probes: dict[str, Path]) -> tuple[list[str], list[str]]:
    return _log(probes["probe_review"]), _log(probes["probe_revise"])




def _line_of(text: str, needle: str) -> int:
    return next(number for number, line in enumerate(text.splitlines(), start=1) if needle in line)
















def test_target_232_caller_that_writes_an_applied_union_type_is_rejected(tmp_path: Path) -> None:
    """The rejection is for writing `Decision[...]` and `Improvement[...]`, not for calling `improve`
    (Ruling R8; the positive case is the next test). It names `run`, whose return type is applied."""

    probes = _write_project(tmp_path, seed="approve", limit=3, target="2.32")
    entry = tmp_path / "grt" / "entry.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path, probes=probes)

    diagnostic = excinfo.value.diagnostics[0]
    assert (diagnostic.code, Path(diagnostic.span.start.path), diagnostic.span.start.line) == (
        "generic_union_requires_dsl_2_33",
        entry,
        _line_of(entry.read_text(encoding="utf-8"), "(defworkflow run"),
    )


@pytest.mark.parametrize("target", ["2.28", "2.32"])
def test_caller_below_233_that_writes_no_applied_union_runs_improve_to_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """Ruling R8: target admission is per defining module. The caller imports only `improve`, takes
    its review hook from a 2.33 module, and binds and matches a result whose type it never names."""

    probes = {
        name: _write_probe(tmp_path, name, text)
        for name, text in (
            ("probe_review", REVIEW_PROBE),
            ("probe_revise", REVISE_PROBE),
            ("probe_summarize", SUMMARIZE_PROBE),
        )
    }
    _write_sources(tmp_path, unnamed_union_caller_sources(seed="draft", limit=2, target=target, probes=probes))
    monkeypatch.chdir(tmp_path)

    _admit_current_entry(tmp_path, probes)
    result = _public_run(_public_run_files(tmp_path, probes))

    assert (result.exit_code, dict(result.workflow_outputs), _hook_calls(probes), _log(probes["probe_summarize"])) == (
        0,
        {"outcome": "EXHAUSTED", "title": "draft+r+r", "score": 2},
        (["draft tidy", "draft+r tidy"], ["draft tidy fb0", "draft+r tidy fb1"]),
        ["EXHAUSTED draft+r+r 2"],
    )




@pytest.mark.parametrize(
    "use",
    ["(d Decision[Out Out])", "(d Improvement[Out Out Out])"],
    ids=["Decision", "Improvement"],
)
def test_target_232_use_of_a_std_improve_union_is_rejected_at_the_use(tmp_path: Path, use: str) -> None:
    source = BARE_IMPORT_232.replace(
        "  (defworkflow run",
        f"  (defproc pick ({use}) -> Out :effects () :lowering inline (record Out :n 1))\n  (defworkflow run",
    )
    entry = _write_sources(tmp_path, {"grt/entry.orc": source})

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path)

    diagnostic = excinfo.value.diagnostics[0]
    line = _line_of(source, use)
    assert (diagnostic.code, Path(diagnostic.span.start.path), diagnostic.span.start.line, diagnostic.span.start.column) == (
        "generic_union_requires_dsl_2_33",
        entry,
        line,
        source.splitlines()[line - 1].index(use) + 1,
    )


def test_specialized_improve_summary_forwards_the_selected_hooks_effects(tmp_path: Path) -> None:
    probes = _write_project(tmp_path, seed="approve", limit=3)
    entry = tmp_path / "grt" / "entry.orc"
    entry.write_text(provider_revise_entry_source(entry.read_text(encoding="utf-8")), encoding="utf-8")

    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "probe_review": ExternalToolBinding(
                name="probe_review", stable_command=("python", probes["probe_review"].as_posix())
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=None,
    )
    specialized = next(
        procedure
        for procedure in result.entry_result.typed_procedures
        if getattr(procedure.specialization, "base_name", "") == "std/improve::improve"
    )

    assert (
        specialized.direct_effect_summary.direct_effects,
        specialized.transitive_effect_summary.transitive_effects,
    ) == (
        frozenset(),
        frozenset({UsesCommandEffect(subject=("probe_review",)), UsesProviderEffect(subject=("providers", "execute"))}),
    )


def test_public_run_returns_the_improvement_through_the_public_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes = _write_project(tmp_path, seed="block", limit=3)
    monkeypatch.chdir(tmp_path)

    _admit_current_entry(tmp_path, probes)
    result = _public_run(_public_run_files(tmp_path, probes))

    assert (result.exit_code, dict(result.workflow_outputs), _hook_calls(probes)) == (
        0,
        {"variant": "BLOCKED", "value": {"title": "block+r", "score": 1},
         "reason": {"why": "refused:block+r"}},
        (["block tidy", "block+r tidy"], ["block tidy fb0"]),
    )






def test_resume_after_a_committed_iteration_exhausts_without_replaying_committed_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes = _write_project(tmp_path, seed="draft", limit=3)
    monkeypatch.chdir(tmp_path)

    _exercise_improve_resume(tmp_path, probes, monkeypatch)



def test_resume_keeps_a_string_workflow_parameter_as_inputs_and_replays_no_committed_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruling R10: `inputs` bound to a `String` workflow parameter reaches every hook call, fresh and resumed."""

    probes = _write_project(tmp_path, seed="draft", limit=3)
    entry = tmp_path / "grt" / "entry.orc"
    entry.write_text(string_inputs_entry_source(entry.read_text(encoding="utf-8")), encoding="utf-8")
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"goal": "steady"}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    _exercise_improve_resume(tmp_path, probes, monkeypatch, inputs=inputs, goal="steady")



def _admit_current_entry(root, probes):
    """Keep the original native source/type proof; admit only the public consumer."""
    _compile(root, probes=probes)
    entry = root / "grt" / "entry.orc"
    import re
    entry.write_text(re.sub(r'(:target-dsl )"[0-9.]+"', r'\1"2.35"', entry.read_text(), count=1))


def _exercise_improve_resume(root, probes, monkeypatch, *, inputs=None, goal="tidy"):
    from tests.workflow_evaluated_totality_helpers import pause_public, checked_run
    from tests.test_workflow_evaluated_resume import _resume_cli, _snapshot
    _admit_current_entry(root, probes)
    files = _public_run_files(root, probes)
    pause_public(files, monkeypatch, inputs)
    authority, snapshot = checked_run(root)
    assert snapshot.terminal is None
    assert _hook_calls(probes) == ([f"draft {goal}"], [])
    prefix = authority.memo_path.read_bytes()
    resumed = _resume_cli(root, authority.run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    authority, snapshot = checked_run(root)
    assert authority.memo_path.read_bytes().startswith(prefix)
    assert snapshot.terminal.data["value"] == {"variant": "EXHAUSTED",
        "value": {"title": "draft+r+r+r", "score": 3}}
    assert _hook_calls(probes) == ([f"{title} {goal}" for title in ("draft", "draft+r", "draft+r+r")],
        [f"{title} {goal} {feedback}" for title, feedback in (("draft", "fb0"), ("draft+r", "fb1"), ("draft+r+r", "fb2"))])
    before = _snapshot(root / ".orchestrate")
    calls = _hook_calls(probes)
    assert _resume_cli(root, authority.run_root.name).returncode == 0
    assert _snapshot(root / ".orchestrate") == before
    assert _hook_calls(probes) == calls
