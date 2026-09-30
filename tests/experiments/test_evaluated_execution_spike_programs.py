"""Spike of evaluated execution: real programs, unchanged in source.

Throwaway (Task 9 of docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md).

- The compact search controller of the paired search (criterion 2 of Task 10): its
  decisions, budget and result against the Python reference.
- The `std/improve` example and the two workflows of the single-call comparison, with
  stand-in providers and a stand-in launcher, against the flat route. The spike does not
  assemble prompts as the flat route does; only values, provider order and commands are
  compared.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.mlevolve_pair.search import run_search
from orchestrator.cli.commands.run import run_workflow
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.workflow_lisp.build_manifest_io import _parse_command_boundaries_manifest
from tests.experiments.test_evaluated_execution_spike import in_cwd, outputs, records, spike
from tests.test_workflow_lisp_generic_union_provider_results import _Provider
from tests.test_workflow_lisp_generic_unions_runtime import _log
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args, _run_argv

REPO = Path(__file__).resolve().parents[2]
CONTROLLER = "mlevolve_pair/search_compact"


# The compact search controller (criterion 2) ----------------------------------


def compact_controller(root: Path) -> tuple[dict[str, str], dict]:
    """The controller's source, unchanged, and its command boundaries; its leaves copied under `root`.

    Read from this checkout, or else from branch `phase0/t7`, where Task 7 adds it.
    """

    texts = []
    for name in ("experiments/mlevolve_pair/search_compact.orc", "experiments/mlevolve_pair/commands_compact.json"):
        if (REPO / name).exists():
            texts.append((REPO / name).read_text(encoding="utf-8"))
            continue
        shown = subprocess.run(["git", "show", f"phase0/t7:{name}"], cwd=REPO, capture_output=True, text=True)
        if shown.returncode != 0:
            pytest.skip(f"{name} is neither in this checkout nor on branch phase0/t7")
        texts.append(shown.stdout)
    leaves = root / "experiments" / "mlevolve_pair"
    leaves.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / "experiments" / "mlevolve_pair" / "leaves.py", leaves / "leaves.py")
    boundaries = _parse_command_boundaries_manifest(json.loads(texts[1]), manifest_path=None)
    return {f"{CONTROLLER}.orc": texts[0]}, boundaries


def run_controller(root: Path, budget: int, **options):
    sources, boundaries = compact_controller(root)
    return spike(root, sources, inputs={"max_evaluations": budget, "target_score": 0.0},
                 boundaries=boundaries, workflow=f"{CONTROLLER}::run-search", **options)


@pytest.mark.parametrize("budget", [2, 3, 4, 7, 12])
def test_the_compact_search_controller_makes_the_decisions_of_the_python_reference(tmp_path: Path, budget: int) -> None:
    """Same decisions in order, same budget spent, same result: the whole result, trace included."""

    _, result = run_controller(tmp_path, budget)

    assert result.value == run_search(max_evaluations=budget)
    assert len(records(tmp_path)) == 2 * result.value["evaluations"] - 2


# Real programs against the flat route -----------------------------------------


class ScriptedProviders:
    """Stand-in provider executor: each provider id answers its payloads in turn; a `report` field is written."""

    def __init__(self, payloads: dict[str, list[dict]], respond=None) -> None:
        self.payloads = {name: list(queue) for name, queue in payloads.items()}
        self.respond = respond  # or else an answer computed from the invocation
        self.calls: list[str] = []

    def prepare_invocation(self, provider_name, *args, **kwargs):
        return _Provider({}).prepare_invocation(provider_name, *args, **kwargs)

    def execute(self, invocation, **kwargs):
        payload = self.respond(invocation) if self.respond else self.payloads[invocation.provider_name].pop(0)
        self.calls.append(invocation.provider_name)
        if "report" in payload:
            report = Path(kwargs.get("cwd") or Path.cwd()) / payload["report"]
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("report\n", encoding="utf-8")
        return in_cwd(_Provider(payload).execute)(invocation, **kwargs)


LAUNCHER = """import json, os, sys
from pathlib import Path
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"status": "launched"}), encoding="utf-8")
"""

REPORT = "artifacts/review/report.md"
REAL = {
    "improve-example": (
        "workflows/examples/improve_experiment_proposal.orc", "run-experiment", "workflows/examples/inputs/improve_experiment_proposal",
        {"question": "Does warmup help?"},
        {"codex": [
            {"variant": "REVISE", "feedback": {"notes": "name a seed"}},
            {"hypothesis": "warmup helps", "parameters": [{"name": "seed", "value": 1}]},
            {"variant": "APPROVE", "evidence": {"notes": "ready"}},
        ]},
    ),
    "reviewed-change": (
        "experiments/orc_vs_single_call/workflows/reviewed_change.orc", "reviewed-change", None,
        {"task": "fix it", "intent": "no crash", "repo": "repo"},
        {"claude_unrestricted_workspace": [{"summary": "s1", "account": "a1"},
                                           {"summary": "s2", "account": "a2", "replies": "done"}],
         "codex_unrestricted_workspace": [
             {"variant": "REQUEST_CHANGES", "report": REPORT, "summary": "missing test", "findings": ["add a test"]},
             {"variant": "APPROVE", "report": REPORT, "notes": ["fine"]}]},
    ),
    "best-of-n": (
        "experiments/orc_vs_single_call/workflows/best_of_n.orc", "best-of-n", None,
        {"task": "fix it", "intent": "no crash", "repos": ["r1", "r2"]},
        {"claude_unrestricted_workspace": [{"summary": "s1", "account": "a1"}, {"summary": "s2", "account": "a2"}],
         "codex_unrestricted_workspace": [{"winner": "r2", "ranking": ["r2: 2 2 2 2", "r1: 1 1 1 1"], "report": REPORT}]},
    ),
}


def _install_real(root: Path, name: str) -> tuple[Path, dict, dict, dict]:
    source, _, inputs_dir, _, _ = REAL[name]
    entry = root / Path(source).name
    root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / source, entry)
    if inputs_dir is None:
        providers = json.loads((REPO / source.replace(".orc", ".providers.json")).read_text(encoding="utf-8"))
        return entry, providers, {}, {}
    shutil.copytree(REPO / "workflows" / "examples" / "prompts", root / "prompts", dirs_exist_ok=True)
    (root / "scripts").mkdir(exist_ok=True)
    (root / "scripts" / "launch_experiment.py").write_text(LAUNCHER, encoding="utf-8")
    load = lambda file: json.loads((REPO / inputs_dir / file).read_text(encoding="utf-8"))  # noqa: E731
    return entry, load("providers.json"), load("prompts.json"), load("commands.json")


def _flat_real(root: Path, name: str, monkeypatch: pytest.MonkeyPatch):
    entry, providers, prompts, commands = _install_real(root, name)
    files = {"source": entry, "source_root": root, "providers": root / "providers.json",
             "prompts": root / "prompts.json", "commands": root / "commands.json"}
    for key, payload in (("providers", providers), ("prompts", prompts), ("commands", commands)):
        files[key].write_text(json.dumps(payload), encoding="utf-8")
    (root / "inputs.json").write_text(json.dumps(REAL[name][3]), encoding="utf-8")
    args = _run_args(files, input_file=root / "inputs.json")
    args.entry_workflow, args.command_boundaries_file = REAL[name][1], str(files["commands"])
    argv = [*_run_argv(files), "--command-boundaries-file", str(files["commands"])]
    argv[argv.index("--entry-workflow") + 1] = REAL[name][1]
    monkeypatch.chdir(root)
    with patch.object(sys, "argv", argv):
        result = run_workflow(args)
    assert result.exit_code == 0, f"the flat route failed on {name}"
    return dict(result.workflow_outputs)


def _spike_real(root: Path, name: str, monkeypatch: pytest.MonkeyPatch, **options):
    entry, providers, prompts, commands = _install_real(root, name)
    monkeypatch.chdir(root)
    module = entry.read_text(encoding="utf-8").split("(defmodule ", 1)[1].split(")", 1)[0]
    closed, result = spike(root, {entry.name: entry.read_text(encoding="utf-8")}, inputs=REAL[name][3],
                           workflow=f"{module}::{REAL[name][1]}",
                           boundaries=_parse_command_boundaries_manifest(commands, manifest_path=None),
                           providers=providers, prompts=prompts, **options)
    return outputs(result.value)


def scripted_providers(monkeypatch: pytest.MonkeyPatch, name: str) -> ScriptedProviders:
    scripted = ScriptedProviders(REAL[name][4])
    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", scripted.prepare_invocation)
    monkeypatch.setattr(ProviderExecutor, "execute", scripted.execute)
    return scripted


def launches(root: Path) -> list[list[str]]:
    return [json.loads(line) for line in _log(root / "scripts" / "launch_experiment.py")]


def _observe(tmp_path: Path, name: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, tuple]:
    """Per route: the final value, the ordered provider calls, and the launcher's argv, as raw text."""

    observed = {}
    for route, run in (("flat", _flat_real), ("spike", _spike_real)):
        scripted = scripted_providers(monkeypatch, name)
        value = json.loads(json.dumps(run(tmp_path / route, name, monkeypatch)))  # the flat route's lists are tuples
        observed[route] = (value, scripted.calls, launches(tmp_path / route))
    return observed


def _parsed(argv_lines: list[list[str]]) -> list[list[object]]:
    def parse(argument: str) -> object:
        return json.loads(argument) if argument[:1] in ("[", "{") else argument

    return [[parse(argument) for argument in argv] for argv in argv_lines]


@pytest.mark.parametrize("name", list(REAL))
def test_a_real_program_agrees_with_the_flat_route_on_value_providers_and_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    observed = _observe(tmp_path, name, monkeypatch)

    flat, spiked = observed["flat"], observed["spike"]
    assert (spiked[0], spiked[1], _parsed(spiked[2])) == (flat[0], flat[1], _parsed(flat[2]))


def test_a_list_in_argv_is_sent_as_the_flat_route_sends_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Item F's rule for a structured argument: rendered as the flat route's substitution renders it."""

    observed = _observe(tmp_path, "improve-example", monkeypatch)

    assert (observed["flat"][2][0][-1], observed["spike"][2][0][-1]) == ('[{"name": "seed", "value": 1}]',) * 2
