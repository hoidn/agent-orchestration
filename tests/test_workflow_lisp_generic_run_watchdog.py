from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml

from orchestrator.workflow.loaded_bundle import (
    workflow_output_contracts,
    workflow_public_input_contracts,
)
from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint


ROOT = Path(__file__).resolve().parents[1]
YAML_WORKFLOW = ROOT / "workflows/examples/generic_run_watchdog.yaml"
ORC_WORKFLOW = ROOT / "workflows/library/generic_run_watchdog/watchdog.orc"
PORT_DESIGN = ROOT / "docs/plans/2026-07-18-generic-run-watchdog-orc-port-design.md"
MIGRATION_INPUTS = ROOT / "workflows/examples/inputs/workflow_lisp_migrations"
ENTRY_WORKFLOW = "generic_run_watchdog/watchdog::watchdog"


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
