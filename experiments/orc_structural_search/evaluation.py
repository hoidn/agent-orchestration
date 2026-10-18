"""One evaluation: an accepted candidate run through the public `run` route in a fresh task clone.

Design: docs/design/orc_structural_search_driver.md, "Execution Contract". `evaluate` compiles the candidate
(a rejected one is refused: only accepted children are evaluated), lets the comparison harness's `run_arm`
build the clone and write `command.sh`/`resume.sh` behind the shims, copies the frozen `dev_check.py` into
the clone (excluded from its patches), runs `command.sh` and classifies the run's memo. The evidence root is
also `run_arm`'s work root:

  <evidence>/runs/<evaluation_id>/<run_id>/   the orchestrator's state (--state-dir): run.json, memo.jsonl
  <evidence>/records/<evaluation_id>/run-1/   record.json, inputs.json, command.sh, resume.sh, calls/<n>/,
                                              launch-<k>.log (k = resume count)
  <evidence>/agents/<16 hex>/cand-1/          the clone (the run's working directory)
  <evidence>/env-manifests/<digest>.json      the environment manifest whose digest is in the identity

Outcome: the memo's terminal row `completed` -> completed, another terminal -> failed (the runtime writes a
failed terminal when a provider exits nonzero), no terminal (the run died, or never started) -> incident; an
incident is resumed under the same evaluation id, never replicated. A launch still running after `timeout_sec`
seconds (required) has its process group killed (SIGKILL), which leaves no terminal: an incident.

Dependencies: git and bwrap on PATH; `env` (the launch environment) must put the real or scripted
`claude`/`codex` on PATH; the runtime checkout must be clean (run_arm refuses it otherwise).
"""

import hashlib
import importlib.metadata
import json
import os
import platform
import signal
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from experiments.compare.prepare import ArmSpec, read_memo, run_arm
from experiments.compare.repos import load, runtime_commit
from experiments.orc_structural_search.candidates import candidate_id, compile_candidate
from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.records import UNAVAILABLE

EVALUATOR_VERSION = "public-run-1"
DEV_CHECK = Path(__file__).resolve().parent / "seeds" / "dev_check.py"
INPUTS = ("task", "intent", "repo")


@dataclass(frozen=True)
class EvaluationRecord:
    evaluation_id: str
    run_id: str  # UNAVAILABLE when no run started
    state_dir: Path
    records_dir: Path  # <evidence>/records/<evaluation_id>/run-1
    outcome: str  # "completed" | "failed" | "incident"
    value: object | None  # the terminal value when completed
    wall_clock_sec: float | str  # summed over launch and resumes
    provider_calls: int | str  # shim call directories, summed over launch and resumes
    resume_count: int
    incidents: tuple[str, ...]


def evaluation_id(candidate: str, task_id: str, evaluator_version: str, env_manifest_digest: str,
                  replicate: int) -> str:
    """Bare sha256 hex over the identity fields (it names the state directory)."""
    fields = [candidate, task_id, evaluator_version, env_manifest_digest, replicate]
    return hashlib.sha256(json.dumps(fields).encode()).hexdigest()


def record_env_manifest(evidence_root: Path) -> str:
    """Write this interpreter's environment manifest (Python, platform, installed distributions) under the
    evidence root; return its sha256 digest."""
    manifest = {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
                "distributions": sorted({f"{d.metadata['Name']}=={d.version}"
                                         for d in importlib.metadata.distributions()})}
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(text.encode()).hexdigest()
    path = evidence_root / "env-manifests" / f"{digest}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return f"sha256:{digest}"


def evaluate(candidate_root: Path, config: ExperimentConfig, *, task_package: Path, evidence_root: Path,
             replicate: int, runtime: Path, env: Mapping[str, str], timeout_sec: float) -> EvaluationRecord:
    """Run the accepted candidate once in a fresh clone of the task package; see the module docstring."""
    candidate_root, evidence_root = candidate_root.resolve(), evidence_root.resolve()
    compiled = compile_candidate(candidate_root, config)
    if compiled.status != "accepted":
        raise ValueError(f"{candidate_root} does not compile; only accepted candidates are evaluated: "
                         f"{compiled.diagnostics}")
    candidate = candidate_id(candidate_root, orchestrator_commit=runtime_commit(runtime))
    eid = evaluation_id(candidate, task_package.name, EVALUATOR_VERSION, record_env_manifest(evidence_root),
                        replicate)
    state_dir = evidence_root / "runs" / eid
    if (evidence_root / "records" / eid).exists():  # even a launch that died before its run started
        raise FileExistsError(f"{evidence_root / 'records' / eid}: evaluation {eid} already ran; "
                              "resume it rather than rerun it")
    source_root = candidate_root / config.source_root
    spec = ArmSpec(
        source=(source_root / config.entry_workflow.split("::")[0]).with_suffix(".orc"),
        entry=config.entry_workflow, source_root=source_root, providers=candidate_root / config.providers_file,
        inputs=INPUTS, state_dir=state_dir,
        command_boundaries=config.command_boundaries_file and candidate_root / config.command_boundaries_file)
    records = run_arm(task_package, eid, evidence_root, runtime, spec=spec)
    clone = Path(load(records / "record.json")["candidates"][0])
    shutil.copyfile(DEV_CHECK, clone / DEV_CHECK.name)
    with (clone / ".git" / "info" / "exclude").open("a") as exclude:  # not part of the agent's patch
        exclude.write(f"/{DEV_CHECK.name}\n")
    pending = EvaluationRecord(eid, UNAVAILABLE, state_dir, records, "incident", None, 0.0, 0, 0, ())
    return _launch(pending, ["bash", str(records / "command.sh")], env, timeout_sec)


def resume(record: EvaluationRecord, *, env: Mapping[str, str], timeout_sec: float) -> EvaluationRecord:
    """Resume an incident's run (`orchestrator resume <run_id> --state-dir <state_dir>` through resume.sh)
    under the same evaluation id; resume_count goes up by one."""
    if record.outcome != "incident" or record.run_id == UNAVAILABLE:
        raise ValueError(f"evaluation {record.evaluation_id} is {record.outcome} with run id {record.run_id}: "
                         "only an incident with a started run can be resumed")
    resumed = replace(record, resume_count=record.resume_count + 1)
    return _launch(resumed, ["bash", str(record.records_dir / "resume.sh"), record.run_id], env, timeout_sec)


def _launch(record: EvaluationRecord, argv: list[str], env: Mapping[str, str],
            timeout_sec: float) -> EvaluationRecord:
    """Run `argv` (output in launch-<resume_count>.log) and fold its run's memo into `record`."""
    records = record.records_dir
    log = records / f"launch-{record.resume_count}.log"
    started = time.monotonic()
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
    run_id, outcome, value = _classify(record.state_dir)
    incidents = record.incidents
    if outcome == "incident":
        incidents += (f"launch {record.resume_count}: no terminal row in run {run_id} "
                      f"(launcher exit {status}; see {log})",)
    return replace(record, run_id=run_id, outcome=outcome, value=value, incidents=incidents,
                   wall_clock_sec=record.wall_clock_sec + elapsed,
                   provider_calls=len(list((records / "calls").glob("*"))))


def _classify(state_dir: Path) -> tuple[str, str, object | None]:
    """(run id, outcome, terminal value) of the one run under `state_dir`."""
    memos = sorted(state_dir.glob("*/memo.jsonl"))
    if len(memos) > 1:
        raise RuntimeError(f"{state_dir}: expected at most one run, found {[m.parent.name for m in memos]}")
    if not memos:
        return UNAVAILABLE, "incident", None
    rows = read_memo(memos[0])
    terminal = rows[-1] if rows and rows[-1]["record"] == "terminal" else None
    if terminal is None:
        return memos[0].parent.name, "incident", None
    if terminal["outcome"] == "completed":
        return memos[0].parent.name, "completed", terminal["value"]
    return memos[0].parent.name, "failed", None
