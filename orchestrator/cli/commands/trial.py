"""Retired target-2.25 trial execution entrypoint."""

import sys
from argparse import Namespace


def trial_workflow(args: Namespace) -> int:
    print("[workflow_execution_target_retired] trial execution is retired; use a separately retained complete release/environment", file=sys.stderr)
    return 2


__all__ = ["trial_workflow"]
