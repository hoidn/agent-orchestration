from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from orchestrator.demo.evaluators.nanobragg_entrypoint import (
    evaluate_workspace as evaluate_nanobragg_workspace,
)
from orchestrator.experiments import canonical_sha256
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.build import (
    load_frontend_initialization_configuration,
)
from orchestrator.workflow_lisp.command_boundaries import (
    build_command_boundary_environment,
)


ROOT = Path(__file__).resolve().parents[2]
COORDINATOR_SCRIPT = ROOT / "scripts" / "experiments" / "conventional_coordinator.py"
ORC_WORKFLOW = (
    ROOT / "workflows" / "experiments" / "repository_task_pilot" / "task_loop.orc"
)
PROMPT_ROOT = ORC_WORKFLOW.parent / "prompts"
SCRIPTED_PROVIDER = (
    ROOT
    / "tests"
    / "experiments"
    / "fixtures"
    / "lean_pilot"
    / "scripted_provider.py"
)
CONTROL_ROOT = ROOT / "experiments" / "orc_effectiveness" / "lean_pilot" / "control"
TREATMENT_ROOT = (
    ROOT / "experiments" / "orc_effectiveness" / "lean_pilot" / "treatments"
)
A1_SEED_ROOT = ROOT / "examples" / "demo_task_nanobragg_entrypoint_port"
ENVIRONMENT_IDENTITY = (
    "sha256:0fc13d7943c27b0ae00b12ae41cdac413090b4c3f4a15e47914a322319e8c0af"
)
PROSPECTIVE_PROVIDER_POLICY = {
    "family": "codex-cli",
    "model": "gpt-5.5",
    "reasoning_effort": "high",
    "tool_policy": "codex_unrestricted_workspace",
    "timeout_milliseconds": 1_800_000,
    "currency": "USD",
}
EXPECTED_PROVIDER_POLICY_DIGEST = (
    "sha256:f6894af0098ad618ceaf74d6e46a76ab0519549d15f31f8b8685e40862bd0b25"
)
LAUNCHER_ENVIRONMENT = {
    "PATH": (
        "/home/ollie/.nvm/versions/node/v20.19.4/bin:"
        "/home/ollie/miniconda3/bin:/usr/local/bin:/usr/bin:/bin"
    ),
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONPATH": "{treatment_runtime_root}",
    "PYTHONUNBUFFERED": "1",
}
PHASES = (
    "discover",
    "plan",
    "review_plan",
    "revise_plan",
    "implement",
    "review_implementation",
    "fix_implementation",
)


def _without_transport_correlation_ids(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"correlation_id", "request_id", "transport_request_id"}:
                continue
            if key == "typed_result_schema" and isinstance(item, str):
                normalized[key] = "\n".join(
                    (
                        "- path: <runtime-output-bundle>"
                        if line.startswith("- path: ")
                        else line
                    )
                    for line in item.splitlines()
                )
                continue
            normalized[key] = _without_transport_correlation_ids(item)
        return normalized
    if isinstance(value, list):
        return [_without_transport_correlation_ids(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_without_transport_correlation_ids(item) for item in value)
    return value


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    return value


def test_frozen_launch_configs_use_standard_manifests_and_staged_assets(
    tmp_path: Path,
) -> None:
    provider_policy_digest = canonical_sha256(PROSPECTIVE_PROVIDER_POLICY)
    assert provider_policy_digest == EXPECTED_PROVIDER_POLICY_DIGEST

    configuration = load_frontend_initialization_configuration(
        workspace_root=ROOT,
        source_roots=(ORC_WORKFLOW.parent,),
        provider_externs_path=CONTROL_ROOT / "providers.json",
        prompt_externs_path=CONTROL_ROOT / "prompts.json",
        command_boundaries_path=CONTROL_ROOT / "commands.json",
    )
    build_command_boundary_environment(configuration.command_boundaries)

    provider_keys = {
        f"providers.repository-task.{phase.replace('_', '-')}"
        for phase in PHASES
    }
    assert set(configuration.provider_externs) == provider_keys
    assert set(configuration.provider_externs.values()) == {
        "codex_unrestricted_workspace"
    }
    assert configuration.prompt_externs == {
        f"prompts.repository-task.{phase.replace('_', '-')}": {
            "asset_file": f"prompts/{phase}.md"
        }
        for phase in PHASES
    }
    assert set(configuration.command_boundaries) == {
        "pilot_product_manifest",
        "pilot_visible_check",
    }
    assert all(
        binding.stable_command == ("python",)
        for binding in configuration.command_boundaries.values()
    )

    forbidden_treatment_token = re.compile(
        r"(?<![A-Za-z0-9])(direct|coordinator|orc)(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    for treatment in ("direct", "coordinator", "orc"):
        config = json.loads(
            (TREATMENT_ROOT / f"{treatment}.json").read_text(encoding="utf-8")
        )
        assert set(config) == {
            "argv",
            "environment",
            "environment_identity",
            "provider_policy_digest",
            "timeout_milliseconds",
        }
        assert config["environment"] == LAUNCHER_ENVIRONMENT
        assert "CODEX_HOME" not in config["environment"]
        assert config["environment_identity"] == ENVIRONMENT_IDENTITY
        assert config["provider_policy_digest"] == provider_policy_digest
        assert config["timeout_milliseconds"] == 18_000_000
        maximum_calls = 1 if treatment == "direct" else 9
        maximum_visible_checks = 0 if treatment == "direct" else 2
        assert config["timeout_milliseconds"] > (
            maximum_calls * 1_800_000
            + maximum_visible_checks * 300_000
        )
        argv = config["argv"]
        assert argv[:4] == [
            "python",
            "-B",
            "-P",
            "{apparatus_root}/treatment_driver.py",
        ]
        assert "-I" not in argv
        assert {
            "{workspace}",
            "{task_path}",
            "{result_path}",
            "{provider_config}",
            "{prompt_config}",
            "{command_config}",
            "{apparatus_root}",
        } <= set(argv)
        assert not any(forbidden_treatment_token.search(token) for token in argv)

    staged_root = tmp_path / "apparatus"
    staged_root.mkdir()
    shutil.copy2(ORC_WORKFLOW, staged_root / "task_loop.orc")
    shutil.copy2(COORDINATOR_SCRIPT, staged_root / "treatment_driver.py")
    shutil.copytree(PROMPT_ROOT, staged_root / "prompts")
    shutil.copy2(CONTROL_ROOT / "providers.json", staged_root / "providers.json")
    shutil.copy2(CONTROL_ROOT / "prompts.json", staged_root / "prompts.json")
    shutil.copy2(CONTROL_ROOT / "commands.json", staged_root / "commands.json")
    assert (
        staged_root.joinpath("treatment_driver.py").read_bytes()
        == COORDINATOR_SCRIPT.read_bytes()
    )

    staged_configuration = load_frontend_initialization_configuration(
        workspace_root=tmp_path,
        source_roots=(staged_root,),
        provider_externs_path=staged_root / "providers.json",
        prompt_externs_path=staged_root / "prompts.json",
        command_boundaries_path=staged_root / "commands.json",
    )
    compiled = compile_stage3_entrypoint(
        staged_root / "task_loop.orc",
        source_roots=(staged_root,),
        provider_externs=staged_configuration.provider_externs,
        prompt_externs=staged_configuration.prompt_externs,
        command_boundaries=staged_configuration.command_boundaries,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    assert any(
        name.endswith("::run-task") or name == "run-task"
        for name in compiled.entry_result.typed_program.workflows
    )


def test_workflow_treatment_uses_locked_runtime_python_invocation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )
    workspace = tmp_path / "candidate"
    workspace.mkdir()
    apparatus_root = tmp_path / "apparatus"
    apparatus_root.mkdir()
    (apparatus_root / "task_loop.orc").write_text(
        "(workflow-lisp)\n",
        encoding="utf-8",
    )
    task_path = workspace / "task.md"
    task_path.write_text("fixture\n", encoding="utf-8")
    control_path = workspace / "control.json"
    control_path.write_text("{}\n", encoding="utf-8")
    command_seen: list[str] = []

    def run_nested(command: Sequence[str], **_kwargs: object) -> object:
        command_seen.extend(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(coordinator.subprocess, "run", run_nested)
    monkeypatch.setattr(
        coordinator,
        "_workflow_treatment_result",
        lambda _state_root: (5, "COMPLETED"),
    )

    assert coordinator._run_workflow_treatment(
        workspace=workspace,
        apparatus_root=apparatus_root,
        task_path=task_path,
        control_path=control_path,
        provider_config=apparatus_root / "providers.json",
        prompt_config=apparatus_root / "prompts.json",
        command_config=apparatus_root / "commands.json",
        controller_script=apparatus_root / "treatment_driver.py",
        model="gpt-5.5",
        effort="high",
        provider_timeout_seconds=1_800,
    ) == (5, "COMPLETED")

    assert command_seen[:5] == [
        Path(sys.executable).resolve().as_posix(),
        "-B",
        "-P",
        "-m",
        "orchestrator",
    ]
    assert "-I" not in command_seen


@pytest.mark.parametrize(
    ("field_names", "product_exists", "expected_phase"),
    (
        (("relevant_paths", "constraints", "risks"), False, "discover"),
        (("steps", "acceptance_checks"), False, "plan"),
        (
            ("decision", "rationale", "findings", "reason"),
            False,
            "review_plan",
        ),
        (
            ("summary", "changed_paths", "checks_summary"),
            False,
            "implement",
        ),
        (
            ("decision", "rationale", "findings", "reason"),
            True,
            "review_implementation",
        ),
    ),
)
def test_test_provider_routes_by_output_contract_not_prompt_prose(
    tmp_path: Path,
    field_names: tuple[str, ...],
    product_exists: bool,
    expected_phase: str,
) -> None:
    workspace = tmp_path / "candidate"
    workspace.mkdir()
    if product_exists:
        (workspace / "fixture-product.txt").write_text(
            "existing implementation\n",
            encoding="utf-8",
        )
    shim_path = tmp_path / "codex"
    shutil.copy2(SCRIPTED_PROVIDER, shim_path)
    shim_path.chmod(0o755)
    bundle_path = tmp_path / "output.json"
    prompt = "\n".join(
        (
            "This role prose is intentionally unrelated to any phase name.",
            "",
            "## Output Contract",
            *(f"- name: {name}" for name in field_names),
            "",
        )
    )

    completed = subprocess.run(
        [str(shim_path)],
        cwd=workspace,
        env={
            "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(bundle_path),
            "PATH": os.environ["PATH"],
        },
        input=prompt.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert json.loads(completed.stdout) == {"fixture_phase": expected_phase}
    assert bundle_path.is_file()


@pytest.mark.parametrize(
    "terminal_outcome",
    ("COMPLETED", "BLOCKED", "EXHAUSTED", "PROTOCOL_FAILURE"),
)
def test_raw_result_preserves_the_strict_semantic_terminal(
    tmp_path: Path,
    terminal_outcome: str,
) -> None:
    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )
    result_path = tmp_path / "raw-result.json"

    coordinator._write_raw_result(
        result_path,
        provider_call_count=5,
        terminal_outcome=terminal_outcome,
    )

    assert json.loads(result_path.read_text(encoding="utf-8")) == {
        "provider_call_count": 5,
        "terminal_outcome": terminal_outcome,
        "token_counts": "UNKNOWN",
        "cost": "UNKNOWN",
    }


def test_raw_result_rejects_an_uncontrolled_semantic_terminal(
    tmp_path: Path,
) -> None:
    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )

    with pytest.raises(
        coordinator.PilotTreatmentError,
        match="semantic terminal outcome",
    ):
        coordinator._write_raw_result(
            tmp_path / "raw-result.json",
            provider_call_count=5,
            terminal_outcome="UNKNOWN",
        )


@pytest.mark.parametrize(
    "terminal_outcome",
    ("COMPLETED", "BLOCKED", "EXHAUSTED", "PROTOCOL_FAILURE"),
)
def test_workflow_state_parser_preserves_the_exact_semantic_terminal(
    tmp_path: Path,
    terminal_outcome: str,
) -> None:
    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )
    state_root = tmp_path / "state"
    run_root = state_root / "run-1"
    run_root.mkdir(parents=True)
    observation_root = run_root / "provider-observation"
    display_root = observation_root / "display"
    transcript_root = observation_root / "transcripts"
    display_root.mkdir(parents=True)
    transcript_root.mkdir()
    for ordinal in range(1, 6):
        stem = f"{ordinal:06d}-{'a' * 16}"
        (display_root / f"{stem}.display").write_bytes(b"")
        (transcript_root / f"{stem}.transcript").write_bytes(b"fixture\n")
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "workflow_outputs": {
                    "__result__": terminal_outcome,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert coordinator._workflow_treatment_result(state_root) == (
        5,
        terminal_outcome,
    )


@pytest.mark.parametrize(
    "workflow_outputs",
    (
        {},
        {"__result__": "UNKNOWN"},
        {"__result__": "BLOCKED", "variant": "COMPLETED"},
    ),
)
def test_workflow_state_parser_rejects_missing_unknown_or_ambiguous_terminals(
    tmp_path: Path,
    workflow_outputs: Mapping[str, str],
) -> None:
    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )
    state_root = tmp_path / "state"
    run_root = state_root / "run-1"
    run_root.mkdir(parents=True)
    display_root = run_root / "provider-observation" / "display"
    transcript_root = run_root / "provider-observation" / "transcripts"
    display_root.mkdir(parents=True)
    transcript_root.mkdir()
    stem = f"{1:06d}-{'a' * 16}"
    (display_root / f"{stem}.display").write_bytes(b"")
    (transcript_root / f"{stem}.transcript").write_bytes(b"fixture\n")
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "workflow_outputs": dict(workflow_outputs),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        coordinator.PilotTreatmentError,
        match="semantic terminal outcome",
    ):
        coordinator._workflow_treatment_result(state_root)


@pytest.mark.parametrize(
    ("display_stems", "transcript_stems"),
    (
        ((), ()),
        (("000001-aaaaaaaaaaaaaaaa",), ()),
        (
            (
                "000001-aaaaaaaaaaaaaaaa",
                "000003-bbbbbbbbbbbbbbbb",
            ),
            (
                "000001-aaaaaaaaaaaaaaaa",
                "000003-bbbbbbbbbbbbbbbb",
            ),
        ),
    ),
)
def test_workflow_state_parser_rejects_incomplete_call_observations(
    tmp_path: Path,
    display_stems: tuple[str, ...],
    transcript_stems: tuple[str, ...],
) -> None:
    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )
    state_root = tmp_path / "state"
    run_root = state_root / "run-1"
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "workflow_outputs": {"__result__": "COMPLETED"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    display_root = run_root / "provider-observation" / "display"
    transcript_root = run_root / "provider-observation" / "transcripts"
    display_root.mkdir(parents=True)
    transcript_root.mkdir()
    for stem in display_stems:
        (display_root / f"{stem}.display").write_bytes(b"")
    for stem in transcript_stems:
        (transcript_root / f"{stem}.transcript").write_bytes(b"fixture\n")

    with pytest.raises(
        coordinator.PilotTreatmentError,
        match="provider call accounting",
    ):
        coordinator._workflow_treatment_result(state_root)


def test_frozen_visible_check_runs_on_materialized_a1_seed(
    tmp_path: Path,
) -> None:
    control = json.loads(
        (CONTROL_ROOT / "runtime-control.json").read_text(encoding="utf-8")
    )
    assert control["visible_check"] == {
        "argv": [
            "python",
            "-m",
            "pytest",
            "-q",
            "tests/test_smoke_entrypoint.py",
        ],
        "timeout_seconds": 300,
    }
    workspace = tmp_path / "a1-seed"
    shutil.copytree(
        A1_SEED_ROOT,
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    completed = subprocess.run(
        control["visible_check"]["argv"],
        cwd=workspace,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=control["visible_check"]["timeout_seconds"],
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")

    hidden_result = evaluate_nanobragg_workspace(workspace)
    assert hidden_result["verdict"] == "FAIL"
    assert hidden_result["summary"]["hidden_tests_passed"] is False
