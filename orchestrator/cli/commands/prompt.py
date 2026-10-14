"""Native prompt resume routing and retired creation refusal."""

import sys
from argparse import Namespace

def prompt_workflow(args: Namespace) -> int:
    """Retain native resume and refuse retired creation before reading inputs."""
    if getattr(args, "prompt_command", None) in ("run", "import"):
        print("[prompt_execution_retired] prompt run/import are retired; use a separately retained complete release/environment", file=sys.stderr)
        return 2
    if getattr(args, "prompt_command", None) == "resume":
        from orchestrator.prompt_resume import prompt_resume_workflow
        return prompt_resume_workflow(args)
    print("prompt: choose run, import, or resume", file=sys.stderr)
    return 2
