"""Compiler-owned monomorphic result contracts for target-2.25 trials."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor

from .definitions import PathDef, RecordDef, RecordField, UnionDef, UnionVariant
from .normalized_type_descriptor import (
    compiler_normalized_type_descriptor,
    validate_compiler_normalized_type_descriptor,
)
from .spans import SourcePosition, SourceSpan
from .type_env import (
    ListTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
)
from .typecheck_run_ref import compiler_run_ref_fixed_types


TRIAL_RESULT_CONTRACT_SCHEMA = "workflow_lisp.trial_result_contract.v1"
TRIAL_FIXED_TYPE_NAMES = (
    "TrialFailure",
    "TrialCheckAuthority",
    "TrialCheckStatus",
    "TrialRepetitionOutcome",
    "TrialRepetitionVerdict",
    "TrialAggregateScore",
    "TrialTokenUsage",
    "TrialCost",
    "TrialBudgetAccounting",
    "TrialVerdict",
    "TrialVerdictPath",
)
_GENERATED_RESULT_NAME = re.compile(r"TrialResult\$[0-9a-f]{16}\Z")
_COMPILER_SPAN = SourceSpan(
    start=SourcePosition(
        path="<compiler:trial-types>", line=1, column=1, offset=0
    ),
    end=SourcePosition(
        path="<compiler:trial-types>", line=1, column=1, offset=0
    ),
)


def _record_type(
    name: str,
    fields: tuple[tuple[str, TypeRef], ...],
) -> RecordTypeRef:
    return RecordTypeRef(
        name=name,
        definition=RecordDef(
            name=name,
            fields=tuple(
                RecordField(name=field_name, type_name=field_type.name, span=_COMPILER_SPAN)
                for field_name, field_type in fields
            ),
            span=_COMPILER_SPAN,
        ),
        field_types=dict(fields),
    )


def _union_type(
    name: str,
    variants: tuple[tuple[str, tuple[tuple[str, TypeRef], ...]], ...],
) -> UnionTypeRef:
    return UnionTypeRef(
        name=name,
        definition=UnionDef(
            name=name,
            variants=tuple(
                UnionVariant(
                    name=variant_name,
                    fields=tuple(
                        RecordField(
                            name=field_name,
                            type_name=field_type.name,
                            span=_COMPILER_SPAN,
                        )
                        for field_name, field_type in fields
                    ),
                    span=_COMPILER_SPAN,
                )
                for variant_name, fields in variants
            ),
            span=_COMPILER_SPAN,
        ),
        variant_field_types={
            variant_name: dict(fields) for variant_name, fields in variants
        },
    )


@dataclass(frozen=True)
class TrialGeneratedTypes:
    """Exact fixed and site-generated type vector for one trial."""

    result_type: RecordTypeRef
    outcome_type: UnionTypeRef
    value_type: TypeRef
    compiler_owned_types: tuple[tuple[str, TypeRef], ...]


def build_trial_generated_types(
    *,
    value_type: TypeRef,
    site_digest: str,
    type_env,
) -> TrialGeneratedTypes:
    """Build the exact monomorphic result/union/path contracts for one site."""

    if not isinstance(site_digest, str) or re.fullmatch(r"[0-9a-f]{64}", site_digest) is None:
        raise ValueError("trial site digest must be 64 lowercase hexadecimal characters")
    suffix = site_digest[:16]

    def primitive(name: str) -> PrimitiveTypeRef:
        resolved = type_env._type_refs.get(name)
        if type(resolved) is not PrimitiveTypeRef or resolved.allowed_values:
            raise ValueError(f"trial compiler contract requires primitive {name!r}")
        return resolved

    string_type = primitive("String")
    int_type = primitive("Int")
    float_type = primitive("Float")
    bool_type = primitive("Bool")
    value_top = primitive("Value")
    run_id_type = primitive("RunId")
    run_ref_fixed = dict(compiler_run_ref_fixed_types(type_env))

    failure = _record_type(
        "TrialFailure",
        (
            ("code", string_type),
            ("phase", string_type),
            ("retryable", bool_type),
            ("secondary_causes", ListTypeRef("List[Value]", value_top)),
        ),
    )
    check_authority = PrimitiveTypeRef(
        "TrialCheckAuthority",
        ("correctness", "invariant"),
    )
    check_status = PrimitiveTypeRef(
        "TrialCheckStatus",
        ("COMPLETED", "TIMED_OUT", "LAUNCH_FAILED"),
    )
    check_result = _record_type(
        f"TrialCheckResult${suffix}",
        (
            ("check_id", string_type),
            ("authority", check_authority),
            ("required", bool_type),
            ("status", check_status),
            ("exit_code", OptionalTypeRef("Optional[Int]", int_type)),
            ("duration_ms", int_type),
            ("output_digest", string_type),
            ("output_bytes", string_type),
        ),
    )
    check_results = ListTypeRef(f"List[{check_result.name}]", check_result)
    partial_fact = _union_type(
        f"PartialTrialFact${suffix}",
        (
            (
                "WorkspaceDelta",
                (("workspace_delta", run_ref_fixed["WorkspaceDelta"]),),
            ),
            (
                "RunAccounting",
                (("accounting", run_ref_fixed["RunRefAccounting"]),),
            ),
            ("CheckResults", (("check_results", check_results),)),
            ("EvaluationLabel", (("evaluation_label", string_type),)),
            ("PacketIdentity", (("packet_identity", string_type),)),
            ("ScorerIdentity", (("scorer_identity", string_type),)),
            ("Score", (("score", float_type),)),
            ("ChildRunId", (("child_run_id", run_id_type),)),
            ("AttemptOrdinal", (("attempt_ordinal", int_type),)),
        ),
    )
    partial_evidence = _record_type(
        f"PartialTrialEvidence${suffix}",
        (
            (
                "facts",
                ListTypeRef(f"List[{partial_fact.name}]", partial_fact),
            ),
        ),
    )
    repetition_outcome = PrimitiveTypeRef(
        "TrialRepetitionOutcome",
        ("COMPLETED", "FAILED"),
    )
    repetition_verdict = _record_type(
        "TrialRepetitionVerdict",
        (
            ("arm_id", string_type),
            ("rep", int_type),
            ("outcome", repetition_outcome),
            ("score", OptionalTypeRef("Optional[Float]", float_type)),
        ),
    )
    aggregate_score = _record_type(
        "TrialAggregateScore",
        (
            ("arm_id", string_type),
            ("score", OptionalTypeRef("Optional[Float]", float_type)),
            ("completed_count", int_type),
            ("failed_count", int_type),
        ),
    )
    token_usage = _union_type(
        "TrialTokenUsage",
        (
            (
                "KNOWN",
                (
                    ("prompt_tokens", int_type),
                    ("completion_tokens", int_type),
                    ("total_tokens", int_type),
                ),
            ),
            ("UNKNOWN", ()),
        ),
    )
    cost = _union_type(
        "TrialCost",
        (
            (
                "KNOWN",
                (
                    ("amount", float_type),
                    ("currency", string_type),
                ),
            ),
            ("UNKNOWN", ()),
        ),
    )
    budget_accounting = _record_type(
        "TrialBudgetAccounting",
        (
            ("cell_count", int_type),
            ("completed_count", int_type),
            ("failed_count", int_type),
            ("child_attempts", int_type),
            ("evaluator_attempts", int_type),
            ("elapsed_ms", int_type),
            ("token_usage", token_usage),
            ("cost", cost),
        ),
    )
    verdict = _record_type(
        "TrialVerdict",
        (
            ("authored_arm_order", ListTypeRef("List[String]", string_type)),
            (
                "per_repetition",
                ListTypeRef(
                    f"List[{repetition_verdict.name}]",
                    repetition_verdict,
                ),
            ),
            (
                "aggregate_scores",
                ListTypeRef(f"List[{aggregate_score.name}]", aggregate_score),
            ),
            ("ranking", ListTypeRef("List[String]", string_type)),
            ("selected_arm", OptionalTypeRef("Optional[String]", string_type)),
            ("success_rule_disposition", string_type),
            ("budget_accounting", budget_accounting),
        ),
    )
    verdict_path = PathTypeRef(
        name="TrialVerdictPath",
        definition=PathDef(
            name="TrialVerdictPath",
            kind="relpath",
            under="artifacts/trials",
            must_exist=True,
            span=_COMPILER_SPAN,
        ),
    )
    completed_evidence = _record_type(
        f"CompletedTrialEvidence${suffix}",
        (
            ("workspace_delta", run_ref_fixed["WorkspaceDelta"]),
            ("accounting", run_ref_fixed["RunRefAccounting"]),
            ("check_results", check_results),
            ("evaluation_label", string_type),
            ("packet_identity", string_type),
            ("scorer_identity", string_type),
            ("score", float_type),
            ("child_run_id", run_id_type),
            ("attempt_ordinal", int_type),
        ),
    )
    outcome = _union_type(
        f"TrialArmOutcome${suffix}",
        (
            (
                "Completed",
                (
                    ("arm_id", string_type),
                    ("rep", int_type),
                    ("value", value_type),
                    ("evidence", completed_evidence),
                ),
            ),
            (
                "Failed",
                (
                    ("arm_id", string_type),
                    ("rep", int_type),
                    ("failure", failure),
                    ("evidence", partial_evidence),
                ),
            ),
        ),
    )
    result = _record_type(
        f"TrialResult${suffix}",
        (
            ("outcomes", ListTypeRef(f"List[{outcome.name}]", outcome)),
            ("verdict", verdict),
            ("verdict_artifact", verdict_path),
        ),
    )
    owned = (
        *tuple(run_ref_fixed.items()),
        (failure.name, failure),
        (check_authority.name, check_authority),
        (check_status.name, check_status),
        (check_result.name, check_result),
        (partial_fact.name, partial_fact),
        (partial_evidence.name, partial_evidence),
        (repetition_outcome.name, repetition_outcome),
        (repetition_verdict.name, repetition_verdict),
        (aggregate_score.name, aggregate_score),
        (token_usage.name, token_usage),
        (cost.name, cost),
        (budget_accounting.name, budget_accounting),
        (verdict.name, verdict),
        (verdict_path.name, verdict_path),
        (completed_evidence.name, completed_evidence),
        (outcome.name, outcome),
        (result.name, result),
    )
    return TrialGeneratedTypes(
        result_type=result,
        outcome_type=outcome,
        value_type=value_type,
        compiler_owned_types=owned,
    )


@dataclass(frozen=True, init=False)
class GeneratedTrialResultContract:
    """Content-addressed normalized contract for one generated trial result."""

    _descriptor_json: bytes = field(repr=False)
    digest: str
    type_ref: RecordTypeRef

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "GeneratedTrialResultContract must be created by derive_trial_result_contract"
        )

    @property
    def descriptor(self) -> dict[str, Any]:
        return json.loads(self._descriptor_json)


def derive_trial_result_contract(
    result_type_ref: RecordTypeRef,
    *,
    type_env,
) -> GeneratedTrialResultContract:
    """Derive and validate one exact compiler-owned trial result contract."""

    if not isinstance(result_type_ref, RecordTypeRef):
        raise ValueError("trial result contract requires a record type")
    if _GENERATED_RESULT_NAME.fullmatch(result_type_ref.name) is None:
        raise ValueError("trial result contract requires a generated TrialResult$ type")
    expected_fields = ("outcomes", "verdict", "verdict_artifact")
    if tuple(result_type_ref.field_types) != expected_fields:
        raise ValueError("trial result fields must be outcomes, verdict, verdict_artifact")
    outcomes = result_type_ref.field_types["outcomes"]
    if not isinstance(outcomes, ListTypeRef) or not isinstance(
        outcomes.item_type_ref, UnionTypeRef
    ):
        raise ValueError("trial outcomes must use the generated arm-outcome union")
    outcome = outcomes.item_type_ref
    if tuple(outcome.variant_field_types) != ("Completed", "Failed"):
        raise ValueError("trial outcome variants must be exactly Completed and Failed")
    completed = outcome.variant_field_types["Completed"]
    if tuple(completed) != ("arm_id", "rep", "value", "evidence"):
        raise ValueError("trial completed outcome fields are malformed")
    suffix = result_type_ref.name.removeprefix("TrialResult$")
    expected = build_trial_generated_types(
        value_type=completed["value"],
        site_digest=f"{suffix}{'0' * 48}",
        type_env=type_env,
    )
    from .typecheck_run_ref import _type_identity

    if _type_identity(result_type_ref) != _type_identity(expected.result_type):
        raise ValueError("trial verdict artifact or generated result schema is invalid")
    envelope = compiler_normalized_type_descriptor(
        result_type_ref,
        type_env=type_env,
    )
    validate_compiler_normalized_type_descriptor(
        envelope,
        context="trial_result_contract.envelope",
    )
    transport_schema_for_descriptor(
        envelope,
        allow_nested_structures=True,
    )
    descriptor = {"schema": TRIAL_RESULT_CONTRACT_SCHEMA, "envelope": envelope}
    contract = object.__new__(GeneratedTrialResultContract)
    object.__setattr__(contract, "_descriptor_json", canonical_json_bytes(descriptor))
    object.__setattr__(contract, "digest", canonical_sha256(descriptor))
    object.__setattr__(contract, "type_ref", result_type_ref)
    return contract


def derive_trial_output_bundle_fields(
    contract: GeneratedTrialResultContract,
) -> list[dict[str, Any]]:
    """Project the exact generated trial envelope into bundle fields."""

    if not isinstance(contract, GeneratedTrialResultContract):
        raise TypeError("trial output bundle fields require a generated contract")
    descriptor = contract.descriptor
    if canonical_sha256(descriptor) != contract.digest:
        raise ValueError("trial result contract digest is invalid")
    envelope = descriptor.get("envelope")
    if not isinstance(envelope, dict) or envelope.get("kind") != "record":
        raise ValueError("trial result envelope descriptor is malformed")
    fields: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    def visit(
        node: dict[str, Any],
        path: tuple[str, ...],
        *,
        projection: dict[str, Any] | None = None,
    ) -> None:
        if node.get("kind") == "record":
            raw_fields = node.get("fields")
            if not isinstance(raw_fields, list):
                raise ValueError("trial result record fields are malformed")
            for raw_field in raw_fields:
                if not isinstance(raw_field, dict):
                    raise ValueError("trial result record field is malformed")
                name = raw_field.get("name")
                field_type = raw_field.get("type")
                if not isinstance(name, str) or not isinstance(field_type, dict):
                    raise ValueError("trial result record field is malformed")
                visit(field_type, (*path, name), projection=projection)
            return
        if node.get("kind") == "union":
            if projection is not None:
                raise ValueError(
                    "trial result output projection cannot encode nested "
                    "conditional unions"
                )
            raw_variants = node.get("variants")
            if not isinstance(raw_variants, list) or not raw_variants:
                raise ValueError("trial result union variants are malformed")
            variant_names: list[str] = []
            payloads: dict[str, tuple[dict[str, Any], list[str]]] = {}
            for raw_variant in raw_variants:
                if not isinstance(raw_variant, dict):
                    raise ValueError("trial result union variant is malformed")
                variant_name = raw_variant.get("name")
                variant_fields = raw_variant.get("fields")
                if not isinstance(variant_name, str) or not isinstance(
                    variant_fields,
                    list,
                ):
                    raise ValueError("trial result union variant is malformed")
                if not variant_name or variant_name in variant_names:
                    raise ValueError("trial result union variant is malformed")
                variant_names.append(variant_name)
                variant_payload_names: set[str] = set()
                for raw_field in variant_fields:
                    if not isinstance(raw_field, dict):
                        raise ValueError("trial result union field is malformed")
                    name = raw_field.get("name")
                    field_type = raw_field.get("type")
                    if (
                        not isinstance(name, str)
                        or not name
                        or name in variant_payload_names
                        or not isinstance(field_type, dict)
                    ):
                        raise ValueError("trial result union field is malformed")
                    variant_payload_names.add(name)
                    previous = payloads.get(name)
                    if previous is None:
                        payloads[name] = (field_type, [variant_name])
                    else:
                        previous_type, active_variants = previous
                        if previous_type != field_type:
                            raise ValueError(
                                "trial result union payload schemas disagree"
                            )
                        active_variants.append(variant_name)
            discriminant_name = "__".join((*path, "variant"))
            union_output_group = "__".join(path)
            if not discriminant_name or not union_output_group:
                raise ValueError("trial result union output projection is malformed")
            common_projection = {
                "projection_class": "union_workflow_boundary",
                "return_kind": "union",
                "union_output_group": union_output_group,
                "discriminant_output": discriminant_name,
            }
            visit(
                {
                    "kind": "enum",
                    "name": f"{node.get('name', 'TrialUnion')}Variant",
                    "allowed": variant_names,
                },
                (*path, "variant"),
                projection={
                    **common_projection,
                    "field_role": "discriminant",
                    "active_variants": list(variant_names),
                },
            )
            for name, (field_type, active_variants) in payloads.items():
                visit(
                    field_type,
                    (*path, name),
                    projection={
                        **common_projection,
                        "field_role": (
                            "shared"
                            if active_variants == variant_names
                            else "variant"
                        ),
                        "active_variants": list(active_variants),
                    },
                )
            return
        name = "__".join(path)
        if not name or name in seen_names:
            raise ValueError("trial result output projection is ambiguous")
        seen_names.add(name)
        field = {
            "name": name,
            "json_pointer": "/"
            + "/".join(
                part.replace("~", "~0").replace("/", "~1")
                for part in path
            ),
            **transport_schema_for_descriptor(
                node,
                allow_nested_structures=True,
            ),
        }
        if projection is not None:
            field["projection"] = projection
        fields.append(field)

    visit(envelope, ())
    if not fields:
        raise ValueError("trial result output projection is empty")
    return fields
