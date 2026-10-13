"""Thin CLI client for durable human-input requests."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from orchestrator.workflow.human_input import get_human_input


def _run_root(run_id: str, state_dir: str | None) -> Path:
    workspace = Path.cwd()
    runs_root = (
        Path(state_dir).expanduser().resolve()
        if state_dir
        else workspace / ".orchestrate" / "runs"
    )
    return runs_root / run_id


def human_input_command(args: Any) -> int:
    """Read a durable request; historical workflow input settlement is retired."""

    if args.input_command in {"answer", "cancel"}:
        print(
            "[workflow_execution_profile_retired] historical workflow execution is retired; "
            "use a separately retained complete release/environment qualified for this run",
            file=sys.stderr,
        )
        return 2

    run_root = _run_root(args.run_id, args.state_dir)
    try:
        if args.input_command == "get":
            record = get_human_input(run_root)
            if record is None:
                raise ValueError("no human input request is recorded")
        else:
            raise ValueError("human input command is invalid")
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"input: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(record, ensure_ascii=True, sort_keys=True))
    return 0
