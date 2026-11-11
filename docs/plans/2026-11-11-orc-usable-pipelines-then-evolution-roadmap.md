# ORC Roadmap: Usable Pipelines First, Then Program Evolution

**Status: Draft proposal, not selected.** This page proposes the next project
roadmap. It selects no work, authorizes no provider spend and changes no
contract until the owner selects it. Until then, work selection stays with the
[evaluated-execution delivery plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md)
and the other owners named in the [docs index](../index.md). Accepted designs
and `specs/` own behavior; this page owns only order, gates and dispositions.
It is not a source of copyable examples.

**Goal:** make typed, resumable agent pipelines easy to write and cheap to
iterate on, then test the quality and program-evolution claims on a benchmark
that can actually measure them.

**Basis:** the project audit of 2026-11-11 (code read and provider-free probes
at `bb63b03b`, plus a review of every roadmap and pending design) and the
[structural search closure](2026-10-18-orc-structural-search-roadmap.md#closure-2026-11-11).

## Claims

| Claim | State | Where it is tested |
| --- | --- | --- |
| **Engineering:** long, expensive, multi-agent pipelines get typed handoffs, exact resume and an audit trail | Supported by the runtime; hard to use today | Phases 1–4 |
| **Quality:** a workflow beats one direct call at acceptable cost | Not shown. One small positive (E-A); the rest null, incomplete or unmeasured | Phase 5 |
| **Evolution:** searching over workflow programs finds better quality/cost trade-offs than hand-written ones | Never measured | Phase 6, gated on Phase 5 |

The roadmap is ordered so that every phase before Phase 5 pays off whichever
way the quality and evolution claims turn out.

## Findings this roadmap answers

| Finding (measured 2026-11-11 unless noted) | Phase |
| --- | --- |
| No page says what comes next; forward work is "pending, unselected" across four files; 641 plan files; 420 stray temp directories in the repo root; 127 worktrees | 0 |
| The captured full suite is red (69 failure mechanisms, [simplification record](2026-10-15-orc-simplification-roadmap-extension.md)) | 0 |
| `(continue (command-result …))` crashes the compiler (`compiler_defect`); a loop without `:on-exhausted` compiles and fails at run time; `run` prints nothing on success; every CLI call pays 2.5–4 s of imports; one error per compile | 1 |
| About 25–35k lines of retired architecture survive as types, fixtures and dead helpers; six language targets are gated at 50 call sites | 2 |
| Any semantic source edit refuses resume (`resume_program_changed`); invalidation cancels the whole journal suffix although per-commit dependencies are recorded | 3 |
| The Python frontend lacks parallel map and agents; parallel map is qualified only in a bounded form | 4 |
| Quality scores had σ ≈ 1 on an 8-point scale with two samples per arm, so a 1-point effect needs about 16 samples per arm; the task family (features of this repo) invites contamination | 5 |
| In the three-arm search readout all 18 children converged on one shape and the compiler rejected none; Phase 1 anchors were inverted | 6 |

## Phases

Each phase gets one plan under `docs/plans/` when it starts. Provider budget is
requested once per phase, at its start, and recorded in that plan's ledger.

### Phase 0: Clear the ground

- **Work:** close superseded roadmaps and drafts with a dated note (see
  [Dispositions](#dispositions)); point the index "Select implementation work"
  row at this page; ignore or relocate the temp directories that land in the
  repo root and fix what creates them; prune merged worktrees and branches;
  run the full suite once and record a single number plus a named quarantine
  list with one owner per entry.
- **Exit test:** one page states the next work; `git status` shows no stray
  temp directories; suite status is one number and a list.
- **Spend:** none.
- **Makes harder:** finding old plans by browsing `docs/plans/`.

### Phase 1: The first hour

- **Work:** let-bind effectful subexpressions in `continue`, `match`
  scrutinees and `loop-state :like`, as the Python emitter already does;
  require `:on-exhausted` at compile time; print the result and the next
  command after `run`, and the failing effect and its stderr on failure; make
  the isolation and `jsonschema` imports lazy; add a multi-line prompt literal
  or a prompt-file convention; write a provider-free tutorial of about 150
  lines (compile, run, fail, resume); add the write-once lint W0.
- **Exit test:** the audit's probe workflow compiles on the first attempt;
  `--help` returns in under 0.5 s; a successful `run` prints its result; a new
  author finishes the tutorial without opening another document.
- **Spend:** none.
- **Makes harder:** workflows that omit `:on-exhausted` stop compiling and
  must be fixed.

### Phase 2: Delete and unify

- **Work:** remove the retired IR stack and `LoadedWorkflowBundle`, the
  `StateManager` mutation methods, trial and adjudication execution and their
  type checking, peer groups and supervision, CLI vestiges, and the tests that
  exist only for them. Then migrate in-repo workflows to one language target
  and replace the scattered version predicates with one check. Split contracts
  from evidence ledgers in the design docs and cut the drafting guide.
- **Exit test:** at least 30k lines removed from `orchestrator/`; one admitted
  target; drafting guide under 1,000 lines; suite no worse than the Phase 0
  number.
- **Stop rule:** a workflow that cannot move to the single target without a
  behavior change keeps its target, with the reason recorded.
- **Spend:** none.
- **Makes harder:** reading and reproducing historical runs once their readers
  are gone. Needs owner approval (decision 3).

### Phase 3: Edit and continue

- **Target:** treat the memo as a build cache. An edited program reuses every
  committed effect whose identity and recorded inputs are unchanged;
  invalidation follows recorded dependencies, not journal order.
- **This changes an accepted contract.**
  [Evaluated execution §8.4](../design/workflow_lisp_evaluated_execution.md)
  refuses a changed program before reading the memo. No code is written until
  a design revision is accepted.
- **Work:** a one-week feasibility spike, then the design revision, then
  implementation. The spike must answer:
  1. Do effect identities survive an unrelated edit? Generated binder names
     (`_e0`, `_e1`, `_loop0`) are positional and may shift.
  2. Can replay accept commits in dependency order when the edited program
     reaches them in a different journal order, or no longer reaches some?
  3. Which effects are safe to reuse when a command reads workspace state its
     recorded inputs do not cover?
- **Exit test:** in a four-step run, edit the third step's prompt; resume
  re-runs steps three and four only, and the kill-at-every-commit resume tests
  still pass.
- **Stop rule:** if reuse cannot be made sound without weakening "a committed
  effect never re-runs and never runs with different inputs", ship
  dependency-based invalidation alone and keep the refusal.
- **Spend:** none.
- **Makes harder:** the resume rule stops being "identical program or
  refusal"; reasoning about a run needs the reuse rule too.

### Phase 4: Python first, parallel map

- **Work:** finish the remaining Phase 5 work of the delivery plan (public
  interruption and resume qualification, a best-of-N consumer selected by
  executed tests, closeout); add `parallel_map`, procedure references and
  readable generated names to the
  [Python frontend](../design/python_workflow_frontend.md); run the Agent
  Sessions comparison (PQ-1c) once and then either add `Agent` to the Python
  frontend or retire Agent Sessions.
- **Exit test:** every catalog example has a Python version that builds to the
  same checked program shape; a parallel best-of-N run survives a kill and
  resumes.
- **Spend:** small, for live parallel qualification and PQ-1c. Requested at
  phase start.
- **Makes harder:** `.orc` becomes the generated form most authors never
  write, so `.orc`-only features need a Python route or a reason.

### Phase 5: One real consumer, one cheap benchmark

- **Consumer:** one long pipeline outside this repo with human gates, built on
  [progressive execution](../design/workflow_lisp_progressive_execution.md) as
  an ordinary workflow. The owner names it (decision 5).
- **Benchmark, in order:**
  1. *Zero spend:* from the existing E-A, E-B2, E-B3 and Phase 1 pools,
     compute what selection by tests, by each judge and by agreement would
     have gained.
  2. *Zero spend:* assemble 30–50 small tasks with pre-existing executable
     tests, outside this repo's own features. Qualify the family by its
     oracle check (tests fail at base, pass at the reference fix) and the
     measure on the same known controls, as `AGENTS.md` requires for
     oracle-scored families.
  3. *Spend:* run direct, best-of-3 with executed-test selection, and
     implement–test–repair, plus the remaining catalog programs and two or
     three model placements, once per task on models at or below
     Sonnet/Terra. Record pass/fail and metered tokens per run. This is the
     table Phase 6 searches. Estimate: 240–320 short runs.
- **Exit test:** the consumer completes a real multi-day task with at least
  one resume; the benchmark reports, with bootstrap intervals, whether any
  workflow Pareto-dominates direct.
- **Stop rule:** if no workflow gains 10 pass-rate points over direct at no
  more than three times the tokens, the quality claim is frozen, Phase 6 does
  not open, and the project keeps the engineering claim only.
- **A Python control** (the same three programs written without ORC) runs on
  the same tasks, so a win is attributable to the structure and not the tool.

### Phase 6: Program evolution

Opens only if Phase 5's bar is met. The audit's research review judged
structural search unpromising on current evidence: the meaningful structures
for one coding task number about five, and enumerating them in Phase 1 showed
no separation. This phase exists because the claim was never measured and its
first step is free once Phase 5's table exists.

- **6a, search on the recorded table (zero spend):** replay search policies
  (random, greedy, an LLM proposer choosing among recorded programs) against
  Phase 5's table. Question: does guided search find the best recorded
  program in fewer evaluations than enumeration?
- **6b, generation (spend):** generate new programs and evaluate them on fresh
  tasks.

  | Element | Choice |
  | --- | --- |
  | Individuals | Typed workflow programs |
  | Variation | Typed edits (add a review step, change fan-out, move a model, add a repair loop) alongside free-form LLM proposals, so that children differ in structure |
  | Admission | The compiler |
  | Fitness | Test pass rate and metered token cost, compared by Pareto dominance |
  | Cost control | Children reuse the parent's committed effects where Phase 3 allows |
  | Apparatus | The offline campaign code from the closed search roadmap, reused without its qualification gates; [checked evaluation of generated source](../design/workflow_lisp_checked_program_evaluation.md) only if generation must run inside a workflow |

- **Exit test:** a generated program beats the best hand-written one on fresh
  tasks at equal or lower cost, or a measured negative is recorded.
- **Stop rule:** a fixed budget set at phase start; no extension after a null.
- **Spend:** none for 6a; 6b requested once.

## Order and dependencies

Phases 0 → 1 → 2 run in sequence; each shrinks the next. Phase 3's spike can
start during Phase 2. Phase 4 depends on Phase 1. Phase 5 depends on Phase 4
(best-of-N) and on Phase 1 (a usable tool). Phase 6 depends on Phase 5's table
and bar; 6b is cheaper after Phase 3 but does not require it.

If the owner makes evolution the project's main claim (decision 6), Phases 3
and 5 move ahead of Phases 2 and 4, which shrink to what the benchmark needs.

## Dispositions

| Existing record | Proposed disposition |
| --- | --- |
| [Evaluated-execution delivery plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md) | Keep as owner of its own remaining Phase 5 work, its consumer migration (its Phase 6b) and PQ-1c; correct its stale Phase 4 text |
| [Evolution follow-on roadmap](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md) | Keep the axis lifecycle; close the workstream ledger except agent authoring (AA-1, into Phase 1) and checked evaluation (CE-1, into this roadmap's Phase 6 generation step) |
| [Agent authoring improvements plan](2026-10-02-agent-authoring-improvements-plan.md) | Fold guide and remedy diagnostics into Phase 1 |
| [Structural search roadmap](2026-10-18-orc-structural-search-roadmap.md) and cumulative campaign plan | Stay closed; offline code kept for Phase 6b |
| [Substrate maintenance track](2026-07-26-substrate-maintenance-track.md) | Close as superseded by evaluated execution |
| LSP [P-series](2026-07-30-lsp-frontend-prerequisites-p-series-roadmap.md) and [L6](2026-07-31-workflow-lisp-language-server-l6-utility-roadmap.md) | Close; move multi-diagnostic accumulation (P1) to Phase 1 if cheap |
| [OMP roadmap](2026-08-14-omp-integration-design-and-roadmap.md) OMP-I2 | Drop |
| Confined provider children, provider-phase isolation, typed program gates C2, MLEvolve architecture, private-runtime C2–C6, write-once W4 | Drop or archive |
| [Backlog](../backlog/README.md) | Archive, keeping provider token-usage accounting (needed for the cost objective) |
| Live cumulative campaigns, the natural-difficulty iteration loop, per-step governance for pilots of one to three calls | Stop |

## Owner decisions

1. **Select this roadmap**, as written or amended.
2. **Project claim:** confirm the engineering claim as the claim the project
   stands on today.
3. **Deletion and single target** (Phase 2), including loss of historical-run
   readers.
4. **Dynamic branch:** its adoption lane is already stopped (simplification
   record, Task 4, typed W3 retained). Remaining question: keep porting main
   into it as research, or tag it and stop. Recommended: tag and stop.
5. **Phase 5 consumer:** which pipeline.
6. **Is evolution the main claim?** If yes, reorder as stated above.
7. **Budgets** for Phase 4, Phase 5 step 3 and Phase 6b, each asked when its
   phase starts.

## Process rules

- One plan per phase, each with one exit test.
- No ordered approval tokens, hash packets or review receipts in design docs;
  a feature gets full review ceremony only after a consumer has used it.
- A phase closes on its exit test or its stop rule, never on a disposition
  list.
- The `AGENTS.md` experiment rules apply unchanged to Phases 4–6: no Fable
  model in any experiment call, models at or below Sonnet/Terra, no quality
  comparison without a qualified task family and a checked measure, "better"
  means Pareto dominance over quality and model-aware cost.

## Routing and records

This roadmap has no manifest, selector or workflow that drains it; selection
is manual. On selection: update the index "Select implementation work" row,
add the Phase 0 plan, and record decisions 1–7 here with dates.
