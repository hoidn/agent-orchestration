"""F2 feasibility and profile-registry invariants for run-ref confinement.

Child authority (header, checked program, memo) can live in an external
control root through the existing `--state-dir` seam; a result file alone is
not authority. The confinement profile is never a registered backend.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.providers.isolation_backend import (
    ProviderIsolationBackendUnavailable,
    get_provider_isolation_backend,
)
from orchestrator.workflow.evaluated.memo import reduce_memo
from orchestrator.workflow.run_ref.evaluated_child import _captured_child_authority

REPO = Path(__file__).resolve().parents[1]
AUTHORITY = ("run.json", "closed_program.json", "memo.jsonl")
CHILD = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule child) (export run)
  (defworkflow run ((n Int)) -> Int (+ n 1)))'''


def _run_child_with_external_control_root(tmp_path: Path) -> tuple[Path, Path]:
    clone, control = tmp_path / "clone", tmp_path / "control"
    clone.mkdir()
    control.mkdir()
    (clone / "child.orc").write_text(CHILD, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "orchestrator", "run", "child.orc", "--input", "n=41",
         "--state-dir", str(control)],
        cwd=clone, env={**os.environ, "PYTHONPATH": str(REPO)},
        capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr
    [run_root] = [path for path in control.iterdir() if path.is_dir()]
    return clone, run_root


def test_child_run_authority_lives_only_in_external_control_root(tmp_path):
    # The clone still receives the compile cache (.orchestrate/build); a confined
    # child must not compile in the clone, which the clone-preparation task owns.
    clone, run_root = _run_child_with_external_control_root(tmp_path)

    in_clone = sorted(path.name for path in clone.rglob("*")
                      if path.name in AUTHORITY and "build" not in path.relative_to(clone).parts)

    assert (in_clone, all((run_root / name).is_file() for name in AUTHORITY)) == ([], True)


def test_external_control_root_memo_carries_the_terminal_value(tmp_path):
    _clone, run_root = _run_child_with_external_control_root(tmp_path)

    _header, _program, memo = _captured_child_authority(run_root)

    assert reduce_memo(memo, {}).terminal.data["value"] == 42


def test_result_file_alone_is_not_child_authority(tmp_path):
    run_root = tmp_path / "control" / "forged"
    run_root.mkdir(parents=True)
    (run_root / "result.json").write_text('{"__result__": 42}', encoding="utf-8")

    with pytest.raises(OSError):
        _captured_child_authority(run_root)


def test_confinement_profile_is_not_a_registered_isolation_backend():
    with pytest.raises(ProviderIsolationBackendUnavailable):
        get_provider_isolation_backend("run_ref_confinement.v1")
