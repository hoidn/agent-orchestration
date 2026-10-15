"""Factory calls with equal inputs are two agents; a branch-selected alias is one; an outside agent is reused inside
a loop in order; an agent constructed inside a loop body is a new agent per iteration."""
from __future__ import annotations

import json
import re

import pytest

from tests.agent_session_shims import install_agent_shims, shim_requests
from tests.test_workflow_evaluated_agent_turns import memo_of
from tests.test_workflow_evaluated_invalidate import _cli

HEADER = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule main) (export run)
  (defrecord Note (text String))
  (defprompt ask (:fills (task :text)) -> Note "Task: {task}")
  (defproc make ((model String)) -> Agent :effects ((uses-provider providers.codex))
    (agent providers.codex :model model :effort "low"))
  (defproc turn ((who Agent) (task String)) -> Note :effects ((uses-provider providers.codex))
    (provider-result who :prompt (ask :task task) :timeout-sec 60))
'''

SOURCE = HEADER + '''  (defworkflow run ((task String) (pick Bool)) -> Note
    (let* ((one (make "m"))
           (two (make "m"))
           (chosen (if pick one two))
           (first (turn chosen task))
           (looped (loop/recur :max 3 :state (loop-state (i Int 0) (last String first.text)) :on-exhausted (record Note :text "x")
                     (fn (state)
                       (if (>= state.i 2) (done (record Note :text state.last))
                           (let* ((n (turn one state.last)))
                             (continue (loop-state :like state :i (+ state.i 1) :last n.text)))))))
           (second (turn two looped.text)))
      second)))'''

PER_ITERATION = HEADER + '''  (defworkflow run ((task String)) -> Note
    (loop/recur :max 3 :state (loop-state (i Int 0) (last String task)) :on-exhausted (record Note :text "x")
      (fn (state)
        (if (>= state.i 2) (done (record Note :text state.last))
            (let* ((inner (make "m"))
                   (a (turn inner state.last))
                   (b (turn inner a.text)))
              (continue (loop-state :like state :i (+ state.i 1) :last b.text))))))))'''

PLAN = {"codex": [{"mode": "success", "result": {"text": f"t{i}"}} for i in range(4)], "claude": []}


def _run(tmp_path, monkeypatch, source, *inputs):
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    (tmp_path / "main.orc").write_text(source, encoding="utf-8")
    (tmp_path / "providers.json").write_text(json.dumps({"providers.codex": "codex"}))
    arguments = [part for value in ("task=t", *inputs) for part in ("--input", value)]
    run = _cli(tmp_path, "run", "main.orc", "--source-root", str(tmp_path), "--provider-externs-file", "providers.json", *arguments)
    assert run.returncode == 0, run.stderr
    _root, _authority, classes, memo = memo_of(tmp_path)
    by_class: dict[str, dict[str, dict]] = {"agent": {}, "agent_turn": {}}
    for identity, commit in memo.active_commits.items():   # loop activations resolve to their `[*]` checked site
        by_class.setdefault(classes[re.sub(r"\[\d+\]", "[*]", identity)], {})[identity] = commit.data
    return by_class["agent"], by_class["agent_turn"]


def _named(rows: dict[str, dict], fragment: str) -> list[dict]:
    return [row for identity, row in rows.items() if fragment in identity]


@pytest.mark.parametrize("pick", ["true", "false"])
def test_factory_agents_are_distinct_and_a_branch_alias_and_loop_reuse_continue_one(tmp_path, monkeypatch, pick) -> None:
    agents, t = _run(tmp_path, monkeypatch, SOURCE, f"pick={pick}")
    (one,) = [i for i in agents if "/ one=" in i]; (two,) = [i for i in agents if "/ two=" in i]
    assert len(agents) == 2 and agents[one]["value"]["policy"] == agents[two]["value"]["policy"]   # equal inputs, two identities
    assert agents[one]["value"]["config_digest"] == agents[two]["value"]["config_digest"]          # identical config does not merge
    (first,) = _named(t, "/ first="); (second,) = _named(t, "/ second=")
    loop_turns = sorted(_named(t, "/ loop:state["), key=lambda row: row["identity"])
    chosen, other = (one, two) if pick == "true" else (two, one)
    assert first["proof"]["agent"] == chosen                                                      # the alias is the selected agent
    assert [row["proof"]["agent"] for row in loop_turns] == [one, one]                             # outside agent reused per iteration
    assert second["proof"]["agent"] == two
    # one predecessor chain per agent, in evaluation order
    chain_one = ([first] if pick == "true" else []) + loop_turns
    chain_two = ([first] if pick == "false" else []) + [second]
    for chain in (chain_one, chain_two):
        assert [row["proof"]["predecessor"] for row in chain] == [None] + [row["identity"] for row in chain[:-1]]
        assert len({row["proof"]["locator"] for row in chain}) == 1
    assert chain_one[0]["proof"]["locator"] != chain_two[0]["proof"]["locator"]
    requests = shim_requests(tmp_path)
    assert len(requests) == 4 and len({r["session"] for r in requests}) == 2                     # exactly two native conversations
    assert sum("resume" not in r["argv"] for r in requests) == 2                                   # one fresh start per agent
    assert chosen in first["depends_on"] and other not in first["depends_on"]


def test_agent_constructed_in_a_loop_body_is_a_new_agent_per_iteration(tmp_path, monkeypatch) -> None:
    agents, t = _run(tmp_path, monkeypatch, PER_ITERATION)
    assert len(agents) == 2                                                                        # one allocation per activation
    for iteration in ("loop:state[1]", "loop:state[2]"):
        (agent,) = [i for i in agents if iteration in i]
        (a,) = _named(t, f"{iteration} / else / a="); (b,) = _named(t, f"{iteration} / else / b=")
        assert a["proof"]["agent"] == b["proof"]["agent"] == agent
        assert (a["proof"]["predecessor"], b["proof"]["predecessor"]) == (None, a["identity"])   # no carry across iterations
    requests = shim_requests(tmp_path)
    assert len(requests) == 4 and len({r["session"] for r in requests}) == 2
    assert ["resume" in r["argv"] for r in requests] == [False, True, False, True]
