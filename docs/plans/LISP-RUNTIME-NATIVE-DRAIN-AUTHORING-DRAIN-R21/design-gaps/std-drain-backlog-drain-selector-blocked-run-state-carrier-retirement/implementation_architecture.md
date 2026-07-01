# Std Drain Selector-Blocked Carrier Retirement Implementation Architecture

Status: retired/superseded implementation architecture
Design gap id: `std-drain-backlog-drain-selector-blocked-run-state-carrier-retirement`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline context: `docs/design/workflow_lisp_frontend_specification.md`
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`

Retirement note: superseded by the current carrier-free `std/drain` contract and
commit `e4d9aae25669839e37be485271a14285adbd6b22`. The narrow selector-blocked
owner-lane checks pass on the current checkout, so this guard slice is not
selectable implementation work.

## Scope

This slice retires selector-blocked `run-state` / `run_state_path` transport
from the imported `std/drain::backlog-drain` route.

The bounded target is:

- selector `BLOCKED` is a typed terminal selection result with a reason only;
- selector `BLOCKED` does not carry run-state, checkpoint paths, generated
  write roots, compatibility bundle paths, pointer files, or rendered reports;
- imported `std/drain::backlog-drain` returns terminal `DrainResult.BLOCKED`
  from loop-owned accumulator fields and stdlib terminal projection, not from
  selector-carried state; and
- any durable drain outcome recording remains a separate declared transition
  or view consumer, not a prerequisite for typed child-call value return.

This slice does not redesign imported `backlog-drain`, the run-item boundary,
the gap-drafter boundary, Design Delta provider request records, work-item
finalization, gap re-entry convergence, public publication, or YAML-primary
promotion.

## Current Checkout Baseline

The current shared stdlib module already expresses the desired blocked-selector
surface:

```lisp
(defunion SelectionResult
  (EMPTY)
  (GAP
    (gap GapPayload))
  (SELECTED
    (selection SelectionPayload))
  (BLOCKED
    (reason String)))
```

The current `DrainLoopState` and `DrainLoopTerminal` in
`orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` do not carry
`run-state`; they carry typed terminal data such as `items_processed`,
`progress_report_path`, and `blocker_class`. Runtime-native drain outcome state
exists under the declared `record-drain-outcome` transition, and summary
rendering is handled by `consume-drain-terminal-effects`.

The Design Delta family already has the matching family selector shape:

```lisp
(defunion DesignDeltaSelectionResult
  (EMPTY)
  (GAP
    (gap DesignDeltaGapPayload))
  (SELECTED
    (selection DesignDeltaSelectedItemPayload))
  (BLOCKED
    (reason String)))
```

The adjacent shared EMPTY carrier-retirement slice owns the broader
`SelectionResult.EMPTY` run-state cleanup. This implementation architecture
therefore focuses on preserving and proving the shared reason-only
`SelectionResult.BLOCKED` contract, removing stale blocked-branch fixture or
validation expectations, and keeping the terminal blocked return path
loop-owned.

## Problem

The runtime-native drain target forbids internal compatibility carriers. A
selector-blocked branch is especially sensitive because it can otherwise become
a hidden lane for old run-state files: the selector cannot produce ordinary
work, yet the parent loop still needs enough terminal information to return a
typed `DrainResult.BLOCKED`.

The correct ownership split is:

- the selector owns only the fact that selection is blocked and the typed
  reason;
- the loop owns accumulator values such as items processed and current progress
  report target;
- `finalize-drain-terminal` owns typed terminal value projection;
- `consume-drain-terminal-effects` owns optional declared terminal effects such
  as resource transition and summary view materialization; and
- runtime-owned checkpoint/resource state remains private execution substrate,
  not selector payload.

Any implementation that reintroduces a selector-carried path merely to satisfy
terminal routing would preserve the old compatibility-carrier lane under a new
name.

## Ownership

`orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` owns the shared
`SelectionResult`, `DrainLoopState`, `DrainLoopTerminal`, `DrainResult`,
`finalize-drain-terminal`, `consume-drain-terminal-effects`, and
`backlog-drain` authoring contract.

`orchestrator/workflow_lisp/drain_stdlib.py` owns the frontend authored
`BacklogDrainSpec` shape, including whether an authored `backlog-drain` call
preserves the imported owner boundary.

`orchestrator/workflow_lisp/lowering/phase_drain.py` owns the current
lowering path for imported/callable `backlog-drain`, including workflow-ref
signature validation, child-call specialization, selector/run-item/gap call
binding, loop accumulator projection, selector-blocked routing, and generated
source-map origins.

Workflow families own their family selector/public result types and projection
helpers. A family may expose richer blocked reason information, but when that
family is consumed by imported `std/drain::backlog-drain`, selector `BLOCKED`
must project to the shared reason-only contract.

The Workflow Lisp frontend, WCC route, shared validation, Semantic IR, and
runtime own proof, effect, source-map, bundle-validation, private-context, and
resume behavior. Any repair exposed by this slice must be generic to the
shared owner lane, not a Design Delta workflow-name exception.

The command-adapter contract owns any touched command, script, adapter, or
runtime-native promotion decision. This slice must not move selector-blocked
semantics into inline Python/shell, stdout JSON, markdown report parsing,
pointer files, ad hoc JSON rewrites, or uncertified state mutation.

## Source Surfaces

Primary source surfaces for this slice are:

- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `orchestrator/workflow_lisp/drain_stdlib.py`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_stdlib_form_migration.py`
- `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc`
- `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain_stdlib.orc`
- `tests/fixtures/workflow_lisp/invalid/backlog_drain_selector_blocked_reason_missing_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/backlog_drain_selector_blocked_extra_state_field_invalid.orc`
- `workflows/library/lisp_frontend_design_delta/types.orc`
- `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`

Generic compiler or validation surfaces outside this list are in scope only if
the carrier-free selector-blocked route exposes a shared owner-lane defect in:

- workflow-ref signature compatibility;
- imported child-call lowering;
- loop-frame or terminal projection;
- source-map lineage;
- variant proof or `requires_variant` ownership; or
- Semantic IR / executable contract projection.

If other files use `std/drain::SelectionResult.BLOCKED`, they follow the same
rule: selector `BLOCKED` carries typed reason data only. Terminal state must
come from loop accumulators, typed terminal projection, runtime-owned
checkpoint/resource state, or declared transitions, not from selector blocked
payload.

## Contract

The shared selector result contract is reason-only for `BLOCKED`:

```lisp
(BLOCKED
  (reason String))
```

This slice does not own unrelated compatibility surfaces that are still
explicitly owned by other variants, workflows, or adjacent carrier-retirement
slices. It also does not require the shared `DrainLoopState` to grow a
run-state field. The accepted current-loop terminal fields are:

- `acc__loop-status`
- `acc__items-processed`
- `acc__progress-report-path`
- `acc__blocker-class`

The selector-blocked route sets terminal status to `BLOCKED`, preserves the
current accumulator values, and uses the shared compatibility blocker class
`BlockerClass.user_decision_required` unless a later typed reason-mapping slice
changes that contract.

The typed value-return path is complete when imported `backlog-drain` can
return `DrainResult.BLOCKED` to its caller without first running
`consume-drain-terminal-effects`, `record-drain-outcome`, materialized summary
rendering, compatibility view rendering, or run-state-file mutation.

Declared terminal effects remain valid as separate consumers:

- publication policy may materialize public summaries from returned terminal
  values;
- `consume-drain-terminal-effects` may record runtime-native drain outcome and
  materialize a summary view when explicitly called;
- a family transition may record external resource state through a typed
  transition; and
- a compatibility bridge may render a legacy view with owner, schema, consumer,
  and retirement metadata.

None of those effects are semantic transport for selector-blocked return.

## Allowed Shapes

Allowed implementation shapes include:

- preserving or restoring reason-only `SelectionResult.BLOCKED` in
  `std/drain.orc`;
- keeping `DesignDeltaSelectionResult.BLOCKED` reason-only;
- aligning fixtures and tests so positive selector-blocked payloads omit
  `run-state`;
- keeping negative coverage that rejects missing blocked `reason`;
- keeping negative coverage that rejects stale or undeclared blocked state
  fields;
- using loop-owned accumulator fields for terminal `BLOCKED` projection;
- preserving `BlockerClass.user_decision_required` for selector-blocked terminal
  projection until a separate typed mapping exists;
- fixing shared `BacklogDrainSpec` or callable-owner lowering propagation when
  it blocks the imported stdlib route; and
- adding generic source-map, Semantic IR, or validation assertions that prove
  selector-blocked terminal projection is attributed to imported
  `backlog-drain`.

## Forbidden Shapes

This slice must not:

- add `run-state`, `run_state_path`, generated write roots, checkpoint paths,
  pointer files, rendered report paths, summary paths, or compatibility bundle
  paths to selector `BLOCKED` payloads;
- widen imported `backlog-drain`, `selector`, `run-item`, or `gap-drafter`
  workflow-ref signatures;
- add wrapper workflows whose only purpose is to recover selector-blocked
  state;
- reread compatibility bundles, pointer files, rendered reports, provider
  prose, command stdout, debug YAML, or summary files as selector-blocked state
  authority;
- require drain outcome recording or summary materialization before typed
  `DrainResult.BLOCKED` return;
- add Design Delta-specific compiler, lowerer, or validator exceptions;
- weaken workflow-ref signature validation, variant proof, source-map, or
  structured-output validation;
- convert selector-blocked routing into a command adapter or script-backed JSON
  rewrite; or
- claim broader runtime-native drain completion, compatibility-carrier
  retirement, imported finalizer adoption, or YAML-primary promotion.

## Command Adapter And Runtime-Native Policy

Selectors may still be implemented by providers, commands, or certified
adapters when those boundaries already belong to a workflow family. Their
structured return contract must match the carrier-free selector-blocked shape:
`BLOCKED` contains a reason and no hidden state field.

Any command boundary touched by this slice remains a declared
`command-result` or certified adapter with typed inputs, typed outputs,
declared effects, fixture coverage, path-safety expectations, stable error
taxonomy, source-map behavior, owner, and retirement metadata. Stdout JSON,
markdown parsing, pointer files, inline shell, and inline Python do not satisfy
the contract.

Runtime-native promotion is justified only for durable transition behavior. A
selector-blocked branch is typed routing, not a new runtime primitive. If
terminal effects need durable mutation, they use the existing declared
`record-drain-outcome` transition or another typed transition that satisfies
the promotion criteria in the command-adapter contract.

## Acceptance Conditions

The slice is accepted when:

- `std/drain::SelectionResult.BLOCKED` has `reason String` and no run-state
  field.
- Design Delta selector stdlib projection returns
  `DesignDeltaSelectionResult.BLOCKED` with reason only.
- imported `std/drain::backlog-drain` compiles and validates with a selector
  whose `BLOCKED` variant omits run-state.
- selector-blocked terminal routing uses current loop accumulator values for
  `items-processed`, `progress-report-path`, and blocker class.
- imported `backlog-drain` can return typed `DrainResult.BLOCKED` without
  requiring terminal effects, publication, compatibility rendering, or
  run-state-file mutation as transport.
- negative coverage rejects selector `BLOCKED` variants that omit `reason`.
- negative coverage rejects stale blocked state fields as signature mismatch,
  undeclared field smuggling, or equivalent shared boundary rejection.
- source maps and Semantic IR attribute selector-blocked terminal projection
  to imported `backlog-drain`, not to hidden command, report, pointer, or
  compatibility-bundle behavior.
- empty, selected-item, gap, completed, blocked, and exhausted routes keep
  their existing typed loop-state, callable-boundary, and proof behavior.
- no command step, script, legacy adapter, materialized view, report parser, or
  pointer file becomes selector-blocked semantic authority.

This architecture closes only the selected shared selector-blocked carrier
retirement gap.
