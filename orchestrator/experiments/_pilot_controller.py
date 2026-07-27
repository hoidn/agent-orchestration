"""Private bounded sequencing for the lean-pilot smoke and live prefix."""

from __future__ import annotations

import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ._pilot_controller_state import (
    PilotControllerStateError,
    prepare_or_load_block_package,
)
from ._pilot_evidence import prepare_block_package
from ._pilot_review import (
    publish_review_bindings,
    publish_unblinding_bindings,
    run_live_review_slot,
    validate_live_reviewer_apparatus,
)
from ._runner_quiescence import (
    surviving_started_process_groups_are_quiescent,
)
from .contracts import (
    PilotContractError,
    canonical_sha256,
    load_record,
    validate_record,
)
from .runner import run_block


class PilotControllerError(ValueError):
    """The locked pilot cannot continue without violating its sequence."""


def _fail(code: str) -> None:
    raise PilotControllerError(code)


def _locked_ids(lock: Mapping[str, object]) -> tuple[str, tuple[str, ...]]:
    smoke_id = lock.get("smoke_id")
    live_ids = lock.get("live_attempt_ids")
    if (
        not isinstance(smoke_id, str)
        or not smoke_id
        or not isinstance(live_ids, list)
        or not live_ids
        or any(not isinstance(item, str) or not item for item in live_ids)
    ):
        _fail("attempt_identifiers_invalid")
    return smoke_id, tuple(live_ids)


def _validate_attempt_binding(
    *,
    lock: Mapping[str, object],
    attempt: Mapping[str, object],
    block_id: str,
    attempt_class: str,
    sequence_index: int,
) -> dict[str, Any]:
    if (
        attempt.get("pilot_lock_digest") != canonical_sha256(lock)
        or attempt.get("block_id") != block_id
        or attempt.get("attempt_class") != attempt_class
        or attempt.get("sequence_index") != sequence_index
    ):
        _fail("attempt_binding_mismatch")
    return dict(attempt)


def _attempt_path(evidence_root: Path, block_id: str) -> Path:
    return evidence_root / block_id / "block-attempt.json"


def _read_optional_attempt(
    *,
    lock: Mapping[str, object],
    evidence_root: Path,
    block_id: str,
    attempt_class: str,
    sequence_index: int,
) -> dict[str, Any] | None:
    path = _attempt_path(evidence_root, block_id)
    try:
        path_identity = path.lstat()
    except FileNotFoundError:
        if path.parent.exists():
            _fail("attempt_incomplete")
        return None
    except OSError as exc:
        raise PilotControllerError("attempt_path_invalid") from exc
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PilotControllerError("attempt_path_invalid") from exc
    if (
        not path_identity.st_mode
        or not path.is_file()
        or path.is_symlink()
        or resolved != path
        or not resolved.is_relative_to(evidence_root)
    ):
        _fail("attempt_path_invalid")
    try:
        value = load_record(path, expected_kind="block_attempt.v1")
    except (OSError, PilotContractError) as exc:
        raise PilotControllerError("attempt_record_invalid") from exc
    return _validate_attempt_binding(
        lock=lock,
        attempt=value,
        block_id=block_id,
        attempt_class=attempt_class,
        sequence_index=sequence_index,
    )


def load_attempt_prefix(
    *,
    lock: Mapping[str, object],
    evidence_root: Path,
) -> tuple[dict[str, Any], ...]:
    """Load the existing smoke and incomplete-but-contiguous live prefix."""

    smoke_id, live_ids = _locked_ids(lock)
    smoke = _read_optional_attempt(
        lock=lock,
        evidence_root=evidence_root,
        block_id=smoke_id,
        attempt_class="SMOKE",
        sequence_index=0,
    )
    records: list[dict[str, Any]] = []
    if smoke is not None:
        records.append(smoke)

    gap_seen = smoke is None
    valid_count = 0
    for index, block_id in enumerate(live_ids):
        attempt = _read_optional_attempt(
            lock=lock,
            evidence_root=evidence_root,
            block_id=block_id,
            attempt_class="LIVE",
            sequence_index=index,
        )
        if attempt is None:
            gap_seen = True
            continue
        if gap_seen:
            _fail("attempt_prefix_gap")
        if smoke is None or smoke.get("status") != "VALID":
            _fail("live_attempt_after_failed_smoke")
        if valid_count >= lock.get("valid_block_count", 0):
            _fail("attempt_after_denominator")
        records.append(attempt)
        if attempt.get("status") == "VALID":
            valid_count += 1
    return tuple(records)


def _evidence_root(lock: Mapping[str, object]) -> Path:
    value = lock.get("evidence_root")
    if not isinstance(value, str):
        _fail("evidence_root_invalid")
    root = Path(value)
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise PilotControllerError("evidence_root_invalid") from exc
    if not root.is_absolute() or root != resolved or not root.is_dir() or root.is_symlink():
        _fail("evidence_root_invalid")
    return root


def _canonical_directory(path: Path, *, label: str) -> Path:
    if not path.is_absolute() or path.resolve(strict=False) != path:
        _fail(f"{label}_invalid")
    try:
        identity = path.lstat()
    except FileNotFoundError:
        return path
    except OSError as exc:
        raise PilotControllerError(f"{label}_invalid") from exc
    if not stat.S_ISDIR(identity.st_mode) or path.is_symlink():
        _fail(f"{label}_invalid")
    return path


def _locked_root(
    lock: Mapping[str, object],
    section: str,
    key: str,
) -> Path:
    value = lock.get(section)
    if not isinstance(value, Mapping) or not isinstance(value.get(key), str):
        _fail("execution_root_invalid")
    path = Path(value[key])
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PilotControllerError("execution_root_invalid") from exc
    if path != resolved or path.is_symlink() or not path.is_dir():
        _fail("execution_root_invalid")
    return path


def _paths_overlap(first: Path, second: Path) -> bool:
    return (
        first == second
        or first.is_relative_to(second)
        or second.is_relative_to(first)
    )


def _validate_execution_inputs(
    *,
    lock: Mapping[str, object],
    work_root: Path,
    evaluation_root: Path,
    package_root: Path,
    reviewer_environment_path: Path,
) -> tuple[Path, Path, Path, Path]:
    roots = (
        _canonical_directory(Path(work_root), label="work_root"),
        _canonical_directory(Path(evaluation_root), label="evaluation_root"),
        _canonical_directory(Path(package_root), label="package_root"),
    )
    protected = (
        _locked_root(lock, "archive", "repository_root"),
        _locked_root(lock, "apparatus", "control_root"),
        _evidence_root(lock),
    )
    all_roots = (*protected, *roots)
    for index, first in enumerate(all_roots):
        if any(_paths_overlap(first, second) for second in all_roots[index + 1 :]):
            _fail("execution_root_overlap")
    environment = Path(reviewer_environment_path)
    try:
        identity = environment.lstat()
        resolved = environment.resolve(strict=True)
    except OSError as exc:
        raise PilotControllerError("reviewer_environment_path_invalid") from exc
    if (
        not environment.is_absolute()
        or resolved != environment
        or not stat.S_ISREG(identity.st_mode)
        or environment.is_symlink()
    ):
        _fail("reviewer_environment_path_invalid")
    return roots[0], roots[1], roots[2], environment


def _package_valid_attempt(
    *,
    lock: Mapping[str, object],
    attempt: Mapping[str, object],
    work_root: Path,
    evaluation_root: Path,
    package_root: Path,
) -> dict[str, object] | None:
    if attempt.get("status") != "VALID":
        return None
    block_id = attempt.get("block_id")
    if not isinstance(block_id, str) or not block_id:
        _fail("attempt_binding_mismatch")
    try:
        return prepare_or_load_block_package(
            lock=lock,
            attempt=attempt,
            work_root=work_root,
            evaluation_root=evaluation_root / block_id,
            package_root=package_root / block_id,
            evidence_root=_evidence_root(lock),
            prepare=prepare_block_package,
        )
    except PilotControllerStateError as exc:
        raise PilotControllerError(str(exc)) from exc


def execute_pilot(
    *,
    lock: Mapping[str, object],
    work_root: Path,
    evaluation_root: Path,
    package_root: Path,
    reviewer_environment_path: Path,
) -> dict[str, object]:
    """Execute the immutable smoke/live denominator and sealed live reviews."""

    try:
        validate_record(lock)
    except PilotContractError as exc:
        raise PilotControllerError("pilot_lock_invalid") from exc
    (
        work_root,
        evaluation_root,
        package_root,
        reviewer_environment_path,
    ) = _validate_execution_inputs(
        lock=lock,
        work_root=work_root,
        evaluation_root=evaluation_root,
        package_root=package_root,
        reviewer_environment_path=reviewer_environment_path,
    )
    evidence_root = _evidence_root(lock)
    smoke_id, live_ids = _locked_ids(lock)
    review_apparatus = validate_live_reviewer_apparatus(
        lock=lock,
        control_root=_locked_root(lock, "apparatus", "control_root"),
        reviewer_environment_path=reviewer_environment_path,
    )
    attempts = list(
        load_attempt_prefix(lock=lock, evidence_root=evidence_root)
    )
    for attempt in attempts:
        if attempt.get("status") == "STARTED" and not (
            surviving_started_process_groups_are_quiescent(
                lock=lock,
                block_id=str(attempt.get("block_id")),
                evidence_root=evidence_root,
            )
        ):
            _fail("surviving_started_quiescence_unproven")

    if not attempts:
        attempts.append(
            run_block(
                lock=lock,
                block_id=smoke_id,
                work_root=work_root,
                evidence_root=evidence_root,
            ).record
        )
    smoke = attempts[0]
    if smoke.get("status") != "VALID":
        review_bindings = publish_review_bindings(
            lock=lock,
            block_packages={},
            reviews=(),
            evidence_root=evidence_root,
        )
        unblinding_bindings = publish_unblinding_bindings(
            lock=lock,
            block_packages={},
            evidence_root=evidence_root,
            review_bindings_path=review_bindings,
        )
        return {
            "status": "STOP_APPARATUS_NOT_VIABLE",
            "attempt_ids": [str(smoke["block_id"])],
            "valid_live_block_ids": [],
            "review_bindings_path": str(review_bindings),
            "unblinding_bindings_path": str(unblinding_bindings),
        }

    _package_valid_attempt(
        lock=lock,
        attempt=smoke,
        work_root=work_root,
        evaluation_root=evaluation_root,
        package_root=package_root,
    )

    existing_live = attempts[1:]
    packages: dict[str, dict[str, object]] = {}
    for attempt in existing_live:
        prepared = _package_valid_attempt(
            lock=lock,
            attempt=attempt,
            work_root=work_root,
            evaluation_root=evaluation_root,
            package_root=package_root,
        )
        if prepared is not None:
            packages[str(attempt["block_id"])] = prepared

    valid_count = len(packages)
    next_index = len(existing_live)
    max_count = lock.get("max_live_attempt_count")
    target_count = lock.get("valid_block_count")
    if not isinstance(max_count, int) or not isinstance(target_count, int):
        _fail("attempt_bounds_invalid")
    for index in range(next_index, min(max_count, len(live_ids))):
        if valid_count >= target_count:
            break
        attempt = run_block(
            lock=lock,
            block_id=live_ids[index],
            work_root=work_root,
            evidence_root=evidence_root,
        ).record
        attempts.append(attempt)
        prepared = _package_valid_attempt(
            lock=lock,
            attempt=attempt,
            work_root=work_root,
            evaluation_root=evaluation_root,
            package_root=package_root,
        )
        if prepared is not None:
            packages[live_ids[index]] = prepared
            valid_count += 1

    used_session_ids = set()
    if isinstance(review_apparatus, Mapping):
        locked_used = review_apparatus.get(
            "calibration_session_ids",
            review_apparatus.get("used_session_ids", ()),
        )
        if isinstance(locked_used, (set, list, tuple)):
            used_session_ids.update(str(item) for item in locked_used)
    reviews: list[dict[str, object]] = []
    reviews_by_block: dict[str, list[dict[str, object]]] = {}
    reviewer_ids = lock.get("review", {}).get("reviewer_ids")
    if not isinstance(reviewer_ids, list):
        _fail("reviewer_ids_invalid")
    package_paths: dict[str, Path] = {}
    for block_id, prepared in packages.items():
        package_path = Path(str(prepared["package_root"]))
        package_paths[block_id] = package_path
        block_reviews = reviews_by_block.setdefault(block_id, [])
        for reviewer_id in reviewer_ids:
            review = run_live_review_slot(
                lock=lock,
                block_id=block_id,
                package_root=package_path,
                reviewer_id=reviewer_id,
                control_root=Path(str(lock["apparatus"]["control_root"])),
                evidence_root=evidence_root,
                reviewer_environment_path=reviewer_environment_path,
                used_session_ids=used_session_ids,
                prior_block_records=tuple(block_reviews),
            )
            if not isinstance(review, Mapping):
                _fail("review_result_invalid")
            review_record = dict(review)
            session_id = review_record.get("session_id")
            if isinstance(session_id, str):
                used_session_ids.add(session_id)
            block_reviews.append(review_record)
            reviews.append(review_record)

    review_bindings = publish_review_bindings(
        lock=lock,
        block_packages=package_paths,
        reviews=tuple(reviews),
        evidence_root=evidence_root,
    )
    unblinding_bindings = publish_unblinding_bindings(
        lock=lock,
        block_packages=package_paths,
        evidence_root=evidence_root,
        review_bindings_path=review_bindings,
    )
    status = (
        "EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED"
        if valid_count >= target_count
        else "STOP_INSUFFICIENT_VALID_BLOCKS"
    )
    return {
        "status": status,
        "attempt_ids": [str(attempt["block_id"]) for attempt in attempts],
        "valid_live_block_ids": list(packages),
        "review_bindings_path": str(review_bindings),
        "unblinding_bindings_path": str(unblinding_bindings),
    }
