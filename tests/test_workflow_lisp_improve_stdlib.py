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
from tests.test_workflow_lisp_generic_stdlib_composition import _execute_bundle
from tests.test_workflow_lisp_generic_unions_runtime import (
    _PostCommitInterruption,
    _compile,
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.workflow_lisp_improve_stdlib_sources import (
    BARE_IMPORT_232,
    REVIEW_PROBE,
    REVISE_PROBE,
    STD_IMPROVE_PATH,
    entry_source,
    inline_entry_source,
    provider_revise_entry_source,
)


def _write_project(root: Path, *, seed: str, limit: int, target: str = "2.33", inline: bool = False) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    probes = {
        "probe_review": _write_probe(root, "probe_review", REVIEW_PROBE),
        "probe_revise": _write_probe(root, "probe_revise", REVISE_PROBE),
    }
    entry = entry_source(seed=seed, limit=limit, probes=probes, target=target)
    _write_sources(root, {"grt/entry.orc": inline_entry_source(entry) if inline else entry})
    return probes


def _execute(root: Path, probes: dict[str, Path]) -> dict[str, object]:
    bundle = _compile(root, probes=probes).validated_bundles_by_name["grt/entry::run"]
    return _execute_bundle(bundle, workflow_path=root / "grt" / "entry.orc", workspace=root, run_id="run")


def _hook_calls(probes: dict[str, Path]) -> tuple[list[str], list[str]]:
    return _log(probes["probe_review"]), _log(probes["probe_revise"])


def _failed_hook_steps(state: dict[str, object]) -> dict[str, str]:
    return {
        name.rsplit("__", 1)[-1]: step["outcome"]["class"]
        for frame in state["call_frames"].values()
        for name, step in frame["state"]["steps"].items()
        if isinstance(step, dict) and step.get("status") == "failed"
    }


def _line_of(text: str, needle: str) -> int:
    return next(number for number, line in enumerate(text.splitlines(), start=1) if needle in line)


def _outcome(root: Path, *, seed: str, limit: int, inline: bool = False):
    probes = _write_project(root, seed=seed, limit=limit, inline=inline)
    state = _execute(root, probes)
    return state["status"], dict(state.get("workflow_outputs") or {}), _hook_calls(probes)


@pytest.mark.parametrize(
    ("seed", "outputs", "calls"),
    [
        (
            "approve",
            {
                "return__variant": "APPROVED",
                "return__value__title": "approve",
                "return__value__score": 0,
                "return__evidence__note": "ok:approve:tidy",
            },
            (["approve tidy"], []),
        ),
        (
            "block",
            {
                "return__variant": "BLOCKED",
                "return__value__title": "block+r",
                "return__value__score": 1,
                "return__reason__why": "refused:block+r",
            },
            (["block tidy", "block+r tidy"], ["block tidy fb0"]),
        ),
        (
            "draft",
            {"return__variant": "EXHAUSTED", "return__value__title": "draft+r+r+r", "return__value__score": 3},
            (
                ["draft tidy", "draft+r tidy", "draft+r+r tidy"],
                ["draft tidy fb0", "draft+r tidy fb1", "draft+r+r tidy fb2"],
            ),
        ),
    ],
    ids=["first-review-approves-initial", "blocked-returns-refused-candidate", "limit-3-exhausts-with-third-revision"],
)
def test_improve_returns_the_candidate_its_outcome_is_about(
    tmp_path: Path, seed: str, outputs: dict[str, object], calls: tuple[list[str], list[str]]
) -> None:
    assert _outcome(tmp_path, seed=seed, limit=3) == ("completed", outputs, calls)


def test_hook_result_failing_its_declared_type_fails_before_a_decision_reaches_the_helper(tmp_path: Path) -> None:
    probes = _write_project(tmp_path, seed="malformed", limit=3)

    state = _execute(tmp_path, probes)

    assert (state["status"], state.get("workflow_outputs") or {}, _failed_hook_steps(state), _hook_calls(probes)) == (
        "failed",
        {},
        {"probe_review": "contract_violation"},
        (["malformed tidy"], []),
    )


def test_revise_failure_in_the_final_permitted_iteration_is_a_runtime_failure_not_exhaustion(tmp_path: Path) -> None:
    probes = _write_project(tmp_path, seed="fail", limit=2)

    state = _execute(tmp_path, probes)

    assert (state["status"], state.get("workflow_outputs") or {}, _failed_hook_steps(state), _hook_calls(probes)) == (
        "failed",
        {},
        {"probe_revise": "command_failed"},
        (["fail tidy", "fail+r tidy"], ["fail tidy fb0", "fail+r tidy fb1"]),
    )


@pytest.mark.parametrize("seed", ["approve", "block", "draft"])
def test_inline_and_imported_helpers_agree_on_outcome_and_ordered_hook_operations(tmp_path: Path, seed: str) -> None:
    imported = _outcome(tmp_path / "imported", seed=seed, limit=3)
    inline = _outcome(tmp_path / "inline", seed=seed, limit=3, inline=True)

    assert inline == imported


def test_zero_limit_keeps_the_existing_zero_max_rejection_and_invokes_no_hook(tmp_path: Path) -> None:
    """A non-generic `loop/recur :max 0` is rejected by shared validation at its `:on-exhausted`
    clause today (`repeat_until.max_iterations` must be > 0); `improve` inherits exactly that."""

    probes = _write_project(tmp_path, seed="approve", limit=0)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _execute(tmp_path, probes)

    diagnostic = excinfo.value.diagnostics[0]
    location = (Path(diagnostic.span.start.path), diagnostic.span.start.line)
    assert (diagnostic.code, location, _hook_calls(probes)) == (
        "workflow_boundary_type_invalid",
        (STD_IMPROVE_PATH, _line_of(STD_IMPROVE_PATH.read_text(encoding="utf-8"), ":on-exhausted")),
        ([], []),
    )


def test_target_232_caller_of_std_improve_is_rejected_with_the_required_target_diagnostic(tmp_path: Path) -> None:
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Owner: target admission (specs/versioning.md; CF-1b Task 1). A 2.32 module that imports "
        "std/improve without writing a type application compiles: module-graph resolution "
        "(orchestrator/workflow_lisp/modules.py:395) never compares an importer's target with the "
        "imported module's target, and std/improve cannot add that check without a name-keyed branch."
    ),
)
def test_target_232_bare_import_of_std_improve_is_rejected(tmp_path: Path) -> None:
    entry = _write_sources(tmp_path, {"grt/entry.orc": BARE_IMPORT_232})

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path)

    diagnostic = excinfo.value.diagnostics[0]
    assert (diagnostic.code, Path(diagnostic.span.start.path), diagnostic.span.start.line) == (
        "generic_union_requires_dsl_2_33",
        entry,
        _line_of(entry.read_text(encoding="utf-8"), "(import std/improve"),
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

    result = _public_run(_public_run_files(tmp_path, probes))

    assert (result.exit_code, dict(result.workflow_outputs), _hook_calls(probes)) == (
        0,
        {
            "return__variant": "BLOCKED",
            "return__value__title": "block+r",
            "return__value__score": 1,
            "return__reason__why": "refused:block+r",
        },
        (["block tidy", "block+r tidy"], ["block tidy fb0"]),
    )


def test_resume_after_a_committed_iteration_exhausts_without_replaying_committed_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.cli.commands.resume import resume_workflow
    from orchestrator.workflow.executor import WorkflowExecutor

    probes = _write_project(tmp_path, seed="draft", limit=3)
    files = _public_run_files(tmp_path, probes)
    original_hook = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_repeat_until_commit

    def interrupt_after_first_commit(self, step, progress):
        original_hook(self, step, progress)
        if progress.get("last_condition_result") is False:
            raise _PostCommitInterruption

    monkeypatch.chdir(tmp_path)
    with monkeypatch.context() as interrupted:
        interrupted.setattr(
            WorkflowExecutor, "_emit_lexical_checkpoint_shadow_after_repeat_until_commit", interrupt_after_first_commit
        )
        with pytest.raises(_PostCommitInterruption):
            _public_run(files)
    assert _hook_calls(probes) == (["draft tidy"], ["draft tidy fb0"])

    run_id = next((tmp_path / ".orchestrate" / "runs").iterdir()).name
    assert resume_workflow(run_id=run_id, retry_delay_ms=0) == 0

    state = json.loads((tmp_path / ".orchestrate" / "runs" / run_id / "state.json").read_text(encoding="utf-8"))
    assert (state["status"], state["workflow_outputs"], _hook_calls(probes)) == (
        "completed",
        {"return__variant": "EXHAUSTED", "return__value__title": "draft+r+r+r", "return__value__score": 3},
        (
            ["draft tidy", "draft+r tidy", "draft+r+r tidy"],
            ["draft tidy fb0", "draft+r tidy fb1", "draft+r+r tidy fb2"],
        ),
    )
