from __future__ import annotations

import json
import hashlib
import pytest
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
import re
from pathlib import Path


from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint


ROOT = Path(__file__).resolve().parents[1]
ORC_WORKFLOW = ROOT / "workflows/library/generic_run_watchdog/watchdog.orc"
PORT_DESIGN = ROOT / "docs/plans/2026-07-18-generic-run-watchdog-orc-port-design.md"
MIGRATION_INPUTS = ROOT / "workflows/examples/inputs/workflow_lisp_migrations"
ENTRY_WORKFLOW = "generic_run_watchdog/watchdog::watchdog"





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




















def test_historical_generic_run_watchdog_source_is_preserved_and_refused() -> None:
    assert hashlib.sha256(ORC_WORKFLOW.read_bytes()).hexdigest() == "af9e136128572b900fcb647796d54de95912b7f847c2e636b407a232515875ef"
    with pytest.raises(LispFrontendCompileError) as caught:
        compile_stage3_entrypoint(ORC_WORKFLOW)
    assert caught.value.diagnostics[0].code == "target_dsl_unsupported"


def test_watchdog_orc_prompt_dependency_retry_and_resume_contract() -> None:


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
        ("target_workspace", "String", "required"),
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
    assert "the branch passes the provider's values to the publisher" in " ".join(
        text.split()
    )
    assert "checks each one against the public enum" in " ".join(text.split())
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






def test_watchdog_historical_route_is_not_current_launch_evidence(tmp_path: Path) -> None:
    registry = json.loads(
        (ROOT / "docs/workflow_lisp_route_readiness_registry.json").read_text()
    )
    route = next(
        row
        for row in registry["surfaces"]
        if row["path"] == "workflows/library/generic_run_watchdog/watchdog.orc"
    )
    assert route["surface_kind"] == "library_workflow"
    assert route["route_label"] == "historical_negative"
    assert "readiness_label" not in route
    assert route["entry_workflow"] == ENTRY_WORKFLOW
