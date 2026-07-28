"""Private, argument-free provider materialization submit client."""

from __future__ import annotations

import json
import sys
from uuid import uuid4

from orchestrator.workflow.provider_phased_delivery.protocol import (
    MAX_CLIENT_REQUEST_ID_BYTES,
    PhasedSubmitProtocolClosedError,
    receipt_to_dict,
    submit_materialization,
)


def _request_id() -> str:
    value = f"phased-submit-{uuid4().hex}"
    assert len(value.encode("ascii")) <= MAX_CLIENT_REQUEST_ID_BYTES
    return value


def provider_materialization_submit_workflow() -> int:
    """Send exactly one bounded request using only the environment binding."""

    try:
        receipt = submit_materialization(request_id=_request_id())
    except (PhasedSubmitProtocolClosedError, ValueError) as exc:
        print(f"provider materialization submit failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            receipt_to_dict(receipt),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )
    return 2 if receipt.status == "failed" else 0


__all__ = ["provider_materialization_submit_workflow"]
