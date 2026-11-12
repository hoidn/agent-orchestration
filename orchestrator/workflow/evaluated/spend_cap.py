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


# Why a `spend_cap_unmetered` refusal was raised; `orchestrator/cli/recovery.py` names the fix for each.
TEMPLATE_UNMETERED, MODEL_UNPRICED, STEP_UNCAPPED, ATTEMPT_UNMETERED = (
    "template_unmetered", "model_unpriced", "step_uncapped", "attempt_unmetered")


class SpendCapRefusal(RuntimeError):
    """`spend_cap_reached` or `spend_cap_unmetered` (with its `cause`); `preflight` keeps the run without a terminal row."""

    def __init__(self, code: str, message: str, *, spent_usd: float, cap_usd: float, unmetered=(),
                 cause: str | None = None) -> None:
        self.code, self.preflight, self.cause = code, True, cause
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
    refused = _unmeterable(node, executor, policy, template, table)
    if refused is not None:
        cause, reason = refused
        raise SpendCapRefusal("spend_cap_unmetered", reason, spent_usd=0.0, cap_usd=cap, cause=cause)
    total, unmetered = spent(authority.run_root, table, in_flight=_in_flight(authority, snapshot))
    if unmetered:
        raise SpendCapRefusal(
            "spend_cap_unmetered",
            f"{len(unmetered)} earlier provider attempt(s) were cut off or have no complete priced usage "
            f"(first: {unmetered[0]})", spent_usd=total, cap_usd=cap, unmetered=unmetered, cause=ATTEMPT_UNMETERED)
    if total >= cap:
        raise SpendCapRefusal("spend_cap_reached", f"spent {total:.6g} USD of a {cap:.6g} USD cap",
                              spent_usd=total, cap_usd=cap)


def _unmeterable(node, executor, policy, template, table) -> tuple[str, str] | None:
    """(cause, reason) when this call cannot be metered, else None."""
    kind = node["class"]
    if kind == "run_ref":
        return STEP_UNCAPPED, "a run reference's child run is not capped"
    if kind == "provider_phased":
        return STEP_UNCAPPED, "a phased provider step reports no usage"
    registry = getattr(executor, "registry", None)
    if template is None and registry is not None:
        template = registry.get(node.get("provider"))
    if template is None:
        return TEMPLATE_UNMETERED, f"provider {node.get('provider')!r} has no template"
    session = template.session_support
    transport = session.metadata_mode if kind == "agent_turn" and session is not None else template.command_metadata_mode
    if transport not in METERED_TRANSPORTS:
        metered = f"{template.name}_metered"
        hint = f"`{metered}`" if registry is not None and registry.get(metered) is not None else "a `<name>_metered` template"
        return TEMPLATE_UNMETERED, f"template {template.name!r} reports no usage; bind the step to {hint}"
    model = (policy or {}).get("model") or template.defaults.get("model")
    if not prices_model(table, model):
        return MODEL_UNPRICED, f"model {model!r} has no complete rates in the price table"
    return None


def pending_attempts(snapshot) -> frozenset[str]:
    """Run-relative attempt directories of the memo's pending starts."""
    return frozenset(Path(entry.data["result_path"]).parent.as_posix() for entry in snapshot.pending_starts.values()
                     if entry.data.get("result_path"))


def _in_flight(authority, snapshot) -> frozenset[str]:
    """Pending attempts this invocation started: those not already pending when it began (`cut_off_attempts`)."""
    cut_off = authority.cut_off_attempts
    return frozenset() if cut_off is None else pending_attempts(snapshot) - cut_off
