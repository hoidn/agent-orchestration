"""Direct source lowering for the bounded dynamic Workflow Lisp target."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path

from .. import compiler, syntax
from ..build import _select_entry_workflow_from_surface
from ..command_boundaries import CertifiedAdapterBinding, build_command_boundary_environment
from ..contracts import derive_prompt_guided_structured_result_contract
from ..definitions import WorkflowLispModule
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..modules import build_import_scope, resolve_module_graph
from ..normalized_type_descriptor import compiler_normalized_type_descriptor
from ..prompts import build_prompt_catalog, elaborate_prompt_definitions
from ..reader import SourceReadTrace
from ..result_guidance import parse_return_spec
from ..syntax import SyntaxBool, SyntaxFloat, SyntaxIdentifier, SyntaxInt, SyntaxKeyword, SyntaxList, SyntaxString
from ..workflows import _resolve_workflow_param_default, elaborate_workflow_definitions, build_extern_environment
from ..closed.effects import require_command_closures
from ..closed.program import canonical_configuration, logical_asset_base_for_module
from orchestrator.workflow.prompt_fragment_contract import _RENDERERS_BY_KIND
from orchestrator.workflow.pure_expr import coerce_pure_value, PureExprEvaluationError
from .program import DynamicProgram, SCHEMA, SOURCE_MAP_SCHEMA, _OPERATORS, _node_children, _pointer, schema_reference


_FORMS = {"define", "fn", "let*", "if", "record", "field", "list", "at", "record-update", "fail", "command-result", "provider-result"}
_RESERVED = _FORMS | _OPERATORS
_DECLARATIONS = {"defrecord", "defenum", "defunion", "defpath", "defschema", "defprompt"}


def _invalid(node, message, *, code="dynamic_source_invalid"):
    return LispFrontendCompileError((LispFrontendDiagnostic(
        code=code, message=message, span=node.span,
        form_path=getattr(node, "form_path", ("workflow-lisp",)),
    ),))


def _items(node, size=None):
    if not isinstance(node, SyntaxList) or (size is not None and len(node.items) != size):
        raise _invalid(node, "malformed source form")
    return node.items


def _symbol(node, *, binder=False):
    if not isinstance(node, SyntaxIdentifier) or not node.resolved_name or (binder and node.resolved_name in _RESERVED):
        raise _invalid(node, "expected an ordinary name")
    return node.resolved_name


def _binders(nodes):
    names = [_symbol(node, binder=True) for node in nodes]
    if len(names) != len(set(names)):
        raise _invalid(nodes[-1], "duplicate binding name")
    return names


@dataclass(frozen=True)
class DynamicSourceCompilation:
    program: DynamicProgram
    source_paths: Mapping[str, Path]
    lowerer: object | None = field(default=None, compare=False, repr=False)


class _Lowerer:
    def __init__(self, graph, linked, commands, externs, trace):
        self.graph, self.linked, self.commands, self.externs, self.trace = graph, linked, commands, externs, trace
        self.definitions, self.schemas, self.bindings, self.locations = {}, {}, {}, {}
        self.scopes, self.type_envs, self.members, self.prompts = {}, {}, {}, {}
        self.definition_locations, self.boundary_locations = {}, {}
        self.effect_subjects = {}
        self.expression_paths = {}
        for module in graph.topological_order:
            source = graph.modules_by_name[module]
            preliminary = WorkflowLispModule(
                language_version=source.syntax_module.language_version,
                target_dsl_version=source.syntax_module.target_dsl_version,
                module_name=module, imports=source.syntax_module.imports,
                exports=source.syntax_module.exports, definitions=(), span=source.syntax_module.span, schemas=(),
            )
            self.scopes[module] = build_import_scope(preliminary, export_surfaces_by_name=graph.export_surfaces_by_name)
            self.type_envs[module] = compiler.linked_module_type_environment(linked, module)
            selected = linked.graph.modules_by_name[module].syntax_module
            catalog = build_prompt_catalog(module, elaborate_prompt_definitions(selected), type_env=self.type_envs[module])
            for prompt in catalog.definitions_by_name.values():
                self.prompts[prompt.qualified_name] = (module, prompt)
            if source.syntax_module.target_dsl_version != "3.0":
                continue
            local = {}
            for form in source.syntax_module.forms:
                row = form.items
                head = syntax.syntax_head_name(syntax.syntax_node_datum(form))
                if head in _DECLARATIONS:
                    name = _symbol(row[1])
                elif head == "define":
                    _items(form.datum, 3)
                    signature = _items(row[1])
                    if not signature:
                        raise _invalid(row[1], "helper requires a name")
                    name = _symbol(signature[0], binder=True)
                    self.members[f"{module}::{name}"] = (_binders(signature[1:]), row[2], None, form)
                elif head == "defworkflow":
                    workflow = elaborate_workflow_definitions(replace(source.syntax_module, forms=(form,)))[0]
                    if workflow.publication_policy is not None or len(row) != 6:
                        raise _invalid(form, "workflow publication policies are outside dynamic qualification")
                    name = _symbol(row[1], binder=True)
                    params = _binders([param.items[0] for param in _items(row[2])])
                    self.members[f"{module}::{name}"] = (params, workflow.body.datum, workflow, form)
                else:
                    raise _invalid(form, f"unsupported dynamic declaration {head!r}")
                if name in local:
                    raise _invalid(form, f"duplicate declaration {name!r}")
                local[name] = form
            # Validate the full export/import surface, including unused helpers.
            from ..modules import derive_export_surface
            derive_export_surface(source.syntax_module)
        def index_expression(node, path):
            self.expression_paths[id(node)] = path
            if isinstance(node, SyntaxList):
                for index, child in enumerate(node.items):
                    index_expression(child, (*path, str(index)))
        for _, body, _, _ in self.members.values():
            index_expression(body, ("body",))

    def owner(self, module):
        return {"module": module, "asset_base": logical_asset_base_for_module(module)}

    def located(self, value, node, module, form_path=None):
        path = tuple(form_path or getattr(node, "form_path", ("workflow-lisp", "expression")))
        self.locations[id(value)] = (node.span, getattr(self, "emitted_module", module), (*path, *self.expression_paths.get(id(node), ())))
        return value

    def type(self, name, node, module):
        ref = self.type_envs[module].resolve_type(name, span=node.span, form_path=getattr(node, "form_path", ("workflow-lisp", "schema")))
        descriptor = compiler_normalized_type_descriptor(ref, type_env=self.type_envs[module])
        self.add_descriptor(descriptor)
        return ref, descriptor

    def add_descriptor(self, descriptor):
        self.schemas[schema_reference(descriptor)] = descriptor
        # Catalog admission checks each nominal nested declaration as well.
        if descriptor["kind"] == "record":
            for field in descriptor["fields"]:
                self.add_descriptor(field["type"])
        elif descriptor["kind"] == "union":
            for variant in descriptor["variants"]:
                for field in variant["fields"]:
                    self.add_descriptor(field["type"])
        elif descriptor["kind"] in {"list", "optional"}:
            self.add_descriptor(descriptor["item"])
        elif descriptor["kind"] == "map":
            self.add_descriptor(descriptor["key"])
            self.add_descriptor(descriptor["value"])

    def binding(self, module):
        if module not in self.bindings:
            self.bindings[module] = {
                "owner": self.owner(module), "types": {},
                "configuration": canonical_configuration(self.commands, origins={}, externs=self.externs, asset_base=logical_asset_base_for_module(module)),
            }
        return self.bindings[module]

    def callable(self, node, module):
        name = _symbol(node)
        local = f"{module}::{name}"
        if local in self.members:
            return local
        scope = self.scopes[module]
        for resolve in (scope.resolve_function_name, scope.resolve_workflow_name):
            canonical = resolve(name, span=node.span, form_path=("workflow-lisp", "call"))
            if canonical in self.members:
                return canonical
        return None

    def lower(self, node, scope, module, owner):
        def result(value, free=()):
            return self.located(value, node, module), set(free)
        if isinstance(node, (SyntaxBool, SyntaxInt, SyntaxFloat, SyntaxString)):
            return result({"k": "lit", "v": node.value})
        if isinstance(node, SyntaxIdentifier):
            if node.resolved_name in scope:
                return result({"k": "name", "n": node.resolved_name}, (node.resolved_name,))
            code = self.callable(node, module)
            if code is not None:
                return result({"k": "fn", "code": code, "captures": []})
            raise _invalid(node, f"unbound name {node.resolved_name!r}")
        row = _items(node)
        if not row:
            raise _invalid(node, "empty application")
        head = row[0].resolved_name if isinstance(row[0], SyntaxIdentifier) else None
        def children(nodes):
            lowered, free = [], set()
            for child in nodes:
                value, used = self.lower(child, scope, module, owner)
                lowered.append(value)
                free.update(used)
            return lowered, free
        if head == "fn":
            _items(node, 3)
            params = _binders(_items(row[1]))
            emitted = getattr(self, "emitted_module", module)
            code = f"{emitted}::{owner}$fn/" + "/".join(self.expression_paths[id(node)])
            if code in self.members or code in self.definitions:
                raise _invalid(node, "lexical closure identifier conflicts with a declared helper")
            body, free = self.lower(row[2], scope | set(params), module, owner)
            captures = sorted(free - set(params))
            self.definitions[code] = {"params": params, "captures": captures, "body": body, "owner": self.owner(emitted), "boundary": None}
            self.definition_locations[code] = (node.span, emitted, (*node.form_path, *self.expression_paths[id(node)]))
            values = [self.located({"k": "name", "n": name}, node, module) for name in captures]
            return result({"k": "fn", "code": code, "captures": values}, captures)
        if head == "let*":
            _items(node, 3)
            rows = [_items(binding, 2) for binding in _items(row[1])]
            names = _binders([binding[0] for binding in rows])
            local, bound, free, bindings = set(scope), set(), set(), []
            for name, binding in zip(names, rows):
                value, used = self.lower(binding[1], local, module, owner)
                free.update(used - bound)
                bindings.append([name, value])
                local.add(name)
                bound.add(name)
            body, used = self.lower(row[2], local, module, owner)
            return result({"k": "let", "bindings": bindings, "body": body}, free | (used - bound))
        if head in {"record", "record-update"}:
            free, fields = set(), []
            start = 1
            value = {"k": head}
            if head == "record-update":
                if len(row) < 3:
                    raise _invalid(node, "record-update requires a base and a field")
                value["base"], free = self.lower(row[1], scope, module, owner)
                start = 2
            seen = set()
            for field in row[start:]:
                key, expression = _items(field, 2)
                name = key.value if isinstance(key, SyntaxString) else _symbol(key)
                if not name or name in seen:
                    raise _invalid(key, "record field names must be nonempty and unique")
                seen.add(name)
                child, used = self.lower(expression, scope, module, owner)
                fields.append([name, child])
                free.update(used)
            return result({**value, "fields": fields}, free)
        if head == "fail":
            _items(node, 2)
            if not isinstance(row[1], SyntaxString) or not row[1].value:
                raise _invalid(row[1], "fail requires a nonempty literal string")
            return result({"k": "fail", "reason": row[1].value})
        if head == "field":
            _items(node, 3)
            if not isinstance(row[2], SyntaxString) or not row[2].value:
                raise _invalid(row[2], "field requires a nonempty literal string")
            base, free = self.lower(row[1], scope, module, owner)
            return result({"k": "field", "base": base, "name": row[2].value}, free)
        if head in {"if", "at"}:
            _items(node, 4 if head == "if" else 3)
            values, free = children(row[1:])
            return result({"k": head, **dict(zip(("cond", "then", "else") if head == "if" else ("base", "index"), values))}, free)
        if head == "list" or head in _OPERATORS:
            values, free = children(row[1:])
            return result({"k": "list", "items": values} if head == "list" else {"k": "op", "name": head, "args": values}, free)
        if head in {"command-result", "provider-result"}:
            return self.effect(node, scope, module, owner)
        values, free = children(row)
        return result({"k": "call", "callee": values[0], "args": values[1:]}, free)

    def effect(self, node, scope, module, owner):
        row = _items(node)
        if len(row) < 4:
            raise _invalid(node, "effect requires a bound name and keyword operands")
        head, target = _symbol(row[0]), _symbol(row[1])
        keywords = self.keywords(row[2:], node)
        allowed = ({":argv", ":adapter", ":inputs", ":input-type", ":returns"} if head == "command-result" else
                   {":prompt", ":inputs", ":returns", ":model", ":effort", ":timeout-sec", ":delivery", ":prompt-dependencies"})
        if set(keywords) - allowed:
            raise _invalid(node, "effect contains an unsupported clause")
        if head == "command-result" and ":adapter" in keywords:
            target = _symbol(keywords[":adapter"])
        bindings, free = [], set()
        def operand(expression, *, argv=False):
            if argv and isinstance(expression, (SyntaxString, SyntaxBool, SyntaxInt, SyntaxFloat)):
                if isinstance(expression, (SyntaxInt, SyntaxFloat)):
                    try:
                        coerce_pure_value(expression.value, {"kind": "primitive", "name": "Int" if isinstance(expression, SyntaxInt) else "Float"}, context="literal argv")
                    except PureExprEvaluationError as exc:
                        raise _invalid(expression, str(exc)) from exc
                value, used = self.located({"k": "lit", "v": str(expression.value)}, expression, module), set()
            else:
                value, used = self.lower(expression, scope, module, owner)
            name = f"$effect{len(bindings)}"
            while name in scope:
                name += "$"
            bindings.append([name, value])
            free.update(used)
            return self.located({"k": "name", "n": name}, expression, module)
        if head == "command-result":
            effect, result_node, result_module = self.command(node, target, keywords, module, operand)
            subjects = {("result",): (result_node.span, result_module, ("workflow-lisp", "command-result", "returns"))}
        else:
            effect, subjects = self.provider(node, target, keywords, module, operand)
        self.located(effect, node, module)
        self.effect_subjects[id(effect)] = subjects
        if bindings:
            return self.located({"k": "let", "bindings": bindings, "body": effect}, node, module), free
        return effect, free

    @staticmethod
    def keywords(nodes, node):
        if len(nodes) % 2:
            raise _invalid(node, "keyword clauses require one value")
        result = {}
        for key, value in zip(nodes[::2], nodes[1::2]):
            if not isinstance(key, SyntaxKeyword) or key.value in result:
                raise _invalid(key, "keyword clauses must be unique")
            result[key.value] = value
        return result

    def result_contract(self, result_node, module, owner, *, resolved=None):
        spec = parse_return_spec(result_node, form_path=("workflow-lisp", "returns"), label="effect return type") if resolved is None else resolved.declaration.return_spec
        ref, descriptor = self.type(spec.type_name, spec, module)
        contract = derive_prompt_guided_structured_result_contract(
            ref, workflow_name=owner, step_id="effect", type_env=self.type_envs[module],
            span=spec.span, form_path=("workflow-lisp", "returns"), guidance=spec.guidance,
            descriptor_projector=lambda nested: compiler_normalized_type_descriptor(nested, type_env=self.type_envs[module]),
            whole_value=True,
        )
        payload = dict(contract.payload)
        payload.pop("path", None)
        for field in payload.get("fields", ()):
            field.pop("source_map_subject", None)
            field.pop("source_map_subjects_by_variant", None)
        return descriptor, {"kind": contract.contract_kind, "payload": payload}

    def command(self, node, target, keywords, module, operand):
        binding = self.commands.get(target)
        if binding is None:
            raise _invalid(node, "command has no trusted binding")
        if ":returns" not in keywords:
            raise _invalid(node, "command requires explicit returns")
        descriptor, contract = self.result_contract(keywords[":returns"], module, target)
        row = self.binding(module)["configuration"]["commands"][target]
        effect = {"k": "perform", "class": "command", "result": descriptor, "repeat": "never" if binding.must_not_repeat else "rerun",
                  "boundary": target, "command": row["stable_command"], "closure": row["closure"], "contract": contract, "argv": []}
        certified = isinstance(binding, CertifiedAdapterBinding)
        if ":adapter" in keywords and (not certified or ":inputs" not in keywords or ":argv" in keywords):
            raise _invalid(node, "adapter mode requires a certified binding and inputs, without argv")
        if certified and ":inputs" in keywords and ":adapter" not in keywords:
            raise _invalid(node, "certified document mode requires the existing adapter clause")
        if certified:
            for name in {binding.output_type_name, *(field.type_name for field in binding.input_signature)}:
                _, association = self.type(name, node, module)
                self.binding(module)["types"][name] = schema_reference(association)
            if ":input-type" in keywords:
                raise _invalid(keywords[":input-type"], "certified commands forbid input-type")
        elif (":inputs" in keywords) != (":input-type" in keywords):
            raise _invalid(node, "external document requires both inputs and input-type")
        if ":argv" not in keywords and ":inputs" not in keywords:
            raise _invalid(node, "command requires argv or certified document inputs")
        if not certified and ":argv" not in keywords:
            raise _invalid(node, "external command requires argv")
        input_descriptor = None
        if ":input-type" in keywords:
            _, input_descriptor = self.type(_symbol(keywords[":input-type"]), keywords[":input-type"], module)
            if input_descriptor["kind"] != "record":
                raise _invalid(keywords[":input-type"], "external input-type requires a declared record")
            effect["input_type"] = input_descriptor
        for key, expression in keywords.items():
            if key == ":argv":
                values = _items(expression)
                stable = binding.stable_command
                if len(values) < len(stable) or any(not isinstance(child, SyntaxString) or child.value != token for child, token in zip(values, stable)):
                    raise _invalid(expression, "argv must begin with the declared stable command")
                effect["argv"] = [operand(child, argv=True) for child in values[len(stable):]]
            elif key == ":inputs":
                supplied = []
                for field in _items(expression):
                    name, child = _items(field, 2)
                    supplied.append((_symbol(name), operand(child)))
                names = [name for name, _ in supplied]
                if len(names) != len(set(names)):
                    raise _invalid(expression, "document fields must be unique")
                values = dict(supplied)
                if certified:
                    signature = binding.input_signature
                    known = {field.name for field in signature}
                    if set(values) - known or any(field.required and field.name not in values for field in signature):
                        raise _invalid(expression, "document fields do not match the certified signature")
                    effect["document"] = [[field.transport_key, values[field.name]] for field in signature if field.name in values]
                else:
                    names = [field["name"] for field in input_descriptor["fields"]]
                    if set(names) != set(values):
                        raise _invalid(expression, "document fields do not match input-type")
                    effect["document"] = [[name, values[name]] for name in names]
        return effect, keywords[":returns"], module

    def provider(self, node, target, keywords, module, operand):
        configuration = self.binding(module)["configuration"]
        binding = configuration["providers"].get(target)
        if binding is None or ":prompt" not in keywords:
            raise _invalid(node, "provider requires trusted provider and prompt bindings")
        prompt_node = keywords[":prompt"]
        resolved, prompt_module = None, module
        if isinstance(prompt_node, SyntaxList):
            application = _items(prompt_node)
            if not application:
                raise _invalid(prompt_node, "prompt application is empty")
            name = _symbol(application[0])
            canonical = f"{module}::{name}"
            if canonical not in self.prompts:
                canonical = self.scopes[module].resolve_prompt_name(name, span=application[0].span, form_path=("workflow-lisp", "prompt"))
            selected = self.prompts.get(canonical)
            if selected is None:
                raise _invalid(application[0], "prompt has no declaration")
            prompt_module, resolved = selected
            self.binding(prompt_module)
            descriptor, contract = self.result_contract(resolved.declaration.return_spec, prompt_module, target, resolved=resolved)
            if ":returns" in keywords:
                explicit, _ = self.result_contract(keywords[":returns"], module, target)
                if explicit != descriptor:
                    raise _invalid(keywords[":returns"], "explicit result differs from prompt declaration")
        else:
            prompt_name = _symbol(prompt_node)
            if prompt_name not in configuration["prompts"] or ":returns" not in keywords:
                raise _invalid(prompt_node, "extern prompt requires a bound prompt and explicit returns")
            descriptor, contract = self.result_contract(keywords[":returns"], module, target)
        effect = {"k": "perform", "class": "provider", "result": descriptor, "repeat": "rerun", "provider": binding["provider_id"],
                  "prompt_owner": self.owner(prompt_module), "inputs": [], "dependencies": None, "policy": {}, "contract": contract}
        subjects = {("result",): ((resolved.declaration.return_spec.span if resolved else keywords[":returns"].span), prompt_module, ("workflow-lisp", "defprompt" if resolved else "provider-result", "returns")),
                    ("prompt",): ((resolved.declaration.span if resolved else prompt_node.span), prompt_module, ("workflow-lisp", "prompt"))}
        for key, expression in keywords.items():
            if key == ":prompt":
                if resolved is None:
                    effect["prompt"] = dict(configuration["prompts"][_symbol(prompt_node)])
                else:
                    fills = self.keywords(application[1:], prompt_node)
                    expected = {":" + slot.declaration.name for slot in resolved.slots}
                    if set(fills) != expected:
                        raise _invalid(prompt_node, "prompt fills must exactly match the declaration")
                    values = {name[1:]: operand(value) for name, value in fills.items()}
                    declaration = resolved.declaration
                    rows = []
                    for index, slot in enumerate(resolved.slots):
                        fill = slot.declaration
                        kind = fill.kind.value
                        if slot.refinement_type_ref is not None:
                            fill_descriptor = compiler_normalized_type_descriptor(slot.refinement_type_ref, type_env=self.type_envs[prompt_module])
                            self.add_descriptor(fill_descriptor)
                        elif kind in {"text", "value"}:
                            _, fill_descriptor = self.type("String" if kind == "text" else "Value", fill, prompt_module)
                        else:
                            raise _invalid(fill, "doc/path fills require a declared defpath refinement")
                        rows.append({"name": fill.name, "kind": kind, "type": fill_descriptor, "value": values[fill.name],
                                     "renderer_id": None if kind == "doc" else _RENDERERS_BY_KIND[kind], "output_role": fill.output_role.value,
                                     "placeholder_ordinals": [i for i, name in enumerate(declaration.template.placeholder_names) if name == fill.name]})
                        subjects[("prompt", "fills", index)] = (fill.span, prompt_module, fill.form_path)
                    effect["prompt"] = {"template": declaration.template.text, "fills": rows}
                    subjects[("prompt", "template")] = (declaration.template.span, prompt_module, declaration.form_path)
            elif key == ":inputs":
                if _items(expression):
                    raise _invalid(expression, "extern inputs lack boundary schemas; use defprompt fills")
            elif key in {":model", ":effort"}:
                effect["policy"][key[1:]] = operand(expression)
            elif key == ":timeout-sec":
                if not isinstance(expression, SyntaxInt) or expression.value <= 0:
                    raise _invalid(expression, "provider timeout requires a positive Int literal")
                effect["policy"]["timeout_sec"] = self.located({"k": "lit", "v": expression.value}, expression, module)
            elif key == ":delivery":
                if not isinstance(expression, SyntaxString) or expression.value != "composed":
                    raise _invalid(expression, "provider delivery requires literal composed")
                effect["policy"]["delivery"] = self.located({"k": "lit", "v": expression.value}, expression, module)
            elif key == ":prompt-dependencies":
                effect["dependencies"] = self.dependencies(expression, operand)
        effect["policy"] = dict(sorted(effect["policy"].items()))
        return effect, subjects

    def dependencies(self, node, operand):
        result = {"required": [], "optional": [], "position": "prepend", "instruction": None}
        sections = self.keywords(_items(node), node)
        for key, value in sections.items():
            if key not in {":required", ":optional", ":position", ":instruction"}:
                raise _invalid(node, "invalid prompt dependency clause")
            name = key[1:]
            if name in {"required", "optional"}:
                values = _items(value)
                if not values:
                    raise _invalid(value, "dependency lists must be nonempty")
                result[name] = [operand(child) for child in values]
            elif name == "position":
                result[name] = _symbol(value)
            elif not isinstance(value, SyntaxString):
                raise _invalid(value, "dependency instruction requires literal text")
            else:
                result[name] = value.value
        if not result["required"] and not result["optional"]:
            raise _invalid(node, "prompt dependencies require required or optional operands")
        return result

    def compile(self, entry):
        for code, (params, body, workflow, form) in self.members.items():
            module, _, member = code.rpartition("::")
            boundary = None
            subjects = {}
            if workflow is not None:
                rows, defaults = [], {}
                for index, param in enumerate(workflow.params):
                    ref, descriptor = self.type(param.type_name, param, module)
                    rows.append([param.name, schema_reference(descriptor)])
                    subjects[("params", index)] = (param.span, module, param.form_path)
                    if param.default_value is not None:
                        defaults[param.name] = _resolve_workflow_param_default(param=param, param_type=ref).normalized_value
                        subjects[("defaults", param.name)] = (param.default_value.span, module, param.form_path)
                _, descriptor = self.type(workflow.return_type_name, workflow.return_spec, module)
                boundary = {"params": rows, "defaults": defaults, "result": schema_reference(descriptor)}
                subjects[("result",)] = (workflow.return_spec.span, module, workflow.form_path)
            lowered, _ = self.lower(body, set(params), module, member)
            self.definitions[code] = {"params": params, "captures": [], "body": lowered, "owner": self.owner(module), "boundary": boundary}
            self.definition_locations[code] = (form.span, module, form.form_path)
            self.boundary_locations[code] = subjects
        sources = {}
        for module, source in self.graph.modules_by_name.items():
            relative = source.path.relative_to(source.source_root).as_posix()
            sources[module] = {"root_role": "source", "relative_path": relative, "source_sha256": "sha256:" + hashlib.sha256(self.trace.raw_bytes_by_path[source.path.resolve()]).hexdigest()}
        return self.assemble(entry, sources)

    def assemble(self, entry, sources):
        """Admit ordinary definitions and source locations as one checked program."""
        entries = {}
        def locate(pointer, location):
            span, module, path = location
            relative = sources[module]["relative_path"]
            entries[pointer] = {"source": module, "form_path": list(path), "span": {
                side: {"path": relative, "line": getattr(span, side).line, "column": getattr(span, side).column, "offset": getattr(span, side).offset}
                for side in ("start", "end")
            }}
        def walk(value, pointer):
            locate(pointer, self.locations[id(value)])
            for segments, location in self.effect_subjects.get(id(value), {}).items():
                subject = pointer
                for segment in segments:
                    subject = _pointer(subject, segment)
                locate(subject, location)
            for child_pointer, child in _node_children(value, pointer):
                walk(child, child_pointer)
        for code, definition in self.definitions.items():
            pointer = _pointer("/definitions", code)
            locate(pointer, self.definition_locations[code])
            walk(definition["body"], _pointer(pointer, "body"))
            for segments, location in self.boundary_locations.get(code, {}).items():
                boundary_pointer = _pointer(pointer, "boundary")
                for segment in segments:
                    boundary_pointer = _pointer(boundary_pointer, segment)
                locate(boundary_pointer, location)
        tree = {"schema": SCHEMA, "target": "3.0", "entry": entry, "budget": self.graph.modules_by_name[self.graph.entry_module_name].syntax_module.budget,
                "definitions": self.definitions, "schemas": self.schemas, "bindings": self.bindings, "sources": sources, "source_map": {"schema": SOURCE_MAP_SCHEMA, "entries": entries}}
        try:
            return DynamicProgram.from_artifact(json.dumps(tree, ensure_ascii=False, allow_nan=False))
        except ValueError as exc:
            pointer = getattr(exc, "location", None)
            nearest = max((key for key in entries if pointer and (pointer == key or pointer.startswith(key + "/"))), key=len, default=_pointer("/definitions", entry))
            location = entries[nearest]
            source = self.graph.modules_by_name.get(location["source"])
            from ..spans import SourcePosition, SourceSpan
            span = SourceSpan(*(SourcePosition(str(source.path) if source is not None else "<repl>", **{key: value for key, value in location["span"][side].items() if key != "path"}) for side in ("start", "end")))
            raise LispFrontendCompileError((LispFrontendDiagnostic(code="dynamic_source_invalid", message=str(exc), span=span, form_path=tuple(location["form_path"])),)) from exc


def compile_source(path: Path, *, source_roots=(), entry_workflow=None, command_boundaries=None, provider_externs=None, prompt_externs=None, source_read_trace=None) -> DynamicSourceCompilation:
    """Resolve source once, elaborate boundary declarations, and independently admit."""
    path = Path(path)
    trace = source_read_trace or SourceReadTrace()
    roots = compiler._effective_source_roots(path, source_roots=tuple(source_roots), source_read_trace=trace)
    attempt = trace._begin_module_graph_read_attempt(path)
    graph = resolve_module_graph(path, source_roots=roots, source_read_trace=trace)
    trace._complete_module_graph_read_attempt(attempt, module_paths=tuple(source.path for source in graph.modules_by_name.values()))
    source = graph.modules_by_name[graph.entry_module_name]
    if source.syntax_module.target_dsl_version != "3.0":
        raise _invalid(source.syntax_module, "dynamic source requires exact target 3.0", code="dynamic_target_required")
    if source.syntax_module.budget is None:
        raise _invalid(source.syntax_module, "entry module requires a positive budget", code="dynamic_budget_invalid")
    for module, imported in graph.modules_by_name.items():
        if module != graph.entry_module_name and imported.syntax_module.budget is not None:
            raise _invalid(imported.syntax_module, "library modules must omit budget", code="dynamic_budget_invalid")
    linked = compiler._compile_stage1_graph(compiler._select_stage1_source_declarations(graph, dynamic_compilation=True))
    commands = build_command_boundary_environment(command_boundaries).bindings_by_name
    require_command_closures(commands, manifest_path=None)
    externs = build_extern_environment(provider_externs=provider_externs, prompt_externs=prompt_externs).bindings_by_name
    lowerer = _Lowerer(graph, linked, commands, externs, trace)
    workflows = [code for code, row in lowerer.members.items() if code.startswith(graph.entry_module_name + "::") and row[2] is not None]
    available = {name: name for name in workflows}
    available.update({name.rpartition("::")[2]: name for name in workflows})
    selected = _select_entry_workflow_from_surface(
        graph.export_surfaces_by_name[graph.entry_module_name], requested_name=entry_workflow,
        available_names=available, source_path=path, entry_span=source.syntax_module.span,
    )
    entry = available[selected.canonical_name]
    try:
        program = lowerer.compile(entry)
    except RecursionError as exc:
        raise _invalid(source.syntax_module, "source nesting exceeds the bounded frontend") from exc
    return DynamicSourceCompilation(program, {module: source.path for module, source in graph.modules_by_name.items()}, lowerer)
