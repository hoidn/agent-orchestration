from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = (
    ROOT
    / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/"
    "migration_experiment_recommendation_report.md"
)

ORC_FIXTURES = (
    ROOT / "tests/fixtures/workflow_lisp/valid/neurips_plan_gate_resume.orc",
    ROOT / "tests/fixtures/workflow_lisp/valid/neurips_selected_item.orc",
    ROOT / "tests/fixtures/workflow_lisp/valid/neurips_remaining_drain.orc",
)
OUTER_ORC_WORKFLOWS = (
    (ROOT / "tests/fixtures/workflow_lisp/valid/neurips_selected_item.orc", "run-selected-item"),
    (ROOT / "tests/fixtures/workflow_lisp/valid/neurips_remaining_drain.orc", "drain"),
)
YAML_BASELINES = (
    ROOT / "workflows/library/neurips_selected_backlog_item.yaml",
    ROOT / "workflows/library/neurips_selected_backlog_item.v214.yaml",
    ROOT / "workflows/examples/neurips_steered_backlog_drain.yaml",
    ROOT / "workflows/examples/neurips_steered_backlog_drain.legacy.yaml",
)
REMAINING_YAML_DEPENDENCIES = (
    {
        "alias": "roadmap-sync",
        "workflow": "workflows/library/neurips_backlog_roadmap_sync.v214.yaml",
        "reason": "Stage 7 selected-item still relies on the YAML roadmap-sync phase surface.",
    },
    {
        "alias": "implementation-phase",
        "workflow": "workflows/library/neurips_backlog_implementation_phase.v214.yaml",
        "reason": "Stage 7 reuses the YAML implementation-phase wrapper around the translated implementation-attempt core.",
    },
    {
        "alias": "selector",
        "workflow": "workflows/library/neurips_backlog_selector.v214.yaml",
        "reason": "Stage 7 top-level drain still depends on the YAML selector role target.",
    },
    {
        "alias": "gap-drafter",
        "workflow": "workflows/library/neurips_backlog_gap_drafter.v214.yaml",
        "reason": "Stage 7 top-level drain still depends on the YAML gap-drafter role target.",
    },
)

STATUS_TOKENS = (
    "APPROVED",
    "BLOCKED",
    "CONTINUE",
    "DONE",
    "EMPTY",
    "GAP",
    "SELECTED",
    "BACKLOG_DRAFTED",
    "RECOVERED_IN_PROGRESS",
    "ACTIVE_SELECTION",
)

BEHAVIORAL_COMMANDS = (
    (
        "python",
        "-m",
        "pytest",
        "tests/test_workflow_lisp_stage7_translation.py",
        "-k",
        "neurips_plan_gate_resume or neurips_selected_item or neurips_remaining_drain or run_item_boundary",
        "-q",
    ),
    (
        "python",
        "-m",
        "pytest",
        "tests/test_workflow_lisp_phase_stdlib.py",
        "-k",
        "resume_or_start or union_start_workflow_call",
        "-q",
    ),
    (
        "python",
        "-m",
        "pytest",
        "tests/test_workflow_lisp_resource_stdlib.py",
        "-k",
        "finalize_selected_item",
        "-q",
    ),
    (
        "python",
        "-m",
        "pytest",
        "tests/test_workflow_lisp_drain_stdlib.py",
        "-k",
        "backlog_drain or run_item_contract or providers_rebinding",
        "-q",
    ),
    (
        "python",
        "-m",
        "pytest",
        "tests/test_lisp_frontend_autonomous_drain_runtime.py",
        "-k",
        "selected_item_fresh_plan or selected_item_reuses_approved_plan",
        "-q",
    ),
    (
        "python",
        "-m",
        "pytest",
        "tests/test_neurips_steered_backlog_runtime.py",
        "-k",
        "drain_continues_to_next_iteration or drain_gap_draft or drain_blocked",
        "-q",
    ),
)


@dataclass(frozen=True)
class BehavioralEvidence:
    status: str
    commands: tuple[dict[str, Any], ...]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _significant_lines(path: Path) -> list[str]:
    lines = []
    for raw_line in _read_text(path).splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith(";"):
            continue
        lines.append(raw_line)
    return lines


def _count_authored_loc(paths: tuple[Path, ...]) -> int:
    return sum(len(_significant_lines(path)) for path in paths)


def _count_regex(paths: tuple[Path, ...], pattern: str) -> int:
    regex = re.compile(pattern, re.MULTILINE)
    return sum(len(regex.findall(_read_text(path))) for path in paths)


def _count_matching_lines(paths: tuple[Path, ...], patterns: tuple[str, ...]) -> int:
    regexes = [re.compile(pattern) for pattern in patterns]
    count = 0
    for path in paths:
        for line in _significant_lines(path):
            if any(regex.search(line) for regex in regexes):
                count += 1
    return count


def _extract_workflow_loc(path: Path, workflow_name: str) -> int:
    text = _read_text(path)
    matcher = re.compile(rf"^\s*\(defworkflow\s+{re.escape(workflow_name)}\b", re.MULTILINE)
    match = matcher.search(text)
    if match is None:
        raise ValueError(f"workflow {workflow_name!r} not found in {path}")
    balance = 0
    in_string = False
    escaped = False
    end_index = None
    for index, char in enumerate(text[match.start() :], start=match.start()):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "(":
            balance += 1
        elif char == ")":
            balance -= 1
            if balance == 0:
                end_index = index + 1
                break
    if end_index is None:
        raise ValueError(f"workflow {workflow_name!r} form did not terminate in {path}")
    snippet = text[match.start() : end_index]
    return sum(
        1
        for line in snippet.splitlines()
        if line.strip() and not line.strip().startswith(";")
    )


def _count_outer_workflow_loc() -> int:
    return sum(_extract_workflow_loc(path, workflow_name) for path, workflow_name in OUTER_ORC_WORKFLOWS)


def _collect_behavioral_evidence(run_commands: bool) -> BehavioralEvidence:
    if not run_commands:
        return BehavioralEvidence(status="SKIPPED", commands=tuple())

    command_results = []
    overall_ok = True
    for command in BEHAVIORAL_COMMANDS:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        summary = stdout.splitlines()[-1] if stdout else (stderr.splitlines()[-1] if stderr else "")
        command_results.append(
            {
                "command": " ".join(command),
                "returncode": completed.returncode,
                "summary": summary,
            }
        )
        overall_ok = overall_ok and completed.returncode == 0
    return BehavioralEvidence(
        status="PASS" if overall_ok else "FAIL",
        commands=tuple(command_results),
    )


def _remaining_yaml_dependencies() -> tuple[dict[str, str], ...]:
    remaining: list[dict[str, str]] = []
    for dependency in REMAINING_YAML_DEPENDENCIES:
        workflow_path = ROOT / dependency["workflow"]
        if workflow_path.is_file():
            remaining.append(
                {
                    "alias": dependency["alias"],
                    "workflow": dependency["workflow"],
                    "reason": dependency["reason"],
                }
            )
    return tuple(remaining)


def measure_stage7_metrics(*, run_behavioral_suite: bool = True) -> dict[str, Any]:
    baseline_paths = YAML_BASELINES
    orc_paths = ORC_FIXTURES
    remaining_yaml_dependencies = _remaining_yaml_dependencies()

    metrics = {
        "authored_loc": {
            "baseline": _count_authored_loc(baseline_paths),
            "orc": _count_authored_loc(orc_paths),
        },
        "semantic_outer_workflow_loc": {
            "baseline": None,
            "orc": _count_outer_workflow_loc(),
        },
        "manual_state_path_count": {
            "baseline": _count_regex(baseline_paths, r"\$\{[^}]*state(?:_|-)root[^}]*\}/"),
            "orc": _count_regex(orc_paths, r"\$\{[^}]*state(?:_|-)root[^}]*\}/"),
        },
        "pointer_file_count": {
            "baseline": _count_regex(baseline_paths, r"\.txt\b"),
            "orc": _count_regex(orc_paths, r"\.txt\b"),
        },
        "pointer_materialization_surface_count": {
            "baseline": _count_matching_lines(
                baseline_paths,
                ("\\bpointer:", "\\bpublishes:", "\\bexpected_outputs:", "\\boutput_bundle:", "\\bvariant_output:"),
            ),
            "orc": _count_matching_lines(
                orc_paths,
                ("\\bpointer:", "\\bpublishes:", "\\bexpected_outputs:", "\\boutput_bundle:", "\\bvariant_output:"),
            ),
        },
        "candidate_path_count": {
            "baseline": _count_matching_lines(baseline_paths, ("\\bcandidates:",)),
            "orc": _count_matching_lines(orc_paths, ("\\bcandidates:",)),
        },
        "variant_boilerplate_count": {
            "baseline": _count_matching_lines(
                baseline_paths,
                (
                    r"\bright:\s*(?:APPROVED|BLOCKED|CONTINUE|DONE|SELECTED|BACKLOG_DRAFTED|MISSING)\b",
                    r"\bif .*?(?:status|decision|mode)\b",
                ),
            ),
            "orc": _count_matching_lines(
                orc_paths,
                (
                    r"\bright:\s*(?:APPROVED|BLOCKED|CONTINUE|DONE|SELECTED|BACKLOG_DRAFTED|MISSING)\b",
                    r"\bif .*?(?:status|decision|mode)\b",
                ),
            ),
        },
        "markdown_text_extractor_count": {
            "baseline": _count_matching_lines(baseline_paths, (r"\bread_text\(", r"\bextract:")),
            "orc": _count_matching_lines(orc_paths, (r"\bread_text\(", r"\bextract:")),
        },
        "glue_command_helper_surface_count": {
            "baseline": _count_matching_lines(baseline_paths, (r"\bpython\b", r"\bbash\b", r"scripts/")),
            "orc": _count_matching_lines(orc_paths, (r"\bpython\b", r"\bbash\b", r"scripts/")),
        },
        "string_status_gate_pattern_count": {
            "baseline": _count_regex(
                baseline_paths,
                r'"(?:' + "|".join(STATUS_TOKENS) + r')"',
            ),
            "orc": _count_regex(
                orc_paths,
                r'(?:"(?:' + "|".join(STATUS_TOKENS) + r')"|:(?:valid-when)\s+\((?:' + "|".join(STATUS_TOKENS) + r')\))',
            ),
        },
        "remaining_imported_yaml_dependency_count": {
            "baseline": _count_regex(baseline_paths, r"^\s+[A-Za-z0-9_-]+:\s+\S+\.ya?ml\s*$"),
            "orc": len(remaining_yaml_dependencies),
        },
    }

    behavioral = _collect_behavioral_evidence(run_behavioral_suite)
    improved_metrics = [
        name
        for name, values in metrics.items()
        if values["baseline"] is not None and values["orc"] < values["baseline"]
    ]
    regressed_metrics = [
        name
        for name, values in metrics.items()
        if values["baseline"] is not None and values["orc"] > values["baseline"]
    ]
    if behavioral.status != "PASS":
        recommendation = "stop"
    elif regressed_metrics:
        recommendation = "stop"
    elif metrics["remaining_imported_yaml_dependency_count"]["orc"] > 0:
        recommendation = "revise"
    elif len(improved_metrics) >= 6:
        recommendation = "continue"
    else:
        recommendation = "revise"

    return {
        "report_path": REPORT_PATH,
        "metrics": metrics,
        "remaining_yaml_dependencies": list(remaining_yaml_dependencies),
        "behavioral_equivalence": {
            "status": behavioral.status,
            "commands": list(behavioral.commands),
        },
        "recommendation": recommendation,
    }


def write_stage7_recommendation_report(measurement: dict[str, Any]) -> Path:
    report_path = Path(measurement["report_path"])
    metrics = measurement["metrics"]
    remaining_yaml_dependencies = measurement.get("remaining_yaml_dependencies", [])
    behavioral = measurement["behavioral_equivalence"]
    recommendation = measurement["recommendation"]

    def _result_for(metric_name: str) -> str:
        values = metrics[metric_name]
        baseline = values["baseline"]
        orc = values["orc"]
        if baseline is None:
            return "Measured"
        if orc < baseline:
            return "Pass"
        if orc == baseline:
            return "Flat"
        return "Regressed"

    table_rows = [
        ("Authored lines", "authored_loc"),
        ("Semantic outer workflow lines", "semantic_outer_workflow_loc"),
        ("Manual state-path occurrences", "manual_state_path_count"),
        ("Pointer-file occurrences", "pointer_file_count"),
        ("Pointer/materialization surface", "pointer_materialization_surface_count"),
        ("Candidate-path occurrences", "candidate_path_count"),
        ("Manual variant boilerplate", "variant_boilerplate_count"),
        ("Markdown/text extractors", "markdown_text_extractor_count"),
        ("Shell/Python glue surfaces", "glue_command_helper_surface_count"),
        ("String status/gate patterns", "string_status_gate_pattern_count"),
        ("Remaining imported YAML dependencies", "remaining_imported_yaml_dependency_count"),
    ]

    lines = [
        "# Stage 7 Migration Experiment Recommendation Report",
        "",
        "## Scope",
        "",
        "This report covers the bounded Stage 7 Workflow Lisp frontend slice for:",
        "",
        "- `tests/fixtures/workflow_lisp/valid/neurips_plan_gate_resume.orc`",
        "- `tests/fixtures/workflow_lisp/valid/neurips_selected_item.orc`",
        "- `tests/fixtures/workflow_lisp/valid/neurips_remaining_drain.orc`",
        "",
        "The YAML baselines are:",
        "",
        "- `workflows/library/neurips_selected_backlog_item.yaml`",
        "- `workflows/library/neurips_selected_backlog_item.v214.yaml`",
        "- `workflows/examples/neurips_steered_backlog_drain.yaml`",
        "- `workflows/examples/neurips_steered_backlog_drain.legacy.yaml`",
        "",
        "## Metrics",
        "",
        "| Metric | YAML baseline | `.orc` slice | Result |",
        "| --- | ---: | ---: | --- |",
    ]
    for label, metric_name in table_rows:
        values = metrics[metric_name]
        baseline = "n/a" if values["baseline"] is None else str(values["baseline"])
        lines.append(f"| {label} | {baseline} | {values['orc']} | {_result_for(metric_name)} |")
    lines.extend(
        [
            f"| Behavioral equivalence suite | n/a | {behavioral['status']} | {behavioral['status']} |",
            "",
            "## Evidence Notes",
            "",
            f"- Behavioral equivalence status: `{behavioral['status']}`.",
        ]
    )
    if behavioral["commands"]:
        lines.append("- Behavioral evidence commands:")
        for command in behavioral["commands"]:
            lines.append(
                f"  - `{command['command']}` -> exit `{command['returncode']}`; `{command['summary']}`"
            )
    else:
        lines.append("- Behavioral evidence commands were skipped for this measurement run.")
    lines.append("- Remaining imported YAML migration debt:")
    if remaining_yaml_dependencies:
        for dependency in remaining_yaml_dependencies:
            lines.append(
                f"  - `{dependency['alias']}` -> `{dependency['workflow']}`. {dependency['reason']}"
            )
    else:
        lines.append("  - none in the translated Stage 7 surface")
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"`{recommendation}`",
            "",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
