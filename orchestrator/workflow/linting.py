"""Advisory authoring-time lint rules for workflow DSL migration."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .conditions import EqualsConditionNode
from .loaded_bundle import workflow_bundle
from .surface_ast import SurfaceOnConfig, SurfaceStep, SurfaceStepKind


_STRINGLY_STEP_REF = re.compile(r"\$\{steps\.[^}]+\}")
_SHELL_GATE_PREFIXES = ("test ", "[ ", "[[ ")
_SHELL_WRAPPERS = {
    ("bash", "-c"),
    ("bash", "-lc"),
    ("sh", "-c"),
    ("sh", "-lc"),
}


def lint_workflow(workflow: Any) -> List[Dict[str, Any]]:
    """Return advisory lint warnings for one already-loaded workflow."""
    bundle = workflow_bundle(workflow)
    if bundle is None:
        raise TypeError("LoadedWorkflowBundle required")

    warnings: List[Dict[str, Any]] = []
    _lint_redundant_relpath_boundary_kinds(bundle.surface.inputs, warnings, boundary_kind="inputs")
    _lint_redundant_relpath_boundary_kinds(bundle.surface.outputs, warnings, boundary_kind="outputs")
    _lint_surface_steps(bundle.surface.steps, warnings, "steps")
    warnings.extend(_lint_import_output_collisions(bundle))
    return warnings


def render_lint_markdown(warnings: List[Dict[str, Any]]) -> str:
    """Render advisory lint warnings as a Markdown appendix."""
    if not warnings:
        return ""

    lines = ["## Advisory Lint", ""]
    for warning in warnings:
        code = warning.get("code", "lint-warning")
        path = warning.get("path", "workflow")
        message = warning.get("message", "")
        suggestion = warning.get("suggestion")
        line = f"- `{code}` at `{path}`: {message}"
        if isinstance(suggestion, str) and suggestion:
            line = f"{line} Suggestion: {suggestion}"
        lines.append(line)
    return "\n".join(lines)


def _lint_surface_steps(
    steps: Iterable[SurfaceStep],
    warnings: List[Dict[str, Any]],
    path_prefix: str,
) -> None:
    for index, step in enumerate(steps):
        step_path = f"{path_prefix}[{index}]"
        step_name = step.name or f"step_{index}"

        _lint_surface_step(step, warnings, step_name=step_name, step_path=step_path)

        if step.for_each_steps:
            _lint_surface_steps(step.for_each_steps, warnings, f"{step_path}.for_each.steps")
        if step.repeat_until is not None:
            _lint_surface_steps(step.repeat_until.steps, warnings, f"{step_path}.repeat_until.steps")
        if step.then_branch is not None:
            _lint_surface_steps(step.then_branch.steps, warnings, f"{step_path}.then.steps")
        if step.else_branch is not None:
            _lint_surface_steps(step.else_branch.steps, warnings, f"{step_path}.else.steps")
        for case_name, case_block in step.match_cases.items():
            _lint_surface_steps(case_block.steps, warnings, f"{step_path}.match.cases.{case_name}.steps")


def _lint_surface_step(
    step: SurfaceStep,
    warnings: List[Dict[str, Any]],
    *,
    step_name: str,
    step_path: str,
) -> None:
    if _looks_like_surface_shell_gate(step):
        warnings.append(
            _warning(
                code="shell-gate-to-assert",
                path=step_path,
                message=(
                    f"Step '{step_name}' looks like a shell gate. Prefer `assert` "
                    "so gate failures stay on the typed `assert_failed` path."
                ),
                step=step_name,
                suggestion="Replace the shell `test` gate with `assert`.",
            )
        )

    if _looks_like_surface_stringly_equals(step.when_predicate):
        warnings.append(
            _warning(
                code="stringly-when-equals",
                path=f"{step_path}.when.equals",
                message=(
                    f"Step '{step_name}' uses stringly `when.equals` against a step reference. "
                    "Prefer typed predicates with structured `ref:` operands."
                ),
                step=step_name,
                suggestion="Use `compare` or `artifact_bool` with `ref:` when migrating to v1.6+.",
            )
        )

    if _looks_like_surface_goto_diamond(step.common.on):
        warnings.append(
            _warning(
                code="goto-diamond-to-structured-control",
                path=f"{step_path}.on",
                message=(
                    f"Step '{step_name}' routes both success and failure with raw `goto`. "
                    "Prefer structured `if` or `match` when the workflow can opt into them."
                ),
                step=step_name,
                suggestion="Replace the hand-wired branch diamond with `if` or `match`.",
            )
        )

def _looks_like_surface_shell_gate(step: SurfaceStep) -> bool:
    if step.kind is not SurfaceStepKind.COMMAND:
        return False
    if step.common.expected_outputs or step.common.output_bundle or step.common.publishes:
        return False
    return _looks_like_shell_command(step.command)


def _looks_like_shell_command(command: Any) -> bool:
    if isinstance(command, str):
        return command.strip().startswith(_SHELL_GATE_PREFIXES)

    if (
        not isinstance(command, Sequence)
        or isinstance(command, (str, bytes))
        or not command
    ):
        return False

    if len(command) >= 1 and isinstance(command[0], str) and command[0] in {"test", "[", "[["}:
        return True

    if len(command) >= 3:
        prefix = (command[0], command[1])
        script = command[2]
        if prefix in _SHELL_WRAPPERS and isinstance(script, str):
            return script.strip().startswith(_SHELL_GATE_PREFIXES)

    return False


def _looks_like_surface_stringly_equals(condition: Any) -> bool:
    if not isinstance(condition, EqualsConditionNode):
        return False

    for value in (condition.left, condition.right):
        if isinstance(value, str) and _STRINGLY_STEP_REF.search(value):
            return True
    return False


def _looks_like_surface_goto_diamond(on: SurfaceOnConfig | None) -> bool:
    if on is None or on.success is None or on.failure is None:
        return False
    return (
        isinstance(on.success.goto, str)
        and isinstance(on.failure.goto, str)
        and on.success.goto != on.failure.goto
    )


def _lint_import_output_collisions(workflow: Any) -> List[Dict[str, Any]]:
    owners: Dict[str, List[str]] = {}
    bundle = workflow_bundle(workflow)
    if bundle is None:
        return []

    for alias, imported_bundle in bundle.imports.items():
        if not isinstance(alias, str):
            continue
        for output_name in imported_bundle.surface.outputs:
            if isinstance(output_name, str):
                owners.setdefault(output_name, []).append(f"import:{alias}")

    warnings: List[Dict[str, Any]] = []
    for output_name, output_owners in sorted(owners.items()):
        unique_owners = sorted(set(output_owners))
        if len(unique_owners) < 2:
            continue
        warnings.append(
            _warning(
                code="import-output-collision",
                path="imports",
                message=(
                    f"Imported/exported output '{output_name}' appears in multiple boundaries "
                    f"({', '.join(unique_owners)}). Keep caller artifact promotion explicit to avoid collisions."
                ),
                output=output_name,
                suggestion="Use explicit call-site `publishes` mappings or rename exported outputs.",
                owners=unique_owners,
            )
        )
    return warnings


def _lint_redundant_relpath_boundary_kinds(
    contracts: Mapping[str, Any],
    warnings: List[Dict[str, Any]],
    *,
    boundary_kind: str,
) -> None:
    for contract_name, contract in contracts.items():
        if not isinstance(contract_name, str):
            continue
        if getattr(contract, "kind", None) != "relpath":
            continue
        if getattr(contract, "value_type", None) != "relpath":
            continue
        warnings.append(
            _warning(
                code="redundant-relpath-boundary-kind",
                path=f"{boundary_kind}.{contract_name}",
                message=(
                    f"Top-level workflow {boundary_kind[:-1]} '{contract_name}' redundantly declares "
                    "`kind: relpath` alongside `type: relpath`. Prefer `type: relpath` alone."
                ),
                suggestion="Drop `kind: relpath` from this workflow boundary contract.",
                boundary=contract_name,
                surface=boundary_kind,
            )
        )


def _warning(*, code: str, path: str, message: str, suggestion: str, **extra: Any) -> Dict[str, Any]:
    warning: Dict[str, Any] = {
        "level": "warning",
        "code": code,
        "path": path,
        "message": message,
        "suggestion": suggestion,
    }
    warning.update(extra)
    return warning
