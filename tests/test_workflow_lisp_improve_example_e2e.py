"""CF-1b Task 6: `workflows/examples/improve_experiment_proposal.orc` end to end.

Contract: docs/design/workflow_lisp_composition_first.md sections 3, 4, 5 and
10; Review Focus item 4 of docs/plans/2026-09-28-composition-first-master-plan.md.

Every run goes through the public entry (`run_workflow`, `resume_workflow`) in a
tmp workspace holding a copy of the example, its prompt assets and its checked-in
command binding. The agents behind the example's provider hooks are stood in for
by a patched provider executor whose answers are a function of the hook's bound
inputs; the executor is `LAUNCH_PROBE`, supplied as the workspace's
`scripts/launch_experiment.py`. Interruptions happen only at commit boundaries.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.types import PreparedProviderPolicy
from tests.test_workflow_evaluated_cli import _run_args
from tests.workflow_lisp_improve_example_sources import (
    APPROVED_LAUNCH,
    EXHAUSTED_LAUNCH,
    QUESTION,
    SEED,
    EXAMPLE,
    EXAMPLE_INPUTS,
    EXAMPLE_PROMPTS,
    LEGACY_COMMANDS,
    MAINTAINED_EXAMPLE,
    LAUNCH_PROBE,
    PANEL_HOOKS,
    PANEL_REVIEW,
    REPO_ROOT,
    SELECTED_REVIEW,
    panel_source,
)


ENTRY = "improve_experiment_proposal::run-experiment"
PROVIDERS = {
    "providers.proposal.review": "methods",
    "providers.proposal.revise": "reviser",
    "providers.proposal.statistics-review": "statistics",
}


# Agents: each answers from the hook's bound inputs. A proposal's version shows in
# its hypothesis (`+r` per revision) and in the length of its parameter list.


def _approve(tag: str):
    return lambda hook: {"variant": "APPROVE", "evidence": {"notes": f"{tag}:ok:{hook[1]}"}}


def _block(tag: str):
    return lambda hook: {"variant": "BLOCKED", "reason": {"issue": f"{tag}:blocked:{hook[1]}"}}


def _revise(tag: str):
    return lambda hook: {"variant": "REVISE", "feedback": {"notes": f"{tag}:add-{len(hook[2])}"}}


def _first_draft(then):
    """Ask for one revision, then answer with `then`."""

    return lambda hook: (then if "+r" in hook[1] else _revise("methods"))(hook)


def _reviser(hook: dict) -> dict:
    parameters = [*hook[2], {"name": hook[3], "value": len(hook[2])}]
    return {"hypothesis": hook[1] + "+r", "parameters": parameters}


# Workspace and public entry.


def _install(root: Path, source: str) -> dict[str, Path]:
    source_path = root / "improve_experiment_proposal.orc"
    source_path.write_text(source.replace('"2.33"', '"2.35"'), encoding="utf-8")
    shutil.copytree(EXAMPLE_PROMPTS, root / "prompts" / "workflows" / "improve_experiment_proposal")
    (root / "scripts").mkdir()
    (root / "scripts" / "launch_experiment.py").write_text(LAUNCH_PROBE, encoding="utf-8")
    files = {
        "source": source_path,
        "source_root": root,
        "providers": root / "providers.json",
        "prompts": EXAMPLE_INPUTS / "prompts.json",
        "commands": root / "commands.json",
        "inputs": root / "inputs.json",
    }
    commands = json.loads(LEGACY_COMMANDS.read_text())
    for binding in commands.values():
        binding["closure"] = ["scripts/launch_experiment.py"]
    files["commands"].write_text(json.dumps(commands))
    files["providers"].write_text(json.dumps(PROVIDERS), encoding="utf-8")
    files["inputs"].write_text(json.dumps({"question": QUESTION}), encoding="utf-8")
    return files


class _Agents:
    """Patched provider executor: answers and records each hook call."""

    def __init__(self, answers: dict) -> None:
        self.answers = answers
        self.calls: list[tuple] = []

    def prepare_invocation(self, provider_name, *_args, **kwargs):
        policy = PreparedProviderPolicy(
            provider_name=provider_name, model=None, effort=None, timeout_sec=None, input_mode="stdin"
        )
        hook = self.bound_inputs
        prompt = str(kwargs.get("prompt_content", ""))
        invocation = SimpleNamespace(
            provider_name=provider_name, prompt=prompt, prepared_prompt=prompt, prepared_provider_policy=policy,
            env=dict(kwargs.get("env") or {}), input_mode="stdin", hook=hook,
        )
        return invocation, None

    def execute(self, invocation, **_kwargs):
        hook = invocation.hook
        self.calls.append((invocation.provider_name, hook[1], (hook[3] if len(hook) > 3 else None)))
        Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
            json.dumps(self.answers[invocation.provider_name](hook)), encoding="utf-8"
        )
        return SimpleNamespace(
            exit_code=0, stdout=b"", stderr=b"", duration_ms=1, error=None, missing_placeholders=None,
            invalid_prompt_placeholder=False, raw_stdout=None, normalized_stdout=None, provider_session=None,
        )

    def installed(self, stack: ExitStack) -> None:
        from orchestrator.workflow.evaluated import effect_inputs
        resolve = effect_inputs.resolve_provider_input
        def observe_native_inputs(node, operands, **kwargs):
            self.bound_inputs = tuple(value.json_value() for value in operands[:len(node["inputs"])])
            return resolve(node, operands, **kwargs)
        stack.enter_context(patch.object(effect_inputs, "resolve_provider_input", observe_native_inputs))
        stack.enter_context(patch.object(ProviderExecutor, "prepare_invocation", self.prepare_invocation))
        stack.enter_context(patch.object(ProviderExecutor, "execute", self.execute))


def _run(files: dict[str, Path], agents: _Agents, *interruptions):
    args = _run_args(files, input_file=files["inputs"])
    args.entry_workflow = ENTRY
    args.command_boundaries_file = str(files["commands"])
    argv = [
        "orchestrator", "run", str(files["source"]), "--source-root", str(files["source_root"]),
        "--entry-workflow", ENTRY, "--provider-externs-file", str(files["providers"]),
        "--prompt-externs-file", str(files["prompts"]), "--command-boundaries-file", str(files["commands"]),
        "--input-file", str(files["inputs"]),
    ]
    with ExitStack() as stack:
        agents.installed(stack)
        stack.enter_context(patch.object(sys, "argv", argv))
        for interruption in interruptions:
            stack.enter_context(interruption)
        return run_workflow(args)


def _resume(root: Path, agents: _Agents) -> dict:
    run_id = next((root / ".orchestrate" / "runs").iterdir()).name
    with ExitStack() as stack:
        agents.installed(stack)
        assert resume_workflow(run_id=run_id, retry_delay_ms=0) == 0
    from tests.workflow_evaluated_totality_helpers import checked_run
    return checked_run(root)[1]


def _launched(root: Path) -> list[dict]:
    log = root / "scripts" / "launch_experiment.log"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []






# Expected hook operations and executor inputs per scenario.

APPROVED_CALLS = [("methods", "warmup", None), ("reviser", "warmup", "methods:add-1"), ("methods", "warmup+r", None)]
EXHAUSTED_CALLS = [
    ("methods", "warmup", None), ("reviser", "warmup", "methods:add-1"),
    ("methods", "warmup+r", None), ("reviser", "warmup+r", "methods:add-2"),
    ("methods", "warmup+r+r", None), ("reviser", "warmup+r+r", "methods:add-3"),
]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_documented_command_dry_runs_the_example(tmp_path: Path) -> None:
    header = MAINTAINED_EXAMPLE.read_text(encoding="utf-8").split("python -m orchestrator run", 1)[1].split("--dry-run", 1)[0]
    documented = "python -m orchestrator run " + " ".join(line.strip(" ;\\") for line in header.splitlines()) + " --dry-run"
    argv = shlex.split(documented)

    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, *argv[1:]], cwd=REPO_ROOT, env=env,
                            capture_output=True, text=True, check=False)

    assert (argv[:4], result.returncode) == (["python", "-m", "orchestrator", "run"], 0), result.stderr


@pytest.mark.parametrize(
    ("reviewer", "calls", "launched", "status"),
    [
        (_first_draft(_approve("methods")), APPROVED_CALLS, APPROVED_LAUNCH, "launched"),
        (
            _first_draft(_block("methods")),
            APPROVED_CALLS,
            {**APPROVED_LAUNCH, "outcome": "blocked", "note": "methods:blocked:warmup+r"},
            "held",
        ),
        (_revise("methods"), EXHAUSTED_CALLS, EXHAUSTED_LAUNCH, "held"),
    ],
    ids=["approved", "blocked", "exhausted-after-final-continue"],
)
def test_executor_consumes_the_returned_proposal(workspace: Path, reviewer, calls, launched, status) -> None:
    files = _install(workspace, EXAMPLE.read_text(encoding="utf-8"))
    agents = _Agents({"methods": reviewer, "reviser": _reviser})

    result = _run(files, agents)

    assert (result.exit_code, dict(result.workflow_outputs), agents.calls, _launched(workspace)) == (
        0, {"status": status}, calls, [launched],
    )




def test_resume_after_the_final_continue_projects_the_latest_proposal(workspace: Path) -> None:
    files = _install(workspace, EXAMPLE.read_text(encoding="utf-8"))
    agents = _Agents({"methods": _revise("methods"), "reviser": _reviser})
    from orchestrator.workflow.evaluated import runtime
    class AfterLastProvider(BaseException):
        pass
    append = runtime.append_record
    providers = []
    def interrupt_after_last_provider(path, record, **kwargs):
        result = append(path, record, **kwargs)
        if record["record"] == "committed" and record["effect_class"] == "provider":
            providers.append(record)
            if len(providers) == len(EXHAUSTED_CALLS):
                raise AfterLastProvider
        return result
    with patch.object(runtime, "append_record", interrupt_after_last_provider):
        with pytest.raises(AfterLastProvider):
            _run(files, agents)
    assert (agents.calls, _launched(workspace)) == (EXHAUSTED_CALLS, [])

    state = _resume(workspace, agents)

    assert (state.terminal.data["outcome"], state.terminal.data["value"], agents.calls, _launched(workspace)) == (
        "completed", {"status": "held"}, EXHAUSTED_CALLS, [EXHAUSTED_LAUNCH],
    )


def test_panel_reviewer_substitution_changes_only_the_selected_hook(workspace: Path) -> None:
    example = EXAMPLE.read_text(encoding="utf-8")
    panel = panel_source(example)
    files = _install(workspace, panel)
    agents = _Agents({"methods": _first_draft(_approve("methods")), "statistics": _approve("stats"), "reviser": _reviser})

    result = _run(files, agents)

    assert panel.replace(PANEL_HOOKS, "").replace(PANEL_REVIEW, SELECTED_REVIEW) == example
    assert (result.exit_code, agents.calls, _launched(workspace)) == (
        0,
        [
            ("methods", "warmup", None), ("statistics", "warmup", None), ("reviser", "warmup", "methods:add-1"),
            ("methods", "warmup+r", None), ("statistics", "warmup+r", None),
        ],
        [{**APPROVED_LAUNCH, "note": "stats:ok:warmup+r"}],
    )


@pytest.mark.parametrize(
    ("methods", "statistics", "blocker"),
    [
        (_block("methods"), _approve("stats"), "methods:blocked:warmup"),
        (_revise("methods"), _block("stats"), "stats:blocked:warmup"),
        (_approve("methods"), _block("stats"), "stats:blocked:warmup"),
    ],
    ids=["methods-blocks-statistics-approves", "statistics-blocks-methods-revises", "statistics-blocks-methods-approves"],
)
def test_panel_returns_an_inner_block_never_a_downgraded_verdict(workspace: Path, methods, statistics, blocker) -> None:
    files = _install(workspace, panel_source(EXAMPLE.read_text(encoding="utf-8")))
    agents = _Agents({"methods": methods, "statistics": statistics, "reviser": _reviser})

    result = _run(files, agents)

    assert (result.exit_code, agents.calls, _launched(workspace)) == (
        0,
        [("methods", "warmup", None), ("statistics", "warmup", None)],
        [{"outcome": "blocked", "note": blocker, "hypothesis": "warmup", "parameters": [SEED]}],
    )
