# Lowering Fork Dossier (phase_scope vs workflow_calls)

Generated for the diverged-pair migration follow-on plan.
Consolidation direction: workflow_calls owns (facade + fix-stream evidence).

## _declare_runtime_context_hidden_inputs

- phase_scope def at :484; recent history: ['d7bf3865 2026-06-04 refactor: split lowering owner families']
- workflow_calls def at :210; recent history: ['e692f635 2026-07-07 Move compile error constructor to lowering context leaf', '121a3b78 2026-06-20 Support carried private context for imported stdlib adapters', '5a35f913 2026-06-18 workflow-lisp: share item-ctx child phase reuse proof lane', '61f15944 2026-06-12 Land G5 structural context bootstrap', 'b53a22c4 2026-06-09 Approve private exec context bridge generalization']
- Classification: needs careful read — workflow_calls rebuilds the control flow around structural classification, bootstrap-role resolution, carried-input-source binding, and `PrivateExecContextBinding` bookkeeping (new error path `private_exec_context_bootstrap_unsupported`, new `field_path`/`carried_source_expr` resolution branches); this is not additive defaulting over the same code path, it is a distinct algorithm that happens to produce the phase_scope result as one case.

```diff
--- phase_scope
+++ workflow_calls
@@ -1,39 +1,192 @@
 def _declare_runtime_context_hidden_inputs(
     *,
-    context: _LoweringContext,
+    context: Any,
     param_name: str,
     param_type: RecordTypeRef,
     requirement: PromotedEntryHiddenContextRequirement,
     source_expr: Any,
+    source_param_name: str | None = None,
+    bridge_class: str = "runtime_owned_context",
+    binding_id: str | None = None,
+    generated_name: str | None = None,
+    carried_input_sources: Mapping[str, tuple[str, ...]] | None = None,
+    carried_source_expr: Any | None = None,
+    local_values: Mapping[str, Any] | None = None,
 ) -> dict[str, Any]:
     """Declare runtime-owned hidden inputs for one omitted promoted-entry context param."""
 
-    origin = _origin_from_context_source(context, source_expr)
-    with_bindings: dict[str, Any] = {}
-    for flattened_field in derive_workflow_boundary_fields(
-        param_type,
-        generated_name=param_name,
-        source_path=(param_name,),
-        span=origin.span,
-        form_path=origin.form_path,
-    ):
-        contract_definition = dict(flattened_field.contract_definition)
+    structural_classification = classify_structural_private_exec_context(param_type)
+    origin = lowering_core._origin_from_context_source(context, source_expr)
+    binding_id = binding_id or param_name
+    generated_name = generated_name or param_name
+    callee_fields = tuple(
+        derive_workflow_boundary_fields(
+            param_type,
+            generated_name=param_name,
+            source_path=(param_name,),
+            span=origin.span,
+            form_path=origin.form_path,
+        )
+    )
+    generated_fields = tuple(
+        derive_workflow_boundary_fields(
+            param_type,
+            generated_name=generated_name,
+            source_path=(param_name,),
+            span=origin.span,
+            form_path=origin.form_path,
+        )
+    )
+    prepared_fields: list[tuple[FlattenedContractField, FlattenedContractField]] = []
+    for callee_field, generated_field in zip(callee_fields, generated_fields, strict=True):
+        if callee_field.source_path != generated_field.source_path:
+            raise _compile_error(
+                code="workflow_boundary_type_invalid",
+                message=(
+                    f"generated hidden binding for `{binding_id}` changed source-path ordering "
+                    "for a private executable context field"
+                ),
+                span=source_expr.span,
+                form_path=source_expr.form_path,
+            )
+        contract_definition = dict(generated_field.contract_definition)
         default_value = _runtime_context_default_value(
             requirement=requirement,
-            source_path=flattened_field.source_path,
+            source_path=generated_field.source_path,
         )
         if default_value is not None:
             contract_definition["default"] = default_value
+        prepared_fields.append(
+            (
+                callee_field,
+                FlattenedContractField(
+                    generated_name=generated_field.generated_name,
+                    source_path=generated_field.source_path,
+                    contract_definition=contract_definition,
+                ),
+            )
+        )
+
+    normalized_carried_input_sources = {
+        str(name): tuple(str(part) for part in source_path)
+        for name, source_path in (carried_input_sources or {}).items()
+        if isinstance(name, str) and isinstance(source_path, (tuple, list))
+    }
+    input_roles: dict[str, str] = {}
+    missing_non_bootstrapable_fields: list[str] = []
+    for callee_field, flattened_field in prepared_fields:
+        role = (
+            _bootstrap_role_for_field(
+                source_path=flattened_field.source_path,
+                contract_definition=flattened_field.contract_definition,
+                anchors=structural_classification.anchors,
+            )
+            if structural_classification is not None
+            else None
+        )
+        if role is not None:
+            input_roles[flattened_field.generated_name] = role
+            continue
+        if callee_field.generated_name in normalized_carried_input_sources:
+            continue
+        missing_non_bootstrapable_fields.append(flattened_field.generated_name)
+    if (
+        missing_non_bootstrapable_fields
+        and not private_exec_context_bootstrap_supported(requirement.context_kind)
+    ):
+        unsupported_input_name = next(
+            iter(missing_non_bootstrapable_fields),
+            None,
+        )
+        raise _compile_error(
+            code="private_exec_context_bootstrap_unsupported",
+            message=(
+                f"promoted-entry hidden binding for `{param_name}` requires unsupported "
+                f"private executable context `{requirement.context_kind}`"
+                + (
+                    f"; generated input `{unsupported_input_name}` has no run-anchor role or compile-time default"
+                    if unsupported_input_name is not None
+                    else ""
+                )
+            ),
+            span=source_expr.span,
+            form_path=source_expr.form_path,
+        )
+
+    with_bindings: dict[str, Any] = {}
+    generated_input_names: list[str] = []
+    for callee_field, flattened_field in prepared_fields:
         context.internal_generated_input_contracts.setdefault(
             flattened_field.generated_name,
-            contract_definition,
+            dict(flattened_field.contract_definition),
         )
         context.generated_input_spans.setdefault(flattened_field.generated_name, origin)
         context.internal_generated_input_reasons.setdefault(
             flattened_field.generated_name,
-            "runtime_owned_context",
+            bridge_class,
         )
-        with_bindings[flattened_field.generated_name] = {
-            "ref": f"inputs.{flattened_field.generated_name}",
+        generated_input_names.append(flattened_field.generated_name)
+        carried_source_path = normalized_carried_input_sources.get(
+            callee_field.generated_name
+        )
+        if (
+            isinstance(carried_source_path, tuple)
+            and local_values is not None
+            and len(carried_source_path) > 1
+        ):
+            field_path = tuple(str(part) for part in carried_source_path[1:])
+            if carried_source_expr is not None:
+                with_bindings[callee_field.generated_name] = _render_call_binding_ref(
+                    carried_source_expr,
+                    local_values=local_values,
+                    field_path=field_path,
+                )
+                continue
+            if source_param_name is not None and source_param_name in local_values:
+                carried_value = _resolve_nested_local_value(
+                    local_values[source_param_name],
+                    field_path,
+                )
+                with_bindings[callee_field.generated_name] = lowering_core._render_call_binding_leaf_ref(
+                    carried_value,
+                    source_expr=source_expr,
+                )
+                continue
+        with_bindings[callee_field.generated_name] = {"ref": f"inputs.{flattened_field.generated_name}"}
+    projection_hints: dict[str, Any] = {}
+    if input_roles or normalized_carried_input_sources:
+        projection_hints["context_binding_schema_version"] = 1
+    if input_roles:
+        projection_hints["context_input_roles"] = dict(input_roles)
+    if normalized_carried_input_sources:
+        projection_hints["carried_input_sources"] = {
+            flattened_field.generated_name: tuple(
+                normalized_carried_input_sources[callee_field.generated_name]
+            )
+            for callee_field, flattened_field in prepared_fields
+            if callee_field.generated_name in normalized_carried_input_sources
         }
+
+    binding_record = PrivateExecContextBinding(
+        binding_id=binding_id,
+        source_param_name=source_param_name or param_name,
+        context_family=requirement.context_kind,
+        bridge_class=bridge_class,
+        generated_input_names=tuple(generated_input_names),
+        required_capabilities=(
+            structural_classification.derived_capabilities
+            if structural_classification is not None
+            else private_exec_context_capabilities(requirement.context_kind)
+        ),
+        derived_phase_identity=requirement.phase_name,
+        projection_hints=projection_hints,
+        source_provenance={
+            "workflow_name": context.workflow_name,
+            "path": str(origin.span.start.path),
+            "line": origin.span.start.line,
+            "form_path": list(origin.form_path),
+        },
+    )
+    if binding_record not in context.private_exec_context_bindings:
+        context.private_exec_context_bindings.append(binding_record)
     return with_bindings
```

## _managed_inputs_from_bundle

- phase_scope def at :525; recent history: ['d7bf3865 2026-06-04 refactor: split lowering owner families']
- workflow_calls def at :404; recent history: ['d7bf3865 2026-06-04 refactor: split lowering owner families', '57fed20d 2026-06-04 refactor: split lowering effects and workflow calls']
- Classification: superset-merge onto workflow_calls — the only change is the parameter annotation loosening from `LoadedWorkflowBundle | None` to `Any`; the function body is byte-identical, so phase_scope's behavior is fully preserved.

```diff
--- phase_scope
+++ workflow_calls
@@ -1,3 +1,3 @@
-def _managed_inputs_from_bundle(bundle: LoadedWorkflowBundle | None) -> tuple[str, ...]:
+def _managed_inputs_from_bundle(bundle: Any) -> tuple[str, ...]:
     """Return generated write-root inputs declared by an imported bundle."""
 
```

## _managed_write_root_bindings

- phase_scope def at :561; recent history: ['d7bf3865 2026-06-04 refactor: split lowering owner families']
- workflow_calls def at :824; recent history: ['23d9e845 2026-06-08 Add Workflow Lisp generated path allocation foundation', 'd7bf3865 2026-06-04 refactor: split lowering owner families', '57fed20d 2026-06-04 refactor: split lowering effects and workflow calls']
- Classification: superset-merge onto workflow_calls — adds two optional keyword params (`context`, `source_expr`, default `None`) that gate a new early-return branch calling `allocate_reusable_call_write_root`; when both are omitted (phase_scope's call shape), execution falls through unchanged to the original base-segments body, so phase_scope's existing behavior survives.

```diff
--- phase_scope
+++ workflow_calls
@@ -1,4 +1,6 @@
 def _managed_write_root_bindings(
     *,
+    context: Any | None = None,
+    source_expr: Any | None = None,
     caller_workflow_name: str,
     call_step_name: str,
@@ -7,6 +9,15 @@
     iteration_scope: str | None = None,
 ) -> dict[str, str]:
-    """Allocate deterministic caller-owned write-root bindings for one call site."""
-
+    if context is not None and source_expr is not None:
+        return {
+            managed_input: allocate_reusable_call_write_root(
+                context=context,
+                source_expr=source_expr,
+                call_step_name=call_step_name,
+                callee_name=callee_name,
+                managed_input_name=managed_input,
+            ).concrete_path_template
+            for managed_input in sorted(managed_inputs)
+        }
     base_segments = [
         ".orchestrate/workflow_lisp/calls",
```

## _managed_write_root_requirements_for_callable

- phase_scope def at :533; recent history: ['d7bf3865 2026-06-04 refactor: split lowering owner families']
- workflow_calls def at :798; recent history: ['e692f635 2026-07-07 Move compile error constructor to lowering context leaf', 'd7bf3865 2026-06-04 refactor: split lowering owner families', '57fed20d 2026-06-04 refactor: split lowering effects and workflow calls']
- Classification: superset-merge onto workflow_calls — only parameter type annotations are loosened (`LoweredWorkflow | None` to `Any`, `SourceSpan` untyped) and the docstring is dropped; the `if lowered_callee is not None:` body and all downstream logic are unchanged.

```diff
--- phase_scope
+++ workflow_calls
@@ -1,11 +1,9 @@
 def _managed_write_root_requirements_for_callable(
     *,
-    lowered_callee: LoweredWorkflow | None,
-    imported_bundle: LoadedWorkflowBundle | None,
-    span: SourceSpan,
+    lowered_callee: Any,
+    imported_bundle: Any,
+    span,
     form_path: tuple[str, ...],
 ) -> tuple[str, ...]:
-    """Return deterministic managed write-root inputs for one callable boundary."""
-
     if lowered_callee is not None:
         managed_projection_inputs = tuple(
```

## _render_argv_tail

- phase_scope def at :656; recent history: ['d7bf3865 2026-06-04 refactor: split lowering owner families']
- workflow_calls def at :430; recent history: ['d7bf3865 2026-06-04 refactor: split lowering owner families', '57fed20d 2026-06-04 refactor: split lowering effects and workflow calls']
- Classification: superset-merge onto workflow_calls — the explicit accumulator loop is rewritten as an equivalent list comprehension over the same `_render_scalar_expr` call; no behavioral difference for any input.

```diff
--- phase_scope
+++ workflow_calls
@@ -2,6 +2,3 @@
     """Render frontend command arguments after a stable command prefix."""
 
-    rendered: list[str] = []
-    for expr in argv:
-        rendered.append(_render_scalar_expr(expr, local_values=local_values))
-    return rendered
+    return [_render_scalar_expr(expr, local_values=local_values) for expr in argv]
```

## _render_boolean_predicate

- phase_scope def at :665; recent history: ['d7bf3865 2026-06-04 refactor: split lowering owner families']
- workflow_calls def at :450; recent history: ['e692f635 2026-07-07 Move compile error constructor to lowering context leaf', 'd7bf3865 2026-06-04 refactor: split lowering owner families', '57fed20d 2026-06-04 refactor: split lowering effects and workflow calls']
- Classification: superset-merge onto workflow_calls — the terminal `else: raise ...` is de-indented to an unconditional `raise` after the preceding branches (which already return), a pure style change with identical reachability and the same `_compile_error` raised on the same condition.

```diff
--- phase_scope
+++ workflow_calls
@@ -22,9 +22,8 @@
             local_values=local_values,
         )
-    else:
-        raise _compile_error(
-            code="workflow_return_not_exportable",
-            message="boolean guards must lower from literals or workflow inputs/refs",
-            span=expr.span,
-            form_path=expr.form_path,
-        )
+    raise _compile_error(
+        code="workflow_return_not_exportable",
+        message="boolean guards must lower from literals or workflow inputs/refs",
+        span=expr.span,
+        form_path=expr.form_path,
+    )
```

## _render_call_binding_ref

- phase_scope def at :697; recent history: ['d7bf3865 2026-06-04 refactor: split lowering owner families']
- workflow_calls def at :1511; recent history: ['d7bf3865 2026-06-04 refactor: split lowering owner families']
- Classification: superset-merge onto workflow_calls — the docstring is trimmed and the two internal calls (`_resolve_expr_local_value`, `_render_call_binding_leaf_ref`) are qualified through `lowering_core.` instead of bare names; same functions, same field_path/local_values handling, no logic change.

```diff
--- phase_scope
+++ workflow_calls
@@ -5,12 +5,8 @@
     field_path: tuple[str, ...] = (),
 ) -> Any:
-    """Render one frontend expression as a `call.with` binding value.
+    """Render one frontend expression as a `call.with` binding value."""
 
-    Structured records are flattened at workflow boundaries, so `field_path`
-    selects the specific leaf needed for one generated `with` entry.
-    """
-
-    value = _resolve_expr_local_value(expr, local_values=local_values)
+    value = lowering_core._resolve_expr_local_value(expr, local_values=local_values)
     if field_path:
         value = _resolve_nested_local_value(value, field_path)
-    return _render_call_binding_leaf_ref(value, source_expr=expr)
+    return lowering_core._render_call_binding_leaf_ref(value, source_expr=expr)
```

## _render_record_call_bindings

- phase_scope def at :715; recent history: ['d7bf3865 2026-06-04 refactor: split lowering owner families']
- workflow_calls def at :1525; recent history: ['d7bf3865 2026-06-04 refactor: split lowering owner families']
- Classification: superset-merge onto workflow_calls — `RecordExpr` and `_inline_expr_field_value` are referenced via the `lowering_core.` qualifier instead of a bare/local import; the `isinstance`/branch structure and returned values are otherwise identical to phase_scope.

```diff
--- phase_scope
+++ workflow_calls
@@ -14,9 +14,9 @@
         if isinstance(resolved_value, Mapping):
             leaf_value = _resolve_nested_local_value(resolved_value, field_path)
-        elif isinstance(resolved_value, RecordExpr):
+        elif isinstance(resolved_value, lowering_core.RecordExpr):
             leaf_source_expr = _record_expr_value_at_path(resolved_value, field_path)
             leaf_value = _resolve_inline_expr_value(leaf_source_expr, local_values=local_values)
         else:
-            leaf_value = _inline_expr_field_value(
+            leaf_value = lowering_core._inline_expr_field_value(
                 value_expr,
                 field_path=field_path,
```

## _runtime_context_default_value

- phase_scope def at :460; recent history: ['d7bf3865 2026-06-04 refactor: split lowering owner families']
- workflow_calls def at :179; recent history: ['61f15944 2026-06-12 Land G5 structural context bootstrap', 'd7bf3865 2026-06-04 refactor: split lowering owner families', '57fed20d 2026-06-04 refactor: split lowering effects and workflow calls']
- Classification: needs careful read — phase_scope treats bare `(param_name, "state-root")`/`(param_name, "artifact-root")` unconditionally as RUN-family paths (returning `"state/run"`/`"artifacts/run"`), which shadows its own later PHASE-family branches for those exact bare tuples (dead code). workflow_calls only takes that shortcut when `requirement.context_kind == RUN_CONTEXT_NAME`; for PHASE-kind requirements the same bare path now falls through to the phase-specific branch and returns `f"state/{phase_name}"`/`f"artifacts/{phase_name}"` instead. That is a genuine output change for a reachable PHASE-kind input, not just added defaulting — needs confirmation that phase_scope's dead branch was in fact a latent bug rather than depended-upon behavior before merging.

```diff
--- phase_scope
+++ workflow_calls
@@ -6,10 +6,17 @@
     param_name = requirement.param_name
     phase_name = requirement.phase_name
-    if source_path == (param_name, "run", "run-id") or source_path == (param_name, "run-id"):
+    if source_path == (param_name, "run", "run-id"):
         return None
-    if source_path == (param_name, "run", "state-root") or source_path == (param_name, "state-root"):
+    if source_path == (param_name, "run", "state-root"):
         return "state/run"
-    if source_path == (param_name, "run", "artifact-root") or source_path == (param_name, "artifact-root"):
+    if source_path == (param_name, "run", "artifact-root"):
         return "artifacts/run"
+    if requirement.context_kind == RUN_CONTEXT_NAME:
+        if source_path == (param_name, "run-id"):
+            return None
+        if source_path == (param_name, "state-root"):
+            return "state/run"
+        if source_path == (param_name, "artifact-root"):
+            return "artifacts/run"
     if requirement.context_kind != PHASE_CONTEXT_NAME or phase_name is None:
         return None
```


---

# Appendix: Task 5 — `lowering_core.<name>` classification table (regenerated 2026-07-07)

Regenerated at Task 5 execution time per the plan's Step 1 script (`re.findall(r'lowering_core\.(\w+)', src)`
over every `orchestrator/workflow_lisp/lowering/*.py`). The Task 5 brief's inventory header (12 modules,
~120 forwarders, per-module forwarder counts) was captured before Tasks 1-4 landed; this table supersedes
it. Ownership below traces through the package's re-export facades (`control.py` re-exports
`control_dispatch`/`control_loops`/`control_match`; `phase_impl.py` re-exports `phase_scope`; `phase_stdlib.py`
wraps `phase_drain`/`phase_flow`/`phase_resource`/`phase_scope`) rather than stopping at the first `def` grep
hit, since several of those hits are themselves `*args, **kwargs` forwarder stubs.

## Raw regenerated inventory (module -> distinct `lowering_core.<name>` uses)

```json
{
 "control_dispatch.py": ["_binding_type_for_expr", "_conditional_case_outputs", "_conditional_output_refs", "_infer_inline_binding_type", "_inline_output_refs_for_expr", "_lower_backlog_drain", "_lower_call_expr", "_lower_command_result", "_lower_composed_with_phase", "_lower_conditional_branch_expr", "_lower_finalize_selected_item", "_lower_produce_one_of", "_lower_record_expr", "_lower_resource_transition", "_lower_resume_or_start", "_lower_run_provider_phase", "_lower_union_variant_expr", "_lower_with_phase", "_normalize_generated_step_id", "_output_contracts_for_type", "_resolved_proc_ref_value"],
 "control_loops.py": ["_normalize_generated_step_id", "_render_repeat_until_max_iterations", "_resolve_lowering_expr_type", "classify_condition_expr", "derive_workflow_boundary_fields", "render_condition_predicate"],
 "control_match.py": ["_boundary_placeholder_literals", "_conditional_case_outputs", "_conditional_output_refs", "_lower_conditional_branch_expr", "_normalize_generated_step_id", "_output_contracts_for_type", "_surface_contract_from_structured_field", "_union_output_contracts"],
 "drain_terminal.py": ["_materialize_values_step", "_normalize_generated_step_id", "_origin_from_context_source", "_record_step_origin"],
 "effects.py": ["PromptExtern", "ProviderExtern", "_build_phase_prompt_input_prelude", "_build_phase_stdlib_prompt_input_prelude", "_normalize_generated_step_id", "_origin_from_context_source", "_phase_prompt_inputs_are_direct", "_prompt_source_step_fields", "_record_output_refs", "_record_step_origin", "_render_argv_tail", "_resolve_inline_expr_value", "_template_for_ref", "_uses_legacy_phase_prompt_input_prelude"],
 "materialize_view.py": ["_normalize_generated_step_id"],
 "phase_drain.py": ["_compile_error", "_conditional_case_ref", "_declare_runtime_context_hidden_inputs", "_flatten_boundary_leaf_paths", "_join_ref_path", "_lower_call_expr", "_lower_expression", "_materialize_values_step", "_normalize_generated_step_id", "_normalize_union_field_path", "_origin_from_context_source", "_phase_target_inline_ref", "_prompt_source_replace_kwargs", "_record_expr_value_at_path", "_record_missing_step_origins", "_record_output_refs", "_record_step_origin", "_render_boolean_predicate", "_render_call_binding_leaf_ref", "_render_call_binding_ref", "_render_record_call_bindings", "_resolve_nested_local_value", "_rewrite_prompt_source_mapping", "_union_variant_expr_value_at_path"],
 "phase_flow.py": ["_assign_nested_local_value", "_conditional_case_ref", "_flatten_boundary_leaf_paths", "_join_ref_path", "_lower_call_expr", "_lower_expression", "_materialize_values_step", "_normalize_generated_step_id", "_normalize_union_field_path", "_origin_from_context_source", "_phase_target_inline_ref", "_prompt_source_step_fields", "_record_expr_value_at_path", "_record_missing_step_origins", "_record_output_refs", "_record_step_origin", "_render_boolean_predicate", "_render_call_binding_ref", "_render_record_call_bindings", "_resolve_nested_local_value", "_union_variant_expr_value_at_path"],
 "phase_resource.py": ["_conditional_case_ref", "_flatten_boundary_leaf_paths", "_join_ref_path", "_lower_call_expr", "_lower_expression", "_materialize_values_step", "_normalize_generated_step_id", "_normalize_union_field_path", "_origin_from_context_source", "_phase_target_inline_ref", "_record_expr_value_at_path", "_record_missing_step_origins", "_record_output_refs", "_record_step_origin", "_render_boolean_predicate", "_render_call_binding_ref", "_render_record_call_bindings", "_resolve_nested_local_value", "_union_variant_expr_value_at_path"],
 "phase_scope.py": ["_conditional_case_ref", "_flatten_boundary_leaf_paths", "_lower_call_expr", "_lower_expression", "_materialize_values_step", "_normalize_generated_step_id", "_normalize_union_field_path", "_origin_from_context_source", "_phase_target_inline_ref", "_record_expr_value_at_path", "_record_missing_step_origins", "_record_output_refs", "_record_step_origin", "_resolve_nested_local_value", "_union_variant_expr_value_at_path"],
 "values.py": ["_materialize_values_step", "_normalize_generated_step_id", "_surface_contract_from_structured_field"],
 "workflow_calls.py": ["RecordExpr", "_inline_expr_field_value", "_normalize_generated_step_id", "_origin_from_context_source", "_record_step_origin", "_resolve_expr_local_value", "_resolved_workflow_ref_value"]
}
```

Note: `workflow_calls.py` has zero self-round-trips (no `lowering_core.<name>` use where `<name>` is also
defined by `workflow_calls.py` itself), confirming Task 4's five self-round-trip removals held.

## Bucket 1 — owner-import (replace `lowering_core.<name>` with a direct `from .<owner> import <name>`)

True owner traced past facade modules (`control.py`, `phase_impl.py`, `phase_stdlib.py` are pure
re-export/thin-wrapper shims, not owners):

| Name | True owner module | Notes |
| --- | --- | --- |
| `_lower_expression` | `control_dispatch.py` (`_control_lower_expression_impl`) | dispatcher body; see Bucket 2 re: why it is *also* a context-callable |
| `_lower_if_expr`, `_lower_let_star`, `_is_inline_let_binding_expr` | `control_dispatch.py` | |
| `_conditional_case_ref`, `_materialize_values_step`, `_inline_procedure_step_prefix`, `_lower_loop_recur` | `control_loops.py` | `_materialize_values_step` real body at `control_loops.py:73`; all other same-name defs elsewhere are stub forwarders |
| `_resolve_lowering_expr_type` | `core.py` (real body, `core.py:1935`) — `control_loops.py`'s copy is a stub | stays core-owned; not a leaf owner-import |
| `_binding_terminal_for_inline_match`, `_binding_terminal_for_match_subject`, `_build_match_projection_anchor_step`, `_lower_binding_match_expr`, `_match_arm_local_values` | `control_match.py` | reached via `.control` facade in core.py's import list; not directly in the regenerated `lowering_core.` grep output but relevant to Task 6-8 since core re-exports them |
| `_lower_call_expr` | `workflow_calls.py:950` | see Bucket 2 — also a context-callable |
| `_render_argv_tail`, `_render_boolean_predicate`, `_render_call_binding_ref`, `_render_call_binding_leaf_ref`, `_render_record_call_bindings`, `_render_repeat_until_max_iterations`, `_declare_runtime_context_hidden_inputs` | `workflow_calls.py` | |
| `_lower_with_phase`, `_lower_composed_with_phase`, `_resolved_workflow_ref_value`, `_resolved_proc_ref_value`, `_build_phase_prompt_input_prelude`, `_build_phase_stdlib_prompt_input_prelude`, `_phase_prompt_inputs_are_direct`, `_uses_legacy_phase_prompt_input_prelude`, `_union_output_contracts` | `phase_scope.py` | reached via `phase_impl.py`/`phase_stdlib.py` facades |
| `_join_ref_path` | `phase_scope.py:2052` (also duplicated verbatim at `phase_flow.py:1569`) | two independent real bodies, same text — dedupe candidate for Tasks 6-8, not just a forwarder swap |
| `_template_for_ref` | duplicated real bodies in `core.py:1762`, `phase_scope.py:114`, `phase_drain.py:139`, `phase_flow.py:114`, `phase_resource.py:114` | core's copy is what `lowering_core._template_for_ref` resolves to; the other four are dead/duplicate real bodies, not forwarders — flag for Tasks 6-8 cleanup, not a clean single-owner swap |
| `_surface_contract_from_structured_field` | dual owners: `phase_scope.py:1968` and `phase_stdlib.py:29` (independent real bodies, same text) | site-dependent: `control_match.py`'s forwarder and `values.py`'s forwarder both point at `lowering_core.` which resolves to whichever core imports (core imports the `phase_stdlib` copy per `phase_stdlib import ... review_loop_result_*` block) |
| `_lower_run_provider_phase`, `_lower_produce_one_of`, `_lower_resume_or_start` | `phase_flow.py` | reached via `phase_stdlib.py` wrapper |
| `_lower_resource_transition`, `_lower_finalize_selected_item` | `phase_resource.py` | reached via `phase_stdlib.py` wrapper |
| `_lower_backlog_drain` | `phase_drain.py` | reached via `phase_stdlib.py` wrapper |
| `_record_step_origin`, `_record_missing_step_origins`, `_origin_from_context_source` | `origins.py` | most modules (`values.py`, `control_dispatch.py`, `control_match.py`, `control_loops.py`, `materialize_view.py`, `pure_projection.py`) already import these directly from `.origins`; only `phase_drain.py`, `phase_flow.py`, `phase_resource.py`, `phase_scope.py`, `effects.py`, `workflow_calls.py`, `drain_terminal.py` still route them through `lowering_core.` (drain_terminal.py's sites are frozen — see Bucket 3) |
| `_flatten_boundary_leaf_paths`, `_normalize_union_field_path`, `_record_expr_value_at_path`, `_union_variant_expr_value_at_path`, `_resolve_nested_local_value`, `_record_output_refs`, `_boundary_placeholder_literals`, `_phase_target_inline_ref`, `_assign_nested_local_value`, `_lower_record_expr`, `_lower_union_variant_expr`, `_inline_expr_field_value` | `values.py` | |
| `_resolve_expr_local_value`, `_resolve_inline_expr_value` | dual owners: `values.py` and `phase_scope.py` (independent real bodies, same signature) | site-dependent — `effects.py`'s and `workflow_calls.py`'s forwarders resolve through whichever `values.py` copy core imports; `phase_scope.py`'s own internal calls use its local copy directly (not via `lowering_core.`) |
| `_output_contracts_for_type` | dual owners: `core.py:1584` and `pure_projection.py:788` (independent real bodies) | `lowering_core._output_contracts_for_type` (used by `control_dispatch.py`, `control_match.py`) resolves to core's own copy — core-owned, not a leaf owner-import; `pure_projection.py`'s copy is currently unreferenced via `lowering_core.` |
| `_prompt_source_step_fields` | `core.py:292` (real body) | despite living in core.py, this has no mutual-recursion need — it is a pure data-shaping helper; classified owner-import-from-core, not context-callable, since nothing calls back into it recursively |
| `PromptExtern`, `ProviderExtern` | `orchestrator/workflow_lisp/workflows.py` (outside `lowering/`) | types merely re-exported by core; `effects.py` uses `lowering_core.ProviderExtern`/`lowering_core.PromptExtern` only for `isinstance` checks |
| `RecordExpr` | `orchestrator/workflow_lisp/expressions.py` (outside `lowering/`) | type only, re-exported by core |
| `derive_workflow_boundary_fields` | `orchestrator/workflow_lisp/contracts.py` (outside `lowering/`) | re-exported by core; `control_loops.py` is the only lowering-package module still reaching it via `lowering_core.` |
| `classify_condition_expr`, `render_condition_predicate` | `orchestrator/workflow_lisp/conditionals.py` (outside `lowering/`) | re-exported by core; same pattern |

## Bucket 2 — context-callable (route through the new `_LoweringContext` fields added this task)

Per the brief's naming, the four names below are mutually recursive across the leaf/core boundary — every
leaf module that needs to recurse back into general expression lowering or call-expression lowering
currently must `import core as lowering_core` to reach them, which is exactly the fork/cycle Tasks 6-8 will
retire. These are the only names populated into `_LoweringContext` this task (fields added, left unused):

| Name | Real body location | Why context-callable, not a plain owner-import |
| --- | --- | --- |
| `_lower_expression` | `control_dispatch.py` (`_control_lower_expression_impl`) | general recursive expression dispatcher; every phase/*.py owner needs to call back into it for nested sub-expressions, which would otherwise require importing `control_dispatch` (or `core`) from every leaf, recreating the cycle |
| `_lower_call_expr` | `workflow_calls.py:950` | reached recursively from `_lower_expression`'s dispatch table and from every phase owner's inline-call handling; same cross-cycle shape |
| `_record_step_origin` | `origins.py:386` | brief names this explicitly; in practice most callers already import it directly from `.origins` (a dependency-free leaf), so after Tasks 6-8 most call sites should probably resolve as owner-import-from-origins rather than context-callable — the field exists per the brief's fixed pattern, but only `phase_drain.py`/`phase_flow.py`/`phase_resource.py`/`phase_scope.py`/`effects.py`/`workflow_calls.py`'s current `lowering_core.` sites are real candidates for routing through `context.record_step_origin`, and even those could equally take the plain owner-import fix since `origins.py` has no core dependency |
| `_normalize_generated_step_id` | `core.py:1387` (genuine core-owned body) | this is the one name of the four that is unambiguously core-owned (not a facade indirection) and used pervasively by every leaf module; core.py itself calls it internally after this task's edit via the same local name, and now also exposes it on the context for leaf callers that hold a `context` but not a `core` import |

Constructor site populated: `core.py`'s single `_LoweringContext(` call (`_lower_one_workflow`, core.py:1028)
now passes `lower_expression=_lower_expression`, `lower_call_expr=_lower_call_expr`,
`record_step_origin=_record_step_origin`, `normalize_generated_step_id=_normalize_generated_step_id`, using
the same names core.py already had in scope from its existing imports (`.control`, `.workflow_calls`,
`.origins`) and its own local definition. No call sites were converted to use `context.lower_expression(...)`
etc. this task — the fields are populated but unused, per Step 3's "fields unused so far" expectation.

## Bucket 3 — frozen (leave untouched; do not convert in Tasks 6-8)

- **`drain_terminal.py`** (all 4 names, unconditionally, per hard constraint): `_normalize_generated_step_id`,
  `_record_step_origin`, `_origin_from_context_source`, `_materialize_values_step`. All four sites are the
  module's top-of-file forwarder-stub block (`drain_terminal.py:19-32`).
- **`phase_drain.py`**, uses inside the frozen region (real lowering-logic body, not the module's own
  top-of-file forwarder-stub block at lines 108-186): `_compile_error` (lines 864, 875, 921),
  `_declare_runtime_context_hidden_inputs` (line 907), `_render_call_binding_leaf_ref` (line 955),
  `_prompt_source_replace_kwargs` (lines 2235, 2283), `_rewrite_prompt_source_mapping` (line 2320). These
  same names (`_declare_runtime_context_hidden_inputs`, etc.) are NOT frozen when they appear in other
  modules (e.g. `workflow_calls.py` owns `_declare_runtime_context_hidden_inputs` outright) — the frozen
  classification is site-specific to phase_drain.py's body, not name-wide.
  `phase_drain.py`'s own forwarder-stub block (lines 108-186, 19 stubs) is ordinary owner-import material
  for Tasks 6-8, same as any other leaf module's stub block — only the body uses (lines 592-2452,
  approximating the brief's "~592-1979" estimate) are frozen.

## Bucket counts

- Owner-import (leaf-owned, safe for a direct-import swap in Tasks 6-8, including duplicate/site-dependent
  names flagged above): 47 distinct names across `control_dispatch.py`, `control_loops.py`, `control_match.py`,
  `workflow_calls.py`, `phase_scope.py`, `phase_flow.py`, `phase_resource.py`, `phase_drain.py`, `origins.py`,
  `values.py`, `pure_projection.py`, plus 5 outside-`lowering/` re-exports (`PromptExtern`, `ProviderExtern`,
  `RecordExpr`, `derive_workflow_boundary_fields`, `classify_condition_expr`/`render_condition_predicate` —
  6 including both conditionals names).
- Context-callable (routed through new `_LoweringContext` fields this task): 4
  (`_lower_expression`, `_lower_call_expr`, `_record_step_origin`, `_normalize_generated_step_id`).
- Frozen (drain_terminal.py wholesale + phase_drain.py body-region sites): `drain_terminal.py` 4 names x 4
  sites (all uses); `phase_drain.py` 5 distinct names across 8 body-region sites (864, 875, 907, 921, 955,
  2235, 2283, 2320).
