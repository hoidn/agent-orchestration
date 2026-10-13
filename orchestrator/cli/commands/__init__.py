"""CLI command handlers."""

from importlib import import_module

__all__ = [
    'compile_workflow',
    'explain_workflow',
    'run_workflow',
    'repl_workflow',
    'RunWorkflowResult',
    'prompt_workflow',
    'resume_workflow',
    'report_workflow',
    'dashboard_workflow',
    'monitor_workflows',
    'human_input_command',
    'provider_isolation_environment_manifest_workflow',
    'route_readiness_workflow',
    'peer_ack_workflow',
    'peer_finish_workflow',
    'peer_ready_workflow',
    'peer_send_workflow',
    'provider_materialization_submit_workflow',
]


def __getattr__(name: str):
    """Load only the selected handler, preserving the public command exports."""
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    owner = {
        "RunWorkflowResult": "run", "monitor_workflows": "monitor",
        "human_input_command": "human_input",
        "provider_materialization_submit_workflow": "provider_materialization",
    }.get(name, "peer" if name.startswith("peer_") else name.removesuffix("_workflow"))
    value = getattr(import_module(f".{owner}", __name__), name)
    globals()[name] = value
    return value
