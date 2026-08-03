"""Controller-owned ES hard findings and primary-outcome override."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, NoReturn

from . import f1_evaluator


PRIMARY_OUTCOMES = ("RICH", "DIRECT", "TIE", "INDETERMINATE")
HARD_DISPOSITION_PROOF_SCHEMA = "es.hard_disposition_proof.v1"
HARD_PROOF_AUTHORITY_SCHEMA = "es.hard_proof_authority.v1"

_PROOF_DISPOSITIONS = {
    "ORACLE_CONTRADICTION": "ORACLE_DEFECT",
    "CONFLICTING_REQUIREMENTS": "SPEC_AMBIGUITY",
    "TREATMENT_LOCAL_INFRASTRUCTURE": "INFRASTRUCTURE",
}
_PROOF_FIELDS = frozenset(
    {
        "schema_version",
        "proof_kind",
        "candidate_id",
        "clause_id",
        "observation_digest",
        "evidence_digest",
        "control_digests",
        "requirement_digests",
        "treatment_local",
        "evaluator_identity_digest",
        "task_identity_digest",
        "fixture_identity_digest",
    }
)
_PROOF_AUTHORITY_FIELDS = frozenset(
    {
        "schema_version",
        "proof_kind",
        "candidate_id",
        "clause_id",
        "control_digests",
        "requirement_digests",
        "evaluator_identity_digest",
        "task_identity_digest",
        "fixture_identity_digest",
    }
)
_OPAQUE_LABEL_RE = re.compile(r"opaque-[0-9a-f]{64}\Z")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class HardContractError(ValueError):
    """ES hard evidence or its primary override is not exact."""

    code = "es_hard_contract_invalid"


def _fail(message: str) -> NoReturn:
    raise HardContractError(message)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return f1_evaluator.canonical_json_bytes(value)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise HardContractError("ES hard-contract value is not canonical JSON") from exc


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_bytes(value))


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_digest(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(f"ES hard-contract {field_name} must be an exact SHA-256 digest")
    return value


def _require_digest_list(value: Any, *, field_name: str) -> list[str]:
    if not isinstance(value, list):
        _fail(f"ES hard-contract {field_name} must be an ordered digest list")
    digests = [
        _require_digest(item, field_name=field_name)
        for item in value
    ]
    if len(digests) != len(set(digests)):
        _fail(f"ES hard-contract {field_name} contains duplicate digests")
    return digests


def _preflight_observations(
    evaluator_observations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(evaluator_observations, (str, bytes)) or not isinstance(
        evaluator_observations, Sequence
    ):
        _fail("ES hard observations must be an ordered sequence")
    normalized = _canonical_copy(list(evaluator_observations))
    if not isinstance(normalized, list):
        _fail("ES hard observations must be an ordered sequence")
    clause_ids: list[str] = []
    for row in normalized:
        if not isinstance(row, dict) or set(row) != {
            "clause_id",
            "satisfied",
            "evidence",
            "details",
        }:
            _fail("ES hard observation field set is not exact")
        clause_id = row["clause_id"]
        if clause_id not in f1_evaluator.HARD_CLAUSE_IDS:
            _fail("ES hard observation names an unknown clause")
        clause_ids.append(clause_id)
        if type(row["satisfied"]) is not bool:
            _fail("ES hard observation satisfied value must be boolean")
        evidence = row["evidence"]
        if not isinstance(evidence, list) or not evidence:
            _fail("ES hard observation evidence must be a nonempty digest list")
        for item in evidence:
            _require_digest(item, field_name="observation evidence")
        if not isinstance(row["details"], str):
            _fail("ES hard observation details must be text")
    if tuple(clause_ids) != f1_evaluator.HARD_CLAUSE_IDS:
        _fail("ES hard observations must cover all ten clauses in exact order")
    return normalized


def _preflight_proofs(
    proof_rows: Sequence[Mapping[str, Any]],
    *,
    failed_clauses: frozenset[str],
) -> list[dict[str, Any]]:
    if isinstance(proof_rows, (str, bytes)) or not isinstance(proof_rows, Sequence):
        _fail("ES hard disposition proofs must be an ordered sequence")
    normalized = _canonical_copy(list(proof_rows))
    if not isinstance(normalized, list):
        _fail("ES hard disposition proofs must be an ordered sequence")
    for row in normalized:
        if not isinstance(row, dict) or set(row) != _PROOF_FIELDS:
            _fail("ES hard disposition proof field set is not exact")
        if row["schema_version"] != HARD_DISPOSITION_PROOF_SCHEMA:
            _fail("ES hard disposition proof schema is unsupported")
        if row["proof_kind"] not in _PROOF_DISPOSITIONS:
            _fail("ES hard disposition proof kind is unsupported")
        if row["clause_id"] not in failed_clauses:
            _fail("ES hard disposition proof does not name a false observation")
        if not isinstance(row["candidate_id"], str):
            _fail("ES hard disposition proof candidate label is invalid")
        for field_name in (
            "observation_digest",
            "evidence_digest",
            "evaluator_identity_digest",
            "task_identity_digest",
            "fixture_identity_digest",
        ):
            _require_digest(row[field_name], field_name=field_name)
        _require_digest_list(row["control_digests"], field_name="control_digests")
        _require_digest_list(
            row["requirement_digests"],
            field_name="requirement_digests",
        )
        if type(row["treatment_local"]) is not bool:
            _fail("ES hard disposition proof treatment_local must be boolean")
    return normalized


def _proof_digest_shape_matches(
    *,
    proof_kind: str,
    control_digests: Sequence[str],
    requirement_digests: Sequence[str],
    treatment_local: bool,
) -> bool:
    if proof_kind == "ORACLE_CONTRADICTION":
        return (
            bool(control_digests)
            and not requirement_digests
            and not treatment_local
        )
    if proof_kind == "CONFLICTING_REQUIREMENTS":
        return (
            not control_digests
            and len(requirement_digests) >= 2
            and not treatment_local
        )
    return bool(control_digests) and not requirement_digests and treatment_local


def _preflight_proof_authority(
    frozen_proof_authority: Sequence[Mapping[str, Any]],
    *,
    evaluator_identity_digest: str,
    task_identity_digest: str,
    fixture_identity_digest: str,
) -> list[dict[str, Any]]:
    if isinstance(frozen_proof_authority, (str, bytes)) or not isinstance(
        frozen_proof_authority, Sequence
    ):
        _fail("ES frozen proof authority must be an ordered sequence")
    normalized = _canonical_copy(list(frozen_proof_authority))
    if not isinstance(normalized, list):
        _fail("ES frozen proof authority must be an ordered sequence")
    row_digests: list[str] = []
    for row in normalized:
        if not isinstance(row, dict) or set(row) != _PROOF_AUTHORITY_FIELDS:
            _fail("ES frozen proof authority field set is not exact")
        if row["schema_version"] != HARD_PROOF_AUTHORITY_SCHEMA:
            _fail("ES frozen proof authority schema is unsupported")
        proof_kind = row["proof_kind"]
        if proof_kind not in _PROOF_DISPOSITIONS:
            _fail("ES frozen proof authority kind is unsupported")
        candidate_id = row["candidate_id"]
        if not isinstance(candidate_id, str) or _OPAQUE_LABEL_RE.fullmatch(
            candidate_id
        ) is None:
            _fail("ES frozen proof authority candidate label is invalid")
        if row["clause_id"] not in f1_evaluator.HARD_CLAUSE_IDS:
            _fail("ES frozen proof authority names an unknown clause")
        control_digests = _require_digest_list(
            row["control_digests"],
            field_name="authority control_digests",
        )
        requirement_digests = _require_digest_list(
            row["requirement_digests"],
            field_name="authority requirement_digests",
        )
        expected_treatment_local = proof_kind == "TREATMENT_LOCAL_INFRASTRUCTURE"
        if not _proof_digest_shape_matches(
            proof_kind=proof_kind,
            control_digests=control_digests,
            requirement_digests=requirement_digests,
            treatment_local=expected_treatment_local,
        ):
            _fail("ES frozen proof authority digest shape is inapplicable")
        for field_name, current_identity in (
            ("evaluator_identity_digest", evaluator_identity_digest),
            ("task_identity_digest", task_identity_digest),
            ("fixture_identity_digest", fixture_identity_digest),
        ):
            identity = _require_digest(row[field_name], field_name=field_name)
            if identity != current_identity:
                _fail("ES frozen proof authority identity is not current")
        row_digests.append(_digest(row))
    if len(row_digests) != len(set(row_digests)):
        _fail("ES frozen proof authority contains duplicate rows")
    return normalized


def _proof_matches_authority(
    proof: Mapping[str, Any],
    *,
    candidate_id: str,
    observation: Mapping[str, Any],
    frozen_proof_authority: Sequence[Mapping[str, Any]],
    evaluator_identity_digest: str,
    task_identity_digest: str,
    fixture_identity_digest: str,
) -> bool:
    common_matches = (
        proof["candidate_id"] == candidate_id
        and proof["clause_id"] == observation["clause_id"]
        and proof["observation_digest"] == _digest(observation)
        and proof["evidence_digest"] == _digest(observation["evidence"])
        and proof["evaluator_identity_digest"] == evaluator_identity_digest
        and proof["task_identity_digest"] == task_identity_digest
        and proof["fixture_identity_digest"] == fixture_identity_digest
    )
    if not common_matches:
        return False
    control_digests = proof["control_digests"]
    requirement_digests = proof["requirement_digests"]
    if not _proof_digest_shape_matches(
        proof_kind=proof["proof_kind"],
        control_digests=control_digests,
        requirement_digests=requirement_digests,
        treatment_local=proof["treatment_local"],
    ):
        return False
    return any(
        authority["candidate_id"] == candidate_id
        and authority["clause_id"] == observation["clause_id"]
        and authority["proof_kind"] == proof["proof_kind"]
        and authority["control_digests"] == control_digests
        and authority["requirement_digests"] == requirement_digests
        and authority["evaluator_identity_digest"] == evaluator_identity_digest
        and authority["task_identity_digest"] == task_identity_digest
        and authority["fixture_identity_digest"] == fixture_identity_digest
        for authority in frozen_proof_authority
    )


def _derived_dispositions(
    *,
    candidate_id: str,
    observations: list[dict[str, Any]],
    proofs: list[dict[str, Any]],
    frozen_proof_authority: list[dict[str, Any]],
    evaluator_identity_digest: str,
    task_identity_digest: str,
    fixture_identity_digest: str,
) -> dict[str, str]:
    false_by_clause = {
        row["clause_id"]: row for row in observations if not row["satisfied"]
    }
    proofs_by_clause = {
        clause_id: [row for row in proofs if row["clause_id"] == clause_id]
        for clause_id in false_by_clause
    }
    dispositions: dict[str, str] = {}
    for clause_id in f1_evaluator.HARD_CLAUSE_IDS:
        observation = false_by_clause.get(clause_id)
        if observation is None:
            continue
        candidates = proofs_by_clause[clause_id]
        if not candidates:
            dispositions[clause_id] = "PRODUCT_DEFECT"
        elif len(candidates) != 1:
            dispositions[clause_id] = "UNRESOLVED"
        else:
            proof = candidates[0]
            dispositions[clause_id] = (
                _PROOF_DISPOSITIONS[proof["proof_kind"]]
                if _proof_matches_authority(
                    proof,
                    candidate_id=candidate_id,
                    observation=observation,
                    frozen_proof_authority=frozen_proof_authority,
                    evaluator_identity_digest=evaluator_identity_digest,
                    task_identity_digest=task_identity_digest,
                    fixture_identity_digest=fixture_identity_digest,
                )
                else "UNRESOLVED"
            )
    return dispositions


@dataclass(frozen=True, slots=True)
class HardEvaluationFreeze:
    """Immutable controller-derived hard evaluation and trusted bindings."""

    candidate_id: str
    trusted_product_freeze_digest: str
    evaluator_identity_digest: str
    task_identity_digest: str
    fixture_identity_digest: str
    observation_set_digest: str
    proof_set_digest: str
    proof_authority_digest: str
    evaluation_digest: str
    digest: str
    product_blockers: tuple[str, ...]
    unresolved_blockers: tuple[str, ...]
    _evaluation_json: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if _OPAQUE_LABEL_RE.fullmatch(self.candidate_id) is None:
            _fail("ES hard evaluation candidate must be one opaque label")
        for field_name in (
            "trusted_product_freeze_digest",
            "evaluator_identity_digest",
            "task_identity_digest",
            "fixture_identity_digest",
            "observation_set_digest",
            "proof_set_digest",
            "proof_authority_digest",
            "evaluation_digest",
            "digest",
        ):
            _require_digest(getattr(self, field_name), field_name=field_name)
        try:
            evaluation = json.loads(self._evaluation_json)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HardContractError("ES hard evaluation bytes are invalid") from exc
        if _canonical_bytes(evaluation) != self._evaluation_json:
            _fail("ES hard evaluation bytes are not canonical")
        if _digest(evaluation) != self.evaluation_digest:
            _fail("ES hard evaluation digest disagrees")
        if not isinstance(evaluation, dict) or evaluation.get("candidate_id") != (
            self.candidate_id
        ):
            _fail("ES hard evaluation candidate binding disagrees")
        findings = evaluation.get("hard_findings")
        if not isinstance(findings, list):
            _fail("ES hard evaluation findings are invalid")
        disposition_by_clause = {
            row.get("clause_id"): row.get("disposition")
            for row in findings
            if isinstance(row, dict)
        }
        expected_product = tuple(
            clause_id
            for clause_id in f1_evaluator.HARD_CLAUSE_IDS
            if disposition_by_clause.get(clause_id) == "PRODUCT_DEFECT"
        )
        expected_unresolved = tuple(
            clause_id
            for clause_id in f1_evaluator.HARD_CLAUSE_IDS
            if disposition_by_clause.get(clause_id) == "UNRESOLVED"
        )
        if self.product_blockers != expected_product:
            _fail("ES hard evaluation product blockers disagree")
        if self.unresolved_blockers != expected_unresolved:
            _fail("ES hard evaluation unresolved blockers disagree")
        if self.digest != _digest(self._digest_record):
            _fail("ES hard evaluation freeze digest disagrees")

    @property
    def evaluation(self) -> dict[str, Any]:
        return json.loads(self._evaluation_json)

    @property
    def _digest_record(self) -> dict[str, Any]:
        return {
            "schema_version": "es.hard_evaluation_freeze.v1",
            "candidate_id": self.candidate_id,
            "trusted_product_freeze_digest": self.trusted_product_freeze_digest,
            "evaluator_identity_digest": self.evaluator_identity_digest,
            "task_identity_digest": self.task_identity_digest,
            "fixture_identity_digest": self.fixture_identity_digest,
            "observation_set_digest": self.observation_set_digest,
            "proof_set_digest": self.proof_set_digest,
            "proof_authority_digest": self.proof_authority_digest,
            "evaluation_digest": self.evaluation_digest,
            "product_blockers": list(self.product_blockers),
            "unresolved_blockers": list(self.unresolved_blockers),
        }

    @property
    def record(self) -> dict[str, Any]:
        return {**self._digest_record, "freeze_digest": self.digest}


def derive_hard_evaluation(
    *,
    candidate_claims: Mapping[str, Any],
    evaluator_observations: Sequence[Mapping[str, Any]],
    proof_rows: Sequence[Mapping[str, Any]],
    frozen_registry: set[str],
    trusted_product_freeze_digest: str,
    evaluator_identity_digest: str,
    task_identity_digest: str,
    fixture_identity_digest: str,
    frozen_proof_authority: Sequence[Mapping[str, Any]] = (),
) -> HardEvaluationFreeze:
    """Derive every disposition before calling the existing F1 evaluator."""

    if not isinstance(candidate_claims, Mapping):
        _fail("ES hard candidate claims must be an object")
    claims = _canonical_copy(dict(candidate_claims))
    candidate_id = claims.get("candidate_id")
    if not isinstance(candidate_id, str) or _OPAQUE_LABEL_RE.fullmatch(
        candidate_id
    ) is None:
        _fail("ES hard candidate_id must be one opaque E2 label")
    if type(frozen_registry) is not set or any(
        not isinstance(value, str) or not value for value in frozen_registry
    ):
        _fail("ES hard frozen registry must be an exact nonempty string set")
    product_freeze = _require_digest(
        trusted_product_freeze_digest,
        field_name="trusted_product_freeze_digest",
    )
    evaluator_identity = _require_digest(
        evaluator_identity_digest,
        field_name="evaluator_identity_digest",
    )
    task_identity = _require_digest(
        task_identity_digest,
        field_name="task_identity_digest",
    )
    fixture_identity = _require_digest(
        fixture_identity_digest,
        field_name="fixture_identity_digest",
    )
    proof_authority = _preflight_proof_authority(
        frozen_proof_authority,
        evaluator_identity_digest=evaluator_identity,
        task_identity_digest=task_identity,
        fixture_identity_digest=fixture_identity,
    )
    observations = _preflight_observations(evaluator_observations)
    failed_clauses = frozenset(
        row["clause_id"] for row in observations if not row["satisfied"]
    )
    proofs = _preflight_proofs(proof_rows, failed_clauses=failed_clauses)
    dispositions = _derived_dispositions(
        candidate_id=candidate_id,
        observations=observations,
        proofs=proofs,
        frozen_proof_authority=proof_authority,
        evaluator_identity_digest=evaluator_identity,
        task_identity_digest=task_identity,
        fixture_identity_digest=fixture_identity,
    )
    evaluation_observations: list[Mapping[str, Any]] = list(observations)
    try:
        evaluated = f1_evaluator.evaluate_observations(
            candidate_claims=claims,
            evaluator_observations=evaluation_observations,
            dispositions=dispositions,
            frozen_registry=set(frozen_registry),
        )
    except (TypeError, ValueError) as exc:
        raise HardContractError("ES hard evaluation refused its frozen inputs") from exc
    normalized_evaluation = _canonical_copy(evaluated)
    evaluation_json = _canonical_bytes(normalized_evaluation)
    disposition_by_clause = {
        finding["clause_id"]: finding["disposition"]
        for finding in normalized_evaluation["hard_findings"]
    }
    product_blockers = tuple(
        clause_id
        for clause_id in f1_evaluator.HARD_CLAUSE_IDS
        if disposition_by_clause.get(clause_id) == "PRODUCT_DEFECT"
    )
    unresolved_blockers = tuple(
        clause_id
        for clause_id in f1_evaluator.HARD_CLAUSE_IDS
        if disposition_by_clause.get(clause_id) == "UNRESOLVED"
    )
    values = {
        "candidate_id": candidate_id,
        "trusted_product_freeze_digest": product_freeze,
        "evaluator_identity_digest": evaluator_identity,
        "task_identity_digest": task_identity,
        "fixture_identity_digest": fixture_identity,
        "observation_set_digest": _digest(observations),
        "proof_set_digest": _digest(proofs),
        "proof_authority_digest": _digest(proof_authority),
        "evaluation_digest": _digest(normalized_evaluation),
        "product_blockers": product_blockers,
        "unresolved_blockers": unresolved_blockers,
        "_evaluation_json": evaluation_json,
    }
    digest_record = {
        "schema_version": "es.hard_evaluation_freeze.v1",
        **{
            key: list(value) if isinstance(value, tuple) else value
            for key, value in values.items()
            if key != "_evaluation_json"
        },
    }
    return HardEvaluationFreeze(**values, digest=_digest(digest_record))


@dataclass(frozen=True, slots=True)
class HardPrimaryOutcome:
    """Typed primary outcome with its complete blocker diagnostics."""

    raw_outcome: str
    derived_outcome: str
    rich_freeze_digest: str | None
    direct_freeze_digest: str | None
    rich_product_blockers: tuple[str, ...]
    direct_product_blockers: tuple[str, ...]
    rich_unresolved_blockers: tuple[str, ...]
    direct_unresolved_blockers: tuple[str, ...]
    comparable_product_blockers: tuple[str, ...]

    @property
    def record(self) -> dict[str, Any]:
        return {
            "schema_version": "es.hard_primary_outcome.v1",
            "raw_outcome": self.raw_outcome,
            "derived_outcome": self.derived_outcome,
            "rich_freeze_digest": self.rich_freeze_digest,
            "direct_freeze_digest": self.direct_freeze_digest,
            "rich_product_blockers": list(self.rich_product_blockers),
            "direct_product_blockers": list(self.direct_product_blockers),
            "rich_unresolved_blockers": list(self.rich_unresolved_blockers),
            "direct_unresolved_blockers": list(self.direct_unresolved_blockers),
            "comparable_product_blockers": list(
                self.comparable_product_blockers
            ),
        }


def derive_primary_outcome(
    *,
    raw_outcome: str,
    rich_freeze: HardEvaluationFreeze | None,
    direct_freeze: HardEvaluationFreeze | None,
) -> HardPrimaryOutcome:
    """Apply the locked missing-freeze and hard-blocker override order."""

    if type(raw_outcome) is not str or raw_outcome not in PRIMARY_OUTCOMES:
        _fail("ES raw primary outcome must be one exact typed outcome")
    for name, value in (("RICH", rich_freeze), ("DIRECT", direct_freeze)):
        if value is not None and type(value) is not HardEvaluationFreeze:
            _fail(f"ES {name} hard evidence must be an exact trusted freeze")
    if (
        rich_freeze is not None
        and direct_freeze is not None
        and rich_freeze.candidate_id == direct_freeze.candidate_id
    ):
        _fail("ES primary candidates must have distinct opaque labels")
    if rich_freeze is not None and direct_freeze is not None:
        rich_authority = (
            rich_freeze.evaluator_identity_digest,
            rich_freeze.task_identity_digest,
            rich_freeze.fixture_identity_digest,
            rich_freeze.proof_authority_digest,
        )
        direct_authority = (
            direct_freeze.evaluator_identity_digest,
            direct_freeze.task_identity_digest,
            direct_freeze.fixture_identity_digest,
            direct_freeze.proof_authority_digest,
        )
        if rich_authority != direct_authority:
            _fail("ES primary hard freezes do not share one frozen authority")

    rich_product = () if rich_freeze is None else rich_freeze.product_blockers
    direct_product = () if direct_freeze is None else direct_freeze.product_blockers
    rich_unresolved = (
        () if rich_freeze is None else rich_freeze.unresolved_blockers
    )
    direct_unresolved = (
        () if direct_freeze is None else direct_freeze.unresolved_blockers
    )
    comparable = tuple(
        clause_id
        for clause_id in f1_evaluator.HARD_CLAUSE_IDS
        if clause_id in rich_product and clause_id in direct_product
    )

    if rich_freeze is None or direct_freeze is None:
        derived = "INDETERMINATE"
    elif raw_outcome == "RICH" and (rich_product or rich_unresolved):
        derived = "INDETERMINATE"
    elif raw_outcome == "DIRECT" and (direct_product or direct_unresolved):
        derived = "INDETERMINATE"
    elif raw_outcome in {"RICH", "DIRECT"} and comparable:
        derived = "INDETERMINATE"
    else:
        derived = raw_outcome

    return HardPrimaryOutcome(
        raw_outcome=raw_outcome,
        derived_outcome=derived,
        rich_freeze_digest=None if rich_freeze is None else rich_freeze.digest,
        direct_freeze_digest=(
            None if direct_freeze is None else direct_freeze.digest
        ),
        rich_product_blockers=rich_product,
        direct_product_blockers=direct_product,
        rich_unresolved_blockers=rich_unresolved,
        direct_unresolved_blockers=direct_unresolved,
        comparable_product_blockers=comparable,
    )


__all__ = [
    "HARD_DISPOSITION_PROOF_SCHEMA",
    "HARD_PROOF_AUTHORITY_SCHEMA",
    "PRIMARY_OUTCOMES",
    "HardContractError",
    "HardEvaluationFreeze",
    "HardPrimaryOutcome",
    "derive_hard_evaluation",
    "derive_primary_outcome",
]
