"""Pure presentation state for one serialized LSP compile-pump interval."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, TypeAlias


ProgressEffectKind: TypeAlias = Literal[
    "create",
    "begin",
    "end",
    "retire",
    "log_transport_error",
]
SettlementReason: TypeAlias = Literal[
    "success",
    "language_error",
    "server_error",
    "close",
    "generation_cancellation",
    "configuration_stale",
    "pump_exception",
    "pump_task_cancellation",
]


@dataclass(frozen=True)
class Inactive:
    """No logical compile-pump interval is open."""


@dataclass(frozen=True)
class Creating:
    """One busy interval is waiting for client token acknowledgment."""

    token: str
    interval: int


@dataclass(frozen=True)
class Active:
    """One acknowledged progress presentation is visible."""

    token: str
    interval: int


@dataclass(frozen=True)
class Suppressed:
    """One busy interval continues without further presentation."""

    interval: int


ProgressState: TypeAlias = Inactive | Creating | Active | Suppressed


@dataclass(frozen=True)
class ProgressEffect:
    """One transport-only instruction emitted by the pure controller."""

    kind: ProgressEffectKind
    token: str
    interval: int
    error: Exception | None = None


@dataclass(frozen=True)
class ProgressTransition:
    """Next immutable controller plus ordered transport instructions."""

    controller: ProgressController
    effects: tuple[ProgressEffect, ...] = ()


@dataclass(frozen=True)
class ProgressController:
    """Project logical pump occupancy into a balanced progress lifecycle."""

    supported: bool
    state: ProgressState = Inactive()
    next_identity: int = 1

    def observe_busy(self, busy: bool) -> ProgressTransition:
        """Open, retain, or settle the interval for the current busy fact."""

        if not self.supported:
            return ProgressTransition(self)
        if busy:
            if not isinstance(self.state, Inactive):
                return ProgressTransition(self)
            identity = self.next_identity
            token = f"workflow-lisp-progress-{identity}"
            controller = replace(
                self,
                state=Creating(token=token, interval=identity),
                next_identity=identity + 1,
            )
            return ProgressTransition(
                controller,
                (
                    ProgressEffect(
                        kind="create",
                        token=token,
                        interval=identity,
                    ),
                ),
            )
        if isinstance(self.state, Active):
            state = self.state
            return ProgressTransition(
                replace(self, state=Inactive()),
                (
                    ProgressEffect(
                        kind="end",
                        token=state.token,
                        interval=state.interval,
                    ),
                    ProgressEffect(
                        kind="retire",
                        token=state.token,
                        interval=state.interval,
                    ),
                ),
            )
        if isinstance(self.state, (Creating, Suppressed)):
            return ProgressTransition(replace(self, state=Inactive()))
        return ProgressTransition(self)

    def create_succeeded(
        self,
        *,
        token: str,
        interval: int,
    ) -> ProgressTransition:
        """Begin only the matching live interval; retire every late token."""

        state = self.state
        if (
            isinstance(state, Creating)
            and state.token == token
            and state.interval == interval
        ):
            return ProgressTransition(
                replace(
                    self,
                    state=Active(token=token, interval=interval),
                ),
                (
                    ProgressEffect(
                        kind="begin",
                        token=token,
                        interval=interval,
                    ),
                ),
            )
        if (
            isinstance(state, Active)
            and state.token == token
            and state.interval == interval
        ):
            return ProgressTransition(self)
        return ProgressTransition(
            self,
            (
                ProgressEffect(
                    kind="retire",
                    token=token,
                    interval=interval,
                ),
            ),
        )

    def create_failed(
        self,
        *,
        token: str,
        interval: int,
        error: Exception,
    ) -> ProgressTransition:
        """Suppress only the matching interval and surface transport failure."""

        state = self.state
        controller = self
        if (
            isinstance(state, Creating)
            and state.token == token
            and state.interval == interval
        ):
            controller = replace(
                self,
                state=Suppressed(interval=interval),
            )
        return ProgressTransition(
            controller,
            (
                ProgressEffect(
                    kind="log_transport_error",
                    token=token,
                    interval=interval,
                    error=error,
                ),
            ),
        )

    def begin_failed(
        self,
        *,
        token: str,
        interval: int,
        error: Exception,
    ) -> ProgressTransition:
        """Suppress a matching active interval after begin delivery fails."""

        state = self.state
        controller = self
        if (
            isinstance(state, Active)
            and state.token == token
            and state.interval == interval
        ):
            controller = replace(
                self,
                state=Suppressed(interval=interval),
            )
        return ProgressTransition(
            controller,
            (
                ProgressEffect(
                    kind="retire",
                    token=token,
                    interval=interval,
                ),
                ProgressEffect(
                    kind="log_transport_error",
                    token=token,
                    interval=interval,
                    error=error,
                ),
            ),
        )

    def create_task_settled(
        self,
        *,
        token: str,
        interval: int,
        error: Exception | None,
    ) -> ProgressTransition:
        """Own cancellation or callback failure for one create task."""

        state = self.state
        controller = self
        if (
            isinstance(state, Creating)
            and state.token == token
            and state.interval == interval
        ):
            controller = replace(
                self,
                state=Suppressed(interval=interval),
            )
        effects = [
            ProgressEffect(
                kind="retire",
                token=token,
                interval=interval,
            )
        ]
        if error is not None:
            effects.append(
                ProgressEffect(
                    kind="log_transport_error",
                    token=token,
                    interval=interval,
                    error=error,
                )
            )
        return ProgressTransition(controller, tuple(effects))

    def cancel_presentation(self, token: str) -> ProgressTransition:
        """Settle presentation without expressing a compile cancellation."""

        state = self.state
        if isinstance(state, Creating) and state.token == token:
            return ProgressTransition(
                replace(
                    self,
                    state=Suppressed(interval=state.interval),
                )
            )
        if isinstance(state, Active) and state.token == token:
            return ProgressTransition(
                replace(
                    self,
                    state=Suppressed(interval=state.interval),
                ),
                (
                    ProgressEffect(
                        kind="end",
                        token=state.token,
                        interval=state.interval,
                    ),
                    ProgressEffect(
                        kind="retire",
                        token=state.token,
                        interval=state.interval,
                    ),
                ),
            )
        return ProgressTransition(self)

    def settle(self, _reason: SettlementReason) -> ProgressTransition:
        """Force the common local quiescence rule for any settlement cause."""

        return self.observe_busy(False)
