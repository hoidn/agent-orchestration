"""Resume behavior for Workflow Lisp effects without a committed result.

Every run goes through the public entry (`run_workflow`, `resume_workflow`).
Effects are command probes that log their argv, and a stand-in provider. A probe
exits 3 while `<name>.broken` exists next to it; deleting that file is the
corrected cause.
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.workflow_lisp.build_manifest_io import (
    _json_data,
    _parse_command_boundaries_manifest,
)
from orchestrator.workflow_lisp.command_boundaries import (
    CertifiedAdapterBinding,
    ExternalToolBinding,
    build_command_boundary_environment,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.test_workflow_lisp_generic_union_provider_results import _Provider
from tests.workflow_evaluated_totality_helpers import (
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.workflow_evaluated_totality_helpers import _public_run


PROBE = """import json, os, sys
from pathlib import Path
name = sys.argv[1]
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(name + "\\n")
if Path(__file__).with_name(name + ".broken").exists():
    sys.exit(3)
payload = {"variant": "FAST", "note": {"note": name}} if name == "route" else {"note": name + "+"}
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(payload), encoding="utf-8")
"""

PRELUDE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/entry)
  (export run)
  (defrecord Note (note String))
  (defproc step ((name String)) -> Note
    :effects ((uses-command probe))
    (command-result probe :argv ("python" "PROBE" name) :returns Note))
"""

SEQUENCE = PRELUDE + """  (defworkflow run () -> Note
    (let* ((a (step "prepare"))
           (b (step "check")))
      (step "finish"))))
"""


def _install(root: Path, source: str, *, target: str = "2.35", broken: tuple[str, ...] = ()) -> dict[str, Path]:
    probe = _write_probe(root, "probe", PROBE)
    _write_sources(root, {"grt/entry.orc": source.replace("TARGET", target).replace("PROBE", probe.as_posix())})
    for name in broken:
        probe.with_name(f"{name}.broken").write_text("", encoding="utf-8")
    files = _public_run_files(root, {"probe": probe})
    files["providers"].write_text(json.dumps({"providers.seed": "codex"}), encoding="utf-8")
    files["prompts"].write_text(json.dumps({"prompts.seed": "seed.md"}), encoding="utf-8")
    (root / "grt" / "seed.md").write_text("Answer.\n", encoding="utf-8")
    return {**files, "probe": probe}


def _resume_diagnostics(state: dict) -> list[dict]:
    return state.get("resume_diagnostics", [])


def _all_resume_diagnostics(state: dict) -> list[dict]:
    diagnostics = list(_resume_diagnostics(state))
    for frame in state.get("call_frames", {}).values():
        child = frame.get("state") if isinstance(frame, dict) else None
        if isinstance(child, dict):
            diagnostics.extend(_all_resume_diagnostics(child))
    return diagnostics


@pytest.mark.parametrize("kind", ["external_tool", "certified_adapter"])
@pytest.mark.parametrize("value", [1, "false", None])
def test_command_boundary_must_not_repeat_requires_an_exact_boolean(
    tmp_path: Path, kind: str, value: object
) -> None:
    with pytest.raises(LispFrontendCompileError):
        _parse_command_boundaries_manifest(
            {
                "probe": {
                    "kind": kind,
                    "stable_command": ["python", "probe.py"],
                    "must_not_repeat": value,
                }
            },
            manifest_path=tmp_path / "commands.json",
        )


def test_default_command_boundary_serialization_omits_repeat_policy() -> None:
    binding = ExternalToolBinding(name="probe", stable_command=("python", "probe.py"))
    assert "must_not_repeat" not in _json_data(binding)


@pytest.mark.parametrize("kind", ["external_tool", "certified_adapter"])
def test_programmatic_command_boundary_must_not_repeat_requires_boolean(kind: str) -> None:
    if kind == "external_tool":
        binding = ExternalToolBinding(
            name="probe",
            stable_command=("python", "probe.py"),
            must_not_repeat=1,
        )
    else:
        binding = CertifiedAdapterBinding(
            name="probe",
            stable_command=("python", "probe.py"),
            input_contract={},
            output_type_name="",
            effects=(),
            path_safety={},
            source_map_behavior="",
            fixture_ids=(),
            negative_fixture_ids=(),
            must_not_repeat=1,
        )
    with pytest.raises(LispFrontendCompileError):
        build_command_boundary_environment({"probe": binding})


def _with_provider(provider: _Provider | None) -> ExitStack:
    stack = ExitStack()
    if provider is not None:
        stack.enter_context(patch.object(ProviderExecutor, "prepare_invocation", provider.prepare_invocation))
        stack.enter_context(patch.object(ProviderExecutor, "execute", provider.execute))
    return stack


def _run(files: dict[str, Path], provider: _Provider | None = None) -> int:
    with _with_provider(provider):
        return _public_run(files).exit_code
