"""The structural search three-arm compile-only readout: I1, I2 and I3 episodes against the rebound direct parents, the
stratified subset, its evaluations, judging through the ledger and the per-arm readout.

Plan: docs/plans/2026-10-19-orc-structural-search-three-arm-readout-plan.md (Task 6); every rule parameter comes
from criteria/three_arm.json (envelope, subset, locality, collapse_threshold, separation, i3). The roots, records,
episodes and evaluation launches are driver.py's (its module docstring); E is the evidence root, W the work root.

A run (run_three_arm) on a fresh E, or continuing one (`--continue`, as mode 1: quota incidents relaunched, killed
launches skipped); it refuses a mutator command other than the criterion's envelope.mutator and a run configuration
whose criterion_sha256 or episode wall clock, or an evaluation wall clock, is not the criterion's, and a `hide`
path that is not an existing directory, before any root exists:
  parents      both parent roots (`orc`: the direct seed with its coder rebound, the parent of I1 and I2; `python`:
               its matched typed Python workflow, the parent of I3) archived, the ORC parent compiled and the Python
               parent type-checked against the runtime (else RuntimeError, never caught); one {"kind": "parents", "orc",
               "python", "run_seed", "subset_seed", "pyright", "program_digests"} row (a continued run must name the
               same parents and seeds; it logs no second row)
  episodes     per arm in ARMS order until `episodes_per_arm` non-quota episodes of the arm exist (accepted,
               rejected, exhausted or incident; a quota incident is relaunched under the next index, at most
               guard.retries times); one at a time; indexes are global over the run; an I2 episode's site is drawn
               uniformly from the parent's eligible sites with random.Random(f"{run_seed} {index}") and the row
               carries run_seed; every row carries `arm` and `mode: "three_arm"`. A slot whose quota relaunches are
               used up stops the run at once (QuotaExhausted): rerun with --continue after the provider's reset
  subset       per arm (subset), from the log, without the children of contaminated episodes or repeated programs
               (scoring.contaminated_children, which refuses an episode with scan hits and no verdict: adjudicate,
               then --continue)
  readout      E/readout.json (compile_readout), written before the evaluations
  evaluations  each chosen child once per task (replicate 1; `mode: "three_arm"`, `arm`), at most `concurrency` in
               flight; reservation-aware (CapGate): a launch refused at the call cap while another is in flight waits
               for one to end and is retried; with none in flight the refusal (CallCapExceeded) is raised; every
               launch that starts after a quota pause waits it out; once a unit's quota relaunches are used up no
               further launch starts and the run raises QuotaExhausted
`smoke` evaluates the two archived parents once per task (`mode: "smoke"`, `parent`) and nothing else.

Judging (judge) scores one task's pool, built by `scoring pool` from E, through judging.score_pool (each judge's
ledger entry reserved before any judge runs) and logs one {"kind": "judging", "generation": -2, ...} row; the readout
(three_arm_readout.readout) reads each task's results.json (scoring.read_pool) and reports per arm and per child.
"""

import argparse
import hashlib
import itertools
import json
import os
import random
import re
import shlex
import threading
from collections import Counter
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from experiments.compare import summarize
from experiments.compare.repos import sha256_file
from experiments.orc_structural_search import qualification, judging, ledger
from experiments.orc_structural_search.acceptance import check_parent, diagnosis, require_candidate
from experiments.orc_structural_search.candidates import compile_candidate
from experiments.orc_structural_search.config import (
    ExperimentConfig, check_criterion_hashes, load_config, solution)
from experiments.orc_structural_search.driver import (
    archive, check_hide, check_roots, check_solutions, launch_units, run_episode)
from experiments.orc_structural_search.evaluation import cli_version
from experiments.orc_structural_search.mode1 import continued
from experiments.orc_structural_search.quota import QuotaGuard, prior_rows, quota_reason, with_retries
from experiments.orc_structural_search.readout import diversity, outcome, share
from experiments.orc_structural_search.records import (UNAVAILABLE, append_record, read_records)
from experiments.orc_structural_search.python_metrics import (python_program_digest)
from experiments.orc_structural_search.scoring import contaminated_children
from experiments.orc_structural_search.sites import eligible_sites, select_site, site_manifest

ARMS = ("I1", "I2", "I3")
PARENT_OF = {"I1": "orc", "I2": "orc", "I3": "python"}
MODE = "three_arm"
JUDGED = ("accepted", "rejected")  # an episode whose child was judged (locality's denominator)
# criterion "locality": the verdicts of an edit outside its scope
OUT_OF_SCOPE = frozenset({"scope_exceeded", "frozen_surface_changed", "digest_mismatch", "site_unlocatable",
                          "declaration_collision"})
DIFF_FILE = re.compile(r"^\+\+\+ b/(.+)$", re.M)  # driver.episode_diff's header of a file
SEEDS = ("orc", "python", "run_seed", "subset_seed")  # the parents row fields a continued run must repeat
EPISODE_KEYS = ("work_root", "evidence_root", "runtime", "env", "solutions", "call_cap", "holdouts", "criterion")
CONTINUE = "rerun with --continue after the provider's reset"


class QuotaExhausted(RuntimeError):
    """A launch's quota relaunches are used up: the run stops before any further launch (see CONTINUE)."""


HISTORICAL_CRITERION_SHA256 = "d994f8daad608b76e342fa4bedcbc03f1e3c771f719877937331035eb0ae97ba"


def load_criterion(path: Path) -> dict:
    return {**json.loads(Path(path).read_text()), "criterion_sha256": sha256_file(path)}


def arm_specs(criterion: Mapping) -> dict:
    return criterion.get("arms") or {arm: {"interface": arm, "condition": criterion["envelope"]["condition"],
                                           "parent": PARENT_OF[arm]}
                                       for arm in criterion["envelope"]["interfaces"]}


def check_row_criteria(rows: Sequence[Mapping], criterion: Mapping) -> None:
    """Never reuse another study's rows; only the frozen original admits historical rows without a hash."""
    expected = criterion.get("criterion_sha256")
    if expected is None:
        if "arms" in criterion:
            raise ValueError("criterion_sha256 required: load the successor with load_criterion")
        return  # historical helper callers supply the original criterion mapping without its file hash
    sources = [row for row in rows if row["kind"] in {"episode", "evaluation"}]
    check_criterion_hashes(sources, expected)
    for row in sources:
        if row.get("mode") == MODE and row.get("arm") not in arm_specs(criterion):
            raise ValueError(f"arm {row.get('arm')!r} is outside this criterion")


def arm_config(base: Path, arm: str, criterion: Mapping | None = None) -> ExperimentConfig:
    """Use an arm's interface and condition independently; its key is only a record/readout label."""
    interface, _, condition = arm.partition("/")
    spec = arm_specs(criterion)[arm] if criterion is not None else {
        "interface": interface, "condition": condition or "topology-only"}
    python = spec["interface"] == "I3"
    return replace(load_config(base), mutable_files=("direct.py",) if python else ("direct.orc",),
                   mutable_definitions=("run",), condition=spec["condition"], interface=spec["interface"],
                   entry_workflow="direct::run", source_root=".", providers_file="providers.json",
                   command_boundaries_file=None if python else "commands.json")


class CapGate:
    """Reservation-aware launches (criterion i3.planned_maximum) under the run's quota guard: `run` waits out a quota
    pause before every launch and relaunch, retries a launch refused at the call cap (ledger.reserve, before any
    workspace) once another launch of the gate has ended, and raises the refusal when no other launch is in flight
    and none ended since it started. A launch that returns a quota incident pauses the guard before the waiters
    wake, so none relaunches into the provider's limit. Once more than guard.retries launches of the gate, any job's,
    have ended in a quota incident since the last launch that did not (`streak`), no further launch starts: `run`
    raises QuotaExhausted (`exhausted`). Under a lasting limit at most max(concurrency, 1 + guard.retries) launches
    happen; a capacity blip that hits that many launches in flight at once also stops the run (for --continue)."""

    def __init__(self, guard: QuotaGuard) -> None:
        self.guard, self.running, self.ended, self.changed = guard, 0, 0, threading.Condition()
        self.streak, self.exhausted = 0, None  # quota incidents since the last launch that ended without one

    def run(self, launch: Callable[[], dict]) -> dict:
        while True:
            self.guard.wait()
            with self.changed:
                if self.exhausted:
                    raise QuotaExhausted(self.exhausted)
                self.running, seen = self.running + 1, self.ended
            try:
                row = launch()
            except ledger.CallCapExceeded as refusal:
                self.refused(refusal, seen)
                continue
            except BaseException:
                self.end(None)
                raise
            self.end(row)
            return row

    def refused(self, refusal: ledger.CallCapExceeded, seen: int) -> None:
        """Leave the gate; raise `refusal` when no launch is in flight and none ended since this one started (`seen`),
        else wait for one to end, unless one already has."""
        with self.changed:
            self.running -= 1
            if self.ended == seen and self.running == 0:
                self.changed.notify_all()  # waiters retry and find nothing in flight either
                raise refusal
            if self.ended == seen:
                self.changed.wait()

    def end(self, row: Mapping | None) -> None:
        """Leave the gate after a launch ended (`row`, None when it raised) and wake the waiters."""
        reason = quota_reason(row) if row is not None else None
        if reason:
            self.guard.pause(reason)
        with self.changed:
            if row is not None:
                self.streak = self.streak + 1 if reason else 0
            if reason and self.streak > self.guard.retries:
                self.exhausted = (f"{self.streak} evaluation launches in a row ended in a quota incident (the last "
                                  f"{row['evaluation_id']}: {reason}); {CONTINUE}")
            self.running, self.ended = self.running - 1, self.ended + 1
            self.changed.notify_all()


def archive_parents(parents: Mapping[str, Path], config_path: Path, *, evidence_root: Path, runtime: Path,
                    env: Mapping[str, str], run_seed: int, subset_seed: int) -> tuple[dict[str, Path], dict]:
    """(parent name -> archived root, the parents row): the program digests are the ORC parent's compiled one and
    the Python parent's entry module's (records.python_program_digest), exact repeats' references. The Python parent
    must type-check against the runtime (acceptance.check_parent) and the ORC parent compile with it, else
    RuntimeError, before anything is spent."""
    if sorted(parents) != ["orc", "python"]:
        raise ValueError(f"parents must be orc and python, not {sorted(parents)}")
    roots = {name: archive(Path(root), evidence_root, runtime)[1] for name, root in parents.items()}
    orc, python = arm_config(config_path, "I1"), arm_config(config_path, "I3")
    compiled = compile_candidate(roots["orc"], orc, runtime=runtime)
    if compiled.status != "accepted":
        raise RuntimeError(f"the ORC parent does not compile against {runtime}: {diagnosis(compiled)['detail']}")
    require_candidate(roots["orc"], orc, runtime=runtime, compiled=compiled)
    check_parent(roots["python"], python, runtime=runtime)
    digests = {"orc": compiled.program_digest,
               "python": python_program_digest(ledger.entry_of(roots["python"], python)[0].read_text())}
    row = {"kind": "parents", **{name: root.name for name, root in roots.items()}, "run_seed": run_seed,
           "subset_seed": subset_seed, "pyright": cli_version("pyright", env), "program_digests": digests}
    return roots, row


def log_parents(row: Mapping, prior: Sequence[Mapping], log: Path) -> None:
    """Append the parents row to a fresh run's log; refuse a continued run whose parents or seeds differ."""
    logged = [r for r in prior if r["kind"] == "parents"]
    if not logged:
        append_record(log, row)
    elif any(logged[0][key] != row[key] for key in SEEDS):
        raise ValueError(f"--continue with parents or seeds {[row[k] for k in SEEDS]} other than the run's "
                         f"{[logged[0][k] for k in SEEDS]}")


def episode(root: Path, config: ExperimentConfig, arm: str, index: int, sites: Sequence[Mapping], *, run_seed: int,
            agent_cmd: Sequence[str], hide: Sequence[Path], launch: Mapping) -> dict:
    """One episode of the arm against its archived parent; I2 at the seeded uniform site of `sites`."""
    site = select_site(sites, random.Random(f"{run_seed} {index}")) if arm == "I2" else None
    return run_episode(root, config, interface=config.interface, mode=MODE, agent_cmd=agent_cmd, episode_index=index, site=site,
                       run_seed=run_seed if site else None, hide=hide, fields={"arm": arm},
                       **{key: launch[key] for key in EPISODE_KEYS})


def episode_indexes(before: Sequence[Mapping], work_root: Path) -> Iterator[int]:
    """The run's next episode indexes: after the highest logged one, skipping each index whose tree exists (an
    episode killed in flight, whose ledger entry ledger.settle_killed_episodes settles)."""
    start = 1 + max((row["episode_index"] for row in before), default=-1)
    return (i for i in itertools.count(start) if not (work_root / "episodes" / f"episode-{i}").exists())


def run_episodes(roots: Mapping[str, Path], config_path: Path, *, episodes_per_arm: int, prior: Sequence[Mapping],
                 run_seed: int, agent_cmd: Sequence[str], hide: Sequence[Path], guard: QuotaGuard,
                 launch: Mapping, criterion: Mapping) -> None:
    """Each arm's episodes until `episodes_per_arm` non-quota episodes of it exist (see the module docstring)."""
    evidence_root = launch["evidence_root"]
    ledger.settle_killed_episodes(evidence_root)
    indexes = episode_indexes([row for row in prior if row["kind"] == "episode"], launch["work_root"])
    done = non_quota(prior, evidence_root)
    for arm, spec in arm_specs(criterion).items():
        missing = episodes_per_arm - done[arm]
        if missing <= 0:
            continue
        config, root = arm_config(config_path, arm, criterion), roots[spec["parent"]]
        sites = eligible_sites(site_manifest(root, config, runtime=launch["runtime"]), config) if arm == "I2" else ()
        for _ in range(missing):
            row = with_retries(lambda _attempt: episode(root, config, arm, next(indexes), sites, run_seed=run_seed,
                                                        agent_cmd=agent_cmd, hide=hide, launch=launch), guard)
            if reason := quota_reason(row, evidence_root):
                raise QuotaExhausted(f"arm {arm}, episode {row['episode_index']}: quota relaunches used up "
                                     f"({reason}); {CONTINUE}")


def non_quota(rows: Sequence[Mapping], evidence_root: Path) -> Counter:
    """Per arm, its three-arm episodes that are no quota incident (the envelope's episode count)."""
    return Counter(row["arm"] for row in rows if row["kind"] == "episode" and row.get("mode") == MODE
                   and quota_reason(row, evidence_root) is None)


def check_episodes(rows: Sequence[Mapping], episodes_per_arm: int, evidence_root: Path,
                   criterion: Mapping | None = None) -> None:
    """Refuse to choose the subset while an arm has fewer than `episodes_per_arm` non-quota episodes (its quota
    relaunches were used up): its subset could still change, and the provider is still at its limit."""
    counts = non_quota(rows, evidence_root)
    short = {arm: counts[arm] for arm in (arm_specs(criterion) if criterion else ARMS) if counts[arm] < episodes_per_arm}
    if short:
        raise RuntimeError(f"non-quota episodes {short} of arms short of {episodes_per_arm}: {CONTINUE}")


def check_run(config_path: Path, criterion: Path, agent_cmd: Sequence[str], timeout_sec: float) -> dict:
    """The frozen criterion; refuse a mutator command other than its envelope.mutator, a run configuration whose
    criterion_sha256 is not the criterion file's sha256 (hex) or whose episode wall clock is not the envelope's, and
    an evaluation wall clock other than the envelope's."""
    frozen, config = load_criterion(criterion), load_config(config_path)
    envelope = frozen["envelope"]
    pairs = {"--agent-cmd": (list(agent_cmd), shlex.split(envelope["mutator"])),
             "criterion_sha256": (config.criterion_sha256, sha256_file(criterion)),
             "episode_wall_clock_sec": (config.episode_wall_clock_sec, envelope["episode_wall_clock_sec"]),
             "models": (config.models, frozen.get("models")),
             "per_call_timeout_sec": (config.per_call_timeout_sec, frozen.get("per_call_timeout_sec")),
             "--eval-timeout-sec": (timeout_sec, envelope["evaluation_wall_clock_sec"])}
    wrong = [f"{name} {got!r}, not {want!r}" for name, (got, want) in pairs.items() if got != want]
    if wrong:
        raise ValueError(f"the run differs from the criterion {criterion}: {'; '.join(wrong)}")
    return frozen


def run_three_arm(config_path: Path, *, parents: Mapping[str, Path], tasks: Sequence[Path], work_root: Path,
                  evidence_root: Path, episodes_per_arm: int, agent_cmd: Sequence[str], runtime: Path,
                  env: Mapping[str, str], timeout_sec: float, solutions: Mapping[str, str], call_cap: int,
                  concurrency: int, run_seed: int, subset_seed: int, criterion: Path, hide: Sequence[Path] = (),
                  holdouts: Sequence[Path] = (), continue_run: bool = False, guard: QuotaGuard | None = None,
                  smoke: bool = False) -> dict:
    """One three-arm run (see the module docstring): the compile-only readout, also E/readout.json; with `smoke`
    (which takes no episodes) {"smoke": the parents' evaluation rows}. `guard` (tests) is the invocation's quota
    pause state; `hide` adds directories every episode's CLI calls cannot see (driver.hidden_roots)."""
    if smoke and episodes_per_arm:
        raise ValueError("a smoke run evaluates the parents only: pass episodes_per_arm 0")
    frozen = check_run(config_path, criterion, agent_cmd, timeout_sec)
    check_hide(hide)
    qualification.validate(criterion, tasks=tasks, config_sha256=load_config(config_path).criterion_sha256,
                           runtime=runtime)
    work_root, evidence_root = check_roots(work_root, evidence_root)
    prior = prior_rows(work_root, evidence_root, continue_run)
    check_row_criteria(prior, frozen)
    guard, log = guard or QuotaGuard(), evidence_root / "log.jsonl"
    launch = {"work_root": work_root, "evidence_root": evidence_root, "runtime": runtime, "env": env,
              "timeout_sec": timeout_sec, "solutions": check_solutions(tasks, solutions, runtime),
              "holdouts": holdouts, "call_cap": call_cap, "criterion": criterion}
    roots, row = archive_parents(parents, config_path, evidence_root=evidence_root, runtime=runtime, env=env,
                                 run_seed=run_seed, subset_seed=subset_seed)
    row["criterion_sha256"] = frozen["criterion_sha256"]
    log_parents(row, prior, log)
    result: dict = {}
    if smoke:
        jobs = [(roots[name], arm_config(config_path, arm), {"mode": "smoke", "parent": name,
                                                             "candidate_id": roots[name].name,
                                                             "candidate_root": str(roots[name])})
                for name, arm in (("orc", "I1"), ("python", "I3"))]
    else:
        run_episodes(roots, config_path, episodes_per_arm=episodes_per_arm, prior=prior, run_seed=run_seed,
                     agent_cmd=agent_cmd, hide=hide, guard=guard, launch=launch, criterion=frozen)
        rows = read_records(log)
        check_episodes(rows, episodes_per_arm, evidence_root, frozen)
        chosen = subset(rows, frozen, subset_seed, contaminated_children(log))
        result = compile_readout(rows, frozen, evidence_root)
        (evidence_root / "readout.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        jobs = [(Path(r["candidate_root"]), arm_config(config_path, arm, frozen),
                 {"mode": MODE, "arm": arm, **{key: r[key] for key in (
                     "episode_id", "candidate_id", "parent_candidate_id", "candidate_root")}})
                for arm, picked in chosen.items() for r in picked]
    gate = CapGate(guard)
    evaluated = launch_units(continued(jobs, tasks, 1, read_records(log)), concurrency=concurrency, guard=guard,
                             gate=gate.run, **launch)
    if gate.exhausted:  # the last unit used up its quota relaunches: no later unit raised it
        raise QuotaExhausted(gate.exhausted)
    return result or {"smoke": evaluated}


def tie_break(seed: int, candidate: str) -> str:
    return hashlib.sha256(f"{seed}:{candidate}".encode()).hexdigest()


def pick(eligible: Sequence[Mapping], taken: set[str], seed: int, count: int) -> list[dict]:
    """The criterion's subset rule over one arm's eligible children (by episode index) whose candidate id and program
    digest are not in `taken` (which grows by the chosen ones): the first; then the first later child with another
    skeleton than the first chosen child's, else the smallest tie_break among the rest; `count` at most."""
    chosen: list[dict] = []
    for _ in range(count):
        rest = [row for row in eligible if row["candidate_id"] not in taken and row["program_digest"] not in taken]
        other = [row for row in rest if chosen and row["skeleton"] != chosen[0]["skeleton"]]
        if not rest:
            break
        row = rest[0] if not chosen else other[0] if other else min(
            rest, key=lambda r: tie_break(seed, r["candidate_id"]))
        chosen.append(dict(row))
        taken |= {row["candidate_id"], row["program_digest"]}
    return chosen


def subset(rows: Sequence[Mapping], criterion: Mapping, seed: int,
           contaminated: Collection[str] = frozenset()) -> dict[str, list[dict]]:
    """Per arm, the chosen episode rows (criterion["subset"]): accepted three-arm children not among `contaminated`
    (scoring.contaminated_children's candidate ids) whose candidate id differs from the parent's and from every
    earlier chosen child's, in any arm in ARMS order (equal ids would share an evaluation id), and whose program
    digest differs from the parents' (the parents row's program_digests) and every earlier chosen child's (a
    comment-only or reformatted child is not paid for), by pick."""
    check_row_criteria(rows, criterion)
    parents = next((row for row in rows if row["kind"] == "parents"), {})
    taken: set[str] = set(parents.get("program_digests", {}).values())  # candidate ids and program digests
    chosen = {}
    for arm in arm_specs(criterion):
        eligible = sorted((row for row in rows if row["kind"] == "episode" and row.get("mode") == MODE
                           and row.get("arm") == arm and row["outcome"] == "accepted"
                           and row["candidate_id"] not in contaminated), key=lambda row: row["episode_index"])
        taken |= {row["parent_candidate_id"] for row in eligible}
        chosen[arm] = pick(eligible, taken, seed, criterion["subset"]["per_arm"])
    return chosen


def files_touched(evidence_root: Path, row: Mapping) -> list[str]:
    """The files the episode's final diff (E/episodes/<episode_id>.diff) names."""
    return sorted(set(DIFF_FILE.findall((evidence_root / "episodes" / f"{row['episode_id']}.diff").read_text())))


def exact_repeats(accepted: Sequence[Mapping], parent_digest: str | None) -> int:
    """Accepted children whose program digest is the parent's or an earlier accepted child's."""
    seen, repeats = {parent_digest}, 0
    for row in sorted(accepted, key=lambda row: row["episode_index"]):
        repeats += row["program_digest"] in seen
        seen.add(row["program_digest"])
    return repeats


def arm_figures(episodes: Sequence[Mapping], criterion: Mapping, evidence_root: Path,
                parent_digest: str | None) -> dict:
    """One arm's compile-only figures: episode outcomes (quota rows as quota_incident), completed (non-quota)
    episodes, acceptance per completed episode, refusals, locality over judged episodes and the files each touched,
    readout.diversity of the accepted children, exact repeats, and collapse against the criterion's threshold."""
    completed = [row for row in episodes if quota_reason(row, evidence_root) is None]
    judged = [row for row in completed if row["outcome"] in JUDGED]
    accepted = [row for row in judged if row["outcome"] == "accepted"]
    figures = diversity(accepted)
    terminal = figures["terminal_only_share"]
    return {"episodes": dict(Counter(outcome(row, evidence_root) for row in episodes)), "completed": len(completed),
            "judged": len(judged), "accepted": len(accepted), "acceptance_rate": share(len(accepted), len(completed)),
            **judged_figures(judged, evidence_root), **figures,
            "exact_repeats": exact_repeats(accepted, parent_digest),
            "collapsed": terminal if terminal == UNAVAILABLE else terminal > criterion["collapse_threshold"]}


def judged_figures(judged: Sequence[Mapping], evidence_root: Path) -> dict:
    """The judged episodes' refusals (refusal or diagnostics code), locality (out-of-scope verdicts over judged
    episodes) and the files each episode's final diff touched."""
    return {"refused": dict(Counter(row["refusal_code"] or row["diagnostics_class"]
                                    for row in judged if row["outcome"] == "rejected")),
            "locality": share(sum(row["refusal_code"] in OUT_OF_SCOPE for row in judged), len(judged)),
            "files_touched": {row["episode_id"]: files_touched(evidence_root, row) for row in judged}}


def compile_readout(rows: Sequence[Mapping], criterion: Mapping, evidence_root: Path) -> dict:
    """Per arm, never pooled: arm_figures of its three-arm episodes and `subset`, its chosen candidate ids (subset
    under the parents row's subset_seed)."""
    parents = next(row for row in rows if row["kind"] == "parents")
    chosen = subset(rows, criterion, parents["subset_seed"], contaminated_children(evidence_root / "log.jsonl"))
    episodes = [row for row in rows if row["kind"] == "episode" and row.get("mode") == MODE]
    return {"criterion_sha256": criterion.get("criterion_sha256", UNAVAILABLE),
            "collapse_threshold": criterion["collapse_threshold"],
            "arms": {arm: arm_figures([row for row in episodes if row["arm"] == arm], criterion, evidence_root,
                                      parents["program_digests"][spec["parent"]])
                     | {"subset": [row["candidate_id"] for row in chosen[arm]]} for arm, spec in arm_specs(criterion).items()}}


def judge(evidence_root: Path, pool: Path, task: Path, *, criterion: Path, judges: Sequence[str], solution: str,
          call_cap: int, scorer: Callable[[Path, str, str], None] | None = None) -> dict:
    """Score the task's pool (built by `scoring pool` from `evidence_root`) with each judge (MODEL[=PROVIDERS_JSON])
    through judging.score_pool (ledger entries reserved before any judge runs, refused beyond `call_cap`), wait for
    a verdict on each judge scan with hits, summarize, and log the judging row (returned)."""
    names, pool = [spec.partition("=")[0] for spec in judges], Path(pool).resolve()
    frozen = load_criterion(criterion)
    mapping = json.loads((pool / "records" / "mapping.json").read_text())
    if mapping.get("criterion_sha256") != frozen["criterion_sha256"]:
        raise ValueError("pool criterion_sha256 differs from the requested criterion")
    check_row_criteria(read_records(evidence_root / "log.jsonl"), frozen)
    checked = judging.score_pool(evidence_root, pool, f"three-arm {task.name}", names=names, solution=solution,
                       call_cap=call_cap, scorer=scorer or judging.run_judge, criterion=criterion)
    for name in names:
        judging.judge_scan(pool, name)
    summarize.summarize(pool, criterion)
    row = {"kind": "judging", "generation": -2, "task": task.name, "pool": str(pool),
           "results": str(pool / "records" / "results.json"), "qualification": checked}
    append_record(evidence_root / "log.jsonl", row)
    return row


def run_parser(sub: argparse._SubParsersAction) -> None:
    run = sub.add_parser("run", help="parents, episodes, subset, compile-only readout, evaluations")
    run.add_argument("--config", type=Path, required=True, help="the run configuration (an ExperimentConfig)")
    run.add_argument("--parents", type=solution, nargs=2, required=True, metavar="NAME=PATH",
                     help="orc=<rebound ORC parent root> python=<Python parent root>")
    run.add_argument("--criterion", type=Path, required=True, help="criteria/three_arm.json")
    run.add_argument("--tasks", type=Path, nargs="+", required=True, help="task package directories")
    run.add_argument("--work-root", type=Path, required=True, help="sandbox-visible work root")
    run.add_argument("--evidence", type=Path, required=True, help="evidence root, outside the work root")
    run.add_argument("--episodes-per-arm", type=int, required=True, help="non-quota episodes per arm (0 with --smoke)")
    run.add_argument("--agent-cmd", required=True, help="the mutator command line (shell words)")
    run.add_argument("--runtime", type=Path, required=True, help="the frozen runtime checkout")
    run.add_argument("--eval-timeout-sec", type=float, required=True, help="wall clock per evaluation launch")
    run.add_argument("--solution", type=solution, action="append", default=[], metavar="TASK=HASH", required=True,
                     help="a task package's solution commit for the scan (repeatable, one per task)")
    run.add_argument("--holdout", type=Path, action="append", default=[], help="a holdout root (repeatable)")
    run.add_argument("--hide", type=Path, action="append", default=[],
                     help="a directory masked from every episode's CLI calls, e.g. another run's root (repeatable)")
    run.add_argument("--call-cap", type=int, required=True, help="provider calls in <evidence>/calls.json, at most")
    run.add_argument("--concurrency", type=int, default=4, help="evaluations in flight, at most")
    run.add_argument("--run-seed", type=int, required=True, help="seeds the I2 site draws")
    run.add_argument("--subset-seed", type=int, required=True, help="seeds the subset's tie-break")
    run.add_argument("--continue", dest="continue_run", action="store_true",
                     help="continue the run in --evidence (same --work-root): relaunch its quota incidents")
    run.add_argument("--smoke", action="store_true", help="evaluate the two parents once per task, nothing else")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="The structural search three-arm compile-only readout.")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser(sub)
    judge_cmd = sub.add_parser("judge", help="score one task's pool through the ledger, then summarize it")
    for name in ("--evidence", "--pool", "--task", "--criterion"):
        judge_cmd.add_argument(name, type=Path, required=True)
    judge_cmd.add_argument("--judge", action="append", required=True, metavar="MODEL[=PROVIDERS_JSON]")
    judge_cmd.add_argument("--solution", required=True, help="the task's solution commit (the judge scan's hash)")
    judge_cmd.add_argument("--call-cap", type=int, required=True)
    readout_cmd = sub.add_parser("readout", help="the per-arm, per-child judged readout")
    for name in ("--log", "--driver-readout", "--criterion"):
        readout_cmd.add_argument(name, type=Path, required=True)
    readout_cmd.add_argument("results", type=Path, nargs="*", help="each task pool's records/results.json")
    a = parser.parse_args(argv)
    from experiments.orc_structural_search.three_arm_readout import readout  # it imports this module
    if a.command == "judge":
        result = judge(a.evidence, a.pool, a.task, criterion=a.criterion, judges=a.judge, solution=a.solution,
                       call_cap=a.call_cap)
    elif a.command == "readout":
        result = readout(a.log, a.driver_readout, a.criterion, a.results)
    else:
        result = run_three_arm(
            a.config, parents={name: Path(path) for name, path in a.parents}, tasks=a.tasks, work_root=a.work_root,
            evidence_root=a.evidence, episodes_per_arm=a.episodes_per_arm, agent_cmd=shlex.split(a.agent_cmd),
            runtime=a.runtime, env=os.environ, timeout_sec=a.eval_timeout_sec, solutions=dict(a.solution),
            call_cap=a.call_cap, concurrency=a.concurrency, run_seed=a.run_seed, subset_seed=a.subset_seed,
            criterion=a.criterion, hide=a.hide, holdouts=a.holdout, continue_run=a.continue_run, smoke=a.smoke)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
