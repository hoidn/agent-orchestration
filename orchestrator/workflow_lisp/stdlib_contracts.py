"""Certified command adapter bindings retained by native typed frontends."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from .command_boundaries import CertifiedAdapterInputField, PROMOTED_CALL_REQUIRED_METADATA_FIELDS
from .workflows import CertifiedAdapterBinding


STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME: Mapping[str, CertifiedAdapterBinding] = MappingProxyType(
    {
        "validate_review_findings_v1": CertifiedAdapterBinding(
            name="validate_review_findings_v1",
            stable_command=(
                "python",
                "-m",
                "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
            ),
            closure=(".",),
            input_contract={"type": "object"},
            output_type_name="ReviewFindings",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("review_findings_valid",),
            negative_fixture_ids=(
                "review_findings_wrong_schema_version",
                "review_findings_path_escape",
                "review_findings_pointer_authority_forbidden",
                "review_findings_bundle_schema_invalid",
            ),
            behavior_class="structured_result",
            input_signature=(
                CertifiedAdapterInputField(
                    name="items_path",
                    type_name="ReviewFindingsJsonPath",
                    required=True,
                    transport_key="items_path",
                ),
            ),
            artifact_contracts=("review_findings_bundle",),
            state_writes=(),
            error_codes=("review_findings_bundle_schema_invalid",),
            owner_module="std/phase",
            replacement_path=None,
            invocation_protocol="json_object_positional_arg",
            declared_promoted_fields=PROMOTED_CALL_REQUIRED_METADATA_FIELDS,
            retirement_class="validation",
            retirement_label="keep_bridge",
            replacement_surface="typed review findings validation bridge",
            bridge_owner="std/phase",
            expiry_condition=(
                "retain until typed review-findings validation parity replaces the command bridge"
            ),
            evidence_refs=("validate_review_findings_v1",),
        ),
    }
)


STDLIB_CERTIFIED_ADAPTER_TRIGGER_NAMES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "review-revise-loop": ("validate_review_findings_v1",),
        "review-revise-loop-proc": ("validate_review_findings_v1",),
        "std/phase/review-revise-loop-proc": ("validate_review_findings_v1",),
    }
)
