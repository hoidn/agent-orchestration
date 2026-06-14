from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from orchestrator.workflow_lisp.workflows import ExternalToolBinding


def validate_review_findings_v1_binding() -> ExternalToolBinding:
    return ExternalToolBinding(
        name="validate_review_findings_v1",
        stable_command=(
            "python",
            "-m",
            "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
        ),
        retirement_class="validation",
        retirement_label="keep_bridge",
        replacement_surface="typed review findings validation bridge",
        bridge_owner="std/phase",
        expiry_condition=(
            "retain until typed review-findings validation parity replaces the command bridge"
        ),
        evidence_refs=("validate_review_findings_v1",),
    )


def run_neurips_backlog_checks_binding() -> ExternalToolBinding:
    return ExternalToolBinding(
        name="run_neurips_backlog_checks",
        stable_command=(
            "python",
            "workflows/library/scripts/run_neurips_backlog_checks.py",
        ),
        retirement_class="genuine_system",
        retirement_label="keep_certified_system",
        replacement_surface="bounded repo-local checks",
        bridge_owner="lisp_frontend_design_delta/implementation_phase",
        expiry_condition="retain while backlog checks remain a genuine external validation",
        evidence_refs=("design_delta_parent_drain_smokes",),
    )


def validate_lisp_frontend_design_gap_architecture_binding() -> ExternalToolBinding:
    return ExternalToolBinding(
        name="validate_lisp_frontend_design_gap_architecture",
        stable_command=(
            "python",
            "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py",
        ),
        retirement_class="validation",
        retirement_label="keep_bridge",
        replacement_surface="typed design-gap validation bridge",
        bridge_owner="lisp_frontend_design_delta/design_gap_architect",
        expiry_condition="retain until typed validation parity replaces the command bridge",
        evidence_refs=("validate_lisp_frontend_design_gap_architecture",),
    )


def run_checks_binding() -> ExternalToolBinding:
    return ExternalToolBinding(
        name="run_checks",
        stable_command=("python", "scripts/run_checks.py"),
    )


def external_tool_binding_from_manifest(
    name: str,
    payload: Mapping[str, Any],
) -> ExternalToolBinding:
    stable_command = tuple(str(token) for token in payload.get("stable_command", ()))
    kwargs: dict[str, Any] = {}
    for key in (
        "retirement_class",
        "retirement_label",
        "replacement_surface",
        "bridge_owner",
        "expiry_condition",
        "retirement_status",
    ):
        value = payload.get(key)
        if value is not None:
            kwargs[key] = str(value)
    evidence_refs = payload.get("evidence_refs")
    if evidence_refs is not None:
        kwargs["evidence_refs"] = tuple(str(item) for item in evidence_refs)
    return ExternalToolBinding(name=name, stable_command=stable_command, **kwargs)
