"""`provider-result :returns <applied generic union>` at target 2.33 (owner decision D1).

A provider hook may declare `:returns Decision[Notes Blocker]` directly. The
payload is checked against the instantiated union at the provider boundary, so a
malformed payload fails the run there and nothing downstream runs. Runs go
through the public entry (`run_workflow`) with a patched provider executor that
writes a fixed payload; the step after the provider call is a command probe that
logs its argv.
"""

from __future__ import annotations

import json
import re
import sys
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.types import PreparedProviderPolicy
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args
from tests.workflow_lisp_improve_stdlib_sources import STD_IMPROVE_PATH


HEADER = '(workflow-lisp\n  (:language "0.1")\n  (:target-dsl "TARGET")\n'

PRELUDE = HEADER + """  (defmodule gpr_entry)
  (import std/improve :only (Decision))
  (export run)
  (defrecord Notes (notes String))
  (defrecord Blocker (issue String) (severity Int))
  (defrecord Outcome (status String))
"""

SOURCE = PRELUDE + """  (defproc review ((draft String)) -> Decision[Notes Blocker]
    :effects ((uses-provider providers.review))
    :lowering inline
    (provider-result providers.review
      :prompt prompts.review
      :inputs (draft)
      :returns Decision[Notes Blocker]))
  (defproc record-outcome ((variant String) (detail String) (severity Int)) -> Outcome
    :effects ((uses-command record_outcome))
    :lowering inline
    (command-result record_outcome
      :argv ("python" "record_outcome.py" variant detail severity)
      :returns Outcome))
  (defworkflow run ((draft String)) -> Outcome
    (let* ((decision (review draft)))
      (match decision
        ((APPROVE a) (record-outcome "APPROVE" a.evidence.notes 0))
        ((REVISE r) (record-outcome "REVISE" r.feedback.notes 0))
        ((BLOCKED b) (record-outcome "BLOCKED" b.reason.issue b.reason.severity))))))
"""

# The applied union appears only in `:returns`, so a rejection names that use.
RETURNS_ONLY_SOURCE = PRELUDE + """  (defworkflow run ((draft String)) -> Outcome
    (let* ((decision (provider-result providers.review
                       :prompt prompts.review
                       :inputs (draft)
                       :returns Decision[Notes Blocker])))
      (record Outcome :status "reviewed"))))
"""

RECORDER = """import json, os, sys
from pathlib import Path
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"status": "recorded"}), encoding="utf-8")
"""

PROVIDERS = {"providers.review": "codex"}
PROMPTS = {"prompts.review": "review.md"}
COMMAND = ("python", "record_outcome.py")


def _install(root: Path, source: str, *, target: str = "2.33") -> Path:
    entry = root / "gpr_entry.orc"
    entry.write_text(source.replace("TARGET", target), encoding="utf-8")
    (root / "review.md").write_text("Review the draft.\n", encoding="utf-8")
    (root / "record_outcome.py").write_text(RECORDER, encoding="utf-8")
    (root / "providers.json").write_text(json.dumps(PROVIDERS), encoding="utf-8")
    (root / "prompts.json").write_text(json.dumps(PROMPTS), encoding="utf-8")
    (root / "commands.json").write_text(
        json.dumps({"record_outcome": {"kind": "external_tool", "stable_command": list(COMMAND)}}), encoding="utf-8"
    )
    (root / "inputs.json").write_text(json.dumps({"draft": "d1"}), encoding="utf-8")
    return entry


class _Provider:
    """Patched provider executor: writes one fixed payload per call and counts calls."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def prepare_invocation(self, provider_name, *_args, **kwargs):
        policy = PreparedProviderPolicy(
            provider_name=provider_name, model=None, effort=None, timeout_sec=None, input_mode="stdin"
        )
        prompt = str(kwargs.get("prompt_content", ""))
        invocation = SimpleNamespace(
            provider_name=provider_name, prompt=prompt, prepared_prompt=prompt, prepared_provider_policy=policy,
            env=dict(kwargs.get("env") or {}), input_mode="stdin",
        )
        return invocation, None

    def execute(self, invocation, **_kwargs):
        self.calls += 1
        Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(self.payload), encoding="utf-8")
        return SimpleNamespace(
            exit_code=0, stdout=b"", stderr=b"", duration_ms=1, error=None, missing_placeholders=None,
            invalid_prompt_placeholder=False, raw_stdout=None, normalized_stdout=None, provider_session=None,
        )


def _public_run(root: Path, payload: dict, monkeypatch: pytest.MonkeyPatch):
    """Run through `run_workflow`; return (exit code, state, provider calls, recorded argv)."""

    entry = _install(root, SOURCE)
    files = {"source": entry, "source_root": root, "providers": root / "providers.json", "prompts": root / "prompts.json"}
    args = _run_args(files, input_file=root / "inputs.json")
    args.entry_workflow = "gpr_entry::run"
    args.command_boundaries_file = str(root / "commands.json")
    provider = _Provider(payload)
    monkeypatch.chdir(root)
    with ExitStack() as stack:
        stack.enter_context(patch.object(ProviderExecutor, "prepare_invocation", provider.prepare_invocation))
        stack.enter_context(patch.object(ProviderExecutor, "execute", provider.execute))
        stack.enter_context(patch.object(sys, "argv", ["orchestrator", "run", str(entry)]))
        exit_code = run_workflow(args).exit_code
    run_dir = next((root / ".orchestrate" / "runs").iterdir())
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    log = root / "record_outcome.log"
    recorded = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return exit_code, state, provider.calls, recorded


def _failed_steps(state: dict) -> dict[str, tuple[str, list[str]]]:
    """Failed step -> (outcome class, violation types)."""

    return {
        name: (
            step["outcome"]["class"],
            [violation["type"] for violation in step["error"]["context"].get("violations", ())],
        )
        for name, step in state["steps"].items()
        if isinstance(step, dict) and step.get("status") == "failed"
    }


@pytest.mark.parametrize(
    ("payload", "recorded"),
    [
        ({"variant": "APPROVE", "evidence": {"notes": "fine"}}, ["APPROVE", "fine", "0"]),
        ({"variant": "REVISE", "feedback": {"notes": "more"}}, ["REVISE", "more", "0"]),
        ({"variant": "BLOCKED", "reason": {"issue": "stop", "severity": 2}}, ["BLOCKED", "stop", "2"]),
    ],
    ids=["approve", "revise", "blocked"],
)
def test_well_formed_payload_reaches_the_caller_as_its_variant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: dict, recorded: list[str]
) -> None:
    exit_code, state, provider_calls, calls = _public_run(tmp_path, payload, monkeypatch)

    assert (exit_code, state["status"], provider_calls, calls) == (0, "completed", 1, [recorded])


@pytest.mark.parametrize(
    ("payload", "violation"),
    [
        ({"variant": "MAYBE", "evidence": {"notes": "x"}}, "variant_discriminant_invalid"),
        ({"variant": "APPROVE"}, "variant_required_field_missing"),
        ({"variant": "APPROVE", "evidence": {"notes": "x"}, "feedback": {"notes": "y"}}, "variant_forbidden_field_present"),
        ({"variant": "BLOCKED", "reason": {"issue": "stop", "severity": "high"}}, "variant_field_type_invalid"),
    ],
    ids=["undeclared-variant", "missing-field", "other-variant-field", "wrong-field-type"],
)
def test_malformed_payload_fails_at_the_provider_boundary_and_nothing_after_it_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: dict, violation: str
) -> None:
    exit_code, state, provider_calls, calls = _public_run(tmp_path, payload, monkeypatch)

    failed = _failed_steps(state)
    assert (exit_code != 0, state["status"], provider_calls, calls) == (True, "failed", 1, [])
    assert [outcome for name, outcome in failed.items() if name.endswith("::review_1")] == [
        ("contract_violation", [violation])
    ]


def _compile(root: Path, source: str, *, target: str):
    entry = _install(root, source, target=target)
    return compile_stage3_entrypoint(
        entry,
        source_roots=(root,),
        provider_externs=PROVIDERS,
        prompt_externs=PROMPTS,
        command_boundaries={"record_outcome": ExternalToolBinding(name="record_outcome", stable_command=COMMAND)},
        validate_shared=True,
        workspace_root=root,
        lowering_route=None,
    )


def _strings(node: object):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def test_output_contract_names_the_concrete_variants_and_fields_and_no_type_parameter(tmp_path: Path) -> None:
    bundle = _compile(tmp_path, SOURCE, target="2.33").validated_bundles_by_name["gpr_entry::run"]
    nodes = workflow_executable_ir_to_json(bundle.ir)["nodes"].values()
    (contract,) = [
        node["execution_config"]["common"]["variant_output"]
        for node in nodes
        if (node.get("execution_config") or {}).get("common", {}).get("variant_output")
    ]
    type_params = set(
        re.search(r"\(defunion Decision :forall \(([^)]*)\)", STD_IMPROVE_PATH.read_text(encoding="utf-8")).group(1).split()
    )
    tokens = {token for text in _strings(contract) for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text)}

    assert contract["discriminant"]["allowed"] == ["APPROVE", "REVISE", "BLOCKED"]
    assert {name: [field["name"] for field in variant["fields"]] for name, variant in contract["variants"].items()} == {
        "APPROVE": ["evidence__notes"],
        "REVISE": ["feedback__notes"],
        "BLOCKED": ["reason__issue", "reason__severity"],
    }
    assert type_params and not tokens & type_params


def test_target_232_rejects_an_applied_union_in_provider_result_returns(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path, RETURNS_ONLY_SOURCE, target="2.32")

    diagnostic = excinfo.value.diagnostics[0]
    lines = RETURNS_ONLY_SOURCE.splitlines()
    line = next(number for number, text in enumerate(lines, start=1) if "(provider-result" in text)
    assert (diagnostic.code, Path(diagnostic.span.start.path).name, diagnostic.span.start.line) == (
        "generic_union_requires_dsl_2_33",
        "gpr_entry.orc",
        line,
    )
