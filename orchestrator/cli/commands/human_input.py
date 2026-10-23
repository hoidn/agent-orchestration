"""Thin CLI client for durable human-input requests."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any

from orchestrator.host_input import answer, cancel, pending
from orchestrator.workflow.human_input import get_human_input
from orchestrator.workflow.evaluated.views import has_evaluated_authority
from orchestrator.workflow.evaluated.host_input import HostInputError
from orchestrator.workflow.evaluated.effect_inputs import _PreflightRefusal
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, render_diagnostic


def _run_root(run_id: str, state_dir: str | None) -> Path:
    workspace = Path.cwd()
    runs_root = (
        Path(state_dir).expanduser().resolve()
        if state_dir
        else workspace / ".orchestrate" / "runs"
    )
    return runs_root / run_id


def human_input_command(args: Any) -> int:
    """Read historical or evaluated requests and delegate typed settlements."""

    run_root = _run_root(args.run_id, args.state_dir)
    try:
        if args.input_command == "get":
            evaluated = has_evaluated_authority(run_root)
            record = pending(run_root) if evaluated else get_human_input(run_root)
            if record is None:
                message = "no human input request is active" if evaluated else "no human input request is recorded"
                raise ValueError(message)
        elif args.input_command in {"answer", "cancel"}:
            if not has_evaluated_authority(run_root):
                return _retired_input_mutation()
            if getattr(args, "text", None) is not None:
                raise ValueError("--text is retired; use --value with strict JSON")
            by = getattr(args, "by", None)
            if not isinstance(by, str):
                raise ValueError("--by is required")
            if args.input_command == "answer":
                raw_value = getattr(args, "value", None)
                if raw_value is None:
                    raise HostInputError("host_input_answer_invalid", "--value is required")
                try:
                    value = _strict_json_value(raw_value)
                except (ValueError, json.JSONDecodeError, RecursionError) as exc:
                    raise HostInputError("host_input_answer_invalid", str(exc)) from exc
                record = answer(
                    run_root,
                    args.request_id,
                    value,
                    by=by,
                    attestation=getattr(args, "attestation", None),
                    accept_changed_evidence=getattr(args, "accept_changed_evidence", False),
                    workspace=Path.cwd(),
                )
            else:
                record = cancel(
                    run_root,
                    args.request_id,
                    by=by,
                    attestation=getattr(args, "attestation", None),
                    accept_changed_evidence=getattr(args, "accept_changed_evidence", False),
                    workspace=Path.cwd(),
                )
        else:
            raise ValueError("human input command is invalid")
    except LispFrontendCompileError as exc:
        for diagnostic in exc.diagnostics:
            print(render_diagnostic(diagnostic), file=sys.stderr)
        return 2
    except _PreflightRefusal as exc:
        print(f"input: [{exc.code}] {exc}", file=sys.stderr)
        return 2
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


def _retired_input_mutation() -> int:
    print(
        "[workflow_execution_profile_retired] historical workflow execution is retired; "
        "use a separately retained complete release/environment qualified for this run",
        file=sys.stderr,
    )
    return 2


def _strict_json_value(raw: str) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("non-finite JSON number")
        return parsed

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    return json.loads(
        raw,
        object_pairs_hook=unique_object,
        parse_float=finite_float,
        parse_constant=reject_constant,
    )
