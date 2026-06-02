"""CLI wrapper for Workflow Lisp migration parity reports."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

from orchestrator.workflow_lisp.migration_parity import run_migration_parity


def migration_parity_workflow(args: Namespace) -> int:
    try:
        summary = run_migration_parity(
            targets_file=Path(args.targets_file).resolve(),
            output_root=Path(args.output_root).resolve(),
            selected_targets=list(args.target or ()),
            repo_root=Path.cwd(),
            generated_by=[
                "python",
                "-m",
                "orchestrator",
                "migration-parity",
                "--targets-file",
                str(args.targets_file),
                "--output-root",
                str(args.output_root),
            ]
            + [item for target in (args.target or ()) for item in ("--target", target)],
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(summary, sort_keys=True))
    return 0
