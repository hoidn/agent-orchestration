"""Refuse retired prompt-import execution before reading or writing inputs."""

import sys
from argparse import Namespace


def prompt_import_workflow(args: Namespace) -> int:
    print("[prompt_execution_retired] prompt run/import are retired; use a separately retained complete release/environment", file=sys.stderr)
    return 2
