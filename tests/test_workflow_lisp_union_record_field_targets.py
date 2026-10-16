"""Current union variant record fields preserve bound values inside and outside loops."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


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
  (:target-dsl "2.35")
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

# The same variant outside a loop, filled from a `let*`-bound name.
NON_LOOP_SOURCE = SOURCE[: SOURCE.index("  (defworkflow run")] + """  (defworkflow run () -> Result
    (let* ((current (record Candidate :title "seed" :score 0)))
      (variant Result APPROVED :value current))))
"""

REBUILT = "(record Candidate :title state.current.title :score state.current.score)"
BOUND = "state.current"
ON_EXHAUSTED_VARIANT = "(variant Result EXHAUSTED"
DONE_VARIANT = "(variant Result APPROVED"

# Placement selects the two current loop result shapes.
PLACEMENTS = {
    "on-exhausted": (BOUND, REBUILT, ON_EXHAUSTED_VARIANT),
    "done": (REBUILT, BOUND, DONE_VARIANT),
    "both": (BOUND, BOUND, DONE_VARIANT),
}


def _write_program(root: Path, *, placement: str, limit: int) -> tuple[Path, Path]:
    probe = root / "probe_check.py"
    probe.write_text(PROBE, encoding="utf-8")
    exhausted_value, done_value, _ = PLACEMENTS[placement]
    source = (
        SOURCE.replace("LIMIT", str(limit))
        .replace("PROBE_PATH", probe.as_posix())
        .replace("EXHAUSTED_VALUE", exhausted_value)
        .replace("DONE_VALUE", done_value)
    )
    entry = root / "tgt" / "entry.orc"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(source, encoding="utf-8")
    return entry, probe


def _compile(root: Path, *, placement: str, limit: int = 1):
    entry, probe = _write_program(root, placement=placement, limit=limit)
    return compile_stage3_entrypoint(
        entry,
        source_roots=(root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={"probe_check": ExternalToolBinding(name="probe_check", stable_command=("python", probe.as_posix()))},
        validate_shared=True,
        workspace_root=root,

    )


def _location_of(entry: Path, marker: str) -> tuple[str, int, int]:
    for line_number, line in enumerate(entry.read_text(encoding="utf-8").splitlines(), start=1):
        if marker in line:
            return (entry.name, line_number, line.index(marker) + 1)
    raise AssertionError(f"{marker!r} not in {entry}")




@pytest.mark.parametrize("placement", sorted(PLACEMENTS))
@pytest.mark.parametrize(
    ("limit", "expected_variant"),
    [(1, "EXHAUSTED"), (2, "APPROVED")],
    ids=["exhausted", "approved"],
)
def test_current_target_types_a_record_field_filled_from_a_bound_name(
    tmp_path: Path, placement: str, limit: int, expected_variant: str
) -> None:
    result = _compile(tmp_path, placement=placement, limit=limit)
    workflow = result.entry_result.typed_program.workflows["tgt/entry::run"]
    assert workflow.signature.return_type_ref.name == "Result"
    assert workflow.typed_body.type_ref == workflow.signature.return_type_ref


def test_current_target_types_a_variant_outside_a_loop_filled_from_a_bound_name(tmp_path: Path) -> None:
    entry = tmp_path / "tgt" / "entry.orc"
    entry.parent.mkdir(parents=True)
    entry.write_text(NON_LOOP_SOURCE, encoding="utf-8")
    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,

    )

    workflow = result.entry_result.typed_program.workflows["tgt/entry::run"]
    assert workflow.signature.return_type_ref.name == "Result"
    assert workflow.typed_body.type_ref == workflow.signature.return_type_ref
