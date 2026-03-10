"""Advisory authoring-time lint rules for workflow DSL migration."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .loaded_bundle import workflow_bundle, workflow_legacy_dict
from .surface_ast import SurfaceStep


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
    warnings: List[Dict[str, Any]] = []
    bundle = workflow_bundle(workflow)
    if bundle is not None:
        _lint_surface_steps(bundle.surface.steps, warnings, "steps")
    else:
        workflow_dict = workflow_legacy_dict(workflow)
        if workflow_dict is None:
            return warnings

        steps = workflow_dict.get("steps")
        if isinstance(steps, list):
            _lint_steps(steps, warnings, "steps")

    warnings.extend(_lint_import_output_collisions(workflow))
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


def _lint_steps(steps: List[Any], warnings: List[Dict[str, Any]], path_prefix: str) -> None:
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue

        step_name = step.get("name")
        if not isinstance(step_name, str) or not step_name:
            step_name = f"step_{index}"
        step_path = f"{path_prefix}[{index}]"

        _lint_step_mapping(step, warnings, step_name=step_name, step_path=step_path)

        _lint_nested_steps(step, warnings, step_path)


def _lint_surface_steps(
    steps: Iterable[SurfaceStep],
    warnings: List[Dict[str, Any]],
    path_prefix: str,
) -> None:
    for index, step in enumerate(steps):
        step_path = f"{path_prefix}[{index}]"
        step_name = step.name or f"step_{index}"

        _lint_step_mapping(step.raw, warnings, step_name=step_name, step_path=step_path)

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


def _lint_step_mapping(
    step: Mapping[str, Any],
    warnings: List[Dict[str, Any]],
    *,
    step_name: str,
    step_path: str,
) -> None:
    if _looks_like_shell_gate(step):
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

    if _looks_like_stringly_equals(step):
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

    if _looks_like_goto_diamond(step):
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


def _lint_nested_steps(step: Mapping[str, Any], warnings: List[Dict[str, Any]], step_path: str) -> None:
    for_each = step.get("for_each")
    if isinstance(for_each, dict):
        nested_steps = for_each.get("steps")
        if isinstance(nested_steps, list):
            _lint_steps(nested_steps, warnings, f"{step_path}.for_each.steps")

    repeat_until = step.get("repeat_until")
    if isinstance(repeat_until, dict):
        nested_steps = repeat_until.get("steps")
        if isinstance(nested_steps, list):
            _lint_steps(nested_steps, warnings, f"{step_path}.repeat_until.steps")

    for branch_name in ("then", "else", "finally"):
        branch = step.get(branch_name)
        if not isinstance(branch, dict):
            continue
        nested_steps = branch.get("steps")
        if isinstance(nested_steps, list):
            _lint_steps(nested_steps, warnings, f"{step_path}.{branch_name}.steps")

    match = step.get("match")
    if isinstance(match, dict):
        cases = match.get("cases")
        if isinstance(cases, dict):
            for case_name, case_block in cases.items():
                if not isinstance(case_block, dict):
                    continue
                nested_steps = case_block.get("steps")
                if isinstance(nested_steps, list):
                    _lint_steps(nested_steps, warnings, f"{step_path}.match.cases.{case_name}.steps")


def _looks_like_shell_gate(step: Mapping[str, Any]) -> bool:
    if "command" not in step:
        return False
    if step.get("expected_outputs") or step.get("output_bundle") or step.get("publishes"):
        return False

    command = step.get("command")
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


def _looks_like_stringly_equals(step: Mapping[str, Any]) -> bool:
    when = step.get("when")
    if not isinstance(when, Mapping):
        return False

    equals = when.get("equals")
    if not isinstance(equals, Mapping):
        return False

    for key in ("left", "right"):
        value = equals.get(key)
        if isinstance(value, str) and _STRINGLY_STEP_REF.search(value):
            return True
    return False


def _looks_like_goto_diamond(step: Mapping[str, Any]) -> bool:
    on = step.get("on")
    if not isinstance(on, Mapping):
        return False

    success = on.get("success")
    failure = on.get("failure")
    if not isinstance(success, Mapping) or not isinstance(failure, Mapping):
        return False

    success_goto = success.get("goto")
    failure_goto = failure.get("goto")
    return (
        isinstance(success_goto, str)
        and isinstance(failure_goto, str)
        and success_goto != failure_goto
    )


def _lint_import_output_collisions(workflow: Any) -> List[Dict[str, Any]]:
    owners: Dict[str, List[str]] = {}
    bundle = workflow_bundle(workflow)
    if bundle is not None:
        for alias, imported_bundle in bundle.imports.items():
            if not isinstance(alias, str):
                continue
            for output_name in imported_bundle.surface.outputs:
                if isinstance(output_name, str):
                    owners.setdefault(output_name, []).append(f"import:{alias}")
    else:
        workflow_dict = workflow_legacy_dict(workflow)
        imports = workflow_dict.get("__imports", {}) if isinstance(workflow_dict, dict) else {}
        if isinstance(imports, dict):
            for alias, imported in imports.items():
                if not isinstance(alias, str) or not isinstance(imported, dict):
                    continue
                output_specs = imported.get("outputs")
                if not isinstance(output_specs, dict):
                    continue
                for output_name in output_specs:
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
