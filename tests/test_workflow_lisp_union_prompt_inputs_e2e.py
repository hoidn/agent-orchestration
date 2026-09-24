"""Public run/resume coverage for target-2.28 union prompt inputs."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.types import PreparedProviderPolicy
from orchestrator.workflow import pure_result_replay
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.executable_ir import NodeResultAddress
from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle
from orchestrator.workflow_lisp.wcc.defunctionalize import _binding_restore_value_document


_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.28")
  (defmodule union_prompt_e2e)
  (export run)
  (defrecord Details (message String))
  (defunion Decision
    (SCALAR (value Int))
    (PAYLOAD (value Details))
    (EMPTY))
  (defprompt consume-decision
    (:fills (decision :value Decision))
    -> Bool
    "{decision}")
  (defworkflow run () -> Bool
    (let* ((decision
             (provider-result providers.produce
               :prompt prompts.produce
               :inputs ()
               :returns Decision))
           (consumed
             (provider-result providers.consume
               :prompt (consume-decision :decision decision)
               :delivery :composed))
           (finished
             (provider-result providers.finish
               :prompt prompts.finish
               :inputs (decision)
               :returns Bool)))
      finished)))
"""

_ACTIVE_DECISIONS = (
    {"variant": "SCALAR", "value": 7},
    {"variant": "PAYLOAD", "value": {"message": "active"}},
    {"variant": "EMPTY"},
)

_IMPORTED_HELPER_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.28")
  (defmodule union_prompt_e2e/helper)
  (export Decision make-decision)
  (defrecord Details (message String))
  (defunion Decision
    (SCALAR (value Int))
    (PAYLOAD (value Details))
    (EMPTY))
  (defproc private-produce () -> Decision
    :effects ((uses-provider providers.produce))
    :lowering private-workflow
    (provider-result providers.produce
      :prompt prompts.produce
      :inputs ()
      :returns Decision))
  (defworkflow make-decision () -> Decision
    (private-produce)))
"""

_IMPORTED_CONSUMER_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.28")
  (defmodule union_prompt_e2e/consumer)
  (import union_prompt_e2e/helper :only (Decision make-decision))
  (export run)
  (defprompt consume-decision
    (:fills (decision :value Decision))
    -> Bool
    "{decision}")
  (defworkflow run () -> Bool
    (let* ((decision (call make-decision))
           (consumed
             (provider-result providers.consume
               :prompt (consume-decision :decision decision)
               :delivery :composed))
           (finished
             (provider-result providers.finish
               :prompt prompts.finish
               :inputs (decision)
               :returns Bool)))
      finished)))
"""


def _write_fixture(workspace: Path) -> dict[str, Path]:
    source = workspace / "union_prompt_e2e.orc"
    source.write_text(_SOURCE, encoding="utf-8")
    prompts = workspace / "prompts"
    prompts.mkdir()
    for name in ("produce", "finish"):
        (prompts / f"{name}.md").write_text(name + "\n", encoding="utf-8")
    providers = workspace / "providers.json"
    providers.write_text(
        json.dumps(
            {
                "providers.produce": "produce",
                "providers.consume": "consume",
                "providers.finish": "finish",
            }
        ),
        encoding="utf-8",
    )
    prompt_externs = workspace / "prompts.json"
    prompt_externs.write_text(
        json.dumps(
            {
                "prompts.produce": "prompts/produce.md",
                "prompts.finish": "prompts/finish.md",
            }
        ),
        encoding="utf-8",
    )
    return {
        "source": source,
        "source_root": workspace,
        "providers": providers,
        "prompts": prompt_externs,
    }


def _write_imported_fixture(workspace: Path) -> dict[str, Path]:
    helper = workspace / "union_prompt_e2e" / "helper.orc"
    helper.parent.mkdir()
    helper.write_text(_IMPORTED_HELPER_SOURCE, encoding="utf-8")
    consumer = helper.with_name("consumer.orc")
    consumer.write_text(_IMPORTED_CONSUMER_SOURCE, encoding="utf-8")
    prompts = helper.parent / "prompts"
    prompts.mkdir()
    for name in ("produce", "finish"):
        (prompts / f"{name}.md").write_text(name + "\n", encoding="utf-8")
    providers = workspace / "providers.json"
    providers.write_text(
        json.dumps(
            {
                "providers.produce": "produce",
                "providers.consume": "consume",
                "providers.finish": "finish",
            }
        ),
        encoding="utf-8",
    )
    prompt_externs = workspace / "prompts.json"
    prompt_externs.write_text(
        json.dumps(
            {
                "prompts.produce": "prompts/produce.md",
                "prompts.finish": "prompts/finish.md",
            }
        ),
        encoding="utf-8",
    )
    return {
        "source": consumer,
        "source_root": workspace,
        "providers": providers,
        "prompts": prompt_externs,
    }


def _build_request(workspace: Path, files: dict[str, Path]) -> FrontendBuildRequest:
    return FrontendBuildRequest(
        source_path=files["source"],
        source_roots=(workspace,),
        entry_workflow="run",
        provider_externs_path=files["providers"],
        prompt_externs_path=files["prompts"],
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=True,
        workspace_root=workspace,
    )


def _run_args(files: dict[str, Path]) -> Namespace:
    return Namespace(
        workflow=str(files["source"]),
        context=None,
        context_file=None,
        input=[],
        input_file=None,
        clean_processed=False,
        archive_processed=None,
        debug=False,
        stream_output=False,
        dry_run=False,
        backup_state=False,
        state_dir=None,
        on_error="stop",
        max_retries=0,
        retry_delay=0,
        quiet=True,
        verbose=False,
        log_level="error",
        step_summaries=False,
        summary_mode=None,
        summary_provider="claude_sonnet_summary",
        summary_timeout_sec=120,
        summary_max_input_chars=12000,
        summary_profile=None,
        live_agent_notes=False,
        live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000,
        entry_workflow="run",
        source_root=[str(files["source_root"])],
        provider_externs_file=str(files["providers"]),
        prompt_externs_file=str(files["prompts"]),
        imported_workflow_bundles_file=None,
        command_boundaries_file=None,
        emit_debug_yaml=True,
    )


def _run_argv(files: dict[str, Path]) -> list[str]:
    return [
        "orchestrator",
        "run",
        str(files["source"]),
        "--source-root",
        str(files["source_root"]),
        "--entry-workflow",
        "run",
        "--provider-externs-file",
        str(files["providers"]),
        "--prompt-externs-file",
        str(files["prompts"]),
        "--emit-debug-yaml",
    ]


def _run_id(workspace: Path) -> str:
    run_roots = list((workspace / ".orchestrate" / "runs").iterdir())
    assert len(run_roots) == 1
    return run_roots[0].name


def _assert_canonical_union_rendering_evidence(
    workspace: Path,
    run_id: str,
    *,
    step_id: str,
) -> None:
    evidence = json.loads(
        (
            workspace
            / ".orchestrate"
            / "runs"
            / run_id
            / "workflow_lisp"
            / "typed_prompt_inputs"
            / f"{step_id.replace('::', '_')}.json"
        ).read_text(encoding="utf-8")
    )
    assert len(evidence) == 1
    assert evidence[0]["binding_name"] == "decision"
    assert evidence[0]["renderer"]["renderer_id"] == "canonical-json"


def _transport(
    workspace: Path,
    *,
    active_decision: dict[str, object],
    malformed: bool = False,
):
    calls: list[dict[str, object]] = []

    def prepare(_self, provider_name, *_args, **kwargs):
        policy = kwargs.get("provider_call_policy") or {}
        prompt = str(kwargs.get("prompt_content", ""))
        invocation = SimpleNamespace(
            provider_name=provider_name,
            prompt=prompt,
            prepared_prompt=prompt,
            prepared_provider_policy=PreparedProviderPolicy(
                provider_name=provider_name,
                model=policy.get("model"),
                effort=policy.get("effort"),
                timeout_sec=kwargs.get("timeout_sec"),
                input_mode="stdin",
            ),
            env=dict(kwargs.get("env") or {}),
            input_mode="stdin",
        )
        calls.append({"provider": provider_name, "invocation": invocation})
        return invocation, None

    def execute(_self, invocation, **_kwargs):
        def result(exit_code: int, *, stderr: bytes = b""):
            return SimpleNamespace(
                exit_code=exit_code,
                stdout=b"",
                stderr=stderr,
                duration_ms=1,
                error=None,
                missing_placeholders=None,
                invalid_prompt_placeholder=False,
                raw_stdout=None,
                normalized_stdout=None,
                provider_session=None,
            )

        output = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if not output.is_absolute():
            output = workspace / output
        output.parent.mkdir(parents=True, exist_ok=True)
        provider = invocation.provider_name
        if provider == "produce":
            payload = {"variant": "UNKNOWN"} if malformed else active_decision
            output.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            return result(0)
        if provider == "consume":
            output.write_text("true\n", encoding="utf-8")
            return result(0)
        output.write_text("true\n", encoding="utf-8")
        return result(0)

    return calls, prepare, execute


class _PostCommitInterruption(BaseException):
    pass


@pytest.mark.parametrize("active_decision", _ACTIVE_DECISIONS)
def test_public_union_prompt_flow_resumes(
    tmp_path: Path, monkeypatch, active_decision: dict[str, object]
) -> None:
    files = _write_fixture(tmp_path)
    built = build_frontend_bundle(_build_request(tmp_path, files))
    consume = next(
        step
        for step in built.validated_bundle.surface.steps
        if step.provider == "consume"
    )
    assert len(consume.typed_prompt_inputs) == 1
    entry = consume.typed_prompt_inputs[0]
    assert entry["binding_name"] == "decision"
    assert entry["renderer"]["renderer_id"] == "canonical-json"
    assert entry["value_source"]["kind"] == "typed_union_projection"
    finish = next(step for step in built.validated_bundle.surface.steps if step.provider == "finish")
    assert finish.typed_prompt_inputs[0]["value_source"]["kind"] == "typed_union_projection"
    assert [
        {
            key: field[key]
            for key in ("name", "json_pointer", "type")
        }
        for field in consume.common.output_bundle["fields"]
    ] == [{"name": "__result__", "json_pointer": "", "type": "bool"}]

    calls, prepare, execute = _transport(
        tmp_path,
        active_decision=active_decision,
    )
    original_checkpoint_hook = (
        WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit
    )
    interrupted = False

    def interrupt_after_consumer_checkpoint(self, state, step_name, step, finalized):
        nonlocal interrupted
        original_checkpoint_hook(self, state, step_name, step, finalized)
        if step_name == "union_prompt_e2e::run__consumed" and not interrupted:
            interrupted = True
            raise _PostCommitInterruption

    monkeypatch.chdir(tmp_path)
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        interrupt_after_consumer_checkpoint,
    ), patch.object(sys, "argv", _run_argv(files)):
        with pytest.raises(_PostCommitInterruption):
            run_workflow(_run_args(files))

    assert [call["provider"] for call in calls] == ["produce", "consume"]
    canonical_active_decision = json.dumps(
        active_decision, sort_keys=True, separators=(",", ":")
    )
    assert calls[1]["invocation"].prompt.count(canonical_active_decision) == 1
    run_id = _run_id(tmp_path)
    _assert_canonical_union_rendering_evidence(
        tmp_path,
        run_id,
        step_id="root.union_prompt_e2e_run__consumed",
    )

    state_before_resume = json.loads(
        (tmp_path / ".orchestrate" / "runs" / run_id / "state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state_before_resume["steps"]["union_prompt_e2e::run__decision"][
        "artifacts"
    ]["variant"] == active_decision["variant"]
    assert state_before_resume["steps"]["union_prompt_e2e::run__consumed"]["artifacts"] == {
        "__result__": True
    }
    checkpoint_records = list(
        (tmp_path / ".orchestrate" / "runs" / run_id / "workflow_lisp" / "checkpoints" / "records").glob(
            "*/*.json"
        )
    )
    assert checkpoint_records
    for record_path in checkpoint_records:
        checkpoint = json.loads(record_path.read_text(encoding="utf-8"))
        assert "decision" not in {
            binding["binding_name"]
            for binding in checkpoint["restore_payload"]["bindings"]
        }

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ):
        assert resume_workflow(run_id=run_id, retry_delay_ms=0) == 0

    assert [call["provider"] for call in calls] == ["produce", "consume", "finish"]
    assert calls[-1]["invocation"].prompt.count(canonical_active_decision) == 1
    _assert_canonical_union_rendering_evidence(
        tmp_path,
        run_id,
        step_id="root.union_prompt_e2e_run__finished",
    )
    resumed = json.loads(
        (tmp_path / ".orchestrate" / "runs" / run_id / "state.json").read_text(
            encoding="utf-8"
        )
    )
    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"__result__": True}

    clean_workspace = tmp_path / "clean"
    clean_workspace.mkdir()
    clean_files = _write_fixture(clean_workspace)
    clean_calls, clean_prepare, clean_execute = _transport(
        clean_workspace, active_decision=active_decision
    )
    monkeypatch.chdir(clean_workspace)
    with patch.object(ProviderExecutor, "prepare_invocation", clean_prepare), patch.object(
        ProviderExecutor, "execute", clean_execute
    ), patch.object(sys, "argv", _run_argv(clean_files)):
        clean = run_workflow(_run_args(clean_files))

    assert clean.exit_code == 0
    assert dict(clean.workflow_outputs) == resumed["workflow_outputs"]
    assert [call["provider"] for call in clean_calls] == [
        "produce",
        "consume",
        "finish",
    ]


def test_malformed_union_result_does_not_invoke_consumer(
    tmp_path: Path, monkeypatch
) -> None:
    files = _write_fixture(tmp_path)
    calls, prepare, execute = _transport(
        tmp_path,
        active_decision=_ACTIVE_DECISIONS[0],
        malformed=True,
    )
    monkeypatch.chdir(tmp_path)
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ), patch.object(sys, "argv", _run_argv(files)):
        result = run_workflow(_run_args(files))

    assert result.exit_code == 1
    assert [call["provider"] for call in calls] == ["produce"]


@pytest.mark.parametrize("active_decision", _ACTIVE_DECISIONS)
def test_public_imported_private_union_flow_resumes(
    tmp_path: Path, monkeypatch, active_decision: dict[str, object]
) -> None:
    files = _write_imported_fixture(tmp_path)
    calls, prepare, execute = _transport(tmp_path, active_decision=active_decision)
    original_checkpoint_hook = (
        WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit
    )
    interrupted = False

    def interrupt_after_consumer_checkpoint(self, state, step_name, step, finalized):
        nonlocal interrupted
        original_checkpoint_hook(self, state, step_name, step, finalized)
        if step_name.endswith("__consumed") and not interrupted:
            interrupted = True
            raise _PostCommitInterruption

    monkeypatch.chdir(tmp_path)
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        interrupt_after_consumer_checkpoint,
    ), patch.object(sys, "argv", _run_argv(files)):
        with pytest.raises(_PostCommitInterruption):
            run_workflow(_run_args(files))

    assert [call["provider"] for call in calls] == ["produce", "consume"]
    run_id = _run_id(tmp_path)
    checkpoint_records = list(
        (tmp_path / ".orchestrate" / "runs" / run_id / "workflow_lisp" / "checkpoints" / "records").glob(
            "*/*.json"
        )
    )
    assert checkpoint_records
    for record_path in checkpoint_records:
        checkpoint = json.loads(record_path.read_text(encoding="utf-8"))
        assert "decision" not in {
            binding["binding_name"]
            for binding in checkpoint["restore_payload"]["bindings"]
        }
    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ):
        assert resume_workflow(run_id=run_id, retry_delay_ms=0) == 0

    assert [call["provider"] for call in calls] == ["produce", "consume", "finish"]
    assert calls[-1]["invocation"].prompt.count(
        json.dumps(active_decision, sort_keys=True, separators=(",", ":"))
    ) == 1


def test_checkpoint_restore_keeps_user_double_underscore_members() -> None:
    document = _binding_restore_value_document(
        {
            "__user_value": "root.steps.produce.artifacts.value",
            "__typed_union_prompt_source__": {"kind": "union"},
        }
    )

    assert document == {
        "__user_value": {"ref": "root.steps.produce.artifacts.value"},
    }


def test_variant_output_members_are_not_promoted_to_pure_contracts(
    tmp_path: Path,
) -> None:
    files = _write_fixture(tmp_path)
    bundle = build_frontend_bundle(_build_request(tmp_path, files)).validated_bundle
    decision = next(step for step in bundle.surface.steps if step.provider == "produce")
    address = NodeResultAddress(
        node_id=decision.step_id,
        field="artifacts",
        member="value__message",
    )

    pure_result_replay._validate_result_member(
        bundle,
        node_id=address.node_id,
        field=address.field,
        member=address.member,
        ref="root.steps.produce.artifacts.value__message",
    )
    assert pure_result_replay._compiled_node_result_contract(bundle, address) is None
    assert not pure_result_replay._result_contract_matches_binding_descriptor(
        bundle,
        address=address,
        binding_descriptor={"kind": "primitive", "name": "String"},
    )
    with pytest.raises(pure_result_replay.PureResultReplayIndexError):
        pure_result_replay._validate_result_member(
            bundle,
            node_id=address.node_id,
            field=address.field,
            member="undeclared",
            ref="root.steps.produce.artifacts.undeclared",
        )
