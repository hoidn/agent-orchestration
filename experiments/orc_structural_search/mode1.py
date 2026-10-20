"""Mode 1 of the structural search driver (run_mode1): the seed catalog enumerated, then unguided I1 episodes
against the seed the configuration's entry names, each accepted child evaluated like a seed (`mode: "unguided"`).
The roots, records, episodes and evaluation launches are driver.py's (its module docstring); its `main` is the
command line.
"""

import itertools
import json
import tempfile
from dataclasses import replace
from collections.abc import Mapping, Sequence
from pathlib import Path

from experiments.orc_structural_search import ledger, qualification
from experiments.orc_structural_search.candidates import imports
from experiments.orc_structural_search.config import ExperimentConfig, load_config
from experiments.orc_structural_search.driver import (
    Unit, archive, check_roots, check_solutions, evaluate_all, launch_units, run_episode, units)
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
              guard: QuotaGuard | None = None, hide: Sequence[Path] = (), criterion: Path | None = None) -> dict:
    """Enumerate the catalog, run `episodes` unguided I1 episodes (not counting quota incidents, each relaunched at
    most guard.retries times) against the seed the configuration's entry names, evaluate every accepted child not
    evaluated before (new_children) like a seed (`mode: "unguided"`) and write <evidence>/readout.json. Evaluations
    run at most `concurrency` at a time; every launch is refused beyond `call_cap` provider calls. `continue_run`
    continues the run already in the evidence root (see driver.py's module docstring); `guard` (tests) is the
    invocation's quota pause state; `hide` adds directories every episode's CLI calls cannot see
    (driver.hidden_roots)."""
    config = load_config(config_path)
    if config.interface != "I1":
        raise ValueError(f"mode 1 runs I1 episodes only; {config_path} names interface {config.interface}")
    work_root, evidence_root = check_roots(work_root, evidence_root)
    prior = prior_rows(work_root, evidence_root, continue_run)
    solutions = check_solutions(tasks, solutions, runtime)
    qualification.validate(criterion, tasks=tasks, config_sha256=config.criterion_sha256, runtime=runtime)
    guard = guard or QuotaGuard()
    launch = {"work_root": work_root, "evidence_root": evidence_root, "runtime": runtime, "env": env,
              "timeout_sec": timeout_sec, "solutions": solutions, "holdouts": holdouts, "call_cap": call_cap,
              "criterion": criterion}
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
            env=env, hide=hide, **{key: launch[key] for key in ("work_root", "evidence_root", "runtime",
                                                               "solutions", "call_cap", "holdouts", "criterion")}), guard)
        launch_units(units(new_children([episode], config, evaluated), tasks, replicates), concurrency=concurrency,
                     guard=guard, **launch)
    result = readout(read_records(evidence_root / "log.jsonl"), evidence_root)
    (evidence_root / "readout.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def seed_files(seed: Path) -> dict[str, bytes]:
    """The seed, the `.orc` modules it imports transitively, and every other regular file of its directory."""
    files = {p.name: p.read_bytes() for p in seed.parent.iterdir() if p.is_file() and p.suffix != ".orc"}
    pending = [seed]
    while pending:
        path = pending.pop()
        if path.name in files or not path.is_file():
            continue  # a library import (no file beside the seed) or one already taken
        files[path.name] = path.read_bytes()
        pending += [path.parent / f"{module}.orc" for module in imports(path)]
    return files


def archive_seed(seed: Path, evidence_root: Path, runtime: Path) -> tuple[str, Path]:
    """(candidate id, archived root) of the seed's candidate root (seed_files)."""
    with tempfile.TemporaryDirectory() as staging:
        for name, data in seed_files(seed).items():
            (Path(staging) / name).write_bytes(data)
        return archive(Path(staging), evidence_root, runtime)


def seed_config(seed: Path, config: ExperimentConfig) -> ExperimentConfig:
    entry = config.entry_workflow.split("::")[1]
    return replace(config, entry_workflow=f"{seed.stem}::{entry}", mutable_files=(seed.name,))


def catalog_jobs(seeds: Sequence[Path], config: ExperimentConfig, evidence_root: Path,
                 runtime: Path) -> list[tuple[Path, ExperimentConfig, dict]]:
    """Each seed archived, as a (root, config, fields) job of `mode: "catalog"`."""
    jobs = []
    for seed in seeds:
        cid, root = archive_seed(seed, evidence_root, runtime)
        jobs.append((root, seed_config(seed, config),
                     {"mode": "catalog", "seed": seed.stem, "candidate_id": cid, "candidate_root": str(root)}))
    return jobs


def enumerate_catalog(seeds: Sequence[Path], config: ExperimentConfig, *, tasks: Sequence[Path], work_root: Path,
                      evidence_root: Path, replicates: int, runtime: Path, env: Mapping[str, str],
                      timeout_sec: float, solutions: Mapping[str, str], call_cap: int, concurrency: int = 1,
                      holdouts: Sequence[Path] = (), criterion: Path | None = None) -> list[dict]:
    """Archive every seed and evaluate it once per task and replicate (`mode: "catalog"`), at most `concurrency`
    evaluations at a time."""
    work_root, evidence_root = check_roots(work_root, evidence_root)
    solutions = check_solutions(tasks, solutions, runtime)
    return evaluate_all(catalog_jobs(seeds, config, evidence_root, runtime), tasks=tasks, replicates=replicates,
                        concurrency=concurrency, work_root=work_root,
                        evidence_root=evidence_root, runtime=runtime, env=env, timeout_sec=timeout_sec,
                        solutions=solutions, holdouts=holdouts, call_cap=call_cap, criterion=criterion)
