from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.trial.contracts import (
    SealedTrialOpaqueLabelMap,
    TrialCellKey,
    build_sealed_opaque_label_map,
)
ROOT = Path(__file__).resolve().parents[2]
BLINDING_MODULE_PATH = ROOT / "scripts/experiments/es/blinding.py"
PACKAGES = ("PACKAGE-01", "PACKAGE-02", "PACKAGE-03", "PACKAGE-04")
ARMS = ("RICH", "DIRECT", "DESIGN_QA", "PRODUCT_QA")
E2_REQUEST_ORDER = ("DIRECT", "DESIGN_QA", "PRODUCT_QA", "RICH")


def _sha(label: str) -> str:
    return canonical_sha256({"label": label})


def _load_decision_lock() -> ModuleType:
    path = ROOT / "scripts/experiments/es/decision_lock.py"
    spec = importlib.util.spec_from_file_location("es_blinding_decision_lock", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decision_lock = _load_decision_lock()


RANDOMIZATION_ROW_DIGEST = _sha("randomization-row")
DECISION_LOCK_DIGEST = _sha("decision-lock")


def _module():
    assert BLINDING_MODULE_PATH.is_file(), "Task-2 blinding module is missing"
    return importlib.import_module("scripts.experiments.es.blinding")


def _fixture(
    *,
    cell_order: tuple[str, ...] = ARMS,
) -> dict[str, object]:
    cells = tuple(TrialCellKey(arm_id, 1) for arm_id in cell_order)
    labels = tuple(f"opaque-{index:064x}" for index in range(1, 5))
    sealed = build_sealed_opaque_label_map(cells, labels=labels)
    request_digest = _sha("request")
    packet_rows = []
    frozen_rows = []
    for cell, label in zip(cells, labels, strict=True):
        packet_digest = _sha(f"packet:{cell.arm_id}")
        packet_rows.append(
            {
                "cell": cell.record,
                "opaque_label": label,
                "packet_digest": packet_digest,
                "packet_relpath": (
                    "artifacts/trials/"
                    f"{request_digest.removeprefix('sha256:')}/packets/"
                    f"{packet_digest.removeprefix('sha256:')}.json"
                ),
            }
        )
        frozen_rows.append(
            {
                "cell": cell.record,
                "opaque_label": label,
                "packet_digest": packet_digest,
            }
        )
    packet_index = {
        "schema_version": "trial.packet_artifact_index.v1",
        "trial_request_digest": request_digest,
        "header_row_digest": _sha("header"),
        "evidence_frozen_row_digest": _sha("evidence"),
        "checks_frozen_row_digest": _sha("checks"),
        "packets_frozen_row_digest": _sha("packets"),
        "sealed_opaque_label_map_digest": sealed.digest,
        "packet_set_digest": canonical_sha256(frozen_rows),
        "packets": packet_rows,
    }
    return {
        "cells": cells,
        "sealed": sealed,
        "packet_index": packet_index,
    }


def _authority() -> dict[str, Any]:
    manifest = decision_lock.generate_randomization_manifest(_sha("randomization-seed"))
    bindings = {
        "arm_workflow_sha256": _sha("arm-workflow"),
        "environment_lock_sha256": _sha("environment-lock"),
        "evaluator_fixture_manifest_sha256": _sha("evaluator-fixture-manifest"),
        "prompt_manifest_sha256": _sha("prompt-manifest"),
        "randomization_manifest_sha256": decision_lock.decision_lock_digest(
            manifest
        ),
        "report_schema_sha256": _sha("report-schema"),
        "source_projection_manifest_sha256": _sha("source-projection-manifest"),
        "task_profile_sha256": _sha("task-profile"),
        "task_seed_manifest_sha256": _sha("task-seed-manifest"),
    }
    lock = decision_lock.build_decision_lock(
        bindings=bindings,
        randomization_manifest=manifest,
    )
    [row] = [
        row
        for row in manifest["attempts"]
        if row["attempt_id"] == "ES-ATTEMPT-01"
    ]
    return {
        "manifest": manifest,
        "bindings": bindings,
        "lock": lock,
        "row": row,
    }


def _attempt(blinding, authority: dict[str, Any]):
    row = authority["row"]
    return blinding.AttemptPackageSchedule(
        attempt_id=row["attempt_id"],
        arm_order=tuple(row["arm_order"]),
        opaque_package_order=tuple(row["opaque_package_order"]),
        randomization_row_digest=decision_lock.decision_lock_digest(row),
        decision_lock_digest=decision_lock.decision_lock_digest(authority["lock"]),
    )


def _build_join(
    case: dict[str, object],
    *,
    authority: dict[str, Any] | None = None,
    attempt=None,
):
    blinding = _module()
    selected_authority = _authority() if authority is None else authority
    selected_attempt = (
        _attempt(blinding, selected_authority) if attempt is None else attempt
    )
    return blinding, blinding.build_private_blinding_join(
        attempt=selected_attempt,
        randomization_manifest=selected_authority["manifest"],
        decision_lock=selected_authority["lock"],
        expected_bindings=selected_authority["bindings"],
        request_cell_domain=case["cells"],
        sealed_opaque_labels=case["sealed"],
        packet_index=case["packet_index"],
    )


def test_private_join_uses_exact_package_arm_cell_label_packet_assignment() -> None:
    case = _fixture()
    authority = _authority()

    blinding, private_join = _build_join(case, authority=authority)

    assert [
        (row.package_id, row.arm_id, row.cell)
        for row in private_join.rows
    ] == [
        (package_id, arm_id, TrialCellKey(arm_id, 1))
        for package_id, arm_id in zip(
            PACKAGES, private_join.attempt.arm_order, strict=True
        )
    ]
    sealed = case["sealed"]
    assert isinstance(sealed, SealedTrialOpaqueLabelMap)
    labels_by_cell = {
        binding.cell: binding.opaque_label for binding in sealed.bindings
    }
    assert [row.opaque_label for row in private_join.rows] == [
        labels_by_cell[TrialCellKey(arm_id, 1)]
        for arm_id in private_join.attempt.arm_order
    ]
    assert private_join.randomization_row_digest == decision_lock.decision_lock_digest(
        authority["row"]
    )
    assert private_join.decision_lock_digest == decision_lock.decision_lock_digest(
        authority["lock"]
    )
    assert private_join.record["randomization_row_digest"] == (
        decision_lock.decision_lock_digest(authority["row"])
    )
    assert private_join.record["decision_lock_digest"] == (
        decision_lock.decision_lock_digest(authority["lock"])
    )

    projection = blinding.build_public_review_projection(private_join)
    rows_by_package = {row.package_id: row for row in private_join.rows}
    expected = [
        {
            "opaque_label": rows_by_package[package_id].opaque_label,
            "packet_path": rows_by_package[package_id].packet_path,
        }
        for package_id in private_join.attempt.opaque_package_order
    ]
    assert projection.record == expected
    assert all(set(row) == {"opaque_label", "packet_path"} for row in projection.record)
    forbidden = {
        "arm",
        "arm_id",
        "package",
        "package_id",
        "cell",
        "workflow",
        "source",
        "sealed_map",
        "sealed_opaque_label_map_digest",
        "private_join",
    }
    assert not any(key in forbidden for row in projection.record for key in row)


def test_private_join_keys_fixed_e2_packets_by_randomized_arm_assignment() -> None:
    case = _fixture(cell_order=E2_REQUEST_ORDER)

    blinding, private_join = _build_join(case)

    packets_by_cell = {
        TrialCellKey(row["cell"]["arm_id"], row["cell"]["rep"]): row
        for row in case["packet_index"]["packets"]
    }
    assert [
        (row.package_id, row.arm_id, row.cell, row.opaque_label)
        for row in private_join.rows
    ] == [
        (
            package_id,
            arm_id,
            TrialCellKey(arm_id, 1),
            packets_by_cell[TrialCellKey(arm_id, 1)]["opaque_label"],
        )
        for package_id, arm_id in zip(
            PACKAGES, private_join.attempt.arm_order, strict=True
        )
    ]


def test_private_join_rejects_tampered_decision_lock() -> None:
    authority = _authority()
    authority["lock"] = deepcopy(authority["lock"])
    authority["lock"]["provider_contract"]["resume_forbidden"] = False

    with pytest.raises(_module().BlindingJoinError) as exc_info:
        _build_join(_fixture(), authority=authority)

    assert exc_info.value.code == "BLINDING_JOIN_INVALID"


def test_private_join_rejects_tampered_randomization_manifest() -> None:
    authority = _authority()
    authority["manifest"] = deepcopy(authority["manifest"])
    authority["manifest"]["attempts"][0]["arm_order"].reverse()

    with pytest.raises(_module().BlindingJoinError) as exc_info:
        _build_join(_fixture(), authority=authority)

    assert exc_info.value.code == "BLINDING_JOIN_INVALID"


def test_private_join_rejects_self_certified_lock_binding_tamper() -> None:
    authority = _authority()
    authority["lock"] = deepcopy(authority["lock"])
    authority["lock"]["bindings"]["task_profile_sha256"] = _sha(
        "other-task-profile"
    )

    with pytest.raises(_module().BlindingJoinError) as exc_info:
        _build_join(_fixture(), authority=authority)

    assert exc_info.value.code == "BLINDING_JOIN_INVALID"


def test_private_join_rejects_unrelated_canonical_authority_digests() -> None:
    authority = _authority()
    blinding = _module()
    valid_attempt = _attempt(blinding, authority)
    unrelated_attempt = replace(
        valid_attempt,
        randomization_row_digest=_sha("unrelated-randomization-row"),
        decision_lock_digest=_sha("unrelated-decision-lock"),
    )

    with pytest.raises(blinding.BlindingJoinError) as exc_info:
        _build_join(
            _fixture(),
            authority=authority,
            attempt=unrelated_attempt,
        )

    assert exc_info.value.code == "BLINDING_JOIN_INVALID"


def test_private_join_rejects_arbitrary_permutations_with_unrelated_digests() -> None:
    authority = _authority()
    blinding = _module()
    valid_attempt = _attempt(blinding, authority)
    arbitrary_attempt = replace(
        valid_attempt,
        arm_order=tuple(reversed(valid_attempt.arm_order)),
        opaque_package_order=tuple(reversed(valid_attempt.opaque_package_order)),
        randomization_row_digest=_sha("unrelated-randomization-row"),
        decision_lock_digest=_sha("unrelated-decision-lock"),
    )

    with pytest.raises(blinding.BlindingJoinError) as exc_info:
        _build_join(
            _fixture(),
            authority=authority,
            attempt=arbitrary_attempt,
        )

    assert exc_info.value.code == "BLINDING_JOIN_INVALID"


def test_schedule_requires_both_frozen_authority_digests() -> None:
    blinding = _module()

    with pytest.raises(TypeError):
        blinding.AttemptPackageSchedule(
            attempt_id="ES-ATTEMPT-01",
            arm_order=ARMS,
            opaque_package_order=PACKAGES,
        )


@pytest.mark.parametrize(
    "field",
    ["randomization_row_digest", "decision_lock_digest"],
)
def test_schedule_rejects_an_invalid_authority_digest(field: str) -> None:
    blinding = _module()
    values = {
        "attempt_id": "ES-ATTEMPT-01",
        "arm_order": ARMS,
        "opaque_package_order": PACKAGES,
        "randomization_row_digest": RANDOMIZATION_ROW_DIGEST,
        "decision_lock_digest": DECISION_LOCK_DIGEST,
    }
    values[field] = "sha256:not-a-digest"

    with pytest.raises(blinding.BlindingJoinError) as exc_info:
        blinding.AttemptPackageSchedule(**values)

    assert exc_info.value.code == "BLINDING_JOIN_INVALID"


@pytest.mark.parametrize(
    "field",
    ["randomization_row_digest", "decision_lock_digest"],
)
def test_private_join_rejects_authority_binding_tamper(field: str) -> None:
    blinding, private_join = _build_join(_fixture())

    with pytest.raises(blinding.BlindingJoinError) as exc_info:
        replace(private_join, **{field: _sha(f"tampered:{field}")})

    assert exc_info.value.code == "BLINDING_JOIN_INVALID"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "duplicate",
        "wrong_repetition",
        "cross_cell",
        "digest_mismatch",
        "index_extra_field",
        "row_extra_field",
    ],
)
def test_private_join_rejects_every_nonexact_packet_index(
    mutation: str,
) -> None:
    case = _fixture()
    packet_index = deepcopy(case["packet_index"])
    packets = packet_index["packets"]
    if mutation == "missing":
        packets.pop()
    elif mutation == "extra":
        packets.append(deepcopy(packets[0]))
    elif mutation == "duplicate":
        packets[1] = deepcopy(packets[0])
    elif mutation == "wrong_repetition":
        packets[0]["cell"]["rep"] = 2
    elif mutation == "cross_cell":
        packets[0]["opaque_label"], packets[1]["opaque_label"] = (
            packets[1]["opaque_label"],
            packets[0]["opaque_label"],
        )
    elif mutation == "digest_mismatch":
        packets[0]["packet_digest"] = _sha("replacement-packet")
    elif mutation == "index_extra_field":
        packet_index["private_join"] = "leak"
    else:
        packets[0]["arm_id"] = "RICH"
    case["packet_index"] = packet_index
    blinding = _module()

    with pytest.raises(blinding.BlindingJoinError) as exc_info:
        _build_join(case)

    assert exc_info.value.code == "BLINDING_JOIN_INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("arm_order", ("RICH", "RICH", "DESIGN_QA", "PRODUCT_QA")),
        (
            "opaque_package_order",
            ("PACKAGE-01", "PACKAGE-01", "PACKAGE-03", "PACKAGE-04"),
        ),
    ],
)
def test_attempt_schedule_rejects_duplicate_or_missing_domain_values(
    field: str,
    value: tuple[str, ...],
) -> None:
    blinding = _module()
    values = {
        "attempt_id": "ES-ATTEMPT-01",
        "arm_order": ARMS,
        "opaque_package_order": PACKAGES,
        "randomization_row_digest": RANDOMIZATION_ROW_DIGEST,
        "decision_lock_digest": DECISION_LOCK_DIGEST,
    }
    values[field] = value

    with pytest.raises(blinding.BlindingJoinError) as exc_info:
        blinding.AttemptPackageSchedule(**values)

    assert exc_info.value.code == "BLINDING_JOIN_INVALID"


@pytest.mark.parametrize(
    ("first_arm", "second_arm", "raw_outcome", "expected"),
    [
        ("RICH", "DIRECT", "A", "RICH"),
        ("RICH", "DIRECT", "B", "DIRECT"),
        ("RICH", "DIRECT", "TIE", "TIE"),
        ("RICH", "DIRECT", "INDETERMINATE", "INDETERMINATE"),
        ("DIRECT", "RICH", "A", "DIRECT"),
        ("DIRECT", "RICH", "B", "RICH"),
    ],
)
def test_unblinding_orients_only_the_frozen_integrated_primary_pair(
    first_arm: str,
    second_arm: str,
    raw_outcome: str,
    expected: str,
) -> None:
    blinding, private_join = _build_join(_fixture())
    rows_by_arm = {row.arm_id: row for row in private_join.rows}
    pair = blinding.FrozenIntegratedPairOutcome(
        integrated_review_record_digest=_sha("integrated-review"),
        packet_set_digest=private_join.packet_set_digest,
        source_pair_row_digest=_sha("integrated-primary-pair"),
        candidate_a_label=rows_by_arm[first_arm].opaque_label,
        candidate_b_label=rows_by_arm[second_arm].opaque_label,
        outcome=raw_outcome,
    )
    hard_evidence = blinding.FrozenHardEvidence(
        record_digest=_sha("hard-evidence"),
        packet_set_digest=private_join.packet_set_digest,
    )

    result = blinding.orient_integrated_primary_pair(
        private_join,
        integrated_pair=pair,
        hard_evidence=hard_evidence,
    )

    assert result.rich_vs_direct == expected
    assert result.source_pair_row_digest == pair.source_pair_row_digest
    assert (
        result.integrated_review_record_digest
        == pair.integrated_review_record_digest
    )
    assert result.hard_evidence_record_digest == hard_evidence.record_digest
    assert result.unblinding_map_digest == private_join.digest


@pytest.mark.parametrize(
    "mutation",
    [
        "nonprimary_pair",
        "review_packet_set",
        "hard_packet_set",
        "missing_hard_freeze",
    ],
)
def test_unblinding_rejects_nonprimary_or_unfrozen_authority(mutation: str) -> None:
    blinding, private_join = _build_join(_fixture())
    rows_by_arm = {row.arm_id: row for row in private_join.rows}
    second_arm = "DESIGN_QA" if mutation == "nonprimary_pair" else "DIRECT"
    pair = blinding.FrozenIntegratedPairOutcome(
        integrated_review_record_digest=_sha("integrated-review"),
        packet_set_digest=(
            _sha("other-packet-set")
            if mutation == "review_packet_set"
            else private_join.packet_set_digest
        ),
        source_pair_row_digest=_sha("integrated-primary-pair"),
        candidate_a_label=rows_by_arm["RICH"].opaque_label,
        candidate_b_label=rows_by_arm[second_arm].opaque_label,
        outcome="A",
    )
    hard_evidence = blinding.FrozenHardEvidence(
        record_digest=_sha("hard-evidence"),
        packet_set_digest=(
            _sha("other-packet-set")
            if mutation == "hard_packet_set"
            else private_join.packet_set_digest
        ),
    )
    selected_hard_evidence = (
        {"record_digest": hard_evidence.record_digest}
        if mutation == "missing_hard_freeze"
        else hard_evidence
    )

    with pytest.raises((TypeError, blinding.BlindingJoinError)):
        blinding.orient_integrated_primary_pair(
            private_join,
            integrated_pair=pair,
            hard_evidence=selected_hard_evidence,
        )
