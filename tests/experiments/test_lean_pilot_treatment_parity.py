from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from orchestrator.contracts import output_contract as output_contract_module
from orchestrator.demo.evaluators.nanobragg_entrypoint import (
    evaluate_workspace as evaluate_nanobragg_workspace,
)
from orchestrator.experiments import canonical_sha256
from orchestrator.providers import (
    CallPolicyBinding,
    InputMode,
    ProviderExecutor,
    ProviderRegistry,
    ProviderTemplate,
)
from orchestrator.state import StateManager
from orchestrator.workflow import executor as workflow_executor_module
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    workflow_context,
    workflow_runtime_input_contracts,
)
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.build import (
    load_frontend_initialization_configuration,
)
from orchestrator.workflow_lisp.command_boundaries import (
    build_command_boundary_environment,
)
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


ROOT = Path(__file__).resolve().parents[2]
COORDINATOR_SCRIPT = ROOT / "scripts" / "experiments" / "conventional_coordinator.py"
ORC_WORKFLOW = (
    ROOT / "workflows" / "experiments" / "repository_task_pilot" / "task_loop.orc"
)
PROMPT_ROOT = ORC_WORKFLOW.parent / "prompts"
SCRIPTED_PROVIDER = (
    ROOT
    / "tests"
    / "experiments"
    / "fixtures"
    / "lean_pilot"
    / "scripted_provider.py"
)
CONTROL_ROOT = ROOT / "experiments" / "orc_effectiveness" / "lean_pilot" / "control"
TREATMENT_ROOT = (
    ROOT / "experiments" / "orc_effectiveness" / "lean_pilot" / "treatments"
)
A1_SEED_ROOT = ROOT / "examples" / "demo_task_nanobragg_entrypoint_port"
ENVIRONMENT_IDENTITY = (
    "sha256:0412722e0436c61866b7f0841f09baf8803853f41f4eb1192561a36437b317ca"
)
PROSPECTIVE_PROVIDER_POLICY = {
    "family": "codex-cli",
    "model": "gpt-5.5",
    "reasoning_effort": "high",
    "tool_policy": "codex_unrestricted_workspace",
    "timeout_milliseconds": 1_800_000,
    "currency": "USD",
}
EXPECTED_PROVIDER_POLICY_DIGEST = (
    "sha256:f6894af0098ad618ceaf74d6e46a76ab0519549d15f31f8b8685e40862bd0b25"
)
LAUNCHER_ENVIRONMENT = {
    "PATH": (
        "/home/ollie/.nvm/versions/node/v20.19.4/bin:"
        "/home/ollie/miniconda3/bin:/usr/local/bin:/usr/bin:/bin"
    ),
    "PYTHONUNBUFFERED": "1",
}
CONTROLLER_CREDENTIAL_ENVIRONMENT = {
    "CODEX_HOME": "/home/ollie/.codex",
}
FLAT_APPARATUS_ASSETS = (
    (COORDINATOR_SCRIPT, "treatment_driver.py"),
    (ORC_WORKFLOW, "task_loop.orc"),
    (PROMPT_ROOT / "discover.md", "prompts/discover.md"),
    (PROMPT_ROOT / "plan.md", "prompts/plan.md"),
    (PROMPT_ROOT / "review_plan.md", "prompts/review_plan.md"),
    (PROMPT_ROOT / "revise_plan.md", "prompts/revise_plan.md"),
    (PROMPT_ROOT / "implement.md", "prompts/implement.md"),
    (
        PROMPT_ROOT / "review_implementation.md",
        "prompts/review_implementation.md",
    ),
    (PROMPT_ROOT / "fix_implementation.md", "prompts/fix_implementation.md"),
    (CONTROL_ROOT / "providers.json", "providers.json"),
    (CONTROL_ROOT / "prompts.json", "prompts.json"),
    (CONTROL_ROOT / "commands.json", "commands.json"),
    (CONTROL_ROOT / "runtime-control.json", "runtime-control.json"),
    (
        ROOT
        / "experiments"
        / "orc_effectiveness"
        / "lean_pilot"
        / "tasks"
        / "a1.md",
        "task.md",
    ),
    (TREATMENT_ROOT / "direct.json", "treatments/direct.json"),
    (TREATMENT_ROOT / "coordinator.json", "treatments/coordinator.json"),
    (TREATMENT_ROOT / "orc.json", "treatments/orc.json"),
)
PHASES = (
    "discover",
    "plan",
    "review_plan",
    "revise_plan",
    "implement",
    "review_implementation",
    "fix_implementation",
)
SYSTEM_MESSAGE = "Act as the repository-task role named by this request."
MODEL = "fixture-model"
EFFORT = "fixture-effort"
TOOL_POLICY = "workspace-edit-and-test"
TASK_TEXT = "Implement the deterministic lean-pilot fixture task.\n"

PARITY_FIELDS = (
    "phase_names",
    "provider_requests",
    "result_validation_outcomes",
    "visible_check_events",
    "product_manifest_guard_events",
    "provider_boundary_events",
    "provider_call_count",
    "terminal_outcome",
)


@dataclass(frozen=True)
class RouteContract:
    name: str
    phases: tuple[str, ...]
    provider_call_count: int
    terminal_outcome: str


@dataclass
class _WorkspaceBoundaryTrace:
    prepared: list[dict[str, Any]] = field(default_factory=list)
    executed_invocation_ids: list[int] = field(default_factory=list)
    validated_result_kinds: list[str] = field(default_factory=list)


class _PublicBoundaryTrace:
    """Test-owned observations at the public adapter/validation boundaries."""

    def __init__(self) -> None:
        self._workspaces: dict[Path, _WorkspaceBoundaryTrace] = {}
        self._tokens_by_invocation_id: dict[int, str] = {}
        self._providers_by_workspace: dict[
            Path,
            tuple[ProviderTemplate, ...],
        ] = {}

    def _for(self, workspace: Path) -> _WorkspaceBoundaryTrace:
        return self._workspaces.setdefault(
            workspace.resolve(),
            _WorkspaceBoundaryTrace(),
        )

    def record_prepared(
        self,
        *,
        workspace: Path,
        provider_name: str,
        invocation: Any,
        session_request: Any,
    ) -> None:
        if not provider_name.startswith("lean-pilot-scripted-"):
            return
        trace = self._for(workspace)
        phase = provider_name.removeprefix("lean-pilot-scripted-").replace("-", "_")
        token = f"public-provider-invocation-{len(trace.prepared) + 1}"
        invocation_id = id(invocation)
        self._tokens_by_invocation_id[invocation_id] = token
        trace.prepared.append(
            {
                "phase": phase,
                "invocation_id": invocation_id,
                "session_identity": token,
                "session_request": session_request,
            }
        )

    def record_executed(self, *, workspace: Path, invocation: Any) -> None:
        invocation_id = id(invocation)
        if invocation_id in self._tokens_by_invocation_id:
            self._for(workspace).executed_invocation_ids.append(invocation_id)

    def record_validated(self, *, workspace: Path, kind: str) -> None:
        self._for(workspace).validated_result_kinds.append(kind)

    def for_workspace(self, workspace: Path) -> _WorkspaceBoundaryTrace:
        return self._for(workspace)

    def install_workspace_providers(
        self,
        workspace: Path,
        providers: Sequence[ProviderTemplate],
    ) -> None:
        self._providers_by_workspace[workspace.resolve()] = tuple(providers)

    def providers_for_workspace(
        self,
        workspace: Path,
    ) -> tuple[ProviderTemplate, ...]:
        return self._providers_by_workspace.get(workspace.resolve(), ())


ROUTES = (
    RouteContract(
        "immediate_approval",
        ("discover", "plan", "review_plan", "implement", "review_implementation"),
        5,
        "COMPLETED",
    ),
    RouteContract(
        "plan_revision",
        (
            "discover",
            "plan",
            "review_plan",
            "revise_plan",
            "review_plan",
            "implement",
            "review_implementation",
        ),
        7,
        "COMPLETED",
    ),
    RouteContract(
        "implementation_fix",
        (
            "discover",
            "plan",
            "review_plan",
            "implement",
            "review_implementation",
            "fix_implementation",
            "review_implementation",
        ),
        7,
        "COMPLETED",
    ),
    RouteContract(
        "both_corrections",
        (
            "discover",
            "plan",
            "review_plan",
            "revise_plan",
            "review_plan",
            "implement",
            "review_implementation",
            "fix_implementation",
            "review_implementation",
        ),
        9,
        "COMPLETED",
    ),
    RouteContract(
        "plan_blocked",
        ("discover", "plan", "review_plan"),
        3,
        "BLOCKED",
    ),
    RouteContract(
        "implementation_blocked",
        ("discover", "plan", "review_plan", "implement", "review_implementation"),
        5,
        "BLOCKED",
    ),
    RouteContract(
        "second_plan_review_revises",
        ("discover", "plan", "review_plan", "revise_plan", "review_plan"),
        5,
        "EXHAUSTED",
    ),
    RouteContract(
        "judgment_mutates_product",
        ("discover", "plan", "review_plan", "implement", "review_implementation"),
        5,
        "PROTOCOL_FAILURE",
    ),
    RouteContract(
        "checks_fail_after_fix",
        (
            "discover",
            "plan",
            "review_plan",
            "implement",
            "review_implementation",
            "fix_implementation",
            "review_implementation",
        ),
        7,
        "EXHAUSTED",
    ),
)


def _is_provider_record_contract(contract: Mapping[str, Any]) -> bool:
    fields = contract.get("fields")
    if not isinstance(fields, list):
        return False
    names = {
        field.get("name")
        for field in fields
        if isinstance(field, Mapping)
    }
    return bool(
        names
        & {
            "relevant_paths",
            "constraints",
            "risks",
            "steps",
            "acceptance_checks",
            "summary",
            "changed_paths",
            "checks_summary",
            "decision",
        }
    )


@pytest.fixture
def public_boundary_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> _PublicBoundaryTrace:
    trace = _PublicBoundaryTrace()
    original_prepare = ProviderExecutor.prepare_invocation
    original_execute = ProviderExecutor.execute
    original_workflow_init = WorkflowExecutor.__init__
    original_validate_record = output_contract_module.validate_output_bundle
    original_validate_variant = (
        output_contract_module.validate_variant_output_bundle
    )
    coordinator_module = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )

    def prepare(self: ProviderExecutor, *args: Any, **kwargs: Any) -> Any:
        result = original_prepare(self, *args, **kwargs)
        invocation, error = result
        provider_name = (
            kwargs.get("provider_name")
            if "provider_name" in kwargs
            else args[0]
        )
        session_request = kwargs.get("session_request")
        if invocation is not None and error is None:
            trace.record_prepared(
                workspace=self.workspace,
                provider_name=provider_name,
                invocation=invocation,
                session_request=session_request,
            )
        return result

    def execute(
        self: ProviderExecutor,
        invocation: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        result = original_execute(self, invocation, *args, **kwargs)
        trace.record_executed(workspace=self.workspace, invocation=invocation)
        return result

    def validate_record(
        contract: dict[str, Any],
        workspace: Path,
    ) -> dict[str, Any]:
        result = original_validate_record(
            contract,
            workspace,
        )
        if _is_provider_record_contract(contract):
            trace.record_validated(workspace=workspace, kind="record")
        return result

    def validate_variant(
        contract: dict[str, Any],
        workspace: Path,
    ) -> dict[str, Any]:
        result = original_validate_variant(
            contract,
            workspace,
        )
        trace.record_validated(workspace=workspace, kind="variant")
        return result

    def workflow_init(self: WorkflowExecutor, *args: Any, **kwargs: Any) -> None:
        original_workflow_init(self, *args, **kwargs)
        for provider in trace.providers_for_workspace(self.workspace):
            self.provider_registry.register(provider)

    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare)
    monkeypatch.setattr(ProviderExecutor, "execute", execute)
    monkeypatch.setattr(WorkflowExecutor, "__init__", workflow_init)
    monkeypatch.setattr(
        output_contract_module,
        "validate_output_bundle",
        validate_record,
    )
    monkeypatch.setattr(
        output_contract_module,
        "validate_variant_output_bundle",
        validate_variant,
    )
    monkeypatch.setattr(
        workflow_executor_module,
        "validate_output_bundle",
        validate_record,
    )
    monkeypatch.setattr(
        workflow_executor_module,
        "validate_variant_output_bundle",
        validate_variant,
    )
    monkeypatch.setattr(
        coordinator_module,
        "validate_output_bundle",
        validate_record,
    )
    return trace


def _without_transport_correlation_ids(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"correlation_id", "request_id", "transport_request_id"}:
                continue
            if key == "typed_result_schema" and isinstance(item, str):
                normalized[key] = "\n".join(
                    (
                        "- path: <runtime-output-bundle>"
                        if line.startswith("- path: ")
                        else line
                    )
                    for line in item.splitlines()
                )
                continue
            normalized[key] = _without_transport_correlation_ids(item)
        return normalized
    if isinstance(value, list):
        return [_without_transport_correlation_ids(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_without_transport_correlation_ids(item) for item in value)
    return value


def _assert_fresh_sessions(observation: Mapping[str, Any]) -> None:
    sessions = observation["provider_session_identities"]
    assert isinstance(sessions, Sequence) and not isinstance(sessions, (str, bytes))
    assert len(sessions) == observation["provider_call_count"]
    assert all(isinstance(item, str) and item for item in sessions)
    assert len(set(sessions)) == len(sessions)
    assert observation["undeclared_conversational_carry_over"] is False


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _stage_flat_apparatus(destination: Path) -> None:
    destination.mkdir()
    for source, relative_path in FLAT_APPARATUS_ASSETS:
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        assert target.read_bytes() == source.read_bytes()
    staged_files = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }
    assert staged_files == {
        relative_path for _source, relative_path in FLAT_APPARATUS_ASSETS
    }


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    return value


def _fixture_provider_registry(
    *,
    route: str,
    state_path: Path,
    request_log: Path,
) -> tuple[ProviderRegistry, dict[str, str]]:
    registry = ProviderRegistry()
    providers: dict[str, str] = {}
    for phase in PHASES:
        provider_name = f"lean-pilot-scripted-{phase.replace('_', '-')}"
        registry.register(
            ProviderTemplate(
                name=provider_name,
                command=[
                    sys.executable,
                    str(SCRIPTED_PROVIDER),
                    "--phase",
                    phase,
                    "--route",
                    route,
                    "--state",
                    str(state_path),
                    "--request-log",
                    str(request_log),
                    "--system-message",
                    SYSTEM_MESSAGE,
                    "--tool-policy",
                    TOOL_POLICY,
                    "--model",
                    "${model}",
                    "--effort",
                    "${effort}",
                ],
                defaults={},
                input_mode=InputMode.STDIN,
                call_policy_bindings={
                    "model": CallPolicyBinding(target_param="model"),
                    "effort": CallPolicyBinding(target_param="effort"),
                },
            )
        )
        providers[phase] = provider_name
    return registry, providers


def _prepare_workspace(workspace: Path, route: str) -> tuple[Path, Path, Path]:
    runtime = workspace / ".pilot" / "runtime"
    runtime.mkdir(parents=True)
    task_path = runtime / "task.md"
    task_path.write_text(TASK_TEXT, encoding="utf-8")
    event_log = runtime / "controller-events.jsonl"
    control_path = runtime / "control.json"
    visible_exit = 1 if route == "checks_fail_after_fix" else 0
    control_path.write_text(
        json.dumps(
            {
                "event_log": event_log.relative_to(workspace).as_posix(),
                "product_exclusions": [
                    ".orchestrate",
                    ".pilot/runtime",
                    "logs",
                ],
                "visible_check": {
                    "argv": [
                        sys.executable,
                        "-c",
                        f"raise SystemExit({visible_exit})",
                    ],
                    "timeout_seconds": 10,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    script_copy = workspace / "scripts" / "experiments" / COORDINATOR_SCRIPT.name
    script_copy.parent.mkdir(parents=True)
    shutil.copy2(COORDINATOR_SCRIPT, script_copy)
    return task_path, control_path, event_log


def _observation_from_evidence(
    *,
    request_log: Path,
    event_log: Path,
    terminal_outcome: str,
    boundary_trace: _PublicBoundaryTrace,
    workspace: Path,
) -> dict[str, Any]:
    requests = _read_jsonl(request_log)
    events = _read_jsonl(event_log)
    phases = [row["phase"] for row in requests]
    for row in requests:
        row.pop("session_identity")
        row.pop("conversational_parent_session")
    boundary = boundary_trace.for_workspace(workspace)
    prepared = boundary.prepared
    executed = boundary.executed_invocation_ids
    assert [row["phase"] for row in prepared] == phases
    assert executed == [row["invocation_id"] for row in prepared]
    assert len(boundary.validated_result_kinds) == len(phases)
    sessions = [row["session_identity"] for row in prepared]
    undeclared_carry = any(
        row["session_request"] is not None for row in prepared
    )
    return {
        "phase_names": phases,
        "provider_requests": requests,
        "result_validation_outcomes": [
            {
                "phase": phase,
                "outcome": "VALID",
                "contract_kind": contract_kind,
            }
            for phase, contract_kind in zip(
                phases,
                boundary.validated_result_kinds,
                strict=True,
            )
        ],
        "visible_check_events": [
            event for event in events if event["event_kind"] == "visible_check"
        ],
        "product_manifest_guard_events": [
            event for event in events if event["event_kind"] == "product_manifest_guard"
        ],
        "provider_boundary_events": [
            {
                "phase": row["phase"],
                "prepared": True,
                "executed": True,
                "fresh_session": row["session_request"] is None,
            }
            for row in prepared
        ],
        "provider_call_count": len(requests),
        "terminal_outcome": terminal_outcome,
        "provider_session_identities": sessions,
        "undeclared_conversational_carry_over": undeclared_carry,
    }


def _prompt_externs() -> dict[str, dict[str, str]]:
    return {
        f"prompts.repository-task.{phase.replace('_', '-')}": {
            "asset_file": f"prompts/{phase}.md"
        }
        for phase in PHASES
    }


def _command_boundaries() -> dict[str, ExternalToolBinding]:
    return {
        "pilot_product_manifest": ExternalToolBinding(
            name="pilot_product_manifest",
            stable_command=("python",),
        ),
        "pilot_visible_check": ExternalToolBinding(
            name="pilot_visible_check",
            stable_command=("python",),
        ),
    }


def _run_orc(
    *,
    route: RouteContract,
    workspace: Path,
    registry: ProviderRegistry,
    provider_names: Mapping[str, str],
    task_path: Path,
    control_path: Path,
    request_log: Path,
    event_log: Path,
    boundary_trace: _PublicBoundaryTrace,
    workflow_path: Path = ORC_WORKFLOW,
    controller_script: Path = COORDINATOR_SCRIPT,
    prompt_externs: Mapping[str, object] | None = None,
    command_boundaries: Mapping[str, ExternalToolBinding] | None = None,
) -> dict[str, Any]:
    compiled = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(workflow_path.parent,),
        provider_externs={
            f"providers.repository-task.{phase.replace('_', '-')}": provider_names[
                phase
            ]
            for phase in PHASES
        },
        prompt_externs=prompt_externs or _prompt_externs(),
        command_boundaries=command_boundaries or _command_boundaries(),
        validate_shared=True,
        workspace_root=workspace,
    )
    boundary_trace.install_workspace_providers(
        workspace,
        tuple(
            provider
            for provider_name in provider_names.values()
            if (provider := registry.get(provider_name)) is not None
        ),
    )
    bundle = next(
        candidate
        for name, candidate in compiled.validated_bundles_by_name.items()
        if name.endswith("::run-task") or name == "run-task"
    )
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    bound_inputs = bind_workflow_inputs(
        {
            name: contract
            for name, contract in runtime_inputs.items()
            if not name.startswith("__write_root__")
        },
        {
            "task_path": task_path.relative_to(workspace).as_posix(),
            "control_path": control_path.relative_to(workspace).as_posix(),
            "controller_script": controller_script.resolve().as_posix(),
            "model": MODEL,
            "effort": EFFORT,
        },
        workspace,
    )
    state_manager = StateManager(workspace=workspace, run_id=f"parity-{route.name}")
    state_manager.initialize(
        workflow_path.as_posix(),
        context=_plain_value(workflow_context(bundle)),
        bound_inputs=bound_inputs,
    )
    executor = WorkflowExecutor(
        bundle,
        workspace,
        state_manager,
        max_retries=0,
        retry_delay_ms=0,
        provider_observation_enabled=False,
    )
    for provider_name in provider_names.values():
        provider = registry.get(provider_name)
        assert provider is not None
        executor.provider_registry.register(provider)
    state = executor.execute(on_error="stop")
    assert state["status"] == "completed", state.get("error")
    outputs = state["workflow_outputs"]
    terminal = (
        outputs.get("__result__")
        or outputs.get("return__variant")
        or outputs.get("variant")
    )
    assert isinstance(terminal, str), outputs
    return _observation_from_evidence(
        request_log=request_log,
        event_log=event_log,
        terminal_outcome=terminal,
        boundary_trace=boundary_trace,
        workspace=workspace,
    )


def _run_coordinator(
    *,
    coordinator: Any,
    workspace: Path,
    registry: ProviderRegistry,
    provider_names: Mapping[str, str],
    task_path: Path,
    control_path: Path,
    request_log: Path,
    event_log: Path,
    boundary_trace: _PublicBoundaryTrace,
) -> Mapping[str, Any]:
    config = coordinator.PilotTreatmentConfig(
        workspace=workspace,
        task_path=task_path.relative_to(workspace).as_posix(),
        control_path=control_path.relative_to(workspace).as_posix(),
        prompt_paths={
            phase: f"prompts/{phase}.md"
            for phase in PHASES
        },
        prompt_workflow_path=ORC_WORKFLOW,
        provider_names=dict(provider_names),
        provider_registry=registry,
        model=MODEL,
        effort=EFFORT,
        timeout_seconds=1_800,
        controller_command=(
            "python",
            COORDINATOR_SCRIPT.resolve().as_posix(),
        ),
    )
    result = coordinator.run_task(config)
    return _observation_from_evidence(
        request_log=request_log,
        event_log=event_log,
        terminal_outcome=result.terminal_outcome,
        boundary_trace=boundary_trace,
        workspace=workspace,
    )


def test_frozen_launch_configs_use_standard_manifests_and_staged_assets(
    tmp_path: Path,
) -> None:
    provider_policy_digest = canonical_sha256(PROSPECTIVE_PROVIDER_POLICY)
    assert provider_policy_digest == EXPECTED_PROVIDER_POLICY_DIGEST

    configuration = load_frontend_initialization_configuration(
        workspace_root=ROOT,
        source_roots=(ORC_WORKFLOW.parent,),
        provider_externs_path=CONTROL_ROOT / "providers.json",
        prompt_externs_path=CONTROL_ROOT / "prompts.json",
        command_boundaries_path=CONTROL_ROOT / "commands.json",
    )
    build_command_boundary_environment(configuration.command_boundaries)

    provider_keys = {
        f"providers.repository-task.{phase.replace('_', '-')}"
        for phase in PHASES
    }
    assert set(configuration.provider_externs) == provider_keys
    assert set(configuration.provider_externs.values()) == {
        "codex_unrestricted_workspace"
    }
    assert configuration.prompt_externs == {
        f"prompts.repository-task.{phase.replace('_', '-')}": {
            "asset_file": f"prompts/{phase}.md"
        }
        for phase in PHASES
    }
    assert set(configuration.command_boundaries) == {
        "pilot_product_manifest",
        "pilot_visible_check",
    }
    assert all(
        binding.stable_command == ("python",)
        for binding in configuration.command_boundaries.values()
    )

    forbidden_treatment_token = re.compile(
        r"(?<![A-Za-z0-9])(direct|coordinator|orc)(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    for treatment in ("direct", "coordinator", "orc"):
        config = json.loads(
            (TREATMENT_ROOT / f"{treatment}.json").read_text(encoding="utf-8")
        )
        assert set(config) == {
            "argv",
            "environment",
            "environment_identity",
            "provider_policy_digest",
            "timeout_milliseconds",
        }
        assert config["environment"] == LAUNCHER_ENVIRONMENT
        assert "CODEX_HOME" not in config["environment"]
        assert config["environment_identity"] == ENVIRONMENT_IDENTITY
        assert config["provider_policy_digest"] == provider_policy_digest
        assert config["timeout_milliseconds"] == 18_000_000
        maximum_calls = 1 if treatment == "direct" else 9
        maximum_visible_checks = 0 if treatment == "direct" else 2
        assert config["timeout_milliseconds"] > (
            maximum_calls * 1_800_000
            + maximum_visible_checks * 300_000
        )
        argv = config["argv"]
        assert argv[:2] == [
            "python",
            "{apparatus_root}/treatment_driver.py",
        ]
        assert {
            "{workspace}",
            "{task_path}",
            "{result_path}",
            "{provider_config}",
            "{prompt_config}",
            "{command_config}",
            "{apparatus_root}",
        } <= set(argv)
        assert not any(forbidden_treatment_token.search(token) for token in argv)

    staged_root = tmp_path / "apparatus"
    staged_root.mkdir()
    shutil.copy2(ORC_WORKFLOW, staged_root / "task_loop.orc")
    shutil.copy2(COORDINATOR_SCRIPT, staged_root / "treatment_driver.py")
    shutil.copytree(PROMPT_ROOT, staged_root / "prompts")
    shutil.copy2(CONTROL_ROOT / "providers.json", staged_root / "providers.json")
    shutil.copy2(CONTROL_ROOT / "prompts.json", staged_root / "prompts.json")
    shutil.copy2(CONTROL_ROOT / "commands.json", staged_root / "commands.json")
    assert (
        staged_root.joinpath("treatment_driver.py").read_bytes()
        == COORDINATOR_SCRIPT.read_bytes()
    )

    staged_configuration = load_frontend_initialization_configuration(
        workspace_root=tmp_path,
        source_roots=(staged_root,),
        provider_externs_path=staged_root / "providers.json",
        prompt_externs_path=staged_root / "prompts.json",
        command_boundaries_path=staged_root / "commands.json",
    )
    compiled = compile_stage3_entrypoint(
        staged_root / "task_loop.orc",
        source_roots=(staged_root,),
        provider_externs=staged_configuration.provider_externs,
        prompt_externs=staged_configuration.prompt_externs,
        command_boundaries=staged_configuration.command_boundaries,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    assert any(
        name.endswith("::run-task") or name == "run-task"
        for name in compiled.validated_bundles_by_name
    )


def test_staged_workflow_compiles_from_candidate_under_closed_environment(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "candidate"
    shutil.copytree(
        A1_SEED_ROOT,
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    staged_root = tmp_path / "apparatus"
    staged_root.mkdir()
    shutil.copy2(ORC_WORKFLOW, staged_root / "task_loop.orc")
    shutil.copytree(PROMPT_ROOT, staged_root / "prompts")
    for name in ("providers.json", "prompts.json", "commands.json"):
        shutil.copy2(CONTROL_ROOT / name, staged_root / name)

    home = tmp_path / "home"
    temporary = tmp_path / "tmp"
    home.mkdir()
    temporary.mkdir()
    environment = {
        **LAUNCHER_ENVIRONMENT,
        **CONTROLLER_CREDENTIAL_ENVIRONMENT,
        "HOME": str(home),
        "TMPDIR": str(temporary),
    }
    completed = subprocess.run(
        [
            "python",
            "-m",
            "orchestrator",
            "compile",
            str(staged_root / "task_loop.orc"),
            "--source-root",
            str(staged_root),
            "--entry-workflow",
            "task_loop::run-task",
            "--provider-externs-file",
            str(staged_root / "providers.json"),
            "--prompt-externs-file",
            str(staged_root / "prompts.json"),
            "--command-boundaries-file",
            str(staged_root / "commands.json"),
        ],
        cwd=workspace,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")


@pytest.mark.parametrize(
    ("field_names", "product_exists", "expected_phase"),
    (
        (("relevant_paths", "constraints", "risks"), False, "discover"),
        (("steps", "acceptance_checks"), False, "plan"),
        (
            ("decision", "rationale", "findings", "reason"),
            False,
            "review_plan",
        ),
        (
            ("summary", "changed_paths", "checks_summary"),
            False,
            "implement",
        ),
        (
            ("decision", "rationale", "findings", "reason"),
            True,
            "review_implementation",
        ),
    ),
)
def test_test_provider_routes_by_output_contract_not_prompt_prose(
    tmp_path: Path,
    field_names: tuple[str, ...],
    product_exists: bool,
    expected_phase: str,
) -> None:
    workspace = tmp_path / "candidate"
    workspace.mkdir()
    if product_exists:
        (workspace / "fixture-product.txt").write_text(
            "existing implementation\n",
            encoding="utf-8",
        )
    shim_path = tmp_path / "codex"
    shutil.copy2(SCRIPTED_PROVIDER, shim_path)
    shim_path.chmod(0o755)
    bundle_path = tmp_path / "output.json"
    prompt = "\n".join(
        (
            "This role prose is intentionally unrelated to any phase name.",
            "",
            "## Output Contract",
            *(f"- name: {name}" for name in field_names),
            "",
        )
    )

    completed = subprocess.run(
        [str(shim_path)],
        cwd=workspace,
        env={
            "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(bundle_path),
            "PATH": os.environ["PATH"],
        },
        input=prompt.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert json.loads(completed.stdout) == {"fixture_phase": expected_phase}
    assert bundle_path.is_file()


@pytest.mark.parametrize(
    ("treatment", "expected_provider_calls"),
    (
        ("direct", 1),
        ("coordinator", 5),
        ("orc", 5),
    ),
)
def test_frozen_treatment_argv_run_through_real_staged_launcher(
    tmp_path: Path,
    treatment: str,
    expected_provider_calls: int,
) -> None:
    apparatus_root = tmp_path / "apparatus"
    _stage_flat_apparatus(apparatus_root)
    workspace = tmp_path / "candidate"
    shutil.copytree(
        A1_SEED_ROOT,
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    result_path = workspace / ".pilot" / "runtime" / "raw-result.json"
    config = json.loads(
        (apparatus_root / "treatments" / f"{treatment}.json").read_text(
            encoding="utf-8"
        )
    )
    replacements = {
        "workspace": str(workspace),
        "task_path": str(apparatus_root / "task.md"),
        "result_path": str(result_path),
        "provider_config": str(apparatus_root / "providers.json"),
        "prompt_config": str(apparatus_root / "prompts.json"),
        "command_config": str(apparatus_root / "commands.json"),
        "apparatus_root": str(apparatus_root),
    }
    argv = [
        token.format_map(replacements)
        for token in config["argv"]
    ]

    shim_root = tmp_path / "test-provider-bin"
    shim_root.mkdir()
    shim_path = shim_root / "codex"
    shutil.copy2(SCRIPTED_PROVIDER, shim_path)
    shim_path.chmod(0o755)
    home = tmp_path / "home"
    temporary = tmp_path / "tmp"
    home.mkdir()
    temporary.mkdir()
    environment = {
        **config["environment"],
        **CONTROLLER_CREDENTIAL_ENVIRONMENT,
        "PATH": f"{shim_root}:{config['environment']['PATH']}",
        "HOME": str(home),
        "TMPDIR": str(temporary),
    }
    assert {
        key: value
        for key, value in environment.items()
        if key not in {"HOME", "TMPDIR", "PATH"}
    } == {
        **{
            key: value
            for key, value in config["environment"].items()
            if key != "PATH"
        },
        **CONTROLLER_CREDENTIAL_ENVIRONMENT,
    }
    assert environment["PATH"] == (
        f"{shim_root}:{LAUNCHER_ENVIRONMENT['PATH']}"
    )
    assert set(environment) == {
        *LAUNCHER_ENVIRONMENT,
        *CONTROLLER_CREDENTIAL_ENVIRONMENT,
        "HOME",
        "TMPDIR",
    }

    completed = subprocess.run(
        argv,
        cwd=workspace,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert json.loads(result_path.read_text(encoding="utf-8")) == {
        "provider_call_count": expected_provider_calls,
        "terminal_outcome": "COMPLETED",
        "token_counts": "UNKNOWN",
        "cost": "UNKNOWN",
    }
    assert (workspace / "fixture-product.txt").is_file()

    runtime_control = json.loads(
        (apparatus_root / "runtime-control.json").read_text(encoding="utf-8")
    )
    visible = subprocess.run(
        runtime_control["visible_check"]["argv"],
        cwd=workspace,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=runtime_control["visible_check"]["timeout_seconds"],
        check=False,
    )
    assert visible.returncode == 0, visible.stderr.decode(errors="replace")


def test_single_treatment_invokes_public_provider_boundary_exactly_once(
    tmp_path: Path,
    public_boundary_trace: _PublicBoundaryTrace,
) -> None:
    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    task_path = workspace / "task.md"
    task_path.write_text(TASK_TEXT, encoding="utf-8")
    provider_name = "lean-pilot-scripted-implement"
    registry = ProviderRegistry()
    registry.register(
        ProviderTemplate(
            name=provider_name,
            command=[
                sys.executable,
                "-c",
                "import sys; sys.stdin.buffer.read()",
                "${model}",
                "${effort}",
            ],
            defaults={},
            input_mode=InputMode.STDIN,
            call_policy_bindings={
                "model": CallPolicyBinding(target_param="model"),
                "effort": CallPolicyBinding(target_param="effort"),
            },
        )
    )

    coordinator._run_single_provider(
        workspace=workspace,
        task_path=task_path,
        provider_registry=registry,
        provider_name=provider_name,
        model=MODEL,
        effort=EFFORT,
        timeout_seconds=1_800,
    )

    boundary = public_boundary_trace.for_workspace(workspace)
    assert len(boundary.prepared) == 1
    assert boundary.executed_invocation_ids == [
        boundary.prepared[0]["invocation_id"]
    ]
    assert boundary.prepared[0]["session_request"] is None


@pytest.mark.parametrize(
    "terminal_outcome",
    ("COMPLETED", "BLOCKED", "EXHAUSTED", "PROTOCOL_FAILURE"),
)
def test_raw_result_preserves_the_strict_semantic_terminal(
    tmp_path: Path,
    terminal_outcome: str,
) -> None:
    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )
    result_path = tmp_path / "raw-result.json"

    coordinator._write_raw_result(
        result_path,
        provider_call_count=5,
        terminal_outcome=terminal_outcome,
    )

    assert json.loads(result_path.read_text(encoding="utf-8")) == {
        "provider_call_count": 5,
        "terminal_outcome": terminal_outcome,
        "token_counts": "UNKNOWN",
        "cost": "UNKNOWN",
    }


def test_raw_result_rejects_an_uncontrolled_semantic_terminal(
    tmp_path: Path,
) -> None:
    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )

    with pytest.raises(
        coordinator.PilotTreatmentError,
        match="semantic terminal outcome",
    ):
        coordinator._write_raw_result(
            tmp_path / "raw-result.json",
            provider_call_count=5,
            terminal_outcome="UNKNOWN",
        )


@pytest.mark.parametrize(
    "terminal_outcome",
    ("COMPLETED", "BLOCKED", "EXHAUSTED", "PROTOCOL_FAILURE"),
)
def test_workflow_state_parser_preserves_the_exact_semantic_terminal(
    tmp_path: Path,
    terminal_outcome: str,
) -> None:
    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )
    state_root = tmp_path / "state"
    run_root = state_root / "run-1"
    run_root.mkdir(parents=True)
    observation_root = run_root / "provider-observation"
    display_root = observation_root / "display"
    transcript_root = observation_root / "transcripts"
    display_root.mkdir(parents=True)
    transcript_root.mkdir()
    for ordinal in range(1, 6):
        stem = f"{ordinal:06d}-{'a' * 16}"
        (display_root / f"{stem}.display").write_bytes(b"")
        (transcript_root / f"{stem}.transcript").write_bytes(b"fixture\n")
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "workflow_outputs": {
                    "__result__": terminal_outcome,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert coordinator._workflow_treatment_result(state_root) == (
        5,
        terminal_outcome,
    )


@pytest.mark.parametrize(
    "workflow_outputs",
    (
        {},
        {"__result__": "UNKNOWN"},
        {"__result__": "BLOCKED", "variant": "COMPLETED"},
    ),
)
def test_workflow_state_parser_rejects_missing_unknown_or_ambiguous_terminals(
    tmp_path: Path,
    workflow_outputs: Mapping[str, str],
) -> None:
    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )
    state_root = tmp_path / "state"
    run_root = state_root / "run-1"
    run_root.mkdir(parents=True)
    display_root = run_root / "provider-observation" / "display"
    transcript_root = run_root / "provider-observation" / "transcripts"
    display_root.mkdir(parents=True)
    transcript_root.mkdir()
    stem = f"{1:06d}-{'a' * 16}"
    (display_root / f"{stem}.display").write_bytes(b"")
    (transcript_root / f"{stem}.transcript").write_bytes(b"fixture\n")
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "workflow_outputs": dict(workflow_outputs),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        coordinator.PilotTreatmentError,
        match="semantic terminal outcome",
    ):
        coordinator._workflow_treatment_result(state_root)


@pytest.mark.parametrize(
    ("display_stems", "transcript_stems"),
    (
        ((), ()),
        (("000001-aaaaaaaaaaaaaaaa",), ()),
        (
            (
                "000001-aaaaaaaaaaaaaaaa",
                "000003-bbbbbbbbbbbbbbbb",
            ),
            (
                "000001-aaaaaaaaaaaaaaaa",
                "000003-bbbbbbbbbbbbbbbb",
            ),
        ),
    ),
)
def test_workflow_state_parser_rejects_incomplete_call_observations(
    tmp_path: Path,
    display_stems: tuple[str, ...],
    transcript_stems: tuple[str, ...],
) -> None:
    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )
    state_root = tmp_path / "state"
    run_root = state_root / "run-1"
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "workflow_outputs": {"__result__": "COMPLETED"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    display_root = run_root / "provider-observation" / "display"
    transcript_root = run_root / "provider-observation" / "transcripts"
    display_root.mkdir(parents=True)
    transcript_root.mkdir()
    for stem in display_stems:
        (display_root / f"{stem}.display").write_bytes(b"")
    for stem in transcript_stems:
        (transcript_root / f"{stem}.transcript").write_bytes(b"fixture\n")

    with pytest.raises(
        coordinator.PilotTreatmentError,
        match="provider call accounting",
    ):
        coordinator._workflow_treatment_result(state_root)


@pytest.mark.parametrize(
    ("mode", "provider_call_count", "terminal_outcome"),
    (
        ("single", 1, "COMPLETED"),
        ("bounded", 3, "BLOCKED"),
        ("workflow", 5, "EXHAUSTED"),
    ),
)
def test_launcher_writes_each_treatments_semantic_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    provider_call_count: int,
    terminal_outcome: str,
) -> None:
    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    apparatus_root = tmp_path / "apparatus"
    apparatus_root.mkdir()
    shutil.copy2(COORDINATOR_SCRIPT, apparatus_root / "treatment_driver.py")
    shutil.copy2(ORC_WORKFLOW, apparatus_root / "task_loop.orc")
    shutil.copytree(PROMPT_ROOT, apparatus_root / "prompts")
    shutil.copy2(
        ROOT / "experiments" / "orc_effectiveness" / "lean_pilot" / "tasks" / "a1.md",
        apparatus_root / "task.md",
    )
    for name in (
        "providers.json",
        "prompts.json",
        "commands.json",
        "runtime-control.json",
    ):
        shutil.copy2(CONTROL_ROOT / name, apparatus_root / name)

    if mode == "single":
        monkeypatch.setattr(
            coordinator,
            "_run_single_provider",
            lambda **_kwargs: None,
        )
    elif mode == "bounded":
        phases = tuple(
            (phase, {})
            for phase in ("discover", "plan", "review_plan")
        )
        monkeypatch.setattr(
            coordinator,
            "run_task",
            lambda _config: coordinator.CoordinatorResult(
                terminal_outcome="BLOCKED",
                phase_results=phases,
            ),
        )
    else:
        monkeypatch.setattr(
            coordinator,
            "_run_workflow_treatment",
            lambda **_kwargs: (5, "EXHAUSTED"),
        )

    result_path = workspace / ".pilot" / "runtime" / "raw-result.json"
    monkeypatch.chdir(workspace)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(apparatus_root / "treatment_driver.py"),
            mode,
            "--workspace",
            str(workspace),
            "--task",
            str(apparatus_root / "task.md"),
            "--result-file",
            str(result_path),
            "--provider-config",
            str(apparatus_root / "providers.json"),
            "--prompt-config",
            str(apparatus_root / "prompts.json"),
            "--command-config",
            str(apparatus_root / "commands.json"),
            "--apparatus-root",
            str(apparatus_root),
            "--runtime-control",
            str(apparatus_root / "runtime-control.json"),
            "--model",
            "gpt-5.5",
            "--effort",
            "high",
            "--provider-timeout-seconds",
            "1800",
        ],
    )

    assert coordinator.main() == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["provider_call_count"] == provider_call_count
    assert result["terminal_outcome"] == terminal_outcome


def test_frozen_visible_check_runs_on_materialized_a1_seed(
    tmp_path: Path,
) -> None:
    control = json.loads(
        (CONTROL_ROOT / "runtime-control.json").read_text(encoding="utf-8")
    )
    assert control["visible_check"] == {
        "argv": [
            "python",
            "-m",
            "pytest",
            "-q",
            "tests/test_smoke_entrypoint.py",
        ],
        "timeout_seconds": 300,
    }
    workspace = tmp_path / "a1-seed"
    shutil.copytree(
        A1_SEED_ROOT,
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    completed = subprocess.run(
        control["visible_check"]["argv"],
        cwd=workspace,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=control["visible_check"]["timeout_seconds"],
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")

    hidden_result = evaluate_nanobragg_workspace(workspace)
    assert hidden_result["verdict"] == "FAIL"
    assert hidden_result["summary"]["hidden_tests_passed"] is False


def _expected_visible_check_count(route: RouteContract) -> int:
    if "implement" not in route.phases:
        return 0
    return 2 if "fix_implementation" in route.phases else 1


def _assert_request_and_control_evidence(
    observation: Mapping[str, Any],
    route: RouteContract,
) -> None:
    requests = observation["provider_requests"]
    assert len(requests) == route.provider_call_count
    for request in requests:
        assert request["system_message"]
        assert request["user_message"]
        assert request["tool_policy"]
        assert request["typed_result_schema"].startswith(
            ("## Output Contract", "## Variant Output Contract")
        )
        assert request["provider_parameters"] == {
            "model": MODEL,
            "effort": EFFORT,
        }

    validations = observation["result_validation_outcomes"]
    assert len(validations) == route.provider_call_count
    assert all(row["outcome"] == "VALID" for row in validations)
    assert all(
        row["contract_kind"] in {"record", "variant"} for row in validations
    )

    boundary_events = observation["provider_boundary_events"]
    assert len(boundary_events) == route.provider_call_count
    assert all(
        row["prepared"] and row["executed"] and row["fresh_session"]
        for row in boundary_events
    )

    judgment_phases = {
        "discover",
        "plan",
        "review_plan",
        "revise_plan",
        "review_implementation",
    }
    expected_guard_phases = [
        phase for phase in route.phases if phase in judgment_phases
    ]
    guards = observation["product_manifest_guard_events"]
    assert [row["phase"] for row in guards] == expected_guard_phases
    for guard in guards:
        assert set(guard) == {
            "event_kind",
            "phase",
            "before_digest",
            "after_digest",
            "mutation_disposition",
        }
        if route.name == "judgment_mutates_product" and (
            guard["phase"] == "review_implementation"
        ):
            assert guard["before_digest"] != guard["after_digest"]
            assert guard["mutation_disposition"] == "MUTATED"
        else:
            assert guard["before_digest"] == guard["after_digest"]
            assert guard["mutation_disposition"] == "UNCHANGED"

    checks = observation["visible_check_events"]
    assert len(checks) == _expected_visible_check_count(route)
    for index, check in enumerate(checks, start=1):
        assert set(check) == {
            "event_kind",
            "attempt",
            "argv",
            "timeout_seconds",
            "exit_code",
            "passed",
        }
        assert check["attempt"] == index
        assert check["argv"]
        assert check["timeout_seconds"] > 0
        if route.name == "checks_fail_after_fix":
            assert check["exit_code"] != 0
            assert check["passed"] is False
        else:
            assert check["exit_code"] == 0
            assert check["passed"] is True


def assert_full_treatment_parity(
    coordinator: Mapping[str, Any],
    orc: Mapping[str, Any],
    route: RouteContract,
) -> None:
    """Compare every representation-parity dimension owned by the pilot."""

    assert set(coordinator) == set(orc)
    assert set(PARITY_FIELDS).issubset(coordinator)
    assert coordinator["phase_names"] == list(route.phases)
    assert orc["phase_names"] == list(route.phases)
    assert coordinator["provider_call_count"] == route.provider_call_count
    assert orc["provider_call_count"] == route.provider_call_count
    assert coordinator["terminal_outcome"] == route.terminal_outcome
    assert orc["terminal_outcome"] == route.terminal_outcome

    _assert_fresh_sessions(coordinator)
    _assert_fresh_sessions(orc)
    _assert_request_and_control_evidence(coordinator, route)
    _assert_request_and_control_evidence(orc, route)

    assert _without_transport_correlation_ids(
        coordinator["provider_requests"]
    ) == _without_transport_correlation_ids(orc["provider_requests"])
    for field in PARITY_FIELDS:
        if field != "provider_requests":
            assert coordinator[field] == orc[field]


@pytest.mark.parametrize("route", ROUTES, ids=lambda route: route.name)
def test_coordinator_and_orc_have_full_route_parity(
    route: RouteContract,
    tmp_path: Path,
    public_boundary_trace: _PublicBoundaryTrace,
) -> None:
    assert route.provider_call_count == len(route.phases)
    assert route.terminal_outcome in {
        "COMPLETED",
        "BLOCKED",
        "EXHAUSTED",
        "PROTOCOL_FAILURE",
    }

    assert SCRIPTED_PROVIDER.is_file()
    assert COORDINATOR_SCRIPT.is_file(), (
        "missing conventional coordinator implementation"
    )
    assert ORC_WORKFLOW.is_file(), f"missing ORC treatment: {ORC_WORKFLOW}"
    assert all((PROMPT_ROOT / f"{phase}.md").is_file() for phase in PHASES)

    coordinator = importlib.import_module(
        "scripts.experiments.conventional_coordinator"
    )
    assert callable(coordinator.run_task)

    coordinator_workspace = tmp_path / "coordinator"
    coordinator_workspace.mkdir()
    coordinator_task, coordinator_control, _ = _prepare_workspace(
        coordinator_workspace,
        route.name,
    )
    coordinator_runtime = coordinator_workspace / ".pilot" / "runtime"
    coordinator_request_log = coordinator_runtime / "provider-requests.jsonl"
    coordinator_event_log = coordinator_runtime / "controller-events.jsonl"
    coordinator_registry, coordinator_providers = _fixture_provider_registry(
        route=route.name,
        state_path=coordinator_runtime / "provider-state.json",
        request_log=coordinator_request_log,
    )
    coordinator_observation = _run_coordinator(
        coordinator=coordinator,
        workspace=coordinator_workspace,
        registry=coordinator_registry,
        provider_names=coordinator_providers,
        task_path=coordinator_task,
        control_path=coordinator_control,
        request_log=coordinator_request_log,
        event_log=coordinator_event_log,
        boundary_trace=public_boundary_trace,
    )

    orc_workspace = tmp_path / "orc"
    orc_workspace.mkdir()
    orc_task, orc_control, orc_event_log = _prepare_workspace(
        orc_workspace,
        route.name,
    )
    orc_runtime = orc_workspace / ".pilot" / "runtime"
    orc_request_log = orc_runtime / "provider-requests.jsonl"
    orc_registry, orc_providers = _fixture_provider_registry(
        route=route.name,
        state_path=orc_runtime / "provider-state.json",
        request_log=orc_request_log,
    )
    orc_observation = _run_orc(
        route=route,
        workspace=orc_workspace,
        registry=orc_registry,
        provider_names=orc_providers,
        task_path=orc_task,
        control_path=orc_control,
        request_log=orc_request_log,
        event_log=orc_event_log,
        boundary_trace=public_boundary_trace,
    )

    assert_full_treatment_parity(
        coordinator_observation,
        orc_observation,
        route,
    )
