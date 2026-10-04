"""Exact target 3.0 public compilation and nonexecuting run preflight."""
from __future__ import annotations

from argparse import Namespace
import json
import logging
from pathlib import Path

from orchestrator._common.io_atomic import atomic_write_text
from orchestrator.contracts.output_contract import OutputContractError, strict_json_loads, validate_contract_value
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.workflow.dynamic.evaluator import bind_inputs
from orchestrator.workflow.evaluated.closure import resolve_command_evidence
from orchestrator.workflow.evaluated.interpreters import InterpreterError, _launchable_digest, pin_command_interpreter
from orchestrator.workflow.evaluated.values import EvaluatedValueError, _thaw
from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow_lisp.build import _cli_request_diagnostic, normalize_frontend_artifact_exports
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, render_diagnostic
from orchestrator.workflow_lisp.dynamic.build import build_dynamic_program_bundle, prepare_dynamic_program_bundle
from orchestrator.workflow_lisp.dynamic.program import _node_children, _pointer
from .evaluated import _request


logger = logging.getLogger(__name__)
_AVAILABLE_RUN_OPTIONS = frozenset({
    'command', 'workflow', 'source_root', 'entry_workflow', 'provider_externs_file',
    'prompt_externs_file', 'command_boundaries_file', 'imported_workflow_bundles_file',
    'input', 'input_file', 'state_dir', 'dry_run', 'log_level', 'debug', 'quiet',
    'verbose', 'stream_output', 'max_retries', 'on_error',
})
_UNAVAILABLE_EXPORTS = ('emit_executable_ir', 'emit_core_ast', 'emit_runtime_plan', 'emit_semantic_ir', 'emit_debug_yaml')
_AVAILABLE_COMPILE_OPTIONS = frozenset({
    'command', 'workflow', 'source_root', 'entry_workflow', 'provider_externs_file',
    'prompt_externs_file', 'command_boundaries_file', 'imported_workflow_bundles_file',
    'diagnostics_json', 'emit_source_map', *_UNAVAILABLE_EXPORTS,
})


def _refuse(path, code, message):
    raise LispFrontendCompileError((_cli_request_diagnostic(code=code, message=message, path=path),))


def validate_dynamic_options(args: Namespace, workflow_path: Path) -> int:
    """Return effective retries; service attributes without a parser marker are explicit."""
    explicit = getattr(args, '_explicit_options', frozenset(vars(args)))
    for name in sorted(set(explicit) - _AVAILABLE_RUN_OPTIONS):
        _refuse(workflow_path, 'dynamic_option_unsupported', f"--{name.replace('_', '-')} is unavailable for target 3.0")
    retries = getattr(args, 'max_retries', 0) if 'max_retries' in explicit else 0
    if type(retries) is not int or retries != 0:
        _refuse(workflow_path, 'dynamic_option_unsupported', 'target 3.0 requires zero runtime retries')
    if getattr(args, 'on_error', 'stop') != 'stop':
        _refuse(workflow_path, 'dynamic_option_unsupported', 'target 3.0 requires --on-error stop')
    return retries


def compile_dynamic_workflow(args, *, workflow_path, workspace, source_read_trace=None):
    """Publish a checked dynamic program; unavailable exports refuse before writes."""
    for name in sorted(set(vars(args)) - _AVAILABLE_COMPILE_OPTIONS):
        _refuse(workflow_path, 'dynamic_option_unsupported', f"{name} is unavailable for target 3.0 compilation")
    for name in _UNAVAILABLE_EXPORTS:
        if getattr(args, name, None):
            _refuse(workflow_path, 'workflow_lisp_cli_input_unsupported', f"--{name.replace('_', '-')} is unavailable for dynamic builds")
    exports = normalize_frontend_artifact_exports(
        {'source_map': list(getattr(args, 'emit_source_map', None) or ())},
        cwd=workspace, source_path=workflow_path, create_parents=False,
    )
    built = build_dynamic_program_bundle(_request(args, workflow_path, workspace), source_read_trace=source_read_trace)
    for export in exports.values():
        export.destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(export.destination, json.dumps(_thaw(built.program.source_map), sort_keys=True, indent=2) + '\n')
    document = {
        'status': 'accepted', 'program_digest': built.program.semantic_digest,
        'provenance_digest': built.program.provenance_digest, 'build_key': built.build_key,
    }
    if not getattr(args, 'diagnostics_json', False):
        document.update(build_root=str(built.build_root), entry_workflow=built.entry_workflow,
                        artifact_paths={'dynamic_program': str(built.artifact_path)},
                        exported_artifacts={name: str(export.destination) for name, export in exports.items()})
    print(json.dumps(document, sort_keys=True))
    return 0


def _inputs(args, program, workspace, files):
    supplied = {}
    if getattr(args, 'input_file', None):
        supplied = strict_json_loads(Path(args.input_file).read_bytes())
        if not isinstance(supplied, dict):
            raise ValueError('input-file must contain a JSON object')
    descriptors = {name: program.schemas[ref] for name, ref in program.definitions[program.entry]['boundary']['params']}
    for override in getattr(args, 'input', None) or ():
        if '=' not in override:
            raise ValueError('--input requires NAME=VALUE')
        name, raw = override.split('=', 1)
        if name not in descriptors:
            raise ValueError('--input names an undeclared parameter')
        schema = transport_schema_for_descriptor(descriptors[name], allow_nested_structures=True)
        supplied[name] = validate_contract_value(raw, _thaw(schema), workspace, finite_floats=True, workspace_files=files)
    return bind_inputs(program, supplied, workspace_files=files)


def _command_preflight(command, closure, workspace):
    pin_command_interpreter(command)
    if '/' in command[0]:
        executable = Path(command[0])
        if not executable.is_absolute():
            executable = workspace / executable
        try:
            _launchable_digest(str(executable))
        except OSError as exc:
            raise InterpreterError(str(exc)) from exc
    resolve_command_evidence(command, closure, workspace_root=workspace)


def _bindings_preflight(program, workspace):
    registry = None
    stack = [(_pointer(_pointer('/definitions', code), 'body'), definition['body'])
             for code, definition in program.definitions.items()]
    while stack:
        pointer, node = stack.pop()
        if node['k'] == 'perform':
            try:
                if node['class'] == 'command':
                    _command_preflight(node['command'], node['closure'], workspace)
                else:
                    if registry is None:
                        registry = ProviderRegistry()
                    provider = registry.get(node['provider'])
                    if provider is None:
                        raise ValueError(f"provider binding {node['provider']!r} is unavailable")
                    _command_preflight(provider.command, (), workspace)
            except (OSError, ValueError) as exc:
                raise EvaluatedValueError(getattr(exc, 'code', 'dynamic_binding_invalid'), str(exc), location=pointer) from exc
        stack.extend(_node_children(node, pointer))


def prepare_dynamic_run(args, *, workflow_path, workspace, source_read_trace=None):
    """Validate options, source, inputs and static bindings without publishing or evaluating."""
    validate_dynamic_options(args, workflow_path)
    built = prepare_dynamic_program_bundle(_request(args, workflow_path, workspace), source_read_trace=source_read_trace)
    files = WorkspaceFiles(workspace)
    try:
        inputs = _inputs(args, built.program, workspace, files)
        _bindings_preflight(built.program, workspace)
    finally:
        files.close()
    return built, inputs


def run_dynamic_workflow(args, *, workspace, workflow_path, source_read_trace=None):
    from .run import RunWorkflowResult
    try:
        built, inputs = prepare_dynamic_run(args, workflow_path=workflow_path, workspace=workspace, source_read_trace=source_read_trace)
        if not getattr(args, 'dry_run', False):
            from orchestrator.workflow.dynamic.runtime import execute_dynamic_run
            exit_code, run_id, run_root, value = execute_dynamic_run(
                built, inputs, workspace=workspace, workflow_path=workflow_path,
                state_dir=getattr(args, 'state_dir', None))
            return RunWorkflowResult(exit_code=exit_code, run_id=run_id, run_root=run_root,
                                     workflow_outputs=value)
    except LispFrontendCompileError as exc:
        for diagnostic in exc.diagnostics:
            logger.error(render_diagnostic(diagnostic))
        return RunWorkflowResult(exit_code=2)
    except (EvaluatedValueError, OutputContractError, OSError, ValueError, TypeError) as exc:
        logger.error('[%s] %s', getattr(exc, 'code', 'dynamic_input_invalid'), exc)
        return RunWorkflowResult(exit_code=2)
    logger.info('Dynamic dry-run passed; no body or effect was executed')
    return RunWorkflowResult(exit_code=0)
