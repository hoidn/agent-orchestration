"""Target 2.34 registration for the evaluated execution and repetition reduction plans.

Registration only: 2.34 accepts and lowers exactly what 2.33 does. Later tasks of
`docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md` (Task 0) add
its surface; see `specs/versioning.md` (v2.34 additions).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

import orchestrator
from orchestrator.workflow import validation
from orchestrator.workflow.run_ref import bundle_transport, config as run_ref_config
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.test_workflow_lisp_generic_unions_runtime import (
    _compile,
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.test_workflow_lisp_improve_stdlib import _hook_calls, _write_project
from tests.workflow_lisp_improve_stdlib_sources import REVISE_PROBE

PROGRAM = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/entry)
  (export run)
  (defrecord Candidate (title String) (score Int))
  (defproc revise-candidate
    ((candidate Candidate))
    -> Candidate
    :effects ((uses-command probe_revise))
    :lowering inline
    (command-result probe_revise
      :argv ("python" "PROBE_REVISE" candidate.title "tidy" "fb")
      :returns Candidate))
  (defworkflow run () -> Candidate
    (let* ((first (revise-candidate (record Candidate :title "seed" :score 0)))
           (second (revise-candidate first)))
      second)))
"""

ARTIFACT_FLAGS = (
    "--emit-executable-ir",
    "--emit-core-ast",
    "--emit-runtime-plan",
    "--emit-semantic-ir",
    "--emit-source-map",
    "--emit-debug-yaml",
)

# Each `*_MIN_TARGET_DSL_VERSION` gate in `syntax.py` and the public predicate that reads it.
GATE_PREDICATES = {
    "PROVIDER_SUPERVISION_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_provider_supervision,
    "PROVIDER_PEER_MESSAGING_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_provider_peer_messaging,
    "LIST_TRAVERSAL_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_list_traversal,
    "VALUE_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_value,
    "PROMPT_CALCULUS_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_prompt_calculus,
    "PROMPT_OUTPUT_POSITIONS_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_prompt_output_positions,
    "PROMPT_ATTEMPT_IDENTITY_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_prompt_attempt_identity,
    "PHASED_CONTRACT_DELIVERY_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_phased_contract_delivery,
    "RUN_REF_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_run_ref,
    "NESTED_STRUCTURAL_TRANSPORT_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_nested_structural_transport,
    "TRIAL_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_trial,
    "STRICT_BOOLEAN_CONTROL_FLOW_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_strict_boolean_control_flow,
    "SESSION_ARTIFACT_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_session_artifact,
    "UNION_PROMPT_INPUT_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_union_prompt_input,
    "RICH_LOOP_VALUES_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_rich_loop_values,
    "PURE_CALL_COMPOSITION_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_pure_call_composition,
    "PROVIDER_CONTEXT_VALUES_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_provider_context_values,
    "HUMAN_INPUT_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_human_input,
    "GENERIC_UNION_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_generic_unions,
}
# The gates of the surface that 2.34 adds, which 2.33 must not pass.
GATES_FROM_234 = {
    "NUMERIC_SURFACE_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_numeric_surface,
}


def _write_program(root: Path, target: str) -> dict[str, Path]:
    probes = {"probe_revise": _write_probe(root, "probe_revise", REVISE_PROBE)}
    source = PROGRAM.replace("TARGET", target).replace("PROBE_REVISE", probes["probe_revise"].as_posix())
    _write_sources(root, {"grt/entry.orc": source})
    return _public_run_files(root, probes)


def _build(files: dict[str, Path], out: Path) -> tuple[str, dict[str, bytes]]:
    """Build through the public compile entry in a fresh interpreter with a fixed hash seed.

    Returns the build key and every artifact: the emitted ones and the build directory's files.
    """

    builds = files["source_root"] / ".orchestrate" / "build"
    earlier = set(builds.iterdir()) if builds.exists() else set()
    out.mkdir()
    argv = [
        sys.executable, "-m", "orchestrator", "compile", str(files["source"]), "--entry-workflow", "grt/entry::run",
        "--source-root", str(files["source_root"]), "--provider-externs-file", str(files["providers"]),
        "--prompt-externs-file", str(files["prompts"]), "--command-boundaries-file", str(files["commands"]),
    ]  # fmt: skip
    for flag in ARTIFACT_FLAGS:
        argv += [flag, str(out / flag.removeprefix("--emit-"))]
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONPATH": str(Path(orchestrator.__file__).parents[1])}
    completed = subprocess.run(argv, cwd=files["source_root"], env=env, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    (build_dir,) = set(builds.iterdir()) - earlier
    artifacts = {path.name: path.read_bytes() for path in out.iterdir()}
    artifacts |= {f"build/{path.name}": path.read_bytes() for path in build_dir.iterdir()}
    return build_dir.name, artifacts


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize(
    "registry",
    [
        pytest.param(syntax.SUPPORTED_TARGET_DSL_VERSIONS, id="frontend"),
        pytest.param(validation.DEFAULT_SUPPORTED_VERSIONS, id="shared-validation"),
        pytest.param(run_ref_config._SUPPORTED_TARGET_DSL_VERSIONS, id="run-ref-config"),
        pytest.param(bundle_transport._SUPPORTED_TARGET_DSL_VERSIONS, id="bundle-transport"),
    ],
)
def test_target_234_is_registered(registry) -> None:
    assert "2.34" in registry


def test_shared_validation_orders_234_last() -> None:
    assert validation.DEFAULT_VERSION_ORDER[-2:] == ("2.33", "2.34")


def test_program_targeting_234_runs_through_the_public_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = _write_program(tmp_path, "2.34")
    monkeypatch.chdir(tmp_path)

    result = _public_run(files)

    assert (result.exit_code, dict(result.workflow_outputs), _log(tmp_path / "probe_revise.py")) == (
        0,
        {"return__title": "seed+r+r", "return__score": 2},
        ["seed tidy fb", "seed+r tidy fb"],
    )


def test_234_builds_the_artifacts_of_233_apart_from_the_recorded_version(tmp_path: Path) -> None:
    root = tmp_path / "program"
    root.mkdir()
    files = _write_program(root, "2.33")
    source_233 = files["source"].read_bytes()
    key_233, at_233 = _build(files, tmp_path / "out-233")
    files = _write_program(root, "2.34")
    key_234, at_234 = _build(files, tmp_path / "out-234")
    surface = "build/persisted_workflow_surface.json"
    # The build key, the source digest and the surface digest each hash bytes that record the version.
    derived = {
        key_234: key_233,
        _sha256(files["source"].read_bytes()): _sha256(source_233),
        _sha256(at_234[surface]): _sha256(at_233[surface]),
    }

    normalised = {}
    for name, data in at_234.items():
        data = data.replace(b"2.34", b"2.33")
        for new, old in derived.items():
            data = data.replace(new.encode(), old.encode())
        normalised[name] = data

    assert all(b"2.34" in at_234[name] for name in at_233 if b"2.33" in at_233[name])
    assert normalised == at_233


def test_program_targeting_234_imports_and_runs_std_improve_at_233(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes = _write_project(tmp_path, seed="block", limit=3, target="2.34")
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, probes))

    assert (result.exit_code, dict(result.workflow_outputs), _hook_calls(probes)) == (
        0,
        {
            "return__variant": "BLOCKED",
            "return__value__title": "block+r",
            "return__value__score": 1,
            "return__reason__why": "refused:block+r",
        },
        (["block tidy", "block+r tidy"], ["block tidy fb0"]),
    )


def test_target_235_is_refused_as_unsupported(tmp_path: Path) -> None:
    files = _write_program(tmp_path, "2.35")
    line = next(n for n, text in enumerate(files["source"].read_text().splitlines(), 1) if ":target-dsl" in text)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path)

    diagnostic = excinfo.value.diagnostics[0]
    assert (diagnostic.code, Path(diagnostic.span.start.path), diagnostic.span.start.line) == (
        "target_dsl_unsupported",
        files["source"],
        line,
    )


def test_every_min_target_gate_has_a_predicate_here() -> None:
    assert {name for name in vars(syntax) if name.endswith("_MIN_TARGET_DSL_VERSION")} == set(GATE_PREDICATES) | set(
        GATES_FROM_234
    )


@pytest.mark.parametrize("gate", sorted(GATE_PREDICATES))
def test_every_gate_that_233_passes_holds_at_234(gate: str) -> None:
    predicate = GATE_PREDICATES[gate]

    assert (predicate("2.33"), predicate("2.34")) == (True, True)


@pytest.mark.parametrize("gate", sorted(GATES_FROM_234))
def test_every_gate_of_234_surface_is_closed_at_233(gate: str) -> None:
    predicate = GATES_FROM_234[gate]

    assert (vars(syntax)[gate], predicate("2.33"), predicate("2.34")) == ("2.34", False, True)


def test_target_234_is_2_33_or_newer() -> None:
    assert syntax.target_dsl_is_2_33_or_newer("2.34")
