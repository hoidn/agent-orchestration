"""Two unnamed effects in one scope compile with one `effect_site_positional` warning.

Plan: docs/plans/2026-11-11-roadmap-phase-2-qualification-metering-names-plan.md, C2.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


CODE = "effect_site_positional"
ASK = "(provider-result providers.review :prompt (ask :task TASK))"
TWO_UNNAMED = f"""(string/concat
      {ASK.replace("TASK", "task")}
      {ASK.replace("TASK", '"again"')})"""
NAMED_AND_TAIL = f"""(let* ((first {ASK.replace("TASK", "task")})
           (second {ASK.replace("TASK", "first")}))
      {ASK.replace("TASK", "second")})"""


def _source(body: str) -> str:
    return (
        "(workflow-lisp\n"
        '  (:language "0.1")\n'
        '  (:target-dsl "2.39")\n'
        "  (defmodule sites)\n"
        "  (export run)\n"
        '  (defprompt ask (:fills (task :text)) -> String "{task}")\n'
        "  (defworkflow run ((task String)) -> String\n"
        f"    {body}))\n"
    )


def _build(root: Path, body: str):
    path = root / "sites.orc"
    path.write_text(_source(body), encoding="utf-8")
    providers = root / "providers.json"
    providers.write_text('{"providers.review": "codex"}', encoding="utf-8")
    return build_closed_program_bundle(FrontendBuildRequest(
        source_path=path, source_roots=(root,), workspace_root=root,
        provider_externs_path=providers,
    ))


def _warnings(root: Path, body: str) -> list:
    return [d for d in _build(root, body).compile_diagnostics if d.code == CODE]


def test_two_unnamed_effects_in_one_scope_warn_at_both_places(tmp_path: Path) -> None:
    (warning,) = _warnings(tmp_path, TWO_UNNAMED)

    # Reported at the second effect (line 10), naming the first (line 9, column 7).
    assert ((warning.span.start.line, warning.span.start.column), "9:7" in warning.message) == ((10, 7), True)


def test_one_unnamed_tail_effect_and_named_effects_do_not_warn(tmp_path: Path) -> None:
    assert _warnings(tmp_path, NAMED_AND_TAIL) == []


def test_the_warning_changes_no_program_digest(tmp_path: Path) -> None:
    # Recorded from this source before the lint existed (commit 801a72ae).
    assert _build(tmp_path, TWO_UNNAMED).program.digest == PRE_LINT_DIGEST


def test_strict_profile_refuses_the_positional_sites(tmp_path: Path) -> None:
    path = tmp_path / "sites.orc"
    path.write_text(_source(TWO_UNNAMED), encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as refused:
        compile_stage3_entrypoint(
            path, source_roots=(tmp_path,), provider_externs={"providers.review": "codex"},
            prompt_externs={}, command_boundaries={}, workspace_root=tmp_path, lint_profile="strict",
        )
    assert [d.code for d in refused.value.diagnostics] == [CODE]


PRE_LINT_DIGEST = "sha256:945b4f720b83949b3b275dd6e459d560778512cacd5ee76c4ab6980893046934"
