"""A union variant's record field filled from a bound name is a target-2.33 relaxation.

Owner decision D2 (Ruling 7 in the CF-1b ledger): targets up to 2.32 do not
change what they accept. Before CF-1b such a field was rejected at compile time
with `workflow_return_not_exportable` at the variant expression; from target
2.33 it lowers and runs. Hooks are command-backed probes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.test_workflow_lisp_generic_stdlib_composition import _execute_bundle


PROBE = """import json, os, sys
from pathlib import Path
title = sys.argv[1]
payload = {"variant": "PASS", "note": title} if title.endswith("+r") else {"variant": "FAIL", "note": title + "+r"}
bundle = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
if bundle:
    Path(bundle).parent.mkdir(parents=True, exist_ok=True)
    Path(bundle).write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps(payload))
"""

SOURCE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule tgt/entry)
  (export run)
  (defrecord Candidate (title String) (score Int))
  (defunion Check (PASS (note String)) (FAIL (note String)))
  (defunion Result (APPROVED (value Candidate)) (EXHAUSTED (value Candidate)))
  (defworkflow run () -> Result
    (loop/recur :max LIMIT
      :state (loop-state (current Candidate (record Candidate :title "seed" :score 0)))
      :on-exhausted (variant Result EXHAUSTED :value EXHAUSTED_VALUE)
      (fn (state)
        (let* ((check (command-result probe_check :argv ("python" "PROBE_PATH" state.current.title) :returns Check)))
          (match check
            ((PASS p) (done (variant Result APPROVED :value DONE_VALUE)))
            ((FAIL f)
             (continue (loop-state :like state
                         :current (record Candidate :title f.note :score (+ state.current.score 1)))))))))))
"""

REBUILT = "(record Candidate :title state.current.title :score state.current.score)"
BOUND = "state.current"
ON_EXHAUSTED_VARIANT = "(variant Result EXHAUSTED"
DONE_VARIANT = "(variant Result APPROVED"

# placement -> (:on-exhausted value, done value, the variant the pre-2.33 rejection names)
PLACEMENTS = {
    "on-exhausted": (BOUND, REBUILT, ON_EXHAUSTED_VARIANT),
    "done": (REBUILT, BOUND, DONE_VARIANT),
    "both": (BOUND, BOUND, DONE_VARIANT),
}


def _write_program(root: Path, *, target: str, placement: str, limit: int) -> tuple[Path, Path]:
    probe = root / "probe_check.py"
    probe.write_text(PROBE, encoding="utf-8")
    exhausted_value, done_value, _ = PLACEMENTS[placement]
    source = (
        SOURCE.replace("TARGET", target)
        .replace("LIMIT", str(limit))
        .replace("PROBE_PATH", probe.as_posix())
        .replace("EXHAUSTED_VALUE", exhausted_value)
        .replace("DONE_VALUE", done_value)
    )
    entry = root / "tgt" / "entry.orc"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(source, encoding="utf-8")
    return entry, probe


def _compile(root: Path, *, target: str, placement: str, limit: int = 1):
    entry, probe = _write_program(root, target=target, placement=placement, limit=limit)
    return compile_stage3_entrypoint(
        entry,
        source_roots=(root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={"probe_check": ExternalToolBinding(name="probe_check", stable_command=("python", probe.as_posix()))},
        validate_shared=True,
        workspace_root=root,
        lowering_route=None,
    )


def _location_of(entry: Path, marker: str) -> tuple[str, int, int]:
    for line_number, line in enumerate(entry.read_text(encoding="utf-8").splitlines(), start=1):
        if marker in line:
            return (entry.name, line_number, line.index(marker) + 1)
    raise AssertionError(f"{marker!r} not in {entry}")


@pytest.mark.parametrize("placement", sorted(PLACEMENTS))
@pytest.mark.parametrize("target", ["2.23", "2.28", "2.29", "2.32"])
def test_older_targets_reject_a_record_field_filled_from_a_bound_name(
    tmp_path: Path, target: str, placement: str
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path, target=target, placement=placement)

    diagnostic = excinfo.value.diagnostics[0]
    span = diagnostic.span.start
    assert (diagnostic.code, (Path(span.path).name, span.line, span.column)) == (
        "workflow_return_not_exportable",
        _location_of(tmp_path / "tgt" / "entry.orc", PLACEMENTS[placement][2]),
    )


@pytest.mark.parametrize("placement", sorted(PLACEMENTS))
@pytest.mark.parametrize(
    ("limit", "expected_variant"),
    [(1, "EXHAUSTED"), (2, "APPROVED")],
    ids=["exhausted", "approved"],
)
def test_target_233_runs_a_record_field_filled_from_a_bound_name(
    tmp_path: Path, placement: str, limit: int, expected_variant: str
) -> None:
    result = _compile(tmp_path, target="2.33", placement=placement, limit=limit)
    bundle = result.validated_bundles_by_name["tgt/entry::run"]

    outcome = _execute_bundle(bundle, workflow_path=tmp_path / "tgt" / "entry.orc", workspace=tmp_path, run_id="run")

    assert (outcome["status"], dict(outcome["workflow_outputs"])) == (
        "completed",
        {"return__variant": expected_variant, "return__value__title": "seed+r", "return__value__score": 1},
    )
