from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.workflow_lisp.build_manifest_io import (
    _json_data,
    _parse_command_boundaries_manifest,
)
from orchestrator.workflow_lisp.command_boundaries import (
    CertifiedAdapterBinding,
    CertifiedAdapterInputField,
    ExternalToolBinding,
)
from orchestrator.workflow_lisp.closed.program import (
    canonical_command_configuration,
    canonical_configuration,
    canonical_digest,
    logical_asset_base_for_module,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.compiler import (
    _command_boundary_fingerprint_payload,
    compile_stage3_entrypoint,
)
from orchestrator.workflow_lisp.stdlib_contracts import STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME
from orchestrator.workflow_lisp.workflows import PromptExtern, ProviderExtern
from tests.test_workflow_lisp_target_234 import _build as _build_target_234
from tests.test_workflow_lisp_target_234 import _write_program as _write_target_234_program


REVIEW_LOOP_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "phase_stdlib_review_loop.orc"
)


def _review_loop_entry(tmp_path: Path) -> Path:
    source = REVIEW_LOOP_FIXTURE.read_text(encoding="utf-8").replace(
        '(:target-dsl "2.14")',
        f'(:target-dsl "{syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")',
        1,
    )
    import_form = (
        "  (import std/phase :only "
        "(ReviewDecision ReviewFindings ReviewLoopResult review-revise-loop with-phase))"
    )
    assert import_form in source
    source = source.replace(
        import_form,
        import_form + "\n  (export review-revise-loop-demo)",
        1,
    )
    entry = tmp_path / "phase_stdlib_review_loop.orc"
    entry.write_text(source, encoding="utf-8")
    return entry


def _review_loop_args(tmp_path: Path, command_boundaries=None):
    entry = _review_loop_entry(tmp_path)
    return entry, {
        "source_roots": (tmp_path,),
        "command_boundaries": command_boundaries or {},
        "provider_externs": {
            "providers.review": "provider-review",
            "providers.fix": "provider-fix",
            "providers.unused": "provider-unused",
        },
        "prompt_externs": {
            "prompts.implementation.review": "prompts/review.md",
            "prompts.implementation.fix": "prompts/fix.md",
            "prompts.unused": "prompts/unused.md",
        },
    }


def test_closure_is_parsed_with_absence_distinct_from_an_empty_declaration(tmp_path: Path) -> None:
    payload = {
        "a": {"kind": "external_tool", "stable_command": ["python", "a.py"], "closure": ["lib/", "b.py"]},
        "b": {"kind": "external_tool", "stable_command": ["python", "b.py"]},
        "c": {"kind": "external_tool", "stable_command": ["python", "c.py"], "closure": []},
    }

    bindings = _parse_command_boundaries_manifest(payload, manifest_path=tmp_path / "commands.json")

    assert [bindings[name].closure for name in "abc"] == [("lib/", "b.py"), None, ()]
























