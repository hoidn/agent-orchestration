"""The `--max-cost-usd` check before a provider-class attempt is reserved (specs/cli.md, "Spend cap").

Reads, only when the invocation set a cap: the run's `usage.json` files and the packaged price table.
Writes nothing; a refusal is a preflight error, so no memo row records it and `resume` continues.
Callers: `runtime.prepare_effect` (provider, phased provider, run reference) and
`agent_turns.prepare_agent_attempt` (where a new turn attempt would be allocated, after recovery).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from orchestrator.providers.pricing import load_price_table, prices_model
from orchestrator.providers.types import ProviderSessionMetadataMode
from orchestrator.providers.usage import spent

CAPPED_CLASSES = frozenset({"provider", "provider_phased", "agent_turn", "run_ref"})
METERED_TRANSPORTS = frozenset({ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT.value,
                                ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value})


class SpendCapRefusal(RuntimeError):
    """`spend_cap_reached` or `spend_cap_unmetered`; `preflight` keeps the run without a terminal row."""

    def __init__(self, code: str, message: str, *, spent_usd: float, cap_usd: float, unmetered=()) -> None:
        self.code, self.preflight = code, True
        self.spent_usd, self.cap_usd, self.unmetered = spent_usd, cap_usd, tuple(unmetered)
        super().__init__(message)


def check_spend_cap(authority, snapshot, node: Mapping[str, Any], *, executor=None, policy=None, template=None) -> None:
    """Refuse a new provider-class attempt this cap cannot meter, or once the run's spend reaches the cap.

    `template` is the call's provider template when the caller holds it (agent turns); otherwise it is
    looked up in `executor` by `node["provider"]`. `policy` is the call's policy (`model`).
    """
    cap = authority.spend_cap_usd
    if cap is None or node["class"] not in CAPPED_CLASSES:
        return
    table = load_price_table()
    reason = _unmeterable(node, executor, policy, template, table)
    if reason is not None:
        raise SpendCapRefusal("spend_cap_unmetered", reason, spent_usd=0.0, cap_usd=cap)
    total, unmetered = spent(authority.run_root, table, in_flight=_started_here(authority, snapshot))
    if unmetered:
        raise SpendCapRefusal(
            "spend_cap_unmetered",
            f"{len(unmetered)} earlier provider attempt(s) have no complete priced usage (first: {unmetered[0]}); "
            "a capped run needs metered templates (`<name>_metered`) for its provider steps",
            spent_usd=total, cap_usd=cap, unmetered=unmetered)
    if total >= cap:
        raise SpendCapRefusal("spend_cap_reached", f"spent {total:.6g} USD of a {cap:.6g} USD cap",
                              spent_usd=total, cap_usd=cap)


def _unmeterable(node, executor, policy, template, table) -> str | None:
    kind = node["class"]
    if kind == "run_ref":
        return "a run reference's child run is not capped"
    if kind == "provider_phased":
        return "a phased provider step reports no usage"
    registry = getattr(executor, "registry", None)
    if template is None and registry is not None:
        template = registry.get(node.get("provider"))
    if template is None:
        return f"provider {node.get('provider')!r} has no template"
    session = template.session_support
    transport = session.metadata_mode if kind == "agent_turn" and session is not None else template.command_metadata_mode
    if transport not in METERED_TRANSPORTS:
        metered = f"{template.name}_metered"
        hint = f"`{metered}`" if registry is not None and registry.get(metered) is not None else "a `<name>_metered` template"
        return f"template {template.name!r} reports no usage; bind the step to {hint}"
    model = (policy or {}).get("model") or template.defaults.get("model")
    if not prices_model(table, model):
        return f"model {model!r} has no complete rates in the price table"
    return None


def _started_here(authority, snapshot) -> frozenset[str]:
    """Attempt directories of pending starts this invocation wrote (a pending start from an earlier one was cut off)."""
    since = authority.invocation_started_at
    if since is None:
        return frozenset()
    return frozenset(Path(entry.data["result_path"]).parent.as_posix() for entry in snapshot.pending_starts.values()
                     if entry.data.get("result_path") and entry.data.get("time", 0) >= since)
