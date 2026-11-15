"""Evidence suite for G6 hook-redundancy and G8 deletion gating."""

from __future__ import annotations

import importlib
from pathlib import Path


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_FIXTURES = FIXTURES / "valid"
PHASE_SCOPE_STDLIB_FIXTURE = VALID_FIXTURES / "phase_scope_stdlib_targets.orc"


def _control_dispatch_module():
    return importlib.import_module("orchestrator.workflow_lisp.lowering.control_dispatch")


