"""Pending agent-turn recovery on resume (design "Persistence" failure table; ruling R3 on pgid reuse).

A `started` agent turn with no commit is classified from its receipt and the native store, never by the
generic retry rule, and no prompt is sent while classifying. Quiescence comes first: the recorded process
group is probed (read-only preflight, `probe_only=True`) or stopped (under the writer lock) before any
native read decides the outcome; inability to prove it stopped is `unresolved`.

Depends on: the attempt directory's receipt and `result.json` (through `run_files.subroot`), the native
store adapter carried by `ResolvedTurn`, `/proc/<pid>/stat` (leader start time), `os.killpg`, and
`agent_turns.update_receipt` (the hookable receipt writer used by kill-point drivers).
"""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from orchestrator.providers.native_store import NativePosition, NativeStoreError
from orchestrator.workflow.run_ref.contracts import canonical_sha256

from . import agent_turns
from .agent_sessions import Receipt, read_receipt
from .agent_turns import AgentTurnError
from .authority import _require_retained_root
from .commands import workspace_relative_path
from .memo import MemoError

_STOP_STEPS = ((0, 0.0), (signal.SIGTERM, 2.0), (signal.SIGKILL, 5.0))   # probe (signal 0), then the executor's termination shape


@dataclass(frozen=True)
class PendingTurn:
    disposition: str            # recoverable | not_dispatched | unresolved | bootstrap | needs_quiescence (probe_only)
    receipt: Receipt | None
    native_turn: Any            # NativeTurn | None
    detail: str


def quiesce(receipt: Receipt, *, probe_only: bool = False) -> str:
    """Prove the recorded process group gone, stopping it first unless `probe_only`.

    Returns "quiescent" (group gone), "alive" (probe_only and the group still answers; nothing was signalled) or
    "unprovable" (we do not own the pgid, or it survives SIGTERM + grace + SIGKILL + grace).

    R3: the pgid number is reusable once every member of our group has exited. A live leader whose start time differs
    from the one recorded at `launching` is therefore an unrelated process and is never signalled. A leader with no
    `/proc` entry says nothing about lingering members (Linux keeps the number reserved while the group has any), so
    the probe and signals proceed.
    """
    if receipt.pgid is None:
        return "quiescent" if receipt.completion in {"intent", "not_dispatched"} else "unprovable"   # launched, pgid never bound
    if _leader_reused(receipt):
        return "quiescent"                                           # our group is gone; never signal a stranger
    try:
        for sig, grace in _STOP_STEPS[:1] if probe_only else _STOP_STEPS:
            os.killpg(receipt.pgid, sig)
            _wait_until_gone(receipt.pgid, grace)
    except ProcessLookupError:
        return "quiescent"
    except PermissionError:
        return "unprovable"                                          # a reused pgid we do not own
    return "alive" if probe_only else "unprovable"


def _leader_reused(receipt: Receipt) -> bool:
    """R3: a live leader whose start time differs from the one recorded at `launching` is not our process."""
    live = agent_turns.leader_start_time(receipt.pgid)
    return receipt.leader_start_time is not None and live is not None and live != receipt.leader_start_time


def _wait_until_gone(pgid: int, grace: float) -> None:
    """Raise ProcessLookupError as soon as the group is empty; return when `grace` expires with members left."""
    deadline = time.monotonic() + grace
    while True:
        os.killpg(pgid, 0)
        if time.monotonic() >= deadline:
            return
        time.sleep(0.05)


def classify_pending_turn(authority, node, identity, snapshot, workspace, resolved, *, probe_only: bool = False) -> PendingTurn:
    """Reconcile a pending agent turn from its receipt and the native store; sends no prompt (design failure table).

    `probe_only=True` is the read-only resume preflight: it never signals a process and reports a live group as
    `needs_quiescence`, which the preflight admits; the writer-locked `prepare_pending` quiesces and re-classifies.
    A receipt locator is only a candidate until `locate` finds its store and that store shows this attempt's turn.
    """
    pending = snapshot.pending_starts[identity]
    files = authority.run_files.subroot(Path(pending.data["result_path"]).parent)
    try:
        receipt = read_receipt(files)
        result_present = files.exists("result.json")
    finally:
        files.close()
    if receipt is not None and (receipt.turn, receipt.attempt, receipt.input_digest) != (
            identity, pending.data["attempt"], pending.data["input_digest"]):
        raise MemoError("memo_inconsistent", f"receipt of {identity} disagrees with its started reservation")
    if receipt is None or receipt.completion in {"intent", "not_dispatched"}:
        return PendingTurn("not_dispatched", receipt, None, "reserved; the executor never bound a child (no `launching`)")
    first_turn = resolved.predecessor is None
    if receipt.completion == "abandoned":
        return _uncertain(first_turn, receipt, None, "candidate already abandoned")
    stopped = quiesce(receipt, probe_only=probe_only)
    if stopped == "alive":
        return PendingTurn("needs_quiescence", receipt, None, "the dispatched process group is still alive; quiesce under the writer lock")
    if stopped == "unprovable":
        return PendingTurn("unresolved", receipt, None, "the dispatched process group cannot be proven stopped")
    marker = workspace_relative_path(workspace, authority.run_root / pending.data["result_path"])
    return _classify_native(first_turn, receipt, resolved.adapter, marker, result_present)


def _classify_native(first_turn, receipt: Receipt, adapter, marker, result_present) -> PendingTurn:
    """After quiescence: recoverable, provably not dispatched, or uncertain (bootstrap / unresolved)."""
    before = None if receipt.position_before is None else NativePosition.from_record(receipt.position_before)
    try:
        facts = _native_facts(receipt, adapter, marker, before)
    except NativeStoreError as exc:
        return _uncertain(first_turn, receipt, None, f"native store: {exc}")
    if facts is None:
        return _uncertain(first_turn, receipt, None, f"native locator {receipt.locator!r} is missing, ambiguous or unknown")
    head, turn = facts
    if turn is not None and result_present and _agrees(receipt, turn):
        return PendingTurn("recoverable", receipt, turn, "native completion and result evidence intact")
    if turn is None and _head_unchanged(receipt, head, before):
        return PendingTurn("not_dispatched", receipt, None, "group stopped and the adapter proves the predecessor head unchanged")
    return _uncertain(first_turn, receipt, turn, "native state advanced, open or uncertain without an intact result")


def _native_facts(receipt: Receipt, adapter, marker, before):
    """(head, this attempt's completed turn or None) from the store the receipt's locator names; None when it names no
    unique store. The locator is only a candidate until this read binds it to the attempt's own prompt marker."""
    located = None if receipt.locator is None else adapter.locate(receipt.locator)
    if located is None or located.path is None:
        return None
    return adapter.head(located.path), adapter.completed_turn(located.path, after=before, prompt_marker=marker)


def _agrees(receipt: Receipt, turn) -> bool:
    """A `completed` receipt's position is frozen: the store must still show exactly that turn."""
    return receipt.completion != "completed" or receipt.position_after == turn.position.record()


def _head_unchanged(receipt: Receipt, head, before) -> bool:
    """Only a resumed conversation can prove non-advance; a `completed` receipt already saw our turn."""
    return receipt.mode == "resume" and receipt.completion != "completed" and not head.open_turn and head.position == before


def _uncertain(first_turn, receipt, turn, detail) -> PendingTurn:
    return PendingTurn("bootstrap" if first_turn else "unresolved", receipt, turn, detail)


def prepare_pending(authority, node, operands, identity, snapshot, *, resolved, dependencies, context):
    """Writer-locked half of recovery, behind `prepare_agent_attempt`: quiesce, re-classify, then act.

    `recoverable` -> a `PreparedAttempt` for the pending ordinal (`recovered=True`, no new `started`);
    `not_dispatched` -> the pending attempt is closed `failed` (`provider_preparation_failed`, outside
    `DISPATCHED_FAILURE_CODES`; the reducer refuses a new start beside a pending one) and None is returned, so the
    caller allocates the next attempt; an `intent`/`launching` receipt is closed `not_dispatched`, an `unknown` one is
    preserved as it was (the receipt owner never moves `unknown` back);
    anything else keeps the start pending as `agent_turn_unresolved` (`bootstrap` is Task 12).
    """
    classified = classify_pending_turn(authority, node, identity, snapshot, context["workspace"], resolved)
    pending = snapshot.pending_starts[identity]
    if classified.disposition == "not_dispatched":
        if classified.receipt is not None and classified.receipt.completion in {"intent", "launching"}:
            _update(context["run_files"], pending, completion="not_dispatched")
        _require_retained_root(authority.run_files)
        agent_turns.append_record(authority.memo_path, {"record": "failed", "identity": identity, "attempt": pending.data["attempt"],
                                                        "code": "provider_preparation_failed", "exit_info": {}},
                                  run_files=authority.run_files, checked_authority=authority)
        return None
    if classified.disposition != "recoverable":
        raise AgentTurnError("agent_turn_unresolved", f"{identity}: pending attempt {pending.data['attempt']} is "
                             f"{classified.disposition}: {classified.detail}", keep_pending=True)
    return _recovered_attempt(authority, node, operands, identity, snapshot, classified, dependencies, context)


def _update(run_files, pending, **changes) -> None:
    files = run_files.subroot(Path(pending.data["result_path"]).parent)
    try:
        agent_turns.update_receipt(files, **changes)
    finally:
        files.close()


def _recovered_attempt(authority, node, operands, identity, snapshot, classified: PendingTurn, dependencies, context):
    """The pending ordinal re-resolved at its own result path; its input must not have changed since `started`."""
    from . import effect_inputs
    from .effect_execution import PreparedAttempt

    pending = snapshot.pending_starts[identity]
    resolved, parts, _files = effect_inputs._resolve_effect_input(
        authority, node, operands, identity, context["workspace"], context["reader"], None, pending, None,
        pending.data["result_path"], owner=None, launch_cwd=context.get("launch_cwd"), snapshot=snapshot)
    if canonical_sha256(parts) != pending.data["input_digest"]:
        raise effect_inputs._EffectInputDiverged(identity, "the pending agent turn's input changed before recovery")
    if classified.receipt.completion != "completed":
        _update(context["run_files"], pending, position_after=classified.native_turn.position.record(), completion="completed")
    return PreparedAttempt(authority, node, identity, pending.data["attempt"], pending.data["result_path"], pending.data["input_digest"],
                           pending.data["input_parts"], pending.data["implementation_files"],
                           agent_turns.turn_dependencies(resolved, dependencies), replace(resolved, pending=classified),
                           context["workspace"], context["workspace_files"], context["site_classes"], context["provider_executor"],
                           context["run_files"].subroot(Path(pending.data["result_path"]).parent), context.get("launch_cwd"),
                           context.get("stream_output", False), views=context.get("views"), recovered=True)


def recover_pending_turn(attempt):
    """Perform step of a recovered attempt: no dispatch; the outcome is the classified native turn."""
    from .effect_execution import ExternalOutcome
    return ExternalOutcome(result_path=agent_turns._result_path(attempt), agent_turn=attempt.resolved.pending.native_turn)
