# Workflow Lisp Lexical Execution Checkpoints And Durable Resource Resumability

Current safety owner: [State](../../specs/state.md),
[evaluated execution](workflow_lisp_evaluated_execution.md) and
[executor retirement](workflow_lisp_executor_retirement.md). Old profiles cannot
resume, replay or repair in this package. A demonstrated exact complete
release/environment is required for historical recovery; otherwise resumability
is retired. No coarse fallback or backward scan is promised.

Retained design constraints: execution-position caches never become domain
state, provider evidence or prompt values; typed values/proofs and identity must
be revalidated before reuse. Node-local evidence is primary. Only positive
absence can permit a uniquely ordered, globally ID-unique, fully validated
nearest prior boundary; present-but-unusable, ambiguous or unsafe state fails
closed without scanning older records. These guardrails do not imply that the
old checkpoint representation is used by the evaluated memo.

Status: predecessor checkpoint architecture; historical rollout with retained
safety rationale. Evaluated memo resume supersedes its executable substrate.
Kind: architecture / runtime resumability target
Created: 2026-06-12
Scope: private lexical execution checkpoints over WCC program identity;
effect-boundary resume policies; the separation between execution
resumability and domain durability; retirement of authored resume plumbing
from public `.orc` boundaries.

Authority:

- Normative runtime and DSL behavior remains in `specs/`. This document
  preserves a predecessor design; no retained tranche or fallback language
  changes current evaluated resume admission.
- `docs/design/workflow_lisp_core_calculus_middle_end.md` owns the WCC
  calculus: structured control, second-class join points, scopes, proof
  state, effect rows, and environment identity. This design consumes that
  identity as the checkpoint substrate; it adds no calculus constructs.
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
  owns `Resource<TState>`, `Transition<TRequest, TResult>`, idempotency,
  audit, conflict handling, and boundary authority classes. This design
  consumes those contracts unchanged; it does not redefine durability.
- `docs/design/workflow_lisp_state_layout.md` owns generated path identity
  and allocation rules. Checkpoint storage receives new allocation roles;
  identity rules are not redefined here.
- `docs/design/workflow_lisp_runtime_migration_foundation.md` owns validated
  structured output and private value transport — the only channel through
  which completed effect results may be reused.
- Current resume/reuse behavior is owned by the runtime/state contracts and
  direct owner behavioral tests. Route identity and copy safety are owned by
  `docs/workflow_lisp_route_readiness_registry.json`; frozen promotion reports
  are historical evidence only. This predecessor is not a selected long-term
  checkpoint substrate and supplies no current recovery authority.

Related docs:

- `docs/design/workflow_lisp_core_calculus_middle_end.md`
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/state.md`

<a id="1-purpose"></a>
<a id="2-alternatives-considered"></a>
<a id="21-resource-only-resumability-rejected"></a>
<a id="22-checkpoint-only-resumability-rejected"></a>
<a id="23-hybrid-lexical-checkpoints-plus-typed-transitions-chosen"></a>
<a id="4-authority-and-dependency-direction"></a>
<a id="41-this-document-consumes"></a>
<a id="42-this-document-owns"></a>
<a id="43-this-document-does-not-own"></a>
<a id="44-sequencing-relative-to-the-generic-core-target"></a>
<a id="45-relationship-to-authority-inversion-deferred-enablement"></a>
<a id="46-prohibited-dependency-directions"></a>
<a id="5-goals"></a>
<a id="6-non-goals"></a>
<a id="7-architecture-invariants"></a>
<a id="8-core-model"></a>
<a id="81-the-two-ledgers"></a>
<a id="82-checkpoint-content-model"></a>
<a id="83-identity-and-validity"></a>
<a id="84-effect-boundary-resume-policies"></a>
<a id="85-what-authors-see"></a>
<a id="3-current-state-anchors"></a>

The predecessor checkpoint architecture, representation and coarse-boundary fallback are historical design rationale. They do not supply current resume policy or select a future port. See the [preserved record](../reports/documentation-history/workflow_lisp_lexical_execution_checkpoints-history.md#1-purpose).

<a id="9-tranche-r0-resume-semantics-census-and-characterization"></a>
<a id="91-contract"></a>
<a id="92-tasks"></a>
<a id="93-acceptance"></a>
<a id="10-tranche-r1-checkpoint-model-schema-and-shadow-emission"></a>
<a id="101-contract"></a>
<a id="102-tasks"></a>
<a id="103-acceptance"></a>
<a id="11-tranche-r2-execution-restore-for-pure-and-structured-regions"></a>
<a id="111-contract"></a>
<a id="112-tasks"></a>
<a id="113-acceptance"></a>
<a id="12-tranche-r3-effect-boundary-resume-policies"></a>
<a id="121-contract"></a>
<a id="122-tasks"></a>
<a id="123-acceptance"></a>
<a id="13-tranche-r4-transition-aware-resume"></a>
<a id="131-contract"></a>
<a id="132-tasks"></a>
<a id="133-acceptance"></a>
<a id="14-tranche-r5-authored-plumbing-retirement"></a>
<a id="141-contract"></a>
<a id="142-tasks"></a>
<a id="143-acceptance"></a>
<a id="15-tranche-r6-evidence-gated-default-flip-and-legacy-cleanup"></a>
<a id="151-contract"></a>
<a id="152-tasks"></a>
<a id="153-acceptance"></a>

The R0–R6 rollout is historical. Its safety criteria constrain retained readers, but cannot retain legacy executable resume in this package. See the [preserved record](../reports/documentation-history/workflow_lisp_lexical_execution_checkpoints-history.md#9-tranche-r0-resume-semantics-census-and-characterization).

<a id="16-failure-modes"></a>
<a id="17-verification-strategy"></a>
<a id="18-declarative-acceptance-scenarios"></a>
<a id="181-branch-local-resume"></a>
<a id="182-loop-resume-without-domain-resources"></a>
<a id="183-transition-audit-reuse"></a>
<a id="184-unsafe-command-non-rerun"></a>
<a id="185-plumbing-free-public-boundary"></a>
<a id="186-executable-drift"></a>
<a id="19-success-criteria"></a>
<a id="20-summary-recommendation"></a>

The predecessor verification/failure scenarios and permanent coarse-resume floor are historical obligations of that design, not supported recovery in the current package. See the [preserved record](../reports/documentation-history/workflow_lisp_lexical_execution_checkpoints-history.md#16-failure-modes).
