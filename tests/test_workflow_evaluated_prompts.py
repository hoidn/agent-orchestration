from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.deps.content_snapshot import (
    AuthoredDependencyRow,
    snapshot_content_dependencies,
)
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.assets import WorkflowAssetResolver
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.prompting import PromptComposer
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.workflows import PromptExtern
from tests.workflow_bundle_helpers import bundle_context_dict


def _run_flat(
    workflow_path: Path,
    workspace: Path,
    *,
    provider_externs: dict[str, str],
    prompt_externs: dict[str, PromptExtern],
    inputs: dict[str, object],
    run_id: str,
    extra_outputs: tuple[str, ...] = (),
) -> dict[str, object]:
    flat_compile = compile_stage3_module(
        workflow_path,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        validate_shared=True,
        workspace_root=workspace,
        lowering_route="legacy",
    )
    assert len(flat_compile.validated_bundles) == 1
    bundle = next(iter(flat_compile.validated_bundles.values()))
    contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    manager = StateManager(workspace, run_id=run_id)
    manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bind_workflow_inputs(contracts, inputs, workspace),
    )
    observed: dict[str, object] = {}

    def prepare(_self, *_args, **kwargs):
        observed["flat_prompt"] = kwargs["prompt_content"]
        env = kwargs.get("env") or {}
        observed["result_path"] = env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        return SimpleNamespace(
            input_mode="stdin",
            prompt=observed["flat_prompt"],
            env=env,
            prepared_prompt=observed["flat_prompt"],
            prepared_provider_policy=SimpleNamespace(
                to_dict=lambda: {
                    "provider_name": kwargs["provider_name"],
                    "model": None,
                    "effort": None,
                    "timeout_sec": kwargs.get("timeout_sec"),
                    "input_mode": "stdin",
                }
            ),
        ), None

    def execute(_self, invocation, **_kwargs):
        output = workspace / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("true\n", encoding="utf-8")
        for relative in extra_outputs:
            artifact = workspace / relative
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("controlled output\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ):
        completed = WorkflowExecutor(
            bundle, workspace, manager, retry_delay_ms=0
        ).execute(on_error="stop")
    assert completed["status"] == "completed"
    return observed


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

    def perform(node, operands, _identity):
        from orchestrator.workflow.evaluated.prompts import assemble_provider_prompt

        observed["node"] = node
        observed["operands"] = operands
        observed["prompt"] = assemble_provider_prompt(
            node,
            operands,
            source_text=source_text,
            dependency_snapshot=dependency_snapshot,
            result_path=result_path,
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
def test_external_prompt_order_and_source_kind_match_flat_executor(
    tmp_path: Path,
    source_kind: str,
    position: str,
) -> None:
    flat_source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
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
    workflow_path.write_text(flat_source, encoding="utf-8")
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
    provider_externs = {"providers.reply": "capturing-provider"}
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
    flat = _run_flat(
        workflow_path,
        tmp_path,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        inputs=inputs,
        run_id=f"flat-{source_kind}-{position}",
    )
    workflow_path.write_text(
        flat_source.replace(
            '(:target-dsl "2.34")',
            f'(:target-dsl "{syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")',
        ),
        encoding="utf-8",
    )
    evaluated_prompt, evaluated = _evaluate(
        workflow_path,
        tmp_path,
        inputs=inputs,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        source_text=captured_source,
        dependency_snapshot=snapshot,
        result_path=str(flat["result_path"]),
    )

    assert evaluated_prompt == flat["flat_prompt"]
    assert [row[0] for row in evaluated["node"]["inputs"]] == [
        "name",
        "name__2",
    ]
    assert str(flat["result_path"]) in evaluated_prompt
    dependency_at = evaluated_prompt.index("DEPENDENCY-CAPTURE")
    source_at = evaluated_prompt.index(f"SOURCE-CAPTURE-{source_kind}")
    typed_at = evaluated_prompt.index("FIRST-INPUT-CAPTURE")
    if position == "prepend":
        assert dependency_at < source_at < typed_at
    else:
        assert source_at < dependency_at < typed_at


def test_external_prompt_without_dependencies_matches_flat_executor(
    tmp_path: Path,
) -> None:
    flat_source = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule prompt_assembly)
  (export run)
  (defworkflow run ((message String)) -> Bool
    (provider-result providers.reply
      :prompt prompts.base :inputs (message) :returns Bool)))
'''
    workflow_path = tmp_path / "prompt_assembly.orc"
    workflow_path.write_text(flat_source, encoding="utf-8")
    source_ref = "inputs/source.md"
    source_path = tmp_path / source_ref
    source_path.parent.mkdir(parents=True)
    source_path.write_text("SOURCE-WITHOUT-DEPENDENCY\n", encoding="utf-8")
    prompt_externs = {
        "prompts.base": PromptExtern(name="prompts.base", input_file=source_ref)
    }
    provider_externs = {"providers.reply": "capturing-provider"}
    inputs: dict[str, object] = {"message": "INPUT-WITHOUT-DEPENDENCY"}
    source_text = _captured_source(
        workflow_path,
        tmp_path,
        source_kind="input_file",
        source_path=source_ref,
    )
    flat = _run_flat(
        workflow_path,
        tmp_path,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        inputs=inputs,
        run_id="flat-no-dependency",
    )
    workflow_path.write_text(
        flat_source.replace(
            '(:target-dsl "2.34")',
            f'(:target-dsl "{syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")',
        ),
        encoding="utf-8",
    )
    evaluated_prompt, _evaluated = _evaluate(
        workflow_path,
        tmp_path,
        inputs=inputs,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        source_text=source_text,
        dependency_snapshot=None,
        result_path=str(flat["result_path"]),
    )

    assert evaluated_prompt == flat["flat_prompt"]


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
        provider_externs={"providers.reply": "capturing-provider"},
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


def test_defprompt_docs_and_output_positions_match_flat_executor(
    tmp_path: Path,
) -> None:
    flat_source = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
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
    workflow_path.write_text(flat_source, encoding="utf-8")
    doc_relpath = "docs/design/brief.md"
    doc_file = tmp_path / doc_relpath
    doc_file.parent.mkdir(parents=True)
    doc_file.write_text("DOC-CAPTURE\n", encoding="utf-8")
    prompt_externs: dict[str, PromptExtern] = {}
    provider_externs = {"providers.reply": "capturing-provider"}
    inputs: dict[str, object] = {
        "document": doc_relpath,
        "message": "MESSAGE-CAPTURE\ncontinued\n",
        "score": 17,
        "report_path": "artifacts/work/report.md",
    }
    snapshot = _snapshot(tmp_path, doc_relpath, "document")
    flat = _run_flat(
        workflow_path,
        tmp_path,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        inputs=inputs,
        run_id="flat-defprompt",
        extra_outputs=("artifacts/work/report.md",),
    )
    workflow_path.write_text(
        flat_source.replace(
            '(:target-dsl "2.34")',
            f'(:target-dsl "{syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")',
        ),
        encoding="utf-8",
    )
    evaluated_prompt, _evaluated = _evaluate(
        workflow_path,
        tmp_path,
        inputs=inputs,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        source_text=None,
        dependency_snapshot=snapshot,
        result_path=str(flat["result_path"]),
    )

    assert evaluated_prompt == flat["flat_prompt"]
    assert evaluated_prompt.index("DOC-CAPTURE") < evaluated_prompt.index(
        "MESSAGE-CAPTURE"
    )
    assert str(flat["result_path"]) in evaluated_prompt
