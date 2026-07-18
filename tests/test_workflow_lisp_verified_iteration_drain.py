import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    workflow_output_contracts,
    workflow_public_input_contracts,
    workflow_runtime_input_contracts,
)
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from tests.workflow_bundle_helpers import bundle_context_dict


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


def _prepare_verified_runtime_workspace(workspace: Path):
    copy_paths = [
        "workflows/library/verified_iteration_drain/drain.orc",
        "workflows/library/scripts/prepare_verified_iteration.py",
        "workflows/library/scripts/run_verified_iteration_checks.py",
        "workflows/library/scripts/record_verified_iteration.py",
        "workflows/library/prompts/verified_iteration_drain/work.md",
        "workflows/library/prompts/verified_iteration_drain/review_iteration.md",
        "workflows/library/prompts/verified_iteration_drain/review_done.md",
    ]
    for relpath in copy_paths:
        destination = workspace / relpath
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relpath, destination)
    target_design = workspace / "docs/design/verified-target.md"
    target_design.parent.mkdir(parents=True, exist_ok=True)
    target_design.write_text("DEPENDENCY_BEFORE_INTERRUPTION\n", encoding="utf-8")
    check_commands = workspace / "workflows/checks.json"
    check_commands.parent.mkdir(parents=True, exist_ok=True)
    check_commands.write_text(
        json.dumps(["python -c 'raise SystemExit(0)'"]) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Parity Fixture"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "config", "user.email", "parity-fixture@example.invalid"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(["git", "add", "--", "workflows", "docs"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "Initialize verified parity fixture"],
        cwd=workspace,
        check=True,
    )

    command_manifest_path = MIGRATION_INPUTS / "verified_iteration_drain.commands.json"
    compile_result = compile_stage3_entrypoint(
        workspace / "workflows/library/verified_iteration_drain/drain.orc",
        source_roots=(workspace / "workflows/library",),
        entry_workflow=ENTRY_WORKFLOW,
        provider_externs=json.loads(
            (MIGRATION_INPUTS / "verified_iteration_drain.providers.json").read_text()
        ),
        prompt_externs=json.loads(
            (MIGRATION_INPUTS / "verified_iteration_drain.prompts.json").read_text()
        ),
        command_boundaries=_parse_command_boundaries_manifest(
            json.loads(command_manifest_path.read_text()),
            manifest_path=command_manifest_path,
        ),
        workspace_root=workspace,
        lowering_route="wcc_m4",
    )
    bundle = compile_result.validated_bundles_by_name[ENTRY_WORKFLOW]
    contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    return bundle, bind_workflow_inputs(
        contracts,
        {
            "target_design_path": "docs/design/verified-target.md",
            "check_commands_path": "workflows/checks.json",
            "drain_state_root": "state/verified",
            "artifact_work_root": "artifacts/work/verified",
        },
        workspace,
    )


def _provider_success():
    return SimpleNamespace(
        exit_code=0,
        stdout=b"mock-provider-observability",
        stderr=b"",
        duration_ms=1,
        error=None,
        missing_placeholders=None,
        invalid_prompt_placeholder=False,
        raw_stdout=None,
        normalized_stdout=None,
        provider_session=None,
    )


def _provider_retryable_failure():
    result = _provider_success()
    result.exit_code = 1
    result.error = "fixture retryable provider failure"
    return result


def _prompt_work_order(prompt: str) -> dict[str, str]:
    match = re.search(r'\{\s*"iteration"\s*:\s*"\d+".*?\n\}', prompt, re.DOTALL)
    assert match is not None, prompt
    return json.loads(match.group(0))


def _captured_prompt_sha256s(prompts: list[str]) -> list[str]:
    return sorted(
        "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        for prompt in prompts
    )


def _evidence_prompt_sha256s(manager: StateManager) -> list[str]:
    return sorted(
        json.loads(path.read_text(encoding="ascii"))["final_prompt"]["sha256"]
        for path in (manager.run_root / "workflow_lisp/prompt_dependencies").rglob(
            "attempt-*.json"
        )
    )


def _execute_verified_runtime(
    workspace: Path,
    *,
    manager: StateManager,
    bundle,
    worker_verdicts: tuple[str, ...],
    review_decisions: tuple[str, ...] = (),
    done_review_decisions: tuple[str, ...] = (),
    commit_iterations: tuple[int, ...] = (),
    blocked_iterations: tuple[int, ...] = (),
    resume: bool = False,
    fail_first_execution_and_refresh: bool = False,
    capture: dict[str, object] | None = None,
) -> dict[str, object]:
    capture = capture if capture is not None else {}
    capture.setdefault("provider_roles", [])
    capture.setdefault("prompts", [])
    capture.setdefault("executions", 0)
    capture.setdefault("preparations", 0)
    worker_queue = list(worker_verdicts)
    review_queue = list(review_decisions)
    done_queue = list(done_review_decisions)

    def _prepare(_self, provider_name=None, prompt_content=None, env=None, **_kwargs):
        capture["preparations"] = int(capture["preparations"]) + 1
        prompt = prompt_content or ""
        capture["prompts"].append(prompt)
        return SimpleNamespace(
            provider_name=provider_name,
            input_mode="stdin",
            prompt=prompt,
            env=env or {},
        ), None

    def _execute(_self, invocation, **_kwargs):
        capture["executions"] = int(capture["executions"]) + 1
        if fail_first_execution_and_refresh and int(capture["executions"]) == 1:
            (workspace / "docs/design/verified-target.md").write_text(
                "DEPENDENCY_AFTER_INTERRUPTION\n", encoding="utf-8"
            )
            return _provider_retryable_failure()
        prompt = str(invocation.prompt)
        work_order = _prompt_work_order(prompt)
        iteration = int(work_order["iteration"])
        output_bundle_path = invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        if "invoke_worker" in output_bundle_path:
            role = "worker"
            assert worker_queue, "worker fixture exhausted"
            decision = worker_queue.pop(0)
            (workspace / work_order["worker_verdict_path"]).write_text(
                decision + "\n", encoding="utf-8"
            )
            (workspace / work_order["worker_note_path"]).write_text(
                f"worker iteration {iteration}\n", encoding="utf-8"
            )
            if iteration in blocked_iterations:
                blocked = workspace / work_order["blocked_notes_dir"] / f"BLOCKED-{iteration}.md"
                blocked.parent.mkdir(parents=True, exist_ok=True)
                blocked.write_text("owner input required\n", encoding="utf-8")
            if iteration in commit_iterations:
                progress = workspace / "docs/design" / f"progress-{iteration}.txt"
                progress.write_text(f"progress {iteration}\n", encoding="utf-8")
                subprocess.run(
                    ["git", "add", "--", progress.relative_to(workspace).as_posix()],
                    cwd=workspace,
                    check=True,
                )
                subprocess.run(
                    ["git", "commit", "-q", "-m", f"Fixture iteration {iteration}"],
                    cwd=workspace,
                    check=True,
                )
        elif "invoke_iteration_review_provider" in output_bundle_path:
            role = "iteration_review"
            assert review_queue, "iteration review fixture exhausted"
            decision = review_queue.pop(0)
            (workspace / work_order["review_decision_path"]).write_text(
                decision + "\n", encoding="utf-8"
            )
            if decision == "FINDINGS":
                (workspace / work_order["review_findings_path"]).write_text(
                    "fixture findings\n", encoding="utf-8"
                )
        elif "invoke_done_review_provider" in output_bundle_path:
            role = "done_review"
            assert done_queue, "done review fixture exhausted"
            decision = done_queue.pop(0)
            (workspace / work_order["done_review_decision_path"]).write_text(
                decision + "\n", encoding="utf-8"
            )
        else:
            raise AssertionError(
                f"unrecognized provider output bundle path: {output_bundle_path}"
            )
        capture["provider_roles"].append(role)
        output = workspace / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(decision) + "\n", encoding="utf-8")
        return _provider_success()

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        return WorkflowExecutor(
            bundle,
            workspace,
            manager,
            max_retries=1,
            retry_delay_ms=0,
        ).execute(
            resume=resume,
            on_error="stop",
        )


def _run_verified_runtime_scenario(
    workspace: Path,
    *,
    worker_verdicts: tuple[str, ...],
    review_decisions: tuple[str, ...] = (),
    done_review_decisions: tuple[str, ...] = (),
    commit_iterations: tuple[int, ...] = (),
    blocked_iterations: tuple[int, ...] = (),
    stall_limit: int = 3,
) -> dict[str, object]:
    workspace.mkdir(parents=True, exist_ok=True)
    bundle, bound_inputs = _prepare_verified_runtime_workspace(workspace)
    bound_inputs["stall_limit"] = str(stall_limit)
    manager = StateManager(workspace, run_id="verified-candidate")
    manager.initialize(
        "workflows/library/verified_iteration_drain/drain.orc",
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    capture: dict[str, object] = {}
    state = _execute_verified_runtime(
        workspace,
        manager=manager,
        bundle=bundle,
        worker_verdicts=worker_verdicts,
        review_decisions=review_decisions,
        done_review_decisions=done_review_decisions,
        commit_iterations=commit_iterations,
        blocked_iterations=blocked_iterations,
        capture=capture,
    )
    summary_path = workspace / "artifacts/work/verified/drain-summary.json"
    ledger_path = workspace / "artifacts/work/verified/ledger.md"
    ledger_lines = [
        line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.startswith("iter ")
    ]
    lineage_roots = (workspace / "state/verified", workspace / "artifacts/work/verified")
    return {
        "state": state,
        "summary": json.loads(summary_path.read_text(encoding="utf-8")),
        "ledger_iterations": [int(line.split()[1]) for line in ledger_lines],
        "provider_roles": capture["provider_roles"],
        "prompt_iterations": [int(_prompt_work_order(prompt)["iteration"]) for prompt in capture["prompts"]],
        "captured_prompt_sha256s": _captured_prompt_sha256s(capture["prompts"]),
        "evidence_prompt_sha256s": _evidence_prompt_sha256s(manager),
        "lineage_paths": sorted(
            path.relative_to(workspace).as_posix()
            for root in lineage_roots
            for path in root.rglob("*")
            if path.is_file() and ".orchestrate" not in path.parts
        ),
    }


def _run_verified_retry_resume_scenario(workspace: Path) -> dict[str, object]:
    workspace.mkdir(parents=True, exist_ok=True)
    bundle, bound_inputs = _prepare_verified_runtime_workspace(workspace)
    manager = StateManager(workspace, run_id="verified-retry-resume")
    manager.initialize(
        "workflows/library/verified_iteration_drain/drain.orc",
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    capture: dict[str, object] = {}
    state = _execute_verified_runtime(
        workspace,
        manager=manager,
        bundle=bundle,
        worker_verdicts=("DONE",),
        done_review_decisions=("APPROVE",),
        fail_first_execution_and_refresh=True,
        capture=capture,
    )
    first_snapshot = str(capture["prompts"][0])
    resumed_snapshot = str(capture["prompts"][1])
    ledger_path = workspace / "artifacts/work/verified/ledger.md"
    summary_path = workspace / "artifacts/work/verified/drain-summary.json"
    ledger_before = ledger_path.read_bytes()
    summary_before = summary_path.read_bytes()
    completed_resume = StateManager(workspace, run_id=manager.run_id)
    completed_resume.load()
    executions_before = int(capture["executions"])
    _execute_verified_runtime(
        workspace,
        manager=completed_resume,
        bundle=bundle,
        worker_verdicts=(),
        resume=True,
        capture=capture,
    )
    allocations = json.loads(completed_resume.state_file.read_text(encoding="utf-8"))[
        "provider_attempt_allocations"
    ]
    return {
        "state": state,
        "run_id_before_resume": manager.run_id,
        "run_id_after_resume": completed_resume.run_id,
        "attempt_ordinals": next(
            [event["ordinal"] for event in allocation["events"] if event["event"] == "allocated"]
            for allocation in allocations.values()
            if sum(event["event"] == "allocated" for event in allocation["events"]) == 2
        ),
        "first_snapshot": first_snapshot,
        "resumed_snapshot": resumed_snapshot,
        "captured_prompt_sha256s": _captured_prompt_sha256s(capture["prompts"]),
        "evidence_prompt_sha256s": _evidence_prompt_sha256s(completed_resume),
        "provider_executions_after_resume": executions_before,
        "provider_executions_after_completed_resume": int(capture["executions"]),
        "ledger_before_completed_resume": ledger_before,
        "ledger_after_completed_resume": ledger_path.read_bytes(),
        "summary_before_completed_resume": summary_before,
        "summary_after_completed_resume": summary_path.read_bytes(),
    }


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
        ["base_sha", "ledger_path", "work_order_path"],
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
    assert fields["workflows/library/scripts/prepare_verified_iteration.py"][
        "ledger_path"
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


def test_verified_orc_one_continue_then_done_preserves_artifact_lineage(
    tmp_path: Path,
) -> None:
    result = _run_verified_runtime_scenario(
        tmp_path,
        worker_verdicts=("CONTINUE", "DONE"),
        review_decisions=("APPROVE",),
        done_review_decisions=("APPROVE",),
        commit_iterations=(0,),
    )

    assert result["state"]["status"] == "completed"
    assert result["state"]["workflow_outputs"]["return__drain_status"] == "DONE"
    assert result["summary"] == {
        "schema": "verified_iteration_drain_summary/v1",
        "drain_status": "DONE",
        "iterations": 2,
        "statuses": ["ACCEPTED", "DONE"],
        "accepted_count": 2,
        "blocked_notes": [],
        "last_note": "worker iteration 1",
    }
    assert result["ledger_iterations"] == [0, 1]
    assert result["provider_roles"] == ["worker", "iteration_review", "worker", "done_review"]
    assert result["prompt_iterations"] == [0, 0, 1, 1]
    assert result["captured_prompt_sha256s"] == result["evidence_prompt_sha256s"]
    assert len(result["evidence_prompt_sha256s"]) == 4
    assert set(result["lineage_paths"]) == {
        "state/verified/iterations/0/work-order.json",
        "state/verified/iterations/0/checks-result.json",
        "state/verified/iterations/0/checks-log.txt",
        "state/verified/iterations/0/review-package.md",
        "state/verified/iterations/0/worker-verdict.txt",
        "state/verified/iterations/0/worker-note.txt",
        "state/verified/iterations/0/review-decision.txt",
        "state/verified/iterations/0/drain-status.txt",
        "state/verified/iterations/1/work-order.json",
        "state/verified/iterations/1/checks-result.json",
        "state/verified/iterations/1/checks-log.txt",
        "state/verified/iterations/1/review-package.md",
        "state/verified/iterations/1/worker-verdict.txt",
        "state/verified/iterations/1/worker-note.txt",
        "state/verified/iterations/1/done-review-decision.txt",
        "state/verified/iterations/1/drain-status.txt",
        "state/verified/statuses.txt",
        "artifacts/work/verified/ledger.md",
        "artifacts/work/verified/drain-summary.json",
    }


def test_verified_orc_blocked_stalled_and_exhausted_paths(tmp_path: Path) -> None:
    blocked = _run_verified_runtime_scenario(
        tmp_path / "blocked",
        worker_verdicts=("BLOCKED_ON_USER",),
        blocked_iterations=(0,),
    )
    stalled = _run_verified_runtime_scenario(
        tmp_path / "stalled",
        worker_verdicts=("CONTINUE", "CONTINUE"),
        stall_limit=2,
    )
    exhausted = _run_verified_runtime_scenario(
        tmp_path / "exhausted",
        worker_verdicts=("CONTINUE",) * 40,
        stall_limit=41,
    )

    assert blocked["state"]["workflow_outputs"]["return__drain_status"] == "BLOCKED_ON_USER"
    assert blocked["summary"]["statuses"] == ["BLOCKED_ON_USER"]
    assert stalled["state"]["workflow_outputs"]["return__drain_status"] == "STALLED"
    assert stalled["summary"]["statuses"] == ["NO_CHANGE", "NO_CHANGE"]
    assert exhausted["state"]["workflow_outputs"]["return__drain_status"] == "STALLED"
    assert exhausted["summary"]["iterations"] == 40
    assert exhausted["ledger_iterations"] == list(range(40))


def test_verified_orc_retry_refreshes_dependencies_and_resume_is_idempotent(
    tmp_path: Path,
) -> None:
    result = _run_verified_retry_resume_scenario(tmp_path)

    assert result["run_id_before_resume"] == result["run_id_after_resume"]
    assert result["attempt_ordinals"] == [1, 2]
    assert "DEPENDENCY_BEFORE_INTERRUPTION" in result["first_snapshot"]
    assert "DEPENDENCY_AFTER_INTERRUPTION" in result["resumed_snapshot"]
    assert "DEPENDENCY_BEFORE_INTERRUPTION" not in result["resumed_snapshot"]
    assert result["captured_prompt_sha256s"] == result["evidence_prompt_sha256s"]
    assert len(result["evidence_prompt_sha256s"]) == 3
    assert result["provider_executions_after_resume"] == 3
    assert result["provider_executions_after_completed_resume"] == 3
    assert result["ledger_before_completed_resume"] == result["ledger_after_completed_resume"]
    assert result["summary_before_completed_resume"] == result["summary_after_completed_resume"]


def test_verified_post_promotion_orc_smoke_is_fresh(tmp_path: Path) -> None:
    targets = json.loads((MIGRATION_INPUTS / "parity_targets.json").read_text())
    target = next(
        row
        for row in targets["targets"]
        if row["workflow_family"] == "verified_iteration_drain"
    )
    assert target["promotion_eligibility"] == {
        "eligible_for_primary_surface": True,
    }

    result = _run_verified_runtime_scenario(
        tmp_path,
        worker_verdicts=("DONE",),
        done_review_decisions=("APPROVE",),
    )

    assert result["state"]["status"] == "completed"
    assert result["state"]["workflow_outputs"] == {
        "return__drain_status": "DONE",
        "return__drain_summary_path": "artifacts/work/verified/drain-summary.json",
    }
    assert result["provider_roles"] == ["worker", "done_review"]
    assert result["captured_prompt_sha256s"] == result["evidence_prompt_sha256s"]
