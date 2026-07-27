#!/usr/bin/env python3
"""Bounded conventional coordinator for the lean repository-task pilot.

The coordinator deliberately uses the same public prompt-composition,
provider-execution, and structured-result contracts as an ordinary workflow.
It is an experiment treatment, not a reusable orchestration framework.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_output_bundle,
)
from orchestrator.experiments.workspace import freeze_product
from orchestrator.providers import (
    ProviderExecutor,
    ProviderParams,
    ProviderRegistry,
)
from orchestrator.workflow.assets import (
    AssetResolutionError,
    WorkflowAssetResolver,
)
from orchestrator.workflow.prompting import PromptComposer
from orchestrator.workflow_lisp.build import (
    load_frontend_initialization_configuration,
)
from orchestrator.workflow_lisp.command_boundaries import (
    build_command_boundary_environment,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


PHASES = (
    "discover",
    "plan",
    "review_plan",
    "revise_plan",
    "implement",
    "review_implementation",
    "fix_implementation",
)
JUDGMENT_PHASES = frozenset(
    {
        "discover",
        "plan",
        "review_plan",
        "revise_plan",
        "review_implementation",
    }
)
PROVIDER_TIMEOUT_SECONDS = 1_800
_RAW_RESULT_FIELDS = {
    "provider_call_count",
    "terminal_outcome",
    "token_counts",
    "cost",
}
_SEMANTIC_TERMINAL_OUTCOMES = frozenset(
    {
        "COMPLETED",
        "BLOCKED",
        "EXHAUSTED",
        "PROTOCOL_FAILURE",
    }
)
_PROVIDER_OBSERVATION_STEM = re.compile(
    r"^(?P<ordinal>[0-9]{6})-[0-9a-f]{16}$"
)

_RECORD_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "discover": (
        ("relevant_paths", "list"),
        ("constraints", "list"),
        ("risks", "list"),
    ),
    "plan": (
        ("steps", "list"),
        ("acceptance_checks", "list"),
    ),
    "revise_plan": (
        ("steps", "list"),
        ("acceptance_checks", "list"),
    ),
    "implement": (
        ("summary", "string"),
        ("changed_paths", "list"),
        ("checks_summary", "string"),
    ),
    "fix_implementation": (
        ("summary", "string"),
        ("changed_paths", "list"),
        ("checks_summary", "string"),
    ),
}


class PilotTreatmentError(RuntimeError):
    """One treatment contract or execution failure."""


class ProductMutationError(PilotTreatmentError):
    """A judgment-only phase changed the projected product."""


@dataclass(frozen=True)
class PilotTreatmentConfig:
    workspace: Path
    task_path: str
    control_path: str
    prompt_paths: Mapping[str, str]
    prompt_workflow_path: Path
    provider_names: Mapping[str, str]
    provider_registry: ProviderRegistry
    model: str
    effort: str
    timeout_seconds: int
    controller_command: tuple[str, ...]

    def __post_init__(self) -> None:
        workspace = self.workspace.resolve()
        if not workspace.is_dir():
            raise ValueError("workspace must be an existing directory")
        _resolve_workspace_relative(workspace, self.task_path, must_exist=True)
        _resolve_workspace_relative(workspace, self.control_path, must_exist=True)
        if tuple(self.prompt_paths) != PHASES:
            raise ValueError("prompt_paths must contain the seven phases in order")
        if tuple(self.provider_names) != PHASES:
            raise ValueError("provider_names must contain the seven phases in order")
        resolver = WorkflowAssetResolver(self.prompt_workflow_path)
        for phase, path in self.prompt_paths.items():
            try:
                resolved_prompt = resolver.resolve(path)
            except AssetResolutionError as exc:
                raise ValueError(
                    f"invalid prompt asset for phase {phase!r}"
                ) from exc
            if phase not in PHASES or not resolved_prompt.is_file():
                raise ValueError(f"missing prompt asset for phase {phase!r}")
        if not self.model or not self.effort:
            raise ValueError("model and effort must be non-empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not self.controller_command:
            raise ValueError("controller_command must be non-empty")


@dataclass(frozen=True)
class CoordinatorResult:
    terminal_outcome: str
    phase_results: tuple[tuple[str, Mapping[str, Any]], ...]

    def to_observation(self) -> dict[str, Any]:
        """Return the coordinator-owned semantic outcome.

        Transport and validation observations are intentionally collected by
        the experiment harness at the public boundaries, not self-reported here.
        """

        return {
            "terminal_outcome": self.terminal_outcome,
            "phase_names": [phase for phase, _ in self.phase_results],
        }


def _resolve_workspace_relative(
    workspace: Path,
    raw_path: str,
    *,
    must_exist: bool,
) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("workspace-relative path must be non-empty")
    relative = PurePosixPath(raw_path)
    if relative.is_absolute() or any(part == ".." for part in relative.parts):
        raise ValueError(f"invalid workspace-relative path: {raw_path!r}")
    resolved = (workspace / Path(*relative.parts)).resolve()
    try:
        resolved.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError(f"workspace-relative path escapes root: {raw_path!r}") from exc
    if must_exist and not resolved.exists():
        raise ValueError(f"workspace-relative path does not exist: {raw_path!r}")
    return resolved


def _load_control(workspace: Path, control_path: str) -> dict[str, Any]:
    path = _resolve_workspace_relative(workspace, control_path, must_exist=True)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PilotTreatmentError(f"invalid controller configuration: {exc}") from exc
    if not isinstance(value, dict):
        raise PilotTreatmentError("controller configuration must be an object")
    expected = {"event_log", "product_exclusions", "visible_check"}
    if set(value) != expected:
        raise PilotTreatmentError(
            "controller configuration must contain exactly "
            f"{sorted(expected)}"
        )
    return value


def _control_event_log(workspace: Path, control: Mapping[str, Any]) -> Path:
    raw = control.get("event_log")
    if not isinstance(raw, str):
        raise PilotTreatmentError("controller event_log must be a path")
    return _resolve_workspace_relative(workspace, raw, must_exist=False)


def _product_exclusions(control: Mapping[str, Any]) -> tuple[PurePosixPath, ...]:
    raw = control.get("product_exclusions")
    if not isinstance(raw, list):
        raise PilotTreatmentError("product_exclusions must be a list")
    exclusions: list[PurePosixPath] = []
    for item in raw:
        if not isinstance(item, str) or not item:
            raise PilotTreatmentError("product exclusion must be a non-empty path")
        path = PurePosixPath(item)
        if path.is_absolute() or any(part == ".." for part in path.parts):
            raise PilotTreatmentError("product exclusion must stay under workspace")
        exclusions.append(path)
    if len(exclusions) != len(set(exclusions)):
        raise PilotTreatmentError("product exclusions must not contain duplicates")
    return tuple(exclusions)


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _append_jsonl(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _authoritative_bundle_path(workspace: Path) -> Path:
    raw = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
    if not raw:
        raise PilotTreatmentError("ORCHESTRATOR_OUTPUT_BUNDLE_PATH is required")
    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.resolve()
        try:
            resolved.relative_to(workspace.resolve())
        except ValueError as exc:
            raise PilotTreatmentError(
                "output bundle path escapes workspace"
            ) from exc
        return resolved
    return _resolve_workspace_relative(workspace, raw, must_exist=False)


def _guard_state_path(workspace: Path) -> Path:
    return workspace / ".pilot" / "runtime" / "product-guard-state.json"


def _product_manifest_command(
    *,
    workspace: Path,
    control_path: str,
    phase: str,
    position: str,
) -> str:
    if phase not in JUDGMENT_PHASES:
        raise PilotTreatmentError(f"phase is not judgment-only: {phase!r}")
    if position not in {"before", "after"}:
        raise PilotTreatmentError("guard position must be before or after")
    control = _load_control(workspace, control_path)
    digest = freeze_product(
        workspace,
        _product_exclusions(control),
    ).digest
    state_path = _guard_state_path(workspace)
    if position == "before":
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            state = {}
        if not isinstance(state, dict) or phase in state:
            raise PilotTreatmentError("product guard state is not quiescent")
        state[phase] = digest
        _atomic_json(state_path, state)
    else:
        if not state_path.exists():
            raise PilotTreatmentError("product guard has no before snapshot")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        before = state.pop(phase, None) if isinstance(state, dict) else None
        if not isinstance(before, str):
            raise PilotTreatmentError("product guard before snapshot is missing")
        _atomic_json(state_path, state)
        _append_jsonl(
            _control_event_log(workspace, control),
            {
                "event_kind": "product_manifest_guard",
                "phase": phase,
                "before_digest": before,
                "after_digest": digest,
                "mutation_disposition": (
                    "UNCHANGED" if before == digest else "MUTATED"
                ),
            },
        )
    _atomic_json(_authoritative_bundle_path(workspace), digest)
    return digest


def _visible_check_command(
    *,
    workspace: Path,
    control_path: str,
    attempt: int,
) -> dict[str, Any]:
    if attempt <= 0:
        raise PilotTreatmentError("visible-check attempt must be positive")
    control = _load_control(workspace, control_path)
    raw_check = control.get("visible_check")
    if not isinstance(raw_check, dict) or set(raw_check) != {
        "argv",
        "timeout_seconds",
    }:
        raise PilotTreatmentError(
            "visible_check must contain exactly argv and timeout_seconds"
        )
    argv = raw_check["argv"]
    timeout_seconds = raw_check["timeout_seconds"]
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(token, str) or not token for token in argv)
        or not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ):
        raise PilotTreatmentError("visible_check command contract is invalid")
    try:
        completed = subprocess.run(
            argv,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        exit_code = completed.returncode
    except subprocess.TimeoutExpired:
        exit_code = 124
    result = {"passed": exit_code == 0, "exit_code": exit_code}
    _append_jsonl(
        _control_event_log(workspace, control),
        {
            "event_kind": "visible_check",
            "attempt": attempt,
            "argv": argv,
            "timeout_seconds": timeout_seconds,
            "exit_code": exit_code,
            "passed": exit_code == 0,
        },
    )
    _atomic_json(_authoritative_bundle_path(workspace), result)
    return result


def _string_list_field(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "json_pointer": f"/{name}",
        "type": "list",
        "items": {"type": "string"},
    }


def _record_contract(phase: str, path: str) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for name, value_type in _RECORD_FIELDS[phase]:
        if value_type == "list":
            fields.append(_string_list_field(name))
        else:
            fields.append(
                {
                    "name": name,
                    "json_pointer": f"/{name}",
                    "type": value_type,
                }
            )
    return {"path": path, "fields": fields}


def _review_contract(path: str) -> dict[str, Any]:
    return {
        "path": path,
        "fields": [
            {
                "name": "decision",
                "json_pointer": "/decision",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE", "BLOCKED"],
            },
            {
                "name": "rationale",
                "json_pointer": "/rationale",
                "type": "string",
            },
            _string_list_field("findings"),
            {
                "name": "reason",
                "json_pointer": "/reason",
                "type": "string",
            },
        ],
    }


def _checks_contract(path: str) -> dict[str, Any]:
    return {
        "path": path,
        "fields": [
            {
                "name": "passed",
                "json_pointer": "/passed",
                "type": "bool",
            },
            {
                "name": "exit_code",
                "json_pointer": "/exit_code",
                "type": "integer",
            },
        ],
    }


def _run_single_provider(
    *,
    workspace: Path,
    task_path: Path,
    provider_registry: ProviderRegistry,
    provider_name: str,
    model: str,
    effort: str,
    timeout_seconds: int,
) -> None:
    """Execute the one-shot treatment through exactly one public adapter call."""

    resolved_workspace = workspace.resolve()
    resolved_task = task_path.resolve()
    try:
        resolved_task.relative_to(resolved_workspace)
    except ValueError as exc:
        raise PilotTreatmentError("direct task path escapes the workspace") from exc
    if not resolved_task.is_file():
        raise PilotTreatmentError("direct task path is not a file")
    try:
        task_text = resolved_task.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PilotTreatmentError(f"cannot read direct task: {exc}") from exc
    if not model or not effort or timeout_seconds <= 0:
        raise PilotTreatmentError("direct provider policy is incomplete")

    executor = ProviderExecutor(
        resolved_workspace,
        provider_registry,
        provider_observation_enabled=False,
    )
    prompt = (
        "Complete the repository task below in the current workspace. "
        "Inspect the repository, plan the work, edit the product, add or update "
        "tests when appropriate, run the task's visible checks, and correct "
        "issues you find before finishing. Do not merely describe changes.\n\n"
        "## Task\n\n"
        f"{task_text.rstrip()}\n"
    )
    invocation, error = executor.prepare_invocation(
        provider_name=provider_name,
        params=ProviderParams(),
        context={},
        prompt_content=prompt,
        timeout_sec=timeout_seconds,
        provider_call_policy={"model": model, "effort": effort},
    )
    if error is not None or invocation is None:
        raise PilotTreatmentError(
            f"direct provider invocation preparation failed: {error}"
        )
    execution = executor.execute(invocation, cwd=resolved_workspace)
    if not execution.is_promotable:
        raise PilotTreatmentError(
            "direct provider execution failed: "
            f"{execution.error or execution.stderr!r}"
        )


def _provider_result_path(phase: str) -> str:
    return (
        ".orchestrate/workflow_lisp/"
        "task_loop::run-task/"
        f"root.run-task__{phase}/result.json"
    )


def _typed_prompt_entry(
    *,
    binding_name: str,
    type_name: str,
    path_value: bool,
    order: int,
) -> dict[str, Any]:
    return {
        "schema_version": "workflow_lisp_typed_prompt_input.v1",
        "binding_name": binding_name,
        "renderer": {
            "renderer_id": "posix-path-line" if path_value else "canonical-json",
            "renderer_version": 1,
            "accepted_shape": "path_value" if path_value else "any_pure_value",
        },
        "value_source": {
            "kind": "typed_binding_ref",
            "ref": f"coordinator.{binding_name}",
        },
        "value_type_name": type_name,
        "source_map_origin_key": "task_loop::run-task",
        "injection_order": order,
    }


def _compose_prompt(
    *,
    composer: PromptComposer,
    prompt_path: str,
    phase: str,
    inputs: Sequence[tuple[str, str, bool, Any]],
    contract: Mapping[str, Any],
) -> str:
    step: dict[str, Any] = {
        "name": phase,
        "asset_file": prompt_path,
    }
    step["output_bundle"] = dict(contract)

    def violation(message: str, context: dict[str, Any]) -> dict[str, Any]:
        return {"message": message, "context": context}

    prompt, error = composer.read_prompt_source(
        step,
        step_name=phase,
        contract_violation_result=violation,
    )
    if error is not None:
        raise PilotTreatmentError(str(error))
    entries = [
        _typed_prompt_entry(
            binding_name=name,
            type_name=type_name,
            path_value=path_value,
            order=index,
        )
        for index, (name, type_name, path_value, _value) in enumerate(inputs)
    ]
    prompt, _evidence = composer.apply_typed_prompt_input_injection(
        step,
        prompt,
        typed_prompt_inputs=entries,
        resolved_typed_values={
            name: value for name, _type, _path, value in inputs
        },
        workflow_name="task_loop::run-task",
        step_id=f"root.run-task__{phase}",
    )
    return composer.apply_output_contract_prompt_suffix(step, prompt)


def _strict_result_keys(
    bundle_path: Path,
    *,
    contract: Mapping[str, Any],
    artifacts: Mapping[str, Any],
) -> None:
    raw = json.loads(bundle_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise PilotTreatmentError("provider structured result must be an object")
    expected = {field["name"] for field in contract.get("fields", ())}
    if set(raw) != expected:
        raise PilotTreatmentError(
            "provider structured result contains missing or unknown fields"
        )


class _Coordinator:
    def __init__(self, config: PilotTreatmentConfig) -> None:
        self.config = config
        self.workspace = config.workspace.resolve()
        self.composer = PromptComposer(
            workspace=self.workspace,
            asset_resolver=WorkflowAssetResolver(
                config.prompt_workflow_path
            ),
        )
        self.provider_executor = ProviderExecutor(
            self.workspace,
            config.provider_registry,
            provider_observation_enabled=False,
        )
        self.results: list[tuple[str, Mapping[str, Any]]] = []

    def _controller_bundle(self, name: str) -> str:
        return f".pilot/runtime/controller-results/{name}.json"

    def _run_controller(self, *args: str, bundle_path: str) -> None:
        output = _resolve_workspace_relative(
            self.workspace,
            bundle_path,
            must_exist=False,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.unlink(missing_ok=True)
        env = dict(os.environ)
        env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] = bundle_path
        completed = subprocess.run(
            [*self.config.controller_command, *args],
            cwd=self.workspace,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            raise PilotTreatmentError(
                f"controller command failed: {completed.stderr.decode(errors='replace')}"
            )

    def _guarded_call(
        self,
        phase: str,
        inputs: Sequence[tuple[str, str, bool, Any]],
    ) -> Mapping[str, Any]:
        before = self._controller_bundle(f"{phase}-guard-before")
        after = self._controller_bundle(f"{phase}-guard-after")
        self._run_controller(
            "product-manifest",
            "--control",
            self.config.control_path,
            "--phase",
            phase,
            "--position",
            "before",
            bundle_path=before,
        )
        result = self._provider_call(phase, inputs)
        self._run_controller(
            "product-manifest",
            "--control",
            self.config.control_path,
            "--phase",
            phase,
            "--position",
            "after",
            bundle_path=after,
        )
        before_digest = json.loads(
            _resolve_workspace_relative(
                self.workspace,
                before,
                must_exist=True,
            ).read_text(encoding="utf-8")
        )
        after_digest = json.loads(
            _resolve_workspace_relative(
                self.workspace,
                after,
                must_exist=True,
            ).read_text(encoding="utf-8")
        )
        if before_digest != after_digest:
            raise ProductMutationError(
                f"judgment phase {phase!r} mutated the product"
            )
        return result

    def _provider_call(
        self,
        phase: str,
        inputs: Sequence[tuple[str, str, bool, Any]],
    ) -> Mapping[str, Any]:
        path = _provider_result_path(phase)
        contract = (
            _review_contract(path)
            if phase in {"review_plan", "review_implementation"}
            else _record_contract(phase, path)
        )
        prompt = _compose_prompt(
            composer=self.composer,
            prompt_path=self.config.prompt_paths[phase],
            phase=phase,
            inputs=inputs,
            contract=contract,
        )
        output = _resolve_workspace_relative(
            self.workspace,
            path,
            must_exist=False,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.unlink(missing_ok=True)
        invocation, error = self.provider_executor.prepare_invocation(
            provider_name=self.config.provider_names[phase],
            params=ProviderParams(),
            context={},
            prompt_content=prompt,
            env={"ORCHESTRATOR_OUTPUT_BUNDLE_PATH": path},
            timeout_sec=self.config.timeout_seconds,
            provider_call_policy={
                "model": self.config.model,
                "effort": self.config.effort,
            },
        )
        if error is not None or invocation is None:
            raise PilotTreatmentError(
                f"provider invocation preparation failed for {phase}: {error}"
            )
        execution = self.provider_executor.execute(invocation, cwd=self.workspace)
        if not execution.is_promotable:
            raise PilotTreatmentError(
                f"provider execution failed for {phase}: "
                f"{execution.error or execution.stderr!r}"
            )
        try:
            artifacts = validate_output_bundle(
                dict(contract),
                workspace=self.workspace,
            )
        except OutputContractError as exc:
            raise PilotTreatmentError(
                f"provider result validation failed for {phase}: {exc.violations}"
            ) from exc
        _strict_result_keys(output, contract=contract, artifacts=artifacts)
        result = dict(artifacts)
        self.results.append((phase, result))
        return result

    def _visible_check(self, attempt: int) -> Mapping[str, Any]:
        bundle = self._controller_bundle(f"visible-check-{attempt}")
        self._run_controller(
            "visible-check",
            "--control",
            self.config.control_path,
            "--attempt",
            str(attempt),
            bundle_path=bundle,
        )
        contract = _checks_contract(bundle)
        try:
            return validate_output_bundle(contract, workspace=self.workspace)
        except OutputContractError as exc:
            raise PilotTreatmentError(
                f"visible-check result validation failed: {exc.violations}"
            ) from exc

    def run(self) -> CoordinatorResult:
        task = ("task_path", "TaskPath", True, self.config.task_path)
        control = ("control_path", "ControlPath", True, self.config.control_path)
        discovery = self._guarded_call("discover", (task,))
        plan = self._guarded_call(
            "plan",
            (
                task,
                ("discovery", "DiscoveryResult", False, discovery),
                control,
            ),
        )
        plan_review = self._guarded_call(
            "review_plan",
            (
                task,
                ("discovery", "DiscoveryResult", False, discovery),
                ("plan", "PlanResult", False, plan),
                control,
            ),
        )
        if plan_review["decision"] == "BLOCKED":
            return self._finish("BLOCKED")
        if plan_review["decision"] == "REVISE":
            plan = self._guarded_call(
                "revise_plan",
                (
                    task,
                    ("discovery", "DiscoveryResult", False, discovery),
                    ("plan", "PlanResult", False, plan),
                    (
                        "plan_review",
                        "ReviewResult",
                        False,
                        plan_review,
                    ),
                    control,
                ),
            )
            plan_review = self._guarded_call(
                "review_plan",
                (
                    task,
                    ("discovery", "DiscoveryResult", False, discovery),
                    ("plan", "PlanResult", False, plan),
                    control,
                ),
            )
            if plan_review["decision"] == "BLOCKED":
                return self._finish("BLOCKED")
            if plan_review["decision"] != "APPROVE":
                return self._finish("EXHAUSTED")

        implementation = self._provider_call(
            "implement",
            (task, ("plan", "PlanResult", False, plan)),
        )
        checks = self._visible_check(1)
        implementation_review = self._guarded_call(
            "review_implementation",
            (
                task,
                ("plan", "PlanResult", False, plan),
                (
                    "implementation",
                    "ImplementationResult",
                    False,
                    implementation,
                ),
                ("checks", "ChecksResult", False, checks),
            ),
        )
        if implementation_review["decision"] == "BLOCKED":
            return self._finish("BLOCKED")
        if (
            implementation_review["decision"] == "APPROVE"
            and checks["passed"]
        ):
            return self._finish("COMPLETED")

        implementation = self._provider_call(
            "fix_implementation",
            (
                task,
                ("plan", "PlanResult", False, plan),
                (
                    "implementation",
                    "ImplementationResult",
                    False,
                    implementation,
                ),
                ("checks", "ChecksResult", False, checks),
                (
                    "implementation_review",
                    "ReviewResult",
                    False,
                    implementation_review,
                ),
            ),
        )
        checks = self._visible_check(2)
        implementation_review = self._guarded_call(
            "review_implementation",
            (
                task,
                ("plan", "PlanResult", False, plan),
                (
                    "implementation",
                    "ImplementationResult",
                    False,
                    implementation,
                ),
                ("checks", "ChecksResult", False, checks),
            ),
        )
        if implementation_review["decision"] == "BLOCKED":
            return self._finish("BLOCKED")
        if (
            implementation_review["decision"] == "APPROVE"
            and checks["passed"]
        ):
            return self._finish("COMPLETED")
        return self._finish("EXHAUSTED")

    def _finish(self, outcome: str) -> CoordinatorResult:
        return CoordinatorResult(
            terminal_outcome=outcome,
            phase_results=tuple(self.results),
        )


def run_task(config: PilotTreatmentConfig) -> CoordinatorResult:
    """Run one bounded conventional treatment."""

    coordinator = _Coordinator(config)
    try:
        return coordinator.run()
    except ProductMutationError:
        # Mutation is a semantic terminal outcome, not a provider transport
        # failure. Re-run is forbidden; report it directly.
        return CoordinatorResult(
            terminal_outcome="PROTOCOL_FAILURE",
            phase_results=tuple(coordinator.results),
        )


def _resolve_apparatus_file(
    apparatus_root: Path,
    raw_path: str | Path,
    *,
    label: str,
) -> Path:
    root = apparatus_root.resolve(strict=True)
    path = Path(raw_path).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PilotTreatmentError(f"{label} escapes the apparatus root") from exc
    if not path.is_file():
        raise PilotTreatmentError(f"{label} is not a regular file")
    return path


def _load_launcher_roles(
    *,
    workspace: Path,
    apparatus_root: Path,
    provider_config: Path,
    prompt_config: Path,
    command_config: Path,
) -> tuple[ProviderRegistry, dict[str, str], dict[str, str]]:
    try:
        configuration = load_frontend_initialization_configuration(
            workspace_root=workspace,
            source_roots=(apparatus_root,),
            provider_externs_path=provider_config,
            prompt_externs_path=prompt_config,
            command_boundaries_path=command_config,
        )
        build_command_boundary_environment(configuration.command_boundaries)
    except (LispFrontendCompileError, OSError, ValueError) as exc:
        raise PilotTreatmentError(
            f"invalid staged Workflow Lisp role manifests: {exc}"
        ) from exc

    expected_provider_keys = {
        f"providers.repository-task.{phase.replace('_', '-')}"
        for phase in PHASES
    }
    expected_prompt_keys = {
        f"prompts.repository-task.{phase.replace('_', '-')}"
        for phase in PHASES
    }
    if set(configuration.provider_externs) != expected_provider_keys:
        raise PilotTreatmentError("provider extern manifest has the wrong roles")
    if set(configuration.prompt_externs) != expected_prompt_keys:
        raise PilotTreatmentError("prompt extern manifest has the wrong roles")
    if set(configuration.command_boundaries) != {
        "pilot_product_manifest",
        "pilot_visible_check",
    }:
        raise PilotTreatmentError("command manifest has the wrong boundaries")

    registry = ProviderRegistry()
    provider_names: dict[str, str] = {}
    prompt_paths: dict[str, str] = {}
    workflow_path = apparatus_root / "task_loop.orc"
    resolver = WorkflowAssetResolver(workflow_path)
    for phase in PHASES:
        suffix = phase.replace("_", "-")
        provider_name = configuration.provider_externs[
            f"providers.repository-task.{suffix}"
        ]
        if registry.get(provider_name) is None:
            raise PilotTreatmentError(
                f"provider extern for {phase!r} is not registered"
            )
        provider_names[phase] = provider_name

        raw_binding = configuration.prompt_externs[
            f"prompts.repository-task.{suffix}"
        ]
        if (
            not isinstance(raw_binding, Mapping)
            or set(raw_binding) != {"asset_file"}
            or not isinstance(raw_binding["asset_file"], str)
        ):
            raise PilotTreatmentError(
                f"prompt extern for {phase!r} must use asset_file"
            )
        prompt_path = raw_binding["asset_file"]
        try:
            resolved_prompt = resolver.resolve(prompt_path)
            resolved_prompt.relative_to(apparatus_root)
        except (AssetResolutionError, ValueError) as exc:
            raise PilotTreatmentError(
                f"prompt extern for {phase!r} escapes the apparatus"
            ) from exc
        if not resolved_prompt.is_file():
            raise PilotTreatmentError(
                f"prompt extern for {phase!r} is missing"
            )
        prompt_paths[phase] = prompt_path
    if len(set(provider_names.values())) != 1:
        raise PilotTreatmentError(
            "all frozen repository-task roles must use one provider template"
        )
    return registry, provider_names, prompt_paths


def _materialize_runtime_inputs(
    *,
    workspace: Path,
    task_path: Path,
    runtime_control_path: Path,
) -> tuple[Path, Path]:
    runtime_root = workspace / ".pilot" / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    local_task = runtime_root / "task.md"
    local_control = runtime_root / "control.json"
    if local_task.exists() or local_control.exists():
        raise PilotTreatmentError("private runtime inputs already exist")
    try:
        shutil.copyfile(task_path, local_task)
        template = json.loads(runtime_control_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PilotTreatmentError(
            f"cannot materialize private runtime inputs: {exc}"
        ) from exc
    if not isinstance(template, dict) or set(template) != {
        "product_exclusions",
        "visible_check",
    }:
        raise PilotTreatmentError(
            "runtime control template has unknown or missing fields"
        )
    control = {
        "event_log": ".pilot/runtime/controller-events.jsonl",
        "product_exclusions": template["product_exclusions"],
        "visible_check": template["visible_check"],
    }
    _product_exclusions(control)
    visible_check = control["visible_check"]
    if not isinstance(visible_check, dict) or set(visible_check) != {
        "argv",
        "timeout_seconds",
    }:
        raise PilotTreatmentError(
            "runtime visible check has unknown or missing fields"
        )
    argv = visible_check["argv"]
    timeout_seconds = visible_check["timeout_seconds"]
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(token, str) or not token for token in argv)
        or isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or timeout_seconds <= 0
    ):
        raise PilotTreatmentError("runtime visible check is malformed")
    _atomic_json(local_control, control)
    return local_task, local_control


def _write_raw_result(
    path: Path,
    provider_call_count: int,
    terminal_outcome: str,
) -> None:
    if (
        isinstance(provider_call_count, bool)
        or not isinstance(provider_call_count, int)
        or provider_call_count < 0
    ):
        raise PilotTreatmentError("provider call count cannot be negative")
    if terminal_outcome not in _SEMANTIC_TERMINAL_OUTCOMES:
        raise PilotTreatmentError("semantic terminal outcome is invalid")
    value = {
        "provider_call_count": provider_call_count,
        "terminal_outcome": terminal_outcome,
        "token_counts": "UNKNOWN",
        "cost": "UNKNOWN",
    }
    if set(value) != _RAW_RESULT_FIELDS:
        raise AssertionError("raw result fields drifted")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise PilotTreatmentError("raw result path already exists")
    _atomic_json(path, value)


def _provider_observation_stems(
    root: Path,
    *,
    suffix: str,
) -> tuple[str, ...]:
    if not root.is_dir() or root.is_symlink():
        raise PilotTreatmentError(
            "workflow provider call accounting is missing"
        )
    stems: list[str] = []
    for path in sorted(root.iterdir()):
        if path.is_symlink() or not path.is_file() or not path.name.endswith(suffix):
            raise PilotTreatmentError(
                "workflow provider call accounting is malformed"
            )
        stem = path.name[: -len(suffix)]
        if _PROVIDER_OBSERVATION_STEM.fullmatch(stem) is None:
            raise PilotTreatmentError(
                "workflow provider call accounting is malformed"
            )
        stems.append(stem)
    return tuple(stems)


def _workflow_treatment_result(state_root: Path) -> tuple[int, str]:
    state_paths = sorted(state_root.glob("*/state.json"))
    if len(state_paths) != 1:
        raise PilotTreatmentError(
            "workflow launcher did not produce exactly one run state"
        )
    try:
        state = json.loads(state_paths[0].read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PilotTreatmentError(f"cannot read workflow state: {exc}") from exc
    if not isinstance(state, dict) or state.get("status") != "completed":
        raise PilotTreatmentError("ordinary Workflow Lisp run did not complete")
    outputs = state.get("workflow_outputs")
    if not isinstance(outputs, dict):
        raise PilotTreatmentError(
            "workflow state lacks a semantic terminal outcome"
        )
    terminal_candidates = [
        outputs[key]
        for key in ("__result__", "return__variant", "variant")
        if key in outputs
    ]
    if len(terminal_candidates) != 1:
        raise PilotTreatmentError(
            "workflow semantic terminal outcome is missing or ambiguous"
        )
    terminal_outcome = terminal_candidates[0]
    if terminal_outcome not in _SEMANTIC_TERMINAL_OUTCOMES:
        raise PilotTreatmentError(
            "workflow semantic terminal outcome is invalid"
        )

    observation_root = state_paths[0].parent / "provider-observation"
    display_stems = _provider_observation_stems(
        observation_root / "display",
        suffix=".display",
    )
    transcript_stems = _provider_observation_stems(
        observation_root / "transcripts",
        suffix=".transcript",
    )
    if (
        not display_stems
        or display_stems != transcript_stems
        or [
            int(
                _PROVIDER_OBSERVATION_STEM.fullmatch(stem).group("ordinal")
            )
            for stem in display_stems
        ]
        != list(range(1, len(display_stems) + 1))
    ):
        raise PilotTreatmentError(
            "workflow provider call accounting is incomplete or ambiguous"
        )
    count = len(display_stems)
    return count, terminal_outcome


def _run_workflow_treatment(
    *,
    workspace: Path,
    apparatus_root: Path,
    task_path: Path,
    control_path: Path,
    provider_config: Path,
    prompt_config: Path,
    command_config: Path,
    controller_script: Path,
    model: str,
    effort: str,
    provider_timeout_seconds: int,
) -> tuple[int, str]:
    if provider_timeout_seconds != PROVIDER_TIMEOUT_SECONDS:
        raise PilotTreatmentError(
            "workflow provider timeout does not match the frozen source"
        )
    state_root = workspace / ".pilot" / "runtime" / "workflow-state"
    if state_root.exists():
        raise PilotTreatmentError("workflow state root already exists")
    workflow_path = apparatus_root / "task_loop.orc"
    if not workflow_path.is_file():
        raise PilotTreatmentError("staged Workflow Lisp source is missing")
    command = [
        "python",
        "-m",
        "orchestrator",
        "run",
        str(workflow_path),
        "--source-root",
        str(apparatus_root),
        "--entry-workflow",
        "task_loop::run-task",
        "--provider-externs-file",
        str(provider_config),
        "--prompt-externs-file",
        str(prompt_config),
        "--command-boundaries-file",
        str(command_config),
        "--input",
        f"task_path={task_path.relative_to(workspace).as_posix()}",
        "--input",
        f"control_path={control_path.relative_to(workspace).as_posix()}",
        "--input",
        f"controller_script={controller_script}",
        "--input",
        f"model={model}",
        "--input",
        f"effort={effort}",
        "--state-dir",
        str(state_root),
        "--max-retries",
        "0",
        "--retry-delay",
        "0",
        "--on-error",
        "stop",
        "--quiet",
    ]
    completed = subprocess.run(
        command,
        cwd=workspace,
        env=dict(os.environ),
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        raise PilotTreatmentError(
            f"ordinary Workflow Lisp run failed with exit {completed.returncode}"
        )
    return _workflow_treatment_result(state_root)


def _parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    manifest = subparsers.add_parser("product-manifest")
    manifest.add_argument("--control", required=True)
    manifest.add_argument("--phase", required=True)
    manifest.add_argument("--position", choices=("before", "after"), required=True)
    check = subparsers.add_parser("visible-check")
    check.add_argument("--control", required=True)
    check.add_argument("--attempt", type=int, required=True)
    for command in ("single", "bounded", "workflow"):
        launcher = subparsers.add_parser(command)
        launcher.add_argument("--workspace", type=Path, required=True)
        launcher.add_argument("--task", type=Path, required=True)
        launcher.add_argument("--result-file", type=Path, required=True)
        launcher.add_argument("--provider-config", type=Path, required=True)
        launcher.add_argument("--prompt-config", type=Path, required=True)
        launcher.add_argument("--command-config", type=Path, required=True)
        launcher.add_argument("--apparatus-root", type=Path, required=True)
        launcher.add_argument("--runtime-control", type=Path, required=True)
        launcher.add_argument("--model", required=True)
        launcher.add_argument("--effort", required=True)
        launcher.add_argument(
            "--provider-timeout-seconds",
            type=int,
            required=True,
        )
    return parser.parse_args()


def main() -> int:
    args = _parse_cli()
    workspace = Path.cwd().resolve()
    try:
        if args.command == "product-manifest":
            _product_manifest_command(
                workspace=workspace,
                control_path=args.control,
                phase=args.phase,
                position=args.position,
            )
        elif args.command == "visible-check":
            _visible_check_command(
                workspace=workspace,
                control_path=args.control,
                attempt=args.attempt,
            )
        elif args.command in {"single", "bounded", "workflow"}:
            declared_workspace = args.workspace.resolve(strict=True)
            if workspace != declared_workspace:
                raise PilotTreatmentError(
                    "declared workspace does not match the process cwd"
                )
            apparatus_root = args.apparatus_root.resolve(strict=True)
            if not apparatus_root.is_dir():
                raise PilotTreatmentError("apparatus root is not a directory")
            task_path = _resolve_apparatus_file(
                apparatus_root,
                args.task,
                label="task",
            )
            provider_config = _resolve_apparatus_file(
                apparatus_root,
                args.provider_config,
                label="provider config",
            )
            prompt_config = _resolve_apparatus_file(
                apparatus_root,
                args.prompt_config,
                label="prompt config",
            )
            command_config = _resolve_apparatus_file(
                apparatus_root,
                args.command_config,
                label="command config",
            )
            runtime_control = _resolve_apparatus_file(
                apparatus_root,
                args.runtime_control,
                label="runtime control",
            )
            controller_script = _resolve_apparatus_file(
                apparatus_root,
                apparatus_root / "treatment_driver.py",
                label="treatment driver",
            )
            if controller_script.read_bytes() != Path(__file__).read_bytes():
                raise PilotTreatmentError(
                    "executed treatment driver differs from the staged binding"
                )
            registry, provider_names, prompt_paths = _load_launcher_roles(
                workspace=workspace,
                apparatus_root=apparatus_root,
                provider_config=provider_config,
                prompt_config=prompt_config,
                command_config=command_config,
            )
            local_task, local_control = _materialize_runtime_inputs(
                workspace=workspace,
                task_path=task_path,
                runtime_control_path=runtime_control,
            )
            if args.provider_timeout_seconds != PROVIDER_TIMEOUT_SECONDS:
                raise PilotTreatmentError(
                    "launcher provider timeout differs from the frozen policy"
                )

            if args.command == "single":
                _run_single_provider(
                    workspace=workspace,
                    task_path=local_task,
                    provider_registry=registry,
                    provider_name=provider_names["implement"],
                    model=args.model,
                    effort=args.effort,
                    timeout_seconds=args.provider_timeout_seconds,
                )
                provider_call_count = 1
                terminal_outcome = "COMPLETED"
            elif args.command == "bounded":
                result = run_task(
                    PilotTreatmentConfig(
                        workspace=workspace,
                        task_path=local_task.relative_to(workspace).as_posix(),
                        control_path=local_control.relative_to(workspace).as_posix(),
                        prompt_paths=prompt_paths,
                        prompt_workflow_path=apparatus_root / "task_loop.orc",
                        provider_names=provider_names,
                        provider_registry=registry,
                        model=args.model,
                        effort=args.effort,
                        timeout_seconds=args.provider_timeout_seconds,
                        controller_command=("python", str(controller_script)),
                    )
                )
                provider_call_count = len(result.phase_results)
                terminal_outcome = result.terminal_outcome
            else:
                (
                    provider_call_count,
                    terminal_outcome,
                ) = _run_workflow_treatment(
                    workspace=workspace,
                    apparatus_root=apparatus_root,
                    task_path=local_task,
                    control_path=local_control,
                    provider_config=provider_config,
                    prompt_config=prompt_config,
                    command_config=command_config,
                    controller_script=controller_script,
                    model=args.model,
                    effort=args.effort,
                    provider_timeout_seconds=args.provider_timeout_seconds,
                )
            _write_raw_result(
                args.result_file.resolve(),
                provider_call_count,
                terminal_outcome,
            )
        else:
            raise AssertionError(f"unhandled command: {args.command}")
    except (OSError, ValueError, PilotTreatmentError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
