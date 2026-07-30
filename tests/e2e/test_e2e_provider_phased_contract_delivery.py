"""Real-provider acceptance for the phased design-review consumer."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shlex
import tempfile
import time
from typing import Any

import pytest

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers import (
    interactive_terminal as interactive_terminal_module,
)
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    workflow_runtime_input_contracts,
)
from orchestrator.workflow.prompt_context_report import (
    project_prompt_context_v2,
)
from orchestrator.workflow.prompt_dependency_evidence import (
    canonical_record_bytes,
    evidence_relative_path,
)
from orchestrator.workflow.provider_phased_delivery.ledger import (
    validate_ledger_bytes,
)
from orchestrator.workflow.provider_phased_delivery.protocol import (
    decode_submit_binding,
)
from orchestrator.workflow.provider_attempts import (
    ProviderAttemptScope,
    resolve_aggregate_run_owner,
    validate_provider_attempt_allocations,
    validate_provider_attempt_scope,
)
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from tests.e2e.conftest import skip_if_no_cli, skip_if_no_e2e
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parents[2]
CONSUMER = (
    REPO_ROOT / "workflows/examples/review_revise_design_docs.orc"
)
FIX_PROMPT = (
    REPO_ROOT
    / "prompts/workflows/review_revise_design_docs/fix.md"
)
REVIEW_REPORT = Path("artifacts/review/review.md")
FINDINGS = Path("artifacts/work/findings.json")
TASK_MARKER = Path("artifacts/work/task-action.marker")
TASK_RELEASE = Path("artifacts/work/task-action.release")
SUBMIT_COUNT = Path("artifacts/work/materialization-submit.count")
MODEL = "gpt-5.5"
EFFORT = "high"


def _compile_consumer(workspace: Path):
    return compile_stage3_module(
        CONSUMER,
        provider_externs={
            "providers.design-docs.review": "codex",
            "providers.design-docs.fix": "codex_gpt55",
        },
        prompt_externs={
            "prompts.design-docs.fix": FIX_PROMPT.relative_to(
                REPO_ROOT
            ).as_posix(),
        },
        validate_shared=True,
        workspace_root=workspace,
        lowering_route="wcc_m4",
    )


def _bundle(result, suffix: str):
    return next(
        bundle
        for name, bundle in result.validated_bundles.items()
        if name.endswith(suffix)
    )


def _review_step(result) -> dict[str, Any]:
    helper = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith(
            "::review-design-docs.v1"
        )
    )
    [step] = helper.authored_mapping["steps"]
    return step


def _write_workspace_inputs(workspace: Path) -> None:
    files = {
        "docs/design/target.md": (
            "# Tiny design\n\n"
            "The implementation returns the input unchanged.\n"
        ),
        "artifacts/work/checks.md": "Focused checks passed.\n",
    }
    for relative_path, content in files.items():
        target = workspace / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    driver = workspace / ".q5-phased-driver.py"
    driver.write_text(
        """
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


root = Path(__file__).resolve().parent
mode = sys.argv[1]
marker = root / "artifacts/work/task-action.marker"
release = root / "artifacts/work/task-action.release"
report = root / "artifacts/review/review.md"
findings = root / "artifacts/work/findings.json"
bundle = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
if not bundle.is_absolute():
    bundle = root / bundle
decision = {
    "variant": "APPROVE",
    "review_report": "artifacts/review/review.md",
    "findings": {
        "schema_version": "ReviewFindings.v1",
        "items_path": "artifacts/work/findings.json",
    },
}

if mode == "task":
    if marker.exists():
        raise SystemExit("task action repeated")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("task-action-once\\n", encoding="utf-8")
    while not release.exists():
        time.sleep(0.05)
    print(
        "TASK_PHASE_ACTION_COMPLETE: immediately finish this response; "
        "do not run another tool or perform further work.",
        flush=True,
    )
elif mode == "invalid":
    if not marker.is_file():
        raise SystemExit("task action missing")
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(
        json.dumps(decision, sort_keys=True) + "\\n",
        encoding="utf-8",
    )
elif mode == "valid":
    if marker.read_text(encoding="utf-8") != "task-action-once\\n":
        raise SystemExit("task action changed")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("REAL_PHASED_REVIEW_APPROVED\\n", encoding="utf-8")
    findings.parent.mkdir(parents=True, exist_ok=True)
    findings.write_text('{"items":[]}\\n', encoding="utf-8")
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(
        json.dumps(decision, sort_keys=True) + "\\n",
        encoding="utf-8",
    )
else:
    raise SystemExit(f"unknown mode: {mode}")
""".lstrip(),
        encoding="utf-8",
    )

    submit_shim = workspace / "orchestrator"
    submit_count = workspace / SUBMIT_COUNT
    submit_shim.write_text(
        "\n".join(
            (
                "#!/bin/sh",
                "set -eu",
                'if [ "$#" -eq 1 ] '
                '&& [ "$1" = "provider-materialization-submit" ]; then',
                f"  count_path={shlex.quote(str(submit_count))}",
                f"  driver={shlex.quote(str(driver))}",
                '  observed="0"',
                '  if [ -f "$count_path" ]; then',
                '    observed="$(cat "$count_path")"',
                "  fi",
                '  case "$observed" in',
                '    0) mode="invalid"; next="1" ;;',
                '    1) mode="valid"; next="2" ;;',
                '    *) echo "materialization submit count invalid" >&2; '
                "exit 64 ;;",
                "  esac",
                '  python "$driver" "$mode"',
                '  temporary="${count_path}.tmp.$$"',
                '  printf "%s\\n" "$next" > "$temporary"',
                '  mv "$temporary" "$count_path"',
                "fi",
                'exec python -m orchestrator "$@"',
                "",
            )
        ),
        encoding="utf-8",
    )
    submit_shim.chmod(0o755)


def _review_focus(workspace: Path) -> str:
    driver = shlex.quote(str(workspace / ".q5-phased-driver.py"))
    return (
        "This is a controlled phased-delivery acceptance run. "
        "The exact driver command below is the complete task-phase action; "
        "do not separately review the target or write any review artifacts "
        "during the task phase. "
        f"During the task phase, run `python {driver} task` "
        "exactly once. The command remains blocked until the runtime "
        "has queued the initial materialization turn. As soon as the command "
        "succeeds, immediately finish the current response with "
        "`TASK_PHASE_COMPLETE`; do not wait, poll, inspect files, run another "
        "tool, or perform any further task-phase work. The runtime will "
        "deliver the queued materialization frame after that natural turn "
        "boundary. For each materialization turn, run only the frame's exact "
        "`orchestrator provider-materialization-submit` command. As soon as "
        "it succeeds, immediately finish that response with "
        "`MATERIALIZATION_SUBMITTED`; do not run any other tool. Do not run "
        "candidate-writing commands separately and do not recreate the task "
        "action during either materialization turn."
    )


def _manager(
    workspace: Path,
    *,
    bundle,
    run_id: str,
) -> StateManager:
    contracts = {
        name: dict(contract)
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        contracts,
        {
            "target_doc": "docs/design/target.md",
            "context_docs": [],
            "review_focus": _review_focus(workspace),
            "checks_report": "artifacts/work/checks.md",
            "review_report_target_path": REVIEW_REPORT.as_posix(),
            "revision_report_target_path": (
                "artifacts/work/revision.md"
            ),
            "review_model": MODEL,
            "review_effort": EFFORT,
            "fix_model": MODEL,
            "fix_effort": EFFORT,
            "run__run-id": run_id,
        },
        workspace,
    )
    manager = StateManager(workspace, run_id=run_id)
    manager.initialize(
        CONSUMER.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    return manager


def _wait_for_exact_text(
    path: Path,
    *,
    expected: str,
    deadline: float,
) -> None:
    while time.monotonic() < deadline:
        if path.is_file():
            observed = path.read_text(encoding="utf-8")
            if observed != expected:
                raise ValueError(
                    f"unexpected readiness marker content: {observed!r}"
                )
            return
        time.sleep(0.05)
    raise interactive_terminal_module.InteractiveTerminalError(
        "offer_timeout"
    )


class _RecordingProductionAdapter:
    """Record public lifecycle calls while delegating every operation."""

    def __init__(
        self,
        delegate: Any,
        *,
        workspace: Path,
        manager: StateManager,
    ) -> None:
        self.delegate = delegate
        self.workspace = workspace
        self.manager = manager
        self.calls: list[str] = []
        self.operation_deadlines: list[float] = []
        self.probe_deadlines: list[float] = []
        self.output_bundle_path: Path | None = None
        self.submit_socket_path: Path | None = None
        self.pre_retry_snapshot: dict[str, object] | None = None
        self.natural_proof: Any = None
        self.abort_calls = 0
        self.offer_calls = 0

    def prove_no_backend_allocation(self):
        self.calls.append("prove_no_backend_allocation")
        return self.delegate.prove_no_backend_allocation()

    def start(self, invocation, *, deadline: float):
        self.calls.append("start")
        self.operation_deadlines.append(deadline)
        self.submit_socket_path = decode_submit_binding(
            invocation.env
        ).socket_path
        output_path = Path(
            invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        )
        if not output_path.is_absolute():
            output_path = self.workspace / output_path
        self.output_bundle_path = output_path
        return self.delegate.start(invocation, deadline=deadline)

    def offer(self, handle, literal_message: str, *, deadline: float):
        self.calls.append("offer")
        self.operation_deadlines.append(deadline)
        self.offer_calls += 1
        if self.offer_calls == 1:
            _wait_for_exact_text(
                self.workspace / TASK_MARKER,
                expected="task-action-once\n",
                deadline=deadline,
            )
        if self.offer_calls == 2:
            assert self.output_bundle_path is not None
            state = self.manager._read_state_from_disk().to_dict()
            self.pre_retry_snapshot = {
                "report_exists": (
                    self.workspace / REVIEW_REPORT
                ).exists(),
                "bundle_exists": self.output_bundle_path.exists(),
                "workflow_outputs": state.get("workflow_outputs", {}),
                "artifact_versions": state.get("artifact_versions", {}),
            }
        receipt = self.delegate.offer(
            handle,
            literal_message,
            deadline=deadline,
        )
        if self.offer_calls == 1:
            release = self.workspace / TASK_RELEASE
            release.parent.mkdir(parents=True, exist_ok=True)
            release.touch()
        return receipt

    def offer_close(self, handle, *, deadline: float):
        self.calls.append("offer_close")
        self.operation_deadlines.append(deadline)
        return self.delegate.offer_close(handle, deadline=deadline)

    def join(self, handle, deadline: float):
        self.calls.append("join")
        self.operation_deadlines.append(deadline)
        self.natural_proof = self.delegate.join(handle, deadline)
        return self.natural_proof

    def abort(self, handle, deadline: float):
        self.calls.append("abort")
        self.operation_deadlines.append(deadline)
        self.abort_calls += 1
        return self.delegate.abort(handle, deadline)

    def probe_process_status(self, handle, *, deadline: float):
        self.calls.append("probe_process_status")
        self.probe_deadlines.append(deadline)
        return self.delegate.probe_process_status(
            handle,
            deadline=deadline,
        )


def _ledger_rows(manager: StateManager) -> list[dict[str, Any]]:
    paths = list(
        manager.run_root.rglob(
            "attempt-*-provider-prompt-phases.jsonl"
        )
    )
    assert len(paths) == 1
    payload = paths[0].read_bytes()
    validation = validate_ledger_bytes(payload)
    assert validation["status"] == "complete"
    assert validation["terminal_event"] == "publication_succeeded"
    return [
        json.loads(line)
        for line in payload.decode("ascii").splitlines()
    ]


def _published_evidence(
    manager: StateManager,
    state: dict[str, Any],
) -> dict[str, Any]:
    allocations = validate_provider_attempt_allocations(
        state["provider_attempt_allocations"]
    )
    [allocation] = allocations.values()
    scope = ProviderAttemptScope.from_dict(allocation["scope"])
    validate_provider_attempt_scope(
        scope,
        resolve_aggregate_run_owner(manager),
    )
    last_ordinal = allocation["last_allocated_ordinal"]
    step = state["steps"][scope.enclosing_step.step_name]
    phased = step.get("debug", {}).get("phased_delivery")
    assert isinstance(phased, dict)
    relative_path = phased["functional_evidence"]
    assert isinstance(relative_path, str)
    matching_ordinals = [
        ordinal
        for ordinal in range(1, last_ordinal + 1)
        if str(evidence_relative_path(scope, ordinal)) == relative_path
    ]
    [ordinal] = matching_ordinals
    payload = (manager.run_root / relative_path).read_bytes()
    evidence = json.loads(payload)
    assert isinstance(evidence, dict)
    canonical = canonical_record_bytes(
        evidence,
        compiler_fragment_identity_schema_version=allocation.get(
            "prompt_fragment_identity_schema_version"
        ),
    )
    assert canonical == payload
    assert evidence["attempt"]["scope"] == scope.to_dict()
    assert evidence["attempt"]["scope_sha256"] == scope.key
    assert evidence["attempt"]["ordinal"] == ordinal
    record_sha256 = evidence["record_sha256"]
    assert isinstance(record_sha256, str)
    assert record_sha256.startswith("sha256:")
    assert len(record_sha256) == 71
    return evidence


@pytest.mark.e2e
def test_review_revise_design_docs_real_provider_invalid_then_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject one candidate, retry only materialization, and publish once."""

    static_result = _compile_consumer(REPO_ROOT)
    review_step = _review_step(static_result)
    assert static_result.module.target_dsl_version == "2.23"
    assert review_step["provider_call_policy"] == {
        "model": "${inputs.inputs__review_model}",
        "effort": "${inputs.inputs__review_effort}",
        "delivery": "phased",
        "materialization_attempts": 2,
    }
    assert review_step["timeout_sec"] == 3600

    skip_if_no_e2e()
    for executable in ("codex", "git", "tmux"):
        skip_if_no_cli(executable)

    trusted_checkout = Path(
        os.environ.get(
            "ORCHESTRATE_E2E_TRUSTED_CHECKOUT",
            str(REPO_ROOT),
        )
    ).resolve()
    assert trusted_checkout.is_dir()
    temporary = tempfile.TemporaryDirectory(
        prefix=".q5-task13-",
        dir=trusted_checkout,
    )
    workspace = Path(temporary.name)
    adapters: list[_RecordingProductionAdapter] = []
    try:
        _write_workspace_inputs(workspace)
        result = _compile_consumer(workspace)
        bundle = _bundle(result, "::review-revise-design-docs")
        manager = _manager(
            workspace,
            bundle=bundle,
            run_id=f"q5-task13-real-provider-{workspace.name}",
        )

        inherited_python_path = os.environ.get("PYTHONPATH")
        python_path = str(REPO_ROOT)
        if inherited_python_path:
            python_path = os.pathsep.join(
                (python_path, inherited_python_path)
            )
        monkeypatch.setenv("PYTHONPATH", python_path)
        monkeypatch.setenv(
            "PATH",
            os.pathsep.join(
                (str(workspace), os.environ.get("PATH", ""))
            ),
        )
        original_adapter = (
            interactive_terminal_module
            .InteractiveTerminalTurnQueueAdapter
        )

        def adapter_factory(*args: Any, **kwargs: Any):
            recording = _RecordingProductionAdapter(
                original_adapter(*args, **kwargs),
                workspace=workspace,
                manager=manager,
            )
            adapters.append(recording)
            return recording

        monkeypatch.setattr(
            interactive_terminal_module,
            "InteractiveTerminalTurnQueueAdapter",
            adapter_factory,
        )
        original_prepare = (
            ProviderExecutor.prepare_interactive_invocation
        )

        def prepare_from_trusted_checkout(
            self: ProviderExecutor,
            *args: Any,
            **kwargs: Any,
        ):
            invocation, error = original_prepare(
                self,
                *args,
                **kwargs,
            )
            if invocation is not None:
                invocation = replace(
                    invocation,
                    cwd=trusted_checkout,
                )
            return invocation, error

        monkeypatch.setattr(
            ProviderExecutor,
            "prepare_interactive_invocation",
            prepare_from_trusted_checkout,
        )
        completed = WorkflowExecutor(
            bundle,
            workspace,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")

        if completed["status"] != "completed":
            failure_states: dict[str, object] = {
                "completed": {
                    "status": completed.get("status"),
                    "error": completed.get("error"),
                    "current_step": completed.get("current_step"),
                    "steps": completed.get("steps"),
                },
                "adapters": [
                    {
                        "call_counts": {
                            name: adapter.calls.count(name)
                            for name in sorted(set(adapter.calls))
                        },
                        "offer_calls": adapter.offer_calls,
                        "abort_calls": adapter.abort_calls,
                    }
                    for adapter in adapters
                ],
            }
            for path in manager.run_root.rglob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue
                if payload.get("status") == "failed" or payload.get(
                    "error"
                ):
                    failure_states[
                        path.relative_to(manager.run_root).as_posix()
                    ] = {
                        "status": payload.get("status"),
                        "error": payload.get("error"),
                        "current_step": payload.get("current_step"),
                        "steps": payload.get("steps"),
                    }
            for path in manager.run_root.rglob(
                "attempt-*-provider-prompt-phases.jsonl"
            ):
                failure_states[
                    path.relative_to(manager.run_root).as_posix()
                ] = [
                    json.loads(line)
                    for line in path.read_text(
                        encoding="ascii"
                    ).splitlines()[-8:]
                ]
            pytest.fail(
                json.dumps(
                    failure_states,
                    sort_keys=True,
                    indent=2,
                    default=str,
                )
            )
        assert completed["workflow_outputs"]["return__variant"] == "APPROVED"
        assert completed["workflow_outputs"]["return__review_report"] == (
            REVIEW_REPORT.as_posix()
        )
        assert (workspace / TASK_MARKER).read_text(
            encoding="utf-8"
        ).splitlines() == ["task-action-once"]
        assert (workspace / SUBMIT_COUNT).read_text(
            encoding="utf-8"
        ) == "2\n"
        assert (workspace / REVIEW_REPORT).read_text(
            encoding="utf-8"
        ) == "REAL_PHASED_REVIEW_APPROVED\n"
        assert json.loads(
            (workspace / FINDINGS).read_text(encoding="utf-8")
        ) == {"items": []}

        [adapter] = adapters
        assert adapter.offer_calls == 2
        assert adapter.abort_calls == 0
        assert adapter.calls.count("start") == 1
        assert adapter.calls.count("offer_close") == 1
        assert adapter.calls.count("join") == 1
        assert adapter.pre_retry_snapshot == {
            "report_exists": False,
            "bundle_exists": False,
            "workflow_outputs": {},
            "artifact_versions": {},
        }
        assert adapter.natural_proof is not None
        assert adapter.natural_proof.disposition == "natural_exit"
        assert adapter.natural_proof.pane_absent is True
        assert adapter.natural_proof.server_absent is True
        assert adapter.natural_proof.proof_complete is True
        assert adapter.operation_deadlines
        [whole_attempt_deadline] = set(adapter.operation_deadlines)
        assert adapter.probe_deadlines
        assert all(
            deadline <= whole_attempt_deadline
            for deadline in adapter.probe_deadlines
        )

        rows = _ledger_rows(manager)
        header = rows[0]
        events = [
            row
            for row in rows[1:]
            if row["record_kind"] == "event"
        ]
        assert sum(
            row["event"] == "task_started" for row in events
        ) == 1
        assert sum(
            row["event"] == "validation_rejected"
            for row in events
        ) == 1
        rejected = next(
            row
            for row in events
            if row["event"] == "validation_rejected"
        )
        assert rejected["payload"]["submission_ordinal"] == 1
        assert rejected["payload"]["candidate_manifest"][
            "disposition"
        ] == "rejected"
        assert [
            row["presence"]
            for row in rejected["payload"]["candidate_manifest"]["rows"]
        ] == ["missing", "regular"]
        assert [
            (
                diagnostic["code"],
                diagnostic["reason"],
                diagnostic["rejected_value"]["canonical_value"],
            )
            for diagnostic in rejected["payload"]["diagnostics"]
        ] == [
            (
                "provider_phased_validation_rejected",
                "output_validation_failed",
                "missing_output_file",
            ),
            (
                "provider_phased_validation_rejected",
                "structured_result_validation_failed",
                "variant_field_type_invalid",
            ),
        ]
        assert sum(
            row["event"] == "publication_succeeded"
            for row in events
        ) == 1
        offered_turns = [
            row["payload"]["turn"]
            for row in events
            if row["event"] == "turn_offered"
        ]
        assert [turn["phase"] for turn in offered_turns] == [
            "initial_materialization",
            "retry_materialization",
        ]
        assert offered_turns[0]["canonical_slice"] == (
            offered_turns[1]["canonical_slice"]
        )
        assert offered_turns[0]["canonical_slice"] == (
            header["materialization_slice"]
        )
        retry_queued = next(
            row
            for row in events
            if row["event"] == "retry_queued"
        )
        assert retry_queued["payload"]["rejected_submission_ordinal"] == 1
        assert retry_queued["payload"]["next_submission_ordinal"] == 2
        assert retry_queued["payload"]["turn"] == offered_turns[1]
        joined = next(
            row
            for row in events
            if row["event"] == "join_succeeded"
        )
        assert joined["payload"]["natural_shutdown_proof"] == {
            "disposition": "natural_exit",
            "return_code": 0,
            "pane_absent": True,
            "server_absent": True,
            "proof_complete": True,
        }
        ingress = next(
            row
            for row in events
            if row["event"] == "ingress_shutdown_finished"
        )
        assert ingress["payload"][
            "endpoint_zero_survivor_proven"
        ] is True

        state = manager._read_state_from_disk().to_dict()
        evidence = _published_evidence(manager, state)
        assert evidence["schema"] == (
            "workflow_prompt_fragment_snapshot.functional.v3"
        )
        identity = evidence["prompt_attempt_identity"]
        assert identity["schema_version"] == (
            "workflow_prompt_attempt_identity.v2"
        )
        assert "final_prompt" not in identity
        assert identity["canonical_composed"] == header["canonical_composed"]
        assert [
            row["phase"]
            for row in identity["actual_deliveries"]
        ] == [
            "task",
            "initial_materialization",
            "retry_materialization",
        ]
        report = project_prompt_context_v2(
            state,
            manager.run_root,
        )
        [attempt] = report["attempts"]
        assert attempt["record_status"] == "snapshot"
        assert attempt["identity"]["identity_version"] == (
            "workflow_prompt_attempt_identity.v2"
        )
        assert attempt["identity"]["legacy_final_prompt_sha256"] is None
        assert attempt["identity"]["actual_deliveries"] == (
            identity["actual_deliveries"]
        )
        assert adapter.submit_socket_path is not None
        assert adapter.submit_socket_path.parent == Path("/tmp")
        assert not adapter.submit_socket_path.exists()
    finally:
        temporary.cleanup()
        assert not workspace.exists()
