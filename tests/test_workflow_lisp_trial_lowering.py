from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_output_bundle,
)
from orchestrator.workflow.persisted_surface import (
    PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA,
    PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V2,
    PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V3,
    PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V4,
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
)
from orchestrator.workflow.runtime_step import RuntimeStep, thaw_runtime_value
from orchestrator.workflow.executable_ir import derive_unbound_trial_step_config
from orchestrator.workflow.surface_ast import (
    SurfaceStep,
    SurfaceStepKind,
    TrialSurfaceStep,
)
from orchestrator.workflow.trial.config import (
    decode_trial_static_config,
    encode_trial_static_config,
)
from orchestrator.state import StateManager
from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle
from orchestrator.workflow_lisp.compiler import WorkflowBoundaryAdmissionProfile
from orchestrator.workflow_lisp import lexical_checkpoints
from orchestrator.workflow_lisp import lexical_checkpoint_restore
from orchestrator.workflow_lisp.lexical_checkpoint_effect_policies import (
    derive_effect_resume_policy_digest,
    validate_effect_resume_policy,
)
from orchestrator.workflow_lisp.wcc.route import LoweringRoute


COMMIT_A = "0123456789abcdef0123456789abcdef01234567"
COMMIT_B = "89abcdef0123456789abcdef0123456789abcdef"


TRANSPORTABLE_TRIAL_TYPES = (
    pytest.param("", "Bool", {"kind": "primitive", "name": "Bool"}, id="direct"),
    pytest.param(
        "  (defrecord Measurement (label String))\n",
        "Measurement",
        {
            "kind": "record",
            "name": "Measurement",
            "fields": [
                {
                    "name": "label",
                    "type": {"kind": "primitive", "name": "String"},
                }
            ],
        },
        id="record",
    ),
    pytest.param(
        "  (defunion Outcome (Completed) (Failed))\n",
        "Outcome",
        {
            "kind": "union",
            "name": "Outcome",
            "variants": [
                {"name": "Completed", "fields": []},
                {"name": "Failed", "fields": []},
            ],
        },
        id="union",
    ),
    pytest.param(
        "",
        "Optional[String]",
        {
            "kind": "optional",
            "item": {"kind": "primitive", "name": "String"},
        },
        id="optional",
    ),
    pytest.param(
        "",
        "List[String]",
        {
            "kind": "list",
            "item": {"kind": "primitive", "name": "String"},
        },
        id="list",
    ),
    pytest.param(
        "",
        "Map[String,Int]",
        {
            "kind": "map",
            "key": {"kind": "primitive", "name": "String"},
            "value": {"kind": "primitive", "name": "Int"},
        },
        id="map",
    ),
    pytest.param(
        (
            "  (defpath ArtifactPath\n"
            "    :kind relpath\n"
            '    :under "artifacts/work"\n'
            "    :must-exist false)\n"
        ),
        "ArtifactPath",
        {
            "kind": "path",
            "name": "ArtifactPath",
            "under": "artifacts/work",
            "must_exist_target": False,
        },
        id="path",
    ),
    pytest.param("", "Value", {"kind": "primitive", "name": "Value"}, id="value"),
)


def _write_trial_module(tmp_path: Path) -> Path:
    source_path = tmp_path / "trial_lowering.orc"
    source_path.write_text(
        f'''\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule trial_lowering)
  (export compare first second)
  (defworkflow first () -> String "first")
  (defworkflow second () -> String "second")
  (defworkflow compare () -> Value
    (trial
      :arms ((:id "direct"
              :run-ref
              (run-ref
                :source (:repo "file:///workspace" :commit "{COMMIT_A}")
                :program (:bundle first)
                :inputs ()
                :policy (:setup ())))
             (:id "orc"
              :run-ref
              (run-ref
                :source (:repo "file:///workspace" :commit "{COMMIT_B}")
                :program (:bundle second)
                :inputs ()
                :policy (:setup ()))))
      :reps 2
      :max-concurrency 2
      :evaluation
      (record
        :checks (list)
        :judgment
        (record :provider "scorer"
                :rubric-asset "rubrics/trial.md"
                :evidence-confidentiality "same_trust_boundary"
                :evidence-limits
                (record :max-item-bytes 4096 :max-packet-bytes 8192))
        :observation
        (record :include (list "validated_result")
                :diff-cap-bytes 4096
                :reveal-provider-identity false)
        :aggregation
        (record :mode "independent_rubric"
                :rep-combine "median"
                :tie "authored_order")
        :success-rule
        (record :superior
                (record :min-abs-improvement 0.10 :max-cost-ratio 1.5)
                :non-inferior
                (record :min-cost-reduction 0.20)
                :count-failures-as-outcomes true))
      :budget
      (record :arm-timeout-ms 900000
              :trial-timeout-ms 3600000
              :max-evaluator-attempts 4
              :max-evaluator-concurrency 2))))
''',
        encoding="utf-8",
    )
    (tmp_path / "providers.json").write_text(
        json.dumps({"scorer": "test-provider"}),
        encoding="utf-8",
    )
    (tmp_path / "prompts.json").write_text(
        json.dumps({"trial-rubric": "rubrics/trial.md"}),
        encoding="utf-8",
    )
    rubric_path = tmp_path / "rubrics" / "trial.md"
    rubric_path.parent.mkdir(parents=True)
    rubric_path.write_text("Score the supplied evidence.\n", encoding="utf-8")
    return source_path


def _build_trial(tmp_path: Path):
    source_path = _write_trial_module(tmp_path)
    return source_path, _compile_trial_source(source_path, workspace=tmp_path)


def _build_nonterminal_trial(tmp_path: Path):
    source_path = _write_trial_module(tmp_path)
    source = source_path.read_text(encoding="utf-8")
    source = source.replace(
        "  (export compare first second)\n",
        (
            "  (export compare first second)\n"
            "  (defrecord FinalResult (summary String))\n"
        ),
        1,
    )
    source = source.replace(
        "  (defworkflow compare () -> Value\n    (trial",
        (
            "  (defworkflow compare () -> FinalResult\n"
            "    (let* ((trial-result\n"
            "             (trial"
        ),
        1,
    )
    source = source.replace(
        "              :max-evaluator-concurrency 2))))\n",
        (
            "              :max-evaluator-concurrency 2))))\n"
            '      (record FinalResult :summary "done"))))\n'
        ),
        1,
    )
    source_path.write_text(source, encoding="utf-8")
    return source_path, _compile_trial_source(source_path, workspace=tmp_path)


def _compile_trial_source(source_path: Path, *, workspace: Path):
    return build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(workspace,),
            entry_workflow="compare",
            provider_externs_path=workspace / "providers.json",
            prompt_externs_path=workspace / "prompts.json",
            workspace_root=workspace,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )


def _trial_node(result):
    [node] = [
        node
        for node in result.validated_bundle.ir.nodes.values()
        if node.kind.value == "trial"
    ]
    return node


def _write_transportable_trial_module(
    tmp_path: Path,
    *,
    declarations: str,
    type_name: str,
) -> Path:
    source_path = tmp_path / "transportable_trial.orc"
    source_path.write_text(
        f'''\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule transportable_trial)
  (export compare first second)
{declarations}  (defworkflow first ((payload {type_name})) -> {type_name} payload)
  (defworkflow second ((payload {type_name})) -> {type_name} payload)
  (defworkflow compare ((payload {type_name})) -> Value
    (trial
      :arms ((:id "direct"
              :run-ref
              (run-ref
                :source (:repo "file:///workspace" :commit "{COMMIT_A}")
                :program (:bundle first)
                :inputs (:payload payload)
                :policy (:setup ())))
             (:id "orc"
              :run-ref
              (run-ref
                :source (:repo "file:///workspace" :commit "{COMMIT_B}")
                :program (:bundle second)
                :inputs (:payload payload)
                :policy (:setup ()))))
      :reps 2
      :max-concurrency 2
      :evaluation
      (record
        :checks (list)
        :judgment
        (record :provider "scorer"
                :rubric-asset "rubrics/trial.md"
                :evidence-confidentiality "same_trust_boundary"
                :evidence-limits
                (record :max-item-bytes 4096 :max-packet-bytes 8192))
        :observation
        (record :include (list "validated_result")
                :diff-cap-bytes 4096
                :reveal-provider-identity false)
        :aggregation
        (record :mode "independent_rubric"
                :rep-combine "median"
                :tie "authored_order")
        :success-rule
        (record :superior
                (record :min-abs-improvement 0.10 :max-cost-ratio 1.5)
                :non-inferior
                (record :min-cost-reduction 0.20)
                :count-failures-as-outcomes true))
      :budget
      (record :arm-timeout-ms 900000
              :trial-timeout-ms 3600000
              :max-evaluator-attempts 4
              :max-evaluator-concurrency 2))))
''',
        encoding="utf-8",
    )
    (tmp_path / "providers.json").write_text(
        json.dumps({"scorer": "test-provider"}),
        encoding="utf-8",
    )
    (tmp_path / "prompts.json").write_text(
        json.dumps({"trial-rubric": "rubrics/trial.md"}),
        encoding="utf-8",
    )
    rubric_path = tmp_path / "rubrics" / "trial.md"
    rubric_path.parent.mkdir(parents=True)
    rubric_path.write_text("Score the supplied evidence.\n", encoding="utf-8")
    return source_path


def _build_transportable_trial(
    tmp_path: Path,
    *,
    declarations: str,
    type_name: str,
):
    source_path = _write_transportable_trial_module(
        tmp_path,
        declarations=declarations,
        type_name=type_name,
    )
    return build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(tmp_path,),
            entry_workflow="compare",
            provider_externs_path=tmp_path / "providers.json",
            prompt_externs_path=tmp_path / "prompts.json",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.WCC_M4,
            boundary_admission_profile=(
                WorkflowBoundaryAdmissionProfile.TRANSPORTABLE_CHILD
            ),
        )
    )


def _completed_trial_value_type(result_descriptor: dict[str, object]) -> object:
    [outcomes_field] = [
        field
        for field in result_descriptor["envelope"]["fields"]
        if field["name"] == "outcomes"
    ]
    [completed_variant] = [
        variant
        for variant in outcomes_field["type"]["item"]["variants"]
        if variant["name"] == "Completed"
    ]
    [value_field] = [
        field for field in completed_variant["fields"] if field["name"] == "value"
    ]
    return value_field["type"]


def test_public_compiler_carries_one_trial_across_all_compiler_views(
    tmp_path: Path,
) -> None:
    source_path, result = _build_trial(tmp_path)

    trial_nodes = [
        node
        for node in result.validated_bundle.ir.nodes.values()
        if node.kind.value == "trial"
    ]
    assert len(trial_nodes) == 1
    [node] = trial_nodes
    assert result.run_ref_bundle_capsule is not None
    assert node.execution_config.trial.evaluation["provider"] == "test-provider"
    assert node.execution_config.trial.digest.startswith("sha256:")
    assert [arm.arm_id for arm in node.execution_config.trial.arms] == [
        "direct",
        "orc",
    ]
    capsule_digests = {
        arm.run_ref.capsule_binding.capsule_digest
        for arm in node.execution_config.arms
        if arm.run_ref.capsule_binding is not None
    }
    assert all(
        arm.run_ref.capsule_binding is not None
        for arm in node.execution_config.arms
    )
    assert capsule_digests == {result.run_ref_bundle_capsule.capsule_digest}
    assert (
        node.execution_config.step_config_digest
        != derive_unbound_trial_step_config(
            node.execution_config.trial
        ).step_config_digest
    )
    assert any(
        effect.effect_kind == "trial"
        for effect in result.validated_bundle.semantic_ir.effects.values()
    )
    assert result.validated_bundle.runtime_plan.nodes[
        node.node_id
    ].trial_config_digest == node.execution_config.trial.digest
    assert result.validated_bundle.runtime_plan.nodes[
        node.node_id
    ].trial_result_contract_digest == node.execution_config.trial.result_digest
    [checkpoint_point] = [
        point
        for point in result.validated_bundle.runtime_plan.lexical_checkpoint_points
        if point.details.get("step_kind") == "trial"
    ]
    assert checkpoint_point.details["executable_identity"][
        "identity_component_digest"
    ] == node.execution_config.trial.digest
    policy = checkpoint_point.details["effect_boundary"]["policy"]
    assert policy["policy_kind"] == "reuse_validated_trial_result"
    assert policy["effect_kind"] == "trial"
    assert policy["boundary_kind"] == "trial"
    assert policy["unsafe_pending_behavior"] == "fail_closed"
    assert policy["evidence_requirements"] == {
        "trial_result": {
            "trial_static_config_digest": node.execution_config.trial.digest,
            "result_contract_digest": node.execution_config.trial.result_digest,
        }
    }
    validate_effect_resume_policy(
        policy,
        expected_origin_key=checkpoint_point.origin_key,
    )
    malformed_policies = []
    missing_evidence = deepcopy(dict(policy))
    missing_evidence["evidence_requirements"] = {}
    malformed_policies.append(missing_evidence)
    extra_evidence = deepcopy(dict(policy))
    extra_evidence["evidence_requirements"]["unexpected"] = {}
    malformed_policies.append(extra_evidence)
    missing_result_digest = deepcopy(dict(policy))
    missing_result_digest["evidence_requirements"]["trial_result"].pop(
        "result_contract_digest"
    )
    malformed_policies.append(missing_result_digest)
    extra_trial_field = deepcopy(dict(policy))
    extra_trial_field["evidence_requirements"]["trial_result"]["unexpected"] = True
    malformed_policies.append(extra_trial_field)
    for malformed_policy in malformed_policies:
        malformed_policy["policy_digest"] = derive_effect_resume_policy_digest(
            malformed_policy
        )
        with pytest.raises((TypeError, ValueError)):
            validate_effect_resume_policy(
                malformed_policy,
                expected_origin_key=checkpoint_point.origin_key,
            )
    for digest_name in (
        "trial_static_config_digest",
        "result_contract_digest",
    ):
        stale_details = deepcopy(dict(checkpoint_point.details))
        stale_policy = deepcopy(dict(policy))
        stale_policy["evidence_requirements"]["trial_result"][digest_name] = (
            "sha256:" + "0" * 64
        )
        stale_policy["policy_digest"] = derive_effect_resume_policy_digest(
            stale_policy
        )
        stale_details["effect_boundary"] = {
            **dict(stale_details["effect_boundary"]),
            "policy": stale_policy,
        }
        with pytest.raises(
            ValueError,
            match="lexical_checkpoint_program_identity_mismatch",
        ):
            lexical_checkpoints._component_checkpoint_policy_digest(
                replace(checkpoint_point, details=stale_details),
                required=True,
            )
    runtime_step = RuntimeStep(
        node=node,
        name=checkpoint_point.presentation_key,
        step_id=checkpoint_point.step_id,
        target_dsl_version=result.validated_bundle.ir.version,
    )
    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_effect_policy_trial_result_invalid",
    ):
        lexical_checkpoints.collect_completed_effect_refs(
            SimpleNamespace(
                state_manager=SimpleNamespace(state={"steps": {}}),
                _runtime_step_for_node_id=lambda *_args, **_kwargs: runtime_step,
            ),
            point=checkpoint_point,
            committed_step_state={
                "status": "completed",
                "step_id": checkpoint_point.step_id,
            },
        )
    point_payload = lexical_checkpoints._point_payload(checkpoint_point)
    empty_record = {
        "completed_effect_refs": [],
        "validity_envelope": {
            "completed_effect_refs_digest": (
                lexical_checkpoints._completed_effect_refs_digest(())
            )
        },
    }
    lexical_checkpoints._validate_completed_effect_refs(
        empty_record,
        expected_point=point_payload,
    )
    forged_ref = {
        "effect_ref_schema_version": "workflow_lisp_completed_effect_ref.v1",
        "effect_kind": "trial",
        "step_id": checkpoint_point.step_id,
        "status": "completed",
        "source_map_origin_key": checkpoint_point.origin_key,
        "evidence_kind": "trial_result",
    }
    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_effect_policy_trial_result_invalid",
    ):
        lexical_checkpoints._validate_completed_effect_refs(
            {
                "completed_effect_refs": [forged_ref],
                "validity_envelope": {
                    "completed_effect_refs_digest": (
                        lexical_checkpoints._completed_effect_refs_digest(
                            (forged_ref,)
                        )
                    )
                },
            },
            expected_point=point_payload,
        )
    run_workspace = tmp_path / "run"
    run_workspace.mkdir()
    state_manager = StateManager(run_workspace, run_id="trial-pending-checkpoint")
    state_manager.initialize(str(source_path))
    checkpoint_executor = SimpleNamespace(
        runtime_plan=result.validated_bundle.runtime_plan,
        state_manager=state_manager,
        loaded_bundle=result.validated_bundle,
        workspace=run_workspace,
        _runtime_step_for_node_id=lambda *_args, **_kwargs: runtime_step,
    )
    record = lexical_checkpoints.emit_runtime_shadow_record(
        executor=checkpoint_executor,
        step_id=checkpoint_point.step_id,
        execution_index=result.validated_bundle.runtime_plan.nodes[
            node.node_id
        ].execution_index,
        visit_count=1,
    )
    assert record is not None
    assert record["completed_effect_refs"] == []
    decision = lexical_checkpoint_restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=result.validated_bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=checkpoint_point.checkpoint_id,
        executable_workflow=result.validated_bundle.ir,
        loaded_workflow=result.validated_bundle,
    )
    assert decision.kind == lexical_checkpoint_restore.RESTORE_DECISION_NOT_RESTORABLE
    assert decision.policy_decision is None
    assert decision.diagnostics == (
        lexical_checkpoint_restore.DIAGNOSTIC_CODES.pending_effect_unsafe,
    )
    persisted_payload = json.loads(
        result.artifact_paths["persisted_workflow_surface"].read_text(
            encoding="utf-8"
        )
    )
    assert (
        persisted_payload["schema_version"]
        == PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V4
    )
    persisted_graph = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(persisted_payload)
    )
    [persisted_trial] = [
        step
        for step in persisted_graph.entry_node.steps
        if step.kind.value == "trial"
    ]
    assert persisted_trial.trial is not None
    assert persisted_trial.trial.record == node.execution_config.trial.record
    assert persisted_trial.trial.digest == node.execution_config.trial.digest
    assert result.manifest.source_map_coverage is not None
    assert set(result.manifest.source_map_coverage.values()) == {"covered"}


def test_trial_surface_subtype_preserves_ordinary_step_shape_and_pairing(
    tmp_path: Path,
) -> None:
    assert "trial" not in {field.name for field in fields(SurfaceStep)}
    with pytest.raises(ValueError, match="trial kind/config pairing is invalid"):
        SurfaceStep(
            name="invalid-trial",
            step_id="root.invalid-trial",
            kind=SurfaceStepKind.TRIAL,
        )

    _, result = _build_trial(tmp_path)
    [trial_step] = [
        step
        for step in result.validated_bundle.surface.steps
        if step.kind is SurfaceStepKind.TRIAL
    ]
    assert type(trial_step) is TrialSurfaceStep
    assert "trial" in {field.name for field in fields(TrialSurfaceStep)}
    assert trial_step.trial.digest == _trial_node(
        result
    ).execution_config.trial.digest


def test_nonterminal_trial_output_bundle_uses_trial_contract_not_workflow_return(
    tmp_path: Path,
) -> None:
    _, result = _build_nonterminal_trial(tmp_path)
    node = _trial_node(result)
    output_bundle = node.execution_config.common.output_bundle
    assert output_bundle is not None
    assert tuple(field["name"] for field in output_bundle["fields"]) == (
        "outcomes",
        "verdict__authored_arm_order",
        "verdict__per_repetition",
        "verdict__aggregate_scores",
        "verdict__ranking",
        "verdict__selected_arm",
        "verdict__success_rule_disposition",
        "verdict__budget_accounting__cell_count",
        "verdict__budget_accounting__completed_count",
        "verdict__budget_accounting__failed_count",
        "verdict__budget_accounting__child_attempts",
        "verdict__budget_accounting__evaluator_attempts",
        "verdict__budget_accounting__elapsed_ms",
        "verdict__budget_accounting__token_usage__variant",
        "verdict__budget_accounting__token_usage__prompt_tokens",
        "verdict__budget_accounting__token_usage__completion_tokens",
        "verdict__budget_accounting__token_usage__total_tokens",
        "verdict__budget_accounting__cost__variant",
        "verdict__budget_accounting__cost__amount",
        "verdict__budget_accounting__cost__currency",
        "verdict_artifact",
    )


def _compiled_trial_output_bundle(tmp_path: Path) -> dict[str, object]:
    _, result = _build_nonterminal_trial(tmp_path)
    output_bundle = thaw_runtime_value(
        _trial_node(result).execution_config.common.output_bundle
    )
    output_bundle["path"] = "artifacts/trials/trial-result.json"
    return output_bundle


def _trial_result_document() -> dict[str, object]:
    return {
        "outcomes": [],
        "verdict": {
            "authored_arm_order": ["direct", "orc"],
            "per_repetition": [],
            "aggregate_scores": [],
            "ranking": ["direct", "orc"],
            "selected_arm": "direct",
            "success_rule_disposition": "superior",
            "budget_accounting": {
                "cell_count": 4,
                "completed_count": 4,
                "failed_count": 0,
                "child_attempts": 4,
                "evaluator_attempts": 2,
                "elapsed_ms": 1250,
                "token_usage": {"variant": "UNKNOWN"},
                "cost": {"variant": "UNKNOWN"},
            },
        },
        "verdict_artifact": "artifacts/trials/verdict.json",
    }


def _write_trial_result_document(tmp_path: Path, document: dict[str, object]) -> None:
    result_path = tmp_path / "artifacts" / "trials" / "trial-result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(document), encoding="utf-8")
    (result_path.parent / "verdict.json").write_text("{}\n", encoding="utf-8")


def test_trial_output_bundle_uses_closed_union_projection_metadata(
    tmp_path: Path,
) -> None:
    output_bundle = _compiled_trial_output_bundle(tmp_path)
    fields_by_name = {
        field["name"]: field for field in output_bundle["fields"]
    }

    token_discriminant = fields_by_name[
        "verdict__budget_accounting__token_usage__variant"
    ]
    cost_discriminant = fields_by_name[
        "verdict__budget_accounting__cost__variant"
    ]
    token_projection = token_discriminant["projection"]
    cost_projection = cost_discriminant["projection"]
    assert token_projection == {
        "projection_class": "union_workflow_boundary",
        "return_kind": "union",
        "union_output_group": token_projection["union_output_group"],
        "discriminant_output": token_discriminant["name"],
        "field_role": "discriminant",
        "active_variants": ["KNOWN", "UNKNOWN"],
    }
    assert cost_projection == {
        "projection_class": "union_workflow_boundary",
        "return_kind": "union",
        "union_output_group": cost_projection["union_output_group"],
        "discriminant_output": cost_discriminant["name"],
        "field_role": "discriminant",
        "active_variants": ["KNOWN", "UNKNOWN"],
    }
    assert token_projection["union_output_group"] != cost_projection[
        "union_output_group"
    ]

    for suffix in ("prompt_tokens", "completion_tokens", "total_tokens"):
        field = fields_by_name[
            f"verdict__budget_accounting__token_usage__{suffix}"
        ]
        assert field["projection"] == {
            **token_projection,
            "field_role": "variant",
            "active_variants": ["KNOWN"],
        }
    for suffix in ("amount", "currency"):
        field = fields_by_name[f"verdict__budget_accounting__cost__{suffix}"]
        assert field["projection"] == {
            **cost_projection,
            "field_role": "variant",
            "active_variants": ["KNOWN"],
        }


def test_real_compiled_trial_contract_enforces_active_union_payloads(
    tmp_path: Path,
) -> None:
    output_bundle = _compiled_trial_output_bundle(tmp_path)
    unknown = _trial_result_document()
    _write_trial_result_document(tmp_path, unknown)

    artifacts = validate_output_bundle(output_bundle, workspace=tmp_path)
    assert artifacts[
        "verdict__budget_accounting__token_usage__variant"
    ] == "UNKNOWN"
    assert artifacts["verdict__budget_accounting__cost__variant"] == "UNKNOWN"
    assert not any(
        name.startswith("verdict__budget_accounting__token_usage__")
        and not name.endswith("__variant")
        for name in artifacts
    )
    assert not any(
        name.startswith("verdict__budget_accounting__cost__")
        and not name.endswith("__variant")
        for name in artifacts
    )

    complete_known = deepcopy(unknown)
    accounting = complete_known["verdict"]["budget_accounting"]
    accounting["token_usage"] = {
        "variant": "KNOWN",
        "prompt_tokens": 100,
        "completion_tokens": 25,
        "total_tokens": 125,
    }
    accounting["cost"] = {
        "variant": "KNOWN",
        "amount": 0.25,
        "currency": "USD",
    }
    _write_trial_result_document(tmp_path, complete_known)
    known_artifacts = validate_output_bundle(output_bundle, workspace=tmp_path)
    assert known_artifacts[
        "verdict__budget_accounting__token_usage__total_tokens"
    ] == 125
    assert known_artifacts["verdict__budget_accounting__cost__amount"] == 0.25

    payload_paths = (
        ("token_usage", "prompt_tokens"),
        ("token_usage", "completion_tokens"),
        ("token_usage", "total_tokens"),
        ("cost", "amount"),
        ("cost", "currency"),
    )
    for union_name, payload_name in payload_paths:
        missing_payload = deepcopy(complete_known)
        del missing_payload["verdict"]["budget_accounting"][union_name][
            payload_name
        ]
        _write_trial_result_document(tmp_path, missing_payload)
        with pytest.raises(OutputContractError) as exc_info:
            validate_output_bundle(output_bundle, workspace=tmp_path)
        assert any(
            violation["type"] == "json_pointer_not_found"
            and violation["context"]["name"].endswith(payload_name)
            for violation in exc_info.value.violations
        )

    for union_name, payload_name, payload_value in (
        ("token_usage", "prompt_tokens", 100),
        ("cost", "amount", 0.25),
    ):
        inactive_payload = deepcopy(unknown)
        inactive_payload["verdict"]["budget_accounting"][union_name][
            payload_name
        ] = payload_value
        _write_trial_result_document(tmp_path, inactive_payload)
        with pytest.raises(OutputContractError) as exc_info:
            validate_output_bundle(output_bundle, workspace=tmp_path)
        assert any(
            violation["type"] == "inactive_union_output_present"
            for violation in exc_info.value.violations
        )


@pytest.mark.parametrize(
    ("declarations", "type_name", "expected_descriptor"),
    TRANSPORTABLE_TRIAL_TYPES,
)
def test_public_compiler_round_trips_every_transportable_trial_value_type(
    tmp_path: Path,
    declarations: str,
    type_name: str,
    expected_descriptor: dict[str, object],
) -> None:
    result = _build_transportable_trial(
        tmp_path,
        declarations=declarations,
        type_name=type_name,
    )
    [node] = [
        node
        for node in result.validated_bundle.ir.nodes.values()
        if node.kind.value == "trial"
    ]
    config = node.execution_config.trial

    assert len(node.execution_config.arms) == 2
    assert all(
        tuple(input_config.name for input_config in arm.run_ref.run_ref.inputs)
        == ("payload",)
        for arm in node.execution_config.arms
    )
    assert all(
        arm.run_ref.result_descriptor["envelope"]["fields"][0]["type"]
        == expected_descriptor
        for arm in config.arms
    )
    assert _completed_trial_value_type(config.result_descriptor) == expected_descriptor
    assert result.validated_bundle.runtime_plan.nodes[
        node.node_id
    ].trial_config_digest == config.digest
    assert result.validated_bundle.runtime_plan.nodes[
        node.node_id
    ].trial_result_contract_digest == config.result_digest

    persisted_payload = json.loads(
        result.artifact_paths["persisted_workflow_surface"].read_text(
            encoding="utf-8"
        )
    )
    persisted_graph = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(persisted_payload)
    )
    [persisted_trial] = [
        step
        for step in persisted_graph.entry_node.steps
        if step.kind.value == "trial"
    ]
    assert persisted_trial.trial is not None
    assert persisted_trial.trial.record == config.record
    assert persisted_trial.trial.digest == config.digest


def test_trial_component_identity_deltas_are_owned_by_changed_inputs(
    tmp_path: Path,
) -> None:
    source_path = _write_trial_module(tmp_path)
    baseline_source = source_path.read_text(encoding="utf-8")

    def compile_variant(old: str | None = None, new: str | None = None):
        source = baseline_source if old is None else baseline_source.replace(old, new, 1)
        source_path.write_text(source, encoding="utf-8")
        node = _trial_node(_compile_trial_source(source_path, workspace=tmp_path))
        return node.execution_config.trial, node.execution_config

    baseline, baseline_step = compile_variant()
    arm_changed, arm_step = compile_variant(COMMIT_A, "1123456789abcdef" + COMMIT_A[16:])
    evaluation_changed, evaluation_step = compile_variant("0.10", "0.11")
    budget_changed, budget_step = compile_variant("900000", "800000")

    assert {
        baseline.site_digest,
        arm_changed.site_digest,
        evaluation_changed.site_digest,
        budget_changed.site_digest,
    } == {baseline.site_digest}
    assert {
        baseline.result_digest,
        arm_changed.result_digest,
        evaluation_changed.result_digest,
        budget_changed.result_digest,
    } == {baseline.result_digest}

    assert arm_changed.arms_digest != baseline.arms_digest
    assert arm_changed.arms[0].run_ref.digest != baseline.arms[0].run_ref.digest
    assert arm_changed.arms[1].run_ref.digest == baseline.arms[1].run_ref.digest
    assert arm_changed.evaluation_digest == baseline.evaluation_digest
    assert arm_changed.budget_digest == baseline.budget_digest

    assert evaluation_changed.arms_digest == baseline.arms_digest
    assert evaluation_changed.evaluation_digest != baseline.evaluation_digest
    assert evaluation_changed.budget_digest == baseline.budget_digest

    assert budget_changed.arms_digest == baseline.arms_digest
    assert budget_changed.evaluation_digest == baseline.evaluation_digest
    assert budget_changed.budget_digest != baseline.budget_digest

    for changed, changed_step in (
        (arm_changed, arm_step),
        (evaluation_changed, evaluation_step),
        (budget_changed, budget_step),
    ):
        assert changed.digest != baseline.digest
        assert (
            derive_unbound_trial_step_config(changed).step_config_digest
            != derive_unbound_trial_step_config(baseline).step_config_digest
        )
        assert changed_step.step_config_digest != baseline_step.step_config_digest


def test_trial_static_config_decoder_rejects_noncanonical_and_forged_bytes(
    tmp_path: Path,
) -> None:
    _, result = _build_trial(tmp_path)
    config = _trial_node(result).execution_config.trial
    canonical = encode_trial_static_config(config)

    decoded = decode_trial_static_config(canonical)
    assert decoded == config
    assert encode_trial_static_config(decoded) == canonical

    def extra_field(row):
        row["unexpected"] = True

    def missing_field(row):
        row.pop("budget")

    def invalid_range(row):
        row["reps"] = 0

    def forged_arms_digest(row):
        row["arms_digest"] = "sha256:" + "0" * 64

    def forged_result_digest(row):
        row["result_digest"] = "sha256:" + "0" * 64

    def invalid_observation(row):
        row["evaluation"]["observation_include"] = ["unknown_evidence"]

    for mutate in (
        extra_field,
        missing_field,
        invalid_range,
        forged_arms_digest,
        forged_result_digest,
        invalid_observation,
    ):
        forged = deepcopy(config.record)
        mutate(forged)
        forged_bytes = json.dumps(
            forged,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        with pytest.raises((TypeError, ValueError)):
            decode_trial_static_config(forged_bytes)

    with pytest.raises(ValueError, match="non-finite"):
        decode_trial_static_config(
            canonical.replace(b'"min_abs_improvement":0.1', b'"min_abs_improvement":NaN')
        )
    with pytest.raises(ValueError, match="not canonical"):
        decode_trial_static_config(b" " + canonical)


def test_trial_static_config_decoder_accepts_matching_target_2_26(
    tmp_path: Path,
) -> None:
    """A canonical 2.26 config with matching arm targets decodes round-trip."""

    source_path = _write_trial_module(tmp_path)
    source_path.write_text(
        source_path.read_text(encoding="utf-8").replace(
            '(:target-dsl "2.25")',
            '(:target-dsl "2.26")',
            1,
        ),
        encoding="utf-8",
    )
    result = _compile_trial_source(source_path, workspace=tmp_path)
    config = _trial_node(result).execution_config.trial

    assert config.target_dsl_version == "2.26"
    assert all(arm.run_ref.target_dsl_version == "2.26" for arm in config.arms)

    canonical = encode_trial_static_config(config)
    decoded = decode_trial_static_config(canonical)
    assert decoded == config
    assert decoded.target_dsl_version == "2.26"
    assert encode_trial_static_config(decoded) == canonical


def test_trial_static_config_decoder_rejects_unsupported_2_27(
    tmp_path: Path,
) -> None:
    """The decoder rejects a target above the admitted catalog (2.27)."""

    _, result = _build_trial(tmp_path)
    config = _trial_node(result).execution_config.trial

    forged = deepcopy(config.record)
    forged["target_dsl_version"] = "2.27"
    forged_bytes = json.dumps(
        forged,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    with pytest.raises(ValueError, match="target DSL"):
        decode_trial_static_config(forged_bytes)


def test_trial_static_config_decoder_rejects_mixed_parent_and_arm_targets(
    tmp_path: Path,
) -> None:
    """The decoder requires the parent target to equal every arm target."""

    _, result = _build_trial(tmp_path)
    config = _trial_node(result).execution_config.trial
    assert config.target_dsl_version == "2.25"

    forged = deepcopy(config.record)
    forged["target_dsl_version"] = "2.26"
    forged_bytes = json.dumps(
        forged,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    with pytest.raises(ValueError, match="match"):
        decode_trial_static_config(forged_bytes)


def test_persisted_trial_rejects_tampered_static_config(
    tmp_path: Path,
) -> None:
    _, result = _build_trial(tmp_path)
    payload = json.loads(
        result.artifact_paths["persisted_workflow_surface"].read_text(
            encoding="utf-8"
        )
    )
    entry = payload["nodes"][payload["entry_workflow"]]
    trial_step = next(
        step
        for step in entry["steps"]
        if step["kind"] == "trial"
    )
    trial_step["trial"]["arms_digest"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="trial_static_config_persistence_mismatch"):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(payload)
        )


@pytest.mark.parametrize(
    "older_schema",
    [
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA,
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V2,
        PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V3,
    ],
)
def test_trial_persisted_carriage_is_rejected_from_frozen_older_schemas(
    tmp_path: Path,
    older_schema: str,
) -> None:
    _, result = _build_trial(tmp_path)
    payload = json.loads(
        result.artifact_paths["persisted_workflow_surface"].read_text(
            encoding="utf-8"
        )
    )
    payload["schema_version"] = older_schema

    with pytest.raises(ValueError, match="trial_static_config_persistence_mismatch"):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(payload)
        )
