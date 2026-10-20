"""Python candidate identity, skeleton and provider allocation metrics."""

import ast
import hashlib
from collections.abc import Iterator, Sequence

_PROVIDERS_NAME = "PROVIDERS"
_PROMPT_SUFFIX = "_PROMPT"


def python_skeleton_hash(source: str, *, definitions: Sequence[str]) -> str:
    """Return the sha256 of the normalized named top-level functions of the
    Python module `source` (I3).

    Names bound inside a function (parameters; assignment, `for`,
    comprehension and `with ... as` targets; `except ... as` names; nested
    function and class names) and their references become per-function
    ordinals `$0`, `$1`... in first-binding order. Other names are kept,
    except `PROVIDERS` and its subscripts (`#provider`) and prompt constants,
    names ending `_PROMPT` (`#prompt`). Every constant becomes `#lit`;
    docstrings are dropped; attribute names, calls, keywords, operators and
    statement kinds are kept. The functions' canonical `ast.dump` is hashed.
    Raises ValueError when a named function is absent.
    """

    canonical = "\n".join(ast.dump(_PythonSkeleton(f).visit(f)) for f in _python_functions(source, definitions))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def python_provider_allocation(source: str, *, definitions: Sequence[str]) -> dict[str, list[str]]:
    """Return, per named top-level function of the Python module `source`,
    the provider keys its `PROVIDERS["..."]` subscripts name, in source order.
    Raises ValueError when a named function is absent."""

    return {f.name: [key for node in _preorder(f) if (key := _provider_key(node))]
            for f in _python_functions(source, definitions)}


def python_program_digest(source: str) -> str:
    """Return "sha256:" over the `ast.dump` of the whole Python module
    `source`: comments and formatting leave it unchanged, a rename does not."""

    return "sha256:" + hashlib.sha256(ast.dump(ast.parse(source)).encode("utf-8")).hexdigest()


def _python_functions(source: str, definitions: Sequence[str]) -> list[ast.FunctionDef]:
    """The first top-level function of each name in `definitions`, in that order."""

    found: dict[str, ast.FunctionDef] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef):
            found.setdefault(node.name, node)
    missing = [name for name in definitions if name not in found]
    if missing:
        raise ValueError(f"definitions not found in source: {missing}")
    return [found[name] for name in definitions]


def _preorder(node: ast.AST) -> Iterator[ast.AST]:
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _preorder(child)


def _provider_key(node: ast.AST) -> str | None:
    """The key of a `PROVIDERS["key"]` subscript, else None."""

    if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == _PROVIDERS_NAME
            and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str)):
        return node.slice.value
    return None


def _python_binders(node: ast.AST, function: ast.FunctionDef) -> list[str]:
    """The names `node` binds inside `function` (its own name excluded)."""

    if isinstance(node, ast.arg):
        return [node.arg]
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return [node.id]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node is not function:
        return [node.name]
    if isinstance(node, ast.ExceptHandler) and node.name:
        return [node.name]
    return []


class _PythonSkeleton(ast.NodeTransformer):
    """Normalize one top-level function in place (see `python_skeleton_hash`)."""

    def __init__(self, function: ast.FunctionDef) -> None:
        self.function = function
        self.local: dict[str, str] = {}
        for node in _preorder(function):
            for name in _python_binders(node, function):
                self.local.setdefault(name, f"${len(self.local)}")

    def _name(self, name: str) -> str:
        if name in self.local:
            return self.local[name]
        if name == _PROVIDERS_NAME:
            return "#provider"
        return "#prompt" if name.endswith(_PROMPT_SUFFIX) else name

    def visit_Name(self, node: ast.Name) -> ast.Name:
        return ast.Name(self._name(node.id), node.ctx)

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        if isinstance(node.value, ast.Name) and self._name(node.value.id) == "#provider":
            return ast.Name("#provider", node.ctx)
        return self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        return ast.Constant("#lit")

    def visit_arg(self, node: ast.arg) -> ast.AST:
        node.arg = self.local[node.arg]
        return self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ast.AST:
        if node.name:
            node.name = self.local[node.name]
        return self.generic_visit(node)

    def _visit_scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> ast.AST:
        if ast.get_docstring(node, clean=False) is not None:
            node.body = node.body[1:]
        if node is not self.function:
            node.name = self.local[node.name]
        return self.generic_visit(node)

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _visit_scope

