"""Closed checkpoint-policy coverage for durable HumanReply artifacts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from types import MappingProxyType

import pytest

from orchestrator.workflow.human_input import human_reply_result_contract_digest
from orchestrator.workflow_lisp.lexical_checkpoint_effect_policies import (
    DIAGNOSTIC_CODES,
    build_effect_resume_policy,
)
from orchestrator.workflow_lisp import lexical_checkpoints
from tests.test_workflow_lisp_human_input import (
    _compile,
    _write_module,
)


def _compile_direct_request_bundle(tmp_path: Path):
    result = _compile(
        _write_module(
            tmp_path / "human_reply_checkpoint.orc",
            """  (defworkflow ask ((question String)) -> HumanReply
    (request-input question))""",
        ),
        workspace=tmp_path,
    )
    return result.validated_bundles["ask"]


def _completed_reply_record(
    point: object,
    artifacts: dict[str, object],
    *,
    visit_count: int = 1,
    runtime_step_id: str | None = None,
) -> dict[str, object]:
    point_payload = lexical_checkpoints._point_payload(point)
    ref = {
        "effect_ref_schema_version": "workflow_lisp_completed_effect_ref.v1",
        "effect_kind": "request_input",
        "step_id": point_payload["step_id"],
        "status": "completed",
        "source_map_origin_key": point_payload["origin_key"],
        "evidence_kind": "human_reply",
        "result_contract_digest": human_reply_result_contract_digest(),
        "artifact_digest": lexical_checkpoints._sha256_json(artifacts),
    }
    frame_identity: dict[str, object] = {
        "execution_index": 0,
        "visit_count": visit_count,
        "loop_iteration": None,
        "call_frame_id": None,
    }
    if runtime_step_id is not None:
        frame_identity["runtime_step_id"] = runtime_step_id
    return {
        "completed_effect_refs": [ref],
        "validity_envelope": {
            "completed_effect_refs_digest": lexical_checkpoints._completed_effect_refs_digest((ref,))
        },
        "frame_identity": frame_identity,
    }


_LOOP_REQUEST_SOURCE = """  (defproc ask-host ((question String)) -> HumanReply
    :effects ((host-input))
    :lowering inline
    (request-input question))
  (defworkflow ask ((question String)) -> HumanReply
    (loop/recur :max 2
      :state 0
      :on-exhausted (variant HumanReply CANCELLED)
      (fn (state)
        (match (ask-host question)
          ((ANSWERED answer) (done (variant HumanReply ANSWERED :text answer.text)))
          ((CANCELLED cancelled) (done (variant HumanReply CANCELLED)))))))"""


def test_human_reply_checkpoint_policy_has_only_fixed_contract_requirement() -> None:
    policy = build_effect_resume_policy(
        policy_kind="reuse_validated_human_reply",
        effect_kind="request_input",
        boundary_kind="request_input",
        step_id="ask",
        source_map_origin_key="source:ask",
        evidence_requirements={
            "human_reply": {
                "result_contract_digest": human_reply_result_contract_digest(),
            }
        },
    )

    assert policy["evidence_requirements"] == {
        "human_reply": {
            "result_contract_digest": human_reply_result_contract_digest(),
        }
    }


def test_human_reply_checkpoint_policy_rejects_non_request_boundary() -> None:
    with pytest.raises(ValueError, match=DIAGNOSTIC_CODES.boundary_mismatch):
        build_effect_resume_policy(
            policy_kind="reuse_validated_human_reply",
            effect_kind="provider",
            boundary_kind="provider",
            step_id="ask",
            source_map_origin_key="source:ask",
            evidence_requirements={
                "human_reply": {"result_contract_digest": "sha256:" + "0" * 64}
            },
        )


def test_human_reply_checkpoint_policy_rejects_extra_evidence() -> None:
    with pytest.raises(ValueError, match=DIAGNOSTIC_CODES.evidence_invalid):
        build_effect_resume_policy(
            policy_kind="reuse_validated_human_reply",
            effect_kind="request_input",
            boundary_kind="request_input",
            step_id="ask",
            source_map_origin_key="source:ask",
            evidence_requirements={
                "human_reply": {
                    "result_contract_digest": human_reply_result_contract_digest(),
                },
                "structured_output": {},
            },
        )


def test_completed_human_reply_ref_seals_full_fixed_artifacts() -> None:
    contract_digest = human_reply_result_contract_digest()
    point = SimpleNamespace(
        node_id="node.ask",
        presentation_key="Ask",
        step_id="ask",
        origin_key="source:ask",
        details={
            "effect_boundary": {
                "effect_kind": "request_input",
                "policy": build_effect_resume_policy(
                    policy_kind="reuse_validated_human_reply",
                    effect_kind="request_input",
                    boundary_kind="request_input",
                    step_id="ask",
                    source_map_origin_key="source:ask",
                    evidence_requirements={
                        "human_reply": {"result_contract_digest": contract_digest}
                    },
                ),
            }
        },
    )
    step_state = {
        "status": "completed",
        "step_id": "ask",
        "artifacts": {"variant": "ANSWERED", "text": "yes"},
    }
    executor = SimpleNamespace(
        state_manager=SimpleNamespace(state={"steps": {"Ask": step_state}}),
        _runtime_step_for_node_id=lambda *_args, **_kwargs: {
            "name": "Ask", "step_id": "ask"
        },
    )

    [ref] = lexical_checkpoints.collect_completed_effect_refs(
        executor, point=point, committed_step_state=step_state
    )

    assert ref["evidence_kind"] == "human_reply"
    assert ref["result_contract_digest"] == contract_digest
    assert ref["artifact_digest"] == lexical_checkpoints._sha256_json(
        step_state["artifacts"]
    )
    lexical_checkpoints._validate_completed_effect_refs(
        {
            "completed_effect_refs": [ref],
            "validity_envelope": {
                "completed_effect_refs_digest": lexical_checkpoints._completed_effect_refs_digest((ref,))
            },
        },
        expected_point=lexical_checkpoints._point_payload(point),
    )
    assert lexical_checkpoints.collect_completed_effect_refs(
        executor, point=point
    ) == []


def test_human_reply_authority_uses_compiled_top_level_projection_identity(
    tmp_path: Path,
) -> None:
    bundle = _compile_direct_request_bundle(tmp_path)
    [point] = bundle.runtime_plan.lexical_checkpoint_points
    artifacts = {"variant": "ANSWERED", "text": "accepted"}
    state = {
        "steps": {
            point.presentation_key: {
                "status": "completed",
                "step_id": point.step_id,
                "visit_count": 1,
                "artifacts": artifacts,
            },
            "unclaimed-later-row": {
                "status": "completed",
                "step_id": point.step_id,
                "visit_count": 99,
                "artifacts": {"variant": "ANSWERED", "text": "wrong row"},
            },
        }
    }
    record = _completed_reply_record(point, artifacts)

    lexical_checkpoints.validate_completed_effect_refs_against_authoritative_state(
        record,
        expected_point=lexical_checkpoints._point_payload(point),
        state=state,
        state_manager=SimpleNamespace(),
        workspace=tmp_path,
        executable_workflow=bundle.ir,
        runtime_plan=bundle.runtime_plan,
        loaded_workflow=bundle,
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "wrong_visit",
        "missing_visit",
        "boolean_visit",
        "string_visit",
        "wrong_runtime_id",
        "missing_artifacts",
        "invalid_active_payload",
    ),
)
def test_human_reply_authority_rejects_resealed_invalid_projection_or_artifacts(
    tmp_path: Path,
    mutation: str,
) -> None:
    bundle = _compile_direct_request_bundle(tmp_path)
    [point] = bundle.runtime_plan.lexical_checkpoint_points
    artifacts: dict[str, object] = {"variant": "ANSWERED", "text": "accepted"}
    state = {
        "steps": {
            point.presentation_key: {
                "status": "completed",
                "step_id": point.step_id,
                "visit_count": 1,
                "artifacts": artifacts,
            }
        }
    }
    record = _completed_reply_record(point, artifacts)
    if mutation == "wrong_visit":
        record["frame_identity"]["visit_count"] = 2
    elif mutation == "missing_visit":
        record["frame_identity"]["visit_count"] = None
    elif mutation == "boolean_visit":
        record["frame_identity"]["visit_count"] = True
    elif mutation == "string_visit":
        record["frame_identity"]["visit_count"] = "1"
    elif mutation == "wrong_runtime_id":
        record["frame_identity"]["runtime_step_id"] = "wrong-runtime-id"
    elif mutation == "missing_artifacts":
        state["steps"][point.presentation_key]["artifacts"] = {}
        record = _completed_reply_record(point, {})
    else:
        invalid = {"variant": "ANSWERED"}
        state["steps"][point.presentation_key]["artifacts"] = invalid
        record = _completed_reply_record(point, invalid)

    with pytest.raises(ValueError, match="lexical_checkpoint_completed_effect_invalid"):
        lexical_checkpoints.validate_completed_effect_refs_against_authoritative_state(
            record,
            expected_point=lexical_checkpoints._point_payload(point),
            state=state,
            state_manager=SimpleNamespace(),
            workspace=tmp_path,
            executable_workflow=bundle.ir,
            runtime_plan=bundle.runtime_plan,
            loaded_workflow=bundle,
        )


def test_human_reply_authority_rejects_ambiguous_compiled_projection_slot(
    tmp_path: Path,
) -> None:
    bundle = _compile_direct_request_bundle(tmp_path)
    [point] = bundle.runtime_plan.lexical_checkpoint_points
    artifacts = {"variant": "CANCELLED"}
    state = {
        "steps": {
            point.presentation_key: {
                "status": "completed",
                "step_id": point.step_id,
                "visit_count": 1,
                "artifacts": artifacts,
            }
        }
    }
    entry = bundle.projection.entries_by_node_id[point.node_id]
    ambiguous_projection = replace(
        bundle.projection,
        entries_by_node_id=MappingProxyType(
            {
                **bundle.projection.entries_by_node_id,
                "duplicate.ask": replace(
                    entry,
                    node_id="duplicate.ask",
                    presentation_key="alternate.ask",
                ),
            }
        ),
    )
    ambiguous_bundle = replace(bundle, projection=ambiguous_projection)

    with pytest.raises(ValueError, match="lexical_checkpoint_completed_effect_invalid"):
        lexical_checkpoints.validate_completed_effect_refs_against_authoritative_state(
            _completed_reply_record(point, artifacts),
            expected_point=lexical_checkpoints._point_payload(point),
            state=state,
            state_manager=SimpleNamespace(),
            workspace=tmp_path,
            executable_workflow=bundle.ir,
            runtime_plan=bundle.runtime_plan,
            loaded_workflow=ambiguous_bundle,
        )


def test_human_reply_exact_lookup_uses_compiled_qualified_loop_slot(
    tmp_path: Path,
) -> None:
    bundle = _compile(
        _write_module(tmp_path / "loop_request.orc", _LOOP_REQUEST_SOURCE),
        workspace=tmp_path,
    ).validated_bundles["ask"]
    loop_node_id, loop_projection = next(
        iter(bundle.projection.repeat_until_nodes.items())
    )
    nested_node_id = next(
        node_id
        for node_id in loop_projection.nested_presentation_keys
        if "call_ask_host" in node_id
    )
    runtime_step_id = bundle.projection.repeat_until_runtime_step_id(
        loop_node_id, 0, nested_node_id
    )
    presentation_key = bundle.projection.repeat_until_step_key(
        loop_node_id, 0, nested_node_id
    )
    state = {
        "steps": {
            presentation_key: {
                "status": "completed",
                "step_id": runtime_step_id,
                "visit_count": 1,
                "artifacts": {"variant": "CANCELLED"},
            }
        },
        "repeat_until": {
            loop_projection.frame_key: {
                "current_iteration": 0,
                "completed_iterations": [],
                "condition_evaluated_for_iteration": None,
                "last_condition_result": None,
            }
        },
    }
    record = {
        "frame_identity": {
            "runtime_step_id": runtime_step_id,
            "loop_iteration": 0,
            "visit_count": 1,
        }
    }

    resolved = lexical_checkpoints._exact_human_reply_step_state(
        loaded_workflow=bundle,
        state=state,
        expected_point={"node_id": nested_node_id},
        record=record,
        runtime_step=SimpleNamespace(name="unused", step_id="unused"),
    )

    assert resolved is state["steps"][presentation_key]
    with pytest.raises(ValueError, match="lexical_checkpoint_completed_effect_invalid"):
        lexical_checkpoints._exact_human_reply_step_state(
            loaded_workflow=bundle,
            state=state,
            expected_point={"node_id": "wrong.node"},
            record=record,
            runtime_step=SimpleNamespace(name="unused", step_id="unused"),
        )
