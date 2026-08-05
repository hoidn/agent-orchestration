from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.experiments.es import task_package

FAILED_CLAUSE = "F1-H09-CONSTRUCTION-REBUILD-EQUALITY"
OTHER_FAILED_CLAUSE = "F1-H10-OWNERSHIP-BOUNDARY"
HARD_CLAUSE_IDS = (
    "F1-H01-FOCUSED-SUITES",
    "F1-H02-SCHEMA-CONFORMANCE",
    "F1-H03-BUILTIN-SIGNATURES",
    "F1-H04-ARTIFACT-ERA-COMPATIBILITY",
    "F1-H05-FULL-ARCHITECTURE-LIFECYCLE",
    "F1-H06-STRUCTURAL-ROUNDTRIP",
    "F1-H07-STRUCTURAL-IDENTITY-REJECTION",
    "F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY",
    FAILED_CLAUSE,
    OTHER_FAILED_CLAUSE,
)
RICH_LABEL = "opaque-" + "1" * 64
DIRECT_LABEL = "opaque-" + "2" * 64
PRODUCT_FREEZE_DIGEST = "sha256:" + "3" * 64
EVALUATOR_IDENTITY_DIGEST = "sha256:" + "4" * 64
TASK_IDENTITY_DIGEST = "sha256:" + "5" * 64
FIXTURE_IDENTITY_DIGEST = "sha256:" + "6" * 64


@pytest.fixture(scope="module")
def hard_contract() -> ModuleType:
    return importlib.import_module("scripts.experiments.es.hard_contract")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(
        (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()


def _candidate_claims(candidate_id: str) -> dict[str, Any]:
    construction_route = "ptycho_torch.generators.registry.resolve_generator"
    persisted_route = (
        "ptycho_torch.application_factory.build_ptychopinn_application"
    )

    def builtin(architecture_id: str) -> dict[str, Any]:
        return {
            "construction_route": construction_route,
            "persisted_rebuild_route": persisted_route,
            "public_id": architecture_id,
            "structural_fields": [
                {
                    "alternate_value": f"{architecture_id}-alternate",
                    "baseline_value": architecture_id,
                    "name": "architecture",
                }
            ],
        }

    return {
        "architecture_decision_path": "docs/architecture.md",
        "builtin_architectures": [
            builtin(architecture_id)
            for architecture_id in task_package.F1_BUILTIN_ARCHITECTURES
        ],
        "candidate_id": candidate_id,
        "candidate_witness": {
            "construction_route": construction_route,
            "persisted_rebuild_route": persisted_route,
            "public_id": "es_f1_witness",
            "structural_fields": [
                {
                    "alternate_value": 3,
                    "baseline_value": 2,
                    "name": "es_f1_depth",
                }
            ],
        },
        "claims": [
            {
                "clause_id": clause_id,
                "evidence_paths": ["tests/control.json"],
                "scope": "IMPLEMENTED",
            }
            for clause_id in task_package.F1_HARD_CLAUSE_IDS
        ],
        "extension_author_guide_path": "docs/extension-guide.md",
        "fixed_outputs": {
            "candidate_test_path": "tests/torch/test_es_f1_extension_boundary.py",
            "lifecycle_adapter_path": "scripts/es_f1_lifecycle_adapter.py",
        },
        "ownership": {
            "excludes": ["PHYSICS", "LOSS", "SCALING", "DATA_OWNERSHIP"],
            "owns": [
                "ARCHITECTURE_IDENTITY",
                "STRUCTURAL_CONFIGURATION",
                "CONSTRUCTION",
                "PERSISTENCE_MIGRATION",
            ],
        },
        "schema_version": "candidate_extension_evidence.v2",
    }


def _observations(*failed_clauses: str) -> list[dict[str, Any]]:
    failed = set(failed_clauses)
    return [
        {
            "clause_id": clause_id,
            "satisfied": clause_id not in failed,
            "evidence": [f"sha256:{index + 10:064x}"],
            "details": "controller observation",
        }
        for index, clause_id in enumerate(HARD_CLAUSE_IDS)
    ]


def _proof(
    *,
    kind: str,
    candidate_id: str,
    observation: dict[str, Any],
) -> dict[str, Any]:
    if kind == "ORACLE_CONTRADICTION":
        control_digests = ["sha256:" + "7" * 64]
        requirement_digests: list[str] = []
        treatment_local = False
    elif kind == "CONFLICTING_REQUIREMENTS":
        control_digests = []
        requirement_digests = [
            "sha256:" + "8" * 64,
            "sha256:" + "9" * 64,
        ]
        treatment_local = False
    elif kind == "TREATMENT_LOCAL_INFRASTRUCTURE":
        control_digests = ["sha256:" + "a" * 64]
        requirement_digests = []
        treatment_local = True
    else:
        raise AssertionError(f"unsupported test proof kind {kind}")
    return {
        "schema_version": "es.hard_disposition_proof.v1",
        "proof_kind": kind,
        "candidate_id": candidate_id,
        "clause_id": observation["clause_id"],
        "observation_digest": _digest(observation),
        "evidence_digest": _digest(observation["evidence"]),
        "control_digests": control_digests,
        "requirement_digests": requirement_digests,
        "treatment_local": treatment_local,
        "evaluator_identity_digest": EVALUATOR_IDENTITY_DIGEST,
        "task_identity_digest": TASK_IDENTITY_DIGEST,
        "fixture_identity_digest": FIXTURE_IDENTITY_DIGEST,
    }


def _proof_authority(
    *proofs: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for proof in proofs:
        row = {
            "schema_version": "es.hard_proof_authority.v1",
            "candidate_id": proof["candidate_id"],
            "clause_id": proof["clause_id"],
            "proof_kind": proof["proof_kind"],
            "control_digests": deepcopy(proof["control_digests"]),
            "requirement_digests": deepcopy(proof["requirement_digests"]),
            "evaluator_identity_digest": proof["evaluator_identity_digest"],
            "task_identity_digest": proof["task_identity_digest"],
            "fixture_identity_digest": proof["fixture_identity_digest"],
        }
        digest = _digest(row)
        if digest not in seen:
            rows.append(row)
            seen.add(digest)
    return rows


def _derive(
    hard_contract: ModuleType,
    candidate_id: str,
    *,
    failed_clauses: tuple[str, ...] = (),
    proof_rows: list[dict[str, Any]] | None = None,
    frozen_proof_authority: list[dict[str, Any]] | None = None,
) -> Any:
    authority = (
        _proof_authority(*(proof_rows or []))
        if frozen_proof_authority is None
        else frozen_proof_authority
    )
    return hard_contract.derive_hard_evaluation(
        candidate_claims=_candidate_claims(candidate_id),
        evaluator_observations=_observations(*failed_clauses),
        proof_rows=proof_rows or [],
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
        trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
        evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
        task_identity_digest=TASK_IDENTITY_DIGEST,
        fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
        frozen_proof_authority=authority,
    )


@pytest.mark.parametrize("mutation", ["evaluation-predecessor", "finding-predecessor"])
def test_hard_freeze_rejects_predecessor_and_mixed_inner_versions(
    hard_contract: ModuleType,
    mutation: str,
) -> None:
    freeze = _derive(
        hard_contract,
        RICH_LABEL,
        failed_clauses=(FAILED_CLAUSE,),
    )
    assert freeze.evaluation["schema_version"] == "es-f1-hard-evaluation.v2"
    assert {
        finding["schema_version"] for finding in freeze.evaluation["hard_findings"]
    } == {"es-f1-hard-finding.v2"}
    evaluation = deepcopy(freeze.evaluation)
    if mutation == "evaluation-predecessor":
        evaluation["schema_version"] = "es-f1-hard-evaluation.v1"
    else:
        evaluation["hard_findings"][0]["schema_version"] = "es-f1-hard-finding.v1"
    evaluation_digest = _digest(evaluation)
    digest_record = {
        **freeze.record,
        "evaluation_digest": evaluation_digest,
    }
    digest_record.pop("freeze_digest")
    with pytest.raises(hard_contract.HardContractError, match="schema"):
        hard_contract.HardEvaluationFreeze(
            candidate_id=freeze.candidate_id,
            trusted_product_freeze_digest=freeze.trusted_product_freeze_digest,
            evaluator_identity_digest=freeze.evaluator_identity_digest,
            task_identity_digest=freeze.task_identity_digest,
            fixture_identity_digest=freeze.fixture_identity_digest,
            observation_set_digest=freeze.observation_set_digest,
            proof_set_digest=freeze.proof_set_digest,
            proof_authority_digest=freeze.proof_authority_digest,
            evaluation_digest=evaluation_digest,
            digest=_digest(digest_record),
            product_blockers=freeze.product_blockers,
            unresolved_blockers=freeze.unresolved_blockers,
            _evaluation_json=hard_contract._canonical_bytes(evaluation),
        )
@pytest.mark.parametrize(
    ("proof_kind", "expected_disposition"),
    [
        (None, "PRODUCT_DEFECT"),
        ("ORACLE_CONTRADICTION", "ORACLE_DEFECT"),
        ("CONFLICTING_REQUIREMENTS", "SPEC_AMBIGUITY"),
        ("TREATMENT_LOCAL_INFRASTRUCTURE", "INFRASTRUCTURE"),
    ],
)
def test_controller_derives_default_and_exact_non_product_dispositions(
    hard_contract: ModuleType,
    proof_kind: str | None,
    expected_disposition: str,
) -> None:
    observations = _observations(FAILED_CLAUSE)
    rows = (
        []
        if proof_kind is None
        else [
            _proof(
                kind=proof_kind,
                candidate_id=RICH_LABEL,
                observation=next(
                    row for row in observations if row["clause_id"] == FAILED_CLAUSE
                ),
            )
        ]
    )

    freeze = hard_contract.derive_hard_evaluation(
        candidate_claims=_candidate_claims(RICH_LABEL),
        evaluator_observations=observations,
        proof_rows=rows,
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
        trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
        evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
        task_identity_digest=TASK_IDENTITY_DIGEST,
        fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
        frozen_proof_authority=_proof_authority(*rows),
    )

    assert [
        finding["disposition"] for finding in freeze.evaluation["hard_findings"]
    ] == [expected_disposition]
    assert freeze.product_blockers == (
        (FAILED_CLAUSE,) if expected_disposition == "PRODUCT_DEFECT" else ()
    )
    assert freeze.unresolved_blockers == ()


@pytest.mark.parametrize(
    "proof_kind",
    [
        "ORACLE_CONTRADICTION",
        "CONFLICTING_REQUIREMENTS",
        "TREATMENT_LOCAL_INFRASTRUCTURE",
    ],
)
def test_fabricated_well_formed_proof_digests_become_unresolved(
    hard_contract: ModuleType,
    proof_kind: str,
) -> None:
    observations = _observations(FAILED_CLAUSE)
    observation = next(
        row for row in observations if row["clause_id"] == FAILED_CLAUSE
    )
    proof = _proof(
        kind=proof_kind,
        candidate_id=RICH_LABEL,
        observation=observation,
    )
    authority = _proof_authority(proof)
    if proof_kind == "CONFLICTING_REQUIREMENTS":
        proof["requirement_digests"] = [
            "sha256:" + "b" * 64,
            "sha256:" + "c" * 64,
        ]
    else:
        proof["control_digests"] = ["sha256:" + "b" * 64]

    freeze = hard_contract.derive_hard_evaluation(
        candidate_claims=_candidate_claims(RICH_LABEL),
        evaluator_observations=observations,
        proof_rows=[proof],
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
        trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
        evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
        task_identity_digest=TASK_IDENTITY_DIGEST,
        fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
        frozen_proof_authority=authority,
    )

    assert freeze.product_blockers == ()
    assert freeze.unresolved_blockers == (FAILED_CLAUSE,)
    assert freeze.evaluation["hard_findings"][0]["disposition"] == "UNRESOLVED"


@pytest.mark.parametrize(
    "authority_mutation",
    ["candidate", "clause", "kind", "digest"],
)
def test_tampered_proof_authority_key_becomes_unresolved(
    hard_contract: ModuleType,
    authority_mutation: str,
) -> None:
    observations = _observations(FAILED_CLAUSE)
    observation = next(
        row for row in observations if row["clause_id"] == FAILED_CLAUSE
    )
    proof = _proof(
        kind="ORACLE_CONTRADICTION",
        candidate_id=RICH_LABEL,
        observation=observation,
    )
    authority = _proof_authority(proof)
    if authority_mutation == "candidate":
        authority[0]["candidate_id"] = DIRECT_LABEL
    elif authority_mutation == "clause":
        authority[0]["clause_id"] = OTHER_FAILED_CLAUSE
    elif authority_mutation == "kind":
        authority[0]["proof_kind"] = "TREATMENT_LOCAL_INFRASTRUCTURE"
    else:
        authority[0]["control_digests"] = ["sha256:" + "b" * 64]

    freeze = hard_contract.derive_hard_evaluation(
        candidate_claims=_candidate_claims(RICH_LABEL),
        evaluator_observations=observations,
        proof_rows=[proof],
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
        trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
        evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
        task_identity_digest=TASK_IDENTITY_DIGEST,
        fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
        frozen_proof_authority=authority,
    )

    assert freeze.product_blockers == ()
    assert freeze.unresolved_blockers == (FAILED_CLAUSE,)


def test_proof_authority_identity_must_match_current_controller_identity(
    hard_contract: ModuleType,
) -> None:
    observations = _observations(FAILED_CLAUSE)
    observation = next(
        row for row in observations if row["clause_id"] == FAILED_CLAUSE
    )
    proof = _proof(
        kind="ORACLE_CONTRADICTION",
        candidate_id=RICH_LABEL,
        observation=observation,
    )
    authority = _proof_authority(proof)
    authority[0]["task_identity_digest"] = "sha256:" + "b" * 64

    with pytest.raises(hard_contract.HardContractError):
        hard_contract.derive_hard_evaluation(
            candidate_claims=_candidate_claims(RICH_LABEL),
            evaluator_observations=observations,
            proof_rows=[proof],
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
            trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
            evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
            task_identity_digest=TASK_IDENTITY_DIGEST,
            fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
            frozen_proof_authority=authority,
        )


def test_hard_evaluation_binds_canonical_proof_authority_digest(
    hard_contract: ModuleType,
) -> None:
    observations = _observations(FAILED_CLAUSE)
    observation = next(
        row for row in observations if row["clause_id"] == FAILED_CLAUSE
    )
    proof = _proof(
        kind="ORACLE_CONTRADICTION",
        candidate_id=RICH_LABEL,
        observation=observation,
    )
    authority = _proof_authority(proof)
    expected_digest = _digest(authority)

    freeze = hard_contract.derive_hard_evaluation(
        candidate_claims=_candidate_claims(RICH_LABEL),
        evaluator_observations=observations,
        proof_rows=[proof],
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
        trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
        evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
        task_identity_digest=TASK_IDENTITY_DIGEST,
        fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
        frozen_proof_authority=authority,
    )
    authority[0]["control_digests"] = ["sha256:" + "b" * 64]

    assert freeze.proof_authority_digest == expected_digest
    assert freeze.record["proof_authority_digest"] == expected_digest


@pytest.mark.parametrize(
    "proof_mutation",
    [
        "observation_digest_mismatch",
        "evidence_digest_mismatch",
        "identity_mismatch",
        "oracle_without_control",
        "conflict_without_two_requirements",
        "infrastructure_not_treatment_local",
    ],
)
def test_missing_or_inexact_non_product_authority_becomes_unresolved(
    hard_contract: ModuleType,
    proof_mutation: str,
) -> None:
    observations = _observations(FAILED_CLAUSE)
    observation = next(
        row for row in observations if row["clause_id"] == FAILED_CLAUSE
    )
    kind = {
        "conflict_without_two_requirements": "CONFLICTING_REQUIREMENTS",
        "infrastructure_not_treatment_local": "TREATMENT_LOCAL_INFRASTRUCTURE",
    }.get(proof_mutation, "ORACLE_CONTRADICTION")
    proof = _proof(kind=kind, candidate_id=RICH_LABEL, observation=observation)
    authority = _proof_authority(proof)
    if proof_mutation == "observation_digest_mismatch":
        proof["observation_digest"] = "sha256:" + "b" * 64
    elif proof_mutation == "evidence_digest_mismatch":
        proof["evidence_digest"] = "sha256:" + "b" * 64
    elif proof_mutation == "identity_mismatch":
        proof["task_identity_digest"] = "sha256:" + "b" * 64
    elif proof_mutation == "oracle_without_control":
        proof["control_digests"] = []
    elif proof_mutation == "conflict_without_two_requirements":
        proof["requirement_digests"] = proof["requirement_digests"][:1]
    else:
        proof["treatment_local"] = False

    freeze = hard_contract.derive_hard_evaluation(
        candidate_claims=_candidate_claims(RICH_LABEL),
        evaluator_observations=observations,
        proof_rows=[proof],
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
        trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
        evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
        task_identity_digest=TASK_IDENTITY_DIGEST,
        fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
        frozen_proof_authority=authority,
    )

    assert freeze.product_blockers == ()
    assert freeze.unresolved_blockers == (FAILED_CLAUSE,)
    assert freeze.evaluation["hard_findings"][0]["disposition"] == "UNRESOLVED"


@pytest.mark.parametrize("proof_kinds", [("ORACLE_CONTRADICTION",) * 2, (
    "ORACLE_CONTRADICTION",
    "CONFLICTING_REQUIREMENTS",
)])
def test_multiple_or_conflicting_non_product_proofs_become_unresolved(
    hard_contract: ModuleType,
    proof_kinds: tuple[str, ...],
) -> None:
    observations = _observations(FAILED_CLAUSE)
    observation = next(
        row for row in observations if row["clause_id"] == FAILED_CLAUSE
    )
    rows = [
        _proof(kind=kind, candidate_id=RICH_LABEL, observation=observation)
        for kind in proof_kinds
    ]

    freeze = hard_contract.derive_hard_evaluation(
        candidate_claims=_candidate_claims(RICH_LABEL),
        evaluator_observations=observations,
        proof_rows=rows,
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
        trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
        evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
        task_identity_digest=TASK_IDENTITY_DIGEST,
        fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
        frozen_proof_authority=_proof_authority(*rows),
    )

    assert freeze.unresolved_blockers == (FAILED_CLAUSE,)


@pytest.mark.parametrize("authority_source", ["candidate", "proof"])
def test_candidate_or_provider_authored_disposition_is_rejected(
    hard_contract: ModuleType,
    authority_source: str,
) -> None:
    claims = _candidate_claims(RICH_LABEL)
    observations = _observations(FAILED_CLAUSE)
    proof_rows: list[dict[str, Any]] = []
    if authority_source == "candidate":
        claims["claims"][0]["disposition"] = "ORACLE_DEFECT"
    else:
        observation = next(
            row for row in observations if row["clause_id"] == FAILED_CLAUSE
        )
        proof = _proof(
            kind="ORACLE_CONTRADICTION",
            candidate_id=RICH_LABEL,
            observation=observation,
        )
        proof["disposition"] = "ORACLE_DEFECT"
        proof_rows.append(proof)

    with pytest.raises(hard_contract.HardContractError):
        hard_contract.derive_hard_evaluation(
            candidate_claims=claims,
            evaluator_observations=observations,
            proof_rows=proof_rows,
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
            trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
            evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
            task_identity_digest=TASK_IDENTITY_DIGEST,
            fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
        )


@pytest.mark.parametrize("coverage", ["missing", "duplicate", "unknown"])
def test_incomplete_or_malformed_clause_coverage_never_reaches_evaluator(
    hard_contract: ModuleType,
    coverage: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations = _observations()
    if coverage == "missing":
        observations.pop()
    elif coverage == "duplicate":
        observations[-1] = deepcopy(observations[0])
    else:
        observations[-1]["clause_id"] = "F1-H99-NOT-FROZEN"
    calls: list[dict[str, Any]] = []

    def forbidden_evaluation(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        raise AssertionError("evaluate_observations must not be called")

    monkeypatch.setattr(
        hard_contract.f1_evaluator,
        "evaluate_observations",
        forbidden_evaluation,
    )

    with pytest.raises(hard_contract.HardContractError):
        hard_contract.derive_hard_evaluation(
            candidate_claims=_candidate_claims(RICH_LABEL),
            evaluator_observations=observations,
            proof_rows=[],
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
            trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
            evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
            task_identity_digest=TASK_IDENTITY_DIGEST,
            fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
        )

    assert calls == []


def test_hard_evaluation_freezes_canonical_input_bytes(
    hard_contract: ModuleType,
) -> None:
    observations = _observations(FAILED_CLAUSE)
    freeze = hard_contract.derive_hard_evaluation(
        candidate_claims=_candidate_claims(RICH_LABEL),
        evaluator_observations=observations,
        proof_rows=[],
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
        trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
        evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
        task_identity_digest=TASK_IDENTITY_DIGEST,
        fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
    )
    original = freeze.evaluation

    observations[-2]["details"] = "mutated after freeze"
    exposed = freeze.evaluation
    exposed["hard_findings"].clear()

    assert freeze.evaluation == original
    with pytest.raises(FrozenInstanceError):
        freeze.candidate_id = DIRECT_LABEL  # type: ignore[misc]


@pytest.mark.parametrize(
    "raw_outcome",
    ["RICH", "DIRECT", "TIE", "INDETERMINATE"],
)
def test_healthy_trusted_freezes_retain_every_raw_primary_outcome(
    hard_contract: ModuleType,
    raw_outcome: str,
) -> None:
    result = hard_contract.derive_primary_outcome(
        raw_outcome=raw_outcome,
        rich_freeze=_derive(hard_contract, RICH_LABEL),
        direct_freeze=_derive(hard_contract, DIRECT_LABEL),
    )

    assert result.raw_outcome == raw_outcome
    assert result.derived_outcome == raw_outcome
    assert result.comparable_product_blockers == ()


@pytest.mark.parametrize(
    ("missing_side", "raw_outcome"),
    [
        (side, raw)
        for side in ("rich", "direct")
        for raw in ("RICH", "DIRECT", "TIE", "INDETERMINATE")
    ],
)
def test_missing_trusted_freeze_forces_indeterminate_before_other_rules(
    hard_contract: ModuleType,
    missing_side: str,
    raw_outcome: str,
) -> None:
    rich = (
        None if missing_side == "rich" else _derive(hard_contract, RICH_LABEL)
    )
    direct = (
        None if missing_side == "direct" else _derive(hard_contract, DIRECT_LABEL)
    )

    result = hard_contract.derive_primary_outcome(
        raw_outcome=raw_outcome,
        rich_freeze=rich,
        direct_freeze=direct,
    )

    assert result.derived_outcome == "INDETERMINATE"


@pytest.mark.parametrize(
    ("blocked_side", "disposition", "raw_outcome", "expected"),
    [
        (side, disposition, raw, expected)
        for side, raw, expected in (
            ("rich", "RICH", "INDETERMINATE"),
            ("rich", "DIRECT", "DIRECT"),
            ("rich", "TIE", "TIE"),
            ("rich", "INDETERMINATE", "INDETERMINATE"),
            ("direct", "RICH", "RICH"),
            ("direct", "DIRECT", "INDETERMINATE"),
            ("direct", "TIE", "TIE"),
            ("direct", "INDETERMINATE", "INDETERMINATE"),
        )
        for disposition in ("PRODUCT_DEFECT", "UNRESOLVED")
    ],
)
def test_one_sided_product_or_unresolved_blocker_only_blocks_that_winner(
    hard_contract: ModuleType,
    blocked_side: str,
    disposition: str,
    raw_outcome: str,
    expected: str,
) -> None:
    candidate_id = RICH_LABEL if blocked_side == "rich" else DIRECT_LABEL
    observations = _observations(FAILED_CLAUSE)
    proof_rows: list[dict[str, Any]] = []
    authority: list[dict[str, Any]] = []
    if disposition == "UNRESOLVED":
        observation = next(
            row for row in observations if row["clause_id"] == FAILED_CLAUSE
        )
        invalid_proof = _proof(
            kind="ORACLE_CONTRADICTION",
            candidate_id=candidate_id,
            observation=observation,
        )
        authority = _proof_authority(invalid_proof)
        invalid_proof["observation_digest"] = "sha256:" + "b" * 64
        proof_rows = [invalid_proof]
    blocked = hard_contract.derive_hard_evaluation(
        candidate_claims=_candidate_claims(candidate_id),
        evaluator_observations=observations,
        proof_rows=proof_rows,
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
        trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
        evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
        task_identity_digest=TASK_IDENTITY_DIGEST,
        fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
        frozen_proof_authority=authority,
    )
    rich = (
        blocked
        if blocked_side == "rich"
        else _derive(
            hard_contract,
            RICH_LABEL,
            frozen_proof_authority=authority,
        )
    )
    direct = (
        blocked
        if blocked_side == "direct"
        else _derive(
            hard_contract,
            DIRECT_LABEL,
            frozen_proof_authority=authority,
        )
    )

    result = hard_contract.derive_primary_outcome(
        raw_outcome=raw_outcome,
        rich_freeze=rich,
        direct_freeze=direct,
    )

    assert result.derived_outcome == expected


@pytest.mark.parametrize(
    ("same_clause", "raw_outcome", "expected"),
    [
        (same, raw, "INDETERMINATE" if raw in {"RICH", "DIRECT"} else raw)
        for same in (True, False)
        for raw in ("RICH", "DIRECT", "TIE", "INDETERMINATE")
    ],
)
def test_comparable_and_noncomparable_two_sided_product_blockers(
    hard_contract: ModuleType,
    same_clause: bool,
    raw_outcome: str,
    expected: str,
) -> None:
    rich = _derive(
        hard_contract,
        RICH_LABEL,
        failed_clauses=(FAILED_CLAUSE,),
    )
    direct_clause = FAILED_CLAUSE if same_clause else OTHER_FAILED_CLAUSE
    direct = _derive(
        hard_contract,
        DIRECT_LABEL,
        failed_clauses=(direct_clause,),
    )

    result = hard_contract.derive_primary_outcome(
        raw_outcome=raw_outcome,
        rich_freeze=rich,
        direct_freeze=direct,
    )

    assert result.derived_outcome == expected
    assert result.comparable_product_blockers == (
        (FAILED_CLAUSE,) if same_clause else ()
    )


@pytest.mark.parametrize(
    "proof_kind",
    [
        "ORACLE_CONTRADICTION",
        "CONFLICTING_REQUIREMENTS",
        "TREATMENT_LOCAL_INFRASTRUCTURE",
    ],
)
def test_exact_non_product_findings_do_not_become_primary_blockers(
    hard_contract: ModuleType,
    proof_kind: str,
) -> None:
    observations = _observations(FAILED_CLAUSE)
    observation = next(
        row for row in observations if row["clause_id"] == FAILED_CLAUSE
    )
    proof = _proof(
        kind=proof_kind,
        candidate_id=RICH_LABEL,
        observation=observation,
    )
    rich = hard_contract.derive_hard_evaluation(
        candidate_claims=_candidate_claims(RICH_LABEL),
        evaluator_observations=observations,
        proof_rows=[proof],
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
        trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
        evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
        task_identity_digest=TASK_IDENTITY_DIGEST,
        fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
        frozen_proof_authority=_proof_authority(proof),
    )

    result = hard_contract.derive_primary_outcome(
        raw_outcome="RICH",
        rich_freeze=rich,
        direct_freeze=_derive(
            hard_contract,
            DIRECT_LABEL,
            frozen_proof_authority=_proof_authority(proof),
        ),
    )

    assert result.derived_outcome == "RICH"


@pytest.mark.parametrize(
    "substitute",
    [0.91, {"scorer_value": 0.91}, {"reviewer_prose": "RICH"}, "RICH because"],
)
def test_scorer_values_or_prose_cannot_substitute_for_typed_primary_outcome(
    hard_contract: ModuleType,
    substitute: Any,
) -> None:
    with pytest.raises(hard_contract.HardContractError):
        hard_contract.derive_primary_outcome(
            raw_outcome=substitute,
            rich_freeze=_derive(hard_contract, RICH_LABEL),
            direct_freeze=_derive(hard_contract, DIRECT_LABEL),
        )


def test_primary_override_requires_exact_trusted_freeze_values(
    hard_contract: ModuleType,
) -> None:
    with pytest.raises(hard_contract.HardContractError):
        hard_contract.derive_primary_outcome(
            raw_outcome="RICH",
            rich_freeze={"product_blockers": []},
            direct_freeze=_derive(hard_contract, DIRECT_LABEL),
        )


def test_primary_override_rejects_cross_authority_freeze_pair(
    hard_contract: ModuleType,
) -> None:
    direct = hard_contract.derive_hard_evaluation(
        candidate_claims=_candidate_claims(DIRECT_LABEL),
        evaluator_observations=_observations(),
        proof_rows=[],
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
        trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
        evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
        task_identity_digest="sha256:" + "c" * 64,
        fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
    )

    with pytest.raises(hard_contract.HardContractError):
        hard_contract.derive_primary_outcome(
            raw_outcome="RICH",
            rich_freeze=_derive(hard_contract, RICH_LABEL),
            direct_freeze=direct,
        )


def test_primary_override_rejects_cross_proof_authority_catalog(
    hard_contract: ModuleType,
) -> None:
    observations = _observations(FAILED_CLAUSE)
    proof = _proof(
        kind="ORACLE_CONTRADICTION",
        candidate_id=RICH_LABEL,
        observation=next(
            row for row in observations if row["clause_id"] == FAILED_CLAUSE
        ),
    )
    rich = hard_contract.derive_hard_evaluation(
        candidate_claims=_candidate_claims(RICH_LABEL),
        evaluator_observations=observations,
        proof_rows=[proof],
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
        trusted_product_freeze_digest=PRODUCT_FREEZE_DIGEST,
        evaluator_identity_digest=EVALUATOR_IDENTITY_DIGEST,
        task_identity_digest=TASK_IDENTITY_DIGEST,
        fixture_identity_digest=FIXTURE_IDENTITY_DIGEST,
        frozen_proof_authority=_proof_authority(proof),
    )

    with pytest.raises(hard_contract.HardContractError):
        hard_contract.derive_primary_outcome(
            raw_outcome="RICH",
            rich_freeze=rich,
            direct_freeze=_derive(hard_contract, DIRECT_LABEL),
        )
