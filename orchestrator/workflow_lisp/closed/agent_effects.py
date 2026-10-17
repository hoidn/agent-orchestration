"""Closed forms for agent allocation (`agent`) and agent turns (`agent_turn`).

Node shapes are the Plan A/Plan B interface contract:
`{"k":"perform","class":"agent","result":Agent,"repeat":"rerun","provider":<id>,"policy":{model?,effort?}}`
and `{"k":"perform","class":"agent_turn","result":<desc>,"repeat":"rerun","agent":<value>,
"origins":[<id>...],"prompt","inputs","dependencies","policy":{timeout_sec?},"contract"}`.
Dependencies: `builder.configuration_for` (owner provider rows), `effects._provider_effect_core`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from orchestrator.workflow_lisp.wcc.model import WccPerform

AGENT_DESCRIPTOR = {"kind": "primitive", "name": "Agent"}


def translate_agent_perform(builder: Any, perform: WccPerform, d: Any, env: Mapping[str, Any]) -> dict[str, Any]:
    if perform.perform_kind == "agent":
        return _translate_agent(builder, perform, d, env)
    return _translate_agent_turn(builder, perform, d, env)


def _provider_id(builder: Any, d: Any, extern_name: str) -> str:
    row = builder.configuration_for(d.source_program, d.owner)["providers"].get(extern_name)
    if not isinstance(row, Mapping) or not isinstance(row.get("provider_id"), str):
        raise ValueError(f"provider extern {extern_name!r} is missing from its owner")
    return row["provider_id"]


def _translate_agent(builder: Any, perform: WccPerform, d: Any, env: Mapping[str, Any]) -> dict[str, Any]:
    node = {
        "k": "perform",
        "class": "agent",
        "result": dict(AGENT_DESCRIPTOR),
        "repeat": "rerun",
        "provider": _provider_id(builder, d, perform.target_name),
        "policy": {name: builder.value(value, d, env) for name, value in perform.keyword_args},
    }
    node.update(builder.provenance(perform.metadata))
    return node


def _translate_agent_turn(builder: Any, perform: WccPerform, d: Any, env: Mapping[str, Any]) -> dict[str, Any]:
    from .effects import _provider_effect_core

    origins = sorted({_provider_id(builder, d, name) for name in perform.operation_payload["agent_origins"]})
    if not origins:
        raise ValueError("agent turn has no provider origin")
    agent_value, *inputs = perform.positional_args
    core, source_subjects = _provider_effect_core(builder, perform, d, env, tuple(inputs))
    core["policy"].pop("delivery", None)  # only the default composed delivery reaches here
    if set(core["policy"]) - {"timeout_sec"}:
        raise ValueError("agent turn policy must contain only timeout_sec")
    node = {
        "k": "perform",
        "class": "agent_turn",
        "result": builder.desc(perform.metadata.type_ref, d),
        "repeat": "rerun",
        "agent": builder.value(agent_value, d, env),
        "origins": origins,
        **core,
    }
    provenance = builder.provenance(perform.metadata)
    if source_subjects:
        provenance.setdefault("@", {})["source_map_subject"] = source_subjects
    node.update(provenance)
    builder.retain_generated_result_contract(node, perform, d)
    return node


def refuse_parallel_effects(tree: Mapping[str, Any]) -> None:
    """Refuse parallel workers that reach a disallowed effect through any callee.

    The closed tree is the one place where macro expansion, specialized helpers, ProcRef
    callees and child workflows are all explicit `call` edges. This shares the same
    transitive call-graph walk as the independent checker.
    """

    from orchestrator.contracts.closed_program.check_agents import find_parallel_effect
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
    from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan

    found = find_parallel_effect(tree, {"agent", "agent_turn", "provider_phased"})
    if found is None:
        return
    worker, _effect = found
    rule = "parallel_provider_boundary" if _effect.get("class") == "provider_phased" else "parallel_agent_boundary"
    path, line, column = worker["@"]["span"].rsplit(":", 2)
    position = SourcePosition(path=path, line=int(line), column=int(column), offset=0)
    raise LispFrontendCompileError((LispFrontendDiagnostic(
        code=rule,
        message=(
            "a parallel worker cannot reach a phased provider effect, including through called helpers or workflows"
            if rule == "parallel_provider_boundary"
            else "a parallel worker cannot allocate or turn an `Agent`, including through called helpers or workflows"
        ),
        span=SourceSpan(start=position, end=position),
        form_path=tuple(worker["@"]["form"]),
        phase="lowering",
    ),))
