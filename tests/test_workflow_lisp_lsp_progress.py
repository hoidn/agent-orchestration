from __future__ import annotations

import importlib
from typing import Any

import pytest


def _progress() -> Any:
    try:
        return importlib.import_module("orchestrator.lsp.progress")
    except ModuleNotFoundError:
        pytest.fail("the production LSP progress controller is missing")


def _open_interval(*, supported: bool = True) -> tuple[Any, Any, tuple[Any, ...]]:
    progress = _progress()
    controller = progress.ProgressController(supported=supported)
    transition = controller.observe_busy(True)
    return progress, transition.controller, transition.effects


@pytest.mark.parametrize("supported", (False,))
def test_unsupported_controller_never_opens_an_interval(
    supported: bool,
) -> None:
    progress = _progress()
    controller = progress.ProgressController(supported=supported)

    busy = controller.observe_busy(True)
    settled = busy.controller.observe_busy(False)

    assert busy.controller.state == progress.Inactive()
    assert busy.effects == ()
    assert settled.controller.state == progress.Inactive()
    assert settled.effects == ()


def test_first_busy_observation_allocates_one_create() -> None:
    progress, controller, effects = _open_interval()

    assert controller.state == progress.Creating(
        token="workflow-lisp-progress-1",
        interval=1,
    )
    assert controller.next_identity == 2
    assert effects == (
        progress.ProgressEffect(
            kind="create",
            token="workflow-lisp-progress-1",
            interval=1,
        ),
    )
    assert controller.observe_busy(True).effects == ()


def test_successful_create_begins_only_the_matching_busy_interval() -> None:
    progress, controller, _effects = _open_interval()

    acknowledged = controller.create_succeeded(
        token="workflow-lisp-progress-1",
        interval=1,
    )

    assert acknowledged.controller.state == progress.Active(
        token="workflow-lisp-progress-1",
        interval=1,
    )
    assert acknowledged.effects == (
        progress.ProgressEffect(
            kind="begin",
            token="workflow-lisp-progress-1",
            interval=1,
        ),
    )


def test_late_success_after_quiescence_only_retires_registration() -> None:
    progress, controller, _effects = _open_interval()
    settled = controller.observe_busy(False)

    late = settled.controller.create_succeeded(
        token="workflow-lisp-progress-1",
        interval=1,
    )

    assert settled.controller.state == progress.Inactive()
    assert settled.effects == ()
    assert late.controller == settled.controller
    assert late.effects == (
        progress.ProgressEffect(
            kind="retire",
            token="workflow-lisp-progress-1",
            interval=1,
        ),
    )


def test_create_failure_suppresses_interval_and_requests_transport_log() -> None:
    progress, controller, _effects = _open_interval()
    error = RuntimeError("client refused progress")

    failed = controller.create_failed(
        token="workflow-lisp-progress-1",
        interval=1,
        error=error,
    )

    assert failed.controller.state == progress.Suppressed(interval=1)
    assert failed.effects == (
        progress.ProgressEffect(
            kind="log_transport_error",
            token="workflow-lisp-progress-1",
            interval=1,
            error=error,
        ),
    )
    assert failed.controller.observe_busy(True).effects == ()
    assert failed.controller.observe_busy(False).controller.state == progress.Inactive()


def test_active_quiescence_emits_one_balanced_end_and_retirement() -> None:
    progress, controller, _effects = _open_interval()
    active = controller.create_succeeded(
        token="workflow-lisp-progress-1",
        interval=1,
    ).controller

    settled = active.observe_busy(False)
    again = settled.controller.observe_busy(False)

    assert settled.controller.state == progress.Inactive()
    assert settled.effects == (
        progress.ProgressEffect(
            kind="end",
            token="workflow-lisp-progress-1",
            interval=1,
        ),
        progress.ProgressEffect(
            kind="retire",
            token="workflow-lisp-progress-1",
            interval=1,
        ),
    )
    assert again.effects == ()


@pytest.mark.parametrize("acknowledged", (False, True))
def test_client_cancel_suppresses_presentation_without_compile_effect(
    acknowledged: bool,
) -> None:
    progress, controller, _effects = _open_interval()
    if acknowledged:
        controller = controller.create_succeeded(
            token="workflow-lisp-progress-1",
            interval=1,
        ).controller

    canceled = controller.cancel_presentation("workflow-lisp-progress-1")

    assert canceled.controller.state == progress.Suppressed(interval=1)
    assert all(effect.kind != "cancel_compile" for effect in canceled.effects)
    assert canceled.effects == (
        (
            progress.ProgressEffect(
                kind="end",
                token="workflow-lisp-progress-1",
                interval=1,
            ),
            progress.ProgressEffect(
                kind="retire",
                token="workflow-lisp-progress-1",
                interval=1,
            ),
        )
        if acknowledged
        else ()
    )
    assert canceled.controller.observe_busy(True).effects == ()
    assert canceled.controller.observe_busy(False).controller.state == progress.Inactive()


@pytest.mark.parametrize(
    "settlement",
    (
        "success",
        "language_error",
        "server_error",
        "close",
        "generation_cancellation",
        "configuration_stale",
        "pump_exception",
        "pump_task_cancellation",
    ),
)
def test_every_local_settlement_uses_the_same_balanced_rule(
    settlement: str,
) -> None:
    progress, controller, _effects = _open_interval()
    active = controller.create_succeeded(
        token="workflow-lisp-progress-1",
        interval=1,
    ).controller

    settled = active.settle(settlement)

    assert settled.controller.state == progress.Inactive()
    assert [effect.kind for effect in settled.effects] == ["end", "retire"]


def test_supersession_with_replacement_keeps_one_interval_and_token() -> None:
    progress, controller, create_effects = _open_interval()
    active_transition = controller.create_succeeded(
        token="workflow-lisp-progress-1",
        interval=1,
    )

    replacement = active_transition.controller.observe_busy(True)
    settled = replacement.controller.observe_busy(False)

    assert [effect.kind for effect in create_effects] == ["create"]
    assert active_transition.effects[0].kind == "begin"
    assert replacement.controller.state == progress.Active(
        token="workflow-lisp-progress-1",
        interval=1,
    )
    assert replacement.effects == ()
    assert [effect.kind for effect in settled.effects] == ["end", "retire"]


def test_old_callbacks_cannot_affect_a_new_interval() -> None:
    progress, controller, _effects = _open_interval()
    settled = controller.observe_busy(False).controller
    newer = settled.observe_busy(True).controller

    stale_success = newer.create_succeeded(
        token="workflow-lisp-progress-1",
        interval=1,
    )
    stale_failure = stale_success.controller.create_failed(
        token="workflow-lisp-progress-1",
        interval=1,
        error=RuntimeError("old failure"),
    )

    assert newer.state == progress.Creating(
        token="workflow-lisp-progress-2",
        interval=2,
    )
    assert stale_success.controller == newer
    assert stale_success.effects == (
        progress.ProgressEffect(
            kind="retire",
            token="workflow-lisp-progress-1",
            interval=1,
        ),
    )
    assert stale_failure.controller == newer
    assert [effect.kind for effect in stale_failure.effects] == [
        "log_transport_error"
    ]


def test_success_after_client_cancel_only_retires_registration() -> None:
    progress, controller, _effects = _open_interval()
    suppressed = controller.cancel_presentation(
        "workflow-lisp-progress-1"
    ).controller

    late = suppressed.create_succeeded(
        token="workflow-lisp-progress-1",
        interval=1,
    )

    assert late.controller == suppressed
    assert [effect.kind for effect in late.effects] == ["retire"]


def test_begin_delivery_failure_suppresses_without_unmatched_end() -> None:
    progress, controller, _effects = _open_interval()
    active = controller.create_succeeded(
        token="workflow-lisp-progress-1",
        interval=1,
    ).controller
    error = RuntimeError("begin notification failed")

    failed = active.begin_failed(
        token="workflow-lisp-progress-1",
        interval=1,
        error=error,
    )

    assert failed.controller.state == progress.Suppressed(interval=1)
    assert failed.effects == (
        progress.ProgressEffect(
            kind="retire",
            token="workflow-lisp-progress-1",
            interval=1,
        ),
        progress.ProgressEffect(
            kind="log_transport_error",
            token="workflow-lisp-progress-1",
            interval=1,
            error=error,
        ),
    )
    assert all(effect.kind != "end" for effect in failed.effects)


def test_stale_begin_delivery_failure_cannot_suppress_new_interval() -> None:
    progress, controller, _effects = _open_interval()
    newer = controller.observe_busy(False).controller.observe_busy(True).controller
    error = RuntimeError("old begin notification failed")

    failed = newer.begin_failed(
        token="workflow-lisp-progress-1",
        interval=1,
        error=error,
    )

    assert failed.controller == newer
    assert [effect.kind for effect in failed.effects] == [
        "retire",
        "log_transport_error",
    ]


@pytest.mark.parametrize("with_error", (False, True))
def test_create_task_completion_failure_suppresses_and_retires(
    with_error: bool,
) -> None:
    progress, controller, _effects = _open_interval()
    error = RuntimeError("create callback failed") if with_error else None

    settled = controller.create_task_settled(
        token="workflow-lisp-progress-1",
        interval=1,
        error=error,
    )

    assert settled.controller.state == progress.Suppressed(interval=1)
    assert [effect.kind for effect in settled.effects] == (
        ["retire", "log_transport_error"]
        if with_error
        else ["retire"]
    )
