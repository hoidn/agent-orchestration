# Workflow Lisp Unified Design for Unimplemented Surfaces

Status: historical unified proposal with current deferred-design routing.
Scope: provenance for V1 local procedures, effectful composition, flat component
architecture, macros and future runtime-closure requirements. This page assigns
no supersession over accepted focused contracts and selects no implementation.

Current language and typed imports are owned by the [frontend baseline](workflow_lisp_frontend_specification.md).
[`let-proc`](workflow_lisp_let_proc_local_proc_refs.md) owns V1 through 2.35;
[W3](workflow_lisp_write_once.md#63-language-changes-to-let-proc) owns bounded
2.36 captures/bindings/signatures. [Evaluated execution](workflow_lisp_evaluated_execution.md)
owns executable composition; [macros](workflow_lisp_macro_surface_contract.md)
own their current hygienic frontend-only boundary.

Runtime closures remain disabled under the [runtime-closure boundary](workflow_lisp_runtime_closures_boundary.md).
The preserved proposal's capability-capture, transport, identity, replay,
source-map and acceptance requirements remain constraints on any separately
selected closure design; they are not an implemented runtime surface. Nested
local definitions and recursion remain excluded. Remaining effect restrictions
and authoring proposals belong to [composition first](workflow_lisp_composition_first.md)
and [effect-ledger simplification](workflow_lisp_effect_ledger_simplification.md);
their own selection and feasibility gates apply.

---

<a id="0-purpose"></a>
<a id="1-fixed-baseline-assumptions"></a>
<a id="11-current-frontend-baseline"></a>
<a id="12-current-procedure-composition-baseline"></a>
<a id="13-current-validation-authority"></a>
<a id="14-current-runtime-authority"></a>
<a id="2-in-scope-future-work"></a>
<a id="3-out-of-scope-implemented-baseline"></a>
<a id="4-cross-cutting-future-invariants"></a>
<a id="41-no-hidden-runtime-values"></a>
<a id="411-value-strata"></a>
<a id="42-no-hidden-effects"></a>
<a id="43-no-second-lowering-path"></a>
<a id="44-source-maps-are-mandatory-for-generated-structure"></a>
<a id="45-reports-are-views-not-authority"></a>
<a id="46-contracts-may-narrow-not-widen"></a>
<a id="part-i--let-proc-local-compile-time-procedure-bindings"></a>
<a id="5-feature-summary"></a>
<a id="6-motivation"></a>
<a id="7-non-goals"></a>
<a id="8-v1-syntax"></a>
<a id="9-v1-restrictions"></a>
<a id="91-single-binding-only"></a>
<a id="92-no-nested-let-proc"></a>
<a id="93-no-recursion"></a>
<a id="94-local-procedure-references-require-explicit-proc-ref"></a>
<a id="95-direct-local-procedure-calls-are-deferred"></a>
<a id="10-capture-semantics"></a>
<a id="11-name-resolution"></a>
<a id="12-type-rules"></a>
<a id="13-lowering-rule"></a>
<a id="14-generated-procedure-identity"></a>
<a id="15-effect-rules"></a>
<a id="16-v1-body-boundary"></a>
<a id="17-source-maps-for-let-proc"></a>
<a id="18-diagnostics-for-let-proc"></a>
<a id="19-explain--debug-metadata-for-let-proc"></a>
<a id="20-acceptance-gate-for-let-proc"></a>
<a id="part-ii--effectful-composition-completion"></a>
<a id="21-feature-summary"></a>
<a id="22-current-gap"></a>
<a id="23-design-goal"></a>
<a id="24-expression-categories"></a>
<a id="25-effectful-let"></a>
<a id="26-effectful-match"></a>
<a id="27-with-phase-as-composable-expression"></a>
<a id="28-same-file-call-bindings-for-locally-constructed-records"></a>
<a id="29-reusable-workflow-boundary-write-roots"></a>
<a id="30-standard-library-lowering-completion"></a>
<a id="31-acceptance-gate-for-effectful-composition"></a>
<a id="part-iii--future-component-contract-architecture"></a>
<a id="32-feature-summary"></a>
<a id="33-target-pipeline"></a>
<a id="34-core-workflow-ast-contract"></a>
<a id="35-core-statement-taxonomy-contract"></a>
<a id="36-semantic-workflow-ir-contract"></a>
<a id="37-executable-ir-contract"></a>
<a id="38-reference-catalog-contract"></a>
<a id="39-type-catalog-contract"></a>
<a id="40-effect-graph-contract"></a>
<a id="41-proof-graph-contract"></a>
<a id="42-state-layout-contract"></a>
<a id="43-source-map-contract"></a>
<a id="44-legacy-adapter-contract"></a>
<a id="45-debug-yaml-renderer-contract"></a>
<a id="46-acceptance-gate-for-component-architecture"></a>
<a id="part-iv--full-macro-system-safety-contract"></a>
<a id="47-feature-summary"></a>
<a id="48-macro-principles"></a>
<a id="49-hygiene-requirements"></a>
<a id="50-macro-effect-visibility"></a>
<a id="51-macro-source-maps"></a>
<a id="52-macro-acceptance-gate"></a>
<a id="part-v--runtime-closures-boundary"></a>
<a id="53-feature-summary"></a>
<a id="54-closure-conformance-profiles"></a>
<a id="541-disabled-profile"></a>
<a id="542-design-fixture-profile"></a>
<a id="543-minimum-executable-profile"></a>
<a id="55-runtime-closure-contract"></a>
<a id="56-forbidden-runtime-closure-shortcuts"></a>
<a id="57-minimum-executable-surface"></a>
<a id="58-closure-family-registry"></a>
<a id="59-closure-value-shape"></a>
<a id="60-capture-contract"></a>
<a id="61-capability-captures"></a>
<a id="62-invocation-contract"></a>
<a id="63-effect-and-write-root-contract-for-closures"></a>
<a id="64-provider-and-model-selection"></a>
<a id="65-storage-and-transport"></a>
<a id="66-replay-and-resume"></a>
<a id="67-closure-diagnostics"></a>
<a id="68-runtime-closure-source-maps"></a>
<a id="69-runtime-closure-fixtures"></a>
<a id="70-runtime-closure-minimum-executable-tests"></a>
<a id="71-relationship-to-let-proc"></a>
<a id="72-runtime-closure-acceptance-gate"></a>
<a id="part-vi--implementation-ordering"></a>
<a id="73-recommended-sequence"></a>
<a id="stage-1-document-status-cleanup"></a>
<a id="stage-2-let-proc-v1-narrow-body-boundary"></a>
<a id="stage-3-effectful-composition-normalization"></a>
<a id="stage-4-standard-library-lowering-completion"></a>
<a id="stage-5-component-contract-promotion"></a>
<a id="stage-6-macro-system-finalization"></a>
<a id="stage-7-runtime-closure-disableddesign-fixture-profile"></a>
<a id="stage-8-runtime-closure-executable-profile-only-if-accepted"></a>
<a id="74-dependency-graph"></a>
<a id="part-vii--unified-test-matrix"></a>
<a id="75-test-categories"></a>
<a id="76-runtime-artifact-invariants"></a>
<a id="77-source-map-fixtures"></a>
<a id="78-effect-fixtures"></a>
<a id="79-forbidden-transport-fixtures"></a>
<a id="part-viii--open-decisions"></a>
<a id="80-let-proc-direct-calls"></a>
<a id="81-capture-aliases"></a>
<a id="82-nested-local-procedures"></a>
<a id="83-runtime-closure-syntax"></a>
<a id="84-executable-ir-migration"></a>
<a id="85-macro-expansion-power"></a>
<a id="part-ix--document-cleanup-plan"></a>
<a id="86-existing-design-docs"></a>
<a id="87-header-template-for-future-docs"></a>
<a id="88-status-vocabulary"></a>
<a id="part-x--final-unified-rule"></a>

The original unified proposal is historical. Its V1/component rollout and scheduling are preserved without selecting work; current and deferred owners are listed above. See the [preserved record](../reports/documentation-history/workflow_lisp_unified_frontend_design-history.md#0-purpose).
