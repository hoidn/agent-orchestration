"""Workflow Lisp MVP frontend compile entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .definition_validation import DefinitionCheckedModule, validate_definition_module
from .expression_validation import ExpressionCheckedModule, validate_expression_module
from .parser import parse_workflow_module_file, parse_workflow_module_text
from .syntax import ParsedWorkflowModule


@dataclass(frozen=True)
class CompiledWorkflowModule:
    """One .orc compilation unit after parser, definition, and expression passes."""

    parsed_module: ParsedWorkflowModule
    definition_module: DefinitionCheckedModule
    expression_module: ExpressionCheckedModule


def compile_workflow_module_text(source_text: str, *, source_path: str) -> CompiledWorkflowModule:
    """Compile one Workflow Lisp source string through the MVP frontend pipeline."""

    parsed_module = parse_workflow_module_text(source_text, source_path=source_path)
    definition_module = validate_definition_module(parsed_module)
    expression_module = validate_expression_module(definition_module)
    return CompiledWorkflowModule(
        parsed_module=parsed_module,
        definition_module=definition_module,
        expression_module=expression_module,
    )


def compile_workflow_module_file(path: str | Path) -> CompiledWorkflowModule:
    """Compile one Workflow Lisp source file through the MVP frontend pipeline."""

    parsed_module = parse_workflow_module_file(path)
    definition_module = validate_definition_module(parsed_module)
    expression_module = validate_expression_module(definition_module)
    return CompiledWorkflowModule(
        parsed_module=parsed_module,
        definition_module=definition_module,
        expression_module=expression_module,
    )


def compile_and_lower_workflow_module_text(source_text: str, *, source_path: str) -> "LoweredWorkflowModule":
    """Compile then lower one Workflow Lisp source string into workflow dictionaries."""

    # Keep lowering imported lazily to avoid a module import cycle.
    from .lowering import lower_compiled_module

    return lower_compiled_module(
        compile_workflow_module_text(
            source_text,
            source_path=source_path,
        )
    )


def compile_and_lower_workflow_module_file(path: str | Path) -> "LoweredWorkflowModule":
    """Compile then lower one Workflow Lisp source file into workflow dictionaries."""

    # Keep lowering imported lazily to avoid a module import cycle.
    from .lowering import lower_compiled_module

    return lower_compiled_module(compile_workflow_module_file(path))
