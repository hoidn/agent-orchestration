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

