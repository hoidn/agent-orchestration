from tests.experiments.orc_structural_search_support import launch_config
"""An I3 episode through run_episode: the Codex mutator command edits the Python parent behind the shims (a scripted
`codex`; no provider is called)."""

import json
import os
import shutil
import sys
from pathlib import Path

from experiments.orc_structural_search.driver import archive, evaluate_and_scan, run_episode
from tests.experiments.orc_structural_search_support import (  # noqa: F401 (pyright, world: fixtures)
    I3_CONFIG, PYTHON_PARENT, capped_copy, pyright, script, world)
from tests.experiments.test_orc_structural_search_driver import sandboxed  # noqa: F401 (fixture)

CODEX_MUTATOR = ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "--model",
                 "gpt-5.6-terra", "--config", "model_reasoning_effort=high"]
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
# the same edit, after running a Python command that imports a module of the workspace (as a mutator checking its
# edit might); the command is not isolated, so it honours the episode environment's PYTHONDONTWRITEBYTECODE
CODEX_IMPORT = CODEX_EDIT + f"""import subprocess
subprocess.run([{sys.executable!r}, "-c", "import dev_check"], check=True)
"""


def i3_episode(world, codex_source):
    (world.fakebin / "codex").write_text(codex_source)
    capped_copy(PYTHON_PARENT, world.tmp / "python")
    evidence = world.tmp / "evidence"
    _, parent = archive(world.tmp / "python", evidence, world.runtime)
    row = run_episode(parent, launch_config(world, I3_CONFIG), interface="I3", mode="unguided", agent_cmd=CODEX_MUTATOR,
                      work_root=world.outside / "work", evidence_root=evidence, episode_index=0, runtime=world.runtime,
                      env={**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}"},
                      solutions={world.task.name: world.solution}, call_cap=160, criterion=world.criterion)
    return row, evidence


def test_an_i3_episode_runs_through_run_episode_with_the_codex_mutator_command(sandboxed, world, pyright):
    row, evidence = i3_episode(world, CODEX_EDIT)
    patch = (evidence / "episodes" / row["episode_id"] / "calls" / "1" / "patch-cand-1.diff").read_text()
    assert (row["interface"], row["agent_cmd"], row["provider_calls"], "b/direct.py" in patch, row["outcome"],
            row["program_digest"].startswith("sha256:"), row["skeleton"] != row["parent_skeleton"]) == (
        "I3", CODEX_MUTATOR, 1, True, "accepted", True, True), row


def test_a_mutator_running_python_in_its_workspace_leaves_no_bytecode_in_the_child(sandboxed, world, pyright):
    row, _ = i3_episode(world, CODEX_IMPORT)
    assert (row["outcome"], row["refusal_code"]) == ("accepted", None), row


def test_an_i3_evaluations_scan_names_other_evaluations_runs(sandboxed, world, pyright):
    work, other = world.outside / "work", "f" * 64  # another evaluation's state directory, W/runs/<evaluation id>
    (work / "runs" / other).mkdir(parents=True)
    script(world, [{"match": "Implement this change", "print": f"cat ../../../runs/{other}/memo.jsonl",
                    "result": {"summary": "s", "account": "a"}}])
    capped_copy(PYTHON_PARENT, world.tmp / "python")
    evidence = world.tmp / "evidence"
    _, root = archive(world.tmp / "python", evidence, world.runtime)
    row = evaluate_and_scan(root, launch_config(world, I3_CONFIG), task=world.task, replicate=1, work_root=work, evidence_root=evidence,
                            runtime=world.runtime, env={**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}",
                                                        "SCRIPTED_RESULTS_FILE": str(world.results)},
                            timeout_sec=600, solutions={world.task.name: world.solution}, holdouts=(), fields={},
                            call_cap=160, criterion=world.criterion)
    hits = json.loads((Path(row["records_dir"]) / "record.json").read_text())["scan"]["hits"]
    assert [hit["pattern"] for hit in hits if other in hit["text"]] == ["other tree or judge"], hits
