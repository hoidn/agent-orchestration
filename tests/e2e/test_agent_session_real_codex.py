"""Bounded real-provider smoke (Plan B Task 20): one real Codex agent, two short turns. PAID; opt-in.

Skipped unless `AGENT_SESSION_REAL_SMOKE` is `codex` or `both`. One run spends at most two model turns
(`gpt-6-luna`, effort `low`, the model authorized for the native-session probe). Run from the repo root inside
tmux, with no fake observation backend:

    AGENT_SESSION_REAL_SMOKE=codex pytest tests/e2e/test_agent_session_real_codex.py -q -m e2e

Evidence for the PQ-1a qualification record (`docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md`):
the two `committed` agent-turn proofs from the run root's `memo.jsonl` and both attempts' `receipt.json`, with
every locator redacted to its first 8 characters, and `codex --version`.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.e2e.test_agent_session_real_claude import check_two_turn_session

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.environ.get("AGENT_SESSION_REAL_SMOKE") not in {"codex", "both"},
                                                  reason="set AGENT_SESSION_REAL_SMOKE=codex to spend one bounded real smoke")]

CODEX_AGENT = '(agent providers.codex :model "gpt-6-luna" :effort "low")'


def test_real_codex_agent_keeps_context_across_two_turns(tmp_path: Path) -> None:
    check_two_turn_session(tmp_path, CODEX_AGENT, ("providers.codex", "codex"))
