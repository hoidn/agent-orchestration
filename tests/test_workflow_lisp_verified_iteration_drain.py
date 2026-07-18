import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
YAML_WORKFLOW = ROOT / "workflows/examples/verified_iteration_drain.yaml"
ORC_WORKFLOW = ROOT / "workflows/library/verified_iteration_drain/drain.orc"
MIGRATION_INPUTS = ROOT / "workflows/examples/inputs/workflow_lisp_migrations"


def test_verified_yaml_baseline_contract_is_frozen() -> None:
    raw = YAML_WORKFLOW.read_bytes()
    workflow = yaml.safe_load(raw)

    assert hashlib.sha256(raw).hexdigest() == "30f868c01d3ead33e958045e37a2062da9256f23f585f68ef9381358d3c4b5b0"
    assert workflow["name"] == "verified-iteration-drain"
    assert workflow["inputs"] == {
        "target_design_path": {
            "type": "relpath",
            "under": "docs/design",
            "must_exist_target": True,
        },
        "check_commands_path": {
            "type": "relpath",
            "under": "workflows",
            "must_exist_target": True,
        },
        "drain_state_root": {
            "type": "relpath",
            "under": "state",
            "default": "state/VERIFIED-ITERATION-DRAIN",
        },
        "artifact_work_root": {
            "type": "relpath",
            "under": "artifacts/work",
            "default": "artifacts/work/VERIFIED-ITERATION-DRAIN",
        },
        "stall_limit": {"kind": "scalar", "type": "string", "default": "3"},
        "worker_provider": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["codex", "claude"],
            "default": "codex",
        },
        "worker_model": {"kind": "scalar", "type": "string", "default": "gpt-5.5"},
        "worker_effort": {"kind": "scalar", "type": "string", "default": "high"},
        "reviewer_provider": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["codex", "claude"],
            "default": "codex",
        },
        "reviewer_model": {"kind": "scalar", "type": "string", "default": "gpt-5.5"},
        "reviewer_effort": {"kind": "scalar", "type": "string", "default": "high"},
    }
    assert workflow["outputs"] == {
        "drain_status": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["CONTINUE", "DONE", "BLOCKED_ON_USER", "STALLED"],
            "from": {"ref": "root.steps.DrainVerifiedIterations.artifacts.drain_status"},
        },
        "drain_summary_path": {
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
            "from": {"ref": "root.steps.PublishSummaryPath.artifacts.drain_summary_path"},
        },
    }
    assert workflow["providers"] == {
        "codex": {
            "command": [
                "codex",
                "exec",
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "--model",
                "${model}",
                "--config",
                "reasoning_effort=${effort}",
            ],
            "input_mode": "stdin",
            "defaults": {
                "model": "${context.workflow_model}",
                "effort": "${context.workflow_effort}",
            },
        },
        "claude": {
            "command": [
                "claude",
                "-p",
                "--model",
                "${model}",
                "--effort",
                "${effort}",
                "--permission-mode",
                "bypassPermissions",
            ],
            "input_mode": "stdin",
            "defaults": {"model": "fable", "effort": "high"},
        },
    }

    loop = workflow["steps"][0]["repeat_until"]
    assert loop["max_iterations"] == 40
    assert loop["on_exhausted"] == {"outputs": {"drain_status": "STALLED"}}
    assert [
        row["compare"]["right"] for row in loop["condition"]["any_of"]
    ] == ["DONE", "BLOCKED_ON_USER", "STALLED"]
    steps = loop["steps"]
    assert [step["input_file"] for step in steps if "input_file" in step] == [
        "workflows/library/prompts/verified_iteration_drain/work.md",
        "workflows/library/prompts/verified_iteration_drain/review_iteration.md",
        "workflows/library/prompts/verified_iteration_drain/review_done.md",
    ]
    assert [step["command"][:2] for step in steps if "command" in step] == [
        ["python", "workflows/library/scripts/prepare_verified_iteration.py"],
        ["python", "workflows/library/scripts/run_verified_iteration_checks.py"],
        ["python", "workflows/library/scripts/record_verified_iteration.py"],
    ]
    assert [
        (step["name"], step["timeout_sec"], step["provider_params"])
        for step in steps
        if "provider" in step
    ] == [
        ("Work", 7200, {"model": "${inputs.worker_model}", "effort": "${inputs.worker_effort}"}),
        (
            "ReviewIteration",
            1800,
            {"model": "${inputs.reviewer_model}", "effort": "${inputs.reviewer_effort}"},
        ),
        (
            "ReviewDoneClaim",
            3600,
            {"model": "${inputs.reviewer_model}", "effort": "${inputs.reviewer_effort}"},
        ),
    ]


def test_verified_port_source_is_absent_at_baseline() -> None:
    assert not ORC_WORKFLOW.exists()


def test_verified_extern_manifests_bind_existing_assets() -> None:
    providers = json.loads((MIGRATION_INPUTS / "verified_iteration_drain.providers.json").read_text())
    prompts = json.loads((MIGRATION_INPUTS / "verified_iteration_drain.prompts.json").read_text())
    commands = json.loads((MIGRATION_INPUTS / "verified_iteration_drain.commands.json").read_text())

    assert providers == {
        "providers.worker.codex": "codex_unrestricted_workspace",
        "providers.worker.claude": "claude_unrestricted_workspace",
        "providers.reviewer.codex": "codex_unrestricted_workspace",
        "providers.reviewer.claude": "claude_unrestricted_workspace",
    }
    assert prompts == {
        "prompts.verified-iteration.work": {
            "input_file": "workflows/library/prompts/verified_iteration_drain/work.md"
        },
        "prompts.verified-iteration.review-iteration": {
            "input_file": "workflows/library/prompts/verified_iteration_drain/review_iteration.md"
        },
        "prompts.verified-iteration.review-done": {
            "input_file": "workflows/library/prompts/verified_iteration_drain/review_done.md"
        },
    }
    assert commands == {
        "prepare_verified_iteration": {
            "kind": "external_tool",
            "stable_command": ["python", "workflows/library/scripts/prepare_verified_iteration.py"],
        },
        "run_verified_iteration_checks": {
            "kind": "external_tool",
            "stable_command": ["python", "workflows/library/scripts/run_verified_iteration_checks.py"],
        },
        "record_verified_iteration": {
            "kind": "external_tool",
            "stable_command": ["python", "workflows/library/scripts/record_verified_iteration.py"],
        },
    }
    for row in [*prompts.values(), *commands.values()]:
        relpath = row.get("input_file") or row["stable_command"][1]
        assert (ROOT / relpath).is_file()
