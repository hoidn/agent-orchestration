# Effect Tracking and Language Ergonomics

Review boundary: this audit assessed EL-1's original 2026-08-15 proposal.
The subsequent [2026-09-08 revision](../design/workflow_lisp_effect_ledger_simplification.md)
and separate [pure-call design](../design/workflow_lisp_pure_call_composition.md)
respond to its recommendations. Critiques of the original proposal below are
retained as audit evidence, not descriptions of the revised target or evidence
that either target is implemented.

## Assessment

Workflow Lisp's effect system is partly overbuilt, but the useful target for
simplification is not effect knowledge itself. The strongest evidence concerns
mandatory, identity-specific declarations that mirror inferred facts; the
conflation of procedure-call structure with impurity; and inconsistent meaning
of declarations across ordinary and specialized procedures. Keeping an inferred
account of provider calls, command calls, workflow boundaries, and other
operations remains valuable for compilation, composition, explanation, and
resumability. These conclusions do not depend on execution safety as an
investment criterion.[^1][^2][^3][^4]

The recommended direction is **inference by default, deliberate checked
contracts where useful, and a clear separation between effects, expression
representability, call structure, and execution evidence**. Do not replace this
with either a handwritten ledger everywhere or a single Boolean everywhere.
Do not select a new algebraic-effect language or runtime merely to repair the
current ergonomics.

The existing EL-1 simplification proposal is directionally helpful but should
not be implemented unchanged. Its empty-ceiling rule conflicts with currently
accepted specialization behavior; its named declarations would cease checking
their names; and its claim to preserve every decision conflicts with its
intentional changes to declaration acceptance. It also deliberately preserves
the most concrete pure-procedure composition restriction.[^6]

| Question | Finding | Confidence |
| --- | --- | --- |
| Is mandatory exact annotation over-specified? | Yes as the default for every ordinary helper; it restates information already inferred. Intentional boundary assertions remain useful. | High: implementation and compile experiments. |
| Does the effect machinery decrease ergonomics? | Yes in demonstrated refactoring and expression-composition cases; not uniformly across all authoring. | High for the cases, unmeasured for aggregate developer time. |
| Is internal effect representation heavier than its consumers need? | Many consumers require only a few predicates, while rich call-site data has separate uses. A split is justified to investigate. | Moderate to high; no performance profile establishes the size of the gain. |
| Should all effect tracking be removed? | No. Doing so would discard useful closure, placement, and explanation facts or require rebuilding them elsewhere. | High. |
| Does this justify abandoning or reimplementing the whole language? | No on this evidence. The problems are identifiable and separable. Reconsider the foundation if later composition work shows a structural limit. | Moderate: broader language feasibility is outside this audit. |

## Scope and evidence

The assessment covers the working tree on 2026-09-08, based on commit
`2effff14a1c9028ac56d9e4893a39a333bff59f9` plus existing uncommitted work. It
distinguishes the implemented compiler from the proposed EL-1 effect-ledger
simplification and proposed PC-1 provider-context values. Neither proposal is
an implemented authoring surface.[^6][^15]

Evidence comprises source tracing, a parsed census of authored `.orc` files,
temporary compile-only counterexamples, existing focused tests, and primary
language documentation for comparison. No live provider calls or study assessments
were needed. Compilation checks used the existing compiler and shared
validation; they establish acceptance behavior, not measured author productivity
or end-to-end superiority over another language.

The conceptual criteria are programmability/compositionality, reuse,
introspection, self-programmability, and optimization in program space. Tool
execution remains an agent/provider responsibility. Correct ordering, input
identity, and reuse of completed work matter here because they determine
whether a program does the intended work, not because this report is assessing
execution-safety policy.

## Four different things called effects

Much apparent disagreement disappears when four responsibilities are separated.

| Layer | Current responsibility | What would be lost by deleting it |
| --- | --- | --- |
| Authored `:effects` | The author repeats a set of named dependencies/operations; ordinary procedures must exactly match inferred transitive atoms. | A deliberately written dependency assertion, but not the compiler's ability to infer those dependencies. |
| Inferred `EffectSummary` | Carries direct atoms, transitive atoms, and located procedure-call edges through typing and specialization. | Compiler knowledge used for placement, boundary classification, closure, and resolving calls. |
| Semantic operation records | Describe lowered provider/command/resource/view operations and source provenance. | Useful explanation of the executable workflow. |
| Checkpoint and dependency evidence | Describes concrete inputs, outputs, policies, and identities needed to reuse or resume work. | Correct distinction between reusable completed work and work that must execute again. |

These layers are related, not interchangeable. Semantic IR reconstructs
operation records from lowered steps and their configuration; it does not simply
consume the typed `EffectSummary`. Checkpoint policy construction dispatches on
operation kinds and concrete contracts. Pure-result replay inspects executable
pure-projection nodes and their bindings. Therefore reducing frontend metadata
does not require deleting runtime evidence, and preserving runtime evidence does
not justify mandatory annotations on every helper.[^8][^9][^10]

The effect-graph contract's requirement that abstractions expose effects to IR
does not logically require authors to enumerate every inferred dependency by
hand. The distinction also fits the language principles that compiler-owned
obligations should not become standing author/provider bookkeeping.[^1][^14]

## Measured annotation burden

The broad census enumerated files under `workflows/` and
`orchestrator/workflow_lisp/stdlib_modules/`, confirmed they were tracked, and
parsed their S-expressions. It excluded the three workflow experiment files
from product/stdlib totals. Effect-clause spans run from the `:effects` keyword
through its closing list; source-line totals are physical lines.

| Source group | Files | Source lines | Procedures | Empty clauses | Effect-clause lines | Authored atoms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Examples | 10 | 1,123 | 9 | 0 | 10 | 10 |
| Library | 20 | 3,842 | 24 | 9 | 47 | 38 |
| Compiler stdlib | 4 | 799 | 9 | 5 | 11 | 6 |
| Total | 34 | 5,764 | 42 | 14 | 68 | 54 |

The 42 procedures all have declarations. Their clauses occupy 4,207 characters,
1.18% of total selected source lines, and 5.16% of the procedures' 1,319 lines.
The 54 atoms comprise 21 `calls-workflow`, 17 `uses-provider`, 13 `uses-command`,
and three `writes`. They contain 33 distinct literal kind/subject pairs, hence
21 repeated occurrences across declarations. Repetition is not automatically
redundancy: an independent intentional assertion may reasonably repeat a fact.

EL-1's headline count of 42 declarations and 14 empty clauses is reproducible,
but it is a broad source census, not 42 currently preferred runtime procedures.
The narrower registry `wcc_default` examples/library group has ten source files
and only three procedures. Much annotation density is in migrated Design Delta
code; the broad library count also includes explicit runtime fixtures and older
unregistered files. The 393 tracked test-fixture sources, including negative
syntax cases, are not product usage evidence.[^7]

Consequently, **annotation text does not dominate this codebase**. The stronger
case against the mandate is the maintenance and abstraction boundary it creates,
not a large number of removable lines.

## Demonstrated ergonomic costs

### Exact transitive declarations propagate implementation changes

Ordinary procedures are validated with set equality, not an upper bound.
Removing an effect, retaining an unused declared permission, or omitting the
clause all fail compilation. The compiler computes the transitive closure
before performing this comparison.[^3][^4]

This reduced program compiles with shared validation:

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defrecord Result (ok Bool))
  (defworkflow leaf () -> Result (record Result :ok true))
  (defproc inner () -> Result
    :effects ((calls-workflow leaf))
    :lowering inline
    (call leaf))
  (defproc outer () -> Result
    :effects ((calls-workflow leaf))
    :lowering inline
    (inner))
  (defworkflow entry () -> Result (outer)))
```

Renaming `leaf` and its call, without updating declarations, produces
`procedure_effect_mismatch` on `inner`. Updating only `inner` exposes the same
error on `outer`. Updating both succeeds. Replacing the child call with its
record expression causes the same two-level annotation-removal propagation.

These changes preserve the returned value and add no provider/command I/O,
but renaming or removing a workflow boundary changes its durable call identity.
They are not invisible to all orchestration semantics. The ergonomic finding
is that the compiler already knows the changed identity while still requiring
authors to restate it at each ordinary wrapper. An author could update all
clauses at once; the experiment does not prove everyone incurs sequential
repair rounds.

This is not merely a toy structure. In the Design Delta library,
`route-blocked-implementation` declares six effects;
`route-blocked-implementation-stdlib` repeats those six while adapting the
result; and `run-selected-item-stdlib` includes them in a twelve-atom clause.
Qualified workflow and provider names cross abstraction boundaries.[^16]

The consequence is stronger implementation coupling than a reusable wrapper's
input/output contract ordinarily needs. It particularly penalizes experiments
that substitute providers, remove work, or rearrange helper boundaries.

### An effect-free procedure is not freely composable as a pure expression

The following helper has no inferred runtime-effect atoms:

```lisp
(defproc helper () -> Int
  :effects ()
  :lowering inline
  7)
```

Nevertheless, this use fails:

```lisp
(record Result :value (helper))
```

The diagnostic is `effect_not_permitted`: record fields must be pure and the
work should first be bound in `let*`. This version succeeds:

```lisp
(let* ((value (helper)))
  (record Result :value value))
```

Changing the helper to an equivalent `defun` also permits direct use. Further
target-2.26 compile checks show the boundary clearly:

| Use of the same constant-returning helper | `defproc` | Equivalent `defun` |
| --- | --- | --- |
| Record field | Reject | Accept |
| List element | Reject | Accept |
| `list/map` body | Reject | Accept |
| Body of another `defun` | Reject | Accept |
| Bind before record/list construction | Accept | Accept |
| `if` condition through `(= (helper) 7)` | Accept | Accept |

The cause is not hidden provider work. A procedure call adds a located call
edge; several positions compare the entire summary with `EMPTY_EFFECT_SUMMARY`.
An edge-only summary therefore fails. Pure functions also reject procedure
calls by AST category. Target-2.26 conditions already have a normalization path
that accepts the tested call, so it would be false to say all pure positions
have the same limitation.[^2][^5][^11]

This is an abstraction penalty: a helper usable as a `ProcRef` hook is not
automatically usable where its equivalent pure function is accepted. Choosing
`defun` is a practical workaround for simple helpers, but not a general account
of composability between these callable forms.

The current lowerer may require a statement boundary or normalization before a
call can appear in a projection. Merely ignoring call edges in a Boolean purity
check is not a complete fix. The language should distinguish **no external
effects** from **currently representable in this expression position**, then
either normalize a supported call or explain the actual representation limit.

### Empty declarations have different meanings after specialization

Generic and `ProcRef` specialization is an important counterexample to the claim
that every caller must enumerate every selected hook's effects. The compiler
recomputes the selected effects but explicitly skips declared equality for
specializations and generated names. This already enables useful effect
propagation without a handwritten transitive ledger.[^4][^12]

For example, this valid helper can acquire workflow-call effects:

```lisp
(defproc forward
  ((runner ProcRef[() -> Result]))
  -> Result
  :effects ()
  :lowering inline
  (runner))
```

A full shared-validation experiment passing `inner` from the first example
produced:

```text
forward:                 declared=(), inferred=()
specialized forward:     declared=(), inferred=(calls-workflow(leaf))
```

Existing tests also cover selecting command and provider hooks and retaining
their effects. This is useful behavior, not a recommendation to disable
inference. But it means a reader cannot universally interpret today's
`:effects ()` as “this execution performs no effects.” The stdlib's
`backlog-drain-proc` uses precisely this empty-declaration pattern.[^12]

### Declared and inferred visibility must not be confused

Current procedure completion text renders `signature.declared_effects`. With
specialization exemptions, that is not necessarily the complete execution
footprint of a selected call. Making annotations optional without updating
introspection would further reduce what an author sees.[^13]

The right replacement for obligatory source text is not invisibility. An
inspection surface should distinguish the authored restriction, the generic
definition's known effects, and the resolved call's inferred effects. It can
reuse existing compiler/source-map information rather than introduce another
effect registry or a new dashboard.

## What earns its keep

Inference remains justified even if no execution-safety benefit is counted.
An imported procedure or selected hook can contain work not apparent at its
call site. The compiler must know whether that work belongs in a pure
projection, needs an execution boundary, or contains a child run/trial that a
particular construct does not support. Local syntax inspection alone cannot
answer those questions across abstractions.[^4][^5]

The consumer inventory also rules out replacing everything with one bit:

| Consumer | Actual information needed |
| --- | --- |
| Ordinary pure-position checks | A positional/representability decision; currently call edges are included. |
| Child-run/trial placement | Whether child-run or trial work occurs. |
| Workflow-only boundary classification | Whether operations are exclusively workflow calls; a generic impure bit loses this distinction. |
| WCC specialization and cycle diagnostics | Resolved callee identities and located call sites, not just effect kinds. |
| Optional dependency assertions and precise diagnostics | Named atoms where the contract actually checks identities. |
| Path-program admission | Current admission tests atom-set emptiness; richer facts are additionally persisted and affect inspection/identity. |

Located call edges have a real use in WCC specialization resolution. They can
move to call metadata, but cannot be discarded because many purity consumers
do not inspect them. Path admission has a serialization compatibility obligation
even though its acceptance decision needs much less information.[^17][^18]

Precise runtime operation records also support reuse and diagnosis. Knowing
that a provider was invoked is not sufficient to reuse its result: the selected
inputs, output contract, committed result, and applicable checkpoint policy
still matter. None of those should be reconstructed from an optional
handwritten effect clause.[^8][^9][^10]

Conversely, current declarations are not a general model of provider tools'
filesystem effects. `WriteEffect` is inferred for materialized views using the
view identity. Reads, publications, and state-update atoms have parser support
but no inferred producers were found in the inspected compiler. The same
`apply_resource_transition` command atom represents several different resource
operations, whose detailed meaning lives elsewhere. A provider or command
classification does not establish that two calls commute or that their results
are interchangeable.[^2][^19]

## Review of the EL-1 proposal

EL-1 appropriately recognizes that inferred knowledge and authored repetition
are different; that call edges are not themselves side effects; and that
runtime evidence must survive a frontend simplification. It is not yet a
sufficient implementation contract.[^6]

### 1. Inference and authored assertions have different enforcement value

The proposal's claim that annotations add no enforcement value is too strong.
Inference determines what the program may do. An intentional annotation can
state what a library boundary is allowed to do. Adding an unexpected provider
or replacing a named command can violate that intention while remaining a
well-typed executable program.

The argument for optional declarations is that not every helper needs such an
assertion—not that assertions are useless. For an intentional maximum contract,
allowing fewer effects is ordinarily more useful than demanding exact equality.
An exhaustive change inventory could instead be generated and reviewed as a
diff; it need not be a compilation obligation everywhere.

Exact equality also detects removal of an intended dependency. Subset ceilings
deliberately give up that disappearance alarm. This can matter at selected
boundaries, although membership in a possible-effect set does not prove an
operation actually ran on the required branch. Preserve important execution
requirements in behavioral checks; do not mistake an upper bound for an
execution-completeness guarantee.

### 2. Named declarations must not silently become kind-only restrictions

EL-1 retains a clause such as:

```lisp
:effects ((uses-provider providers.review))
```

but stops validating its subject. Under that proposed interpretation, calling
another provider would satisfy the clause because both map to `provider`.
That is a material weakening, not merely optional annotation.

The smaller coherent first change is optional, identity-aware subset assertions
using the existing atoms. If coarse ceilings prove useful, give them an
unmistakably coarse contract; do not preserve apparently checked names as
decoration. This separates removing compulsory text from deciding how much
precision an explicit restriction buys.

### 3. Empty-ceiling compatibility requires an explicit migration decision

“Existing equality implies coverage” does not prove compatibility for
specialized procedures, because they never satisfied the equality check in the
first place. Enforcing EL-1's pure-empty rule after specialization rejects the
valid `forward` example. Keeping the exemption means an empty clause is not
universally a purity assertion.

A new inference-default regime should migrate effect-forwarding helpers to
omitted declarations, reserve explicit empty for an actual enforced restriction,
and specify how that restriction is checked on each resolved specialization.
Existing targets must retain their old meaning until deliberately migrated.
This needs a clear language-version or migration boundary, not a silent
reinterpretation. It does not require building runtime effect polymorphism as
a prerequisite: today's specialization can still propagate inferred effects.

### 4. Representation cleanup and ergonomic improvement are independent

EL-1 preserves edge-only positional impurity explicitly. That can be sensible
for a behavior-preserving internal refactor, but it leaves the record/list
counterexamples unchanged. Its current ordering also places structural work
before optional annotations. The immediate authoring improvement can be scoped
independently of replacing the entire per-node representation.

### 5. Decision-equivalence claims need a precise domain

Dropping `ReadEffect` is not equivalent on arbitrary summaries: an actual read
atom makes current pure-position, structural-boundary, and path-admission
predicates reject. No reachable inferred producer was found, so removal may be
valid for the current reachable language; that narrower claim needs to be
stated and tested. A later stored-context load must not be accidentally treated
as pure just because reads were absent from this census.

Likewise, strict-Boolean normalization currently uses expression classes; its
function receives a summary but does not decide normalization by reading it.
The proposed consumer inventory should describe the actual decision path,
rather than mechanically replacing every mention of a summary with a predicate.

### 6. Verification must allow intended language changes

The proposal requires identical accept/reject outcomes and diagnostic codes
over the whole corpus while deliberately accepting omitted clauses and surplus
permissions and retiring diagnostics. Those requirements cannot all hold
without an explicit exception set.

Separate the comparison: an internal representation change must preserve
existing decisions; an authoring-contract change must pass its newly specified
acceptance and rejection cases. Keep unchanged runtime contracts and relevant
resume behavior checked across both. A temporary comparison harness should
disappear after it has answered its question, not become a second compiler.

### 7. Richness should follow consumers, not a fixed simplification ideology

Fifteen atom classes exist, while only nine kinds are authorable and four occur
in the broad product/stdlib declarations. Some promoted atoms have no current
production constructors. This supports a targeted deletion review, not deletion
of every unused spelling: negative tests, persisted records, and concrete future
contracts have different compatibility implications.

The audit found no evidence quantifying memory or compile-time savings from
shrinking summaries. Immutable storage sharing, traversal count, and call-graph
shape matter. Do not promise a speedup from class counts alone. Conversely, a
future useful consumer may justify identity-rich analysis again at a particular
boundary; the proposed small footprint should not become an unquestionable
foundation.

## Implications for the five axes and provider context

| Axis | Useful effect knowledge | Current obstacle and preferred direction |
| --- | --- | --- |
| Programmability/compositionality | Infer what selected procedures and hooks require. | Exact restatement and edge-only impurity constrain ordinary composition. Keep inference, improve normalization and callable interoperability. |
| Reuse | Expose relevant dependencies and retain concrete input/output identity for reuse. | Subject identities repeated through wrappers couple helpers to internals. Make restrictions intentional; keep identity at its actual owners. |
| Introspection | Explain possible operations, chosen bindings, and actual completed execution separately. | Declared clauses and flat sets are incomplete explanations. Distinguish restrictions, inferred footprints, call structure, and actual traces. |
| Self-programmability | Check the consequences of an agent-authored program revision automatically. | Requiring an agent to update a deterministically derivable ledger adds repair work. Infer it; preserve constraints the task deliberately chose. |
| Search/optimization | Reject incompatible candidates early and expose useful program features. | Annotations create avoidable coupled edits; name-specific restrictions may block meaningful substitutions. Search executable behavior, not redundant mirrors. |

Effect sets are generally descriptions of possible work, not execution counts,
order, causality, task quality, or cost. A union cannot tell an optimizer whether
a provider runs once or repeatedly, or whether a tool operation consumed the
right artifact. Whole-task evaluation and actual execution evidence remain
necessary. No search-throughput or agent-token improvement was measured here.

For proposed provider-context values, the useful distinction is between
manipulating already materialized immutable content and loading, capturing,
exporting, or model-summarizing context. The first can be pure; the others have
I/O or provider effects. Passing a value through a record is not itself a
provider invocation. Context lineage also belongs to value/execution provenance,
not a growing list of mandatory effect names on every wrapper.[^15]

The pure-procedure counterexamples are therefore relevant to PC-1's requirement
for ordinary aggregate, generic, and loop-carried composition. They are not
proof that first-class context is impossible. They identify a language boundary
to resolve if it obstructs a useful implementation.

Future unbounded recursion and runtime-selected callables would change the
analysis problem. Current cycle rejection is part of finite specialization and
lowering, not a theorem that effect inference requires an acyclic language.
Recursive analysis can require a fixed point; termination and I/O are different
properties. Revisit that foundation when a concrete consumer warrants it,
rather than adding a general recursion/effect-row system speculatively.

## Comparison with other language designs

Koka provides a useful counterexample to the idea that effects inherently
require repeated handwritten ledgers. It infers function effects and supports
an effect-polymorphic `map`: the mapping operation propagates its callback's
effects. It also distinguishes possible nontermination from other effects.
The transferable lesson is inferred, compositional effect knowledge—not that
Workflow Lisp should adopt Koka's compiler or full handler system.[^20][^23]

Unison similarly infers requirements from called functions and checks that a
call's required abilities fit the available set. An explicitly empty ability
set excludes abilities. That illustrates why an optional restriction can be
meaningful without exact equality between permitted and used operations.[^21]

OCaml 5.4 has effect handlers without static checking that every performed
effect is handled. This demonstrates that runtime effect mechanisms and static
effect tracking are independent design choices. It does not establish that
removing Workflow Lisp's existing inference would preserve its compiler's
placement or specialization behavior.[^22]

These are architectural comparisons, not controlled ergonomics studies.
Workflow Lisp currently describes statically compiled workflow operations; it
does not expose Koka/Unison-style user-defined operation handlers. A wholesale
move to that foundation requires a recurring benefit such as genuinely needed
runtime higher-order composition or handler-based substitution, not resemblance
in terminology.

## Recommended next decisions

1. **Separate the decisions before implementing EL-1.** Treat optional authored
   contracts, internal representation cleanup, and expression-composition
   improvement as independently reviewable changes. None should claim the
   benefits of the others.
2. **Prioritize inference-default ergonomics.** Retain existing named atoms for
   optional subset assertions initially. Define specialization and target-version
   semantics, including migration of empty effect-forwarding declarations.
   An explicit restriction should be checked, including after specialization.
3. **Address the demonstrated pure-call boundary.** Start with the existing
   inline, constant-returning counterexample. Preserve evaluation order and
   call/source ownership while establishing which pure procedure uses can be
   normalized. Do not implement this by weakening a guard without corresponding
   lowering support.
4. **Preserve useful inspection.** Show inferred effects at resolved call sites
   separately from authored restrictions, using existing compiler projections.
   Keep possible effects distinct from actual execution and dependency evidence.
5. **Simplify internals by demonstrated consumer need.** Separate located calls
   from operation classifications; remove unused propagation only after checking
   consumers and persisted facts. Profile before promising performance gains.
6. **Evaluate utility with real authoring changes.** Compare adding/removing an
   operation, substituting a provider, adapting an imported generic hook, and
   composing a pure helper. Measure source edits, affected files, failed compile
   rounds, and actual author/agent effort. Retain improvements that help; cancel
   or simplify machinery that adds no value.

No new benchmark platform is needed for the initial decision. The retained
counterexamples and representative existing workflows already provide useful
small checks. A passing minimum example should lead to a supported expansion or
a clear limitation, not a blanket claim of language superiority.

## Verification and limitations

Five narrow existing procedure tests passed. The complete selected effect,
procedure, and lexical-checkpoint modules then passed with
`pytest -q -n 16 --dist=worksteal`: **230 passed in 4.07s**, exit 0. This is a
baseline check, not verification of an implemented simplification. The full
repository suite was not run because no production behavior changed.

The temporary counterexample set contains nine declaration/refactoring cases,
fourteen pure-call placement cases, and one specialization case. Seventeen
selected cases and the specialization case were independently reproduced through
`compile_stage3_module(..., validate_shared=True)` using the default WCC route.
The broader matrix's remaining record/list variants were checked in the initial
investigation. No runtime/provider launch was performed by these probes.

Local reproducibility evidence remains under `/tmp/orc-effect-audit.Kc8ZHT/`;
the selected-suite output is `/tmp/orc-effect-audit.vx0CvO/tests.log`. These
temporary paths are not permanent contracts. The minimal source examples above,
named compiler entrypoint, and cited existing tests describe the durable
reproduction method. Corpus headline counts were also cross-checked directly
against the selected source roots.

There is no measured developer-time, agent-token, search-success, memory, or
compile-speed improvement for the alternatives. The evidence supports concrete
friction and semantic inconsistencies, not a quantified return on a rewrite.
This report changes no compiler, accepted design, roadmap selection, active
workflow, or execution budget.

## Sources

[^1]: Repository, [Workflow Lisp Effect Graph](../design/workflow_lisp_effect_graph.md), especially Purpose, Procedure Effect Views, and Validation Responsibilities. Current component contract; its coverage wording is less specific than the implementation's exact-equality rule.
[^2]: Repository, [effect algebra](../../orchestrator/workflow_lisp/effects.py), `EffectSummary`, `effect_summary_from_procedure_call`, `merge_effect_summaries`, and `parse_effect_clause`.
[^3]: Repository, [procedure definitions and validation](../../orchestrator/workflow_lisp/procedures.py), `validate_procedure_effects`, `_elaborate_procedure_definition`, and `_raise_missing_effects`.
[^4]: Repository, [compiler](../../orchestrator/workflow_lisp/compiler.py), `_validate_procedure_effects_and_cycles`, especially monomorphic closure and the specialization/generated-name exemptions.
[^5]: Repository, [expression typechecking](../../orchestrator/workflow_lisp/typecheck_dispatch.py), record and union field checks; [structural-value checking](../../orchestrator/workflow_lisp/typecheck_structural_values.py), list/list-map checks; [pure helpers](../../orchestrator/workflow_lisp/functions.py), `_find_purity_violation`.
[^6]: Repository, [Workflow Lisp Effect Ledger Simplification](../design/workflow_lisp_effect_ledger_simplification.md), proposed EL-1; Summary, Declarations, Compatibility, Verification Strategy, and Implementation Handoff. Not accepted implementation.
[^7]: Repository, [workflow route-readiness registry](../workflow_lisp_route_readiness_registry.json), [examples](../../workflows/examples/), [library](../../workflows/library/), and [compiler stdlib](../../orchestrator/workflow_lisp/stdlib_modules/). Working-tree source census described in this report.
[^8]: Repository, [Semantic IR](../../orchestrator/workflow/semantic_ir.py), construction of command, resource-transition, and materialized-view effect entries from lowered operations.
[^9]: Repository, [WCC defunctionalization](../../orchestrator/workflow_lisp/wcc/defunctionalize.py), `_build_effect_resume_policy_payload`; [checkpoint effect policies](../../orchestrator/workflow_lisp/lexical_checkpoint_effect_policies.py).
[^10]: Repository, [pure-result replay](../../orchestrator/workflow/pure_result_replay.py), executable pure-projection eligibility and binding/dependency-index construction.
[^11]: Repository, [strict Boolean normalization](../../orchestrator/workflow_lisp/conditionals.py), `_contains_effect` and `normalize_condition_expr`; [proof/type checking](../../orchestrator/workflow_lisp/typecheck_proofs.py), condition admissibility.
[^12]: Repository, [procedure tests](../../tests/test_workflow_lisp_procedures.py), `test_selected_hook_recomputes_transitive_effects`, `test_compile_stage3_preserves_effect_visibility_for_constrained_generic_procref_fixture`, and nested workflow-effect checks; [std/drain](../../orchestrator/workflow_lisp/stdlib_modules/std/drain.orc), `backlog-drain-proc`.
[^13]: Repository, [LSP navigation](../../orchestrator/lsp/navigation.py), `_procedure_completion`, which currently renders declared effects.
[^14]: Repository, [Workflow Language Design Principles](../design/workflow_language_design_principles.md), principles 13–17, 21, 26, 29, and 30. Guidance rather than a claim that every desired surface is implemented.
[^15]: Repository, [Provider Context Values](../design/workflow_lisp_provider_context_values.md) and [Capability Status Matrix](../capability_status_matrix.md), first-class provider-context and effect-ledger-simplification rows. Both proposals remain unimplemented.
[^16]: Repository, [Design Delta work-item composition](../../workflows/library/lisp_frontend_design_delta/work_item.orc), `route-blocked-implementation`, `route-blocked-implementation-stdlib`, and `run-selected-item-stdlib`.
[^17]: Repository, [WCC elaboration](../../orchestrator/workflow_lisp/wcc/elaborate.py), located procedure-edge mapping and specialization selection; [boundary classification](../../orchestrator/workflow_lisp/phase_family_boundary.py), `is_structural_pure_projection_effect_summary`.
[^18]: Repository, [path-program compilation/admission](../../orchestrator/workflow/run_ref/path_compile.py), `_compile`, `_effect_facts`, and `compile_and_admit_path_program`. Full build precedes the admission check; Semantic IR is available at this consumer.
[^19]: Repository, [resource/view typechecking](../../orchestrator/workflow_lisp/typecheck_resource_view.py), resource-transition and materialized-view effect construction; [effect tests](../../tests/test_workflow_lisp_effects.py).
[^20]: Daan Leijen, [The Koka Programming Language](https://koka-lang.github.io/koka/doc/book.html), March 17, 2026, sections 2.2 and 3.2.3. Primary documentation on inference, effect-polymorphic mapping, and divergence; accessed September 8, 2026.
[^21]: Unison, [Abilities and ability handlers](https://www.unison-lang.org/docs/language-reference/abilities-and-ability-handlers/), sections Abilities in function types, The typechecking rule for abilities, and Ability inference; accessed September 8, 2026.
[^22]: OCaml, [OCaml 5.4 manual: Effect handlers](https://ocaml.org/manual/5.4/effects.html), Unhandled effects; accessed September 8, 2026.
[^23]: Daan Leijen, [Koka: Programming with Row Polymorphic Effect Types](https://arxiv.org/abs/1406.2061), 2014. Primary research on inferred polymorphic effect types; used as conceptual corroboration, not empirical evidence of `.orc` ergonomics.
