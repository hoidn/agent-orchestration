"""Canonical digests distinguish adjacent doubles and signed zero."""

from __future__ import annotations

import hashlib
import math

import pytest

from orchestrator._common.canonical import sha256_json
from orchestrator.workflow.pure_expr import canonical_json_for_pure_value
from orchestrator.workflow.run_ref.contracts import canonical_sha256


DIGESTS = {
    "checkpoint": lambda value: sha256_json({"v": value}),
    "pure": lambda value: hashlib.sha256(canonical_json_for_pure_value({"v": value}).encode("utf-8")).hexdigest(),
    "run-ref": lambda value: canonical_sha256({"v": value}),
}


@pytest.mark.parametrize("name", DIGESTS)
def test_a_digest_distinguishes_every_double_and_only_doubles(name: str) -> None:
    digest = DIGESTS[name]
    value = 0.1 + 0.2

    assert digest(value) != digest(math.nextafter(value, 1.0))
    assert digest(value) == digest(float("0.30000000000000004"))
    assert digest(-0.0) != digest(0.0)
