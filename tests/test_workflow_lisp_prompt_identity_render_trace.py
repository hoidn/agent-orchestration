"""Target-2.22 one-render prompt-fragment trace contract."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from types import MappingProxyType

import pytest

from orchestrator.workflow.prompt_fragment_contract import (
    COMPILER_PROMPT_ATTEMPT_BINDING_PLAN_SCHEMA,
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
    CompilerPromptAttemptBindingPlan,
    CompilerPromptAttemptBindingPlanRow,
    CompilerPromptFragmentContract,
    CompilerPromptFragmentRenderedSlot,
)


_IDENTITY = "sha256:" + "1" * 64


def _digest(payload: bytes) -> str:
    return f"sha256:{sha256(payload).hexdigest()}"


def _slot(
    name: str,
    kind: str,
    renderer_id: str,
    placeholder_ordinals: tuple[int, ...],
) -> CompilerPromptFragmentRenderedSlot:
    static_type: dict[str, object]
    if kind == "path":
        static_type = {
            "kind": "path",
            "name": "ReportPath",
            "under": "artifacts/reports",
            "must_exist_target": False,
        }
    else:
        static_type = {
            "kind": "primitive",
            "name": "String" if kind == "text" else "Value",
        }
    return CompilerPromptFragmentRenderedSlot(
        name=name,
        kind=kind,
        static_type=static_type,
        renderer_id=renderer_id,
        value_source={
            "kind": "typed_binding_ref",
            "binding": {"ref": f"inputs.{name}"},
        },
        placeholder_ordinals=placeholder_ordinals,
    )


def _contract() -> CompilerPromptFragmentContract:
    return CompilerPromptFragmentContract(
        schema_version=COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
        template_utf8=(
            "{message}|{payload}|{report_path}|{payload}|{message}"
        ),
        rendered_slots=(
            _slot(
                "message",
                "text",
                "raw-utf8-string",
                (0, 4),
            ),
            _slot(
                "payload",
                "value",
                "canonical-json",
                (1, 3),
            ),
            _slot(
                "report_path",
                "path",
                "posix-path-line",
                (2,),
            ),
        ),
        compiled_prompt_fragment_identity=_IDENTITY,
    )


def _plan() -> CompilerPromptAttemptBindingPlan:
    rows = (
        CompilerPromptAttemptBindingPlanRow(
            declaration_ordinal=0,
            slot_name="design_doc",
            slot_kind="doc",
            refinement=None,
            output_role="none",
            delivery="dependency",
            runtime_source={
                "kind": "required_dependency",
                "ordinal": 0,
            },
            renderer=None,
        ),
        CompilerPromptAttemptBindingPlanRow(
            declaration_ordinal=1,
            slot_name="message",
            slot_kind="text",
            refinement=None,
            output_role="none",
            delivery="template",
            runtime_source={"kind": "rendered_slot", "ordinal": 0},
            renderer={
                "renderer_id": "raw-utf8-string",
                "renderer_version": 1,
            },
        ),
        CompilerPromptAttemptBindingPlanRow(
            declaration_ordinal=2,
            slot_name="payload",
            slot_kind="value",
            refinement=None,
            output_role="none",
            delivery="template",
            runtime_source={"kind": "rendered_slot", "ordinal": 1},
            renderer={
                "renderer_id": "canonical-json",
                "renderer_version": 1,
            },
        ),
        CompilerPromptAttemptBindingPlanRow(
            declaration_ordinal=3,
            slot_name="reference_doc",
            slot_kind="doc",
            refinement=None,
            output_role="none",
            delivery="dependency",
            runtime_source={
                "kind": "required_dependency",
                "ordinal": 1,
            },
            renderer=None,
        ),
        CompilerPromptAttemptBindingPlanRow(
            declaration_ordinal=4,
            slot_name="report_path",
            slot_kind="path",
            refinement=None,
            output_role="none",
            delivery="template",
            runtime_source={"kind": "rendered_slot", "ordinal": 2},
            renderer={
                "renderer_id": "posix-path-line",
                "renderer_version": 1,
            },
        ),
    )
    return CompilerPromptAttemptBindingPlan(
        schema_version=COMPILER_PROMPT_ATTEMPT_BINDING_PLAN_SCHEMA,
        rows=rows,
        plan_sha256=None,
    ).with_canonical_sha256()


def _resolved_values() -> dict[str, object]:
    return {
        "message": "Inspect 雪\n\n",
        "payload": {"score": 2, "ready": True},
        "report_path": "artifacts/reports/review.md",
    }


def _typed_entries() -> list[dict[str, object]]:
    return [
        {
            "schema_version": "workflow_lisp_typed_prompt_input.v1",
            "binding_name": "payload",
            "renderer": {
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "accepted_shape": "any_pure_value",
            },
            "value_source": {
                "kind": "typed_binding_ref",
                "ref": "inputs.payload",
            },
            "value_type_name": "Value",
            "source_map_origin_key": "render-trace::payload",
            "injection_order": 0,
        },
        {
            "schema_version": "workflow_lisp_typed_prompt_input.v1",
            "binding_name": "report_path",
            "renderer": {
                "renderer_id": "posix-path-line",
                "renderer_version": 1,
                "accepted_shape": "path_value",
            },
            "value_source": {
                "kind": "typed_binding_ref",
                "ref": "inputs.report_path",
            },
            "value_type_name": "ReportPath",
            "source_map_origin_key": "render-trace::report-path",
            "injection_order": 1,
        },
    ]


def _render_target_2_22():
    from orchestrator.workflow import prompting

    return prompting.render_prompt_fragment_base(
        _contract(),
        resolved_slot_values=_resolved_values(),
        target_dsl_version="2.22",
        compiler_prompt_attempt_binding_plan=_plan(),
    )


def test_target_2_22_fragment_trace_renders_each_value_and_path_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow import prompting

    actual_render_view = prompting.render_view
    calls: list[tuple[str, int, object]] = []

    def counted_render_view(
        renderer_id: str,
        renderer_version: int,
        value: object,
    ) -> bytes:
        calls.append((renderer_id, renderer_version, value))
        return actual_render_view(renderer_id, renderer_version, value)

    monkeypatch.setattr(prompting, "render_view", counted_render_view)
    result = _render_target_2_22()

    assert isinstance(result, prompting.PromptFragmentRenderResult)
    assert result.rendered_base == (
        'Inspect 雪\n\n|{"ready":true,"score":2}|'
        'artifacts/reports/review.md|{"ready":true,"score":2}|'
        "Inspect 雪\n\n"
    )
    assert tuple(row.slot_name for row in result.trace) == (
        "message",
        "payload",
        "report_path",
    )
    assert tuple(row.rendered_slot_ordinal for row in result.trace) == (
        0,
        1,
        2,
    )
    assert calls == [
        ("canonical-json", 1, {"score": 2, "ready": True}),
        ("posix-path-line", 1, "artifacts/reports/review.md"),
    ]
    with pytest.raises(FrozenInstanceError):
        result.trace[0].slot_name = "changed"
    with pytest.raises(TypeError):
        result.trace[0].renderer["renderer_id"] = "changed"


def test_target_2_22_fragment_trace_records_exact_raw_and_substitution_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow import prompting

    custom_rendered = {
        "canonical-json": b'{"custom":true}',
        "posix-path-line": b"artifacts/reports/custom.md\n\n\n",
    }

    def render_once(
        renderer_id: str,
        renderer_version: int,
        value: object,
    ) -> bytes:
        assert renderer_version == 1
        return custom_rendered[renderer_id]

    monkeypatch.setattr(prompting, "render_view", render_once)
    result = _render_target_2_22()
    text, value, path = result.trace

    text_bytes = "Inspect 雪\n\n".encode("utf-8", errors="strict")
    assert dict(text.renderer) == {
        "renderer_id": "raw-utf8-string",
        "renderer_version": 1,
    }
    assert text.value_sha256 == _digest(text_bytes)
    assert text.raw_renderer_bytes_sha256 == _digest(text_bytes)
    assert text.substitution_bytes == len(text_bytes)
    assert text.substitution_bytes_sha256 == _digest(text_bytes)

    canonical_value_bytes = b'{"ready":true,"score":2}'
    assert value.value_sha256 == _digest(canonical_value_bytes)
    assert value.raw_renderer_bytes_sha256 == _digest(
        custom_rendered["canonical-json"]
    )
    assert value.substitution_bytes == len(
        custom_rendered["canonical-json"]
    )
    assert value.substitution_bytes_sha256 == _digest(
        custom_rendered["canonical-json"]
    )

    raw_path = custom_rendered["posix-path-line"]
    substituted_path = b"artifacts/reports/custom.md\n\n"
    assert path.value_sha256 == _digest(
        b"artifacts/reports/review.md"
    )
    assert path.raw_renderer_bytes_sha256 == _digest(raw_path)
    assert path.substitution_bytes == len(substituted_path)
    assert path.substitution_bytes_sha256 == _digest(substituted_path)
    assert result.rendered_base == (
        "Inspect 雪\n\n|"
        '{"custom":true}|artifacts/reports/custom.md\n\n|'
        '{"custom":true}|'
        "Inspect 雪\n\n"
    )


def test_target_2_22_fragment_trace_rejects_non_utf8_raw_text_before_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow import prompting

    monkeypatch.setattr(
        prompting,
        "render_view",
        lambda *_args: pytest.fail(
            "typed renderer must not run after invalid raw text"
        ),
    )
    values = _resolved_values()
    values["message"] = "\ud800"

    with pytest.raises(ValueError, match="valid UTF-8"):
        prompting.render_prompt_fragment_base(
            _contract(),
            resolved_slot_values=values,
            target_dsl_version="2.22",
            compiler_prompt_attempt_binding_plan=_plan(),
        )


def test_target_2_22_fragment_typed_evidence_reuses_trace_without_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow import prompting
    from orchestrator.workflow_lisp import typed_prompt_inputs

    actual_render_view = prompting.render_view
    calls: list[str] = []

    def changes_on_second_call(
        renderer_id: str,
        renderer_version: int,
        value: object,
    ) -> bytes:
        calls.append(renderer_id)
        if calls.count(renderer_id) > 1:
            return b"changed-on-second-call\n"
        return actual_render_view(renderer_id, renderer_version, value)

    monkeypatch.setattr(prompting, "render_view", changes_on_second_call)
    monkeypatch.setattr(
        typed_prompt_inputs,
        "render_view",
        lambda *_args: pytest.fail(
            "fragment-owned typed evidence must reuse the trace"
        ),
    )
    result = _render_target_2_22()
    rendered_block, evidence = typed_prompt_inputs.render_typed_prompt_inputs(
        _typed_entries(),
        resolved_typed_values={
            "payload": _resolved_values()["payload"],
            "report_path": _resolved_values()["report_path"],
        },
        workflow_name="render-trace::run",
        step_id="root.render-trace",
        fragment_render_result=result,
        compiler_prompt_attempt_binding_plan=_plan(),
    )

    assert rendered_block == ""
    assert calls == ["canonical-json", "posix-path-line"]
    assert [row["binding_name"] for row in evidence] == [
        "payload",
        "report_path",
    ]
    assert evidence[0]["value_digest"] == result.trace[1].value_sha256
    assert (
        evidence[0]["rendered_bytes_digest"]
        == result.trace[1].raw_renderer_bytes_sha256
    )
    assert evidence[1]["value_digest"] == result.trace[2].value_sha256
    assert (
        evidence[1]["rendered_bytes_digest"]
        == result.trace[2].raw_renderer_bytes_sha256
    )
    assert all(row["binding_name"] != "message" for row in evidence)


@pytest.mark.parametrize(
    "mutation",
    (
        "missing",
        "extra",
        "duplicate",
        "reordered",
        "wrong_name",
        "wrong_renderer",
        "wrong_version",
        "wrong_value_digest",
        "wrong_raw_digest",
        "wrong_substitution_length",
        "wrong_substitution_digest",
    ),
)
def test_target_2_22_fragment_trace_tampering_fails_before_evidence(
    mutation: str,
) -> None:
    from orchestrator.workflow_lisp import typed_prompt_inputs

    result = _render_target_2_22()
    rows = list(result.trace)
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append(rows[-1])
    elif mutation == "duplicate":
        rows[1] = rows[0]
    elif mutation == "reordered":
        rows[1], rows[2] = rows[2], rows[1]
    elif mutation == "wrong_name":
        object.__setattr__(rows[1], "slot_name", "wrong")
    elif mutation == "wrong_renderer":
        object.__setattr__(
            rows[1],
            "renderer",
            MappingProxyType(
                {
                    "renderer_id": "posix-path-line",
                    "renderer_version": 1,
                }
            ),
        )
    elif mutation == "wrong_version":
        object.__setattr__(
            rows[1],
            "renderer",
            MappingProxyType(
                {
                    "renderer_id": "canonical-json",
                    "renderer_version": 2,
                }
            ),
        )
    elif mutation == "wrong_value_digest":
        object.__setattr__(rows[1], "value_sha256", "sha256:" + "0" * 64)
    elif mutation == "wrong_raw_digest":
        object.__setattr__(
            rows[1],
            "raw_renderer_bytes_sha256",
            "sha256:" + "0" * 64,
        )
    elif mutation == "wrong_substitution_length":
        object.__setattr__(
            rows[1],
            "substitution_bytes",
            rows[1].substitution_bytes + 1,
        )
    elif mutation == "wrong_substitution_digest":
        object.__setattr__(
            rows[1],
            "substitution_bytes_sha256",
            "sha256:" + "0" * 64,
        )
    object.__setattr__(result, "trace", tuple(rows))

    with pytest.raises(
        ValueError,
        match="prompt_attempt_binding_plan_invalid",
    ):
        typed_prompt_inputs.render_typed_prompt_inputs(
            _typed_entries(),
            resolved_typed_values={
                "payload": _resolved_values()["payload"],
                "report_path": _resolved_values()["report_path"],
            },
            workflow_name="render-trace::run",
            step_id="root.render-trace",
            fragment_render_result=result,
            compiler_prompt_attempt_binding_plan=_plan(),
        )


def test_target_2_22_wrong_slot_kind_fails_trace_carrier_correspondence() -> None:
    from orchestrator.workflow_lisp import typed_prompt_inputs

    result = _render_target_2_22()
    plan = _plan()
    rows = list(plan.rows)
    rows[2] = replace(
        rows[2],
        slot_kind="text",
        renderer={
            "renderer_id": "raw-utf8-string",
            "renderer_version": 1,
        },
    )
    changed_plan = CompilerPromptAttemptBindingPlan(
        schema_version=plan.schema_version,
        rows=tuple(rows),
        plan_sha256=None,
    ).with_canonical_sha256()

    with pytest.raises(
        ValueError,
        match="prompt_attempt_binding_plan_invalid",
    ):
        typed_prompt_inputs.render_typed_prompt_inputs(
            _typed_entries(),
            resolved_typed_values={
                "payload": _resolved_values()["payload"],
                "report_path": _resolved_values()["report_path"],
            },
            workflow_name="render-trace::run",
            step_id="root.render-trace",
            fragment_render_result=result,
            compiler_prompt_attempt_binding_plan=changed_plan,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "missing",
        "extra",
        "duplicate",
        "reordered",
        "wrong_name",
        "wrong_renderer",
        "wrong_version",
        "wrong_value_digest",
        "wrong_raw_digest",
        "wrong_evidence_key",
    ),
)
def test_target_2_22_typed_evidence_tampering_fails_both_direction_check(
    mutation: str,
) -> None:
    from orchestrator.workflow_lisp import typed_prompt_inputs

    result = _render_target_2_22()
    kwargs = {
        "resolved_typed_values": {
            "payload": _resolved_values()["payload"],
            "report_path": _resolved_values()["report_path"],
        },
        "workflow_name": "render-trace::run",
        "step_id": "root.render-trace",
        "fragment_render_result": result,
        "compiler_prompt_attempt_binding_plan": _plan(),
    }
    _block, evidence = typed_prompt_inputs.render_typed_prompt_inputs(
        _typed_entries(),
        **kwargs,
    )
    changed = [dict(row) for row in evidence]
    if mutation == "missing":
        changed.pop()
    elif mutation == "extra":
        changed.append(dict(changed[-1]))
    elif mutation == "duplicate":
        changed[1] = dict(changed[0])
    elif mutation == "reordered":
        changed.reverse()
    elif mutation == "wrong_name":
        changed[0]["binding_name"] = "wrong"
    elif mutation == "wrong_renderer":
        changed[0]["renderer"] = dict(
            changed[0]["renderer"],
            renderer_id="posix-path-line",
        )
    elif mutation == "wrong_version":
        changed[0]["renderer"] = dict(
            changed[0]["renderer"],
            renderer_version=2,
        )
    elif mutation == "wrong_value_digest":
        changed[0]["value_digest"] = "sha256:" + "0" * 64
    elif mutation == "wrong_raw_digest":
        changed[0]["rendered_bytes_digest"] = "sha256:" + "0" * 64
    elif mutation == "wrong_evidence_key":
        changed[0]["evidence_key"] = "sha256:" + "0" * 64

    with pytest.raises(
        ValueError,
        match="prompt_attempt_binding_plan_invalid",
    ):
        typed_prompt_inputs.validate_typed_prompt_input_composition(
            _typed_entries(),
            evidence=changed,
            **kwargs,
        )


def test_target_2_22_trace_and_evidence_presence_must_match() -> None:
    from orchestrator.workflow_lisp import typed_prompt_inputs

    result = _render_target_2_22()
    values = {
        "payload": _resolved_values()["payload"],
        "report_path": _resolved_values()["report_path"],
    }
    _block, evidence = typed_prompt_inputs.render_typed_prompt_inputs(
        _typed_entries(),
        resolved_typed_values=values,
        workflow_name="render-trace::run",
        step_id="root.render-trace",
        fragment_render_result=result,
        compiler_prompt_attempt_binding_plan=_plan(),
    )

    with pytest.raises(
        ValueError,
        match="prompt_attempt_binding_plan_invalid",
    ):
        typed_prompt_inputs.validate_typed_prompt_input_composition(
            _typed_entries(),
            resolved_typed_values=values,
            evidence=[],
            workflow_name="render-trace::run",
            step_id="root.render-trace",
            fragment_render_result=result,
            compiler_prompt_attempt_binding_plan=_plan(),
        )
    with pytest.raises(
        ValueError,
        match="prompt_attempt_binding_plan_invalid",
    ):
        typed_prompt_inputs.validate_typed_prompt_input_composition(
            _typed_entries(),
            resolved_typed_values=values,
            evidence=evidence,
            workflow_name="render-trace::run",
            step_id="root.render-trace",
            fragment_render_result=None,
            compiler_prompt_attempt_binding_plan=_plan(),
        )
