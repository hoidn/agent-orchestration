from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from orchestrator.experiments.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.experiments import _pilot_controller as controller


def _lock(evidence_root: Path) -> dict[str, Any]:
    repository_root = evidence_root.parent / "repository"
    control_root = evidence_root.parent / "control"
    repository_root.mkdir(exist_ok=True)
    control_root.mkdir(exist_ok=True)
    return {
        "record_kind": "pilot_lock.v1",
        "smoke_id": "smoke",
        "live_attempt_ids": ["live-1", "live-2", "live-3", "live-4", "live-5"],
        "valid_block_count": 3,
        "max_live_attempt_count": 5,
        "evidence_root": evidence_root.as_posix(),
        "review": {"reviewer_ids": ["reviewer-1", "reviewer-2"]},
        "apparatus": {"control_root": control_root.as_posix()},
        "archive": {"repository_root": repository_root.as_posix()},
    }


def _reviewer_environment(tmp_path: Path) -> Path:
    path = (tmp_path / "reviewer-env.json").resolve()
    path.write_bytes(b"{}")
    return path


def _attempt(
    lock: dict[str, Any],
    block_id: str,
    *,
    status: str,
    attempt_class: str,
    sequence_index: int,
) -> dict[str, Any]:
    return {
        "record_kind": "block_attempt.v1",
        "pilot_lock_digest": canonical_sha256(lock),
        "attempt_class": attempt_class,
        "sequence_index": sequence_index,
        "block_id": block_id,
        "status": status,
        "treatment_executions": [],
    }


def _terminal_denominator(
    lock: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    return (
        _attempt(
            lock,
            "smoke",
            status="VALID",
            attempt_class="SMOKE",
            sequence_index=0,
        ),
        *(
            _attempt(
                lock,
                f"live-{index}",
                status="VALID",
                attempt_class="LIVE",
                sequence_index=index - 1,
            )
            for index in range(1, 4)
        ),
    )


def _write_attempt(
    evidence_root: Path,
    attempt: dict[str, Any],
) -> None:
    path = evidence_root / attempt["block_id"] / "block-attempt.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(canonical_json_bytes(attempt))


def test_attempt_prefix_loader_accepts_only_the_contiguous_locked_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    lock = _lock(evidence_root)
    smoke = _attempt(
        lock,
        "smoke",
        status="VALID",
        attempt_class="SMOKE",
        sequence_index=0,
    )
    first = _attempt(
        lock,
        "live-1",
        status="ABORTED",
        attempt_class="LIVE",
        sequence_index=0,
    )
    _write_attempt(evidence_root, smoke)
    _write_attempt(evidence_root, first)
    monkeypatch.setattr(
        controller,
        "load_record",
        lambda path, *, expected_kind: json.loads(path.read_bytes()),
    )

    assert controller.load_attempt_prefix(
        lock=lock,
        evidence_root=evidence_root,
    ) == (smoke, first)

    third = _attempt(
        lock,
        "live-3",
        status="VALID",
        attempt_class="LIVE",
        sequence_index=2,
    )
    _write_attempt(evidence_root, third)
    with pytest.raises(
        controller.PilotControllerError,
        match="attempt_prefix_gap",
    ):
        controller.load_attempt_prefix(
            lock=lock,
            evidence_root=evidence_root,
        )


def test_execute_runs_smoke_then_minimal_live_prefix_and_reviews_after_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    lock = _lock(evidence_root)
    events: list[str] = []
    statuses = iter(["VALID", "ABORTED", "VALID", "VALID", "VALID"])
    attempts: list[dict[str, Any]] = []

    monkeypatch.setattr(controller, "validate_record", lambda value: None)
    monkeypatch.setattr(
        controller,
        "load_attempt_prefix",
        lambda **_kwargs: tuple(attempts),
    )

    def fake_run_block(**kwargs: Any) -> SimpleNamespace:
        block_id = kwargs["block_id"]
        events.append(f"run:{block_id}")
        status = next(statuses)
        if block_id == "smoke":
            attempt_class, sequence_index = "SMOKE", 0
        else:
            attempt_class = "LIVE"
            sequence_index = lock["live_attempt_ids"].index(block_id)
        record = _attempt(
            lock,
            block_id,
            status=status,
            attempt_class=attempt_class,
            sequence_index=sequence_index,
        )
        attempts.append(record)
        return SimpleNamespace(record=record)

    def fake_package(**kwargs: Any) -> dict[str, object]:
        block_id = kwargs["attempt"]["block_id"]
        events.append(f"package:{block_id}")
        return {
            "block_id": block_id,
            "package_id": block_id,
            "package_root": str(tmp_path / "packages" / block_id),
        }

    def fake_review(**kwargs: Any) -> dict[str, object]:
        events.append(
            f"review:{kwargs['block_id']}:{kwargs['reviewer_id']}"
        )
        return {
            "block_id": kwargs["block_id"],
            "reviewer_id": kwargs["reviewer_id"],
            "session_id": f"session-{kwargs['block_id']}-{kwargs['reviewer_id']}",
        }

    monkeypatch.setattr(controller, "run_block", fake_run_block)
    monkeypatch.setattr(
        controller,
        "prepare_or_load_block_package",
        fake_package,
    )
    monkeypatch.setattr(
        controller,
        "validate_live_reviewer_apparatus",
        lambda **_kwargs: {
            "calibration_session_ids": frozenset({"calibration-session"})
        },
    )
    monkeypatch.setattr(controller, "run_live_review_slot", fake_review)
    monkeypatch.setattr(
        controller,
        "publish_review_bindings",
        lambda **_kwargs: tmp_path / "review-bindings.json",
    )
    monkeypatch.setattr(
        controller,
        "publish_unblinding_bindings",
        lambda **_kwargs: tmp_path / "unblinding-bindings.json",
    )

    result = controller.execute_pilot(
        lock=lock,
        work_root=(tmp_path / "work").resolve(),
        evaluation_root=(tmp_path / "evaluation").resolve(),
        package_root=(tmp_path / "packages").resolve(),
        reviewer_environment_path=_reviewer_environment(tmp_path),
    )

    assert result["status"] == "EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED"
    assert [event for event in events if event.startswith("run:")] == [
        "run:smoke",
        "run:live-1",
        "run:live-2",
        "run:live-3",
        "run:live-4",
    ]
    first_review = next(
        index for index, event in enumerate(events) if event.startswith("review:")
    )
    assert all(
        event.startswith("run:") or event.startswith("package:")
        for event in events[:first_review]
    )
    assert all(
        "live-1" not in event
        for event in events
        if event.startswith(("package:", "review:"))
    )
    assert len(
        [event for event in events if event.startswith("review:")]
    ) == 6


def test_terminal_denominator_reuses_blocks_and_accumulates_strict_session_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    lock = _lock(evidence_root)
    attempts = _terminal_denominator(lock)
    calibration_sessions = frozenset(
        {"calibration-session-1", "calibration-session-2"}
    )
    run_calls = 0
    review_order: list[tuple[str, str]] = []
    observed_ledgers: list[frozenset[str]] = []
    live_sessions: list[str] = []

    monkeypatch.setattr(controller, "validate_record", lambda value: None)
    monkeypatch.setattr(
        controller,
        "load_attempt_prefix",
        lambda **_kwargs: attempts,
    )

    def fail_if_run(**_kwargs: Any) -> object:
        nonlocal run_calls
        run_calls += 1
        pytest.fail("terminal denominator must not launch another block")

    def fake_package(**kwargs: Any) -> dict[str, object]:
        block_id = kwargs["attempt"]["block_id"]
        return {
            "package_id": block_id,
            "package_root": tmp_path / "packages" / block_id,
        }

    def fake_review(**kwargs: Any) -> dict[str, object]:
        expected_ledger = set(calibration_sessions) | set(live_sessions)
        assert kwargs["used_session_ids"] == expected_ledger
        observed_ledgers.append(frozenset(kwargs["used_session_ids"]))
        review_order.append((kwargs["block_id"], kwargs["reviewer_id"]))
        session_id = f"live-session-{len(live_sessions) + 1}"
        live_sessions.append(session_id)
        return {
            "block_id": kwargs["block_id"],
            "reviewer_id": kwargs["reviewer_id"],
            "session_id": session_id,
        }

    monkeypatch.setattr(controller, "run_block", fail_if_run)
    monkeypatch.setattr(
        controller,
        "prepare_or_load_block_package",
        fake_package,
    )
    monkeypatch.setattr(
        controller,
        "validate_live_reviewer_apparatus",
        lambda **_kwargs: {
            "calibration_session_ids": calibration_sessions
        },
    )
    monkeypatch.setattr(controller, "run_live_review_slot", fake_review)
    monkeypatch.setattr(
        controller,
        "publish_review_bindings",
        lambda **_kwargs: tmp_path / "review-bindings.json",
    )
    monkeypatch.setattr(
        controller,
        "publish_unblinding_bindings",
        lambda **_kwargs: tmp_path / "unblinding-bindings.json",
    )

    result = controller.execute_pilot(
        lock=lock,
        work_root=(tmp_path / "work").resolve(),
        evaluation_root=(tmp_path / "evaluation").resolve(),
        package_root=(tmp_path / "packages").resolve(),
        reviewer_environment_path=_reviewer_environment(tmp_path),
    )

    assert run_calls == 0
    assert review_order == [
        (f"live-{block_index}", f"reviewer-{reviewer_index}")
        for block_index in range(1, 4)
        for reviewer_index in range(1, 3)
    ]
    assert observed_ledgers == [
        calibration_sessions | frozenset(live_sessions[:index])
        for index in range(6)
    ]
    assert result["attempt_ids"] == [
        "smoke",
        "live-1",
        "live-2",
        "live-3",
    ]
    assert result["valid_live_block_ids"] == [
        "live-1",
        "live-2",
        "live-3",
    ]


@pytest.mark.parametrize(
    "review_apparatus",
    [
        pytest.param({}, id="missing"),
        pytest.param(
            {"calibration_session_ids": {"calibration-session"}},
            id="mutable-set",
        ),
        pytest.param(
            {"calibration_session_ids": ["calibration-session"]},
            id="mutable-list",
        ),
        pytest.param(
            {"calibration_session_ids": ("calibration-session",)},
            id="tuple",
        ),
        pytest.param(
            {"calibration_session_ids": frozenset()},
            id="empty",
        ),
        pytest.param(
            {
                "calibration_session_ids": frozenset(
                    {"calibration-session", 1}
                )
            },
            id="non-string",
        ),
        pytest.param(
            {"calibration_session_ids": frozenset({""})},
            id="empty-string",
        ),
    ],
)
def test_invalid_calibration_session_collection_fails_before_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    review_apparatus: dict[str, object],
) -> None:
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    lock = _lock(evidence_root)
    attempts = _terminal_denominator(lock)
    review_calls = 0

    monkeypatch.setattr(controller, "validate_record", lambda value: None)
    monkeypatch.setattr(
        controller,
        "load_attempt_prefix",
        lambda **_kwargs: attempts,
    )
    monkeypatch.setattr(
        controller,
        "run_block",
        lambda **_kwargs: pytest.fail(
            "terminal denominator must not launch another block"
        ),
    )
    monkeypatch.setattr(
        controller,
        "prepare_or_load_block_package",
        lambda **kwargs: {
            "package_id": kwargs["attempt"]["block_id"],
            "package_root": (
                tmp_path / "packages" / kwargs["attempt"]["block_id"]
            ),
        },
    )
    monkeypatch.setattr(
        controller,
        "validate_live_reviewer_apparatus",
        lambda **_kwargs: review_apparatus,
    )

    def fail_if_reviewed(**_kwargs: Any) -> object:
        nonlocal review_calls
        review_calls += 1
        pytest.fail("invalid calibration ledger reached a reviewer")

    monkeypatch.setattr(controller, "run_live_review_slot", fail_if_reviewed)

    with pytest.raises(
        controller.PilotControllerError,
        match="live_reviewer_session_ledger_invalid",
    ):
        controller.execute_pilot(
            lock=lock,
            work_root=(tmp_path / "work").resolve(),
            evaluation_root=(tmp_path / "evaluation").resolve(),
            package_root=(tmp_path / "packages").resolve(),
            reviewer_environment_path=_reviewer_environment(tmp_path),
        )

    assert review_calls == 0


def test_failed_smoke_stops_without_live_launch_or_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    lock = _lock(evidence_root)
    launches: list[str] = []

    monkeypatch.setattr(controller, "validate_record", lambda value: None)
    monkeypatch.setattr(
        controller,
        "load_attempt_prefix",
        lambda **_kwargs: (),
    )

    def fake_run_block(**kwargs: Any) -> SimpleNamespace:
        launches.append(kwargs["block_id"])
        return SimpleNamespace(
            record=_attempt(
                lock,
                "smoke",
                status="INVALID",
                attempt_class="SMOKE",
                sequence_index=0,
            )
        )

    monkeypatch.setattr(controller, "run_block", fake_run_block)
    monkeypatch.setattr(
        controller,
        "prepare_or_load_block_package",
        lambda **_kwargs: pytest.fail("failed smoke must not be packaged"),
    )
    monkeypatch.setattr(
        controller,
        "validate_live_reviewer_apparatus",
        lambda **_kwargs: {"used_session_ids": set()},
    )
    monkeypatch.setattr(
        controller,
        "run_live_review_slot",
        lambda **_kwargs: pytest.fail("failed smoke must not be reviewed"),
    )
    review_bindings = (evidence_root / "review-bindings.json").resolve()
    unblinding_bindings = (
        evidence_root / "unblinding-bindings.json"
    ).resolve()
    monkeypatch.setattr(
        controller,
        "publish_review_bindings",
        lambda **kwargs: (
            review_bindings
            if kwargs["block_packages"] == {} and kwargs["reviews"] == ()
            else pytest.fail("failed smoke bindings must be empty")
        ),
    )
    monkeypatch.setattr(
        controller,
        "publish_unblinding_bindings",
        lambda **kwargs: (
            unblinding_bindings
            if kwargs["block_packages"] == {}
            and kwargs["review_bindings_path"] == review_bindings
            else pytest.fail("failed smoke unblinding must be empty")
        ),
    )

    result = controller.execute_pilot(
        lock=lock,
        work_root=(tmp_path / "work").resolve(),
        evaluation_root=(tmp_path / "evaluation").resolve(),
        package_root=(tmp_path / "packages").resolve(),
        reviewer_environment_path=_reviewer_environment(tmp_path),
    )

    assert result == {
        "status": "STOP_APPARATUS_NOT_VIABLE",
        "attempt_ids": ["smoke"],
        "valid_live_block_ids": [],
        "review_bindings_path": str(review_bindings),
        "unblinding_bindings_path": str(unblinding_bindings),
    }
    assert launches == ["smoke"]


def test_preflight_failure_consumes_no_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    lock = _lock(evidence_root)
    launched = False

    monkeypatch.setattr(controller, "validate_record", lambda value: None)

    def fail_if_launched(**_kwargs: Any) -> object:
        nonlocal launched
        launched = True
        return object()

    monkeypatch.setattr(controller, "run_block", fail_if_launched)

    with pytest.raises(
        controller.PilotControllerError,
        match="reviewer_environment_path_invalid",
    ):
        controller.execute_pilot(
            lock=lock,
            work_root=(tmp_path / "work").resolve(),
            evaluation_root=(tmp_path / "evaluation").resolve(),
            package_root=(tmp_path / "packages").resolve(),
            reviewer_environment_path=(tmp_path / "missing-env.json").resolve(),
        )

    assert launched is False
    assert list(evidence_root.iterdir()) == []


def test_surviving_started_attempt_never_allows_the_next_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    lock = _lock(evidence_root)
    smoke = _attempt(
        lock,
        "smoke",
        status="VALID",
        attempt_class="SMOKE",
        sequence_index=0,
    )
    started = _attempt(
        lock,
        "live-1",
        status="STARTED",
        attempt_class="LIVE",
        sequence_index=0,
    )
    launched = False

    monkeypatch.setattr(controller, "validate_record", lambda value: None)
    monkeypatch.setattr(
        controller,
        "load_attempt_prefix",
        lambda **_kwargs: (smoke, started),
    )
    monkeypatch.setattr(
        controller,
        "validate_live_reviewer_apparatus",
        lambda **_kwargs: {"calibration_session_ids": frozenset()},
    )
    monkeypatch.setattr(
        controller,
        "surviving_started_process_groups_are_quiescent",
        lambda **_kwargs: False,
    )

    def fail_if_launched(**_kwargs: Any) -> object:
        nonlocal launched
        launched = True
        return object()

    monkeypatch.setattr(controller, "run_block", fail_if_launched)

    with pytest.raises(
        controller.PilotControllerError,
        match="surviving_started_quiescence_unproven",
    ):
        controller.execute_pilot(
            lock=lock,
            work_root=(tmp_path / "work").resolve(),
            evaluation_root=(tmp_path / "evaluation").resolve(),
            package_root=(tmp_path / "packages").resolve(),
            reviewer_environment_path=_reviewer_environment(tmp_path),
        )

    assert launched is False


def test_quiescent_started_attempt_is_consumed_before_next_locked_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    lock = _lock(evidence_root)
    smoke = _attempt(
        lock,
        "smoke",
        status="VALID",
        attempt_class="SMOKE",
        sequence_index=0,
    )
    started = _attempt(
        lock,
        "live-1",
        status="STARTED",
        attempt_class="LIVE",
        sequence_index=0,
    )
    launched: list[str] = []

    monkeypatch.setattr(controller, "validate_record", lambda value: None)
    monkeypatch.setattr(
        controller,
        "load_attempt_prefix",
        lambda **_kwargs: (smoke, started),
    )
    monkeypatch.setattr(
        controller,
        "validate_live_reviewer_apparatus",
        lambda **_kwargs: {"calibration_session_ids": frozenset()},
    )
    monkeypatch.setattr(
        controller,
        "surviving_started_process_groups_are_quiescent",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        controller,
        "prepare_or_load_block_package",
        lambda **kwargs: {
            "package_id": kwargs["attempt"]["block_id"],
            "package_root": tmp_path / "package",
        },
    )

    def observe_next(**kwargs: Any) -> object:
        launched.append(kwargs["block_id"])
        raise RuntimeError("observed next launch")

    monkeypatch.setattr(controller, "run_block", observe_next)

    with pytest.raises(RuntimeError, match="observed next launch"):
        controller.execute_pilot(
            lock=lock,
            work_root=(tmp_path / "work").resolve(),
            evaluation_root=(tmp_path / "evaluation").resolve(),
            package_root=(tmp_path / "packages").resolve(),
            reviewer_environment_path=_reviewer_environment(tmp_path),
        )

    assert launched == ["live-2"]


def test_five_attempt_shortfall_publishes_empty_sealed_bindings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    lock = _lock(evidence_root)
    records: list[dict[str, Any]] = []
    review_calls = 0
    statuses = iter(["VALID", "ABORTED", "INVALID", "ABORTED", "INVALID", "ABORTED"])

    monkeypatch.setattr(controller, "validate_record", lambda value: None)
    monkeypatch.setattr(
        controller,
        "load_attempt_prefix",
        lambda **_kwargs: tuple(records),
    )

    def fake_run(**kwargs: Any) -> SimpleNamespace:
        block_id = kwargs["block_id"]
        live = block_id != "smoke"
        record = _attempt(
            lock,
            block_id,
            status=next(statuses),
            attempt_class="LIVE" if live else "SMOKE",
            sequence_index=(
                lock["live_attempt_ids"].index(block_id) if live else 0
            ),
        )
        records.append(record)
        return SimpleNamespace(record=record)

    def fail_if_reviewed(**_kwargs: Any) -> object:
        nonlocal review_calls
        review_calls += 1
        return object()

    monkeypatch.setattr(controller, "run_block", fake_run)
    monkeypatch.setattr(
        controller,
        "prepare_or_load_block_package",
        lambda **kwargs: (
            {
                "package_id": "smoke",
                "package_root": tmp_path / "packages" / "smoke",
            }
            if kwargs["attempt"]["block_id"] == "smoke"
            else pytest.fail("non-VALID live attempts must not be packaged")
        ),
    )
    monkeypatch.setattr(
        controller,
        "validate_live_reviewer_apparatus",
        lambda **_kwargs: {"calibration_session_ids": frozenset({"c1", "c2"})},
    )
    monkeypatch.setattr(controller, "run_live_review_slot", fail_if_reviewed)
    monkeypatch.setattr(
        controller,
        "publish_review_bindings",
        lambda **kwargs: (
            tmp_path / "review-bindings.json"
            if kwargs["block_packages"] == {} and kwargs["reviews"] == ()
            else pytest.fail("shortfall bindings were not empty")
        ),
    )
    monkeypatch.setattr(
        controller,
        "publish_unblinding_bindings",
        lambda **kwargs: tmp_path / "unblinding-bindings.json",
    )

    result = controller.execute_pilot(
        lock=lock,
        work_root=(tmp_path / "work").resolve(),
        evaluation_root=(tmp_path / "evaluation").resolve(),
        package_root=(tmp_path / "packages").resolve(),
        reviewer_environment_path=_reviewer_environment(tmp_path),
    )

    assert result["status"] == "STOP_INSUFFICIENT_VALID_BLOCKS"
    assert result["attempt_ids"] == [
        "smoke",
        "live-1",
        "live-2",
        "live-3",
        "live-4",
        "live-5",
    ]
    assert review_calls == 0


def test_post_valid_package_failure_is_not_rewritten_as_a_stop_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    lock = _lock(evidence_root)
    smoke = _attempt(
        lock,
        "smoke",
        status="VALID",
        attempt_class="SMOKE",
        sequence_index=0,
    )

    monkeypatch.setattr(controller, "validate_record", lambda value: None)
    monkeypatch.setattr(
        controller,
        "load_attempt_prefix",
        lambda **_kwargs: (),
    )
    monkeypatch.setattr(
        controller,
        "run_block",
        lambda **_kwargs: SimpleNamespace(record=smoke),
    )
    monkeypatch.setattr(
        controller,
        "prepare_or_load_block_package",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("package defect")),
    )
    monkeypatch.setattr(
        controller,
        "validate_live_reviewer_apparatus",
        lambda **_kwargs: {"used_session_ids": set()},
    )

    with pytest.raises(RuntimeError, match="package defect"):
        controller.execute_pilot(
            lock=lock,
            work_root=(tmp_path / "work").resolve(),
            evaluation_root=(tmp_path / "evaluation").resolve(),
            package_root=(tmp_path / "packages").resolve(),
            reviewer_environment_path=_reviewer_environment(tmp_path),
        )
