"""Deferred authoring declarations. No body executes during registration."""
from __future__ import annotations

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
    annotations = resolved_hints(cls)
    reserved = set(Expr.__dict__) | {"_kind", "_args", "_annotation", "_site", "_scope"}
    if reserved.intersection(annotations):
        raise PythonFrontendError("python_record_field_reserved", "Fields cannot use symbolic protocol or private trace names", site=definition_site(cls))
    return annotations


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
            captures[path] = raw
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


class Definition:
    def __init__(self, function, *, returns=MISSING):
        self.function = function
        self.returns = returns
        self.__name__ = function.__name__
        self.__module__ = function.__module__
        self.site = definition_site(function)
        self.kind = "workflow"

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
