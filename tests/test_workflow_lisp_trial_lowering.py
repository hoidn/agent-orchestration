from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import fields
from pathlib import Path

import pytest

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_output_bundle,
)
from orchestrator.workflow.persisted_surface import PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA, PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V2, PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA_V3, canonical_persisted_surface_bytes, decode_persisted_workflow_surface_graph
from orchestrator.workflow.surface_ast import (
    SurfaceStep,
    SurfaceStepKind,
    TrialSurfaceStep,
)
from orchestrator.workflow.trial.config import (
    decode_trial_static_config,
    encode_trial_static_config,
)


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

    config = _historical_trial_config()
    trial_step = TrialSurfaceStep("Trial", "trial", SurfaceStepKind.TRIAL, trial=config)
    assert type(trial_step) is TrialSurfaceStep
    assert "trial" in {field.name for field in fields(TrialSurfaceStep)}
    assert trial_step.trial.digest == config.digest


def _compiled_trial_output_bundle(tmp_path: Path) -> dict[str, object]:
    from orchestrator.workflow_lisp.trial_result_contract import derive_trial_output_bundle_fields
    return {"path": "artifacts/trials/trial-result.json",
            "fields": derive_trial_output_bundle_fields(_historical_trial_contract())}


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






def test_trial_static_config_decoder_rejects_noncanonical_and_forged_bytes(
    tmp_path: Path,
) -> None:
    config = _historical_trial_config()
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


def test_trial_static_config_decoder_accepts_matching_current_target(
    tmp_path: Path,
) -> None:
    """A canonical current config with matching arm targets decodes round-trip."""

    config = _historical_trial_config(target="2.36")

    assert config.target_dsl_version == "2.36"
    assert all(arm.run_ref.target_dsl_version == "2.36" for arm in config.arms)

    canonical = encode_trial_static_config(config)
    decoded = decode_trial_static_config(canonical)
    assert decoded == config
    assert decoded.target_dsl_version == "2.36"
    assert encode_trial_static_config(decoded) == canonical


def test_trial_static_config_decoder_rejects_unsupported_target(
    tmp_path: Path,
) -> None:
    """The decoder rejects a target above the admitted catalog."""

    config = _historical_trial_config()

    forged = deepcopy(config.record)
    forged["target_dsl_version"] = "9.99"
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

    config = _historical_trial_config()
    assert config.target_dsl_version == "2.35"

    forged = deepcopy(config.record)
    forged["target_dsl_version"] = "2.36"
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
    payload = _historical_trial_wire_graph()
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
    payload = _historical_trial_wire_graph()
    payload["schema_version"] = older_schema

    with pytest.raises(ValueError, match="trial_static_config_persistence_mismatch"):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(payload)
        )




def _historical_trial_contract():
    from tests.test_workflow_lisp_trial import _type_env
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
    from orchestrator.workflow_lisp.trial_result_contract import build_trial_generated_types, derive_trial_result_contract
    env = _type_env()
    generated = build_trial_generated_types(value_type=PrimitiveTypeRef("String"),
        site_digest="1" * 64, type_env=env)
    return derive_trial_result_contract(generated.result_type, type_env=env)


def _historical_trial_config(*, target="2.35"):
    """Exact shared static authority from literal reader inputs; never compile or execute."""
    from tests.test_workflow_run_ref_config import _config
    from orchestrator.workflow.trial.config import TrialArmStaticConfig, build_trial_static_config
    contract = _historical_trial_contract()
    arm = _config(value_descriptor={"kind": "primitive", "name": "String"},
        inputs=(), target_dsl_version=target)
    config = build_trial_static_config(
        compiler_runtime_identity_digest="sha256:" + "f" * 64, site_digest="1" * 64,
        arms=(TrialArmStaticConfig("direct", arm), TrialArmStaticConfig("orc", arm)),
        reps=2, max_concurrency=2, result_descriptor=contract.descriptor, result_digest=contract.digest,
        evaluation={"checks": [], "provider": "test-provider", "rubric_asset": "rubrics/trial.md",
            "evidence_confidentiality": "same_trust_boundary", "max_item_bytes": 4096, "max_packet_bytes": 8192,
            "observation_include": ["validated_result"], "diff_cap_bytes": 4096, "reveal_provider_identity": False,
            "aggregation_mode": "independent_rubric", "rep_combine": "median", "tie": "authored_order",
            "min_abs_improvement": 0.1, "max_cost_ratio": 1.5, "min_cost_reduction": 0.2,
            "count_failures_as_outcomes": True},
        budget={"arm_timeout_ms": 900000, "trial_timeout_ms": 3600000,
            "max_evaluator_attempts": 4, "max_evaluator_concurrency": 2}, target_dsl_version=target,
    )
    return decode_trial_static_config(encode_trial_static_config(config))


def _historical_trial_wire_graph():
    from tests.test_workflow_lisp_build_artifacts import _historical_surface_template, _synthetic_surface_bundle
    from orchestrator.workflow.persisted_surface import serialize_persisted_workflow_surface_graph
    step = TrialSurfaceStep("Trial", "trial", SurfaceStepKind.TRIAL, trial=_historical_trial_config())
    graph = _synthetic_surface_bundle(_historical_surface_template(target="2.35"),
        "historical::trial", steps=(step,))
    return serialize_persisted_workflow_surface_graph(graph)
