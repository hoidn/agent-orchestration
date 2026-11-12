"""The `--max-cost-usd` check before a provider-class attempt is reserved (specs/cli.md, `run`).

Reads, only when the invocation set a cap: the run's `usage.json` files and the packaged price table.
Writes nothing; a refusal is a preflight error, so no memo row records it and `resume` continues.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from orchestrator.providers.pricing import load_price_table
from orchestrator.providers.usage import spent

PROVIDER_CLASSES = frozenset({"provider", "provider_phased", "agent_turn"})


class SpendCapRefusal(RuntimeError):
    """`spend_cap_reached` or `spend_cap_unmetered`; `preflight` keeps the run without a terminal row."""

    def __init__(self, code: str, message: str, *, spent_usd: float, cap_usd: float, unmetered=()) -> None:
        self.code, self.preflight = code, True
        self.spent_usd, self.cap_usd, self.unmetered = spent_usd, cap_usd, tuple(unmetered)
        super().__init__(message)


def check_spend_cap(authority, node: Mapping[str, Any], snapshot) -> None:
    """Refuse a new provider call once the run's priced usage reaches the cap or any is unknown."""
    cap = authority.spend_cap_usd
    if cap is None or node["class"] not in PROVIDER_CLASSES:
        return
    in_flight = frozenset(Path(entry.data["result_path"]).parent.as_posix()
                          for entry in snapshot.pending_starts.values() if entry.data.get("result_path"))
    total, unmetered = spent(authority.run_root, load_price_table(), in_flight=in_flight)
    if unmetered:
        raise SpendCapRefusal(
            "spend_cap_unmetered",
            f"{len(unmetered)} earlier provider attempt(s) have no priced usage (first: {unmetered[0]}); "
            "a capped run needs metered templates (`<name>_metered`) for its provider steps",
            spent_usd=total, cap_usd=cap, unmetered=unmetered)
    if total >= cap:
        raise SpendCapRefusal("spend_cap_reached", f"spent {total:.6g} USD of a {cap:.6g} USD cap",
                              spent_usd=total, cap_usd=cap)
