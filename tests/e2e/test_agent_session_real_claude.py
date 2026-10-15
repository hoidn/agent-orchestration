"""Bounded real-provider smoke (Plan B Task 19): one real Claude agent, two short turns. PAID; opt-in.

Skipped unless `AGENT_SESSION_REAL_SMOKE` is `claude` or `both`. One run spends at most two model turns
(`haiku`, effort `low`). Run from the repo root inside tmux, with no fake observation backend:

    AGENT_SESSION_REAL_SMOKE=claude pytest tests/e2e/test_agent_session_real_claude.py -q -m e2e

Evidence for the PQ-1a qualification record (`docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md`):
the two `committed` agent-turn proofs from the run root's `memo.jsonl` and both attempts' `receipt.json`, with
every locator redacted to its first 8 characters, and `claude --version`.

`check_two_turn_session` is shared with the Codex smoke.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from orchestrator.providers.native_store import native_store_adapter
from tests.test_workflow_evaluated_agent_turns import memo_of, turns
from tests.test_workflow_evaluated_invalidate import _cli

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.environ.get("AGENT_SESSION_REAL_SMOKE") not in {"claude", "both"},
                                                  reason="set AGENT_SESSION_REAL_SMOKE=claude to spend one bounded real smoke")]

SECRET = "marmalade-7"
CLAUDE_AGENT = '(agent providers.claude :model "haiku" :effort "low")'
SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule main) (export run)
  (defrecord Word (word String))
  (defprompt first (:fills (seed :text)) -> Word "Remember the secret word {seed}. Reply with the word `ready` as `word`.")
  (defprompt second (:fills (again :text)) -> Word "What was the secret word I gave you earlier in this conversation? Return it as `word`. ({again})")
  (defworkflow run ((seed String)) -> Word
    (let* ((a AGENT)
           (r1 (provider-result a :prompt (first :seed seed) :timeout-sec 300))
           (r2 (provider-result a :prompt (second :again "no hints") :timeout-sec 300)))
      r2)))'''


def check_two_turn_session(root: Path, agent: str, extern: tuple[str, str]) -> None:
    """Run SOURCE with `agent` through the public CLI (real observation) and check one native session served both turns."""
    (root / "main.orc").write_text(SOURCE.replace("AGENT", agent), encoding="utf-8")
    (root / "providers.json").write_text(json.dumps(dict([extern])))
    run = _cli(root, "run", "main.orc", "--source-root", str(root), "--provider-externs-file", "providers.json",
               "--input", f"seed={SECRET}")
    assert run.returncode == 0, run.stderr
    run_root, _authority, classes, memo = memo_of(root)
    t = turns(memo, classes)
    assert set(t) == {"r1", "r2"}
    first, second = t["r1"], t["r2"]
    assert (first["proof"]["predecessor"], second["proof"]["predecessor"]) == (None, first["identity"])
    locator = first["proof"]["locator"]
    assert locator and second["proof"]["locator"] == locator                    # exactly one native session
    assert SECRET in second["value"]["word"].lower()                            # context retained across turns
    assert native_store_adapter(first["proof"]["adapter"]).locate(locator).path is not None
    receipts = [json.loads((run_root / Path(row["result_path"]).parent / "receipt.json").read_text()) for row in (first, second)]
    assert [(r["completion"], r["locator"], r["mode"]) for r in receipts] == [("completed", locator, "fresh"),
                                                                              ("completed", locator, "resume")]
    assert all(r["pgid"] is not None for r in receipts)
    assert locator not in (run_root / "state.json").read_text()


def test_real_claude_agent_keeps_context_across_two_turns(tmp_path: Path) -> None:
    check_two_turn_session(tmp_path, CLAUDE_AGENT, ("providers.claude", "claude_unrestricted_workspace"))
