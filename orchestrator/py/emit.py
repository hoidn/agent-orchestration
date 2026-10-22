"""Generate inspectable Workflow Lisp; the existing compiler checks the result."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import re
from types import ModuleType, UnionType
from typing import Union, get_args, get_origin

from .declarations import Definition, Fill, MISSING, Prompt, fields_of
from .diagnostics import (PythonFrontendError, PythonSite, PythonSourceMap,
                          SourceMapEntry, definition_site)
from .trace import Expr, Trace


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
    def __init__(self, module, output_root, *, module_name=None):
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
        self.fallback = PythonSite(str(module.__file__), 1)
        self._discover()

    def _discover(self):
        namespace = vars(self.module)
        selected = getattr(self.module, "__all__", None)
        for name, value in namespace.items():
            if _closed_union(value):
                if value in self.union_names and self.union_names[value] != name:
                    raise PythonFrontendError("python_union_owner_ambiguous", "A closed union requires one defining alias", site=self.fallback)
                self.union_names[value] = name
        for name, value in namespace.items():
            if isinstance(value, type) and value.__module__ == self.module.__name__:
                if "_orc_kind" in value.__dict__ or issubclass(value, Enum):
                    self.type_names[value] = value.__name__
            elif isinstance(value, Definition) and value.__module__ == self.module.__name__:
                is_root = name in selected if selected is not None else not name.startswith("_")
                if is_root:
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
        if id(value) not in self.definition_names:
            if value.__module__ != self.module.__name__:
                raise PythonFrontendError("python_module_import_unsupported", "Cross-module generation requires the import bridge", site=value.site)
            self.definition_names[id(value)] = value.__name__
            self.definitions.append(value)

    def type_ref(self, annotation, *, site=None, signature=False):
        site = site or self.fallback
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
            signature, annotations, returns = definition.signature()
            for annotation in (*annotations.values(), returns):
                self.type_ref(annotation, site=definition.site, signature=True)
            trace = Trace(self, definition)
            arguments = {name: trace.reference(name, annotation, site=definition.site)
                         for name, annotation in annotations.items()}
            result = trace.run(definition.function, arguments)
            self.traces[id(definition)] = (trace, result, signature, annotations, returns)
            index += 1
        for _name, prompt in self.prompt_names.values():
            self.type_ref(prompt.returns, site=prompt.site)
            for fill in prompt.signature().values():
                if fill.annotation is not None: self.type_ref(fill.annotation, site=prompt.site)

    def emit(self):
        self._trace_all()
        w = self.writer
        w.write('(workflow-lisp\n  (:language "0.1")\n  (:target-dsl ')
        self.literal(str(getattr(self.module, "TARGET", "2.39")))
        w.write(f")\n  (defmodule {self.module_name})\n")
        exports = self._exports()
        if exports: w.write("  (export " + " ".join(exports) + ")\n")
        for annotation in self.type_order: self.emit_type(annotation)
        for name, prompt in self.prompt_names.values(): self.emit_prompt(name, prompt)
        for definition in self.definitions: self.emit_definition(definition)
        w.write(")\n")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(w.text(), encoding="utf-8")
        source_path = Path(self.module.__file__)
        self.source_map.source_hashes[str(source_path)] = "sha256:" + sha256(source_path.read_bytes()).hexdigest()
        for path, raw in self.prompt_assets.items():
            self.source_map.source_hashes[str(path)] = "sha256:" + sha256(raw).hexdigest()
        return GeneratedModule(self.path, self.root, self.source_map, self.prompt_assets, self.module_name)

    def _exports(self):
        selected = getattr(self.module, "__all__", None)
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
            w.write(f"  (defworkflow {definition.__name__} (")
            for index, (name, annotation) in enumerate(annotations.items()):
                if index: w.write(" ")
                w.write(f"({name} {self.type_ref(annotation)}")
                default = signature.parameters[name].default
                if default is not signature.empty:
                    w.write(" :default ")
                    self.expression(default, expected=annotation)
                w.write(")")
            w.write(") -> " + self.type_ref(returns) + "\n    ")
            self.region(trace, result, expected=returns)
            w.write(")\n")

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

        def collect(value, annotation):
            if isinstance(value, Expr):
                if value._kind == "ref":
                    if annotation is not None:
                        expectations.setdefault(value._args[0], []).append(annotation)
                elif value._kind == "when":
                    condition, then_region, else_region = value._args
                    collect(condition, bool)
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
                        collect(argument, annotations[name])
                elif value._kind == "provider":
                    from .declarations import PromptApplication
                    _provider, application, _options = value._args
                    if isinstance(application, PromptApplication) and not isinstance(application.values, tuple):
                        fills = application.prompt.signature()
                        for name, argument in application.values.items():
                            collect(argument, fills[name].annotation)
                elif value._kind == "op":
                    operator = value._args[0]
                    operand_type = bool if operator == "not" else str if operator == "string/concat" else None
                    for argument in value._args[1:]: collect(argument, operand_type)
                elif value._kind == "path":
                    collect(value._args[1], str)
            elif isinstance(value, list):
                arguments = get_args(annotation)
                child_type = arguments[0] if get_origin(annotation) is list and arguments else None
                for item in value: collect(item, child_type)

        def collect_region(region_trace, region_result, *, expected):
            collect(region_result, expected)
            for name, expression in reversed(region_trace.bindings):
                types = expectations.get(name, ())
                unique = []
                for annotation in types:
                    if not any(annotation == item for item in unique): unique.append(annotation)
                # Discarded bindings still supply declared argument and child-region contexts.
                collect(expression, unique[0] if len(unique) == 1 else None)

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
        kind = "call" if isinstance(value, Expr) and value._kind in {"call", "provider"} else "expression"
        with w.mark(site, kind):
            if isinstance(value, Expr):
                self._expression(value, expected=expected)
            elif isinstance(value, Enum):
                w.write(self.type_ref(type(value)) + "." + value.value)
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
        elif value._kind == "path":
            owner, child = value._args
            w.write(f"(path/join-under {self.type_ref(owner)} ")
            self.expression(child)
            w.write(")")
        elif value._kind == "call":
            definition, arguments = value._args
            _signature, annotations, _result = definition.signature()
            w.write(f"(call {self.definition_names[id(definition)]}")
            for name, argument in arguments.items():
                w.write(f" :{name} ")
                self.expression(argument, expected=annotations[name])
            w.write(")")
        elif value._kind == "provider": self.emit_provider(value)
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
        elif value._kind in {"all_of", "any_of"}:
            self.emit_boolean_thunks(value._kind, value._args)
        else:
            raise PythonFrontendError("python_expression_unsupported", f"Unsupported expression {value._kind}", site=value._site)

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
        if _closed_union(expected) and case in get_args(expected): return expected
        owners = [union for union in self.union_names if case in get_args(union)]
        if len(owners) != 1:
            raise PythonFrontendError("python_union_owner_ambiguous", "Variant construction requires one expected closed union", site=site)
        return owners[0]

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
            w.write(prompt.extern_name + " :inputs (")
            for index, argument in enumerate(application.values):
                if index: w.write(" ")
                self.expression(argument)
            w.write(") :returns " + self.type_ref(prompt.returns))
        else:
            if id(prompt) not in self.prompt_names:
                raise PythonFrontendError("python_prompt_owner", "Prompt must be a module-owned declaration", site=application.site)
            name, _ = self.prompt_names[id(prompt)]
            w.write("(" + name)
            for key, argument in application.values.items():
                fill = prompt.signature()[key]
                w.write(f" :{key} ")
                self.expression(argument, expected=fill.annotation)
            w.write(")")
        w.write(")")


def generate_module(module: ModuleType, output_root: Path, *, module_name: str | None = None) -> GeneratedModule:
    """Internal in-process generation; durable public builds use the isolated worker."""
    return ModuleGenerator(module, output_root, module_name=module_name).emit()
