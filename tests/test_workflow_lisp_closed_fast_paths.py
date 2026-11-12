"""Compile-side fast paths build the same programs as the reference paths."""

from __future__ import annotations

import shutil

import pytest

from orchestrator.cli.main import main
from orchestrator.workflow_lisp import procedure_typecheck
from tests.test_workflow_evaluated_fast_paths import force_reference_paths
from tests.test_workflow_lisp_closed_program_corpus import EXPECTED
from tests.workflow_evaluated_program_sources import growth_source, install, stock_source
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


def _outcome(workflow, scratch):
    """Digest and artifact bytes of a built program, or the refusal and its diagnostic."""
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir()
    result = try_build(workflow, scratch)
    if result.program is not None:
        return result.program.digest, result.program.artifact()
    return repr(result.outcome), repr(result.diagnostic)


@pytest.mark.parametrize("workflow", corpus(), ids=lambda workflow: workflow.key)
def test_fast_and_reference_paths_build_the_same_corpus_outcome(tmp_path, monkeypatch, workflow):
    fast = _outcome(workflow, tmp_path / "scratch")
    with monkeypatch.context() as reference:
        force_reference_paths(reference)
        assert _outcome(workflow, tmp_path / "scratch") == fast


def _compile_growth(monkeypatch, root):
    root.mkdir()
    files = install(root, growth_source(stock_source())[0], None)
    monkeypatch.chdir(root)
    assert main(["compile", str(files["source"]), "--source-root", str(files["source_root"]),
                 "--provider-externs-file", str(files["providers"]), "--prompt-externs-file", str(files["prompts"]),
                 "--command-boundaries-file", str(files["commands"])]) == 0
    (program,) = (root / ".orchestrate" / "build").glob("*/closed_program.json")
    return program.read_text().replace(str(root), "ROOT")


def test_fast_and_reference_paths_compile_the_same_growth_program(tmp_path, monkeypatch):
    fast = _compile_growth(monkeypatch, tmp_path / "fast")
    with monkeypatch.context() as reference:
        force_reference_paths(reference)
        assert _compile_growth(reference, tmp_path / "slow") == fast
