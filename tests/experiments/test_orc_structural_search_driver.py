"""Mode 1 driver: catalog enumeration and unguided I1 episodes with a scripted mutator and scripted providers
(no provider is called)."""

import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from experiments.orc_structural_search import ledger
from experiments.orc_structural_search.briefs import episode_brief
from experiments.orc_structural_search.config import ExperimentConfig, load_config
from experiments.orc_structural_search.driver import (
    archive, check_roots, check_solutions, enumerate_catalog, episode_workspace, evaluate_all, evaluate_and_scan,
    judge_child, run_episode)
from experiments.orc_structural_search.mode1 import readout, run_mode1
from experiments.orc_structural_search.ledger import CallCapExceeded, max_provider_calls
from experiments.orc_structural_search.records import read_records
from experiments.orc_structural_search.sites import eligible_sites, site_manifest
from tests.experiments.compare_harness_support import skip_without_sandbox
from tests.experiments.orc_structural_search_support import (  # noqa: F401 (world: fixture)
    MUTATOR, MUTATOR_I2, REPO, SEEDS, script, world)

CATALOG = ["direct", "plan_then_implement", "implement_review_revise", "best_of_n", "implement_check_diagnose_repair"]
CONFIG = {"mutable_files": ["direct.orc"], "mutable_definitions": ["run"], "condition": "topology-only",
          "interface": "I1", "entry_workflow": "direct::run", "source_root": ".", "providers_file": "providers.json",
          "command_boundaries_file": "commands.json", "episode_wall_clock_sec": 120, "criterion_sha256": None}
CHANGE = {"summary": "set VALUE", "account": "edited pkg"}
# implement_review_revise's review prompt has no entry: its provider exits nonzero and the run fails
ANSWERS = [
    {"match": "Implement this change", "result": CHANGE},
    {"match": "Execute this plan", "result": CHANGE},
    {"match": "Plan this task", "result": {"steps": ["edit pkg"]}},
    {"match": "Review this plan", "result": {"findings": []}},
    {"match": "Revise the plan", "result": {"steps": ["edit pkg"]}},
    {"match": "You are writing proposal", "result": {"approach": "edit pkg"}},
    {"match": "Two engineers", "result": {"winner": 1, "reason": "first"}},
]
# a prompt-only child: the coder prompt's wording changes, nothing else
PROMPT_EDIT = f"""#!{sys.executable} -I
from pathlib import Path
source = Path("direct.orc").read_text()
Path("direct.orc").write_text(source.replace("Implement this change there", "Make this change there"))
"""
# a role swap: the same skeleton, another provider extern
ROLE_SWAP = f"""#!{sys.executable} -I
from pathlib import Path
source = Path("direct.orc").read_text()
Path("direct.orc").write_text(source.replace("providers.coder", "providers.planner"))
"""


@pytest.fixture
def sandboxed():
    skip_without_sandbox()


def mode1(world, seeds, **launch):
    script(world, ANSWERS)
    (world.tmp / "config.json").write_text(json.dumps(CONFIG))
    mutator = world.outside / "mutator.py"
    mutator.write_text(MUTATOR)
    env = {**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}", "SCRIPTED_RESULTS_FILE": str(world.results)}
    evidence = world.tmp / "evidence"
    readout = run_mode1(world.tmp / "config.json", seeds=[SEEDS / f"{name}.orc" for name in seeds], tasks=[world.task],
                        work_root=world.outside / "work", evidence_root=evidence, episodes=3,
                        agent_cmd=[sys.executable, "-I", str(mutator)], replicates=1, runtime=world.runtime, env=env,
                        timeout_sec=600, solutions={world.task.name: world.solution}, call_cap=160, concurrency=1, **launch)
    return readout, read_records(evidence / "log.jsonl"), evidence


def test_mode1_enumerates_catalog_and_samples_unguided_episodes(sandboxed, world):
    readout, _, evidence = mode1(world, CATALOG)
    assert ({seed: len(row["outcomes"]) for seed, row in readout["catalog"].items()},
            readout["episodes"], readout["refused"], readout["distinct_skeletons"], readout["revisit_rate"],
            json.loads((evidence / "readout.json").read_text()) == readout) == (
        dict.fromkeys(CATALOG, 1), {"accepted": 2, "rejected": 1}, {"frozen_surface_changed": 1}, 2, 0.5, True)


def test_rejected_proposal_never_enters_evaluation(sandboxed, world):
    _, rows, evidence = mode1(world, ["direct"])
    (rejected,) = [row for row in rows if row["kind"] == "episode" and row["outcome"] == "rejected"]
    evaluated = [row["candidate_id"] for row in rows if row["kind"] == "evaluation" and row["mode"] == "unguided"]
    assert (len(evaluated), rejected["candidate_id"] in evaluated,
            (evidence / "candidates" / rejected["candidate_id"]).exists()) == (2, False, False)


def test_log_records_carry_identities_and_unavailable_markers(sandboxed, world):
    _, rows, _ = mode1(world, ["direct"])
    (catalog,) = [row for row in rows if row["mode"] == "catalog"]
    episodes = [row for row in rows if row["kind"] == "episode"]
    evaluations = [row for row in rows if row["kind"] == "evaluation"]
    assert all(row["evaluation_id"] and row["env_manifest_digest"].startswith("sha256:")
               and row["run_id"] != "unavailable" and row["task_id"] == world.task.name
               and (row["scan_hits"], row["scan_pending"], row["consumption"]) == (0, False, "unavailable")
               for row in evaluations)
    assert all(row["episode_id"] and row["parent_candidate_id"] == catalog["candidate_id"]
               and (row["interface"], row["mode"], row["consumption"]) == ("I1", "unguided", "unavailable")
               and (row["provider_calls"], row["scan_hits"], row["scan_pending"]) == (0, 0, False)
               for row in episodes)


@pytest.mark.parametrize("work, evidence", [("w", "w/e"), ("e/w", "e"), ("same", "same")])
def test_nested_or_equal_roots_are_refused(tmp_path, work, evidence):
    with pytest.raises(ValueError, match="must not nest"):
        check_roots(tmp_path / work, tmp_path / evidence)


def test_a_task_without_a_solution_hash_is_refused_before_any_evaluation(tmp_path):
    with pytest.raises(ValueError, match="no solution hash for task packages \\['task-1'\\]"):
        enumerate_catalog([SEEDS / "direct.orc"], ExperimentConfig(**CONFIG | {"mutable_files": ("direct.orc",),
                                                                              "mutable_definitions": ("run",)}),
                          tasks=[tmp_path / "task-1"], work_root=tmp_path / "work", evidence_root=tmp_path / "evidence",
                          replicates=1, runtime=tmp_path / "runtime", env={}, timeout_sec=1, solutions={}, call_cap=160)
    assert not (tmp_path / "work").exists()


def test_a_child_whose_unexported_entry_changes_result_type_is_refused(tmp_path):
    parent, child = tmp_path / "parent", tmp_path / "child"
    shutil.copytree(SEEDS, parent, ignore=shutil.ignore_patterns("__pycache__"))
    entry = parent / "direct.orc"
    entry.write_text(entry.read_text().replace("  (export run)\n", ""))  # an unexported entry's signature is mutable
    shutil.copytree(parent, child)
    source = Path(child / "direct.orc").read_text()
    (child / "direct.orc").write_text(source.replace("    -> Outcome\n", "    -> Change\n").replace(
        "(variant Outcome DONE :summary change.summary)", "change"))
    config = ExperimentConfig(**CONFIG | {"mutable_files": ("direct.orc",), "mutable_definitions": ("run",)})
    assert judge_child(parent, child, config, runtime=REPO)["refusal_code"] == "slot_type_changed"


def config_of(**overrides) -> ExperimentConfig:
    data = CONFIG | overrides
    return ExperimentConfig(**data | {key: tuple(data[key]) for key in ("mutable_files", "mutable_definitions")})


def episode(world, mutator_source, config, tamper=False, env=os.environ, call_cap=160, index=0, site=None):
    """One episode (compile only, no evaluation) against the archived seed catalog: I2 with `site`, else I1."""
    evidence = world.tmp / "evidence"
    _, parent = archive(world.candidate, evidence, world.runtime)
    if tamper:
        (parent / "direct.orc").write_text((parent / "direct.orc").read_text() + "\n;; edited in the archive\n")
    mutator = world.outside / f"mutator-{index}.py"
    mutator.write_text(mutator_source)
    row = run_episode(parent, config, interface="I1" if site is None else "I2",
                      mode="unguided" if site is None else "adaptive", agent_cmd=[sys.executable, "-I", str(mutator)],
                      work_root=world.outside / "work", evidence_root=evidence, episode_index=index,
                      runtime=world.runtime, env=env, solutions={world.task.name: world.solution},
                      call_cap=call_cap, site=site)
    return row, evidence


# a child that compiles but whose loop bound is a variable around the coder call: its planned maximum is unbounded
UNBOUNDED = f"""#!{sys.executable} -I
from pathlib import Path
source = Path("direct.orc").read_text()
call = source[source.index("(provider-result"):source.index(":timeout-sec 5400)") + len(":timeout-sec 5400)")]
loop = ("(loop/recur :max tries :state (record Change :summary \\"none\\" :account \\"none\\") :on-exhausted state "
        f"(fn (state) (let* ((next {{call}})) (done next))))")
Path("direct.orc").write_text(source.replace("(let* ((change " + call, "(let* ((tries 2) (change " + loop))
"""


def test_a_child_with_an_unbounded_planned_maximum_is_refused_and_never_archived(world):
    row, evidence = episode(world, UNBOUNDED, config_of())
    assert (row["outcome"], row["refusal_code"], (evidence / "candidates" / row["candidate_id"]).exists()) == (
        "rejected", "unbounded_calls", False)


def test_a_prompt_only_child_is_accepted_with_its_parents_skeleton(world):
    row, _ = episode(world, PROMPT_EDIT, config_of(condition="prompt-only",
                                                   mutable_definitions=["run", "implement-prompt"]))
    assert (row["outcome"], row["skeleton"] == row["parent_skeleton"]) == ("accepted", True)


def test_each_episode_diff_is_kept_in_the_evidence_root(world):
    row, evidence = episode(world, PROMPT_EDIT, config_of(condition="prompt-only",
                                                          mutable_definitions=["run", "implement-prompt"]))
    diff = (evidence / "episodes" / f"{row['episode_id']}.diff").read_text()
    assert "+++ b/direct.orc" in diff and "Make this change there" in diff


def test_a_role_swap_child_counts_as_allocation_distinct_not_terminal_only(world):
    row, _ = episode(world, ROLE_SWAP, config_of())
    result = readout([row])
    assert (row["outcome"], row["provider_allocation"], row["parent_provider_allocation"],
            result["allocation_distinct"], result["terminal_only_share"]) == (
        "accepted", {"run": ["providers.planner"]}, {"run": ["providers.coder"]}, 1, 0.0)


def test_a_tampered_archived_parent_is_refused_before_the_episode(world):
    with pytest.raises(RuntimeError, match="archive"):
        episode(world, ROLE_SWAP, config_of(), tamper=True)
    assert not (world.outside / "work" / "episodes").exists()


def test_a_tampered_archived_candidate_is_refused_before_its_evaluation(world):
    evidence = world.tmp / "evidence"
    _, root = archive(world.candidate, evidence, world.runtime)
    (root / "providers.json").write_text("{}\n")
    with pytest.raises(RuntimeError, match="archive"):
        evaluate_and_scan(root, config_of(), task=world.task, replicate=1, work_root=world.outside / "work",
                          evidence_root=evidence, runtime=world.runtime, env=os.environ, timeout_sec=1,
                          solutions={world.task.name: world.solution}, holdouts=(), fields={}, call_cap=160)
    assert not (world.outside / "work").exists()


def test_an_evidence_root_that_already_holds_a_log_is_refused(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps(CONFIG))
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "log.jsonl").write_text("")
    with pytest.raises(FileExistsError, match="log.jsonl"):
        run_mode1(tmp_path / "config.json", seeds=[], tasks=[], work_root=tmp_path / "work",
                  evidence_root=tmp_path / "evidence", episodes=0, agent_cmd=[], replicates=1,
                  runtime=tmp_path / "runtime", env={}, timeout_sec=1, solutions={}, call_cap=160)


@pytest.mark.parametrize("solution", ["abc12", "deadbeefdeadbeef", "tree"])
def test_a_solution_hash_that_is_not_a_runtime_commit_is_refused(world, solution):
    if solution == "tree":
        solution = subprocess.run(["git", "-C", str(world.runtime), "rev-parse", "HEAD^{tree}"], check=True,
                                  capture_output=True, text=True).stdout.strip()
    with pytest.raises(ValueError, match="not a commit"):
        enumerate_catalog([SEEDS / "direct.orc"], config_of(), tasks=[world.task], work_root=world.outside / "work",
                          evidence_root=world.tmp / "evidence", replicates=1, runtime=world.runtime, env={},
                          timeout_sec=1, solutions={world.task.name: solution}, call_cap=160)


def test_the_episode_brief_omits_the_command_boundary_when_none_is_configured():
    assert "None" not in episode_brief(config_of(command_boundaries_file=None), 0)


def test_solution_hashes_are_lowercased_before_use(world):
    assert check_solutions([world.task], {world.task.name: world.solution.upper()}, world.runtime) == {
        world.task.name: world.solution}


def test_a_string_where_a_list_is_required_is_refused_naming_the_field(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps(CONFIG | {"mutable_definitions": "run"}))
    with pytest.raises(ValueError, match="mutable_definitions"):
        load_config(tmp_path / "config.json")


# Stand-ins for the real claude CLI behind the shims (they run inside the sandbox in the episode's cand-1)
CLAUDE_PRINTS = f"""#!{sys.executable} -I
print("cat {{path}}")
"""
# A mutator that asks claude for an edit (recorded with its patch), then asks for a Fable model (refused by the guard)
MUTATOR_FABLE = f"""#!{sys.executable} -I
import subprocess, sys
from pathlib import Path
subprocess.run(["claude", "-p"], input=Path("EPISODE.md").read_text(), text=True, check=True)
sys.exit(subprocess.run(["claude", "-p", "--model", "fable-x"], input="edit", text=True).returncode)
"""
MUTATOR_ONE_CALL = f"""#!{sys.executable} -I
import subprocess
from pathlib import Path
subprocess.run(["claude", "-p"], input=Path("EPISODE.md").read_text(), text=True, check=True)
"""


def fake_claude(world, source):
    (world.fakebin / "claude").write_text(source)
    return {**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}"}


def test_mutator_runs_behind_shims_and_guard(sandboxed, world):
    env = fake_claude(world, ROLE_SWAP)
    row, evidence = episode(world, MUTATOR_FABLE, config_of(), env=env)
    calls = evidence / "episodes" / row["episode_id"] / "calls"
    assert (row["outcome"], row["provider_calls"], (calls / "1" / "prompt.txt").read_text().startswith("# Episode 0"),
            "providers.planner" in (calls / "1" / "patch-cand-1.diff").read_text(),
            "names a Fable model" in (calls / "2" / "stderr.txt").read_text()) == ("incident", 2, True, True, True)


def test_an_episode_session_naming_the_evidence_root_is_scan_pending(sandboxed, world):
    env = fake_claude(world, CLAUDE_PRINTS.format(path=world.tmp / "evidence" / "log.jsonl"))
    row, _ = episode(world, MUTATOR_ONE_CALL, config_of(), env=env)
    assert (row["scan_pending"], row["scan_hits"] > 0) == (True, True)


def test_an_episode_session_naming_the_work_roots_evaluation_records_is_scan_pending(sandboxed, world):
    records = (world.outside / "work").resolve() / "records" / "3f2a" / "run-1" / "inputs.json"
    row, _ = episode(world, MUTATOR_ONE_CALL, config_of(), env=fake_claude(world, CLAUDE_PRINTS.format(path=records)))
    assert (row["scan_pending"], row["scan_hits"] > 0) == (True, True)


def test_concurrent_catalog_logs_each_evaluation_once(sandboxed, world):
    script(world, [{"match": "Plan this task", "sleep": 15, "result": {"steps": ["edit pkg"]}}, *ANSWERS])
    env = {**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}", "SCRIPTED_RESULTS_FILE": str(world.results)}
    evidence = world.tmp / "evidence"
    rows = enumerate_catalog([SEEDS / "plan_then_implement.orc", SEEDS / "direct.orc"], config_of(), tasks=[world.task],
                             work_root=world.outside / "work", evidence_root=evidence, replicates=1,
                             runtime=world.runtime, env=env, timeout_sec=600,
                             solutions={world.task.name: world.solution}, call_cap=160, concurrency=2)
    logged = read_records(evidence / "log.jsonl")
    assert ([row["seed"] for row in logged], [row["outcome"] for row in logged],
            {row["seed"]: (row["evaluation_id"], row["candidate_id"]) for row in logged}) == (
        ["direct", "plan_then_implement"], ["completed", "completed"],
        {row["seed"]: (row["evaluation_id"], row["candidate_id"]) for row in rows})


def test_call_ledger_counts_each_evaluation_and_episode_from_shim_records(sandboxed, world):
    _, rows, evidence = mode1(world, ["direct"])
    entries = json.loads((evidence / "calls.json").read_text())
    assert (Counter((entry["kind"], entry["calls"]) for entry in entries),
            sorted(entry["evaluation_id"] for entry in entries if entry["kind"] == "evaluation")) == (
        Counter({("evaluation", 1): 3, ("episode", 0): 3}),
        sorted(row["evaluation_id"] for row in rows if row["kind"] == "evaluation"))


def test_call_cap_refuses_launch(world):
    evidence = world.tmp / "evidence"
    _, root = archive(world.candidate, evidence, world.runtime)
    ledger.reserve(evidence, kind="evaluation", key="in flight", planned=159, cap=160)
    with pytest.raises(CallCapExceeded, match="call cap 160"):
        evaluate_and_scan(root, config_of(entry_workflow="best_of_n::run", mutable_files=["best_of_n.orc"]),
                          task=world.task, replicate=1, work_root=world.outside / "work", evidence_root=evidence,
                          runtime=world.runtime, env=os.environ, timeout_sec=1,
                          solutions={world.task.name: world.solution}, holdouts=(), fields={}, call_cap=160)
    assert not (world.outside / "work").exists()


def test_an_episode_beyond_the_call_cap_is_refused_before_its_workspace(world):
    with pytest.raises(CallCapExceeded):
        episode(world, ROLE_SWAP, config_of(), call_cap=0)
    assert not (world.outside / "work" / "episodes").exists()


def test_planned_maximum_counts_provider_calls_under_loop_and_map_bounds():
    assert {seed: max_provider_calls(SEEDS / f"{seed}.orc", "run") for seed in CATALOG} == {
        "direct": 1, "plan_then_implement": 4, "implement_review_revise": 10, "best_of_n": 4,
        "implement_check_diagnose_repair": 3}


def test_the_brief_names_no_runtime_path_and_its_compile_line_runs_from_the_runtime_copy(world):
    _, parent = archive(world.candidate, world.tmp / "evidence", world.runtime)
    brief, tree = episode_brief(config_of(), 0), world.outside / "work" / "episodes" / "episode-0"
    copy, _ = episode_workspace(parent, tree, brief, world.runtime)
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}  # the shims strip it
    compiled = subprocess.run(["bash", "-c", brief.split("Check an edit with: ")[1].strip()], cwd=copy, env=env,
                              capture_output=True, text=True)
    found = subprocess.run(["bash", "-c", "PYTHONPATH=../py python -P -c 'import orchestrator; print(orchestrator.__file__)'"],
                           cwd=copy, env=env, capture_output=True, text=True).stdout
    assert (str(world.runtime) in brief, compiled.returncode, found.startswith(str(tree.resolve() / "py" / "orchestrator"))) == (
        False, 0, True), compiled.stderr


REMOVE_GIT = f"""#!{sys.executable} -I
import shutil
shutil.rmtree(".git")
"""
PRINT_ENV = f"""#!{sys.executable} -I
import os
print("DISABLE_AUTOUPDATER=" + str(os.environ.get("DISABLE_AUTOUPDATER")))
"""


def test_an_episode_whose_mutator_removes_git_is_recorded_as_an_incident(world):
    row, evidence = episode(world, REMOVE_GIT, config_of())
    assert (row["outcome"], row["workspace_intact"], [r["episode_id"] for r in read_records(evidence / "log.jsonl")]) == (
        "incident", False, [row["episode_id"]])


def test_the_mutator_runs_with_the_cli_autoupdater_disabled(world):
    _, evidence = episode(world, PRINT_ENV, config_of())
    assert "DISABLE_AUTOUPDATER=1" in (evidence / "episodes" / "episode-0.log").read_text()


def provider_site(root: Path, config: ExperimentConfig, runtime: Path, line: int | None = None) -> dict:
    """The first (or the `line`'s) eligible provider-call site of the candidate at `root`."""
    return next(site for site in eligible_sites(site_manifest(root, config, runtime=runtime), config)
                if site["kind"] == "provider-call" and line in (None, site["span"]["start"]["line"]))


def i2_episode(world, index, config=None):
    config = config or config_of(interface="I2")
    return episode(world, MUTATOR_I2, config, index=index, site=provider_site(world.candidate, config, world.runtime))


def test_i2_episode_records_site_receipt_and_accepts_a_single_subtree_replacement(sandboxed, world):
    row, _ = i2_episode(world, 0)
    site = provider_site(world.candidate, config_of(interface="I2"), world.runtime)
    assert (row["interface"], row["site_id"], row["receipt"]["replacement_expression"].startswith("(if true"),
            row["receipt"]["hypothesis"], row["outcome"], row["skeleton"] != row["parent_skeleton"]) == (
        "I2", site["site_id"], True, "episode 0 should do better", "accepted", True)


def test_i2_refuses_an_edit_outside_the_selected_site_with_scope_exceeded(sandboxed, world):
    row, _ = i2_episode(world, 1)
    assert (row["outcome"], row["refusal_code"]) == ("rejected", "scope_exceeded")


UNUSED_BINDING = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule unused_binding)
  (import common :only (Change Outcome))
  (export run)

  (defrecord Plan (steps List[String]))

  (defprompt p-change (:fills (task :text)) -> Change "Implement this change: {task}")
  (defprompt p-plan (:fills (task :text)) -> Plan "Plan this task: {task}")

  (defworkflow run
    ((task String)
     (intent String)
     (repo String))
    -> Outcome
    (let* ((x (provider-result providers.coder :prompt (p-change :task task)
                :model "claude-sonnet-5-5" :effort "medium" :timeout-sec 60))
           (change (provider-result providers.coder :prompt (p-change :task task)
                     :model "claude-sonnet-5-5" :effort "medium" :timeout-sec 60)))
      (variant Outcome DONE :summary change.summary)))
)
"""
UNUSED_CONFIG = {"entry_workflow": "unused_binding::run", "mutable_files": ["unused_binding.orc"], "interface": "I2"}
X_CALL = """(provider-result providers.coder :prompt (p-change :task task)
                :model "claude-sonnet-5-5" :effort "medium" :timeout-sec 60)"""


def unused_binding_candidate(root: Path) -> Path:
    (root / "unused_binding.orc").write_text(UNUSED_BINDING)
    return root


def test_i2_refuses_a_replacement_whose_slot_type_differs(world):
    parent, child = unused_binding_candidate(world.candidate), world.tmp / "child"
    shutil.copytree(parent, child)
    plan_call = '(provider-result providers.coder :prompt (p-plan :task task) :model "claude-sonnet-5-5")'
    (child / "unused_binding.orc").write_text(UNUSED_BINDING.replace(X_CALL, plan_call))
    config = config_of(**UNUSED_CONFIG)
    verdict = judge_child(parent, child, config, runtime=world.runtime,
                          site=provider_site(parent, config, world.runtime, line=18), parent_candidate_id="sha256:p")
    assert verdict["refusal_code"] == "slot_type_changed", verdict


def test_i2_refuses_a_replacement_whose_type_the_manifest_cannot_report(world):
    unused_binding_candidate(world.candidate)
    config = config_of(**UNUSED_CONFIG)
    row, _ = episode(world, MUTATOR_I2, config, index=3,
                     site=provider_site(world.candidate, config, world.runtime, line=18))
    assert (row["receipt"]["replacement_expression"], row["refusal_code"]) == ('"x"', "slot_type_unavailable"), row


def test_two_structurally_different_i2_replacements_both_compile_and_execute(sandboxed, world):
    rows = [i2_episode(world, index)[0] for index in (0, 2)]
    script(world, ANSWERS)
    env = {**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}", "SCRIPTED_RESULTS_FILE": str(world.results)}
    evaluations = evaluate_all([(Path(row["candidate_root"]), config_of(), {}) for row in rows], tasks=[world.task],
                               replicates=1, concurrency=2, work_root=world.outside / "work",
                               evidence_root=world.tmp / "evidence", runtime=world.runtime, env=env, timeout_sec=600,
                               solutions={world.task.name: world.solution}, holdouts=(), call_cap=160)
    assert ([row["outcome"] for row in rows], len({row["skeleton"] for row in rows} | {rows[0]["parent_skeleton"]}),
            [row["outcome"] for row in evaluations]) == (["accepted", "accepted"], 3, ["completed", "completed"])


FEEDBACK = {"hidden": 0.9, "other_candidates": {"sha256:other": 9.5},
            "mean_value": {"task-1": {"mean": 7.25, "n": 2}},
            "runs": [{"task": "task-1", "outcome": "completed", "terminal": "DONE", "provider_calls": 3,
                      "wall_clock_sec": 812.5, "hidden": 0.9}]}


def test_the_i2_brief_carries_the_site_and_feedback_but_no_hidden_figures_or_evidence_path(world):
    config = config_of(interface="I2")
    site = provider_site(world.candidate, config, world.runtime)
    brief = episode_brief(config, 0, site=site, feedback=FEEDBACK)
    assert (site["site_id"] in brief, "7.25" in brief, "812.5" in brief, "DONE" in brief, "0.9" in brief,
            "9.5" in brief, str(world.tmp) in brief, str(world.outside) in brief) == (
        True, True, True, True, False, False, False, False)


def test_i1_episodes_still_run_through_run_episode_with_no_site(sandboxed, world):
    row, _ = episode(world, MUTATOR, config_of())
    assert (row["interface"], row["mode"], row["outcome"], row["site_id"], row["receipt"]) == (
        "I1", "unguided", "accepted", None, None)


def test_an_i2_hypothesis_directory_is_removed_and_reads_as_unavailable(world):
    mutator = MUTATOR_I2.replace('Path("HYPOTHESIS.txt").write_text(', 'Path("HYPOTHESIS.txt/notes").mkdir(parents=True) or (')
    config = config_of(interface="I2")
    row, evidence = episode(world, mutator, config, site=provider_site(world.candidate, config, world.runtime))
    assert (row["outcome"], row["hypothesis"], (Path(row["candidate_root"]) / "HYPOTHESIS.txt").exists()) == (
        "accepted", "unavailable", False)


def test_mode1_refuses_a_configuration_whose_interface_is_not_i1(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps(CONFIG | {"interface": "I2"}))
    with pytest.raises(ValueError, match="I1"):
        run_mode1(tmp_path / "config.json", seeds=[], tasks=[], work_root=tmp_path / "work",
                  evidence_root=tmp_path / "evidence", episodes=0, agent_cmd=[], replicates=1,
                  runtime=tmp_path / "runtime", env={}, timeout_sec=1, solutions={}, call_cap=160)
    assert not (tmp_path / "evidence").exists()
