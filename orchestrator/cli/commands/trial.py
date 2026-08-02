"""Public target-2.25 trial command."""

from __future__ import annotations

import json
import logging
from argparse import Namespace
from pathlib import Path

from orchestrator.cli.commands.run import parse_inputs
from orchestrator.cli.run_ref_root import resolve_run_ref_root
from orchestrator.workflow.trial.sdk import (
    TrialEntryRequestError,
    TrialRunOptions,
    run_trial_entry,
)


logger = logging.getLogger(__name__)


def _optional_path(raw: str | None, *, workspace: Path) -> Path | None:
    if raw is None:
        return None
    value = Path(raw)
    return (value if value.is_absolute() else workspace / value).resolve()


def trial_workflow(args: Namespace) -> int:
    """Compile and execute one trial entry and print its canonical summary."""

    workspace = Path.cwd().resolve()
    try:
        inputs = parse_inputs(args)
        result = run_trial_entry(
            workflow_file=Path(args.workflow).resolve(),
            entry_workflow=args.entry_workflow,
            inputs=inputs,
            workspace=workspace,
            state_dir=_optional_path(args.state_dir, workspace=workspace),
            run_ref_root=resolve_run_ref_root(args.run_ref_root),
            options=TrialRunOptions(
                source_roots=tuple(
                    Path(path).resolve() for path in (args.source_root or ())
                ),
                provider_externs_file=_optional_path(
                    args.provider_externs_file,
                    workspace=workspace,
                ),
                prompt_externs_file=_optional_path(
                    args.prompt_externs_file,
                    workspace=workspace,
                ),
                imported_workflow_bundles_file=_optional_path(
                    args.imported_workflow_bundles_file,
                    workspace=workspace,
                ),
                command_boundaries_file=_optional_path(
                    args.command_boundaries_file,
                    workspace=workspace,
                ),
            ),
        )
    except TrialEntryRequestError as exc:
        logger.error("%s: %s", exc.code, exc)
        return 2
    except (FileNotFoundError, TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.error("trial request invalid: %s", exc)
        return 2
    print(result.canonical_bytes.decode("utf-8"))
    return 0 if result.terminal_status == "completed" else 1


__all__ = ["trial_workflow"]
