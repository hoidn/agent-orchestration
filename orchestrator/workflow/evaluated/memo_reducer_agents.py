"""Journal-only agent guards for the pure memo reducer (R1).

Each function reads the reducer's in-memory state (`active`, `entries`,
`site_class`) and raises through `reducer.inconsistent`; none reads a receipt
or touches the filesystem. Receipt-based guards live in the write preflight and
the resume-time prefix validation.
"""

from __future__ import annotations

from typing import Any

DISPATCHED_FAILURE_CODES = frozenset({"agent_bootstrap_restarted", "agent_turn_result_invalid", "provider_result_invalid"})

_PROOF_FIELDS = {"adapter", "locator", "position", "predecessor", "agent", "config_digest"}


def check_started(reducer, identity: str, kind: str) -> None:
    """An `agent_turn` start requires an active allocation commit and no pending earlier attempt of the turn."""
    if kind != "agent_turn":
        return
    if identity in reducer.pending:
        raise reducer.inconsistent(f"agent turn {identity} starts a new attempt while an earlier attempt is still pending")
    if not any(commit.data["effect_class"] == "agent" for commit in reducer.active.values()):
        raise reducer.inconsistent(f"agent turn {identity} started without an active allocation commit")


def check_committed_proof(reducer, row: dict[str, Any], identity: str) -> None:
    """Validate the inline proof and refuse forks: the predecessor is the agent's latest active committed turn."""
    proof = _agent_turn_proof(reducer, row.get("proof"))
    same_agent = [
        commit for commit in reducer.active.values()
        if commit.data["effect_class"] == "agent_turn" and commit.data["proof"]["agent"] == proof["agent"]
    ]
    latest = max(same_agent, key=lambda commit: commit.offset, default=None)
    expected = None if latest is None else latest.data["identity"]
    if proof["predecessor"] != expected:
        raise reducer.inconsistent(
            f"agent turn {identity} names predecessor {proof['predecessor']!r}; the agent's latest committed turn is {expected!r}"
        )


def check_invalidation_cut(reducer, anchor: int) -> None:
    """Refuse a cut over an `agent_turn` attempt that is pending or failed after dispatch."""
    pending: set[tuple[str, int]] = set()
    for entry in reducer.entries:
        row = entry.data
        if entry.offset < anchor or row["record"] not in {"started", "committed", "failed"}:
            continue
        if reducer.site_class(row["identity"]) != "agent_turn":
            continue
        key = (row["identity"], row["attempt"])
        if row["record"] == "started":
            pending.add(key)
        elif key in pending:
            pending.discard(key)
            if row["record"] == "failed" and row["code"] in DISPATCHED_FAILURE_CODES:
                raise reducer.inconsistent(f"invalidation range covers a dispatched agent turn attempt: {key[0]} #{key[1]}")
    if pending:
        identity, attempt = min(pending)
        raise reducer.inconsistent(f"invalidation range covers a pending agent turn attempt: {identity} #{attempt}")


def _agent_turn_proof(reducer, value: Any) -> dict[str, Any]:
    """Exact proof shape, bound to an active allocation (same pinned configuration) and an active predecessor turn."""
    from .memo_reducer import _text

    proof = _proof_shape(reducer, value)
    allocation = reducer.active.get(_text(proof["agent"], "proof.agent"))
    if allocation is None or allocation.data["effect_class"] != "agent":
        raise reducer.inconsistent("agent turn proof names no active allocation commit")
    descriptor = allocation.data["value"]
    if not isinstance(descriptor, dict) or descriptor.get("config_digest") != proof["config_digest"]:
        raise reducer.inconsistent("agent turn config_digest differs from the allocation's pinned configuration")
    predecessor = proof["predecessor"]
    if predecessor is not None:
        commit = reducer.active.get(_text(predecessor, "proof.predecessor"))
        if commit is None or commit.data["effect_class"] != "agent_turn":
            raise reducer.inconsistent("agent turn predecessor is not an active committed turn")
    return proof


def _proof_shape(reducer, value: Any) -> dict[str, Any]:
    from .memo_reducer import _object, _text

    proof = _object(value, "agent turn proof")
    if set(proof) != _PROOF_FIELDS:
        raise reducer.inconsistent("agent turn proof must contain exactly " + ", ".join(sorted(_PROOF_FIELDS)))
    for field in ("adapter", "locator", "config_digest"):
        _text(proof[field], f"proof.{field}")
    position = _object(proof["position"], "proof.position")
    if set(position) != {"turn_id", "end_line"} or type(position["end_line"]) is not int or position["end_line"] < 1:
        raise reducer.inconsistent("agent turn position must carry turn_id and a positive end_line")
    _text(position["turn_id"], "proof.position.turn_id")
    return proof
