"""One fresh dynamic run with direct shared command performance."""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import logging
import os
from pathlib import Path

from orchestrator.contracts.output_contract import OutputContractError
from orchestrator.prompt_scaffold_fs import open_root_creating
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.run_lock import reserved_run_writer_lock, run_root_matches_fd, workspace_run_lock
from orchestrator.state import StateManager
from orchestrator.variables.substitution import render_variable_value
from orchestrator.workflow.evaluated.closure import ClosureEvidenceError, resolve_command_evidence
from orchestrator.workflow.evaluated.commands import (
    CommandPerformerError,
    CommandTemplateError,
    _command_document_argv,
    perform_command,
    workspace_relative_path,
)
from orchestrator.workflow.evaluated.inputs import DocumentInputError, _prepare_command_document_fields
from orchestrator.workflow.evaluated.interpreters import InterpreterError, check_command_interpreter
from orchestrator.workflow.evaluated.providers import (
    ProviderPerformerError,
    _resolve_provider_input_values,
    current_provider_delivery_name,
    perform_provider,
)
from orchestrator.workflow.evaluated.values import _thaw
from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow_lisp.dynamic.program import _pointer
from orchestrator.workflow_lisp.closed.frontend import WorkflowIOReader
from .evaluator import _error, evaluate
from .state import effect_paths, error_payload, publish_dynamic_run

logger = logging.getLogger(__name__)


def _safe_command_error(
    program, exc, *, pointer, code, context, steps, ordinal=None,
    node=None, result_descriptor=None,
):
    error_code = getattr(exc, 'code', None)
    if type(error_code) is not str or not error_code:
        error_code = 'dynamic_command_failed'
    details = {}
    if isinstance(exc, OutputContractError):
        error_code = 'dynamic_command_result_invalid'
        details['violation_kinds'] = _violation_kinds(exc.violations)
        if result_descriptor is not None:
            details['expected_contract'] = _thaw(result_descriptor)
    if isinstance(exc, DocumentInputError):
        details['violation_kinds'] = _violation_kinds(exc.violations)
        if node is not None:
            owner = program.definitions[code]['owner']['module']
            binding = program.bindings[owner]['configuration']['commands'][node['boundary']]
            expected = _command_input_descriptors(program, node, owner, binding).get(exc.field)
            if expected is not None:
                details['expected_contract'] = _thaw(expected)
    if ordinal is not None:
        details['effect_ordinal'] = ordinal
    field_path = getattr(exc, 'value_path', None)
    if type(field_path) is str:
        details['field_path'] = field_path
    return _error(
        program,
        error_code,
        'dynamic command invocation failed',
        pointer,
        context,
        steps,
        **details,
    )


def _safe_provider_error(
    program, exc, *, pointer, code, context, steps, ordinal=None, node=None,
):
    error_code = getattr(exc, 'code', None)
    if type(error_code) is not str or not error_code:
        error_code = 'dynamic_provider_result_invalid' if isinstance(exc, OutputContractError) else 'dynamic_provider_failed'
    details = {}
    violations = getattr(exc, 'violations', None)
    if isinstance(violations, list):
        details['violation_kinds'] = _violation_kinds(violations)
    if error_code in {'provider_result_invalid', 'provider_result_contract', 'dynamic_provider_result_invalid'} and node is not None:
        details['expected_contract'] = _thaw(node['result'])
    if ordinal is not None:
        details['effect_ordinal'] = ordinal
    return _error(
        program,
        error_code,
        'dynamic provider invocation failed',
        pointer,
        context,
        steps,
        **details,
    )


def _violation_kinds(rows):
    return sorted({
        row['type'] for row in rows
        if isinstance(row, dict) and type(row.get('type')) is str
    })


def _check_interpreter(run, command):
    token = command[0]
    if token.startswith('/') or '/' in token:
        return None
    pin = run.header['interpreters'].get(token)
    if pin is None:
        raise InterpreterError('dynamic run has no recorded command interpreter pin')
    changed = check_command_interpreter(pin)
    if changed:
        raise InterpreterError('recorded command interpreter changed during invocation', code='command_interpreter_changed')
    return pin['path']


def _command_input_descriptors(program, node, owner, binding):
    if binding['kind'] == 'external_tool':
        return {row['name']: row['type'] for row in node['input_type']['fields']}
    types = program.bindings[owner]['types']
    return {
        row['transport_key']: program.schemas[types[row['type_name']]]
        for row in binding['input_signature']
    }


def _command_fields(program, node, operands, *, owner, binding, workspace, workspace_files):
    if 'document' not in node:
        return None
    argv_count = len(node['argv'])
    document_values = operands[argv_count:]
    if len(document_values) != len(node['document']):
        raise CommandTemplateError('checked command document operands are incomplete', code='effect_input_invalid')
    external = binding['kind'] == 'external_tool'
    descriptors = _command_input_descriptors(program, node, owner, binding)
    fields = (
        (field, _thaw(value), descriptors[field])
        for (field, _expression), value in zip(node['document'], document_values, strict=True)
    )
    return _prepare_command_document_fields(
        fields,
        external=external,
        workspace=workspace,
        workspace_files=workspace_files,
        require_int64=True,
        redact_runtime_keys=True,
    )[0]


def _perform_dynamic_command(run, program, node, operands, *, pointer, code, context, steps, workspace_files):
    workspace = workspace_files.workspace
    owner = program.definitions[code]['owner']['module']
    binding = program.bindings[owner]['configuration']['commands'][node['boundary']]
    external = binding['kind'] == 'external_tool'
    argv_count = len(node['argv'])
    try:
        document = _command_fields(
            program, node, operands, owner=owner, binding=binding,
            workspace=workspace, workspace_files=workspace_files,
        )
        tail = [render_variable_value(_thaw(value)) for value in operands[:argv_count]]
        argv = [*node['command'], *tail]
        interpreter_path = _check_interpreter(run, node['command'])
        destinations = [
            run.files.workspace / effect_paths(len(run.state['effects']) + 1, 'command')[field]
            for field in ('result_path', 'stdout_path', 'stderr_path')
        ]
        if external and document is not None:
            destinations.append(destinations[0].parent / 'inputs.json')
        evidence = resolve_command_evidence(
            node['command'], node['closure'], workspace_root=workspace,
            destinations=destinations,
        )
    except (OSError, TypeError, ValueError, RecursionError) as exc:
        raise _safe_command_error(
            program, exc, pointer=pointer, code=code, context=context, steps=steps,
            node=node,
        ) from None

    row = run.start_effect(code, pointer, 'command', steps=steps)
    attempt_files = run.active_attempt_files
    try:
        if not run_root_matches_fd(run.files.workspace, run.files.root_fd):
            raise CommandPerformerError('dynamic_state_invalid', 'dynamic run root changed')
        if not run_root_matches_fd(attempt_files.workspace, attempt_files.root_fd):
            raise CommandPerformerError('dynamic_state_invalid', 'dynamic effect attempt changed')
        if interpreter_path is not None:
            argv[0] = interpreter_path
        launch_argv = _command_document_argv(
            argv,
            document if external else None,
            attempt_files=attempt_files,
            workspace_files=workspace_files,
        )
        if document is not None and not external:
            launch_argv.append(document.decode('utf-8'))
        value, _digest = perform_command(
            _thaw(node),
            launch_argv,
            attempt_files=attempt_files,
            workspace_files=workspace_files,
            input_document=document if external else None,
            native_result=True,
        )
        if not run_root_matches_fd(run.files.workspace, run.files.root_fd):
            raise CommandPerformerError('dynamic_state_invalid', 'dynamic run root changed')
        if not run_root_matches_fd(attempt_files.workspace, attempt_files.root_fd):
            raise CommandPerformerError('dynamic_state_invalid', 'dynamic effect attempt changed')
        after = resolve_command_evidence(
            node['command'], node['closure'], workspace_root=workspace,
            prior=evidence, destinations=destinations,
        )
        if after != evidence:
            raise CommandPerformerError('command_closure_written', 'command closure changed during invocation')
        _check_interpreter(run, node['command'])
    except Exception as exc:
        error = _safe_command_error(
            program, exc, pointer=pointer, code=code, context=context,
            steps=steps, ordinal=row['ordinal'], node=node,
            result_descriptor=node['result'],
        )
        run.finish_effect(steps=steps, error=error_payload(error))
        raise error from None
    run.finish_effect(steps=steps)
    return value


def _perform_dynamic_provider(
    run, built, program, node, operands, *, pointer, code, context, steps,
    workspace_files, executor,
):
    owner = program.definitions[code]['owner']['module']
    try:
        provider_bindings = program.bindings[owner]['configuration']['providers']
        provider_binding = provider_bindings.get(node['provider'])
        if provider_binding is None:
            provider_binding = next(
                (
                    row for row in provider_bindings.values()
                    if row['provider_id'] == node['provider']
                ),
                None,
            )
        if provider_binding is None:
            raise ValueError('checked dynamic provider binding is unavailable')
        native_node = _thaw(node)
        native_node['provider'] = provider_binding['provider_id']
        # Null is admitted by the dynamic artifact reader; the shared typed
        # helper's historical contract uses an empty policy mapping.
        native_node['policy'] = native_node['policy'] or {}
        prompt_module = native_node['prompt_owner']['module']
        reader_path = built.source_paths[prompt_module]
        reader = WorkflowIOReader(Path(reader_path), source_paths=built.source_paths)
        ordinal = len(run.state['effects']) + 1
        result_path = workspace_relative_path(
            workspace_files.workspace,
            run.files.workspace / effect_paths(ordinal, 'provider')['result_path'],
        )
        resolved = _resolve_provider_input_values(
            native_node,
            operands,
            workspace=workspace_files.workspace,
            reader=reader,
            result_path=result_path,
            delivery_name=current_provider_delivery_name(native_node["provider"], executor.registry),
        )
    except Exception as exc:
        raise _safe_provider_error(
            program, exc, pointer=pointer, code=code, context=context, steps=steps,
            node=node,
        ) from None

    row = run.start_effect(code, pointer, 'provider', steps=steps)
    attempt_files = run.active_attempt_files
    try:
        if not run_root_matches_fd(run.files.workspace, run.files.root_fd):
            raise ProviderPerformerError('dynamic_state_invalid', 'dynamic run root changed')
        if not run_root_matches_fd(attempt_files.workspace, attempt_files.root_fd):
            raise ProviderPerformerError('dynamic_state_invalid', 'dynamic effect attempt changed')
        value, _digest = perform_provider(
            native_node,
            resolved,
            f"{run.header['run_id']}:{code}:{pointer}:{row['ordinal']}",
            executor=executor,
            attempt_files=attempt_files,
            workspace_files=workspace_files,
            result_path=result_path,
            native_result=True,
        )
        if not run_root_matches_fd(run.files.workspace, run.files.root_fd):
            raise ProviderPerformerError('dynamic_state_invalid', 'dynamic run root changed')
        if not run_root_matches_fd(attempt_files.workspace, attempt_files.root_fd):
            raise ProviderPerformerError('dynamic_state_invalid', 'dynamic effect attempt changed')
    except Exception as exc:
        error = _safe_provider_error(
            program, exc, pointer=pointer, code=code, context=context,
            steps=steps, ordinal=row['ordinal'], node=node,
        )
        run.finish_effect(steps=steps, error=error_payload(error))
        raise error from None
    run.finish_effect(steps=steps)
    return value


def execute_dynamic_run(built, inputs, *, workspace, workflow_path, state_dir=None):
    """Publish captured checked authority before source-free pure evaluation."""
    run_id = StateManager.new_run_id()
    runs_root = Path(state_dir).expanduser().absolute() if state_dir else workspace / '.orchestrate/runs'
    run_root = runs_root / run_id
    source_bytes = built.source_read_trace.raw_bytes_by_path[workflow_path]
    try:
        with ExitStack() as owners:
            owners.enter_context(workspace_run_lock(workspace, run_id))
            parent = WorkspaceFiles(runs_root, root_fd=open_root_creating(runs_root), owns_root=True)
            owners.callback(parent.close)
            files = parent.mkdir_exclusive(run_id)
            owners.callback(files.close)
            info = os.fstat(files.root_fd)
            owners.enter_context(reserved_run_writer_lock(run_root, (info.st_dev, info.st_ino)))
            run = publish_dynamic_run(files, built.program, run_id=run_id, workflow_file=str(workflow_path),
                workflow_checksum='sha256:' + hashlib.sha256(source_bytes).hexdigest(),
                bound_inputs=inputs, workspace=workspace)
            owners.callback(run.close)
            workspace_files = WorkspaceFiles(workspace)
            owners.callback(workspace_files.close)
            provider_executor = None

            def provider_effect(program, node, operands, **details):
                nonlocal provider_executor
                if provider_executor is None:
                    try:
                        provider_executor = ProviderExecutor(
                            workspace,
                            ProviderRegistry(),
                            provider_observation_enabled=False,
                        )
                    except Exception as exc:
                        raise _safe_provider_error(
                            program, exc, pointer=details['pointer'],
                            code=details['code'], context=details['context'],
                            steps=details['steps'], node=node,
                        ) from None
                return _perform_dynamic_provider(
                    run, built, program, node, operands,
                    executor=provider_executor,
                    **details,
                )

            try:
                result = evaluate(
                    run.program,
                    inputs,
                    workspace_files=workspace_files,
                    command_effect=lambda program, node, operands, **details: _perform_dynamic_command(
                        run, program, node, operands, **details,
                    ),
                    provider_effect=provider_effect,
                )
            except ValueError as exc:
                steps = getattr(exc, 'metadata', {}).get('steps', run.state['steps_used'])
                run.fail(error_payload(exc), steps=steps)
                logger.error('[%s] %s', getattr(exc, 'code', 'dynamic_execution_failed'), exc)
                return 1, run_id, run_root, None
            run.complete(result.value, steps=result.steps)
            return 0, run_id, run_root, result.value
    except (OSError, ValueError, RuntimeError) as exc:
        logger.error('[%s] %s', getattr(exc, 'code', 'dynamic_execution_failed'), exc)
        return 1, run_id, run_root, None
