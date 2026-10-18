"""Mode 1 driver: catalog enumeration and unguided I1 episodes with a scripted mutator and scripted providers
(no provider is called)."""

import json
import os
import sys

import pytest

from experiments.orc_structural_search.driver import run_mode1
from experiments.orc_structural_search.records import read_records
from tests.experiments.compare_harness_support import skip_without_sandbox
from tests.experiments.orc_structural_search_support import MUTATOR, SEEDS, script, world  # noqa: F401 (fixture)

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
SOLUTION = "5a1d0c0ffee5a1d0c0ffee5a1d0c0ffee5a1d0c0"


@pytest.fixture
def sandboxed():
    skip_without_sandbox()


def mode1(world, seeds):
    script(world, ANSWERS)
    (world.task / "solution_commit").write_text(SOLUTION + "\n")
    (world.tmp / "config.json").write_text(json.dumps(CONFIG))
    mutator = world.outside / "mutator.py"
    mutator.write_text(MUTATOR)
    env = {**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}", "SCRIPTED_RESULTS_FILE": str(world.results)}
    evidence = world.tmp / "evidence"
    readout = run_mode1(world.tmp / "config.json", seeds=[SEEDS / f"{name}.orc" for name in seeds], tasks=[world.task],
                        work_root=world.outside / "work", evidence_root=evidence, episodes=3,
                        agent_cmd=[sys.executable, "-I", str(mutator)], replicates=1, runtime=world.runtime, env=env,
                        timeout_sec=600)
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
               for row in episodes)
