"""Known defects of resume for Workflow Lisp effects without a committed result.

Each test asserts the intended behavior. A case that fails today carries a
strict xfail that names its defect. Runs go through the public entry
(`run_workflow`, `resume_workflow`)
with the command probe and helpers of
`tests/test_workflow_resume_after_known_failure.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_workflow_lisp_generic_unions_runtime import _log
from tests.test_workflow_lisp_provider_supervision_e2e import _install_fake_provider_runtime
from tests.test_workflow_resume_after_known_failure import (
    CALL,
    LOOP,
    PRELUDE,
    _all_resume_diagnostics,
    _install,
    _interrupt_command,
    _Interruption,
    _mark_probe_must_not_repeat,
    _outcome,
    _repair,
    _resume,
    _run,
)


REFUSAL = "lexical_restore_pending_effect_unsafe"
COMMAND_LINE = PRELUDE.splitlines().index(
    '    (command-result probe :argv ("python" "PROBE" name) :returns Note))'
) + 1

SUPERVISED = PRELUDE + """  (defworkflow run () -> Note
    (let* ((answer
             (with-live-providers
               ((worker
                 (provider-result providers.worker
                   :prompt prompts.worker :inputs () :timeout-sec 30 :returns String))
                (supervisor
                 (provider-result providers.supervisor
                   :prompt prompts.supervisor :inputs () :timeout-sec 30
                   :returns ProviderSteeringDirective)
                 :observes worker))
               worker)))
      (step answer))))
"""

LOOP_DEFECT = (
    "Known defect (Task 11 review, finding 3a): resume refuses an interrupted command in the second or "
    "later call of the same called workflow, such as a later loop iteration, with lexical_restore_invalid "
    "and lexical_checkpoint_completed_effect_invalid, also when the command must not repeat."
)
GROUP_DEFECT = (
    "Known defect (Task 11 review, finding 3b): resume refuses an interrupted command whose nearest earlier "
    "effect is a provider group with lexical_default_resume_prior_boundary_not_restorable."
)
CALLEE_DEFECT = (
    "Known defect (Task 11 review, finding 2): a must_not_repeat refusal inside a called workflow has "
    "the code lexical_restore_pending_effect_unsafe but no source_location."
)


def _refusals(value: object):
    """Every mapping in the state, at any depth, whose diagnostics name the refusal."""

    if isinstance(value, dict):
        diagnostics = value.get("diagnostics")
        if isinstance(diagnostics, list) and REFUSAL in diagnostics:
            yield value
        for item in value.values():
            yield from _refusals(item)
    elif isinstance(value, list):
        for item in value:
            yield from _refusals(item)


def _assert_located_refusal(exit_code: int, state: dict, files: dict[str, Path], log: list[str]) -> None:
    refusals = list(_refusals(state))
    assert (exit_code, state["status"], _log(files["probe"]), bool(refusals)) == (1, "failed", log, True)
    locations = [refusal.get("source_location") or {} for refusal in refusals]
    assert [(Path(str(location.get("path"))).name, location.get("line")) for location in locations] == [
        ("entry.orc", COMMAND_LINE)
    ] * len(locations)


def _rerun_recorded(state: dict) -> bool:
    return "workflow_effect_rerun" in {row["diagnostic"] for row in _all_resume_diagnostics(state)}


def _install_supervised(root: Path, monkeypatch: pytest.MonkeyPatch):
    files = _install(root, SUPERVISED)
    files["providers"].write_text(
        json.dumps({"providers.worker": "codex", "providers.supervisor": "supervisor-provider"}),
        encoding="utf-8",
    )
    files["prompts"].write_text(
        json.dumps({"prompts.worker": "worker.md", "prompts.supervisor": "supervisor.md"}),
        encoding="utf-8",
    )
    for name in ("worker", "supervisor"):
        (root / "grt" / f"{name}.md").write_text("Answer.\n", encoding="utf-8")
    return files, _install_fake_provider_runtime(monkeypatch)


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=LOOP_DEFECT)
@pytest.mark.parametrize("must_not_repeat", [False, True], ids=["rerun", "must_not_repeat"])
def test_interrupted_command_in_a_later_loop_iteration_runs_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, must_not_repeat: bool
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, LOOP)
    if must_not_repeat:
        _mark_probe_must_not_repeat(files)
    with _interrupt_command("seed+"), pytest.raises(_Interruption):
        _run(files)
    assert _log(files["probe"]) == ["seed", "seed+"]

    exit_code, state = _resume(tmp_path)

    if must_not_repeat:
        _assert_located_refusal(exit_code, state, files, ["seed", "seed+"])
        return
    assert (*_outcome(exit_code, state, files), _rerun_recorded(state)) == (
        0, "completed", {"return__note": "seed+++"}, ["seed", "seed+", "seed+", "seed++"], True,
    )


@pytest.mark.parametrize(
    "must_not_repeat",
    [
        pytest.param(
            False,
            id="rerun",
            marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason=GROUP_DEFECT),
        ),
        pytest.param(True, id="must_not_repeat"),
    ],
)
def test_interrupted_command_after_a_provider_group_runs_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, must_not_repeat: bool
) -> None:
    monkeypatch.chdir(tmp_path)
    files, providers = _install_supervised(tmp_path, monkeypatch)
    if must_not_repeat:
        _mark_probe_must_not_repeat(files)
    with _interrupt_command("fresh-value"), pytest.raises(_Interruption):
        _run(files)
    assert (len(providers.executed), _log(files["probe"])) == (2, ["fresh-value"])

    exit_code, state = _resume(tmp_path)

    assert len(providers.executed) == 2
    if must_not_repeat:
        _assert_located_refusal(exit_code, state, files, ["fresh-value"])
        return
    assert (*_outcome(exit_code, state, files), _rerun_recorded(state)) == (
        0, "completed", {"return__note": "fresh-value+"}, ["fresh-value", "fresh-value"], True,
    )


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=CALLEE_DEFECT)
@pytest.mark.parametrize("interrupted", [False, True], ids=["failed", "interrupted"])
def test_nonrepeatable_command_inside_a_called_workflow_is_refused_with_a_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupted: bool
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, CALL, broken=() if interrupted else ("two",))
    _mark_probe_must_not_repeat(files)
    if interrupted:
        with _interrupt_command("two"), pytest.raises(_Interruption):
            _run(files)
    else:
        assert _run(files) == 1
        _repair(files, "two")
    assert _log(files["probe"]) == ["prepare", "one", "two"]

    exit_code, state = _resume(tmp_path)

    _assert_located_refusal(exit_code, state, files, ["prepare", "one", "two"])
