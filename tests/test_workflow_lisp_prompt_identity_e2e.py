"""End-to-end Q3 retry identity, publication, and report acceptance."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.observability.report import (
    build_status_snapshot,
    render_status_markdown,
)
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.types import (
    InputMode,
    PreparedProviderPolicy,
    ProviderInvocation,
)
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.prompt_context_report import (
    PROMPT_CONTEXT_REPORT_SCHEMA,
)
from orchestrator.workflow.prompt_dependency_evidence import (
    FRAGMENT_SUCCESS_SCHEMA_V2,
    validate_fragment_success_evidence_v2,
)
from tests.test_workflow_lisp_prompt_identity_runtime import (
    _runtime_q3_fixture,
    _successful_execution,
)


def _failed_execution() -> SimpleNamespace:
    return SimpleNamespace(
        exit_code=1,
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


def test_target_222_retry_attributes_changed_roles_before_terminal_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence
    from orchestrator.workflow import prompting

    bundle, manager = _runtime_q3_fixture(tmp_path)
    phase = {"retry": False}
    prepared_prompts: list[str] = []
    lifecycle: list[str] = []

    original_resolve = WorkflowExecutor._resolve_typed_prompt_input_value

    def resolve_binding(self, value, state, *, scope=None):
        resolved, error = original_resolve(
            self,
            value,
            state,
            scope=scope,
        )
        if (
            phase["retry"]
            and isinstance(value, dict)
            and value.get("ref") == "inputs.message"
        ):
            return "MESSAGE_RETRY_SENTINEL", error
        return resolved, error

    original_output_contract = prompting.render_output_contract_block

    def render_output_contract(value):
        suffix = (
            "RUNTIME_CONTRIBUTION_RETRY_SENTINEL"
            if phase["retry"]
            else "RUNTIME_CONTRIBUTION_INITIAL_SENTINEL"
        )
        return f"{original_output_contract(value)}\n{suffix}"

    def prepare(_self, *_args, **kwargs):
        prompt = kwargs["prompt_content"]
        prepared_prompts.append(prompt)
        lifecycle.append(f"prepare-{len(prepared_prompts)}")
        policy = PreparedProviderPolicy(
            provider_name=kwargs["provider_name"],
            model=(
                "retry-model"
                if phase["retry"]
                else "initial-model"
            ),
            effort=None,
            timeout_sec=kwargs.get("timeout_sec"),
            input_mode="stdin",
        )
        return (
            ProviderInvocation(
                command=["capturing-provider"],
                input_mode=InputMode.STDIN,
                prompt=prompt,
                env=kwargs.get("env") or {},
                prepared_prompt=prompt,
                prepared_provider_policy=policy,
            ),
            None,
        )

    actual_publish = evidence.publish_evidence_file

    def publish(state_manager, scope, ordinal, record, **kwargs):
        lifecycle.append(f"publish-{ordinal}")
        return actual_publish(
            state_manager,
            scope,
            ordinal,
            record,
            **kwargs,
        )

    launches = 0

    def execute(_self, invocation, **_kwargs):
        nonlocal launches
        launches += 1
        lifecycle.append(f"launch-{launches}")
        if launches == 1:
            dependency = tmp_path / "docs" / "design" / "target.md"
            dependency.write_text(
                "DOCUMENT_RETRY_SENTINEL\n",
                encoding="utf-8",
            )
            phase["retry"] = True
            return _failed_execution()
        return _successful_execution(tmp_path, invocation)

    monkeypatch.setattr(
        WorkflowExecutor,
        "_resolve_typed_prompt_input_value",
        resolve_binding,
    )
    monkeypatch.setattr(
        prompting,
        "render_output_contract_block",
        render_output_contract,
    )
    monkeypatch.setattr(
        ProviderExecutor,
        "prepare_invocation",
        prepare,
    )
    monkeypatch.setattr(
        "orchestrator.workflow.executor.publish_evidence_file",
        publish,
    )
    monkeypatch.setattr(ProviderExecutor, "execute", execute)

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
        max_retries=1,
    ).execute(on_error="stop")

    assert result["status"] == "completed", (
        result.get("error"),
        result.get("steps"),
    )
    assert lifecycle == [
        "prepare-1",
        "publish-1",
        "launch-1",
        "prepare-2",
        "publish-2",
        "launch-2",
    ]
    assert len(prepared_prompts) == 2
    assert "MESSAGE_RETRY_SENTINEL" not in prepared_prompts[0]
    assert "MESSAGE_RETRY_SENTINEL" in prepared_prompts[1]
    assert "DOCUMENT_RETRY_SENTINEL" not in prepared_prompts[0]
    assert "DOCUMENT_RETRY_SENTINEL" in prepared_prompts[1]
    assert "RUNTIME_CONTRIBUTION_INITIAL_SENTINEL" in (
        prepared_prompts[0]
    )
    assert "RUNTIME_CONTRIBUTION_RETRY_SENTINEL" in (
        prepared_prompts[1]
    )

    state = manager._read_state_from_disk().to_dict()
    [allocation] = state["provider_attempt_allocations"].values()
    assert allocation["last_allocated_ordinal"] == 2
    assert [
        (event["ordinal"], event["event"])
        for event in allocation["events"]
    ] == [
        (1, "allocated"),
        (1, "evidence_published"),
        (2, "allocated"),
        (2, "evidence_published"),
    ]
    publications = [
        event
        for event in allocation["events"]
        if event["event"] == "evidence_published"
    ]
    records = [
        json.loads(
            (manager.run_root / event["relative_path"]).read_text(
                encoding="ascii"
            )
        )
        for event in publications
    ]
    assert [record["schema"] for record in records] == [
        FRAGMENT_SUCCESS_SCHEMA_V2,
        FRAGMENT_SUCCESS_SCHEMA_V2,
    ]
    for record in records:
        assert validate_fragment_success_evidence_v2(
            record,
            compiler_fragment_identity_schema_version=(
                allocation[
                    "prompt_fragment_identity_schema_version"
                ]
            ),
        ) == record

    snapshot = build_status_snapshot(
        bundle,
        state,
        manager.run_root,
    )
    assert snapshot["run"]["status"] == "completed"
    prompt_context = snapshot["prompt_context"]
    assert prompt_context["schema_version"] == (
        PROMPT_CONTEXT_REPORT_SCHEMA
    )
    assert [
        attempt["attempt_ordinal"]
        for attempt in prompt_context["attempts"]
    ] == [1, 2]
    assert prompt_context["attempts"][0]["comparison"] == {
        "status": "unavailable",
        "previous_attempt_ordinal": None,
        "classifications": [],
        "reason": "no_predecessor",
    }
    assert prompt_context["attempts"][1]["comparison"] == {
        "status": "available",
        "previous_attempt_ordinal": 1,
        "classifications": [
            "input_drift",
            "dependency_content_drift",
            "runtime_prelude_drift",
            "provider_policy_drift",
        ],
        "reason": None,
    }

    content_free_projection = json.dumps(
        prompt_context,
        sort_keys=True,
    )
    prompt_context_markdown = render_status_markdown(snapshot).split(
        "## Prompt context",
        1,
    )[1]
    for forbidden in (
        "MESSAGE_SENTINEL",
        "MESSAGE_RETRY_SENTINEL",
        "DOCUMENT_SENTINEL",
        "DOCUMENT_RETRY_SENTINEL",
        "RUNTIME_CONTRIBUTION_INITIAL_SENTINEL",
        "RUNTIME_CONTRIBUTION_RETRY_SENTINEL",
    ):
        assert forbidden not in content_free_projection
        assert forbidden not in prompt_context_markdown
