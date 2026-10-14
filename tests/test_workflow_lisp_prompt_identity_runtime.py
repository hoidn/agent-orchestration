"""Runtime-only contracts for target-2.22 prompt-attempt identity."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path

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

    def structured_block(_value, **_kwargs):
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
        lambda _value, **_kwargs: "STRUCTURED",
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
        lambda _value, **_kwargs: "STRUCTURED",
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
