"""Attempt-private external dispatch, separated from coordinator publication."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.workflow.workspace_files import WorkspaceFiles

from .authority import RunAuthority
from .commands import CommandPerformerError, launch_command, workspace_relative_path
from .confined_dispatch import EFFECT_UNSUPPORTED, ConfinedDispatchRefusal, ConfinedLeafContext, dispatch_confined
from .interpreters import is_image_pin
from . import agent_turn_recovery, agent_turns, phased_providers
from .agent_sessions import perform_allocation
from .providers import launch_provider
from .run_ref import perform_evaluated_run_ref


@dataclass(frozen=True)
class PreparedAttempt:
    authority: RunAuthority
    node: Mapping[str, Any]
    identity: str
    ordinal: int
    result_path: str
    input_digest: str
    parts: Mapping[str, str]
    implementation_files: Mapping[str, Any]
    dependencies: tuple[str, ...]
    resolved: Any
    workspace: Path
    workspace_files: WorkspaceFiles
    site_classes: Mapping[str, str]
    provider_executor: ProviderExecutor | None
    attempt_files: WorkspaceFiles
    launch_cwd: Path | None = None
    stream_output: bool = False
    confined: ConfinedLeafContext | None = None  # set for run_ref_confinement.v1 children only
    views: Any = None
    recovered: bool = False
    phased_deadline: float | None = None


@dataclass(frozen=True)
class ExternalOutcome:
    result_path: str | None = None
    run_ref: Any = None
    agent_turn: Any = None
    phased: Any = None


def perform_external(attempt: PreparedAttempt) -> ExternalOutcome:
    """Perform one external operation without publishing the parent memo.

    Serial E1 uses its synchronous wrapper. Parallel workers use that driver
    with lifecycle acknowledgements persisted by the parent coordinator. A confined
    attempt dispatches only through its leaf runner; it has no host route.
    """
    node = attempt.node
    if attempt.confined is not None:
        return ExternalOutcome(result_path=dispatch_confined(attempt))
    if attempt.authority.confined or any(map(is_image_pin, attempt.authority.header["interpreters"].values())):
        raise ConfinedDispatchRefusal(EFFECT_UNSUPPORTED)
    logical_root = attempt.workspace if attempt.launch_cwd is not None else None
    if node['class'] == 'command':
        path = _dispatch_command(attempt, logical_root)
        return ExternalOutcome(result_path=path)
    if node['class'] == 'agent':
        return perform_allocation(attempt)
    if node['class'] == 'agent_turn' and attempt.recovered:    # resume of a completed pending turn: never redispatched
        return agent_turn_recovery.recover_pending_turn(attempt)
    if node['class'] == 'agent_turn':
        return agent_turns.perform_turn(attempt, views=attempt.views)
    if node['class'] == 'provider_phased':
        return ExternalOutcome(phased=phased_providers.prepare_phased_provider_attempt(
            attempt, deadline=attempt.phased_deadline, transport_root=Path('/tmp')))
    if node['class'] == 'run_ref':
        result = perform_evaluated_run_ref(attempt.authority, attempt.resolved,
            attempt.identity, attempt.ordinal, attempt.workspace)
        return ExternalOutcome(run_ref=result)
    path = workspace_relative_path(attempt.workspace, attempt.authority.run_root / attempt.result_path)
    launch_provider(node, attempt.resolved, attempt.identity,
        executor=attempt.provider_executor, attempt_files=attempt.attempt_files,
        workspace_files=attempt.workspace_files, result_path=path,
        stream_output=attempt.stream_output, launch_cwd=attempt.launch_cwd,
        logical_workspace_root=logical_root)
    return ExternalOutcome(result_path=path)


def _dispatch_command(attempt, logical_root):
    resolved_argv, document = attempt.resolved
    argv = list(resolved_argv)
    if document is not None:
        path = attempt.attempt_files.workspace / 'inputs.json'
        argv.append(str(path) if logical_root is not None
            else workspace_relative_path(attempt.workspace, path))
    interpreter = attempt.node['command'][0]
    if '/' not in interpreter:
        pin = attempt.authority.header['interpreters'].get(interpreter)
        if not isinstance(pin, Mapping) or not isinstance(pin.get('path'), str):
            raise CommandPerformerError('command_interpreter_missing',
                f'run authority has no interpreter pin for {interpreter!r}')
        argv[0] = pin['path']
    return launch_command(attempt.node, argv, attempt_files=attempt.attempt_files,
        workspace_files=attempt.workspace_files, input_document=document,
        launch_cwd=attempt.launch_cwd, logical_workspace_root=logical_root)
