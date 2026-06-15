"""C6 author-facing rendering-ergonomics regression surface.

Contract: docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/
workflow-lisp-private-runtime-state-and-consumer-value-flow-c6-author-facing-rendering-ergonomics/
implementation_architecture.md
Target design: docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md
(Sec 7.2, 7.6, 8, 10 C6, 12, 13).

These tests assert on stable diagnostic codes, schema ids, lane/resolution sets,
and dataflow — never on prompt prose.
"""
import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.rendering_ergonomics import (
    RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION,
    RENDERING_ERGONOMICS_REPORT_SCHEMA_VERSION,
    ALLOWED_CONSUMER_LANES,
    ALLOWED_RESOLUTIONS,
    load_rendering_ergonomics_policy,
    build_rendering_ergonomics_report,
    resolve_renderer_for_slot,
)

REPO = Path(__file__).resolve().parents[1]
POLICY_PATH = (
    REPO
    / "workflows/examples/inputs/workflow_lisp_migrations/"
    "design_delta_parent_drain.rendering_ergonomics.json"
)


def test_schema_version_constants_are_exact():
    assert (
        RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION
        == "workflow_lisp_rendering_ergonomics_policy.v1"
    )
    assert (
        RENDERING_ERGONOMICS_REPORT_SCHEMA_VERSION
        == "workflow_lisp_rendering_ergonomics_report.v1"
    )


def test_allowed_lanes_and_resolutions_are_exact():
    assert ALLOWED_CONSUMER_LANES == frozenset(
        {
            "typed_step",
            "prompt_input",
            "observability",
            "entry_publication",
            "compatibility_bridge",
            "timed_body_materialization",
        }
    )
    assert ALLOWED_RESOLUTIONS == frozenset(
        {
            "selected",
            "not_rendered",
            "requires_override",
            "blocked",
        }
    )
