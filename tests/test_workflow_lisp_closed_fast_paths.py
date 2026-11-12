"""Compile-side fast paths build the same programs as the reference paths."""

from __future__ import annotations

import pytest

from orchestrator.workflow_lisp import procedure_typecheck
from tests.test_workflow_lisp_closed_program_corpus import EXPECTED
from tests.workflow_lisp_closed_program_corpus import Built, corpus, try_build

_BUILT = [workflow for workflow in corpus() if isinstance(EXPECTED[workflow.key], Built)]


def _check_noop_rewrites(monkeypatch) -> list[object]:
    """With nothing to replace, the full rewrite (forced by a map that matches no node) is the identity."""
    real = procedure_typecheck._replace_eliminated_let_procs
    checked = []

    def rewrite(node, *, let_proc_rewrite_results=None):
        if not let_proc_rewrite_results:
            assert real(node, let_proc_rewrite_results={0: None}) == node
            checked.append(node)
        return real(node, let_proc_rewrite_results=let_proc_rewrite_results)

    monkeypatch.setattr(procedure_typecheck, "_replace_eliminated_let_procs", rewrite)
    return checked


@pytest.mark.parametrize("workflow", _BUILT, ids=lambda workflow: workflow.key)
def test_skipped_let_proc_rewrite_returns_what_the_full_rewrite_equals(tmp_path, monkeypatch, workflow):
    checked = _check_noop_rewrites(monkeypatch)
    assert try_build(workflow, tmp_path).program is not None
    assert checked
