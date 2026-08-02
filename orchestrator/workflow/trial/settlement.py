"""Effect-free outer parent settlement for one terminal trial value."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.type_descriptor import validate_transport_value

from .config import TrialRuntimeRequest
from .contracts import (
    SealedTrialOpaqueLabelMap,
    TrialCellKey,
    TrialOpaqueLabelBinding,
)
from .ledger import (
    TrialEventLedger,
    TrialLedgerRow,
    append_trial_parent_commit,
    append_trial_preparation,
    load_trial_event_ledger,
    validate_trial_event_ledger_authority,
)


_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_VERDICT_ARTIFACT_KEYS = {
    "schema_version",
    "trial_request_digest",
    "evaluation_digest",
    "evidence_frozen_digest",
    "checks_frozen_digest",
    "score_digest",
    "scorer_identity_digest",
    "sealed_label_map_digest",
    "aggregation_digest",
    "verdict_digest",
    "authored_outcomes",
    "verdict",
    "artifact_digest",
}


class TrialSettlementError(ValueError):
    """The outer terminal trial authority cannot be prepared or committed."""

    code = "trial_settlement_invalid"


@dataclass(frozen=True, slots=True)
class PreparedTrialParentSettlement:
    """The exact reusable authority immediately before atomic parent state."""

    ledger_path: Path
    row: TrialLedgerRow

    def __post_init__(self) -> None:
        path = Path(self.ledger_path)
        if not path.is_absolute() or path.resolve(strict=False) != path:
            raise ValueError("trial settlement ledger path must be canonical")
        if type(self.row) is not TrialLedgerRow or self.row.kind != "trial_prepared":
            raise TypeError("trial prepared settlement requires its exact ledger row")
        object.__setattr__(self, "ledger_path", path)


@dataclass(frozen=True, slots=True)
class TrialParentStateSettlement:
    """Closed digest input derived from one reread atomic parent state leaf."""

    parent_run_id: str
    execution_frame_id: str
    call_frame_id: str | None
    step_name: str
    step_id: str
    visit_count: int
    result_envelope_digest: str
    artifacts_digest: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value
            for value in (
                self.parent_run_id,
                self.execution_frame_id,
                self.step_name,
                self.step_id,
            )
        ):
            raise ValueError("trial parent settlement identity is invalid")
        if self.call_frame_id is not None and (
            not isinstance(self.call_frame_id, str) or not self.call_frame_id
        ):
            raise ValueError("trial parent settlement call-frame identity is invalid")
        if type(self.visit_count) is not int or self.visit_count < 1:
            raise ValueError("trial parent settlement visit count is invalid")
        _digest(self.result_envelope_digest, field="result_envelope_digest")
        _digest(self.artifacts_digest, field="artifacts_digest")

    @property
    def record(self) -> dict[str, Any]:
        return {
            "schema_version": "trial_parent_state_settlement.v1",
            "parent_run_id": self.parent_run_id,
            "execution_frame_id": self.execution_frame_id,
            "call_frame_id": self.call_frame_id,
            "step_name": self.step_name,
            "step_id": self.step_id,
            "visit_count": self.visit_count,
            "status": "completed",
            "result_envelope_digest": self.result_envelope_digest,
            "artifacts_digest": self.artifacts_digest,
            "current_step_cleared": True,
        }

    @property
    def digest(self) -> str:
        return canonical_sha256(self.record)


def _fail(message: str) -> None:
    raise TrialSettlementError(message)


def _digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(f"{field} must be a canonical sha256 digest")
    return value


def _canonical_ledger_path(value: object) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError("trial settlement ledger path must be path-like")
    path = Path(value)
    if not path.is_absolute() or path.resolve(strict=False) != path:
        raise ValueError("trial settlement ledger path must be canonical")
    return path


def _one_row(
    ledger: TrialEventLedger,
    kind: str,
    *,
    required: bool,
) -> TrialLedgerRow | None:
    rows = tuple(row for row in ledger.rows if row.kind == kind)
    if len(rows) > 1 or (required and len(rows) != 1):
        _fail(f"trial {kind.replace('_', ' ')} authority is missing or ambiguous")
    return rows[0] if rows else None


def _sealed_labels(ledger: TrialEventLedger) -> SealedTrialOpaqueLabelMap:
    header = ledger.rows[0].payload
    try:
        bindings = tuple(
            TrialOpaqueLabelBinding(
                cell=TrialCellKey(
                    arm_id=value["cell"]["arm_id"],
                    rep=value["cell"]["rep"],
                ),
                opaque_label=value["opaque_label"],
            )
            for value in header["sealed_opaque_label_map"]["bindings"]
        )
        return SealedTrialOpaqueLabelMap(
            bindings=bindings,
            digest=header["sealed_opaque_label_map_digest"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TrialSettlementError(
            "trial sealed opaque-label authority is invalid"
        ) from exc


def _load_request_authority(
    path: Path,
    request: TrialRuntimeRequest,
) -> TrialEventLedger:
    if type(request) is not TrialRuntimeRequest:
        raise TypeError("request must be exact TrialRuntimeRequest")
    ledger = load_trial_event_ledger(path)
    validate_trial_event_ledger_authority(
        path,
        request=request,
        sealed_opaque_labels=_sealed_labels(ledger),
    )
    return load_trial_event_ledger(path)


def _path_validator(workspace: Path) -> Callable[[str, Mapping[str, Any]], str]:
    def validate(value: str, descriptor: Mapping[str, Any]) -> str:
        path = PurePosixPath(value)
        under = PurePosixPath(descriptor["under"])
        if (
            path.is_absolute()
            or path.as_posix() != value
            or any(part in {"", ".", ".."} for part in path.parts)
            or path.parts[: len(under.parts)] != under.parts
        ):
            _fail("trial result artifact path violates its root contract")
        target = workspace.joinpath(*path.parts)
        if descriptor["must_exist_target"] and not target.is_file():
            _fail("trial result artifact path target does not exist")
        return value

    return validate


def _validate_verdict_artifact(
    *,
    workspace: Path,
    request: TrialRuntimeRequest,
    envelope: Mapping[str, Any],
    artifact_digest: str,
) -> None:
    artifact_path = workspace.joinpath(
        *PurePosixPath(envelope["verdict_artifact"]).parts
    )
    try:
        identity = artifact_path.lstat()
        raw = artifact_path.read_bytes()
    except OSError as exc:
        raise TrialSettlementError(
            "trial verdict artifact is missing or unreadable"
        ) from exc
    if not stat.S_ISREG(identity.st_mode) or not raw.endswith(b"\n"):
        _fail("trial verdict artifact is not a complete regular file")
    try:
        record = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TrialSettlementError("trial verdict artifact is not strict JSON") from exc
    if (
        not isinstance(record, Mapping)
        or set(record) != _VERDICT_ARTIFACT_KEYS
        or canonical_json_bytes(dict(record)) + b"\n" != raw
    ):
        _fail("trial verdict artifact is not canonical and closed")
    authority = dict(record)
    observed_digest = authority.pop("artifact_digest")
    if (
        record["schema_version"] != "trial.verdict_artifact.v1"
        or observed_digest != artifact_digest
        or canonical_sha256(authority) != artifact_digest
        or record["trial_request_digest"] != request.digest
        or record["evaluation_digest"] != request.evaluation_digest
        or record["authored_outcomes"] != envelope["outcomes"]
        or record["verdict"] != envelope["verdict"]
        or record["verdict_digest"] != canonical_sha256(envelope["verdict"])
    ):
        _fail("trial verdict artifact authority disagrees")


def _normalized_terminal_envelope(
    *,
    request: TrialRuntimeRequest,
    parent_workspace: Path,
    result_envelope: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(result_envelope, Mapping):
        raise TypeError("result_envelope must be a mapping")
    workspace = Path(parent_workspace)
    if not workspace.is_absolute() or workspace.resolve(strict=False) != workspace:
        raise ValueError("trial parent workspace must be canonical and absolute")
    try:
        normalized = validate_transport_value(
            dict(result_envelope),
            request.static_config.result_descriptor["envelope"],
            allow_nested_structures=True,
            path_validator=_path_validator(workspace),
        )
    except ValueError as exc:
        raise TrialSettlementError("trial terminal result envelope is invalid") from exc
    assert isinstance(normalized, dict)
    return normalized


def _expected_prepared_payload(
    *,
    request: TrialRuntimeRequest,
    publication: TrialLedgerRow,
    envelope: Mapping[str, Any],
) -> dict[str, Any]:
    verdict = envelope["verdict"]
    budget_accounting = verdict["budget_accounting"]
    return {
        "verdict_publication_row_digest": publication.row_digest,
        "result_contract_digest": request.result_contract_digest,
        "result_envelope_digest": canonical_sha256(dict(envelope)),
        "authored_outcomes_digest": canonical_sha256(envelope["outcomes"]),
        "verdict_digest": canonical_sha256(verdict),
        "verdict_artifact_digest": publication.payload["verdict_artifact_digest"],
        "verdict_artifact_relpath": publication.payload["verdict_artifact_relpath"],
        "budget_digest": request.budget_digest,
        "budget_accounting_digest": canonical_sha256(budget_accounting),
    }


def prepare_trial_parent_settlement(
    path: Path,
    *,
    request: TrialRuntimeRequest,
    parent_workspace: Path,
    result_envelope: Mapping[str, Any],
    recorded_at: str | None = None,
) -> PreparedTrialParentSettlement:
    """Append or exactly reuse the terminal row before atomic parent state."""

    source = _canonical_ledger_path(path)
    ledger = _load_request_authority(source, request)
    publication = _one_row(ledger, "verdict_published", required=True)
    verdict_settlement = _one_row(ledger, "verdict_settled", required=True)
    aggregation = _one_row(ledger, "aggregation_frozen", required=True)
    assert (
        publication is not None
        and verdict_settlement is not None
        and aggregation is not None
    )
    normalized = _normalized_terminal_envelope(
        request=request,
        parent_workspace=parent_workspace,
        result_envelope=result_envelope,
    )
    expected = _expected_prepared_payload(
        request=request,
        publication=publication,
        envelope=normalized,
    )
    if (
        expected["verdict_digest"] != verdict_settlement.payload["verdict_digest"]
        or expected["authored_outcomes_digest"]
        != aggregation.payload["final_outcomes_digest"]
        or expected["verdict_artifact_relpath"] != normalized["verdict_artifact"]
    ):
        _fail("trial terminal result disagrees with verdict publication")
    _validate_verdict_artifact(
        workspace=Path(parent_workspace),
        request=request,
        envelope=normalized,
        artifact_digest=expected["verdict_artifact_digest"],
    )
    existing = _one_row(ledger, "trial_prepared", required=False)
    if existing is not None:
        if existing.payload != expected:
            _fail("trial prepared authority disagrees with terminal result")
        return PreparedTrialParentSettlement(source, existing)
    if ledger.rows[-1].row_digest != publication.row_digest:
        _fail("trial preparation does not immediately follow verdict publication")
    appended = append_trial_preparation(
        source,
        expected_head_digest=publication.row_digest,
        verdict_publication_row_digest=publication.row_digest,
        result_contract_digest=request.result_contract_digest,
        result_envelope_digest=expected["result_envelope_digest"],
        authored_outcomes_digest=expected["authored_outcomes_digest"],
        verdict_digest=expected["verdict_digest"],
        verdict_artifact_digest=expected["verdict_artifact_digest"],
        verdict_artifact_relpath=expected["verdict_artifact_relpath"],
        budget_digest=request.budget_digest,
        budget_accounting_digest=expected["budget_accounting_digest"],
        recorded_at=recorded_at,
    )
    return PreparedTrialParentSettlement(source, appended)


def validate_trial_parent_state_settlement(
    *,
    request: TrialRuntimeRequest,
    prepared: PreparedTrialParentSettlement,
    step_name: str,
    expected_artifacts: Mapping[str, Any],
    persisted_state: Mapping[str, Any],
) -> TrialParentStateSettlement:
    """Validate one reread parent state and derive its closed settlement digest."""

    if type(request) is not TrialRuntimeRequest:
        raise TypeError("request must be exact TrialRuntimeRequest")
    if type(prepared) is not PreparedTrialParentSettlement:
        raise TypeError("prepared must be exact PreparedTrialParentSettlement")
    if not isinstance(step_name, str) or not step_name:
        raise ValueError("trial parent settlement step name is invalid")
    if not isinstance(expected_artifacts, Mapping):
        raise TypeError("expected_artifacts must be a mapping")
    if not isinstance(persisted_state, Mapping):
        raise TypeError("persisted_state must be a mapping")
    try:
        state = json.loads(canonical_json_bytes(dict(persisted_state)))
        artifacts = json.loads(canonical_json_bytes(dict(expected_artifacts)))
    except (TypeError, ValueError) as exc:
        raise TrialSettlementError(
            "persisted trial parent state is not canonical JSON"
        ) from exc
    if (
        state.get("run_id") != request.visit.parent_run_id
        or state.get("current_step") is not None
        or not isinstance(state.get("steps"), Mapping)
    ):
        _fail("parent trial state is not settled")
    leaf = state["steps"].get(step_name)
    if not isinstance(leaf, Mapping):
        _fail("parent trial state is not settled")
    required = {
        "status",
        "name",
        "step_id",
        "visit_count",
        "trial",
        "artifacts",
    }
    if not required.issubset(leaf):
        _fail("parent trial state is not settled")
    if (
        leaf["status"] != "completed"
        or leaf["name"] != step_name
        or leaf["step_id"] != request.visit.step_id
        or isinstance(leaf["visit_count"], bool)
        or leaf["visit_count"] != request.visit.visit_count
        or not isinstance(leaf["trial"], Mapping)
        or not isinstance(leaf["artifacts"], Mapping)
    ):
        _fail("parent trial state identity is invalid")
    result_digest = canonical_sha256(dict(leaf["trial"]))
    if result_digest != prepared.row.payload["result_envelope_digest"]:
        _fail("parent trial result disagrees with prepared authority")
    normalized_leaf_artifacts = json.loads(
        canonical_json_bytes(dict(leaf["artifacts"]))
    )
    if normalized_leaf_artifacts != artifacts:
        _fail("parent trial artifacts disagree with expected settlement")
    return TrialParentStateSettlement(
        parent_run_id=request.visit.parent_run_id,
        execution_frame_id=request.visit.execution_frame_id,
        call_frame_id=request.visit.call_frame_id,
        step_name=step_name,
        step_id=request.visit.step_id,
        visit_count=request.visit.visit_count,
        result_envelope_digest=result_digest,
        artifacts_digest=canonical_sha256(artifacts),
    )


def commit_trial_parent_settlement(
    path: Path,
    *,
    request: TrialRuntimeRequest,
    prepared: PreparedTrialParentSettlement,
    step_name: str,
    expected_artifacts: Mapping[str, Any],
    read_parent_state: Callable[[], Mapping[str, Any]],
    recorded_at: str | None = None,
) -> TrialLedgerRow:
    """Append or reuse the commit edge after exact atomic parent settlement."""

    if type(prepared) is not PreparedTrialParentSettlement:
        raise TypeError("prepared must be exact PreparedTrialParentSettlement")
    source = _canonical_ledger_path(path)
    if source != prepared.ledger_path:
        _fail("trial prepared authority belongs to a different ledger")
    if not callable(read_parent_state):
        raise TypeError("read_parent_state must be callable")
    ledger = _load_request_authority(source, request)
    current_prepared = _one_row(ledger, "trial_prepared", required=True)
    assert current_prepared is not None
    if (
        current_prepared.row_digest != prepared.row.row_digest
        or current_prepared.payload != prepared.row.payload
    ):
        _fail("trial prepared authority disagrees with current ledger")
    try:
        persisted_state = read_parent_state()
    except Exception as exc:
        raise TrialSettlementError(
            "persisted trial parent state is unreadable"
        ) from exc
    state_settlement = validate_trial_parent_state_settlement(
        request=request,
        prepared=prepared,
        step_name=step_name,
        expected_artifacts=expected_artifacts,
        persisted_state=persisted_state,
    )
    if (
        state_settlement.result_envelope_digest
        != current_prepared.payload["result_envelope_digest"]
    ):
        _fail("persisted parent trial result disagrees with prepared authority")
    expected = {
        "trial_prepared_row_digest": current_prepared.row_digest,
        "result_envelope_digest": current_prepared.payload[
            "result_envelope_digest"
        ],
        "parent_state_settlement_digest": state_settlement.digest,
    }
    committed = _one_row(ledger, "trial_parent_committed", required=False)
    if committed is not None:
        if committed.payload != expected:
            _fail("trial parent settlement disagrees with committed authority")
        return committed
    if ledger.rows[-1].row_digest != current_prepared.row_digest:
        _fail("trial parent settlement does not immediately follow preparation")
    return append_trial_parent_commit(
        source,
        expected_head_digest=current_prepared.row_digest,
        trial_prepared_row_digest=current_prepared.row_digest,
        result_envelope_digest=current_prepared.payload["result_envelope_digest"],
        parent_state_settlement_digest=state_settlement.digest,
        recorded_at=recorded_at,
    )


__all__ = [
    "PreparedTrialParentSettlement",
    "TrialParentStateSettlement",
    "TrialSettlementError",
    "commit_trial_parent_settlement",
    "prepare_trial_parent_settlement",
    "validate_trial_parent_state_settlement",
]
