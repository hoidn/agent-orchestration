"""Spike of evaluated execution, iteration 2, items E and G: SIGKILL from outside, and the decisive experiment.

Throwaway. The evaluator runs in a child process (this file, run as a script). The
child reads the closed program from its artifact and answers provider calls with a
stand-in whose answer is a function of the request, so that a new process answers as
the old one did. At a chosen moment of a chosen effect the child writes a marker and
waits; the test kills its whole process group with SIGKILL and resumes in a new child.

Windows of the design's section 8, at the k-th effect:
- `resolved`: before `started` is written (the evaluator's hook blocks);
- `during`: while the effect runs (the command or the provider blocks on a hold file);
- `finished`: the result file is complete, `committed` not written (the hook blocks);
- `committed`: after `committed` (the hook blocks).

The program is the `std/improve` example, unchanged: providers review and revise a
proposal, and a command launches it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WINDOWS = ("resolved", "during", "finished", "committed")
POLICIES = ("approve", "revise-twice", "blocked", "exhausted")

LAUNCHER = """import json, os, sys, time
from pathlib import Path
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
if Path("hold").exists():
    Path("marker").write_text("during", encoding="utf-8")
    while True:
        time.sleep(0.05)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"status": "launched"}), encoding="utf-8")
"""


def answer(policy: str, prompt: str) -> dict:
    """A reviewer and a reviser whose answers depend only on the proposal in the prompt."""

    hypothesis = re.search(r'## Typed Prompt Input: hypothesis\n"(.*)"', prompt).group(1)
    revisions = hypothesis.count("+r")
    if prompt.startswith("Revise"):
        return {"hypothesis": hypothesis + "+r", "parameters": [{"name": "seed", "value": revisions + 1}]}
    decision = {"approve": "APPROVE", "blocked": "BLOCKED", "exhausted": "REVISE",
                "revise-twice": "APPROVE" if revisions >= 2 else "REVISE"}[policy]
    field = {"APPROVE": ("evidence", {"notes": "ready"}), "REVISE": ("feedback", {"notes": f"again {revisions}"}),
             "BLOCKED": ("reason", {"issue": "no budget"})}[decision]
    return {"variant": decision, field[0]: field[1]}


class FunctionalProviders:
    """Stand-in provider executor for the child: logs each call, blocks on the hold file, answers by `answer`."""

    def __init__(self, policy: str, workspace: Path) -> None:
        self.policy, self.workspace = policy, workspace

    def prepare_invocation(self, provider_name, *args, **kwargs):
        from tests.test_workflow_lisp_generic_union_provider_results import _Provider

        return _Provider({}).prepare_invocation(provider_name, *args, **kwargs)

    def execute(self, invocation, **kwargs):
        from tests.test_workflow_lisp_generic_union_provider_results import _Provider

        with open(self.workspace / "providers.log", "a", encoding="utf-8") as log:
            log.write(invocation.prompt.split("\n", 1)[0] + "\n")
        if (self.workspace / "hold").exists():
            (self.workspace / "marker").write_text("during", encoding="utf-8")
            while True:
                time.sleep(0.05)
        return _Provider(answer(self.policy, invocation.prompt)).execute(invocation)


def child(config_path: str) -> None:
    """Run or resume the program in the workspace the configuration names; stop at its window."""

    from experiments.evaluated_execution_spike.evaluator import EvaluationFailed, evaluate
    from experiments.evaluated_execution_spike.sites import ClosedProgram
    from orchestrator.providers.executor import ProviderExecutor

    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    workspace = Path(config["workspace"])
    providers = FunctionalProviders(config["policy"], workspace)
    ProviderExecutor.prepare_invocation = providers.prepare_invocation
    ProviderExecutor.execute = providers.execute
    closed = ClosedProgram.from_artifact(Path(config["program"]).read_text(encoding="utf-8"))
    seen: Counter[str] = Counter()

    def hook(event: str, identity: str) -> None:
        seen[event] += 1
        if seen[event] != config.get("at"):
            return
        if config.get("window") == "during" and event == "started":
            (workspace / "hold").write_text("", encoding="utf-8")
        elif config.get("window") == event:
            (workspace / "marker").write_text(event, encoding="utf-8")
            while True:
                time.sleep(0.05)

    os.chdir(workspace)
    try:
        result = evaluate(closed, inputs=config["inputs"], workspace=workspace, run_root=workspace / "run", hook=hook)
        print(json.dumps({"value": result.value}))
    except EvaluationFailed as failed:
        print(json.dumps({"refused": failed.code, "detail": failed.detail, "at": failed.at}))


# The parent side ------------------------------------------------------------------------


def _spawn(config: dict, root: Path) -> subprocess.Popen:
    path = root / f"config-{time.monotonic_ns()}.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.Popen([sys.executable, __file__, "child", str(path)], cwd=REPO, env=env, start_new_session=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def run_child(config: dict, root: Path) -> dict:
    out, err = _spawn(config, root).communicate(timeout=120)
    lines = out.strip().splitlines()
    assert lines, err[-2000:]
    return json.loads(lines[-1])


def kill_child(config: dict, root: Path) -> None:
    """Start the child, wait until it stands at its window, and kill its process group."""

    process = _spawn(config, root)
    marker = Path(config["workspace"]) / "marker"
    deadline = time.monotonic() + 60
    while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert marker.exists(), process.communicate()[1][-2000:]
    os.killpg(process.pid, signal.SIGKILL)
    process.communicate()
    marker.unlink()
    (Path(config["workspace"]) / "hold").unlink(missing_ok=True)


def prepare(tmp_path: Path) -> Path:
    """The example's closed program, built once, and a template workspace."""

    from orchestrator.workflow_lisp.build_manifest_io import _parse_command_boundaries_manifest
    from tests.experiments.test_evaluated_execution_spike import build
    from tests.experiments.test_evaluated_execution_spike_programs import REAL, _install_real

    template = tmp_path / "template"
    entry, providers, prompts, commands = _install_real(template, "improve-example")
    closed = build(template, {entry.name: entry.read_text(encoding="utf-8")},
                   workflow=f"improve_experiment_proposal::{REAL['improve-example'][1]}",
                   boundaries=_parse_command_boundaries_manifest(commands, manifest_path=None),
                   providers=providers, prompts=prompts)
    (template / "scripts" / "launch_experiment.py").write_text(LAUNCHER, encoding="utf-8")
    (tmp_path / "program.json").write_text(closed.artifact(), encoding="utf-8")
    return template


def workspace(tmp_path: Path, template: Path, name: str, policy: str) -> dict:
    root = tmp_path / name
    shutil.copytree(template, root)
    return {"workspace": str(root), "program": str(tmp_path / "program.json"), "policy": policy,
            "inputs": {"question": "Does warmup help?"}}


def observation(config: dict) -> tuple:
    """What a run did: its result, and every provider and command launch, in order."""

    root = Path(config["workspace"])
    read = lambda path: path.read_text(encoding="utf-8").splitlines() if path.exists() else []  # noqa: E731
    return read(root / "providers.log"), read(root / "scripts" / "launch_experiment.log")


def records(config: dict, kind: str) -> list[dict]:
    from experiments.evaluated_execution_spike.memo import read_records

    return [r for r in read_records(Path(config["workspace"]) / "run") if r["record"] == kind]


# What a kill at each window leaves for the stopped effect: launched before the kill, attempts after resume.
EXPECTED = {"resolved": (0, [1]), "during": (1, [1, 2]), "finished": (1, [1, 2]), "committed": (1, [1])}


def kill_and_resume_at(tmp_path: Path, template: Path, policy: str, k: int, window: str, once: dict) -> None:
    config = workspace(tmp_path, template, f"{policy}-{k}-{window}", policy)
    kill_child({**config, "window": window, "at": k}, tmp_path)
    launched_before = sum(map(len, observation(config)))
    resumed = run_child(config, tmp_path)
    identity = once["committed"][k - 1]
    launched, attempts = EXPECTED[window]

    where = f"{policy}, effect {k}, window {window}"
    assert resumed == {"value": once["value"]}, where
    assert launched_before == k - 1 + launched, where
    assert sum(map(len, observation(config))) == once["launches"] + (1 if attempts == [1, 2] else 0), where
    assert [r["identity"] for r in records(config, "committed")] == once["committed"], where
    assert [r["attempt"] for r in records(config, "started") if r["identity"] == identity] == attempts, where


def uninterrupted(tmp_path: Path, template: Path, policy: str) -> dict:
    config = workspace(tmp_path, template, f"{policy}-once", policy)
    result = run_child(config, tmp_path)
    return {"config": config, "value": result["value"], "launches": sum(map(len, observation(config))),
            "committed": [r["identity"] for r in records(config, "committed")]}


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize("effect", ["provider", "command"])
def test_a_sigkill_in_each_window_of_a_provider_and_of_a_command_resumes_to_the_uninterrupted_result(
    tmp_path: Path, effect: str, window: str
) -> None:
    """Policy `approve`: effect 1 reviews (a provider), effect 2 launches (a command)."""

    template = prepare(tmp_path)
    once = uninterrupted(tmp_path, template, "approve")
    assert once["launches"] == 2

    kill_and_resume_at(tmp_path, template, "approve", 1 if effect == "provider" else 2, window, once)


def test_decisive_experiment_reviewer_both_routes_every_memo_window_then_a_changed_command_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The review's decisive experiment, on the `std/improve` example.

    For each policy of the stand-in reviewer (approve at once, revise twice then approve,
    blocked, exhausted): (1) both routes give the same value, and every effect receives
    the same complete request apart from the listed design differences; (2) the spike's
    run, killed by SIGKILL at each memo window of each effect and resumed, gives the
    uninterrupted result with no committed effect launched twice; (3) after the launcher,
    a declared command file, changes, a resume is refused before any effect is launched.
    """

    from tests.experiments.test_evaluated_execution_spike_requests import (
        DESIGN_DIFFERENCES,
        differing_fields,
        normalized,
        requests_on_both_routes,
    )

    template = prepare(tmp_path)
    for policy in POLICIES:
        routes = requests_on_both_routes(tmp_path / f"routes-{policy}", "improve-example", monkeypatch,
                                         respond=lambda invocation, policy=policy: answer(policy, invocation.prompt))
        (flat_value, flat), (spike_value, spiked) = routes["flat"], routes["spike"]
        assert spike_value == flat_value, policy
        assert [normalized(r) for r in spiked] == [normalized(r) for r in flat], policy
        assert differing_fields(flat, spiked) <= set(DESIGN_DIFFERENCES), policy

        once = uninterrupted(tmp_path, template, policy)
        assert len(once["committed"]) == len(spiked), policy
        for k in range(1, len(once["committed"]) + 1):
            for window in WINDOWS:
                kill_and_resume_at(tmp_path, template, policy, k, window, once)

        config = once["config"]
        before = observation(config)
        launcher = Path(config["workspace"]) / "scripts" / "launch_experiment.py"
        launcher.write_text(launcher.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
        refused = run_child(config, tmp_path)
        assert (refused["refused"], refused["detail"]["files"]) == ("effect_input_diverged", ["scripts/launch_experiment.py"]), policy
        assert observation(config) == before, policy


if __name__ == "__main__" and sys.argv[1:2] == ["child"]:
    child(sys.argv[2])
