from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.workflows import PromptExtern


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "closed_program"
TARGET = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
BOUNDARIES = {
    name: ExternalToolBinding(
        name=name,
        stable_command=("python", "probe.py"),
        closure=("probe.py",),
    )
    for name in ("fetch", "inc", "check")
}
PROVIDERS = {"provider": "probe-provider"}
PROMPTS = {"prompt": PromptExtern(name="prompt", input_file="inputs/prompt.md")}


def fixture(name: str, *, target: str = TARGET) -> str:
    return (FIXTURES / f"{name}.orc").read_text(encoding="utf-8").replace("TARGET", target)


def install(
    root: Path,
    sources: str | Mapping[str, str],
    *,
    entry_path: str | Path | None = None,
) -> Path:
    """Write one source or a path-to-source graph under a disposable root."""

    if isinstance(sources, str):
        module = re.search(r"\(defmodule\s+([^\s)]+)\)", sources)
        relative = Path(*module.group(1).split("/")) if module else Path("entry")
        paths = {relative.with_suffix(".orc"): sources}
    else:
        paths = {Path(name): source for name, source in sources.items()}

    installed: dict[Path, Path] = {}
    for relative, source in paths.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source.replace("TARGET", TARGET), encoding="utf-8")
        installed[relative] = path

    if entry_path is not None:
        selected = Path(entry_path)
        return installed.get(selected, root / selected)
    return next(iter(installed.values()))


def build(
    root: Path,
    sources: str | Mapping[str, str],
    *,
    entry_workflow: str | None = None,
    entry_path: str | Path | None = None,
    boundaries: Mapping[str, object] = BOUNDARIES,
    providers: Mapping[str, str] = PROVIDERS,
    prompts: Mapping[str, object] = PROMPTS,
):
    path = install(root, sources, entry_path=entry_path)
    source = path.read_text(encoding="utf-8")
    module = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    if entry_workflow is None:
        entry_workflow = f"{module.group(1)}::run" if module else "run"
    typed = compile_typed_program(
        path,
        entry_workflow=entry_workflow,
        source_roots=(root,),
        command_boundaries=boundaries,
        provider_externs=providers,
        prompt_externs=prompts,
        workspace_root=root,
    )
    from orchestrator.workflow_lisp.closed.build import build_closed_program

    return build_closed_program(typed)


def with_blank_lines(source: str, count: int = 1) -> str:
    return "\n" * count + source


def _wcc_body_nodes(body):
    """Walk retained WCC body nodes without importing an emitter."""
    from orchestrator.workflow_lisp.wcc.model import WccLet, WccCase, WccIf, WccJoin, WccRecJoin, WccParallelMap

    yield body
    if isinstance(body, WccLet):
        yield from _wcc_body_nodes(body.body)
    elif isinstance(body, WccCase):
        for arm in body.arms:
            yield from _wcc_body_nodes(arm.body)
    elif isinstance(body, WccIf):
        yield from _wcc_body_nodes(body.then_body)
        yield from _wcc_body_nodes(body.else_body)
    elif isinstance(body, WccJoin):
        yield from _wcc_body_nodes(body.body)
        yield from _wcc_body_nodes(body.continuation)
    elif isinstance(body, WccRecJoin):
        yield from _wcc_body_nodes(body.body)
        if body.exhaustion is not None:
            yield from _wcc_body_nodes(body.exhaustion)
    elif isinstance(body, WccParallelMap):
        yield from _wcc_body_nodes(body.workspace_body)
        yield from _wcc_body_nodes(body.body)


# ---------------------------------------------------------------------------------------------
# The outcome of a public build and the key of a crash. The defect backlog module and the mutant
# generator both import these, so that one crash has one key in both.

import traceback  # noqa: E402  (appended block: the imports above are another branch's to edit)

import orchestrator  # noqa: E402
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError  # noqa: E402

_PACKAGE = Path(orchestrator.__file__).resolve().parent
# Functions that only raise: the key names their caller.
RAISING_HELPERS = frozenset({
    "contracts/closed_program/check.py:_Checker.fail",
    "workflow_lisp/closed/preparation_check.py:_fail",
})


def crash_signature(error: BaseException) -> tuple[str, str]:
    """The class of `error` and the place it was raised: `path/under/orchestrator.py:qualified.name` of the
    innermost function of the package in its traceback that is not a raising helper. The qualified name keeps
    two methods, or two nested functions, of one name in one file apart. No line number and no message."""
    places = []
    for frame, _line in traceback.walk_tb(error.__traceback__):
        path = Path(frame.f_code.co_filename).resolve()
        if _PACKAGE in path.parents:
            places.append(f"{path.relative_to(_PACKAGE).as_posix()}:{frame.f_code.co_qualname}")
    return type(error).__name__, next(place for place in reversed(places) if place not in RAISING_HELPERS)


def build_outcome(build) -> tuple:
    """What the in-process public build `build()` does: `("builds",)`; `("refused", code, ...)`;
    `("crash", class, place)` for a `compiler_defect`, from the signature of its cause; or
    `("traceback", class, place)` for an exception that leaves the build, which the command line prints as a
    traceback with exit 1."""
    try:
        build()
    except LispFrontendCompileError as stopped:
        codes = [diagnostic.code for diagnostic in stopped.diagnostics]
        if codes == ["compiler_defect"]:
            return ("crash", *crash_signature(stopped.diagnostics[0].cause))
        return ("refused", *codes)
    except Exception as escaped:  # the outcome under test, returned for the caller to compare; nothing is hidden
        return ("traceback", *crash_signature(escaped))
    return ("builds",)
