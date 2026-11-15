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
| Any semantic source edit refuses resume (`resume_program_changed`) | Phase 3; 3b done: the refusal prints a plan, and `resume --accept-changes=plan-<token>` continues under the edit; a run that uses a run reference cannot be resumed after a package change (parked) |
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
  [plan](2026-11-12-roadmap-phase-3b-edited-program-resume-plan.md), and is
  implemented (T1 to T8, 2026-11-13), exit cases (b) and (c) included:
  `resume` under an edit prints a read-only plan with a token, and
  `resume --accept-changes=plan-<token>` continues the same run under the
  edit, so the plan the author saw is the plan that is applied. The lane then
  stopped (decision 13). Not done: the H-G3 measurement. Parked: what the
  program and run-reference `config` digests cover, and the message-text match
  in `effect_inputs._is_destination_overlap`.

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
     launch is called only by its tests (closed 2026-11-14 by the backlog's
     TA2, `9bb55dda`: both are refused before a new launch);
   - a `defworkflow` with a workflow-reference parameter fails with
     `compiler_defect`, although the specification's own example has that
     shape;
   - choosing a procedure reference with `if` fails with `compiler_defect`
     where a refusal is intended (closed 2026-11-13 by the callables change:
     `proc_ref_literal_required`);
   - inside a macro template: `list/map`, a call to a `let-proc` local, and a
     nested loop used as an operand each fail or crash;
   - a free name in a macro template binds to the caller's local, so hygiene
     is weaker than the retired macro contract claimed;
   - `(and (= a.variant V) …)` is refused by module compilation while the
     expression typechecker grants the proof;
   - a loop's `continue` value holding an effectful `if` inside an operand
     fails with `compiler_defect` (closed 2026-11-14 by the effects change: refused `effect_not_permitted`);
   - the guard that forbids a confined run-reference site in a map body does
     not see one reached through a procedure-reference parameter or a
     `let-proc` local, in serial and parallel maps (a hole in a safety guard:
     first in line for a fix);
   - a parallel map written directly in a `loop/recur` body fails with
     `compiler_defect` (through a procedure call it works) (closed 2026-11-13
     by the map-bodies change);
   - a `let-proc` local whose body is a loop crashes with an internal error
     (closed 2026-11-13 by the backlog's TD5, `c0f397ab`);
   - dead code: the prompt snapshot and attempt-identity builders and the
     fragment-identity projection have no caller in the package.
   - added 2026-11-13 (second batch): an empty `(list)` in a `match` arm,
     and a `list/map` with a `match` body used directly as an `if` condition
     inside a loop body, each fail with `compiler_defect` (closed 2026-11-14 by
     staged-authoring Task 0b; the first was a list in the `match` subject, not
     the arm); a nested loop used directly as an
     operand fails with an internal `KeyError`, with or without a macro; an
     `Int` literal beyond 64 bits fails with `compiler_defect`; the `and`/`or`
     item above has its cause (the proof facts are lost when the condition is
     hoisted into a binding, so the refinement in the typechecker and the
     tests that assert it cannot be reached from a compile); a template-bound
     name in the first position of a list is never renamed by macro expansion
     (not closed: the loop-binder change withdrew its fix; see the sixth
     batch).
   - added 2026-11-13 (third batch): an inner binding that is not a procedure
     reference does not hide an outer procedure reference of the same name
     (`(let* ((g (proc-ref p))) (let* ((g 5)) (g 1)))` compiles and calls
     `p`); the fix refuses source that compiles today, so it was assigned to
     the one-target cut's release, beside refusing a `let-proc` local named
     like a function or a form (not made at the cut; see the end of this
     list); a `defproc` parameter of procedure-reference type forwarded
     through `let*` fails with `name_unknown`; reading a variant field on a
     `match` subject instead of the arm's binder passes the typechecker and
     fails with `compiler_defect` (confirmed by a second agent; the
     variant-field fix branch does not change it; closed 2026-11-14 by the
     backlog's TD2, `1b910fc8`).
   - added 2026-11-13 (fourth batch, each confirmed by an independent probe
     on `main`): a prompt declared with a missing `input_file` does not fail,
     and the provider runs with no authored prompt (closed 2026-11-13,
     `f004a59c`: a missing, unreadable or directory prompt file fails before
     launch with `input_file_read_failed` or `asset_file_read_failed`); `defpath` silently
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
     was assigned to the one-target cut's release (not made at the cut; see
     the end of this list); a `let-proc` local that forwards a captured
     outer procedure reference fails with `compiler_defect` (closed
     2026-11-14 by the backlog's TD6, `5d3dacb6`).
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
   - added 2026-11-13 (seventh batch, from the third review of the map-body
     change): effect summaries are unsound for imported workflows. The effect
     fixpoint keeps an imported workflow's summary for its first round only,
     and a missing summary is read as "no effects", so any check that asks a
     summary whether a call reaches an effect can be answered wrongly (found
     through the run-reference rule for map bodies, which no longer relies on
     summaries; other effect checks on `main` may be affected and have not
     been audited: second in line after the missing prompt file). Also: a
     one-call map body that is a `let-proc` capture, and a map inside a
     `continue` argument of a specialized procedure, each fail with
     `compiler_defect`; a variant-only field read fails with `compiler_defect`
     when the tested name is rebound in one operand while a sibling operand
     tests it (needs four lines in the renaming pass).
   - added 2026-11-13 (eighth batch, from the conditionals documentation and
     its review; each confirmed by probe): a discriminant proof reaches a
     parallel `list/map-effect` body and a pure `list/map` body but not a
     serial `list/map-effect` body (the same read is refused there); inside a
     generic procedure a discriminant test on a value of a type parameter is
     refused with a misleading code (`variant_tag_union_mismatch`), although
     `match` works; `cond`, `if` and `match` can be bound as names; the
     `and`/`or` proof item above has its cause confirmed a second time (the
     facts are lost when the condition is hoisted into a generated binding).
   - added 2026-11-13 (ninth batch, from the reviews of the fixture
     migration, the missing-prompt-file fix and the effects change; each
     reproduced by the reviewer on `main`): `path/join-under` looks up its
     path type in the caller's scope, so a procedure called from a module that
     does not import that type is refused `path_join_under_type_invalid` (a
     module-qualified type name works); a prompt `input_file` given as an
     absolute path, with `..`, or as a symlink that leaves the workspace is
     read and the provider launches, while `asset_file` refuses all three;
     `(continue (if c (if c E 0) 0))` and a procedure call holding a
     conditional effect used as a `match` subject each fail with
     `compiler_defect` (closed 2026-11-14 by the backlog's TD1, `1b910fc8`:
     the first is refused `effect_not_permitted`, the second builds); two
     refusal messages mislead (a parallel map in an
     `if` condition; `bind-proc` with an effect).
   - added 2026-11-13 (tenth batch): `done` as a `let*` binding value inside
     a loop fails with a `TypeError` in the elaborator (found by the
     prototype of the mutant generator on three seed programs: by the scope
     cut's own rule a defect a mutant hits returns to the fix list; closed
     2026-11-14, `1b910fc8`: refused `loop_recur_contract_invalid`); after
     `invalidate`, the refusal of `resume` suggests a bare
     `--accept-changes`, which is itself refused `resume_preflight_failed`
     (found by the re-review of the missing-prompt-file fix; not re-run on
     `main` by the coordinator).
   - added 2026-11-13 (eleventh batch; the most serious item on this list,
     the seed-dependent part closed 2026-11-14, `ecd57051`; a sibling stays open, see the end of this item): the compiler
     chooses a call's target from a set whose order depends on Python's hash
     seed and, through a path inside a hash, on the source directory. The
     same source can build on one run and end in `compiler_defect` on the
     next, and some builds silently call the wrong procedure and compute a
     wrong value, with a different program digest. Two triggers: a macro
     expanded more than once in one owner into calls with different targets
     (every target; for example a template with a `let-proc` local used twice
     gives 707 or 505 where 705 is meant), and, at targets 2.39 and 2.40, a
     procedure specialized more than once in one call chain (a bound, nested
     procedure reference). Found by the test-source migration and by a
     review, traced by a debugger to a site-keyed map in the elaborator
     ([report in the fix's plan row](2026-11-13-compiler-and-runtime-defect-backlog-plan.md)).
     It was fixed before the one-target cut. A program whose build
     depended on the seed gets one digest after the fix; programs with no
     such collision keep theirs (shown over every tracked `.orc` file and
     test fixture: no digest moved). Sibling, deterministic and on every
     target: a macro template whose `bind-proc` binds a computed value or a
     workflow reference gave every expansion the first expansion's value,
     because a bound value was identified by its source position. Fixed for
     a value made of stable kinds (literals, operators other than `and`,
     `or` and `not`, workflow references, enum members, records, variants,
     lists): its identity is the position plus that content. Still open: a
     bound value of another kind (`if`, `let*`, `match`, a loop, `and`, `or`,
     `not`, a call) or one that reads a local, and two equal bound workflow
     references written at two sites (known rows `B7-macro-*`, `B7-free-*`,
     `B7-same-written` and `B7-same-ref` of the defect record).
   - added 2026-11-14 (twelfth batch, from staged-authoring Task 0b; rows of
     the defect record): in a procedure without effects, a `bind-proc` over one
     of its parameters passed to a `ProcRef` parameter is refused by name
     (`proc_ref_binding_parameter_unsupported`, row E8, the plan's D5): the
     procedure is expanded where it is called and its parameters renamed, and
     its specializations were made from the definition's names, so the fix is
     in the bound-reference path beside rows `E23-*`, not local; a `let-proc`
     written in a serial `list/map-effect` body is `proc_ref_unknown` (row
     E7-local); a `match` arm whose value is its own binder, used as a value of
     the union, fails the closed check with `compiler_defect` (row
     match-arm-binder); from its review: a `let-proc` local that captures a
     name bound to a generic call is refused `procedure_call_unknown` naming
     the generated procedure (row let-proc-generic-capture); one that captures
     the result of a procedure with an effect and calls one ends in
     `compiler_defect` (row let-proc-effect-capture); a `match` subject that is
     an `if` on a variant test reading the tested variant's field ends in
     `compiler_defect` (row D20-subject-tag); from its re-review: in a subject
     that lowers typed, an `if` on an `and` or `or` with a `let-proc` branch
     ends in `compiler_defect` (row D20-let-proc-branch).
   The [defect backlog plan](2026-11-13-compiler-and-runtime-defect-backlog-plan.md)
   (accepted 2026-11-13 after an independent review and one revision) orders
   this list by harm. By the owner's direction of 2026-11-13 it is cut to
   eight tasks (48 hours, about 85 with reviews): what can
   spend provider money or commit a wrong output, and the crashes a short
   staged seed or its mutants would plausibly hit. The rest stay listed and
   pinned as known, and return only when the mutant generator or a real
   workflow hits one. The defect record
   (`tests/test_workflow_lisp_defect_backlog.py`) is the authority for each
   row: an item above with no "closed" mark may have been fixed since.
   The nine
   [changes assigned to the cut's release](2026-11-12-lane-d-stage-4-one-target-plan.md#changes-assigned-to-the-cuts-release-on-2026-11-13-not-yet-sized)
   were not taken at the cut, by the coordinator's
   [ruling of 2026-11-15](2026-11-12-lane-d-stage-4-one-target-plan.md#ledger) in that
   plan's ledger: the cut moved no program at 2.40 by design, so the frozen
   seeds and the seed-set programs keep their digests until the paid runs are
   done, and the changes' rows stay known rows of the defect record. Each is
   decided after the first experiment has a result, as a separate change with
   its own identity ruling (a new target or a declared break, versioning
   rules 2 and 3).
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
     already one-token edits today, as string literals at each role's call
     sites (not as inputs: a resumed run with changed inputs reuses nothing,
     [mutant generator plan](2026-11-13-phase-6-mutant-generator-plan.md#the-first-space-is-programs-not-bindings)), so
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
     coherence changes of stage 5. The timeout operand, the list operators
     and the typed list literal landed before the long-horizon seed was
     frozen (2026-11-14); the prompt and role tasks did not, and the first
     search space does not need them.

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

Added 2026-11-13 by owner decisions 14 and 16; decision 18 fixes its
credential. Its
[plan](2026-11-13-long-horizon-task-family-and-seed-plan.md) owns the effort
ladder's task list, limits, thresholds and readout; this section owns the
staging.

- **Aim:** a task family of long tasks on which a direct `claude-haiku-5-5`
  session succeeds 10 to 30 percent of the time (software, machine learning,
  scientific programming and reasoning), and one compact `.orc` seed that
  stages such a task with feedback at several timescales, as the starting
  point of the Phase 6 search.
- **Tasks:** individual tasks taken from public benchmarks. First candidate
  set: 16 named Terminal-Bench 4 tasks (single image, no GPU), with
  Terminal-Bench-Science as a second source and single MLE-bench
  competitions as a third (decision 17; steps 10 to 12). Scoring is each task's own
  verifier, so the family is oracle-scored: its qualification is the oracle
  check (the reference solution passes, an untouched environment fails), not
  a judge.
- **Seed:** `experiments/long_horizon_seed/milestones.orc` (49 lines of at most 120 columns):
  set up the project (directories, `AGENTS.md`, a document catalogue, an
  append-only log, topic notes), write spec targets, then rounds of plan,
  build each milestone (work, check, review), check and acceptance. Three
  neighbours are kept as comparison points (`staged`, one flat loop;
  `designed`, `staged` with a reviewed design before the plan; `roles`, the
  seed with Agent Sessions).
- **Search dimensions:** in the
  [seed-set plan](2026-11-11-seed-set-calibration-plan.md), "Search dimensions
  around one seed". First space: one model (Haiku), effort per role. Prompt
  wording, the setup step's included, is a later dimension.

| Step | What | Gate | State (2026-11-15) |
| --- | --- | --- | --- |
| 1 | Survey of public benchmarks; choose the candidate tasks | None (no spend) | Done; findings to be carried into the plan |
| 2 | Build, run and grade the tasks on this machine without Docker (rootless Podman, the published harness unchanged); the oracle check | None (no spend) | First pass done on the pinned images (2026-11-14): 15 of the 16 pass both halves; `vba-userform-port` passes only in a labelled variant with a recorded verifier image. All 32 pinned images are measured and the 16 agent images pass the withholding check. The second pass (five and five in a quiet window under the final policy, the only qualifying pass) was started on 2026-11-15 and has no result row yet ([report](../reports/2026-11-13-long-horizon-benchmark-survey-and-feasibility.md)) |
| 3 | Seed design, with scripted runs and kill-and-resume | None (no spend) | Done; the four seeds are on `main` with their stand-in driver and tests |
| 4 | The [plan](2026-11-13-long-horizon-task-family-and-seed-plan.md) with its ledger: task list, network policy, what is withheld from the agent, metering, stop rules, readout | Independent review | Accepted 2026-11-13 after review and two revisions; the third revision (decision 18: a subscription token, usage limits, a live probe and a measured pilot; the Task 2 probes) was accepted the same day. Of its about 133 hours of work, about 95 are on `main`; left: the second oracle pass, the live probe, the freeze, the smoke and pilot, the run and the readout. The attempts' 35 to 45 quiet machine hours are spread over as many weekly allowance windows as the pilot implies, and the owner gives a meter reading before each |
| 5 | Guarded launcher: only the approved model and efforts, a reservation before every attempt, the dollar ceiling, reference solutions and verifier tests never in the agent's container | Independent review; a zero-spend rehearsal with stand-ins | Done, on `main` (2026-11-15, `ad016fc1`), with the frozen configuration, the passthrough and the readout: two independent reviews, a re-review with a scoped check, and two zero-spend container rehearsals with the real CLI. The live probe of the subscription route is not approved: it waits for two owner confirmations ([open owner decisions](#open-owner-decisions)) |
| 6 | Effort ladder: direct Haiku at effort low, medium and high, five attempts per task, at most 240 attempts, ceiling USD 200 | Steps 2, 4 and 5; approved (decision 16) | Not started. Before it: the live probe, the second oracle pass, the freeze, the smoke and the pilot |
| 7 | Freeze the task set from the ladder: tasks in the band, and the answer on whether success falls as effort rises | Reported to the owner | After step 6 |
| 8 | Merge the seed to `main` and freeze it | Surface-coherence changes merged (the seed is written once, in the language as revised); the staged-authoring revisions are not required for the first search space | Done 2026-11-14 (`ef821464`): the four seeds are on `main`, frozen by `experiments/long_horizon_seed/seeds.json`. Open: whether `designed` (62 lines, over the 50-line figure) stays in the set (owner) |
| 9 | Seed against a direct session at matched priced-token cost on the frozen tasks | **A new owner approval** (not covered by decision 16) | Not requested |
| 10 | MLE-bench competitions as tasks of this harness ([feasibility report](../reports/2026-11-13-mle-bench-subset-feasibility.md)): each candidate wrapped so that the private answers and the credential stay outside the agent's container (the upstream harness puts its API key and the answers inside; under decision 18 the credential is the subscription token, held by the host-side passthrough), reusing the launcher, relay, allowlist, passthrough and allowance guard of step 5; the grader check (the answers file earns a gold medal, an untouched environment scores zero); a CPU-only competition first, then one on the GPU. The score is continuous, so every attempt also records the leaderboard percentile as a graded outcome | Step 5 done; its own plan and ledger, with the success definition (any medal, as proposed) and a total ceiling fixed before spend; independent review. Owner actions: a Kaggle API token and acceptance of each competition's rules; the NVIDIA Container Toolkit for rootless Podman | Staged 2026-11-13 (decision 17); not started. About 16 hours for the first CPU-only competition, 6 to 10 more for the first on the GPU, 1 to 2 for each further one |
| 11 | Screen the 13 ranked candidates: a direct Haiku session, 3 attempts each at one effort (39 attempts), the benchmark's 24-hour limit, about four attempts at once and one of them on the GPU | Step 10; decision 17 (Haiku up to USD 200 a day, a priced-token figure under decision 18; the report estimates USD 40 to 310 in all and 3 to 4 days if sessions stop by themselves, before any wait at the subscription's usage limits). Its plan states how the screen pauses at a usage limit and how an attempt cut off by one is counted (`AGENTS.md`, "Credential"), as the ladder's plan does | Not started |
| 12 | Place the competitions: one enters the family only at 10 to 30 percent success. Three attempts only exclude the clear ceilings and floors, so a competition that survives the screen gets the ladder's attempts (step 6's size per task) before it is frozen with step 7's set | Reported to the owner; a top-up beyond the plan's ceiling is a new request | After step 11. The report expects 2 to 5 of the 13 to fall in the band |

- **Exit test:** a frozen task list with each task's measured direct success
  rate by effort; a seed on `main` that completes those tasks' stages under
  stand-ins and resumes after a kill; and either a measured Pareto comparison
  of the seed against a direct session or a recorded decision not to buy it.
- **Limits:** five attempts per cell resolve only large differences (a task
  at 20 percent shows 0 of 5 about a third of the time), so step 7 places
  tasks in bands and makes no fine ranking. No claim about any workflow comes
  from step 6.
- **Making fitness cheaper to measure (added 2026-11-13, owner direction).**
  A search over workflows is limited by fitness: one evaluation costs dollars
  and pass or fail at a 20 percent rate needs about 290 attempts per
  candidate to tell 20 from 30 percent. These five items raise the chance
  that a later search finds anything; each is attached to a step above and
  none adds spend unless marked.

| Lever | What is done | Where | Spend |
| --- | --- | --- | --- |
| Graded fitness | Record, for every attempt, the verifier's count of sub-tests passed and total, where the verifier exposes one; prefer tasks with many sub-tests when the set is frozen. Reported beside pass or fail; it places no task and changes no frozen rule of the ladder | Steps 6 and 7 | None |
| Deterministic stage signals | On the first paid seed runs, record at each stage boundary the visible check's pass fraction and the agents' typed verdicts, beside the final verifier result; report how well each predicts the end. Early stopping is designed only on a signal that does | Step 9 (its smoke first) | None beyond step 9 |
| Tasks chosen by how the direct session fails | Read the ladder's failed transcripts and label each failure as process (lost track, stopped early, did not verify, broke earlier work) or capability; the frozen set states the mix, and the staged comparison is read per label | Step 7 | None (the transcripts are paid for by step 6) |
| A cheaper task family for the inner loop | A second, shorter family with the same failure labels, at about a tenth of the cost per attempt, for selection; finalists are validated on the long tasks | A new step after 7 | **New calibration spend; needs an owner approval; not requested** |
| Exhaust the small space before searching | The first space (one model, an effort per role, three levels) has 27 points: it is evaluated as a grid, or a declared fraction of one, on the frozen tasks, not searched | Phase 6, first run | Part of the Phase 6 request |

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
- **Search readiness (added 2026-11-13, owner direction; no spend).** What
  this system could add to a search is not the rejection of invalid
  candidates (in October the typed admission rejected nothing). It is:
  evaluation that can be paused at a stage boundary and resumed, so weak
  candidates stop early and promising ones continue without paying twice;
  an identity that recognises the same program respelled; spend bounds the
  runtime enforces on a generated program; a uniform typed tree to mutate;
  and typed per-stage records for a proposer. Three pieces of work make
  those real before any paid search, each with its own plan when it starts:

| Readiness item | What is built or measured | Gate | Depends on |
| --- | --- | --- | --- |
| R1 Checkpoint controller and workspace snapshots ([design](../design/orc_search_checkpoint_controller.md), reviewed twice and accepted as a design on 2026-11-13; **not built**: Part 1, a `--stop-after` flag and a stop-and-copy procedure, about 27 hours, waits for two answers: where a staged seed's workspace lives when it drives a container task (Phase 5b step 9's design) and whether stage signals predict the final result (the first paid seed runs). Measured while designing: a fork saves a fixed number of calls, 42 percent of a two-milestone run and 17 percent of an eight-milestone one, and on the long-horizon tasks a host copy does not capture the agent's work, which lives in the task container) | A snapshot of the workspace after every committed step (a commit for a repository task, an image layer for a container task), recorded beside the memo; a controller that runs candidates to a named stage boundary, stops the weak ones and resumes the rest; a fork of a run at a step with its workspace. This is the design item H-E2 needs and nobody has assessed: design first | Stand-in runs: a stopped candidate resumes with no step dispatched twice; a fork at step k reproduces the parent's workspace at k byte for byte; cost of a child equals its changed suffix | Phase 3b (done); the stage-signal result of Phase 5b for where to stop |
| R2 Canonical digest, then a replay of October | Local and generated names leave the program digest, so two spellings of one program share it; then the digests of the October search's recorded candidates are recomputed and the share that collapse is reported | Zero spend. The replay decides whether de-duplication is worth wiring into admission | The one-target cut (a digest change moves identity); the cut is merged (2026-11-15) and did not include the digest change, which is now its own identity-moving change (versioning rule 3) |
| R3 Mutants never crash the compiler ([plan](2026-11-13-phase-6-mutant-generator-plan.md), accepted 2026-11-13, 22 hours) | A generator of mechanical mutants of the seeds over the declared dimensions (a few hundred); every mutant compiles or is refused with a code, none ends in `compiler_defect`, and the count of distinct digests is reported. The open defect list of Lane D stage 5 is the backlog it draws on, ordered by what the mutants actually hit | Zero spend; runs in the default suite at a small sample | Stage 5 merges; the mutation operators are the same ones a search uses |

  Order: R3 and the October replay first (days, no design); R1 after its
  design is reviewed. A zero-spend check of H-E2's reach belongs here too:
  apply each declared mutation to a stand-in run of the seed and read the
  plan `resume` prints, which gives the share of steps each dimension keeps.
- **Estimate these items answer (coordinator's judgment, 2026-11-13, not a
  measurement):** about a quarter to a third that a search on this system
  produces a workflow that beats its seed with these mechanisms material to
  it; the items here and the fitness items of Phase 5b are what could raise
  that. The cap is whether a staged structure pays for its extra calls on
  long tasks, which Phase 5b step 9 tests.

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

**Whole-roadmap weights (coordinator's estimate, 2026-11-13; the owner asked that progress
figures cover every part).** The table above covers Phases 0 to 4 and Lane D as first scoped.
Lane D has since gained stages 5 and 6, the documentation consolidation and a defect backlog, and
four parts had no weight. Midpoints in engineer-weeks, from each plan's hours where one exists and
from judgment where none does; a progress figure is done weeks over this total and says so.
The current figure is under [Progress by the weight table](#progress-by-the-weight-table).

| Part | Weeks | Basis |
| --- | --- | --- |
| Phase 0 | 0.75 | Table above |
| Phase 1 | 2.5 | Table above |
| Phase 2 | 4 | Table above |
| Phase 3 | 6 | Table above |
| Phase 4 | 4 | Table above |
| Lane D | 17 | 9 as first scoped; stage 5 about 3; stage 6 about 2 (79 hours); documentation consolidation about 3 (112 hours); defect backlog and the changes assigned to the cut about 2 (judgment, unsized) |
| Consumer thread | 3 | Judgment: one pipeline written, run to a used result, and its friction log |
| Phase 5, seed set | 4 | Judgment: tasks, programs and runner (built), calibration, seed evaluation |
| Phase 5b, long-horizon | 6 | 133 hours for the ladder and the freeze (93 before the plan's third revision: the subscription route, its probe and pilot, the allowance guard), plus the staged comparison (judgment); about 1 for the MLE-bench steps 10 to 12 (about 45 hours and the screen) |
| Phase 6, program evolution | 8 | Judgment: the three readiness items, a search harness and its runs; the least certain row |
| **Total** | **about 55** | |

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
| 17 | A second long-horizon family from MLE-bench | 2026-11-13: the owner asked "can we consider some mlebench tasks" and, told that the benchmark's standard limit is 24 hours per attempt, answered "parallel up to 24 hours ok , haiku spend up to $200 per day ok". The coordinator's reading: attempts on this family may run in parallel under the benchmark's 24-hour limit, and `claude-haiku-5-5` spend on this family may reach USD 200 per calendar day. Added the same day: "mlebench includsion depends on the included tasks fallin in the 10 to 30 percent range we specified", so a competition enters the family only when a calibration places `claude-haiku-5-5` at 10 to 30 percent success on it (the band of decision 14), under a success definition the plan fixes before spend. It is not yet a tranche. No call is made before the feasibility study is in, a plan with its ledger exists (attempt caps, a total ceiling, stop rules), an oracle-style check passes on this machine, the launcher is guarded and reviewed, and the calibration rules of [`AGENTS.md`](../../AGENTS.md) hold; the `AGENTS.md` rule for the line is written with that plan. The Kaggle account and the acceptance of each competition's rules are the owner's action. The [feasibility report](../reports/2026-11-13-mle-bench-subset-feasibility.md) (no spend) ranks 13 candidate competitions (13.4 GB) and expects 2 to 5 of them to fall in the band; it recommends a small screen after the Terminal-Bench launcher exists, each competition wrapped as a Harbor task because the upstream harness puts the answers and the API key inside the agent's container. Told that the coordinator recommends the screen after the Terminal-Bench launcher is built, the owner answered "ok. stage in the roadmap": staged as steps 10 to 12 of [Phase 5b](#phase-5b-long-horizon-task-family-and-staged-seed). Open: the owner gave a daily figure and no total, so the plan proposes a total; the daily figure is read as covering this family only, not the other Haiku experiment lines |
| 18 | Which credential experiments use | 2026-11-13: told that the coordinator recommended an API key in a capped workspace for the effort ladder and the MLE-bench screen, the owner answered "no. subscription only. No api key for this or anythning else". Every provider call authenticates through the owner's Claude subscription; no API key is created or used ([`AGENTS.md`](../../AGENTS.md), experiment rules). Consequences taken into the [long-horizon plan](2026-11-13-long-horizon-task-family-and-seed-plan.md): the host-side passthrough holds a subscription token, not a key; there is no vendor-side spend limit, so the approved dollar ceilings are priced-token caps that the passthrough and the launcher enforce; runs share the subscription's usage limits with the owner's own sessions and must pause at a limit. Not yet shown: that the vendor accepts a subscription token through the passthrough (one live probe, usage only) |

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
is manual. Phase plans are linked here as they start. The lines below state
`main` at `5f548f7f` (2026-11-15); after them come the
[parked work](#parked-work), the [open owner decisions](#open-owner-decisions)
and the [progress figure](#progress-by-the-weight-table).

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
  3a and 3b are feasible; 3a is implemented by its [plan](2026-11-11-roadmap-phase-3a-script-fix-retry-plan.md); 3b has its [design](../design/workflow_lisp_edit_and_continue.md) and its [plan](2026-11-12-roadmap-phase-3b-edited-program-resume-plan.md), accepted; tasks T1 to T8 are done (2026-11-13): `resume` under an edited program prints a read-only plan with a token, and `resume --accept-changes=plan-<token>` continues the run under the edit; the lane has stopped (decision 13), with the H-G3 measurement not done and two items parked.
- Phase 5, in preparation, nothing spent: [seed-set calibration plan](2026-11-11-seed-set-calibration-plan.md). The kit is on `main` (2026-11-15, `09068ec8`) after five review rounds: 118 task packages, the candidate programs, the usage-limit pause and cut rules, the priced ceiling, the guard process and the hidden-test bounds. Owed before the first paid call, in the ledger's order: four owner decisions ([open owner decisions](#open-owner-decisions)), the freeze on the merged commit, the 20-task rehearsal on the frozen code, the tranche's spend row, then the smoke. The freeze waits on the owner's credential-route decision. The seed evaluation is not authorized.
- Phase 5b, in preparation, nothing spent: staged in this roadmap ([Phase 5b](#phase-5b-long-horizon-task-family-and-staged-seed)); its [plan](2026-11-13-long-horizon-task-family-and-seed-plan.md) is in its third revision, accepted 2026-11-13 (`96adb33d`) for the subscription-only credential. On `main`: the recording kit and the recordings redone in the ladder's configuration; the measurement and withholding check of the pinned images; the first oracle pass (15 of 16 tasks pass both halves, `vba-userform-port` in a labelled variant); the frozen configuration as data (`ladder.json`) and the manifest; the passthrough, the token scanner and the live probe script; the readout; the launcher (`ad016fc1`, 2026-11-15) after two independent reviews, a re-review with a scoped check and two zero-spend container rehearsals with the real CLI; and the four seeds, frozen by `seeds.json` (step 8). The owner placed the subscription token on 2026-11-14 and replaced it the same day. The effort ladder is the only owner-approved spend (decision 16). The live probe of the subscription route (decision 18) is not approved: no `Live probe approved` row is written, and it waits for the owner's two confirmations ([open owner decisions](#open-owner-decisions)). In progress: the second oracle pass, started on 2026-11-15 (no ledger row yet; no result). Then, in the ledger's order: the dry run of the contamination terms, the freeze, the smoke and pilot, the ladder. Steps 10 to 12 (MLE-bench) are not started.
- Phase 6, search readiness, in progress: the [mutant generator](2026-11-13-phase-6-mutant-generator-plan.md)'s operators, compile check, reuse report and first readout over the real seeds are on `main` (Tasks T1 to T3 and T5); the one crash the readout found (a loop exit as a `let*` binding value) returned to the fix list and is fixed. Its Task T6 (the readout over the seeds as frozen on `main`) is [parked](#parked-work). The [checkpoint controller](../design/orc_search_checkpoint_controller.md) is designed and not built (see row R1). The canonical digest (R2) is not started: the stage 4 cut it waited for is merged and did not include it, and it is decided after the first experiment has a result ([ruling of 2026-11-15](2026-11-12-lane-d-stage-4-one-target-plan.md#ledger)). Measured so far, on stand-in runs of the long-horizon seeds: an edit to a role that runs first keeps none of a finished run under `resume`, an edit to the role that acts last keeps about half, a loop bound keeps all of it.
- Lane D, defects: [backlog plan](2026-11-13-compiler-and-runtime-defect-backlog-plan.md), cut by the owner to a short list. The seven tasks before the closeout are on `main`: the defect record (every known defect as a row of `tests/test_workflow_lisp_defect_backlog.py`), output slots checked before a launch, typecheck crashes reported as `compiler_defect`, a field read on a `match` subject, control forms as operands, a `let-proc` local with a loop, and a `let-proc` local that captures a reference or a role. Also on `main`, found on the way: the missing prompt file, the hash-seed dependence of a call's target, the identity of a value bound with `bind-proc` in two expansions of one macro (for values of stable kinds; the rows `B7-macro-*`, `B7-free-*`, `B7-same-written` and `B7-same-ref` stay open), a loop exit as a `let*` binding value or in another value position, and the defects the staged seeds met. Left: the closeout (Task TF), [parked](#parked-work). The nine changes assigned to the stage 4 cut's release were not taken there and are decided after the first experiment has a result ([ruling of 2026-11-15](2026-11-12-lane-d-stage-4-one-target-plan.md#ledger)).
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
- Lane D, one target, done: [stage 4 plan](2026-11-12-lane-d-stage-4-one-target-plan.md).
  Target 2.40 is the one admitted source target (package 0.3.0, cut merged 2026-11-15); a source at
  2.35-2.39 refuses with the migration message, and a run recorded at an older target is read-only
  (`report`, dashboard and monitor read it; it is finished with the local tag `v0.2.1`). The plan's
  Final Figures section holds the measured lines and tests: the stage removed about 21,300 lines net
  against an estimate of 16,500, and the cut itself about 4,600 against 2,800. The weight table is
  not changed for it.
- Lane D, surface coherence (stage 5): [design](../design/workflow_lisp_surface_coherence.md)
  accepted. The constructor-field defect is fixed and the callables change (C1) is merged
  (2026-11-13), as are the loop binder form with its migration tool (I2a) and map bodies
  (I1: any expression as a map body and a computed serial `:max`, in programs with no run
  reference; `624ff688`, full suite 15,349 passed, the six failures being the baseline four and
  two that passed alone); effects in fields (E1) merged on 2026-11-14 (`ecd57051`) after five
  reviews and a mechanical acceptance gate, narrower than first accepted: a direct effect beside
  simple parts (frontend specification §16.3; the design's §13 lists the departures). Stage 5 is
  complete except the Python emitter change (I2b); the `fn` loop form stayed at the stage 4 cut, and
  its removal is a separate change decided after the experiments.
- Lane D, authoring revisions for staged workflows (stage 6):
  [design](../design/workflow_lisp_staged_workflow_authoring.md) and
  [plan](2026-11-13-staged-workflow-authoring-revisions-plan.md), reviewed and accepted
  2026-11-13. On `main` (2026-11-14): the baselines and the kit, the timeout operand, the three list operators, the typed list literal and the defects the seeds meet (Tasks 0, T, O, L and 0b; 31 of the plan's 79 hours). Not started: the prompt and role tasks (P1 to P6) and the closeout, [parked](#parked-work). Direction fixed by owner decision 15: roles by partial application over
  first-class prompts.
- Lane D, design corpus consolidation (the documentation half of stage 5):
  [plan](2026-11-13-workflow-lisp-design-corpus-consolidation-plan.md). On `main`: wave 1 (2026-11-13),
  the list rules (T8) and the callable rules (T9) (2026-11-14); about 75 of the plan's 112.5 hours.
  T6 and T7 (the index pass and the guide's first pass, 11.5 hours) have no ledger row: not
  confirmed as started. T10 to T15 (26 hours) are [parked](#parked-work).
- Side work, done: run and resume cost. A run re-read the whole memo and replayed the whole program
  after every record; memo reduction now continues from the last fold, a start the evaluator has
  just reached is published without a replay, and two compile passes skip work that cannot matter.
  A loop of 300 commands went from 45.0 s to 9.9 s of CPU (47.2 s to 12.0 s wall), with program
  digests, memo rows and published views byte-identical. Not done, because each changes a contract:
  dropping the replay after a commit (the remaining quadratic cost) and a build cache that lets
  resume skip compiling.
- Thread M, reduced: [zero-spend measurement plan](2026-11-11-roadmap-thread-m-zero-spend-measurement-plan.md).

### Parked work

On 2026-11-14 the coordinator parked the language-lane work that the first two
experiments (the seed-set calibration and the long-horizon effort ladder) do
not need, until the first experiment has a result. No plan ledger carries the
ruling yet; this section records it.

| Parked | Plan | Left |
| --- | --- | --- |
| Design corpus consolidation, T10 to T15 | [corpus plan](2026-11-13-workflow-lisp-design-corpus-consolidation-plan.md) | 26 hours: procedures and effects, loop values, executor retirement, the reference's final shape, the guide's second pass, the close |
| Staged-workflow authoring, P1 to P6, and the closeout after them | [authoring plan](2026-11-13-staged-workflow-authoring-revisions-plan.md) | 48 hours: a prompt as an argument, `Prompt[T]` and `Provider` as compile-time parameters, a reference over a generic procedure, `std/ask` and the role idiom, the documents |
| Mutant generator, T6 | [mutant generator plan](2026-11-13-phase-6-mutant-generator-plan.md) | 2 hours: the readout over the seeds as frozen on `main` |
| Defect backlog, closeout (TF) | [backlog plan](2026-11-13-compiler-and-runtime-defect-backlog-plan.md) | 2 hours: for each row, fixed, refused, dropped or the cut's |

Held by a ruling of its own: the nine changes that were assigned to the
stage 4 cut's release, the canonical digest (R2) among them, each decided
after the first experiment has a result
([ruling of 2026-11-15](2026-11-12-lane-d-stage-4-one-target-plan.md#ledger)).

Not started and not named by either ruling (whether parked is not confirmed):
the corpus plan's T6 and T7, the checkpoint
controller's build (R1, which waits for two answers its row names), and the
Python emitter change of stage 5 (I2b, decided after the experiments).

### Open owner decisions

Open on 2026-11-15. The first eight come from the two experiment plans; the
last is decision 3 of [Owner decisions](#owner-decisions).

| Decision | Recorded in | Blocks |
| --- | --- | --- |
| Confirm that paid extra usage is off for the account | [long-horizon plan](2026-11-13-long-horizon-task-family-and-seed-plan.md#owner-preconditions-and-questions), preconditions; [seed-set plan](2026-11-11-seed-set-calibration-plan.md#ledger), row of 2026-11-15 | The long-horizon live probe, pilot and freeze (confirmed again each time); the seed set's first paid call |
| Confirm that the subscription's terms allow unattended runs of this size | Long-horizon plan, preconditions | The long-horizon live probe, and again the freeze |
| The seed-set credential route: today each unit's private home gets a copy of the subscription login file (ruling R7); the coordinator recommends the long-horizon kit's host-side passthrough instead (the recommendation is not yet a ledger row) | Seed-set plan, rows R7 and 2026-11-15 | The seed-set freeze, and with it the rehearsal, the smoke and the calibration |
| Allowance: the hours in which attempts may start, the shares of the weekly and the five-hour allowance kept free, and a meter reading before each window | Long-horizon plan, question 2; seed-set plan, row of 2026-11-15 | The long-horizon smoke (hours and shares) and every window of attempts (a reading); the seed set's first paid call |
| Whether the token disclosed to the coordinating session on 2026-11-14 was revoked | Long-horizon plan, ledger rows of 2026-11-14 and 2026-11-15 | Nothing by itself: the replaced token is in place. The answer is recorded before the live probe; unrevoked, the disclosed token may stay valid until 2027-11-14 |
| Whether `designed` (62 lines, over the 50-line figure) stays in the long-horizon seed set | Long-horizon plan, ledger row of 2026-11-14 (third fix round of the seeds) | Nothing before step 9; it fixes which programs step 9's request names |
| Whether a slot cut by a usage limit may run again outside the caps | Seed-set plan, row of 2026-11-15 | The seed set's first paid call |
| Whether "experiment critical path first" becomes a standing rule | The coordinator's parking of 2026-11-14 ([parked work](#parked-work)); no ledger row | Nothing. Until it is answered the parking holds as one coordinator ruling, not as a rule |
| Name the consumer (decision 3) | [Owner decisions](#owner-decisions) | The consumer thread, and Phase 4, which enters only with the consumer's friction items |

The long-horizon plan's questions 3 to 6 (quiet machine time, two root
commands, tasks outside the 16, the disk) stay in that plan.

### Progress by the weight table

Done weeks over the [whole-roadmap weights](#effort), with `main` at
`5f548f7f` (2026-11-15). The weights are unchanged. A share is hours on
`main` over the plan's hours where a plan has hours, and the coordinator's
judgment where it has none (marked).

| Part | Weight | Share done | Weeks done | Basis |
| --- | ---: | ---: | ---: | --- |
| Phase 0 | 0.75 | 1.00 | 0.75 | Done |
| Phase 1 | 2.5 | 1.00 | 2.5 | Done |
| Phase 2 | 4 | 0.95 | 3.8 | Every task of its plan is merged and the headline exit test passes; the live smoke's frozen verdict is a fail on a criterion defect and the plan has no closing row, so "closed" is not confirmed (judgment) |
| Phase 3 | 6 | 0.90 | 5.4 | 3a and 3b are done and the lane stopped (decision 13); the H-G3 measurement is not done and was never sized (judgment) |
| Phase 4 | 4 | 0 | 0 | Not started; waits for the consumer |
| Lane D | 17 | 0.92 | 15.7 | As first scoped, 9 of 9 (stages 1 to 4, the dashboard, the test removal). Stage 5, 2.7 of 3 (all but I2b; judgment). Stage 6, 0.8 of 2 (31 of 79 hours). Documentation consolidation, 2.0 of 3 (75 of 112.5 hours). Defect backlog and the cut's changes, 1.2 of 2 (46 of the backlog's 48 hours; the nine cut changes not taken and unsized; judgment) |
| Consumer thread | 3 | 0 | 0 | Not started; decision 3 is open |
| Phase 5, seed set | 4 | 0.45 | 1.8 | The kit (tasks, programs, runner, guards) is built and reviewed; the freeze, the rehearsal, the calibration and the seed evaluation are not done (judgment) |
| Phase 5b, long-horizon | 6 | 0.50 | 3.0 | The ladder and the freeze, 2.5 of 3.5 (about 95 of 133 hours: Tasks 1 to 8 less the live probe and the second oracle pass). The staged comparison, 0.45 of 1.5 (the seeds are frozen; step 9 is not requested; judgment). MLE-bench steps 10 to 12, 0 of 1 |
| Phase 6, program evolution | 8 | 0.10 | 0.8 | The mutant generator's 18 of 23 hours and the checkpoint controller's accepted design; no digest work, no search harness, no run (judgment) |
| **Total** | **55.25** | **0.61** | **33.75** | **About 34 of about 55 engineer-weeks: about 61 percent** |

What the figure means: about three fifths of the estimated engineering
effort of the whole roadmap is on `main`.

What it does not mean:

- It is not a measure of results. Both experiments have spent nothing and
  have no result; no seed has been evaluated; the consumer pipeline, which
  the roadmap's goal names first, is not started.
- It is not time left. Most of what remains waits on owner decisions, on paid
  tranches that run over weekly allowance windows, or on work that is parked;
  about 7 of the remaining 21.5 weeks are Phase 6 and 7 more are Phase 4 and
  the consumer thread, none of which has started.
- It is no better than its weights: reviewer and coordinator estimates of low
  to medium confidence, with shares by judgment in six rows. One estimate is
  known to be off: stage 4 removed about 21,300 lines net against 16,500
  estimated. The weights are kept so that successive figures compare.
