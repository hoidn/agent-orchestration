"""Physical WorkflowExecutor bindings for target-2.23 phased delivery."""

from __future__ import annotations

import time
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, cast

from ...contracts.output_contract import (
    OutputContractError,
    validate_expected_outputs,
    validate_output_bundle,
    validate_variant_output_bundle,
)
from ...deps.content_snapshot import snapshot_content_dependencies
from ...providers.types import INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION
from ..executor_runtime import RuntimeStepInput
from ..prompt_dependency_evidence import (
    build_fragment_success_evidence,
    publish_evidence_file,
)
from ..prompt_fragment_contract import (
    CompilerPromptFragmentContract,
    CompilerPromptFragmentContractV2,
)
from ..prompt_identity import (
    build_fragment_program_role,
    build_injected_dependencies_role,
    build_resolved_bindings_role,
    build_runtime_contributions_role,
)
from ..prompting import (
    PromptFragmentRenderResult,
    render_prompt_fragment_base,
    validate_runtime_contribution_composition,
)
from ..provider_attempts import ProviderAttemptScope, resolve_aggregate_run_owner
from ..runtime_context import RuntimeContext
from ..runtime_step import RuntimeStep
from .models import PhasedRuntimePolicy, ProviderBoundPolicy

if TYPE_CHECKING:
    from ..executor import WorkflowExecutor

class _WorkflowPhasedAdapter:
    """Remember only the exact active handle around the public adapter API."""

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        self.active_handle: Any = None

    def start(self, invocation: Any, *, deadline: float) -> Any:
        outcome = self._adapter.start(invocation, deadline=deadline)
        if getattr(outcome, "status", None) == "started":
            self.active_handle = outcome.handle
        return outcome

    def offer(self, handle: Any, literal_message: str, *, deadline: float) -> Any:
        return self._adapter.offer(
            handle,
            literal_message,
            deadline=deadline,
        )

    def offer_close(self, handle: Any, *, deadline: float) -> Any:
        return self._adapter.offer_close(handle, deadline=deadline)

    def join(self, handle: Any, deadline: float) -> Any:
        return self._adapter.join(handle, deadline)

    def abort(self, handle: Any, deadline: float) -> Any:
        return self._adapter.abort(handle, deadline)

    def probe_process_status(self, *, deadline: float) -> Any:
        if self.active_handle is None:
            return None
        return self._adapter.probe_process_status(
            self.active_handle,
            deadline=deadline,
        )

    def prove_no_backend_allocation(self) -> Any:
        return self._adapter.prove_no_backend_allocation()


class _WorkflowPhasedProviderAttemptBindings:
    """Private physical bindings from one RuntimeStep to the Q5 coordinator."""

    def __init__(
        self,
        *,
        executor: "WorkflowExecutor",
        step: RuntimeStepInput,
        context: Dict[str, Any],
        state: Dict[str, Any],
        provider_bound_policy: ProviderBoundPolicy,
        runtime_policy: PhasedRuntimePolicy,
        runtime_step_id: Optional[str],
        parent_steps: Optional[Dict[str, Any]],
        self_steps: Optional[Dict[str, Any]],
        root_steps: Optional[Dict[str, Any]],
    ) -> None:
        from ...providers.interactive_terminal import (
            InteractiveTerminalTurnQueueAdapter,
        )

        if runtime_policy.delivery != "phased":
            raise ValueError("phased bindings require explicit phased delivery")
        self.executor = executor
        self.step = step
        self.context = context
        self.state = state
        self.provider_bound_policy = provider_bound_policy
        self.runtime_policy = runtime_policy
        self.runtime_step_id = runtime_step_id or executor._step_id(step)
        self.parent_steps = parent_steps
        self.self_steps = self_steps
        self.root_steps = root_steps
        self.step_name = step.get("name", f"step_{executor.current_step}")
        self.scope: ProviderAttemptScope | None = None
        self.allocation: Any = None
        self.resolved_expected_outputs: Optional[List[Dict[str, Any]]] = None
        self.resolved_output_bundle: Optional[Dict[str, Any]] = None
        self.prompt_contract_step: RuntimeStepInput = step
        self.retained_fragment_v1: Mapping[str, Any] | None = None
        self.fragment_render_result: PromptFragmentRenderResult | None = None
        self.runtime_contribution_rows: tuple[Mapping[str, Any], ...] = ()
        self.cut: Any = None
        self.preflight: Any = None
        self._validated_artifacts: Dict[str, Any] = {}
        self._validated_structured_artifacts: Dict[str, Any] = {}
        self._prepared_result: Dict[str, Any] | None = None
        self._failure: Any = None
        pending_rerun = getattr(
            executor,
            "_pending_interrupted_provider_rerun",
            None,
        )
        self._interrupted_rerun = (
            dict(pending_rerun)
            if isinstance(pending_rerun, Mapping)
            else None
        )
        runtime_root = (
            Path(executor.state_manager.run_root)
            / "provider-phased-delivery"
        )
        self.adapter = _WorkflowPhasedAdapter(
            InteractiveTerminalTurnQueueAdapter(
                runtime_root,
                socket_root=Path("/tmp"),
            )
        )

    @staticmethod
    def _policy_dict(policy: ProviderBoundPolicy) -> Dict[str, str]:
        return {
            key: value
            for key, value in (
                ("model", policy.model),
                ("effort", policy.effort),
            )
            if value is not None
        }

    @staticmethod
    def _diagnostic(
        reason: str,
        *,
        canonical_value: bool | int | str | None = None,
    ):
        from .coordinator import (
            _runtime_diagnostic,
        )

        return _runtime_diagnostic(
            reason,
            canonical_value=canonical_value,
        )

    @staticmethod
    def _q2_violation_type(
        error: OutputContractError,
        *,
        fallback: str,
    ) -> str:
        first = next(iter(error.violations), {})
        violation_type = first.get("type")
        return (
            violation_type
            if isinstance(violation_type, str) and violation_type
            else fallback
        )

    def observed_at(self) -> str:
        from datetime import datetime, timezone

        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )

    def monotonic_now(self) -> float:
        return float(time.monotonic())

    def prestart_no_backend_allocation_proof(self):
        return self.adapter.prove_no_backend_allocation()

    def allocate_attempt(self):
        from .bindings import AttemptAllocation

        scope = self.executor._provider_attempt_scope(
            step_name=self.step_name,
            runtime_step_id=self.runtime_step_id,
        )
        fragment_contract, _fragment_identity = (
            self.executor._compiler_prompt_fragment_pair(self.step)
        )
        fragment_schema_version = (
            "compiled_prompt_fragment_identity.v2"
            if isinstance(fragment_contract, CompilerPromptFragmentContractV2)
            else None
        )
        ordinal = self.executor.state_manager.allocate_provider_attempt(
            scope,
            prompt_fragment_identity_schema_version=fragment_schema_version,
        )
        self.scope = scope
        self.allocation = AttemptAllocation(
            scope=scope,
            attempt_ordinal=ordinal,
        )
        return self.allocation

    def derive_attempt_deadline(self, allocation) -> float:
        del allocation
        timeout = self.step.get("timeout_sec", 3600)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout <= 0
        ):
            raise ValueError("phased timeout_sec must be positive")
        return float(time.monotonic() + timeout)

    def _resolved_runtime_context(self) -> RuntimeContext:
        runtime_context = RuntimeContext.from_mapping(
            self.context,
            default_context=self.executor.workflow_context_defaults,
            parent_steps=self.parent_steps,
            root_steps=self.root_steps or self.state.get("steps", {}),
        )
        if isinstance(self.self_steps, dict):
            runtime_context = RuntimeContext(
                values=runtime_context.values,
                workflow_context=runtime_context.workflow_context,
                self_steps=self.self_steps,
                explicit_steps=True,
                parent_steps=runtime_context.parent_steps,
                root_steps=runtime_context.root_steps,
            )
        return runtime_context

    def _resolve_contract_paths(self) -> None:
        (
            expected,
            bundle,
            path_error,
        ) = self.executor._resolve_output_contract_paths(
            self.step,
            self.state,
            context=self.context,
        )
        if path_error is not None:
            raise ValueError(str(path_error))
        fragment_contract, _identity = (
            self.executor._compiler_prompt_fragment_pair(self.step)
        )
        position_error = (
            self.executor._prompt_output_position_prelaunch_result(
                step=self.step,
                fragment_contract=fragment_contract,
                resolved_expected_outputs=expected,
                resolved_output_bundle=bundle,
                state=self.state,
                runtime_context=self._resolved_runtime_context(),
            )
        )
        if position_error is not None:
            raise ValueError(str(position_error))
        bundle_error = self.executor._prepare_runtime_output_bundle_parent(
            bundle
        )
        if bundle_error is not None:
            raise ValueError(str(bundle_error))
        contract_step: RuntimeStepInput = self.step
        if expected is not None or bundle is not None:
            resolved_contract_step = dict(self.step)
            if expected is not None:
                resolved_contract_step["expected_outputs"] = expected
            if bundle is not None:
                resolved_contract_step[
                    "variant_output"
                    if "variant_output" in self.step
                    else "output_bundle"
                ] = bundle
            contract_step = resolved_contract_step
        self.resolved_expected_outputs = expected
        self.resolved_output_bundle = bundle
        self.prompt_contract_step = contract_step

    def _render_fragment_and_cut(self, allocation):
        from ...workflow_lisp.typed_prompt_inputs import (
            render_typed_prompt_inputs,
            validate_typed_prompt_input_composition,
        )

        fragment_contract, fragment_identity = (
            self.executor._compiler_prompt_fragment_pair(self.step)
        )
        if (
            type(fragment_contract) is not CompilerPromptFragmentContractV2
            or not isinstance(fragment_identity, str)
            or not isinstance(self.step, RuntimeStep)
            or self.step.compiler_prompt_attempt_binding_plan is None
        ):
            raise ValueError(
                "phased delivery requires the complete fragment binding pair"
            )
        runtime_context = self._resolved_runtime_context()
        resolved_fragment_values: Dict[str, Any] = {}
        for slot in fragment_contract.rendered_slots:
            binding = slot.value_source.get("binding")
            if isinstance(binding, Mapping):
                binding = dict(binding)
            value, error = self.executor._resolve_typed_prompt_input_value(
                binding,
                self.state,
                scope=runtime_context.scope(),
            )
            if error is not None:
                raise ValueError("prompt fragment slot value unavailable")
            resolved_fragment_values[slot.name] = value
        rendered = render_prompt_fragment_base(
            cast(CompilerPromptFragmentContract, fragment_contract),
            resolved_slot_values=resolved_fragment_values,
            target_dsl_version=self.step.target_dsl_version,
            compiler_prompt_attempt_binding_plan=(
                self.step.compiler_prompt_attempt_binding_plan
            ),
        )
        if type(rendered) is not PromptFragmentRenderResult:
            raise ValueError("phased fragment render trace is missing")
        self.fragment_render_result = rendered

        typed_inputs = self.step.get("typed_prompt_inputs")
        resolved_typed_values: Dict[str, Any] = {}
        if isinstance(typed_inputs, list):
            for item in typed_inputs:
                if not isinstance(item, dict):
                    raise ValueError("typed prompt input is invalid")
                source = item.get("value_source")
                if not isinstance(source, dict):
                    raise ValueError("typed prompt input source is invalid")
                binding = source.get("binding")
                if binding is None and isinstance(source.get("ref"), str):
                    binding = {"ref": source["ref"]}
                value, error = (
                    self.executor._resolve_typed_prompt_input_value(
                        binding,
                        self.state,
                        scope=runtime_context.scope(),
                    )
                )
                name = item.get("binding_name")
                if error is not None or not isinstance(name, str) or not name:
                    raise ValueError("typed prompt input value is unavailable")
                resolved_typed_values[name] = value
            _block, typed_evidence = render_typed_prompt_inputs(
                typed_inputs,
                resolved_typed_values=resolved_typed_values,
                workflow_name=self.executor.workflow_name or "",
                step_id=self.runtime_step_id,
                fragment_render_result=rendered,
                compiler_prompt_attempt_binding_plan=(
                    self.step.compiler_prompt_attempt_binding_plan
                ),
            )
            validate_typed_prompt_input_composition(
                typed_inputs,
                resolved_typed_values=resolved_typed_values,
                evidence=typed_evidence,
                workflow_name=self.executor.workflow_name or "",
                step_id=self.runtime_step_id,
                fragment_render_result=rendered,
                compiler_prompt_attempt_binding_plan=(
                    self.step.compiler_prompt_attempt_binding_plan
                ),
            )

        resolved_consumes = self.state.get("_resolved_consumes", {})

        def finish(candidate_prompt: str) -> str:
            before_contract = (
                self.executor.prompt_composer
                .apply_consumes_prompt_injection_with_trace(
                    self.step,
                    candidate_prompt,
                    resolved_consumes=(
                        resolved_consumes
                        if isinstance(resolved_consumes, dict)
                        else {}
                    ),
                    step_name=self.step_name,
                    consume_identity=self.runtime_step_id,
                    uses_qualified_identities=(
                        self.executor._uses_qualified_identities()
                    ),
                )
            )
            completed = (
                self.executor.prompt_composer
                .apply_output_contract_prompt_suffix_with_trace(
                    self.prompt_contract_step,
                    before_contract,
                )
            )
            self.runtime_contribution_rows = (
                validate_runtime_contribution_composition(completed)
            )
            self.cut = (
                self.executor.prompt_composer
                .apply_output_contract_prompt_suffix_with_cut(
                    self.prompt_contract_step,
                    before_contract.prompt,
                )
            )
            if completed.prompt.encode("utf-8") != self.cut.canonical_composed:
                raise ValueError("phased prompt cut changed canonical rendering")
            return completed.prompt

        dependency_contract = (
            self.executor._compiler_prompt_dependency_contract(self.step)
        )
        if dependency_contract is None:
            raise ValueError(
                "phased delivery requires compiler dependency carriage"
            )
        variables = runtime_context.build_variables(
            self.executor.variable_substitutor,
            self.state,
        )
        depends_on = self.step.get("depends_on", {})
        resolution = self.executor._resolve_typed_content_dependencies(
            contract=dependency_contract,
            depends_on=depends_on,
            variables=variables,
        )
        if not resolution.is_valid:
            raise ValueError("phased prompt dependencies are unresolved")
        snapshot = snapshot_content_dependencies(
            self.executor.workspace,
            resolution.classified_rows,
        )
        inject = depends_on.get("inject", {})
        if not isinstance(inject, dict):
            raise ValueError("phased dependency injection is invalid")
        instruction = inject.get(
            "instruction",
            self.executor.dependency_injector._get_default_instruction(
                "content",
                bool(dependency_contract.required_binding_refs),
            ),
        )
        if not dependency_contract.required_binding_refs:
            instruction = ""
        instruction_source = (
            "authored"
            if dependency_contract.instruction_utf8_sha256_or_null is not None
            else (
                "default_required"
                if dependency_contract.required_binding_refs
                else (
                    "default_optional"
                    if dependency_contract.optional_binding_refs
                    else "none"
                )
            )
        )

        def render_owner(compose_final_prompt):
            owner = resolve_aggregate_run_owner(
                self.executor.state_manager
            )
            run_state = owner.root_manager.state
            if run_state is None:
                raise RuntimeError("aggregate root state is missing")
            return build_fragment_success_evidence(
                run_state=run_state,
                scope=allocation.scope,
                ordinal=allocation.attempt_ordinal,
                compiler_contract=dependency_contract,
                compiled_prompt_fragment_identity=fragment_identity,
                snapshot=snapshot,
                instruction=instruction,
                instruction_source=instruction_source,
                compose_final_prompt=compose_final_prompt,
            )

        composition = (
            self.executor.prompt_composer.compose_content_dependency_attempt(
                base_prompt=rendered.rendered_base,
                snapshot=snapshot,
                instruction=instruction,
                position=dependency_contract.position.value,
                finish_prompt=finish,
                render_owner=render_owner,
            )
        )
        self.retained_fragment_v1 = (
            composition.render_owner_result.evidence
        )
        if self.cut is None:
            raise ValueError("phased prompt cut was not retained")
        return self.cut

    def compose_attempt(self, allocation, *, deadline: float):
        from .bindings import PhasedOperationFailure

        try:
            return self._compose_attempt(allocation, deadline=deadline)
        except PhasedOperationFailure:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise PhasedOperationFailure(
                self._diagnostic("preparation_failed")
            ) from exc

    def _compose_attempt(self, allocation, *, deadline: float):
        from ...providers.types import ProviderParams
        from .bindings import AttemptComposition
        from .frames import (
            render_initial_materialization_turn,
            render_task_turn,
        )
        from .protocol import (
            PHASED_PROVIDER_BINDING_ENV,
            derive_submit_binding_and_locator,
        )

        self._resolve_contract_paths()
        cut = self._render_fragment_and_cut(allocation)
        task_turn = render_task_turn(cut=cut)
        provider_context = self.executor._create_provider_context(
            self.context,
            self.state,
            parent_steps=self.parent_steps,
            self_steps=self.self_steps,
            root_steps=self.root_steps,
        )
        provider_name, provider_error = (
            self.executor._resolve_provider_name_for_step(
                self.step,
                provider_context,
            )
        )
        if provider_error is not None or provider_name is None:
            raise ValueError(str(provider_error))
        provider = self.executor.provider_registry.get(provider_name)
        support = getattr(provider, "interactive_session_support", None)
        if support is None:
            raise ValueError("interactive provider support disappeared")
        nonce = (
            allocation.scope.key[7:31]
            + f"{allocation.attempt_ordinal:06d}"
        )
        submit_binding, locator = derive_submit_binding_and_locator(
            attempt_scope_sha256=allocation.scope.key,
            socket_root=Path("/tmp"),
            nonce=nonce,
            deadline=deadline,
        )
        env = self.executor._provider_env_with_runtime_output_bundle_path(
            self.step,
            self.resolved_output_bundle,
        ) or {}
        env = dict(env)
        env[PHASED_PROVIDER_BINDING_ENV] = submit_binding.opaque_value
        params = ProviderParams(
            params=self.step.get("provider_params", {}),
            input_file=self.step.get("input_file"),
            output_file=self.step.get("output_file"),
        )
        invocation, error = (
            self.executor.provider_executor.prepare_interactive_invocation(
                provider_name=provider_name,
                params=params.params,
                context=provider_context,
                prompt_content=task_turn.delivered_turn.decode("utf-8"),
                invocation_id=(
                    f"{allocation.scope.key}:"
                    f"{allocation.attempt_ordinal}"
                ),
                member_id=self.runtime_step_id,
                attempt_scope_key=allocation.scope.key,
                attempt_ordinal=allocation.attempt_ordinal,
                cwd=self.executor.workspace,
                env=env,
                timeout_sec=self.step.get("timeout_sec", 3600),
                provider_call_policy=self._policy_dict(
                    self.provider_bound_policy
                ),
            )
        )
        if error is not None or invocation is None:
            raise ValueError(str(error))
        prepared_policy = invocation.prepared_provider_policy
        if prepared_policy is None:
            raise ValueError("prepared provider policy projection is missing")
        pre_prompt_command = invocation.pre_prompt_command
        if pre_prompt_command is None:
            raise ValueError(
                "prepared provider pre-prompt command is missing"
            )
        self.resolved_provider_policy = {
            key: value
            for key, value in prepared_policy.to_dict().items()
            if key != "input_mode"
        }
        self.resolved_provider_policy.update(
            {
                "transport": {
                    "kind": "interactive_terminal_turn_queue",
                    "schema_version": (
                        INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION
                    ),
                },
                "phased_call_policy": {
                    "delivery": "phased",
                    "materialization_attempts": (
                        self.runtime_policy.materialization_attempts
                    ),
                },
            }
        )
        attempts = self.runtime_policy.materialization_attempts
        assert isinstance(attempts, int)
        initial_turn = render_initial_materialization_turn(
            cut=cut,
            submit_keys=tuple(support.message_submit_keys),
        )
        return AttemptComposition(
            cut=cut,
            materialization_attempts=attempts,
            task_turn=task_turn,
            initial_materialization_turn=initial_turn,
            pre_prompt_command=pre_prompt_command,
            invocation=invocation,
            submit_binding=submit_binding,
            endpoint_locator=locator,
            deadline=deadline,
        )

    def preflight_candidates(self, composition):
        from .bindings import (
            CandidatePathBinding,
            CandidatePreflight,
            PhasedOperationFailure,
        )

        bindings = []
        for spec in self.resolved_expected_outputs or []:
            name = spec.get("name")
            path = spec.get("path")
            if not isinstance(name, str) or not isinstance(path, str):
                raise PhasedOperationFailure(
                    self._diagnostic("preparation_failed")
                )
            bindings.append(
                CandidatePathBinding(
                    contract_ordinal=len(bindings),
                    role="expected_output",
                    logical_name=name,
                    workspace_relative_path=path,
                )
            )
        bundle_path = (
            self.resolved_output_bundle.get("path")
            if isinstance(self.resolved_output_bundle, dict)
            else None
        )
        if not isinstance(bundle_path, str):
            raise PhasedOperationFailure(
                self._diagnostic("preparation_failed")
            )
        bindings.append(
            CandidatePathBinding(
                contract_ordinal=len(bindings),
                role="structured_bundle",
                logical_name="__structured_result_bundle__",
                workspace_relative_path=bundle_path,
            )
        )
        preflight = CandidatePreflight.create(bindings=tuple(bindings))
        if self._is_exact_interrupted_rerun():
            try:
                self._discard_interrupted_candidates(preflight)
            except PhasedOperationFailure:
                raise
            except OSError as exc:
                raise PhasedOperationFailure(
                    self._diagnostic("candidate_reset_failed")
                ) from exc
        for binding in preflight.bindings:
            path = self.executor._resolve_workspace_path(
                binding.workspace_relative_path
            )
            if path is None or path.exists() or path.is_symlink():
                raise PhasedOperationFailure(
                    self._diagnostic("candidate_path_preexisting")
                )
        self.preflight = preflight
        return preflight

    def _is_exact_interrupted_rerun(self) -> bool:
        context = self._interrupted_rerun
        visits = self.state.get("step_visits")
        visit_count = (
            visits.get(self.step_name)
            if isinstance(visits, Mapping)
            else None
        )
        discarded_visit = (
            context.get("discarded_visit")
            if isinstance(context, Mapping)
            else None
        )
        next_visit = (
            context.get("next_visit")
            if isinstance(context, Mapping)
            else None
        )
        return (
            isinstance(context, Mapping)
            and context.get("diagnostic")
            == "provider_attempt_interrupted_rerun"
            and context.get("family") == "phased"
            and context.get("step_id") == self.runtime_step_id
            and not isinstance(discarded_visit, bool)
            and isinstance(discarded_visit, int)
            and discarded_visit > 0
            and not isinstance(next_visit, bool)
            and isinstance(next_visit, int)
            and next_visit == discarded_visit + 1
            and visit_count == next_visit
        )

    def _discard_interrupted_candidates(self, preflight) -> None:
        from .bindings import PhasedOperationFailure

        paths: list[Path] = []
        for binding in preflight.bindings:
            path = self.executor._resolve_workspace_path(
                binding.workspace_relative_path
            )
            if (
                path is None
                or path.is_symlink()
                or (path.exists() and not path.is_file())
            ):
                raise PhasedOperationFailure(
                    self._diagnostic("candidate_reset_failed")
                )
            paths.append(path)
        for path in paths:
            if path.exists():
                path.unlink()
        if any(path.exists() or path.is_symlink() for path in paths):
            raise PhasedOperationFailure(
                self._diagnostic("candidate_reset_failed")
            )

    def create_ledger(self, allocation, composition):
        from .ledger import (
            ProviderPromptPhaseLedgerWriter,
        )

        return ProviderPromptPhaseLedgerWriter.create(
            self.executor.state_manager.run_root,
            scope=allocation.scope,
            ordinal=allocation.attempt_ordinal,
            cut=composition.cut,
            materialization_attempts=composition.materialization_attempts,
            created_at=self.observed_at(),
        )

    def create_endpoint(self, composition):
        from .endpoint import PhasedSubmitEndpoint

        return PhasedSubmitEndpoint(
            binding=composition.submit_binding,
            locator=composition.endpoint_locator,
            configured_total=composition.materialization_attempts,
        )

    def receive_attempt_event(
        self,
        *,
        boundary: str,
        endpoint,
        deadline: float,
    ):
        from ...providers.interactive_terminal import InteractiveTerminalError
        from .bindings import SerializedAttemptEvent

        if boundary != "AWAITING_SUBMIT":
            return None
        while True:
            poll_deadline = min(deadline, time.monotonic() + 0.05)
            try:
                submit = endpoint.receive_event(deadline=poll_deadline)
            except TimeoutError:
                probe_now = time.monotonic()
                if probe_now >= deadline:
                    return SerializedAttemptEvent(kind="deadline")
                try:
                    status = self.adapter.probe_process_status(
                        deadline=min(deadline, probe_now + 0.05),
                    )
                except InteractiveTerminalError as exc:
                    if exc.code == "backend_operation_timeout":
                        if time.monotonic() >= deadline:
                            return SerializedAttemptEvent(kind="deadline")
                        continue
                    return SerializedAttemptEvent(kind="provider_exit")
                if getattr(status, "state", None) != "running":
                    return SerializedAttemptEvent(kind="provider_exit")
                continue
            return SerializedAttemptEvent(kind="submit", submit=submit)

    def _snapshot_row(self, binding):
        from .models import CandidateDigestRow

        path = self.executor._resolve_workspace_path(
            binding.workspace_relative_path
        )
        if path is None or path.is_symlink():
            presence = "invalid"
            payload = None
        elif not path.exists():
            presence = "missing"
            payload = None
        elif not path.is_file():
            presence = "invalid"
            payload = None
        else:
            presence = "regular"
            payload = path.read_bytes()
        return CandidateDigestRow(
            contract_ordinal=binding.contract_ordinal,
            role=binding.role,
            logical_name=binding.logical_name,
            workspace_relative_path=binding.workspace_relative_path,
            presence=presence,
            byte_length=None if payload is None else len(payload),
            sha256=(
                None
                if payload is None
                else "sha256:" + sha256(payload).hexdigest()
            ),
        )

    def snapshot_candidates(self, preflight, submission_ordinal: int):
        from .bindings import PhasedOperationFailure

        try:
            return self._snapshot_candidates(
                preflight,
                submission_ordinal,
            )
        except PhasedOperationFailure:
            raise
        except OSError as exc:
            raise PhasedOperationFailure(
                self._diagnostic("candidate_freeze_failed")
            ) from exc

    def _snapshot_candidates(self, preflight, submission_ordinal: int):
        from .bindings import CandidateSnapshot

        return CandidateSnapshot.create(
            preflight=preflight,
            submission_ordinal=submission_ordinal,
            rows=tuple(
                self._snapshot_row(binding)
                for binding in preflight.bindings
            ),
        )

    def validate_output_positions(self, snapshot):
        from .bindings import (
            OutputPositionValidation,
            ValidatedArtifact,
        )

        if not self._snapshot_matches(snapshot):
            return OutputPositionValidation(
                snapshot_sha256=snapshot.snapshot_sha256,
                artifacts=(),
                diagnostic=self._diagnostic(
                    "output_validation_failed",
                    canonical_value=(
                        "prompt_output_position_contract_mismatch"
                    ),
                ),
            )
        try:
            artifacts = validate_expected_outputs(
                self.executor._q2_expected_outputs_with_subjects(
                    self.step,
                    self.resolved_expected_outputs,
                )
                or [],
                workspace=self.executor.workspace,
            )
        except OutputContractError as exc:
            return OutputPositionValidation(
                snapshot_sha256=snapshot.snapshot_sha256,
                artifacts=(),
                diagnostic=self._diagnostic(
                    "output_validation_failed",
                    canonical_value=self._q2_violation_type(
                        exc,
                        fallback="invalid_output_path",
                    ),
                ),
            )
        if not self._snapshot_matches(snapshot):
            return OutputPositionValidation(
                snapshot_sha256=snapshot.snapshot_sha256,
                artifacts=(),
                diagnostic=self._diagnostic(
                    "output_validation_failed",
                    canonical_value=(
                        "prompt_output_position_contract_mismatch"
                    ),
                ),
            )
        self._validated_artifacts = artifacts
        by_name = {
            binding.logical_name: binding.workspace_relative_path
            for binding in self.preflight.bindings
            if binding.role == "expected_output"
        }
        return OutputPositionValidation(
            snapshot_sha256=snapshot.snapshot_sha256,
            artifacts=tuple(
                ValidatedArtifact(
                    logical_name=name,
                    workspace_relative_path=by_name[name],
                )
                for name in artifacts
            ),
            diagnostic=None,
        )

    def validate_structured_result(self, snapshot):
        from .bindings import (
            StructuredResultValidation,
            ValidatedStructuredResult,
        )

        if not self._snapshot_matches(snapshot):
            return StructuredResultValidation(
                snapshot_sha256=snapshot.snapshot_sha256,
                result=None,
                diagnostic=self._diagnostic(
                    "structured_result_validation_failed",
                    canonical_value="invalid_bundle_field",
                ),
            )
        try:
            resolved_output_bundle = self.resolved_output_bundle or {}
            if isinstance(self.step.get("variant_output"), dict):
                artifacts = validate_variant_output_bundle(
                    resolved_output_bundle,
                    workspace=self.executor.workspace,
                )
            else:
                artifacts = validate_output_bundle(
                    resolved_output_bundle,
                    workspace=self.executor.workspace,
                )
            bundle_path = self.executor._resolve_workspace_path(
                resolved_output_bundle["path"]
            )
            if bundle_path is None:
                raise ValueError("structured result path escaped workspace")
            payload = bundle_path.read_bytes()
        except OutputContractError as exc:
            return StructuredResultValidation(
                snapshot_sha256=snapshot.snapshot_sha256,
                result=None,
                diagnostic=self._diagnostic(
                    "structured_result_validation_failed",
                    canonical_value=self._q2_violation_type(
                        exc,
                        fallback="invalid_bundle_field",
                    ),
                ),
            )
        except KeyError:
            return StructuredResultValidation(
                snapshot_sha256=snapshot.snapshot_sha256,
                result=None,
                diagnostic=self._diagnostic(
                    "structured_result_validation_failed",
                    canonical_value="invalid_bundle_path",
                ),
            )
        except OSError:
            return StructuredResultValidation(
                snapshot_sha256=snapshot.snapshot_sha256,
                result=None,
                diagnostic=self._diagnostic(
                    "structured_result_validation_failed",
                    canonical_value="missing_bundle_file",
                ),
            )
        except ValueError:
            return StructuredResultValidation(
                snapshot_sha256=snapshot.snapshot_sha256,
                result=None,
                diagnostic=self._diagnostic(
                    "structured_result_validation_failed",
                    canonical_value="invalid_bundle_path",
                ),
            )
        if not self._snapshot_matches(snapshot):
            return StructuredResultValidation(
                snapshot_sha256=snapshot.snapshot_sha256,
                result=None,
                diagnostic=self._diagnostic(
                    "structured_result_validation_failed",
                    canonical_value="invalid_bundle_field",
                ),
            )
        self._validated_structured_artifacts = artifacts
        return StructuredResultValidation(
            snapshot_sha256=snapshot.snapshot_sha256,
            result=ValidatedStructuredResult(canonical_bundle=payload),
            diagnostic=None,
        )

    def reset_candidates(self, snapshot):
        from .bindings import PhasedOperationFailure

        try:
            return self._reset_candidates(snapshot)
        except PhasedOperationFailure:
            raise
        except OSError as exc:
            raise PhasedOperationFailure(
                self._diagnostic("candidate_reset_failed")
            ) from exc

    def _reset_candidates(self, snapshot):
        from .bindings import (
            CandidateResetResult,
            PhasedOperationFailure,
        )

        for row in snapshot.rows:
            path = self.executor._resolve_workspace_path(
                row.workspace_relative_path
            )
            if path is None:
                raise PhasedOperationFailure(
                    self._diagnostic("candidate_reset_failed")
                )
            if row.presence == "regular":
                current = self._snapshot_row(
                    self.preflight.bindings[row.contract_ordinal]
                )
                if current != row:
                    raise PhasedOperationFailure(
                        self._diagnostic("candidate_reset_failed")
                    )
                path.unlink()
            elif row.presence != "missing":
                raise PhasedOperationFailure(
                    self._diagnostic("candidate_reset_failed")
                )
        if any(
            (
                (path := self.executor._resolve_workspace_path(
                    binding.workspace_relative_path
                ))
                is None
                or path.exists()
                or path.is_symlink()
            )
            for binding in self.preflight.bindings
        ):
            raise PhasedOperationFailure(
                self._diagnostic("candidate_reset_failed")
            )
        return CandidateResetResult(
            snapshot_sha256=snapshot.snapshot_sha256,
            preflight_sha256=snapshot.preflight_sha256,
            postcondition="all_bound_paths_absent",
        )

    def _snapshot_matches(self, snapshot) -> bool:
        return tuple(
            self._snapshot_row(binding)
            for binding in self.preflight.bindings
        ) == snapshot.rows

    def freeze_candidate(self, snapshot, output, structured):
        from .bindings import PhasedOperationFailure

        try:
            return self._freeze_candidate(snapshot, output, structured)
        except PhasedOperationFailure:
            raise
        except OSError as exc:
            raise PhasedOperationFailure(
                self._diagnostic("candidate_freeze_failed")
            ) from exc

    def _freeze_candidate(self, snapshot, output, structured):
        from .bindings import (
            FrozenCandidate,
            FrozenCandidateFile,
            PhasedOperationFailure,
        )

        files = []
        for binding, row in zip(
            self.preflight.bindings,
            snapshot.rows,
            strict=True,
        ):
            path = self.executor._resolve_workspace_path(
                binding.workspace_relative_path
            )
            if path is None or not path.is_file() or path.is_symlink():
                raise PhasedOperationFailure(
                    self._diagnostic("candidate_freeze_failed")
                )
            content = path.read_bytes()
            if (
                row.presence != "regular"
                or row.byte_length != len(content)
                or row.sha256 != "sha256:" + sha256(content).hexdigest()
            ):
                raise PhasedOperationFailure(
                    self._diagnostic("candidate_freeze_failed")
                )
            files.append(
                FrozenCandidateFile(binding=binding, content=content)
            )
        return FrozenCandidate.create(
            snapshot=snapshot,
            files=tuple(files),
        )

    def publish_functional_evidence(self, frozen, actual_deliveries):
        from .bindings import PhasedOperationFailure

        try:
            return self._publish_functional_evidence(
                frozen,
                actual_deliveries,
            )
        except PhasedOperationFailure:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise PhasedOperationFailure(
                self._diagnostic("evidence_publication_failed")
            ) from exc

    def _publish_functional_evidence(self, frozen, actual_deliveries):
        from ..prompt_dependency_evidence import (
            build_fragment_success_evidence_v3,
        )
        from ..prompt_identity import (
            build_prompt_attempt_identity_v2,
            build_provider_policy_role_v2,
        )
        from .bindings import (
            FunctionalEvidencePublication,
        )

        if (
            self.retained_fragment_v1 is None
            or self.fragment_render_result is None
            or self.cut is None
            or not isinstance(self.step, RuntimeStep)
        ):
            raise ValueError("phased prompt identity preparation is incomplete")
        fragment_contract, fragment_identity = (
            self.executor._compiler_prompt_fragment_pair(self.step)
        )
        binding_plan = self.step.compiler_prompt_attempt_binding_plan
        if (
            type(fragment_contract) is not CompilerPromptFragmentContractV2
            or not isinstance(fragment_identity, str)
            or binding_plan is None
        ):
            raise ValueError("phased prompt identity carriage is incomplete")
        roles = {
            "fragment_program": build_fragment_program_role(
                identity_schema_version=(
                    "compiled_prompt_fragment_identity.v2"
                ),
                compiled_prompt_fragment_identity=fragment_identity,
            ),
            "resolved_bindings": build_resolved_bindings_role(
                binding_plan=binding_plan,
                fragment_render_result=self.fragment_render_result,
                authored_rows=self.retained_fragment_v1["authored_rows"],
            ),
            "injected_dependencies": build_injected_dependencies_role(
                canonical_groups=(
                    self.retained_fragment_v1["canonical_groups"]
                ),
                injection=self.retained_fragment_v1["injection"],
            ),
            "runtime_contributions": build_runtime_contributions_role(
                self.runtime_contribution_rows
            ),
            "provider_policy": build_provider_policy_role_v2(
                self.resolved_provider_policy
            ),
        }
        identity = build_prompt_attempt_identity_v2(
            roles=roles,
            cut=self.cut,
            actual_deliveries=actual_deliveries,
        )
        record = build_fragment_success_evidence_v3(
            retained_v1=self.retained_fragment_v1,
            cut=self.cut,
            prompt_attempt_identity=identity,
            compiler_fragment_identity_schema_version=(
                "compiled_prompt_fragment_identity.v2"
            ),
        )
        scope = self.scope
        if scope is None:
            raise ValueError("phased prompt evidence scope is incomplete")
        publication = publish_evidence_file(
            self.executor.state_manager,
            scope,
            self.allocation.attempt_ordinal,
            record,
            compiler_fragment_identity_schema_version=(
                "compiled_prompt_fragment_identity.v2"
            ),
        )
        return FunctionalEvidencePublication.create(
            frozen=frozen,
            actual_deliveries=actual_deliveries,
            relative_path=str(publication.relative_path),
            evidence_sha256=publication.file_sha256,
        )

    def restore_frozen_candidate(self, frozen):
        from .bindings import PhasedOperationFailure

        try:
            return self._restore_frozen_candidate(frozen)
        except PhasedOperationFailure:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise PhasedOperationFailure(
                self._diagnostic("frozen_restoration_failed")
            ) from exc

    def _restore_frozen_candidate(self, frozen):
        from ...state_locking import durable_atomic_write
        from .bindings import (
            FrozenCandidateRestoration,
        )

        restored = 0
        for item in frozen.files:
            path = self.executor._resolve_workspace_path(
                item.binding.workspace_relative_path
            )
            if path is None:
                raise ValueError("frozen path escaped workspace")
            durable_atomic_write(path, item.content)
            restored += 1
        return FrozenCandidateRestoration(
            frozen_sha256=frozen.frozen_sha256,
            restored_paths=restored,
        )

    def verify_frozen_candidate(self, frozen, restoration):
        from .bindings import PhasedOperationFailure

        try:
            return self._verify_frozen_candidate(frozen, restoration)
        except PhasedOperationFailure:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise PhasedOperationFailure(
                self._diagnostic("frozen_verification_failed")
            ) from exc

    def _verify_frozen_candidate(self, frozen, restoration):
        from .bindings import (
            FrozenCandidateVerification,
        )

        for item in frozen.files:
            path = self.executor._resolve_workspace_path(
                item.binding.workspace_relative_path
            )
            if (
                path is None
                or not path.is_file()
                or path.is_symlink()
                or path.read_bytes() != item.content
            ):
                raise ValueError("restored frozen candidate changed")
        return FrozenCandidateVerification(
            frozen_sha256=frozen.frozen_sha256,
            verified=True,
        )

    def prepare_success_commit(
        self,
        *,
        allocation,
        output,
        structured,
        frozen,
        evidence,
        verification,
    ):
        from .bindings import PhasedOperationFailure

        try:
            return self._prepare_success_commit(
                allocation=allocation,
                output=output,
                structured=structured,
                frozen=frozen,
                evidence=evidence,
                verification=verification,
            )
        except PhasedOperationFailure:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise PhasedOperationFailure(
                self._diagnostic("workflow_state_commit_failed")
            ) from exc

    def _prepare_success_commit(
        self,
        *,
        allocation,
        output,
        structured,
        frozen,
        evidence,
        verification,
    ):
        from .bindings import PreparedSuccessCommit

        result = {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "artifacts": {
                **self._validated_artifacts,
                **self._validated_structured_artifacts,
            },
            "debug": {
                "phased_delivery": {
                    "submission_ordinal": frozen.manifest.submission_ordinal,
                    "functional_evidence": evidence.relative_path,
                }
            },
        }
        candidate_state = deepcopy(self.state)
        publish_error = self.executor._record_published_artifacts(
            self.step,
            self.step_name,
            result,
            candidate_state,
            runtime_step_id=self.runtime_step_id,
            persist=False,
        )
        if publish_error is not None:
            raise ValueError(str(publish_error))
        finalized = self.executor._attach_outcome(self.step, result)
        finalized.setdefault("name", self.step_name)
        finalized.setdefault("step_id", self.runtime_step_id)
        visit_count = allocation.scope.enclosing_step.visit_count
        finalized.setdefault("visit_count", visit_count)
        loop_iteration = allocation.scope.loop_iteration
        result_key = self.step_name
        if loop_iteration is not None:
            result_key = (
                f"{allocation.scope.enclosing_step.step_name}"
                f"[{loop_iteration.iteration}].{self.step_name}"
            )
        candidate_state.setdefault("steps", {})[result_key] = finalized
        self.executor._finalize_consumes(
            self.step,
            self.step_name,
            candidate_state,
            succeeded=True,
            runtime_step_id=self.runtime_step_id,
            persist=False,
        )
        self._prepared_result = finalized
        self._prepared_state = candidate_state
        self._prepared_visit_count = visit_count
        return PreparedSuccessCommit(
            allocation=allocation,
            output=output,
            structured=structured,
            frozen=frozen,
            evidence=evidence,
            verification=verification,
        )

    def atomic_success_commit(self, prepared, *, deadline: float):
        from .bindings import PhasedOperationFailure

        state_snapshots = []
        manager = self.executor.state_manager
        cursor = manager
        while cursor is not None:
            manager_state = getattr(cursor, "state", None)
            if manager_state is not None and hasattr(
                manager_state,
                "to_dict",
            ):
                state_snapshots.append(
                    (cursor, deepcopy(manager_state.to_dict()))
                )
            cursor = getattr(cursor, "parent_manager", None)
        live_state_before = deepcopy(self.state)
        try:
            return self._atomic_success_commit(
                prepared,
                deadline=deadline,
            )
        except PhasedOperationFailure:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            for state_manager, snapshot in reversed(state_snapshots):
                current = getattr(state_manager, "state", None)
                if current is not None:
                    state_manager.state = type(current).from_dict(snapshot)
            self.state.clear()
            self.state.update(live_state_before)
            raise PhasedOperationFailure(
                self._diagnostic("workflow_state_commit_failed")
            ) from exc

    def _atomic_success_commit(self, prepared, *, deadline: float):
        from .bindings import (
            AtomicSuccessCommitReceipt,
        )

        if (
            self._prepared_result is None
            or not hasattr(self, "_prepared_state")
        ):
            raise RuntimeError("phased state commit was not prepared")
        prepared_state = self._prepared_state
        expected_visit_count = (
            self._prepared_visit_count
            if isinstance(self._prepared_visit_count, int)
            else None
        )
        scope = prepared.allocation.scope
        enclosing = scope.enclosing_step
        loop_iteration = scope.loop_iteration
        expected_current_type = (
            loop_iteration.kind
            if loop_iteration is not None
            else "provider"
        )

        def commit_guard() -> bool:
            return time.monotonic() < deadline

        finalize_kwargs = {
            "artifact_versions": deepcopy(
                prepared_state.get("artifact_versions", {})
            ),
            "artifact_consumes": deepcopy(
                prepared_state.get("artifact_consumes", {})
            ),
            "private_artifact_versions": deepcopy(
                prepared_state.get("private_artifact_versions", {})
            ),
            "private_artifact_consumes": deepcopy(
                prepared_state.get("private_artifact_consumes", {})
            ),
            "expected_visit_count": expected_visit_count,
            "commit_guard": commit_guard,
        }
        step_result = self.executor._to_step_result(
            self._prepared_result,
            self.step_name,
        )
        if loop_iteration is None:
            self.executor.state_manager.finalize_step_with_dataflow(
                self.step_name,
                step_result,
                expected_step_id=enclosing.step_id,
                expected_step_name=enclosing.step_name,
                expected_step_type=expected_current_type,
                expected_step_status="running",
                **finalize_kwargs,
            )
        else:
            self.executor.state_manager.finalize_loop_step_with_dataflow(
                enclosing.step_name,
                loop_iteration.iteration,
                self.step_name,
                step_result,
                expected_enclosing_step_id=enclosing.step_id,
                expected_enclosing_step_name=enclosing.step_name,
                expected_enclosing_step_type=expected_current_type,
                expected_enclosing_step_status="running",
                **finalize_kwargs,
            )
        committed_state = self.executor.state_manager.state
        if committed_state is None:
            raise RuntimeError("phased state commit lost its state owner")
        self.state.clear()
        self.state.update(committed_state.to_dict())
        committed = getattr(
            self.executor,
            "_phased_authoritative_result_ids",
            None,
        )
        if not isinstance(committed, set):
            committed = set()
            cast(Any, self.executor)._phased_authoritative_result_ids = (
                committed
            )
        committed.add(id(self._prepared_result))
        return AtomicSuccessCommitReceipt(
            evidence_sha256=prepared.evidence.evidence_sha256,
            frozen_sha256=prepared.frozen.frozen_sha256,
            status="authoritative_state_committed",
        )

    def finalize_failure(self, first_diagnostic, lifecycle) -> None:
        self._failure = (first_diagnostic, lifecycle)

    def runtime_result(self, result: Any) -> Dict[str, Any]:
        from .bindings import (
            PhasedProviderAttemptFailure,
            PhasedProviderAttemptSuccess,
        )

        if type(result) is PhasedProviderAttemptSuccess:
            if self._prepared_result is None:
                raise RuntimeError("phased success has no prepared result")
            return self._prepared_result
        if type(result) is not PhasedProviderAttemptFailure:
            raise TypeError("coordinator returned an invalid result")
        diagnostic = result.first_diagnostic
        sticky = diagnostic.reason == "interrupted_nonterminal_visit"
        return {
            "status": "failed",
            "exit_code": 1,
            "duration_ms": 0,
            "error": {
                "type": (
                    "provider_phased_interrupted_visit_quarantined"
                    if sticky
                    else diagnostic.code
                ),
                "message": diagnostic.rejected_value.summary,
                "context": {
                    "reason": diagnostic.reason,
                    "terminalization_tier": result.terminalization_tier,
                    "sticky": sticky,
                },
            },
        }
