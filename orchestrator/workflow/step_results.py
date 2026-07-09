"""Pure step-result and dictionary helpers for direct loop/call imports.

This leaf module keeps result shaping independent of the workflow executor and
other execution helpers so orchestration loops and calls need not reach back
through the whole executor for stateless operations.
"""

from dataclasses import is_dataclass
from typing import Any, Dict, Mapping, Optional

from ..state import StepResult


def json_safe_runtime_value(value: Any) -> Any:
    """Convert bound runtime metadata into a JSON-safe error/debug payload."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): json_safe_runtime_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [json_safe_runtime_value(item) for item in value]
    if is_dataclass(value):
        return {
            key: json_safe_runtime_value(item)
            for key, item in vars(value).items()
        }
    return str(value)


def contract_violation_result(
    message: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a standardized contract_violation failure result."""
    return {
        'status': 'failed',
        'exit_code': 2,
        'duration_ms': 0,
        'output': '',
        'error': {
            'type': 'contract_violation',
            'message': message,
            'context': context or {},
        },
    }


def to_step_result(result: Dict[str, Any], fallback_name: str) -> StepResult:
    """Convert a persisted result payload into the runtime StepResult model."""
    return StepResult(
        status=result.get("status", "completed" if result.get("exit_code", 0) == 0 else "failed"),
        name=result.get("name", fallback_name),
        step_id=result.get("step_id"),
        exit_code=result.get("exit_code", 0),
        duration_ms=result.get("duration_ms", 0),
        output=result.get("output"),
        lines=result.get("lines"),
        json=result.get("json"),
        error=result.get("error"),
        debug=result.get("debug"),
        truncated=result.get("truncated") if "truncated" in result or result.get("adjudication") else False,
        artifacts=result.get("artifacts"),
        snapshots=result.get("snapshots"),
        adjudication=result.get("adjudication"),
        managed_jobs=result.get("managed_jobs"),
        skipped=result.get("skipped", False),
        files=result.get("files"),
        wait_duration_ms=result.get("wait_duration_ms"),
        poll_count=result.get("poll_count"),
        timed_out=result.get("timed_out"),
        outcome=result.get("outcome"),
        visit_count=result.get("visit_count"),
    )
