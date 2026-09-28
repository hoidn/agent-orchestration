"""CF-1b Task 4: generic unions instantiated through specialization, end to end.

Contract: docs/design/workflow_lisp_parametric_type_system.md, "Proposed CF-1
First-Order Generic Unions"; transport obligations in
docs/design/workflow_lisp_composition_first.md sections 4, 9 and 10.

Hooks are command-backed probes (the supported deterministic route); every
probe appends its argv to a call log so tests can assert provider-free replay.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.test_workflow_lisp_generic_stdlib_composition import _execute_bundle

HEADER = '(workflow-lisp\n  (:language "0.1")\n  (:target-dsl "2.33")\n'

DECISION_LIB = HEADER + """  (defmodule grt/lib)
  (export Decision Box keep-first)
  (defunion Decision :forall (F B)
    (APPROVE (evidence F))
    (BLOCKED (reason B)))
  (defrecord Box (n Int))
  (defproc keep-first
    :forall (F B)
    ((decision Decision[F B]) (fallback F))
    -> Box
    :effects ()
    (record Box :n 1)))
"""

TRIVIAL_ENTRY = HEADER + """  (defmodule grt/entry)
  (import grt/lib :only (Decision))
  (export run)
  (defrecord Out (n Int))
  (defworkflow run () -> Out
    (record Out :n 1)))
"""


def _write_sources(root: Path, sources: dict[str, str]) -> Path:
    for relative, text in sources.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root / "grt" / "entry.orc"


def _compile(root: Path, *, probes: dict[str, Path] | None = None, validate_shared: bool = True):
    return compile_stage3_entrypoint(
        root / "grt" / "entry.orc",
        source_roots=(root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            name: ExternalToolBinding(name=name, stable_command=("python", path.as_posix()))
            for name, path in (probes or {}).items()
        },
        validate_shared=validate_shared,
        workspace_root=root,
        lowering_route=None,
    )


def test_uncalled_generic_with_applied_union_parameter_compiles(tmp_path: Path) -> None:
    """Addendum A: a generic template is not lowered before specialization."""

    _write_sources(tmp_path, {"grt/lib.orc": DECISION_LIB, "grt/entry.orc": TRIVIAL_ENTRY})

    result = _compile(tmp_path)

    assert "grt/entry::run" in result.validated_bundles_by_name


CALLING_ENTRY = HEADER + """  (defmodule grt/entry)
  (import grt/lib :only (Decision Box keep-first))
  (export run)
  (defrecord Note (text String))
  (defworkflow run () -> Box
    (keep-first (variant Decision[Note Note] APPROVE :evidence (record Note :text "a"))
                (record Note :text "b"))))
"""


def test_generic_with_applied_union_parameter_lowers_after_specialization(tmp_path: Path) -> None:
    _write_sources(tmp_path, {"grt/lib.orc": DECISION_LIB, "grt/entry.orc": CALLING_ENTRY})

    result = _compile(tmp_path)

    assert "grt/entry::run" in result.validated_bundles_by_name
