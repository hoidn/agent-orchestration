# From Flat Steps To Evaluated Execution: Why The Flat Route Is Being Retired

- **Status:** historical record and learning summary. It proposes nothing and
  selects nothing. Current status belongs to the
  [capability matrix](../capability_status_matrix.md), the
  [consolidation design](../design/workflow_lisp_consolidation.md) and the
  [executor retirement design](../design/workflow_lisp_executor_retirement.md).
- **Date:** 2026-10-13, `main` at `3f897f33`.
- **Kind:** retrospective. It reads the decision records, designs, plans and
  closeouts listed in section 10 and arranges their reasoning in order. Every
  number is quoted from one of them or measured on the named revision.
- **Audience:** someone who meets `orchestrator/workflow_lisp/lowering/`,
  `orchestrator/workflow/executor.py` or `wcc/defunctionalize.py` and asks why
  they exist, why they are scheduled for deletion, and why they are still here.

## 1. What Is Being Retired, And What Is Not

The phrase "retiring flat and WCC" needs one correction. The workflow core
calculus (WCC) is not being retired. What is being retired is the **flat
route**: the compilation path that defunctionalizes WCC into a flat list of
steps, and the runtime that executes those steps. WCC elaboration itself is
the front half of the evaluated route and stays.

| Component | Lines on 2026-10-13 | Disposition | Owner of the decision |
| --- | ---: | --- | --- |
| `orchestrator/workflow/executor.py` (`WorkflowExecutor`, the flat validated step runtime) | 16,340 | Delete after gate R | [Retirement design §6](../design/workflow_lisp_executor_retirement.md#6-target-ownership-and-deletions) |
| `orchestrator/workflow_lisp/lowering/` (per-form flat lowerers, pure projection, control loops) | 23,915 | Delete exclusive flat-step production | same |
| `orchestrator/workflow_lisp/wcc/{defunctionalize,lower}.py` (WCC to flat steps) | 7,983 | Delete | same |
| `orchestrator/workflow/lowering.py`, `workflow/pure_result_replay.py`, `workflow_lisp/lexical_checkpoint*.py` (replay index, positional resume, serialized checkpoints) | 12,510 | Delete; keep only read-only decoding a reader still needs | same |
| `orchestrator/workflow_lisp/wcc/{model,elaborate,anf,analysis,hygiene}.py` (the calculus, elaboration, ANF, scope/effect/proof analysis) | 10,253 | **Keep.** Feeds the closed program at targets 2.35 and later | [Core calculus §15](../design/workflow_lisp_core_calculus_middle_end.md#15-alternatives-considered) |
| `orchestrator/contracts/closed_program/`, `orchestrator/workflow/evaluated/` | 13,068 | The route that remains | [Evaluated execution](../design/workflow_lisp_evaluated_execution.md) |
| `exec/step_executor.py`, `providers/`, run-reference services | n/a | Keep; shared performers used by both routes | [Consolidation design](../design/workflow_lisp_consolidation.md#ownership-and-target-topology) |

Nothing in the first four rows has been deleted. The
[consolidation closeout](2026-10-12-workflow-lisp-consolidation-closeout.md#size-measurement-and-deletion-status)
states it plainly: "No old executor or flat lowering has been deleted.
Extraction changes ownership; consumer migration and the retirement gates
still precede their removal." Line counts are observations at one revision,
not a promise of savings; the decision records say the same.

## 2. Timeline

| Date | Event | Record |
| --- | --- | --- |
| 2026-02 to 2026-03 | `WorkflowExecutor` enforces output contracts; executor kernel consolidated. Workflows are YAML; the runtime executes a flat validated step list | `ad16d3a1`, `f18d155c` |
| 2026-05-09 to 05-19 | Workflow Lisp frontend: parser, types, macros, `defproc`, modules. A "Stage 3 lowering bridge" turns each surface form into flat steps, form by form | `87f171a1`, `a468a74b` |
| 2026-06-09 | Migrating the Design Delta drain to `.orc` finds that nested structured control (a loop inside a branch) is rejected by lowering although it typechecks. Root cause named: a surface language with no middle end | [drain findings](2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md) |
| 2026-06-09 | Core calculus design accepted: elaborate every form into WCC, normalize to ANF, analyze, defunctionalize second-class join points into the **same flat runtime**. Authority inversion (executing the calculus) is "deferred, not rejected"; Temporal-style journal replay is rejected | [core calculus](../design/workflow_lisp_core_calculus_middle_end.md) |
| 2026-06 to 2026-09 | Tranches M0 to M5 move the route onto WCC through target 2.34. Positional limits keep appearing; each gets a repair where it occurs | core calculus §12 |
| 2026-07-26 | M0 decision brief records re-spend traced to positional invalidation and names memo-first resume as the evidence that reopens the question | [M0 brief](2026-07-26-m0-decision-brief.md) |
| 2026-09-08 | Effect-tracking audit: the effect system is "partly overbuilt"; reconsider the foundation if composition work shows a structural limit | [audit](2026-09-08-workflow-lisp-effect-tracking-audit.md) |
| 2026-09-28 | Composition work for the single-call comparison produces six positional limits in one day | [comparison](2026-09-28-orc-versus-single-call.md) |
| 2026-09-29 | Decision brief: the six limits share one cause; five options compared; owner approves the option-independent repairs and a bounded spike. Execution facts and the repetition census are recorded the same day | [brief](2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md), [facts](2026-09-29-workflow-lisp-execution-facts.md), [census](2026-09-29-workflow-lisp-repetition-census.md) |
| 2026-09-29 | A search controller written five ways against the flat route meets three separate refusals and a 361-node expression against a 256-node bound | [limitations](2026-09-29-orc-language-limitations-and-solutions.md) |
| 2026-09-29 | Spike of evaluated execution, three adversarial reviews, gate G1: build it at a new target; keep the flat route for existing targets | [gate report](2026-09-29-evaluated-execution-spike.md) |
| 2026-09-30 | Target 2.35 selected. `compile` gains a public entry that stops after typecheck | `141e8553` |
| 2026-10-01 to 10-02 | Phase 2: the closed program, compile-only at 2.35; 52-export corpus | [Phase 2 closeout](2026-10-02-workflow-lisp-evaluated-execution-phase-2-closeout.md) |
| 2026-10-02 to 10-07 | Phase 3: values, memo, attempts, command closure evidence, interpreter pins, provider IO, resume replay, invalidation, run references, readers. Delivered at `06130a53` | [Phase 3 closeout](2026-10-02-workflow-lisp-evaluated-execution-phase-3-closeout.md) |
| 2026-10-06 | `specs/{state,cli,io,versioning}.md` gain the evaluated profile at 2.35 | `73a27652` |
| 2026-10-07 | Phase 6a pilot; pure-capture correction; W3 "write each fact once" at 2.36; Phase 5 parallel map registered at 2.37 | [6a pilot](2026-10-07-evaluated-execution-phase-6a-pilot.md), [4c closeout](2026-10-07-evaluated-execution-phase-4c-w3-closeout.md), [Phase 5 closeout](2026-10-07-evaluated-execution-phase-5-closeout.md) |
| 2026-10-12 | Consolidation design and plan; extraction Tasks 0 to 4 accepted at `bfd0f324`: the runtime no longer imports the compiler. Nothing deleted | [consolidation closeout](2026-10-12-workflow-lisp-consolidation-closeout.md) |
| 2026-10-13 | Executor retirement design and plan drafted: serial best-of-N migration, finite consumer dispositions, gate R, deletion table. All tasks unselected | [retirement design](../design/workflow_lisp_executor_retirement.md), [plan](../plans/2026-10-13-best-of-n-and-executor-retirement-plan.md) |

## 3. Three Architectures, One Runtime Model Too Many

### 3.1 Flat validated steps

The original runtime executes a plan of steps. Its edges express order,
fallthrough, transfer and loop body; it has no edge for "this value depends on
that one". A result is stored under its step's presentation name, and one
value can end up in as many as seven places. Resume is positional: the runtime
finds where it was by step and iteration ordinal. A provider attempt's
identity includes its visit count, so an interrupted call gets a new identity
on resume. These are the runtime facts the decision brief records in its
section 2.3, and they were adequate for YAML workflows whose steps were
written by hand.

### 3.2 WCC: a real middle end over the same runtime

The June 2026 drain migration showed that composition failures were not
isolated bugs. Each surface form had its own lowerer that only knew how to emit
top-level shapes, so a well-typed nested composition died after shared
validation with no owned diagnostic. The core calculus design fixed the
compiler's half: every form elaborates into one small calculus, ANF
normalization atomizes effectful subexpressions, analysis computes scope,
effects and proofs, and defunctionalization turns second-class join points
into the flat step graph the existing runtime already executes. The payoff
was meant to be categorical: "anything that typechecks elaborates and lowers".

The design was explicit about what it did not change. Alternatives considered
in §15 included authority inversion, running the calculus directly, which was
deferred with a revisit condition: after the flat route has proven the
calculus on a real promoted family. Journal replay in the style of Temporal
was rejected because it trades static effect visibility, validation before
commit and machine-diffable parity for composition generality.

### 3.3 Evaluated execution

The September design keeps typecheck and elaboration to WCC and replaces what
comes after. A compiled workflow is a closed program: a table of definitions
with effect sites listed before any run. The runtime evaluates it in a
lexical environment. Values are computed and have no stored copy. An effect is
identified by its site in its definition and the path of activations that
reached it, and nothing else. An effect runs only when the memo holds no
committed result for its identity. Resume evaluates the program again from its
entry and takes each committed result from the memo.

## 4. Why The Middle End Was Not Enough

The decision brief reproduced six limits at `main` `1fb5b167`. Each had a
local cause in a different file: an effect map rebuilt from local procedures
only, a `loop-state` passed through unexamined, a `match` typechecker that
discards its subject, lowering that emits references the type does not
declare, an inliner that forgets to substitute specialized types, a result
bundle that reads a variant field without proof. A rewrite that pre-binds
subexpressions fixes two of the six.

Behind the six instances the brief names one rule: **at run time a value
exists only as the output of a step.** Three consequences follow.

1. **Branching needs a producer.** A `match` is a transfer between steps
   chosen by a step's output. A union that no step produced cannot be a
   subject.
2. **Pure computation is a second world.** Pure expressions were bolted on as
   `pure_projection` steps plus a run-time replay index. Every position that
   accepts a value has to say which world it accepts, and the worlds have
   different rules.
3. **The effect system is consumed for placement.** Inferred effects decide
   whether work becomes a pure projection or needs an execution boundary, so
   an error in inference changes how code is lowered, not just what is
   reported.

WCC removed the per-form lowerers, but defunctionalization still had to land
every value in a step of the same runtime. The calculus held up to the
lowering boundary and the runtime's value model reintroduced the positional
rules on the other side. The same work was being done in several places
because of it: three inliners, three binders, two pure evaluators, and a loop
lowering that elaborated to WCC, converted back to a surface expression, and
lowered that with the older lowerer.

The runtime facts made the cost concrete. A result file was written to a path
with no iteration part and never removed; a command that wrote its result only
in iteration 1 completed iterations 2 and 3 with iteration 1's value, and a
second run read the first run's file. Nothing bound what a command actually
ran. The workspace was not captured. Each is a defect in its own right, and
each is cheaper to fix in a model where an effect has an identity and an
attempt has its own result path.

## 5. How The Decision Was Made

### 5.1 Five options, compared on fixed criteria

| Option | Removes the producer rule | Totality | Disposition |
| --- | --- | --- | --- |
| A. Repair the flat route | No | By enumeration of forms × positions | Measured first (5.2), then rejected at G1 |
| B. Flat steps, pure values as expressions evaluated on demand | Yes | By enumeration, fewer positions | Not chosen; keeps defunctionalization and positional resume |
| C. Inverted runtime with an effect memo | Yes | By construction: evaluation is recursion over the calculus | Selected at G1 |
| D. Everything is a step | Boundary removed | n/a | Not recommended; multiplies stored rows |
| E. A library in a host language | n/a | n/a | Rejected; loses checks before a run and the bound on agent-authored workflows |

The brief's comparison table also recorded the size of the code that would
serve only the mechanism being replaced: `lowering/` 22,767 lines,
`wcc/defunctionalize.py` 7,630, lexical checkpoints 7,409,
`pure_result_replay.py` 2,929. It added, in the same breath, that these are
sizes of existing modules and not a promise of deletion.

### 5.2 Measure the repair rate before deciding

The owner approved the repairs that no option made obsolete (effect map,
`match` subject, specialization substitution, replay index at `--dry-run`,
result path per call, scoped pending-effect rule, bound prefixes), plus a
generated matrix of forms × positions so that "every program that typechecks
must compile and run" became a number. The repairs ran as the
[shared defect repairs plan](../plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md),
and the gate report records what the number did:

| Fact about repairing the flat route | Value |
| --- | --- |
| Tasks at the start, at the end | 10, 16 |
| Matrix cells that typecheck and still fail after all repairs | 34 of 120 |
| Rounds of repair on one defect class (name capture); each review found another site | 4 |
| Environments in which lowering resolves a name | 6 |
| Forms found outside the matrix in one day by people writing programs | 6 |
| Separate refusals met by one search controller | 3 |

"Every one of these has one cause." The repairs were still worth making: they
removed silent wrong values and made resume, the workspace lock and result
files correct for the programs that run today, which the new route also
needed.

### 5.3 A spike with its criteria fixed in advance

The spike was throwaway code under `experiments/evaluated_execution_spike/`,
not wired to `orchestrator run`, with nine criteria written into the plan
before it started and a size bound of 2,000 lines "to make the claim
falsifiable". It ran three iterations; after each, a reviewer of another model
family attacked it with programs of its own, and each review asked for
changes.

| Criterion | Result |
| --- | --- |
| Every fixture that typechecks evaluates | 100 matrix cells including the 32 the flat route fails; the six brief programs; a loop in a branch, a loop in a loop; `std/improve`. 38 of 52 shipped workflows built |
| The search controller makes the decisions of its Python reference | 72 pairs of leaf scenario and budget, source unchanged |
| Interrupt after each effect, resume, same result, no committed effect twice | 168 in-process stops, 96 external kills |
| Identity unchanged under blank lines and a move of program and package | Pass; and identity does change when an effect's meaning changes |
| Every memo identity is an instance of a site listed before the run | Pass on every run |
| Parity with the flat route on programs both accept | Equal values and effect order on 68 cells; eight request fields differ, each by a stated rule |
| Evaluator and memo under 2,000 lines | 625 |

The reviews found what the implementer's own tests had not: a committed
result was reused after the command's script changed (the flat route has the
same defect and returns a mixed value, 206, where an uninterrupted run gives 6
or 306); five more ways to change what a command runs without changing the
bytes that were bound; a view that said "completed" before a coordinator's
final commit; invalidation that missed a dependence through a file, which a
shipped workflow (`verified_iteration_drain/drain.orc`) has. Each became a
condition on the first release rather than an adjustment of the criterion.

### 5.4 Decisions that are hard to reverse once memos exist on disk

The spike had to guess 38 decisions the design did not make. The last review
named the five whose wrong choice is hardest to undo:

| Decision | Choice |
| --- | --- |
| Identity of an effect | A table of definitions, each body stored once; identity is the site within its definition plus the activation path. Halves the largest shipped program (2,659 nodes to 1,284) against a tree with one callee body per call path |
| Meaning of the terminal record | Written last, after every settlement; the only source of "completed" |
| What a command declares | Its implementation files, read-only; declaration required, even when it is nothing |
| What invalidation covers | The chosen effect and every later committed effect, until file dependence is declared |
| Whether a request carries the run's variables | No; the run's identity reaches a program only as a value |

Gate G1 selected building evaluated execution in stages at a new target, with
the first release limited to commands, portable composed providers, calls and
run references, and the review conditions in its acceptance.

## 6. Delivering Without Breaking The Old Route

- **A new target, not a flag.** Target 2.35 selects the evaluated route in the
  source header. Targets through 2.34 keep the flat route unchanged, so the
  change is reversible while it is confined.
- **Compile first, run later.** Phase 2 shipped the closed program with public
  `run` and `resume` still refusing (`evaluated_execution_unavailable`), so
  the compiler's output could be checked against the 52-export corpus before
  any runtime existed.
- **Byte identity as the regression guard for old targets.** Phase 3's final
  audit at `ef689a39` compared build artifacts for older targets: 88 of 88 raw
  public artifact pairs equal, with the 12 pin-derived differences in authentic
  capsules explained separately. Parity with the new route is behavioral by
  design: ordered effect identities, input digests, result digests and final
  value.
- **Real programs as acceptance.** The controller's 72 pairs at 2.35; doubling
  its state fields and branches (14 to 28, 27 to 54) leaves it running with no
  limit on expression size; the `std/improve` example and the two comparison
  workflows unchanged apart from the target.
- **Honest full-suite baselines.** The Phase 2 base completed RED (275
  failed); the original Phase 3 full suite completed RED (402 failed) and every
  failure received a disposition. No test was relaxed to manufacture green.
- **Each later capability got its own target and gate.** W3 at 2.36, parallel
  map registered at 2.37 with bounded qualification. Neither implies the
  retirement of anything.

## 7. Why Deletion Is Gated Rather Than Done

The delivery plan is unambiguous about intent: "Two runtimes are a migration
cost, not the intended permanent architecture; retirement is a delivery
milestone, not indefinite optional cleanup." It is equally unambiguous about
order: Phase 7 retirement enters after maintained consumers run at the new
target and the owner's decision 8 gives existing runs a disposition.

The October work turned that into mechanics.

- **Consolidation extracted before it deleted.** The evaluated runtime
  imported `workflow_lisp.closed` and compiler-owned prompt helpers. The
  consolidation moved the closed-program loader and checker to
  `contracts/closed_program/` and provider IO carriers to
  `workflow/evaluated/provider_io.py`, so parent evaluation, inspection and
  coordinator recovery import no compiler, including through deferred imports.
  The net line change of the extraction alone was +137. Renaming directories
  removes neither a dependency nor an execution path, and the closeout says so.
- **A finite inventory with four dispositions.** Every `.orc` root, Python
  caller, registry row and launch recipe gets `migrate`, `retain
  evaluated/shared`, `retire executable` or `read-only history`. An unresolved
  row blocks cutoff; it does not open a port project. The run census found
  4,173 state files under `.orchestrate/`, all schema 2.1.
- **Recovery through a retained release, not a shim.** Old checkpoints are
  recovered on an exact retained release and environment where interrupted
  recovery is demonstrated, or their resumability is explicitly retired. No
  compatibility backend, legacy adapter or dormant fallback remains in the new
  package.
- **One gate, R.** Delete only when every frozen consumer and run family has
  its disposition, migrated consumers pass public lifecycle checks, old-route
  refusal is non-mutating, recovery claims are evidenced, and no candidate has
  a supported execution caller. Deletion and cutoff ship in the same change.
- **The trap named in advance.** A path-mode run reference lets an evaluated
  parent invoke an old child through `child.py`; a 2.24 child inside a 2.35
  parent is a real dependency in the test suite. Ending top-level CLI admission
  is not enough.
- **Order amended by evidence.** Serial best-of-N already runs at 2.35 through
  a public consumer test, so the retirement draft proposes migrating it without
  waiting for Phase 5 parallel map. Waiting for everything was rejected as the
  default dependency; a legacy backend was rejected outright.

## 8. Learnings

1. **Count positions before fixing the next one.** The flat route's defects
   were real and each had a one-file cause. What settled the question was a
   generated matrix of forms × positions that made "done" a number and showed
   the rate: four rounds on one defect class, 34 of 120 cells still failing,
   six new forms found in a day.
2. **A middle end cannot repair the backend's value model.** WCC gave
   composition by construction up to the lowering boundary. The runtime's rule
   that a value is a step output reintroduced positional rules past it. Ask
   where the authority over "what is a value" lives before investing in the
   layer above it.
3. **Defer explicitly, with a revisit condition, and then honor it.** The
   June design deferred authority inversion rather than rejecting it and named
   when to revisit. In September the condition was evaluated on recent
   programs, after the owner ruled the deprecated Design Delta family out as
   evidence.
4. **Fix the criteria and the size bound before the experiment.** "A failed
   criterion is a finding, not a reason to adjust the criterion." The 2,000-line
   bound existed to make the claim falsifiable; the result was 625.
5. **Adversarial review from a different model family, writing its own
   programs, finds what the author's tests do not.** Every review round changed
   the design: closure binding, file dependence, terminal record semantics, the
   request contract.
6. **Repairs on the route being replaced are not wasted.** Silent wrong
   values, stale result files and the workspace lock were fixed on the flat
   route first, and the evaluated route needed every one of them.
7. **Make identity semantic and stable.** Site plus activation path, never a
   source span or file path; blank lines and moves change nothing; a change in
   meaning changes the digest. Bind what a command runs as read-only files, pin
   the interpreter per run rather than per effect, and let invalidation cover
   the whole suffix until file dependence is declared.
8. **Introduce the replacement at a new target and keep old targets
   byte-identical.** Parity of the old route is bytes; parity between routes is
   behavior. Both are machine-checkable.
9. **Keep RED baselines honest.** Full-suite failures were recorded with
   dispositions at every phase instead of being hidden or relaxed.
10. **Extraction is not deletion, and a rename is neither.** The consolidation
    closeout records a net gain of lines and states that nothing was deleted.
    Deletion needs a finite inventory, a retained release for recovery, and one
    gate, with no indefinite compatibility grace period.
11. **Line counts are observations.** Every record that quotes a module size
    says it is not a promise of savings. The retirement plan measures tracked
    production and test lines separately before and after, by the same recipe.
12. **Record owner decisions with dates and keep them separate from
    proposals.** Each design and plan names its selected and unselected items;
    a draft "does not pretend that old targets are already unsupported".

## 9. Open On 2026-10-13

- No old executor, flat lowerer or replay module has been deleted. Gate R is
  unmet; the retirement plan's tasks are unselected, as are the ordering
  amendment, the maintained consumer set and the cutoff and recovery policy.
- Targets through 2.34 still compile and run on the flat route; path-mode
  children at old targets still execute under evaluated parents.
- Global Phase 6a, parallel best-of-N under Phase 5 and evaluated LSP F2
  remain open and are not prerequisites for serial migration.

## 10. Sources

- [Core calculus and middle end](../design/workflow_lisp_core_calculus_middle_end.md), 2026-06-09, updated 2026-10-06
- [Design Delta drain findings](2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md), 2026-06-09
- [M0 decision brief](2026-07-26-m0-decision-brief.md), 2026-07-26
- [Effect-tracking audit](2026-09-08-workflow-lisp-effect-tracking-audit.md), 2026-09-08
- [Value/effect separation decision brief](2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md), 2026-09-29
- [Execution facts](2026-09-29-workflow-lisp-execution-facts.md), 2026-09-29
- [Language limitations found in use](2026-09-29-orc-language-limitations-and-solutions.md), 2026-09-29
- [Shared defect repairs plan](../plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md), 2026-09-29
- [Evaluated execution spike, gate G1](2026-09-29-evaluated-execution-spike.md), 2026-09-29
- [Evaluated execution design](../design/workflow_lisp_evaluated_execution.md) and [delivery plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md), 2026-09-29 onward
- [Phase 2 closeout](2026-10-02-workflow-lisp-evaluated-execution-phase-2-closeout.md) and [Phase 3 closeout](2026-10-02-workflow-lisp-evaluated-execution-phase-3-closeout.md)
- [Consolidation design](../design/workflow_lisp_consolidation.md), [plan](../plans/2026-10-12-workflow-lisp-consolidation-plan.md) and [closeout](2026-10-12-workflow-lisp-consolidation-closeout.md), 2026-10-12
- [Executor retirement design](../design/workflow_lisp_executor_retirement.md) and [plan](../plans/2026-10-13-best-of-n-and-executor-retirement-plan.md), 2026-10-13
