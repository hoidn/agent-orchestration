"""One evaluation: an accepted candidate run through the public `run` route in a fresh task clone.

Design: docs/design/orc_structural_search_driver.md, "Execution Contract". `evaluate` compiles the candidate
with the runtime's orchestrator (a rejected one is refused: only accepted children are evaluated), lets the
comparison harness's `run_arm` build the clone and write `command.sh`/`resume.sh` behind the shims, copies the
candidate root's `dev_check.py` (covered by its candidate id) into the clone (excluded from its patches), runs
`command.sh` and classifies the run's memo. An I3 candidate (`is_python`) is type-checked instead
(`acceptance.check_python`) and runs as the harness's generic command `python -P <entry module> inputs.json`
(no resume.sh); its state is <clone>/.orchestrate/runs, where it writes <run_id>/terminal.json, classified like a
memo's terminal row. The work root is `run_arm`'s work root, so it must be visible in the shims' sandbox (not
under /tmp, /dev/shm or /var/tmp) and outside the main checkout's prefix:

  <work>/runs/<evaluation_id>/<run_id>/   the orchestrator's state (--state-dir): run.json, memo.jsonl (not I3)
  <work>/records/<evaluation_id>/run-1/   record.json, inputs.json, command.sh, resume.sh, calls/<n>/,
                                          launch-<k>.log (k = resume count)
  <work>/agents/<16 hex>/cand-1/          the clone (the run's working directory)
  <work>/env-manifests/<digest>.json      the environment manifest whose digest is in the identity

The environment manifest holds Python, the platform, the installed distributions and the `--version` output of
claude, codex, bwrap and git as the launch environment's PATH finds them (a directory holding `model-guard`, the
shims', is skipped), so the evaluation id changes with a CLI version. Model names need no entry: they are the
candidate's provider bindings and `:model` values, already in its candidate id.

Outcome: the memo's terminal row `completed` -> completed, another terminal -> failed (the runtime writes a
failed terminal when a provider exits nonzero), no terminal (the run died, or never started) -> incident; an
incident is resumed under the same evaluation id, never replicated. A launch that is not completed and whose own
shim calls show a provider quota message (quota.py) is an incident whose latest incidents entry is
`quota: <first matching line>`: the driver relaunches it as a new attempt, whose evaluation id covers the attempt
number (attempts after the first only, so first attempts keep their ids). A launch still running after `timeout_sec`
seconds (required) has its process group killed (SIGKILL), which leaves no terminal: an incident.

Dependencies: git and bwrap on PATH; `env` (the launch environment) must put the real or scripted
`claude`/`codex` on PATH; the runtime checkout must be clean (run_arm refuses it otherwise).
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from experiments.compare.prepare import ArmSpec, read_memo, run_arm
from experiments.compare.repos import build_candidate, dump, git, load, runtime_commit
from experiments.orc_structural_search import acceptance, ledger, site_evidence, qualification  # acceptance imports this module: call time only
from experiments.orc_structural_search.candidates import candidate_id, compile_candidate
from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.metrics import is_python
from experiments.orc_structural_search.quota import PREFIX, quota_hit
from experiments.orc_structural_search.records import UNAVAILABLE

EVALUATOR_VERSION = "public-run-1"
DEV_CHECK = "dev_check.py"  # in the candidate root
FROZEN_PATHS = ("dev-check.json", "tests/")  # relative to a task package's seed
INPUTS = ("task", "intent", "repo")
CLIS = ("claude", "codex", "bwrap", "git")
CLI_VERSION_TIMEOUT_SEC = 60


@dataclass(frozen=True)
class EvaluationRecord:
    evaluation_id: str
    run_id: str  # UNAVAILABLE when no run started
    state_dir: Path
    records_dir: Path  # <work>/records/<evaluation_id>/run-1
    env_manifest_digest: str  # "sha256:..." of the environment manifest in the evaluation id
    outcome: str  # "completed" | "failed" | "incident"
    value: object | None  # the terminal value when completed
    wall_clock_sec: float | str  # summed over launch and resumes
    provider_calls: int | str  # shim call directories, summed over launch and resumes
    resume_count: int
    incidents: tuple[str, ...]
    attempt: int = 1  # quota relaunches of one job are attempts 2, 3, ...
    criterion_sha256: str | None = None
    realized_perform_sites: list[dict] | str = UNAVAILABLE
    exercised_branches: str = UNAVAILABLE
    branch_coverage_reason: str = "run_not_started"
    planned_perform_sites: list[dict] | str = UNAVAILABLE
    unexercised_perform_sites: list[dict] | str = UNAVAILABLE
    allocation_signature: dict | str = UNAVAILABLE
    allocation_signature_reason: str | None = "missing_closed_program"
    qualification: dict | None = None
    candidate_identity: str = UNAVAILABLE
    program_digest: str = UNAVAILABLE


def evaluation_id(candidate: str, task_id: str, evaluator_version: str, env_manifest_digest: str,
                  replicate: int, attempt: int = 1) -> str:
    """Bare sha256 hex over the identity fields (it names the state directory); the attempt only after the first."""
    fields = [candidate, task_id, evaluator_version, env_manifest_digest, replicate]
    fields += [attempt] if attempt > 1 else []
    return hashlib.sha256(json.dumps(fields).encode()).hexdigest()


def cli_version(name: str, env: Mapping[str, str]) -> str:
    """`<name> --version` output as `env`'s PATH finds it outside the shims' directory, or UNAVAILABLE."""
    path = os.pathsep.join(d for d in env.get("PATH", "").split(os.pathsep) if not (Path(d) / "model-guard").exists())
    found = shutil.which(name, path=path)
    if found is None:
        return UNAVAILABLE
    done = subprocess.run([found, "--version"], env=dict(env), stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=CLI_VERSION_TIMEOUT_SEC)
    return (done.stdout + done.stderr).strip()


def env_manifest(env: Mapping[str, str]) -> tuple[str, str]:
    """(text, sha256 hex digest) of the environment manifest (Python, platform, installed distributions, CLI
    versions under `env`)."""
    manifest = {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
                "distributions": sorted({f"{d.metadata['Name']}=={d.version}"
                                         for d in importlib.metadata.distributions()}),
                "cli": {name: cli_version(name, env) for name in CLIS}}
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    return text, hashlib.sha256(text.encode()).hexdigest()


def record_env_manifest(work_root: Path, env: Mapping[str, str]) -> str:
    """Write the environment manifest under the work root; return its "sha256:..." digest."""
    text, digest = env_manifest(env)
    path = work_root / "env-manifests" / f"{digest}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return f"sha256:{digest}"


def records_root(candidate_root: Path, *, task_package: Path, work_root: Path, replicate: int, runtime: Path,
                 env: Mapping[str, str], attempt: int = 1) -> Path:
    """<work>/records/<evaluation_id> of this attempt of the candidate on the task (writes nothing)."""
    candidate = candidate_id(candidate_root.resolve(), orchestrator_commit=runtime_commit(runtime))
    return work_root / "records" / evaluation_id(candidate, task_package.name, EVALUATOR_VERSION,
                                                  f"sha256:{env_manifest(env)[1]}", replicate, attempt)


def evaluate(candidate_root: Path, config: ExperimentConfig, *, task_package: Path, work_root: Path,
             replicate: int, runtime: Path, env: Mapping[str, str], timeout_sec: float,
             attempt: int = 1, criterion: Path | None = None) -> EvaluationRecord:
    """Run the accepted candidate once in a fresh clone of the task package; `work_root` is the sandbox-visible
    work root (see the module docstring); `attempt` > 1 is a quota relaunch of the same job."""
    checked = qualification.validate(criterion, tasks=[task_package], config_sha256=config.criterion_sha256,
                                     runtime=runtime)
    private = qualification.private_roots(criterion, public_roots=[runtime, task_package],
                                          workspace_roots=[candidate_root, work_root])
    env = qualification.hidden_env(env, private)
    if config.models is not None:
        env["COMPARE_CLAUDE_MODELS"] = ",".join(model for model in config.models if model.startswith("claude"))
    candidate_root, work_root = candidate_root.resolve(), work_root.resolve()
    orchestrator_commit = runtime_commit(runtime)
    candidate = candidate_id(candidate_root, orchestrator_commit=orchestrator_commit)
    python = is_python(config)
    compiled = (acceptance.check_python(candidate_root, config, runtime=runtime) if python
                else compile_candidate(candidate_root, config, runtime=runtime))
    if not python:
        acceptance.require_candidate(candidate_root, config, runtime=runtime, compiled=compiled)
    elif compiled.status != "accepted":
        raise ValueError(f"{candidate_root} does not compile; only accepted candidates are evaluated: "
                         f"{compiled.diagnostics}")
    if not (candidate_root / DEV_CHECK).is_file():
        raise FileNotFoundError(f"{candidate_root} has no {DEV_CHECK}: the clone's dev-check boundary would not run")
    env_digest = record_env_manifest(work_root, env)
    eid = evaluation_id(candidate, task_package.name, EVALUATOR_VERSION, env_digest, replicate, attempt)
    if (work_root / "records" / eid).exists():  # even a launch that died before its run started
        raise FileExistsError(f"{work_root / 'records' / eid}: evaluation {eid} already ran; "
                              "resume it rather than rerun it")
    source = ledger.entry_of(candidate_root, config)[0]
    spec = ArmSpec(
        source=source, entry=config.entry_workflow, source_root=candidate_root / config.source_root,
        providers=candidate_root / config.providers_file, inputs=INPUTS,
        state_dir=None if python else work_root / "runs" / eid,
        command_boundaries=config.command_boundaries_file and candidate_root / config.command_boundaries_file,
        command=(sys.executable, "-P", str(source)) if python else None)
    records = run_arm(task_package, eid, work_root, runtime, spec=spec, environment=env)
    arm = load(records / "record.json")
    arm.update(qualification=checked, qualification_private_roots=list(map(str, private)))
    dump(records / "record.json", arm)
    if "COMPARE_MAX_CALLS" in env:
        arm["planned_maximum"] = env["COMPARE_MAX_CALLS"]
        dump(records / "record.json", arm)
    if config.models is not None:
        arm["allowed_claude_models"] = [model for model in config.models if model.startswith("claude")]
        dump(records / "record.json", arm)
    state_dir, clone = Path(arm["state_root"]), Path(arm["candidates"][0])
    shutil.copyfile(candidate_root / DEV_CHECK, clone / DEV_CHECK)
    with (clone / ".git" / "info" / "exclude").open("a") as exclude:  # not part of the agent's patch
        exclude.write(f"/{DEV_CHECK}\n")
    pending = EvaluationRecord(eid, UNAVAILABLE, state_dir, records, env_digest, "incident", None, 0.0, 0, 0, (),
                               attempt, config.criterion_sha256, candidate_identity=candidate,
                               program_digest=compiled.program_digest or UNAVAILABLE)
    pending = replace(pending, qualification=checked)
    pending = replace(pending, **site_evidence.candidate_evidence(candidate_root, config, runtime=runtime,
                                                                  compiled=compiled,
                                                                  candidate_identity=candidate,
                                                                  orchestrator_commit=orchestrator_commit))
    return _launch(pending, ["bash", str(records / "command.sh")], env, timeout_sec)


def resume(record: EvaluationRecord, *, env: Mapping[str, str], timeout_sec: float,
           criterion: Path | None = None) -> EvaluationRecord:
    """Resume an incident's run (`orchestrator resume <run_id> --state-dir <state_dir>` through resume.sh)
    under the same evaluation id; resume_count goes up by one."""
    if criterion is None:
        qualification.validate(None)
    metadata = load(record.records_dir / 'record.json')
    runtime, task = Path(metadata['runtime']), Path(metadata['task'])
    checked = qualification.validate(criterion, tasks=[task], config_sha256=record.criterion_sha256, runtime=runtime)
    private = qualification.private_roots(criterion, public_roots=[runtime, task],
                                          workspace_roots=[Path(metadata['tree'])])
    env = qualification.hidden_env(env, private)
    metadata.update(qualification=checked, qualification_private_roots=list(map(str, private)))
    if not (record.records_dir / "resume.sh").is_file():
        raise ValueError(f"evaluation {record.evaluation_id} has no resume.sh: a generic-command run is not resumable")
    if record.outcome != "incident" or record.run_id == UNAVAILABLE:
        raise ValueError(f"evaluation {record.evaluation_id} is {record.outcome} with run id {record.run_id}: "
                         "only an incident with a started run can be resumed")
    metadata.pop('scan', None)  # A resume can change evidence without creating another provider call.
    dump(record.records_dir / 'record.json', metadata)
    resumed = replace(record, resume_count=record.resume_count + 1, qualification=checked)
    return _launch(resumed, ["bash", str(record.records_dir / "resume.sh"), record.run_id], env, timeout_sec)


def _launch(record: EvaluationRecord, argv: list[str], env: Mapping[str, str],
            timeout_sec: float) -> EvaluationRecord:
    """Run `argv` (output in launch-<resume_count>.log) and fold its run's memo and its calls' quota messages into
    `record`."""
    records = record.records_dir
    log = records / f"launch-{record.resume_count}.log"
    before = len(list((records / "calls").glob("*")))
    started = time.monotonic()
    metadata = load(records / "record.json")
    env = dict(env)
    if "planned_maximum" in metadata:
        env["COMPARE_MAX_CALLS"] = metadata["planned_maximum"]
    if "allowed_claude_models" in metadata:
        env["COMPARE_CLAUDE_MODELS"] = ",".join(metadata["allowed_claude_models"])
    with log.open("w") as out:
        launcher = subprocess.Popen(argv, env=dict(env), stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            status = launcher.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            # ponytail: kills the launcher's process group only; agent-turn providers start their own session and
            # would escape it (provider-result calls die with the run); kill by session when agent turns are used
            os.killpg(launcher.pid, signal.SIGKILL)
            status = launcher.wait()
    elapsed = time.monotonic() - started
    run_id, outcome, value = _classify(record.state_dir,
                                       generic=load(records / "record.json")["arm_kind"] == "generic-command")
    incidents = record.incidents
    quota = quota_hit(records, after=before) if outcome != "completed" else None
    if quota:
        outcome, incidents = "incident", incidents + (f"{PREFIX}{quota}",)
    elif outcome == "incident":
        incidents += (f"launch {record.resume_count}: no terminal row in run {run_id} "
                      f"(launcher exit {status}; see {log})",)
    if metadata.get('qualification_private_roots'):
        try:
            qualification.scan_evidence(records, metadata)
        except (SystemExit, json.JSONDecodeError, OSError, ValueError) as error:
            diagnostic = f'qualification_scan_incomplete: {type(error).__name__}: {error}'
            metadata.pop('scan', None)
            metadata['qualification_scan'] = {'hits': UNAVAILABLE, 'calls': len(list((records / 'calls').glob('*'))),
                                               'error': diagnostic}
            dump(records / 'record.json', metadata)
            outcome, incidents = 'incident', incidents + (diagnostic,)
    return replace(record, run_id=run_id, outcome=outcome, value=value, incidents=incidents,
                   wall_clock_sec=record.wall_clock_sec + elapsed,
                   provider_calls=len(list((records / "calls").glob("*"))),
                   **realized_effects(record.state_dir, run_id, generic=metadata["arm_kind"] == "generic-command",
                                      planned_sites=record.planned_perform_sites,
                                      candidate_identity=record.candidate_identity,
                                      program_digest=record.program_digest))


def realized_effects(state_dir: Path, run_id: str, *, generic: bool, planned_sites=UNAVAILABLE,
                     candidate_identity=UNAVAILABLE, program_digest=UNAVAILABLE) -> dict:
    """Validated memo effects are execution evidence; they do not identify exercised source branches."""
    result = {"realized_perform_sites": UNAVAILABLE, "unexercised_perform_sites": UNAVAILABLE,
              "exercised_branches": UNAVAILABLE,
              "branch_coverage_reason": "generic_command_has_no_orc_memo" if generic else "run_not_started"}
    if generic or run_id == UNAVAILABLE:
        return result
    from orchestrator.workflow.evaluated.views import load_evaluated_view
    view = load_evaluated_view(state_dir / run_id)
    planned = _bound_planned_sites(state_dir / run_id, planned_sites, candidate_identity, program_digest)
    realized = []
    for step in view["steps"].values():
        row = {"identity": step["identity"], "effect_class": step["effect_class"],
               "attempts": step.get("attempt", UNAVAILABLE), "status": step.get("status", UNAVAILABLE)}
        if row["effect_class"] == "provider":
            row["provider_role"] = (site_evidence.provider_role(row["identity"], planned)
                                     if isinstance(planned, list) else UNAVAILABLE)
        realized.append(row)
    result.update(realized_perform_sites=realized, branch_coverage_reason="memo_records_effects_only")
    result.update(planned_perform_sites=planned, unexercised_perform_sites=(
        site_evidence.unexercised_sites(planned, result["realized_perform_sites"],
                                        completed=view["status"] == "completed")
        if isinstance(planned, list) else UNAVAILABLE))
    return result


def _bound_planned_sites(run_dir: Path, planned_sites, candidate_identity, program_digest):
    if (not isinstance(planned_sites, list) or not isinstance(candidate_identity, str)
            or candidate_identity == UNAVAILABLE or not isinstance(program_digest, str)
            or program_digest == UNAVAILABLE):
        return UNAVAILABLE
    from orchestrator.contracts.closed_program.program import ClosedProgram, ClosedProgramInvalid
    try:
        program = ClosedProgram.from_artifact((run_dir / "closed_program.json").read_text())
    except (ClosedProgramInvalid, OSError, UnicodeDecodeError):
        return UNAVAILABLE
    return planned_sites if program.digest == program_digest else UNAVAILABLE


def _classify(state_dir: Path, *, generic: bool) -> tuple[str, str, object | None]:
    """(run id, outcome, terminal value) of the one run under `state_dir`: its memo's terminal row, or for a
    `generic` command the run directory holding a terminal.json (other directories there, such as an orchestrator run
    the agent started from the clone, are not the run; a run killed before writing it has no run id here)."""
    runs = sorted(state_dir.glob("*/terminal.json" if generic else "*/memo.jsonl"))
    if len(runs) > 1:
        raise RuntimeError(f"{state_dir}: expected at most one run, found {[m.parent.name for m in runs]}")
    if not runs:
        return UNAVAILABLE, "incident", None
    if generic:
        terminal = load(runs[0])
    else:
        rows = read_memo(runs[0])
        terminal = rows[-1] if rows and rows[-1]["record"] == "terminal" else None
    if terminal is None:
        return runs[0].parent.name, "incident", None
    if terminal["outcome"] == "completed":
        return runs[0].parent.name, "completed", terminal["value"]
    return runs[0].parent.name, "failed", None


def _patch_paths(patch: Path) -> set[str]:
    from experiments.compare.pool import sections
    return {path.decode(errors="replace") for paths, _ in sections(patch.read_bytes()) for path in paths}


def _is_frozen_path(path: str) -> bool:
    return any(path == root.rstrip("/") or (root.endswith("/") and path.startswith(root))
               for root in FROZEN_PATHS)


def _seeded_frozen_files(seed: Path) -> list[str]:
    frozen = []
    for path in seed.rglob("*"):
        if path.is_file():
            relative = path.relative_to(seed).as_posix()
            if _is_frozen_path(relative):
                frozen.append(relative)
    return sorted(frozen)


def _restore_seeded_files(seed: Path, clone: Path, frozen_files: list[str]) -> None:
    for relative in frozen_files:
        source, target = seed / relative, clone / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        shutil.copyfile(source, target)


def _copy_trusted_helper(clone: Path, runtime: Path) -> Path:
    helper = clone / DEV_CHECK
    if helper.is_symlink() or helper.is_file():
        helper.unlink()
    elif helper.is_dir():
        shutil.rmtree(helper)
    shutil.copyfile(runtime / "experiments/orc_structural_search/seeds" / DEV_CHECK, helper)
    return helper


def _run_trusted_check(clone: Path, helper: Path, bundle: Path, python: str, touched: list[str]) -> dict:
    env = {**os.environ, "PYTHONPATH": str(clone), "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(bundle)}
    done = subprocess.run([python, str(helper)], cwd=clone, env=env, capture_output=True, text=True)
    output = (done.stdout + done.stderr)[-4000:]
    try:
        report = load(bundle)
    except (OSError, json.JSONDecodeError):
        return {"passed": False, "failing": [f"trusted dev check exited {done.returncode} without a report"],
                "excerpt": output, "touched_frozen": touched}
    valid = (isinstance(report, dict) and isinstance(report.get("passed"), bool)
             and isinstance(report.get("failing"), list) and isinstance(report.get("excerpt"), str))
    if done.returncode or not valid:
        return {"passed": False, "failing": ["trusted dev check returned an invalid report"],
                "excerpt": output, "touched_frozen": touched}
    return {"passed": report["passed"], "failing": report["failing"], "excerpt": report["excerpt"],
            "touched_frozen": touched}


def check_first_attempt(task: Path, patch: Path, runtime: Path, python: str = sys.executable) -> dict:
    """Apply a candidate to a fresh seeded clone, then run the trusted agent-visible check."""
    task, patch, runtime = task.resolve(), patch.resolve(), runtime.resolve()
    seed = task / "seed"
    frozen_files = _seeded_frozen_files(seed)
    touched = sorted(path for path in _patch_paths(patch) if _is_frozen_path(path))
    base = git(runtime, "rev-parse", "--verify", (task / "base_commit").read_text().strip() + "^{commit}")
    with tempfile.TemporaryDirectory(prefix="orc-first-attempt-") as directory:
        clone = Path(directory) / "candidate"
        build_candidate(runtime, base, seed, clone)
        if patch.stat().st_size:
            exclude = set(frozen_files)
            done = subprocess.run(["git", "-C", str(clone), "apply", "--binary",
                                   *(f"--exclude={path}" for path in sorted(exclude)), str(patch)],
                                  capture_output=True, text=True)
            if done.returncode:
                return {"passed": False, "failing": [f"candidate patch does not apply: {done.stderr.strip()}"],
                        "excerpt": "", "touched_frozen": touched}
        _restore_seeded_files(seed, clone, frozen_files)
        helper = _copy_trusted_helper(clone, runtime)
        return _run_trusted_check(clone, helper, Path(directory) / "check-report.json", python, touched)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Controller-side structural-search evaluation checks.")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="run a task's trusted agent-visible check on a candidate patch")
    check.add_argument("--task", type=Path, required=True)
    check.add_argument("--patch", type=Path, required=True)
    check.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(check_first_attempt(args.task, args.patch, args.runtime), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
