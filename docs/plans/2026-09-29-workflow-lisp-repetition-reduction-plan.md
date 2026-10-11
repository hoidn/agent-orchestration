# Workflow Lisp Repetition Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to execute selected tasks, with
> `superpowers:test-driven-development` for behavior changes and
> `superpowers:verification-before-completion` before completion claims.
> Tasks inside one phase that touch disjoint files may run in parallel, each
> in its own git worktree. Track execution with the checkboxes below.

**Goal:** Make `.orc` programs state each fact once: import shared
declarations, construct values from the expected type, infer effects, let
hooks capture their context, and bind provider options once.

**Architecture:** Changes use declarations, the typechecker, elaboration and
provider configuration, reusing the selected execution route rather than
adding an evaluator. Phase A changes no language rule. Each selected language
change needs a target and compatibility decision; W3 can be qualified
independently of the other authoring changes.

**Tech Stack:** Python, Workflow Lisp reader, typechecker, specialization and
elaboration, provider registry and shared validation, pytest/pytest-xdist,
command-backed deterministic procedures and stand-in providers.

**Spec:** [Writing Each Fact Once](../design/workflow_lisp_write_once.md)
(rules W0 to W5),
[repetition census](../reports/2026-09-29-workflow-lisp-repetition-census.md),
[effect ledger simplification](../design/workflow_lisp_effect_ledger_simplification.md),
[local ProcRef bindings](../design/workflow_lisp_let_proc_local_proc_refs.md).

---

## Status, Authorities, And Scope

Status: W3 is implemented at 2.36; qualification is recorded in the closeout. Task 4 scratch qualification, Task 6, Tasks
11–13 and bounded Task14A/14B/F-CODE-1 have coordinator acceptance. Authentic
old-artifact/resume/replay and migrated-source refusal have bounded
compatibility03 acceptance for the final frozen package. The closeout owns final
Task F qualification, original RED campaigns and retained causal dispositions.
W0/W1/W2/W4 remain unselected and W5 deferred.
The bounded [Phase 4c execution plan](2026-10-07-evaluated-execution-phase-4c-w3-plan.md)
owns W3 execution and evidence under the parent delivery sequence.

### W3 Planning Amendment

Owner request, 2026-10-01: make the before/after local-hook proposal concrete
in the roadmap and this planset. W3 covers multiple local bindings, inferred
lexical captures, expected `ProcRef` signatures, and removal of `inputs I`
from `improve`. This selects the planning revision, not implementation of
W0–W5 or a new language target. At that planning cut all implementation tasks remained pending; the current
recovery status above supersedes only the selected W3 task statuses.

Delivery integration, 2026-10-01: W3 is a component of evaluated-execution
delivery, not a separately scheduled feature. The
[parent delivery sequence](2026-09-29-workflow-lisp-evaluated-execution-plan.md#delivery-order-and-preserved-capabilities)
owns scheduling: Phase 3 provides the runtime; Task 4 qualification feeds
the Phase 6a pilot; Phase 4c delivers Tasks 11–14 after qualification
and Task 6 target registration; Phase 6b owns broader consumer migration.
Phase E below is the component's work breakdown for Phase 4c, not another
top-level phase. Qualification preparation can overlap Phase 3; W3 does not
gate that phase or require its new syntax in the pilot. W0/W1/W2/W4 remain
independent. [Design §6](../design/workflow_lisp_write_once.md#6-w3-hooks-see-their-context)
owns the target contract and illustrative before/after; the
[closeout](../reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md)
owns current bounded evidence and final gate status.

Owner selection, 2026-10-07: complete the separate pure lexical-capture
correction, then W3 before Phase 5. W3 uses target 2.36 and one `std/improve`
API per source import graph; old source callers migrate when their graph is
retargeted. The accepted bounded contract is recorded in
[design §§6/9](../design/workflow_lisp_write_once.md#6-w3-hooks-see-their-context)
and the Phase 4c plan. Existing targets, complete compiled snapshot authority,
conflict refusal and truthful-pin/resume rules remain preserved obligations.
Selection alone establishes neither executable feasibility nor delivery; the
current status records subsequent bounded implementation evidence.

Decisions and remaining scope:

| # | Decision | Recommendation |
| --- | --- | --- |
| 1 | Which of the rules W0 to W5 are accepted | W3 is selected, qualified by Task 4 independently of unselected W0/W1/W2/W4; W5 stays deferred |
| 2 | The target for each selected language change | W3 uses target 2.36 on the evaluated route as Phase 4c. Other repetition rules retain their own unselected target decisions |
| 3 | The module that owns declarations shared by a workflow family and unused by the standard library | One module per family under `workflows/library/`, named for the family |
| 4 | The adoption bar for W3 | Preserve behavior while removing the context-only record/constructor, forwarding parameter and restated hook signatures. Review actual callers and edit locality; line counts are supporting evidence, not a percentage gate |
| 5 | Where provider defaults are written | The provider externs file |
| 6 | How the context-free `improve` signature replaces the current API | Select one builtin source API by graph entry target: old entries preserve the old module bytes/path; 2.36 graphs use the no-context variant and migrate old source calls. Preserve complete snapshot authority, conflict checks and old-target build/resume evidence; inventory indirect consumers too |
| 7 | Who implements Phase B | The runtime owner, because the change is in provider configuration and shared validation |

Depends on: the
[shared defect repairs plan](2026-09-29-workflow-lisp-shared-defect-repairs-plan.md)
merged to `main`. Tasks 7 and 8 edit the typechecker handlers that plan
repaired.

Out of scope: the compiler defects recorded in the
[value/effect separation decision brief](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md);
broad migration of older workflows to the new target (parent Phase 6b owns
that rollout; Task 14 proves the representative W3 consumers); the Design
Delta family.

## Global Constraints

- Older targets accept and lower exactly what they do at the commit each
  phase starts from. Evidence is byte identity of every build artifact at one
  fixed path with `PYTHONHASHSEED=0`, with the orchestrator package at one
  fixed path as well. Preserve truthful package/command-closure pins; report
  genuine pin changes separately from fixed-identity equality, as the evaluated
  design §13 requires. Safe refusal does not prove successful retained-run resume.
- A program using no new authoring form preserves its values, effects and
  resume behavior. Compare canonical output within the selected route;
  do not require flat and evaluated routes to serialize identically.
- A new form has the same canonical output as its explicit equivalent on
  the same route, excluding source provenance where that route requires it.
- Every refusal has a diagnostic code and a source location.
- Tests assert behavior through the public run entry. No test asserts prompt
  text.
- New modules stay under 500 lines and new functions under cyclomatic
  complexity 12.
- No broad or full-suite test run while other agents are running. One full
  run at each phase closeout, alone, in tmux.
- Commit by pathspec. Commit messages carry no tool or assistant attribution.

## Review Focus

1. Importing a declaration in place of a local copy changes the qualified
   name of a type. A workflow's contracts, output schemas and checkpoint
   digests may name it. Task 1 compares them before and after, per workflow.
2. A constructor without its type name in a position with no expected type
   must be rejected with a located diagnostic, never resolved by a guess.
   Task 8 tests each position of design section 4.3.
3. A bare tag that two visible unions declare must resolve to the expected
   union and to no other. Task 8 tests it with three unions sharing one tag.
4. Passing the expected type through more forms must not change the type of
   any program that compiles today. Task 7 proves it on the corpus before any
   new form exists.
5. A binding's default must not apply to a call that sets the option, and a
   changed default must be seen by resume as a source change. Task 5 tests
   both.

## Baseline

Before Phase A, from the repository root:

```bash
python experiments/orc_repetition_census/declaration_repeats.py .
```

Expected at the census commit: 201 declarations, 61 repeats, 44 identical,
253 lines in repeats. Record the output.

---

## A. No Language Change

### Task 1: Import Declarations That Are Repeated With Identical Text

- [ ] Complete

**Read/trace:** the census, section 4.2; the export lists of
`orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`, `std/resource.orc`
and `std/context.orc`; how a build artifact names a type
(`orchestrator/workflow_lisp/normalized_type_descriptor.py`,
`orchestrator/workflow_lisp/contracts.py`).
**Update:** the corpus files under `workflows/examples/` and
`workflows/library/` that repeat a declaration with identical text.
**Create:** one module per family for declarations the standard library does
not own, as decision 3 records.

1. List every declaration that repeats with identical text, the module that
   will own it, and the files that will import it.
2. For each file, before editing: compile it and keep every build artifact,
   and run its existing tests.
3. Replace the local declaration by an import. Add the name to the owner's
   export list where it is missing.
4. After editing: compile and run the same tests. Report, per workflow, which
   artifacts changed and why. A change in a qualified type name is expected;
   a change in a field, a contract or a step is a defect.
5. Run `declaration_repeats.py` and record the counts.

### Task 2: Resolve Names Declared With Differing Text

- [ ] Complete

**Read/trace:** each declaration of `DesignDocPath`, `BlockerClass`,
`ReviewDecision`, and every other name the census reports as repeated and not
identical.
**Update:** the files that declare them.

1. For each name, write a table of its definitions: file, fields or values,
   and what differs.
2. Apply this rule. Where one definition contains the others, keep it, export
   it from its owner and import it. Where two definitions mean different
   things, rename the narrower one for what it means.
3. Where neither applies, stop and report the name with its table. Do not
   choose.
4. Verify as in Task 1, steps 2 and 4.

### Task 3: Lint For A Declaration That Repeats An Importable One

- [ ] Complete

**Read/trace:** `orchestrator/workflow_lisp/linting.py`, the existing lint
codes and how `--dry-run` prints them.
**Update:** `linting.py`.
**Create:** `tests/test_workflow_lisp_lint_declaration_repeats.py`.

1. Write failing tests: a module that declares a path family identical to one
   `std/phase` exports gets the warning `declaration_repeats_importable`,
   located at the declaration, naming the module to import from; a module
   that declares a record of the same name and different fields gets none; a
   module that imports the type gets none.
2. Implement. Compare definitions, not text.
3. Run the lint over the corpus. After Tasks 1 and 2 it reports nothing.

### Task 4: Qualify W3 On Concrete Callers

- [ ] Complete

Bounded qualification update, 2026-10-07: the [Phase 6a pilot assessment](../reports/2026-10-07-evaluated-execution-phase-6a-pilot.md#w3-specimen-and-qualification-status) records current-syntax explicit/bound callers, public parity/capture/resume and review-only locality evidence, proposed-only W3 counts and a bounded caller inventory. All 21 pilot cases pass in its full campaign, which remains RED overall; that report owns closeout status. No overall size reduction or W3 feasibility is established. The owner subsequently selected W3 at 2.36 and graph migration as recorded above. That historical cut established no W3 feasibility. Recovered Task 4 now has accepted bounded scratch proof, followed by accepted Tasks 6/11–13 and bounded 14A/14B/F-CODE-1. The subsequent exact final-package compatibility03 controls are accepted; the Phase 4c closeout owns qualification and delivery; the pure prerequisite is freshly revalidated within its exact exception and shared final gate status is recorded there.

**Read/trace:** `experiments/orc_repetition_census/variants/`, the
`let-proc` and `bind-proc` contracts, design §6,
`orchestrator/workflow_lisp/stdlib_modules/std/improve.orc`, its maintained
callers and public compile/run/resume fixtures. Trace capture ownership
through `procedure_typecheck.py`, specialization and the selected execution
route; the existing capture/replay defects in composition-first §11 are
required counterexamples, not behavior to preserve.
**Create:** variants under `experiments/orc_repetition_census/variants/`,
stored as `.orc.txt`; an addendum to the census report.

1. Write a local copy of `improve` without `inputs I`, in a scratch module.
2. Rewrite `reviewed_change.orc` against it, with hooks that take their
   context through `bind-proc` or `let-proc` as the language allows today.
   Keep every behaviour of the original; where one cannot be kept, record the
   diagnostic.
3. Count lines with `count_lines.py`, in the census's categories.
4. Write a second variant as design §6.3 would allow it, and count it.
   Mark proposed syntax as non-runnable. Qualify the selected multiple-binding
   grammar, how a directly supplied local `proc-ref` obtains its expected
   signature, and diagnostics for missing or incompatible expectations. Neither hook
   may refer to itself or a sibling; general inference remains out of scope.
   Use the selected grammar in design §6.3. An incomplete signature requires
   exactly one authored direct consumer call, checked before inference across
   the whole consumer. Record the `need`/`seed` counterexample: both call orders
   refuse shared incomplete `h(x)=x`; full `(Int)->Int` annotations permit reuse.
   Several arguments of one call share a site; repeated activations are legal.
5. Report both counts against the hand-written variant (92 lines at the
   census baseline). Assess the actual record/constructor/parameter deletions
   and the change needed when only one hook needs another enclosing value.
   Preserve domain records that have uses beyond context forwarding. Use
   decision 4, not the former 10 % threshold, for the adoption recommendation.
6. Apply the recorded 2.36/one-API-per-source-graph selection to the caller
   inventory; qualify old-target artifacts, retained-run resume and snapshot
   authority without changing truthful pins or conflict guards. A local scratch
   helper is feasibility evidence, not a second production API. Resolve execution-route gaps before claiming
   public run/resume proof; a compiler-only spike is insufficient.

## B. Provider Options Bound Once

### Task 5: Defaults On A Provider Binding

- [ ] Complete

**Read/trace:** how the provider externs file is read
(`orchestrator/workflow_lisp/build_manifest_io.py`,
`orchestrator/workflow_lisp/build_artifacts.py`), how call options reach a
provider (`orchestrator/providers/registry.py`, call policy bindings), the
diagnostic `provider_parameters_missing`, `specs/providers.md`.
**Update:** the externs reader, shared validation, `specs/providers.md`.
**Create:** `tests/test_workflow_lisp_provider_binding_defaults.py`.

1. Write failing tests, with stand-in providers:
   - a binding written as an object supplies `model`, `effort` and
     `timeout_sec` to a call that sets none;
   - a call that sets an option overrides the binding for that option only;
   - a binding written as a string behaves as today;
   - a required parameter that the call, the binding and the template all
     omit is rejected at compile time, located at the call;
   - the build artifacts of a workflow are identical whether an option is on
     the call or on the binding;
   - resume after the binding's default changed is refused as a source
     change;
   - one supervision call, one peer-group call and one adjudication call take
     their options from the binding.
2. Implement.
3. State the rule and the order of precedence in `specs/providers.md`.
4. Move the repeated options of
   `experiments/orc_vs_single_call/workflows/*.orc` to their providers files
   and show that their build artifacts do not change.

## C. Construction From The Expected Type

### Task 6: Register The New Target

- [x] Complete for selected W3 scope — bounded coordinator acceptance in the Phase 4c plan; no selection of other repetition rules.

**Read/trace:** how target 2.33 was registered: `specs/versioning.md`,
`orchestrator/workflow_lisp/syntax.py`,
`orchestrator/workflow/validation.py`, `tests/test_workflow_lisp_target_233.py`.
**Update:** those owners.
For selected W3, register only 2.36 through the bounded Phase 4c plan;
this does not select W1 or the other repetition rules.
**Tests:** `tests/test_workflow_lisp_w3_target.py` for W3; choose separate
owners after selection for other rules. The existing
`tests/test_workflow_lisp_target_234.py` owns numeric-target evidence and must
not be replaced or presented as repetition-reduction delivery.

1. Write failing tests: a module at the new target that uses no new form
   compiles and retains its behavior; compare canonical output to the same
   execution route's baseline, with older-target controls unchanged.
2. Register the target and one predicate named for it.

### Task 7: Pass The Expected Type Through Every Position Of Design Section 4.2

- [ ] Complete

**Read/trace:** `orchestrator/workflow_lisp/typecheck_dispatch.py`
(`typecheck_expression`, `_typecheck` and its `recurse`, which resets the
expected type), `typecheck_structural_values.py` (the empty `(list)`),
`typecheck_proofs.py` (`match`, `if`, `cond`), `typecheck_loop_recur.py`,
`loop_state.py`, `procedure_typecheck.py`, `workflows.py`.
**Update:** those owners.
**Create:** `tests/test_workflow_lisp_expected_type_positions.py`.

1. Write failing tests at the new target with the one form that already uses
   an expected type, the empty `(list)`: it compiles in a `let*` body, a
   `with-phase` body, as a `done` value, as an `:on-exhausted` value and as a
   `loop-state` field, where a declaration fixes the type. It is still
   rejected with `list_empty_type_context_required` as a `let*` binding.
2. Write the controls at 2.33: each of those programs is rejected as today.
3. Implement. A loop takes its expected type from its position and passes it
   to `done` and `:on-exhausted`.
4. Compile the whole corpus at its own targets: artifacts remain identical.
   For retargeted programs, compare before/after expected-type threading on
   the selected route; do not conflate this change with runtime migration.

### Task 8: Constructors Without A Type Name

- [ ] Complete

**Read/trace:** `orchestrator/workflow_lisp/expressions.py`
(`_elaborate_record`, `_elaborate_variant`, and `_trial_record_sections`),
`typecheck_dispatch.py` (the record and variant branches),
`typecheck_pure_ops.py` (a bare tag resolved against a union),
`orchestrator/workflow_lisp/form_registry.py`.
**Update:** those owners.
**Create:** `tests/test_workflow_lisp_expected_type_constructors.py`.

1. Write failing tests at the new target:
   - `(record :k v)` and `(variant V :k v)` compile at each position of
     design section 4.2 and run to the value the explicit form gives;
   - each builds artifacts identical to the explicit form;
   - at each position of section 4.3 the form is rejected with
     `constructor_type_context_required`, located at the constructor;
   - with three visible unions that declare one tag, the tag resolves to the
     expected union;
   - a tag the expected union does not declare is rejected with
     `constructor_variant_not_in_expected_union`;
   - a generic procedure whose body writes `(variant V …)`, imported and
     inlined in a module that does not import the union, compiles and runs;
   - `(record :key value)` inside a `trial` section behaves as today.
2. Write the controls at 2.33: both forms are parse errors, as today.
3. Implement.
4. Rewrite `std/improve.orc` with constructors that omit
   `Improvement[S F B]`. Its callers' build artifacts are identical.

### Task 9: Documents For Phases A To C

- [ ] Complete

**Update:** `specs/versioning.md`, `specs/providers.md`,
`docs/lisp_workflow_drafting_guide.md`,
`docs/design/workflow_lisp_frontend_specification.md`,
`docs/design/workflow_lisp_parametric_type_system.md` (the rule that a
constructor names its type), `docs/orc_workflow_design_lessons.md`,
`docs/capability_status_matrix.md`, `docs/index.md`.

1. State the new target's contract.
2. Replace the rule that a constructor names its type by the rule of design
   section 4, in the documents that state it.
3. Add W0 to the drafting guide: import before declaring, with the lint's
   name.
4. Run the documentation test selectors and check every link edited.

## D. Effects Inferred

### Task 10: Plan The Effect Ledger Simplification

- [ ] Complete

The design exists and lists its own prerequisites. This task writes its plan.

**Read:** `docs/design/workflow_lisp_effect_ledger_simplification.md`,
`docs/reports/2026-09-08-workflow-lisp-effect-tracking-audit.md`, roadmap
entry EL-1.
**Create:** `docs/plans/<date>-workflow-lisp-effect-inference-plan.md`.

1. Record the target of decision 2 as the design's target.
2. Turn each prerequisite of the design (defining-scope resolution of effect
   subjects, carriage of the restriction's origin, mixed-target linking,
   editor projection) into a task with its fixture.
3. Turn each acceptance lane of the design into a closeout item.

## E. Hooks That Capture Their Context

This is the technical breakdown of the parent's Phase 4c. Entry: Phase 3's
runtime, the Phase 6a caller assessment, and Task 4's grammar, inference,
capture ownership, target/module compatibility and decision-4 evidence.
Task 6 registers the selected target before new syntax is admitted. Tasks
11 → 12 → 13 → 14 form the W3 delivery order; unrelated W0/W1/W2/W4 delivery
is not a prerequisite. Public run/resume acceptance uses Phase 3's evaluator.

### Task 11: Several Bindings In One `let-proc`

- [x] Complete for selected W3 scope — bounded coordinator acceptance in the Phase 4c plan; no selection of other repetition rules.

**Read/trace:** `docs/design/workflow_lisp_let_proc_local_proc_refs.md`
(sections 9, 10, 12 and 13), the `let-proc` elaboration and its generated
procedures.
**Update:** the `let-proc` owners.
**Create:** `tests/test_workflow_lisp_let_proc_bindings.py`.

1. Write failing tests at the new target: two local procedures in one form,
   both passed by `proc-ref` to one helper, compile and run; a local
   procedure that names another of the same form, or itself, is rejected with
   a located diagnostic. Older targets retain their single-binding syntax;
   scope escape and nested local-procedure definitions remain refused.
2. Extend the existing binding representation and all structural users,
   including both closed local key/DId walkers. Preserve existing-target
   single-binding generated procedures and identities; Task 12's selected
   2.36 capture canonicalization governs new-target output.

### Task 12: Captures Inferred

- [x] Complete for selected W3 scope — bounded coordinator acceptance in the Phase 4c plan; no selection of other repetition rules.

**Update:** the `let-proc` owners.
**Create:** tests in `tests/test_workflow_lisp_let_proc_bindings.py`.

1. Write failing tests: without `:captures`, a body that uses names of the
   enclosing scope compiles and runs like the form with the list written; a
   name bound both outside and as a parameter is the parameter; an authored
   list that omits a name the body uses is rejected, naming the name. A later
   call-site binder cannot change a captured value. Capturing a committed
   effect result does not dispatch it again, either fresh or on resume.
2. Implement through the existing capture/specialization owners. Record a
   deterministic resolved-name ordering of used captures at 2.36 for both
   spellings, dropping allowed unused entries after validation. Compare omitted,
   reordered and superset explicit lists; retain old-target authored order.
   Include field roots and lexical ProcRef callees, excluding nonlexical names.
   Do not serialize runtime procedure/closure values or add another evaluator
   or capture store.

### Task 13: A Local Procedure Takes Its Signature From The Expected Type

- [x] Complete for selected W3 scope — bounded coordinator acceptance in the Phase 4c plan; no selection of other repetition rules.

**Read/trace:** `_infer_parametric_type_bindings` and
`_typecheck_parametric_procedure_call` in `procedure_typecheck.py`.
**Update:** those owners and the `let-proc` owners.
**Create:** `tests/test_workflow_lisp_local_hook_signatures.py`.

1. Write failing tests: a local procedure passed directly to a `ProcRef`
   parameter omits its parameter types and its return type; the callee's type
   parameters are bound from the other arguments and from the body; a local
   procedure whose body does not fit the expected type is rejected at the
   body. Exercise the pair of review/revise hooks: the review result fixes
   feedback/blocker types used by the revise signature. An unresolved or
   conflicting expectation gets a located diagnostic requesting explicit
   types, rather than a guess or source-order-dependent result.
2. Before consumer typechecking, count direct sites by structural occurrence
   path and lexical local binding, not name/span/object identity; refuse zero,
   multiple or indirect sites for an incomplete signature. Fully annotated
   signatures retain reuse and forwarding. Test both `need`/`seed` orders,
   both annotated counterparts, disjoint same-name locals, repeated same-call
   arguments with agreeing/conflicting expectations and repeated activations.
3. At the one call, type ordinary/full arguments and group all pending local
   occurrences; reuse the existing unifier. Check a body once when all residual
   parameters are concrete, unify its return, then advance newly ready hooks.
   Reverse declaration/argument order; reject stuck/conflicting expectations.
   Keep temporary state scoped and feed complete signatures to existing
   generated-procedure/ProcRef specialization before closed construction.
   Compare inferred and fully annotated forms;
   effect declarations keep their current rules unless W2 is separately
   selected and delivered.

### Task 14: `improve` Without `inputs`

- [ ] Complete

Bounded Task14A/14B and F-CODE-1 are accepted: representative public consumers,
pilots, graph/snapshot/package source selection and usefulness are demonstrated.
Exact old-artifact/resume/replay and migrated-source refusal have subsequent
bounded acceptance. The
[closeout](../reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md)
records the 30-row Phase 6b handoff and exact retained limits.

**Preserve:** legacy `orchestrator/workflow_lisp/stdlib_modules/std/improve.orc`
bytes/path. **Create:** alternate `stdlib_modules/w3/std/improve.orc` with
header 2.33 and correct source root. **Update:** builtin candidate selection
in existing compiler/module owners, `workflows/examples/improve_experiment_proposal.orc`
and its tests,
`docs/design/workflow_lisp_composition_first.md`, the drafting guide's
section on `improve`.
**Create:** the measured helper variant of `reviewed_change.orc` as a test
program.

1. Apply design §9's selected graph rule, then change only the new helper's
   signature as §6.4 gives it: remove `I`, `inputs`, and hook forwarding.
   Old entries retain the old source; every source importer in a 2.36 graph
   sees the new API. Preserve per-defining-module syntax admission, user-root
   ambiguity and actual source/root provenance across public compiler/LSP
   entries and package installation. Old five-argument source calls require
   a located migration diagnostic; old type-only/compatible imports remain legal.
   Complete snapshots retain producer authority and sole-old admission;
   differing canonical overlap still refuses, without reopening sources.
   Inventory every affected maintained caller and fixture; retain historical
   measurement copies as evidence.
2. Rewrite the example and measured helper variant with local hooks; remove
   only context-only records/constructors. Retain reusable top-level hooks
   through existing `bind-proc` where that is clearer. Leave one public
   signature per resolved stdlib module, without an `improve-v2` wrapper.
   These are Phase 4c's representative migrations; hand the remaining
   maintained-consumer inventory and migration recipe to parent Phase 6b.
3. Prove APPROVED, BLOCKED and EXHAUSTED results, final candidate and feedback,
   bounded review/revise ordering, distinct captures for two helper calls
   using distinct inferred locals or fully annotated reused locals,
   lexical shadowing and committed-boundary resume through public entries
   with deterministic fixture providers. Check effect invocation counts and
   raw older-target artifact identity at fixed identity inputs and actual
   compatible retained-run resume. Report authentic changed-pin/source refusals
   separately; never rewrite pins/digests or count refusal as successful resume.
   No live study is required.
4. Report the before/after callers, deleted declarations and forwarding, and
   line counts against decision 4. Update the local-procedure baseline,
   composition-first contract, drafting guide, capability/design indexes and
   this roadmap together when the feature lands; do not publish proposed
   syntax as supported before that evidence exists.

## F. Constraints That Bind

### Task 15: Deferred

W5 is planned when its condition in design section 8.4 holds.

---

## Closeout, Per Phase

- [ ] Run the census scripts and record the counts beside the baseline.
- [ ] Byte identity for older targets, as the global constraints state.
- [ ] Full suite in tmux, alone: `pytest -q -n 16 --dist=worksteal`, compared
  with the failure set of the commit the phase started from; no new
  failures.
- [ ] Public evidence, fresh output: compile, run and resume of one program
  per new form.
- [ ] Review of the phase by a reviewer of a model family other than the
  implementer's.
- [ ] Merge to `main` by fast-forward; push.

## Expected Result

Figures are taken from the census. Those marked estimated are not measured.

| Phase | Rule | Repetition removed |
| --- | --- | --- |
| A | W0 | Up to 253 lines of repeated declarations, 8.9 % of the corpus |
| B | W4 | The options of 20 calls; 9 lines in `reviewed_change.orc` |
| C | W1 | The type name at 76 of 105 constructor sites; 1,583 characters; no line |
| D | W2 | 27 lines of `:effects` clauses, and the edits they force when a helper changes |
| E | W3 | Estimated: one record, one constructor and the restated hook signatures per caller of a helper; about 20 lines in the measured workflow |
