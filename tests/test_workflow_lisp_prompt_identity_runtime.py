"""Runtime-only contracts for target-2.22 prompt-attempt identity."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.workflow.prompting import PromptComposer


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _composer(tmp_path: Path) -> PromptComposer:
    return PromptComposer(workspace=tmp_path, asset_resolver=None)


def _consumed_step(*, position: str = "prepend") -> dict[str, object]:
    return {
        "name": "review",
        "consumes": [
            {
                "artifact": "report",
                "inject": {"mode": "content"},
            }
        ],
        "consumes_injection_position": position,
    }


@pytest.mark.parametrize("position", ("prepend", "append"))
def test_runtime_contribution_trace_captures_exact_consumed_delta_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    position: str,
) -> None:
    from orchestrator.workflow import prompting

    calls = 0
    original = prompting.render_consumed_artifacts_block

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(prompting, "render_consumed_artifacts_block", counted)
    composer = _composer(tmp_path)
    base = "BASE"
    composition = composer.apply_consumes_prompt_injection_with_trace(
        _consumed_step(position=position),
        base,
        resolved_consumes={"review": {"report": "VALUE"}},
        step_name="review",
        consume_identity="review",
        uses_qualified_identities=False,
    )
    rows = prompting.validate_runtime_contribution_composition(composition)

    assert calls == 1
    assert len(rows) == 1
    assert rows[0]["composition_ordinal"] == 0
    assert rows[0]["kind"] == "consumed_artifacts"
    assert rows[0]["position"] == position
    segment = composition.segments[0].segment
    assert rows[0]["bytes"] == len(segment)
    assert rows[0]["sha256"] == _sha256(segment)
    if position == "prepend":
        assert composition.prompt == segment.decode("utf-8") + base
    else:
        assert composition.prompt == base + segment.decode("utf-8")


@pytest.mark.parametrize(
    ("step", "resolved"),
    (
        ({}, {}),
        ({"inject_consumes": False, **_consumed_step()}, {
            "review": {"report": "VALUE"}
        }),
        (_consumed_step(), {}),
        (_consumed_step(), {"review": {}}),
        (_consumed_step(), {"review": {"report": None}}),
    ),
)
def test_runtime_contribution_trace_omits_empty_consumed_contributions(
    tmp_path: Path,
    step: dict[str, object],
    resolved: dict[str, object],
) -> None:
    from orchestrator.workflow import prompting

    composition = _composer(
        tmp_path
    ).apply_consumes_prompt_injection_with_trace(
        step,
        "BASE",
        resolved_consumes=resolved,
        step_name="review",
        consume_identity="review",
        uses_qualified_identities=False,
    )

    assert composition.prompt == "BASE"
    assert prompting.validate_runtime_contribution_composition(
        composition
    ) == ()


def test_runtime_contribution_trace_orders_output_before_structured_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow import prompting

    calls: list[str] = []

    def output_block(_value):
        calls.append("output_positions")
        return "OUTPUT"

    def structured_block(_value):
        calls.append("structured_result")
        return "STRUCTURED"

    monkeypatch.setattr(
        prompting,
        "render_output_contract_block",
        output_block,
    )
    monkeypatch.setattr(
        prompting,
        "render_output_bundle_contract_block",
        structured_block,
    )
    composer = _composer(tmp_path)
    initial = composer.apply_consumes_prompt_injection_with_trace(
        {},
        "BASE",
        resolved_consumes={},
        step_name="review",
        consume_identity="review",
        uses_qualified_identities=False,
    )
    composition = composer.apply_output_contract_prompt_suffix_with_trace(
        {
            "expected_outputs": [{"name": "report"}],
            "output_bundle": {"path": "result.json"},
        },
        initial,
    )
    rows = prompting.validate_runtime_contribution_composition(composition)

    assert calls == ["output_positions", "structured_result"]
    assert [row["kind"] for row in rows] == [
        "output_positions",
        "structured_result",
    ]
    assert [row["position"] for row in rows] == ["append", "append"]
    assert composition.prompt == "BASE\n\nOUTPUT\n\nSTRUCTURED"


@pytest.mark.parametrize(
    ("step", "expected_kind"),
    (
        (
            {"expected_outputs": [{"name": "report"}]},
            "output_positions",
        ),
        (
            {"output_bundle": {"path": "result.json"}},
            "structured_result",
        ),
    ),
)
def test_runtime_contribution_trace_captures_each_suffix_independently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    step: dict[str, object],
    expected_kind: str,
) -> None:
    from orchestrator.workflow import prompting

    monkeypatch.setattr(
        prompting,
        "render_output_contract_block",
        lambda _value: "OUTPUT",
    )
    monkeypatch.setattr(
        prompting,
        "render_output_bundle_contract_block",
        lambda _value: "STRUCTURED",
    )
    initial = prompting.RuntimeContributionComposition(
        base_prompt="BASE",
        prompt="BASE",
    )

    composition = _composer(
        tmp_path
    ).apply_output_contract_prompt_suffix_with_trace(step, initial)
    rows = prompting.validate_runtime_contribution_composition(composition)

    assert len(rows) == 1
    assert rows[0]["kind"] == expected_kind
    assert rows[0]["position"] == "append"


@pytest.mark.parametrize(
    "tamper",
    (
        "missing",
        "extra",
        "reordered",
        "duplicate",
        "position",
        "kind",
        "empty",
        "gap",
        "overlap",
    ),
)
def test_runtime_contribution_trace_rejects_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    from orchestrator.workflow import prompting

    monkeypatch.setattr(
        prompting,
        "render_output_contract_block",
        lambda _value: "OUTPUT",
    )
    monkeypatch.setattr(
        prompting,
        "render_output_bundle_contract_block",
        lambda _value: "STRUCTURED",
    )
    composer = _composer(tmp_path)
    initial = composer.apply_consumes_prompt_injection_with_trace(
        {},
        "BASE",
        resolved_consumes={},
        step_name="review",
        consume_identity="review",
        uses_qualified_identities=False,
    )
    valid = composer.apply_output_contract_prompt_suffix_with_trace(
        {
            "expected_outputs": [{"name": "report"}],
            "output_bundle": {"path": "result.json"},
        },
        initial,
    )
    rows = list(valid.segments)
    prompt = valid.prompt
    if tamper == "missing":
        rows = rows[:-1]
    elif tamper == "extra":
        rows.append(rows[-1])
    elif tamper == "reordered":
        rows.reverse()
    elif tamper == "duplicate":
        rows[1] = replace(rows[1], kind=rows[0].kind)
    elif tamper == "position":
        rows[0] = replace(rows[0], position="prepend")
    elif tamper == "kind":
        rows[0] = replace(rows[0], kind="unknown")
    elif tamper == "empty":
        rows[0] = replace(rows[0], segment=b"")
    elif tamper == "gap":
        prompt = prompt + "GAP"
    elif tamper == "overlap":
        rows[1] = replace(
            rows[1],
            segment=rows[0].segment + rows[1].segment,
        )
    corrupted = replace(valid, prompt=prompt, segments=tuple(rows))

    with pytest.raises(ValueError, match="runtime contribution"):
        prompting.validate_runtime_contribution_composition(corrupted)


def test_existing_string_only_composer_apis_remain_strings(
    tmp_path: Path,
) -> None:
    composer = _composer(tmp_path)

    consumed = composer.apply_consumes_prompt_injection(
        _consumed_step(),
        "BASE",
        resolved_consumes={"review": {"report": "VALUE"}},
        step_name="review",
        consume_identity="review",
        uses_qualified_identities=False,
    )
    completed = composer.apply_output_contract_prompt_suffix({}, consumed)

    assert type(consumed) is str
    assert type(completed) is str


def test_composite_v2_validator_runs_retained_v1_before_q3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests import test_prompt_identity as pure_vectors
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    _retained, record = pure_vectors._valid_v2()
    order: list[str] = []
    projected: dict[str, object] = {}

    def validate_v1(value):
        order.append("v1")
        projected.update(value)
        return value

    actual_q3 = evidence.validate_prompt_fragment_snapshot_v2_q3

    def validate_q3(value, **kwargs):
        order.append("q3")
        return actual_q3(value, **kwargs)

    monkeypatch.setattr(
        evidence,
        "validate_fragment_success_evidence",
        validate_v1,
    )
    monkeypatch.setattr(
        evidence,
        "validate_prompt_fragment_snapshot_v2_q3",
        validate_q3,
    )

    validated = evidence.validate_fragment_success_evidence_v2(
        record,
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    )

    assert order == ["v1", "q3"]
    assert projected["schema"] == evidence.FRAGMENT_SUCCESS_SCHEMA
    assert "prompt_attempt_identity" not in projected
    assert validated["schema"] == evidence.FRAGMENT_SUCCESS_SCHEMA_V2


def _actual_v2_schema_record_and_manager(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], object]:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path)
    monkeypatch.setattr(
        ProviderExecutor,
        "prepare_invocation",
        lambda _self, *_args, **kwargs: (
            _prepared_invocation(
                kwargs["prompt_content"],
                kwargs.get("env") or {},
            ),
            None,
        ),
    )
    monkeypatch.setattr(
        ProviderExecutor,
        "execute",
        lambda _self, invocation, **_kwargs: _successful_execution(
            tmp_path,
            invocation,
        ),
    )
    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")
    assert result["status"] == "completed"
    return _published_record(manager), manager


def _actual_v2_schema_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    record, _manager = _actual_v2_schema_record_and_manager(
        tmp_path,
        monkeypatch,
    )
    return record


def test_v2_canonicalization_accepts_trusted_actual_compiler_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        canonical_record_bytes,
    )

    record = _actual_v2_schema_record(tmp_path, monkeypatch)

    assert json.loads(
        canonical_record_bytes(
            record,
            compiler_fragment_identity_schema_version=(
                "compiled_prompt_fragment_identity.v2"
            ),
        )
    ) == record


def test_v2_canonicalization_rejects_missing_trusted_compiler_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        canonical_record_bytes,
    )

    with pytest.raises(
        ValueError,
        match="compiler_fragment_identity_schema_version",
    ):
        canonical_record_bytes(
            _actual_v2_schema_record(tmp_path, monkeypatch)
        )


def test_v2_canonicalization_rejects_resealed_payload_schema_claim_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests import test_prompt_identity as pure_vectors
    from orchestrator.workflow.prompt_dependency_evidence import (
        canonical_record_bytes,
    )

    resealed_v1_claim = _actual_v2_schema_record(tmp_path, monkeypatch)
    fragment_role = resealed_v1_claim["prompt_attempt_identity"]["roles"][
        "fragment_program"
    ]
    fragment_role["payload"]["identity_schema_version"] = (
        "compiled_prompt_fragment_identity.v1"
    )
    pure_vectors._reseal_role(fragment_role)
    pure_vectors._reseal_v2_identity(resealed_v1_claim)

    with pytest.raises(
        ValueError,
        match="prompt_attempt_identity_role_invalid",
    ):
        canonical_record_bytes(
            resealed_v1_claim,
            compiler_fragment_identity_schema_version=(
                "compiled_prompt_fragment_identity.v2"
            ),
        )


def test_v2_terminal_validation_derives_persisted_scope_schema_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_terminal_evidence,
    )

    _record, manager = _actual_v2_schema_record_and_manager(
        tmp_path,
        monkeypatch,
    )
    result = validate_terminal_evidence(manager.run_root, manager.state_file)
    assert result.index["publications"][0]["record_kind"] == (
        "prompt_snapshot"
    )


def test_v2_terminal_validation_rejects_missing_scope_schema_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_terminal_evidence,
    )

    _record, manager = _actual_v2_schema_record_and_manager(
        tmp_path,
        monkeypatch,
    )
    state = manager._read_state_from_disk()
    allocation = next(iter(state.provider_attempt_allocations.values()))
    allocation.pop("prompt_fragment_identity_schema_version")
    manager.state_file.write_text(
        json.dumps(state.to_dict(), indent=2),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="compiler_fragment_identity_schema_version",
    ):
        validate_terminal_evidence(manager.run_root, manager.state_file)


def test_v2_terminal_validation_rejects_conflicting_scope_schema_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_terminal_evidence,
    )

    _record, manager = _actual_v2_schema_record_and_manager(
        tmp_path,
        monkeypatch,
    )
    state = manager._read_state_from_disk()
    allocation = next(iter(state.provider_attempt_allocations.values()))
    allocation["prompt_fragment_identity_schema_version"] = (
        "compiled_prompt_fragment_identity.v1"
    )
    manager.state_file.write_text(
        json.dumps(state.to_dict(), indent=2),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="prompt_attempt_identity_role_invalid",
    ):
        validate_terminal_evidence(manager.run_root, manager.state_file)


def _runtime_q3_fixture(
    tmp_path: Path,
    *,
    target_dsl: str = "2.22",
    with_output_position: bool | None = None,
):
    from tests.test_workflow_lisp_prompt_calculus_runtime import (
        _compile_runtime_fragment,
        _runtime_fragment_manager,
    )

    source_path, bundle = _compile_runtime_fragment(
        tmp_path,
        lowering_route="wcc_m4" if target_dsl == "2.22" else "legacy",
        target_dsl=target_dsl,
        with_output_position=(
            target_dsl == "2.22"
            if with_output_position is None
            else with_output_position
        ),
    )
    manager = _runtime_fragment_manager(
        tmp_path,
        source_path,
        bundle,
        run_id=f"prompt-identity-runtime-{target_dsl.replace('.', '')}",
    )
    return bundle, manager


@pytest.mark.parametrize(
    ("with_output_position", "expected_schema_version"),
    (
        (False, "compiled_prompt_fragment_identity.v1"),
        (True, "compiled_prompt_fragment_identity.v2"),
    ),
)
def test_target_222_allocation_persists_compiler_fragment_schema_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    with_output_position: bool,
    expected_schema_version: str,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(
        tmp_path,
        with_output_position=with_output_position,
    )
    monkeypatch.setattr(
        ProviderExecutor,
        "prepare_invocation",
        lambda _self, *_args, **kwargs: (
            _prepared_invocation(
                kwargs["prompt_content"],
                kwargs.get("env") or {},
            ),
            None,
        ),
    )
    monkeypatch.setattr(
        ProviderExecutor,
        "execute",
        lambda _self, invocation, **_kwargs: _successful_execution(
            tmp_path,
            invocation,
        ),
    )

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert result["status"] == "completed"
    state = manager._read_state_from_disk()
    allocation = next(iter(state.provider_attempt_allocations.values()))
    record = _published_record(manager)
    assert allocation["prompt_fragment_identity_schema_version"] == (
        expected_schema_version
    )
    assert record["prompt_attempt_identity"]["roles"]["fragment_program"][
        "payload"
    ]["identity_schema_version"] == expected_schema_version


def test_target_222_preparation_failure_retains_allocation_schema_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path)
    monkeypatch.setattr(
        ProviderExecutor,
        "prepare_invocation",
        lambda *_args, **_kwargs: (
            None,
            {"type": "substitution_error", "message": "unresolved"},
        ),
    )

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert result["status"] == "failed"
    state = manager._read_state_from_disk()
    allocation = next(iter(state.provider_attempt_allocations.values()))
    record = _published_record(manager)
    assert allocation["prompt_fragment_identity_schema_version"] == (
        "compiled_prompt_fragment_identity.v2"
    )
    assert record["fragment"]["identity_schema_version"] == allocation[
        "prompt_fragment_identity_schema_version"
    ]


def test_legacy_fragment_execution_does_not_add_schema_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path, target_dsl="2.21")
    monkeypatch.setattr(
        ProviderExecutor,
        "prepare_invocation",
        lambda _self, *_args, **kwargs: (
            _prepared_invocation(
                kwargs["prompt_content"],
                kwargs.get("env") or {},
            ),
            None,
        ),
    )
    monkeypatch.setattr(
        ProviderExecutor,
        "execute",
        lambda _self, invocation, **_kwargs: _successful_execution(
            tmp_path,
            invocation,
        ),
    )

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert result["status"] == "completed"
    state = manager._read_state_from_disk()
    allocation = next(iter(state.provider_attempt_allocations.values()))
    assert "prompt_fragment_identity_schema_version" not in allocation


def _prepared_invocation(prompt: str, env: dict[str, str]):
    from orchestrator.providers.types import (
        InputMode,
        PreparedProviderPolicy,
        ProviderInvocation,
    )

    return ProviderInvocation(
        command=["tool"],
        input_mode=InputMode.STDIN,
        prompt=prompt,
        env=env,
        prepared_prompt=prompt,
        prepared_provider_policy=PreparedProviderPolicy(
            provider_name="capturing-provider",
            model=None,
            effort=None,
            timeout_sec=None,
            input_mode="stdin",
        ),
    )


def _successful_execution(tmp_path: Path, invocation):
    output = (
        tmp_path
        / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("true\n", encoding="utf-8")
    report = tmp_path / "artifacts" / "work" / "review.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("reviewed\n", encoding="utf-8")
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


def _allocation_evidence_paths(manager, allocation) -> list[Path]:
    from orchestrator.workflow.prompt_dependency_evidence import (
        evidence_relative_path,
    )
    from orchestrator.workflow.provider_attempts import ProviderAttemptScope

    scope = ProviderAttemptScope.from_dict(allocation["scope"])
    return [
        manager.run_root / evidence_relative_path(scope, ordinal)
        for ordinal in range(
            1,
            allocation["last_allocated_ordinal"] + 1,
        )
    ]


def _published_record(manager) -> dict[str, object]:
    state = manager._read_state_from_disk()
    allocation = next(iter(state.provider_attempt_allocations.values()))
    evidence_path = next(
        path
        for path in _allocation_evidence_paths(manager, allocation)
        if path.is_file()
    )
    return json.loads(
        evidence_path.read_text(encoding="utf-8")
    )


def test_target_222_publishes_valid_v2_after_prepare_before_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.workflow import prompt_dependency_evidence as evidence
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path)
    order: list[str] = []

    def prepare(_self, *_args, **kwargs):
        order.append("prepare")
        return _prepared_invocation(
            kwargs["prompt_content"],
            kwargs.get("env") or {},
        ), None

    actual_publish = evidence.publish_evidence_file

    def publish(*args, **kwargs):
        order.append("publish")
        assert kwargs[
            "compiler_fragment_identity_schema_version"
        ] == "compiled_prompt_fragment_identity.v2"
        return actual_publish(*args, **kwargs)

    def execute(_self, invocation, **_kwargs):
        order.append("launch")
        return _successful_execution(tmp_path, invocation)

    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare)
    monkeypatch.setattr(evidence, "publish_evidence_file", publish)
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
    ).execute(on_error="stop")

    assert result["status"] == "completed"
    assert order == ["prepare", "publish", "launch"]
    record = _published_record(manager)
    assert record["schema"] == evidence.FRAGMENT_SUCCESS_SCHEMA_V2
    assert evidence.validate_fragment_success_evidence_v2(
        record,
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v2"
        ),
    ) == record


def test_target_222_allocates_before_output_position_and_all_typed_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.state import StateManager
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path)
    order: list[str] = []
    actual_allocate = StateManager.allocate_provider_attempt
    actual_output_position = (
        WorkflowExecutor._prompt_output_position_prelaunch_result
    )
    actual_resolve_typed = (
        WorkflowExecutor._resolve_typed_prompt_input_value
    )

    def allocate(self, scope, **kwargs):
        order.append("allocate")
        return actual_allocate(self, scope, **kwargs)

    def output_position(self, **kwargs):
        order.append("output_position")
        return actual_output_position(self, **kwargs)

    def resolve_typed(self, value, state, **kwargs):
        order.append("typed")
        return actual_resolve_typed(self, value, state, **kwargs)

    def prepare(_self, *_args, **kwargs):
        order.append("prepare")
        return _prepared_invocation(
            kwargs["prompt_content"],
            kwargs.get("env") or {},
        ), None

    def execute(_self, invocation, **_kwargs):
        order.append("launch")
        return _successful_execution(tmp_path, invocation)

    monkeypatch.setattr(
        StateManager,
        "allocate_provider_attempt",
        allocate,
    )
    monkeypatch.setattr(
        WorkflowExecutor,
        "_prompt_output_position_prelaunch_result",
        output_position,
    )
    monkeypatch.setattr(
        WorkflowExecutor,
        "_resolve_typed_prompt_input_value",
        resolve_typed,
    )
    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare)
    monkeypatch.setattr(ProviderExecutor, "execute", execute)

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert result["status"] == "completed"
    assert order[0:2] == ["allocate", "output_position"]
    assert "typed" in order[2:]
    assert max(
        index
        for index, event in enumerate(order)
        if event in {"output_position", "typed"}
    ) < order.index("prepare")
    assert order[-2:] == ["prepare", "launch"]


def test_target_222_output_position_failure_leaves_allocated_attempt_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path)
    preparations = 0
    launches = 0

    def fail_output_position(self, **_kwargs):
        return self._contract_violation_result(
            "Provider prompt output-position preparation failed",
            {"reason": "forced_output_position_failure"},
        )

    def prepare(*_args, **_kwargs):
        nonlocal preparations
        preparations += 1
        raise AssertionError(
            "output-position failure must not prepare"
        )

    def execute(*_args, **_kwargs):
        nonlocal launches
        launches += 1
        raise AssertionError("output-position failure must not launch")

    monkeypatch.setattr(
        WorkflowExecutor,
        "_prompt_output_position_prelaunch_result",
        fail_output_position,
    )
    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare)
    monkeypatch.setattr(ProviderExecutor, "execute", execute)

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert result["status"] == "failed"
    assert preparations == 0
    assert launches == 0
    state = manager._read_state_from_disk()
    allocations = list(state.provider_attempt_allocations.values())
    assert len(allocations) == 1
    allocation = allocations[0]
    assert allocation["last_allocated_ordinal"] == 1
    assert "events" not in allocation
    assert not list(
        (manager.run_root / "workflow_lisp" / "prompt_dependencies").rglob(
            "attempt-*.json"
        )
    )


def test_target_222_retry_repeats_all_attempt_scoped_resolution_after_allocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.state import StateManager
    from orchestrator.workflow import executor as workflow_executor
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path)
    events: list[str] = []
    actual_allocate = StateManager.allocate_provider_attempt
    actual_output_position = (
        WorkflowExecutor._prompt_output_position_prelaunch_result
    )
    actual_resolve_typed = (
        WorkflowExecutor._resolve_typed_prompt_input_value
    )
    actual_render = workflow_executor.render_prompt_fragment_base
    launches = 0

    def allocate(self, scope, **kwargs):
        events.append("allocate")
        return actual_allocate(self, scope, **kwargs)

    def output_position(self, **kwargs):
        events.append("output_position")
        return actual_output_position(self, **kwargs)

    def resolve_typed(self, value, state, **kwargs):
        events.append("typed")
        return actual_resolve_typed(self, value, state, **kwargs)

    def render(*args, **kwargs):
        events.append("render")
        return actual_render(*args, **kwargs)

    def prepare(_self, *_args, **kwargs):
        events.append("prepare")
        return _prepared_invocation(
            kwargs["prompt_content"],
            kwargs.get("env") or {},
        ), None

    def execute(_self, invocation, **_kwargs):
        nonlocal launches
        events.append("launch")
        launches += 1
        execution = _successful_execution(tmp_path, invocation)
        if launches == 1:
            execution.exit_code = 1
        return execution

    monkeypatch.setattr(
        StateManager,
        "allocate_provider_attempt",
        allocate,
    )
    monkeypatch.setattr(
        WorkflowExecutor,
        "_prompt_output_position_prelaunch_result",
        output_position,
    )
    monkeypatch.setattr(
        WorkflowExecutor,
        "_resolve_typed_prompt_input_value",
        resolve_typed,
    )
    monkeypatch.setattr(
        "orchestrator.workflow.executor.render_prompt_fragment_base",
        render,
    )
    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare)
    monkeypatch.setattr(ProviderExecutor, "execute", execute)

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        max_retries=1,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert result["status"] == "completed"
    allocation_indices = [
        index
        for index, event in enumerate(events)
        if event == "allocate"
    ]
    assert len(allocation_indices) == 2
    groups = [
        events[start:end]
        for start, end in zip(
            allocation_indices,
            allocation_indices[1:] + [len(events)],
        )
    ]
    assert [group.count("typed") for group in groups] == [
        groups[0].count("typed"),
        groups[0].count("typed"),
    ]
    assert groups[0].count("typed") > 0
    for group in groups:
        assert group[0:2] == ["allocate", "output_position"]
        assert group.count("output_position") == 1
        assert group.count("render") == 1
        assert group.count("prepare") == 1
        assert group.count("launch") == 1
        assert (
            group.index("output_position")
            < group.index("typed")
            < group.index("render")
            < group.index("prepare")
            < group.index("launch")
        )


def test_old_target_keeps_typed_resolution_before_attempt_allocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.state import StateManager
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path, target_dsl="2.20")
    order: list[str] = []
    actual_allocate = StateManager.allocate_provider_attempt
    actual_resolve_typed = (
        WorkflowExecutor._resolve_typed_prompt_input_value
    )

    def allocate(self, scope):
        order.append("allocate")
        return actual_allocate(self, scope)

    def resolve_typed(self, value, state, **kwargs):
        order.append("typed")
        return actual_resolve_typed(self, value, state, **kwargs)

    monkeypatch.setattr(
        StateManager,
        "allocate_provider_attempt",
        allocate,
    )
    monkeypatch.setattr(
        WorkflowExecutor,
        "_resolve_typed_prompt_input_value",
        resolve_typed,
    )
    monkeypatch.setattr(
        ProviderExecutor,
        "prepare_invocation",
        lambda _self, *_args, **kwargs: (
            _prepared_invocation(
                kwargs["prompt_content"],
                kwargs.get("env") or {},
            ),
            None,
        ),
    )
    monkeypatch.setattr(
        ProviderExecutor,
        "execute",
        lambda _self, invocation, **_kwargs: _successful_execution(
            tmp_path,
            invocation,
        ),
    )

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert result["status"] == "completed"
    assert order[0] == "typed"
    assert order.index("typed") < order.index("allocate")


def test_target_222_render_failure_allocates_once_and_never_prepares_or_launches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path)
    preparations = 0
    launches = 0

    def fail_render(*_args, **_kwargs):
        raise ValueError("forced fragment render failure")

    def prepare(*_args, **_kwargs):
        nonlocal preparations
        preparations += 1
        raise AssertionError("render failure must not prepare")

    def execute(*_args, **_kwargs):
        nonlocal launches
        launches += 1
        raise AssertionError("render failure must not launch")

    monkeypatch.setattr(
        "orchestrator.workflow.executor.render_prompt_fragment_base",
        fail_render,
    )
    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare)
    monkeypatch.setattr(ProviderExecutor, "execute", execute)

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert result["status"] == "failed"
    assert preparations == 0
    assert launches == 0
    state = manager._read_state_from_disk()
    allocations = list(state.provider_attempt_allocations.values())
    assert len(allocations) == 1
    assert allocations[0]["last_allocated_ordinal"] == 1
    assert "events" not in allocations[0]
    assert not list(
        (manager.run_root / "workflow_lisp" / "prompt_dependencies").rglob(
            "attempt-*.json"
        )
    )


def test_target_222_retry_derives_fragment_and_trace_once_per_allocated_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.workflow import executor as workflow_executor
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path)
    actual_render = workflow_executor.render_prompt_fragment_base
    render_results: list[object] = []
    prepared_prompts: list[str] = []
    launches = 0

    def render(*args, **kwargs):
        result = actual_render(*args, **kwargs)
        render_results.append(result)
        return result

    def prepare(_self, *_args, **kwargs):
        prepared_prompts.append(kwargs["prompt_content"])
        return _prepared_invocation(
            kwargs["prompt_content"],
            kwargs.get("env") or {},
        ), None

    def execute(_self, invocation, **_kwargs):
        nonlocal launches
        launches += 1
        if launches == 1:
            failed = _successful_execution(tmp_path, invocation)
            failed.exit_code = 1
            return failed
        return _successful_execution(tmp_path, invocation)

    monkeypatch.setattr(
        "orchestrator.workflow.executor.render_prompt_fragment_base",
        render,
    )
    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare)
    monkeypatch.setattr(ProviderExecutor, "execute", execute)

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        max_retries=1,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert result["status"] == "completed"
    assert len(render_results) == 2
    assert render_results[0] is not render_results[1]
    assert len(prepared_prompts) == 2
    assert launches == 2
    state = manager._read_state_from_disk()
    allocation = next(iter(state.provider_attempt_allocations.values()))
    assert allocation["last_allocated_ordinal"] == 2
    assert "events" not in allocation
    records = [
        json.loads(
            path.read_text(encoding="utf-8")
        )
        for path in _allocation_evidence_paths(manager, allocation)
    ]
    assert [record["attempt"]["ordinal"] for record in records] == [1, 2]


def test_target_222_preparation_failure_publishes_exact_failure_and_never_launches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.workflow import prompt_dependency_evidence as evidence
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path)
    launches = 0

    def execute(*_args, **_kwargs):
        nonlocal launches
        launches += 1
        raise AssertionError("preparation failure must not launch")

    monkeypatch.setattr(
        ProviderExecutor,
        "prepare_invocation",
        lambda *_args, **_kwargs: (
            None,
            {"type": "substitution_error", "message": "unresolved"},
        ),
    )
    monkeypatch.setattr(ProviderExecutor, "execute", execute)

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert result["status"] == "failed"
    assert launches == 0
    record = _published_record(manager)
    assert record["schema"] == (
        evidence.PROMPT_FRAGMENT_PREPARATION_FAILURE_SCHEMA
    )
    assert record["provider_calls"] == {
        "preparation": True,
        "execution": False,
    }
    terminal = evidence.validate_terminal_evidence(
        manager.run_root,
        manager.state_file,
    )
    assert terminal.index["publications"][0]["record_kind"] == "failure"


def test_target_222_publication_failure_leaves_allocation_only_and_never_launches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path)
    launches = 0
    order: list[str] = []

    def prepare(_self, *_args, **kwargs):
        order.append("prepare")
        return _prepared_invocation(
            kwargs["prompt_content"],
            kwargs.get("env") or {},
        ), None

    def execute(*_args, **_kwargs):
        nonlocal launches
        launches += 1
        raise AssertionError("publication failure must not launch")

    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare)
    monkeypatch.setattr(ProviderExecutor, "execute", execute)
    monkeypatch.setattr(
        "orchestrator.workflow.executor.publish_evidence_file",
        lambda *_args, **_kwargs: (
            order.append("publish"),
            (_ for _ in ()).throw(OSError("publication failed")),
        )[1],
    )

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert result["status"] == "failed"
    assert launches == 0
    assert order == ["prepare", "publish"]
    state = manager._read_state_from_disk()
    allocation = next(
        iter(state.provider_attempt_allocations.values())
    )
    assert allocation["last_allocated_ordinal"] == 1
    assert "events" not in allocation
    assert not any(
        path.exists()
        for path in _allocation_evidence_paths(manager, allocation)
    )


@pytest.mark.parametrize("tamper", ("prompt", "policy"))
def test_target_222_prepared_invocation_tamper_fails_before_publication_or_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path)
    launches = 0

    def prepare(_self, *_args, **kwargs):
        invocation = _prepared_invocation(
            kwargs["prompt_content"],
            kwargs.get("env") or {},
        )
        if tamper == "prompt":
            invocation.prepared_prompt = "different"
        else:
            invocation.prepared_provider_policy = None
        return invocation, None

    def execute(*_args, **_kwargs):
        nonlocal launches
        launches += 1
        raise AssertionError("invalid preparation must not launch")

    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare)
    monkeypatch.setattr(ProviderExecutor, "execute", execute)

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert result["status"] == "failed"
    assert launches == 0
    state = manager._read_state_from_disk()
    allocation = next(
        iter(state.provider_attempt_allocations.values())
    )
    assert allocation["last_allocated_ordinal"] == 1
    assert "events" not in allocation
    assert not any(
        path.exists()
        for path in _allocation_evidence_paths(manager, allocation)
    )


def test_old_target_fragment_keeps_v1_prelaunch_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.workflow import prompt_dependency_evidence as evidence
    from orchestrator.workflow.executor import WorkflowExecutor

    bundle, manager = _runtime_q3_fixture(tmp_path, target_dsl="2.20")

    def prepare(_self, *_args, **kwargs):
        return _prepared_invocation(
            kwargs["prompt_content"],
            kwargs.get("env") or {},
        ), None

    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare)
    monkeypatch.setattr(
        ProviderExecutor,
        "execute",
        lambda _self, invocation, **_kwargs: _successful_execution(
            tmp_path, invocation
        ),
    )

    result = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert result["status"] == "completed"
    assert _published_record(manager)["schema"] == (
        evidence.FRAGMENT_SUCCESS_SCHEMA
    )
