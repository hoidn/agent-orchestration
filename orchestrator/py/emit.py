"""Generate inspectable Workflow Lisp; the existing compiler checks the result."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, UnionType
from typing import Union, get_args, get_origin

from .declarations import Definition, Fill, MISSING, Prompt, fields_of, validate_field_names
from .diagnostics import (PythonFrontendError, PythonSite, PythonSourceMap,
                          SourceMapEntry, definition_site, python_span, remap_compiler_error)
from .trace import Expr, Trace, _require_host_input_target
from .imports import (CompilerCase, CompilerType, ImportedCallable, ImportedPrompt,
                      OrcMember, OrcModule, _GENERATOR)


PRIMITIVES = {str: "String", int: "Int", float: "Float", bool: "Bool"}


def _closed_union(annotation):
    args = get_args(annotation)
    return (get_origin(annotation) in {UnionType, Union} and args and
            all(getattr(case, "_orc_kind", None) == "variant" for case in args))


@dataclass(frozen=True)
class GeneratedModule:
    source_path: Path
    source_root: Path
    source_map: PythonSourceMap
    prompt_assets: dict[Path, bytes]
    module_name: str


@dataclass(frozen=True)
class GeneratedGraph:
    source_path: Path
    source_root: Path
    source_roots: tuple[Path, ...]
    modules: tuple[GeneratedModule, ...]
    source_map: PythonSourceMap
    prompt_assets: dict[Path, bytes]
    generated_to_python: dict[Path, Path]
    python_sources: dict[Path, bytes]
    source_reads: dict[Path, bytes]
    entry_aliases: dict[str, tuple[str, str]]
    asset_bindings: tuple[dict, ...] = ()

    @property
    def source_paths(self): return tuple(module.source_path for module in self.modules)


class _Writer:
    def __init__(self, path, source_map):
        self.path = str(path)
        self.source_map = source_map
        self.parts = []
        self.line = 1
        self.column = 1

    def write(self, text):
        self.parts.append(text)
        lines = text.split("\n")
        if len(lines) > 1:
            self.line += len(lines) - 1
            self.column = len(lines[-1]) + 1
        else:
            self.column += len(text)

    @contextmanager
    def mark(self, site, kind):
        line, column = self.line, self.column
        yield
        self.source_map.entries.append(SourceMapEntry(site,
            PythonSite(self.path, line, column, self.line, self.column), kind))

    def text(self): return "".join(self.parts)


class ModuleGenerator:
    def __init__(self, module, output_root, *, module_name=None, graph=None):
        self.graph = graph
        self.module = module
        logical = module_name or module.__name__
        if logical == "__main__":
            logical = Path(module.__file__).stem
        self.module_name = "py/" + logical.replace(".", "/")
        if any(part in {"", ".", ".."} for part in self.module_name.split("/")):
            raise PythonFrontendError("python_module_name", "Invalid logical module name")
        self.root = Path(output_root)
        self.path = self.root / (self.module_name + ".orc")
        self.source_map = PythonSourceMap()
        self.prompt_assets = {}
        self.writer = _Writer(self.path, self.source_map)
        self.type_names = {}
        self.union_names = {}
        self.type_order = []
        self.visiting = set()
        self.visited = set()
        self.definitions = []
        self.definition_names = {}
        self.prompt_names = {}
        self.traces = {}
        self.loop_binders = {}
        self.imports = {}
        self.fallback = PythonSite(str(module.__file__), 1)
        self._discover()

    def _discover(self):
        namespace = vars(self.module)
        selected = getattr(self.module, "__all__", None)
        for name, value in namespace.items():
            if _closed_union(value) and (self.graph is None or self.graph.type_owners.get(value, (None,))[0] == self.module.__name__):
                if value in self.union_names and self.union_names[value] != name:
                    raise PythonFrontendError("python_union_owner_ambiguous", "A closed union requires one defining alias", site=self.fallback)
                self.union_names[value] = name
        for name, value in namespace.items():
            if isinstance(value, type) and value.__module__ == self.module.__name__:
                if "_orc_kind" in value.__dict__ or issubclass(value, Enum):
                    self.type_names[value] = value.__name__
            elif isinstance(value, Definition) and value.__module__ == self.module.__name__:
                is_root = name in selected if selected is not None else not name.startswith("_")
                if is_root and (self.graph is None or self.graph.is_root_definition(value)):
                    self.require_definition(value)
            elif isinstance(value, Prompt) and value.owner == self.module.__name__ and value.extern_name is None:
                self.prompt_names.setdefault(id(value), (name, value))
        for annotation in (*self.type_names, *self.union_names):
            if getattr(annotation, "_orc_kind", None) != "variant":
                self.type_ref(annotation, site=self._type_site(annotation))
        # Cases still require valid fields even when their union is not exported.
        for annotation in self.type_names:
            if getattr(annotation, "_orc_kind", None) == "variant":
                for field_type in fields_of(annotation).values():
                    self.type_ref(field_type, site=self._type_site(annotation))

    def _type_site(self, annotation):
        if _closed_union(annotation): return self.fallback
        return getattr(annotation, "_orc_site", None) or definition_site(annotation)

    def require_definition(self, value):
        if isinstance(value, OrcMember):
            resolved = self.graph.resolve_member(value, self)
            if not isinstance(resolved, ImportedCallable) or resolved.kind != "workflow":
                raise PythonFrontendError("python_proc_effect_invalid", "calls_workflow requires an exported workflow", site=value._site)
            self.definition_names[id(value)] = self.graph.definition_ref(resolved, self)
            return
        if self.graph is not None and (isinstance(value, ImportedCallable) or value.__module__ != self.module.__name__):
            self.definition_names[id(value)] = self.graph.definition_ref(value, self)
            return
        if id(value) not in self.definition_names:
            if value.__module__ != self.module.__name__:
                raise PythonFrontendError("python_module_import_unsupported", "Cross-module generation requires the import bridge", site=value.site)
            self.definition_names[id(value)] = value.__name__
            self.definitions.append(value)

    def type_ref(self, annotation, *, site=None, signature=False):
        site = site or self.fallback
        if isinstance(annotation, OrcMember):
            if annotation._module._name == "std/host" and annotation._name == "HostReply":
                _require_host_input_target(self, site=site)
            name = self.import_name(annotation._module._name, annotation._name)
            if annotation._arguments:
                name += "[" + " ".join(self.type_ref(arg, site=site) for arg in annotation._arguments) + "]"
            return name
        if isinstance(annotation, CompilerType):
            if annotation._owner == "std/host" and annotation._name == "HostReply":
                _require_host_input_target(self, site=site)
            name = self.import_name(annotation._owner, annotation._name)
            if annotation._arguments:
                name += "[" + " ".join(self.type_ref(arg, site=site) for arg in annotation._arguments) + "]"
            return name
        if self.graph is not None and annotation in self.graph.type_owners:
            owner, name = self.graph.type_owners[annotation]
            if owner != self.module.__name__:
                return self.import_name(self.graph.logical_names[owner], name)
        if annotation in PRIMITIVES:
            return PRIMITIVES[annotation]
        origin, args = get_origin(annotation), get_args(annotation)
        if origin is list and len(args) == 1:
            return f"List[{self.type_ref(args[0], site=site, signature=signature)}]"
        if origin in {UnionType, Union} and type(None) in args and len(args) == 2:
            item = next(arg for arg in args if arg is not type(None))
            return f"Optional[{self.type_ref(item, site=site, signature=signature)}]"
        if getattr(annotation, "_orc_kind", None) == "variant":
            raise PythonFrontendError("python_variant_signature_unsupported", "A bare variant case is not a callable type; use its named closed union", site=site)
        if annotation in self.type_names or annotation in self.union_names:
            if annotation in self.visiting:
                raise PythonFrontendError("python_recursive_type", "Recursive Python types are unsupported", site=site)
            if annotation not in self.visited:
                self.visiting.add(annotation)
                if _closed_union(annotation):
                    cases = get_args(annotation)
                    for case in cases:
                        for child in fields_of(case).values(): self.type_ref(child, site=self._type_site(case))
                elif getattr(annotation, "_orc_kind", None) == "record":
                    for child in fields_of(annotation).values(): self.type_ref(child, site=self._type_site(annotation))
                elif isinstance(annotation, type) and issubclass(annotation, Enum):
                    self._validate_enum(annotation)
                self.visiting.remove(annotation)
                self.visited.add(annotation)
                self.type_order.append(annotation)
            return self.union_names[annotation] if annotation in self.union_names else self.type_names[annotation]
        raise PythonFrontendError("python_annotation_unsupported", f"Unsupported annotation {annotation!r}", site=site)

    def import_name(self, module_name, name):
        if module_name == self.module_name:
            return name
        alias = self.imports.setdefault(module_name, f"_import{len(self.imports)}")
        return alias + "." + name

    def _validate_enum(self, annotation):
        members = list(annotation.__members__.values())
        tokens = [member.value for member in members]
        # A member token must lex as one unqualified, nonliteral identifier.
        from orchestrator.workflow_lisp.reader import read_sexpr_text
        from orchestrator.workflow_lisp.sexpr import SymbolAtom
        valid = len(members) == len(annotation)
        for token in tokens:
            if not isinstance(token, str) or not token or re.search(r'[.\s()\[\]{}";:\\]', token):
                valid = False
                continue
            try:
                parsed = read_sexpr_text(token, source_path=definition_site(annotation).path)
                valid = valid and len(parsed.items) == 1 and isinstance(parsed.items[0], SymbolAtom)
            except Exception:
                valid = False
        if not valid:
            raise PythonFrontendError("python_enum_invalid", "Enum values must be unique strings admitted as enum identifiers", site=definition_site(annotation))

    def _trace_all(self):
        index = 0
        while index < len(self.definitions):
            definition = self.definitions[index]
            if id(definition) in self.traces:
                index += 1
                continue
            signature, annotations, returns = definition.signature()
            if definition.effects is not MISSING:
                for effect in definition.effects:
                    if effect.kind == "calls-workflow":
                        self.require_definition(effect.subject)
            for annotation in (*annotations.values(), returns):
                self.type_ref(annotation, site=definition.site, signature=True)
            trace = Trace(self, definition)
            arguments = {name: trace.reference(name, annotation, site=definition.site)
                         for name, annotation in annotations.items()}
            if self.graph is not None:
                arguments = {name: trace.reference(name, self.graph.resolve_annotation(annotation, self, site=definition.site), site=definition.site)
                             for name, annotation in annotations.items()}
            result = trace.run(definition.function, arguments)
            self.traces[id(definition)] = (trace, result, signature, annotations, returns)
            index += 1
        for _name, prompt in self.prompt_names.values():
            self.type_ref(prompt.returns, site=prompt.site)
            for fill in prompt.signature().values():
                if fill.annotation is not None: self.type_ref(fill.annotation, site=prompt.site)

    def emit(self):
        if not self.traces:
            self._trace_all()
        w = self.writer
        w.write('(workflow-lisp\n  (:language "0.1")\n  (:target-dsl ')
        self.literal(str(getattr(self.module, "TARGET", "2.39")))
        w.write(f")\n  (defmodule {self.module_name})\n")
        import_offset = len(w.text())
        exports = self._exports()
        if exports: w.write("  (export " + " ".join(exports) + ")\n")
        for annotation in self.type_order: self.emit_type(annotation)
        for name, prompt in self.prompt_names.values(): self.emit_prompt(name, prompt)
        for definition in self.definitions: self.emit_definition(definition)
        w.write(")\n")
        imports = "".join(f"  (import {name} :as {alias})\n" for name, alias in self.imports.items())
        content = w.text()
        content = content[:import_offset] + imports + content[import_offset:]
        if self.imports:
            count = len(self.imports)
            self.source_map.entries = [replace(entry, generated=replace(entry.generated,
                line=entry.generated.line + count,
                end_line=None if entry.generated.end_line is None else entry.generated.end_line + count))
                for entry in self.source_map.entries]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(content, encoding="utf-8")
        source_path = Path(self.module.__file__)
        raw = self.graph.python_sources[source_path.resolve()] if self.graph is not None else source_path.read_bytes()
        self.source_map.source_hashes[str(source_path)] = "sha256:" + sha256(raw).hexdigest()
        for path, raw in self.prompt_assets.items():
            self.source_map.source_hashes[str(path)] = "sha256:" + sha256(raw).hexdigest()
        return GeneratedModule(self.path, self.root, self.source_map, self.prompt_assets, self.module_name)

    def emit_imports(self):
        for module_name, alias in self.imports.items():
            site = self.fallback
            if self.graph is not None:
                for value in vars(self.module).values():
                    reference = value._module if isinstance(value, OrcMember) else value
                    if isinstance(reference, OrcModule) and reference._name == module_name:
                        site = reference._site
                        break
            with self.writer.mark(site, "import"):
                self.writer.write(f"  (import {module_name} :as {alias})\n")
            self.writer.source_map.entries.append(SourceMapEntry(site,
                PythonSite(f"<module:{module_name}>", 1, 1, 1, 1), "import"))

    def _exports(self):
        selected = getattr(self.module, "__all__", None)
        if self.graph is not None:
            names = []
            for name, value in vars(self.module).items():
                if not (name in selected if selected is not None else not name.startswith("_")): continue
                if isinstance(value, Definition) and value.__module__ == self.module.__name__:
                    if id(value) in self.definition_names:
                        names.append(value.__name__)
                elif isinstance(value, Prompt) and value.owner == self.module.__name__ and value.extern_name is None:
                    names.append(self.prompt_names[id(value)][0])
                elif isinstance(value, type) and value in self.type_names and getattr(value, "_orc_kind", None) != "variant":
                    names.append(self.type_names[value])
                elif _closed_union(value) and value in self.union_names:
                    names.append(self.union_names[value])
            return list(dict.fromkeys(names))
        names = []
        candidates = {value.__name__: value for value in self.definitions}
        candidates.update({name: value for value, name in self.type_names.items() if getattr(value, "_orc_kind", None) != "variant"})
        candidates.update({name: value for value, name in self.union_names.items()})
        candidates.update({name: value for name, value in self.prompt_names.values()})
        for name in (selected if selected is not None else candidates):
            if name in candidates and (selected is not None or not name.startswith("_")):
                names.append(name)
        return names

    def emit_type(self, annotation):
        w = self.writer
        with w.mark(self._type_site(annotation), "declaration"):
            name = self.type_ref(annotation)
            kind = getattr(annotation, "_orc_kind", None)
            if _closed_union(annotation):
                w.write(f"  (defunion {name}")
                for case in get_args(annotation):
                    w.write(f" ({case.__name__}")
                    self.emit_fields(fields_of(case))
                    w.write(")")
                w.write(")\n")
            elif kind == "record":
                w.write(f"  (defrecord {name}")
                self.emit_fields(fields_of(annotation))
                w.write(")\n")
            elif kind == "path":
                w.write(f"  (defpath {name} :kind relpath :under ")
                self.literal(annotation._orc_under)
                w.write(" :must-exist " + ("true" if annotation._orc_must_exist else "false") + ")\n")
            else:
                w.write(f"  (defenum {name} " + " ".join(member.value for member in annotation) + ")\n")

    def emit_fields(self, annotations):
        for name, annotation in annotations.items():
            self.writer.write(f" ({name} {self.type_ref(annotation)})")

    def emit_prompt(self, name, prompt):
        w = self.writer
        with w.mark(prompt.site, "prompt"):
            w.write(f"  (defprompt {name} (:fills")
            for key, fill in prompt.signature().items():
                w.write(f" ({key} :{fill.kind}")
                if fill.out: w.write(" :out")
                if fill.annotation is not None: w.write(" " + self.type_ref(fill.annotation))
                w.write(")")
            w.write(") -> " + self.type_ref(prompt.returns) + "\n    ")
            self.literal(prompt.template(self.prompt_assets))
            w.write(")\n")

    def emit_definition(self, definition):
        w = self.writer
        trace, result, signature, annotations, returns = self.traces[id(definition)]
        self.fallback = definition.site
        with w.mark(definition.site, "definition"):
            head = {"workflow": "defworkflow", "proc": "defproc", "pure": "defun"}[definition.kind]
            w.write(f"  ({head} {definition.__name__} (")
            for index, (name, annotation) in enumerate(annotations.items()):
                if index: w.write(" ")
                w.write(f"({name} {self.type_ref(annotation)}")
                default = signature.parameters[name].default
                if definition.kind == "workflow" and default is not signature.empty:
                    w.write(" :default ")
                    self.expression(default, expected=annotation)
                w.write(")")
            w.write(") -> " + self.type_ref(returns))
            if definition.kind == "proc":
                from orchestrator.workflow_lisp.syntax import target_dsl_supports_effect_ceilings
                target = str(getattr(self.module, "TARGET", "2.39"))
                effects = definition.effects
                if target_dsl_supports_effect_ceilings(target):
                    if effects is not MISSING:
                        self.emit_effects(effects)
                else:
                    if effects is MISSING:
                        raise PythonFrontendError(
                            "python_proc_effects_required",
                            "Targets 2.35–2.38 require an explicit proc effects contract",
                            site=definition.site,
                        )
                    self.emit_effects(effects)
                    w.write(" :lowering inline")
            w.write("\n    ")
            self.region(trace, result, expected=returns)
            w.write(")\n")

    def emit_effects(self, effects):
        from .declarations import Effect
        self.writer.write(" :effects (")
        for index, effect in enumerate(effects):
            if index: self.writer.write(" ")
            if not isinstance(effect, Effect):
                raise PythonFrontendError(
                    "python_proc_effect_invalid",
                    "proc effects must use the declared effect descriptors",
                )
            subject = effect.subject
            if effect.kind == "host-input":
                self.writer.write("(host-input)")
                continue
            elif effect.kind == "uses-command":
                name = subject.name
            elif effect.kind == "uses-provider":
                name = subject.name
            elif effect.kind == "calls-workflow":
                name = self.definition_names[id(subject)]
            else:
                raise PythonFrontendError("python_proc_effect_invalid", "Unknown proc effect descriptor")
            self.writer.write(f"({effect.kind} {name})")
        self.writer.write(")")

    def region(self, trace, result, *, expected=None):
        w = self.writer
        expected_bindings = self.binding_expectations(trace, result, expected)
        if trace.bindings:
            w.write("(let* (")
            for index, (name, expression) in enumerate(trace.bindings):
                if index: w.write("\n           ")
                w.write(f"({name} ")
                self.expression(expression, expected=expected_bindings.get(name))
                w.write(")")
            w.write(")\n      ")
        self.expression(result, expected=expected)
        if trace.bindings: w.write(")")

    def binding_expectations(self, trace, result, expected):
        expectations = {}

        def collect(value, annotation, loop_state_type=None):
            if isinstance(value, Expr):
                if value._kind == "ref":
                    if annotation is not None:
                        expectations.setdefault(value._args[0], []).append(annotation)
                elif value._kind == "continue":
                    _owner, state = value._args
                    collect(state, loop_state_type, loop_state_type)
                elif value._kind == "done":
                    _owner, result = value._args
                    collect(result, annotation, loop_state_type)
                elif value._kind == "when":
                    condition, then_region, else_region = value._args
                    collect(condition, bool, loop_state_type)
                    collect_region(*then_region, expected=annotation)
                    collect_region(*else_region, expected=annotation)
                elif value._kind == "match":
                    _subject, arms = value._args
                    for _variant, _binder, child, child_result in arms:
                        collect_region(child, child_result, expected=annotation)
                elif value._kind in {"all_of", "any_of"}:
                    for child, child_result in value._args:
                        collect_region(child, child_result, expected=bool)
                elif value._kind == "construct":
                    owner, fields = value._args
                    for name, field_type in fields_of(owner).items():
                        if name in fields: collect(fields[name], field_type)
                elif value._kind == "call":
                    definition, arguments = value._args
                    _signature, annotations, _returns = definition.signature()
                    for name, argument in arguments.items():
                        collect(argument, annotations[name], loop_state_type)
                elif value._kind == "loop":
                    maximum, state, body_region, exhausted_region, _owner = value._args
                    collect(maximum, int, loop_state_type)
                    state_type = getattr(state, "_annotation", None)
                    if state_type is None and type(state) in {bool, int, float, str}:
                        state_type = type(state)
                    collect(state, state_type, loop_state_type)
                    result_type = annotation if annotation is not None else value._annotation
                    collect_region(*body_region[:2], expected=result_type)
                    collect_region(*exhausted_region[:2], expected=result_type)
                elif value._kind == "command":
                    command, argv, inputs, _inputs_present = value._args
                    for argument in argv: collect(argument, None, loop_state_type)
                    for argument in inputs.values(): collect(argument, None, loop_state_type)
                elif value._kind in {"provider", "ask"}:
                    from .declarations import PromptApplication
                    if value._kind == "provider":
                        _provider, application, _options = value._args
                    else:
                        application, _returns, timeout, shown = value._args
                        collect(timeout, int, loop_state_type)
                        for argument in shown: collect(argument, None, loop_state_type)
                    if isinstance(application, PromptApplication) and not isinstance(application.values, tuple):
                        fills = application.prompt.signature()
                        for name, argument in application.values.items():
                            collect(argument, fills[name].annotation, loop_state_type)
                    elif value._kind == "ask":
                        collect(application, str, loop_state_type)
                elif value._kind == "op":
                    operator = value._args[0]
                    operand_type = bool if operator == "not" else str if operator == "string/concat" else None
                    for argument in value._args[1:]: collect(argument, operand_type, loop_state_type)
                elif value._kind == "path":
                    collect(value._args[1], str, loop_state_type)
            elif isinstance(value, list):
                arguments = get_args(annotation)
                child_type = arguments[0] if get_origin(annotation) is list and arguments else None
                for item in value: collect(item, child_type, loop_state_type)

        def collect_region(region_trace, region_result, *, expected):
            collect(region_result, expected, region_trace.loop_state_type)
            for name, expression in reversed(region_trace.bindings):
                types = expectations.get(name, ())
                unique = []
                for annotation in types:
                    if not any(annotation == item for item in unique): unique.append(annotation)
                # Discarded bindings still supply declared argument and child-region contexts.
                collect(expression, unique[0] if len(unique) == 1 else None,
                        region_trace.loop_state_type)

        collect_region(trace, result, expected=expected)
        bindings = dict(trace.bindings)
        resolved = {}
        for name, types in expectations.items():
            unique = []
            for annotation in types:
                if not any(annotation == item for item in unique): unique.append(annotation)
            if len(unique) == 1 and name in bindings:
                resolved[name] = unique[0]
        return resolved

    def literal(self, value):
        if value is None:
            raise PythonFrontendError("python_none_literal_unsupported", "Optional types accept transported None inputs; the compiler has no None source literal", site=self.fallback)
        elif value is True: text = "true"
        elif value is False: text = "false"
        elif isinstance(value, (str, int, float)):
            try: text = json.dumps(value, ensure_ascii=False, allow_nan=False)
            except (ValueError, TypeError) as exc:
                raise PythonFrontendError("python_value_unsupported", str(exc), site=self.fallback) from exc
        else:
            raise PythonFrontendError("python_value_unsupported", f"Unsupported literal {type(value).__name__}", site=self.fallback)
        self.writer.write(text)

    def expression(self, value, *, expected=None):
        w = self.writer
        site = value._site if isinstance(value, Expr) else self.fallback
        kind = "call" if isinstance(value, Expr) and value._kind in {"call", "provider", "command", "ask"} else "expression"
        with w.mark(site, kind):
            if isinstance(value, Expr):
                self._expression(value, expected=expected)
            elif isinstance(value, Enum):
                w.write(self.enum_name(type(value)) + "." + value.value)
            elif isinstance(value, list):
                w.write("(list")
                args = get_args(expected)
                child_type = args[0] if get_origin(expected) is list else None
                for item in value:
                    w.write(" ")
                    self.expression(item, expected=child_type)
                w.write(")")
            else:
                self.literal(value)

    def _expression(self, value, *, expected):
        w = self.writer
        if value._kind == "ref": w.write(value._args[0])
        elif value._kind == "case_ref": w.write(value._args[0])
        elif value._kind == "field":
            self.expression(value._args[0])
            w.write("." + value._args[1])
        elif value._kind == "op":
            w.write("(" + value._args[0])
            for argument in value._args[1:]:
                w.write(" ")
                self.expression(argument)
            w.write(")")
        elif value._kind == "construct":
            owner, fields = value._args
            annotations = fields_of(owner)
            if set(fields) != set(annotations):
                raise PythonFrontendError("python_constructor_fields", "Constructor keyword fields must exactly match their declaration", site=value._site)
            if owner._orc_kind == "variant":
                union = self.union_for(owner, expected, value._site)
                w.write(f"(variant {self.type_ref(union)} {owner.__name__}")
            else:
                w.write(f"(record {self.type_ref(owner)}")
            for name, field_type in annotations.items():
                w.write(f" :{name} ")
                self.expression(fields[name], expected=field_type)
            w.write(")")
        elif value._kind == "import_construct":
            member, arguments, fields = value._args
            owner = self.graph.resolve_member(member, self)
            if not isinstance(owner, CompilerType):
                raise PythonFrontendError("python_effect_outside_trace", "Imported calls require a registered definition being generated", site=value._site)
            if owner._orc_kind == "record" and not arguments:
                self._expression(Expr("construct", (owner, fields), owner, value._site), expected=expected)
            elif owner._orc_kind == "path" and len(arguments) == 1 and not fields:
                self._expression(Expr("path", (owner, arguments[0]), owner, value._site), expected=expected)
            else:
                raise PythonFrontendError("python_constructor_fields", "Imported constructors require their declared fields", site=value._site)
        elif value._kind == "path":
            owner, child = value._args
            w.write(f"(path/join-under {self.type_ref(owner)} ")
            self.expression(child)
            w.write(")")
        elif value._kind == "enum":
            owner, token = value._args
            w.write(self.enum_name(owner) + "." + token)
        elif value._kind == "import_enum":
            member, token = value._args
            owner = self.graph.resolve_member(member, self)
            if not isinstance(owner, CompilerType) or owner._orc_kind != "enum":
                raise PythonFrontendError("python_import_kind_unsupported", "Only imported enum types have constant members", site=value._site)
            w.write(self.enum_name(owner) + "." + token)
        elif value._kind == "call":
            definition, arguments = value._args
            _signature, annotations, _result = definition.signature()
            if definition.kind == "workflow":
                w.write(f"(call {self.definition_names[id(definition)]}")
                for name, argument in arguments.items():
                    w.write(f" :{name} ")
                    self.expression(argument, expected=annotations[name])
            else:
                w.write(f"({self.definition_names[id(definition)]}")
                for name, annotation in annotations.items():
                    w.write(" ")
                    self.expression(arguments[name], expected=annotation)
            w.write(")")
        elif value._kind == "command":
            command, argv, inputs, inputs_present = value._args
            w.write(f"(command-result {command.name} :argv (")
            for index, argument in enumerate(argv):
                if index: w.write(" ")
                self.expression(argument)
            w.write(")")
            if inputs_present:
                w.write(" :inputs (")
                for index, (name, argument) in enumerate(inputs.items()):
                    if index: w.write(" ")
                    w.write(f"({name} ")
                    self.expression(argument)
                    w.write(")")
                w.write(")")
            w.write(" :returns " + self.type_ref(command.returns) + ")")
        elif value._kind == "provider": self.emit_provider(value)
        elif value._kind == "ask":
            from .declarations import PromptApplication
            question, returns, timeout, shown = value._args
            w.write("(request-input ")
            if isinstance(question, PromptApplication):
                self.emit_prompt_application(question)
            else:
                self.expression(question, expected=str)
            w.write(" :returns " + self.type_ref(returns))
            if timeout is not None:
                w.write(" :timeout-sec ")
                self.expression(timeout, expected=int)
            if shown:
                w.write(" :show (")
                for index, argument in enumerate(shown):
                    if index: w.write(" ")
                    self.expression(argument)
                w.write(")")
            w.write(")")
        elif value._kind == "when":
            condition, then_region, else_region = value._args
            w.write("(if ")
            self.expression(condition, expected=bool)
            w.write(" ")
            self.region(*then_region, expected=expected)
            w.write(" ")
            self.region(*else_region, expected=expected)
            w.write(")")
        elif value._kind == "match":
            subject, arms = value._args
            w.write("(match ")
            self.expression(subject)
            for variant, binder, trace, result in arms:
                w.write(f" (({variant.__name__} {binder}) ")
                self.region(trace, result, expected=expected)
                w.write(")")
            w.write(")")
        elif value._kind == "loop":
            maximum, state, body_region, exhausted_region, owner = value._args
            body_trace, body_result, body_binder = body_region
            exhausted_trace, exhausted_result, exhausted_binder = exhausted_region
            w.write("(loop/recur :max ")
            self.expression(maximum, expected=int)
            w.write(" :state ")
            self.expression(state, expected=body_trace.loop_state_type)
            w.write(" :on-exhausted (let* ((" + exhausted_binder + " " + body_binder + ")) ")
            self.region(exhausted_trace, exhausted_result, expected=expected)
            w.write(") (fn (" + body_binder + ") ")
            self.loop_binders[owner] = (body_binder, body_trace.loop_state_type)
            try:
                self.region(body_trace, body_result, expected=expected)
            finally:
                self.loop_binders.pop(owner, None)
            w.write("))")
        elif value._kind == "continue":
            owner, state = value._args
            self.require_current_loop_owner(owner, value)
            w.write("(continue ")
            self.expression(state, expected=self.loop_binders[owner][1])
            w.write(")")
        elif value._kind == "done":
            owner, result = value._args
            self.require_current_loop_owner(owner, value)
            w.write("(done ")
            self.expression(result, expected=expected)
            w.write(")")
        elif value._kind in {"all_of", "any_of"}:
            self.emit_boolean_thunks(value._kind, value._args)
        else:
            raise PythonFrontendError("python_expression_unsupported", f"Unsupported expression {value._kind}", site=value._site)

    def require_current_loop_owner(self, owner, value):
        if not self.loop_binders or next(reversed(self.loop_binders)) is not owner:
            site = value._site if isinstance(value, Expr) else self.fallback
            raise PythonFrontendError(
                "python_loop_control_owner_mismatch",
                "Loop transfers must target the innermost active loop body",
                site=site,
            )

    def emit_boolean_thunks(self, kind, regions):
        if not regions:
            self.literal(kind == "all_of")
            return

        def emit(index):
            if index == len(regions):
                self.literal(kind == "all_of")
                return
            self.writer.write("(if ")
            self.region(*regions[index], expected=bool)
            self.writer.write(" ")
            if kind == "all_of":
                emit(index + 1)
                self.writer.write(" ")
                self.literal(False)
            else:
                self.literal(True)
                self.writer.write(" ")
                emit(index + 1)
            self.writer.write(")")

        emit(0)

    def union_for(self, case, expected, site):
        if isinstance(case, CompilerCase): return case._union
        if _closed_union(expected) and case in get_args(expected): return expected
        candidates = self.graph.type_owners if self.graph is not None else self.union_names
        owners = [union for union in candidates if case in get_args(union)]
        if len(owners) != 1:
            raise PythonFrontendError("python_union_owner_ambiguous", "Variant construction requires one expected closed union", site=site)
        return owners[0]

    def enum_name(self, annotation):
        if isinstance(annotation, CompilerType):
            owner, name = annotation._owner, annotation._name
        elif self.graph is not None:
            python_owner, name = self.graph.type_owners[annotation]
            owner = self.graph.logical_names[python_owner]
        else:
            return self.type_ref(annotation)
        self.import_name(owner, name)
        return name if owner == self.module_name else owner + "::" + name

    def emit_provider(self, value):
        provider, application, options = value._args
        prompt = application.prompt
        w = self.writer
        w.write(f"(provider-result {provider.name}")
        for name, option in options.items():
            if option is not None:
                w.write(" :" + name.replace("_", "-") + " ")
                self.expression(option)
        w.write(" :prompt ")
        if prompt.extern_name is not None:
            if self.graph is not None:
                self.graph.capture_prompt_asset(prompt, self)
            w.write(prompt.extern_name + " :inputs (")
            for index, argument in enumerate(application.values):
                if index: w.write(" ")
                self.expression(argument)
            w.write(") :returns " + self.type_ref(prompt.returns))
        else:
            self.emit_prompt_application(application)
        w.write(")")

    def emit_prompt_application(self, application):
        prompt = application.prompt
        if isinstance(prompt, ImportedPrompt):
            name = self.import_name(prompt.module_name, prompt.name)
        elif self.graph is not None and prompt.owner != self.module.__name__:
            name = self.graph.prompt_ref(prompt, self)
        elif id(prompt) not in self.prompt_names:
            raise PythonFrontendError("python_prompt_owner", "Prompt must be a module-owned declaration", site=application.site)
        else:
            name, _ = self.prompt_names[id(prompt)]
        self.writer.write("(" + name)
        for key, argument in application.values.items():
            fill = prompt.signature()[key]
            self.writer.write(f" :{key} ")
            self.expression(argument, expected=fill.annotation)
        self.writer.write(")")


def generate_module(module: ModuleType, output_root: Path, *, module_name: str | None = None) -> GeneratedModule:
    """Internal in-process generation; durable public builds use the isolated worker."""
    graph = generate_graph(module, output_root, module_name=module_name)
    return next(item for item in graph.modules if item.source_path == graph.source_path)


class ModuleGraph:
    def __init__(self, module, output_root, *, module_name=None, source_roots=(),
                 module_names=None, python_sources=None, **compile_options):
        self.module = module
        self.root = Path(output_root).resolve()
        self.compile_options = {key: value for key, value in compile_options.items() if value is not None}
        self.modules = {}
        self.logical_names = {}
        self.type_owners = {}
        self.type_annotations = {}
        self.environments = {}
        self.linked = {}
        self.members = {}
        self.asset_bindings = []
        self.captured_sources_supplied = python_sources is not None
        self.python_sources = {Path(path).resolve(): raw for path, raw in (python_sources or {}).items()}
        self._discover_modules(module)
        overrides = dict(module_names or {})
        if module_name is not None: overrides[module.__name__] = module_name
        seen = {}
        for name, value in self.modules.items():
            logical = overrides.get(name, name)
            if logical == "__main__": logical = Path(value.__file__).stem
            logical = "py/" + logical.replace(".", "/")
            if logical in seen:
                raise PythonFrontendError("python_module_duplicate", f"Duplicate logical module `{logical}`")
            seen[logical] = value.__file__
            self.logical_names[name] = logical
            path = Path(value.__file__).resolve()
            if path not in self.python_sources:
                if self.captured_sources_supplied:
                    raise PythonFrontendError("python_source_not_captured", f"Declaration source `{path}` was not captured by the source loader")
                self.python_sources[path] = path.read_bytes()
        self._discover_type_owners()
        selected = getattr(module, "__all__", None)
        self.root_definitions = {id(value) for name, value in vars(module).items()
            if isinstance(value, Definition) and (name in selected if selected is not None else not name.startswith("_"))}
        roots = [Path(root).resolve() for root in source_roots]
        if len(set(roots)) != len(roots):
            raise PythonFrontendError("python_source_root_duplicate", "Source roots must be distinct")
        for value in self.modules.values():
            for declaration in vars(value).values():
                reference = declaration._module if isinstance(declaration, OrcMember) else declaration
                if isinstance(reference, OrcModule) and reference._source_root is not None and reference._source_root not in roots:
                    roots.append(reference._source_root)
        self.external_roots = tuple(roots)
        if self.root in self.external_roots:
            raise PythonFrontendError("python_source_root_duplicate", "The generated root cannot also be an input root")
        self.generators = {name: ModuleGenerator(value, self.root,
                            module_name=self.logical_names[name][3:].replace("/", "."), graph=self)
                           for name, value in self.modules.items()}
        from orchestrator.workflow_lisp.reader import SourceReadTrace
        self.read_trace = SourceReadTrace()

    def _discover_modules(self, module):
        if module.__name__ in self.modules: return
        if not getattr(module, "__file__", None):
            raise PythonFrontendError("python_source_required", "Workflow declarations need a source-backed module")
        self.modules[module.__name__] = module
        base = Path(self.module.__file__).resolve().parent
        for value in vars(module).values():
            owner = None
            if _closed_union(value):
                for case in get_args(value):
                    candidate = sys.modules.get(case.__module__)
                    if candidate is None:
                        raise PythonFrontendError("python_source_required", "Union cases need a loaded defining module")
                    self._discover_modules(candidate)
            if isinstance(value, Definition): owner = value.__module__
            elif isinstance(value, Prompt): owner = value.owner
            elif isinstance(value, type) and ("_orc_kind" in value.__dict__ or
                      (issubclass(value, Enum) and value is not Enum)):
                owner = value.__module__
            elif isinstance(value, ModuleType) and getattr(value, "__file__", None):
                path = Path(value.__file__).resolve()
                if path in self.python_sources or (not self.python_sources and base in path.parents):
                    if any(isinstance(item, (Definition, Prompt)) or
                           (isinstance(item, type) and ("_orc_kind" in item.__dict__ or
                            (issubclass(item, Enum) and item is not Enum)))
                           for item in vars(value).values()):
                        owner = value.__name__
            if owner and owner not in self.modules:
                candidate = sys.modules.get(owner)
                if candidate is None:
                    raise PythonFrontendError("python_source_required", f"Declaration owner `{owner}` is not loaded")
                self._discover_modules(candidate)

    def _discover_type_owners(self):
        unions = {}
        for owner, module in self.modules.items():
            for name, value in vars(module).items():
                if isinstance(value, type) and value.__module__ == owner and (
                        "_orc_kind" in value.__dict__ or (issubclass(value, Enum) and value is not Enum)):
                    self.type_owners[value] = owner, value.__name__
                elif _closed_union(value):
                    unions.setdefault(value, []).append((owner, name))
        for union, aliases in unions.items():
            local = [(owner, name) for owner, name in aliases
                     if all(case.__module__ == owner for case in get_args(union))]
            candidates = local or aliases
            if len(candidates) != 1:
                raise PythonFrontendError("python_union_owner_ambiguous", "A closed union requires one defining owner and alias")
            self.type_owners[union] = candidates[0]

    def definition_ref(self, value, generator):
        if isinstance(value, ImportedCallable):
            return generator.import_name(value.module_name, value.name)
        owner = self.generators.get(value.__module__)
        if owner is None:
            raise PythonFrontendError("python_module_import_unsupported", "Definition owner is outside the source graph", site=value.site)
        if not self.is_public(value.__module__, value):
            raise PythonFrontendError("python_import_member_missing", f"Definition `{value.__name__}` is private in `{owner.module_name}`")
        owner.require_definition(value)
        return generator.import_name(owner.module_name, value.__name__)

    def is_root_definition(self, value):
        return id(value) in self.root_definitions

    def prompt_ref(self, prompt, generator):
        owner = self.generators[prompt.owner]
        if not self.is_public(prompt.owner, prompt):
            raise PythonFrontendError("python_import_member_missing", "Imported prompt is private", site=prompt.site)
        name, _prompt = owner.prompt_names[id(prompt)]
        return generator.import_name(owner.module_name, name)

    def capture_prompt_asset(self, prompt, generator):
        from orchestrator.workflow.assets import WorkflowAssetResolver
        from orchestrator.workflow_lisp.workflows import normalize_prompt_extern_bindings
        bindings = normalize_prompt_extern_bindings(self.compile_options.get("prompt_externs"))
        binding = bindings.get(prompt.extern_name)
        if binding is None or binding.source_kind != "asset_file": return
        owner = Path(self.modules[prompt.owner].__file__).resolve()
        source = WorkflowAssetResolver(owner).resolve(binding.path)
        raw = source.read_bytes()
        existing = generator.prompt_assets.get(source)
        if existing is not None and existing != raw:
            raise PythonFrontendError("python_source_changed", "Prompt source changed during generation", site=prompt.site)
        generator.prompt_assets[source] = raw
        target = WorkflowAssetResolver(generator.path).resolve(binding.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != raw:
            raise PythonFrontendError("python_prompt_asset_conflict", "Different prompt assets share a generated locator", site=prompt.site)
        target.write_bytes(raw)
        row = {"owner": str(owner), "generated_owner": str(generator.path),
               "relative_path": binding.path, "source_path": str(source)}
        if row not in self.asset_bindings: self.asset_bindings.append(row)

    def is_public(self, owner, value):
        module = self.modules[owner]
        selected = getattr(module, "__all__", None)
        return any(candidate is value and (name in selected if selected is not None else not name.startswith("_"))
                   for name, candidate in vars(module).items())

    def resolve_annotation(self, annotation, generator, *, site=None):
        if isinstance(annotation, OrcMember):
            resolved = self.resolve_member(annotation, generator, site=site)
            if not isinstance(resolved, CompilerType):
                raise PythonFrontendError("python_annotation_unsupported", "An imported annotation must name an exported type", site=annotation._site)
            return resolved
        return annotation

    def resolve_member(self, member, generator, *, site=None):
        key = (generator.module_name, member._module._name, member._name, member._arguments)
        if key in self.members: return self.members[key]
        linked = self.linked[generator.module_name]
        surface = linked.graph.export_surfaces_by_name.get(member._module._name)
        binding = surface.binding_for(member._name) if surface is not None else None
        if binding is None:
            raise PythonFrontendError("python_import_member_missing", f"No public export `{member._name}` in `{member._module._name}`", site=site or member._site)
        if member._arguments and binding.kind != "type":
            raise PythonFrontendError("python_import_generic_callable_unsupported",
                "Type application requires an exported type; callable specialization needs a concrete compiler signature", site=site or member._site)
        result = linked.compiled_results_by_name[binding.module_name]
        if binding.kind == "type":
            environment = self.environments[generator.module_name]
            reference = environment.resolve_type(generator.type_ref(member), span=python_span(site or member._site),
                                                 form_path=("workflow-lisp",))
            resolved = self.annotation_from_ref(reference, site=site or member._site)
        elif binding.kind in {"procedure", "workflow"}:
            catalog = result.procedure_catalog if binding.kind == "procedure" else result.workflow_catalog
            signature = catalog.signatures_by_name[binding.member_name]
            resolved = ImportedCallable(self, binding.module_name, binding.member_name,
                       "proc" if binding.kind == "procedure" else "workflow", signature, member._site)
        elif binding.kind == "prompt":
            prompt = result.prompt_catalog.resolve(binding.member_name)
            resolved = ImportedPrompt(self, binding.module_name, binding.member_name, prompt, member._site)
        else:
            raise PythonFrontendError("python_import_kind_unsupported", f"Imported {binding.kind} is not supported", site=member._site)
        self.members[key] = resolved
        return resolved

    def annotation_from_ref(self, reference, *, module_name=None, site=None):
        from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef, ListTypeRef, OptionalTypeRef
        primitive = {"String": str, "Int": int, "Float": float, "Bool": bool}
        if isinstance(reference, PrimitiveTypeRef) and not reference.allowed_values and reference.name in primitive:
            return primitive[reference.name]
        if isinstance(reference, PrimitiveTypeRef) and reference.allowed_values:
            reserved = (set(OrcMember.__dataclass_fields__) | set(CompilerType.__dataclass_fields__) |
                        set(OrcMember.__dict__) | set(CompilerType.__dict__) | set(object.__dict__))
            if reserved.intersection(reference.allowed_values):
                raise PythonFrontendError("python_import_member_reserved", "Imported enum tokens cannot use private handle metadata names", site=site)
        if isinstance(reference, ListTypeRef): return list[self.annotation_from_ref(reference.item_type_ref, module_name=module_name, site=site)]
        if isinstance(reference, OptionalTypeRef): return self.annotation_from_ref(reference.item_type_ref, module_name=module_name, site=site) | None
        if hasattr(reference, "field_types"):
            validate_field_names(reference.field_types, site=site)
        if hasattr(reference, "variant_field_types"):
            for fields in reference.variant_field_types.values(): validate_field_names(fields, site=site)
        if id(reference) in self.type_annotations: return self.type_annotations[id(reference)]
        owner = None
        name = getattr(getattr(reference, "definition", None), "name", reference.name).partition("[")[0]
        for environment in self.environments.values():
            owner = environment.declaring_module(reference)
            if owner is None and getattr(reference, "type_args", ()):
                template = environment.retained_type_ref(reference.name.partition("[")[0])
                if template is not None: owner = environment.declaring_module(template)
            if owner is not None:
                name = environment.declaring_name(reference) or name
                break
        if owner is None:
            if isinstance(reference, PrimitiveTypeRef) and reference.allowed_values and module_name is not None:
                environment = self.environments[module_name]
                retained = environment.retained_type_ref(reference.name)
                if retained is not None:
                    owner = environment.declaring_module(retained)
                    name = environment.declaring_name(retained) or name
        if owner is None:
            raise PythonFrontendError("python_import_type_owner", f"Compiler did not retain the owner of `{reference.name}`")
        arguments = tuple(self.annotation_from_ref(arg) for arg in getattr(reference, "type_args", ()))
        generator = _GENERATOR.get()
        if generator is not None and generator.graph is self:
            generator.import_name(owner, name)
        local = next((annotation for annotation, (python_owner, short) in self.type_owners.items()
                      if self.logical_names[python_owner] == owner and short == name), None)
        annotation = local if local is not None and not arguments else CompilerType(self, reference, owner, name, arguments)
        self.type_annotations[id(reference)] = annotation
        return annotation

    def capture_imported_assets(self):
        from orchestrator.workflow.assets import WorkflowAssetResolver
        from orchestrator.workflow_lisp.expression_traversal import walk_expr
        from orchestrator.workflow_lisp.expressions import NameExpr, ProviderResultExpr
        from orchestrator.workflow_lisp.workflows import PromptExtern
        seen = set()
        self.imported_assets = {}
        for linked in self.linked.values():
            for name, result in linked.compiled_results_by_name.items():
                if name in self.logical_names.values() or name in seen: continue
                seen.add(name)
                owner = linked.graph.modules_by_name[name].path
                for definition in (*result.typed_workflows, *result.typed_procedures):
                    for expression in walk_expr(definition.typed_body.expr):
                        if not isinstance(expression, ProviderResultExpr) or not isinstance(expression.prompt, NameExpr): continue
                        binding = result.extern_environment.bindings_by_name.get(expression.prompt.name)
                        if not isinstance(binding, PromptExtern) or binding.source_kind != "asset_file": continue
                        source = WorkflowAssetResolver(owner).resolve(binding.path)
                        raw = source.read_bytes()
                        if source in self.imported_assets and self.imported_assets[source] != raw:
                            raise PythonFrontendError("python_source_changed", "Imported prompt source changed during generation")
                        self.imported_assets[source] = raw
                        row = {"owner": str(owner), "generated_owner": str(owner),
                               "relative_path": binding.path, "source_path": str(source)}
                        if row not in self.asset_bindings: self.asset_bindings.append(row)

    def validate_imported_names(self):
        from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
        for generator in self.generators.values():
            linked = self.linked[generator.module_name]
            for name, surface in linked.graph.export_surfaces_by_name.items():
                if name in self.logical_names.values(): continue
                for reserved in (set(OrcModule.__dataclass_fields__) | set(OrcModule.__dict__) | set(object.__dict__)):
                    if surface.binding_for(reserved) is not None:
                        raise PythonFrontendError("python_import_member_reserved", "Imported exports cannot use private module handle metadata names", site=generator.fallback)
                environment = self.environments[name]
                for type_name in surface.types_by_name:
                    reference = environment.retained_type_ref(type_name)
                    if isinstance(reference, PrimitiveTypeRef) and reference.allowed_values:
                        self.annotation_from_ref(reference, module_name=name, site=generator.fallback)

    def _skeletons(self, root):
        self.skeleton_source_map = PythonSourceMap()
        # Skeleton paths are read once and never overwritten with final source.
        for generator in self.generators.values():
            if str(getattr(generator.module, "TARGET", "2.39")) == "2.40":
                generator.import_name("std/host", "HostReply")
            declarations = {id(value): value for value in vars(generator.module).values()
                            if isinstance(value, Definition) and value.__module__ == generator.module.__name__}
            for definition in declarations.values():
                try:
                    _signature, parameters, result = definition.signature()
                    for annotation in (*parameters.values(), result): generator.type_ref(annotation, site=definition.site)
                except PythonFrontendError:
                    if id(definition) in generator.definition_names: raise
                    # Unreachable signatures cannot reject a build; tracing checks them when called.
            for value in vars(generator.module).values():
                reference = value._module if isinstance(value, OrcMember) else value
                if isinstance(reference, OrcModule): generator.import_name(reference._name, "_metadata")
            writer = _Writer(root / (generator.module_name + ".orc"), PythonSourceMap())
            original = generator.writer
            generator.writer = writer
            try:
                writer.write('(workflow-lisp (:language "0.1") (:target-dsl ')
                generator.literal(str(getattr(generator.module, "TARGET", "2.39")))
                writer.write(f") (defmodule {generator.module_name})\n")
                generator.emit_imports()
                public_types = {name for annotation, name in (*generator.type_names.items(), *generator.union_names.items())
                                if getattr(annotation, "_orc_kind", None) != "variant"}
                exports = [name for name in generator._exports() if name in public_types]
                if exports: writer.write("(export " + " ".join(exports) + ")\n")
                for annotation in generator.type_order: generator.emit_type(annotation)
                writer.write(")\n")
                writer.source_map.entries.append(SourceMapEntry(generator.fallback,
                    PythonSite(writer.path, 1, 1, writer.line, writer.column), "module"))
                self.skeleton_source_map.entries.extend(writer.source_map.entries)
            finally:
                generator.writer = original
            path = Path(writer.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(writer.text(), encoding="utf-8")

    def emit(self):
        from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, linked_module_type_environment
        with TemporaryDirectory(prefix="workflow-python-types-") as temporary:
            skeleton_root = Path(temporary)
            self._skeletons(skeleton_root)
            for generator in self.generators.values():
                from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
                try:
                    linked = compile_stage3_entrypoint(skeleton_root / (generator.module_name + ".orc"),
                        source_roots=(skeleton_root, *self.external_roots), source_read_trace=self.read_trace,
                        **self.compile_options)
                except LispFrontendCompileError as error:
                    raise remap_compiler_error(error, self.skeleton_source_map) from error
                self.linked[generator.module_name] = linked
                self.environments[generator.module_name] = linked_module_type_environment(linked, generator.module_name)
                for name in linked.compiled_results_by_name:
                    if name not in self.environments:
                        self.environments[name] = linked_module_type_environment(linked, name)
            self.validate_imported_names()
            self.capture_imported_assets()
            while any(id(definition) not in generator.traces for generator in self.generators.values()
                      for definition in generator.definitions):
                for generator in self.generators.values():
                    token = _GENERATOR.set(generator)
                    try: generator._trace_all()
                    finally: _GENERATOR.reset(token)
            generated = []
            for generator in self.generators.values():
                token = _GENERATOR.set(generator)
                try: generated.append(generator.emit())
                finally: _GENERATOR.reset(token)
            source_reads = {path: raw for path, raw in self.read_trace.raw_bytes_by_path.items()
                            if skeleton_root not in path.parents}
        source_map = PythonSourceMap()
        prompt_assets = dict(self.imported_assets)
        for item in generated:
            source_map.entries.extend(item.source_map.entries)
            source_map.source_hashes.update(item.source_map.source_hashes)
            for path, raw in item.prompt_assets.items():
                if prompt_assets.setdefault(path, raw) != raw:
                    raise PythonFrontendError("python_source_changed", "Prompt source changed between module reads")
        for path, raw in (*self.python_sources.items(), *prompt_assets.items()):
            if path in self.python_sources and self.python_sources[path] != raw:
                raise PythonFrontendError("python_source_changed", "One authored path produced different Python and prompt bytes")
            source_map.source_hashes[str(path)] = "sha256:" + sha256(raw).hexdigest()
        selected = self.generators[self.module.__name__]
        exports = getattr(self.module, "__all__", None)
        aliases = {name: (self.logical_names[value.__module__], value.__name__)
                   for name, value in vars(self.module).items()
                   if isinstance(value, Definition) and value.kind == "workflow" and
                   (name in exports if exports is not None else not name.startswith("_"))}
        return GeneratedGraph(selected.path, self.root, (self.root, *self.external_roots), tuple(generated),
                              source_map, prompt_assets,
                              {item.source_path: Path(self.modules[name].__file__).resolve()
                               for name, item in zip(self.generators, generated)},
                              self.python_sources, source_reads, aliases, tuple(self.asset_bindings))


def generate_graph(module: ModuleType, output_root: Path, *, module_name=None, source_roots=(),
                   module_names=None, python_sources=None, provider_externs=None,
                   prompt_externs=None, command_boundaries=None, workspace_root=None,
                   imported_programs=None, imported_workflow_bundles=None):
    """Generate an ownership-preserving graph and retain exact dependency evidence."""
    return ModuleGraph(module, output_root, module_name=module_name, source_roots=source_roots,
                       module_names=module_names, python_sources=python_sources,
                       provider_externs=provider_externs, prompt_externs=prompt_externs,
                       command_boundaries=command_boundaries, workspace_root=workspace_root,
                       imported_programs=imported_programs, imported_workflow_bundles=imported_workflow_bundles).emit()
