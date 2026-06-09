"""CLI wrapper for Workflow Lisp migration parity reports."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

from orchestrator.workflow_lisp.migration_parity import run_migration_parity


def migration_parity_workflow(args: Namespace) -> int:
    gate_mode = "advisory"
    if getattr(args, "require_promotable", False):
        gate_mode = "require_promotable"
    elif getattr(args, "require_non_regressive", False):
        gate_mode = "require_non_regressive"

    try:
        summary = run_migration_parity(
            targets_file=Path(args.targets_file).resolve(),
            output_root=Path(args.output_root).resolve(),
            selected_targets=list(args.target or ()),
            repo_root=Path.cwd(),
            gate_mode=gate_mode,
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
            + (
                ["--require-promotable"]
                if gate_mode == "require_promotable"
                else ["--require-non-regressive"]
                if gate_mode == "require_non_regressive"
                else []
            )
            + [item for target in (args.target or ()) for item in ("--target", target)],
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(summary, sort_keys=True))
    if gate_mode != "advisory" and not bool(summary.get("overall_pass")):
        return 1
    return 0
