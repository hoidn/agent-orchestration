"""D6: one read-only observation view per agent instance for the life of this process.

Every turn of an agent appends to its one view with turn/idle boundary lines. Targets are transient and never
persisted. Every failure is best-effort: an agent whose view cannot open gets a cached no-op view, so the executor
never opens a second (ordinary) pane for it and the open is not retried each turn.

Depends on: a `ProviderObservationManager` (or None when observation is disabled for the run).
"""

from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)


class _NoView:
    """Stands in for an agent view that failed to open; the executor treats it as a pre-opened handle."""

    def append_display(self, data: bytes) -> None:
        pass

    def check_health(self) -> bool:
        return False

    def finalize(self) -> dict:
        return {}

    close = finalize


class AgentViews:
    """`close` finalizes the views and closes the run's manager."""

    def __init__(self, manager) -> None:
        self._manager, self._handles = manager, {}

    def handle_for(self, agent_identity: str, turn_identity: str, ordinal: int):
        if self._manager is None:
            return None
        handle = self._handles.get(agent_identity) or self._open(agent_identity)
        try:
            handle.append_display(f"\n--- turn {turn_identity} attempt {ordinal} ---\n".encode("utf-8"))
        except Exception as exc:
            logger.warning("[provider_observation] agent view append failed: %s", type(exc).__name__)
        return handle

    def _open(self, agent_identity: str):
        digest = hashlib.sha256(agent_identity.encode("utf-8")).hexdigest()[:16]
        try:
            handle = self._manager.open_observation(invocation_id=f"agent-{digest}", member_id="agent", turn_id="all")
            logger.info("[provider_observation] agent view: tmux -S %s attach -r -t %s (pane %s)",
                        handle.socket_path, self._manager.session_name, handle.target)
        except Exception as exc:
            logger.warning("[provider_observation] agent view unavailable: %s", type(exc).__name__)
            handle = _NoView()
        self._handles[agent_identity] = handle
        return handle

    def idle(self, agent_identity: str) -> None:
        try:
            self._handles[agent_identity].append_display(b"\n--- idle ---\n")
        except Exception:
            pass

    def close(self) -> None:
        for closable in (*self._handles.values(), self._manager):
            try:
                if closable is not None:
                    closable.close()
            except Exception:
                pass
        self._handles.clear()
