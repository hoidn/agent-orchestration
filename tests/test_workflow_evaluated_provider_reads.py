"""Provider IO follows the checked activation through evaluated calls."""

from hashlib import sha256
from dataclasses import replace
from pathlib import Path

import orchestrator.deps.content_snapshot as content_snapshot
import pytest

from orchestrator.deps.content_snapshot import (
    MAX_INJECTION_BYTES,
    render_content_snapshot,
)
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow.evaluated.prompts import assemble_provider_prompt
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from tests.test_workflow_evaluated_provider_io import WREF, _checked, _stages, _typed


def test_evaluated_provider_reads_follow_parent_left_parent_right(tmp_path):
    _, imports = _stages(tmp_path)
    imports["right"].provenance.workflow_path.with_name("prompt.md").write_text(
        "TARGET RIGHT\n"
    )
    checked, provider_io = _checked(_typed(tmp_path, WREF, imports))
    reads = []

    def handle(node, operands, identity, owner, reader):
        from orchestrator.workflow.evaluated.providers import resolve_provider_io

        reads.append(
            (
                owner,
                resolve_provider_io(
                    node, operands, workspace=tmp_path, reader=reader
                ),
                node,
                operands,
            )
        )
        return coerce_evaluated_value(
            {"n": len(reads)}, node["result"], context="controlled provider result"
        )

    result = evaluate_closed_program(
        checked,
        {"input": {"n": 0}},
        effect_handler=handle,
        provider_io=provider_io,
    )

    assert [read.source_text for _, read, _, _ in reads] == [
        "PARENT INLINE\n",
        "TARGET LEFT\n",
        "PARENT INLINE\n",
        "TARGET RIGHT\n",
    ]
    assert [read.source_sha256 for _, read, _, _ in reads] == [
        "sha256:" + sha256(content.encode()).hexdigest()
        for content in (
            "PARENT INLINE\n",
            "TARGET LEFT\n",
            "PARENT INLINE\n",
            "TARGET RIGHT\n",
        )
    ]
    assert [read.source_path for _, read, _, _ in reads] == ["prompt.md"] * 4
    assert [read.source_kind for _, read, _, _ in reads] == ["asset_file"] * 4
    assert reads[0][0] == reads[2][0]
    assert reads[1][0] == reads[3][0]
    assert result.value == {"n": 4}
    _owner, read, node, operands = reads[-1]
    assembled = assemble_provider_prompt(
        node,
        operands,
        source_text=read.source_text,
        dependency_snapshot=read.dependency_snapshot,
        result_path="captured/result.json",
    )
    assert "TARGET RIGHT" in assembled


def _direct_program(tmp_path, prompt_externs, source):
    workflow_root = tmp_path / "workflow"
    workflow_path = workflow_root / "main.orc"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(source, encoding="utf-8")
    typed = compile_typed_program(
        workflow_path,
        entry_workflow="main::run",
        source_roots=(workflow_root,),
        command_boundaries={},
        provider_externs={"provider": "controlled-provider"},
        prompt_externs=prompt_externs,
        workspace_root=tmp_path,
    )
    return _checked(typed)


def _read_direct(checked, provider_io, tmp_path, inputs):
    from orchestrator.workflow.evaluated.providers import resolve_provider_io

    observed = []

    def handle(node, operands, _identity, owner, reader):
        observed.append(
            (
                owner,
                resolve_provider_io(
                    node, operands, workspace=tmp_path, reader=reader
                ),
                node,
                operands,
            )
        )
        return coerce_evaluated_value(True, node["result"])

    result = evaluate_closed_program(
        checked,
        inputs,
        effect_handler=handle,
        provider_io=provider_io,
    )
    return result, observed


def test_input_and_asset_with_same_path_use_different_roots(tmp_path):
    workflow_root = tmp_path / "workflow"
    workflow_root.mkdir()
    (workflow_root / "same.md").write_text("ASSET ROOT\n", encoding="utf-8")
    (tmp_path / "same.md").write_text("WORKSPACE ROOT\n", encoding="utf-8")
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defworkflow run ((message String)) -> Bool
        (provider-result provider :prompt prompt :inputs (message) :returns Bool)))'''

    asset_program, asset_io = _direct_program(
        tmp_path, {"prompt": {"asset_file": "same.md"}}, source
    )
    input_program, input_io = _direct_program(
        tmp_path, {"prompt": {"input_file": "same.md"}}, source
    )
    _, asset_reads = _read_direct(asset_program, asset_io, tmp_path, {"message": "x"})
    _, input_reads = _read_direct(input_program, input_io, tmp_path, {"message": "x"})

    assert asset_reads[0][1].source_text == "ASSET ROOT\n"
    assert input_reads[0][1].source_text == "WORKSPACE ROOT\n"
    assert asset_reads[0][1].source_kind == "asset_file"
    assert input_reads[0][1].source_kind == "input_file"
    assert asset_reads[0][1].source_path == input_reads[0][1].source_path == "same.md"


def test_input_source_absent_empty_and_raw_bytes_are_distinct(tmp_path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defworkflow run ((message String)) -> Bool
        (provider-result provider :prompt prompt :inputs (message) :returns Bool)))'''
    checked, provider_io = _direct_program(
        tmp_path, {"prompt": {"input_file": "source.md"}}, source
    )
    path = tmp_path / "source.md"

    _, absent = _read_direct(checked, provider_io, tmp_path, {"message": "x"})
    path.write_bytes(b"")
    _, empty = _read_direct(checked, provider_io, tmp_path, {"message": "x"})
    path.write_bytes(b"same\n")
    _, lf = _read_direct(checked, provider_io, tmp_path, {"message": "x"})
    path.write_bytes(b"same\r\n")
    _, crlf = _read_direct(checked, provider_io, tmp_path, {"message": "x"})

    assert absent[0][1].source_text == empty[0][1].source_text == ""
    assert absent[0][1].source_sha256 is None
    assert empty[0][1].source_sha256 == "sha256:" + sha256(b"").hexdigest()
    assert lf[0][1].source_text == crlf[0][1].source_text == "same\n"
    assert lf[0][1].source_sha256 != crlf[0][1].source_sha256


def test_duplicate_doc_fills_share_one_raw_snapshot(tmp_path, monkeypatch):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defpath DocPath :kind relpath :under "docs" :must-exist true)
      (defprompt review
        (:fills (document :doc DocPath) (again :doc DocPath) (message :text)) -> Bool
        "{message}")
      (defworkflow run ((document DocPath) (again DocPath) (message String)) -> Bool
        (provider-result provider
          :prompt (review :document document :again again :message message)
          )))'''
    checked, provider_io = _direct_program(tmp_path, {}, source)
    doc_path = tmp_path / "docs" / "brief.md"
    doc_path.parent.mkdir()
    doc_path.write_bytes(b"ONE READ\r\n")
    original = content_snapshot.read_text_with_sha256
    seen = []

    def counted(path, **kwargs):
        if Path(path).resolve() == doc_path.resolve():
            seen.append(Path(path))
        return original(path, **kwargs)

    monkeypatch.setattr(content_snapshot, "read_text_with_sha256", counted)
    _, observed = _read_direct(
        checked,
        provider_io,
        tmp_path,
        {"document": "docs/brief.md", "again": "docs/brief.md", "message": "hello"},
    )

    captured = observed[0][1]
    assert len(seen) == 1
    assert len(captured.dependency_snapshot.canonical_groups) == 1
    assert len(captured.dependency_snapshot.authored_rows) == 2
    assert captured.dependency_sha256s == {
        "docs/brief.md": "sha256:" + sha256(b"ONE READ\r\n").hexdigest()
    }
    _owner, _read, node, operands = observed[0]
    assembled = assemble_provider_prompt(
        node,
        operands,
        source_text=None,
        dependency_snapshot=captured.dependency_snapshot,
        result_path="captured/result.json",
    )
    assert "ONE READ" in assembled


def test_required_and_optional_dependency_aliases_share_one_raw_snapshot(
    tmp_path, monkeypatch
):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defpath DocPath :kind relpath :under "docs" :must-exist true)
      (defworkflow run
        ((first DocPath) (second DocPath) (optional DocPath) (message String)) -> Bool
        (provider-result provider :prompt prompt :inputs (message)
          :prompt-dependencies (:required (first second) :optional (optional)
            :position append :instruction "Captured files")
          :returns Bool)))'''
    checked, provider_io = _direct_program(
        tmp_path, {"prompt": {"asset_file": "prompt.md"}}, source
    )
    prompt_path = tmp_path / "workflow" / "prompt.md"
    prompt_path.write_text("BASE PROMPT\n", encoding="utf-8")
    doc_path = tmp_path / "docs" / "brief.md"
    doc_path.parent.mkdir()
    doc_path.write_bytes(b"ONE READ\r\n")
    original = content_snapshot.read_text_with_sha256
    seen = []

    def counted(path, **kwargs):
        if Path(path).resolve() == doc_path.resolve():
            seen.append(Path(path))
        return original(path, **kwargs)

    monkeypatch.setattr(content_snapshot, "read_text_with_sha256", counted)
    _, observed = _read_direct(
        checked,
        provider_io,
        tmp_path,
        {
            "first": "docs/brief.md",
            "second": "docs/brief.md",
            "optional": "docs/brief.md",
            "message": "hello",
        },
    )

    captured = observed[0][1]
    assert len(seen) == 1
    assert len(captured.dependency_snapshot.canonical_groups) == 1
    assert len(captured.dependency_snapshot.authored_rows) == 3
    assert set(captured.dependency_sha256s) == {"docs/brief.md"}


def test_raw_dependency_tail_changes_hash_but_not_captured_render(tmp_path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defpath DocPath :kind relpath :under "docs" :must-exist true)
      (defworkflow run ((document DocPath) (message String)) -> Bool
        (provider-result provider :prompt prompt :inputs (message)
          :prompt-dependencies (:required (document) :position append
            :instruction "Captured files")
          :returns Bool)))'''
    checked, provider_io = _direct_program(
        tmp_path, {"prompt": {"asset_file": "prompt.md"}}, source
    )
    (tmp_path / "workflow" / "prompt.md").write_text("BASE\n", encoding="utf-8")
    doc_path = tmp_path / "docs" / "large.md"
    doc_path.parent.mkdir()
    retained_prefix = b"x" * MAX_INJECTION_BYTES
    tail_length = 4096

    def capture(tail):
        doc_path.write_bytes(retained_prefix + tail)
        _, observed = _read_direct(
            checked,
            provider_io,
            tmp_path,
            {"document": "docs/large.md", "message": "hello"},
        )
        return observed[0][1]

    first = capture(b"a" * tail_length)
    second = capture(b"b" * tail_length)
    first_render = render_content_snapshot(
        first.dependency_snapshot, "Captured files"
    )
    second_render = render_content_snapshot(
        second.dependency_snapshot, "Captured files"
    )

    assert first.dependency_snapshot == second.dependency_snapshot
    assert first_render == second_render
    assert first_render.was_truncated
    assert first.dependency_sha256s["docs/large.md"] != second.dependency_sha256s[
        "docs/large.md"
    ]


def test_unreached_provider_does_not_read_prompt_source(tmp_path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defworkflow run ((should_read Bool) (message String)) -> Bool
        (if should_read
          (provider-result provider :prompt prompt :inputs (message) :returns Bool)
          false)))'''
    checked, provider_io = _direct_program(
        tmp_path, {"prompt": {"asset_file": "missing.md"}}, source
    )

    result, observed = _read_direct(
        checked, provider_io, tmp_path, {"should_read": False, "message": "unused"}
    )

    assert result.value is False
    assert observed == []


def test_asset_file_read_requires_a_checked_reader(tmp_path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defworkflow run ((message String)) -> Bool
        (provider-result provider :prompt prompt :inputs (message) :returns Bool)))'''
    checked, _provider_io = _direct_program(
        tmp_path, {"prompt": {"asset_file": "source.md"}}, source
    )
    (tmp_path / "workflow" / "source.md").write_text("SOURCE\n", encoding="utf-8")

    from orchestrator.workflow.evaluated.providers import resolve_provider_io

    def handle(node, operands, _identity, _owner, reader):
        resolve_provider_io(node, operands, workspace=tmp_path, reader=reader)
        return coerce_evaluated_value(True, node["result"])

    with pytest.raises(ValueError, match="checked reader"):
        evaluate_closed_program(
            checked,
            {"message": "x"},
            effect_handler=handle,
        )


def test_mismatched_provider_io_is_rejected_before_dispatch(tmp_path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defworkflow run ((message String)) -> Bool
        (provider-result provider :prompt prompt :inputs (message) :returns Bool)))'''
    checked, provider_io = _direct_program(
        tmp_path, {"prompt": {"asset_file": "source.md"}}, source
    )
    dispatched = []

    def handle(node, _operands, _identity, _owner, _reader):
        dispatched.append(node)
        return coerce_evaluated_value(True, node["result"])

    with pytest.raises(ValueError, match="carrier does not match"):
        evaluate_closed_program(
            checked,
            {"message": "x"},
            effect_handler=handle,
            provider_io=replace(provider_io, sites=frozenset()),
        )
    assert dispatched == []
