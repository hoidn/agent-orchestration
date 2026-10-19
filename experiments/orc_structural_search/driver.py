"""Mode 1 of the structural search driver (catalog enumeration and unguided I1 episodes) and the episode
function I1 and I2 share (run_episode).

Design: docs/design/orc_structural_search_driver.md ("Search Modes" mode 1, "Proposal Interfaces" I1 and I2,
"Edit Validation And Transactions", "Records", "Evaluation Hygiene"). Two roots, neither inside the other:

  work root (`run_arm`'s work root; an episode's CLI calls see only their own episode tree of it: hidden_roots)
    records/, runs/, agents/, env-manifests/   evaluations (see evaluation.py)
    episodes/episode-<n>/cand-1/               the mutator's working copy of the parent: a git repository whose
                                               one commit (the shims' COMPARE_BASE) is the parent snapshot
    episodes/episode-<n>/tmp/                  the mutator's private /tmp under the shims
    episodes/episode-<n>/py/orchestrator/      the runtime's orchestrator, for the brief's compile line
  evidence root (never shown to an agent; masked from an episode's CLI calls)
    log.jsonl                                  every episode and evaluation record, append-only
    calls.json                                 the provider-call ledger (ledger.py)
    candidates/<candidate_id>/                 the archive: catalog seeds and accepted children
    episodes/episode-<n>.log                   the mutator command's output
    episodes/<episode_id>/                     the episode's shim records (COMPARE_ROOT): calls/<n>/, record.json
    episodes/<episode_id>.diff                 the episode's final diff against its parent, whatever the outcome
    readout.json                               the mode 1 readout

The evidence root must be fresh unless `run_mode1` continues its run (`--continue`: quota.py, README "Quota
guard"); the driver never resumes an incident. A quota launch pauses new launches until the reset and is relaunched
as a new attempt (quota.QuotaGuard, with_retries). An archived candidate is checked before each episode and
evaluation: its content must still hash to its directory name (archive tamper check).

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

`run_mode1` (mode1.py) runs mode 1 over these functions; `main` is its command line.

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
from collections import namedtuple
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path

from experiments.compare import prepare
from experiments.compare.repos import (
    SEED_COMMIT, SEED_DATES, dump, git, guard, main_checkout, runtime_commit, shim_prefix, visible_in_sandbox)
from experiments.orc_structural_search import ledger
from experiments.orc_structural_search.acceptance import judge_child
from experiments.orc_structural_search.briefs import episode_brief
from experiments.orc_structural_search.candidates import _file_names, candidate_id, imports, snapshot
from experiments.orc_structural_search.config import ExperimentConfig, solution
from experiments.orc_structural_search.evaluation import EVALUATOR_VERSION, evaluate, is_python, records_root
from experiments.orc_structural_search.quota import PREFIX, QuotaGuard, quota_hit, with_retries
from experiments.orc_structural_search.records import (
    UNAVAILABLE, append_record, provider_allocation, python_provider_allocation, python_skeleton_hash, read_records,
    skeleton_hash)
from experiments.orc_structural_search.sites import HYPOTHESIS, drop_hypothesis

EPISODE = "EPISODE.md"
_LOG_LOCK = threading.Lock()  # concurrent evaluations append to one log
LAUNCH_ENV = {"DISABLE_AUTOUPDATER": "1"}  # added to every evaluation's and episode's environment


# one evaluation job (root, config, log fields, task package, replicate) and the attempt it launches as
Unit = namedtuple("Unit", "root config fields task replicate attempt", defaults=(1,))


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


def archive_seed(seed: Path, evidence_root: Path, runtime: Path) -> tuple[str, Path]:
    """(candidate id, archived root) of the seed's candidate root (seed_files)."""
    with tempfile.TemporaryDirectory() as staging:
        for name, data in seed_files(seed).items():
            (Path(staging) / name).write_bytes(data)
        return archive(Path(staging), evidence_root, runtime)


def seed_config(seed: Path, config: ExperimentConfig) -> ExperimentConfig:
    entry = config.entry_workflow.split("::")[1]
    return replace(config, entry_workflow=f"{seed.stem}::{entry}", mutable_files=(seed.name,))


def logged_evaluations(evidence_root: Path) -> set[str]:
    """The evaluation ids the log's evaluation rows name."""
    log = evidence_root / "log.jsonl"
    with _LOG_LOCK:
        rows = read_records(log) if log.exists() else []
    return {row["evaluation_id"] for row in rows if row["kind"] == "evaluation"}


def evaluate_and_scan(root: Path, config: ExperimentConfig, *, task: Path, replicate: int, work_root: Path,
                      evidence_root: Path, runtime: Path, env: Mapping[str, str], timeout_sec: float,
                      solutions: Mapping[str, str], holdouts: Sequence[Path], fields: Mapping[str, object],
                      call_cap: int, attempt: int = 1) -> dict:
    """Evaluate the archived `root` once as `attempt` (refused beyond the call cap), scan the run and append the
    evaluation record (with `fields`) to the log."""
    cid, env = check_archived(root, runtime_commit(runtime)), {**env, **LAUNCH_ENV}
    key = lambda n: f"{cid} {task.name} replicate {replicate}" + (f" attempt {n}" if n > 1 else "")  # noqa: E731
    while (killed := records_root(root, task_package=task, work_root=work_root, replicate=replicate, runtime=runtime,
                                  env=env, attempt=attempt)).exists():  # killed in flight, unlogged: skipped, settled
        if killed.name in logged_evaluations(evidence_root):
            raise FileExistsError(f"{killed}: evaluation {killed.name} already ran and is logged; resume it rather "
                                  "than rerun it")
        ledger.settle_killed(evidence_root, "evaluation", key(attempt), killed / "run-1")
        attempt += 1
    slot = ledger.reserve(evidence_root, kind="evaluation", key=key(attempt),
                          planned=ledger.planned_calls(root, config), cap=call_cap)
    record = evaluate(root, config, task_package=task, work_root=work_root, replicate=replicate,
                      runtime=runtime, env=env, timeout_sec=timeout_sec, attempt=attempt)
    ledger.settle(evidence_root, slot, record.records_dir, evaluation_id=record.evaluation_id)
    roots = [("archive", evidence_root), ("archive", work_root / "episodes"), ("lineage", evidence_root / "log.jsonl"),
             *(("holdout", holdout) for holdout in holdouts)]
    hits = prepare.scan(record.records_dir, solutions[task.name], roots=roots)
    row = {"split": UNAVAILABLE, **fields,  # mode 2 names the split
           **{k: str(v) if isinstance(v, Path) else v for k, v in asdict(record).items()},
           "kind": "evaluation", "task_id": task.name, "replicate": replicate, "evaluator_version": EVALUATOR_VERSION,
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


def units(jobs: Sequence[tuple[Path, ExperimentConfig, Mapping[str, object]]], tasks: Sequence[Path],
          replicates: int) -> list[Unit]:
    return [Unit(root, config, fields, task, replicate)
            for root, config, fields in jobs for task in tasks for replicate in range(1, replicates + 1)]


def evaluate_all(jobs: Sequence[tuple[Path, ExperimentConfig, Mapping[str, object]]], *, tasks: Sequence[Path],
                 replicates: int, concurrency: int, guard: QuotaGuard | None = None, **launch) -> list[dict]:
    """Evaluate each (root, config, fields) job once per task and replicate (launch_units)."""
    return launch_units(units(jobs, tasks, replicates), concurrency=concurrency, guard=guard, **launch)


def launch_units(pending: Sequence[Unit], *, concurrency: int, guard: QuotaGuard | None = None, **launch) -> list[dict]:
    """Evaluate each unit with at most `concurrency` evaluations in flight, a quota incident relaunched as the
    next attempt after the guard's pause (quota.with_retries); each unit's last row, in unit order. Every
    evaluation is attempted before the first failure (a launch refused at the call cap among them) is raised."""
    guard = guard or QuotaGuard()

    def run(unit: Unit) -> dict:
        return with_retries(lambda attempt: evaluate_and_scan(
            unit.root, unit.config, task=unit.task, replicate=unit.replicate, fields=unit.fields, attempt=attempt,
            **launch), guard, unit.attempt)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(run, unit) for unit in pending]
    return [future.result() for future in futures]


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
                      holdouts: Sequence[Path] = ()) -> list[dict]:
    """Archive every seed and evaluate it once per task and replicate (`mode: "catalog"`), at most `concurrency`
    evaluations at a time."""
    work_root, evidence_root = check_roots(work_root, evidence_root)
    solutions = check_solutions(tasks, solutions, runtime)
    return evaluate_all(catalog_jobs(seeds, config, evidence_root, runtime), tasks=tasks, replicates=replicates,
                        concurrency=concurrency, work_root=work_root,
                        evidence_root=evidence_root, runtime=runtime, env=env, timeout_sec=timeout_sec,
                        solutions=solutions, holdouts=holdouts, call_cap=call_cap)


def episode_workspace(parent_root: Path, tree: Path, brief: str, runtime: Path) -> tuple[Path, str]:
    """(<tree>/cand-1, its commit): a git repository holding the parent snapshot in one commit, with the brief
    in EPISODE.md (excluded from patches, like the build cache and the I2 HYPOTHESIS.txt); <tree>/tmp; and
    <tree>/py/orchestrator, a copy of the runtime's orchestrator for the brief's compile line (the shims strip
    PYTHONPATH, and naming the runtime would be a scan hit)."""
    guard(main_checkout(runtime), tree)
    visible_in_sandbox(tree)
    shutil.copytree(runtime / "orchestrator", tree / "py" / "orchestrator",
                    ignore=shutil.ignore_patterns("__pycache__"))
    copy = snapshot(parent_root, {}, tree / "cand-1")
    git(copy, "init", "-q")
    git(copy, "add", "-A", "-f", ".")
    git(copy, *SEED_COMMIT, env=SEED_DATES)
    (copy / ".git" / "info").mkdir(exist_ok=True)
    with (copy / ".git" / "info" / "exclude").open("a") as exclude:
        exclude.write(f"/{EPISODE}\n/{HYPOTHESIS}\n/.orchestrate/\n")
    (copy / EPISODE).write_text(brief)
    (tree / "tmp").mkdir()
    return copy, git(copy, "rev-parse", "HEAD")


def hidden_roots(work_root: Path, evidence_root: Path, hide: Sequence[Path] = ()) -> list[Path]:
    """The directories the shims mask from an episode's CLI calls (COMPARE_HIDE): the evidence root, every episode
    tree but the call's own (the shims bind it back), the work root's evaluation directories and the operator's
    `hide` (other runs' roots); each is created so bubblewrap finds a mount point."""
    roots = [root.resolve() for root in (
        evidence_root, *(work_root / name for name in ("episodes", "records", "runs", "agents", "env-manifests")), *hide)]
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
    return roots


def run_agent(agent_cmd: Sequence[str], cwd: Path, log: Path, env: Mapping[str, str], wall_clock_sec: float, *,
              runtime: Path, shim_env: Mapping[str, object]) -> tuple[str | None, int | str]:
    """Run the command from `cwd` behind the shim prefix (`shim_env`: COMPARE_ROOT, COMPARE_TREE, COMPARE_BASE,
    COMPARE_HIDE, TMPDIR) with <cwd>/EPISODE.md on stdin: (None when it exited 0, else "incident"; or "exhausted"
    after the wall clock), exit status."""
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


def mutable_source(root: Path, config: ExperimentConfig) -> str:
    suffix = ".py" if is_python(config) else ".orc"
    return "\n".join((root / name).read_text() for name in config.mutable_files if name.endswith(suffix))


def skeleton(root: Path, config: ExperimentConfig) -> str:
    """The skeleton hash of the mutable definitions; prompts contribute nothing (records.skeleton_hash, for an I3
    module records.python_skeleton_hash)."""
    hash_of = python_skeleton_hash if is_python(config) else skeleton_hash
    return hash_of(mutable_source(root, config), definitions=config.mutable_definitions)


def allocation(root: Path, config: ExperimentConfig) -> dict[str, list[str]]:
    """The provider externs (an I3 module: provider keys) each non-prompt mutable definition names, in source
    order."""
    allocate = python_provider_allocation if is_python(config) else provider_allocation
    return allocate(mutable_source(root, config), definitions=config.mutable_definitions)


def episode_diff(parent: Path, child: Path) -> str:
    """Unified diff of the content files, parent to child; a file missing on one side diffs against nothing."""
    def lines(path: Path) -> list[str]:
        return path.read_text(errors="replace").splitlines(keepends=True) if path.is_file() else []
    return "".join(line for name in _file_names(parent, child)
                   for line in difflib.unified_diff(lines(parent / name), lines(child / name), f"a/{name}", f"b/{name}"))


def scan_episode(records: Path, tree: Path, *, runtime: Path, work_root: Path, evidence_root: Path,
                 solutions: Mapping[str, str], holdouts: Sequence[Path], created_at: float) -> list[dict]:
    """`prepare.scan` over the episode's shim records, once per distinct solution hash until one scan hits; its
    record.json then holds the scan that hit (or the last one). The work root's evaluation directories are archive
    roots; the work root itself is none (the episode's own tree lies under it)."""
    dump(records / "record.json", {"tree": str(tree), "main": str(main_checkout(runtime)), "runtime": str(runtime),
                                   "created_at": created_at})
    roots = [("archive", evidence_root), ("lineage", evidence_root / "log.jsonl"),
             *(("archive", work_root / name) for name in ("records", "runs", "agents", "env-manifests")),
             *(("holdout", holdout) for holdout in holdouts)]
    # ponytail: stops at the first hit; after clearing that scan, rescan with the remaining hashes (prepare.py scan)
    for solution in sorted(set(solutions.values())):
        hits = prepare.scan(records, solution, roots=roots)
        if hits:
            return hits
    return []


def drop_git(copy: Path, base: str) -> bool:
    """Remove the workspace's .git, whatever the mutator left there (the child is the copy's content files; the
    shims kept every call's patch); False when it was removed or replaced (no repository holding `base`)."""
    dot_git = copy / ".git"
    intact = dot_git.is_dir() and not dot_git.is_symlink() and object_type(copy, base) == "commit"
    if dot_git.is_symlink() or dot_git.is_file():
        dot_git.unlink()
    elif dot_git.is_dir():
        shutil.rmtree(dot_git)
    return intact


def run_episode(parent_root: Path, config: ExperimentConfig, *, interface: str, mode: str, agent_cmd: Sequence[str],
                work_root: Path, evidence_root: Path, episode_index: int, runtime: Path, env: Mapping[str, str],
                solutions: Mapping[str, str], call_cap: int, holdouts: Sequence[Path] = (),
                site: Mapping | None = None, feedback: Mapping | None = None, generation: int | None = None,
                run_seed: int | None = None, hide: Sequence[Path] = ()) -> dict:
    """One episode against the archived parent (refused beyond the call cap): the agent command edits a copy of it
    behind the shims (see the module docstring), which mask hidden_roots (with `hide`) from its CLI calls, briefed
    by `briefs.episode_brief` (I2: `site`, which I1 must not have; `feedback`, the parent's own evidence); the child
    is the copy's final files, whose diff is kept. The episode is scanned and judged (judge_child; I2 through the
    one-site transaction); an accepted child is archived; the episode record is appended to the log."""
    if (interface == "I2") != (site is not None):
        raise ValueError(f"interface {interface} with site {site and site['site_id']}: an I2 episode needs a site, "
                         "an I1 episode takes none")
    work_root, evidence_root = check_roots(work_root, evidence_root)
    commit = runtime_commit(runtime)
    parent_id = check_archived(parent_root, commit)
    site_id = site["site_id"] if site else None
    identity = [parent_id, interface, config.condition, config.episode_wall_clock_sec, episode_index]
    if (generation, site_id, run_seed) != (None, None, None):  # Phase 1 episode ids stay as they were
        identity += [generation, site_id, run_seed]
    episode_id = "sha256:" + hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    slot = ledger.reserve(evidence_root, kind="episode", key=episode_id, planned=1, cap=call_cap)
    parent_shape = {"parent_skeleton": skeleton(parent_root, config),  # before the episode, which may be paid
                    "parent_provider_allocation": allocation(parent_root, config)}
    tree, records = work_root / "episodes" / f"episode-{episode_index}", evidence_root / "episodes" / episode_id
    brief = episode_brief(config, episode_index, site=site, feedback=feedback)
    copy, base = episode_workspace(parent_root, tree, brief, runtime)
    records.mkdir(parents=True)
    created_at, started = time.time(), time.monotonic()
    hidden = hidden_roots(work_root, evidence_root, hide)
    shim_env = {"COMPARE_ROOT": records, "COMPARE_TREE": tree, "COMPARE_BASE": base, "TMPDIR": tree / "tmp",
                "COMPARE_HIDE": os.pathsep.join(map(str, hidden))}
    stopped, status = run_agent(agent_cmd, copy, evidence_root / "episodes" / f"episode-{episode_index}.log",
                                {**env, **LAUNCH_ENV}, config.episode_wall_clock_sec, runtime=runtime, shim_env=shim_env)
    elapsed = time.monotonic() - started
    calls = ledger.settle(evidence_root, slot, records)
    quota = quota_hit(records)  # a quota episode is an incident whatever the agent's exit status
    incidents = [f"{PREFIX}{quota}"] * bool(quota)
    hits = scan_episode(records, tree, runtime=runtime, work_root=work_root, evidence_root=evidence_root,
                        solutions=solutions, holdouts=holdouts, created_at=created_at)
    (copy / EPISODE).unlink(missing_ok=True)
    intact = drop_git(copy, base)
    stopped = "incident" if quota else stopped or (None if intact else "incident")  # intact: the shims' base
    verdict = {"outcome": stopped, "receipt": None} if stopped else judge_child(
        parent_root, copy, config, runtime=runtime, site=site, parent_candidate_id=parent_id)
    drop_hypothesis(copy)  # judge_child read it into the receipt; it is never part of the child
    (evidence_root / "episodes" / f"{episode_id}.diff").write_text(episode_diff(parent_root, copy))
    row = {"kind": "episode", "mode": mode, "interface": interface, "condition": config.condition,
           "episode_id": episode_id, "episode_index": episode_index, "generation": generation, "run_seed": run_seed,
           "site_id": site_id, "feedback": feedback, "parent_candidate_id": parent_id,
           "candidate_id": candidate_id(copy, orchestrator_commit=commit), "agent_cmd": list(agent_cmd),
           "agent_exit": status, "envelope": {"wall_clock_sec": config.episode_wall_clock_sec},
           "wall_clock_sec": elapsed, "provider_calls": calls, "scan_hits": len(hits), "scan_pending": bool(hits),
           "workspace_intact": intact, "incidents": incidents, "hidden_roots": [str(root) for root in hidden],
           "consumption": UNAVAILABLE, "model_revision": UNAVAILABLE,
           "hypothesis": verdict["receipt"]["hypothesis"] if verdict["receipt"] else UNAVAILABLE,
           "refusal_code": None, "diagnostics_class": None, "skeleton": None,
           "provider_allocation": None, **parent_shape, **verdict}
    if row["outcome"] == "accepted":
        _, root = archive(copy, evidence_root, runtime)
        row.update(candidate_root=str(root), skeleton=skeleton(root, config),
                   provider_allocation=allocation(root, config))
    with _LOG_LOCK:
        append_record(evidence_root / "log.jsonl", row)
    return row


def main(argv: Sequence[str] | None = None) -> None:
    from experiments.orc_structural_search.mode1 import run_mode1  # mode1 imports this module
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
    parser.add_argument("--hide", type=Path, action="append", default=[],
                        help="a directory masked from every episode's CLI calls, e.g. another run's root (repeatable)")
    parser.add_argument("--call-cap", type=int, required=True,
                        help="provider calls (evaluations and episodes) recorded in <evidence>/calls.json, at most")
    parser.add_argument("--concurrency", type=int, default=4, help="evaluations in flight, at most")
    parser.add_argument("--continue", dest="continue_run", action="store_true",
                        help="continue the run in --evidence (same --work-root): relaunch its quota incidents")
    a = parser.parse_args(argv)
    run_mode1(a.config, seeds=a.seeds, tasks=a.tasks, work_root=a.work_root, evidence_root=a.evidence,
              episodes=a.episodes, agent_cmd=shlex.split(a.agent_cmd), replicates=a.replicates, runtime=a.runtime,
              env=os.environ, timeout_sec=a.eval_timeout_sec, solutions=dict(a.solution), call_cap=a.call_cap,
              concurrency=a.concurrency, holdouts=a.holdout, continue_run=a.continue_run, hide=a.hide)
    print(a.evidence / "readout.json")


if __name__ == "__main__":
    main()
