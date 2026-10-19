"""Mutator isolation: the shims mask the evidence root, sibling episodes and the work root's evaluation
directories from an episode's sandboxed CLI calls (scripted mutator and CLI; no provider is called)."""

import sys

from experiments.orc_structural_search.driver import archive, run_episode
from tests.experiments.orc_structural_search_support import world  # noqa: F401 (fixture)
from tests.experiments.test_orc_structural_search_driver import (  # noqa: F401 (sandboxed: fixture)
    MUTATOR_ONE_CALL, config_of, fake_claude, mode1, sandboxed)


def test_a_mutator_cannot_read_a_siblings_file_or_the_evidence_root(sandboxed, world):
    work, evidence = world.outside / "work", world.evidence  # both outside the sandbox's private /tmp
    sibling = work / "episodes" / "episode-0" / "cand-1" / "direct.orc"
    sibling.parent.mkdir(parents=True)
    sibling.write_text("sibling-edit\n")
    _, parent = archive(world.candidate, evidence, world.runtime)
    (evidence / "log.jsonl").write_text('{"kind": "evidence-row"}\n')
    reads = f"{sibling} {evidence / 'log.jsonl'} direct.orc ../py/orchestrator/__init__.py"
    env = fake_claude(world, f"#!/bin/sh\ncat {reads} 2>/dev/null\nexit 0\n")
    (world.outside / "mutator.py").write_text(MUTATOR_ONE_CALL)
    row = run_episode(parent, config_of(), interface="I1", mode="unguided", episode_index=1, work_root=work,
                      agent_cmd=[sys.executable, "-I", str(world.outside / "mutator.py")], evidence_root=evidence,
                      runtime=world.runtime, env=env, solutions={world.task.name: world.solution}, call_cap=160)
    out = (evidence / "episodes" / row["episode_id"] / "calls" / "1" / "stdout.txt").read_text()
    names = ("episodes", "records", "runs", "agents", "env-manifests")
    assert ((parent / "direct.orc").read_text() in out, "__version__" in out, "sibling-edit" in out,
            "evidence-row" in out, row["hidden_roots"], row["outcome"] != "incident") == (
        True, True, False, False, [str(evidence.resolve()), *(str(work.resolve() / name) for name in names)], True)


def test_hide_paths_from_the_command_line_reach_the_episode(sandboxed, world):
    hidden = world.outside / "other-run"
    _, rows, _ = mode1(world, ["direct"], hide=[hidden])
    assert [str(hidden) in row["hidden_roots"] for row in rows if row["kind"] == "episode"] == [True] * 3
