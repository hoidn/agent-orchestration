"""Numeric surface N6 and N7 for persisted values: resume and digests.

Contract: docs/design/workflow_lisp_numeric_surface.md, rules N6 and N7; Task 4
of docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md.

Resume reads values back from `state.json`, so it is a place where a value
enters a run. A 2.34 run whose first command committed and whose second failed
has its saved state edited; the resume through the public entry is refused with
`float_not_finite`, naming the field, before the next command is launched. At
2.33 the same edit is accepted, as today. The refusal covers non-finite values
only: a finite value edited by hand is still trusted.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from pathlib import Path

import pytest

from orchestrator._common.canonical import sha256_json
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.workflow.pure_expr import canonical_json_for_pure_value
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.test_workflow_lisp_generic_unions_runtime import (
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.workflow_lisp_improve_stdlib_sources import _PROBE_PRELUDE

# The command called with label "a" fails once; every other call answers a finite Score.
PROBE = _PROBE_PRELUDE + """marker = Path(__file__).with_name("failed-once")
if sys.argv[1] == "a" and not marker.exists():
    marker.write_text("yes", encoding="utf-8")
    sys.exit(1)
bundle = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
bundle.parent.mkdir(parents=True, exist_ok=True)
bundle.write_text('{"value": 1.5, "label": "a"}', encoding="utf-8")
"""

# `x` reaches every command; `first.value` reaches the command that fails once.
PROGRAM = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/entry)
  (export run)
  (defrecord Score (value Float) (label String))
  (defproc measure ((label String) (x Float) (y Float)) -> Score
    :effects ((uses-command probe))
    :lowering inline
    (command-result probe :argv ("python" "PROBE" label x y) :returns Score))
  (defworkflow inner ((y Float)) -> Score
    (measure "inner" y y))
  (defworkflow run ((x Float)) -> Score
    (let* ((first (measure "first" x x))
           (called (call inner :y x))
           (second (measure first.label x first.value)))
      second)))
"""

FIRST_RUN = ["first 1.0 1.0", "inner 1.0 1.0", "a 1.0 1.5"]


def _pointer_token(name: str) -> str:
    return name.replace("~", "~0").replace("/", "~1")


def _edit_input(state: dict) -> str:
    state["bound_inputs"]["x"] = math.nan
    return "/bound_inputs/x"


def _edit_artifact(state: dict) -> str:
    (name,) = [name for name, step in state["steps"].items() if step.get("artifacts", {}).get("value") == 1.5]
    state["steps"][name]["artifacts"]["value"] = math.inf
    return f"/steps/{_pointer_token(name)}/artifacts/value"


def _edit_call_frame(state: dict) -> str:
    (frame_id,) = state["call_frames"]
    state["call_frames"][frame_id]["state"]["bound_inputs"]["y"] = -math.inf
    return f"/call_frames/{_pointer_token(frame_id)}/state/bound_inputs/y"


EDITS = {"workflow-input": _edit_input, "committed-artifact": _edit_artifact, "call-frame": _edit_call_frame}
PRINTED = {"workflow-input": "nan", "committed-artifact": "inf", "call-frame": "-inf"}
# What the resumed command receives at 2.33, where the edit is accepted.
RESUMED_233 = {"workflow-input": "a nan 1.5", "committed-artifact": "a 1.0 inf", "call-frame": "a 1.0 1.5"}


def _run_until_the_second_command_fails(root: Path, target: str) -> tuple[Path, Path]:
    probe = _write_probe(root, "probe", PROBE)
    _write_sources(root, {"grt/entry.orc": PROGRAM.replace("TARGET", target).replace("PROBE", probe.as_posix())})
    inputs = root / "inputs.json"
    inputs.write_text('{"x": 1.0}', encoding="utf-8")
    result = _public_run(_public_run_files(root, {"probe": probe}), input_file=inputs)
    assert (result.exit_code, _log(probe)) == (1, FIRST_RUN)
    return probe, result.run_root / "state.json"


def _edit(state_path: Path, edit: Callable[[dict], str]) -> str:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    field = edit(state)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return field


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("edit", EDITS)
def test_234_resume_refuses_a_non_finite_float_in_saved_state(
    root: Path, edit: str, capsys: pytest.CaptureFixture[str]
) -> None:
    probe, state_path = _run_until_the_second_command_fails(root, "2.34")
    field = _edit(state_path, EDITS[edit])
    capsys.readouterr()

    exit_code = resume_workflow(run_id=state_path.parent.name, retry_delay_ms=0)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    (violation,) = state["error"]["context"]["violations"]
    assert (exit_code, state["status"], state["error"]["type"]) == (1, "failed", "float_not_finite")
    assert (violation["type"], violation["context"]) == ("float_not_finite", {"value": PRINTED[edit], "value_path": field})
    assert field in capsys.readouterr().err
    # No command was launched by the resume.
    assert _log(probe) == FIRST_RUN


@pytest.mark.parametrize("edit", EDITS)
def test_233_resume_accepts_a_non_finite_float_in_saved_state_as_today(root: Path, edit: str) -> None:
    probe, state_path = _run_until_the_second_command_fails(root, "2.33")
    _edit(state_path, EDITS[edit])

    exit_code = resume_workflow(run_id=state_path.parent.name, retry_delay_ms=0)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert (exit_code, state["status"], _log(probe)) == (0, "completed", [*FIRST_RUN, RESUMED_233[edit]])


# N7: a Float enters a digest as the shortest decimal that reads back as the same double.
DIGESTS = {
    "checkpoint": lambda value: sha256_json({"v": value}),
    "pure": lambda value: hashlib.sha256(canonical_json_for_pure_value({"v": value}).encode("utf-8")).hexdigest(),
    "run-ref": lambda value: canonical_sha256({"v": value}),
}


@pytest.mark.parametrize("name", DIGESTS)
def test_a_digest_distinguishes_every_double_and_only_doubles(name: str) -> None:
    digest = DIGESTS[name]
    value = 0.1 + 0.2

    assert digest(value) != digest(math.nextafter(value, 1.0))
    assert digest(value) == digest(float("0.30000000000000004"))
    assert digest(-0.0) != digest(0.0)
