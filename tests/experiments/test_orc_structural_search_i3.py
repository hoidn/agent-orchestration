"""An I3 episode through run_episode: the Codex mutator command edits the Python parent behind the shims (a scripted
`codex`; no provider is called)."""

import os
import shutil
import sys

from experiments.orc_structural_search.driver import archive, run_episode
from tests.experiments.orc_structural_search_support import (  # noqa: F401 (pyright, world: fixtures)
    I3_CONFIG, PYTHON_PARENT, pyright, world)
from tests.experiments.test_orc_structural_search_driver import sandboxed  # noqa: F401 (fixture)

CODEX_MUTATOR = ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "--model",
                 "gpt-6.1-sol", "--config", "model_reasoning_effort=high"]
# the scripted `codex`: reads the brief on stdin and gates the parent's DONE on the task's check
CODEX_EDIT = f"""#!{sys.executable} -I
import sys
from pathlib import Path
sys.stdin.read()
old = "    return DONE(summary=change.summary)\\n"
source = Path("direct.py").read_text()
assert source.count(old) == 1, old
Path("direct.py").write_text(source.replace(old, "    if not dev_check().passed:\\n"
                                                 "        return BLOCKED(reason=change.summary)\\n" + old))
"""


def test_an_i3_episode_runs_through_run_episode_with_the_codex_mutator_command(sandboxed, world, pyright):
    (world.fakebin / "codex").write_text(CODEX_EDIT)
    shutil.copytree(PYTHON_PARENT, world.tmp / "python", ignore=shutil.ignore_patterns("__pycache__"))
    evidence = world.tmp / "evidence"
    _, parent = archive(world.tmp / "python", evidence, world.runtime)
    row = run_episode(parent, I3_CONFIG, interface="I3", mode="unguided", agent_cmd=CODEX_MUTATOR,
                      work_root=world.outside / "work", evidence_root=evidence, episode_index=0, runtime=world.runtime,
                      env={**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}"},
                      solutions={world.task.name: world.solution}, call_cap=160)
    patch = (evidence / "episodes" / row["episode_id"] / "calls" / "1" / "patch-cand-1.diff").read_text()
    assert (row["interface"], row["agent_cmd"], row["provider_calls"], "b/direct.py" in patch, row["outcome"],
            row["program_digest"].startswith("sha256:"), row["skeleton"] != row["parent_skeleton"]) == (
        "I3", CODEX_MUTATOR, 1, True, "accepted", True, True), row
