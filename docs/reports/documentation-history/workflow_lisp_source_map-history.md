# Workflow Lisp Source Map: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_source_map.md](../../design/workflow_lisp_source_map.md).

### Compile and lowering flow

1. Structured-result contract derivation visits the resolved union definition.
2. For every `(variant, field)` declaration it creates a deterministic
   `ValidationSubjectRef` and retains that field's exact `SourceSpan` and
   compiler form path in a lowering-owned origin binding.
3. The generated contract field specification carries the subject reference
   needed for its runtime role:
   - variant-specific fields carry their one field subject;
   - shared fields carry a subject keyed by selected variant, because each
     variant declaration may have a distinct origin;
   - inactive-variant field specifications retain the inactive declaration's
     subject for forbidden-field diagnostics.
4. Lowering merges these bindings into `LoweringOriginMap` alongside existing
   workflow, step, input, output, and path subjects. The classic and WCC
   context constructors own the same mutable field-origin catalog; inline
   procedure child contexts share it rather than copying it.
5. Source-map construction emits a `contract_fields` entry for every bound
   field and validates that every persisted field subject resolves to exactly
   one origin entry.

Every lowering-owned call that attaches a derived structured-result contract
to a generated step must register the returned field-origin bindings
immediately. This includes provider, command, match, phase/resource, stdlib,
flow, scope, and value lowering paths. A derivation used only for static
projection or reusable-state analysis need not register runtime lineage unless
its payload is attached to an executable step.

Both classic lowering and WCC defunctionalization copy the shared catalog into
their independently constructed `LoweringOriginMap`. When a generated drain
workflow is cloned under an alias, the clone operation rekeys the field origins
and rewrites the embedded subject references' `workflow_name` together; it must
not rebuild only the standard validation bindings and drop custom fields.

### Runtime flow

1. The existing variant-output validator determines the active contract rule.
2. When it emits a field violation, it copies the rule's subject reference into
   the violation. Shared-field lookup uses the selected variant.
3. The executor passes serialized subjects to the compiled frontend index.
4. The index resolves the subject through `validation_subjects` and then the
   corresponding `contract_fields` origin entry.
5. The executor preserves the violation code and context and adds the resolved
   structured source origin. Multiple violations retain independent origins.
6. If resolution is impossible, the diagnostic remains valid and uses the
   existing generated-step origin when available.
