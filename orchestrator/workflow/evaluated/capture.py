"""Capture the lexical environment at a checked evaluated-run boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

from orchestrator.workflow.workspace_files import WorkspaceFiles
from . import views
from .authority import (
    HEADER_FILENAME,
    MEMO_FILENAME,
    PROGRAM_FILENAME,
    RunAuthority,
    RunAuthorityError,
    load_run_authority_from_bytes,
)
from .machine import EffectHandler, _ControlTransfer, _Machine, site_classes
from .memo import MemoError, reduce_memo
from .memo_reducer import MemoSnapshot
from .values import EvaluatedValue, EvaluatedValueError, LexicalEnvironment


@dataclass
class _CaptureTrace:
    completions: list[tuple[LexicalEnvironment, EvaluatedValue]] = field(default_factory=list)
    stop: tuple[LexicalEnvironment, str] | None = None
    result: EvaluatedValue | None = None


@dataclass(frozen=True)
class _CaptureMachine(_Machine):
    trace: _CaptureTrace = field(default_factory=_CaptureTrace, compare=False, repr=False)

    def _halt(self, node, environment, owner, activation, loops):
        result = super()._halt(node, environment, owner, activation, loops)
        self.trace.completions.append((environment, result))
        return result

    def _done(self, node, environment, owner, activation, loops):
        try:
            return super()._done(node, environment, owner, activation, loops)
        except _ControlTransfer as transfer:
            if transfer.kind == "done":
                self.trace.completions.append((environment, transfer.values[0]))
            raise

    def _perform(self, node, environment, owner, activation, loops):
        try:
            return super()._perform(node, environment, owner, activation, loops)
        except views._MissingCommit as exc:
            if self.trace.stop is None:
                self.trace.stop = environment, exc.identity
            raise

    def _body(self, node, environment, owner, activation, loops):
        try:
            return super()._body(node, environment, owner, activation, loops)
        except EvaluatedValueError as exc:
            if self.trace.stop is None:
                self.trace.stop = environment, f"failed:{exc.code}"
            raise


@dataclass(frozen=True)
class CapturedRun:
    environment: LexicalEnvironment
    position: str
    halted: bool
    result: EvaluatedValue | None
    snapshot: MemoSnapshot
    authority: RunAuthority


def visible_bindings(captured: CapturedRun) -> dict[str, EvaluatedValue]:
    """Return visible bindings innermost first, omitting compiler temporaries."""
    bindings: dict[str, EvaluatedValue] = {}
    frame = captured.environment
    while frame is not None:
        for name, value in frame.bindings.items():
            if not name.startswith("%"):
                bindings.setdefault(name, value)
        frame = frame.parent
    return bindings


def capture_run_environment(
    authority: RunAuthority,
    snapshot: MemoSnapshot,
) -> CapturedRun:
    """Replay one checked memo prefix and retain its true lexical position."""
    trace = _CaptureTrace()

    def evaluate(program, inputs, *, effect_handler: EffectHandler, run_id: str):
        result = _CaptureMachine(
            program, effect_handler, run_id, None, None, trace=trace
        ).evaluate(inputs)
        trace.result = result
        return result

    result, _next_effect, halted = views._replay(
        authority, snapshot, evaluate=evaluate
    )
    views._checked_terminal(snapshot, result, halted)
    if halted:
        if trace.stop is not None or not trace.completions or trace.result is None:
            raise MemoError(
                "memo_inconsistent", "checked halt differs from the captured environment"
            )
        environment, _exit_value = trace.completions[-1]
        position = "halt"
        result_value = trace.result
    else:
        if trace.stop is None:
            raise MemoError(
                "memo_inconsistent",
                "checked replay stopped without a captured failure or effect position",
            )
        environment, position = trace.stop
        result_value = None
    return CapturedRun(
        environment, position, halted, result_value, snapshot, authority
    )


def load_run_for_capture(run_root: Path) -> tuple[RunAuthority, MemoSnapshot]:
    """Load checked run files without locking or modifying them."""
    root = Path(os.path.abspath(os.fspath(run_root)))
    files = WorkspaceFiles(root)
    try:
        authority = load_run_authority_from_bytes(
            root,
            header_bytes=files.read(HEADER_FILENAME),
            program_bytes=files.read(PROGRAM_FILENAME),
        )
        snapshot = reduce_memo(
            files.read(MEMO_FILENAME), site_classes(authority.program)
        )
        return authority, snapshot
    except (OSError, OverflowError, TypeError, ValueError) as exc:
        if isinstance(exc, (MemoError, RunAuthorityError)):
            raise
        raise MemoError("memo_inconsistent", str(exc)) from exc
    finally:
        files.close()
