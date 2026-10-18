"""Mode 1 of the structural search driver: catalog enumeration and unguided I1 episodes.

Design: docs/design/orc_structural_search_driver.md ("Search Modes" mode 1, "Proposal Interfaces" I1,
"Records", "Evaluation Hygiene"). Two roots, neither inside the other:

  work root (sandbox-visible; `run_arm`'s work root)
    records/, runs/, agents/, env-manifests/   evaluations (see evaluation.py)
    episodes/episode-<n>/                      the mutator's working copy of the parent
  evidence root (never shown to an agent)
    log.jsonl                                  every episode and evaluation record, append-only
    candidates/<candidate_id>/                 the archive: catalog seeds and accepted children
    episodes/episode-<n>.log                   the mutator command's output
    readout.json                               the mode 1 readout

A seed is one `.orc` file of a catalog directory; its candidate root holds that file, the `.orc` modules it
imports (transitively) and every other regular file of the directory, and its entry is `<stem>::<entry
definition of the configuration>`. After every evaluation `prepare.scan` runs over its records with the
evidence root and the episode copies named `archive`, the log `lineage` and the holdout roots `holdout`;
the solution commit of each task comes from the operator's `solutions` mapping (task package name -> hash),
never from the package, which sits in the runtime agents can read. A nonzero hit count marks the
evaluation record `scan_pending`; the log is append-only, so the adjudicated verdict lives in the run's
<records_dir>/record.json.

Dependencies: everything evaluation.py needs (git, bwrap, a clean runtime checkout, the shims); `env` is the
launch environment of evaluations and of the mutator command, which must reach any agent CLI through the
shims. Consumption is not metered here: it is recorded "unavailable".
"""

import argparse
import hashlib
import json
import os
import shlex
import signal
import subprocess
import tempfile
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from pathlib import Path

from experiments.compare import prepare
from experiments.compare.repos import runtime_commit
from experiments.orc_structural_search.candidates import (
    candidate_id, compile_candidate, imports, snapshot, validate_frozen_surfaces)
from experiments.orc_structural_search.config import ExperimentConfig, load_config
from experiments.orc_structural_search.evaluation import EVALUATOR_VERSION, evaluate
from experiments.orc_structural_search.records import UNAVAILABLE, append_record, read_records, skeleton_hash

EPISODE = "EPISODE.md"
COLLAPSE_THRESHOLD = 0.75  # design default: a terminal-only share above it means the interface collapsed


def check_roots(work_root: Path, evidence_root: Path) -> tuple[Path, Path]:
    """Both roots resolved; refuse an evidence root inside the work root (agents could read the archive and
    the lineage) or a work root inside the evidence root."""
    work_root, evidence_root = work_root.resolve(), evidence_root.resolve()
    if evidence_root.is_relative_to(work_root) or work_root.is_relative_to(evidence_root):
        raise ValueError(f"the evidence root {evidence_root} and the work root {work_root} must not nest: "
                         "agents work under the work root and must not see the archive or the log")
    evidence_root.mkdir(parents=True, exist_ok=True)
    return work_root, evidence_root


def archive(root: Path, evidence_root: Path, runtime: Path) -> tuple[str, Path]:
    """(candidate id, archived root): `root` copied to <evidence>/candidates/<candidate_id>/ unless that
    candidate is already there (equal ids are the same candidate)."""
    cid = candidate_id(root, orchestrator_commit=runtime_commit(runtime))
    dest = evidence_root / "candidates" / cid
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        snapshot(root, {}, dest)
    return cid, dest


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


def seed_config(seed: Path, config: ExperimentConfig) -> ExperimentConfig:
    entry = config.entry_workflow.split("::")[1]
    return replace(config, entry_workflow=f"{seed.stem}::{entry}", mutable_files=(seed.name,))


def evaluate_and_scan(root: Path, config: ExperimentConfig, *, task: Path, replicate: int, work_root: Path,
                      evidence_root: Path, runtime: Path, env: Mapping[str, str], timeout_sec: float,
                      solutions: Mapping[str, str], holdouts: Sequence[Path], fields: Mapping[str, object]) -> dict:
    """Evaluate `root` once, scan the run and append the evaluation record (with `fields`) to the log."""
    record = evaluate(root, config, task_package=task, work_root=work_root, replicate=replicate,
                      runtime=runtime, env=env, timeout_sec=timeout_sec)
    roots = [("archive", evidence_root), ("archive", work_root / "episodes"), ("lineage", evidence_root / "log.jsonl"),
             *(("holdout", holdout) for holdout in holdouts)]
    hits = prepare.scan(record.records_dir, solutions[task.name], roots=roots)
    row = {**fields, **{k: str(v) if isinstance(v, Path) else v for k, v in asdict(record).items()},
           "kind": "evaluation", "task_id": task.name, "replicate": replicate, "split": UNAVAILABLE,
           "evaluator_version": EVALUATOR_VERSION,
           "consumption": UNAVAILABLE, "scan_hits": len(hits), "scan_pending": bool(hits)}
    append_record(evidence_root / "log.jsonl", row)
    return row


def check_solutions(tasks: Sequence[Path], solutions: Mapping[str, str]) -> None:
    """Refuse a task package without the operator's solution hash: its runs could not be scanned."""
    missing = sorted(task.name for task in tasks if not solutions.get(task.name))
    if missing:
        raise ValueError(f"no solution hash for task packages {missing}; pass --solution TASK=HASH for each")


def evaluate_on_tasks(root: Path, config: ExperimentConfig, *, tasks: Sequence[Path], replicates: int,
                      fields: Mapping[str, object], **launch) -> list[dict]:
    return [evaluate_and_scan(root, config, task=task, replicate=replicate, fields=fields, **launch)
            for task in tasks for replicate in range(1, replicates + 1)]


def enumerate_catalog(seeds: Sequence[Path], config: ExperimentConfig, *, tasks: Sequence[Path], work_root: Path,
                      evidence_root: Path, replicates: int, runtime: Path, env: Mapping[str, str],
                      timeout_sec: float, solutions: Mapping[str, str], holdouts: Sequence[Path] = ()) -> list[dict]:
    """Archive every seed and evaluate it once per task and replicate (`mode: "catalog"`)."""
    work_root, evidence_root = check_roots(work_root, evidence_root)
    check_solutions(tasks, solutions)
    rows = []
    for seed in seeds:
        with tempfile.TemporaryDirectory() as staging:
            for name, data in seed_files(seed).items():
                (Path(staging) / name).write_bytes(data)
            cid, root = archive(Path(staging), evidence_root, runtime)
        fields = {"mode": "catalog", "seed": seed.stem, "candidate_id": cid, "candidate_root": str(root)}
        rows += evaluate_on_tasks(root, seed_config(seed, config), tasks=tasks, replicates=replicates,
                                  fields=fields, work_root=work_root, evidence_root=evidence_root,
                                  runtime=runtime, env=env, timeout_sec=timeout_sec, solutions=solutions,
                                  holdouts=holdouts)
    return rows


def episode_brief(config: ExperimentConfig, index: int) -> str:
    module = config.entry_workflow.split("::")[0]
    compile_args = ["python", "-m", "orchestrator", "compile", f"{module}.orc", "--entry-workflow",
                    config.entry_workflow, "--source-root", config.source_root, "--provider-externs-file",
                    config.providers_file]
    if config.command_boundaries_file:
        compile_args += ["--command-boundaries-file", config.command_boundaries_file]
    return (f"# Episode {index}\n\n"
            f"Objective: rewrite the workflow `{config.entry_workflow}` in this directory into a policy you expect "
            "to complete coding tasks in a git repository more reliably or with fewer provider calls. The "
            "evaluator and its tasks are not visible here.\n\n"
            f"Mutable scope: files {', '.join(config.mutable_files)}; definitions "
            f"{', '.join(config.mutable_definitions)}; condition {config.condition}.\n\n"
            "Frozen surfaces: imports; deftype, defrecord, defunion and defenum declarations; export, module and "
            f"language forms; exported signatures; the command boundary file {config.command_boundaries_file}; "
            "and what the condition does not permit (topology-only freezes prompts, the providers file and any "
            ":model/:effort value the module does not already use). Adding or removing files or definitions, "
            "or changing a frozen surface, refuses the proposal.\n\n"
            f"Check an edit with: {shlex.join(compile_args)}\n")


def run_agent(agent_cmd: Sequence[str], cwd: Path, log: Path, env: Mapping[str, str],
              wall_clock_sec: float) -> tuple[str | None, int | str]:
    """(None when the command exited 0, else "incident"; or "exhausted" after the wall clock), exit status."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as out:
        agent = subprocess.Popen(list(agent_cmd), cwd=cwd, env=dict(env), stdout=out, stderr=subprocess.STDOUT,
                                 start_new_session=True)
        try:
            status = agent.wait(timeout=wall_clock_sec)
        except subprocess.TimeoutExpired:
            os.killpg(agent.pid, signal.SIGKILL)  # ponytail: same process-group ceiling as evaluation._launch
            agent.wait()
            return "exhausted", UNAVAILABLE
    return (None if status == 0 else "incident"), status


def entry_result(root: Path, build_key: str) -> object:
    return json.loads((root / ".orchestrate" / "build" / build_key / "closed_program.json").read_text())["result"]


def judge_child(parent: Path, child: Path, config: ExperimentConfig, *, runtime: Path) -> dict:
    """Frozen-surface validation, full compilation with the runtime's orchestrator (a compiler crash is a
    rejection), then the entry's result type against the parent's."""
    verdict = validate_frozen_surfaces(parent, child, config)
    if not verdict.accepted:
        return {"outcome": "rejected", "refusal_code": verdict.code, "detail": verdict.detail}
    compiled = compile_candidate(child, config, runtime=runtime)
    if compiled.status != "accepted":
        first = compiled.diagnostics[0] if compiled.diagnostics else {}
        return {"outcome": "rejected", "diagnostics_class": first.get("code", UNAVAILABLE),
                "detail": first.get("message") or first.get("stderr", "")}
    # Fires only when the entry is not exported or lacks a result annotation: frozen-surface validation already
    # freezes an exported signature and every type declaration.
    parent_build = compile_candidate(parent, config, runtime=runtime)
    if entry_result(parent, parent_build.build_key) != entry_result(child, compiled.build_key):
        return {"outcome": "rejected", "refusal_code": "slot_type_changed",
                "detail": f"the result type of {config.entry_workflow} differs from the parent's"}
    return {"outcome": "accepted", "program_digest": compiled.program_digest, "build_key": compiled.build_key}


def skeleton(root: Path, config: ExperimentConfig) -> str:
    source = "\n".join((root / name).read_text() for name in config.mutable_files if name.endswith(".orc"))
    return skeleton_hash(source, definitions=config.mutable_definitions)


def unguided_episode(parent_root: Path, config: ExperimentConfig, *, agent_cmd: Sequence[str], work_root: Path,
                     evidence_root: Path, episode_index: int, runtime: Path, env: Mapping[str, str]) -> dict:
    """One I1 episode: the agent command edits a copy of the parent (cwd, with EPISODE.md); the child is the
    copy's final files. An accepted child is archived; the episode record is appended to the log."""
    work_root, evidence_root = check_roots(work_root, evidence_root)
    commit = runtime_commit(runtime)
    parent_id = candidate_id(parent_root, orchestrator_commit=commit)
    episode_id = "sha256:" + hashlib.sha256(json.dumps(
        [parent_id, config.interface, config.condition, config.episode_wall_clock_sec, episode_index]).encode()
    ).hexdigest()
    copy = snapshot(parent_root, {EPISODE: episode_brief(config, episode_index).encode()},
                    work_root / "episodes" / f"episode-{episode_index}")
    started = time.monotonic()
    stopped, status = run_agent(agent_cmd, copy, evidence_root / "episodes" / f"episode-{episode_index}.log", env,
                                config.episode_wall_clock_sec)
    elapsed = time.monotonic() - started
    (copy / EPISODE).unlink(missing_ok=True)
    row = {"kind": "episode", "mode": "unguided", "interface": config.interface, "condition": config.condition,
           "episode_id": episode_id, "episode_index": episode_index, "parent_candidate_id": parent_id,
           "candidate_id": candidate_id(copy, orchestrator_commit=commit), "agent_cmd": list(agent_cmd),
           "agent_exit": status, "envelope": {"wall_clock_sec": config.episode_wall_clock_sec},
           "wall_clock_sec": elapsed, "consumption": UNAVAILABLE, "model_revision": UNAVAILABLE,
           "hypothesis": UNAVAILABLE, "refusal_code": None, "diagnostics_class": None, "skeleton": None,
           "parent_skeleton": skeleton(parent_root, config)}
    row.update({"outcome": stopped} if stopped else judge_child(parent_root, copy, config, runtime=runtime))
    if row["outcome"] == "accepted":
        _, root = archive(copy, evidence_root, runtime)
        row.update(candidate_root=str(root), skeleton=skeleton(root, config))
    append_record(evidence_root / "log.jsonl", row)
    return row


def share(count: int, total: int) -> float | str:
    return count / total if total else UNAVAILABLE


def readout(rows: Sequence[Mapping]) -> dict:
    """Per-seed outcomes, episode outcomes and refusals, and skeleton diversity among accepted children."""
    catalog: dict[str, dict] = {}
    for row in rows:
        if row["kind"] == "evaluation" and row["mode"] == "catalog":
            entry = catalog.setdefault(row["seed"], {"candidate_id": row["candidate_id"], "outcomes": []})
            entry["outcomes"].append(row["outcome"])
    episodes = [row for row in rows if row["kind"] == "episode"]
    accepted = [row for row in episodes if row["outcome"] == "accepted"]
    seen, revisits = set(), 0
    for row in accepted:
        seen.add(row["parent_skeleton"])
        revisits += row["skeleton"] in seen
        seen.add(row["skeleton"])
    terminal_only = share(sum(row["skeleton"] == row["parent_skeleton"] for row in accepted), len(accepted))
    children = {}
    for row in rows:
        if row["kind"] == "evaluation" and row["mode"] == "unguided":
            children.setdefault(row["candidate_id"], []).append(row["outcome"])
    return {"catalog": catalog, "episodes": dict(Counter(row["outcome"] for row in episodes)),
            "refused": dict(Counter(row["refusal_code"] or row["diagnostics_class"]
                                    for row in episodes if row["outcome"] == "rejected")),
            "distinct_skeletons": len({row["skeleton"] for row in accepted}),
            "revisit_rate": share(revisits, len(accepted)), "terminal_only_share": terminal_only,
            "collapsed": terminal_only if terminal_only == UNAVAILABLE else terminal_only > COLLAPSE_THRESHOLD,
            "child_outcomes": children,
            "scan_pending": [row["evaluation_id"] for row in rows if row.get("scan_pending")]}


def run_mode1(config_path: Path, *, seeds: Sequence[Path], tasks: Sequence[Path], work_root: Path,
              evidence_root: Path, episodes: int, agent_cmd: Sequence[str], replicates: int, runtime: Path,
              env: Mapping[str, str], timeout_sec: float, solutions: Mapping[str, str],
              holdouts: Sequence[Path] = ()) -> dict:
    """Enumerate the catalog, run `episodes` unguided I1 episodes against the seed the configuration's entry
    names, evaluate every accepted child like a seed (`mode: "unguided"`) and write <evidence>/readout.json."""
    config = load_config(config_path)
    work_root, evidence_root = check_roots(work_root, evidence_root)
    launch = {"work_root": work_root, "evidence_root": evidence_root, "runtime": runtime, "env": env,
              "timeout_sec": timeout_sec, "solutions": solutions, "holdouts": holdouts}
    catalog = enumerate_catalog(seeds, config, tasks=tasks, replicates=replicates, **launch)
    module = config.entry_workflow.split("::")[0]
    parents = {row["candidate_root"] for row in catalog if row["seed"] == module}
    if len(parents) != 1:
        raise ValueError(f"the entry {config.entry_workflow} names no seed among {[s.name for s in seeds]}")
    parent = Path(parents.pop())
    for index in range(episodes):
        episode = unguided_episode(parent, config, agent_cmd=agent_cmd, work_root=work_root,
                                   evidence_root=evidence_root, episode_index=index, runtime=runtime, env=env)
        if episode["outcome"] == "accepted":
            fields = {"mode": "unguided", "episode_id": episode["episode_id"], "candidate_id": episode["candidate_id"],
                      "parent_candidate_id": episode["parent_candidate_id"], "candidate_root": episode["candidate_root"]}
            evaluate_on_tasks(Path(episode["candidate_root"]), config, tasks=tasks, replicates=replicates,
                              fields=fields, **launch)
    result = readout(read_records(evidence_root / "log.jsonl"))
    (evidence_root / "readout.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def solution(text: str) -> tuple[str, str]:
    task, sep, commit = text.partition("=")
    if not (task and sep and commit):
        raise argparse.ArgumentTypeError(f"expected TASK=HASH, not {text!r}")
    return task, commit


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seeds", type=Path, nargs="+", required=True, help="seed .orc files")
    parser.add_argument("--tasks", type=Path, nargs="+", required=True, help="task package directories")
    parser.add_argument("--work-root", type=Path, required=True, help="sandbox-visible work root")
    parser.add_argument("--evidence", type=Path, required=True, help="evidence root, outside the work root")
    parser.add_argument("--episodes", type=int, required=True)
    parser.add_argument("--agent-cmd", required=True, help="the mutator command line (shell words)")
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument("--runtime", type=Path, required=True, help="the frozen runtime checkout")
    parser.add_argument("--eval-timeout-sec", type=float, required=True, help="wall clock per evaluation launch")
    parser.add_argument("--solution", type=solution, action="append", default=[], metavar="TASK=HASH", required=True,
                        help="a task package's solution commit for the scan (repeatable, one per task)")
    parser.add_argument("--holdout", type=Path, action="append", default=[], help="a holdout root (repeatable)")
    a = parser.parse_args(argv)
    run_mode1(a.config, seeds=a.seeds, tasks=a.tasks, work_root=a.work_root, evidence_root=a.evidence,
              episodes=a.episodes, agent_cmd=shlex.split(a.agent_cmd), replicates=a.replicates, runtime=a.runtime,
              env=os.environ, timeout_sec=a.eval_timeout_sec, solutions=dict(a.solution), holdouts=a.holdout)
    print(a.evidence / "readout.json")


if __name__ == "__main__":
    main()
