"""Spike of evaluated execution, iteration 3, item D: forms that typecheck and did not build.

Throwaway. Review 2, finding 6. Each form runs on both routes where the flat route
accepts it:

- an effectful call as the argument of another effectful call, `(fetch (inc 4))`;
- a workflow call that leaves out the compiler-supplied `run` context parameter;
- `provider-bundle-path`, the path of a provider's result file (`ProviderBundlePathExpr`);
- `phase-target` inside `with-phase` (`WccPhaseTargetAtom`).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.evaluated_execution_spike.closed import ClosedProgramGap, build_closed_program
from experiments.evaluated_execution_spike.frontend import typecheck_program
from experiments.evaluated_execution_spike.memo import read_records
from experiments.evaluated_execution_spike.performers import result_path
from orchestrator.cli.commands.run import run_workflow
from tests.experiments.test_evaluated_execution_spike import (
    PROMPTS,
    PROVIDERS,
    calls,
    install,
    run_root,
    spike,
    stand_in_provider,
)
from tests.test_workflow_lisp_generic_unions_runtime import _public_run_files
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args, _run_argv
from tests.workflow_lisp_totality_matrix_sources import COMMANDS

REPO = Path(__file__).resolve().parents[2]
HEADER = '(workflow-lisp (:language "0.1") (:target-dsl "2.33")\n'
FETCH = ('  (defrecord Box (n Int))\n'
         '  (defproc fetch ((n Int)) -> Box :effects ((uses-command fetch)) :lowering inline\n'
         '    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))\n')
NESTED = HEADER + '  (defmodule spk/nested) (export entry)\n' + FETCH + '''\
  (defproc inc ((n Int)) -> Int :effects ((uses-command fetch)) :lowering inline
    (let* ((discard (fetch n))) (+ n 1)))
  (defworkflow entry () -> Box (fetch (inc 4))))'''
RUN_CONTEXT = HEADER + '''\
  (defmodule spk/run_context)
  (import std/context :only (RunCtx))
  (export entry)
  (defworkflow where ((run RunCtx)) -> RunCtx run)
  (defworkflow entry () -> RunCtx (call where)))'''
BUNDLE_PATH = HEADER + '''\
  (defmodule spk/bundle_path) (export entry)
  (defpath BundlePath :kind relpath :under "state" :must-exist true)
  (defrecord Pick (choice Int))
  (defrecord Picked (choice Int) (bundle BundlePath))
  (defworkflow pick ((topic String)) -> Picked
    (let* ((decision (provider-result providers.review :prompt prompts.review :inputs (topic) :returns Pick))
           (path (provider-bundle-path decision :as BundlePath)))
      (record Picked :choice decision.choice :bundle path)))
  (defworkflow entry ((topic String)) -> Picked (call pick :topic topic)))'''


def flat_entry(root: Path, sources: dict[str, str], monkeypatch: pytest.MonkeyPatch, inputs: dict | None = None):
    """The flat route through the public run entry, with the entry workflow named `entry` (the name the
    compiler accepts for an entry that receives hidden context): (exit code, outputs, run state)."""

    source = install(root, sources)
    files = {**_public_run_files(root, {name: Path("probe.py") for name in COMMANDS}), "source": source}
    files["providers"].write_text(json.dumps(PROVIDERS), encoding="utf-8")
    files["prompts"].write_text(json.dumps(PROMPTS), encoding="utf-8")
    (root / "inputs.json").write_text(json.dumps(inputs or {}), encoding="utf-8")
    args = _run_args(files, input_file=root / "inputs.json")
    args.command_boundaries_file, args.entry_workflow = str(files["commands"]), "entry"
    argv = [*_run_argv(files), "--command-boundaries-file", str(files["commands"])]
    argv[argv.index("--entry-workflow") + 1] = "entry"
    monkeypatch.chdir(root)
    with patch.object(sys, "argv", argv):
        result = run_workflow(args)
    runs = root / ".orchestrate" / "runs"
    state = json.loads(next(runs.iterdir()).joinpath("state.json").read_text(encoding="utf-8")) if runs.exists() else {}
    return result.exit_code, dict(result.workflow_outputs), state


def spiked(root: Path, sources: dict[str, str], monkeypatch: pytest.MonkeyPatch, inputs: dict | None = None):
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(root)
    return spike(root, sources, workflow=next(iter(sources)).removesuffix(".orc") + "::entry", inputs=inputs)[1]


def test_an_effectful_call_as_an_argument_is_bound_first_in_source_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review 2's probe. The flat route refuses it as a compiler defect at elaboration."""

    sources = {"spk/nested.orc": NESTED}
    flat_code, flat_outputs, _ = flat_entry(tmp_path / "flat", sources, monkeypatch)
    result = spiked(tmp_path / "spike", sources, monkeypatch)

    assert (flat_code, flat_outputs, calls(tmp_path / "flat")) == (2, {}, [])
    assert (result.value, calls(tmp_path / "spike")) == ({"n": 5}, ["fetch 4", "fetch 5"])


def test_the_omitted_run_context_is_the_runs_identity_and_two_constant_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`RunCtx` has three fields: `run-id` (the run's identity: the flat route's run id, the spike's run root
    name), `state-root` and `artifact-root` (constants on both routes)."""

    sources = {"spk/run_context.orc": RUN_CONTEXT}
    flat_code, flat_outputs, state = flat_entry(tmp_path / "flat", sources, monkeypatch)
    result = spiked(tmp_path / "spike", sources, monkeypatch)

    assert (flat_code, flat_outputs) == (0, {"return__run-id": state["run_id"], "return__state-root": "state/run",
                                             "return__artifact-root": "artifacts/run"})
    assert result.value == {"run-id": run_root(tmp_path / "spike").name, "state-root": "state/run",
                            "artifact-root": "artifacts/run"}


def test_a_provider_bundle_path_is_the_committed_attempts_result_file_outside_its_declared_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The value is a path the memo fixes (the committed attempt's result file), the same on every resume.
    Its declared type puts it under `state`: the flat route refuses its own bundle path as outside that root;
    the spike does not check path roots, and its result file is outside it too."""

    stand_in_provider(monkeypatch, {"choice": 7})
    sources = {"spk/bundle_path.orc": BUNDLE_PATH}
    flat_code, _, state = flat_entry(tmp_path / "flat", sources, monkeypatch, {"topic": "t"})
    result = spiked(tmp_path / "spike", sources, monkeypatch, {"topic": "t"})
    resumed = spiked(tmp_path / "spike", sources, monkeypatch, {"topic": "t"})

    frame = next(iter(state["call_frames"].values()))["state"]["steps"]["spk/bundle_path::pick__terminal_projection"]
    violation = frame["error"]["context"]["violations"][0]
    assert (flat_code, violation["type"], violation["context"]["under"]) == (1, "outside_under_root", "state")
    assert violation["context"]["value"].startswith(".orchestrate/workflow_lisp/calls/")
    (committed,) = [r for r in read_records(run_root(tmp_path / "spike")) if r["record"] == "committed"]
    expected = result_path(run_root(tmp_path / "spike"), committed["identity"], 1).relative_to(tmp_path / "spike")
    assert (result.value, resumed.value) == ({"choice": 7, "bundle": expected.as_posix()},) * 2
    assert not expected.as_posix().startswith("state/")


def test_a_phase_target_has_lost_its_with_phase_scope_in_normal_form(tmp_path: Path) -> None:
    """The one corpus use (`with_phase_composed_binding.orc`). Its value would be the phase context's
    `execution_report_target`; the atom carries only the target's name."""

    shutil.copy2(REPO / "workflows" / "examples" / "with_phase_composed_binding.orc", tmp_path)
    typed = typecheck_program(
        tmp_path / "with_phase_composed_binding.orc",
        entry_workflow="with_phase_composed_binding::run-with-phase-composed-binding", source_roots=(tmp_path,),
        command_boundaries={}, provider_externs={"providers.execute": "codex"},
        prompt_externs={"prompts.implementation.execute": "execute.md"})

    with pytest.raises(ClosedProgramGap, match="`phase-target execution-report` has lost its `with-phase` scope"):
        build_closed_program(typed)
