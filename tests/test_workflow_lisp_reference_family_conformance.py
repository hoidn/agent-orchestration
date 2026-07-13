from __future__ import annotations

import copy
import importlib
import json
import shutil
from datetime import date
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
BOUNDARY_AUTHORITY_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.boundary_authority.json"
)
COMMAND_BOUNDARIES_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.commands.json"
)
VALUE_FLOW_CENSUS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.value_flow_census.json"
)
CONSUMER_RENDERING_CENSUS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.consumer_rendering_census.json"
)
COMPATIBILITY_BRIDGES_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.compatibility_bridges.json"
)
RENDERING_CLEANUP_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.rendering_cleanup.json"
)
RENDERING_ERGONOMICS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.rendering_ergonomics.json"
)
TRANSITION_AUTHORING_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.transition_authoring.json"
)
RESUME_PLUMBING_RETIREMENT_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.resume_plumbing_retirement.json"
)
OBSERVABILITY_OLD_WRITER_COMPARISONS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.observability_old_writer_comparisons.json"
)
REFERENCE_FAMILY_EVIDENCE_PATHS = importlib.import_module(
    "orchestrator.workflow_lisp.build"
)._resolve_reference_family_evidence_paths()
REFERENCE_FAMILY_RUN_STATE_RELATIVE_PATH = (
    REFERENCE_FAMILY_EVIDENCE_PATHS.run_state_path.relative_to(REPO_ROOT).as_posix()
)
REFERENCE_FAMILY_DRAIN_SUMMARY_RELATIVE_PATH = (
    REFERENCE_FAMILY_EVIDENCE_PATHS.drain_summary_path.relative_to(REPO_ROOT).as_posix()
)
REFERENCE_FAMILY_DESIGN_GAP_SUMMARY_ROOT_RELATIVE_PATH = (
    REFERENCE_FAMILY_EVIDENCE_PATHS.design_gap_summary_root.relative_to(REPO_ROOT).as_posix()
)
REFERENCE_FAMILY_IMPLEMENTATION_ARCHITECTURE_ROOT_RELATIVE_PATH = (
    REFERENCE_FAMILY_EVIDENCE_PATHS.implementation_architecture_root.relative_to(REPO_ROOT).as_posix()
)
REFERENCE_FAMILY_ARCHITECTURE_INDEX_RELATIVE_PATH = (
    REFERENCE_FAMILY_EVIDENCE_PATHS.architecture_index_path.relative_to(REPO_ROOT).as_posix()
)
REFERENCE_FAMILY_COMPLETED_GAP_IDS = json.loads(
    (
        REPO_ROOT
        / REFERENCE_FAMILY_RUN_STATE_RELATIVE_PATH
    ).read_text(encoding="utf-8")
)["completed_design_gaps"]
LIVE_MISSING_GAP_IDS = [
    "workflow-lisp-runtime-native-drain-reference-family-completion-inventory-realignment-after-final-gap-closures",
]
CHECKED_MANIFEST_SOURCE_PATHS = {
    "boundary_authority_manifest": BOUNDARY_AUTHORITY_PATH,
    "command_boundaries_manifest": COMMAND_BOUNDARIES_PATH,
    "value_flow_census": VALUE_FLOW_CENSUS_PATH,
    "consumer_rendering_census": CONSUMER_RENDERING_CENSUS_PATH,
    "compatibility_bridges_manifest": COMPATIBILITY_BRIDGES_PATH,
    "rendering_cleanup_manifest": RENDERING_CLEANUP_PATH,
    "rendering_ergonomics_manifest": RENDERING_ERGONOMICS_PATH,
    "transition_authoring_manifest": TRANSITION_AUTHORING_PATH,
    "resume_plumbing_retirement_manifest": RESUME_PLUMBING_RETIREMENT_PATH,
    "observability_old_writer_comparisons": OBSERVABILITY_OLD_WRITER_COMPARISONS_PATH,
}


def _markdown_table_row(path: Path, key: str) -> str:
    return next(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("|") and key in line
    )


def test_design_delta_promotion_routes_current_docs_to_orc_primary() -> None:
    orc_path = "workflows/library/lisp_frontend_design_delta/drain.orc"
    yaml_path = "workflows/examples/lisp_frontend_design_delta_drain.yaml"

    workflow_catalog = (REPO_ROOT / "workflows" / "README.md").read_text(
        encoding="utf-8"
    )
    preferred_section = workflow_catalog.split(
        "Fresh preferred starting points:", 1
    )[1].split("Reference corpus:", 1)[0]
    assert orc_path in preferred_section
    assert yaml_path not in preferred_section
    assert "Primary" in _markdown_table_row(
        REPO_ROOT / "workflows" / "README.md", orc_path
    )
    assert "Compatibility" in _markdown_table_row(
        REPO_ROOT / "workflows" / "README.md", yaml_path
    )

    docs_index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    fast_triage = docs_index.split("## Fast Triage", 1)[1].split(
        "## Clarifications", 1
    )[0]
    assert orc_path in fast_triage

    triage_path = REPO_ROOT / "docs" / "workflow_yaml_estate_triage.md"
    triage_row = _markdown_table_row(triage_path, yaml_path)
    assert "| yes |" in triage_row
    assert ".orc primary" in triage_row
    assert "Stage 6" in triage_row
    triage_text = triage_path.read_text(encoding="utf-8")
    assert "- compatibility — .orc primary; retain through Stage 6 archive: 1" in triage_text
    assert "- production — needs .orc port + promotion evidence: 27" in triage_text

    capability_matrix = REPO_ROOT / "docs" / "capability_status_matrix.md"
    yaml_surface_row = _markdown_table_row(capability_matrix, "YAML DSL v2.x")
    assert "Preferred fresh starting point" not in yaml_surface_row
    design_delta_row = _markdown_table_row(
        capability_matrix, "Design Delta parent-family boundary"
    )
    assert orc_path in design_delta_row
    assert "primary" in design_delta_row.lower()

    migration_record = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION"
        / "migration_record.md"
    ).read_text(encoding="utf-8")
    current_surface = migration_record.split("## Historical YAML Baseline", 1)[0]
    assert orc_path in current_surface
    assert "primary" in current_surface.lower()
    assert "Gate P3" in current_surface


def test_design_delta_promotion_handoff_routes_to_independent_gate_p3_closure() -> None:
    drain_plan = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-07-drain-migration-g8-retirement.md"
    ).read_text(encoding="utf-8")
    gate_p2_status = drain_plan.split(
        "**Status (reviewed 2026-07-12): SATISFIED.**", 1
    )[1].split("**Gate P3 (entry to Phase 3):**", 1)[0]
    historical_gate_p2_routing = drain_plan.split(
        "**Historical routing effect at the Gate P2 checkpoint:**", 1
    )[1].split("## Phase 2 Ledger", 1)[0]
    typed_guidance_row = _markdown_table_row(
        REPO_ROOT / "docs" / "capability_status_matrix.md",
        "Workflow Lisp typed result guidance",
    )
    docs_index_routing = (REPO_ROOT / "docs" / "index.md").read_text(
        encoding="utf-8"
    ).split("**Component-plan routing:**", 1)[1].split(
        "**Later procedure-first substrate:**", 1
    )[0]
    procedure_sequence_routing = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-execution-sequence.md"
    ).read_text(encoding="utf-8").split(
        "**Current next selection (2026-07-12):**", 1
    )[1].split("The completed Phase 1 execution order was:", 1)[0]
    activation_amendment = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-activation-plan.md"
    ).read_text(encoding="utf-8").split(
        "> **Current execution amendment (updated 2026-07-12):**", 1
    )[1].split("**Tech Stack:**", 1)[0]
    migration_record_routing = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION"
        / "migration_record.md"
    ).read_text(encoding="utf-8").split(
        "The promotion handoff now has strict promotable parity", 1
    )[1].split("The remaining sections preserve the June migration inventory", 1)[0]
    routing_surfaces = {
        "drain plan Gate P2 status": (gate_p2_status, "current selector"),
        "drain plan historical Gate P2 routing": (
            historical_gate_p2_routing,
            "current selector",
        ),
        "typed-guidance capability row": (typed_guidance_row, "current selector"),
        "docs index component-plan routing": (docs_index_routing, "current selector"),
        "procedure-first current selection": (
            procedure_sequence_routing,
            "active step is",
        ),
        "activation current amendment": (
            activation_amendment,
            "next active selection:",
        ),
        "migration-record current authority": (
            migration_record_routing,
            "current selector",
        ),
    }

    for label, (surface, selector_marker) in routing_surfaces.items():
        normalized = " ".join(
            surface.lower()
            .replace("-", " ")
            .replace("–", " ")
            .replace(">", " ")
            .split()
        )
        selector_target = normalized.split(selector_marker, 1)[1].split(".", 1)[0]
        assert "gate p3" in selector_target, label
        assert "all four" in selector_target, label
        assert "verif" in selector_target, label
        assert (
            "promotion handoff" not in selector_target.split("gate p3", 1)[0]
        ), label

    completed_handoff_surfaces = {
        "drain plan Gate P2 status": gate_p2_status,
        "drain plan historical Gate P2 routing": historical_gate_p2_routing,
    }
    for label, surface in completed_handoff_surfaces.items():
        normalized = " ".join(surface.lower().replace("-", " ").split())
        assert "promotion handoff" in normalized, label
        assert "complet" in normalized, label

    normalized_history = " ".join(
        historical_gate_p2_routing.lower()
        .replace("-", " ")
        .replace("–", " ")
        .split()
    )
    assert "at that checkpoint" in normalized_history
    assert "superseded" in normalized_history
    assert "phase 2 ledger entry (e)" in normalized_history

    normalized_guidance = " ".join(
        typed_guidance_row.lower().replace("-", " ").replace("–", " ").split()
    )
    guidance_selector_sentence = next(
        sentence
        for sentence in normalized_guidance.split(".")
        if "current selector" in sentence
    )
    assert guidance_selector_sentence.index("gate p3") < guidance_selector_sentence.index(
        "phases 3 4"
    )
    assert guidance_selector_sentence.index(
        "phases 3 4"
    ) < guidance_selector_sentence.index("stage 5")

    retirement_program = (
        REPO_ROOT / "docs" / "plans" / "2026-07-07-yaml-retirement-program.md"
    ).read_text(encoding="utf-8")
    family_one_row = _markdown_table_row(
        REPO_ROOT / "docs" / "plans" / "2026-07-07-yaml-retirement-program.md",
        "lisp_frontend_design_delta_drain.yaml",
    )
    assert "Family (YAML primary or retained twin)" in retirement_program
    assert "+ 6 `v214` library imports" in family_one_row
    assert ".orc" in family_one_row
    assert "recorded" in family_one_row
    assert "Stage 6" in family_one_row
    assert retirement_program.count("lisp_frontend_design_delta_") >= 1


def _reference_family_module():
    return importlib.import_module(
        "orchestrator.workflow_lisp.reference_family_conformance"
    )


def _migration_parity_module():
    return importlib.import_module("orchestrator.workflow_lisp.migration_parity")


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _copy_json(path: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def _copy_tree(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination


def _completed_gap_summary_payload(gap_id: str) -> dict[str, str]:
    return {
        "work_item_id": gap_id,
        "work_item_source": "DESIGN_GAP",
        "item_status": "COMPLETED",
        "run_state_path": REFERENCE_FAMILY_RUN_STATE_RELATIVE_PATH,
    }


def _copy_checked_manifests(repo_root: Path) -> dict[str, Path]:
    copied: dict[str, Path] = {}
    for input_id, source_path in CHECKED_MANIFEST_SOURCE_PATHS.items():
        destination = (
            repo_root
            / "workflows"
            / "examples"
            / "inputs"
            / "workflow_lisp_migrations"
            / source_path.name
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, destination)
        copied[input_id] = destination
    return copied


def _owner_reports(repo_root: Path) -> dict[str, dict[str, object]]:
    report = {"workflow_family": "design_delta_parent_drain", "status": "pass"}
    return {
        "boundary_authority_report": {
            "workflow_family": "design_delta_parent_drain",
            "path": "artifacts/work/review-parity-check/boundary_authority_report.json",
            "workflows": [{"workflow_name": "lisp_frontend_design_delta/drain::drain"}],
        },
        "compatibility_bridge_report": {
            **dict(report),
            "path": "artifacts/work/review-parity-check/compatibility_bridge_report.json",
        },
        "typed_prompt_input_report": {
            **dict(report),
            "path": "artifacts/work/review-parity-check/typed_prompt_input_report.json",
        },
        "rendering_cleanup_report": {
            **dict(report),
            "path": "artifacts/work/review-parity-check/rendering_cleanup_report.json",
        },
        "rendering_ergonomics_report": {
            **dict(report),
            "path": "artifacts/work/review-parity-check/rendering_ergonomics_report.json",
        },
        "transition_authoring_report": {
            **dict(report),
            "path": "artifacts/work/review-parity-check/transition_authoring_report.json",
        },
        "resume_plumbing_retirement_report": {
            **dict(report),
            "path": "artifacts/work/review-parity-check/resume_plumbing_retirement_report.json",
        },
        "observability_summary_report": {
            **dict(report),
            "path": "artifacts/work/review-parity-check/observability_summary_report.json",
        },
        "parent_drain_census_alignment_report": {
            **dict(report),
            "path": "artifacts/work/review-parity-check/parent_drain_census_alignment_report.json",
        },
    }


def _write_parity_fixture(repo_root: Path) -> dict[str, Path]:
    migration_parity = _migration_parity_module()
    _write_text(
        repo_root / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc",
        "(defworkflow drain ())\n",
    )
    _write_text(
        repo_root / "workflows" / "examples" / "lisp_frontend_design_delta_drain.yaml",
        "steps: []\n",
    )
    targets_path = _write_json(
        repo_root
        / "workflows"
        / "examples"
        / "inputs"
        / "workflow_lisp_migrations"
        / "parity_targets.json",
        {
            "schema_version": "workflow_lisp_migration_parity_targets.v1",
            "targets": [
                {
                    "workflow_family": "design_delta_parent_drain",
                    "candidate": "workflows/library/lisp_frontend_design_delta/drain.orc",
                    "yaml_primary": "workflows/examples/lisp_frontend_design_delta_drain.yaml",
                    "entry_workflow": "lisp_frontend_design_delta/drain::drain",
                    "baseline_characterization": {
                        "inputs": ["progress_report", "execution_report", "backlog_item"],
                        "outputs": ["execution_report", "implementation_state"],
                        "terminal_states": ["completed", "failed"],
                        "artifacts": ["execution_report.md", "implementation_state.json"],
                        "resume_behavior": [
                            "resume reuses approved upstream artifacts"
                        ],
                    },
                    "accepted_differences": [],
                    "deprecated_yaml_mechanics": [
                        {
                            "mechanic": "manual markdown parity summary",
                            "replacement": "machine-readable parity JSON report",
                        }
                    ],
                    "promotion_eligibility": {
                        "eligible_for_primary_surface": False,
                        "blocked_reason": "parent-family candidate only",
                    },
                    "compile_artifacts": {
                        "required": ["core_workflow_ast", "semantic_ir", "source_map"],
                        "optional": [],
                    },
                    "evidence_commands": {
                        "compile": ["python", "-m", "orchestrator", "compile"],
                        "dry_run": ["python", "-m", "orchestrator", "run", "--dry-run"],
                        "smoke_or_integration": ["python", "-m", "pytest", "-q"],
                        "output_contract_parity": ["python", "-m", "pytest", "-q"],
                        "terminal_state_parity": ["python", "-m", "pytest", "-q"],
                        "artifact_parity": ["python", "-m", "pytest", "-q"],
                        "resume_parity": ["python", "-m", "pytest", "-q"],
                    },
                }
            ],
        },
    )
    target = migration_parity.load_parity_targets(targets_path)[0]
    report_root = repo_root / "artifacts" / "work" / "review-parity-check"
    build_root = report_root / "build"
    required_artifact_paths = {
        "core_workflow_ast": build_root / "core_workflow_ast.json",
        "semantic_ir": build_root / "semantic_ir.json",
        "source_map": build_root / "source_map.json",
    }
    for artifact_name, artifact_path in required_artifact_paths.items():
        _write_json(artifact_path, {"artifact": artifact_name, "status": "pass"})
    command_logs: dict[str, dict[str, str]] = {}
    evidence_refs: dict[str, dict[str, dict[str, str]]] = {}
    for role in (
        "compile",
        "dry_run",
        "smoke_or_integration",
        "output_contract_parity",
        "terminal_state_parity",
        "artifact_parity",
        "resume_parity",
    ):
        stdout_path = report_root / "logs" / "design_delta_parent_drain" / f"{role}.stdout.log"
        stderr_path = report_root / "logs" / "design_delta_parent_drain" / f"{role}.stderr.log"
        _write_text(stdout_path, f"{role} stdout\n")
        _write_text(stderr_path, f"{role} stderr\n")
        stdout_rel = stdout_path.relative_to(repo_root).as_posix()
        stderr_rel = stderr_path.relative_to(repo_root).as_posix()
        command_logs[role] = {"stdout": stdout_rel, "stderr": stderr_rel}
        evidence_refs[role] = {
            "stdout": {"path": stdout_rel, "sha256": migration_parity._sha256_file(stdout_path)},
            "stderr": {"path": stderr_rel, "sha256": migration_parity._sha256_file(stderr_path)},
        }
    report_path = report_root / "design_delta_parent_drain.json"
    generated_at = "2026-06-24T00:00:00Z"
    report = {
        "schema_version": "workflow_lisp_migration_parity_report.v2",
        "workflow_family": "design_delta_parent_drain",
        "candidate": target.candidate,
        "yaml_primary": target.yaml_primary,
        "tool_version": "workflow_lisp_migration_parity.v2",
        "dsl_version": "2.14",
        "generated_at": generated_at,
        "generated_by": ["python", "-m", "orchestrator", "migration-parity"],
        "report_path": report_path.relative_to(repo_root).as_posix(),
        "target_identity": migration_parity._build_target_identity(
            target,
            repo_root=repo_root,
            targets_file=targets_path,
        ),
        "evidence_freshness": {
            "generated_at": generated_at,
            "required_artifacts": {
                artifact_name: {
                    "status": "pass",
                    "path": artifact_path.relative_to(repo_root).as_posix(),
                    "sha256": migration_parity._sha256_file(artifact_path),
                }
                for artifact_name, artifact_path in required_artifact_paths.items()
            },
            "evidence_refs": evidence_refs,
        },
        "command_logs": command_logs,
        "accepted_differences": [dict(entry) for entry in target.accepted_differences],
        "deprecated_yaml_mechanics": [
            dict(entry) for entry in target.deprecated_yaml_mechanics
        ],
        "promotion_eligibility": dict(target.promotion_eligibility),
        "compile_artifacts": {
            "required": {
                artifact_name: {
                    "status": "pass",
                    "path": artifact_path.relative_to(repo_root).as_posix(),
                }
                for artifact_name, artifact_path in required_artifact_paths.items()
            },
            "optional": {},
        },
        "evidence": {
            role: {
                "status": "pass",
                "argv": ["python", "-m", "pytest", role],
                "exit_code": 0,
                "elapsed_seconds": 0.1,
            }
            for role in (
                "compile",
                "dry_run",
                "smoke_or_integration",
                "output_contract_parity",
                "terminal_state_parity",
                "artifact_parity",
                "resume_parity",
            )
        },
        "non_regressive": True,
    }
    report["evidence"]["shared_validation"] = {"status": "pass"}
    report["evidence"]["baseline_characterization"] = {
        "status": "pass",
        **{
            field_name: list(values)
            for field_name, values in target.baseline_characterization.items()
        },
    }
    _write_json(report_path, report)
    _write_text(report_path.with_suffix(".md"), migration_parity.render_parity_markdown(report))
    gate_row = migration_parity.validate_report_for_target(
        report,
        target=target,
        targets_file=targets_path,
        repo_root=repo_root,
        today=date(2026, 6, 24),
    )
    index_path = report_root / "index.json"
    _write_json(index_path, migration_parity.render_parity_index([gate_row]))
    return {
        "parity_targets_path": targets_path,
        "parity_report_json_path": report_path,
        "parity_report_markdown_path": report_path.with_suffix(".md"),
        "parity_index_path": index_path,
    }


def _reference_family_fixture(tmp_path: Path) -> dict[str, object]:
    repo_root = tmp_path / "repo"
    run_state_path = _write_json(
        repo_root / REFERENCE_FAMILY_RUN_STATE_RELATIVE_PATH,
        {"completed_design_gaps": list(REFERENCE_FAMILY_COMPLETED_GAP_IDS)},
    )
    drain_summary_path = _write_json(
        repo_root / REFERENCE_FAMILY_DRAIN_SUMMARY_RELATIVE_PATH,
        {"completed_design_gaps": list(REFERENCE_FAMILY_COMPLETED_GAP_IDS)},
    )
    design_gap_summary_root = repo_root / REFERENCE_FAMILY_DESIGN_GAP_SUMMARY_ROOT_RELATIVE_PATH
    implementation_architecture_root = (
        repo_root / REFERENCE_FAMILY_IMPLEMENTATION_ARCHITECTURE_ROOT_RELATIVE_PATH
    )
    architecture_index_lines: list[str] = []
    for gap_id in REFERENCE_FAMILY_COMPLETED_GAP_IDS:
        _write_json(
            design_gap_summary_root / f"{gap_id}-summary.json",
            _completed_gap_summary_payload(gap_id),
        )
        architecture_path = (
            implementation_architecture_root / gap_id / "implementation_architecture.md"
        )
        _write_text(architecture_path, f"# {gap_id}\n")
        architecture_index_lines.append(
            architecture_path.relative_to(repo_root).as_posix()
        )
    architecture_index_path = _write_text(
        repo_root / REFERENCE_FAMILY_ARCHITECTURE_INDEX_RELATIVE_PATH,
        "\n".join(f"- {line}" for line in architecture_index_lines) + "\n",
    )
    target_design_path = _write_text(
        repo_root / "docs" / "design" / "workflow_lisp_runtime_native_drain_authoring.md",
        "# Target design\n",
    )
    baseline_design_path = _write_text(
        repo_root / "docs" / "design" / "workflow_lisp_frontend_specification.md",
        "# Baseline design\n",
    )
    command_adapter_contract_path = _write_text(
        repo_root / "docs" / "design" / "workflow_command_adapter_contract.md",
        "# Command adapter contract\n",
    )
    parity_paths = _write_parity_fixture(repo_root)
    return {
        "repo_root": repo_root,
        "run_state_path": run_state_path,
        "drain_summary_path": drain_summary_path,
        "design_gap_summary_root": design_gap_summary_root,
        "implementation_architecture_root": implementation_architecture_root,
        "architecture_index_path": architecture_index_path,
        "target_design_path": target_design_path,
        "baseline_design_path": baseline_design_path,
        "command_adapter_contract_path": command_adapter_contract_path,
        "checked_manifest_paths": _copy_checked_manifests(repo_root),
        "owner_reports": _owner_reports(repo_root),
        **parity_paths,
    }


def _reference_family_inputs(
    fixture: dict[str, object],
    *,
    drain_summary_path: Path | None = None,
    design_gap_summary_root: Path | None = None,
    architecture_index_path: Path | None = None,
    target_design_path: Path | None = None,
    baseline_design_path: Path | None = None,
    command_adapter_contract_path: Path | None = None,
    parity_report_json_path: Path | None = None,
    parity_report_markdown_path: Path | None = None,
    parity_index_path: Path | None = None,
) -> dict[str, object]:
    return {
        "workflow_family": "design_delta_parent_drain",
        "run_state_path": fixture["run_state_path"],
        "drain_summary_path": drain_summary_path or fixture["drain_summary_path"],
        "design_gap_summary_root": design_gap_summary_root
        or fixture["design_gap_summary_root"],
        "implementation_architecture_root": fixture["implementation_architecture_root"],
        "architecture_index_path": architecture_index_path
        or fixture["architecture_index_path"],
        "target_design_path": target_design_path or fixture["target_design_path"],
        "baseline_design_path": baseline_design_path or fixture["baseline_design_path"],
        "command_adapter_contract_path": command_adapter_contract_path
        or fixture["command_adapter_contract_path"],
        "parity_targets_path": fixture["parity_targets_path"],
        "parity_report_json_path": parity_report_json_path
        or fixture["parity_report_json_path"],
        "parity_report_markdown_path": parity_report_markdown_path
        or fixture["parity_report_markdown_path"],
        "parity_index_path": parity_index_path or fixture["parity_index_path"],
        "checked_manifest_paths": fixture["checked_manifest_paths"],
        "owner_reports": fixture["owner_reports"],
        "repo_root": fixture["repo_root"],
    }


def _aligned_drain_summary_copy(fixture: dict[str, object], destination: Path) -> Path:
    return _copy_json(fixture["drain_summary_path"], destination)


def test_build_reference_family_conformance_profile_passes_for_aligned_fixture(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(fixture)
    )

    assert profile["schema_version"] == "workflow_lisp_reference_family_conformance_profile.v1"
    assert "schema_id" not in profile
    assert profile["profile_status"] == "pass"
    assert profile["completed_gap_reconciliation"]["run_state_count"] == len(
        REFERENCE_FAMILY_COMPLETED_GAP_IDS
    )
    assert profile["completed_gap_reconciliation"]["drain_summary_count"] == len(
        REFERENCE_FAMILY_COMPLETED_GAP_IDS
    )
    assert profile["target_design"] == "docs/design/workflow_lisp_runtime_native_drain_authoring.md"
    assert profile["baseline_design"] == "docs/design/workflow_lisp_frontend_specification.md"
    assert isinstance(profile["generated_at"], str) and profile["generated_at"]
    assert profile["completed_gap_reconciliation"]["missing_from_drain_summary"] == []
    assert profile["parity_surface_reconciliation"]["derived_primary_surface"] == "yaml"
    assert {row["input_id"] for row in profile["evidence_inputs"]} >= {
        "architecture_index",
        "target_design",
        "baseline_design",
        "command_adapter_contract",
    }
    assert "surface_rows" not in profile
    assert {
        row["surface_id"] for row in profile["conformance_surfaces"]
    } == {
        "parent_callable_orc_route",
        "public_private_boundary",
        "hidden_compatibility_bridge_carriage",
        "hidden_compatibility_bridge_evidence_alignment",
        "observability_old_writer_retirement",
        "provider_inputs",
        "provider_write_targets",
        "body_renderings",
        "compatibility_files",
        "deterministic_helpers",
        "durable_state_changes",
        "source_shape_gate",
        "completion_inventory",
        "migration_parity_surface",
    }
    surfaces_by_id = {
        row["surface_id"]: row for row in profile["conformance_surfaces"]
    }
    for surface_id in (
        "parent_callable_orc_route",
        "completion_inventory",
        "migration_parity_surface",
    ):
        assert surfaces_by_id[surface_id]["evidence_paths"] != []


def test_build_reference_family_conformance_profile_reports_live_one_gap_omission(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)
    selected_gap_id = REFERENCE_FAMILY_COMPLETED_GAP_IDS[0]
    summary_copy = _aligned_drain_summary_copy(fixture, tmp_path / "drain-summary.json")
    payload = json.loads(summary_copy.read_text(encoding="utf-8"))
    payload["completed_design_gaps"] = [
        gap_id
        for gap_id in payload["completed_design_gaps"]
        if gap_id != selected_gap_id
    ]
    summary_copy.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(fixture, drain_summary_path=summary_copy)
    )

    assert profile["profile_status"] == "fail"
    assert profile["completed_gap_reconciliation"]["run_state_count"] == len(
        REFERENCE_FAMILY_COMPLETED_GAP_IDS
    )
    assert profile["completed_gap_reconciliation"]["drain_summary_count"] == len(
        REFERENCE_FAMILY_COMPLETED_GAP_IDS
    ) - 1
    assert profile["completed_gap_reconciliation"]["missing_from_drain_summary"] == [
        selected_gap_id
    ]
    assert [
        diagnostic["code"] for diagnostic in profile["diagnostics"]
    ] == ["reference_family_completed_gap_summary_mismatch"]


def test_build_reference_family_conformance_profile_reports_missing_per_gap_summary_artifact(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)
    summary_root = _copy_tree(
        fixture["design_gap_summary_root"], tmp_path / "design-gap-summaries"
    )
    missing_gap_id = REFERENCE_FAMILY_COMPLETED_GAP_IDS[0]
    (summary_root / f"{missing_gap_id}-summary.json").unlink()

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(fixture, design_gap_summary_root=summary_root)
    )

    assert profile["profile_status"] == "fail"
    assert profile["completed_gap_reconciliation"]["missing_summary_artifacts"] == [
        missing_gap_id
    ]
    assert [
        diagnostic["code"] for diagnostic in profile["diagnostics"]
    ] == ["reference_family_completed_gap_artifact_missing"]


def test_build_reference_family_conformance_profile_rejects_incomplete_per_gap_summary_metadata(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)
    summary_root = _copy_tree(
        fixture["design_gap_summary_root"], tmp_path / "design-gap-summaries"
    )
    invalid_gap_id = REFERENCE_FAMILY_COMPLETED_GAP_IDS[0]
    summary_path = summary_root / f"{invalid_gap_id}-summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["item_status"] = "IN_PROGRESS"
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(fixture, design_gap_summary_root=summary_root)
    )

    assert profile["profile_status"] == "fail"
    assert [
        diagnostic["code"] for diagnostic in profile["diagnostics"]
    ] == ["reference_family_completed_gap_artifact_missing"]


def test_build_reference_family_conformance_profile_rejects_per_gap_summary_run_state_drift(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)
    summary_root = _copy_tree(
        fixture["design_gap_summary_root"], tmp_path / "design-gap-summaries"
    )
    invalid_gap_id = REFERENCE_FAMILY_COMPLETED_GAP_IDS[0]
    summary_path = summary_root / f"{invalid_gap_id}-summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["run_state_path"] = "state/other/run_state.json"
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(fixture, design_gap_summary_root=summary_root)
    )

    assert profile["profile_status"] == "fail"
    assert [
        diagnostic["code"] for diagnostic in profile["diagnostics"]
    ] == ["reference_family_completed_gap_artifact_missing"]


def test_build_reference_family_conformance_profile_reports_missing_implementation_architecture(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)
    architecture_root = tmp_path / "implementation-architectures"
    _copy_tree(fixture["implementation_architecture_root"], architecture_root)
    missing_gap_id = REFERENCE_FAMILY_COMPLETED_GAP_IDS[0]
    (
        architecture_root / missing_gap_id / "implementation_architecture.md"
    ).unlink()

    profile = module.build_reference_family_conformance_profile(
        **{
            **_reference_family_inputs(fixture),
            "implementation_architecture_root": architecture_root,
        }
    )

    assert profile["profile_status"] == "fail"
    assert profile["completed_gap_reconciliation"]["missing_architecture_files"] == [
        missing_gap_id
    ]
    assert [
        diagnostic["code"] for diagnostic in profile["diagnostics"]
    ] == ["reference_family_completed_gap_artifact_missing"]


def test_build_reference_family_conformance_profile_rejects_missing_architecture_index_coverage(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)
    architecture_index_path = tmp_path / "existing-architecture-index.md"
    _copy_json(fixture["architecture_index_path"], architecture_index_path)
    selected_gap_id = REFERENCE_FAMILY_COMPLETED_GAP_IDS[0]
    architecture_path = (
        f"{REFERENCE_FAMILY_IMPLEMENTATION_ARCHITECTURE_ROOT_RELATIVE_PATH}/"
        f"{selected_gap_id}/implementation_architecture.md"
    )
    architecture_index_path.write_text(
        "\n".join(
            line
            for line in architecture_index_path.read_text(encoding="utf-8").splitlines()
            if selected_gap_id not in line and architecture_path not in line
        )
        + "\n",
        encoding="utf-8",
    )

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(
            fixture,
            architecture_index_path=architecture_index_path,
        )
    )

    assert profile["profile_status"] == "fail"
    assert profile["completed_gap_reconciliation"]["missing_from_architecture_index"] == [
        selected_gap_id
    ]
    assert [
        diagnostic["code"] for diagnostic in profile["diagnostics"]
    ] == ["reference_family_completed_gap_artifact_missing"]
    assert profile["diagnostics"][0]["missing_from_architecture_index"] == [
        selected_gap_id
    ]


def test_build_reference_family_conformance_profile_allows_missing_owned_architecture_index_with_direct_reconciliation(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)
    missing_index_path = tmp_path / "missing-existing-architecture-index.md"

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(
            fixture,
            architecture_index_path=missing_index_path,
        )
    )

    assert profile["profile_status"] == "pass"
    assert profile["completed_gap_reconciliation"]["status"] == "pass"
    assert profile["completed_gap_reconciliation"]["missing_from_architecture_index"] == []
    assert (
        profile["completed_gap_reconciliation"]["architecture_index_strategy"]
        == "direct_architecture_root_reconciliation"
    )
    architecture_index_row = next(
        row for row in profile["evidence_inputs"] if row["input_id"] == "architecture_index"
    )
    assert architecture_index_row["load_status"] == "missing"


@pytest.mark.parametrize(
    (
        "missing_input_id",
        "architecture_index_path",
        "target_design_path",
        "baseline_design_path",
        "command_adapter_contract_path",
    ),
    [
        ("target_design", None, Path("/does/not/exist.md"), None, None),
        ("baseline_design", None, None, Path("/does/not/exist.md"), None),
        ("command_adapter_contract", None, None, None, Path("/does/not/exist.md")),
    ],
)
def test_build_reference_family_conformance_profile_fails_closed_when_required_evidence_input_is_missing(
    tmp_path: Path,
    missing_input_id: str,
    architecture_index_path: Path | None,
    target_design_path: Path | None,
    baseline_design_path: Path | None,
    command_adapter_contract_path: Path | None,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(
            fixture,
            architecture_index_path=architecture_index_path,
            target_design_path=target_design_path,
            baseline_design_path=baseline_design_path,
            command_adapter_contract_path=command_adapter_contract_path,
        )
    )

    assert profile["profile_status"] == "fail"
    evidence_row = next(row for row in profile["evidence_inputs"] if row["input_id"] == missing_input_id)
    assert evidence_row["load_status"] == "missing"
    assert any(
        diagnostic["code"] == "reference_family_conformance_input_missing"
        and diagnostic["input_id"] == missing_input_id
        for diagnostic in profile["diagnostics"]
    )


def test_build_reference_family_conformance_profile_rejects_parity_surface_metadata_mismatch(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)
    markdown_path = _copy_json(
        fixture["parity_report_markdown_path"], tmp_path / "design_delta_parent_drain.md"
    )
    text = markdown_path.read_text(encoding="utf-8").replace(
        "- Primary surface: `yaml`",
        "- Primary surface: `orc`",
    )
    markdown_path.write_text(text, encoding="utf-8")

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(
            fixture,
            parity_report_markdown_path=markdown_path,
        )
    )

    assert profile["profile_status"] == "fail"
    assert profile["parity_surface_reconciliation"]["derived_primary_surface"] == "yaml"
    assert profile["parity_surface_reconciliation"]["markdown_primary_surface"] == "orc"
    assert {diagnostic["code"] for diagnostic in profile["diagnostics"]} == {
        "reference_family_parity_surface_mismatch",
        "reference_family_conformance_surface_failed",
    }


def test_build_reference_family_conformance_profile_rejects_malformed_parity_markdown_metadata(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)
    markdown_path = _copy_json(
        fixture["parity_report_markdown_path"], tmp_path / "design_delta_parent_drain.md"
    )
    text = markdown_path.read_text(encoding="utf-8").replace(
        "- Promotion eligible: `false`\n",
        "",
    )
    markdown_path.write_text(text, encoding="utf-8")

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(
            fixture,
            parity_report_markdown_path=markdown_path,
        )
    )

    assert profile["profile_status"] == "fail"
    assert profile["parity_surface_reconciliation"]["status"] == "fail"
    assert (
        profile["parity_surface_reconciliation"]["json_eligible_for_primary_surface"]
        is False
    )
    assert {diagnostic["code"] for diagnostic in profile["diagnostics"]} == {
        "reference_family_parity_report_invalid",
        "reference_family_conformance_surface_failed",
    }
    assert "missing metadata bullets: promotion_eligible" in profile["diagnostics"][0][
        "message"
    ]


def test_build_reference_family_conformance_profile_rejects_parity_report_that_fails_shared_gate_validation(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)
    json_path = _copy_json(
        fixture["parity_report_json_path"], tmp_path / "design_delta_parent_drain.json"
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    del payload["target_identity"]["candidate_sha256"]
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(fixture, parity_report_json_path=json_path)
    )

    assert profile["profile_status"] == "fail"
    assert profile["parity_surface_reconciliation"]["status"] == "fail"
    assert profile["parity_surface_reconciliation"]["derived_primary_surface"] is None
    assert {diagnostic["code"] for diagnostic in profile["diagnostics"]} == {
        "reference_family_parity_report_invalid",
        "reference_family_conformance_surface_failed",
    }


def test_build_reference_family_conformance_profile_allows_stale_parity_during_regeneration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)
    json_path = _copy_json(
        fixture["parity_report_json_path"], tmp_path / "design_delta_parent_drain.json"
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    del payload["target_identity"]["candidate_sha256"]
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setenv(
        "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_FAMILY",
        "design_delta_parent_drain",
    )
    monkeypatch.setenv(
        "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_REPORT",
        str(json_path.resolve()),
    )
    monkeypatch.setenv(
        "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_MARKDOWN",
        str(Path(fixture["parity_report_markdown_path"]).resolve()),
    )
    monkeypatch.setenv(
        "ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_INDEX",
        str(Path(fixture["parity_index_path"]).resolve()),
    )

    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(fixture, parity_report_json_path=json_path)
    )

    assert profile["profile_status"] == "pass"
    assert profile["parity_surface_reconciliation"]["status"] == "pass"
    assert profile["parity_surface_reconciliation"]["regeneration_in_progress"] is True
    assert profile["diagnostics"] == []


def test_build_reference_family_conformance_profile_requires_explicit_passing_owner_reports(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)
    owner_reports = copy.deepcopy(fixture["owner_reports"])
    owner_reports["typed_prompt_input_report"] = {}
    owner_reports["rendering_ergonomics_report"] = {}

    profile = module.build_reference_family_conformance_profile(
        **{
            **_reference_family_inputs(fixture),
            "owner_reports": owner_reports,
        }
    )

    assert profile["profile_status"] == "fail"
    surface_rows = {
        row["surface_id"]: row["status"] for row in profile["conformance_surfaces"]
    }
    assert surface_rows["provider_inputs"] == "fail"
    assert surface_rows["provider_write_targets"] == "fail"
    assert {diagnostic["code"] for diagnostic in profile["diagnostics"]} == {
        "reference_family_conformance_surface_failed"
    }


def test_build_reference_family_conformance_profile_derives_yaml_primary_for_non_promotable_report(
    tmp_path: Path,
) -> None:
    module = _reference_family_module()
    fixture = _reference_family_fixture(tmp_path)
    profile = module.build_reference_family_conformance_profile(
        **_reference_family_inputs(fixture)
    )

    parity = profile["parity_surface_reconciliation"]

    assert parity["json_eligible_for_primary_surface"] is False
    assert parity["derived_primary_surface"] == "yaml"


def test_parse_parity_markdown_metadata_ignores_non_metadata_prose() -> None:
    module = _reference_family_module()
    text = """# Parity Report: design_delta_parent_drain

Intro prose that should not be parsed.
- Primary surface: `orc`

- Non-regressive: `true`
- Promotion eligible: `false`
- Primary surface: `yaml`

Trailing prose that should not be parsed either.
"""

    metadata = module.parse_parity_markdown_metadata(text)

    assert metadata == {
        "non_regressive": True,
        "promotion_eligible": False,
        "primary_surface": "yaml",
    }
