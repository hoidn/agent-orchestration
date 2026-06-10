# Workflow Command Adapter Contract

Status: draft design guidance
Scope: workflow YAML, v2.14+ deterministic surfaces, future frontend lowering,
legacy migration adapters, command steps

This document defines how workflow-authored command behavior should be treated
when it carries semantic meaning. It does not ban Python, shell, or command
steps. It bans hidden workflow semantics embedded in opaque command text.

## Core Policy

Workflow source must not contain hidden procedural semantics.

Procedural behavior must be represented as one of:

1. a typed workflow procedure;
2. a typed workflow call;
3. a certified command adapter with declared inputs, outputs, effects,
   fixtures, and source maps;
4. a runtime-native effect.

Inline Python, shell, heredocs, report parsing, pointer-as-state, and ad hoc
JSON rewrites are migration debt when they decide workflow state, routing,
artifact lineage, resource movement, or resume behavior.

## Command Steps Are Not The Problem

A command step is legitimate when it invokes an external tool or a certified
adapter with explicit contracts.

Examples that can be legitimate:

- run a deterministic validator;
- run a benchmark script with declared outputs;
- invoke a named adapter that moves a queue item and emits a typed bundle;
- invoke a named adapter that bridges a legacy JSON format.

Examples that are not acceptable in new high-level workflows:

- `python -c` or `python -` blocks that rewrite semantic state;
- `bash -c` gates that decide phase status;
- inline code that parses markdown reports for `APPROVE`, `BLOCKED`, or
  `Blocker Class:`;
- inline code that reads a pointer file as if it were semantic authority;
- inline code that shells out to other helper scripts and hides the real
  effects from workflow validation.

The distinction is semantic, not aesthetic: command execution is allowed, but
hidden workflow semantics are not.

## Classification Model

Classify glue by the behavior it implements first, then by implementation form.

Behavior classes:

- `pointer_materialization`: writes or reads pointer files for path values.
- `structured_result`: creates or validates typed JSON state.
- `provider_output_protocol`: converts provider output into structured state.
- `variant_selection`: chooses one result variant from evidence.
- `assertion_gate`: checks status strings or file presence before continuing.
- `resume_state_reuse`: decides whether prior canonical state can be reused.
- `resource_transition`: moves a resource between queues or states.
- `ledger_update`: appends or updates progress/run ledgers.
- `outcome_finalization`: routes multiple phase outcomes into one final result.
- `report_parsing`: extracts semantic fields from human-readable text.
- `external_tool`: invokes a tool whose semantics are outside the workflow but
  whose outputs are declared and validated.

Implementation forms:

- inline Python or shell;
- named script without a typed adapter contract;
- certified command adapter;
- existing DSL surface such as `output_bundle`, `variant_output`,
  `select_variant_output`, `materialize_artifacts`, or `match`;
- frontend procedure such as `provider-result`, `resume-or-start`,
  `resource-transition`, or `finalize-selected-item`;
- runtime-native effect.

Migration decisions should be based on the behavior class. The implementation
form determines urgency and enforcement severity.

## Certified Command Adapter

A certified command adapter is a named command boundary that is allowed to
carry workflow semantics because its contract is explicit and testable.

Every certified adapter declares:

```text
name
stable command path
typed input signature
typed output signature
declared effects
artifact contracts
state writes
path-safety expectations
exit-code and error taxonomy
fixture tests
negative tests
source-map behavior
owner module
replacement path, if temporary
```

For promoted Workflow Lisp authoring, certified adapters may also be invoked
through a typed `command-result` surface instead of raw argv assembly:

```lisp
(command-result normalize-summary
  :adapter normalize_result
  :inputs
    ((execution_report completed.execution_report)
     (review_report approved.review_report))
  :returns ImplementationSummary)
```

Promoted adapter declarations must carry the metadata that makes that call
surface typecheckable and lowerable:

- `behavior_class`
- `input_signature`
- `artifact_contracts`
- `state_writes`
- `error_codes`
- `owner_module`
- `replacement_path`
- `invocation_protocol`

The current promoted invocation protocol is `json_object_positional_arg`:
the frontend validates typed inputs, renders one JSON object positional
argument in declared field order, and reuses the existing structured-result
command bundle path.

The adapter command must be a stable script or executable, not an inline
`python -c`, `python -`, `bash -c`, heredoc, or nested `subprocess.run` shell.

## Adapter Validation

The workflow compiler or loader should be able to validate:

- all adapter inputs have known contracts;
- output bundles validate before publication;
- declared artifacts exist when required;
- effects are visible in the effect graph;
- path arguments follow workspace path-safety rules;
- pointer files are representations, not semantic authority;
- report parsing is absent, or the adapter is explicitly marked legacy;
- errors map to stable error codes or typed failure outputs;
- source maps identify the frontend form or workflow step that invoked the
  adapter.

For promoted `command-result :adapter` calls, the frontend must also validate:

- required inputs are present and undeclared inputs are rejected;
- each authored input expression matches the declared field type;
- each authored input is projectable into the declared invocation protocol;
- the declared adapter return type matches `:returns`.

## Legacy Adapters

A legacy adapter is a certified command adapter with an explicit compatibility
debt label.

Use a legacy adapter only for:

- old scripts whose behavior cannot be replaced immediately;
- old pointer conventions;
- markdown report parsing needed during migration;
- historical state layouts;
- command protocols that predate structured output bundles.

Legacy adapters must be fixture-tested, source-mapped, linted, and preferably
deprecated. They must not be imported by new high-level workflow libraries
unless the dependency is explicitly allowed.

See also: [Workflow Lisp Legacy Adapter](workflow_lisp_legacy_adapter.md).

## Provider Output Protocol

Provider output must not rely on prose as semantic authority.

When a provider decides a workflow outcome, the preferred protocol is:

1. provider emits a structured bundle or typed union result;
2. runtime validates the bundle or variant contract;
3. runtime atomically commits canonical state;
4. markdown reports are published as views linked from that state.

This maps to current and planned surfaces:

- `variant_output` for provider/command-emitted tagged unions;
- `output_bundle` for fixed-shape structured outputs;
- `select_variant_output` for exactly-one candidate selection from durable
  evidence;
- future `provider-result` and `command-result` frontend forms for typed
  structured results.

Prose-only provider output may be tolerated only behind a legacy adapter during
migration.

## Structured Validator Adapters

Certified validators that publish or prove structured workflow state are command
adapters, not loopholes for hidden glue. This includes schema validators for
review findings and validator/projection adapters that turn raw command bundles
into variant-proof-compatible results.

When invoked as command steps, these validators must use the command structured
bundle contract: declared inputs, declared `output_bundle` or `variant_output`
outputs, path-safe bundle targets, stable error taxonomy, source maps, and
negative fixtures for malformed inputs. They must not establish workflow
meaning by parsing markdown reports, rewriting ad hoc JSON in place, or relying
on stdout as semantic authority.

## Versioned Lint Policy

Recommended lints:

- `inline_python_command_in_workflow`
- `inline_shell_command_in_workflow`
- `inline_json_state_rewrite`
- `inline_pointer_write`
- `inline_subprocess_nested_command`
- `semantic_field_extracted_from_report`
- `command_adapter_missing_contract`
- `legacy_adapter_missing_fixture`
- `pointer_used_as_semantic_authority`
- `resource_move_without_transition`
- `recovery_gate_without_resume_or_start`

Severity policy:

| Surface | Severity |
| --- | --- |
| Existing YAML workflows | Warning plus inventory classification. |
| v2.14 migrated workflows | Warning unless allowlisted with replacement metadata. |
| New high-level frontend workflows such as `.orc` | Error. |
| Strict migration CI | Error unless explicitly allowlisted. |
| Future major DSL/runtime tranche | May become hard error for semantic inline glue. |

## Allowlist Metadata

Any temporary allowlist entry must say what the glue does and how it will be
removed.

```yaml
inline_glue_allowlist:
  - workflow: workflows/library/neurips_selected_backlog_item.v214.yaml
    step: AssertPlanApproved
    class: assertion_gate
    reason: legacy selected-item migration still normalizes plan gate state
    replacement: PlanGateResult + match over APPROVED/BLOCKED
    owner: dsl-v214-workflow-migration
    expires_after: workflow_lisp_mvp_or_plan_gate_typed_result
```

Do not allowlist inline glue only because it is inconvenient to migrate.

## Replacement Map

| Glue Pattern | Preferred Replacement |
| --- | --- |
| Pointer writes and path txt files | `materialize_artifacts` or runtime-owned optional pointer materialization. |
| Status assertions | Typed union result plus `match`. |
| Plan-gate recovery | `resume-or-start` with canonical reusable-state validation. |
| Queue movement and ledger update | `resource-transition`, initially via certified adapter if needed. |
| Final completed/blocked fan-in scripts | `finalize-selected-item` typed outcome router. |
| JSON rewrite and field checking | `output_bundle`, `variant_output`, `command-result`, or `provider-result`. |
| Exactly-one report selection | `pre_snapshot` plus `select_variant_output`. |
| Provider prose parsed for decisions | Structured provider output protocol. |

## `resume-or-start` Requirement

`resume-or-start` is not a nicer name for recovery glue.

It requires a canonical reusable-state validation contract:

- where prior state is stored;
- which schema/version it uses;
- which terminal variants are reusable;
- which referenced artifacts must still exist;
- how stale or invalid prior state fails;
- how resumed and fresh branches normalize to the same typed result.

Without that contract, recovery remains a legacy adapter or explicit workflow
logic.

High-level `.orc` must not bypass this form with direct
`command-result :adapter` calls to adapters classified as
`resume_state_reuse`.

## Dedicated High-Level Forms

Certified adapters are not a loophole around established high-level semantic
forms.

- Resource or queue movement remains `resource-transition`, even if the current
  lowering path still uses a certified adapter backend.
- Reusable-state gating remains `resume-or-start`, even if the current
  implementation still depends on certified adapters behind that surface.

Direct promoted adapter calls for those semantic classes are rejected so the
authored `.orc` surface keeps the semantic transition visible.

## Runtime-Native Promotion Criteria

Do not promote every script into a runtime primitive.

Promotion is justified only when an adapter repeatedly needs at least one
property that a command adapter cannot provide well:

- atomic multi-file or resource transition semantics;
- cross-workflow reuse with stable semantics;
- resumability integrated with state checkpoints;
- source-map and observability fidelity beyond command logs;
- security/path-safety guarantees that must be enforced before command launch;
- variant/proof/effect information needed by the semantic IR.

If a certified adapter is testable, explicit, and rare, keep it as an adapter.

## Migration Sequence

1. Inventory inline and script glue.
   Scan for `python -c`, `python -`, `bash -c`, `sh -c`, heredocs,
   `subprocess.run`, manual JSON rewrites, pointer reads/writes, report
   parsing, and manual status assertions.

2. Ban new hidden inline glue.
   Add lints as warnings for existing YAML and errors for new high-level
   frontend workflows.

3. Extract inline blocks into named adapters.
   This is an interim step that makes the behavior testable and source-mapped.

4. Replace simple cases with existing v2.14 surfaces.
   Use `materialize_artifacts`, `output_bundle`, `variant_output`,
   `select_variant_output`, `match`, `requires_variant`, and `publishes` where
   they fit.

5. Replace recurring semantic patterns with typed procedures.
   Add frontend/library forms such as `provider-result`, `command-result`,
   `resume-or-start`, `resource-transition`, `review-revise-loop`,
   `finalize-selected-item`, and `backlog-drain`.

6. Promote only fundamental repeated transitions into runtime-native effects.
   Use the promotion criteria above.

## Bottom Line

Inline Python and shell glue should be treated as evidence that the DSL or
frontend is missing typed transitions, structured results, reusable procedures,
or certified adapters.

The target authoring model is:

```text
resume-or-start
resource-transition
provider-result
command-result
finalize-selected-item
backlog-drain
```

not inline code that reads pointer files, rewrites JSON, parses markdown, shells
out to helper scripts, and reconstructs workflow state by hand.
