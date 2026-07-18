from __future__ import annotations

import hashlib
import json
import re
import shutil
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
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
YAML_WORKFLOW = ROOT / "workflows/examples/generic_run_watchdog.yaml"
ORC_WORKFLOW = ROOT / "workflows/library/generic_run_watchdog/watchdog.orc"
PORT_DESIGN = ROOT / "docs/plans/2026-07-18-generic-run-watchdog-orc-port-design.md"
MIGRATION_INPUTS = ROOT / "workflows/examples/inputs/workflow_lisp_migrations"
ENTRY_WORKFLOW = "generic_run_watchdog/watchdog::watchdog"


class _WatchdogProviderBoundaryInterruption(BaseException):
    pass


def _compile_watchdog_orc():
    assert ORC_WORKFLOW.is_file(), f"watchdog Workflow Lisp candidate is absent: {ORC_WORKFLOW}"
    commands_path = MIGRATION_INPUTS / "generic_run_watchdog.commands.json"
    return compile_stage3_entrypoint(
        ORC_WORKFLOW,
        source_roots=(ROOT / "workflows/library",),
        entry_workflow=ENTRY_WORKFLOW,
        provider_externs=json.loads(
            (MIGRATION_INPUTS / "generic_run_watchdog.providers.json").read_text()
        ),
        prompt_externs=json.loads(
            (MIGRATION_INPUTS / "generic_run_watchdog.prompts.json").read_text()
        ),
        command_boundaries=_parse_command_boundaries_manifest(
            json.loads(commands_path.read_text()),
            manifest_path=commands_path,
        ),
        workspace_root=ROOT,
        lowering_route="wcc_m4",
    )


def _watchdog_authored_mappings() -> dict[str, dict]:
    result = _compile_watchdog_orc()
    return {
        lowered.typed_workflow.definition.name: lowered.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for lowered in compiled.lowered_workflows
    }


def _walk_steps(steps):
    for step in steps:
        yield step
        for branch_name in ("then", "else"):
            branch = step.get(branch_name)
            if isinstance(branch, dict):
                yield from _walk_steps(branch.get("steps", []))
        match = step.get("match")
        if isinstance(match, dict):
            for case in match.get("cases", {}).values():
                yield from _walk_steps(case.get("steps", []))


def _argv_value(argv: list[str], option: str) -> str:
    return argv[argv.index(option) + 1]


def _table_after_heading(text: str, heading: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    start = lines.index(heading)
    table_lines: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if line.startswith("|"):
            table_lines.append(line)
    assert len(table_lines) >= 3, f"missing Markdown table after {heading}"
    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip().replace("`", "") for cell in line.strip("|").split("|")]
        assert len(cells) == len(headers), line
        rows.append(dict(zip(headers, cells, strict=True)))
    return rows


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


def _prepare_watchdog_runtime_workspace(
    workspace: Path,
    *,
    target_status: str,
    repair_provider: str,
):
    workspace.mkdir(parents=True, exist_ok=True)
    copy_paths = [
        "workflows/library/generic_run_watchdog/watchdog.orc",
        "workflows/library/scripts/probe_orchestrator_run.py",
        "workflows/library/scripts/publish_run_watchdog_result.py",
        "workflows/library/prompts/generic_run_watchdog/repair_run_failure.md",
    ]
    for relpath in copy_paths:
        destination = workspace / relpath
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relpath, destination)

    target_state = workspace / ".orchestrate/runs/target-run/state.json"
    target_state.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()
    target_state.write_text(
        json.dumps(
            {
                "schema_version": "2.1",
                "run_id": "target-run",
                "workflow_file": "workflows/examples/fixture.yaml",
                "started_at": now,
                "updated_at": now,
                "status": target_status,
                "steps": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    commands_path = MIGRATION_INPUTS / "generic_run_watchdog.commands.json"
    compile_result = compile_stage3_entrypoint(
        workspace / "workflows/library/generic_run_watchdog/watchdog.orc",
        source_roots=(workspace / "workflows/library",),
        entry_workflow=ENTRY_WORKFLOW,
        provider_externs=json.loads(
            (MIGRATION_INPUTS / "generic_run_watchdog.providers.json").read_text()
        ),
        prompt_externs=json.loads(
            (MIGRATION_INPUTS / "generic_run_watchdog.prompts.json").read_text()
        ),
        command_boundaries=_parse_command_boundaries_manifest(
            json.loads(commands_path.read_text()),
            manifest_path=commands_path,
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
    bound_inputs = bind_workflow_inputs(
        contracts,
        {
            "target_run_id": "target-run",
            "state_root": "state/watchdog",
            "evidence_root": "artifacts/work/watchdog",
            "repair_result_target_path": "artifacts/work/watchdog/repair-result.json",
            "repair_provider": repair_provider,
        },
        workspace,
    )
    return bundle, bound_inputs


def _provider_role_from_profile(provider_name: str) -> str:
    if provider_name == "codex_unrestricted_workspace":
        return "codex"
    if provider_name == "claude_unrestricted_workspace":
        return "claude_opus"
    raise AssertionError(f"unrecognized watchdog provider profile: {provider_name}")


def _prompt_evidence_sha256s(manager: StateManager) -> list[str]:
    return sorted(
        json.loads(path.read_text(encoding="ascii"))["final_prompt"]["sha256"]
        for path in (manager.run_root / "workflow_lisp/prompt_dependencies").rglob(
            "attempt-*.json"
        )
    )


def _publisher_command_instrumentation(capture: dict[str, object]):
    original_execute_command = WorkflowExecutor._execute_command

    def _execute_command(self, step, state):
        command = step.get("command")
        if isinstance(command, list) and command[:2] == [
            "python",
            "workflows/library/scripts/publish_run_watchdog_result.py",
        ]:
            capture["publisher_executions"] = int(
                capture.get("publisher_executions", 0)
            ) + 1
        return original_execute_command(self, step, state)

    return patch.object(WorkflowExecutor, "_execute_command", _execute_command)


def _execute_watchdog_runtime(
    workspace: Path,
    *,
    manager: StateManager,
    bundle,
    capture: dict[str, object],
    resume: bool = False,
    fail_first_provider_attempt: bool = False,
    interrupt_after_provider_commit: bool = False,
) -> dict[str, object]:
    capture.setdefault("provider_roles", [])
    capture.setdefault("prompts", [])
    capture.setdefault("provider_executions", 0)
    capture.setdefault("publisher_executions", 0)

    def _prepare(_self, provider_name=None, prompt_content=None, env=None, **_kwargs):
        prompt = str(prompt_content or "")
        capture["prompts"].append(prompt)
        return SimpleNamespace(
            provider_name=provider_name,
            input_mode="stdin",
            prompt=prompt,
            env=env or {},
        ), None

    def _execute(_self, invocation, **_kwargs):
        capture["provider_executions"] = int(capture["provider_executions"]) + 1
        bundle_path = str(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        capture["provider_roles"].append(
            _provider_role_from_profile(str(invocation.provider_name))
        )
        if fail_first_provider_attempt and int(capture["provider_executions"]) == 1:
            watch_path = workspace / "state/watchdog/watch.json"
            watch = json.loads(watch_path.read_text(encoding="utf-8"))
            watch["fixture_dependency_version"] = "after-first-attempt"
            watch_path.write_text(json.dumps(watch, indent=2) + "\n", encoding="utf-8")
            return _provider_retryable_failure()

        report_path = workspace / "artifacts/work/watchdog/repair-report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("# Fixture repair report\n", encoding="utf-8")
        provider_result = {
            "repair_status": "FIXED_AND_RESUMED",
            "fix_complexity": "TRIVIAL",
            "recovery_action": "RESUME",
            "repair_report_path": "artifacts/work/watchdog/repair-report.md",
            "plan_path": "",
            "new_run_id": "",
        }
        compatibility_path = workspace / "artifacts/work/watchdog/repair-result.json"
        compatibility_path.write_text(
            json.dumps(provider_result, indent=2) + "\n", encoding="utf-8"
        )
        output = workspace / bundle_path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(provider_result) + "\n", encoding="utf-8")
        return _provider_success()

    original_emit = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit

    def _emit_then_interrupt(self, state, step_name, step, finalized):
        original_emit(self, state, step_name, step, finalized)
        output_bundle = step.get("output_bundle")
        fields = output_bundle.get("fields", []) if isinstance(output_bundle, dict) else []
        field_names = {
            field.get("name") for field in fields if isinstance(field, dict)
        }
        if "provider" in step and {
            "repair_status",
            "fix_complexity",
            "recovery_action",
            "repair_report_path",
        }.issubset(field_names):
            raise _WatchdogProviderBoundaryInterruption

    with ExitStack() as stack:
        stack.enter_context(patch.object(ProviderExecutor, "prepare_invocation", _prepare))
        stack.enter_context(patch.object(ProviderExecutor, "execute", _execute))
        stack.enter_context(_publisher_command_instrumentation(capture))
        if interrupt_after_provider_commit:
            stack.enter_context(
                patch.object(
                    WorkflowExecutor,
                    "_emit_lexical_checkpoint_shadow_after_step_commit",
                    _emit_then_interrupt,
                )
            )
        return WorkflowExecutor(
            bundle,
            workspace,
            manager,
            max_retries=1,
            retry_delay_ms=0,
        ).execute(resume=resume, on_error="stop")


def _run_watchdog_runtime_scenario(
    workspace: Path,
    *,
    target_status: str,
    repair_provider: str = "codex",
) -> dict[str, object]:
    bundle, bound_inputs = _prepare_watchdog_runtime_workspace(
        workspace,
        target_status=target_status,
        repair_provider=repair_provider,
    )
    manager = StateManager(workspace, run_id="watchdog-candidate")
    manager.initialize(
        "workflows/library/generic_run_watchdog/watchdog.orc",
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    capture: dict[str, object] = {}
    state = _execute_watchdog_runtime(
        workspace,
        manager=manager,
        bundle=bundle,
        capture=capture,
    )
    semantic_result = json.loads(
        (workspace / "state/watchdog/watchdog-result.json").read_text(encoding="utf-8")
    )
    lineage_roots = (workspace / "state/watchdog", workspace / "artifacts/work/watchdog")
    return {
        "outputs": state["workflow_outputs"],
        "provider_roles": capture["provider_roles"],
        "semantic_result": semantic_result,
        "lineage_paths": sorted(
            path.relative_to(workspace).as_posix()
            for root in lineage_roots
            for path in root.rglob("*")
            if path.is_file()
        ),
    }


def _run_watchdog_retry_resume_scenario(workspace: Path) -> dict[str, object]:
    bundle, bound_inputs = _prepare_watchdog_runtime_workspace(
        workspace,
        target_status="failed",
        repair_provider="codex",
    )
    manager = StateManager(workspace, run_id="watchdog-retry-resume")
    manager.initialize(
        "workflows/library/generic_run_watchdog/watchdog.orc",
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    capture: dict[str, object] = {}
    with pytest.raises(_WatchdogProviderBoundaryInterruption):
        _execute_watchdog_runtime(
            workspace,
            manager=manager,
            bundle=bundle,
            capture=capture,
            fail_first_provider_attempt=True,
            interrupt_after_provider_commit=True,
        )

    prompts = list(capture["prompts"])
    prompt_sha256s = sorted(
        "sha256:" + hashlib.sha256(str(prompt).encode("utf-8")).hexdigest()
        for prompt in prompts
    )
    persisted = json.loads(manager.state_file.read_text(encoding="utf-8"))
    attempt_ordinals = next(
        [event["ordinal"] for event in allocation["events"] if event["event"] == "allocated"]
        for allocation in persisted["provider_attempt_allocations"].values()
        if sum(event["event"] == "allocated" for event in allocation["events"]) == 2
    )
    provider_executions_before_resume = int(capture["provider_executions"])
    publication_count_before_resume = int(capture["publisher_executions"])

    resume_manager = StateManager(workspace, run_id=manager.run_id)
    resume_manager.load()
    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        side_effect=AssertionError("completed provider boundary must not prepare on resume"),
    ), patch.object(
        ProviderExecutor,
        "execute",
        side_effect=AssertionError("completed provider boundary must not execute on resume"),
    ), _publisher_command_instrumentation(capture):
        resumed = WorkflowExecutor(
            bundle, workspace, resume_manager, retry_delay_ms=0
        ).execute(resume=True, on_error="stop")
    semantic_result_after_resume = json.loads(
        (workspace / "state/watchdog/watchdog-result.json").read_text(encoding="utf-8")
    )
    publication_count_after_resume = int(capture["publisher_executions"])

    replay_manager = StateManager(workspace, run_id=manager.run_id)
    replay_manager.load()
    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        side_effect=AssertionError("completed replay must not prepare provider"),
    ), patch.object(
        ProviderExecutor,
        "execute",
        side_effect=AssertionError("completed replay must not execute provider"),
    ), _publisher_command_instrumentation(capture):
        replayed = WorkflowExecutor(
            bundle, workspace, replay_manager, retry_delay_ms=0
        ).execute(resume=True, on_error="stop")
    semantic_result_after_replay = json.loads(
        (workspace / "state/watchdog/watchdog-result.json").read_text(encoding="utf-8")
    )
    publication_count_after_replay = int(capture["publisher_executions"])

    return {
        "status": resumed["status"],
        "provider_roles": capture["provider_roles"],
        "attempt_ordinals": attempt_ordinals,
        "first_dependency_sha256": prompt_sha256s[0],
        "retry_dependency_sha256": prompt_sha256s[1],
        "captured_prompt_sha256s": prompt_sha256s,
        "evidence_prompt_sha256s": _prompt_evidence_sha256s(resume_manager),
        "provider_executions_before_resume": provider_executions_before_resume,
        "provider_executions_after_resume": int(capture["provider_executions"]),
        "publication_count_before_resume": publication_count_before_resume,
        "publication_count_after_resume": publication_count_after_resume,
        "publication_count_after_replay": publication_count_after_replay,
        "semantic_result_after_resume": semantic_result_after_resume,
        "semantic_result_after_replay": semantic_result_after_replay,
    }


def test_watchdog_yaml_baseline_contract_is_frozen() -> None:
    payload = YAML_WORKFLOW.read_bytes()
    workflow = yaml.safe_load(payload)

    assert hashlib.sha256(payload).hexdigest() == (
        "797f02672508f70a1b5071b216a30946f5a78a98d9413cca25ed5fa167c07b85"
    )
    assert workflow["version"] == "2.14"
    assert workflow["name"] == "generic-run-watchdog-v214"
    assert workflow["context"] == {
        "workflow_model": "gpt-5.4",
        "workflow_effort": "high",
    }
    assert list(workflow["inputs"]) == [
        "target_run_id",
        "state_root",
        "evidence_root",
        "repair_result_target_path",
        "max_stale_minutes",
        "repair_provider",
    ]
    assert {
        name: (contract.get("type"), contract.get("default"), contract.get("allowed"))
        for name, contract in workflow["inputs"].items()
    } == {
        "target_run_id": ("string", None, None),
        "state_root": ("relpath", "state/GENERIC-RUN-WATCHDOG", None),
        "evidence_root": ("relpath", "artifacts/work/generic-run-watchdog", None),
        "repair_result_target_path": (
            "relpath",
            "artifacts/work/generic-run-watchdog/repair-result.json",
            None,
        ),
        "max_stale_minutes": ("integer", 60, None),
        "repair_provider": ("enum", "codex", ["codex", "claude_opus"]),
    }
    assert {
        name: (contract["type"], contract.get("allowed"))
        for name, contract in workflow["outputs"].items()
    } == {
        "watch_status": (
            "enum",
            ["RUNNING_OK", "COMPLETED", "FAILED", "CRASHED", "STALLED", "UNKNOWN"],
        ),
        "repair_status": (
            "enum",
            [
                "NO_ACTION",
                "FIXED_AND_RESUMED",
                "FIXED_AND_RELAUNCHED",
                "PLAN_WRITTEN",
                "BLOCKED",
            ],
        ),
        "recovery_action": (
            "enum",
            ["NONE", "RESUME", "RELAUNCH", "RESTART", "DECLINED"],
        ),
        "watchdog_result_path": ("relpath", None),
    }

    probe, repair, publish = workflow["steps"]
    assert [probe["id"], repair["id"], publish["id"]] == [
        "probe_run_state",
        "repair_run_failure",
        "publish_watchdog_result",
    ]
    assert [field["name"] for field in probe["output_bundle"]["fields"]] == [
        "watch_status",
        "repair_required",
        "recommended_recovery",
        "evidence_bundle_path",
        "repair_result_target_path",
    ]
    assert repair["provider"] == "${inputs.repair_provider}"
    assert repair["timeout_sec"] == 7200
    assert repair["when"]["compare"]["right"] == "YES"
    assert repair["depends_on"]["required"] == ["${inputs.state_root}/watch.json"]
    assert repair["depends_on"]["inject"]["mode"] == "content"
    assert repair["depends_on"]["inject"]["position"] == "prepend"
    assert [field["name"] for field in repair["output_bundle"]["fields"]] == [
        "repair_status",
        "fix_complexity",
        "recovery_action",
        "repair_report_path",
        "plan_path",
        "new_run_id",
    ]
    assert [field["name"] for field in publish["output_bundle"]["fields"]] == [
        "watchdog_result_path",
        "watch_status",
        "repair_status",
        "recovery_action",
    ]


def test_watchdog_orc_compiles_with_exact_six_input_four_output_contract() -> None:
    result = _compile_watchdog_orc()
    bundle = result.validated_bundles_by_name[ENTRY_WORKFLOW]

    assert result.entry_result.module.target_dsl_version == "2.15"
    assert bundle.surface.name == ENTRY_WORKFLOW
    assert workflow_public_input_contracts(bundle) == {
        "target_run_id": {"kind": "scalar", "type": "string"},
        "state_root": {
            "kind": "relpath",
            "type": "relpath",
            "under": "state",
            "must_exist_target": False,
            "default": "state/GENERIC-RUN-WATCHDOG",
        },
        "evidence_root": {
            "kind": "relpath",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": False,
            "default": "artifacts/work/generic-run-watchdog",
        },
        "repair_result_target_path": {
            "kind": "relpath",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": False,
            "default": "artifacts/work/generic-run-watchdog/repair-result.json",
        },
        "max_stale_minutes": {"kind": "scalar", "type": "integer", "default": 60},
        "repair_provider": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["codex", "claude_opus"],
            "default": "codex",
        },
    }
    assert list(workflow_output_contracts(bundle)) == [
        "return__watch_status",
        "return__repair_status",
        "return__recovery_action",
        "return__watchdog_result_path",
    ]
    assert [
        contract["allowed"]
        for contract in workflow_output_contracts(bundle).values()
        if contract["type"] == "enum"
    ] == [
        ["RUNNING_OK", "COMPLETED", "FAILED", "CRASHED", "STALLED", "UNKNOWN"],
        ["NO_ACTION", "FIXED_AND_RESUMED", "FIXED_AND_RELAUNCHED", "PLAN_WRITTEN", "BLOCKED"],
        ["NONE", "RESUME", "RELAUNCH", "RESTART", "DECLINED"],
    ]


def test_watchdog_orc_clean_path_skips_provider_and_publishes_no_action() -> None:
    mappings = _watchdog_authored_mappings()
    entry = mappings[ENTRY_WORKFLOW]
    entry_steps = list(_walk_steps(entry["steps"]))

    assert not any("provider" in step for step in entry_steps)
    assert any(
        step.get("command", [])[:2]
        == ["python", "workflows/library/scripts/probe_orchestrator_run.py"]
        for step in entry_steps
    )
    outcome_branch = next(step for step in entry["steps"] if step.get("if"))
    assert any("call" in step for step in outcome_branch["then"]["steps"])
    assert not any("call" in step or "provider" in step for step in outcome_branch["else"]["steps"])

    publishers = [
        step["command"]
        for step in entry_steps
        if step.get("command", [])[:2]
        == ["python", "workflows/library/scripts/publish_run_watchdog_result.py"]
    ]
    assert len(publishers) == 2
    no_action = next(
        argv for argv in publishers if _argv_value(argv, "--repair-status") == "NO_ACTION"
    )
    assert {
        option: _argv_value(no_action, option)
        for option in (
            "--repair-result-path",
            "--repair-status",
            "--fix-complexity",
            "--recovery-action",
            "--repair-report-path",
            "--plan-path",
            "--new-run-id",
        )
    } == {
        "--repair-result-path": "",
        "--repair-status": "NO_ACTION",
        "--fix-complexity": "NOT_APPLICABLE",
        "--recovery-action": "NONE",
        "--repair-report-path": "",
        "--plan-path": "",
        "--new-run-id": "",
    }


def test_watchdog_orc_repair_path_selects_exact_provider_policy() -> None:
    mappings = _watchdog_authored_mappings()
    providers = [
        step
        for mapping in mappings.values()
        for step in _walk_steps(mapping["steps"])
        if "provider" in step
    ]

    assert [(step["provider"], step["timeout_sec"]) for step in providers] == [
        ("codex_unrestricted_workspace", 7200),
        ("claude_unrestricted_workspace", 7200),
    ]
    assert [step["provider_call_policy"] for step in providers] == [
        {"model": "gpt-5.4", "effort": "high"},
        {"model": "opus", "effort": "high"},
    ]
    assert all(
        [field["name"] for field in step["output_bundle"]["fields"]]
        == [
            "repair_status",
            "fix_complexity",
            "recovery_action",
            "repair_report_path",
            "plan_path",
            "new_run_id",
        ]
        for step in providers
    )
    assert all(
        next(
            field
            for field in step["output_bundle"]["fields"]
            if field["name"] == "repair_report_path"
        )
        == {
            "name": "repair_report_path",
            "json_pointer": "/repair_report_path",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        }
        for step in providers
    )


def test_watchdog_orc_prompt_dependency_retry_and_resume_contract() -> None:
    mappings = _watchdog_authored_mappings()
    providers = [
        step
        for mapping in mappings.values()
        for step in _walk_steps(mapping["steps"])
        if "provider" in step
    ]

    assert len(providers) == 2
    assert all(
        step["depends_on"]
        == {
            "required": ["${inputs.watch_bundle_path}"],
            "optional": [],
            "inject": {"mode": "content", "position": "prepend"},
        }
        and step["inject_output_contract"] is True
        for step in providers
    )

    entry_steps = list(_walk_steps(mappings[ENTRY_WORKFLOW]["steps"]))
    probe = next(
        step
        for step in entry_steps
        if step.get("command", [])[:2]
        == ["python", "workflows/library/scripts/probe_orchestrator_run.py"]
    )
    assert [field["name"] for field in probe["output_bundle"]["fields"]] == [
        "watch_bundle_path",
        "watch_status",
        "repair_required",
        "recommended_recovery",
        "evidence_bundle_path",
        "repair_result_target_path",
    ]
    prompt_manifest = json.loads(
        (MIGRATION_INPUTS / "generic_run_watchdog.prompts.json").read_text()
    )
    prompt_relpath = prompt_manifest[
        "prompts.generic-run-watchdog.repair-run-failure"
    ]["input_file"]
    assert "${inputs." not in (ROOT / prompt_relpath).read_text()


def test_watchdog_port_design_closes_both_typed_branches() -> None:
    assert PORT_DESIGN.is_file(), f"bounded watchdog port design is absent: {PORT_DESIGN}"
    text = PORT_DESIGN.read_text(encoding="utf-8")

    assert "**Module:** `generic_run_watchdog/watchdog`" in text
    assert "**Entry workflow:** `generic_run_watchdog/watchdog::watchdog`" in text
    assert "**Target DSL:** `2.15`" in text

    inputs = _table_after_heading(text, "## Public Inputs")
    assert [(row["Name"], row["Type"], row["Default"]) for row in inputs] == [
        ("target_run_id", "String", "required"),
        ("state_root", "StateRoot", "state/GENERIC-RUN-WATCHDOG"),
        ("evidence_root", "ArtifactRoot", "artifacts/work/generic-run-watchdog"),
        (
            "repair_result_target_path",
            "ArtifactOutputPath",
            "artifacts/work/generic-run-watchdog/repair-result.json",
        ),
        ("max_stale_minutes", "Int", "60"),
        ("repair_provider", "RepairProvider", "codex"),
    ]

    outputs = _table_after_heading(text, "## Public Outputs")
    assert [(row["Name"], row["Type"]) for row in outputs] == [
        ("watch_status", "WatchStatus"),
        ("repair_status", "RepairStatus"),
        ("recovery_action", "RecoveryAction"),
        ("watchdog_result_path", "ProducedStatePath"),
    ]

    providers = _table_after_heading(text, "## Branch-Local Provider Policy")
    assert [
        (
            row["Branch"],
            row["Extern"],
            row["Profile"],
            row["Model"],
            row["Effort"],
            row["Timeout seconds"],
        )
        for row in providers
    ] == [
        (
            "codex",
            "providers.repair.codex",
            "codex_unrestricted_workspace",
            "gpt-5.4",
            "high",
            "7200",
        ),
        (
            "claude_opus",
            "providers.repair.claude",
            "claude_unrestricted_workspace",
            "opus",
            "high",
            "7200",
        ),
    ]

    flow = {row["Phase"]: row for row in _table_after_heading(text, "## Typed Flow")}
    assert list(flow) == ["probe", "no_action", "repair", "publish"]
    assert flow["probe"]["Typed result"] == "WatchProbe"
    assert flow["no_action"]["Typed result"] == "RepairOutcome.NO_ACTION"
    assert flow["repair"]["Typed result"] == "RepairOutcome.REPAIR"
    assert flow["publish"]["Typed result"] == "WatchdogOutput"
    assert "provider is skipped" in flow["no_action"]["Contract"]
    assert "compiler-known extern" in flow["repair"]["Contract"]
    assert "typed fields" in flow["publish"]["Contract"]

    assert (
        "ProviderRepairStatus = FIXED_AND_RESUMED | FIXED_AND_RELAUNCHED | "
        "PLAN_WRITTEN | BLOCKED"
    ) in text
    assert "ProviderFixComplexity = TRIVIAL | NONTRIVIAL" in text
    assert (
        "ProviderRecoveryAction = RESUME | RELAUNCH | RESTART | DECLINED"
    ) in text
    assert "FixComplexity = NOT_APPLICABLE | TRIVIAL | NONTRIVIAL" in text
    assert "repair_status: ProviderRepairStatus" in text
    assert "recovery_action: ProviderRecoveryAction" in text
    assert "fix_complexity: ProviderFixComplexity" in text
    assert "RepairPublication" not in text
    assert "exhaustively widens all three provider-only enums" in " ".join(
        text.split()
    )
    assert "the three provider-only enums" in " ".join(text.lower().split())
    assert "cannot return public `no_action`, `not_applicable`, or `none`" in text.lower()
    normalized_text = " ".join(text.split())
    assert "no path-to-`String` coercion" in normalized_text
    assert "two branch-local invocations of the same certified publisher command" in normalized_text

    dependencies = _table_after_heading(text, "## Prompt Dependency Contract")
    assert dependencies == [
        {
            "Provider boundary": "repair",
            "Required exact relpath": "watch.watch_bundle_path",
            "Position": "prepend",
            "Instruction meaning": "the injected watch bundle is authoritative evidence",
            "Retry": "fresh immutable snapshot per new attempt",
            "Completed reuse": "do not reopen dependency files",
        }
    ]

    parity = {row["Case"]: row for row in _table_after_heading(text, "## Parity Cases")}
    assert set(parity) == {
        "running_or_completed",
        "repair_required_codex",
        "repair_required_claude",
        "provider_retry",
        "completed_resume",
    }
    assert parity["running_or_completed"]["Provider calls"] == "0"
    assert parity["repair_required_codex"]["Provider calls"] == "1 codex"
    assert parity["repair_required_claude"]["Provider calls"] == "1 claude"

    normalized = " ".join(re.sub(r"[`*_-]", " ", text.lower()).split())
    assert "compatibility mirrors are not orchestration control authority" in normalized
    assert "recovery action from recovery certification" in normalized
    assert "explicitly deferred" in normalized
    assert "docs/backlog/active/2026 05 30 watchdog recovery status model.md" in normalized
    assert "no family specific compiler branch" in normalized


def test_watchdog_extern_manifests_bind_existing_assets() -> None:
    providers = json.loads(
        (MIGRATION_INPUTS / "generic_run_watchdog.providers.json").read_text()
    )
    prompts = json.loads(
        (MIGRATION_INPUTS / "generic_run_watchdog.prompts.json").read_text()
    )
    commands = json.loads(
        (MIGRATION_INPUTS / "generic_run_watchdog.commands.json").read_text()
    )

    assert providers == {
        "providers.repair.codex": "codex_unrestricted_workspace",
        "providers.repair.claude": "claude_unrestricted_workspace",
    }
    assert prompts == {
        "prompts.generic-run-watchdog.repair-run-failure": {
            "input_file": (
                "workflows/library/prompts/generic_run_watchdog/"
                "repair_run_failure.md"
            )
        }
    }
    assert commands == {
        "probe_orchestrator_run": {
            "kind": "external_tool",
            "stable_command": [
                "python",
                "workflows/library/scripts/probe_orchestrator_run.py",
            ],
        },
        "publish_run_watchdog_result": {
            "kind": "external_tool",
            "stable_command": [
                "python",
                "workflows/library/scripts/publish_run_watchdog_result.py",
            ],
        },
    }
    for row in [*prompts.values(), *commands.values()]:
        relpath = row.get("input_file") or row["stable_command"][1]
        assert (ROOT / relpath).is_file()


def test_watchdog_orc_both_branches_preserve_artifact_lineage(tmp_path: Path) -> None:
    no_action = _run_watchdog_runtime_scenario(
        tmp_path / "no-action",
        target_status="running",
    )
    codex_repair = _run_watchdog_runtime_scenario(
        tmp_path / "codex-repair",
        target_status="failed",
        repair_provider="codex",
    )
    claude_repair = _run_watchdog_runtime_scenario(
        tmp_path / "claude-repair",
        target_status="failed",
        repair_provider="claude_opus",
    )

    assert no_action["outputs"] == {
        "return__watch_status": "RUNNING_OK",
        "return__repair_status": "NO_ACTION",
        "return__recovery_action": "NONE",
        "return__watchdog_result_path": "state/watchdog/watchdog-result.json",
    }
    assert no_action["provider_roles"] == []
    no_action_lineage = set(no_action["lineage_paths"])
    assert {
        "state/watchdog/watch.json",
        "state/watchdog/watchdog-result.json",
        "artifacts/work/watchdog/target-run-evidence.json",
    }.issubset(no_action_lineage)
    assert {
        "artifacts/work/watchdog/repair-result.json",
        "artifacts/work/watchdog/repair-report.md",
    }.isdisjoint(no_action_lineage)
    assert codex_repair["provider_roles"] == ["codex"]
    assert claude_repair["provider_roles"] == ["claude_opus"]
    assert codex_repair["outputs"] == claude_repair["outputs"] == {
        "return__watch_status": "FAILED",
        "return__repair_status": "FIXED_AND_RESUMED",
        "return__recovery_action": "RESUME",
        "return__watchdog_result_path": "state/watchdog/watchdog-result.json",
    }
    assert no_action["semantic_result"]["repair_result_path"] == ""
    assert codex_repair["semantic_result"]["repair_result_path"] == (
        "artifacts/work/watchdog/repair-result.json"
    )
    assert codex_repair["lineage_paths"] == claude_repair["lineage_paths"]
    assert {
        "state/watchdog/watch.json",
        "state/watchdog/watchdog-result.json",
        "artifacts/work/watchdog/target-run-evidence.json",
        "artifacts/work/watchdog/repair-result.json",
        "artifacts/work/watchdog/repair-report.md",
    }.issubset(set(codex_repair["lineage_paths"]))


def test_watchdog_orc_resume_reuses_provider_and_publishes_once(tmp_path: Path) -> None:
    result = _run_watchdog_retry_resume_scenario(tmp_path / "retry-resume")

    assert result["status"] == "completed"
    assert result["provider_roles"] == ["codex", "codex"]
    assert result["attempt_ordinals"] == [1, 2]
    assert result["first_dependency_sha256"] != result["retry_dependency_sha256"]
    assert result["captured_prompt_sha256s"] == result["evidence_prompt_sha256s"]
    assert result["provider_executions_before_resume"] == 2
    assert result["provider_executions_after_resume"] == 2
    assert result["publication_count_before_resume"] == 0
    assert result["publication_count_after_resume"] == 1
    assert result["publication_count_after_replay"] == 1
    assert result["semantic_result_after_resume"] == result["semantic_result_after_replay"]


def test_watchdog_post_promotion_both_branch_smoke_is_fresh(tmp_path: Path) -> None:
    targets = json.loads((MIGRATION_INPUTS / "parity_targets.json").read_text())
    target = next(
        row
        for row in targets["targets"]
        if row["workflow_family"] == "generic_run_watchdog"
    )
    assert target["promotion_eligibility"] == {
        "eligible_for_primary_surface": True,
    }

    no_action = _run_watchdog_runtime_scenario(
        tmp_path / "no-action",
        target_status="running",
    )
    repaired = _run_watchdog_runtime_scenario(
        tmp_path / "repair",
        target_status="failed",
        repair_provider="codex",
    )

    assert no_action["outputs"]["return__repair_status"] == "NO_ACTION"
    assert no_action["provider_roles"] == []
    assert repaired["outputs"]["return__repair_status"] == "FIXED_AND_RESUMED"
    assert repaired["provider_roles"] == ["codex"]
