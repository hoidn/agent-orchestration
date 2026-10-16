"""Source-to-runtime coverage for portable provider-context composition."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError

















def test_target_231_private_workflow_accepts_an_ordinary_nested_collection_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "ordinary_private.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.35\")
  (defmodule ordinary_private)
  (export keep)
  (defunion Choice (ONE (value Int)) (TWO (value Int)))
  (defrecord Packet (items List[Choice]))
  (defproc keep ((value Packet)) -> Packet
    :effects () :lowering private-workflow value))
""",
        encoding="utf-8",
    )

    compiled = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )

    (procedure,) = compiled.entry_result.typed_procedures
    assert procedure.resolved_lowering_mode.value == "private-workflow"
