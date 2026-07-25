"""Thin provider peer-group client commands."""

from __future__ import annotations

import json
import sys
from typing import Callable
from uuid import uuid4

from orchestrator.workflow.provider_peer_group.models import (
    PeerFailureReceipt,
    PeerReceipt,
)
from orchestrator.workflow.provider_peer_group.protocol import (
    PeerProtocolClosedError,
    peer_ack,
    peer_finish,
    peer_ready,
    peer_send,
)


def _request_id() -> str:
    return f"peer-client-{uuid4().hex}"


def _run(operation: Callable[[str], PeerReceipt]) -> int:
    try:
        receipt = operation(_request_id())
    except (PeerProtocolClosedError, ValueError) as exc:
        print(f"peer request failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            receipt.to_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 2 if isinstance(receipt, PeerFailureReceipt) else 0


def peer_ready_workflow() -> int:
    return _run(lambda request_id: peer_ready(request_id=request_id))


def peer_send_workflow(
    *,
    target_binding: str,
    message: str,
) -> int:
    return _run(
        lambda request_id: peer_send(
            target_binding=target_binding,
            message=message,
            request_id=request_id,
        )
    )


def peer_ack_workflow(*, message_id: str) -> int:
    return _run(
        lambda request_id: peer_ack(
            message_id=message_id,
            request_id=request_id,
        )
    )


def peer_finish_workflow() -> int:
    return _run(lambda request_id: peer_finish(request_id=request_id))
