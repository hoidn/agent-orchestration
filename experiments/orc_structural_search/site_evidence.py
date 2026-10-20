"""Closed provider allocation and candidate-local perform evidence, without branch claims."""

import re
from collections.abc import Mapping
from pathlib import Path

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.contracts.closed_program.node_walk import _ast_nodes
from orchestrator.workflow.evaluated.machine import site_nodes
from experiments.orc_structural_search.candidates import compile_candidate
from experiments.orc_structural_search.metrics import is_python, metric_definitions, mutable_source
from experiments.orc_structural_search.records import UNAVAILABLE
from experiments.orc_structural_search.record_normalization import _module_names, _named_definitions


def checked_program(root: Path, build_key: str) -> ClosedProgram:
    path = root / '.orchestrate/build' / build_key / 'closed_program.json'
    return ClosedProgram.from_artifact(path.read_text())


def planned_sites(program: ClosedProgram) -> list[dict]:
    return [{"identity": identity, "effect_class": node["class"]}
            for identity, node in site_nodes(program).items()]


def _owner(definition, names, own_module):
    key = definition.get("key", [])
    if len(key) < 3 or not isinstance(key[2], str):
        raise ValueError("unresolved_or_local_definition_owner")
    module, kind, declaration = key[:3]
    if module == own_module and declaration in names:
        return names[declaration]
    return f"{kind}:{module}::{declaration}"


def _policy(node):
    policy = node.get("policy", {})
    values = {key: policy.get(key, {}).get("v") if policy.get(key, {}).get("k") == "lit" else None
              for key in ("model", "effort")}
    if not all(isinstance(value, str) and value for value in values.values()):
        raise ValueError("unresolved_model_or_effort")
    return {"provider": node["provider"], **values}


def _definition_owners(program, names, own_module):
    reachable = {id(node) for node in site_nodes(program).values()}
    result = {}
    for canonical, definition in program.tree["definitions"].items():
        nodes = _ast_nodes(definition["body"])
        if any(id(node) in reachable and node.get("class") == "provider" for node in nodes):
            result[canonical] = _owner(definition, names, own_module)
    if len(set(result.values())) != len(result):
        raise ValueError("ambiguous_specialized_definition_owner")
    return result


def _expand_signature(body, prefix, definitions, owners, active):
    result, calls, providers = {}, 0, 0
    for node in _ast_nodes(body):
        if node.get("k") == "perform" and node.get("class") == "provider":
            result[f"{prefix} / provider{providers}"] = _policy(node)
            providers += 1
        if node.get("k") != "call":
            continue
        callee = node["callee"]
        if callee in active:
            raise ValueError("recursive_definition_owner")
        owner = owners.get(callee)
        if owner is not None:
            path = f"{prefix} / call{calls}:{owner}"
            result.update(_expand_signature(definitions[callee]["body"], path, definitions, owners, active | {callee}))
        calls += 1
    return result


def _signature(program, names, own_module):
    owners = _definition_owners(program, names, own_module)
    # Helpers without their own provider may still call a provider-bearing helper.
    for canonical, definition in program.tree["definitions"].items():
        owners.setdefault(canonical, _owner(definition, names, own_module))
    return _expand_signature(program.tree["body"], program.tree["entry"], program.tree["definitions"], owners, set())


def candidate_evidence(root, config, *, runtime, compiled=None):
    result = {"allocation_signature": UNAVAILABLE, "allocation_signature_reason": "generic_command_has_no_closed_program",
              "planned_perform_sites": UNAVAILABLE}
    if is_python(config):
        return result
    try:
        compiled = compiled or compile_candidate(root, config, runtime=runtime)
        if compiled.status != "accepted":
            raise ValueError("candidate_does_not_compile")
        program = checked_program(root, compiled.build_key)
        result["planned_perform_sites"] = planned_sites(program)
        names = (_module_names(_named_definitions(mutable_source(root, config), metric_definitions(root, config)),
                               config.entry_workflow) if config.condition == "module" else {})
        result.update(allocation_signature=_signature(program, names, config.entry_workflow.split("::")[0]),
                      allocation_signature_reason=None)
    except (OSError, KeyError, TypeError, ValueError, RecursionError) as error:
        result["allocation_signature_reason"] = str(error)
    return result


def allocation_comparison(parent, child):
    before, after = parent.get("allocation_signature", UNAVAILABLE), child.get("allocation_signature", UNAVAILABLE)
    policies = tuple(_policy_set(signature) for signature in (before, after))
    if any(policy_set is None for policy_set in policies):
        return {"allocation_changed": UNAVAILABLE, "allocation_comparison_reason":
                child.get("allocation_signature_reason") or parent.get("allocation_signature_reason") or "invalid_signature"}
    return {"allocation_changed": policies[0] != policies[1], "allocation_comparison_reason": None}


def _policy_set(signature):
    if not isinstance(signature, Mapping):
        return None
    policies = set()
    for policy in signature.values():
        if not isinstance(policy, Mapping):
            return None
        values = tuple(policy.get(key) for key in ("provider", "model", "effort"))
        if not all(isinstance(value, str) and value.strip() and value.lower() not in
                   (UNAVAILABLE, "unknown", "auto", "default") for value in values):
            return None
        policies.add(values)
    return policies


def unexercised_sites(planned, realized, *, completed):
    """A completed validated memo can exclude planned effect sites, never source branches."""
    if not completed:
        return UNAVAILABLE
    expressions = {row["identity"]: re.escape(row["identity"]).replace(r"\[\*\]", r"\[\d+\]") for row in planned}
    if not all(any(re.fullmatch(pattern, row["identity"]) for pattern in expressions.values()) for row in realized):
        return UNAVAILABLE
    return [row for row in planned if not any(re.fullmatch(expressions[row["identity"]], effect["identity"])
                                             for effect in realized)]


def evaluation_comparison(root, config, *, runtime, evidence_root, parent_id, child):
    parent = evidence_root / "candidates" / parent_id if parent_id else None
    if parent is None or not parent.is_dir():
        return {"allocation_changed": UNAVAILABLE, "allocation_comparison_reason": "missing_parent_evidence",
                "parent_allocation_signature": UNAVAILABLE}
    evidence = candidate_evidence(parent, config, runtime=runtime)
    return {"parent_allocation_signature": evidence["allocation_signature"], **allocation_comparison(evidence, child)}
