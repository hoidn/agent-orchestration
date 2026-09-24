"""Compiled target-2.28 union prompt-input carriage coverage."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow.pure_result_replay import PureResultReplayIndexError
from tests.workflow_bundle_helpers import bundle_context_dict


_HELPER_SOURCE = """\
(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.28\")
  (defmodule union_carriage/helper)
  (export Request Decision make-decision)
  (defrecord Nested (value Int))
  (defrecord Request (seed String))
  (defunion Decision
    (SCALAR (value Int))
    (RECORD (value Nested))
    (EMPTY))
  (defproc private-produce ((request Request)) -> Decision
    :effects ((uses-provider providers.produce))
    :lowering private-workflow
    (provider-result providers.produce
      :prompt prompts.produce
      :inputs (request)
      :returns Decision))
  (defworkflow make-decision ((request Request)) -> Decision
    (private-produce request)))
"""

_CONSUMER_SOURCE = """\
(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.28\")
  (defmodule union_carriage/consumer)
  (import union_carriage/helper :only (Request Decision make-decision))
  (export consume)
  (defworkflow consume ((request Request)) -> Bool
    (let* ((decision (call make-decision :request request)))
      (provider-result providers.consume
        :prompt prompts.consume
        :inputs (decision)
        :returns Bool))))
"""

_OLD_TARGET_CONSUMER_SOURCE = """\
(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.27\")
  (defmodule union_carriage/consumer)
  (import union_carriage/helper :only (Request Decision make-decision))
  (export consume)
  (defworkflow consume ((request Request)) -> Bool
    (let* ((decision (call make-decision :request request)))
      (match decision
        ((SCALAR scalar) true)
        ((RECORD record) true)
        ((EMPTY empty) true)))))
"""

_LIST_SOURCE = """\
(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.28\")
  (defmodule union_carriage/list_consumer)
  (export consume-list)
  (defunion Decision
    (PAYLOAD (payload String))
    (EMPTY))
  (defworkflow consume-list () -> Bool
    (let* ((decisions
             (provider-result providers.produce
               :prompt prompts.produce
               :inputs ()
               :returns List[Decision])))
      (provider-result providers.consume
        :prompt prompts.consume
        :inputs (decisions)
        :returns Bool))))
"""


def _compile_imported_private_consumer(
    workspace: Path,
    *,
    target: str = "2.28",
    consumer_source: str = _CONSUMER_SOURCE,
):
    helper = workspace / "union_carriage" / "helper.orc"
    consumer = workspace / "union_carriage" / "consumer.orc"
    helper.parent.mkdir(parents=True)
    helper.write_text(_HELPER_SOURCE.replace('"2.28"', f'"{target}"'), encoding="utf-8")
    consumer.write_text(consumer_source, encoding="utf-8")
    (helper.parent / "prompts").mkdir()
    (helper.parent / "prompts" / "produce.md").write_text("produce\n", encoding="utf-8")
    (helper.parent / "prompts" / "consume.md").write_text("consume\n", encoding="utf-8")
    result = compile_stage3_entrypoint(
        consumer,
        source_roots=(workspace,),
        entry_workflow="consume",
        provider_externs={
            "providers.produce": "test-produce",
            "providers.consume": "test-consume",
        },
        prompt_externs={
            "prompts.produce": "prompts/produce.md",
            "prompts.consume": "prompts/consume.md",
        },
        validate_shared=True,
        workspace_root=workspace,
    )
    return consumer, result.validated_bundles_by_name["union_carriage/consumer::consume"]


def _provider_step(bundle):
    return next(step for step in bundle.surface.steps if step.provider == "test-consume")


@pytest.mark.parametrize(
    ("bound_request", "expected"),
    (
        (
            {"request__seed": "scalar"},
            {"variant": "SCALAR", "value": 7},
        ),
        (
            {"request__seed": "record"},
            {"variant": "RECORD", "value": {"value": 8}},
        ),
        (
            {"request__seed": "empty"},
            {"variant": "EMPTY"},
        ),
    ),
)
def test_imported_private_union_return_reaches_provider_typed_input(
    tmp_path: Path,
    bound_request: dict[str, object],
    expected: dict[str, object],
) -> None:
    """A private imported return reaches the consumer as one typed union."""

    consumer, bundle = _compile_imported_private_consumer(tmp_path)
    provider = _provider_step(bundle)
    source = provider.typed_prompt_inputs[0]["value_source"]
    assert source["kind"] == "typed_union_projection"
    assert set(source["source"]["variants"]) == {"SCALAR", "RECORD", "EMPTY"}

    input_contracts = dict(workflow_runtime_input_contracts(bundle))
    bound_inputs = bind_workflow_inputs(
        {name: contract for name, contract in input_contracts.items() if not name.startswith("__write_root__")},
        bound_request,
        tmp_path,
    )
    state_manager = StateManager(workspace=tmp_path, run_id="imported-private-union")
    state_manager.initialize(consumer.as_posix(), context=bundle_context_dict(bundle), bound_inputs=bound_inputs)
    executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)
    captured: list[dict[str, object]] = []

    def prepare(_self, *args, **kwargs):
        captured.append({"prompt": kwargs.get("prompt_content", ""), "env": dict(kwargs.get("env") or {})})
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", ""), env=dict(kwargs.get("env") or {})), None

    def execute(_self, invocation, **_kwargs):
        output_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(expected if len(captured) == 1 else True), encoding="utf-8"
        )
        return SimpleNamespace(exit_code=0, stdout=b"", stderr=b"", duration_ms=1, error=None, missing_placeholders=None, invalid_prompt_placeholder=False, raw_stdout=None, normalized_stdout=None, provider_session=None)

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(ProviderExecutor, "execute", execute):
        state = executor.execute(on_error="stop")

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"__result__": True}
    assert len(captured) == 2
    assert json.dumps(expected, sort_keys=True, separators=(",", ":")) in str(captured[1]["prompt"])


def test_target_227_private_runtime_union_return_is_an_adjacent_limitation(
    tmp_path: Path,
) -> None:
    """Reproduce the old private-runtime union limitation without prompt admission."""

    consumer, bundle = _compile_imported_private_consumer(
        tmp_path,
        target="2.27",
        consumer_source=_OLD_TARGET_CONSUMER_SOURCE,
    )
    input_contracts = dict(workflow_runtime_input_contracts(bundle))
    bound_inputs = bind_workflow_inputs(
        {name: contract for name, contract in input_contracts.items() if not name.startswith("__write_root__")},
        {"request__seed": "old-target"},
        tmp_path,
    )
    state_manager = StateManager(workspace=tmp_path, run_id="old-target-private-union")
    state_manager.initialize(consumer.as_posix(), context=bundle_context_dict(bundle), bound_inputs=bound_inputs)
    executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)

    with pytest.raises(
        PureResultReplayIndexError,
        match="pure replay union binding must have a literal variant",
    ):
        executor.execute(on_error="stop")


@pytest.mark.parametrize(
    "decisions",
    (
        [{"variant": "PAYLOAD", "payload": "one"}],
        [{"variant": "EMPTY"}],
        [
            {"variant": "PAYLOAD", "payload": "one"},
            {"variant": "EMPTY"},
            {"variant": "PAYLOAD", "payload": "two"},
        ],
    ),
)
def test_list_of_union_typed_input_resolves_whole_mixed_values(
    tmp_path: Path,
    decisions: list[dict[str, object]],
) -> None:
    source_path = tmp_path / "union_carriage" / "list_consumer.orc"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(_LIST_SOURCE, encoding="utf-8")
    (source_path.parent / "prompts").mkdir()
    (source_path.parent / "prompts" / "produce.md").write_text("produce\n", encoding="utf-8")
    (source_path.parent / "prompts" / "consume.md").write_text("consume\n", encoding="utf-8")
    result = compile_stage3_entrypoint(
        source_path,
        source_roots=(tmp_path,),
        entry_workflow="consume-list",
        provider_externs={
            "providers.produce": "test-produce",
            "providers.consume": "test-consume",
        },
        prompt_externs={
            "prompts.produce": "prompts/produce.md",
            "prompts.consume": "prompts/consume.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles_by_name["union_carriage/list_consumer::consume-list"]
    source = _provider_step(bundle).typed_prompt_inputs[0]["value_source"]
    assert source["kind"] == "typed_binding_ref"

    state_manager = StateManager(workspace=tmp_path, run_id="list-union-resolution")
    state_manager.initialize(source_path.as_posix(), context=bundle_context_dict(bundle))
    executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)
    captured: list[dict[str, object]] = []

    def prepare(_self, *args, **kwargs):
        captured.append({"prompt": kwargs.get("prompt_content", ""), "env": dict(kwargs.get("env") or {})})
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", ""), env=dict(kwargs.get("env") or {})), None

    def execute(_self, invocation, **_kwargs):
        output_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(decisions if len(captured) == 1 else True), encoding="utf-8"
        )
        return SimpleNamespace(exit_code=0, stdout=b"", stderr=b"", duration_ms=1, error=None, missing_placeholders=None, invalid_prompt_placeholder=False, raw_stdout=None, normalized_stdout=None, provider_session=None)

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(ProviderExecutor, "execute", execute):
        state = executor.execute(on_error="stop")

    assert state["status"] == "completed"
    assert len(captured) == 2
    assert json.dumps(decisions, sort_keys=True, separators=(",", ":")) in str(captured[1]["prompt"])
