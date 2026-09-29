"""`defprompt ... -> <applied generic union>` at target 2.33 (owner decision, shared defect repairs Task 6).

A prompt declaration may name `Decision[Notes Blocker]` as its result. The provider call
that uses the prompt takes that type as its result contract, so a malformed payload fails
the run at the provider boundary and nothing downstream runs. Same technique as
`test_workflow_lisp_generic_union_provider_results.py`: the public entry (`run_workflow`)
with a stand-in provider that writes a fixed payload, and a command probe after the call.
"""

from __future__ import annotations

import json
import re
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.test_workflow_lisp_generic_union_provider_results import (
    PRELUDE,
    PROMPTS,
    PROVIDERS,
    _compile,
    _failed_steps,
    _install,
    _Provider,
    _strings,
)
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args
from tests.workflow_lisp_improve_stdlib_sources import STD_IMPROVE_PATH

PROMPT = """  (defprompt review-prompt
    (:fills (draft :text))
    -> Decision[Notes Blocker]
    "Review {draft}.")
"""

SOURCE = PRELUDE + PROMPT + """  (defproc review ((draft String)) -> Decision[Notes Blocker]
    :effects ((uses-provider providers.review))
    :lowering inline
    (provider-result providers.review
      :prompt (review-prompt :draft draft)))
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

# The applied union appears only in the prompt's `->`, so a rejection names that declaration.
DECLARATION_ONLY_SOURCE = PRELUDE + PROMPT + """  (defworkflow run ((draft String)) -> Outcome
    (let* ((decision (provider-result providers.review :prompt (review-prompt :draft draft))))
      (record Outcome :status "reviewed"))))
"""


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
    assert list(failed.values()) == [("contract_violation", [violation])]
    assert list(state["steps"]) == list(failed)


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


def test_target_232_rejects_an_applied_union_in_a_defprompt_result(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path, DECLARATION_ONLY_SOURCE, target="2.32")

    diagnostic = excinfo.value.diagnostics[0]
    lines = DECLARATION_ONLY_SOURCE.splitlines()
    line = next(number for number, text in enumerate(lines, start=1) if "-> Decision[Notes Blocker]" in text)
    start = diagnostic.span.start
    assert (diagnostic.code, Path(start.path).name, start.line, start.column) == (
        "generic_union_requires_dsl_2_33",
        "gpr_entry.orc",
        line,
        lines[line - 1].index("Decision[") + 1,
    )
