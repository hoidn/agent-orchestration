# ORC Roadmap: Usable Pipelines First, Then Program Evolution

**Status: Selected 2026-11-11 by owner approval (revision 2).** This page is
the project's current roadmap. It owns order, gates and dispositions; accepted
designs and `specs/` own behavior. Selection authorizes no provider spend:
each experiment budget is requested when its phase starts. The
[evaluated-execution delivery plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md)
keeps its own remaining work as [Dispositions](#dispositions) states. This
page is not a source of copyable examples.

**Goal:** make typed, resumable agent pipelines usable for one real long
pipeline, and find a small number of simple workflows that work well on a
calibrated task set, as seeds for a search over workflow programs.

**Research scope (owner, 2026-11-11, after selection):** the research work is
scaled down to that second aim. Calibration of the task set and of the judge
comes first; every later research or practical use depends on it. The
sections below are written to this scope. The larger benchmark and
measurement designs that revision 2 carried are kept in the
[review record](../reports/2026-11-11-roadmap-review/experiment-design.md) and
the [Thread M plan](2026-11-11-roadmap-thread-m-zero-spend-measurement-plan.md)
as not selected.

**Basis:** the project audit of 2026-11-11 (code read and provider-free probes
at `bb63b03b`), the
[structural search closure](2026-10-18-orc-structural-search-roadmap.md#closure-2026-11-11),
and five independent reviews of revision 1 (see [Review record](#review-record)).
The [audit notes](../reports/2026-11-11-project-audit/README.md), the
[reviews](../reports/2026-11-11-roadmap-review/README.md) and
[what the experiments established](../reports/2026-11-11-what-the-experiments-established.md)
are recorded as dated reports.

## Where this tool is chosen

Pipelines of command-line coding agents from more than one vendor, lasting
hours to days, with typed validated handoffs, gates an agent cannot skip,
human decisions and a per-attempt audit trail, on one machine with no service.

Not chosen for: command-only data pipelines (Snakemake, DVC), API-level agent
graphs (LangGraph), fleet-scale durable execution (Temporal), or a task one
agent session finishes. Every work item below is tested against this
statement.

## Hypotheses

Each claim is stated so that it can fail.

| Id | Hypothesis | Refuted by | Built in | Measured in |
| --- | --- | --- | --- | --- |
| H-G1 crash behaviour | For every kill point and effect kind, a resumed run returns the same value, re-dispatches no committed effect and recovers a completed uncommitted agent turn without re-dispatch | Any duplicated committed effect or lost completed turn. It is parity, not an advantage, if LangGraph checkpoints pass the same matrix | done | Phase 2 kill tests; the LangGraph comparison is not selected |
| H-G2 errors before spend | The checker rejects, before the first provider call, defect classes that a typed Python equivalent reports only at run time | A typed Python control with a standard type checker catching the same set | done | Consumer friction log; the seeded-defect comparison is not selected |
| H-G3 iteration cost | After an edit, a run reuses a large share of committed provider cost soundly | Reuse that is small on real edit histories, or unsound | Phase 3 | Phase 3 |
| H-Q quality | On single-context coding tasks, a workflow beats a direct-call baseline given equal compute | Not tested at the selected size: Phase 5 selects seeds and reports which differences it cannot resolve | exists | not selected |
| H-E1 representation | At equal proposer budget, typed edits with compiler admission waste fewer evaluations than free-form Python edits | Rates within a predeclared tolerance | Phase 6 | Phase 6 |
| H-E2 cheap evaluation | A child program sharing a committed prefix with its parent is evaluated at a fraction of full cost and detects the same difference in fewer runs | Cost or variance no better than independent runs | Phase 6 | Phase 6 |

Priors the project already holds: the one direct comparison with LangGraph
(the untracked adversarial DAQ study) found parity on H-G1-like claims; in the
three-arm search readout the compiler rejected 0 of 18 proposals in every
interface, which counts against H-E1; the Phase 1 report itself says its flat
result is not evidence that the search space is flat.

**Mechanism hypothesis for H-Q:** structure helps only where it adds an
independent sample, a different model, or an executed signal that can fail.

## What is already known elsewhere

From the reviewers' memory of the literature; verify before citing.

- Durable execution is an established field (Temporal, Durable Functions,
  DBOS, Restate, LangGraph checkpointers). "Has resume and an audit trail" is
  a feature list those systems share.
- Reuse after pipeline edits is solved for hermetic tasks (Nextflow and
  Snakemake resume, Bazel, Nix). It is open for agent turns that edit a shared
  workspace. H-G3 is the question this project can add to.
- Test-based selection among samples helps (AlphaCode, CodeT); repair is close
  to resampling at equal budget (Olausson et al.); baselines must be
  cost-controlled (Kapoor et al.). A result on H-Q would be a replication; Phase 5
  does not attempt one.
- Search over agent workflows beats hand-written baselines when fitness is
  cheap (ADAS, AFlow, AlphaEvolve). This project cannot afford those regimes,
  so Phase 6 tests only what its representation and memo could add.

## Findings this roadmap answers

| Finding | Where |
| --- | --- |
| No page says what comes next; forward work is "pending, unselected" across four files | Phase 0 |
| The recorded full suite has 71 failing tests, some dependent on launch context | Phase 0 |
| Bare `(continue <effect>)` crashes the compiler; a loop without `:on-exhausted` compiles and fails at run time | Phase 1 |
| A run prints nothing while in flight or on success; a failure prints no run id; resume refusals name no recourse | Phase 1 |
| A command that failed because of a bug in its own script cannot be resumed once the script is fixed (`effect_input_diverged`; no override) | Phase 3; 3a done: plain `resume` retries after a clean failure, `resume --accept-changes` covers the rest |
| Any semantic source edit refuses resume (`resume_program_changed`) | Phase 3 |
| Inserting one effect renames every later generated binder on the Python surface, shifting effect identities | Phase 2 |
| Provider token usage is not recorded; every Phase 1 search row logged consumption as unavailable | Phase 2 |
| About 34k lines of retired architecture remain, dead as executors but imported as types by 28 production modules | Lane D |
| Six language targets; 388 of 686 `.orc` files sit on the oldest, under different procedure semantics from the newest | Lane D |
| Quality scores had σ ≈ 1 on an 8-point scale with two samples per arm; the rubric placed the merged fix at or below candidates | Phase 5 |

## Sequence

```
Phase 0 ─ Phase 1 ─┬─ Consumer thread (continuous, selects Phase 3 and 4 items)
                   ├─ Phase 2 ─ Phase 3 ─ Phase 4
                   └─ Lane D (background, time-boxed)
Phase 5 (seed set) and Phase 5b (long-horizon task family and staged seed)
run beside the phases; each of their paid tranches and Phase 6 open only by
owner budget decision.
```

Phase 3 and each Phase 4 item enter only with a named friction item from the
consumer or a measurement need. Each phase gets one plan under `docs/plans/`
when it starts.

### Phase 0: Records and baseline

- **Work:** commit the audit and the roadmap reviews as dated reports; record
  the adversarial DAQ study as a result (commit or archive, with its ledger);
  write one "what the experiments established" page; close superseded
  roadmaps with a dated note (see [Dispositions](#dispositions)); delete the
  420 leftover temp directories in the repo root (their creators were fixed in
  July); prune merged worktrees not in use by a live session; record the
  failing test ids from one fixed launch recipe (command, basetemp, session),
  each with a mechanism and an owner; run the doc-reading tests after the
  disposition edits.
- **Headline exit test:** one page states the next work, and a second run of
  the launch recipe reproduces the same failing ids.
- **Spend:** none. **Effort:** 0.5–1 week.

### Thread M: Zero-spend measurement (starts in Phase 0)

Reduced by the research scope above. Its
[plan](2026-11-11-roadmap-thread-m-zero-spend-measurement-plan.md) keeps the
full designs.

- **Done:** the input snapshot (pool records, readouts, ledgers and 135 run
  memos under `experiments/thread_m/inputs/`) and the stub `claude` and
  `codex` executables that refuse and log every call.
- **Optional background:** the descriptive reanalysis of the existing pools.
- **Not selected:** the resume retrospective, the crash matrix against a
  LangGraph checkpointer (H-G1) and the seeded-defect list against a typed
  Python control (H-G2). H-G1 and H-G2 therefore stay unmeasured against a
  comparator; the one existing comparison (the adversarial DAQ study) found
  parity.
- **Replaced:** the external task pool, by the task set of Phase 5.

### Phase 1: The first hour and the long run

- **Work:**
  - let-bind an effect given directly to `continue` (the `match` and
    `loop-state :like` cases already landed in `91e4a538`);
  - report a missing `:on-exhausted` at compile time, as a warning on admitted
    targets and an error on the target Lane D settles on;
  - print the run id first, one line per effect start, commit and failure,
    and the result on success;
  - make every resume refusal name what changed and the command that recovers;
  - pick up `commands.json`, `providers.json` and `prompts.json` beside the
    source when the flags are absent; hide maintainer subcommands;
  - make the `jsonschema` import chain lazy (measured: `--help` 1.8 s to
    0.3 s, `compile` 2.7 s to 1.1 s);
  - check whether prompts kept in files plus `invalidate` already give prompt
    edit-and-continue, and document it if so;
  - write a provider-free tutorial of about 150 lines that includes wrapping
    an existing script as a command, and run it as a smoke test in a fresh
    environment and an empty directory.
- **Alongside:** the Phase 3 feasibility spike (reading plus a prototype).
- **Headline exit test:** a failed run can be diagnosed and resumed using only
  what the terminal printed, in a fresh environment outside this checkout.
- **Authoring check (small spend, asked with the phase):** a fresh agent
  session at or below the model cap, given only the tutorial, writes a working
  provider-free workflow; run before and after the phase.
- **Not selected:** more than one diagnostic per compile (960 raise sites; a
  project of its own); the write-once lint.
- **Effort:** 2–3 weeks.

### Consumer thread (starts after Phase 1)

- **What:** one existing piece of the owner's work that would otherwise be run
  by hand or by agent subagents, named at selection (decision 3). Written as
  an ordinary workflow on today's system; progressive execution is used only
  if the consumer needs it.
- **Friction log:** every workaround, fallback to manual orchestration and
  restart from scratch, with the compute it discarded. The log selects the
  Phase 3 and Phase 4 work items and feeds H-G2.
- **Exit test:** the pipeline's output is used (a merged change, a figure, a
  paper section); the run had at least one unplanned failure recovered by
  resume and one mid-run edit; the owner records whether the next such task
  will use the tool and what they would have used instead.
- **Spend:** the consumer's own provider use, budgeted by the owner as
  ordinary work, not as an experiment.

### Phase 2: Qualification, metering and stable names

- **Work:**
  - finish the open parallel-map items of the
    [Phase 5 execution plan](2026-10-07-evaluated-execution-phase-5-plan.md)
    (item working directories, public kill and resume, the best-of-N consumer,
    closeout). These tests become the regression baseline for Phase 3;
  - record per-attempt provider token usage where the agent CLI reports it;
    `report` shows per-step and total tokens and priced cost; an optional
    per-run spend cap stops before the next provider call;
  - make generated binder names stable under insertion. Done for the Python
    surface only: the `.orc` site rule is unchanged, because prefix reuse
    (Phase 3) does not match effects by name;
  - run the Agent Sessions comparison (PQ-1c) as its plan defines it (done;
    [result](../../experiments/pq1c/README.md#result)): four
    cells, three outcomes, models inside the Sonnet/Terra cap unless the owner
    authorizes otherwise. One run per cell decides measure-free axes only.
- **Headline exit test:** a parallel best-of-N run survives a kill and
  resumes, and its report shows tokens per step and a total.
- **State:** in execution under its
  [plan](2026-11-11-roadmap-phase-2-qualification-metering-names-plan.md).
  Usage is recorded only for provider steps bound to the opt-in metered
  templates, since switching the built-in templates would change what the
  terminal shows. The Agent Sessions comparison is done: Retire by cost on
  measure-free figures; the owner keeps Agent Sessions for the workflow
  patterns it allows (decision 11).
- **Spend:** small, as gated tranches. **Effort:** 3–5 weeks.

### Phase 3: Edit and continue

- **This changes accepted contracts.** In
  [evaluated execution](../design/workflow_lisp_evaluated_execution.md): the
  program-equality refusal of §8.4, and the retry-baseline rule of §8.1 that
  refuses a changed script after a failed attempt "with no override". No code
  before an accepted design revision. The design must first recover why the
  retry-baseline rule exists.
- **Protected invariant:** replay equivalence. After an edit, the active memo
  is one an uninterrupted run of the edited program could have produced, with
  reused effects returning their recorded results.
- **3a, script fix:** a step whose latest attempt failed may be retried after
  its script is edited. The effect has no committed result to protect.
- **3b, prefix reuse:** an edited program resumes if replay reproduces a
  prefix of the active journal with equal identities and equal resolved-input
  digests. The first effect that is new, missing or diverged cancels the
  journal suffix from that point. The run records each program digest it ran
  under. The design covers interleaved parallel commits and keeps the
  coordinator refusals.
- **Deferred, 3c:** reuse scoped by recorded dependencies. The accepted design
  tried it and mixed old and new results, because effects couple through
  workspace files that leave no trace in values. It enters only when command
  boundaries declare what they read and write.
- **Headline exit test:** three cases pass and the kill-at-every-commit suite
  still passes: (a) fix the script of a failed third step, resume runs steps
  three and four only; (b) insert an effect before step two, resume re-runs
  two to four; (c) a file-dependence fixture never mixes old and new results.
- **Measurement (H-G3):** replay the recorded edit history of at least three
  real workflows, the consumer among them. Report per edit the share of
  committed provider cost reused, the cost re-spent, and every refusal;
  compare with whole-run restart.
- **Stop rule:** if 3b cannot be made sound, keep the refusal and ship 3a plus
  the recovery messages of Phase 1.
- **Makes harder:** a run can be the product of several programs, so reading
  its audit trail needs the program lineage.
- **Spend:** none. **Effort:** 5–7 weeks (spike 1, design 1–2, build 3–4).
- **State:** the [spike](../design/workflow_lisp_edit_and_continue_spike.md)
  found 3a and 3b feasible and recovered why the retry-baseline rule exists.
  3a keeps that protection: a failed attempt records whether it changed its
  own script; plain `resume` retries when it did not, and
  `resume --accept-changes` covers the other cases. 3a is implemented by its
  [plan](2026-11-11-roadmap-phase-3a-script-fix-retry-plan.md), exit case (a)
  included. 3b (resume under an edited program) has an accepted
  [design](../design/workflow_lisp_edit_and_continue.md) and
  [plan](2026-11-12-roadmap-phase-3b-edited-program-resume-plan.md); its first
  task proved the design's nine open claims by test before any feature code,
  and the build is in execution. Accepting an edit needs a plan token that
  the refusal prints, so the plan the author saw is the plan that is applied.

### Phase 4: Python additions pulled by the consumer

- **Work:** only what the friction log names, from: `parallel_map`; `Agent`
  (Agent Sessions is kept, decision 11; opened when the consumer asks for it); procedure references, which
  need a revision of the
  [Python frontend design](../design/python_workflow_frontend.md) that
  excludes them today; `invalidate` accepting a readable name.
- **Headline exit test:** the consumer runs from its Python source, including
  one `parallel_map`, and a kill-resumed best-of-N.
- **Makes harder:** `.orc` becomes the generated form; the remaining role of
  hand-written Lisp (the standard library and the language tests) is stated in
  the drafting guide.
- **Effort:** 3–5 weeks if all items are pulled.

### Lane D: Delete and unify (background, time-boxed)

Runs beside the phases and gates none of them. Each stage has its own exit
test; the gate throughout is "no test outside the Phase 0 list fails, and
every removed test is listed with the code it covered".

1. **Dead executors:** trial, adjudication, peer groups and supervision, with
   their CLI commands, specs and tests (about 20k lines), and the `trial`
   source form. Removing an accepted source form is a language change with
   spec edits. The two live-provider forms (`with-live-providers`,
   `with-live-provider-peers`) are **not** removed: the owner keeps live
   supervision and peers as a future direction (decision 9). Their old
   executor packages are still deleted, since a port to evaluated execution
   would not reuse them; the code stays under the local tag
   `archive/dead-executors-2026-11-11`, and the reusable design is recorded in
   a salvage page before the deletion merges.
2. **`StateManager` dead methods and CLI vestiges.**
3. **The old IR stack,** after moving the dozen live types to a small module
   and after the dashboard is migrated to evaluated runs (it reads only the
   old bundles today). `report` and the dashboard then drop their readers for
   runs of the retired runtime, with the tests held back for them.
4. **Targets, in three steps:** collapse the monotone capability gates into
   one table; migrate the catalog and the fixtures to the newest target with
   a behavior comparison; then, in one step, migrate the packaged library and
   remove the older procedure regime (the library cannot move first: an older
   module cannot import a newer one). The same plan
   deletes the source forms that are registered but refuse at build.
5. **Surface coherence** (added 2026-11-12 from an assessment of the language
   by its compiler and about 55 provider-free programs; the coordinator
   confirmed the counts and the guide drift, a design task reproduces the
   rest before deciding anything). The core holds together; the edges do not:
   - one rule for where an effect may appear (today it is allowed as a
     procedure argument, operand, `if` condition and `match` subject, and
     refused in a record field, a variant field and a list element);
   - the three iteration forms (`loop/recur`, `list/map`, `list/map-effect`)
     differ in binder shape, in what a body may contain and in whether `:max`
     takes a variable;
   - four kinds of callable with three calling conventions;
   - the authoring guide (3,438 lines) describes much that is unavailable,
     and the design record (81 documents, 52,000 lines) is too large to act
     as a design. Each language change in this stage shrinks the guide, and
     the stage ends with one current language reference and the superseded
     designs marked historical.
   Order: the design for the effect rule and the iteration and callable
   conventions first; code only after it is accepted.
   **Compiler and runtime defects found by probes on the way (open list,
   2026-11-13; each reproduced by the agent that found it, none scheduled
   unless marked).** They are separate from the design's changes and each
   needs its own small fix with tests:
   - two prompt outputs filled with the same path commit with nothing
     refusing the alias, and an output name equal to a result field is caught
     only after the provider has run; the check that would refuse both before
     launch is called only by its tests;
   - a `defworkflow` with a workflow-reference parameter fails with
     `compiler_defect`, although the specification's own example has that
     shape;
   - choosing a procedure reference with `if` fails with `compiler_defect`
     where a refusal is intended;
   - inside a macro template: `list/map`, a call to a `let-proc` local, and a
     nested loop used as an operand each fail or crash;
   - a free name in a macro template binds to the caller's local, so hygiene
     is weaker than the retired macro contract claimed;
   - `(and (= a.variant V) …)` is refused by module compilation while the
     expression typechecker grants the proof;
   - a loop's `continue` value holding an effectful `if` inside an operand
     fails with `compiler_defect` (being closed with the effects change);
   - the guard that forbids a confined run-reference site in a map body does
     not see one reached through a procedure-reference parameter or a
     `let-proc` local, in serial and parallel maps (a hole in a safety guard:
     first in line for a fix);
   - a parallel map written directly in a `loop/recur` body fails with
     `compiler_defect` (through a procedure call it works);
   - a `let-proc` local whose body is a loop crashes with an internal error;
   - dead code: the prompt snapshot and attempt-identity builders and the
     fragment-identity projection have no caller in the package.
   - added 2026-11-13 (second batch): an empty `(list)` in a `match` arm,
     and a `list/map` with a `match` body used directly as an `if` condition
     inside a loop body, each fail with `compiler_defect` (the staged-authoring
     plan fixes both as its first task); a nested loop used directly as an
     operand fails with an internal `KeyError`, with or without a macro; an
     `Int` literal beyond 64 bits fails with `compiler_defect`; the `and`/`or`
     item above has its cause (the proof facts are lost when the condition is
     hoisted into a binding, so the refinement in the typechecker and the
     tests that assert it cannot be reached from a compile); a template-bound
     name in the first position of a list is never renamed by macro expansion
     (being closed with the loop-binder change).
   - added 2026-11-13 (third batch): an inner binding that is not a procedure
     reference does not hide an outer procedure reference of the same name
     (`(let* ((g (proc-ref p))) (let* ((g 5)) (g 1)))` compiles and calls
     `p`); the fix refuses source that compiles today, so it goes with the
     one-target cut, beside refusing a `let-proc` local named like a function
     or a form; a `defproc` parameter of procedure-reference type forwarded
     through `let*` fails with `name_unknown`; reading a variant field on a
     `match` subject instead of the arm's binder passes the typechecker and
     fails with `compiler_defect` (confirmed by a second agent; the
     variant-field fix branch does not change it).
   - added 2026-11-13 (fourth batch, each confirmed by an independent probe
     on `main`): a prompt declared with a missing `input_file` does not fail,
     and the provider runs with no authored prompt (first in line with the
     guard hole above: a paid call with no instruction); `defpath` silently
     ignores unknown keywords; return guidance on a workflow, procedure or
     function is checked and then discarded (an accepted form with no
     effect); a `Bool` result accepts the strings "true" and "false";
     `TimestampNs` is documented as a type and does not exist; a prompt
     extern's path is checked only when the call runs, not at compile.
     Not a defect, a spec correction: result guidance on a provider or
     command effect is part of program identity (the specs said it was not).
   - added 2026-11-13 (fifth batch, from the second review of the callables
     change): macro hygiene never renames a template's `let-proc` binder, so
     caller code passed to the macro can call the template's local (with the
     alias form on `main` already; by name once the callables change merges);
     renaming it moves the digest of macro programs that compile today, so it
     goes with the one-target cut; a `let-proc` local that forwards a captured
     outer procedure reference fails with `compiler_defect`.
   - added 2026-11-13 (sixth batch, from the third review of the loop-binder
     change): macro hygiene in head position. A template-bound name at the
     head of a list is never renamed, so a caller's binding of the same name
     answers a call the template meant for its own local (a silent wrong
     value; reached through a direct procedure reference, an alias, or
     `bind-proc`). Two attempts to fix it inside the hygiene pass each let a
     new wrong case through, because what a head names is the resolver's
     knowledge; it needs one resolver-aware change, not a patch. Also: a
     workflow defined by a macro gets its parameters renamed, so it cannot be
     called or used as an entry through its public inputs.
6. **Authoring revisions for staged workflows** (added 2026-11-13 from writing
   a compact long-horizon seed under the 50-line limit; owner decisions 14 and
   15). Six things the language made awkward, each reproduced by probe before
   any design: a role (provider, model, effort, timeout) cannot be bound once
   for fresh calls; a timeout must be a literal; an empty list as loop state
   needs a type carrier; a document fill on a file that later steps edit
   blocks `resume`; a list longer than a map's cap fails the run after the
   work is done; a list cannot be reduced.
   - **The principled fix for roles (owner direction):** ordinary partial
     application with what the language already has. A typed prompt becomes a
     first-class value (`Prompt[T]`), so one generic procedure can wrap
     `provider-result`, and a role is that procedure with its provider, model,
     effort and timeout bound once by `bind-proc`. No new `role` form. Probes
     on 2026-11-13 showed that `bind-proc`, generic procedures and a provider
     call inside a procedure all work today, that a macro wrapping the call is
     refused on purpose (`macro_hidden_effect`), and that the one missing
     piece is that a prompt is not a value.
   - **Why it matters for the search:** changing one role's model or effort,
     or switching a role between a fresh call and a continued conversation,
     becomes a one-token edit in one place.
   - Design and plan drafted 2026-11-13 as proposed
     ([design](../design/workflow_lisp_staged_workflow_authoring.md),
     [plan](2026-11-13-staged-workflow-authoring-revisions-plan.md); about 118
     hours in 15 tasks). The probes corrected the findings: a prompt as a
     value is not the only missing piece (a provider cannot be an argument, a
     reference to a generic procedure does not instantiate, and an agent
     cannot be a `bind-proc` argument), and model and effort per role are
     already one-token edits today through inputs with literal defaults, so
     the first search space needs none of this; what prompt values buy is
     structural edits in one place (conversation scope, adding or splitting a
     role).
   - Reviewed and accepted 2026-11-13 (0 blockers, 8 majors, all applied). A
     compiler prototype on the spike branch proved the role idiom: the three
     seeds compile as written and no existing program's identity moves. Scope
     after the review: about 79 hours in 11 tasks. Deferred, with the designed
     rule kept: the snapshot fill for living documents, and an agent as a
     bound argument (so fresh against continued stays an edit at each call
     site until the conversation dimension is searched).
   - Order: code starts after the stage 5 branches E1, I1 and C1 are merged. First-class prompts come first, since the timeout and
     document-fill questions meet them (when a fill is read: at the creation
     of the prompt value or at the call). The changes follow the surface
     coherence changes of stage 5 and land before the long-horizon seed is
     frozen, so the seed is written once in the revised language.

- **Exit test:** the named packages are gone and nothing imports them; one
  admitted target for new source; any retained older target is listed with its
  reason and removal condition.
- **Versioning rule to write at step 4:** whether an identity-affecting change
  adds a target or breaks retained runs.
- **Effort:** 7–11 weeks. **Needs owner approval** (decision 4).

### Phase 5: Seed set (calibration, then seed selection)

Owned by the [seed-set calibration plan](2026-11-11-seed-set-calibration-plan.md);
this section only summarizes it.

- **Aim:** two to four simple workflows, each shown to run reliably and to do
  at least as well as one direct call at acceptable cost on a small calibrated
  task set. This is seed selection, not a test of H-Q: at this size only
  differences of about 20 points can be resolved.
- **Tasks:** about 20 small natural bug fixes from this repository, dated
  after the bound model's training cutoff, each with a visible failing check
  and a disjoint hidden test set.
- **Programs:** `direct`, `retry_until_check`, `implement_check_repair` and
  `implement_review_revise`, all on `claude-haiku-5-5`. Each seed program file
  has fewer than 50 lines of `.orc`; the shared result types in `common.orc`
  do not count and are frozen.
- **Measure:** a blind judge's functional 0–8 score is primary; hidden tests
  are secondary evidence and the check on the judge.
- **Calibration first:** direct Haiku and Sonnet runs on every task, then two
  judges on the same batches. Gates on task difficulty, on the stronger
  model's observed advantage, and on the judge (reference fix above the
  untouched base, a repeat judgment of identical code agreeing, agreement
  with the hidden tests). One redraw of tasks, then stop.
- **Spend:** the smoke and calibration tranches are authorized (the caps are
  in `AGENTS.md` "Experiment rules"). The seed evaluation needs a new owner
  approval after the calibration result is reported.
- **Output:** the seed programs, the frozen task list and per-run results, in
  a place a later search can load.

### Phase 5b: Long-horizon task family and staged seed

Added 2026-11-13 by owner decisions 14 and 16. Its plan is not written yet;
until it is, this section is the staging.

- **Aim:** a task family of long tasks on which a direct `claude-haiku-5-5`
  session succeeds 10 to 30 percent of the time (software, machine learning,
  scientific programming and reasoning), and one compact `.orc` seed that
  stages such a task with feedback at several timescales, as the starting
  point of the Phase 6 search.
- **Tasks:** individual tasks taken from public benchmarks. First candidate
  set: 16 named Terminal-Bench 4 tasks (single image, no GPU), with
  Terminal-Bench-Science as a second source. Scoring is each task's own
  verifier, so the family is oracle-scored: its qualification is the oracle
  check (the reference solution passes, an untouched environment fails), not
  a judge.
- **Seed:** `milestones.orc` (49 lines; branch `spike/long-horizon-seed`):
  set up the project (directories, `AGENTS.md`, a document catalogue, an
  append-only log, topic notes), write spec targets, then rounds of plan,
  build each milestone (work, check, review), check and acceptance. Two
  neighbours are kept as comparison points (`staged`, one flat loop; `roles`,
  the same with Agent Sessions).
- **Search dimensions:** in the
  [seed-set plan](2026-11-11-seed-set-calibration-plan.md), "Search dimensions
  around one seed". First space: one model (Haiku), effort per role. Prompt
  wording, the setup step's included, is a later dimension.

| Step | What | Gate | State (2026-11-13) |
| --- | --- | --- | --- |
| 1 | Survey of public benchmarks; choose the candidate tasks | None (no spend) | Done; findings to be carried into the plan |
| 2 | Build, run and grade the tasks on this machine without Docker (rootless Podman, the published harness unchanged); the oracle check | None (no spend) | Done for 13 tasks (11 of the 16, 2 science tasks): 12 pass both halves with task logic unchanged, one needs a wider user-id range or a one-line verifier change; one verifier is timing-sensitive under load. Five of the 16 are untried, and none has been run five times ([report](../reports/2026-11-13-long-horizon-benchmark-survey-and-feasibility.md)) |
| 3 | Seed design, with scripted runs and kill-and-resume | None (no spend) | Done on the spike branch; not on `main` |
| 4 | The [plan](2026-11-13-long-horizon-task-family-and-seed-plan.md) with its ledger: task list, network policy, what is withheld from the agent, metering, stop rules, readout | Independent review | Accepted 2026-11-13 after review and one revision; about 79 hours of work and a quiet machine for 35 to 45 hours |
| 5 | Guarded launcher: only the approved model and efforts, a reservation before every attempt, the dollar ceiling, reference solutions and verifier tests never in the agent's container | Independent review; a zero-spend rehearsal with stand-ins | Not started |
| 6 | Effort ladder: direct Haiku at effort low, medium and high, five attempts per task, at most 240 attempts, ceiling USD 200 | Steps 2, 4 and 5; approved (decision 16) | Not started |
| 7 | Freeze the task set from the ladder: tasks in the band, and the answer on whether success falls as effort rises | Reported to the owner | After step 6 |
| 8 | Merge the seed to `main` and freeze it | Surface-coherence changes merged (the seed is written once, in the language as revised); the staged-authoring revisions are not required for the first search space | Waits on Lane D stage 5 |
| 9 | Seed against a direct session at matched priced-token cost on the frozen tasks | **A new owner approval** (not covered by decision 16) | Not requested |

- **Exit test:** a frozen task list with each task's measured direct success
  rate by effort; a seed on `main` that completes those tasks' stages under
  stand-ins and resumes after a kill; and either a measured Pareto comparison
  of the seed against a direct session or a recorded decision not to buy it.
- **Limits:** five attempts per cell resolve only large differences (a task
  at 20 percent shows 0 of 5 about a third of the time), so step 7 places
  tasks in bands and makes no fine ranking. No claim about any workflow comes
  from step 6.

### Phase 6: Program evolution

The owner chose the form below on 2026-11-11 (decision 7). The alternative,
closing the question as answered in the literature for cheap-fitness regimes,
was not taken. No spend is authorized.

- **Test what this system could add:**
  - *H-E2 first.* It needs no generation spend, but it needs a run to be
    forked with its workspace, because a memo belongs to one run and one
    workspace. That is a new design item nobody has assessed. Comparisons are
    reported over several independent parent prefixes, since a parent chosen
    for a lucky prefix passes the luck to its children.
  - *H-E1* against a free-form Python arm and an equal-budget unguided arm.
  - The most interesting target is search over suffix variants of a long
    pipeline where intermediate signals exist, using the consumer.
- **Generic search ("a generated program beats the best hand-written one"):**
  not selected. It would need a task pool several times the seed set's, with
  search, validation and sealed task sets fixed at pool assembly, a frozen number of generations and
  proposer model, and the incumbent re-run beside the finalists. Price: about
  1,600 calls at 15-point resolution, about 2,100 at 9. Below that, "not
  tested".
- Whatever form is chosen, the search starts from the
  [seed set](2026-11-11-seed-set-calibration-plan.md) and admits a generated
  program only if it compiles and stays under the seed set's size limit
  (fewer than 50 lines of `.orc`; owner, 2026-11-11).
- The campaign code from the closed search roadmap is kept outside the default
  test suite (`ORCHESTRATE_CAMPAIGN_TESTS=1` runs its tests) until this
  phase decides what it reuses.

## Effort

Reviewer estimates inferred from code counts; low to medium confidence. Token
metering in Phase 2 was not sized by any reviewer.
Phase 3 is larger than the table says: the accepted plan for 3b alone estimates
27 to 45 working days before review rounds.

| Item | Engineer-weeks |
| --- | --- |
| Phase 0 | 0.5–1 |
| Phase 1 | 2–3 |
| Phase 2 | 3–5 |
| Phase 3 | 5–7 |
| Phase 4 | 3–5 |
| Lane D | 7–11 |
| Total | 21–32 |

## Dispositions

| Existing record | Proposed disposition |
| --- | --- |
| [Evaluated-execution delivery plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md) | Keep as owner of its remaining Phase 5 work, its consumer migration; PQ-1c ran under the Phase 2 plan (decision 11); correct its stale Phase 4 text |
| [Evolution follow-on roadmap](2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md) | Keep the axis lifecycle; close the workstream ledger. The agent-authoring baseline trial becomes the Phase 1 authoring check |
| [Checked evaluation of generated source](../design/workflow_lisp_checked_program_evaluation.md) | Park; reopen on a positive H-E result that needs generation inside a workflow |
| [Structural search roadmap](2026-10-18-orc-structural-search-roadmap.md) and cumulative campaign plan | Stay closed; code handled as Phase 6 states |
| [Token usage accounting backlog item](../backlog/active/2026-04-30-provider-step-token-usage-accounting.md) | Moved to Phase 2 |
| [Substrate maintenance track](2026-07-26-substrate-maintenance-track.md) | Close as superseded by evaluated execution |
| LSP [P-series](2026-07-30-lsp-frontend-prerequisites-p-series-roadmap.md) and [L6](2026-07-31-workflow-lisp-language-server-l6-utility-roadmap.md) | Close |
| [OMP roadmap](2026-08-14-omp-integration-design-and-roadmap.md) OMP-I2 | Drop |
| Confined provider children, provider-phase isolation, typed program gates C2, MLEvolve architecture, private-runtime C2–C6, write-once W4 | Drop or archive |
| Rest of the [backlog](../backlog/README.md) | Archive |
| Live cumulative campaigns; the natural-difficulty iteration loop | Stop |

## Owner decisions

The owner approved revision 2 as written on 2026-11-11. Items 2, 4, 5 and 7
are recorded on the reading that approval covers the stated recommendations;
the owner can amend any of them.

| # | Decision | State |
| --- | --- | --- |
| 1 | Select this roadmap | Selected 2026-11-11 |
| 2 | H-G1 to H-G3 are the claims the project stands on, each with its refutation condition | Confirmed 2026-11-11 |
| 3 | Name the consumer | Open; needed before the consumer thread starts |
| 4 | Lane D deletions | Approved 2026-11-11. Owner, same day: the dashboard and `report` stop reading runs from the retired runtime, and the dashboard is migrated to read evaluated runs. The migration precedes stage 3 |
| 5 | Dynamic branch: tag it and stop porting main into it; reopen if the authoring check shows typed authoring is the agents' bottleneck. Its adoption lane was already stopped (simplification record, Task 4) | Approved 2026-11-11 |
| 6 | Phase 5 size | Superseded by decision 8 |
| 7 | Phase 6 form | Option B approved 2026-11-11; no spend authorized; generic search not selected |
| 8 | Research scope | Scaled down by the owner 2026-11-11: find a few simple workflows that work well on a calibrated task set, as seeds for genetic search; calibration first. Supersedes decision 6. Same day: judge-primary scoring validated on two natural controls; smoke and calibration spend authorized; seed programs under 50 lines of `.orc`, `common.orc` not counted |
| 9 | Live supervision and peer groups | Kept as a future direction by the owner 2026-11-11: not scheduled, no phase owns it. Lane D keeps the two source forms and their frontend support, deletes the old executor packages, and records the reusable design first. A port needs its own design on evaluated execution; the [salvage record](../design/live_provider_supervision_and_peers_salvage.md) is its starting material and finds supervision the closer of the two |
| 10 | Budget for the Agent Sessions comparison (PQ-1c) | Approved 2026-11-12: the comparison only, at most 20 `claude-haiku-5-5` calls, ceiling USD 10, through the kit's launcher. The live best-of-N smoke is not approved |
| 11 | Agent Sessions after the comparison | Kept, 2026-11-12. The owner values sessions for versatility in workflow patterns, not efficiency. The comparison's cost finding (1.4 to 1.7 times the plain handoff on a four-turn pattern; a committed turn cannot be invalidated) is the known price, not a reason to retire |
| 12 | Who approves provider spend | Delegated to the coordinator, 2026-11-12, "within reason": planned-size tranches with a cap recorded in the plan ledger before the first call, Haiku by default and nothing above the Sonnet/Terra ceiling. The coordinator still asks for a tranche above about USD 100, cumulative spend above about USD 300, a new experiment line, or a top-up after a null result ([`AGENTS.md`](../../AGENTS.md), experiment rules) |
| 13 | How far to take edited-program resume (Phase 3b) | 2026-11-12: the owner asked why resume and effect tracking take so much effort, and chose to finish the two remaining tasks (accepting a plan; guides and closeout) and then stop. No scope is added to that lane after them: the open design question about resuming a run that uses a run reference after a package change stays parked, and capacity moves to the seed-set calibration and the language cleanup |
| 14 | A long-horizon seed and task family | 2026-11-13, owner direction, added to the seed work: tasks with a long horizon on which `claude-haiku-5-5` succeeds 10 to 30 percent of the time, in software, machine learning and scientific programming or reasoning, extracted individually from public benchmarks; and one compact `.orc` seed (few lines) that stages the work (a clean project repository with its documentation structure and agent guides, then spec-driven targets, then design and planning, then implementation) with feedback at several timescales and semantic levels. Nothing like it exists in the repository yet. Staged as [Phase 5b](#phase-5b-long-horizon-task-family-and-staged-seed). Added the same day: mutations of the seed vary model (Haiku or Sonnet) and effort level per agent role; the first space searched keeps one model (Haiku) and varies only effort per role, after an effort ladder confirms that success does not fall as effort rises |
| 15 | How a role is bound once | 2026-11-13: the owner asked for "a nice schemey partial application simple fix" and then for the design and roadmap staging of "the principled fix that this points to". Decided direction: a typed prompt is a first-class value and a role is a generic procedure wrapping `provider-result`, partially applied with `bind-proc`; no new `role` form. The design must still report any guarantee this would break (effect identity per call site, the provider declaration digest, metering, the closures boundary) before code is written |
| 16 | Budget for the long-horizon effort ladder | Approved 2026-11-13 ("ok" to the stated request): 16 named benchmark tasks, a direct `claude-haiku-5-5` session at effort low, medium and high, five attempts each; at most 240 attempts, ceiling USD 200 (requested as about USD 170 at reported prices). Conditions before the first attempt: the oracle check passes here, the network policy is fixed, a guarded launcher is reviewed, the plan and its ledger exist. It places tasks relative to the 10 to 30 percent band and tests whether success falls as effort rises; the workflow comparison is a separate request ([`AGENTS.md`](../../AGENTS.md), experiment rules) |

## Process rules

- One plan per phase, with one headline exit test that fails today and a
  checklist for the rest.
- A feature gets full review ceremony only after the consumer has used it.
- Experiment budget is requested once per phase as gated tranches
  (calibration, main, one reserved extension). Each tranche is a ledger row
  with its limit, released by its predeclared gate, with no top-up after a
  null.
- Every experiment keeps one frozen, hashed criterion and one ledger row.
  Nothing else is required for a pilot.
- The `AGENTS.md` experiment rules apply unchanged, including the owner's
  cost default of 2026-11-11: as many experiment calls as possible on Haiku.

## Review record

Revision 1 was reviewed on 2026-11-11 from five viewpoints (conceptual,
practical value, scientific value, experiment design, engineering
feasibility): 14 blocker, 34 major and 32 minor findings. Revision 2 changes:

- claims restated as hypotheses with refutation conditions, plus a "where
  chosen" statement and a prior-results section;
- the consumer and the zero-spend measurements moved to the front;
- Phase 3 retargeted from dependency-scoped reuse, which the accepted design
  rules out, to script-fix retry and prefix reuse, with stable names and
  parallel-map qualification as prerequisites;
- token metering scheduled; deletion re-sized and moved to a background lane
  in stages;
- the benchmark re-designed with replicates, a visible and hidden test split,
  compute-matched baselines, three decision regions and honest call counts;
- the free table-search step cut; program evolution offered as explicit
  options with prices.

Not yet verified: whether a task pool of the needed size exists; the
literature notes; the effort estimates. Revision 2 was approved without a
second review.

## Routing and records

This roadmap has no manifest, selector or workflow that drains it; selection
is manual. Phase plans are linked here as they start:

- Phase 0, done: [records and baseline plan](2026-11-11-roadmap-phase-0-records-and-baseline-plan.md)
  and [test baseline](../reports/2026-11-11-test-baseline.md).
- Phase 1, done: [first hour and long run plan](2026-11-11-roadmap-phase-1-first-hour-plan.md)
  and the [tutorial](../tutorial_first_pipeline.md); its ledger records the
  known gaps and the friction left for later.
- Phase 2, in execution: [qualification, metering and stable names plan](2026-11-11-roadmap-phase-2-qualification-metering-names-plan.md).
  The headline exit test passes on `main` and the parallel-map closeout is merged. The Agent
  Sessions comparison ran under the budget of decision 10 (16 calls, USD 0.33): outcome
  Retire, by cost (the session variant cost 1.74 and 1.38 times the plain baseline). The
  owner keeps Agent Sessions (decision 11): its value is the workflow patterns it allows, which
  the comparison did not measure. The live best-of-N smoke ran once on 2026-11-13 under the coordinator's
  delegated approval (5 `claude-haiku-5-5` calls, USD 0.022): the parallel map, the kill mid-map, the resume and
  the metering behaved as specified (nine of ten checks); the frozen verdict is fail on the isolation check,
  because the criterion's list of the CLI's built-in agents was incomplete (the plan's ledger has the detail).
- Phase 3, in execution: [edit and continue feasibility spike](../design/workflow_lisp_edit_and_continue_spike.md);
  3a and 3b are feasible; 3a is implemented by its [plan](2026-11-11-roadmap-phase-3a-script-fix-retry-plan.md); 3b has its [design](../design/workflow_lisp_edit_and_continue.md) and its [plan](2026-11-12-roadmap-phase-3b-edited-program-resume-plan.md), accepted; tasks T1 to T7 are merged (2026-11-13): `resume` under an edited program prints a read-only plan with a token, and `resume --accept-changes=plan-<token>` continues the run under the edit. T8 (guides and closeout) remains; after it the lane stops (decision 13).
- Phase 5, in preparation: [seed-set calibration plan](2026-11-11-seed-set-calibration-plan.md).
- Phase 5b, in preparation: staged in this roadmap ([Phase 5b](#phase-5b-long-horizon-task-family-and-staged-seed)); survey, machine feasibility and seed design are done on spike branches (`spike/long-horizon-tasks`, `spike/long-horizon-seed`); its plan is being written. The effort ladder is the only approved spend (decision 16).
- Lane D, tests, done: [low-value test removal plan](2026-11-11-low-value-test-removal-plan.md).
- Lane D, dashboard, done: [dashboard migration plan](2026-11-11-dashboard-evaluated-runs-migration-plan.md).
  `report` and the dashboard read evaluated runs only and refuse retired runs
  (old readers at the git tag `archive/retired-run-readers-2026-11-11`); this
  unblocks stage 3, the old IR stack.
- Lane D, dead executors, done: [dead executors and `StateManager` plan](2026-11-11-lane-d-dead-executors-and-state-manager-plan.md).
  Stages 1 and 2 are merged; the two live-provider source forms stay (decision 9).
- Lane D, old IR stack, done: [stage 3 plan](2026-11-12-lane-d-stage-3-old-ir-stack-plan.md).
  The old stack's modules are gone and nothing imports them (code kept at the local tag
  `archive/old-ir-stack-2026-11-12`); a small leftovers list remains in the plan's ledger.
- Lane D, one target, in execution: [stage 4 plan](2026-11-12-lane-d-stage-4-one-target-plan.md),
  accepted. Target 2.40 survives; after the cut a run recorded at an older target is read-only
  (`report`, dashboard and monitor read it; continuing it needs the tagged release).
- Lane D, surface coherence (stage 5): [design](../design/workflow_lisp_surface_coherence.md)
  accepted. A wrong-value defect the review found in constructor fields is fixed first; the
  changes that only admit refused source follow; the loop binder rewrite rides the stage 4
  sweep and the `fn` form goes at the stage 4 cut.
- Lane D, authoring revisions for staged workflows (stage 6): design and plan being drafted
  (`docs/design/workflow_lisp_staged_workflow_authoring.md`,
  `docs/plans/2026-11-13-staged-workflow-authoring-revisions-plan.md`; neither exists until the
  draft is committed). Direction fixed by owner decision 15: roles by partial application over
  first-class prompts.
- Side work, done: run and resume cost. A run re-read the whole memo and replayed the whole program
  after every record; memo reduction now continues from the last fold, a start the evaluator has
  just reached is published without a replay, and two compile passes skip work that cannot matter.
  A loop of 300 commands went from 45.0 s to 9.9 s of CPU (47.2 s to 12.0 s wall), with program
  digests, memo rows and published views byte-identical. Not done, because each changes a contract:
  dropping the replay after a commit (the remaining quadratic cost) and a build cache that lets
  resume skip compiling.
- Thread M, reduced: [zero-spend measurement plan](2026-11-11-roadmap-thread-m-zero-spend-measurement-plan.md).
