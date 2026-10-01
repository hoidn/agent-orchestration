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
