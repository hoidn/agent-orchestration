"""Deferred authoring declarations. No body executes during registration."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import inspect
from pathlib import Path
import sys
from typing import get_type_hints

from .diagnostics import PythonFrontendError, author_site, definition_site
from .trace import Expr, active_trace, declaration_expression


MISSING = object()


def resolved_hints(value):
    try:
        return get_type_hints(value, globalns=vars(sys.modules[value.__module__]))
    except (NameError, TypeError, ValueError) as exc:
        raise PythonFrontendError("python_annotation_unsupported", str(exc), site=definition_site(value)) from exc


def fields_of(cls):
    from .imports import CompilerCase, CompilerType
    if isinstance(cls, (CompilerCase, CompilerType)):
        return cls._fields()
    annotations = resolved_hints(cls)
    validate_field_names(annotations, site=definition_site(cls))
    return annotations


def validate_field_names(names, *, site=None):
    reserved = set(Expr.__dict__) | {"_kind", "_args", "_annotation", "_site", "_scope"}
    if reserved.intersection(names):
        raise PythonFrontendError("python_record_field_reserved", "Fields cannot use symbolic protocol or private trace names", site=site)


def _shape(cls, kind):
    cls._orc_kind = kind
    cls._orc_site = definition_site(cls)
    def construct(owner, **fields):
        return declaration_expression("construct", (owner, dict(fields)), owner)
    cls.__new__ = staticmethod(construct)
    return cls


def record(cls): return _shape(cls, "record")
def variant(cls): return _shape(cls, "variant")


class RelPath:
    def __init_subclass__(cls, *, under, must_exist=False, **kwargs):
        super().__init_subclass__(**kwargs)
        if not isinstance(must_exist, bool):
            raise PythonFrontendError("python_path_must_exist_invalid", "must_exist requires a bool")
        cls._orc_kind = "path"
        cls._orc_under = under
        cls._orc_must_exist = must_exist
        cls._orc_site = definition_site(cls)

    def __new__(cls, value):
        return declaration_expression("path", (cls, value), cls)


@dataclass(frozen=True)
class Fill:
    kind: str
    annotation: object = None
    out: bool = False


Text = Fill("text")


class Doc:
    def __class_getitem__(cls, annotation): return Fill("doc", annotation)


class PathOf:
    def __class_getitem__(cls, annotation): return Fill("path", annotation)


class Value:
    def __class_getitem__(cls, annotation): return Fill("value", annotation)


class Out:
    def __class_getitem__(cls, annotation): return Fill("path", annotation, True)


@dataclass(frozen=True)
class PromptApplication:
    prompt: Prompt
    values: dict | tuple
    site: object


class _TemplateMarker:
    def __str__(self):
        raise PythonFrontendError("python_prompt_marker_interpolation", "Return a literal template with placeholders")
    __format__ = lambda self, spec: self.__str__()


class Prompt:
    def __init__(self, *, text=None, file=None, fills, returns):
        if (text is None) == (file is None):
            raise PythonFrontendError("python_prompt_source", "Prompt requires exactly one of text or file")
        self.text, self.file = text, file
        self.fills, self.returns = dict(fills), returns
        self.site = author_site()
        self.owner = _caller_module()
        self.function = None
        self.extern_name = None

    @classmethod
    def extern(cls, name, *, returns):
        value = object.__new__(cls)
        value.text = value.file = value.function = None
        value.fills = {}
        value.returns = returns
        value.site = author_site()
        value.owner = _caller_module()
        value.extern_name = name
        return value

    def signature(self):
        if self.function is not None:
            hints = resolved_hints(self.function)
            result = hints.pop("return", MISSING)
            if result is not str:
                raise PythonFrontendError("python_prompt_signature", "Prompt templates require -> str", site=self.site)
            signature = inspect.signature(self.function)
            if any(p.kind not in {p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY} for p in signature.parameters.values()):
                raise PythonFrontendError("python_prompt_signature", "Prompt fills must be named parameters", site=self.site)
            self.fills = {name: hints.get(name) for name in signature.parameters}
        if any(not isinstance(fill, Fill) for fill in self.fills.values()):
            raise PythonFrontendError("python_prompt_signature", "Every fill needs Text, Doc[P], PathOf[P], Value[T] or Out[P]", site=self.site)
        return self.fills

    def template(self, captures):
        if self.function is not None:
            text = self.function(**{name: _TemplateMarker() for name in self.signature()})
        elif self.file is not None:
            path = (Path(self.site.path).parent / self.file).resolve()
            raw = path.read_bytes()
            if captures.setdefault(path, raw) != raw:
                raise PythonFrontendError("python_source_changed", "Prompt source changed during generation", site=self.site)
            text = raw.decode("utf-8")
        else:
            text = self.text
        if not isinstance(text, str):
            raise PythonFrontendError("python_prompt_template", "Prompt template must return a literal string", site=self.site)
        return text

    def __call__(self, *args, **kwargs):
        if self.extern_name is not None:
            if kwargs:
                raise PythonFrontendError("python_prompt_extern_arguments", "Extern prompts take positional typed inputs")
            return PromptApplication(self, tuple(args), author_site())
        names = tuple(self.signature())
        if len(args) > len(names):
            raise PythonFrontendError("python_prompt_arguments", "Too many prompt fill arguments")
        values = dict(zip(names, args))
        if values.keys() & kwargs.keys():
            raise PythonFrontendError("python_prompt_arguments", "Duplicate prompt fill arguments")
        values.update(kwargs)
        if set(values) != set(names):
            raise PythonFrontendError("python_prompt_arguments", "Prompt arguments must supply exactly the declared fills")
        return PromptApplication(self, values, author_site())


def _caller_module():
    frame = inspect.currentframe()
    try:
        while frame:
            if Path(frame.f_code.co_filename).parent != Path(__file__).parent:
                return frame.f_globals.get("__name__")
            frame = frame.f_back
    finally:
        del frame


def prompt(*, returns):
    def decorate(function):
        value = Prompt(text="", fills={}, returns=returns)
        value.function = function
        value.site = definition_site(function)
        value.owner = function.__module__
        return value
    return decorate


class Provider:
    def __init__(self, name, model=None, effort=None, timeout_sec=None):
        self.name = name if name.startswith("providers.") else f"providers.{name}"
        self.options = dict(model=model, effort=effort, timeout_sec=timeout_sec)
        self.site = author_site()

    def __call__(self, fragment, *, model=MISSING, effort=MISSING, timeout_sec=MISSING):
        trace = active_trace()
        if not isinstance(fragment, PromptApplication):
            raise PythonFrontendError("python_provider_prompt", "Provider calls require a Prompt application")
        options = dict(self.options)
        options.update({name: value for name, value in dict(model=model, effort=effort, timeout_sec=timeout_sec).items() if value is not MISSING})
        return trace.bind(trace.expression("provider", (self, fragment, options), fragment.prompt.returns))


class Command:
    def __init__(self, name, *, returns):
        self.name = name
        self.returns = returns

    def __call__(self, *argv, inputs=None):
        trace = active_trace()
        inputs_present = inputs is not None
        inputs = {} if inputs is None else inputs
        if not isinstance(inputs, Mapping) or any(not isinstance(name, str) for name in inputs):
            raise PythonFrontendError("python_command_inputs_invalid", "Command inputs must map string names to typed values")
        return trace.bind(trace.expression(
            "command", (self, tuple(argv), dict(inputs), inputs_present), self.returns,
        ))


@dataclass(frozen=True)
class Effect:
    kind: str
    subject: object


host_input = Effect("host-input", None)


class HostReply:
    def __class_getitem__(cls, answer):
        from .imports import import_orc
        return import_orc("std/host").HostReply[answer]


def uses_command(command):
    if not isinstance(command, Command):
        raise PythonFrontendError("python_proc_effect_invalid", "uses_command requires a Command")
    return Effect("uses-command", command)


def uses_provider(provider):
    if not isinstance(provider, Provider):
        raise PythonFrontendError("python_proc_effect_invalid", "uses_provider requires a Provider")
    return Effect("uses-provider", provider)


def calls_workflow(workflow):
    from .imports import ImportedCallable, OrcMember
    if isinstance(workflow, OrcMember):
        return Effect("calls-workflow", workflow)
    if not isinstance(workflow, (Definition, ImportedCallable, OrcMember)) or workflow.kind != "workflow":
        raise PythonFrontendError("python_proc_effect_invalid", "calls_workflow requires a workflow definition")
    return Effect("calls-workflow", workflow)


class Definition:
    def __init__(self, function, *, returns=MISSING, kind="workflow", effects=MISSING):
        self.function = function
        self.returns = returns
        self.effects = effects
        self.__name__ = function.__name__
        self.__module__ = function.__module__
        self.site = definition_site(function)
        self.kind = kind

    def signature(self):
        hints = resolved_hints(self.function)
        signature = inspect.signature(self.function)
        for name, parameter in signature.parameters.items():
            if parameter.kind not in {parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY} or name not in hints:
                raise PythonFrontendError("python_annotation_unsupported", "Callable parameters require named, annotated arguments", site=self.site)
        annotation = hints.get("return", MISSING)
        if self.returns is not MISSING and annotation is not MISSING and self.returns != annotation:
            raise PythonFrontendError("python_return_annotation_conflict", "returns= conflicts with the return annotation", site=self.site)
        result = annotation if self.returns is MISSING else self.returns
        if result is MISSING:
            raise PythonFrontendError("python_annotation_unsupported", "Callable return annotation is required", site=self.site)
        return signature, {name: hints[name] for name in signature.parameters}, result

    def __call__(self, *args, **kwargs):
        trace = active_trace()
        signature, annotations, result = self.signature()
        try:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
        except TypeError as exc:
            raise PythonFrontendError("python_call_arguments", str(exc)) from exc
        trace.generator.require_definition(self)
        return trace.bind(trace.expression("call", (self, dict(bound.arguments)), result))


def workflow(function=None, *, returns=MISSING):
    def decorate(value): return Definition(value, returns=returns)
    return decorate if function is None else decorate(function)


def proc(function=None, *, returns=MISSING, effects=MISSING):
    def decorate(value):
        if effects is not MISSING and (not isinstance(effects, (tuple, list)) or
                                       any(not isinstance(effect, Effect) for effect in effects)):
            raise PythonFrontendError("python_proc_effect_invalid", "proc effects must be a sequence of effect descriptors", site=definition_site(value))
        return Definition(value, returns=returns, kind="proc", effects=effects)
    return decorate if function is None else decorate(function)


def pure(function):
    return Definition(function, kind="pure")
