"""Maintained consumer programs run on both routes with deterministic stand-ins.

Each program is copied into a fresh workspace at its repository path, unchanged, with
its checked-in manifests; the 2.35 copy differs only in its target header and in the
command closure each certified command row declares. `SHIM` is installed as the `codex`
and `claude` executables on PATH, so every request goes through the real provider
templates, ProviderExecutor and attempt lifecycle of either route: it answers from a
scripted plan per executable, writes the files the plan names (report files, edits in
the repository named by its prompt) and logs the request it received before answering, so
a dispatch the script does not expect still leaves a row. `LAUNCHER` is the stand-in
`scripts/launch_experiment.py`: `LAUNCH_PROBE` behind a log of its raw argv. Copied Python
assets (the watchdog's probe and publisher) log each execution's argv (`EXEC_LOG`).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_invalidate import _cli, _tree_bytes
from tests.test_workflow_evaluated_resume import _resume_cli
from tests.test_workflow_evaluated_verified_drain import STOP_AFTER_COMMIT
from tests.workflow_evaluated_totality_helpers import assert_commit_bytes, checked_run
from tests.workflow_lisp_improve_example_sources import LAUNCH_PROBE


ROOT = Path(__file__).resolve().parents[1]
COMPARISON = "experiments/orc_vs_single_call/workflows"
MIGRATIONS = "workflows/examples/inputs/workflow_lisp_migrations"
IMPROVE_INPUTS = "workflows/examples/inputs/improve_experiment_proposal"
IMPROVE_PROMPTS = "workflows/examples/prompts/workflows/improve_experiment_proposal"
FLAGS = {"providers": "--provider-externs-file", "prompts": "--prompt-externs-file",
         "commands": "--command-boundaries-file"}
STOPPED = 75  # STOP_AFTER_COMMIT's exit status right after the selected commit
BUGGY = "def add(a, b):\n    return a - b\n"
CANDIDATES = ("candidates/alpha", "candidates/beta")
BUNDLE = "ORCHESTRATOR_OUTPUT_BUNDLE_PATH"  # R2: differs between routes by rule
SITE = "ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY"  # R5: differs between routes by rule
FUTURE = "from __future__ import annotations\n"

SHIM = r'''import json, os, sys
from pathlib import Path
prompt = sys.stdin.buffer.read().decode("utf-8")
tool = Path(sys.argv[0]).name
log = Path("requests.jsonl")
rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
plan = json.loads(os.environ["CONSUMER_SHIM_PLAN"])
repos = sorted((repo for repo in plan.get("repos", []) if repo in prompt), key=prompt.index)
env = {key: value for key, value in os.environ.items() if key.startswith("ORCHESTRATOR_")}
with log.open("a", encoding="utf-8") as out:
    out.write(json.dumps({"tool": tool, "argv": sys.argv[1:], "prompt": prompt, "cwd": os.getcwd(),
                          "env": env, "repos": repos}) + "\n")
answer = plan[tool][sum(1 for row in rows if row["tool"] == tool)]
for name, text in answer.get("files", {}).items():
    if "{repo}" in name:
        (repo,) = repos
        name = name.replace("{repo}", repo)
    Path(name).parent.mkdir(parents=True, exist_ok=True)
    Path(name).write_text(text, encoding="utf-8")
for name, fields in answer.get("merge", {}).items():
    document = json.loads(Path(name).read_text(encoding="utf-8"))
    Path(name).write_text(json.dumps({**document, **fields}, indent=2) + "\n", encoding="utf-8")
if "exit" in answer:
    sys.exit(answer["exit"])
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(answer["result"]), encoding="utf-8")
'''

ARGV_LOG = '''import json as _json, os as _os, sys as _sys
with open(__file__ + ".argv.jsonl", "a", encoding="utf-8") as _log:
    _log.write(_json.dumps({"argv": _sys.orig_argv, "bundle": _os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"],
                            "PYTHONDONTWRITEBYTECODE": _os.environ.get("PYTHONDONTWRITEBYTECODE")}) + "\\n")
'''
LAUNCHER = ARGV_LOG + LAUNCH_PROBE
EXEC_LOG = '''import json as _json, sys as _sys
with open(__file__ + ".runs.jsonl", "a", encoding="utf-8") as _log:
    _log.write(_json.dumps(_sys.argv) + "\\n")
'''


def git(root: Path, *argv: str) -> str:
    return subprocess.run(["git", "-c", "user.name=Consumer Fixture", "-c", "user.email=fixture@example.invalid",
                           *argv], cwd=root, check=True, capture_output=True, text=True).stdout


def _repository(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "calc.py").write_text(BUGGY, encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "calc.py")
    git(root, "commit", "-qm", "Seed the bug")


def _launcher(root: Path) -> None:
    (root / "scripts").mkdir()
    (root / "scripts" / "launch_experiment.py").write_text(LAUNCHER, encoding="utf-8")


def _candidates(root: Path) -> None:
    _repository(root / CANDIDATES[0])
    for repo in CANDIDATES[1:]:
        git(root, "clone", "-q", CANDIDATES[0], repo)


@dataclass(frozen=True)
class Program:
    """A maintained source, its accepted old target and what its workspace holds."""

    source: str
    target: str
    entry: str
    source_root: str
    manifests: dict[str, str]
    assets: tuple[str, ...] = ()
    prepare: Callable[[Path], None] = lambda root: None


PROGRAMS = {
    "improve": Program(
        "workflows/examples/improve_experiment_proposal.orc", "2.33", "improve_experiment_proposal::run-experiment",
        "workflows/examples", {kind: f"{IMPROVE_INPUTS}/{kind}.json" for kind in FLAGS},
        (f"{IMPROVE_PROMPTS}/review.md", f"{IMPROVE_PROMPTS}/revise.md"), _launcher),
    "reviewed_change": Program(
        f"{COMPARISON}/reviewed_change.orc", "2.28", "reviewed_change::reviewed-change", COMPARISON,
        {"providers": f"{COMPARISON}/reviewed_change.providers.json"}, prepare=lambda root: _repository(root / "repo")),
    "best_of_n": Program(
        f"{COMPARISON}/best_of_n.orc", "2.28", "best_of_n::best-of-n", COMPARISON,
        {"providers": f"{COMPARISON}/best_of_n.providers.json"}, prepare=_candidates),
    "watchdog": Program(
        "workflows/library/generic_run_watchdog/watchdog.orc", "2.15", "generic_run_watchdog/watchdog::watchdog",
        "workflows/library", {kind: f"{MIGRATIONS}/generic_run_watchdog.{kind}.json" for kind in FLAGS},
        ("workflows/library/scripts/probe_orchestrator_run.py",
         "workflows/library/scripts/publish_run_watchdog_result.py",
         "workflows/library/prompts/generic_run_watchdog/repair_run_failure.md")),
}


def _copy(root: Path, relpath: str) -> None:
    """Copy one file to the same path under `root`; a Python script also logs its executions."""
    (root / relpath).parent.mkdir(parents=True, exist_ok=True)
    text = (ROOT / relpath).read_text(encoding="utf-8")
    if relpath.endswith(".py"):
        assert text.count(FUTURE) == 1
        text = text.replace(FUTURE, FUTURE + EXEC_LOG)
    (root / relpath).write_text(text, encoding="utf-8")


def executions(routes, *scripts: str) -> list[list[str]]:
    """Each copied script ran once per route with the same argv on both; the argv of each."""
    runs = [[jsonl(route.root / f"{script}.runs.jsonl") for script in scripts] for route in routes]
    assert [[len(rows) for rows in route_runs] for route_runs in runs] == [[1] * len(scripts)] * len(runs)
    assert all(route_runs == runs[0] for route_runs in runs)
    return [rows[0] for rows in runs[0]]


def install_shims(bin_dir: Path, monkeypatch, plan: dict) -> None:
    bin_dir.mkdir(parents=True)
    for tool in ("codex", "claude"):
        (bin_dir / tool).write_text(f"#!{sys.executable}\n" + SHIM, encoding="utf-8")
        (bin_dir / tool).chmod(0o700)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("CONSUMER_SHIM_PLAN", json.dumps(plan))


def install(root: Path, program: Program, inputs: dict, *, current: bool) -> list[str]:
    """Copy the program into `root`; return its workspace-relative frontend arguments."""
    for relpath in (program.source, *program.assets):
        _copy(root, relpath)
    if current:
        source, header = root / program.source, f'(:target-dsl "{program.target}")'
        text = source.read_text(encoding="utf-8")
        assert text.count(header) == 1
        source.write_text(text.replace(header, '(:target-dsl "2.35")'), encoding="utf-8")
    frontend = [program.source, "--entry-workflow", program.entry, "--source-root", program.source_root]
    (root / "manifests").mkdir(parents=True)
    for kind, relpath in program.manifests.items():
        rows = json.loads((ROOT / relpath).read_text(encoding="utf-8"))
        for row in rows.values() if current and kind == "commands" else ():
            row["closure"] = [row["stable_command"][1]]
        (root / "manifests" / f"{kind}.json").write_text(json.dumps(rows), encoding="utf-8")
        frontend += [FLAGS[kind], f"manifests/{kind}.json"]
    (root / "inputs.json").write_text(json.dumps(inputs), encoding="utf-8")
    program.prepare(root)
    return frontend


def sha256(text: str | bytes) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def jsonl(path: Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def requests(root: Path) -> list[dict]:
    """The provider requests the shim received in this workspace, in order."""
    return jsonl(root / "requests.jsonl")


def stop_after(root: Path, argv: list[str], marker: str) -> None:
    """Run `orchestrator <argv>` and stop it right after the first commit whose identity has `marker`."""
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", "STOP_AFTER_COMMIT": marker}
    stopped = subprocess.run([sys.executable, "-c", STOP_AFTER_COMMIT, *argv], cwd=root, env=env,
                             capture_output=True, text=True, check=False)
    assert stopped.returncode == STOPPED, stopped.stderr


@dataclass
class Route:
    """One route's run of a scenario: final value, logged requests and, on 2.35, its authority."""

    root: Path
    value: dict
    requests: list[dict]
    authority: object = None
    snapshot: object = None
    paused: list[dict] = field(default_factory=list)

    @property
    def commits(self) -> list[dict]:
        return [entry.data for entry in sorted(self.snapshot.active_commits.values(), key=lambda entry: entry.offset)]

    def started(self) -> Counter:
        return Counter(entry.data["identity"] for entry in self.snapshot.entries if entry.data["record"] == "started")

    def result(self, data: dict) -> str:
        """The workspace-relative result path of a committed or attempted effect (R2)."""
        return f".orchestrate/runs/{self.authority.run_root.name}/{data['result_path']}"


def old_route(root: Path, frontend: list[str], *options: str) -> Route:
    result = _run_cli(root, *frontend, "--input-file", "inputs.json", *options)
    assert result.returncode == 0, result.stderr
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    state = json.loads((run_root / "state.json").read_text(encoding="utf-8"))
    return Route(root, state["workflow_outputs"], requests(root))


def compile_current(root: Path, frontend: list[str]) -> None:
    compiled = _cli(root, "compile", *frontend)
    (root / "compile.stdout").write_text(compiled.stdout, encoding="utf-8")
    assert compiled.returncode == 0, compiled.stderr


def resume_without_bytecode_flag(root: Path, run_id: str) -> subprocess.CompletedProcess[str]:
    """`orchestrator resume` with no PYTHONDONTWRITEBYTECODE of its own, so only R10 gives commands one.

    Its bytecode goes under a prefix next to the workspace, never into the package or workspace.
    """
    env = {key: value for key, value in os.environ.items() if key != "PYTHONDONTWRITEBYTECODE"}
    env.update(PYTHONPATH=str(ROOT), PYTHONPYCACHEPREFIX=str(root.parent / "pycache"))
    return subprocess.run([sys.executable, "-m", "orchestrator", "resume", run_id], cwd=root, env=env,
                          capture_output=True, text=True, check=False)


def resume_to_completion(root: Path) -> Route:
    """CLI resume to the terminal value, then a completed CLI resume that changes no byte."""
    authority, _ = checked_run(root)
    prefix = authority.memo_path.read_bytes()
    resumed = resume_without_bytecode_flag(root, authority.run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert authority.memo_path.read_bytes().startswith(prefix)
    authority, snapshot = checked_run(root)
    assert snapshot.terminal.data["outcome"] == "completed"
    for entry in snapshot.active_commits.values():
        if entry.data["attempt"] == 1:
            assert_commit_bytes(authority, entry)
    before = _tree_bytes(root)
    completed = _resume_cli(root, authority.run_root.name)
    assert completed.returncode == 0, completed.stderr
    assert _tree_bytes(root) == before
    return Route(root, snapshot.terminal.data["value"], requests(root), authority, snapshot)


def current_route(root: Path, frontend: list[str], marker: str) -> Route:
    """Public compile, a run stopped after the `marker` commit, then `resume_to_completion`."""
    compile_current(root, frontend)
    stop_after(root, ["run", *frontend, "--input-file", "inputs.json"], marker)
    _, paused = checked_run(root)
    last = paused.entries[-1].data
    assert (paused.terminal, last["record"], marker in last["identity"]) == (None, "committed", True)
    assert not paused.pending_starts
    seen = requests(root)
    route = resume_to_completion(root)
    route.paused = seen
    return route


def r3(request: dict) -> str:
    """The prompt with the request's own R2 path, which R3 places in it once, named."""
    assert request["prompt"].count(request["env"][BUNDLE]) == 1
    return request["prompt"].replace(request["env"][BUNDLE], "<R2>")


def request_view(route: Route) -> list[tuple]:
    """What R1–R12 leave equal on both routes: executable, argv (R7 policy), the `ORCHESTRATOR_*`
    environment apart from R2/R5 (R1: no run state) and the prompt apart from R3."""
    assert {Path(request["cwd"]) for request in route.requests} <= {route.root.resolve()}  # R6
    return [(request["tool"], request["argv"], {key: value for key, value in request["env"].items()
                                                 if key not in (BUNDLE, SITE)}, r3(request))
            for request in route.requests]


def assert_request_lineage(route: Route) -> None:
    """R2/R5 per request; each provider commit is the request that wrote its result, prompt digest included."""
    commits = {route.result(data): data for data in route.commits if data["effect_class"] == "provider"}
    effects = f".orchestrate/runs/{route.authority.run_root.name}/effects/"
    for request in route.requests:
        bundle, site = request["env"][BUNDLE], request["env"][SITE]
        assert bundle.startswith(f"{effects}{site.removeprefix('sha256:')}/attempt-")
        if bundle in commits:
            assert (site, commits[bundle]["input_parts"]["prompt"]) == (
                sha256(commits[bundle]["identity"]), sha256(request["prompt"]))
    linked = [commits[request["env"][BUNDLE]] for request in route.requests if request["env"][BUNDLE] in commits]
    assert linked == list(commits.values())


def lineage(route: Route) -> list[list[int]]:
    """C9: for each commit in journal order, the positions of the commits in its `depends_on`."""
    order = {data["identity"]: index for index, data in enumerate(route.commits)}
    return [sorted(order[identity] for identity in data["depends_on"]) for data in route.commits]


def missing_edges(route: Route, required: list[set[int]]) -> list[list[int]]:
    """Per commit, the `required` C9 edges (results its resolved input reads) that `depends_on` lacks."""
    return [sorted(need - set(have)) for need, have in zip(required, lineage(route), strict=True)]


def flat_outputs(value: dict) -> dict:
    """The old route's workflow outputs for a returned record or variant."""
    return {f"return__{key}": item for key, item in value.items()}


def routes(root: Path, monkeypatch, name: str, plan: dict, inputs: dict, marker: str) -> tuple[Route, Route]:
    """The scenario on the accepted old route and at 2.35, compared value for value and request for request.

    The 2.35 run stops after the `marker` commit, resumes through the CLI and is resumed
    again once completed; each effect starts once.
    """
    install_shims(root / "bin", monkeypatch, plan)
    program = PROGRAMS[name]
    old = old_route(root / "old", install(root / "old", program, inputs, current=False))
    new = current_route(root / "new", install(root / "new", program, inputs, current=True), marker)
    assert (old.value, request_view(old)) == (flat_outputs(new.value), request_view(new))
    assert set(new.started().values()) == {1}
    assert_request_lineage(new)
    return old, new
