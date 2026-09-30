"""Target 2.33 registration for CF-1b generic unions and `std/improve`.

Registration only: no new forms are admitted here. See
`docs/plans/2026-09-28-cf1b-composition-first-implementation-plan.md` (Task 1)
and `specs/versioning.md` (v2.33 additions).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow import validation
from orchestrator.workflow.run_ref import bundle_transport, config as run_ref_config
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


def _compile_minimal_module(tmp_path: Path, target_dsl_version: str):
    path = tmp_path / f"target_{target_dsl_version.replace('.', '_')}.orc"
    path.write_text(
        f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target_dsl_version}")
  (defrecord Out
    (label String))
  (defworkflow tiny
    ()
    -> Out
    (record Out :label "ok")))
""",
        encoding="utf-8",
    )
    return compile_stage3_module(
        path,
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=None,
    )


def test_generic_union_minimum_target_is_233() -> None:
    assert syntax.GENERIC_UNION_MIN_TARGET_DSL_VERSION == "2.33"


@pytest.mark.parametrize(
    "registry",
    [
        pytest.param(syntax.SUPPORTED_TARGET_DSL_VERSIONS, id="frontend"),
        pytest.param(validation.DEFAULT_SUPPORTED_VERSIONS, id="shared-validation"),
        pytest.param(run_ref_config._SUPPORTED_TARGET_DSL_VERSIONS, id="run-ref-config"),
        pytest.param(bundle_transport._SUPPORTED_TARGET_DSL_VERSIONS, id="bundle-transport"),
    ],
)
def test_target_233_is_registered(registry) -> None:
    assert "2.33" in registry


def test_shared_validation_orders_233_after_232() -> None:
    order = validation.DEFAULT_VERSION_ORDER
    assert order.index("2.33") == order.index("2.32") + 1


def test_module_targeting_233_compiles_with_no_new_forms(tmp_path: Path) -> None:
    result = _compile_minimal_module(tmp_path, "2.33")

    assert result.validated_bundles["tiny"].surface.version == "2.33"


def test_module_targeting_236_is_rejected_as_unsupported(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_minimal_module(tmp_path, "2.36")

    assert excinfo.value.diagnostics[0].code == "target_dsl_unsupported"


def test_module_targeting_232_still_compiles(tmp_path: Path) -> None:
    result = _compile_minimal_module(tmp_path, "2.32")

    assert result.validated_bundles["tiny"].surface.version == "2.32"
