"""Effect nodes of the closed program (P3): each carries what its performer needs, resolved at build time.

A command carries its boundary, its stable command (whose declared files the
evaluator binds into the resolved input), its argv tail or its adapter document,
its contract and its repeat rule. A provider carries its provider id, its prompt
(an asset path, or a `defprompt` template with its fills), its typed prompt
inputs with the names and renderers lowering gives them, its prompt
dependencies, its policy and its contract. A run reference carries the runtime's static
configuration and its named inputs.
"""

from __future__ import annotations

import base64
import functools
import posixpath
from typing import Any

from orchestrator.workflow.run_ref.config import (
    PathProgram,
    ReferenceBinding,
    RunRefInput,
    build_run_ref_static_config,
    encode_run_ref_static_config,
)
from orchestrator.workflow.run_ref.contracts import compute_compiler_runtime_identity
from orchestrator.workflow.trial.config import TrialArmStaticConfig, build_trial_static_config, encode_trial_static_config
from orchestrator.workflow.view_renderer import resolve_default_view_renderer
from orchestrator.workflow_lisp.contracts import derive_prompt_guided_structured_result_contract
from orchestrator.workflow_lisp.wcc import model as w

_UNSUPPORTED_PROVIDER_PARTS = frozenset({"context_expr", "session_artifact", "capture_context"})


def translate_perform(builder: Any, perform: w.WccPerform, d: Any, env: dict[str, Any]) -> dict[str, Any]:
    from .closed import ClosedProgramGap

    kind = perform.perform_kind
    node = {"k": "perform", "result": d.desc(perform.metadata.type_ref)}
    if kind == "command_result":
        return {**node, **_command(builder, perform, d, env)}
    if kind == "provider_result":
        return {**node, **_provider(builder, perform, d, env)}
    if kind == "request_input":
        return {**node, "class": "request_input", "question": builder.value(perform.positional_args[0], d, env)}
    if kind == "run_ref":
        return {**node, **_run_ref(builder, perform, d, env)}
    if kind == "trial":
        return {**node, **_trial(builder, perform, d, env)}
    raise ClosedProgramGap("P3", f"effect class `{kind}` has no performer in the spike")


@functools.cache
def _compiler_runtime_identity() -> str:
    return compute_compiler_runtime_identity().digest


def _run_ref(builder: Any, perform: w.WccPerform, d: Any, env: dict[str, Any]) -> dict[str, Any]:
    """A run reference: the runtime's static configuration, built here as lowering builds it except that
    each input is the reference `inputs.<name>`, which the coordinator resolves against the input values."""

    from .closed import ClosedProgramGap

    payload = perform.operation_payload
    if not isinstance(payload.program, PathProgram):
        raise ClosedProgramGap("P3", "a bundle-mode run-ref needs the build's capsule, which the spike does not build")
    config = _run_ref_config(builder, payload)
    values = dict(perform.keyword_args)
    return {"class": "run_ref", "config": base64.b64encode(encode_run_ref_static_config(config)).decode("ascii"),
            "inputs": [[name, builder.value(values[name], d, env)] for name, _ in payload.input_type_descriptors],
            "repeat": "rerun"}


def _run_ref_config(builder: Any, payload: Any) -> Any:
    rows = tuple(RunRefInput(name=name, type_descriptor=descriptor, binding=ReferenceBinding(f"inputs.{name}"))
                 for name, descriptor in payload.input_type_descriptors)
    return build_run_ref_static_config(
        compiler_runtime_identity_digest=_compiler_runtime_identity(), site_digest=payload.site_digest,
        source=payload.source, program=payload.program, inputs=rows, result_descriptor=payload.result_descriptor,
        result_digest=payload.result_digest, target_dsl_version=builder.typed.target,
    )


def _trial(builder: Any, perform: w.WccPerform, d: Any, env: dict[str, Any]) -> dict[str, Any]:
    """A trial: the runtime's static configuration, built as lowering builds it, each arm a run reference whose
    inputs are `inputs.<name>`; its dynamic inputs by keyword. The arms' capsule is the coordinator's."""

    payload = perform.operation_payload
    arms = tuple(TrialArmStaticConfig(arm_id=arm.arm_id, run_ref=_run_ref_config(builder, arm.run_ref))
                 for arm in payload.arms)
    config = build_trial_static_config(
        compiler_runtime_identity_digest=_compiler_runtime_identity(), site_digest=payload.site_digest, arms=arms,
        reps=payload.reps, max_concurrency=payload.max_concurrency, evaluation=payload.evaluation,
        budget=payload.budget, result_descriptor=payload.result_descriptor, result_digest=payload.result_digest,
        target_dsl_version=builder.typed.target,
    )
    values = dict(perform.keyword_args)
    keywords = [(arm.arm_id, name, keyword) for arm in payload.arms for name, keyword in arm.input_keywords]
    return {"class": "trial", "config": base64.b64encode(encode_trial_static_config(config)).decode("ascii"),
            "arm_inputs": [list(row) for row in keywords],
            "inputs": [[keyword, builder.value(values[keyword], d, env)] for _, _, keyword in keywords],
            "repeat": "rerun"}


def _contract(result_type: Any, d: Any, return_spec: Any) -> dict[str, Any]:
    """The output contract of the result type, derived as lowering derives it, without its path."""

    contract = derive_prompt_guided_structured_result_contract(
        result_type, workflow_name=d.canonical, step_id="effect", type_env=d.type_env,
        guidance=getattr(return_spec, "guidance", None),
    )
    return {"kind": contract.contract_kind, "payload": {k: v for k, v in contract.payload.items() if k != "path"}}


def _command(builder: Any, perform: w.WccPerform, d: Any, env: dict[str, Any]) -> dict[str, Any]:
    from .closed import ClosedProgramGap

    payload = perform.operation_payload
    boundary = payload.get("adapter_name") or perform.target_name
    binding = builder.typed.command_boundaries[boundary]
    stable = list(binding.stable_command)
    if builder.closure == "strict" and boundary not in builder.closures:
        raise ClosedProgramGap("closure", f"command boundary `{boundary}` declares no implementation closure "
                                          "(build option `strict`)")
    node = {"class": "command", "boundary": boundary, "command": stable, "closure": builder.closures.get(boundary),
            "contract": _contract(perform.metadata.type_ref, d, payload.get("return_spec")),
            "repeat": "never" if boundary in builder.no_repeat else "rerun"}
    if payload.get("adapter_name") is None:
        return {**node, "argv": [builder.value(a, d, env) for a in perform.positional_args[len(stable):]]}
    if binding.invocation_protocol not in (None, "json_object_positional_arg"):
        raise ClosedProgramGap("P3", f"adapter protocol `{binding.invocation_protocol}` has no performer in the spike")
    # A certified adapter receives one JSON object, its fields in the order of the adapter's signature.
    inputs = dict(payload["adapter_inputs"])
    document = [[f.transport_key, builder.value(inputs[f.name], d, env)] for f in binding.input_signature if f.name in inputs]
    return {**node, "argv": [], "document": document}


def _provider(builder: Any, perform: w.WccPerform, d: Any, env: dict[str, Any]) -> dict[str, Any]:
    from .closed import ClosedProgramGap

    payload = perform.operation_payload
    unsupported = sorted(set(payload) & _UNSUPPORTED_PROVIDER_PARTS)
    if unsupported:
        raise ClosedProgramGap("P3", f"provider payload parts {unsupported} have no closed form in the spike")
    policy = {key: builder.value(payload[key], d, env) for key in
              ("model", "effort", "delivery", "materialization_attempts", "timeout_sec") if key in payload}
    inputs = [[_input_name(a), _renderer(d.desc(a.metadata.type_ref)), builder.value(a, d, env)]
              for a in perform.positional_args]
    return {"class": "provider", "provider": builder.typed.externs[perform.target_name].provider_id,
            "prompt": _prompt(builder, perform, d, env), "inputs": inputs, "policy": policy,
            "dependencies": _dependencies(builder, payload.get("prompt_dependencies"), d, env),
            "contract": _contract(perform.metadata.type_ref, d, payload.get("return_spec")), "repeat": "rerun"}


def _input_name(atom: Any) -> str:
    """The name lowering gives a typed prompt input: the last field read, or the variable's name."""

    if isinstance(atom, w.WccFieldAccessAtom) and atom.fields:
        return atom.fields[-1]
    if isinstance(atom, w.WccNameAtom) and not atom.name.startswith("__"):
        return atom.name
    return "inputs"


def _renderer(desc: dict[str, Any]) -> str:
    return resolve_default_view_renderer("path_value" if desc["kind"] == "path" else "any_pure_value").renderer_id


def _prompt(builder: Any, perform: w.WccPerform, d: Any, env: dict[str, Any]) -> str | dict[str, Any]:
    """An asset prompt: its path, relative to the entry module as the flat route reads it.
    A `defprompt` application: its template and its fills, each with its renderer."""

    from .closed import ClosedProgramGap

    application = perform.operation_payload.get("prompt_application")
    if application is None:
        path = builder.typed.externs[perform.prompt_name].path
        return posixpath.normpath(posixpath.join(builder.typed.entry_dir, path))
    if any(fill.renderer_id is None for fill in application.fills):
        raise ClosedProgramGap("P3", "a document prompt slot has no closed form in the spike")
    return {"template": application.prompt.declaration.template.text,
            "fills": [[f.name, f.renderer_id, builder.value(f.value_expr, d, env)] for f in application.fills]}


def _dependencies(builder: Any, spec: Any, d: Any, env: dict[str, Any]) -> dict[str, Any] | None:
    """Prompt dependencies: workspace files whose contents the prompt carries (and the resolved input binds)."""

    if spec is None:
        return None
    rows = {"required": [], "optional": []}
    for row in spec.rows:
        rows[row.role].append(builder.value(row.value, d, env))
    return {**rows, "position": spec.position, "instruction": spec.instruction}
