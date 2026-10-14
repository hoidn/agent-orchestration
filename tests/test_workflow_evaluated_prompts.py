from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.deps.content_snapshot import (
    AuthoredDependencyRow,
    snapshot_content_dependencies,
)
from orchestrator.workflow.assets import WorkflowAssetResolver
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow.prompting import PromptComposer
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.workflows import PromptExtern


def _captured_source(
    workflow_path: Path,
    workspace: Path,
    *,
    source_kind: str,
    source_path: str,
) -> str:
    source, _digest, error = PromptComposer(
        workspace=workspace,
        asset_resolver=WorkflowAssetResolver(workflow_path),
    ).read_prompt_source_with_sha256(
        {source_kind: source_path},
        step_name="reply",
        contract_violation_result=lambda *_args: {},
    )
    assert error is None
    return source


def _evaluate(
    workflow_path: Path,
    workspace: Path,
    *,
    inputs: dict[str, object],
    provider_externs: dict[str, str],
    prompt_externs: dict[str, PromptExtern],
    source_text: str | None,
    dependency_snapshot,
    result_path: str,
) -> tuple[str, dict[str, object]]:
    typed = compile_typed_program(
        workflow_path,
        entry_workflow="prompt_assembly::run",
        source_roots=(workspace,),
        command_boundaries={},
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        workspace_root=workspace,
    )
    closed = build_closed_program(typed)
    observed: dict[str, object] = {}

    def perform(node, operands, _identity, _owner, _reader):
        from orchestrator.workflow.evaluated.prompts import assemble_provider_prompt

        observed["node"] = node
        observed["operands"] = operands
        observed["prompt"] = assemble_provider_prompt(
            node,
            operands,
            source_text=source_text,
            dependency_snapshot=dependency_snapshot,
            result_path=result_path,
            delivery="legacy",
        )
        return coerce_evaluated_value(True, node["result"])

    evaluate_closed_program(closed, inputs, effect_handler=perform)
    return str(observed["prompt"]), observed


def _snapshot(workspace: Path, relpath: str, binding: str):
    return snapshot_content_dependencies(
        workspace,
        (
            AuthoredDependencyRow(
                role="required",
                authored_index=0,
                binding_ref=f"inputs.{binding}",
                evaluated_relpath=relpath,
                canonical_target=relpath,
            ),
        ),
    )


@pytest.mark.parametrize(
    ("source_kind", "position"),
    (
        ("input_file", "prepend"),
        ("input_file", "append"),
        ("asset_file", "prepend"),
        ("asset_file", "append"),
    ),
)
def test_external_prompt_order_and_source_kind_preserve_captured_dataflow(
    tmp_path: Path,
    source_kind: str,
    position: str,
) -> None:
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule prompt_assembly)
  (export run)
  (defpath Note :kind relpath :under "artifacts/work" :must-exist true)
  (defworkflow run ((name String) (name__2 String) (note Note)) -> Bool
    (provider-result providers.reply
      :prompt prompts.base
      :inputs (name name__2)
      :prompt-dependencies
        (:required (note) :position {position} :instruction "Use the captured dependency.")
      :returns Bool)))
'''
    workflow_path = tmp_path / "prompt_assembly.orc"
    workflow_path.write_text(source, encoding="utf-8")
    source_ref = (
        "inputs/source.md" if source_kind == "input_file" else "assets/source.md"
    )
    source_path = tmp_path / source_ref
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_text = f"SOURCE-CAPTURE-{source_kind}\n"
    source_path.write_text(source_text, encoding="utf-8")
    dependency_path = "artifacts/work/note.md"
    dependency_file = tmp_path / dependency_path
    dependency_file.parent.mkdir(parents=True)
    dependency_file.write_text("DEPENDENCY-CAPTURE\n", encoding="utf-8")
    prompt_externs = {
        "prompts.base": PromptExtern(
            name="prompts.base",
            **{source_kind: source_ref},
        )
    }
    provider_externs = {"providers.reply": "codex"}
    inputs: dict[str, object] = {
        "name": "FIRST-INPUT-CAPTURE",
        "name__2": "AUTHORED-SUFFIX-CAPTURE",
        "note": dependency_path,
    }
    captured_source = _captured_source(
        workflow_path,
        tmp_path,
        source_kind=source_kind,
        source_path=source_ref,
    )
    snapshot = _snapshot(tmp_path, dependency_path, "note")
    evaluated_prompt, evaluated = _evaluate(
        workflow_path,
        tmp_path,
        inputs=inputs,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        source_text=captured_source,
        dependency_snapshot=snapshot,
        result_path="captured-result-path",
    )

    assert [row[0] for row in evaluated["node"]["inputs"]] == [
        "name",
        "name__2",
    ]
    assert "captured-result-path" in evaluated_prompt
    assert evaluated_prompt.count(inputs["name__2"]) == 1
    assert evaluated_prompt.count(inputs["name"]) == 1
    dependency_at = evaluated_prompt.index("DEPENDENCY-CAPTURE")
    source_at = evaluated_prompt.index(f"SOURCE-CAPTURE-{source_kind}")
    typed_at = evaluated_prompt.index("FIRST-INPUT-CAPTURE")
    if position == "prepend":
        assert dependency_at < source_at < typed_at
    else:
        assert source_at < dependency_at < typed_at


def test_external_prompt_without_dependencies_preserves_captured_dataflow(
    tmp_path: Path,
) -> None:
    source = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule prompt_assembly)
  (export run)
  (defworkflow run ((message String)) -> Bool
    (provider-result providers.reply
      :prompt prompts.base :inputs (message) :returns Bool)))
'''
    workflow_path = tmp_path / "prompt_assembly.orc"
    workflow_path.write_text(source, encoding="utf-8")
    source_ref = "inputs/source.md"
    source_path = tmp_path / source_ref
    source_path.parent.mkdir(parents=True)
    source_path.write_text("SOURCE-WITHOUT-DEPENDENCY\n", encoding="utf-8")
    prompt_externs = {
        "prompts.base": PromptExtern(name="prompts.base", input_file=source_ref)
    }
    provider_externs = {"providers.reply": "codex"}
    inputs: dict[str, object] = {"message": "INPUT-WITHOUT-DEPENDENCY"}
    source_text = _captured_source(
        workflow_path,
        tmp_path,
        source_kind="input_file",
        source_path=source_ref,
    )
    evaluated_prompt, _evaluated = _evaluate(
        workflow_path,
        tmp_path,
        inputs=inputs,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        source_text=source_text,
        dependency_snapshot=None,
        result_path="captured-result-path",
    )

    assert evaluated_prompt.index("SOURCE-WITHOUT-DEPENDENCY") < evaluated_prompt.index(inputs["message"])
    assert evaluated_prompt.count(inputs["message"]) == 1
    assert "captured-result-path" in evaluated_prompt



def test_evaluated_provider_labels_reserve_authored_suffixes(
    tmp_path: Path,
) -> None:
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")
  (defmodule prompt_assembly)
  (export run)
  (defworkflow run ((name String) (name__2 String)) -> Bool
    (provider-result providers.reply
      :prompt prompts.base :inputs (name name name__2) :returns Bool)))
'''
    workflow_path = tmp_path / "prompt_assembly.orc"
    workflow_path.write_text(source, encoding="utf-8")
    source_ref = "inputs/source.md"
    source_path = tmp_path / source_ref
    source_path.parent.mkdir(parents=True)
    source_path.write_text("CAPTURED-SOURCE\n", encoding="utf-8")
    prompt_externs = {
        "prompts.base": PromptExtern(name="prompts.base", input_file=source_ref)
    }
    inputs: dict[str, object] = {
        "name": "DUPLICATED-VALUE",
        "name__2": "AUTHORED-SUFFIX-VALUE",
    }
    source_text = _captured_source(
        workflow_path,
        tmp_path,
        source_kind="input_file",
        source_path=source_ref,
    )
    evaluated_prompt, evaluated = _evaluate(
        workflow_path,
        tmp_path,
        inputs=inputs,
        provider_externs={"providers.reply": "codex"},
        prompt_externs=prompt_externs,
        source_text=source_text,
        dependency_snapshot=None,
        result_path="captured-result-path",
    )

    assert [row[0] for row in evaluated["node"]["inputs"]] == [
        "name",
        "name__3",
        "name__2",
    ]
    assert evaluated_prompt.count("DUPLICATED-VALUE") == 2
    assert evaluated_prompt.count("AUTHORED-SUFFIX-VALUE") == 1


def test_defprompt_docs_and_output_positions_preserve_captured_dataflow(
    tmp_path: Path,
) -> None:
    source = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule prompt_assembly)
  (export run)
  (defpath DesignDocPath :kind relpath :under "docs/design" :must-exist true)
  (defpath WorkReportPath :kind relpath :under "artifacts/work" :must-exist false)
  (defprompt review
    (:fills
      (document :doc DesignDocPath)
      (message :text)
      (score :value Int)
      (report_path :path :out WorkReportPath))
    -> Bool
    "{{title}}\\nMessage={message}; score={score}; report={report_path}; repeat={message}\\n")
  (defworkflow run
    ((document DesignDocPath) (message String) (score Int) (report_path WorkReportPath))
    -> Bool
    (provider-result providers.reply
      :prompt (review :document document :message message :score score :report_path report_path)
      )))
'''
    workflow_path = tmp_path / "prompt_assembly.orc"
    workflow_path.write_text(source, encoding="utf-8")
    doc_relpath = "docs/design/brief.md"
    doc_file = tmp_path / doc_relpath
    doc_file.parent.mkdir(parents=True)
    doc_file.write_text("DOC-CAPTURE\n", encoding="utf-8")
    prompt_externs: dict[str, PromptExtern] = {}
    provider_externs = {"providers.reply": "codex"}
    inputs: dict[str, object] = {
        "document": doc_relpath,
        "message": "MESSAGE-CAPTURE\ncontinued\n",
        "score": 17,
        "report_path": "artifacts/work/report.md",
    }
    snapshot = _snapshot(tmp_path, doc_relpath, "document")
    evaluated_prompt, _evaluated = _evaluate(
        workflow_path,
        tmp_path,
        inputs=inputs,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        source_text=None,
        dependency_snapshot=snapshot,
        result_path="captured-result-path",
    )

    assert evaluated_prompt.count(inputs["message"].strip()) == 2
    assert str(inputs["score"]) in evaluated_prompt
    assert inputs["report_path"] in evaluated_prompt
    assert evaluated_prompt.index("DOC-CAPTURE") < evaluated_prompt.index(
        "MESSAGE-CAPTURE"
    )
    assert "captured-result-path" in evaluated_prompt
