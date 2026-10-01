"""Closed forms for command effects and located gaps for the remaining effects."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from orchestrator.workflow_lisp.build_manifest_io import _cli_request_diagnostic
from orchestrator.workflow_lisp.command_boundaries import (
    CertifiedAdapterBinding,
    ExternalToolBinding,
    _environment_span,
)
from orchestrator.workflow_lisp.contracts import derive_prompt_guided_structured_result_contract
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from orchestrator.workflow_lisp.wcc.model import WccPerform

def require_command_closures(
    bindings: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding],
    *,
    manifest_path: Path | None,
) -> None:
    """Refuse each supplied command declaration without an explicit closure."""

    missing = [name for name, binding in sorted(bindings.items()) if binding.closure is None]
    if not missing:
        return
    diagnostics = []
    for name in missing:
        message = f"command boundary {name!r} must declare a closure (an empty closure is allowed)"
        if manifest_path is not None:
            diagnostics.append(
                _cli_request_diagnostic(
                    code="command_boundary_closure_missing",
                    message=message,
                    path=manifest_path,
                    notes=(f"boundary={name}",),
                )
            )
        else:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="command_boundary_closure_missing",
                    message=message,
                    span=_environment_span(),
                    notes=(f"boundary={name}",),
                    phase="lowering",
                )
            )
    raise LispFrontendCompileError(tuple(diagnostics))


def translate_perform(builder: Any, perform: WccPerform, d: Any, env: Mapping[str, Any]) -> dict[str, Any]:
    if perform.perform_kind != "command_result":
        forms = {
            "provider_result": "provider-result",
            "run_ref": "run-ref",
            "request_input": "request-input",
            "trial": "trial",
            "run_provider_phase": "run-provider-phase",
            "produce_one_of": "produce-one-of",
            "resume_or_start": "resume-or-start",
            "finalize_selected_item": "finalize-selected-item",
            "resource_transition": "resource-transition",
            "materialize_view": "materialize-view",
            "with_live_providers": "with-live-providers",
            "with_live_provider_peers": "with-live-provider-peers",
        }
        form = forms.get(perform.perform_kind)
        if form is None:
            raise ValueError(f"unknown WCC effect kind {perform.perform_kind!r}")
        raise builder.gap(
            form,
            f"effect kind {perform.perform_kind!r} has no closed form in this task",
            perform,
        )

    payload = perform.operation_payload
    if not isinstance(payload, Mapping):
        raise ValueError("command_result WCC payload is missing")
    boundary = payload.get("adapter_name") or perform.target_name
    binding = builder.command_binding_for(d.source_program, d.owner, boundary)
    if binding is None:
        raise ValueError(f"command boundary {boundary!r} is missing from its owner")
    if binding.closure is None:
        raise ValueError(f"command boundary {boundary!r} reached translation without a required closure")

    source_program = d.source_program
    scope = builder.configuration_for(source_program, d.owner)
    command_rows = scope["commands"]
    config_row = command_rows.get(boundary)
    if not isinstance(config_row, Mapping):
        raise ValueError(f"command boundary {boundary!r} has no canonical owner configuration row")

    result_type = builder.desc(perform.metadata.type_ref, d)
    return_spec = payload.get("return_spec")
    guidance = getattr(return_spec, "guidance", None)
    contract = derive_prompt_guided_structured_result_contract(
        perform.metadata.type_ref,
        workflow_name=d.canonical,
        step_id="effect",
        span=perform.metadata.source_span,
        form_path=perform.metadata.form_path,
        guidance=guidance,
        type_env=d.type_env,
    )
    contract_payload = dict(contract.payload)
    contract_payload.pop("path", None)
    source_subjects: list[dict[str, Any]] = []

    def strip_field_rows(rows: Any, path: tuple[str, ...]) -> None:
        if not isinstance(rows, list):
            return
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            for key in ("source_map_subject", "source_map_subjects_by_variant"):
                if key in row:
                    source_subjects.append(
                        {"path": [*path, str(index)], "field": key, "value": row.pop(key)}
                    )

    # These are the exact owners emitted by contracts.py. Keep authored
    # variant-name maps and arbitrary guidance/example payloads untouched.
    strip_field_rows(contract_payload.get("fields"), ("fields",))
    strip_field_rows(contract_payload.get("shared_fields"), ("shared_fields",))
    variants = contract_payload.get("variants")
    if isinstance(variants, Mapping):
        for variant_name, variant in variants.items():
            if isinstance(variant, Mapping):
                strip_field_rows(variant.get("fields"), ("variants", str(variant_name), "fields"))
    contract_value = {"kind": contract.contract_kind, "payload": contract_payload}

    effect: dict[str, Any] = {
        "k": "perform",
        "class": "command",
        "result": result_type,
        "repeat": "never" if binding.must_not_repeat else "rerun",
        "boundary": boundary,
        "command": list(binding.stable_command),
        "closure": config_row["closure"],
        "contract": contract_value,
    }

    if isinstance(binding, CertifiedAdapterBinding):
        supplied = dict(payload.get("adapter_inputs", ()))
        selected_rows = [row for row in binding.input_signature if row.name in supplied]
        unknown = set(supplied) - {row.name for row in binding.input_signature}
        if unknown:
            raise ValueError(f"certified adapter inputs are undeclared: {sorted(unknown)!r}")
        effect["argv"] = []
        effect["document"] = [
            [row.transport_key, builder.value(supplied[row.name], d, env)]
            for row in selected_rows
        ]
    else:
        tokens = tuple(binding.stable_command)
        actual_tokens = tuple(
            item.value
            for item in perform.positional_args[: len(tokens)]
            if hasattr(item, "value")
        )
        if len(actual_tokens) != len(tokens) or actual_tokens != tokens:
            raise ValueError(f"command_result for {boundary!r} changed its stable command tokens")
        effect["argv"] = [
            builder.value(item, d, env) for item in perform.positional_args[len(tokens) :]
        ]

    provenance = builder.provenance(perform.metadata)
    if source_subjects:
        # The subject is diagnostic provenance and is removed by program_digest.
        provenance.setdefault("@", {})["source_map_subject"] = source_subjects
    effect.update(provenance)
    return effect
