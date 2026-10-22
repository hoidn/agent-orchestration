"""Lazy source imports; all resolved signatures and types belong to the compiler."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import inspect
from pathlib import Path
from typing import Union

from .diagnostics import PythonFrontendError, author_site


_GENERATOR = ContextVar("workflow_python_generator", default=None)


def current_generator():
    from .trace import _ACTIVE
    trace = _ACTIVE.get()
    generator = trace.generator if trace is not None else _GENERATOR.get()
    if generator is None or generator.graph is None:
        raise PythonFrontendError("python_import_outside_generation", "Imported declarations resolve during generation")
    return generator


@dataclass(eq=False)
class OrcModule:
    _name: str
    _source_root: Path | None
    _site: object

    def __getattr__(self, _name):
        if _name.startswith("__"):
            raise AttributeError(_name)
        return OrcMember(self, _name, author_site())


@dataclass(eq=False)
class OrcMember:
    _module: OrcModule
    _name: str
    _site: object
    _arguments: tuple = ()

    @property
    def __name__(self): return self._name

    def __getitem__(self, _arguments):
        return OrcMember(self._module, self._name, author_site(),
                         _arguments if isinstance(_arguments, tuple) else (_arguments,))

    def __or__(self, other): return Union[self, other]
    def __ror__(self, other): return Union[other, self]

    def _resolve(self):
        generator = current_generator()
        return generator.graph.resolve_member(self, generator)

    def __call__(self, *args, **kwargs):
        from .trace import _ACTIVE, declaration_expression
        if _ACTIVE.get() is None and _GENERATOR.get() is None:
            return declaration_expression("import_construct", (self, tuple(args), dict(kwargs)), self)
        return self._resolve()(*args, **kwargs)

    def __getattr__(self, _name):
        if _name.startswith("_"):
            raise AttributeError(_name)
        from .trace import _ACTIVE, declaration_expression
        if _ACTIVE.get() is None and _GENERATOR.get() is None:
            return declaration_expression("import_enum", (self, _name), self)
        resolved = self._resolve()
        if not isinstance(resolved, CompilerType):
            raise AttributeError(_name)
        return getattr(resolved, _name)


@dataclass(eq=False)
class CompilerType:
    """A source-nameable handle retaining the compiler's actual resolved _ref."""
    _graph: object
    _ref: object
    _owner: str
    _name: str
    _arguments: tuple = ()

    @property
    def __name__(self): return self._name

    @property
    def _orc_kind(self):
        from orchestrator.workflow_lisp.type_env import PathTypeRef, RecordTypeRef, UnionTypeRef
        if isinstance(self._ref, RecordTypeRef): return "record"
        if isinstance(self._ref, UnionTypeRef): return "union"
        if isinstance(self._ref, PathTypeRef): return "path"
        return "enum"

    def __or__(self, other): return Union[self, other]
    def __ror__(self, other): return Union[other, self]

    def _fields(self):
        return {_name: self._graph.annotation_from_ref(_ref, module_name=self._owner)
                for _name, _ref in self._ref.field_types.items()}

    def _cases(self):
        return tuple(CompilerCase(self, _name, fields)
                     for _name, fields in self._ref.variant_field_types.items())

    def __getattr__(self, _name):
        if _name.startswith("__"):
            raise AttributeError(_name)
        from .trace import declaration_expression
        if self._orc_kind == "enum" and _name in self._ref.allowed_values:
            return declaration_expression("enum", (self, _name), self)
        raise AttributeError(_name)

    def __call__(self, *args, **kwargs):
        from .trace import declaration_expression
        if self._orc_kind == "record" and not args:
            return declaration_expression("construct", (self, dict(kwargs)), self)
        if self._orc_kind == "path" and len(args) == 1 and not kwargs:
            return declaration_expression("path", (self, args[0]), self)
        raise PythonFrontendError("python_constructor_fields", "Imported record constructors require named fields; paths require one value")


@dataclass(eq=False)
class CompilerCase:
    _union: CompilerType
    _name: str
    _field_refs: dict
    _orc_kind = "variant"

    @property
    def __name__(self): return self._name

    def _fields(self):
        return {_name: self._union._graph.annotation_from_ref(_ref, module_name=self._union._owner)
                for _name, _ref in self._field_refs.items()}

@dataclass(eq=False)
class ImportedCallable:
    graph: object
    module_name: str
    name: str
    kind: str
    compiler_signature: object
    site: object

    @property
    def __name__(self): return self.name

    def signature(self):
        signature = self.compiler_signature
        if getattr(signature, "type_params", ()):
            raise PythonFrontendError("python_import_generic_callable_unsupported",
                                      "Imported callables require a concrete compiler-resolved signature", site=self.site)
        annotations = {name: self.graph.annotation_from_ref(ref, module_name=self.module_name) for name, ref in signature.params}
        parameters = [inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                      for name in annotations]
        return inspect.Signature(parameters), annotations, self.graph.annotation_from_ref(signature.return_type_ref, module_name=self.module_name)

    def __call__(self, *args, **kwargs):
        from .trace import active_trace
        trace = active_trace()
        signature, _annotations, result = self.signature()
        try:
            bound = signature.bind_partial(*args, **kwargs)
            defaults = getattr(self.compiler_signature, "param_defaults", {})
            missing = signature.parameters.keys() - bound.arguments.keys() - defaults.keys()
            if missing:
                raise TypeError("Missing required arguments: " + ", ".join(sorted(missing)))
        except TypeError as exc:
            raise PythonFrontendError("python_call_arguments", str(exc), site=author_site()) from exc
        trace.generator.require_definition(self)
        return trace.bind(trace.expression("call", (self, dict(bound.arguments)), result))


@dataclass(eq=False)
class ImportedPrompt:
    graph: object
    module_name: str
    name: str
    definition: object
    site: object
    extern_name = None

    @property
    def returns(self): return self.graph.annotation_from_ref(self.definition.return_type_ref, module_name=self.module_name)

    def signature(self):
        from .declarations import Fill
        return {slot.declaration.name: Fill(slot.declaration.kind.value,
                    None if slot.refinement_type_ref is None else self.graph.annotation_from_ref(slot.refinement_type_ref, module_name=self.module_name),
                    getattr(slot.declaration.output_role, "value", None) == "required_string_file")
                for slot in self.definition.slots}

    def __call__(self, *args, **kwargs):
        from .declarations import PromptApplication
        names = tuple(self.signature())
        if len(args) > len(names) or set(names[:len(args)]) & kwargs.keys():
            raise PythonFrontendError("python_prompt_arguments", "Duplicate or excess prompt fill arguments")
        values = dict(zip(names, args))
        values.update(kwargs)
        if set(values) != set(names):
            raise PythonFrontendError("python_prompt_arguments", "Prompt arguments must supply exactly the declared fills")
        current_generator().import_name(self.module_name, self.name)
        return PromptApplication(self, values, author_site())


def import_orc(name, *, source_root=None):
    """Register a module; resolve it only after the build supplies configuration."""
    site = author_site()
    if not isinstance(name, str) or any(part in {"", ".", ".."} for part in name.split("/")) or "\\" in name:
        raise PythonFrontendError("python_module_name", "Expected a logical .orc module name", site=site)
    root = None
    if source_root is not None:
        root = Path(source_root)
        root = (Path(site.path).parent / root).resolve() if not root.is_absolute() else root.resolve()
    return OrcModule(name, root, site)
