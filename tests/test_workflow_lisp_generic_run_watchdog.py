from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
YAML_WORKFLOW = ROOT / "workflows/examples/generic_run_watchdog.yaml"
ORC_WORKFLOW = ROOT / "workflows/library/generic_run_watchdog/watchdog.orc"
PORT_DESIGN = ROOT / "docs/plans/2026-07-18-generic-run-watchdog-orc-port-design.md"


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


def test_watchdog_port_source_is_absent_at_design_boundary() -> None:
    assert not ORC_WORKFLOW.exists(), (
        "the watchdog candidate must remain absent until the reviewed design gate closes"
    )


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
    assert "fix_complexity: FixComplexity" in text
    assert "exhaustively widens all three provider-only enums" in " ".join(
        text.split()
    )
    assert "the three provider-only enums" in " ".join(text.lower().split())
    assert "cannot return public `no_action`, `not_applicable`, or `none`" in text.lower()

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
