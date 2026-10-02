"""Bounded P3 comparison helpers for maintained evaluated-execution tests."""

from __future__ import annotations

from collections.abc import Mapping
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.workflow.assets import WorkflowAssetResolver
from orchestrator.workflow.view_renderer import resolve_view_renderer
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.closed.sites import _ast_nodes
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from orchestrator.workflow_lisp.compiler import (
    compile_stage3_entrypoint,
    linked_module_type_environment,
)
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import (
    CommandResultExpr,
    FieldAccessExpr,
    IfExpr,
    LiteralExpr,
    PureOpExpr,
    PromptApplicationExpr,
    ProviderResultExpr,
)
from orchestrator.workflow_lisp.typed_prompt_inputs import normalize_typed_prompt_input_entry
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.normalized_type_descriptor import (
    compiler_normalized_type_descriptor,
)
from orchestrator.workflow_lisp.closed.names import canonical_type_descriptor
from orchestrator.workflow.prompt_dependency_contract import (
    serialize_compiler_prompt_dependency_contract,
)
from orchestrator.workflow.prompt_fragment_contract import (
    serialize_compiler_prompt_attempt_binding_plan,
    serialize_compiler_prompt_fragment_contract,
)

from tests.workflow_lisp_closed_program_corpus import (
    Prepared,
    REPO_ROOT,
    Workflow,
    compile as compile_typed,
    entry_with_target,
    prepare,
)


def _compile_flat(prepared: Prepared):
    return compile_stage3_entrypoint(
        prepared.entry,
        entry_workflow=prepared.workflow.canonical_name,
        source_roots=prepared.source_roots,
        command_boundaries=prepared.commands,
        provider_externs=prepared.providers,
        prompt_externs=prepared.prompts,
        workspace_root=prepared.workspace_root,
    )


def _compile_closed(prepared: Prepared):
    typed = compile_typed(prepared)
    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        program.tree,
        program.sites,
        program.digest,
    )
    return typed, program


def _pair(workflow: Workflow, scratch: Path):
    prepared = prepare(workflow, scratch)
    original = workflow.source.read_text(encoding="utf-8")
    assert prepared.entry.read_text(encoding="utf-8") == entry_with_target(
        workflow.source,
        syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION,
    )
    prepared.entry.write_text(original, encoding="utf-8")
    flat = _compile_flat(prepared)
    prepared.entry.write_text(
        entry_with_target(
            workflow.source,
            syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION,
        ),
        encoding="utf-8",
    )
    typed, closed = _compile_closed(prepared)
    return prepared, flat, typed, closed


def _span_key(value: Any) -> tuple[str, int, int]:
    span = value.span if hasattr(value, "span") else value
    start = span.start
    path = Path(start.path).resolve().as_posix()
    return path, start.line, start.column


def _closed_span_key(node: Mapping[str, Any]) -> tuple[str, int, int]:
    path, line, column = node["@"]["span"].rsplit(":", 2)
    return Path(path).resolve().as_posix(), int(line), int(column)


def _flat_steps(steps, context=()):
    for step in steps:
        yield step, context
        if "repeat_until" in step:
            yield from _flat_steps(
                step["repeat_until"]["steps"], context + (("loop", step["id"]),)
            )
        if "match" in step:
            for tag, arm in step["match"]["cases"].items():
                yield from _flat_steps(arm["steps"], context + (("case", tag),))
        if "if" in step:
            for tag in ("then", "else"):
                yield from _flat_steps(step[tag]["steps"], context + (("if", tag),))


def _one(values):
    values = list(values)
    assert len(values) == 1, values
    return values[0]


def _symbol(owner: str, binder: Any, *path: str, tag: str | None = None):
    return ("ref", owner, binder, tag, tuple(path))


def _literal(value: Any):
    return ("lit", type(value).__name__, json.dumps(value, sort_keys=True))


def _field(value, path):
    if not path:
        return value
    if value[0] == "record":
        return _field(dict(value[1])[path[0]], path[1:])
    assert value[0] == "ref", value
    return (*value[:4], value[4] + tuple(path))


def _closed_value(node, names):
    if node["k"] == "name":
        assert node["n"] in names, node["n"]
        return names[node["n"]]
    if node["k"] == "field":
        return _field(_closed_value(node["base"], names), node["path"])
    if node["k"] == "lit":
        return _literal(node["v"])
    raise AssertionError(("unsupported bounded operand", node))


def _flat_value(value, refs):
    if isinstance(value, Mapping):
        assert set(value) == {"ref"}, value
        assert value["ref"] in refs, value["ref"]
        return refs[value["ref"]]
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        key = value[2:-1]
        assert key in refs, key
        return refs[key]
    return _literal(value)


def _resolve_type(typed, module: str, name: str):
    return typed.module_type_envs[module].resolve_type(
        name,
        span=typed.entry.definition.span,
        form_path=typed.entry.definition.form_path,
    )


def _type_descriptor(typed, module: str, descriptor: Mapping[str, Any]):
    result = copy.deepcopy(descriptor)
    kind = result["kind"]
    if kind in {"record", "union", "path", "enum"}:
        normalized = canonical_type_descriptor(
            _resolve_type(typed, module, result["name"]), typed=typed
        )
        result["name"] = normalized["name"]
    if kind in {"record", "variant_case"}:
        for field in result["fields"]:
            field["type"] = _type_descriptor(typed, module, field["type"])
    elif kind == "union":
        for variant in result["variants"]:
            for field in variant["fields"]:
                field["type"] = _type_descriptor(typed, module, field["type"])
    elif kind in {"list", "optional"}:
        result["item"] = _type_descriptor(typed, module, result["item"])
    elif kind == "map":
        result["key"] = _type_descriptor(typed, module, result["key"])
        result["value"] = _type_descriptor(typed, module, result["value"])
    return result


def _contract(step, typed, module: str):
    kind = _one(key for key in ("output_bundle", "variant_output") if key in step)
    payload = copy.deepcopy(step[kind])
    # R3 owns this transport path. Authored output paths are checked separately.
    payload.pop("path")

    def visit_schema(row):
        if row.get("type") == "record":
            row["record_name"] = canonical_type_descriptor(
                _resolve_type(typed, module, row["record_name"]), typed=typed
            )["name"]
            for child in row["fields"]:
                visit_schema(child)
        elif row.get("type") == "list":
            visit_schema(row["items"])
        elif row.get("type") == "map":
            visit_schema(row["values"])

    rows = list(payload.get("fields", ())) + list(payload.get("shared_fields", ()))
    for variant in payload.get("variants", {}).values():
        rows.extend(variant.get("fields", ()))
    for row in rows:
        row.pop("source_map_subject", None)
        row.pop("source_map_subjects_by_variant", None)
        visit_schema(row)
    return {"kind": kind, "payload": payload}


def _typed_source(row, refs):
    assert row["kind"] == "typed_binding_ref", row
    return _flat_value(row["binding"], refs)


def _compare_dependencies(lowered, step, effect, refs, names, fragment):
    authored = step.get("depends_on")
    closed = effect["dependencies"]
    if authored is None:
        assert closed is None
        assert step["id"] not in lowered.compiler_prompt_dependency_contracts
        return

    contract = serialize_compiler_prompt_dependency_contract(
        lowered.compiler_prompt_dependency_contracts[step["id"]]
    )
    lineage = _one(
        row
        for row in lowered.origin_map.prompt_dependency_lineages
        if row.step_id == step["id"]
    )
    assert authored["inject"]["mode"] == "content"
    position = authored["inject"]["position"]
    assert contract["position"] == lineage.position.value == position
    instruction = authored["inject"].get("instruction")
    expected_hash = None if instruction is None else "sha256:" + hashlib.sha256(
        instruction.encode("utf-8")
    ).hexdigest()
    assert contract["instruction_utf8_sha256_or_null"] == expected_hash
    assert (None if lineage.instruction is None else lineage.instruction.value) == instruction
    rows = []
    for role in ("required", "optional"):
        values = authored.get(role, [])
        refs_in_contract = contract[role + "_binding_refs"]
        assert refs_in_contract == [value[2:-1] for value in values]
        rows.extend((role, index, value[2:-1]) for index, value in enumerate(values))
    assert rows == [
        (row.role, row.authored_index, row.binding_ref)
        for row in lineage.rows
    ]

    if fragment:
        assert contract["origin_kind"] == "workflow_lisp_prompt_fragment"
        assert closed is None
        docs = [fill for fill in effect["prompt"]["fills"] if fill["kind"] == "doc"]
        assert not authored.get("optional") and instruction is None
        assert position == "prepend"
        assert [
            _flat_value(value, refs) for value in authored.get("required", [])
        ] == [_closed_value(fill["value"], names) for fill in docs]
        assert all(fill["type"]["must_exist_target"] for fill in docs)
        return

    assert contract["origin_kind"] == "workflow_lisp_provider_result_prompt_dependencies"
    assert closed is not None
    assert closed["position"] == position and closed["instruction"] == instruction
    for role in ("required", "optional"):
        assert [_flat_value(value, refs) for value in authored.get(role, [])] == [
            _closed_value(value, names) for value in closed[role]
        ]


def _compare_provider(lowered, step, effect, typed, source_typed, module, refs, names, types):
    assert step["provider"] == effect["provider"]
    assert effect["repeat"] == "rerun"
    policy = dict(step.get("provider_call_policy", {}))
    if "timeout_sec" in step:
        policy["timeout_sec"] = step["timeout_sec"]
    assert {
        key: _flat_value(value, refs) for key, value in policy.items()
    } == {key: _closed_value(value, names) for key, value in effect["policy"].items()}

    fragment_carrier = step.get("compiler_prompt_fragment_contract")
    fragment = (
        None
        if fragment_carrier is None
        else serialize_compiler_prompt_fragment_contract(fragment_carrier)
    )
    typed_inputs = [
        normalize_typed_prompt_input_entry(row)
        for row in step.get("typed_prompt_inputs", ())
    ]
    assert [row["injection_order"] for row in typed_inputs] == list(range(len(typed_inputs)))
    if fragment:
        assert fragment["template_utf8"] == effect["prompt"]["template"]
        plan = serialize_compiler_prompt_attempt_binding_plan(
            step["compiler_prompt_attempt_binding_plan"]
        )["rows"]
        assert [row["declaration_ordinal"] for row in plan] == list(range(len(plan)))
        fills = []
        for row in plan:
            source = row["runtime_source"]
            if source["kind"] == "rendered_slot":
                rendered = fragment["rendered_slots"][source["ordinal"]]
                assert (row["slot_name"], row["slot_kind"]) == (
                    rendered["name"], rendered["kind"]
                )
                assert row["renderer"] == {
                    "renderer_id": rendered["renderer_id"],
                    "renderer_version": 1,
                }
                if row["refinement"] is not None:
                    assert row["refinement"] == rendered["static_type"]
                typ = _type_descriptor(typed, module, rendered["static_type"])
                value = _typed_source(rendered["value_source"], refs)
                renderer = rendered["renderer_id"]
                ordinals = rendered["placeholder_ordinals"]
            else:
                assert source["kind"] == "required_dependency"
                assert row["slot_kind"] == "doc" and row["renderer"] is None
                typ = _type_descriptor(typed, module, row["refinement"])
                value = _flat_value(
                    step["depends_on"]["required"][source["ordinal"]], refs
                )
                renderer, ordinals = None, []
            fills.append(
                {
                    "name": row["slot_name"],
                    "kind": row["slot_kind"],
                    "type": typ,
                    "value": value,
                    "renderer_id": renderer,
                    "output_role": row["output_role"],
                    "placeholder_ordinals": ordinals,
                }
            )
        expected = [
            {
                **{key: value for key, value in fill.items() if key != "value"},
                "value": _closed_value(fill["value"], names),
            }
            for fill in effect["prompt"]["fills"]
        ]
        assert fills == expected, (step["id"], "complete prompt fills")
        assert effect["inputs"] == []
        typed_slots = [
            row for row in fragment["rendered_slots"] if row["kind"] in {"value", "path"}
        ]
        assert len(typed_inputs) == len(typed_slots)
        for typed_input, slot in zip(typed_inputs, typed_slots, strict=True):
            assert typed_input["binding_name"] == slot["name"]
            assert typed_input["renderer"]["renderer_id"] == slot["renderer_id"]
            assert _typed_source(typed_input["value_source"], refs) == _typed_source(
                slot["value_source"], refs
            )
            descriptor = canonical_type_descriptor(
                _resolve_type(typed, module, typed_input["value_type_name"]), typed=typed
            )
            assert descriptor == _type_descriptor(typed, module, slot["static_type"])
        positions = fragment.get("output_positions", [])
        assert [row["expected_output"] for row in positions] == step.get(
            "expected_outputs", []
        )
        for row in positions:
            fill = _one(fill for fill in fills if fill["name"] == row["slot_name"])
            output = row["expected_output"]
            assert row["output_role"] == fill["output_role"] == "required_string_file"
            assert output["name"] == fill["name"] and output["type"] == "string"
            assert output["required"] is True
            assert _flat_value(output["path"], refs) == fill["value"]
    else:
        source_kind = _one(kind for kind in ("asset_file", "input_file") if kind in step)
        prompt = effect["prompt"]
        assert prompt["source_kind"] == source_kind
        assert prompt["path"] == step[source_kind]
        if source_kind == "asset_file":
            assert prompt["asset_base"] == Path(module).parent.as_posix()
        else:
            assert "asset_base" not in prompt
        assert len(typed_inputs) == len(effect["inputs"])
        for typed_input, (name, renderer_id, value) in zip(
            typed_inputs, effect["inputs"], strict=True
        ):
            assert typed_input["binding_name"] == name
            assert typed_input["renderer"]["renderer_id"] == renderer_id
            renderer = resolve_view_renderer(renderer_id, 1)
            assert typed_input["renderer"] == {
                "renderer_id": renderer_id,
                "renderer_version": renderer.renderer_version,
                "accepted_shape": renderer.accepted_shape,
            }
            assert _typed_source(typed_input["value_source"], refs) == _closed_value(
                value, names
            )
            value_type = canonical_type_descriptor(
                _resolve_type(typed, module, typed_input["value_type_name"]), typed=typed
            )
            assert value_type == types[_closed_value(value, names)]
    _compare_dependencies(lowered, step, effect, refs, names, bool(fragment))


def _source_result_descriptors(flat):
    modules_by_path = {
        Path(module.path).resolve().as_posix(): name
        for name, module in flat.graph.modules_by_name.items()
    }
    results = {}
    for result in flat.compiled_results_by_name.values():
        for declaration in (*result.typed_procedures, *result.typed_workflows):
            for expr in walk_expr(declaration.typed_body.expr):
                if not isinstance(expr, (ProviderResultExpr, CommandResultExpr)):
                    continue
                key = _span_key(expr)
                module = modules_by_path[key[0]]
                type_name = (
                    expr.prompt.prompt.declaration.return_type_name
                    if isinstance(expr, ProviderResultExpr)
                    and isinstance(expr.prompt, PromptApplicationExpr)
                    else expr.return_spec.type_name
                )
                source_env = linked_module_type_environment(flat, module)
                type_ref = source_env.resolve_type(
                    type_name,
                    span=expr.span,
                    form_path=expr.form_path,
                )
                descriptor = compiler_normalized_type_descriptor(
                    type_ref, type_env=source_env
                )
                assert key not in results or results[key] == descriptor
                results[key] = descriptor
    return results


def _emitted_binding(definition, line: int):
    return _one(
        node
        for node in _ast_nodes(definition["body"])
        if node.get("k") == "let"
        and node["value"].get("k") == "perform"
        and int(node["@"]["span"].rsplit(":", 2)[1]) == line
    )


def _setup_reviewed(lowered, definition, owner, steps, names, refs):
    loop = _one(node for node in _ast_nodes(definition["body"]) if node.get("k") == "loop")
    flat_loop = _one(step for step, _ in steps if "repeat_until" in step)
    assert int(loop["@"]["span"].rsplit(":", 2)[1]) == 62
    assert _span_key(lowered.origin_map.step_spans[flat_loop["id"]]) == _closed_span_key(
        loop["exhausted"]
    )
    assert [field["name"] for field in loop["state_type"]["fields"]] == [
        "round", "account", "replies"
    ]
    names[loop["param"]] = _symbol(owner, ("loop", 62))
    flat_state = _one(
        step
        for step, _ in steps
        if "if" in step
        and set(step["then"].get("outputs", {}))
        == {"state__round", "state__account", "state__replies"}
    )
    initial = _one(
        node["value"]
        for node in _ast_nodes(definition["body"])
        if node.get("k") == "let" and node["name"] == loop["init"]["n"]
    )
    assert initial["k"] == "record"
    for step, _ in steps:
        if "provider" not in step:
            continue
        line = _span_key(lowered.origin_map.step_spans[step["id"]])[1]
        binding = _emitted_binding(definition, line)
        producer = _symbol(owner, ("provider", line))
        names[binding["name"]] = producer
        if "output_bundle" in step:
            for field in step["output_bundle"]["fields"]:
                refs[
                    "root.steps." + step["name"] + ".artifacts." + field["name"]
                ] = _field(producer, field["json_pointer"].strip("/").split("/") if field["json_pointer"] else [])
        else:
            case = _one(
                node
                for node in _ast_nodes(definition["body"])
                if node.get("k") == "case" and node["subject"].get("n") == binding["name"]
            )
            for arm in case["arms"]:
                names[arm["bind"]] = _symbol(
                    owner, ("provider", line), tag=arm["variant"]
                )
            field_sources = {}
            for tag, arm in step["variant_output"]["variants"].items():
                for field in arm["fields"]:
                    field_sources.setdefault(field["name"], []).append((tag, field))
            for name, sources in field_sources.items():
                if len(sources) == 1:
                    tag, field = sources[0]
                    path = field["json_pointer"].strip("/").split("/") if field["json_pointer"] else []
                    refs[
                        "parent.steps." + step["name"] + ".artifacts." + name
                    ] = _field(_symbol(owner, ("provider", line), tag=tag), path)

    seed = _one(
        step
        for step, context in steps
        if not context
        and [row["name"] for row in step.get("materialize_artifacts", {}).get("values", [])]
        == ["state__round", "state__account", "state__replies"]
    )
    closed_fields = dict(initial["fields"])
    for field_name in ("round", "account", "replies"):
        wire = "state__" + field_name
        expected = _field(names[loop["param"]], [field_name])
        refs[
            "self.steps." + flat_state["name"] + ".artifacts." + wire
        ] = expected
        seed_row = _one(
            row for row in seed["materialize_artifacts"]["values"] if row["name"] == wire
        )
        source = seed_row["source"]
        flat_value = (
            _literal(source["literal"])
            if "literal" in source
            else _flat_value(source, refs)
        )
        assert flat_value == _closed_value(closed_fields[field_name], names)
        for branch, producer in (("then", flat_loop), ("else", seed)):
            transport = _one(flat_state[branch]["steps"])
            row = _one(
                value
                for value in transport["materialize_artifacts"]["values"]
                if value["name"] == wire
            )
            assert row["source"] == {
                "ref": f"root.steps.{producer['name']}.artifacts.{wire}"
            }
            assert flat_state[branch]["outputs"][wire]["from"] == {
                "ref": f"self.steps.{transport['name']}.artifacts.{wire}"
            }
            assert row["contract"] == seed_row["contract"]


def _setup_best(lowered, definition, owner, steps, names, refs):
    join = _one(node for node in _ast_nodes(definition["body"]) if node.get("k") == "join")
    assert join["params"] == [[
        "accounts", {"kind": "list", "item": {"kind": "primitive", "name": "String"}}
    ]]
    loop = _one(node for node in _ast_nodes(definition["body"]) if node.get("k") == "loop")
    assert tuple(map(int, loop["@"]["span"].rsplit(":", 2)[1:])) == (47, 22)
    names["accounts"] = _symbol(owner, ("map-result", 47, 22))
    result_step = _one(
        step
        for step, _ in steps
        if "materialize_artifacts" in step
        and [row["name"] for row in step["materialize_artifacts"]["values"]] == ["__result__"]
    )
    flat_loop = _one(step for step, _ in steps if "repeat_until" in step)
    assert result_step["materialize_artifacts"]["values"] == [{
        "name": "__result__",
        "source": {"ref": "root.steps." + flat_loop["name"] + ".artifacts.result"},
        "contract": {"kind": "collection", "type": "list", "items": {"type": "string"}},
    }]
    refs["root.steps." + result_step["name"] + ".artifacts.__result__"] = names["accounts"]
    head_step = _one(
        step
        for step, _ in steps
        if step.get("pure_projection", {}).get("payload", {}).get("expr", {}).get("kind")
        == "list_nonempty_head"
    )
    assert _span_key(lowered.origin_map.step_spans[head_step["id"]])[1:] == (47, 22)
    head = _one(
        node
        for node in _ast_nodes(definition["body"])
        if node.get("k") == "let"
        and node["value"].get("k") == "op"
        and node["value"].get("payload", {}).get("expr", {}).get("kind") == "list_nonempty_head"
    )
    assert head["name"] == "repo"
    source = head["value"]["args"][0]
    assert source["k"] == "field"
    assert source["base"]["k"] == "name"
    assert source["base"]["n"] == loop["param"]
    assert source["path"] == ["remaining"]
    assert head["value"]["payload"]["expr"]["compiler_owned"] is True
    assert head_step["pure_projection"]["payload"]["expr"]["compiler_owned"] is True
    symbol = _symbol(owner, ("map-item", 47, 22))
    names["repo"] = symbol
    output = _one(head_step["output_bundle"]["fields"])
    assert output["json_pointer"] == "" and output["type"] == "string"
    refs["self.steps." + head_step["name"] + ".artifacts." + output["name"]] = symbol
    flat_call = _one(step for step, _ in steps if "call" in step)
    closed_call = _one(node for node in _ast_nodes(definition["body"]) if node.get("k") == "call")
    assert _span_key(lowered.origin_map.step_spans[flat_call["id"]]) == _closed_span_key(closed_call)
    assert flat_call["call"] == "best_of_n::implement-one"
    assert closed_call["callee"] == "workflow:best_of_n::implement-one"
    assert [
        _flat_value(flat_call["with"][name], refs) for name in ("task", "repo")
    ] == [_closed_value(arg, names) for arg in closed_call["args"]]


def _compare_improve_command(tree, lowered, step, context, owner, effect):
    tag = _one(value for kind, value in context if kind == "case")
    (case,) = [node for node in _ast_nodes(tree["body"]) if node.get("k") == "case"]
    assert case["subject"]["n"] == "result"
    arm = _one(row for row in case["arms"] if row["variant"] == tag)
    call = _one(node for node in _ast_nodes(arm["body"]) if node.get("k") == "call")
    assert call["callee"] == owner and call["frame"].startswith(tag + " / ")
    names = {arm["bind"]: _symbol(tree["entry"], "result", tag=tag)}
    params = tree["definitions"][owner]["params"]
    names.update(
        {
            name: _closed_value(arg, names)
            for (name, _type), arg in zip(params, call["args"], strict=True)
        }
    )

    # These flat outputs are associated with their authored variant and loop
    # state before being compared to execute's ordered argv.
    steps = list(_flat_steps(lowered.authored_mapping["steps"]))
    consumer = _one(
        source
        for source, _context in steps
        if "match" in source
        and any(step in arm_source["steps"] for arm_source in source["match"]["cases"].values())
    )
    producer = _one(
        source
        for source, _context in steps
        if "match" in source
        and consumer["match"]["ref"] == "root.steps." + source["name"] + ".artifacts.return__variant"
    )
    loop_step = _one(source for source, _context in steps if "repeat_until" in source)
    result_fields = {
        "return__value__hypothesis": ("value", "hypothesis"),
        "return__value__parameters": ("value", "parameters"),
        "return__evidence__notes": ("evidence", "notes"),
        "return__reason__issue": ("reason", "issue"),
    }
    outputs = producer["match"]["cases"][tag]["outputs"]
    refs = {}
    for wire, path in result_fields.items():
        source_wire = (
            "state__current__" + path[-1]
            if tag == "EXHAUSTED" and path[0] == "value"
            else "result__" + "__".join(path)
        )
        assert outputs[wire]["from"] == {
            "ref": "root.steps." + loop_step["name"] + ".artifacts." + source_wire
        }
        refs["root.steps." + producer["name"] + ".artifacts." + wire] = _symbol(
            tree["entry"], "result", *path, tag=tag
        )

    assert effect["boundary"] == "launch_experiment"
    configuration = tree["configuration"]["commands"][effect["boundary"]]
    assert effect["command"] == configuration["stable_command"]
    assert effect["closure"] == configuration["closure"]
    assert effect["repeat"] == ("must_not_repeat" if configuration["must_not_repeat"] else "rerun")
    authored = [_flat_value(value, refs) for value in step["command"]]
    emitted = [_literal(value) for value in effect["command"]] + [
        _closed_value(value, names) for value in effect["argv"]
    ]
    assert authored == emitted, (tag, authored, emitted)
    assert [
        value["v"] for value in effect["argv"] if value["k"] == "lit"
    ] == ["--outcome", "--note", "--hypothesis", "--parameters"]


def _compare_improve_calls(tree, lowereds, entry):
    owner, definition = _one(
        (name, row)
        for name, row in tree["definitions"].items()
        if row["key"][:3] == ["std/improve", "procedure", "improve"]
    )
    parent_call = _one(
        node
        for node in _ast_nodes(tree["body"])
        if node.get("k") == "call" and node["callee"] == owner
    )
    assert parent_call["args"][2]["v"] == 3
    brief_node = _one(
        node["value"]
        for node in _ast_nodes(tree["body"])
        if node.get("k") == "let" and node["name"] == parent_call["args"][1]["n"]
    )
    assert brief_node["k"] == "record"
    assert [name for name, _ in brief_node["fields"]] == ["question"]
    input_names = {name: _symbol(tree["entry"], name) for name, _ in tree["params"]}
    input_record = (
        "record",
        tuple((name, _closed_value(value, input_names)) for name, value in brief_node["fields"]),
    )
    loop = _one(node for node in _ast_nodes(definition["body"]) if node.get("k") == "loop")
    assert [field["name"] for field in loop["state_type"]["fields"]] == ["current"]
    names = {
        loop["param"]: _symbol(owner, ("loop", 29)),
        "inputs": input_record,
    }
    case = _one(node for node in _ast_nodes(definition["body"]) if node.get("k") == "case")
    for arm in case["arms"]:
        names[arm["bind"]] = _symbol(owner, "decision", tag=arm["variant"])

    lowered = lowereds[entry][1]
    steps = list(_flat_steps(lowered.authored_mapping["steps"]))
    loop_step = _one(step for step, _ in steps if "repeat_until" in step)
    state_step = _one(
        step
        for step, _ in steps
        if "if" in step
        and set(step["then"].get("outputs", {}))
        == {"state__current__hypothesis", "state__current__parameters"}
    )
    refs = {"inputs.question": input_names["question"]}
    for branch in ("self", "parent"):
        for leaf in ("hypothesis", "parameters"):
            key = "state__current__" + leaf
            refs[f"{branch}.steps.{state_step['name']}.artifacts.{key}"] = _symbol(
                owner, ("loop", 29), "current", leaf
            )
    calls = [step for step, _ in steps if "call" in step]
    assert len(calls) == 2
    review = _one(
        step
        for step in calls
        if lowereds[step["call"]][1].origin_map.workflow_origin.form_path[-1]
        == "review-proposal"
    )
    projection = lowereds[review["call"]][1].boundary_projection
    feedback = _one(
        row for row in projection.flattened_outputs if row.source_path == ("return", "feedback", "notes")
    )
    refs[
        "parent.steps." + review["name"] + ".artifacts." + feedback.generated_name
    ] = _symbol(owner, "decision", "feedback", "notes", tag="REVISE")

    for step in calls:
        callee = lowereds[step["call"]][1]
        authored = callee.origin_map.workflow_origin.form_path[-1]
        closed_owner, closed_definition = _one(
            (name, row)
            for name, row in tree["definitions"].items()
            if row["key"][:3] == ["improve_experiment_proposal", "procedure", authored]
        )
        proc_ref = dict(definition["key"][4])["review" if authored == "review-proposal" else "revise"]
        assert proc_ref["target"] == closed_definition["key"] and proc_ref["bound"] == []
        closed_call = _one(
            node
            for node in _ast_nodes(definition["body"])
            if node.get("k") == "call" and node["callee"] == closed_owner
        )
        assert _span_key(lowered.origin_map.step_spans[step["id"]]) == _closed_span_key(
            closed_call
        )
        args = {
            name: _closed_value(arg, names)
            for (name, _type), arg in zip(closed_definition["params"], closed_call["args"], strict=True)
        }
        projection = callee.boundary_projection
        internal = {
            row.generated_name
            for row in projection.generated_internal_inputs
            if row.reason == "managed_write_root"
        }
        assert all(row.reason == "managed_write_root" for row in projection.generated_internal_inputs)
        actual = {
            name: _flat_value(value, refs)
            for name, value in step["with"].items()
            if name not in internal
        }
        projected = {
            row.generated_name: _field(args[row.source_path[0]], row.source_path[1:])
            for row in projection.flattened_inputs
        }
        assert actual == projected, (authored, actual, projected)
        assert set(step["with"]) == set(projected) | internal


def _register_type(types, symbol, descriptor):
    types[symbol] = descriptor
    if descriptor["kind"] == "record":
        for field in descriptor["fields"]:
            _register_type(types, _field(symbol, [field["name"]]), field["type"])


def _expected_external_configuration(typed):
    providers = {
        name: {"provider_id": value.provider_id}
        for name, value in typed.externs.items()
        if hasattr(value, "provider_id")
    }
    prompts = {
        name: {"source_kind": value.source_kind, "path": value.path}
        for name, value in typed.externs.items()
        if hasattr(value, "source_kind") and hasattr(value, "path")
    }
    return providers, prompts


def _compare_command_configuration(flat, typed, tree):
    flat_env = flat.entry_result.command_boundary_environment
    for name, actual in tree["configuration"]["commands"].items():
        binding = typed.command_boundaries[name]
        assert flat_env.bindings_by_name[name] == binding
        assert isinstance(binding, ExternalToolBinding)
        expected = {
            "kind": "external_tool",
            "name": binding.name,
            "stable_command": list(binding.stable_command),
            "must_not_repeat": binding.must_not_repeat,
            "closure": [
                {"base": "workspace", "path": path} for path in binding.closure or ()
            ],
            "retirement_class": binding.retirement_class,
            "retirement_label": binding.retirement_label,
            "replacement_surface": binding.replacement_surface,
            "bridge_owner": binding.bridge_owner,
            "expiry_condition": binding.expiry_condition,
            "evidence_refs": list(binding.evidence_refs),
            "retirement_status": binding.retirement_status,
        }
        assert actual == expected, name

    providers, prompts = _expected_external_configuration(typed)
    closed_providers = tree["configuration"]["providers"]
    closed_prompts = tree["configuration"]["prompts"]
    for name, expected in providers.items():
        assert closed_providers[name] == expected
    for name, expected in prompts.items():
        actual = closed_prompts[name]
        assert {key: actual[key] for key in ("source_kind", "path")} == expected
        if expected["source_kind"] == "asset_file":
            assert actual["asset_base"] == Path(typed.entry_module).parent.as_posix()
    if "launch_experiment" in flat.entry_result.command_boundary_environment.bindings_by_name:
        assert flat.entry_result.command_boundary_environment.origins_by_name.get(
            "launch_experiment"
        ) == "workspace"


def _compare_pair(name, flat, typed, closed, expected_counts):
    tree = closed.tree
    definitions = {
        tree["entry"]: {"params": tree["params"], "body": tree["body"]},
        **tree["definitions"],
    }
    effects = {}
    for owner, definition in definitions.items():
        for effect in _ast_nodes(definition["body"]):
            if effect.get("k") == "perform":
                key = _closed_span_key(effect)
                assert key not in effects, (key, effects.get(key), effect)
                effects[key] = owner, effect
    assert len(effects) == len(closed.sites)
    source_results = _source_result_descriptors(flat)
    modules_by_path = {
        Path(module.path).resolve().as_posix(): module_name
        for module_name, module in flat.graph.modules_by_name.items()
    }
    lowereds = {}
    for result in flat.compiled_results_by_name.values():
        for lowered in result.lowered_workflows:
            module = modules_by_path[
                Path(lowered.origin_map.workflow_origin.span.start.path).resolve().as_posix()
            ]
            mapping_name = lowered.authored_mapping["name"]
            if mapping_name in lowereds:
                assert lowereds[mapping_name][1].authored_mapping == lowered.authored_mapping
            else:
                lowereds[mapping_name] = module, lowered
    entry = typed.entry.definition.name
    assert entry in lowereds
    reachable = set()

    def visit(workflow_name):
        if workflow_name in reachable:
            return
        assert workflow_name in lowereds, workflow_name
        reachable.add(workflow_name)
        for step, _context in _flat_steps(lowereds[workflow_name][1].authored_mapping["steps"]):
            if "call" in step:
                visit(step["call"])

    visit(entry)
    hits = {key: 0 for key in effects}
    pairings = []
    for flat_owner in sorted(reachable):
        module, lowered = lowereds[flat_owner]
        source_typed = flat.compiled_results_by_name[module].typed_program
        assert source_typed is not None
        assert source_typed.module_externs[module] == typed.module_externs[module]
        origin = lowered.origin_map.workflow_origin
        kind, authored_name = origin.form_path[-2:]
        if flat_owner == entry:
            closed_owner = tree["entry"]
        else:
            closed_owner = _one(
                key
                for key, definition in tree["definitions"].items()
                if definition["key"][:3]
                == [module, "procedure" if kind == "defproc" else "workflow", authored_name]
            )
        params = definitions[closed_owner]["params"]
        names = {name: _symbol(closed_owner, name) for name, _type in params}
        refs = {}
        types = {}
        for param_name, type_descriptor in params:
            _register_type(types, names[param_name], type_descriptor)
        for projection in lowered.boundary_projection.flattened_inputs:
            refs["inputs." + projection.generated_name] = _field(
                names[projection.source_path[0]], projection.source_path[1:]
            )
        steps = list(_flat_steps(lowered.authored_mapping["steps"]))
        if name == "reviewed_change":
            _setup_reviewed(lowered, definitions[closed_owner], closed_owner, steps, names, refs)
        elif name == "best_of_n" and flat_owner == entry:
            _setup_best(lowered, definitions[closed_owner], closed_owner, steps, names, refs)

        for step, context in steps:
            is_launch = step.get("command", [])[:2] == ["python", "scripts/launch_experiment.py"]
            if "provider" not in step and not is_launch:
                continue
            key = _span_key(lowered.origin_map.step_spans[step["id"]])
            assert key in effects, (flat_owner, step["id"], key)
            effect_owner, effect = effects[key]
            hits[key] += 1
            assert _contract(step, typed, module) == effect["contract"]
            assert _type_descriptor(typed, module, source_results[key]) == effect["result"], (
                key,
                _type_descriptor(typed, module, source_results[key]),
                effect["result"],
            )
            if "provider" in step:
                assert step["provider"] == effect["provider"]
                if not step.get("compiler_prompt_fragment_contract"):
                    source_kind = _one(
                        kind for kind in ("asset_file", "input_file") if kind in step
                    )
                    configured = [
                        extern
                        for extern in source_typed.module_externs[module].values()
                        if getattr(extern, "source_kind", None) == source_kind
                        and getattr(extern, "path", None) == step[source_kind]
                    ]
                    assert configured, (module, source_kind, step[source_kind])
                    closed_configured = [
                        extern
                        for extern in typed.module_externs[module].values()
                        if getattr(extern, "source_kind", None) == source_kind
                        and getattr(extern, "path", None) == step[source_kind]
                    ]
                    assert len(closed_configured) == len(configured)
                _compare_provider(
                    lowered, step, effect, typed, source_typed, module, refs, names, types
                )
            else:
                _compare_improve_command(tree, lowered, step, context, effect_owner, effect)
            pairings.append((flat_owner, step["id"], effect_owner, effect["site"], context))

    if name == "improve_experiment_proposal":
        _compare_improve_calls(tree, lowereds, entry)
        expected_owners = {
            "procedure:improve_experiment_proposal::review-proposal": 1,
            "procedure:improve_experiment_proposal::revise-proposal": 1,
            "procedure:improve_experiment_proposal::execute": 3,
        }
        actual_owners = {}
        for owner, _step, closed_owner, _site, context in pairings:
            actual_owners[closed_owner] = actual_owners.get(closed_owner, 0) + 1
            if closed_owner.endswith("::execute"):
                assert len(context) == 1 and context[0][0] == "case"
        assert actual_owners == expected_owners
    elif name == "reviewed_change":
        assert len(pairings) == 4
        assert sum(bool(context and context[0][0] == "loop") for *_, context in pairings) == 3
    elif name == "best_of_n":
        assert {(owner, site) for owner, _step, _closed, site, _context in pairings} == {
            ("best_of_n::best-of-n", "selection"),
            ("best_of_n::implement-one", "change"),
        }
    elif name == "private_owners":
        assert {owner for owner, *_rest in pairings} == {"alpha::alpha-run", "beta::beta-run"}
    else:
        assert len(pairings) == 1
    assert (len(pairings), len(effects)) == expected_counts
    assert all(count for count in hits.values())
    _compare_command_configuration(flat, typed, tree)
    return pairings


def _source_pair(
    entry: Path,
    *,
    module_roots: tuple[Path, ...],
    entry_workflow: str,
    workspace: Path,
    providers: Mapping[str, str],
    prompts: Mapping[str, Any],
    commands: Mapping[str, Any] | None = None,
):
    options = {
        "entry_workflow": entry_workflow,
        "source_roots": module_roots,
        "workspace_root": workspace,
        "command_boundaries": commands or {},
        "provider_externs": providers,
        "prompt_externs": prompts,
    }
    flat = compile_stage3_entrypoint(entry, **options)
    entry.write_text(entry_with_target(entry, syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION), encoding="utf-8")
    typed = compile_typed_program(entry, **options)
    closed = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        closed.tree,
        closed.sites,
        closed.digest,
    )
    return flat, typed, closed


def _fixture_pair(root, source: str, module: str, name: str, providers, prompts):
    entry = root / Path(module).with_suffix(".orc")
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(source, encoding="utf-8")
    return _source_pair(
        entry,
        module_roots=(root,),
        entry_workflow=f"{module}::{name}",
        workspace=root,
        providers=providers,
        prompts=prompts,
    )


def _fixture_types_and_assets(root: Path, scratch: Path):
    provider_name = "providers.review"
    providers = {provider_name: "p3-provider"}
    docs_source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
      (defmodule probe/docs) (export run)
      (defpath SourcePath :kind relpath :under "docs" :must-exist true)
      (defpath ReportPath :kind relpath :under ".orchestrate/runs" :must-exist false)
      (defrecord Piece (value String))
      (defrecord Answer (payload List[Piece] :description "preserve Piece in guidance"))
      (defprompt review
        (:fills (first :doc SourcePath) (message :text) (second :doc SourcePath)
                (payload :value List[Piece]) (report :path :out ReportPath))
        -> Answer
        "Check {message}, {payload}, and {report}; repeat {message}")
      (defworkflow run ((first SourcePath) (message String) (second SourcePath)
                        (payload List[Piece]) (report ReportPath)) -> Answer
        (provider-result providers.review
          :prompt (review :first first :message message :second second
                          :payload payload :report report)
          :delivery :composed :timeout-sec 30)))'''
    docs_root = scratch / "docs"
    docs_root.mkdir(parents=True)
    (docs_root / "source.md").write_text("compile-only doc input", encoding="utf-8")
    docs_pair = _fixture_pair(
        docs_root,
        docs_source,
        "probe/docs",
        "run",
        providers,
        {},
    )
    _compare_pair("docs", *docs_pair, (1, 1))
    doc_program = docs_pair[2]
    (doc_effect,) = [
        node for node in _ast_nodes(doc_program.tree["body"]) if node.get("k") == "perform"
    ]
    assert [row["kind"] for row in doc_effect["prompt"]["fills"]] == [
        "doc", "text", "doc", "value", "path"
    ]
    assert doc_effect["prompt"]["fills"][1]["placeholder_ordinals"] == [0, 3]
    assert doc_effect["prompt"]["fills"][4]["output_role"] == "required_string_file"
    assert doc_effect["prompt"]["fills"][4]["type"]["under"] == ".orchestrate/runs"

    dependency_source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
      (defmodule probe/dependencies) (export run)
      (defpath RequiredPath :kind relpath :under "docs" :must-exist true)
      (defpath OptionalPath :kind relpath :under "docs" :must-exist true)
      (defworkflow run ((required RequiredPath) (optional OptionalPath)
                        (model String) (effort String)) -> Int
        (provider-result providers.review :prompt prompts.review
          :inputs (required optional) :returns Int
          :prompt-dependencies
            (:required (required optional required) :optional (optional)
             :position POSITION INSTRUCTION)
          :model model :effort effort :timeout-sec 30)))'''
    asset_root = scratch / "asset"
    asset_root.mkdir(parents=True)
    asset_source = dependency_source.replace("POSITION", "prepend").replace("INSTRUCTION", "")
    asset_path = asset_root / "probe/dependencies.orc"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_text(asset_source, encoding="utf-8")
    (asset_path.parent / "prompts").mkdir()
    (asset_path.parent / "prompts/p.md").write_text("ASSET SOURCE", encoding="utf-8")
    (asset_root / "prompts").mkdir()
    (asset_root / "prompts/p.md").write_text("INPUT SOURCE", encoding="utf-8")
    from orchestrator.workflow_lisp.workflows import PromptExtern

    asset_prompt = PromptExtern(name="prompts.review", asset_file="prompts/p.md")
    asset_pair = _source_pair(
        asset_path,
        module_roots=(asset_root,),
        entry_workflow="probe/dependencies::run",
        workspace=asset_root,
        providers=providers,
        prompts={"prompts.review": asset_prompt},
    )
    _compare_pair("deps_asset", *asset_pair, (1, 1))
    asset_effect = next(
        node for node in _ast_nodes(asset_pair[2].tree["body"]) if node.get("k") == "perform"
    )
    assert asset_effect["prompt"]["source_kind"] == "asset_file"
    asset_read = WorkflowAssetResolver(asset_path).resolve("prompts/p.md")
    closed_asset = asset_root / asset_effect["prompt"]["asset_base"] / asset_effect["prompt"]["path"]
    assert asset_read.read_text(encoding="utf-8") == closed_asset.read_text(encoding="utf-8") == "ASSET SOURCE"

    input_root = scratch / "input"
    input_root.mkdir()
    input_path = input_root / "probe/dependencies.orc"
    input_path.parent.mkdir(parents=True)
    input_path.write_text(dependency_source.replace("POSITION", "append").replace(
        "INSTRUCTION", ':instruction "Keep required order @ path"'
    ), encoding="utf-8")
    (input_root / "prompts").mkdir()
    (input_root / "prompts/p.md").write_text("INPUT SOURCE", encoding="utf-8")
    input_prompt = PromptExtern(name="prompts.review", input_file="prompts/p.md")
    input_pair = _source_pair(
        input_path,
        module_roots=(input_root,),
        entry_workflow="probe/dependencies::run",
        workspace=input_root,
        providers=providers,
        prompts={"prompts.review": input_prompt},
    )
    _compare_pair("deps_input", *input_pair, (1, 1))
    input_effect = next(
        node for node in _ast_nodes(input_pair[2].tree["body"]) if node.get("k") == "perform"
    )
    assert input_effect["prompt"]["source_kind"] == "input_file"
    assert input_effect["dependencies"]["position"] == "append"
    assert input_effect["dependencies"]["instruction"] == "Keep required order @ path"
    assert (input_root / input_effect["prompt"]["path"]).read_text(encoding="utf-8") == "INPUT SOURCE"
    assert asset_read.read_text(encoding="utf-8") != (input_root / input_effect["prompt"]["path"]).read_text(encoding="utf-8")
    return {
        "docs": docs_pair,
        "asset": asset_pair,
        "input": input_pair,
    }


def _private_nominal_pair(scratch: Path):
    root = scratch / "private"
    root.mkdir(parents=True)
    for module in ("alpha", "beta"):
        path = root / f"{module}.orc"
        path.write_text(
            f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
              (defmodule {module}) (export {module}-run)
              (defrecord Piece (value String))
              (defrecord Answer
                (items List[Piece] :description "Keep record_name Piece and @ path unchanged."))
              (defworkflow {module}-run () -> Answer
                (provider-result provider :prompt prompt :inputs () :returns Answer)))''',
            encoding="utf-8",
        )
    entry = root / "private_entry.orc"
    entry.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule private_entry) (import alpha :only (alpha-run))
          (import beta :only (beta-run)) (export run)
          (defworkflow run () -> Int
            (let* ((alpha-result (call alpha-run)) (beta-result (call beta-run))) 1)))''',
        encoding="utf-8",
    )
    from orchestrator.workflow_lisp.workflows import PromptExtern

    prompt = PromptExtern(name="prompt", input_file="p.md")
    (root / "p.md").write_text("compile-only", encoding="utf-8")
    pair = _source_pair(
        entry,
        module_roots=(root,),
        entry_workflow="private_entry::run",
        workspace=root,
        providers={"provider": "nominal-test-provider"},
        prompts={"prompt": prompt},
    )
    pairings = _compare_pair("private_owners", *pair, (2, 2))
    effects = [
        node
        for definition in pair[2].tree["definitions"].values()
        for node in _ast_nodes(definition["body"])
        if node.get("k") == "perform"
    ]
    names = {
        effect["contract"]["payload"]["fields"][0]["items"]["record_name"]
        for effect in effects
    }
    assert names == {"alpha::Piece", "beta::Piece"}
    assert all(
        effect["contract"]["payload"]["fields"][0]["description"]
        == "Keep record_name Piece and @ path unchanged."
        for effect in effects
    )
    return pair


def _calculated_and_authored_label_pair(scratch: Path):
    root = scratch / "labels"
    root.mkdir()
    module = "probe/labels"
    entry = root / "probe/labels.orc"
    entry.parent.mkdir()
    entry.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule probe/labels) (export run)
          (defrecord Box (n Int))
          (defworkflow run ((a Box) (b Box) (__wcc_anf_0123456789 String)) -> Int
            (provider-result providers.p :prompt prompts.p
              :inputs ((if (> a.n 0) a b) __wcc_anf_0123456789) :returns Int)))''',
        encoding="utf-8",
    )
    (root / "prompts").mkdir()
    (root / "prompts/p.md").write_text("compile-only", encoding="utf-8")
    from orchestrator.workflow_lisp.workflows import PromptExtern

    flat, typed, closed = _source_pair(
        entry,
        module_roots=(root,),
        entry_workflow=module + "::run",
        workspace=root,
        providers={"providers.p": "label-test-provider"},
        prompts={
            "prompts.p": PromptExtern(name="prompts.p", input_file="prompts/p.md")
        },
    )
    lowered = next(
        lowered
        for result in flat.compiled_results_by_name.values()
        for lowered in result.lowered_workflows
        if lowered.authored_mapping["name"] == module + "::run"
    )
    provider_step = _one(
        step
        for step, _context in _flat_steps(lowered.authored_mapping["steps"])
        if "provider" in step
    )
    (generated_input, authored_input) = [
        normalize_typed_prompt_input_entry(row)
        for row in provider_step["typed_prompt_inputs"]
    ]
    assert authored_input["binding_name"] == "__wcc_anf_0123456789"
    assert generated_input["binding_name"] != authored_input["binding_name"]
    assert authored_input["value_source"]["binding"] == {"ref": "inputs.__wcc_anf_0123456789"}
    calculated_ref = generated_input["value_source"]["binding"]["n"]["ref"]
    assert calculated_ref.startswith("root.steps.") and calculated_ref.endswith(".artifacts.return__n")
    producer_name = calculated_ref.removeprefix("root.steps.").split(".artifacts.", 1)[0]
    producer_step = _one(
        step
        for step, _context in _flat_steps(lowered.authored_mapping["steps"])
        if step["name"] == producer_name
    )
    flat_source_expr = _one(
        expr
        for result in flat.compiled_results_by_name.values()
        for workflow in result.typed_workflows
        if workflow.definition.name == module + "::run"
        for expr in walk_expr(workflow.typed_body.expr)
        if isinstance(expr, ProviderResultExpr)
    )
    assert flat_source_expr.inputs[0].__class__.__name__ == "IfExpr"
    assert flat_source_expr.inputs[1].__class__.__name__ == "NameExpr"
    assert flat_source_expr.inputs[1].name == "__wcc_anf_0123456789"
    selected = flat_source_expr.inputs[0]
    assert isinstance(selected, IfExpr)
    assert isinstance(selected.condition_expr, PureOpExpr)
    assert selected.condition_expr.operator == ">"
    field, positive = selected.condition_expr.args
    assert isinstance(field, FieldAccessExpr)
    assert field.base.name == "a" and field.fields == ("n",)
    assert isinstance(positive, LiteralExpr) and positive.value == 0
    assert _span_key(lowered.origin_map.step_spans[producer_step["id"]]) == _span_key(
        selected
    )
    projection = producer_step["pure_projection"]
    assert projection["payload"]["expr"]["body"]["kind"] == "if"
    assert projection["binding_refs"] == {
        "inputs.a__n": {"ref": "inputs.a__n"},
        "inputs.b__n": {"ref": "inputs.b__n"},
    }
    assert projection["payload"]["expr"]["bindings"][0]["value"]["fields"] == [
        {"name": "n", "value": {"kind": "binding", "name": "inputs.a__n"}}
    ]
    assert projection["payload"]["expr"]["body"]["then"] == {
        "kind": "binding",
        "name": projection["payload"]["expr"]["bindings"][0]["name"],
    }
    assert projection["payload"]["expr"]["body"]["else"]["fields"] == [
        {"name": "n", "value": {"kind": "binding", "name": "inputs.b__n"}}
    ]
    assert producer_step["output_bundle"]["fields"][0]["json_pointer"] == "/result/n"
    workflow = next(
        workflow
        for result in flat.compiled_results_by_name.values()
        for workflow in result.typed_workflows
        if workflow.definition.name == module + "::run"
    )
    assert {"a", "b", "__wcc_anf_0123456789"} <= set(
        workflow.typed_body.binding_environment
    )
    assert generated_input["binding_name"] not in workflow.typed_body.binding_environment

    (effect,) = [node for node in _ast_nodes(closed.tree["body"]) if node.get("k") == "perform"]
    first_name, second_name = effect["inputs"][0][0], effect["inputs"][1][0]
    assert second_name == "__wcc_anf_0123456789"
    assert first_name != second_name
    first_binding = _one(
        node
        for node in _ast_nodes(closed.tree["body"])
        if node.get("k") == "let" and node["name"] == first_name
    )
    assert effect["inputs"][0][2]["k"] == "name"
    assert effect["inputs"][0][2]["n"] == first_binding["name"]
    assert first_binding["value"]["k"] == "select"
    assert _closed_span_key(first_binding) == _span_key(selected)
    selected_condition = first_binding["value"]["cond"]
    assert selected_condition["k"] == "op"
    selected_operator = selected_condition["payload"]["expr"]
    assert selected_operator["operator"] == selected.condition_expr.operator
    assert selected_operator["args"] == [
        {"kind": "binding", "name": "a0"},
        {"kind": "binding", "name": "a1"},
    ]
    assert set(selected_condition["payload"]["bindings"]) == {"a0", "a1"}
    assert selected_condition["args"][0]["k"] == "field"
    assert selected_condition["args"][0]["base"]["n"] == field.base.name
    assert selected_condition["args"][0]["path"] == list(field.fields)
    assert selected_condition["args"][1]["k"] == "lit"
    assert selected_condition["args"][1]["v"] == positive.value
    assert "label" not in first_binding
    then_value = first_binding["value"]["then"]["value"]
    else_value = first_binding["value"]["else"]["value"]
    assert (then_value["k"], then_value["n"]) == ("name", "a")
    assert (else_value["k"], else_value["n"]) == ("name", "b")
    source_typed = flat.compiled_results_by_name[module].typed_program
    assert _contract(provider_step, typed, module) == effect["contract"]
    assert _type_descriptor(
        typed, module, _source_result_descriptors(flat)[_closed_span_key(effect)]
    ) == effect["result"]
    assert generated_input["renderer"] == {
        "renderer_id": "canonical-json",
        "renderer_version": 1,
        "accepted_shape": "any_pure_value",
    }
    assert effect["inputs"][0][1] == generated_input["renderer"]["renderer_id"]
    assert effect["inputs"][1][1] == authored_input["renderer"]["renderer_id"]
    assert effect["inputs"][1][2]["n"] == second_name
    return flat, typed, closed


def _effect(tree, *, owner=None, site=None, class_name=None):
    definitions = {
        tree["entry"]: {"body": tree["body"]},
        **tree["definitions"],
    }
    return _one(
        node
        for definition_owner, definition in definitions.items()
        if owner is None or definition_owner == owner
        for node in _ast_nodes(definition["body"])
        if node.get("k") == "perform"
        and (site is None or node.get("site") == site)
        and (class_name is None or node.get("class") == class_name)
    )


def _expect_projection_rejection(name, pair, count, mutate):
    from dataclasses import replace

    flat, typed, closed = pair
    changed = copy.deepcopy(closed.tree)
    mutate(changed)
    try:
        _compare_pair(name, flat, typed, replace(closed, tree=changed), count)
    except AssertionError:
        return
    raise AssertionError(f"P3 comparison accepted a changed carrier: {name}")


def _reject_p3_mutations(pairs):
    def alter_guidance(tree):
        effect = _effect(tree)
        row = _one(
            row
            for row in effect["contract"]["payload"]["fields"]
            if "description" in row
        )
        row["description"] += " changed"

    def alter_account_operands(tree):
        effect = _effect(tree, site="loop:state[*] / review", class_name="provider")
        fills = effect["prompt"]["fills"]
        fills[2]["value"], fills[3]["value"] = fills[3]["value"], fills[2]["value"]

    def alter_slot_order(tree):
        fills = _effect(tree)["prompt"]["fills"]
        fills[0], fills[2] = fills[2], fills[0]

    def alter_authored_output_path(tree):
        fill = _one(fill for fill in _effect(tree)["prompt"]["fills"] if fill["name"] == "report")
        fill["value"] = {
            "k": "lit",
            "v": "docs/changed.md",
            "type": copy.deepcopy(fill["type"]),
        }

    def alter_dependencies(tree):
        values = _effect(tree)["dependencies"]["required"]
        values[0], values[1] = values[1], values[0]

    def add_default_policy(tree):
        effect = _effect(
            tree,
            owner="procedure:improve_experiment_proposal::review-proposal",
            class_name="provider",
        )
        effect["policy"]["delivery"] = {
            "k": "lit",
            "v": "composed",
            "type": {"kind": "primitive", "name": "String"},
        }

    def change_execute_argv(tree):
        effect = _effect(tree, owner="procedure:improve_experiment_proposal::execute", class_name="command")
        effect["argv"][0]["v"] = "--mutated"

    _expect_projection_rejection("docs", pairs["docs"], (1, 1), alter_guidance)
    _expect_projection_rejection(
        "reviewed_change", pairs["reviewed_change"], (4, 4), alter_account_operands
    )
    _expect_projection_rejection("docs", pairs["docs"], (1, 1), alter_slot_order)
    _expect_projection_rejection("docs", pairs["docs"], (1, 1), alter_authored_output_path)
    _expect_projection_rejection("deps_input", pairs["deps_input"], (1, 1), alter_dependencies)
    _expect_projection_rejection(
        "improve_experiment_proposal",
        pairs["improve_experiment_proposal"],
        (5, 3),
        add_default_policy,
    )
    _expect_projection_rejection(
        "improve_experiment_proposal",
        pairs["improve_experiment_proposal"],
        (5, 3),
        change_execute_argv,
    )


def assert_p3_carriers(workflows: list[Workflow], scratch: Path) -> None:
    """Compare the retained flat and reread closed carriers for Task10 P3."""

    scratch.mkdir(parents=True, exist_ok=True)
    real_keys = {
        "improve_experiment_proposal": "workflows/examples/improve_experiment_proposal.orc::run-experiment",
        "reviewed_change": "experiments/orc_vs_single_call/workflows/reviewed_change.orc::reviewed-change",
        "best_of_n": "experiments/orc_vs_single_call/workflows/best_of_n.orc::best-of-n",
    }
    expected = {
        "improve_experiment_proposal": (5, 3),
        "reviewed_change": (4, 4),
        "best_of_n": (2, 2),
    }
    pairs = {}
    for name, key in real_keys.items():
        workflow = _one(row for row in workflows if row.key == key)
        prepared, flat, typed, closed = _pair(workflow, scratch / name)
        assert prepared.workflow == workflow
        pairs[name] = (flat, typed, closed)
        _compare_pair(name, flat, typed, closed, expected[name])

    fixture_pairs = _fixture_types_and_assets(scratch, scratch / "fixtures")
    pairs.update(
        {
            "docs": fixture_pairs["docs"],
            "deps_asset": fixture_pairs["asset"],
            "deps_input": fixture_pairs["input"],
        }
    )
    pairs["private_owners"] = _private_nominal_pair(scratch)
    _calculated_and_authored_label_pair(scratch)
    _reject_p3_mutations(pairs)
