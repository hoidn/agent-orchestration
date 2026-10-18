"""Mode 1 of the structural search driver: catalog enumeration and unguided I1 episodes.

Design: docs/design/orc_structural_search_driver.md ("Search Modes" mode 1, "Proposal Interfaces" I1,
"Records", "Evaluation Hygiene"). Two roots, neither inside the other:

  work root (sandbox-visible; `run_arm`'s work root)
    records/, runs/, agents/, env-manifests/   evaluations (see evaluation.py)
    episodes/episode-<n>/cand-1/               the mutator's working copy of the parent: a git repository whose
                                               one commit (the shims' COMPARE_BASE) is the parent snapshot
    episodes/episode-<n>/tmp/                  the mutator's private /tmp under the shims
  evidence root (never shown to an agent)
    log.jsonl                                  every episode and evaluation record, append-only
    calls.json                                 the provider-call ledger (ledger.py)
    candidates/<candidate_id>/                 the archive: catalog seeds and accepted children
    episodes/episode-<n>.log                   the mutator command's output
    episodes/<episode_id>/                     the episode's shim records (COMPARE_ROOT): calls/<n>/, record.json
    episodes/<episode_id>.diff                 the episode's final diff against its parent, whatever the outcome
    readout.json                               the mode 1 readout

The evidence root must be fresh: `run_mode1` refuses one that already holds a log, and the driver never resumes
an incident. An archived candidate is checked before each episode and evaluation: its content must still hash to
its directory name (archive tamper check).

A seed is one `.orc` file of a catalog directory; its candidate root holds that file, the `.orc` modules it
imports (transitively) and every other regular file of the directory, and its entry is `<stem>::<entry
definition of the configuration>`. After every evaluation `prepare.scan` runs over its records with the
evidence root and the episode copies named `archive`, the log `lineage` and the holdout roots `holdout`, and
after every episode (scan_episode) over the episode's shim records; the solution commits come from the
operator's `solutions` mapping (task package name -> hash, checked by check_solutions), never from the package,
which agents can read. Hits mark the record `scan_pending`; the log is append-only, so the adjudicated verdict
lives in the scanned records' record.json. The mutator runs behind the shims (run_agent). Evaluations run at most
`concurrency` at a time (evaluate_all; log and ledger writes are serialized); every launch is refused beyond the
call cap (ledger.py).

Dependencies: everything evaluation.py needs (git, bwrap, a clean runtime checkout, the shims); `env` is the
launch environment of evaluations and of the mutator command (the driver adds the shims itself). Consumption is
not metered here: it is recorded "unavailable".
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path

from experiments.compare import prepare
from experiments.compare.repos import (
    SEED_COMMIT, SEED_DATES, dump, git, guard, main_checkout, runtime_commit, shim_prefix, visible_in_sandbox)
from experiments.orc_structural_search import ledger
from experiments.orc_structural_search.candidates import (
    _file_names, candidate_id, compile_candidate, imports, snapshot, validate_frozen_surfaces)
from experiments.orc_structural_search.config import ExperimentConfig, load_config
from experiments.orc_structural_search.evaluation import EVALUATOR_VERSION, evaluate
from experiments.orc_structural_search.records import (
    UNAVAILABLE, append_record, provider_allocation, read_records, skeleton_hash)

EPISODE = "EPISODE.md"
_LOG_LOCK = threading.Lock()  # concurrent evaluations append to one log
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


def check_archived(root: Path, commit: str) -> str:
    """The archived candidate's id; refuse one whose content no longer hashes to its directory name."""
    cid = candidate_id(root, orchestrator_commit=commit)
    if cid != root.name:
        raise RuntimeError(f"the archived candidate {root} now hashes to {cid}: the archive was modified")
    return cid


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


def entry_source(root: Path, config: ExperimentConfig) -> Path:
    return (root / config.source_root / config.entry_workflow.split("::")[0]).with_suffix(".orc")


def evaluate_and_scan(root: Path, config: ExperimentConfig, *, task: Path, replicate: int, work_root: Path,
                      evidence_root: Path, runtime: Path, env: Mapping[str, str], timeout_sec: float,
                      solutions: Mapping[str, str], holdouts: Sequence[Path], fields: Mapping[str, object],
                      call_cap: int) -> dict:
    """Evaluate the archived `root` once (refused beyond the call cap), scan the run and append the evaluation
    record (with `fields`) to the log."""
    cid = check_archived(root, runtime_commit(runtime))
    slot = ledger.reserve(evidence_root, kind="evaluation", key=f"{cid} {task.name} replicate {replicate}",
                          planned=ledger.max_provider_calls(entry_source(root, config)), cap=call_cap)
    record = evaluate(root, config, task_package=task, work_root=work_root, replicate=replicate,
                      runtime=runtime, env=env, timeout_sec=timeout_sec)
    ledger.settle(evidence_root, slot, record.records_dir, evaluation_id=record.evaluation_id)
    roots = [("archive", evidence_root), ("archive", work_root / "episodes"), ("lineage", evidence_root / "log.jsonl"),
             *(("holdout", holdout) for holdout in holdouts)]
    hits = prepare.scan(record.records_dir, solutions[task.name], roots=roots)
    row = {**fields, **{k: str(v) if isinstance(v, Path) else v for k, v in asdict(record).items()},
           "kind": "evaluation", "task_id": task.name, "replicate": replicate, "split": UNAVAILABLE,
           "evaluator_version": EVALUATOR_VERSION,
           "consumption": UNAVAILABLE, "scan_hits": len(hits), "scan_pending": bool(hits)}
    with _LOG_LOCK:
        append_record(evidence_root / "log.jsonl", row)
    return row


def object_type(repo: Path, name: str) -> str:
    """`git cat-file -t` of `name` in `repo`, or "" when git cannot resolve it."""
    done = subprocess.run(["git", "-C", str(repo), "cat-file", "-t", name], capture_output=True, text=True)
    return done.stdout.strip()


def check_solutions(tasks: Sequence[Path], solutions: Mapping[str, str], runtime: Path) -> dict[str, str]:
    """The solution hashes lowercased (the scan matches the hash's prefix case-sensitively); refuse a task package
    without the operator's solution hash (its runs could not be scanned), or whose hash has fewer than 7 hex
    characters or names no commit of the runtime (where the task's base commit lives)."""
    solutions = {task: commit.lower() for task, commit in solutions.items()}
    missing = sorted(task.name for task in tasks if not solutions.get(task.name))
    if missing:
        raise ValueError(f"no solution hash for task packages {missing}; pass --solution TASK=HASH for each")
    for task in tasks:
        given = solutions[task.name]
        if not re.fullmatch(r"[0-9a-f]{7,64}", given) or object_type(runtime, given) != "commit":
            raise ValueError(f"--solution {task.name}={given} is not a commit of the runtime {runtime}: give at "
                             "least 7 hex characters of the task's solution commit")
    return solutions


def evaluate_all(jobs: Sequence[tuple[Path, ExperimentConfig, Mapping[str, object]]], *, tasks: Sequence[Path],
                 replicates: int, concurrency: int, **launch) -> list[dict]:
    """Evaluate each (root, config, fields) job once per task and replicate with at most `concurrency`
    evaluations in flight; rows in job order. Every evaluation is attempted before the first failure (a launch
    refused at the call cap among them) is raised."""
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(evaluate_and_scan, root, config, task=task, replicate=replicate, fields=fields, **launch)
                   for root, config, fields in jobs for task in tasks for replicate in range(1, replicates + 1)]
    return [future.result() for future in futures]


def enumerate_catalog(seeds: Sequence[Path], config: ExperimentConfig, *, tasks: Sequence[Path], work_root: Path,
                      evidence_root: Path, replicates: int, runtime: Path, env: Mapping[str, str],
                      timeout_sec: float, solutions: Mapping[str, str], call_cap: int, concurrency: int = 1,
                      holdouts: Sequence[Path] = ()) -> list[dict]:
    """Archive every seed and evaluate it once per task and replicate (`mode: "catalog"`), at most `concurrency`
    evaluations at a time."""
    work_root, evidence_root = check_roots(work_root, evidence_root)
    solutions = check_solutions(tasks, solutions, runtime)
    jobs = []
    for seed in seeds:
        with tempfile.TemporaryDirectory() as staging:
            for name, data in seed_files(seed).items():
                (Path(staging) / name).write_bytes(data)
            cid, root = archive(Path(staging), evidence_root, runtime)
        jobs.append((root, seed_config(seed, config),
                     {"mode": "catalog", "seed": seed.stem, "candidate_id": cid, "candidate_root": str(root)}))
    return evaluate_all(jobs, tasks=tasks, replicates=replicates, concurrency=concurrency, work_root=work_root,
                        evidence_root=evidence_root, runtime=runtime, env=env, timeout_sec=timeout_sec,
                        solutions=solutions, holdouts=holdouts, call_cap=call_cap)


def episode_brief(config: ExperimentConfig, index: int) -> str:
    module = config.entry_workflow.split("::")[0]
    compile_args = ["python", "-m", "orchestrator", "compile", f"{module}.orc", "--entry-workflow",
                    config.entry_workflow, "--source-root", config.source_root, "--provider-externs-file",
                    config.providers_file]
    boundary = ""
    if config.command_boundaries_file:
        compile_args += ["--command-boundaries-file", config.command_boundaries_file]
        boundary = f"the command boundary file {config.command_boundaries_file}; "
    return (f"# Episode {index}\n\n"
            f"Objective: rewrite the workflow `{config.entry_workflow}` in this directory into a policy you expect "
            "to complete coding tasks in a git repository more reliably or with fewer provider calls. The "
            "evaluator and its tasks are not visible here.\n\n"
            f"Mutable scope: files {', '.join(config.mutable_files)}; definitions "
            f"{', '.join(config.mutable_definitions)}; condition {config.condition}.\n\n"
            "Frozen surfaces: imports; deftype, defrecord, defunion and defenum declarations; export, module and "
            f"language forms; exported signatures; {boundary}and what the condition does not permit (topology-only freezes prompts, the providers file and any "
            ":model/:effort value the module does not already use). Adding or removing files or definitions, "
            "or changing a frozen surface, refuses the proposal.\n\n"
            f"Check an edit with: {shlex.join(compile_args)}\n")


def episode_workspace(parent_root: Path, tree: Path, brief: str, runtime: Path) -> tuple[Path, str]:
    """(<tree>/cand-1, its commit): a git repository holding the parent snapshot in one commit, with the brief
    in EPISODE.md (excluded from patches, like the build cache), and <tree>/tmp."""
    guard(main_checkout(runtime), tree)
    visible_in_sandbox(tree)
    copy = snapshot(parent_root, {}, tree / "cand-1")
    git(copy, "init", "-q")
    git(copy, "add", "-A", "-f", ".")
    git(copy, *SEED_COMMIT, env=SEED_DATES)
    (copy / ".git" / "info").mkdir(exist_ok=True)
    with (copy / ".git" / "info" / "exclude").open("a") as exclude:
        exclude.write(f"/{EPISODE}\n/.orchestrate/\n")
    (copy / EPISODE).write_text(brief)
    (tree / "tmp").mkdir()
    return copy, git(copy, "rev-parse", "HEAD")


def run_agent(agent_cmd: Sequence[str], cwd: Path, log: Path, env: Mapping[str, str], wall_clock_sec: float, *,
              runtime: Path, shim_env: Mapping[str, object]) -> tuple[str | None, int | str]:
    """Run the command from `cwd` behind the shim prefix (`shim_env`: COMPARE_ROOT, COMPARE_TREE, COMPARE_BASE,
    TMPDIR) with <cwd>/EPISODE.md on stdin: (None when it exited 0, else "incident"; or "exhausted" after the
    wall clock), exit status."""
    log.parent.mkdir(parents=True, exist_ok=True)
    argv = ["bash", "-c", shim_prefix(cwd, runtime, shim_env) + shlex.join(agent_cmd)]
    with log.open("w") as out, (cwd / EPISODE).open() as brief:
        agent = subprocess.Popen(argv, cwd=cwd, env=dict(env), stdin=brief, stdout=out, stderr=subprocess.STDOUT,
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


def mutable_source(root: Path, config: ExperimentConfig) -> str:
    return "\n".join((root / name).read_text() for name in config.mutable_files if name.endswith(".orc"))


def skeleton(root: Path, config: ExperimentConfig) -> str:
    """The skeleton hash of the mutable definitions; prompts contribute nothing (records.skeleton_hash)."""
    return skeleton_hash(mutable_source(root, config), definitions=config.mutable_definitions)


def allocation(root: Path, config: ExperimentConfig) -> dict[str, list[str]]:
    """The provider externs each non-prompt mutable definition names, in source order."""
    return provider_allocation(mutable_source(root, config), definitions=config.mutable_definitions)


def episode_diff(parent: Path, child: Path) -> str:
    """Unified diff of the content files, parent to child; a file missing on one side diffs against nothing."""
    def lines(path: Path) -> list[str]:
        return path.read_text(errors="replace").splitlines(keepends=True) if path.is_file() else []
    return "".join(line for name in _file_names(parent, child)
                   for line in difflib.unified_diff(lines(parent / name), lines(child / name), f"a/{name}", f"b/{name}"))


def scan_episode(records: Path, tree: Path, *, runtime: Path, evidence_root: Path, solutions: Mapping[str, str],
                 holdouts: Sequence[Path], created_at: float) -> list[dict]:
    """`prepare.scan` over the episode's shim records, once per distinct solution hash until one scan hits; its
    record.json then holds the scan that hit (or the last one)."""
    dump(records / "record.json", {"tree": str(tree), "main": str(main_checkout(runtime)), "runtime": str(runtime),
                                   "created_at": created_at})
    roots = [("archive", evidence_root), ("lineage", evidence_root / "log.jsonl"),
             *(("holdout", holdout) for holdout in holdouts)]
    # ponytail: stops at the first hit; after clearing that scan, rescan with the remaining hashes (prepare.py scan)
    for solution in sorted(set(solutions.values())):
        hits = prepare.scan(records, solution, roots=roots)
        if hits:
            return hits
    return []


def unguided_episode(parent_root: Path, config: ExperimentConfig, *, agent_cmd: Sequence[str], work_root: Path,
                     evidence_root: Path, episode_index: int, runtime: Path, env: Mapping[str, str],
                     solutions: Mapping[str, str], call_cap: int, holdouts: Sequence[Path] = ()) -> dict:
    """One I1 episode against the archived parent (refused beyond the call cap): the agent command edits a copy
    of it behind the shims (see the module docstring); the child is the copy's final files, whose diff is kept.
    The episode is scanned; an accepted child is archived; the episode record is appended to the log."""
    work_root, evidence_root = check_roots(work_root, evidence_root)
    commit = runtime_commit(runtime)
    parent_id = check_archived(parent_root, commit)
    episode_id = "sha256:" + hashlib.sha256(json.dumps(
        [parent_id, config.interface, config.condition, config.episode_wall_clock_sec, episode_index]).encode()
    ).hexdigest()
    slot = ledger.reserve(evidence_root, kind="episode", key=episode_id, planned=1, cap=call_cap)
    parent_shape = {"parent_skeleton": skeleton(parent_root, config),  # before the episode, which may be paid
                    "parent_provider_allocation": allocation(parent_root, config)}
    tree, records = work_root / "episodes" / f"episode-{episode_index}", evidence_root / "episodes" / episode_id
    copy, base = episode_workspace(parent_root, tree, episode_brief(config, episode_index), runtime)
    records.mkdir(parents=True)
    created_at, started = time.time(), time.monotonic()
    stopped, status = run_agent(agent_cmd, copy, evidence_root / "episodes" / f"episode-{episode_index}.log", env,
                                config.episode_wall_clock_sec, runtime=runtime, shim_env={
                                    "COMPARE_ROOT": records, "COMPARE_TREE": tree, "COMPARE_BASE": base,
                                    "TMPDIR": tree / "tmp"})
    elapsed = time.monotonic() - started
    calls = ledger.settle(evidence_root, slot, records)
    hits = scan_episode(records, tree, runtime=runtime, evidence_root=evidence_root, solutions=solutions,
                        holdouts=holdouts, created_at=created_at)
    (copy / EPISODE).unlink(missing_ok=True)
    shutil.rmtree(copy / ".git")  # the child is the copy's content files; the shims kept every call's patch
    (evidence_root / "episodes" / f"{episode_id}.diff").write_text(episode_diff(parent_root, copy))
    row = {"kind": "episode", "mode": "unguided", "interface": config.interface, "condition": config.condition,
           "episode_id": episode_id, "episode_index": episode_index, "parent_candidate_id": parent_id,
           "candidate_id": candidate_id(copy, orchestrator_commit=commit), "agent_cmd": list(agent_cmd),
           "agent_exit": status, "envelope": {"wall_clock_sec": config.episode_wall_clock_sec},
           "wall_clock_sec": elapsed, "provider_calls": calls, "scan_hits": len(hits), "scan_pending": bool(hits),
           "consumption": UNAVAILABLE, "model_revision": UNAVAILABLE,
           "hypothesis": UNAVAILABLE, "refusal_code": None, "diagnostics_class": None, "skeleton": None,
           "provider_allocation": None, **parent_shape}
    row.update({"outcome": stopped} if stopped else judge_child(parent_root, copy, config, runtime=runtime))
    if row["outcome"] == "accepted":
        _, root = archive(copy, evidence_root, runtime)
        row.update(candidate_root=str(root), skeleton=skeleton(root, config),
                   provider_allocation=allocation(root, config))
    with _LOG_LOCK:
        append_record(evidence_root / "log.jsonl", row)
    return row


def share(count: int, total: int) -> float | str:
    return count / total if total else UNAVAILABLE


def catalog_outcomes(rows: Sequence[Mapping]) -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for row in rows:
        if row["kind"] == "evaluation" and row["mode"] == "catalog":
            entry = catalog.setdefault(row["seed"], {"candidate_id": row["candidate_id"], "outcomes": []})
            entry["outcomes"].append(row["outcome"])
    return catalog


def child_outcomes(rows: Sequence[Mapping]) -> dict[str, list]:
    children: dict[str, list] = {}
    for row in rows:
        if row["kind"] == "evaluation" and row["mode"] == "unguided":
            children.setdefault(row["candidate_id"], []).append(row["outcome"])
    return children


def revisit_count(accepted: Sequence[Mapping]) -> int:
    seen, revisits = set(), 0
    for row in accepted:
        seen.add(row["parent_skeleton"])
        revisits += row["skeleton"] in seen
        seen.add(row["skeleton"])
    return revisits


def diversity(accepted: Sequence[Mapping]) -> dict:
    """Skeleton diversity among accepted children. A child is terminal-only when both its skeleton and its
    provider allocation equal the parent's; one with the parent's skeleton but another allocation is
    `allocation_distinct`."""
    same_skeleton = [row for row in accepted if row["skeleton"] == row["parent_skeleton"]]
    terminal = sum(row["provider_allocation"] == row["parent_provider_allocation"] for row in same_skeleton)
    terminal_only = share(terminal, len(accepted))
    return {"distinct_skeletons": len({row["skeleton"] for row in accepted}),
            "revisit_rate": share(revisit_count(accepted), len(accepted)), "terminal_only_share": terminal_only,
            "allocation_distinct": len(same_skeleton) - terminal,
            "collapsed": terminal_only if terminal_only == UNAVAILABLE else terminal_only > COLLAPSE_THRESHOLD}


def readout(rows: Sequence[Mapping]) -> dict:
    """Per-seed outcomes, episode outcomes and refusals, skeleton diversity and provider allocation among
    accepted children, their evaluation outcomes and the evaluations and episodes pending a scan verdict."""
    episodes = [row for row in rows if row["kind"] == "episode"]
    accepted = [row for row in episodes if row["outcome"] == "accepted"]
    return {"catalog": catalog_outcomes(rows), "episodes": dict(Counter(row["outcome"] for row in episodes)),
            "refused": dict(Counter(row["refusal_code"] or row["diagnostics_class"]
                                    for row in episodes if row["outcome"] == "rejected")),
            **diversity(accepted), "child_outcomes": child_outcomes(rows),
            "scan_pending": [row.get("evaluation_id") or row["episode_id"] for row in rows if row.get("scan_pending")]}


def run_mode1(config_path: Path, *, seeds: Sequence[Path], tasks: Sequence[Path], work_root: Path,
              evidence_root: Path, episodes: int, agent_cmd: Sequence[str], replicates: int, runtime: Path,
              env: Mapping[str, str], timeout_sec: float, solutions: Mapping[str, str], call_cap: int,
              concurrency: int = 1, holdouts: Sequence[Path] = ()) -> dict:
    """Enumerate the catalog, run `episodes` unguided I1 episodes against the seed the configuration's entry
    names, evaluate every accepted child like a seed (`mode: "unguided"`) and write <evidence>/readout.json.
    Evaluations run at most `concurrency` at a time; every launch is refused beyond `call_cap` provider calls."""
    config = load_config(config_path)
    work_root, evidence_root = check_roots(work_root, evidence_root)
    if (evidence_root / "log.jsonl").exists():
        raise FileExistsError(f"{evidence_root / 'log.jsonl'} exists: give every mode 1 run a fresh evidence root "
                              "(the driver never resumes or appends to an earlier run)")
    solutions = check_solutions(tasks, solutions, runtime)
    launch = {"work_root": work_root, "evidence_root": evidence_root, "runtime": runtime, "env": env,
              "timeout_sec": timeout_sec, "solutions": solutions, "holdouts": holdouts, "call_cap": call_cap}
    catalog = enumerate_catalog(seeds, config, tasks=tasks, replicates=replicates, concurrency=concurrency, **launch)
    module = config.entry_workflow.split("::")[0]
    parents = {row["candidate_root"] for row in catalog if row["seed"] == module}
    if len(parents) != 1:
        raise ValueError(f"the entry {config.entry_workflow} names no seed among {[s.name for s in seeds]}")
    parent = Path(parents.pop())
    for index in range(episodes):
        episode = unguided_episode(parent, config, agent_cmd=agent_cmd, work_root=work_root,
                                   evidence_root=evidence_root, episode_index=index, runtime=runtime, env=env,
                                   solutions=solutions, call_cap=call_cap, holdouts=holdouts)
        if episode["outcome"] == "accepted":
            fields = {"mode": "unguided", "episode_id": episode["episode_id"], "candidate_id": episode["candidate_id"],
                      "parent_candidate_id": episode["parent_candidate_id"], "candidate_root": episode["candidate_root"]}
            evaluate_all([(Path(episode["candidate_root"]), config, fields)], tasks=tasks, replicates=replicates,
                         concurrency=concurrency, **launch)
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
    parser.add_argument("--call-cap", type=int, required=True,
                        help="provider calls (evaluations and episodes) recorded in <evidence>/calls.json, at most")
    parser.add_argument("--concurrency", type=int, default=1, help="evaluations in flight, at most")
    a = parser.parse_args(argv)
    run_mode1(a.config, seeds=a.seeds, tasks=a.tasks, work_root=a.work_root, evidence_root=a.evidence,
              episodes=a.episodes, agent_cmd=shlex.split(a.agent_cmd), replicates=a.replicates, runtime=a.runtime,
              env=os.environ, timeout_sec=a.eval_timeout_sec, solutions=dict(a.solution), call_cap=a.call_cap,
              concurrency=a.concurrency, holdouts=a.holdout)
    print(a.evidence / "readout.json")


if __name__ == "__main__":
    main()
