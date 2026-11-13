"""Evidence suite for G6 hook-redundancy and G8 deletion gating."""

from __future__ import annotations

import importlib
from pathlib import Path


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_FIXTURES = FIXTURES / "valid"
PHASE_SCOPE_STDLIB_FIXTURE = VALID_FIXTURES / "phase_scope_stdlib_targets.orc"


def _form_registry_module():
    return importlib.import_module("orchestrator.workflow_lisp.form_registry")


def _control_dispatch_module():
    return importlib.import_module("orchestrator.workflow_lisp.lowering.control_dispatch")


def test_g8_marks_public_with_phase_registry_head_as_compatibility_only() -> None:
    registry = _form_registry_module()

    spec = registry.get_form_spec("with-phase")

    assert spec is not None
    assert spec.macro_bindable is True
    assert "compatibility_route_only" in spec.feature_tags
