"""One bounded coordinator for sequential native-session turns on a run-local agent (K2/K3 shape).

A turn is the checked `agent_turn` node seen as a provider node of the agent's pinned template,
plus the agent and predecessor bindings. Before an append the native head must equal the
predecessor's committed position (D1); the attempt receipt is written `intent` before dispatch,
`launching` (process group + leader start time, R3) when the executor binds the child, and
`completed` only after the native store shows exactly one completed turn bound to this attempt.
Once a child is bound, every outcome other than a conclusively invalid typed result keeps the
`started` row pending (`agent_turn_unresolved`, `keep_pending=True`); resume reconciles it.

Depends on: `ProviderRegistry()` (current templates), the native store adapters (read-only, default
or env-selected homes), the attempt directory's receipt (`agent_sessions`), and the memo journal.
`append_record` and `write_receipt` are module globals so kill-point drivers can hook them.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from orchestrator.providers.control import ProviderExecutionControl
from orchestrator.providers.native_store import NativePosition, NativeStoreError, native_store_adapter
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.types import ProviderSessionMode, ProviderSessionRequest
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256

from .agent_sessions import (
    AgentBinding, Receipt, effective_cwd, merged_receipt, pinned_config_digest, read_receipt, resolve_agent_reference,
    write_receipt,
)
from .attempts import allocate_attempt
from .authority import _require_retained_root
from .commands import workspace_relative_path
from .memo import MemoError, append_record, read_memo
from .providers import ProviderPerformerError, launch_provider, provider_delivery_name_for_template, provider_result, resolve_provider_input


class AgentTurnError(RuntimeError):
    def __init__(self, code, message, *, exit_info=None, violations=None, keep_pending=False):
        super().__init__(message)
        self.code, self.exit_info, self.violations, self.keep_pending = code, exit_info, violations, keep_pending


@dataclass(frozen=True)
class ResolvedTurn:
    agent: AgentBinding
    predecessor: Any            # JournalEntry | None
    provider: Any               # ResolvedProviderInput (policy = allocation model/effort + turn timeout)
    provider_node: dict
    template: Any
    adapter: Any
    input_parts: dict
    delivery_name: str
    pending: Any = None         # PendingTurn | None (Task 11), set with dataclasses.replace


def update_receipt(attempt_files, **changes) -> Receipt:
    """Monotone receipt update; every receipt write of a turn goes through this module's `write_receipt`."""
    updated = merged_receipt(attempt_files, **changes)
    write_receipt(attempt_files, updated)
    return updated


def leader_start_time(pid: int) -> int | None:
    """Start time (clock ticks since boot) of `pid`: field 22 of `/proc/<pid>/stat`, split after the last `)` so a
    command name containing spaces or parentheses cannot shift the fields. None when the pid has no `/proc` entry."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except OSError:
        return None
    fields = raw[raw.rfind(")") + 2:].split()
    return int(fields[19]) if len(fields) >= 20 else None


class AgentTurnControl(ProviderExecutionControl):
    """Records the child's process group and its leader's start time in the receipt when the executor binds it.

    Single use: one control per turn attempt.
    """

    def __init__(self, attempt_files) -> None:
        super().__init__()
        self._attempt_files = attempt_files

    def bind(self, process, pgid: int) -> None:
        update_receipt(self._attempt_files, completion="launching", pgid=pgid, leader_start_time=leader_start_time(pgid))
        super().bind(process, pgid)


def check_origins(node, agent: AgentBinding, template=None, cwd=None) -> None:
    """Defense in depth before dispatch: the agent's provider is a checked origin and its pinned configuration holds."""
    if agent.provider not in node["origins"]:
        raise AgentTurnError("agent_policy_mismatch",
                             f"agent provider {agent.provider!r} is outside the checked origins {node['origins']}")
    if template is not None:
        current = pinned_config_digest(template, agent.policy, cwd)
        if current != agent.config_digest:
            raise AgentTurnError("agent_policy_mismatch",
                                 f"provider template, defaults or cwd changed since allocation ({agent.config_digest} -> {current})")


def predecessor_commit(snapshot, agent_identity: str, *, before_offset: int | None = None):
    """The latest active committed turn of this agent in journal order (single writer => evaluation order).

    Replay passes `before_offset` (the replayed commit's offset): an old turn is checked against its
    historical predecessor, never against turns committed after it (the logical cursor).
    """
    turns = [c for c in snapshot.active_commits.values()
             if c.data["effect_class"] == "agent_turn" and c.data["proof"]["agent"] == agent_identity
             and (before_offset is None or c.offset < before_offset)]
    return max(turns, key=lambda c: c.offset, default=None)


def provider_view(node, agent: AgentBinding) -> dict:
    """The checked turn node seen as a provider node, so the prompt/result owners stay unchanged.

    Its `policy` stays the turn's own (`timeout_sec` operands only); model/effort join the resolved policy.
    """
    return {**{k: v for k, v in node.items() if k not in {"agent", "origins"}}, "class": "provider", "provider": agent.provider}


def _session_template(provider: str):
    template = ProviderRegistry().get(provider)
    if template is None or template.session_support is None:
        raise AgentTurnError("agent_session_unavailable", f"provider {provider!r} has no session_support")
    adapter = native_store_adapter(template.session_support.metadata_mode)
    if adapter is None:
        raise AgentTurnError("agent_session_unavailable", f"no native store adapter for {template.session_support.metadata_mode!r}")
    return template, adapter


def resolve_turn_input(authority, node, operands, identity, workspace, reader, *, snapshot, result_path, launch_cwd,
                       committed_offset: int | None = None, delivery_name: str | None = None) -> ResolvedTurn:
    """`committed_offset` is the replayed commit's offset (replay and reuse paths): the predecessor is then the agent's
    latest turn committed *before* it, and the current template is neither consulted nor re-pinned (a committed turn's
    proof is its own authority, design "Committed and settled"); `delivery_name` is then the committed rendering, and
    `template`/`adapter` are None."""
    agent = resolve_agent_reference(snapshot, operands[0].json_value(), run_id=authority.header["run_id"])
    if committed_offset is None:
        template, adapter = _session_template(agent.provider)
        check_origins(node, agent, template, effective_cwd(launch_cwd, workspace))
        delivery = provider_delivery_name_for_template(template)
    else:
        template = adapter = None
        check_origins(node, agent)
        delivery = delivery_name
    view = provider_view(node, agent)
    provider = resolve_provider_input(view, operands[1:], workspace=workspace, reader=reader,
                                      result_path=workspace_relative_path(workspace, authority.run_root / result_path),
                                      delivery_name=delivery, logical_workspace=launch_cwd is not None)
    provider = replace(provider, policy=turn_policy(agent.policy, provider.policy))
    predecessor = predecessor_commit(snapshot, agent.identity, before_offset=committed_offset)
    continuation = None if predecessor is None else {"turn": predecessor.data["identity"], "proof": predecessor.data["proof"]}
    parts = {**provider.input_parts, "agent": canonical_sha256(agent.record()), "predecessor": canonical_sha256(continuation)}
    return ResolvedTurn(agent, predecessor, provider, view, template, adapter, parts, delivery)


def turn_policy(allocation_policy, turn_policy_values) -> dict:
    """Model/effort come from the allocation only: its keys win over anything the turn carries (defense in depth)."""
    return {**turn_policy_values, **allocation_policy}


def turn_dependencies(resolved: ResolvedTurn, operand_dependencies) -> tuple[str, ...]:
    """The predecessor is a dependency even when the prompt does not consume its result (design, Identity)."""
    extra = () if resolved.predecessor is None else (resolved.predecessor.data["identity"],)
    return tuple(sorted(set(operand_dependencies) | set(extra)))


def _head_or_refuse(resolved: ResolvedTurn):
    """D1: before an append, the native head must equal the recorded committed position of the predecessor."""
    if resolved.predecessor is None:
        return None, None
    proof, predecessor = resolved.predecessor.data["proof"], resolved.predecessor.data["identity"]
    located = resolved.adapter.locate(proof["locator"])
    if located.path is None:
        raise AgentTurnError("agent_session_unavailable",
                             f"native session of {predecessor} is {'ambiguous' if located.ambiguous else 'missing'}")
    try:
        head = resolved.adapter.head(located.path)
    except NativeStoreError as exc:
        raise AgentTurnError("agent_session_unavailable", f"native session of {predecessor} is unreadable") from exc
    expected = NativePosition.from_record(proof["position"])
    if head.open_turn or head.position != expected:
        raise AgentTurnError("agent_session_diverged", f"native head differs from the recorded position of {predecessor}")
    return proof["locator"], expected


def prepare_agent_attempt(authority, node, operands, identity, snapshot, *, ordinal, attempt_directory, result_path,
                          resolved: ResolvedTurn, parts, implementation_files, dependencies, context):
    """All agent-turn start decisions, behind one dispatch line in `runtime.prepare_effect`.

    Order: pending-turn classification (recover / bootstrap / refuse), or with no pending attempt the latest failure
    (later-turn invalid result refuses; first-turn bootstrap abandons) -> D1 head check -> `started` +
    exclusive attempt directory through `allocate_attempt` (so the kill-point hooks on `attempts.append_record`
    fire exactly as for every other class). Other pending effects were refused by `_ensure_effect_can_start`.
    """
    from .effect_execution import PreparedAttempt

    from .agent_turn_recovery import prepare_pending, restart_failed_turn
    if identity in snapshot.pending_starts:
        recovered = prepare_pending(authority, node, operands, identity, snapshot, resolved=resolved,
                                    dependencies=dependencies, context=context)
        if recovered is not None:       # else the pending attempt was closed (not dispatched, or bootstrap): allocate the next one
            return recovered
    else:
        restart_failed_turn(authority, identity, snapshot, context)
    _head_or_refuse(resolved)
    started = dict(record="started", identity=identity, attempt=ordinal, input_digest=canonical_sha256(parts), input_parts=parts,
                   implementation_files=implementation_files, result_path=result_path, time=time.time())
    _require_retained_root(context["run_files"])
    attempt_files = allocate_attempt(context["run_files"], authority.memo_path, started, checked_authority=authority)
    return PreparedAttempt(authority, node, identity, ordinal, result_path, started["input_digest"], parts, implementation_files,
                           turn_dependencies(resolved, dependencies), resolved, context["workspace"], context["workspace_files"],
                           context["site_classes"], context["provider_executor"], attempt_files, context.get("launch_cwd"),
                           context.get("stream_output", False), views=context.get("views"))


def _intent_receipt(attempt, resolved: ResolvedTurn, locator, before) -> Receipt:
    return Receipt(run_id=attempt.authority.header["run_id"], agent=resolved.agent.identity, turn=attempt.identity,
                   attempt=attempt.ordinal, predecessor=None if resolved.predecessor is None else resolved.predecessor.data["identity"],
                   input_digest=attempt.input_digest, adapter=resolved.adapter.metadata_mode, config_digest=resolved.agent.config_digest,
                   mode="resume" if locator else "fresh", locator=locator, pgid=None, leader_start_time=None,
                   position_before=None if before is None else before.record(), position_after=None,
                   completion="intent", result_digest=None)


def _result_path(attempt) -> str:
    """The workspace-relative result path; the prompt renders it, so it also marks this attempt's native user turn."""
    return workspace_relative_path(attempt.workspace, attempt.authority.run_root / attempt.result_path)


def _launch(attempt, resolved: ResolvedTurn, request, handle):
    """Dispatch at most once on a worker; the single-use control gets the execution Future before anything relies on it."""
    control = AgentTurnControl(attempt.attempt_files)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-turn") as pool:
        future = pool.submit(launch_provider, resolved.provider_node, resolved.provider, attempt.identity,
            executor=attempt.provider_executor, attempt_files=attempt.attempt_files, workspace_files=attempt.workspace_files,
            result_path=_result_path(attempt), stream_output=attempt.stream_output, launch_cwd=attempt.launch_cwd,
            logical_workspace_root=attempt.workspace if attempt.launch_cwd is not None else None,
            session_request=request, observation_handle=handle, control=control)
        control.attach_execution_future(future)
        return future.result()


def perform_turn(attempt, *, views=None):
    from .effect_execution import ExternalOutcome

    resolved: ResolvedTurn = attempt.resolved
    locator, before = _head_or_refuse(resolved)
    write_receipt(attempt.attempt_files, _intent_receipt(attempt, resolved, locator, before))   # durable before dispatch
    request = ProviderSessionRequest(mode=ProviderSessionMode.RESUME, session_id=locator) if locator \
        else ProviderSessionRequest(mode=ProviderSessionMode.FRESH)
    handle = None if views is None else views.handle_for(resolved.agent.identity, attempt.identity, attempt.ordinal)
    try:
        execution = _launch(attempt, resolved, request, handle)
        session = execution.provider_session or {}
        turn = _verify_completion(attempt, resolved, session.get("session_id") or locator, before)
        if session.get("is_error"):     # Claude `is_error: true` finalizes as metadata, never as a valid result
            raise _result_invalid(resolved, f"{attempt.identity}: provider reported is_error ({session.get('result_subtype')})")
    except ProviderPerformerError as exc:
        raise _unresolved_or_failed(attempt, exc) from exc
    except AgentTurnError:
        raise                                               # already classified
    except Exception as exc:
        raise _after_launch(attempt, exc) from exc
    finally:
        if views is not None:
            views.idle(resolved.agent.identity)
    return ExternalOutcome(result_path=_result_path(attempt), agent_turn=turn)


def _after_launch(attempt, exc: Exception) -> Exception:
    """Design failure table row 3: once the executor bound a child, an exception this module does not map is an
    unknown append/completion outcome; before `launching` no child was spawned and the ordinary failure path holds."""
    try:
        stored = read_receipt(attempt.attempt_files)
    except MemoError as err:        # receipt evidence is broken: never permission to retry, so keep `started` pending
        return AgentTurnError(err.code, f"{attempt.identity}: {err}", keep_pending=True)
    if stored is None or stored.completion == "intent":
        return exc
    return _unresolved(attempt, stored.locator or _session_from_stdout(attempt), f"{type(exc).__name__} after launch")


def _verify_completion(attempt, resolved, session_id, before):
    located = resolved.adapter.locate(session_id) if session_id else None
    if located is None or located.path is None:
        raise _unresolved(attempt, session_id, "native session has no unique store after dispatch")
    try:
        turn = resolved.adapter.completed_turn(located.path, after=before, prompt_marker=_result_path(attempt))
    except NativeStoreError as exc:
        raise _unresolved(attempt, session_id, "native store is unreadable after dispatch") from exc
    if turn is None:        # an external turn landed after ours, or a later open turn exists: possible advancement
        raise _unresolved(attempt, session_id, "native store does not show exactly one completed turn for this attempt")
    update_receipt(attempt.attempt_files, locator=session_id, position_after=turn.position.record(), completion="completed")
    return turn


def _unresolved(attempt, locator, detail):
    """Always an unresolved, keep-pending error: failing to record `unknown` never turns uncertainty into `failed`."""
    try:
        update_receipt(attempt.attempt_files, locator=locator, completion="unknown")
    except Exception as err:
        detail = f"{detail}; recording `unknown` failed: {type(err).__name__}"
    return AgentTurnError("agent_turn_unresolved", f"{attempt.identity}: {detail}", keep_pending=True)


def unresolved_after_projection(attempt, exc: Exception) -> AgentTurnError:
    """Failure table rows 6/7: after confirmed completion, only an invalid typed result may close `failed`."""
    return AgentTurnError("agent_turn_unresolved", f"{attempt.identity}: {type(exc).__name__} after native completion",
                          keep_pending=True)


def _result_invalid(resolved: ResolvedTurn, detail, *, exit_info=None, violations=None):
    code = "provider_result_invalid" if resolved.predecessor is None else "agent_turn_result_invalid"
    return AgentTurnError(code, detail, exit_info=exit_info, violations=violations)


def _head_unchanged(resolved: ResolvedTurn, receipt: Receipt) -> bool:
    """True only when the adapter proves the resumed conversation did not advance."""
    try:
        located = resolved.adapter.locate(receipt.locator)
        head = None if located.path is None else resolved.adapter.head(located.path)
    except NativeStoreError:
        return False
    return head is not None and not head.open_turn and head.position == NativePosition.from_record(receipt.position_before)


def _proves_no_dispatch(resolved: ResolvedTurn, receipt: Receipt, exc: ProviderPerformerError) -> bool:
    """No child was ever spawned, or the process group is proven empty (stopped first if needed) and only then the
    adapter proves the resumed conversation did not advance."""
    from .agent_turn_recovery import quiesce
    if exc.code == "provider_preparation_failed" and receipt.completion == "intent":
        return True
    return receipt.mode == "resume" and quiesce(receipt) == "quiescent" and _head_unchanged(resolved, receipt)


def _unresolved_or_failed(attempt, exc: ProviderPerformerError):
    """Design failure table rows 3 and 4: only the adapter can prove non-dispatch; exit codes and stdout never do.

    The failure is returned (closing `failed`) only once `not_dispatched` is durable; anything else stays unresolved.
    """
    try:
        receipt = read_receipt(attempt.attempt_files)
    except MemoError as err:        # receipt evidence is broken: never permission to retry, so keep `started` pending
        return AgentTurnError(err.code, f"{attempt.identity}: {err}", keep_pending=True)
    if receipt is not None and _proves_no_dispatch(attempt.resolved, receipt, exc):
        try:
            update_receipt(attempt.attempt_files, completion="not_dispatched")
            return exc
        except Exception as err:
            return _unresolved(attempt, receipt.locator, f"{exc.code}; recording `not_dispatched` failed: {type(err).__name__}")
    # fresh: a locator exists only if the CLI created a conversation
    locator = receipt.locator if receipt is not None and receipt.locator else _session_from_stdout(attempt)
    return _unresolved(attempt, locator, f"{exc.code}: native advance not disproved")


def _session_from_stdout(attempt) -> str | None:
    try:
        text = attempt.attempt_files.read("stdout.txt").decode("utf-8", "replace")
    except (OSError, ValueError):
        return None
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        for key in ("session_id", "thread_id"):
            if isinstance(row, dict) and isinstance(row.get(key), str):
                return row[key]
    return None


def project_turn(attempt, outcome):
    """Typed-result projection after adapter-confirmed completion (receipt `completed`).

    Only a conclusively invalid typed result closes the attempt `failed`. Any other exception is an interruption
    before the prepared proof (failure table row 6, R4): `started` stays pending, the receipt stays `completed`, and
    resume recovers the same ordinal from the receipt and the native store without redispatch.
    """
    resolved: ResolvedTurn = attempt.resolved
    try:
        result, digest = provider_result(resolved.provider_node, resolved.provider, attempt.attempt_files,
                                         attempt.workspace_files, outcome.result_path)
        receipt = update_receipt(attempt.attempt_files, result_digest=digest)   # the prepared proof is durable here
    except ProviderPerformerError as exc:
        raise _result_invalid(resolved, str(exc), exit_info=exc.exit_info, violations=exc.violations) from exc
    except Exception as exc:
        raise unresolved_after_projection(attempt, exc) from exc
    proof = {"adapter": resolved.adapter.metadata_mode, "locator": receipt.locator, "position": receipt.position_after,
             "predecessor": receipt.predecessor, "agent": resolved.agent.identity, "config_digest": resolved.agent.config_digest}
    return result, digest, proof, proof


def settle_turn(authority, resolved, identity, attempt, workspace, site_classes, prepared, committed) -> None:
    """Settlement is local bookkeeping: confirm the commit is active, then append `settled`. Sends no prompt."""
    _require_retained_root(authority.run_files)
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    commit = snapshot.active_commits.get(identity)
    if commit is None or canonical_json_bytes(commit.data) != canonical_json_bytes(committed):
        raise MemoError("memo_inconsistent", "active agent turn commit disagrees before settlement")
    append_record(authority.memo_path, {"record": "settled", "identity": identity, "attempt": attempt, "by": "settle"},
                  run_files=authority.run_files, checked_authority=authority)


def validate_turn(authority, resolved: ResolvedTurn, identity, commit, *, settled) -> None:
    """Replay: the committed proof must agree with the resolved agent and its historical predecessor; no native read,
    no current template (the proof's `adapter` is its own authority) and, settled or not, no attempt receipt (R8)."""
    proof = commit.data["proof"]
    expected = None if resolved.predecessor is None else resolved.predecessor.data["identity"]
    if (proof["agent"], proof["predecessor"], proof["config_digest"]) != (
            resolved.agent.identity, expected, resolved.agent.config_digest):
        raise MemoError("memo_inconsistent", f"agent turn proof of {identity} disagrees with its replayed agent or predecessor")
    if native_store_adapter(proof["adapter"]) is None:
        raise MemoError("memo_inconsistent", f"agent turn proof of {identity} names an unknown native store adapter")


def reconcile_turn(authority, resolved, identity, commit, site_classes) -> None:
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    if (identity, commit.data["attempt"]) in snapshot.settlements:
        return
    validate_turn(authority, resolved, identity, commit, settled=False)
    append_record(authority.memo_path, {"record": "settled", "identity": identity, "attempt": commit.data["attempt"], "by": "reconcile"},
                  run_files=authority.run_files, checked_authority=authority)
