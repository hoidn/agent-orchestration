"""Numeric surface N6 and N7 for persisted values: resume and digests.

Contract: docs/design/workflow_lisp_numeric_surface.md, rules N6 and N7; Task 4
of docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md.

Resume reads values back from `state.json`, so it is a place where a value
enters a run. A 2.34 run whose first command committed and whose second failed
has its saved state edited; the resume through the public entry is refused with
`float_not_finite`, naming the field, before the next command is launched. At
2.33 the same edit is accepted, as today. The refusal covers non-finite values
only: a finite value edited by hand is still trusted.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from orchestrator._common.canonical import sha256_json
from orchestrator.workflow.pure_expr import canonical_json_for_pure_value
from orchestrator.workflow.run_ref.contracts import canonical_sha256

# The command called with label "a" fails once; every other call answers a finite Score.

# `x` reaches every command; `first.value` reaches the command that fails once.


# What the resumed command receives at 2.33, where the edit is accepted.


# N7: a Float enters a digest as the shortest decimal that reads back as the same double.
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
