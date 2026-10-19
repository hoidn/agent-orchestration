"""Mode 1 of the structural search driver (run_mode1): the seed catalog enumerated, then unguided I1 episodes
against the seed the configuration's entry names, each accepted child evaluated like a seed (`mode: "unguided"`).
The roots, records, episodes and evaluation launches are driver.py's (its module docstring); its `main` is the
command line.
"""

import itertools
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from experiments.orc_structural_search import ledger
from experiments.orc_structural_search.config import ExperimentConfig, load_config
from experiments.orc_structural_search.driver import (
    Unit, catalog_jobs, check_roots, check_solutions, launch_units, run_episode, units)
from experiments.orc_structural_search.quota import (
    QuotaGuard, job_key, next_attempts, prior_rows, quota_reason, with_retries)
from experiments.orc_structural_search.readout import readout
from experiments.orc_structural_search.records import UNAVAILABLE, read_records


def continued(jobs: Sequence[tuple[Path, ExperimentConfig, Mapping]], tasks: Sequence[Path], replicates: int,
              prior: Sequence[Mapping]) -> list[Unit]:
    """The units still to launch: those without a log row in `prior`, and those whose latest row is a quota
    incident, as their next attempt (quota.next_attempts)."""
    pending = units(jobs, tasks, replicates)
    attempts = next_attempts([job_key({"split": UNAVAILABLE, **u.fields, "task_id": u.task.name,  # as the row
                                       "replicate": u.replicate}) for u in pending], prior)
    return [u._replace(attempt=a) for u, a in zip(pending, attempts, strict=True) if a is not None]


def child_job(episode: Mapping, config: ExperimentConfig) -> tuple[Path, ExperimentConfig, dict]:
    """An accepted unguided child's (root, config, fields) evaluation job."""
    fields = {"mode": "unguided", "episode_id": episode["episode_id"], "candidate_id": episode["candidate_id"],
              "parent_candidate_id": episode["parent_candidate_id"], "candidate_root": episode["candidate_root"]}
    return Path(episode["candidate_root"]), config, fields


def new_children(episodes: Sequence[Mapping], config: ExperimentConfig,
                 evaluated: set[str]) -> list[tuple[Path, ExperimentConfig, dict]]:
    """The evaluation jobs (child_job) of the accepted episodes whose child is not among the `evaluated` candidate
    ids, which it extends. A revisit (a no-op episode, a copy of a seed or of an earlier child) has an evaluated
    candidate's id, so its evaluation ids: it is not evaluated again, and its episode row still counts in the
    readout's diversity figures."""
    jobs = []
    for row in episodes:
        if row["outcome"] == "accepted" and row["candidate_id"] not in evaluated:
            evaluated.add(row["candidate_id"])
            jobs.append(child_job(row, config))
    return jobs


def entry_parent(seeded: Sequence[tuple[Path, ExperimentConfig, Mapping]], config: ExperimentConfig) -> Path:
    """The archived root of the seed the configuration's entry names (the unguided episodes' parent)."""
    module = config.entry_workflow.split("::")[0]
    parents = [Path(fields["candidate_root"]) for _, _, fields in seeded if fields["seed"] == module]
    if len(parents) != 1:
        raise ValueError(f"the entry {config.entry_workflow} names no seed among {[f['seed'] for _, _, f in seeded]}")
    return parents[0]


def run_mode1(config_path: Path, *, seeds: Sequence[Path], tasks: Sequence[Path], work_root: Path,
              evidence_root: Path, episodes: int, agent_cmd: Sequence[str], replicates: int, runtime: Path,
              env: Mapping[str, str], timeout_sec: float, solutions: Mapping[str, str], call_cap: int,
              concurrency: int = 4, holdouts: Sequence[Path] = (), continue_run: bool = False,
              guard: QuotaGuard | None = None) -> dict:
    """Enumerate the catalog, run `episodes` unguided I1 episodes (not counting quota incidents, each relaunched at
    most guard.retries times) against the seed the configuration's entry names, evaluate every accepted child not
    evaluated before (new_children) like a seed (`mode: "unguided"`) and write <evidence>/readout.json. Evaluations
    run at most `concurrency` at a time; every launch is refused beyond `call_cap` provider calls. `continue_run`
    continues the run already in the evidence root (see driver.py's module docstring); `guard` (tests) is the
    invocation's quota pause state."""
    config = load_config(config_path)
    if config.interface != "I1":
        raise ValueError(f"mode 1 runs I1 episodes only; {config_path} names interface {config.interface}")
    work_root, evidence_root = check_roots(work_root, evidence_root)
    prior = prior_rows(work_root, evidence_root, continue_run)
    solutions = check_solutions(tasks, solutions, runtime)
    guard = guard or QuotaGuard()
    launch = {"work_root": work_root, "evidence_root": evidence_root, "runtime": runtime, "env": env,
              "timeout_sec": timeout_sec, "solutions": solutions, "holdouts": holdouts, "call_cap": call_cap}
    seeded = catalog_jobs(seeds, config, evidence_root, runtime)
    parent = entry_parent(seeded, config)
    before = [row for row in prior if row["kind"] == "episode"]
    evaluated = {fields["candidate_id"] for _, _, fields in seeded}  # new_children extends it
    children = new_children(before, config, evaluated)
    launch_units(continued(seeded + children, tasks, replicates, prior), concurrency=concurrency, guard=guard, **launch)
    ledger.settle_killed_episodes(evidence_root)  # an index whose tree exists was killed in flight: skipped
    index = (i for i in itertools.count(1 + max((row["episode_index"] for row in before), default=-1))
             if not (work_root / "episodes" / f"episode-{i}").exists())
    for _ in range(episodes - sum(quota_reason(row, evidence_root) is None for row in before)):
        episode = with_retries(lambda _attempt: run_episode(
            parent, config, interface="I1", mode="unguided", agent_cmd=agent_cmd, episode_index=next(index),
            env=env, **{key: launch[key] for key in ("work_root", "evidence_root", "runtime", "solutions",
                                                    "call_cap", "holdouts")}), guard)
        launch_units(units(new_children([episode], config, evaluated), tasks, replicates), concurrency=concurrency,
                     guard=guard, **launch)
    result = readout(read_records(evidence_root / "log.jsonl"), evidence_root)
    (evidence_root / "readout.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result
