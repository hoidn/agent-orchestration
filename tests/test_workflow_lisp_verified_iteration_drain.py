import hashlib
import json
from pathlib import Path

import yaml

from orchestrator.workflow.loaded_bundle import (
    workflow_output_contracts,
    workflow_public_input_contracts,
)
from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint


ROOT = Path(__file__).resolve().parents[1]
YAML_WORKFLOW = ROOT / "workflows/examples/verified_iteration_drain.yaml"
ORC_WORKFLOW = ROOT / "workflows/library/verified_iteration_drain/drain.orc"
MIGRATION_INPUTS = ROOT / "workflows/examples/inputs/workflow_lisp_migrations"
ENTRY_WORKFLOW = "verified_iteration_drain/drain::drain"


def _compile_verified_orc():
    assert ORC_WORKFLOW.is_file(), f"verified Workflow Lisp candidate is absent: {ORC_WORKFLOW}"
    return compile_stage3_entrypoint(
        ORC_WORKFLOW,
        source_roots=(ROOT / "workflows/library",),
        entry_workflow=ENTRY_WORKFLOW,
        provider_externs=json.loads(
            (MIGRATION_INPUTS / "verified_iteration_drain.providers.json").read_text()
        ),
        prompt_externs=json.loads(
            (MIGRATION_INPUTS / "verified_iteration_drain.prompts.json").read_text()
        ),
        command_boundaries=_parse_command_boundaries_manifest(
            json.loads(
                (MIGRATION_INPUTS / "verified_iteration_drain.commands.json").read_text()
            ),
            manifest_path=MIGRATION_INPUTS / "verified_iteration_drain.commands.json",
        ),
        workspace_root=ROOT,
        lowering_route="wcc_m4",
    )


def _verified_mapping() -> dict:
    result = _compile_verified_orc()
    return next(
        lowered.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for lowered in compiled.lowered_workflows
        if lowered.typed_workflow.definition.name == ENTRY_WORKFLOW
    )


def _authored_mappings() -> dict[str, dict]:
    result = _compile_verified_orc()
    return {
        lowered.typed_workflow.definition.name: lowered.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for lowered in compiled.lowered_workflows
    }


def _walk_steps(steps):
    for step in steps:
        yield step
        repeat = step.get("repeat_until")
        if isinstance(repeat, dict):
            yield from _walk_steps(repeat.get("steps", []))
        when = step.get("when")
        if isinstance(when, dict):
            yield from _walk_steps(when.get("steps", []))
        for branch_name in ("then", "else"):
            branch = step.get(branch_name)
            if isinstance(branch, dict):
                yield from _walk_steps(branch.get("steps", []))


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


def test_verified_orc_compiles_with_exact_public_contract() -> None:
    result = _compile_verified_orc()
    bundle = result.validated_bundles_by_name[ENTRY_WORKFLOW]

    assert result.entry_result.module.target_dsl_version == "2.15"
    assert bundle.surface.name == ENTRY_WORKFLOW
    assert workflow_public_input_contracts(bundle) == {
        "target_design_path": {
            "kind": "relpath",
            "type": "relpath",
            "under": "docs/design",
            "must_exist_target": True,
        },
        "check_commands_path": {
            "kind": "relpath",
            "type": "relpath",
            "under": "workflows",
            "must_exist_target": True,
        },
        "drain_state_root": {
            "kind": "relpath",
            "type": "relpath",
            "under": "state",
            "must_exist_target": False,
            "default": "state/VERIFIED-ITERATION-DRAIN",
        },
        "artifact_work_root": {
            "kind": "relpath",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": False,
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
    assert workflow_output_contracts(bundle) == {
        "return__drain_status": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["CONTINUE", "DONE", "BLOCKED_ON_USER", "STALLED"],
            "from": {
                "ref": (
                    "root.steps.verified_iteration_drain/drain::drain__match_loop-result"
                    ".artifacts.return__drain_status"
                )
            },
        },
        "return__drain_summary_path": {
            "kind": "relpath",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
            "from": {
                "ref": (
                    "root.steps.verified_iteration_drain/drain::drain__match_loop-result"
                    ".artifacts.return__drain_summary_path"
                )
            },
        },
    }


def test_verified_orc_binds_provider_policy_and_prompt_dependencies() -> None:
    mappings = _authored_mappings()
    provider_workflows = (
        "verified_iteration_drain/drain::invoke-worker",
        "verified_iteration_drain/drain::invoke-iteration-review-provider",
        "verified_iteration_drain/drain::invoke-done-review-provider",
    )
    providers = [
        step
        for workflow_name in provider_workflows
        for step in _walk_steps(mappings[workflow_name]["steps"])
        if "provider" in step
    ]

    assert [(step["provider"], step["timeout_sec"]) for step in providers] == [
        ("codex_unrestricted_workspace", 7200),
        ("claude_unrestricted_workspace", 7200),
        ("codex_unrestricted_workspace", 1800),
        ("claude_unrestricted_workspace", 1800),
        ("codex_unrestricted_workspace", 3600),
        ("claude_unrestricted_workspace", 3600),
    ]
    assert all(
        step["provider_call_policy"]
        == {"model": "${inputs.model}", "effort": "${inputs.effort}"}
        for step in providers
    )
    assert [step["depends_on"]["required"] for step in providers] == [
        *(["${inputs.work_order_path}", "${inputs.target_design_path}", "${inputs.ledger_path}"],) * 2,
        *(
            [
                "${inputs.work_order_path}",
                "${inputs.review_package_path}",
                "${inputs.target_design_path}",
                "${inputs.ledger_path}",
            ],
        )
        * 2,
        *(["${inputs.work_order_path}", "${inputs.target_design_path}"],) * 2,
    ]
    assert all(
        step["depends_on"]["inject"] == {"mode": "content", "position": "prepend"}
        and step["inject_output_contract"] is True
        for step in providers
    )
    assert [
        step["output_bundle"]["fields"][0]["allowed"] for step in providers[2:4]
    ] == [["APPROVE", "FINDINGS"], ["APPROVE", "FINDINGS"]]
    review_mapping = mappings["verified_iteration_drain/drain::invoke-iteration-review"]
    review_branch = next(step for step in review_mapping["steps"] if "if" in step)
    skipped_projection = next(
        step["pure_projection"]
        for step in review_branch["else"]["steps"]
        if "pure_projection" in step
    )
    assert skipped_projection["payload"]["expr"]["value"] == "SKIPPED"


def test_verified_orc_lowers_prepare_check_record_and_direct_summary_return() -> None:
    mapping = _verified_mapping()
    stable_scripts = {
        "workflows/library/scripts/prepare_verified_iteration.py",
        "workflows/library/scripts/run_verified_iteration_checks.py",
        "workflows/library/scripts/record_verified_iteration.py",
    }
    commands = [
        step
        for step in _walk_steps(mapping["steps"])
        if "command" in step and len(step["command"]) > 1 and step["command"][1] in stable_scripts
    ]

    assert [step["command"][1] for step in commands] == [
        "workflows/library/scripts/prepare_verified_iteration.py",
        "workflows/library/scripts/run_verified_iteration_checks.py",
        "workflows/library/scripts/record_verified_iteration.py",
    ]
    assert [sorted(field["name"] for field in step["output_bundle"]["fields"]) for step in commands] == [
        ["base_sha", "work_order_path"],
        ["checks_log_path", "commits_landed", "review_package_path", "verify_status"],
        ["drain_status", "drain_summary_path"],
    ]
    prepare, checks, record = commands
    fields = {
        step["command"][1]: {
            field["name"]: field for field in step["output_bundle"]["fields"]
        }
        for step in commands
    }
    assert fields["workflows/library/scripts/prepare_verified_iteration.py"][
        "work_order_path"
    ]["must_exist_target"] is True
    assert fields["workflows/library/scripts/run_verified_iteration_checks.py"][
        "commits_landed"
    ]["type"] == "bool"
    assert all(
        fields["workflows/library/scripts/run_verified_iteration_checks.py"][name][
            "must_exist_target"
        ]
        is True
        for name in ("checks_log_path", "review_package_path")
    )
    assert prepare["command"][prepare["command"].index("--output") + 1] == (
        "${inputs.drain_state_root}/iterations/${loop.index}/work-order.json"
    )
    assert checks["command"][checks["command"].index("--iteration-dir") + 1] == (
        "${inputs.drain_state_root}/iterations/${loop.index}"
    )
    assert {
        flag: record["command"][record["command"].index(flag) + 1]
        for flag in ("--worker-verdict", "--review-decision", "--done-review-decision")
    } == {
        "--worker-verdict": (
            "${self.steps.verified_iteration_drain/drain::drain__loop-result__body__"
            "worker-verdict__call_verified_iteration_drain/drain::invoke-worker.artifacts.__result__}"
        ),
        "--review-decision": (
            "${self.steps.verified_iteration_drain/drain::drain__loop-result__body__"
            "review-decision__call_verified_iteration_drain/drain::invoke-iteration-review"
            ".artifacts.__result__}"
        ),
        "--done-review-decision": (
            "${self.steps.verified_iteration_drain/drain::drain__loop-result__body__"
            "done-review-decision__call_verified_iteration_drain/drain::invoke-done-review"
            ".artifacts.__result__}"
        ),
    }
    worker_call = next(
        step
        for step in _walk_steps(mapping["steps"])
        if step.get("call") == "verified_iteration_drain/drain::invoke-worker"
    )
    assert worker_call["with"]["work_order_path"]["ref"].endswith(
        "__prepared__prepare_verified_iteration.artifacts.work_order_path"
    )
    assert mapping["outputs"]["return__drain_summary_path"]["from"]["ref"].endswith(
        ".artifacts.return__drain_summary_path"
    )
    assert not any(
        "write_lisp_frontend_relpath_value.py" in step.get("command", []) for step in commands
    )


def test_verified_orc_projects_terminal_and_exhaustion_states() -> None:
    mapping = _verified_mapping()
    repeat = next(step["repeat_until"] for step in mapping["steps"] if "repeat_until" in step)

    assert repeat["max_iterations"] == 40
    assert repeat["on_exhausted"] == {
        "outputs": {
            "status": "DONE",
            "result__variant": "EXHAUSTED",
            "result__drain_status": "STALLED",
            "result__reason": "max_iterations_exhausted",
        }
    }
    assert repeat["condition"] == {
        "compare": {
            "left": {"ref": "self.outputs.status"},
            "op": "eq",
            "right": "DONE",
        }
    }
    terminal_mapping = _authored_mappings()["verified_iteration_drain/drain::is-terminal"]
    terminal_projection = next(
        step["pure_projection"] for step in terminal_mapping["steps"] if "pure_projection" in step
    )
    terminal_expr = terminal_projection["payload"]["expr"]
    assert terminal_expr["operator"] == "or"
    assert [argument["args"][1]["value"] for argument in terminal_expr["args"]] == [
        "DONE",
        "BLOCKED_ON_USER",
        "STALLED",
    ]
    loop_result_match = next(
        step["match"]
        for step in mapping["steps"]
        if step["name"].endswith("__loop-result__result")
    )
    assert loop_result_match["cases"]["TERMINAL"]["outputs"][
        "return__drain_summary_path"
    ]["from"]["ref"].endswith(".artifacts.result__drain_summary_path")
    assert loop_result_match["cases"]["EXHAUSTED"]["outputs"][
        "return__drain_summary_path"
    ]["from"]["ref"].endswith(".artifacts.state__drain_summary_path")
    provider_refs = json.dumps(repeat)
    assert "worker_verdict" in provider_refs
    assert "review_decision" in provider_refs
    assert "done_review_decision" in provider_refs


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
