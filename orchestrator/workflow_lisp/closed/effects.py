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


def _result_contract(
    builder: Any,
    perform: WccPerform,
    d: Any,
    *,
    descriptor_projector: Any | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Project the shared structured-result contract used by command/provider effects."""

    return_spec = (perform.operation_payload or {}).get("return_spec")

    def default_descriptor_projector(nested_type: Any) -> Any:
        return builder.desc(nested_type, d)

    project_descriptor = descriptor_projector or default_descriptor_projector
    contract = derive_prompt_guided_structured_result_contract(
        perform.metadata.type_ref,
        workflow_name=d.canonical,
        step_id="effect",
        span=perform.metadata.source_span,
        form_path=perform.metadata.form_path,
        guidance=getattr(return_spec, "guidance", None),
        type_env=d.type_env,
        descriptor_projector=project_descriptor,
    )
    payload = dict(contract.payload)
    payload.pop("path", None)
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

    # These schema-owned diagnostics are removed for a source-free effect contract;
    # authored variant-name maps and arbitrary guidance payloads remain intact.
    strip_field_rows(payload.get("fields"), ("fields",))
    strip_field_rows(payload.get("shared_fields"), ("shared_fields",))
    variants = payload.get("variants")
    if isinstance(variants, Mapping):
        for variant_name, variant in variants.items():
            if isinstance(variant, Mapping):
                strip_field_rows(variant.get("fields"), ("variants", str(variant_name), "fields"))
    result = {"kind": contract.contract_kind, "payload": payload}
    return result, source_subjects


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
    if perform.perform_kind == "provider_result":
        return _translate_provider_result(builder, perform, d, env)
    if perform.perform_kind == "run_ref":
        return _translate_run_ref(builder, perform, d, env)
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
    contract_value, source_subjects = _result_contract(builder, perform, d)

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
    builder.retain_generated_result_contract(effect, perform, d)
    return effect


def _translate_provider_result(
    builder: Any,
    perform: WccPerform,
    d: Any,
    env: Mapping[str, Any],
) -> dict[str, Any]:
    """Translate one supported provider result from its retained WCC payload."""

    from orchestrator.workflow_lisp.prompts import PromptApplicationExpr
    from orchestrator.workflow_lisp.type_env import PathTypeRef
    from orchestrator.workflow_lisp.typed_prompt_inputs import select_prompt_fragment_renderer
    from orchestrator.workflow.prompt_fragment_contract import _RENDERERS_BY_KIND
    from orchestrator.workflow.view_renderer import ViewRendererError, resolve_default_view_renderer

    payload = perform.operation_payload
    if not isinstance(payload, Mapping):
        raise ValueError("provider_result WCC payload is missing")
    if payload.get("session_artifact") is not None:
        raise builder.gap("provider-result", "provider session artifacts are outside the closed provider surface", perform)
    if payload.get("context_expr") is not None or payload.get("capture_context") is not None:
        raise builder.gap("provider-result", "provider context capture is outside the closed provider surface", perform)
    if payload.get("materialization_attempts") is not None:
        raise builder.gap("provider-result", "provider materialization attempts are outside the closed provider surface", perform)

    owner_config = builder.configuration_for(d.source_program, d.owner)
    provider_row = owner_config["providers"].get(perform.target_name)
    if not isinstance(provider_row, Mapping) or not isinstance(provider_row.get("provider_id"), str):
        raise ValueError(f"provider extern {perform.target_name!r} is missing from its owner")

    prompt_application = payload.get("prompt_application")
    if prompt_application is None:
        prompt = owner_config["prompts"].get(perform.prompt_name)
        if not isinstance(prompt, Mapping):
            raise ValueError(f"prompt extern {perform.prompt_name!r} is missing from its owner")
        prompt_payload = dict(prompt)
    elif isinstance(prompt_application, PromptApplicationExpr):
        declaration = prompt_application.prompt.declaration
        placeholder_names = declaration.template.placeholder_names
        fills = []
        for slot, fill in zip(
            prompt_application.prompt.slots,
            prompt_application.fills,
            strict=True,
        ):
            kind = slot.declaration.kind.value
            type_ref = fill.static_type_ref
            if type_ref is None:
                raise ValueError(f"prompt fill {fill.name!r} has no retained type")
            value = builder.value(fill.value_expr, d, env)
            renderer_id = None if kind == "doc" else _RENDERERS_BY_KIND.get(kind)
            if fill.renderer_id is not None and kind not in {"doc", "text"}:
                renderer_id = fill.renderer_id
            output_role = slot.declaration.output_role.value
            fills.append(
                {
                    "name": fill.name,
                    "kind": kind,
                    "type": builder.desc(type_ref, d),
                    "value": value,
                    "renderer_id": renderer_id,
                    "output_role": output_role,
                    "placeholder_ordinals": [
                        index for index, name in enumerate(placeholder_names) if name == fill.name
                    ],
                }
            )
        prompt_payload = {"template": declaration.template.text, "fills": fills}
    else:
        raise ValueError("provider prompt application has no retained semantic owner")
    dependencies = _closed_prompt_dependencies(
        builder,
        payload.get("prompt_dependencies"),
        d,
        env,
    )

    input_rows = []
    input_names = _unique_provider_input_names(perform.positional_args, d)
    for value, name in zip(perform.positional_args, input_names, strict=True):
        type_ref = value.metadata.type_ref
        renderer_id = (
            "posix-path-line"
            if isinstance(type_ref, PathTypeRef)
            else select_prompt_fragment_renderer(
                type_ref,
                kind="value",
                target_dsl_version=getattr(d.type_env, "target_dsl_version", None),
            )
        )
        if renderer_id is None:
            try:
                renderer_id = resolve_default_view_renderer("any_pure_value").renderer_id
            except ViewRendererError as exc:
                raise builder.gap("provider-result", f"provider input {name!r} has no supported renderer", perform) from exc
            if renderer_id != "canonical-json":
                raise builder.gap("provider-result", f"provider input {name!r} has no supported renderer", perform)
        input_rows.append([name, renderer_id, builder.value(value, d, env)])

    policy: dict[str, Any] = {}
    for field_name in ("model", "effort", "timeout_sec"):
        value = payload.get(field_name)
        if value is not None:
            policy[field_name] = builder.value(value, d, env)
    delivery = payload.get("delivery")
    if delivery is not None:
        delivery_value = builder.value(delivery, d, env)
        if delivery_value.get("v") == "phased":
            raise builder.gap("provider-result", "phased provider delivery is outside the closed provider surface", perform)
        policy["delivery"] = delivery_value

    contract, source_subjects = _result_contract(builder, perform, d)
    effect = {
        "k": "perform",
        "class": "provider",
        "result": builder.desc(perform.metadata.type_ref, d),
        "repeat": "rerun",
        "provider": provider_row["provider_id"],
        "prompt": prompt_payload,
        "inputs": input_rows,
        "dependencies": dependencies,
        "policy": policy,
        "contract": contract,
    }
    provenance = builder.provenance(perform.metadata)
    if source_subjects:
        provenance.setdefault("@", {})["source_map_subject"] = source_subjects
    effect.update(provenance)
    builder.retain_generated_result_contract(effect, perform, d)
    return effect


def _provider_input_name(value: Any, index: int, d: Any) -> str:
    from orchestrator.workflow_lisp.wcc.model import WccFieldAccessAtom, WccNameAtom, WccPhaseTargetAtom

    if isinstance(value, WccNameAtom):
        return d.ref(value.name)
    if isinstance(value, WccFieldAccessAtom) and value.fields:
        return value.fields[-1]
    if isinstance(value, WccPhaseTargetAtom):
        from orchestrator.workflow_lisp.phase import IMPLEMENTATION_ATTEMPT_TARGET_FIELDS

        return IMPLEMENTATION_ATTEMPT_TARGET_FIELDS.get(
            value.target_name,
            value.target_name.replace("-", "_"),
        )
    return f"inputs__{index}"


def _unique_provider_input_names(values: Any, d: Any) -> list[str]:
    """Keep preferred input labels where possible and suffix only collisions."""

    preferred = [_provider_input_name(value, index, d) for index, value in enumerate(values)]
    reserved = set(preferred)
    assigned: set[str] = set()
    next_suffix: dict[str, int] = {}
    names: list[str] = []
    for name in preferred:
        if name not in assigned:
            assigned.add(name)
            names.append(name)
            continue
        suffix = next_suffix.get(name, 2)
        while f"{name}__{suffix}" in reserved:
            suffix += 1
        unique_name = f"{name}__{suffix}"
        reserved.add(unique_name)
        assigned.add(unique_name)
        next_suffix[name] = suffix + 1
        names.append(unique_name)
    return names


def _closed_prompt_dependencies(builder: Any, payload: Any, d: Any, env: Mapping[str, Any]):
    if payload is None:
        return None
    dependencies = {"required": [], "optional": [], "position": payload.position, "instruction": payload.instruction}
    for row in payload.rows:
        if row.role not in {"required", "optional"}:
            raise ValueError("provider prompt dependency role is invalid")
        dependencies[row.role].append(builder.value(row.value, d, env))
    return dependencies


def _translate_run_ref(
    builder: Any,
    perform: WccPerform,
    d: Any,
    env: Mapping[str, Any],
) -> dict[str, Any]:
    from orchestrator.workflow.run_ref.config import PathProgram
    from orchestrator.workflow_lisp.wcc.model import WccRunRefPayload

    payload = perform.operation_payload
    if not isinstance(payload, WccRunRefPayload):
        raise ValueError("run-ref perform has no retained static configuration")
    if not isinstance(payload.program, PathProgram):
        raise builder.gap("run-ref", "bundle-mode run references are outside the closed surface", perform)
    origin = getattr(perform.metadata.type_ref, "run_ref_origin", None)
    if not isinstance(origin, tuple) or len(origin) != 2 or not isinstance(origin[1], tuple):
        raise ValueError("run-ref perform has no retained ordered input TypeRefs")
    if tuple(name for name, _type_ref in origin[1]) != tuple(name for name, _value in perform.keyword_args):
        raise ValueError("run-ref WCC inputs disagree with the retained result origin")

    node = {
        "k": "perform",
        "class": "run_ref",
        "result": {},
        "repeat": "rerun",
        "config": "",
        "inputs": [
            [name, builder.value(value, d, env)]
            for name, value in perform.keyword_args
        ],
    }
    node.update(builder.provenance(perform.metadata))
    producer = builder.register_run_ref(perform, d, node)
    node["result"] = builder.desc(
        perform.metadata.type_ref,
        d,
        run_ref_producer=producer,
    )
    return node
