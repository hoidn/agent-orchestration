"""Private ES package assignment and blinded reviewer presentation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.trial.contracts import (
    SealedTrialOpaqueLabelMap,
    TrialCellKey,
)

try:
    from . import decision_lock as decision_lock_contract
except ImportError:  # pragma: no cover - direct script/import-file execution
    import decision_lock as decision_lock_contract  # type: ignore[no-redef]


ARMS = ("DIRECT", "DESIGN_QA", "PRODUCT_QA", "RICH")
PACKAGES = ("PACKAGE-01", "PACKAGE-02", "PACKAGE-03", "PACKAGE-04")
_ATTEMPT_RE = re.compile(r"ES-ATTEMPT-0[1-4]\Z")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OPAQUE_LABEL_RE = re.compile(r"opaque-[0-9a-f]{64}\Z")
_PACKET_INDEX_KEYS = frozenset(
    {
        "schema_version",
        "trial_request_digest",
        "header_row_digest",
        "evidence_frozen_row_digest",
        "checks_frozen_row_digest",
        "packets_frozen_row_digest",
        "sealed_opaque_label_map_digest",
        "packet_set_digest",
        "packets",
    }
)
_PACKET_ROW_KEYS = frozenset(
    {"cell", "opaque_label", "packet_digest", "packet_relpath"}
)
_PAIR_OUTCOMES = frozenset({"A", "B", "TIE", "INDETERMINATE"})
_PRIMARY_OUTCOMES = frozenset({"RICH", "DIRECT", "TIE", "INDETERMINATE"})


class BlindingJoinError(ValueError):
    """The private ES package/arm/cell/label join failed closed."""

    code = "BLINDING_JOIN_INVALID"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"{self.code}: {detail}")


def _sha256(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise BlindingJoinError(f"{field} is not a canonical SHA-256 digest")
    return value


def _opaque_label(value: object) -> str:
    if not isinstance(value, str) or _OPAQUE_LABEL_RE.fullmatch(value) is None:
        raise BlindingJoinError("opaque label is invalid")
    return value


@dataclass(frozen=True, slots=True)
class AttemptPackageSchedule:
    attempt_id: str
    arm_order: tuple[str, ...]
    opaque_package_order: tuple[str, ...]
    randomization_row_digest: str
    decision_lock_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_id, str) or _ATTEMPT_RE.fullmatch(
            self.attempt_id
        ) is None:
            raise BlindingJoinError("attempt id is invalid")
        if type(self.arm_order) is not tuple or set(self.arm_order) != set(ARMS):
            raise BlindingJoinError("arm order is not the exact arm permutation")
        if len(self.arm_order) != len(ARMS):
            raise BlindingJoinError("arm order is not the exact arm permutation")
        if type(self.opaque_package_order) is not tuple or set(
            self.opaque_package_order
        ) != set(PACKAGES):
            raise BlindingJoinError(
                "opaque package order is not the exact package permutation"
            )
        if len(self.opaque_package_order) != len(PACKAGES):
            raise BlindingJoinError(
                "opaque package order is not the exact package permutation"
            )
        _sha256(
            self.randomization_row_digest,
            field="randomization_row_digest",
        )
        _sha256(self.decision_lock_digest, field="decision_lock_digest")


@dataclass(frozen=True, slots=True)
class PrivateBlindingRow:
    package_id: str
    arm_id: str
    cell: TrialCellKey
    opaque_label: str
    packet_digest: str
    packet_path: str

    def __post_init__(self) -> None:
        if self.package_id not in PACKAGES or self.arm_id not in ARMS:
            raise BlindingJoinError("private row package or arm is invalid")
        if type(self.cell) is not TrialCellKey or self.cell != TrialCellKey(
            self.arm_id, 1
        ):
            raise BlindingJoinError("private row cell is invalid")
        _opaque_label(self.opaque_label)
        _sha256(self.packet_digest, field="packet_digest")
        if not isinstance(self.packet_path, str) or not self.packet_path:
            raise BlindingJoinError("packet path is invalid")

    @property
    def record(self) -> dict[str, object]:
        return {
            "package_id": self.package_id,
            "arm_id": self.arm_id,
            "cell": self.cell.record,
            "opaque_label": self.opaque_label,
            "packet_digest": self.packet_digest,
            "packet_path": self.packet_path,
        }


@dataclass(frozen=True, slots=True)
class PrivateBlindingJoin:
    attempt: AttemptPackageSchedule
    randomization_row_digest: str
    decision_lock_digest: str
    trial_request_digest: str
    sealed_opaque_label_map_digest: str
    packet_set_digest: str
    rows: tuple[PrivateBlindingRow, ...]

    def __post_init__(self) -> None:
        if type(self.attempt) is not AttemptPackageSchedule:
            raise TypeError("attempt must be exact AttemptPackageSchedule")
        _sha256(
            self.randomization_row_digest,
            field="randomization_row_digest",
        )
        _sha256(self.decision_lock_digest, field="decision_lock_digest")
        if (
            self.randomization_row_digest != self.attempt.randomization_row_digest
            or self.decision_lock_digest != self.attempt.decision_lock_digest
        ):
            raise BlindingJoinError("private join authority binding disagrees")
        _sha256(self.trial_request_digest, field="trial_request_digest")
        _sha256(
            self.sealed_opaque_label_map_digest,
            field="sealed_opaque_label_map_digest",
        )
        _sha256(self.packet_set_digest, field="packet_set_digest")
        if type(self.rows) is not tuple or len(self.rows) != len(PACKAGES) or any(
            type(row) is not PrivateBlindingRow for row in self.rows
        ):
            raise BlindingJoinError("private join rows are invalid")
        if tuple(row.package_id for row in self.rows) != PACKAGES or tuple(
            row.arm_id for row in self.rows
        ) != self.attempt.arm_order:
            raise BlindingJoinError("private join assignment is invalid")
        for field in ("cell", "opaque_label", "packet_digest", "packet_path"):
            if len({getattr(row, field) for row in self.rows}) != len(self.rows):
                raise BlindingJoinError(f"private join {field} is not unique")

    @property
    def record(self) -> dict[str, object]:
        return {
            "schema_version": "es_private_blinding_join.v1",
            "attempt_id": self.attempt.attempt_id,
            "randomization_row_digest": self.randomization_row_digest,
            "decision_lock_digest": self.decision_lock_digest,
            "trial_request_digest": self.trial_request_digest,
            "sealed_opaque_label_map_digest": self.sealed_opaque_label_map_digest,
            "packet_set_digest": self.packet_set_digest,
            "rows": [row.record for row in self.rows],
        }

    @property
    def digest(self) -> str:
        return canonical_sha256(self.record)


@dataclass(frozen=True, slots=True)
class PublicReviewPacket:
    opaque_label: str
    packet_path: str

    def __post_init__(self) -> None:
        _opaque_label(self.opaque_label)
        if not isinstance(self.packet_path, str) or not self.packet_path:
            raise BlindingJoinError("review packet path is invalid")

    @property
    def record(self) -> dict[str, str]:
        return {
            "opaque_label": self.opaque_label,
            "packet_path": self.packet_path,
        }


@dataclass(frozen=True, slots=True)
class PublicReviewProjection:
    packets: tuple[PublicReviewPacket, ...]

    def __post_init__(self) -> None:
        if type(self.packets) is not tuple or len(self.packets) != len(PACKAGES) or any(
            type(packet) is not PublicReviewPacket for packet in self.packets
        ):
            raise BlindingJoinError("review projection is not an exact packet vector")
        if len({packet.opaque_label for packet in self.packets}) != len(
            self.packets
        ) or len({packet.packet_path for packet in self.packets}) != len(self.packets):
            raise BlindingJoinError("review projection is not a bijection")

    @property
    def record(self) -> list[dict[str, str]]:
        return [packet.record for packet in self.packets]


@dataclass(frozen=True, slots=True)
class FrozenIntegratedPairOutcome:
    """One validated pair row bound to its frozen integrated-review record."""

    integrated_review_record_digest: str
    packet_set_digest: str
    source_pair_row_digest: str
    candidate_a_label: str
    candidate_b_label: str
    outcome: str

    def __post_init__(self) -> None:
        _sha256(
            self.integrated_review_record_digest,
            field="integrated_review_record_digest",
        )
        _sha256(self.packet_set_digest, field="packet_set_digest")
        _sha256(self.source_pair_row_digest, field="source_pair_row_digest")
        _opaque_label(self.candidate_a_label)
        _opaque_label(self.candidate_b_label)
        if self.candidate_a_label == self.candidate_b_label:
            raise BlindingJoinError("integrated pair repeats one opaque label")
        if self.outcome not in _PAIR_OUTCOMES:
            raise BlindingJoinError("integrated pair outcome is invalid")


@dataclass(frozen=True, slots=True)
class FrozenHardEvidence:
    """Digest authority proving hard evidence froze before unblinding."""

    record_digest: str
    packet_set_digest: str

    def __post_init__(self) -> None:
        _sha256(self.record_digest, field="hard_evidence_record_digest")
        _sha256(self.packet_set_digest, field="packet_set_digest")


@dataclass(frozen=True, slots=True)
class OrientedPrimaryPair:
    rich_vs_direct: str
    source_pair_row_digest: str
    integrated_review_record_digest: str
    hard_evidence_record_digest: str
    unblinding_map_digest: str

    def __post_init__(self) -> None:
        if self.rich_vs_direct not in _PRIMARY_OUTCOMES:
            raise BlindingJoinError("oriented primary outcome is invalid")
        for field in (
            "source_pair_row_digest",
            "integrated_review_record_digest",
            "hard_evidence_record_digest",
            "unblinding_map_digest",
        ):
            _sha256(getattr(self, field), field=field)

    @property
    def record(self) -> dict[str, str]:
        return {
            "rich_vs_direct": self.rich_vs_direct,
            "source_pair_row_digest": self.source_pair_row_digest,
            "integrated_review_record_digest": self.integrated_review_record_digest,
            "hard_evidence_record_digest": self.hard_evidence_record_digest,
            "unblinding_map_digest": self.unblinding_map_digest,
        }


def _cell(value: object) -> TrialCellKey:
    if type(value) is not dict or set(value) != {"arm_id", "rep"}:
        raise BlindingJoinError("packet cell is invalid")
    try:
        return TrialCellKey(value["arm_id"], value["rep"])
    except (TypeError, ValueError) as exc:
        raise BlindingJoinError("packet cell is invalid") from exc


def _validate_packet_index(
    packet_index: Mapping[str, Any],
    *,
    cells: tuple[TrialCellKey, ...],
    sealed_opaque_labels: SealedTrialOpaqueLabelMap,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    if type(packet_index) is not dict or set(packet_index) != _PACKET_INDEX_KEYS:
        raise BlindingJoinError("packet index is not a closed record")
    if packet_index["schema_version"] != "trial.packet_artifact_index.v1":
        raise BlindingJoinError("packet index schema is invalid")
    for field in (
        "trial_request_digest",
        "header_row_digest",
        "evidence_frozen_row_digest",
        "checks_frozen_row_digest",
        "packets_frozen_row_digest",
        "sealed_opaque_label_map_digest",
        "packet_set_digest",
    ):
        _sha256(packet_index[field], field=field)
    if (
        packet_index["sealed_opaque_label_map_digest"]
        != sealed_opaque_labels.digest
    ):
        raise BlindingJoinError("packet index sealed-map digest disagrees")
    if tuple(binding.cell for binding in sealed_opaque_labels.bindings) != cells:
        raise BlindingJoinError("sealed labels disagree with the request domain")

    values = packet_index["packets"]
    if type(values) is not list or len(values) != len(cells):
        raise BlindingJoinError("packet index does not cover exactly four cells")
    request_hex = packet_index["trial_request_digest"].removeprefix("sha256:")
    normalized: list[dict[str, Any]] = []
    frozen_rows: list[dict[str, object]] = []
    for expected_cell, binding, value in zip(
        cells,
        sealed_opaque_labels.bindings,
        values,
        strict=True,
    ):
        if type(value) is not dict or set(value) != _PACKET_ROW_KEYS:
            raise BlindingJoinError("packet index row is not a closed record")
        cell = _cell(value["cell"])
        if cell != expected_cell or cell.rep != 1:
            raise BlindingJoinError("packet index cell is crossed or out of domain")
        label = _opaque_label(value["opaque_label"])
        if binding.cell != cell or binding.opaque_label != label:
            raise BlindingJoinError("packet index label is bound to the wrong cell")
        packet_digest = _sha256(value["packet_digest"], field="packet_digest")
        expected_path = (
            f"artifacts/trials/{request_hex}/packets/"
            f"{packet_digest.removeprefix('sha256:')}.json"
        )
        if value["packet_relpath"] != expected_path:
            raise BlindingJoinError("packet path disagrees with its digest")
        row = {
            "cell": cell.record,
            "opaque_label": label,
            "packet_digest": packet_digest,
            "packet_relpath": expected_path,
        }
        normalized.append(row)
        frozen_rows.append(
            {
                "cell": cell.record,
                "opaque_label": label,
                "packet_digest": packet_digest,
            }
        )
    if canonical_sha256(frozen_rows) != packet_index["packet_set_digest"]:
        raise BlindingJoinError("packet-set digest disagrees with packet rows")
    for field in ("cell", "opaque_label", "packet_digest", "packet_relpath"):
        values = [
            canonical_sha256(row[field]) if field == "cell" else row[field]
            for row in normalized
        ]
        if len(set(values)) != len(values):
            raise BlindingJoinError(f"packet index {field} is not unique")
    return dict(packet_index), tuple(normalized)


def build_private_blinding_join(
    *,
    attempt: AttemptPackageSchedule,
    randomization_manifest: Mapping[str, object],
    decision_lock: Mapping[str, object],
    expected_bindings: Mapping[str, object],
    request_cell_domain: tuple[TrialCellKey, ...],
    sealed_opaque_labels: SealedTrialOpaqueLabelMap,
    packet_index: Mapping[str, Any],
) -> PrivateBlindingJoin:
    """Join one frozen ES schedule to its exact E2 packet projection."""

    if type(attempt) is not AttemptPackageSchedule:
        raise TypeError("attempt must be exact AttemptPackageSchedule")
    try:
        checked_manifest = decision_lock_contract.validate_randomization_manifest(
            randomization_manifest
        )
        checked_lock = decision_lock_contract.validate_decision_lock(
            decision_lock,
            randomization_manifest=checked_manifest,
            expected_bindings=expected_bindings,
        )
    except decision_lock_contract.DecisionLockError as exc:
        raise BlindingJoinError("randomization or decision-lock authority is invalid") from exc
    manifest_attempts = checked_manifest["attempts"]
    if not isinstance(manifest_attempts, list):
        raise BlindingJoinError("randomization attempt table is invalid")
    matching_rows = [
        row
        for row in manifest_attempts
        if isinstance(row, dict) and row.get("attempt_id") == attempt.attempt_id
    ]
    if len(matching_rows) != 1:
        raise BlindingJoinError("attempt is absent or ambiguous in randomization authority")
    authority_row = matching_rows[0]
    arm_order = authority_row.get("arm_order")
    package_order = authority_row.get("opaque_package_order")
    if not isinstance(arm_order, list) or not isinstance(package_order, list):
        raise BlindingJoinError("randomization attempt row is invalid")
    authoritative_attempt = AttemptPackageSchedule(
        attempt_id=attempt.attempt_id,
        arm_order=tuple(arm_order),
        opaque_package_order=tuple(package_order),
        randomization_row_digest=decision_lock_contract.decision_lock_digest(
            authority_row
        ),
        decision_lock_digest=decision_lock_contract.decision_lock_digest(
            checked_lock
        ),
    )
    if attempt != authoritative_attempt:
        raise BlindingJoinError("attempt schedule disagrees with frozen authority")
    if type(sealed_opaque_labels) is not SealedTrialOpaqueLabelMap:
        raise TypeError("sealed labels must be exact SealedTrialOpaqueLabelMap")
    if type(request_cell_domain) is not tuple or any(
        type(cell) is not TrialCellKey for cell in request_cell_domain
    ):
        raise TypeError("request cell domain must be an exact TrialCellKey tuple")
    assigned_cells = tuple(TrialCellKey(arm_id, 1) for arm_id in attempt.arm_order)
    if (
        len(request_cell_domain) != len(assigned_cells)
        or set(request_cell_domain) != set(assigned_cells)
    ):
        raise BlindingJoinError("request domain disagrees with the attempt")
    normalized_index, packets = _validate_packet_index(
        packet_index,
        cells=request_cell_domain,
        sealed_opaque_labels=sealed_opaque_labels,
    )
    labels_by_cell = {
        binding.cell: binding.opaque_label
        for binding in sealed_opaque_labels.bindings
    }
    packets_by_cell = {
        _cell(packet["cell"]): packet
        for packet in packets
    }
    rows: list[PrivateBlindingRow] = []
    for package_id, arm_id in zip(
        PACKAGES,
        attempt.arm_order,
        strict=True,
    ):
        cell = TrialCellKey(arm_id, 1)
        packet = packets_by_cell[cell]
        rows.append(
            PrivateBlindingRow(
                package_id=package_id,
                arm_id=arm_id,
                cell=cell,
                opaque_label=labels_by_cell[cell],
                packet_digest=packet["packet_digest"],
                packet_path=packet["packet_relpath"],
            )
        )
    return PrivateBlindingJoin(
        attempt=attempt,
        randomization_row_digest=attempt.randomization_row_digest,
        decision_lock_digest=attempt.decision_lock_digest,
        trial_request_digest=normalized_index["trial_request_digest"],
        sealed_opaque_label_map_digest=normalized_index[
            "sealed_opaque_label_map_digest"
        ],
        packet_set_digest=normalized_index["packet_set_digest"],
        rows=tuple(rows),
    )


def build_public_review_projection(
    private_join: PrivateBlindingJoin,
) -> PublicReviewProjection:
    """Project only opaque labels and packet paths in reviewer order."""

    if type(private_join) is not PrivateBlindingJoin:
        raise TypeError("private join must be exact PrivateBlindingJoin")
    by_package = {row.package_id: row for row in private_join.rows}
    return PublicReviewProjection(
        packets=tuple(
            PublicReviewPacket(
                opaque_label=by_package[package_id].opaque_label,
                packet_path=by_package[package_id].packet_path,
            )
            for package_id in private_join.attempt.opaque_package_order
        )
    )


def orient_integrated_primary_pair(
    private_join: PrivateBlindingJoin,
    *,
    integrated_pair: FrozenIntegratedPairOutcome,
    hard_evidence: FrozenHardEvidence,
) -> OrientedPrimaryPair:
    """Orient only frozen integrated RICH/DIRECT authority after hard freeze."""

    if type(private_join) is not PrivateBlindingJoin:
        raise TypeError("private join must be exact PrivateBlindingJoin")
    if type(integrated_pair) is not FrozenIntegratedPairOutcome:
        raise TypeError(
            "integrated pair must be exact FrozenIntegratedPairOutcome"
        )
    if type(hard_evidence) is not FrozenHardEvidence:
        raise TypeError("hard evidence must be exact FrozenHardEvidence")
    if (
        integrated_pair.packet_set_digest != private_join.packet_set_digest
        or hard_evidence.packet_set_digest != private_join.packet_set_digest
    ):
        raise BlindingJoinError("frozen review or hard evidence names another packet set")
    labels_by_arm = {row.arm_id: row.opaque_label for row in private_join.rows}
    rich_label = labels_by_arm["RICH"]
    direct_label = labels_by_arm["DIRECT"]
    if {
        integrated_pair.candidate_a_label,
        integrated_pair.candidate_b_label,
    } != {rich_label, direct_label}:
        raise BlindingJoinError("integrated pair is not the RICH/DIRECT pair")
    if integrated_pair.outcome in {"TIE", "INDETERMINATE"}:
        oriented = integrated_pair.outcome
    else:
        winning_label = (
            integrated_pair.candidate_a_label
            if integrated_pair.outcome == "A"
            else integrated_pair.candidate_b_label
        )
        oriented = "RICH" if winning_label == rich_label else "DIRECT"
    return OrientedPrimaryPair(
        rich_vs_direct=oriented,
        source_pair_row_digest=integrated_pair.source_pair_row_digest,
        integrated_review_record_digest=(
            integrated_pair.integrated_review_record_digest
        ),
        hard_evidence_record_digest=hard_evidence.record_digest,
        unblinding_map_digest=private_join.digest,
    )


__all__ = [
    "ARMS",
    "PACKAGES",
    "AttemptPackageSchedule",
    "BlindingJoinError",
    "FrozenHardEvidence",
    "FrozenIntegratedPairOutcome",
    "OrientedPrimaryPair",
    "PrivateBlindingJoin",
    "PrivateBlindingRow",
    "PublicReviewPacket",
    "PublicReviewProjection",
    "build_private_blinding_join",
    "build_public_review_projection",
    "orient_integrated_primary_pair",
]
