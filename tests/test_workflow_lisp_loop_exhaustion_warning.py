"""A loop without `:on-exhausted` compiles with one located warning.

Plan: docs/plans/2026-11-11-roadmap-phase-1-first-hour-plan.md, Task 2.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle


CODE = "loop_missing_on_exhausted"
LOOP = "(loop/recur :max 3 :state 0EXHAUSTED (fn (n) (if (>= n 2) (done n) (continue (+ n 1)))))"


def _source(*, in_procedure: bool = False, exhausted: str = "") -> str:
    loop = LOOP.replace("EXHAUSTED", exhausted)
    body = "(count)" if in_procedure else loop
    procedure = f"  (defproc count () -> Int\n    {loop})\n" if in_procedure else ""
    return (
        "(workflow-lisp\n"
        '  (:language "0.1")\n'
        '  (:target-dsl "2.39")\n'
        "  (defmodule counter)\n"
        "  (export run)\n"
        f"{procedure}"
        "  (defworkflow run () -> Int\n"
        f"    {body}))\n"
    )


def _write(root: Path, text: str) -> Path:
    path = root / "counter.orc"
    path.write_text(text, encoding="utf-8")
    return path


def _warnings(root: Path, text: str) -> list[tuple[str, str, int]]:
    path = _write(root, text)
    built = build_closed_program_bundle(
        FrontendBuildRequest(source_path=path, source_roots=(root,), workspace_root=root)
    )
    return [
        (d.code, Path(d.span.start.path).name, d.span.start.line)
        for d in built.compile_diagnostics
    ]


def test_loop_without_on_exhausted_compiles_with_one_located_warning(tmp_path: Path) -> None:
    assert _warnings(tmp_path, _source()) == [(CODE, "counter.orc", 7)]


def test_loop_inside_a_procedure_is_warned_too(tmp_path: Path) -> None:
    assert _warnings(tmp_path, _source(in_procedure=True)) == [(CODE, "counter.orc", 7)]


def test_loop_with_on_exhausted_has_no_warning(tmp_path: Path) -> None:
    assert _warnings(tmp_path, _source(exhausted=" :on-exhausted 99")) == []


GENERIC = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule lib/keep)
  (export keep)
  (defproc keep :forall (S) ((initial S)) -> S
    :effects ()
    (loop/recur :max 2 :state initial (fn (s) (done s)))))
"""


def test_an_imported_generic_procedure_is_warned_once_at_its_definition(tmp_path: Path) -> None:
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "keep.orc").write_text(GENERIC, encoding="utf-8")
    entry = _source(exhausted=" :on-exhausted 99").replace(
        "  (export run)\n", "  (import lib/keep :only (keep))\n  (export run)\n"
    ).replace("(done n)", "(done (keep n))")

    assert _warnings(tmp_path, entry) == [(CODE, "keep.orc", 8)]


def test_compile_command_prints_the_warning_and_exits_zero(tmp_path: Path) -> None:
    path = _write(tmp_path, _source())
    result = subprocess.run(
        [sys.executable, "-m", "orchestrator", "compile", str(path)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1])},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "program_digest" in json.loads(result.stdout)
    assert f"counter.orc:7:5: [{CODE}]" in result.stderr
