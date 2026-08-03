"""Immutable canonical packet artifacts for external trial consumers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
from typing import Any

from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)

from .config import TrialRuntimeRequest
from .contracts import SealedTrialOpaqueLabelMap
from .ledger import (
    TrialEventLedger,
    TrialLedgerRow,
    load_trial_event_ledger,
    validate_trial_event_ledger_authority,
)
from .packets import validate_trial_cell_evaluation_packet


PACKET_ARTIFACT_INDEX_SCHEMA = "trial.packet_artifact_index.v1"


class TrialPacketArtifactError(ValueError):
    """Frozen packet bytes cannot be published under their exact authority."""

    code = "trial_packet_artifact_invalid"


def _fail(message: str) -> None:
    raise TrialPacketArtifactError(message)


def _one_row(ledger: TrialEventLedger, kind: str) -> TrialLedgerRow:
    rows = tuple(row for row in ledger.rows if row.kind == kind)
    if len(rows) != 1:
        _fail(f"trial packet artifact {kind} authority is missing or ambiguous")
    return rows[0]


def _workspace_root(value: Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or path.resolve(strict=False) != path:
        _fail("trial packet artifact workspace must be canonical and absolute")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise TrialPacketArtifactError(
            "trial packet artifact workspace is unreadable"
        ) from exc
    if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
        _fail("trial packet artifact workspace must be a regular directory")
    return path


def _ensure_directory(root: Path, relative: PurePosixPath) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            except OSError as exc:
                raise TrialPacketArtifactError(
                    "trial packet artifact directory cannot be created"
                ) from exc
            try:
                metadata = current.lstat()
            except OSError as exc:
                raise TrialPacketArtifactError(
                    "trial packet artifact directory is unreadable"
                ) from exc
        except OSError as exc:
            raise TrialPacketArtifactError(
                "trial packet artifact directory is unreadable"
            ) from exc
        if not stat.S_ISDIR(metadata.st_mode) or current.is_symlink():
            _fail("trial packet artifact directory is aliased or non-directory")
    return current


def _read_exact_regular(path: Path, expected: bytes) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise TrialPacketArtifactError(
            "trial packet artifact existing destination is unreadable"
        ) from exc
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        _fail("trial packet artifact destination is aliased or non-regular")
    try:
        observed = path.read_bytes()
    except OSError as exc:
        raise TrialPacketArtifactError(
            "trial packet artifact existing destination is unreadable"
        ) from exc
    if observed != expected:
        _fail("trial packet artifact overwrite is forbidden")


def _write_all(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("trial packet artifact write made no progress")
        remaining = remaining[written:]


def _publish_exact(path: Path, payload: bytes) -> None:
    if os.path.lexists(path):
        _read_exact_regular(path, payload)
        return
    temporary = path.with_name(
        f".orc-packet-{os.getpid()}-{secrets.token_hex(8)}.tmp"
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            _read_exact_regular(path, payload)
        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except TrialPacketArtifactError:
        raise
    except OSError as exc:
        raise TrialPacketArtifactError(
            "trial packet artifact publication failed"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def publish_trial_packet_artifacts(
    *,
    parent_workspace: Path,
    request: TrialRuntimeRequest,
    sealed_opaque_labels: SealedTrialOpaqueLabelMap,
    packets: Sequence[Mapping[str, Any]],
    trial_event_ledger_path: Path,
) -> dict[str, Any]:
    """Validate and publish the exact frozen packet set before scoring."""

    if type(request) is not TrialRuntimeRequest:
        raise TypeError("packet artifact request must be exact TrialRuntimeRequest")
    if type(sealed_opaque_labels) is not SealedTrialOpaqueLabelMap:
        raise TypeError(
            "packet artifact labels must be exact SealedTrialOpaqueLabelMap"
        )
    if isinstance(packets, (str, bytes)) or not isinstance(packets, Sequence):
        raise TypeError("packet artifacts must be an ordered packet sequence")
    packet_values = tuple(packets)
    if len(packet_values) != len(request.cell_domain):
        _fail("trial packet artifact domain is incomplete")
    if tuple(binding.cell for binding in sealed_opaque_labels.bindings) != tuple(
        request.cell_domain
    ):
        _fail("trial packet artifact sealed-label domain disagrees")

    ledger_path = Path(trial_event_ledger_path)
    validate_trial_event_ledger_authority(
        ledger_path,
        request=request,
        sealed_opaque_labels=sealed_opaque_labels,
    )
    ledger = load_trial_event_ledger(ledger_path)
    header = _one_row(ledger, "header")
    evidence = _one_row(ledger, "evidence_frozen")
    checks = _one_row(ledger, "checks_frozen")
    frozen = _one_row(ledger, "packets_frozen")
    frozen_packets = frozen.payload["cell_packets"]
    if not isinstance(frozen_packets, list) or len(frozen_packets) != len(
        packet_values
    ):
        _fail("trial packet artifact frozen domain is incomplete")

    request_hex = request.digest.removeprefix("sha256:")
    relative_root = PurePosixPath(
        "artifacts", "trials", request_hex, "packets"
    )
    prepared: list[tuple[dict[str, Any], PurePosixPath, dict[str, Any]]] = []
    for cell, binding, packet, frozen_packet in zip(
        request.cell_domain,
        sealed_opaque_labels.bindings,
        packet_values,
        frozen_packets,
        strict=True,
    ):
        normalized = validate_trial_cell_evaluation_packet(
            packet,
            request=request,
            cell=cell,
            opaque_label_binding=binding,
        )
        packet_digest = canonical_sha256(normalized)
        expected_frozen = {
            "cell": cell.record,
            "opaque_label": binding.opaque_label,
            "packet_digest": packet_digest,
        }
        if frozen_packet != expected_frozen:
            _fail("trial packet artifact disagrees with packets_frozen")
        packet_hex = packet_digest.removeprefix("sha256:")
        packet_relative = relative_root / f"{packet_hex}.json"
        prepared.append(
            (
                normalized,
                packet_relative,
                {
                    "cell": cell.record,
                    "opaque_label": binding.opaque_label,
                    "packet_digest": packet_digest,
                    "packet_relpath": packet_relative.as_posix(),
                },
            )
        )

    workspace = _workspace_root(parent_workspace)
    artifact_root = _ensure_directory(workspace, relative_root)
    rows: list[dict[str, Any]] = []
    for normalized, packet_relative, row in prepared:
        _publish_exact(
            workspace.joinpath(*packet_relative.parts),
            canonical_json_bytes(normalized) + b"\n",
        )
        rows.append(row)

    index = {
        "schema_version": PACKET_ARTIFACT_INDEX_SCHEMA,
        "trial_request_digest": request.digest,
        "header_row_digest": header.row_digest,
        "evidence_frozen_row_digest": evidence.row_digest,
        "checks_frozen_row_digest": checks.row_digest,
        "packets_frozen_row_digest": frozen.row_digest,
        "sealed_opaque_label_map_digest": sealed_opaque_labels.digest,
        "packet_set_digest": frozen.payload["packet_set_digest"],
        "packets": rows,
    }
    _publish_exact(
        artifact_root / "index.json",
        canonical_json_bytes(index) + b"\n",
    )
    return index


__all__ = [
    "PACKET_ARTIFACT_INDEX_SCHEMA",
    "TrialPacketArtifactError",
    "publish_trial_packet_artifacts",
]
