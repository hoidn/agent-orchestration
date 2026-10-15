# docs/lisp_workflow_drafting_guide.md: Historical Sections

Status: **Historical.** Original tense, versioned acceptance language, receipts
and commands are preserved as evidence, not current execution or work selection.
Current owner: [lisp_workflow_drafting_guide.md](../../lisp_workflow_drafting_guide.md).

## Historical operational record 1

Design references:

- [Capability Status Matrix](../../capability_status_matrix.md)
- [Workflow Lisp Frontend Specification](../../design/workflow_lisp_frontend_specification.md)
- [Workflow Lisp Core Calculus And Compiler Middle-End](../../design/workflow_lisp_core_calculus_middle_end.md)
- [Workflow Lisp Frontend MVP Specification](../../design/workflow_lisp_frontend_mvp_specification.md)
- [Workflow Lisp Core Statement Taxonomy](../../design/workflow_lisp_core_stmt_taxonomy.md)
- [Workflow Lisp Semantic Workflow IR](../../design/workflow_lisp_semantic_workflow_ir.md)
- [Workflow Lisp Executable IR](../../design/workflow_lisp_executable_ir.md)
- [Workflow Lisp Macro Surface Contract](../../design/workflow_lisp_macro_surface_contract.md)
- [Workflow Lisp Frontend Standard Library Lowering](../../design/workflow_lisp_stdlib_lowering.md)
- [Workflow Lisp Parametric Type System](../../design/workflow_lisp_parametric_type_system.md)
- [Workflow Lisp Procedure-First Reuse Contract](../../design/workflow_lisp_procedure_first_reuse_contract.md)
- [Workflow Lisp Runtime Closures Boundary](../../design/workflow_lisp_runtime_closures_boundary.md)
- [Workflow Lisp Unified Frontend Design](../../design/workflow_lisp_unified_frontend_design.md)
- [Workflow Lisp Native Transportable Returns And Typed Result Guidance](../../design/workflow_lisp_native_transportable_returns.md)
- [Workflow Lisp Prompt Calculus](../../design/workflow_lisp_prompt_calculus.md)
- [Workflow Lisp Provider Live Binding](../../design/workflow_lisp_provider_live_binding.md)
- [Workflow Lisp Provider Peer Messaging](../../design/workflow_lisp_provider_peer_messaging.md)
- [Workflow Lisp Language Server](../../design/workflow_lisp_language_server.md)
- [Workflow Lisp Language Server Setup](../../workflow_lisp_language_server_setup.md)
- [Workflow Language Design Principles](../../design/workflow_language_design_principles.md)
- [Workflow Command Adapter Contract](../../design/workflow_command_adapter_contract.md)
- [Workflow Lisp Generic Core, Expression Surface, And Adapter Retirement](../../design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md)
- [Workflow Lisp Private Runtime State And Consumer Value Flow](../../design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md)
- [Workflow Lisp Runtime-Native Drain Authoring](../../design/workflow_lisp_runtime_native_drain_authoring.md)

## Historical operational record 2

## 21. Historical YAML-To-Core Translation Surfaces

This section helps interpret retired YAML definitions and historical migration
evidence. The rows describe Core behaviors that `.orc` lowering may still
target; they do not define a runnable YAML frontend.

| YAML/Core surface | Lisp-oriented replacement |
| --- | --- |
| `expected_outputs` | `defrecord`, `command-result`, simple typed artifact result |
| `output_bundle` | `defrecord` plus `provider-result` or `command-result` |
| `variant_output` | `defunion` plus `provider-result` |
| `pre_snapshot` + `select_variant_output` | `run-provider-phase` or another structured producer result |
| `materialize_artifacts` | Context-derived materialization or internal lowering |
| `requires_variant` | Compiler-generated from `match` or typed discriminant proof |
| `match` | Same concept, used directly over unions |
| `repeat_until` | `review-revise-loop`, `backlog-drain`, or `loop/recur` |
| Raw `goto` | Avoid; use structured control |
| Shell gate | Assert, typed result, transition, or certified adapter |
| Pointer sidecar | Optional representation, not semantic source |

Do not write YAML-shaped Lisp:

```lisp
;; Bad direct translation
(step SelectImplementationOutcome
  (select-variant-output
    :path "${inputs.state_root}/implementation_state.json"
    :snapshot root.steps.Execute.snapshots.before
    :variants ...))
```

Prefer high-level authoring:

```lisp
(let* ((attempt
         (provider-result providers.execute
           :prompt prompts.implementation.execute
           :inputs (inputs.design inputs.plan)
           :returns ImplementationAttempt)))

  (match attempt
    ((COMPLETED c) ...)
    ((BLOCKED b) ...)))
```

If Lisp code is only YAML with parentheses, stop and revise the abstraction.

## 22. Historical Migration From YAML To `.orc`

Use this process when translating a historical definition or auditing how a
retired workflow was converted.

1. Inventory behavior, not syntax.
2. Translate types first: path contracts, enums, records, unions, context
   records, provider records, and workflow signatures.
3. Translate one phase before the whole stack.
4. Measure authoring improvement.

Behavior inventory:

| Current pattern | Target |
| --- | --- |
| Pointer/path setup | Context-derived materialization or certified adapter |
| Fixed JSON bundle | `defrecord` plus `command-result`/`provider-result` |
| Completed/blocked output | `defunion` plus `match` |
| mtime/custom freshness selector | Structured producer result |
| Recovery gate | `resume-or-start` |
| Queue move + ledger update | `resource-transition` |
| Review/fix loop | `review-revise-loop` |
| Selected-item fan-in scripts | `finalize-selected-item` |
| Top-level select/run/gap/repeat | `backlog-drain` |
| Markdown line extraction | Structured result; legacy adapter only if necessary |
| Compare/count/default/format helper script | Closed pure-expression surface or typed projection |

For each migrated workflow, measure:

- authored LOC;
- semantic LOC;
- manual state-path count;
- pointer-file count;
- manual variant-check count;
- markdown/text extractor count;
- shell/Python glue count;
- gate-pattern count;
- behavioral equivalence.

A translation is not successful merely because the `.orc` parses. If the
`.orc` version remains YAML-shaped or requires more boilerplate than the
captured baseline, stop and revise the frontend design before translating more
workflows.

## 23. Example: Implementation Phase

The former phase/context/publication recipe is not a target-2.35/2.36 copy
example. Start with the [evaluated review/revise recipe](../../lisp_workflow_drafting_guide.md#137-improve) and
compose only admitted provider, command and call effects. The
[review-loop contract](../../design/workflow_lisp_review_revise_stdlib_parametric_integration.md)
retains the separate phase helper's schemas.

## 24. Example: Selected Backlog Item

The former recipe depended on `resource-transition`, `resume-or-start` and
`finalize-selected-item`, all unavailable at targets 2.35/2.36. The
[stdlib lowering contract](../../design/workflow_lisp_stdlib_lowering.md) owns their
separate semantics. Do not copy that recipe into an evaluated entry.

## 25. Example: Top-Level Backlog Drain

The former context/resource-based drain example is not an evaluated-target
recipe. Resource transitions and materialized views are outside 2.35/2.36
admission. The [drain-authoring design](../../design/workflow_lisp_runtime_native_drain_authoring.md)
retains the separate family's intended lifecycle; use Section 2A to assess
ordinary bounded compositions.

## Historical operational record 2

## 30. Low-Level Core Surfaces

These older-route Core surfaces remain useful for historical debugging,
persisted compatibility and runtime tests. They are compiler targets, not
current evaluated authoring instructions or a second source language.

| Surface | Purpose |
| --- | --- |
| `expected_outputs` | File-per-artifact validation |
| `output_bundle` | Fixed-shape JSON bundle validation |
| `variant_output` | Tagged-union JSON bundle validation |
| `pre_snapshot` | Durable before-state evidence |
| `select_variant_output` | Exactly-one changed candidate selection and atomic bundle commit |
| `materialize_artifacts` | Runtime-owned materialization and pointer representation |
| `requires_variant` | Explicit variant proof for low-level steps |
| `match` | Structured branch/proof context |
| `repeat_until` | Bounded post-test loop |
| `call` | Public-boundary workflow call |

Do not duplicate this low-level substrate in high-level `.orc` unless you are
writing a compatibility fixture, runtime test, or standard-library lowering.
