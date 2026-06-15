"""Workflow Lisp entry-boundary publication policy helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from orchestrator.workflow.view_renderer import ViewRendererError, resolve_view_renderer

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourceSpan
from .syntax import ExpansionStack, SyntaxIdentifier, SyntaxKeyword, SyntaxList, SyntaxNode, syntax_identifier


ENTRY_PUBLICATION_POLICY_SCHEMA_VERSION = "workflow_lisp_entry_publication_policy.v1"
PUBLICATION_ROLE_REGISTRY_SCHEMA_VERSION = "workflow_lisp_publication_roles.v1"
ENTRY_PUBLICATION_REPORT_SCHEMA_VERSION = "workflow_lisp_entry_publication_report.v1"


@dataclass(frozen=True)
class EntryPublicationPolicyRow:
    row_id: str
    variant: str
    role: str
    renderer_id: str | None
    renderer_version: int | None
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class EntryPublicationPolicy:
    schema_version: str
    workflow_name: str
    form_path: tuple[str, ...]
    rows: tuple[EntryPublicationPolicyRow, ...]
    span: SourceSpan
    expansion_stack: ExpansionStack = ()


_PUBLICATION_ROLE_REGISTRY = {
    "schema_version": PUBLICATION_ROLE_REGISTRY_SCHEMA_VERSION,
    "roles": {
        "drain-summary": {
            "role": "drain-summary",
            "renderer_id": "canonical-json",
            "renderer_version": 1,
            "output_contract": {
                "kind": "relpath",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            },
            "authority_class": "public_artifact",
        }
    },
}


def resolve_publication_role_registry() -> Mapping[str, Mapping[str, object]]:
    return dict(_PUBLICATION_ROLE_REGISTRY["roles"])


def select_entry_publication_rows(census_payload: object) -> list[dict[str, object]]:
    if not isinstance(census_payload, Mapping):
        return []
    rows = census_payload.get("rows")
    if not isinstance(rows, Sequence):
        return []
    selected: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if row.get("consumer_lane") == "entry_publication" or row.get(
            "track_c_decision"
        ) == "RETIRE_TO_ENTRY_PUBLICATION":
            selected.append(dict(row))
    return selected


def classify_entry_publication_rows(
    *,
    workflow_name: str,
    return_union_name: str,
    return_variants: Sequence[str],
    selected_rows: Sequence[Mapping[str, object]],
    policy_rows: Sequence[Mapping[str, object] | EntryPublicationPolicyRow],
) -> dict[str, object]:
    del workflow_name
    del return_union_name
    publishable_variants = {
        _policy_variant_name(row)
        for row in policy_rows
        if _policy_variant_name(row) is not None
    }
    legal_rows: list[dict[str, object]] = []
    compatibility_reasons: list[dict[str, object]] = []
    for row in selected_rows:
        row_id = str(row.get("row_id", ""))
        row_variant = row.get("variant")
        if (
            row.get("typed_value_surface") == "terminal_result_variant"
            and row.get("value_kind") == "union_variant"
            and isinstance(row_variant, str)
            and row_variant in publishable_variants
        ):
            legal_rows.append(dict(row))
            continue
        compatibility_reasons.append(
            {
                "row_id": row_id,
                "reason": "field_level_publication_not_supported_in_c3",
            }
        )
    omitted_variants = [
        variant for variant in return_variants if variant not in publishable_variants
    ]
    return {
        "legal_rows": legal_rows,
        "compatibility_reasons": compatibility_reasons,
        "omitted_variants": omitted_variants,
    }


def serialize_entry_publication_report(
    *,
    target_family: str,
    workflow_name: str,
    source_census: Mapping[str, object],
    consumer_rendering_census: Mapping[str, object],
    publication_policy: Mapping[str, object],
    selected_c0_rows: Sequence[Mapping[str, object]],
    lowered_publications: Sequence[Mapping[str, object]],
    compatibility_reasons: Sequence[Mapping[str, object]],
    omitted_variants: Sequence[str],
    contract_isolation: Mapping[str, object],
    diagnostics: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    report_diagnostics = [dict(row) for row in diagnostics]
    return {
        "schema_version": ENTRY_PUBLICATION_REPORT_SCHEMA_VERSION,
        "status": "pass" if not report_diagnostics else "fail",
        "target_family": target_family,
        "workflow_name": workflow_name,
        "source_census": dict(source_census),
        "consumer_rendering_census": dict(consumer_rendering_census),
        "publication_policy": dict(publication_policy),
        "selected_c0_rows": [dict(row) for row in selected_c0_rows],
        "lowered_publications": [dict(row) for row in lowered_publications],
        "compatibility_reasons": [dict(row) for row in compatibility_reasons],
        "omitted_variants": list(omitted_variants),
        "contract_isolation": dict(contract_isolation),
        "diagnostics": report_diagnostics,
    }


def serialize_entry_publication_policy(
    policy: EntryPublicationPolicy | None,
) -> dict[str, object]:
    if policy is None:
        return {}
    return {
        "schema_version": policy.schema_version,
        "workflow_name": policy.workflow_name,
        "rows": [
            {
                "row_id": row.row_id,
                "variant": row.variant,
                "role": row.role,
                "renderer_id": row.renderer_id,
                "renderer_version": row.renderer_version,
            }
            for row in policy.rows
        ],
    }


def compatibility_reason_for_selected_row(
    row: Mapping[str, object],
    *,
    workflow_surface: str | None,
    is_entry_workflow: bool,
    return_kind: str | None,
) -> dict[str, object]:
    reason = "field_level_publication_not_supported_in_c3"
    if not is_entry_workflow:
        reason = "non_entry_workflow_not_publishable_in_c3"
    elif return_kind != "union":
        reason = "non_union_return_not_publishable_in_c3"
    elif (
        row.get("typed_value_surface") != "terminal_result_variant"
        or row.get("value_kind") != "union_variant"
        or not isinstance(row.get("variant"), str)
    ):
        reason = "whole_variant_typed_source_missing_in_c3"
    return {
        "row_id": str(row.get("row_id", "")),
        "u0_row_id": str(row.get("u0_row_id", "")),
        "workflow_surface": workflow_surface,
        "reason": reason,
    }


def parse_entry_publication_policy(
    policy_node: SyntaxNode,
    *,
    workflow_name: str,
) -> EntryPublicationPolicy:
    datum = policy_node.datum
    if not isinstance(datum, SyntaxList) or len(datum.items) != 2:
        _raise_policy_error(
            code="entry_publication_policy_invalid",
            message="`:publish` requires exactly one list of publication rows",
            span=policy_node.span,
            form_path=policy_node.form_path,
            expansion_stack=policy_node.expansion_stack,
        )
    keyword = datum.items[0]
    if not isinstance(keyword, SyntaxKeyword) or keyword.value != ":publish":
        _raise_policy_error(
            code="entry_publication_policy_invalid",
            message="workflow metadata clause must start with `:publish`",
            span=policy_node.span,
            form_path=policy_node.form_path,
            expansion_stack=policy_node.expansion_stack,
        )
    raw_rows = datum.items[1]
    if not isinstance(raw_rows, SyntaxList):
        _raise_policy_error(
            code="entry_publication_policy_invalid",
            message="`:publish` requires a list of publication rows",
            span=policy_node.span,
            form_path=policy_node.form_path,
            expansion_stack=policy_node.expansion_stack,
        )
    rows = tuple(
        _parse_policy_row(row, workflow_name=workflow_name)
        for row in raw_rows.items
    )
    return EntryPublicationPolicy(
        schema_version=ENTRY_PUBLICATION_POLICY_SCHEMA_VERSION,
        workflow_name=workflow_name,
        form_path=policy_node.form_path + (":publish",),
        rows=rows,
        span=policy_node.span,
        expansion_stack=policy_node.expansion_stack,
    )


def validate_entry_publication_policy(
    policy: EntryPublicationPolicy,
    *,
    workflow_name: str,
    return_union_variants: Sequence[str] | None,
    selected_entry_workflow_name: str | None = None,
    exported_workflow_names: Sequence[str] = (),
) -> None:
    if selected_entry_workflow_name is not None:
        selected_names = {
            selected_entry_workflow_name,
            selected_entry_workflow_name.rsplit("::", 1)[-1],
        }
        if workflow_name not in selected_names and workflow_name.rsplit("::", 1)[-1] not in selected_names:
            _raise_policy_error(
                code="entry_publication_not_entrypoint",
                message=(
                    f"workflow `{workflow_name}` may only declare `:publish` when selected as "
                    "the top-level entry workflow"
                ),
                span=policy.span,
                form_path=policy.form_path,
                expansion_stack=policy.expansion_stack,
            )
    raw_export_names = set(exported_workflow_names)
    export_names = raw_export_names | {
        name.rsplit("::", 1)[-1] for name in raw_export_names if isinstance(name, str)
    }
    if export_names and workflow_name not in export_names and workflow_name.rsplit("::", 1)[-1] not in export_names:
        _raise_policy_error(
            code="entry_publication_not_entrypoint",
            message=f"workflow `{workflow_name}` may only declare `:publish` when exported as an entry workflow",
            span=policy.span,
            form_path=policy.form_path,
            expansion_stack=policy.expansion_stack,
        )
    if return_union_variants is None:
        _raise_policy_error(
            code="entry_publication_return_not_union",
            message=f"workflow `{workflow_name}` must return a union to use `:publish`",
            span=policy.span,
            form_path=policy.form_path,
            expansion_stack=policy.expansion_stack,
        )

    role_registry = resolve_publication_role_registry()
    seen_rows: set[tuple[str, str]] = set()
    allowed_variants = set(return_union_variants)
    for row in policy.rows:
        if row.variant not in allowed_variants:
            _raise_policy_error(
                code="entry_publication_variant_unknown",
                message=f"`:publish` row references unknown variant `{row.variant}`",
                span=row.span,
                form_path=row.form_path,
                expansion_stack=row.expansion_stack,
            )
        row_key = (row.variant, row.role)
        if row_key in seen_rows:
            _raise_policy_error(
                code="entry_publication_duplicate_row",
                message=f"duplicate `:publish` row for variant `{row.variant}` and role `{row.role}`",
                span=row.span,
                form_path=row.form_path,
                expansion_stack=row.expansion_stack,
            )
        seen_rows.add(row_key)
        role_descriptor = role_registry.get(row.role)
        if role_descriptor is None:
            _raise_policy_error(
                code="entry_publication_role_unknown",
                message=f"`:publish` row references unknown role `{row.role}`",
                span=row.span,
                form_path=row.form_path,
                expansion_stack=row.expansion_stack,
            )
        renderer_id = row.renderer_id or str(role_descriptor["renderer_id"])
        renderer_version = row.renderer_version or int(role_descriptor["renderer_version"])
        try:
            resolve_view_renderer(renderer_id, renderer_version)
        except ViewRendererError as exc:
            _raise_policy_error(
                code="entry_publication_renderer_unknown",
                message=str(exc),
                span=row.span,
                form_path=row.form_path,
                expansion_stack=row.expansion_stack,
            )


def _parse_policy_row(
    row_node: object,
    *,
    workflow_name: str,
) -> EntryPublicationPolicyRow:
    if not isinstance(row_node, SyntaxList):
        span = getattr(row_node, "span", None)
        form_path = getattr(row_node, "form_path", ())
        expansion_stack = getattr(row_node, "expansion_stack", ())
        if span is None:
            raise TypeError("publication rows must carry spans")
        _raise_policy_error(
            code="entry_publication_policy_invalid",
            message="`:publish` rows must be lists of `(VARIANT :as role)`",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if len(row_node.items) not in {3, 5}:
        _raise_policy_error(
            code="entry_publication_policy_invalid",
            message="`:publish` rows must be `(VARIANT :as role)` or `(VARIANT :as role :renderer renderer-id)`",
            span=row_node.span,
            form_path=row_node.form_path,
            expansion_stack=row_node.expansion_stack,
        )
    variant_identifier = syntax_identifier(row_node.items[0])
    if variant_identifier is None:
        _raise_policy_error(
            code="entry_publication_policy_invalid",
            message="publication variant must be a symbol",
            span=row_node.items[0].span,
            form_path=row_node.form_path,
            expansion_stack=row_node.items[0].expansion_stack,
        )
    as_keyword = row_node.items[1]
    if not isinstance(as_keyword, SyntaxKeyword) or as_keyword.value != ":as":
        _raise_policy_error(
            code="entry_publication_policy_invalid",
            message="publication rows must use `:as <role>`",
            span=row_node.span,
            form_path=row_node.form_path,
            expansion_stack=row_node.expansion_stack,
        )
    role_identifier = syntax_identifier(row_node.items[2])
    if role_identifier is None:
        _raise_policy_error(
            code="entry_publication_policy_invalid",
            message="publication role must be a symbol",
            span=row_node.items[2].span,
            form_path=row_node.form_path,
            expansion_stack=row_node.items[2].expansion_stack,
        )
    renderer_id = None
    renderer_version = None
    if len(row_node.items) == 5:
        renderer_keyword = row_node.items[3]
        if not isinstance(renderer_keyword, SyntaxKeyword) or renderer_keyword.value != ":renderer":
            _raise_policy_error(
                code="entry_publication_policy_invalid",
                message="only `:renderer` overrides are supported in `:publish` rows",
                span=row_node.span,
                form_path=row_node.form_path,
                expansion_stack=row_node.expansion_stack,
            )
        renderer_identifier = syntax_identifier(row_node.items[4])
        if renderer_identifier is None:
            _raise_policy_error(
                code="entry_publication_policy_invalid",
                message="renderer override must be a symbol",
                span=row_node.items[4].span,
                form_path=row_node.form_path,
                expansion_stack=row_node.items[4].expansion_stack,
            )
        renderer_id = renderer_identifier.resolved_name
    variant = variant_identifier.resolved_name
    role = role_identifier.resolved_name
    return EntryPublicationPolicyRow(
        row_id=f"publish.{_slug(workflow_name)}.{variant.lower()}.{_slug(role)}",
        variant=variant,
        role=role,
        renderer_id=renderer_id,
        renderer_version=renderer_version,
        span=row_node.span,
        form_path=row_node.form_path,
        expansion_stack=row_node.expansion_stack,
    )


def _policy_variant_name(row: Mapping[str, object] | EntryPublicationPolicyRow) -> str | None:
    if isinstance(row, EntryPublicationPolicyRow):
        return row.variant
    variant = row.get("variant")
    return variant if isinstance(variant, str) else None


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-")


def _raise_policy_error(
    *,
    code: str,
    message: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: ExpansionStack = (),
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )
