"""Run-local agent allocation (ordinary `agent` effect) and the attempt receipt of a turn.

Allocation never launches a provider: it pins the provider id, the model/effort policy and a
digest of the registry template's native configuration (I7) into a runtime-owned `Agent`
descriptor `{run_id, identity, provider, policy, config_digest}` committed as an ordinary
memo value. A handle decodes only against this run's active allocation commit with the same
descriptor. Depends on: `ProviderRegistry()` (current templates), the attempt directory's
`WorkspaceFiles` (`result.json`, `receipt.json`). `write_receipt` is the one receipt writer and
enforces monotonicity; `read_receipt` refuses a malformed receipt as `memo_inconsistent`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping

from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.workspace_files import WorkspaceFiles

from .memo import MemoError, MemoSnapshot
from .values import EvaluatedValue, coerce_evaluated_value

AGENT_DESCRIPTOR = {"kind": "primitive", "name": "Agent"}
RECEIPT_SCHEMA = "agent_turn_receipt.v1"


@dataclass(frozen=True)
class AgentBinding:
    identity: str
    run_id: str
    provider: str
    policy: Mapping[str, str]
    config_digest: str

    def record(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "identity": self.identity, "provider": self.provider,
                "policy": dict(self.policy), "config_digest": self.config_digest}


def pinned_config_digest(template, policy: Mapping[str, str], launch_cwd) -> str:
    """Everything the conversation's native configuration depends on, pinned once at allocation."""
    session = template.session_support
    return canonical_sha256({
        "name": template.name, "command": list(template.command), "input_mode": template.input_mode.value,
        "defaults": dict(template.defaults),
        "bindings": {name: binding.target_param for name, binding in template.call_policy_bindings.items()},
        "session": None if session is None else {
            "metadata_mode": session.metadata_mode, "fresh": list(session.fresh_command),
            "resume": list(session.resume_command or [])},
        "policy": dict(policy), "launch_cwd": None if launch_cwd is None else str(launch_cwd),
    })


def effective_cwd(launch_cwd, workspace):
    """The directory a turn's CLI runs in; Claude keys its native store by it, so it is pinned at allocation."""
    return launch_cwd or workspace


def resolve_allocation_input(node: Mapping[str, Any], operands) -> tuple[dict[str, Any], dict[str, str]]:
    """Pin provider and policy once; both parts enter the ordinary input digest."""
    policy = dict(zip(node["policy"], (value.json_value() for value in operands), strict=True))
    if any(not isinstance(value, str) for value in policy.values()):
        raise MemoError("memo_inconsistent", "agent policy operands must be strings")
    resolved = {"provider": node["provider"], "policy": policy}
    return resolved, {"provider": canonical_sha256(node["provider"]), "policy": canonical_sha256(policy)}


def perform_allocation(attempt):
    """Write the descriptor as the attempt result; no provider, no session, no process."""
    from orchestrator.providers.registry import ProviderRegistry

    from .effect_execution import ExternalOutcome

    provider, policy = attempt.resolved["provider"], attempt.resolved["policy"]
    template = ProviderRegistry().get(provider)
    if template is None:
        raise MemoError("memo_inconsistent", f"agent provider {provider!r} is not registered")
    binding = AgentBinding(attempt.identity, attempt.authority.header["run_id"], provider, policy,
                           pinned_config_digest(template, policy, effective_cwd(attempt.launch_cwd, attempt.workspace)))
    attempt.attempt_files.write_atomic("result.json", canonical_json_bytes(binding.record()))
    return ExternalOutcome(result_path=attempt.result_path)


def allocation_result(attempt) -> tuple[EvaluatedValue, str]:
    raw = attempt.attempt_files.read("result.json")
    value = coerce_evaluated_value(json.loads(raw), AGENT_DESCRIPTOR, committed_result_path=attempt.result_path,
                                   context="agent allocation result")
    return value, "sha256:" + hashlib.sha256(raw).hexdigest()


def resolve_agent_reference(snapshot: MemoSnapshot, value: Any, *, run_id: str) -> AgentBinding:
    """Decode a handle only against this run's active allocation commit with the same pinned configuration."""
    if not isinstance(value, Mapping) or value.get("run_id") != run_id:
        raise MemoError("memo_inconsistent", "agent reference does not belong to this run")
    commit = snapshot.active_commits.get(value.get("identity"))
    if commit is None or commit.data["effect_class"] != "agent" or commit.data["value"] != dict(value):
        raise MemoError("memo_inconsistent", f"agent reference has no matching active allocation: {value.get('identity')!r}")
    return AgentBinding(value["identity"], run_id, value["provider"], dict(value["policy"]), value["config_digest"])


@dataclass(frozen=True)
class Receipt:
    run_id: str
    agent: str
    turn: str
    attempt: int
    predecessor: str | None
    input_digest: str
    adapter: str
    config_digest: str
    mode: str                          # "fresh" | "resume"
    locator: str | None
    pgid: int | None
    leader_start_time: int | None      # R3: /proc/<pgid>/stat field 22, recorded with pgid at `launching`
    position_before: dict | None
    position_after: dict | None
    completion: str                    # intent | launching | completed | not_dispatched | unknown | abandoned
    result_digest: str | None
    schema: str = RECEIPT_SCHEMA


# Allowed `completion` moves; `completed -> completed` adds the prepared `result_digest`. A move into
# `not_dispatched` is only possible before the adapter saw an advance, so it never licenses a retry over one.
_TRANSITIONS = {
    "intent": {"launching", "not_dispatched", "unknown"},
    "launching": {"unknown", "completed", "not_dispatched"},
    "unknown": {"completed", "abandoned"},
    "completed": {"completed", "abandoned"},
    "not_dispatched": set(),
    "abandoned": set(),
}
_BINDING_FIELDS = ("run_id", "agent", "turn", "attempt", "input_digest", "predecessor")
_TEXT, _OPTIONAL_TEXT, _OPTIONAL_INT = (str,), (str, type(None)), (int, type(None))
_FIELD_TYPES = {"run_id": _TEXT, "agent": _TEXT, "turn": _TEXT, "attempt": (int,), "predecessor": _OPTIONAL_TEXT,
                "input_digest": _TEXT, "adapter": _TEXT, "config_digest": _TEXT, "mode": _TEXT, "locator": _OPTIONAL_TEXT,
                "pgid": _OPTIONAL_INT, "leader_start_time": _OPTIONAL_INT, "completion": _TEXT, "result_digest": _OPTIONAL_TEXT,
                "schema": _TEXT}
_ENUMS = {"mode": {"fresh", "resume"}, "completion": set(_TRANSITIONS), "schema": {RECEIPT_SCHEMA}}


def _check_receipt(receipt: Receipt) -> None:
    """Field types and enums of one receipt; a malformed receipt is unreadable evidence (`memo_inconsistent`)."""
    from orchestrator.providers.native_store import NativePosition

    wrong = [name for name, kinds in _FIELD_TYPES.items() if type(getattr(receipt, name)) not in kinds]
    wrong += [name for name, allowed in _ENUMS.items() if getattr(receipt, name) not in allowed]
    if wrong or receipt.attempt < 1:
        raise MemoError("memo_inconsistent", f"agent turn receipt is malformed: {wrong or 'attempt'}")
    try:
        for position in (receipt.position_before, receipt.position_after):
            if position is not None:
                NativePosition.from_record(position)
    except ValueError as exc:
            raise MemoError("memo_inconsistent", f"agent turn receipt is malformed: {exc}") from exc


def write_receipt(files: WorkspaceFiles, receipt: Receipt) -> None:
    """The one receipt writer: creation, or a monotone update of the stored receipt.

    Binding fields never change and `completion` moves only along `_TRANSITIONS`.
    """
    _check_receipt(receipt)
    current = read_receipt(files)
    if current is not None:
        changed = [name for name in _BINDING_FIELDS if getattr(current, name) != getattr(receipt, name)]
        if changed or receipt.completion not in _TRANSITIONS[current.completion]:
            raise MemoError("memo_inconsistent", f"receipt update is not monotone: binding {changed}, "
                            f"completion {current.completion} -> {receipt.completion}")
    files.write_atomic("receipt.json", canonical_json_bytes(asdict(receipt)))


def merged_receipt(files: WorkspaceFiles, **changes) -> Receipt:
    """The stored receipt with `changes` applied: a field already set keeps its value unless `changes` gives one.

    Callers write the result through `write_receipt`, which refuses a non-monotone update.
    """
    current = read_receipt(files)
    if current is None:
        raise MemoError("memo_inconsistent", "receipt update without a stored receipt")
    return replace(current, **{name: value for name, value in changes.items() if value is not None or getattr(current, name) is None})


def read_receipt(files: WorkspaceFiles) -> Receipt | None:
    try:
        raw = files.read("receipt.json")
    except FileNotFoundError:
        return None
    try:
        receipt = Receipt(**json.loads(raw))
    except (ValueError, TypeError) as exc:
        raise MemoError("memo_inconsistent", f"agent turn receipt is unreadable: {exc}") from exc
    _check_receipt(receipt)
    return receipt
