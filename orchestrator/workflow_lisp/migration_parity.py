"""Workflow Lisp migration parity reports and derived views."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


TARGETS_SCHEMA_VERSION = "workflow_lisp_migration_parity_targets.v1"
REPORT_SCHEMA_VERSION = "workflow_lisp_migration_parity_report.v2"
INDEX_SCHEMA_VERSION = "workflow_lisp_migration_parity_index.v2"
GATE_EVALUATION_SCHEMA_VERSION = "workflow_lisp_migration_parity_gate_evaluation.v1"
TOOL_VERSION = "workflow_lisp_migration_parity.v2"
COMMAND_ROLES = (
    "compile",
    "dry_run",
    "smoke_or_integration",
    "output_contract_parity",
    "terminal_state_parity",
    "artifact_parity",
    "resume_parity",
)
REQUIRED_EVIDENCE_ROLES = (
    "compile",
    "shared_validation",
    "dry_run",
    "smoke_or_integration",
    "baseline_characterization",
    "output_contract_parity",
    "terminal_state_parity",
    "artifact_parity",
    "resume_parity",
)
BASELINE_FIELDS = ("inputs", "outputs", "terminal_states", "artifacts", "resume_behavior")
PASSING_ARTIFACT_STATUSES = {"emitted", "validated", "pass"}
GATE_OWNED_REPORT_FIELDS = frozenset({"primary_surface", "report_valid", "evidence_complete"})
REQUIRED_REPORT_STRING_FIELDS = (
    "workflow_family",
    "candidate",
    "yaml_primary",
    "tool_version",
    "dsl_version",
    "generated_at",
    "report_path",
)
REQUIRED_REPORT_MAPPING_FIELDS = (
    "target_identity",
    "evidence_freshness",
    "command_logs",
    "promotion_eligibility",
    "compile_artifacts",
    "evidence",
)
REQUIRED_REPORT_OBJECT_LIST_FIELDS = ("accepted_differences", "deprecated_yaml_mechanics")


@dataclass(frozen=True)
class EvidenceCommand:
    argv: tuple[str, ...] | None
    waiver: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ParityTarget:
    target_manifest_path: Path
    target_manifest_sha256: str
    target_index: int
    workflow_family: str
    candidate: str
    yaml_primary: str
    entry_workflow: str
    provider_externs_file: str | None
    prompt_externs_file: str | None
    command_boundaries_file: str | None
    imported_workflow_bundles_file: str | None
    baseline_characterization: Mapping[str, list[str]]
    accepted_differences: tuple[Mapping[str, Any], ...]
    deprecated_yaml_mechanics: tuple[Mapping[str, Any], ...]
    promotion_eligibility: Mapping[str, Any]
    compile_artifacts: Mapping[str, tuple[str, ...]]
    evidence_commands: Mapping[str, EvidenceCommand]


@dataclass(frozen=True)
class CommandOutcome:
    status: str
    argv: tuple[str, ...] | None
    exit_code: int | None
    elapsed_seconds: float
    stdout: str
    stderr: str
    waiver: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ValidatedGateRow:
    workflow_family: str
    report: Mapping[str, Any]
    report_valid: bool
    evidence_complete: bool
    non_regressive: bool
    eligible_for_primary_surface: bool
    primary_surface: str
    reasons: tuple[str, ...]
    target_identity: Mapping[str, Any]


def load_parity_targets(path: Path) -> list[ParityTarget]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != TARGETS_SCHEMA_VERSION:
        raise ValueError(f"expected schema_version {TARGETS_SCHEMA_VERSION}")
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("targets must be a non-empty array")

    manifest_sha256 = _sha256_file(path.resolve())
    targets: list[ParityTarget] = []
    seen_families: set[str] = set()
    for index, raw_target in enumerate(raw_targets):
        if not isinstance(raw_target, Mapping):
            raise ValueError(f"target at index {index} must be an object")
        if "non_regressive" in raw_target:
            raise ValueError("manifest may not author non_regressive")

        workflow_family = _require_string(raw_target, "workflow_family")
        if workflow_family in seen_families:
            raise ValueError(f"duplicate workflow_family `{workflow_family}`")
        seen_families.add(workflow_family)

        baseline = _require_mapping(raw_target, "baseline_characterization")
        normalized_baseline = {
            field_name: _require_non_empty_string_list(baseline, field_name)
            for field_name in BASELINE_FIELDS
        }
        promotion_eligibility = _require_mapping(raw_target, "promotion_eligibility")
        eligible = promotion_eligibility.get("eligible_for_primary_surface")
        if not isinstance(eligible, bool):
            raise ValueError(
                f"promotion_eligibility.eligible_for_primary_surface must be a boolean for `{workflow_family}`"
            )
        if not eligible and not _string_or_none(promotion_eligibility.get("blocked_reason")):
            raise ValueError(
                f"promotion_eligibility.blocked_reason is required for ineligible `{workflow_family}`"
            )

        compile_artifacts = _require_mapping(raw_target, "compile_artifacts")
        normalized_compile_artifacts = {
            "required": tuple(_require_non_empty_string_list(compile_artifacts, "required")),
            "optional": tuple(_require_string_list(compile_artifacts, "optional")),
        }
        evidence_commands = _require_mapping(raw_target, "evidence_commands")
        normalized_commands = {
            role: _parse_command_spec(
                workflow_family=workflow_family,
                role=role,
                raw_value=evidence_commands.get(role),
            )
            for role in COMMAND_ROLES
        }

        targets.append(
            ParityTarget(
                target_manifest_path=path.resolve(),
                target_manifest_sha256=manifest_sha256,
                target_index=index,
                workflow_family=workflow_family,
                candidate=_require_string(raw_target, "candidate"),
                yaml_primary=_require_string(raw_target, "yaml_primary"),
                entry_workflow=_require_string(raw_target, "entry_workflow"),
                provider_externs_file=_optional_string(raw_target, "provider_externs_file"),
                prompt_externs_file=_optional_string(raw_target, "prompt_externs_file"),
                command_boundaries_file=_optional_string(raw_target, "command_boundaries_file"),
                imported_workflow_bundles_file=_optional_string(raw_target, "imported_workflow_bundles_file"),
                baseline_characterization=normalized_baseline,
                accepted_differences=tuple(_require_object_list(raw_target, "accepted_differences")),
                deprecated_yaml_mechanics=tuple(_require_object_list(raw_target, "deprecated_yaml_mechanics")),
                promotion_eligibility=promotion_eligibility,
                compile_artifacts=normalized_compile_artifacts,
                evidence_commands=normalized_commands,
            )
        )

    return targets


def run_parity_target(
    target: ParityTarget,
    *,
    output_root: Path,
    repo_root: Path,
    today: date | None = None,
    generated_by: Sequence[str] | None = None,
) -> dict[str, object]:
    resolved_output_root = output_root.resolve()
    resolved_output_root.mkdir(parents=True, exist_ok=True)
    logs_root = resolved_output_root / "logs" / target.workflow_family
    logs_root.mkdir(parents=True, exist_ok=True)

    evidence: dict[str, object] = {}
    command_logs: dict[str, object] = {}
    compile_payload: Mapping[str, Any] | None = None
    build_manifest: Mapping[str, Any] | None = None

    for role in COMMAND_ROLES:
        stdout_log = logs_root / f"{role}.stdout.log"
        stderr_log = logs_root / f"{role}.stderr.log"
        outcome = _run_command(
            target.evidence_commands[role],
            role=role,
            repo_root=repo_root,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
        )
        command_logs[role] = {
            "stdout": _relative_path(stdout_log, repo_root),
            "stderr": _relative_path(stderr_log, repo_root),
        }
        evidence_record: dict[str, object] = {
            "status": outcome.status,
        }
        if outcome.argv is not None:
            evidence_record["argv"] = list(outcome.argv)
        if outcome.exit_code is not None:
            evidence_record["exit_code"] = outcome.exit_code
        evidence_record["elapsed_seconds"] = round(outcome.elapsed_seconds, 3)
        if outcome.waiver is not None:
            evidence_record["waiver"] = dict(outcome.waiver)
        evidence[role] = evidence_record
        if role == "compile" and outcome.status == "pass":
            compile_payload, build_manifest = _load_compile_outputs(outcome.stdout, repo_root)
            if compile_payload is not None:
                evidence_record["build_root"] = _relative_or_absolute_path(
                    Path(str(compile_payload["build_root"])),
                    repo_root,
                )
                evidence_record["manifest_path"] = _relative_or_absolute_path(
                    Path(str(compile_payload["build_root"])) / "manifest.json",
                    repo_root,
                )

    evidence["shared_validation"] = _shared_validation_evidence(build_manifest)
    evidence["baseline_characterization"] = {
        "status": "pass",
        **{field_name: list(values) for field_name, values in target.baseline_characterization.items()},
    }

    compile_artifacts = _compile_artifact_report(
        target=target,
        build_manifest=build_manifest,
        build_root=Path(str(compile_payload["build_root"])) if compile_payload and isinstance(compile_payload.get("build_root"), str) else None,
        repo_root=repo_root,
    )
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    target_identity = _build_target_identity(target, repo_root=repo_root)
    evidence_freshness = _build_evidence_freshness(
        generated_at=generated_at,
        compile_artifacts=compile_artifacts,
        command_logs=command_logs,
        compile_payload=compile_payload,
        build_manifest=build_manifest,
        repo_root=repo_root,
    )
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "workflow_family": target.workflow_family,
        "candidate": target.candidate,
        "yaml_primary": target.yaml_primary,
        "tool_version": TOOL_VERSION,
        "dsl_version": "2.14",
        "generated_at": generated_at,
        "generated_by": list(generated_by or ("python", "-m", "orchestrator", "migration-parity")),
        "report_path": _relative_path(resolved_output_root / f"{target.workflow_family}.json", repo_root),
        "target_identity": target_identity,
        "evidence_freshness": evidence_freshness,
        "command_logs": command_logs,
        "accepted_differences": [dict(entry) for entry in target.accepted_differences],
        "deprecated_yaml_mechanics": [dict(entry) for entry in target.deprecated_yaml_mechanics],
        "promotion_eligibility": dict(target.promotion_eligibility),
        "compile_artifacts": compile_artifacts,
        "evidence": evidence,
    }
    workflow_boundary = _load_selected_workflow_boundary_projection(
        target=target,
        build_manifest=build_manifest,
        build_root=Path(str(compile_payload["build_root"])) if compile_payload and isinstance(compile_payload.get("build_root"), str) else None,
        repo_root=repo_root,
    )
    if workflow_boundary is not None:
        report["workflow_boundary_projection"] = workflow_boundary
    report["non_regressive"] = compute_non_regressive(report, today=today or date.today())
    return report


def compute_non_regressive(report: Mapping[str, Any], *, today: date) -> bool:
    evidence = _require_report_mapping(report, "evidence")
    for role in REQUIRED_EVIDENCE_ROLES:
        if role not in evidence:
            return False

    if _status(evidence["compile"]) != "pass":
        return False
    if _status(evidence["shared_validation"]) != "pass":
        return False
    if _status(evidence["dry_run"]) != "pass":
        return False

    smoke = _require_report_mapping(evidence, "smoke_or_integration")
    smoke_status = _status(smoke)
    if smoke_status == "waived":
        if not _waiver_is_valid(smoke.get("waiver"), today=today, require_targeted_evidence=True):
            return False
    elif smoke_status != "pass":
        return False

    baseline = _require_report_mapping(evidence, "baseline_characterization")
    for field_name in BASELINE_FIELDS:
        values = baseline.get(field_name)
        if not isinstance(values, list) or not values:
            return False

    for role in ("output_contract_parity", "terminal_state_parity", "artifact_parity", "resume_parity"):
        if _status(evidence[role]) != "pass":
            return False

    compile_artifacts = _require_report_mapping(report, "compile_artifacts")
    required_artifacts = _require_report_mapping(compile_artifacts, "required")
    for artifact in required_artifacts.values():
        if _status(artifact) != "pass":
            return False

    for mechanic in _require_report_object_list(report, "deprecated_yaml_mechanics"):
        if _string_or_none(mechanic.get("replacement")):
            continue
        if _waiver_is_valid(mechanic.get("waiver"), today=today, require_targeted_evidence=False):
            continue
        return False

    return True


def render_parity_markdown(report: Mapping[str, Any]) -> str:
    primary_surface = _primary_surface_for_report(report)
    promotion = _require_report_mapping(report, "promotion_eligibility")
    evidence = _require_report_mapping(report, "evidence")
    compile_artifacts = _require_report_mapping(report, "compile_artifacts")
    baseline = _require_report_mapping(evidence, "baseline_characterization")

    lines = [
        f"# Parity Report: {report['workflow_family']}",
        "",
        f"- Candidate: `{report['candidate']}`",
        f"- YAML primary: `{report['yaml_primary']}`",
        f"- Generated at: `{report['generated_at']}`",
        f"- Non-regressive: `{str(bool(report['non_regressive'])).lower()}`",
        f"- Promotion eligible: `{str(bool(promotion['eligible_for_primary_surface'])).lower()}`",
        f"- Primary surface: `{primary_surface}`",
        "",
        "## Baseline Characterization",
        f"- Inputs: {', '.join(f'`{value}`' for value in baseline['inputs'])}",
        f"- Outputs: {', '.join(f'`{value}`' for value in baseline['outputs'])}",
        f"- Terminal states: {', '.join(f'`{value}`' for value in baseline['terminal_states'])}",
        f"- Artifacts: {', '.join(f'`{value}`' for value in baseline['artifacts'])}",
        f"- Resume behavior: {', '.join(f'`{value}`' for value in baseline['resume_behavior'])}",
        "",
        "## Evidence",
    ]
    for role in REQUIRED_EVIDENCE_ROLES:
        role_evidence = _require_report_mapping(evidence, role)
        lines.append(f"- `{role}`: `{_status(role_evidence)}`")

    lines.extend(
        [
            "",
            "## Compile Artifacts",
        ]
    )
    for bucket in ("required", "optional"):
        bucket_items = _require_report_mapping(compile_artifacts, bucket)
        for artifact_name, artifact_data in sorted(bucket_items.items()):
            artifact_mapping = _require_report_mapping(bucket_items, artifact_name)
            artifact_path = artifact_mapping.get("path")
            artifact_suffix = f" (`{artifact_path}`)" if artifact_path else ""
            lines.append(f"- `{bucket}.{artifact_name}`: `{_status(artifact_mapping)}`{artifact_suffix}")

    lines.extend(
        [
            "",
            "## Deprecated YAML Mechanics",
        ]
    )
    mechanics = _require_report_object_list(report, "deprecated_yaml_mechanics")
    if not mechanics:
        lines.append("- None")
    else:
        for mechanic in mechanics:
            mechanic_name = mechanic.get("mechanic", "unknown")
            replacement = _string_or_none(mechanic.get("replacement"))
            waiver = mechanic.get("waiver")
            if replacement:
                lines.append(f"- `{mechanic_name}` -> `{replacement}`")
            elif isinstance(waiver, Mapping):
                lines.append(
                    f"- `{mechanic_name}` waived by `{waiver.get('owner', 'unknown')}` until `{waiver.get('expiry', 'unknown')}`"
                )
            else:
                lines.append(f"- `{mechanic_name}` unresolved")

    return "\n".join(lines) + "\n"


def render_parity_index(
    reports: Sequence[ValidatedGateRow],
) -> dict[str, object]:
    rows = []
    for gate_row in reports:
        if not isinstance(gate_row, ValidatedGateRow):
            raise TypeError("render_parity_index expects ValidatedGateRow inputs")
        report = gate_row.report
        report_path = Path(str(report["report_path"]))
        rows.append(
            {
                "workflow_family": report["workflow_family"],
                "candidate": report["candidate"],
                "yaml_primary": report["yaml_primary"],
                "json_report": str(report_path),
                "markdown_report": str(report_path.with_suffix(".md")),
                "report_valid": gate_row.report_valid,
                "evidence_complete": gate_row.evidence_complete,
                "non_regressive": gate_row.non_regressive,
                "promotion_eligibility": dict(_require_report_mapping(report, "promotion_eligibility")),
                "primary_surface": gate_row.primary_surface,
            }
        )
    rows.sort(key=lambda row: str(row["workflow_family"]))
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "targets": rows,
    }


def _validate_report_for_gate(
    report: Mapping[str, Any],
    *,
    target: ParityTarget,
    targets_file: Path,
    repo_root: Path,
    today: date,
    fail_closed_for_stale_evidence: bool = False,
) -> ValidatedGateRow:
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ValueError(f"report schema_version must be {REPORT_SCHEMA_VERSION}")

    gate_owned_fields = sorted(GATE_OWNED_REPORT_FIELDS.intersection(report.keys()))
    if gate_owned_fields:
        raise ValueError(
            "report may not publish gate-owned fields: " + ", ".join(gate_owned_fields)
        )

    _require_report_contract(report)

    target_identity = _require_report_mapping(report, "target_identity")
    expected_identity = _build_target_identity(
        target,
        repo_root=repo_root,
        targets_file=targets_file,
    )
    _require_exact_mapping_match(
        target_identity,
        expected_identity,
        label="target_identity",
    )

    expected_non_regressive = compute_non_regressive(report, today=today)
    if bool(report.get("non_regressive")) != expected_non_regressive:
        raise ValueError("report non_regressive does not match recomputed non_regressive")

    evidence_complete, reasons = _validate_required_evidence_completeness(report)
    evidence_freshness = _require_report_mapping(report, "evidence_freshness")
    freshness_complete, freshness_reasons = _validate_evidence_freshness(
        report,
        evidence_freshness=evidence_freshness,
        repo_root=repo_root,
        fail_closed=fail_closed_for_stale_evidence,
    )
    evidence_complete = evidence_complete and freshness_complete
    reasons.extend(freshness_reasons)
    promotion = _require_report_mapping(report, "promotion_eligibility")
    eligible_for_primary_surface = bool(promotion.get("eligible_for_primary_surface"))
    if not expected_non_regressive:
        reasons.append("non_regressive=false")
    if not eligible_for_primary_surface:
        reasons.append(
            _string_or_none(promotion.get("blocked_reason")) or "eligible_for_primary_surface=false"
        )
    primary_surface = _primary_surface_for_non_regressive_and_eligibility(
        non_regressive=expected_non_regressive,
        eligible_for_primary_surface=eligible_for_primary_surface,
    )
    return ValidatedGateRow(
        workflow_family=str(report["workflow_family"]),
        report=report,
        report_valid=True,
        evidence_complete=evidence_complete,
        non_regressive=expected_non_regressive,
        eligible_for_primary_surface=eligible_for_primary_surface,
        primary_surface=primary_surface,
        reasons=tuple(reasons),
        target_identity=target_identity,
    )


def render_gate_evaluation(
    *,
    gate_rows: Sequence[ValidatedGateRow],
    gate_mode: str,
    targets_file: Path,
    selected_targets: Sequence[str],
    repo_root: Path,
) -> dict[str, object]:
    ordered_rows = sorted(gate_rows, key=lambda row: row.workflow_family)
    selected_set = set(selected_targets)
    gated_rows = [
        row for row in ordered_rows if not selected_set or row.workflow_family in selected_set
    ]
    results = [
        {
            "workflow_family": row.workflow_family,
            "report_path": str(row.report["report_path"]),
            "target_identity": dict(row.target_identity),
            "report_valid": row.report_valid,
            "evidence_complete": row.evidence_complete,
            "non_regressive": row.non_regressive,
            "eligible_for_primary_surface": row.eligible_for_primary_surface,
            "primary_surface": _gate_primary_surface_for_row(row),
            "reasons": list(row.reasons),
        }
        for row in ordered_rows
    ]
    selected_identity_rows = [
        dict(row.target_identity)
        for row in ordered_rows
        if row.workflow_family in set(selected_targets)
    ]
    return {
        "schema_version": GATE_EVALUATION_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "gate_mode": gate_mode,
        "targets_file": _relative_or_absolute_path(targets_file, repo_root),
        "selected_targets": list(selected_targets),
        "selected_target_identities": selected_identity_rows,
        "results": results,
        "overall_pass": all(_gate_row_passes(row, gate_mode=gate_mode) for row in gated_rows),
    }


def write_reports(
    reports: Sequence[Mapping[str, Any]],
    *,
    output_root: Path,
    repo_root: Path,
    gate_rows: Sequence[ValidatedGateRow],
    gate_evaluation: Mapping[str, Any],
) -> tuple[Path, Path]:
    resolved_output_root = output_root.resolve()
    resolved_output_root.mkdir(parents=True, exist_ok=True)
    for report in reports:
        report_path = repo_root / str(report["report_path"])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        markdown_path = report_path.with_suffix(".md")
        markdown_path.write_text(render_parity_markdown(report), encoding="utf-8")

    index_path = resolved_output_root / "index.json"
    index_path.write_text(
        json.dumps(render_parity_index(gate_rows), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    gate_evaluation_path = resolved_output_root / "gate_evaluation.json"
    gate_evaluation_path.write_text(
        json.dumps(gate_evaluation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return index_path, gate_evaluation_path


def run_migration_parity(
    *,
    targets_file: Path,
    output_root: Path,
    selected_targets: Sequence[str] | None = None,
    repo_root: Path,
    today: date | None = None,
    generated_by: Sequence[str] | None = None,
    gate_mode: str = "advisory",
) -> dict[str, object]:
    evaluation_date = today or date.today()
    all_targets = load_parity_targets(targets_file)
    selected_target_names = (
        list(selected_targets)
        if selected_targets
        else [target.workflow_family for target in all_targets]
    )
    targets = list(all_targets)
    if selected_targets:
        selected = set(selected_targets)
        missing = sorted(selected.difference(target.workflow_family for target in all_targets))
        if missing:
            raise ValueError(f"unknown workflow_family selection(s): {', '.join(missing)}")
        targets = [target for target in targets if target.workflow_family in selected]

    reports = [
        run_parity_target(
            target,
            output_root=output_root,
            repo_root=repo_root,
            today=evaluation_date,
            generated_by=generated_by,
        )
        for target in targets
    ]
    gate_rows = _validated_gate_rows_for_targets(
        all_targets,
        refreshed_reports=reports,
        output_root=output_root,
        targets_file=targets_file,
        repo_root=repo_root,
        today=evaluation_date,
    )
    gate_evaluation = render_gate_evaluation(
        gate_rows=gate_rows,
        gate_mode=gate_mode,
        targets_file=targets_file,
        selected_targets=selected_target_names,
        repo_root=repo_root,
    )
    index_path, gate_evaluation_path = write_reports(
        reports,
        output_root=output_root,
        repo_root=repo_root,
        gate_rows=gate_rows,
        gate_evaluation=gate_evaluation,
    )
    non_regressive_targets = sorted(
        report["workflow_family"] for report in reports if bool(report["non_regressive"])
    )
    regressive_targets = sorted(
        report["workflow_family"] for report in reports if not bool(report["non_regressive"])
    )
    return {
        "targets_processed": len(reports),
        "reports_written": len(reports),
        "non_regressive_targets": non_regressive_targets,
        "regressive_targets": regressive_targets,
        "gate_mode": gate_mode,
        "overall_pass": bool(gate_evaluation["overall_pass"]),
        "index_path": _relative_path(index_path, repo_root),
        "gate_evaluation_path": _relative_path(gate_evaluation_path, repo_root),
    }


def _validated_gate_rows_for_targets(
    targets: Sequence[ParityTarget],
    *,
    refreshed_reports: Sequence[Mapping[str, Any]],
    output_root: Path,
    targets_file: Path,
    repo_root: Path,
    today: date,
) -> list[ValidatedGateRow]:
    refreshed_by_family = {
        str(report["workflow_family"]): report for report in refreshed_reports
    }
    gate_rows: list[ValidatedGateRow] = []
    for target in targets:
        report = refreshed_by_family.get(target.workflow_family)
        if report is None:
            report = _load_existing_report(
                output_root / f"{target.workflow_family}.json",
                workflow_family=target.workflow_family,
            )
        gate_rows.append(
            _validate_report_for_gate(
                report,
                target=target,
                targets_file=targets_file,
                repo_root=repo_root,
                today=today,
                fail_closed_for_stale_evidence=target.workflow_family not in refreshed_by_family,
            )
        )
    return gate_rows


def _load_existing_report(path: Path, *, workflow_family: str) -> Mapping[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(
            "cannot refresh aggregate parity index without an existing report for "
            f"unselected workflow_family `{workflow_family}` at `{path}`"
        ) from exc

    if not isinstance(report, Mapping):
        raise ValueError(f"existing report for `{workflow_family}` at `{path}` must be a JSON object")
    if report.get("workflow_family") != workflow_family:
        raise ValueError(
            f"existing report at `{path}` does not match workflow_family `{workflow_family}`"
        )
    return report


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _sha256_json_bytes(payload: Any) -> str:
    return f"sha256:{hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()}"


def _build_target_identity(
    target: ParityTarget,
    *,
    repo_root: Path,
    targets_file: Path | None = None,
) -> dict[str, object]:
    candidate_path = repo_root / target.candidate
    return {
        "targets_schema_version": TARGETS_SCHEMA_VERSION,
        "target_manifest_path": _relative_or_absolute_path((targets_file or target.target_manifest_path), repo_root),
        "target_manifest_sha256": target.target_manifest_sha256,
        "target_index": target.target_index,
        "workflow_family": target.workflow_family,
        "candidate_path": target.candidate,
        "candidate_sha256": _sha256_file(candidate_path),
        "yaml_primary_path": target.yaml_primary,
        "entry_workflow": target.entry_workflow,
    }


def _build_required_artifact_freshness(
    compile_artifacts: Mapping[str, Any],
    *,
    repo_root: Path,
) -> dict[str, object]:
    required = _require_report_mapping(compile_artifacts, "required")
    freshness: dict[str, object] = {}
    for artifact_name, artifact_value in required.items():
        artifact = _require_report_mapping(required, artifact_name)
        artifact_path = _string_or_none(artifact.get("path"))
        artifact_entry: dict[str, object] = {
            "status": _status(artifact),
            "path": artifact_path,
        }
        if artifact_path:
            resolved_path = repo_root / artifact_path
            if resolved_path.exists():
                artifact_entry["sha256"] = _sha256_file(resolved_path)
        freshness[artifact_name] = artifact_entry
    return freshness


def _build_evidence_refs(
    command_logs: Mapping[str, Any],
    *,
    repo_root: Path,
) -> dict[str, object]:
    refs: dict[str, object] = {}
    for role, raw_paths in command_logs.items():
        paths = _require_report_mapping(command_logs, str(role))
        role_refs: dict[str, object] = {}
        for stream in ("stdout", "stderr"):
            stream_path = _string_or_none(paths.get(stream))
            if not stream_path:
                continue
            resolved_path = repo_root / stream_path
            role_refs[stream] = {
                "path": stream_path,
                "sha256": _sha256_file(resolved_path) if resolved_path.exists() else None,
            }
        refs[str(role)] = role_refs
    return refs


def _build_evidence_freshness(
    *,
    generated_at: str,
    compile_artifacts: Mapping[str, Any],
    command_logs: Mapping[str, Any],
    compile_payload: Mapping[str, Any] | None,
    build_manifest: Mapping[str, Any] | None,
    repo_root: Path,
) -> dict[str, object]:
    freshness: dict[str, object] = {
        "generated_at": generated_at,
        "required_artifacts": _build_required_artifact_freshness(
            compile_artifacts,
            repo_root=repo_root,
        ),
        "evidence_refs": _build_evidence_refs(command_logs, repo_root=repo_root),
    }
    compile_manifest_path = None
    if isinstance(compile_payload, Mapping) and isinstance(compile_payload.get("build_root"), str):
        compile_manifest_path = Path(str(compile_payload["build_root"])) / "manifest.json"
    if compile_manifest_path is not None and compile_manifest_path.exists():
        freshness["compile_manifest_path"] = _relative_or_absolute_path(
            compile_manifest_path,
            repo_root,
        )
        freshness["compile_manifest_sha256"] = _sha256_file(compile_manifest_path)
    checksum = None
    if isinstance(build_manifest, Mapping):
        checksum = _string_or_none(build_manifest.get("compiled_workflow_checksum"))
    if checksum:
        freshness["compiled_workflow_checksum"] = checksum
    return freshness


def _load_selected_workflow_boundary_projection(
    *,
    target: ParityTarget,
    build_manifest: Mapping[str, Any] | None,
    build_root: Path | None,
    repo_root: Path,
) -> dict[str, object] | None:
    if build_manifest is None:
        return None
    artifact_paths = dict(build_manifest.get("artifact_paths", {}))
    boundary_path = _resolve_build_artifact_path(
        artifact_paths.get("workflow_boundary_projection"),
        build_root=build_root,
        repo_root=repo_root,
    )
    if boundary_path is None or not boundary_path.exists():
        return None
    try:
        payload = json.loads(boundary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    workflows = payload.get("workflows")
    if not isinstance(workflows, list):
        return None
    selected = next(
        (
            item
            for item in workflows
            if isinstance(item, Mapping)
            and (
                item.get("display_name") == target.entry_workflow
                or item.get("workflow_name") == target.entry_workflow
                or str(item.get("workflow_name", "")).endswith(f"::{target.entry_workflow}")
            )
        ),
        None,
    )
    if not isinstance(selected, Mapping):
        return None
    boundary = selected.get("boundary")
    if not isinstance(boundary, Mapping):
        return None
    return {
        "workflow_name": str(selected.get("workflow_name")),
        "display_name": str(selected.get("display_name")),
        "public_input_names": sorted(
            name
            for name in boundary.get("public_input_names", ())
            if isinstance(name, str)
        ),
        "private_runtime_context_bindings": [
            {
                key: value
                for key, value in binding.items()
                if key
                in {
                    "binding_id",
                    "source_param_name",
                    "context_family",
                    "bridge_class",
                    "derived_phase_identity",
                    "generated_input_names",
                }
            }
            for binding in boundary.get("private_runtime_context_bindings", ())
            if isinstance(binding, Mapping)
        ],
        "private_managed_write_root_inputs": sorted(
            name
            for name in boundary.get("private_managed_write_root_inputs", ())
            if isinstance(name, str)
        ),
        "private_compatibility_bridge_inputs": sorted(
            name
            for name in boundary.get("private_compatibility_bridge_inputs", ())
            if isinstance(name, str)
        ),
    }


def _validate_evidence_freshness(
    report: Mapping[str, Any],
    *,
    evidence_freshness: Mapping[str, Any],
    repo_root: Path,
    fail_closed: bool = False,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    evidence_complete = True

    def mark_incomplete(message: str) -> None:
        nonlocal evidence_complete
        if fail_closed:
            raise ValueError(message)
        evidence_complete = False
        reasons.append(message)

    compile_evidence = _require_report_mapping(_require_report_mapping(report, "evidence"), "compile")
    compile_manifest_path = _string_or_none(compile_evidence.get("manifest_path")) or _string_or_none(
        evidence_freshness.get("compile_manifest_path")
    )
    if compile_manifest_path:
        if evidence_freshness.get("compile_manifest_path") != compile_manifest_path:
            raise ValueError("evidence_freshness.compile_manifest_path does not match current compile manifest path")
        compile_manifest_file = repo_root / compile_manifest_path
        if not compile_manifest_file.exists():
            mark_incomplete("missing compile manifest")
        else:
            expected_sha = _string_or_none(evidence_freshness.get("compile_manifest_sha256"))
            if not expected_sha:
                mark_incomplete("missing compile_manifest_sha256")
            elif expected_sha != _sha256_file(compile_manifest_file):
                raise ValueError("evidence_freshness.compile_manifest_sha256 does not match current compile manifest")
            compile_manifest = json.loads(compile_manifest_file.read_text(encoding="utf-8"))
            current_checksum = _string_or_none(compile_manifest.get("compiled_workflow_checksum"))
            if current_checksum:
                reported_checksum = _string_or_none(evidence_freshness.get("compiled_workflow_checksum"))
                if not reported_checksum:
                    mark_incomplete("missing compiled_workflow_checksum")
                elif reported_checksum != current_checksum:
                    raise ValueError("evidence_freshness.compiled_workflow_checksum does not match current compile evidence")

    required_artifacts = _require_report_mapping(evidence_freshness, "required_artifacts")
    current_required_artifacts = _require_report_mapping(_require_report_mapping(report, "compile_artifacts"), "required")
    for artifact_name, artifact_value in current_required_artifacts.items():
        artifact = _require_report_mapping(current_required_artifacts, artifact_name)
        current_path = _string_or_none(artifact.get("path"))
        current_status = _status(artifact)
        freshness_artifact = required_artifacts.get(artifact_name)
        if not isinstance(freshness_artifact, Mapping):
            mark_incomplete(f"missing freshness row for required artifact `{artifact_name}`")
            continue
        if freshness_artifact.get("path") != current_path:
            raise ValueError(f"required_artifacts.{artifact_name}.path does not match current required artifact path")
        if freshness_artifact.get("status") != current_status:
            raise ValueError(f"required_artifacts.{artifact_name}.status does not match current required artifact status")
        if current_path:
            current_file = repo_root / current_path
            if not current_file.exists():
                mark_incomplete(f"missing required artifact file `{artifact_name}`")
                continue
            expected_sha = _string_or_none(freshness_artifact.get("sha256"))
            if not expected_sha:
                mark_incomplete(f"missing required artifact digest `{artifact_name}`")
            elif expected_sha != _sha256_file(current_file):
                raise ValueError(f"required_artifacts.{artifact_name}.sha256 does not match current artifact")

    evidence_refs = _require_report_mapping(evidence_freshness, "evidence_refs")
    current_command_logs = _require_report_mapping(report, "command_logs")
    for role, raw_paths in current_command_logs.items():
        paths = _require_report_mapping(current_command_logs, str(role))
        freshness_role = evidence_refs.get(role)
        if not isinstance(freshness_role, Mapping):
            mark_incomplete(f"missing evidence freshness refs for `{role}`")
            continue
        for stream in ("stdout", "stderr"):
            current_path = _string_or_none(paths.get(stream))
            if not current_path:
                mark_incomplete(f"missing {stream} log path for `{role}`")
                continue
            current_file = repo_root / current_path
            stream_ref = freshness_role.get(stream)
            if not isinstance(stream_ref, Mapping):
                mark_incomplete(f"missing freshness ref for `{role}` {stream}")
                continue
            if stream_ref.get("path") != current_path:
                raise ValueError(f"evidence_refs.{role}.{stream}.path does not match current log path")
            if not current_file.exists():
                mark_incomplete(f"missing {stream} log for `{role}`")
                continue
            expected_sha = _string_or_none(stream_ref.get("sha256"))
            if not expected_sha:
                mark_incomplete(f"missing {stream} log digest for `{role}`")
            elif expected_sha != _sha256_file(current_file):
                raise ValueError(f"evidence_refs.{role}.{stream}.sha256 does not match current log")

    return evidence_complete, reasons


def _validate_required_evidence_completeness(
    report: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    evidence_complete = True

    def mark_incomplete(message: str) -> None:
        nonlocal evidence_complete
        evidence_complete = False
        reasons.append(message)

    evidence = _require_report_mapping(report, "evidence")
    for role in REQUIRED_EVIDENCE_ROLES:
        if role not in evidence:
            mark_incomplete(f"missing required evidence role `{role}`")

    compile_artifacts = _require_report_mapping(report, "compile_artifacts")
    required_artifacts = _require_report_mapping(compile_artifacts, "required")
    for artifact_name, artifact_value in required_artifacts.items():
        artifact = _require_report_mapping(required_artifacts, artifact_name)
        if _status(artifact) != "pass":
            mark_incomplete(f"required compile artifact `{artifact_name}` is not passing")

    return evidence_complete, reasons


def _require_exact_mapping_match(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    label: str,
) -> None:
    actual_keys = set(actual.keys())
    expected_keys = set(expected.keys())
    extra_keys = sorted(actual_keys - expected_keys)
    if extra_keys:
        raise ValueError(f"{label} contains unexpected keys: {', '.join(extra_keys)}")
    missing_keys = sorted(expected_keys - actual_keys)
    if missing_keys:
        raise ValueError(f"{label} is missing keys: {', '.join(missing_keys)}")
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if actual_value != expected_value:
            raise ValueError(f"{label}.{key} does not match current selected target")


def _require_report_contract(report: Mapping[str, Any]) -> None:
    for field_name in REQUIRED_REPORT_STRING_FIELDS:
        _require_string(report, field_name)
    _require_non_empty_string_list(report, "generated_by")
    for field_name in REQUIRED_REPORT_OBJECT_LIST_FIELDS:
        _require_report_object_list(report, field_name)
    for field_name in REQUIRED_REPORT_MAPPING_FIELDS:
        _require_report_mapping(report, field_name)
    if not isinstance(report.get("non_regressive"), bool):
        raise ValueError("report field `non_regressive` must be a boolean")


def _gate_row_passes(row: ValidatedGateRow, *, gate_mode: str) -> bool:
    base_pass = row.report_valid and row.evidence_complete and row.non_regressive
    if gate_mode == "advisory":
        return True
    if gate_mode == "require_non_regressive":
        return base_pass
    if gate_mode == "require_promotable":
        return base_pass and row.eligible_for_primary_surface
    raise ValueError(f"unknown gate mode `{gate_mode}`")


def _parse_command_spec(*, workflow_family: str, role: str, raw_value: Any) -> EvidenceCommand:
    if role == "smoke_or_integration" and isinstance(raw_value, Mapping):
        argv = raw_value.get("argv")
        waiver = raw_value.get("waiver")
        if argv is None and waiver is None:
            raise ValueError(f"`{workflow_family}` smoke_or_integration must declare argv or waiver")
        normalized_argv = None if argv is None else tuple(_validate_argv(argv, role=role, workflow_family=workflow_family))
        if waiver is not None and not _waiver_is_valid(waiver, today=date.max, require_targeted_evidence=True):
            raise ValueError(f"`{workflow_family}` smoke_or_integration waiver is malformed")
        return EvidenceCommand(argv=normalized_argv, waiver=waiver)

    return EvidenceCommand(
        argv=tuple(_validate_argv(raw_value, role=role, workflow_family=workflow_family)),
        waiver=None,
    )


def _validate_argv(raw_argv: Any, *, role: str, workflow_family: str) -> list[str]:
    if isinstance(raw_argv, str):
        raise ValueError(f"`{workflow_family}` {role} command must be argv, not a shell string")
    if not isinstance(raw_argv, list) or not raw_argv:
        raise ValueError(f"`{workflow_family}` {role} command must be a non-empty argv array")
    argv: list[str] = []
    for arg in raw_argv:
        if not isinstance(arg, str) or not arg:
            raise ValueError(f"`{workflow_family}` {role} command argv must contain non-empty strings")
        if "__write_root__" in arg:
            raise ValueError(
                f"`{workflow_family}` {role} command may not expose compiler-owned hidden managed write roots such as `__write_root__...`"
            )
        argv.append(arg)
    return argv


def _run_command(
    command: EvidenceCommand,
    *,
    role: str,
    repo_root: Path,
    stdout_log: Path,
    stderr_log: Path,
) -> CommandOutcome:
    started = time.perf_counter()
    if command.argv is None:
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        return CommandOutcome(
            status="waived",
            argv=None,
            exit_code=None,
            elapsed_seconds=time.perf_counter() - started,
            stdout="",
            stderr="",
            waiver=command.waiver,
        )

    try:
        completed = subprocess.run(
            command.argv,
            cwd=repo_root,
            shell=False,
            capture_output=True,
            text=True,
            check=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        exit_code = completed.returncode
    except OSError as exc:
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}\n"
        exit_code = 1

    stdout_log.write_text(stdout, encoding="utf-8")
    stderr_log.write_text(stderr, encoding="utf-8")
    return CommandOutcome(
        status="pass" if exit_code == 0 else "fail",
        argv=command.argv,
        exit_code=exit_code,
        elapsed_seconds=time.perf_counter() - started,
        stdout=stdout,
        stderr=stderr,
        waiver=command.waiver,
    )


def _load_compile_outputs(stdout: str, repo_root: Path) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None, None
    build_root_raw = payload.get("build_root")
    if not isinstance(build_root_raw, str):
        return payload, None
    manifest_path = Path(build_root_raw) / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return payload, None
    return payload, manifest


def _shared_validation_evidence(build_manifest: Mapping[str, Any] | None) -> dict[str, object]:
    if build_manifest is None:
        return {"status": "fail"}
    return {
        "status": "pass" if build_manifest.get("shared_validation_status") == "validated" else "fail",
    }


def _compile_artifact_report(
    *,
    target: ParityTarget,
    build_manifest: Mapping[str, Any] | None,
    build_root: Path | None,
    repo_root: Path,
) -> dict[str, object]:
    required: dict[str, object] = {}
    optional: dict[str, object] = {}
    artifact_paths = dict(build_manifest.get("artifact_paths", {})) if build_manifest else {}
    artifact_status = dict(build_manifest.get("artifact_status", {})) if build_manifest else {}
    debug_yaml_status = build_manifest.get("debug_yaml_status") if build_manifest else None

    for artifact_name in target.compile_artifacts["required"]:
        path = _report_artifact_path(artifact_paths.get(artifact_name), build_root=build_root, repo_root=repo_root)
        raw_status = _artifact_raw_status(
            artifact_name,
            path=path,
            artifact_status=artifact_status,
            debug_yaml_status=debug_yaml_status,
        )
        required[artifact_name] = {
            "status": "pass" if path and raw_status in PASSING_ARTIFACT_STATUSES else "missing",
            "path": path,
        }

    for artifact_name in target.compile_artifacts["optional"]:
        path = _report_artifact_path(artifact_paths.get(artifact_name), build_root=build_root, repo_root=repo_root)
        raw_status = _artifact_raw_status(
            artifact_name,
            path=path,
            artifact_status=artifact_status,
            debug_yaml_status=debug_yaml_status,
        )
        optional[artifact_name] = {
            "status": "pass" if path and raw_status in PASSING_ARTIFACT_STATUSES else "not_implemented",
            "path": path,
        }

    return {"required": required, "optional": optional}


def _report_artifact_path(
    raw_path: str | None,
    *,
    build_root: Path | None,
    repo_root: Path,
) -> str | None:
    if raw_path is None:
        return None
    artifact_path = Path(raw_path)
    if artifact_path.is_absolute():
        return _relative_or_absolute_path(artifact_path, repo_root)
    if build_root is not None:
        artifact_path = build_root.parent.parent / artifact_path
        return _relative_or_absolute_path(artifact_path, repo_root)
    return raw_path


def _resolve_build_artifact_path(
    raw_path: str | None,
    *,
    build_root: Path | None,
    repo_root: Path,
) -> Path | None:
    if raw_path is None:
        return None
    artifact_path = Path(raw_path)
    if artifact_path.is_absolute():
        return artifact_path
    if build_root is not None:
        candidate = build_root / artifact_path
        if candidate.exists():
            return candidate
        candidate = build_root.parent.parent / artifact_path
        if candidate.exists():
            return candidate
    return repo_root / artifact_path


def _artifact_raw_status(
    artifact_name: str,
    *,
    path: str | None,
    artifact_status: Mapping[str, Any],
    debug_yaml_status: Any,
) -> str:
    if artifact_name == "expanded_debug_yaml":
        return str(debug_yaml_status or "not_requested")
    if artifact_name in artifact_status:
        return str(artifact_status[artifact_name])
    if path:
        return "emitted"
    return "missing"


def _primary_surface_for_report(report: Mapping[str, Any]) -> str:
    promotion = _require_report_mapping(report, "promotion_eligibility")
    return _primary_surface_for_non_regressive_and_eligibility(
        non_regressive=bool(report.get("non_regressive")),
        eligible_for_primary_surface=bool(promotion.get("eligible_for_primary_surface")),
    )


def _primary_surface_for_non_regressive_and_eligibility(
    *,
    non_regressive: bool,
    eligible_for_primary_surface: bool,
) -> str:
    if non_regressive and eligible_for_primary_surface:
        return "orc"
    return "yaml"


def _gate_primary_surface_for_row(row: ValidatedGateRow) -> str | None:
    if not row.report_valid or not row.evidence_complete or not row.non_regressive:
        return None
    return row.primary_surface


def _waiver_is_valid(
    waiver: Any,
    *,
    today: date,
    require_targeted_evidence: bool,
) -> bool:
    if not isinstance(waiver, Mapping):
        return False
    owner = _string_or_none(waiver.get("owner"))
    justification = _string_or_none(waiver.get("justification"))
    expiry = _string_or_none(waiver.get("expiry"))
    if not owner or not justification or not expiry:
        return False
    try:
        expiry_date = date.fromisoformat(expiry)
    except ValueError:
        return False
    if expiry_date < today:
        return False
    if require_targeted_evidence:
        targeted_evidence = waiver.get("targeted_evidence")
        if not isinstance(targeted_evidence, list) or not targeted_evidence:
            return False
        if not all(isinstance(item, str) and item for item in targeted_evidence):
            return False
    return True


def _require_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"`{key}` must be a non-empty string")
    return value


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"`{key}` must be a non-empty string when provided")
    return value


def _require_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"`{key}` must be an object")
    return value


def _require_non_empty_string_list(payload: Mapping[str, Any], key: str) -> list[str]:
    values = _require_string_list(payload, key)
    if not values:
        raise ValueError(f"`{key}` must contain at least one string")
    return values


def _require_string_list(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"`{key}` must be an array of strings")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"`{key}` must be an array of non-empty strings")
    return list(value)


def _require_object_list(payload: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"`{key}` must be an array of objects")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"`{key}` must be an array of objects")
    return list(value)


def _require_report_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"report field `{key}` must be an object")
    return value


def _require_report_object_list(payload: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"report field `{key}` must be an array of objects")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"report field `{key}` must be an array of objects")
    return list(value)


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _status(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("status", "missing"))
    return "missing"


def _relative_path(path: Path, repo_root: Path) -> str:
    return str(path.resolve().relative_to(repo_root.resolve()))


def _relative_or_absolute_path(path: Path, repo_root: Path) -> str:
    resolved_repo_root = repo_root.resolve()
    resolved_path = path.resolve()
    try:
        return str(resolved_path.relative_to(resolved_repo_root))
    except ValueError:
        return str(resolved_path)
