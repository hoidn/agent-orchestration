# ADR: DSL Evolution for Typed Gates, Scoped References, Structured Control Flow, and Reusable Subworkflows

**Status:** Proposed
**Date:** 2026-03-06
**Owners:** Orchestrator maintainers

## Context

The current DSL is correct enough to run real workflows, but it has three authoring-level problems that now matter more than adding new surface area:

1. Control flow is too stringly.
   - `when.equals` compares strings, not typed values.
   - common workflow decisions like `APPROVE|REVISE` or boolean gates are modeled indirectly through files and shell checks.

2. Author-facing routing is too low-level.
   - `on.*.goto` works as a runtime mechanism, but it is a poor primary authoring abstraction.
   - real workflows end up written as explicit state machines even when the intended structure is just `if/else`, bounded retry, or `repeat until approved`.

3. Reuse is too weak.
   - there is no `import`, `call`, or subworkflow mechanism.
   - authors duplicate large review/fix or plan/review/revise blocks across workflows.
   - this makes maintenance and migration harder than it should be.
   - near-term reusable `call` may need to target a narrower, mechanically enforceable subset first; provider/command-heavy reusable workflows likely require a stronger execution boundary than the current runtime provides.

The result is a DSL that is operationally capable but author-hostile. The next improvements should optimize for correctness and maintainability first, not just syntax convenience.

## Problem Statement

We need to improve the DSL in a way that:

1. Makes correctness gates typed and explicit.
2. Reduces direct dependence on raw `goto` in authored workflows.
3. Introduces reuse without turning YAML into a full programming language.
4. Preserves the current runtime's determinism and sequential execution model.
5. Makes any required state-model changes explicit instead of pretending they are syntax-only.
6. Provides a migration path from existing `version: "1.4"` workflows.

## Non-Goals

This proposal does **not** recommend:

1. A general embedded expression language.
2. Arbitrary scripting inside YAML.
3. User-defined functions with local execution semantics beyond workflow calls.
4. A large static type system with structs, unions, generics, or inference.
5. Replacing the current runtime graph executor.

Those ideas raise complexity faster than they improve workflow quality.

## Scope Clarification

This ADR is intended to guide real spec changes, not just capture direction.

It makes four different kinds of recommendations:

1. **Incremental DSL additions that fit the current state model**
   - first-class `assert` / gate steps

2. **Version-gated predicate/reference additions**
   - typed predicates added to `when`
   - typed success/failure routing over existing step state
   - structured `ref:` operands

3. **Foundational identity and boundary changes**
   - low-level cycle guards with persisted visit/transition counters
   - scoped references
   - stable internal step IDs for lowered and nested execution
   - typed workflow signatures built on the artifact contract model

4. **Versioned DSL + state-model changes built on that foundation**
   - structured `if/else` and later `match`
   - imported subworkflows and `call`
   - structured finalization
   - loops such as `repeat_until`

5. **Additional runtime primitives that remove shell glue but still need new execution/state semantics**
   - lightweight scalar bookkeeping

The second through fourth categories are not pure surface-syntax layers. They require explicit runtime identity, logging, resume, and state-schema rules. `call` also requires a precise import boundary and caller/callee artifact model; it should not silently rewrite authored workspace-relative paths.

Version boundary rule:
- legacy `${...}` substitution keeps its current scoping semantics until a workflow explicitly opts into the new versioned `ref:` model
- the new `ref:` model should be introduced as an opt-in DSL/version boundary, not as a reinterpretation of legacy variable interpolation

## Decision Summary

The recommended roadmap is:

### D1. Add first-class `assert` / gate steps

Introduce a dedicated gate step that evaluates a typed condition and turns it into deterministic step success/failure without requiring shell glue.

Low-risk initial example:

```yaml
- name: GateReviewApproval
  assert:
    equals:
      left: "${steps.ReviewPlan.artifacts.plan_review_decision}"
      right: "APPROVE"
```

Recommended semantics:
- `assert` succeeds when the condition is true
- `assert` fails with a dedicated non-zero gate code (recommended: `3`) and `error.type: "assert_failed"` when the condition is false
- `assert_failed` must be distinguishable from validation / preflight / contract failures, which should keep their existing exit-`2` channel
- Phase 1 `assert` should be able to reuse the current condition surface (`equals|exists|not_exists`) so it remains a genuinely low-risk tranche
- once D2 lands, `assert` can also accept the typed predicate surface
- D1 should not add any synthetic publish semantics; exposing a decision artifact remains a separate later feature

Why this is first:
- smallest surface-area improvement with immediate workflow payoff
- removes many `bash test`, `jq`, and tiny Python gate steps
- provides a cleaner migration target than jumping directly to nested structured control flow

### D2. Add typed predicates and typed failure routing

Introduce typed predicates in a **new version-gated `ref:` model** rather than trying to reinterpret current `${...}` semantics.

This is required because the current repo already gives bare `${steps.<Name>.*}` special current-iteration meaning inside `for_each`. The new predicate surface must not silently change that existing contract.

Initial scope rule for D2:
- only typed root-scoped step state and literals should be legal operands in the first typed-predicate tranche
- `self` / `parent` should not appear until D4 lands
- bare `steps.<Name>` should not be legal in `ref:` operands at all

Recommended forms:

```yaml
when:
  artifact_bool:
    ref: root.steps.ReviewImplementation.artifacts.approved
```

```yaml
when:
  compare:
    left:
      ref: root.steps.Score.artifacts.hidden_score
    op: gte
    right: 0.95
```

```yaml
when:
  compare:
    left:
      ref: root.steps.RunChecks.outcome.kind
    op: eq
    right: contract_violation
```

This example only applies once the workflow has routed `RunChecks` failure into an observable recovery path, for example via `on.failure.goto`. It is not a claim that later predicate steps can observe failures that still terminate the workflow immediately.

Supported boolean composition should stay intentionally small:
- `all_of`
- `any_of`
- `not`

Supported typed comparisons should stay intentionally small:
- `eq`
- `ne`
- `lt`
- `lte`
- `gt`
- `gte`

Predicate operand and failure rules should be explicit:
- `artifact_bool` accepts only `{ ref: ... }` operands that resolve to scalar `bool` artifacts.
- `compare.left` / `compare.right` may be:
  - `{ ref: root.steps.<Step>.artifacts.<name> }` for root-scoped scalar step artifacts
  - `{ ref: root.steps.<Step>.exit_code }`
  - `{ ref: root.steps.<Step>.outcome.kind }` for a closed, versioned normalized outcome enum
  - literals (`string|number|boolean`)
- typed predicates should not reuse `${...}` string interpolation; they should resolve structured refs directly so existing string-coercion rules do not leak into the new feature.
- `relpath` artifacts are valid only for `eq` / `ne`.
- `lt` / `lte` / `gt` / `gte` are valid only for numeric operands (`integer|float`).
- D2 should not expose raw `error.type` or `error.context` in predicates. If typed failure routing is part of D2, it should land with a small closed outcome surface such as `completed|skipped|assert_failed|command_failed|timeout|contract_violation`.
- D2 must ship with a normative normalization matrix from current step execution tuples (`status`, `exit_code`, `error.type`) into `outcome.kind`.
- Pre-execution validation failures are workflow/run load failures, not step outcomes. They therefore have no `steps.<Step>.outcome.kind` value.
- under the current control-flow model, typed failure routing is only observable after an explicit recovery edge such as `on.failure.goto`; a later predicate step cannot observe a failed step that already terminated the workflow
- in the first D2 tranche, `root.steps.<Step>...` refs should only be legal for steps that can execute at most once in the current scope
- if later DSL versions need refs to multi-visit steps, they should add explicit visit/frame-qualified syntax rather than making unqualified refs depend on execution history
- statically undefined `ref:` targets (unknown steps, unknown artifacts, invalid fields) should be workflow-load validation errors, not runtime failures.
- runtime predicate failures should be reserved for dynamically absent values or runtime-only mismatches that cannot be proven at load time.
- statically provable type errors should fail workflow validation; runtime-only mismatches should fail the step with structured predicate error context.
- v1 should not expose non-persisted consumed values directly to predicates. If a workflow wants predicate-visible data, it must surface it as a typed artifact.
- root scope must be written explicitly as `root.steps.<Name>` in the `ref:` model
- untyped `context` is intentionally out of scope for D2. Once D6 lands, typed workflow-level inputs may be exposed separately through a typed surface such as `inputs.<name>`.

Why this is second:
- highest correctness payoff after gates for single-visit and already-materialized decision points
- low conceptual overhead
- removes fragile shell/string checks for both success and failure routing
- aligns naturally with existing scalar artifacts (`enum|integer|float|bool`)

Scope note:
- D2 does **not** by itself make typed routing generally usable inside today's multi-visit `goto` loops
- those workflows still need either explicit visit-qualified refs or later structured/block identity features before typed predicates can replace most stringly loop-local gates
- migration examples and rollout should present D2 as a strong improvement for single-visit gates first, not as a complete replacement for current loop-heavy control flow
- migration examples should also be explicit that typed failure routing under D2 only applies to recovered/observable failed outcomes, not to steps that still terminate the workflow immediately on failure

### D3. Add low-level cycle guards for raw graph workflows

Structured loops are not the only place workflows need protection. Existing workflows still build review/fix and retry loops directly with `goto`, shell counters, and file-backed integers.

Add low-level runtime guards such as:
- workflow-level `max_transitions`
- step-level `max_visits`
- optionally explicit guarded back-edge declarations if the implementation wants a narrower primitive

Example target style:

```yaml
version: "future"
max_transitions: 500
steps:
  - name: PostCycleGate
    max_visits: 6
    assert:
      compare:
        left:
          ref: root.steps.RunPostWorkTests.artifacts.failed_count
        op: eq
        right: 0
    on:
      success: { goto: _end }
      failure: { goto: FixPostWorkIssues }
```

Why this is third:
- protects current raw-graph workflows before they migrate to `repeat_until`
- prevents accidental infinite `goto` loops
- is still narrower than structured loop syntax, but it is **not** current-state-compatible

Required state/runtime work for D3:
- persist workflow-level transition counters and step-level visit counters in `state.json`
- make those counters resume-safe across revisits and mid-loop resumes
- define acceptance coverage for revisit, retry, resume, and reporting semantics
- treat D3 as a versioned state-model change, not as a syntax-only addition
- the first D3 tranche should be limited to top-level pre-lowering step identities; extending cycle guards cleanly to lowered/nested execution should either wait for D5 or be treated as a second migration

### D4. Add scoped reference resolution

Before adding imports or structured blocks, the DSL needs a scoped reference model. Flat `steps.<name>` addressing is tolerable for today's top-level workflows, but brittle once nested branches, loops, and calls exist.

Recommended direction:
- require explicit `self|parent|root` prefixes in the `ref:` model
- do **not** make bare `steps.<Name>` legal in the `ref:` model, because legacy `${steps.<Name>.*}` already has different meaning inside `for_each`
- do **not** make nested references lexical by default, because that would create silent shadowing and migration hazards

Hard rule:
- `root.steps.<Name>` is always the root workflow scope
- nested-scope local references must use `self.steps.<Name>`
- references to the immediately enclosing scope must use `parent.steps.<Name>`
- bare `steps.<Name>` is not valid in the `ref:` model
- this rule applies to the new `ref:` model only; it does **not** retroactively change current `${steps.<Name>.*}` substitution semantics inside existing `for_each`

Illustrative shapes:
- `self.steps.<Inner>.artifacts.<x>` for the current lexical block or call frame
- `parent.steps.<Name>.artifacts.<x>` for the immediately enclosing scope
- `root.steps.<Name>.artifacts.<x>` for the root workflow

Why this is fourth:
- more fundamental than `call` itself
- necessary to make nested workflows readable and non-brittle
- reduces accidental name collisions even before imports arrive

### D5. Add stable internal step IDs

Author-facing `name` is not enough once the loader starts lowering structured blocks into executable helper nodes. The runtime needs a stable internal identity model for:
- resume
- log/debug output
- state compatibility
- lowered helper steps
- nested call frames
- durable publish/consume lineage and freshness bookkeeping

Recommended direction:
- retain author-facing `name` for UX
- add an optional author-controlled stable `id` distinct from display `name` for steps, lowered blocks, and call sites that need durable identities across refactors
- assign a stable internal `step_id` during validation/lowering
- store both human-facing `name` and machine-stable `step_id` in runtime state and logs
- derive qualified `step_id` values from lexical paths of stable authored IDs where present, not from sibling ordinals alone
- use qualified `step_id` values, not display names, as the durable producer/consumer identities in lineage and freshness bookkeeping
- keep any existing display-oriented state views (for example loop-shaped `steps.<Loop>[i].<Inner>` compatibility views) as presentation only; durable lineage, freshness, and resume should key off qualified internal identities

Stability contract:
- sibling insertion should not change descendant internal identities when enclosing authored IDs are unchanged
- import alias renames, branch reshaping, or step/block renames should not change internal identities if explicit stable IDs are preserved
- if a workflow relies only on compiler-generated IDs, stability is guaranteed only within the same validated workflow checksum, not across edited workflow files
- resume across checksum-changing workflow edits should remain unsupported unless a future migration mechanism is defined explicitly

This is infrastructure, not syntax, but it is required before D6-D10.

When D5 lands, it should retrofit all nested execution forms, not just future `call` frames. Existing `for_each` lineage/freshness bookkeeping should move from bare display names to qualified internal identities as part of the same transition. Concretely, loop iterations need durable identities such as `<LoopStep>#<iteration>::<InnerStep>` (or equivalent stable `step_id` derivations) for producer/consumer lineage, freshness state, and resume.

### D6. Add typed workflow signatures (`inputs` / `outputs`)

The DSL needs typed workflow-level interfaces, not just typed step predicates. Today `context` is an untyped key/value bag. Reuse through `call` will remain loosely typed until workflows can declare their own signatures.

Recommended additions:
- top-level `inputs`
- top-level `outputs`

These should be defined as a **separate workflow-boundary contract family** that reuses the existing artifact contract model's type and path-validation rules. They are not the same schema as the top-level artifact registry, because they deliberately omit pointer semantics and add boundary-only fields.

Workflow-boundary contracts should therefore reuse:
- `kind: relpath|scalar`
- `type`
- `allowed`
- `under`
- `must_exist_target`

Workflow-boundary contracts should add only boundary-specific fields such as:
- `required`
- `default`
- `description`
- `from` (for outputs only)

Unlike top-level v1.2 artifact registry entries, workflow `inputs` / `outputs` should not use pointer files. They are bound and exported directly at the workflow boundary. Implementations may share validators/helpers with the artifact contract system, but loaders should treat workflow signatures as a distinct contract family with their own schema and export timing rules.

Suggested shape:

```yaml
inputs:
  task_artifact:
    kind: relpath
    type: relpath
    under: docs/tasks
    required: true
    must_exist_target: true
    description: Canonical task artifact for this workflow.
  max_cycles:
    kind: scalar
    type: integer
    default: 4

outputs:
  review_decision:
    kind: scalar
    type: enum
    allowed: [APPROVE, REVISE]
    from:
      ref: root.steps.Review.artifacts.review_decision
  execution_log:
    kind: relpath
    type: relpath
    under: artifacts
    must_exist_target: true
    from:
      ref: root.steps.ExecutePlan.artifacts.execution_report
```

Recommended semantics:
- top-level runs may bind `inputs` from CLI/context, with validation before execution starts
- imported/called workflows must declare `inputs`/`outputs` explicitly
- `with:` bindings on `call` must type-check against callee `inputs`
- every declared workflow `output` must include an explicit `from` binding to a root-scoped produced value, such as `root.steps.<Step>.artifacts.<name>`
- top-level workflow outputs are materialized only after the workflow body and any finalization complete successfully, immediately before final result/report emission
- callee outputs in a `call` are materialized only after the callee body and any callee finalization complete successfully, immediately before control resumes to the caller
- relpath outputs must be validated against their declared contract at export time, just as step artifacts are validated at publish time
- if an output `from` binding is missing, unresolved, or type-invalid, the top-level workflow or call step should fail with a contract-style error that points at the referenced internal producer
- caller-visible results from `call` are limited to declared callee `outputs`
- exported callee outputs surface on the caller as `steps.<CallStep>.artifacts.<name>` and are the only publishable/consumable artifacts of the call step
- semantically, declared callee outputs should count as local produced fields of the `call` step so existing `publishes.from` composition can refer to them by output name
- `context` may remain as a legacy escape hatch for backward compatibility, but `call` should prefer typed `inputs`
- once typed workflow signatures exist, any predicate-visible workflow-level values should come from declared `inputs`, not untyped `context`

Why this is sixth:
- more important than `call` itself
- gives reuse a real typed boundary
- reduces reliance on implicit, weakly documented context keys

### D7. Add structured `if/else`

Introduce author-facing structured branching once typed predicates, scoped references, stable step IDs, and typed workflow signatures exist.

Structured blocks should be modeled as introducing a **statement layer** above the current flat `Step[]` schema. They are not just a prettier spelling of existing step records. That means the loader/lowering pass must define a separate block/statement IR with its own validation rules and then lower that IR into executable steps with stable identities.

Structured blocks need an explicit scope/output join model:
- branch-local steps are visible only inside the branch/block that defines them
- downstream steps must not reference branch-local step names directly from outside the block
- if a block needs to expose values downstream, it should do so through declared block outputs, analogous to workflow/call outputs
- block outputs should be materialized onto the block node itself so downstream refs target the block, not the internals of one branch
- lowered state/debug output should record which branch executed and mark non-taken branches explicitly as non-executed rather than leaving their state ambiguous

Example target style:

```yaml
- name: DecideNextStep
  if:
    compare:
      left:
        ref: root.steps.Review.artifacts.review_decision
      op: eq
      right: APPROVE
  then:
    - name: Complete
      command: ["true"]
  else:
    - name: FixIssues
      provider: codex
      input_file: prompts/fix.md
```

This should lower internally to the current step graph + `goto` model, but not as a state-transparent transformation. It requires explicit branch identity and debug naming.

### D8. Add structured finalization (`finally` / `defer`)

Current `on.always.goto` is still just another branch override. It is not true teardown semantics. The DSL should gain a finalization primitive with resume-idempotent behavior for queue movement, temp-file cleanup, lock release, and similar concerns.

Recommended direction:
- top-level `finally` block for workflow teardown
- optionally `defer` / scoped finalization later for structured blocks and calls

Minimum semantics:
- runs once after success or failure of the guarded region
- records finalization progress in state so resume does not double-run cleanup
- does not silently override the primary success/failure result of the guarded region
- if the guarded region succeeded and `finally` fails, the overall result becomes failed with a dedicated finalization failure classification
- if the guarded region already failed and `finally` also fails, the original guarded-region failure remains primary and the finalization failure is recorded as secondary diagnostic state
- resume after a partial `finally` execution must continue from the first unfinished finalization step, not restart the whole finalization block

Why this is eighth:
- a real operational improvement over `on.always.goto`
- important for queue and lock correctness
- distinct from generic branching

### D8a. Add an enforceable restricted reusable-execution subset

Before `call` can be shippable, the DSL/runtime needs an execution subset whose file effects are actually enforceable under the current no-sandbox execution model.

The current runtime cannot soundly prove or constrain arbitrary child-process writes from `command` / `provider` steps. A generic declarative write contract is therefore not enforceable today without stronger sandboxing/capability controls.

Recommended first-tranche direction:
- define a **restricted reusable subset** for imported workflows rather than pretending arbitrary workflows can be proven safe
- limit that subset to execution forms whose file effects are mechanically declared and runtime-mediated, or introduce a stronger sandbox/capability boundary first
- do not treat arbitrary `command` / `provider` child processes as safely reusable under `call` unless a later execution model can actually constrain their filesystem effects
- require imported workflows in that subset to write only through declared DSL-managed paths and runtime-mediated outputs
- require every authored DSL-managed write root used by a reusable workflow to be exposed as a typed `relpath` input
- require call sites to bind unique per-invocation write roots for those inputs whenever multiple calls could otherwise alias the same managed paths
- have the loader reject imported workflows that fall outside this statically checkable subset

This is intentionally weaker than full sandboxing and narrower than generic workflow reuse, but it is implementable only if the first tranche is explicit about excluding unconstrained child-process execution. D9 should depend on this restricted-subset model, or on a future stronger sandbox/capability mechanism, not on an unenforceable promise about arbitrary child-process writes.

Principle:
- the first shippable `call` tranche should target controlled, DSL-managed reusable helpers
- it should **not** claim to cover today's provider/command-heavy review-fix or plan-review-revise workflows until a stronger execution boundary exists

### D9. Add reusable subworkflow imports and calls

Introduce:
- top-level `imports`
- step-level `call`
- typed `with:` binding against declared callee `inputs`
- declared exported callee `outputs`

Example:

```yaml
imports:
  plan_loop: workflows/library/plan_loop.yaml
  execute_review_fix: workflows/library/execute_review_fix.yaml

steps:
  - name: BuildPlan
    call: plan_loop
    with:
      task_artifact:
        ref: root.steps.PublishTask.artifacts.task
      max_cycles: 4
```

Execution model must be explicit:
- `call` executes inline within the same run
- callee step names and artifacts are call-scoped
- only declared call outputs cross the call boundary into the caller
- exported callee outputs are materialized by evaluating the callee's declared `outputs[*].from` bindings at call completion
- exported callee outputs surface on the caller as `steps.<CallStep>.artifacts.<name>`; downstream predicates, `publishes.from`, and consumers should compose through that existing step-artifact surface
- internal publish/consume lineage uses **qualified producer/consumer identities** rooted in the call frame, for example `<CallStep>::<InnerStep>` or a stable derived `step_id`
- `since_last_consume` freshness for callee-internal artifacts must be keyed by those qualified consumer identities, not by bare step display names
- authored workspace-relative paths must keep their normal meaning whether a workflow is run top-level or under `call`
- `state/*`, `artifacts/*`, `output_file`, deterministic relpath outputs, and other declared DSL-managed write paths should therefore continue to resolve against the workflow workspace exactly as they do today
- this means `call` namespaces logical identities, not authored workspace files
- path-parameterization of declared write roots is mandatory for the first reusable-library tranche, because otherwise repeated calls or looped calls will alias the same DSL-managed paths
- path-parameterization alone is still not sufficient for safe generic reuse, because the current runtime cannot enforce or sandbox undeclared relative writes from child processes
- therefore D9 depends explicitly on D8a's restricted reusable-execution subset
- D8a must let the loader/runtime reject imported workflows that cannot be proven to stay within declared DSL-managed writes
- undeclared arbitrary child-process writes are incompatible with the first shippable `call` tranche
- existing workflows with fixed shared write paths, or workflows that rely on arbitrary undeclared shell writes, must be migrated or remain top-level-only until a stronger, enforceable isolation model is defined in a later ADR
- call-frame isolation should apply only to runtime-owned metadata/log roots, for example `.orchestrate/call_frames/<call-step-id>/<invocation-id>/...`

Import boundary must also be explicit:
- workflow-authored **source/reference paths** should resolve relative to the imported workflow file
- workflow-authored **workspace/runtime paths** should resolve relative to the execution workspace exactly as they do today
- source/reference paths include:
  - nested imports
  - workflow-bundled schemas, helper assets, prompt/template assets, or similar library-owned source files
- workspace/runtime paths include:
  - `input_file`
  - `depends_on` globs
  - `output_file`
  - `expected_outputs.path`
  - `output_bundle.path`
  - `consume_bundle.path`
  - deterministic relpath outputs
  - authored `state/*` and `artifacts/*` paths
- generic workflows may also rely on other relative file paths used by commands/providers during execution, but those remain outside the first shippable reusable subset unless a future capability/sandbox model can constrain them
- source-path resolution and runtime-write resolution are separate concerns and should be specified as a complete taxonomy, not by ad hoc examples
- reusable provider workflows that depend on bundled prompt/template/schema assets therefore need an explicit workflow-source-relative field as part of D9's required surface area, not as a vague later improvement
- proposed first-class syntax should be explicit, for example:
  - `asset_file: prompts/fix.md`
  - resolved relative to the imported workflow file
  - validated to stay within the imported workflow's source tree
  - distinct from `input_file`, which remains workspace-relative
- `input_file` should remain workspace-relative; do not overload it with import-local asset semantics
- first-tranche imported workflows must not depend on undeclared provider/command relative file effects beyond the declared DSL-managed write roots and explicit source-relative assets above
- imported workflows bring their own private `providers`, `artifacts`, and `context` defaults unless explicitly bound/exported
- imported workflows must declare their own DSL version and be validated independently
- for the first implementation tranche, caller and callee should require the same DSL version to avoid mixed-version lowering semantics
- imported artifact names are private to the callee unless exported through declared outputs
- provider-template name collisions across caller/callee are irrelevant if provider namespaces are private to the call frame; otherwise the spec must define merge precedence before shipping

Recommended state/debug shape:
- caller-visible step result remains `steps.<CallStep>`
- nested execution lives under `steps.<CallStep>.call...`
- logs/debug identities use qualified names like `<CallStep>::<InnerStep>`
- artifact lineage / freshness entries must record those same qualified identities rather than bare step names

### D10. Add first-class enum branching / `match`

Many workflow decisions are enum-valued (`APPROVE|REVISE|BLOCKED`, `PASS|FAIL|SOFT_FAIL`). For that shape, `match` is often a better fit than nested `if/else`.

Example:

```yaml
- name: RouteReviewDecision
  match:
    ref: root.steps.Review.artifacts.review_decision
    cases:
      APPROVE:
        - goto: _end
      REVISE:
        - goto: FixIssues
      BLOCKED:
        - goto: Escalate
```

This should follow `if/else`, not precede it, because it depends on the same scope and identity foundation.
Like `if/else`, `match` should operate over the new structured statement layer rather than pretending raw `goto` statements are already valid members of today's `Step[]` grammar.

### D1a. Add lightweight scalar assignment/update steps as a dedicated runtime primitive

The DSL should remove shell glue not just for gates, but also for routine scalar bookkeeping.

Recommended additions should stay intentionally narrow:
- `set_scalar`
- `increment_scalar`
- `emit_scalar` or a similarly named primitive for writing one typed scalar artifact without shelling out

Example target style:

```yaml
- name: InitializePostTestCycle
  set_scalar:
    artifact: post_test_cycle
    value: 0
  publishes:
    - artifact: post_test_cycle
      from: post_test_cycle

- name: IncrementPostTestCycle
  increment_scalar:
    artifact: post_test_cycle
    by: 1
  publishes:
    - artifact: post_test_cycle
      from: post_test_cycle
```

Constraints:
- only for scalar artifacts already declared in the top-level registry
- no general arithmetic expression language
- runtime must still validate type and artifact publication rules
- these steps should produce local step artifacts with the declared artifact name, just like other step-local produced values
- top-level artifact lineage should still advance only through `publishes.from`; `set_scalar` / `increment_scalar` should not create a second direct registry-mutation path
- this is a new execution primitive, not a pure syntax sugar over existing `expected_outputs` / `output_bundle` flow
- it therefore needs explicit runtime/state/debug semantics for local produced values, `publishes.from` composition, and acceptance coverage

Why this should ship after D1/D2:
- removes a lot of incidental bash from current workflows
- improves readability without drifting into a general scripting DSL
- but it is more invasive than `assert`, because it adds a new step execution/output mechanism rather than only a new typed gate surface

### D11. Add loops such as `repeat_until` later

Loops are valuable, but they are not the next correctness improvement. They depend on:
- typed predicates
- stable internal step IDs
- scoped references
- structured block state semantics
- ideally `match` and `call`

`repeat_until` should use **post-test semantics** in v1:
- iteration 0 always executes once
- the condition is evaluated after each completed iteration
- resume state must record the current iteration index and whether condition evaluation for that iteration already occurred

Example target style:

```yaml
- name: ReviewLoop
  repeat_until:
    condition:
      compare:
        left:
          ref: self.steps.Review.artifacts.review_decision
        op: eq
        right: APPROVE
    max_iterations: 6
    steps:
      - call: ExecuteAndCheck
      - call: Review
      - match:
          ref: self.steps.Review.artifacts.review_decision
          cases:
            REVISE:
              - call: FixIssues
```

As with `if/else` and `match`, the body of `repeat_until` should be defined in the structured statement layer, not as today's raw `Step[]` schema. Unnamed `call` / `goto` forms in examples are statements in that new IR and must be lowered to executable steps with stable identities.

### D13. Add score-aware gates and decisions

Standardize the benchmark/evaluation pattern on top of the predicate system:
- numeric score artifacts
- threshold gates
- optional score bands or enum decisions derived from score

This remains valuable, but it is downstream of D1-D3.

### D14. Add static linting and normalization rules

Syntax alone will not deliver the ergonomic win. The DSL should ship with linting / normalization support such as:
- this shell gate can become `assert`
- this `goto` diamond can become `if`
- this imported workflow collides on exported artifact names
- this predicate is stringly and can be typed
- this loop can be normalized to `match` or `repeat_until`

This is tooling, not core syntax, but it should be part of the roadmap rather than an afterthought.

## Alternatives Considered

### A1. Keep `goto` as the main control-flow model and only add more examples

Rejected.

Reason:
- examples help, but they do not fix the authoring abstraction problem
- the current model still forces structured logic to be expressed as manual state-machine wiring

### A2. Add a full boolean/expression language

Rejected.

Reason:
- too much complexity for too little gain
- easy to create unreadable YAML logic
- pushes the DSL toward an ad hoc programming language

### A3. Add a general-purpose function language

Rejected.

Reason:
- overkill for current needs
- callable subworkflows solve the actual reuse problem with less complexity

### A4. Add imports/call first, without gates, predicates, scoped references, or typed signatures

Rejected as the first step.

Reason:
- reuse helps, but it would mostly preserve today's stringly `goto` patterns inside imported files
- without scoped name resolution, stable IDs, and typed interfaces, imports would be brittle and collision-prone
- correctness-first sequencing says typed gates should come before packaging up reusable loops

## Evaluation of Candidate Improvements

### Tier 1: Best ideas

1. **First-class typed `assert` / gate**
   - Best immediate correctness payoff.
   - Smallest surface-area addition.
   - Cleanest migration away from shell/jq gate steps.

2. **Typed predicates and typed failure routing**
   - Foundational for both success-path and failure-path routing.
   - Lowest implementation risk after `assert`.

3. **Lightweight scalar assignment/update**
   - Removes incidental shell without becoming a general programming language.
   - Still needs explicit runtime semantics, so it is not bundled into D1 itself.

4. **Low-level cycle guards**
   - Protects today's raw-graph workflows immediately.
   - Prevents accidental infinite `goto` loops before structured loops exist.

5. **Scoped reference resolution**
   - More fundamental than imports.
   - Necessary before nested blocks or calls become pleasant to use.

6. **Stable internal step IDs + typed workflow signatures**
   - Infrastructure, but required for lowering, resume, debug clarity, and reusable typed calls.

### Tier 2: Strong next steps

7. **Structured `if/else`**
   - Best readability improvement after the identity model exists.

8. **Structured finalization (`finally` / `defer`)**
   - Real operational improvement over `on.always.goto`.

9. **Imports + callable subworkflows**
   - Best reuse and maintenance improvement.
   - Depends on scoped references, stable IDs, and typed workflow signatures.

10. **Enum `match`**
   - Especially useful for review and evaluation workflows.
   - Often a better fit than nested `if/else` for decision artifacts.

### Tier 3: Later syntax / tooling

11. **Loops (`repeat_until`, `while`)**
   - Valuable, but later than gates, predicates, and structured branching.

12. **Static linting / normalization**
   - High ergonomic value.
   - Should land alongside or shortly after the syntax it recommends.

13. **Score-aware gates**
   - Valuable for benchmark/evaluation workflows.
   - Should build on typed predicates rather than precede them.

### Tier 4: Good ideas, but later

14. **Richer artifact object schemas**
   - Useful, but not the sharpest current pain point.

15. **Local bindings / `let`**
   - Nice readability improvement, but not urgent.

### Ideas to avoid for now

16. **General expression language**
17. **General scripting in YAML**
18. **Heavy type system**

These would make the DSL harder to validate, harder to teach, and easier to misuse.

## Proposed Surface Syntax

### 1. First-class typed gate

```yaml
- name: GateReviewApproval
  assert:
    compare:
      left:
        ref: root.steps.Review.artifacts.review_decision
      op: eq
      right: APPROVE
```

### 2. Typed predicates

```yaml
when:
  compare:
    left:
      ref: root.steps.Score.artifacts.total_score
    op: gte
    right: 0.95
```

```yaml
when:
  artifact_bool:
    ref: root.steps.Preflight.artifacts.ready
```

```yaml
when:
  compare:
    left:
      ref: root.steps.RunChecks.outcome.kind
    op: eq
    right: contract_violation
```

### 3. Low-level cycle guards

```yaml
version: "future"
max_transitions: 500
steps:
  - name: PostCycleGate
    max_visits: 6
    assert:
      compare:
        left:
          ref: root.steps.RunPostWorkTests.artifacts.failed_count
        op: eq
        right: 0
    on:
      success: { goto: _end }
      failure: { goto: FixPostWorkIssues }
```

### 4. Typed workflow signatures

```yaml
inputs:
  task_artifact:
    kind: relpath
    type: relpath
    must_exist_target: true
  max_cycles:
    kind: scalar
    type: integer
    default: 4

outputs:
  review_decision:
    kind: scalar
    type: enum
    allowed: [APPROVE, REVISE]
    from:
      ref: root.steps.Review.artifacts.review_decision
  execution_log:
    kind: relpath
    type: relpath
    must_exist_target: true
    from:
      ref: root.steps.ExecutePlan.artifacts.execution_report
```

### 5. Structured branching

```yaml
- name: DecideNextStep
  if:
    compare:
      left:
        ref: root.steps.Review.artifacts.review_decision
      op: eq
      right: APPROVE
  then:
    - name: Complete
      command: ["true"]
  else:
    - name: FixIssues
      provider: codex
      input_file: prompts/fix.md
```

### 6. Structured finalization

```yaml
finally:
  steps:
    - name: ReleaseLock
      command: ["rm", "-f", "state/workflow.lock"]
```

### 7. Imports and calls

```yaml
imports:
  review_loop: workflows/library/review_loop.yaml

steps:
  - name: ImplementFeature
    call: review_loop
    with:
      task_artifact:
        ref: root.steps.PublishTask.artifacts.task
      max_cycles: 6
```

### 8. Enum match

```yaml
- name: RouteReviewDecision
  match:
    ref: root.steps.Review.artifacts.review_decision
    cases:
      APPROVE:
        - goto: _end
      REVISE:
        - goto: FixIssues
      BLOCKED:
        - goto: Escalate
```

### 9. Lightweight scalar bookkeeping

```yaml
- name: InitializePostTestCycle
  set_scalar:
    artifact: post_test_cycle
    value: 0
  publishes:
    - artifact: post_test_cycle
      from: post_test_cycle

- name: IncrementPostTestCycle
  increment_scalar:
    artifact: post_test_cycle
    by: 1
  publishes:
    - artifact: post_test_cycle
      from: post_test_cycle
```

### 10. Structured looping

```yaml
- name: ReviewFixLoop
  repeat_until:
    condition:
      compare:
        left:
          ref: self.steps.Review.artifacts.review_decision
        op: eq
        right: APPROVE
    max_iterations: 6
    steps:
      - call: ExecutePlan
      - call: RunChecks
      - call: ReviewImplementation
      - match:
          ref: self.steps.ReviewImplementation.artifacts.review_decision
          cases:
            REVISE:
              - call: FixIssues
```

## Compatibility and Lowering Model

The runtime does not need to become a new interpreter.

Recommended implementation model:
1. Parse incremental low-level additions (`assert`, typed predicates, typed workflow signatures) directly.
2. Add dedicated runtime primitives such as scalar bookkeeping with explicit execution/state semantics rather than pretending they are syntax-only sugar.
3. Introduce resume-safe persisted counters for cycle guards, plus scoped references and stable internal step IDs, before nested lowering features ship.
4. Lower structured forms (`if`, `match`, `repeat_until`, `call`, `finally`) into the existing internal graph model.
5. Preserve current `state.json` semantics for D1 and D2 where practical, and introduce explicit versioned state-schema extensions for D1a, D3, and later features.

This keeps the implementation incremental and reduces migration risk without pretending that nested flow and reuse are state-transparent changes.

## Migration Strategy

### Phase 1: First-class `assert`

Add `assert` while keeping existing `when.equals|exists|not_exists` and `on.*.goto` behavior unchanged.

Migration example:

Before:

```yaml
- name: PlanReviewGate
  command: ["python", "-c", "from pathlib import Path; import sys; sys.exit(0 if Path('state/plan_review_decision.txt').read_text().strip() == 'APPROVE' else 1)"]
  on:
    success: { goto: ExecutePlan }
    failure: { goto: PlanCycleGate }
```

After Phase 1:

```yaml
- name: GateReviewApproval
  assert:
    equals:
      left: "${steps.ReviewPlan.artifacts.plan_review_decision}"
      right: "APPROVE"
  on:
    success: { goto: ExecutePlan }
    failure: { goto: PlanCycleGate }
```

Phase 1 deliberately stays within the current variable model. It should not depend on the future `ref:` syntax or future scoped-reference rules.

### Phase 2: Typed predicates/failure routing with versioned `ref:` semantics

Add typed predicates and failure routing in a new DSL version that explicitly introduces `ref:` and its scope rules.

### Phase 3: Lightweight scalar bookkeeping as a runtime primitive

Add `set_scalar` / `increment_scalar` only with explicit runtime semantics for local produced values, state/debug representation, and `publishes.from` composition.

### Phase 4: Resume-safe cycle guards

Add `max_transitions` / `max_visits` only after the runtime and state schema can persist transition and visit counters across revisits and resume.

### Phase 5: Scoped refs + stable internal IDs + typed workflow signatures

Add the reference, identity, and signature foundation before nested blocks or subworkflow calls ship.

Migration guidance:
- existing top-level `${steps.<Name>.*}` references remain valid in the legacy variable model
- current `${steps.<Name>.*}` inside `for_each` keeps its current-iteration semantics until the workflow opts into the new versioned `ref:` model
- new nested features must use scoped refs and internal stable IDs
- top-level workflows may gradually replace untyped `context` assumptions with typed `inputs`
- `for_each` lineage/freshness should be migrated to qualified identities as part of this phase, not deferred to calls only
- even after D4, bare `steps.<Name>` remains legacy `${...}` syntax only; the `ref:` model keeps explicit `root|self|parent` prefixes

### Phase 6: Structured `if/else`

Add `if/else` as an opt-in new-version feature.

### Phase 7: Structured finalization

Add `finally` / later `defer` with explicit resume-idempotent semantics.

### Phase 8: Enforceable restricted reusable-execution subset

Add the statically checkable reusable-execution subset required for reusable imported execution units.

### Phase 9: Imports and calls

Introduce subworkflow libraries for the most duplicated patterns.

### Phase 10: Enum `match`

Add `match` once structured branching and scoped refs exist.

### Phase 11: Loops such as `repeat_until`

Add loops after branch identity, scoped refs, internal IDs, and ideally `match` exist.

### Phase 12: Linting / normalization

Ship workflow linting and normalization rules alongside or shortly after the new syntax.

### Phase 13: Score-aware gates

Add first-class scoring examples and benchmark-oriented workflows after typed gates and predicates exist.


## Spec / Doc Changes Required

Normative:
- [specs/dsl.md](/home/ollie/Documents/agent-orchestration/specs/dsl.md)
- [specs/cli.md](/home/ollie/Documents/agent-orchestration/specs/cli.md)
- [specs/dependencies.md](/home/ollie/Documents/agent-orchestration/specs/dependencies.md)
- [specs/providers.md](/home/ollie/Documents/agent-orchestration/specs/providers.md)
- [specs/security.md](/home/ollie/Documents/agent-orchestration/specs/security.md)
- [specs/state.md](/home/ollie/Documents/agent-orchestration/specs/state.md)
- [specs/variables.md](/home/ollie/Documents/agent-orchestration/specs/variables.md)
- [specs/versioning.md](/home/ollie/Documents/agent-orchestration/specs/versioning.md)
- [specs/observability.md](/home/ollie/Documents/agent-orchestration/specs/observability.md)
- [specs/acceptance/index.md](/home/ollie/Documents/agent-orchestration/specs/acceptance/index.md)

Informative:
- [docs/workflow_drafting_guide.md](/home/ollie/Documents/agent-orchestration/docs/workflow_drafting_guide.md)
- [docs/runtime_execution_lifecycle.md](/home/ollie/Documents/agent-orchestration/docs/runtime_execution_lifecycle.md)
- new example workflows under `workflows/examples/`

## Recommended Sequencing

1. Ship first-class typed `assert` / gate.
2. Ship typed predicates, including typed failure routing.
3. Ship lightweight scalar bookkeeping as a dedicated runtime primitive.
4. Ship resume-safe cycle guards.
5. Ship scoped reference resolution.
6. Ship stable internal step IDs and typed workflow signatures.
7. Ship structured `if/else`.
8. Ship structured finalization.
9. Ship the enforceable restricted reusable-execution subset.
10. Ship imports + `call` only once that restricted subset exists and reusable workflows have a workflow-source-relative asset mechanism.
11. Ship enum `match`.
12. Ship loops such as `repeat_until`.
13. Ship linting / normalization rules alongside the new syntax.
14. Add score-oriented examples and docs.

This sequence maximizes correctness first, then state-model safety, then readability and reuse.

## Concrete Recommendation

If only one improvement can be made next, it should be **first-class typed `assert` / gate**.

If two can be made, they should be:
1. typed `assert` / gate
2. typed predicates

If three can be made, add:
3. resume-safe cycle guards

That set directly addresses the current design smell:
- too much string-based control logic
- too much shell glue for gates
- raw-graph loops that are still too easy to make non-terminating

## Appendix: What Should Stay Low-Level

Some low-level mechanisms should remain available even after the new surface syntax lands:
- raw `goto` for advanced or generated workflows
- explicit `command` gates for non-typed shell-level assertions
- current internal graph execution model

The goal is not to eliminate low-level power. The goal is to stop making low-level graph wiring the default authoring experience.
