"""Target 2.36 registration, public route, and artifact identity checks."""

import json
from pathlib import Path

import pytest

from orchestrator.workflow import validation
from orchestrator.workflow.run_ref import bundle_transport, config as run_ref_config
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.closed.target import entry_target_dsl_version
from tests.test_workflow_lisp_closed_program_compile_cli import _build_state
from tests.test_workflow_lisp_generic_unions_runtime import _public_run, _public_run_files


W3_TARGET = "2.36"
EVALUATED_TARGET = "2.35"
FLAT_CONTROL_TARGET = "2.34"

PURE_PROGRAM = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/entry)
  (export run)
  (defrecord Result (answer Int))
  (defworkflow run () -> Result
    (record Result :answer 7)))
"""


def _write_program(root: Path, target: str) -> dict[str, Path]:
    files = _public_run_files(root, {})
    files["source"].parent.mkdir(parents=True, exist_ok=True)
    files["source"].write_text(PURE_PROGRAM.replace("TARGET", target), encoding="utf-8")
    files["workspace"] = root
    return files


@pytest.mark.parametrize(
    "registry",
    [
        pytest.param(syntax.SUPPORTED_TARGET_DSL_VERSIONS, id="frontend"),
        pytest.param(validation.DEFAULT_SUPPORTED_VERSIONS, id="shared-validation"),
        pytest.param(run_ref_config._SUPPORTED_TARGET_DSL_VERSIONS, id="run-ref-config"),
        pytest.param(bundle_transport._SUPPORTED_TARGET_DSL_VERSIONS, id="bundle-transport"),
    ],
)
def test_target_236_is_registered(registry) -> None:
    assert W3_TARGET in registry


def test_w3_feature_gate_starts_at_236_and_evaluated_route_stays_at_235() -> None:
    # W3-only local-hook inference starts at 2.36; evaluated execution starts at 2.35.
    assert syntax.target_dsl_supports_local_hook_inference("2.35") is False
    assert syntax.target_dsl_supports_local_hook_inference(W3_TARGET) is True
    assert syntax.target_dsl_uses_evaluated_execution(FLAT_CONTROL_TARGET) is False
    assert syntax.target_dsl_uses_evaluated_execution(EVALUATED_TARGET) is True
    assert syntax.target_dsl_uses_evaluated_execution(W3_TARGET) is True
    assert syntax.target_dsl_uses_evaluated_execution("3.0") is False
    assert syntax.target_dsl_supports_local_hook_inference("3.0") is False


def test_shared_validation_orders_236_after_235() -> None:
    order = validation.DEFAULT_VERSION_ORDER
    assert order[order.index(EVALUATED_TARGET) + 1] == W3_TARGET


@pytest.mark.parametrize(
    "target",
    [FLAT_CONTROL_TARGET, EVALUATED_TARGET, W3_TARGET],
    ids=["flat-234", "evaluated-235", "evaluated-w3-236"],
)
def test_public_run_keeps_pure_program_semantics_across_routes(tmp_path: Path, monkeypatch, target: str) -> None:
    files = _write_program(tmp_path, target)
    monkeypatch.chdir(tmp_path)

    result = _public_run(files)

    assert result.exit_code == 0
    assert result.run_root is not None
    if target == FLAT_CONTROL_TARGET:
        assert dict(result.workflow_outputs) == {"return__answer": 7}
        assert (result.run_root / "state.json").is_file()
        assert not (result.run_root / "run.json").exists()
    else:
        # Evaluated execution returns the result record directly and publishes
        # its run authority; the flat route uses legacy return__ fields.
        assert dict(result.workflow_outputs) == {"answer": 7}
        assert (result.run_root / "run.json").is_file()
        assert (result.run_root / "memo.jsonl").is_file()


def test_public_compile_w3_artifact_preserves_non_target_structure_and_source_identity(
    tmp_path: Path,
) -> None:
    files = _write_program(tmp_path, EVALUATED_TARGET)
    source_target_235 = entry_target_dsl_version(files["source"])
    summary_235, program_235, _artifact_235 = _build_state(files)
    source_235 = files["source"].read_bytes()

    files = _write_program(tmp_path, W3_TARGET)
    source_target_236 = entry_target_dsl_version(files["source"])
    summary_236, program_236, _artifact_236 = _build_state(files)

    assert source_target_235 == EVALUATED_TARGET
    assert source_target_236 == W3_TARGET
    # Source target participates in identity; the representation stays the same.
    tree_235 = dict(program_235.tree)
    tree_236 = dict(program_236.tree)
    assert tree_235.pop("target") == EVALUATED_TARGET
    assert tree_236.pop("target") == W3_TARGET
    assert tree_235 == tree_236
    assert program_235.digest != program_236.digest
    for summary, program, source_target in (
        (summary_235, program_235, source_target_235),
        (summary_236, program_236, source_target_236),
    ):
        manifest = json.loads((Path(summary["build_root"]) / "manifest.json").read_text())
        assert program.tree["target"] == source_target
        assert manifest["target"] == source_target
    assert summary_235["program_digest"] == program_235.digest
    assert summary_236["program_digest"] == program_236.digest
    assert summary_235["build_key"] != summary_236["build_key"]
    assert source_235 != files["source"].read_bytes()
