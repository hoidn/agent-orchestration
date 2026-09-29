"""The typechecked program of an entry module, taken from the compiler's own pipeline.

The compiler has no public entry that stops after typecheck: every module is
typechecked and then lowered to flat steps in `_lower_workflows_for_route`.
The spike replaces that function for the duration of one compile. Imported
modules are lowered as usual (their bundles feed the entry's typecheck); for
the entry module the arguments are kept and lowering does not run, so a program
that typechecks is captured even when the flat route would refuse it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from orchestrator.workflow_lisp import compiler
from orchestrator.workflow_lisp.procedures import procedure_type_env_for


class _Typechecked(BaseException):
    """Stops the compile of the entry module after typecheck (not an error)."""


@dataclass(frozen=True)
class TypedProgram:
    entry: Any  # TypedWorkflowDef
    workflows: Mapping[str, Any]
    procedures: Mapping[str, Any]
    type_env: Any
    procedure_type_envs: Mapping[str, Any]
    workflow_type_envs: Mapping[str, Any]
    command_boundaries: Mapping[str, Any]
    externs: Mapping[str, Any]
    target: str
    entry_dir: str  # the entry module's directory, relative to the first source root

    def workflow_type_env(self, name: str) -> Any:
        return self.workflow_type_envs.get(name) or self.type_env

    def procedure_type_env(self, procedure: Any) -> Any:
        return procedure_type_env_for(procedure, procedure_type_envs=self.procedure_type_envs, default=self.type_env)


def typecheck_program(
    entry_path: Path,
    *,
    entry_workflow: str,
    source_roots: tuple[Path, ...],
    command_boundaries: Mapping[str, Any],
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, str] | None = None,
) -> TypedProgram:
    """Typecheck `entry_path` and its imports; raise the compiler's error if it does not typecheck."""

    entry_resolved = entry_path.resolve()
    captured: dict[str, Any] = {}
    original = compiler._lower_workflows_for_route

    def capture(**kwargs: Any):
        if Path(kwargs["workflow_path"]).resolve() != entry_resolved:
            return original(**kwargs)
        captured.update(kwargs)
        raise _Typechecked

    with patch.object(compiler, "_lower_workflows_for_route", capture):
        try:
            compiler.compile_stage3_entrypoint(
                entry_path,
                source_roots=source_roots,
                provider_externs=dict(provider_externs or {}),
                prompt_externs=dict(prompt_externs or {}),
                command_boundaries=dict(command_boundaries),
                validate_shared=True,
                workspace_root=source_roots[0],
                lowering_route=None,
            )
        except _Typechecked:
            pass
    if not captured:
        raise RuntimeError(f"the compile of {entry_path} never reached lowering")
    workflows = dict(captured.get("available_workflows_by_name") or {})
    workflows.update({w.definition.name: w for w in captured["typed_workflows"]})
    return TypedProgram(
        entry=workflows[entry_workflow],
        workflows=workflows,
        procedures={p.definition.name: p for p in captured["typed_procedures"]},
        type_env=captured["type_env"],
        procedure_type_envs=dict(captured["procedure_type_envs"]),
        workflow_type_envs=dict(captured.get("workflow_type_envs") or {}),
        command_boundaries=dict(captured["command_boundary_environment"].bindings_by_name),
        externs=dict(captured["extern_environment"].bindings_by_name),
        target=str(captured["target_dsl_version"]),
        entry_dir=entry_resolved.parent.relative_to(source_roots[0].resolve()).as_posix(),
    )
