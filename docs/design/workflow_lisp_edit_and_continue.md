# Workflow Lisp Edit And Continue: Resume Under An Edited Program

**What this page is.** The design for part 3b of
[roadmap Phase 3](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-3-edit-and-continue):
a run continues under an edited workflow and keeps the committed results
whose identity and inputs the edit did not change.

**Status.** Proposed revision of [evaluated execution](workflow_lisp_evaluated_execution.md).
Not accepted and not implemented. It applies rulings 2 to 8 of the
[feasibility spike](workflow_lisp_edit_and_continue_spike.md#coordinator-rulings-2026-11-11).

**What owns the behavior today.** Evaluated execution (§7.3 C7, §8.1, §8.4,
§8.5) and the [CLI contract](../../specs/cli.md) ("Resume preflight
precedence", "Diagnostics"). Until an implementation plan lands this page, a
run resumes only under the program it started with, and
`resume --accept-changes` covers only an unfinished command attempt's changed
files. Follow those documents and the recovery lines the CLI prints.

**Copy safety.** Nothing here is a recipe: the record, file names and printed
lines are proposals. Probe scripts are in the session scratch directory
`/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/design-3b/`,
which is not durable; [Probes](#probes) lists what each showed.

**Terms.** *Journal:* the run's `memo.jsonl`. *Commit:* a `committed` record
that nothing later cancels. *Pending start:* a `started` record with no
`committed` or `failed` record. *Lineage:* the ordered programs a run has
executed under; the last is the *current program*. *Cut:* the journal offset
from which an accepted edit cancels. *Stand-in:* a local script that plays a
provider; no model is called.

## 1. Summary

Replay the edited program against the journal, keep the commits it
reproduces in journal order, and cancel everything from the first one it
does not (§3). One `rebased` record names the edited program and the cut
(§4). Plain `resume` refuses and prints the plan; `resume --accept-changes`
applies it; every refusal precedes any write (§5, §6). First, a provider's
`declaration` digest stops carrying source positions (§2).

## 2. The `declaration` prerequisite

**Defect.** `resolve_provider_input` (`evaluated/providers.py`) digests the
provider node after `strip_provenance`, which removes the position record `@`
from the effect node only. Operand nodes under `inputs` and `policy` keep
`@`: the source file's absolute path, line and column. A comment line above a
provider changes its digest under an edited program.

**New rule.** `declaration` is the digest of the checked effect node with
every `@` key removed, at any depth, and nothing else removed
(`_strip_provenance` in `workflow_lisp/closed/build.py` does it). Agent turns
and phased providers resolve through the same function and get the same rule.
No other class digests a node with positions: commands digest argv, contract,
closure and file evidence; host requests digest position-free contracts
(probe).

| Edit | Today | New rule |
| --- | --- | --- |
| Comment or blank lines; a step or pure binding inserted on an earlier line | changes | same |
| Keyword arguments reordered (`:effort` before `:model`) | changes | same; the program digest is also the same |
| A binder that `:inputs` reads is renamed, or replaced by a pure alias | changes | changes |
| A literal changes (`:model`); an operand changes shape (`s1` to `(+ s1 0)`) | changes | changes |
| The provider's own label changes, or it moves into a procedure | changes | changes; its identity changes too |

A renamed input binder must change the digest, because the name is prompt
text: each input row is rendered as `## Typed Prompt Input: <name>`. A
changed prompt file does not touch `declaration`; it changes the `source:`
and `prompt` parts (C6).

**Hygiene names: a limit, not fixed here.** When `:inputs` reads a binder that
shadows another in the same definition, the compiler names it by counter
(`%1`). An unrelated shadow added earlier shifts it to `%2`. The name is in
the node and in the prompt text, so the provider runs again: sound, since the
prompt did change, but reuse is lost. The fix is to label input rows by
authored name, which changes prompt bytes and needs a new target.

**Runs in flight (ruling 4): the old digest is accepted.** Whenever a recorded
`declaration` is compared (a commit on replay, a pending start on recovery),
the current value is computed by the rule the recorded value satisfies:

```text
current = new_rule(node)
if recorded == current: use current
elif recorded == old_rule(written_node) and new_rule(written_node) == current: use recorded
else: use current                       # a real difference; diverges as today
```

`written_node` is the site's node in the program in force when the record was
written (§4); under an unchanged program it is `node`. New records always use
the new rule. This is nine lines in the replay comparison and none in the
closed-program checker. Probe, on a journal written by the current tree: all
commits kept with no edit; the provider kept after a comment line (today it
is cancelled); cancelled after its model changes. **Rejected:** refusing such
runs at their first provider commit, which strands every run in flight.

## 3. The reuse rule

**Rule C10.** Resume under an accepted edit replays the edited program P′
against the active journal with stored values. A commit is **reused** when:

1. P′ reaches a `perform` at the commit's identity, at a site of the same
   effect class;
2. it is reached in the order relation of resume replay
   (`_Discovery._check_order` in `evaluated/replay.py`): after its structured
   predecessor's commit and, in a parallel map, after that predecessor settled;
3. the `depends_on` computed from the reached operands equals the recorded one;
4. the stored value fits the site's result type, a host reply's stored
   request validates against the node, and an agent turn's predecessor is the
   agent's previous replayed turn;
5. its freshly resolved input equals the recorded one, part by part (§2).

The **cut** is the smallest journal offset among active commits that are not
reused and pending starts that are not kept, or null. A pending start is
**kept** when P′ reaches it as the next effect of its thread at a site of the
same class; a pending host request or coordinator attempt must also resolve
to the input digest of its `started` record.

Everything at or after the cut is cancelled or retired as a C8 range does it;
nothing before it changes. Conditions 1 to 4 are checked while P′ is
evaluated, and a failure makes that effect the next to run in its thread.
Condition 5 is checked afterwards in journal-offset order and stops at the
first difference, as C7's preflight does today. §7 gives the argument.

**Edit kinds.** `plan_probe.py` ran these on completed runs, except the
binder rename (the spike's probe) and the manifest and prompt-file rows
(the spike's analysis and current C7 and C8 behavior).

| Edit | Kept | Cancelled, then run again |
| --- | --- | --- |
| Insert a step before the first | none | all |
| Insert a step between `s1` and `s2` | `s1` | `s2` to `s4`; the new step runs first |
| Insert a step after the last | all | none; the new step runs |
| Remove `s3` | `s1`, `s2` | `s3` (not run again), `s4` |
| Reorder independent `s2`, `s3` | `s1` | `s2`, `s3`, `s4`: P′ reaches `s3` first, and `s2` committed before it |
| Rename a binder | commits before it | that step (a new identity) and all later |
| Change a literal of `s3` | `s1`, `s2` | `s3`, `s4` |
| Rewrite an argument to an equal value (`a` to `(+ a 0)`) | all | none: the resolved input is equal |
| Pure edit of the result | all | none; the terminal is rewritten |
| Loop body with three committed iterations: insert a step, or change one's argument | commits before that point of iteration 1 | the rest of iteration 1, every later iteration, what follows the loop |
| Arm of a branch that was not taken | all | none |
| Second step of the taken arm | up to the arm's first step | from the arm's second step |
| Second step of a procedure called from two sites | the first call's first step | from the first call's second step, the second call included |
| Macro template used at two sites | commits before the first use whose input changes | from that use; a macro cannot hide an effect (`macro_hidden_effect`), so its edit changes operands at each use |
| Second step of an imported module's helper | up to the helper's first step | from its second step |
| Manifest: stable command, closure list, provider id, prompt source | commits before the first effect whose input part changes | from that effect |
| Manifest: an unused entry, `must_not_repeat` of a committed step | all | none |
| Prompt file or script of a committed step (program unchanged) | commits before the first effect that binds it | from that effect, by C8 (§6) |
| A step becomes another class at the same identity | commits before it | from it; attempt ordinals continue |

**Parallel map.** The cut is one journal offset, as C8's range is. Probe,
journal order `pre, [1].f, [1].g, [2].f, [2].g, [0].f, [0].g, post`:

| Edit | Kept | Cancelled |
| --- | --- | --- |
| The step after the map | 7 | `post` |
| Add an item | 7 | `post`; the new item runs |
| The second body step `g` | `pre`, `[1].f` | `[1].g`, `[2].f`, `[2].g`, `[0].f`, `[0].g`, `post` |

The third row cancels `[2].f` and `[0].f`, whose inputs did not change. That
is the rule: they committed after `[1].g`, which is not reused. Items run in
one workspace tree and no record says what a step read, so a commit is kept
only when everything that committed before it is kept. C8 made this choice
for this reason ([Phase 5 plan](../plans/2026-10-07-evaluated-execution-phase-5-plan.md)).
The cost is real: with many items, an edit to a late body step keeps about as
many first steps as the map runs at once. H-G3 reports it (§10).

## 4. The record and the lineage

**Record.** `{"record": "rebased", "program_digest": "sha256:…",
"from_offset": <byte offset or null>, "time": <seconds>}`, exactly these
keys: the edited program's digest and the cut.

**Artifact.** The edited program is published in the run root as
`closed_program.<64 hex digits of its digest>.json`, with the durable atomic
write the first program uses. `run.json` and `closed_program.json` are never
rewritten: the header's `program_digest`, `workflow_checksum` and recipe
describe the first program. An edit that returns to an earlier program
publishes it under its digest name. A name already taken must hold equal bytes.

**Lineage.** The first program, then the program of each complete `rebased`
record in journal order. Files that no record names are not lineage. Both
loaders in `evaluated/authority.py` resolve it and return the current
program; the captured-bytes loader reads the header, the first program and
the journal as today, then each named artifact once. A named artifact that is
missing, unchecked or of another digest is `memo_inconsistent`.

**Reduction.** The reducer starts with the first program's site table. At a
`rebased` record it requires that `from_offset` is null or the offset of an
active commit or pending start, that no coordinator commit lies at or after
it, and the agent rule of C8 (`check_invalidation_cut`). It applies the cut,
switches to the named program's table, and requires that every commit and
pending start that stays resolves to a site of the new program with the same
class. The record reopens a terminal, completed or failed.

So each record is validated against the program in force when it was written,
and readers take a row's class from that program, not the current one. A
reduction that meets a `rebased` record without that program's table fails
`memo_inconsistent`. A union of tables is wrong: when a step becomes a
provider at the same identity, the union answers `memo_inconsistent: effect
class disagrees with the checked site`; per-program tables reduce (probe).

**Write order,** under the run writer lock, after every refusal check:
publish the artifact; truncate a torn tail (M3); append and synchronize the
record; publish the view under the new program; evaluate. The record is
written only in resume preflight, so the program in force never changes
during an evaluation.

| Crash | On disk | Next `resume` |
| --- | --- | --- |
| W1, before the artifact's rename | Perhaps a temporary file | As before the attempt: refuses, or plans again with the flag |
| W2, artifact durable, no record | An artifact no record names | Same. Restoring the source resumes under the old program; accepting again reuses the file |
| W3, a torn `rebased` line | Not a record (M3) | Same as W2; the next writer truncates the line |
| W4, record complete, sync failed or unacknowledged | The record survives or not | Survives: W5. Not: W2. The failing process stops and dispatches nothing |
| W5, record durable, view stale or acknowledgment lost | Program switched and cut applied | Plain `resume` continues under the edited program; the flag is refused as not needed |
| W6, any later point | An ordinary journal under the edited program | §8.3 of evaluated execution, unchanged |

No state has the program switched and the cut not applied: one record does
both.

**Older builds.** Profile and schema do not change; journals are read forward
only, as for the `closure` field. A build without this design answers
`memo_inconsistent` ("record kind is missing or unknown") from `resume`
(exit 2), `invalidate` (exit 2) and `report` (exit 1) and writes nothing
(probe). With the source still edited it refuses `resume_program_changed`
first.

## 5. Refusals that stay

Each is decided before the artifact or the record is written. Without the
flag the first line is always `resume_program_changed`, and the recovery
lines give the condition as the reason the flag would not help.

| Condition | Code with `--accept-changes` |
| --- | --- |
| The edited source does not compile, or reaches a confined run-reference site | The compile diagnostics; `refuse_confined_run_ref_sites`, as today |
| The entry workflow's canonical name, the target or the representation differs from the current program's | `resume_program_changed`, naming which; a run keeps its entry and target |
| The bound inputs differ, also when the edit adds, removes or retypes an entry input | `resume_inputs_changed`; the flag does not accept inputs |
| The edit uses a bare interpreter the header did not pin | `resume_program_changed`, naming it (decision 1). A recorded pin that is missing: `resume_interpreter_missing` |
| A committed run reference, agent turn or phased provider call at or after the cut (K8) | `invalidate_coordinator_committed` |
| An agent turn attempt at or after the cut that is pending, dispatched, advanced or of uncertain outcome | `invalidate_agent_session_advanced` |
| A pending run-reference or phased-provider attempt that is not kept (§3); a kept one is recovered by K4 and the phased rules, unchanged | `resume_program_changed`: restore the source and resume, so the attempt settles under the program that started it |
| A confined child with a committed effect whose parent attempt is at or after the cut | The refusal of `guard_confined_invalidation` |
| An uncommitted attempt with a retry baseline, anywhere in the journal, at a site that declared `must_not_repeat` in the program in force when it started | `lexical_restore_pending_effect_unsafe` |
| A pure fault in the strict replay under the edited program | That `pure_expr_*` code |
| A header without a rebuild recipe; the other header and root checks | Unchanged (preflight steps 1 to 6) |

- **`must_not_repeat`.** Today the refusal reads the current node when the
  step is reached. Under an edit, a renamed step is a new identity with no
  earlier attempt, and a manifest that drops the declaration makes the node
  repeatable: in both cases the tree's strict replay passes and would run the
  step again (probe). So the check reads the journal and the program that
  wrote the attempt. A *committed* such step at or after the cut is cancelled
  and runs again, as C8 allows today; the plan marks it (decision 3).
- **Host input (ruling 6).** A `request_input` commit at or after the cut is
  cancelled like any commit, the plan lists it under "asked again", and the
  next resume issues a new request with a new ID; the old ID is refused as
  `host_input_stale` (probe, with C8 on the current tree). A pending request
  is kept when its question, contracts and dependencies are unchanged; else
  the cut withdraws it. **Required change:** `_request_id` binds the current
  program's digest, so today a committed reply fails validation under any
  edited program, also one edited after it (probe). The ID is checked against
  the program in force when the request started; the probe then keeps the
  reply. `input answer` and `input cancel` take no flag.
- **Run-reference children (ruling 8).** The flag and the edit are never
  passed to a child run. A child whose own program changed refuses under its
  own header, as today.
- **Python-built runs (ruling 5).** `resume` rebuilds the generated `.orc`
  copy the header names. An edit to the `.py` file is not seen and nothing
  refuses; the guide must say so.

## 6. Preflight and the command line

Steps 1 to 6 of "Resume preflight precedence" are unchanged. Then:

7. Fresh build; compile errors refuse. Decode only the journal's complete
   lines of kind `rebased`: the current program's digest is the last one
   named, else the header's. No artifact is loaded. Equal: continue as today.
   Different without the flag: refuse `resume_program_changed`. Different
   with the flag: the fresh program is the candidate; check its entry, target
   and representation.
8. Fresh inputs against the fresh program; `resume_inputs_changed` against the
   header's digest, with or without the flag.
9. Stored authority: every program of the lineage, command transport and
   interpreter pins.
10. Memo replay. *Program unchanged:* as today, except that with the flag a
    first divergence at a **committed** effect is not a refusal: after C8's
    checks it becomes the anchor of the `invalidated` record that
    `invalidate` would write. *Candidate program:* plan the cut (§3) and
    check §5 on the cancelled range. In both cases, reduce the journal in
    memory as it will be after the record and run today's strict replay on
    it, under the program that will be current; that pass includes the
    retry-baseline rule for unfinished commands. Last, the flag is refused
    with `resume_preflight_failed` unless something needs it: an edited
    program, a committed effect's diverged input, or an unproven command
    attempt as defined today.
11. Write (§4, or the `invalidated` record), log `[changes_accepted]` with the
    plan, then evaluate.

**The plan** follows the refusal's first line and is printed again on
acceptance. It is computed after the refusal is decided, read-only; if it
cannot be computed (a corrupt stored artifact, an unreadable journal) today's
generic lines are printed and the exit code is unchanged. Lists stop at 20
lines, then `... and N more`.

```text
[resume_program_changed] current program differs from the run's program
effect sites that differ from the recorded program:
  added   workflow:four::run / x
with --accept-changes this run continues under the edited program:
  kept      1 committed step: workflow:four::run / s1
  cancelled 3 committed steps, which run again when reached:
    workflow:four::run / s2   (provider cost USD 0.42)
    workflow:four::run / s3   (declared must-not-repeat)
    workflow:four::run / s4
  asked again: none
  runs first: workflow:four::run / x
  files that cancelled steps wrote in the workspace are not rolled back
    orchestrator resume RUN_ID --accept-changes
```

Cost is the cancelled attempts' `usage.json`, priced as `report` prices it,
where metered. The lines for restoring the source and for a new run follow as
today. A §5 refusal found in step 10 replaces the plan with its code and
reason, and no flag command is printed. The `effect_input_diverged` refusal
for a committed step gains the same flag command beside `invalidate`.

**One flag (ruling 3).** One invocation accepts the edited program, a
committed effect's changed input and the changed files of every unproven
unfinished command attempt; the refusal lists all of them first. The 3a
properties hold: explicit, refused when nothing needs it, prints what it
accepts.

**Idempotence.** After acceptance the fresh build equals the current program:
plain `resume` continues or returns the recorded terminal with no write, and
the flag is refused as not needed. Accepting twice never writes two records.

## 7. Soundness and its limits

**Protected invariant: replay equivalence.** After an accepted edit the active
journal is one that an uninterrupted run of the edited program could have
produced, with reused effects returning their recorded results. It holds
because the strict replay of §8.4 passes on the journal as it will be: every
active commit is reached at its identity, in order, with equal dependencies
and equal resolved input; every pending start is the next effect of its
thread; nothing else is active. The planner is not trusted for this; the
unchanged strict check is. `plan_probe.py` ran that check, from the current
tree, on its 20 edits (§3), and it passed each time.

**Why a prefix.** Kept commits are downward closed: an effect P′ evaluates
before a kept one is itself kept (else evaluation stopped there), and by
condition 2 it lies earlier in the journal. Every kept effect therefore ran
after only kept effects had committed, so what it read from the workspace was
written by the same committed history.

**Not covered.**

- **Workspace files of cancelled effects.** A step that runs again sees files
  a cancelled later step left, and repeats its own writes (the spike's case:
  102 after the edit, 2 from a fresh run). This is `invalidate`'s limit made
  routine. It is the author's risk (ruling 7), stated in the printed plan and
  the guide. For agent steps it is the normal case.
- **Undeclared reads** (C5): environment, clock, network, files opened by
  computed name, the model behind a provider id. Such an effect may be reused
  with a result a fresh run would not give, as today.
- **Siblings in flight.** In a parallel map a kept effect may have run while a
  now-cancelled sibling was running, as today after a kill or `invalidate`.

**Why 3c stays out.** Keeping a commit that follows a cancelled one needs to
know what it read. `depends_on` records values only, and a file dependence
leaves no trace (the handoff fixture of §17); the spike's value-only rule
mixed old and new results. Per-item reuse in a parallel map is the same
question.

## 8. Readers, metering and caches

- **View.** When the journal has a `rebased` record, the view gains `programs`
  (per lineage program: digest, the record's time or the header's
  `started_at`, the cut) and each row gains `program`, the index of the
  program in force when its latest attempt started. Without such a record
  neither key exists, so views of existing runs are byte-identical. Rows stay
  for identities the current program no longer has. A commit a cut covers and
  a start a cut retired show `invalidated`.
- **`report` and the dashboard** print the program list and each row's
  program. Cost totals still sum every attempt of every row, and the spend
  cap already sums every attempt directory under the run root (`spent` in
  `providers/usage.py`): cancelled attempts stay counted and an edit refunds
  nothing.
- **`invalidate`** works on a run with several programs: C8 is about offsets
  and may reach back past a `rebased` record. It never changes the program.
- **The REPL** attaches by comparing its build with the current program.
- **The reduction cache** (`_LAST` in `evaluated/memo_reducer.py`) compares
  the caller's site table and a byte prefix, and saves the fold's state
  without the table. Under a lineage it must compare the lineage's tables as
  the caller gave them and save the table in force with the state; else a
  fold continued after a `rebased` record runs under the wrong program. The
  `start_reached` shortcut of `publish_evaluated_view` is unaffected: the
  record is not a `started` row, and its own view is replayed in full.

## 9. Evidence, exit test and regression baseline

Case table in the style of evaluated execution §17; each row is measured
through the public `run` and `resume` entries with stand-in scripts.

| Requirement | Measure |
| --- | --- |
| Insert before step two (exit case b) | A completed four-step run; insert an effect before step two. Plain `resume` exits 2 with `resume_program_changed`, prints the plan and changes no byte. The printed flag command exits 0; started are the new step and steps two to four at attempt 2; step one was dispatched once. One `rebased` record and a second artifact. A second `resume` exits 0 with no write; the flag again is refused |
| A file dependence under an edit (exit case c) | `a` writes a file that `b` reads by name; edit `a`'s argument and accept. The result equals a fresh run of the edited program in a clean clone; `a`, `b` and `c` ran again |
| Each edit kind | Every row of §3's tables: the kept and cancelled sets, and for command-only fixtures the final value against a fresh run in a clean clone. No kept commit has a cancelled one before it in the journal |
| Positions | A comment line above a provider, accepted: the provider is not dispatched. The same on a journal recorded before the `declaration` change |
| Record durability | Kill at W1 to W5 of §4: each recovered run is entirely under the old program, or entirely under the new one with the cut applied; nothing is dispatched before the record is durable |
| Lineage | Three accepted edits, one returning to the first program: `report`, the dashboard, `invalidate` and a completed resume read the run; a deleted or altered artifact is `memo_inconsistent` |
| Refusals | Each row of §5, with and without the flag: its code, exit 2, run tree bytes unchanged |
| Host input | An edit after a committed reply keeps it; an edit before it asks again, lists it in the plan and refuses the old request ID |
| The flag | Not needed: refused. An edit together with a failed step's fixed script: one resume. A committed step's changed prompt file: one resume, and the journal that `invalidate` then `resume` writes |
| Kills under an edited program | The kill suite's windows on a run that has a `rebased` record: the final value of the uninterrupted edited run, and no kept commit dispatched twice |

**Exit test (roadmap).** Case (a), the fixed script of a failed third step,
is owned by 3a's test `test_fixed_script_resumes_the_failed_step_and_the_one_after`,
which passes unchanged. Cases (b) and (c) are the first two rows. The
kill-at-every-commit suite passes unchanged.

**Must pass unchanged,** except the tests named under "Change":
`tests/test_workflow_evaluated_{resume_kills,recovery,recovery_branches,recovery_views,resume,resume_replay,resume_replay_boundary,resume_retry,script_fix_retry,script_fix_review,invalidate,invalidate_durability,invalidate_smoke,invalidate_windows,memo,memo_writes,views,readers,authority,child_authority,prompt_edit_continue,provider_usage,report_usage,spend_cap}.py`,
every `tests/test_workflow_evaluated_parallel_*.py`,
`tests/test_resume_command.py`, `tests/test_cli_recovery_messages.py` and
`tests/test_first_hour_e2e.py`. Among them
`test_terminal_helper_captures_three_files_once_without_source_or_preparation`
holds because a run without a `rebased` record is still read as exactly three
files in the same order.

**Change.**

- `tests/test_workflow_evaluated_resume.py`:
  `test_preflight_refusals_preserve_all_evidence` (case `program`) and
  `test_program_comparison_precedes_invalid_file_inputs_and_artifact` keep
  their code, exit status and unchanged-bytes assertions. What they pin
  narrows from "no memo record or artifact is read before the refusal" to
  "the refusal is decided from the header and the journal's `rebased` records;
  the plan reads the stored programs and the memo afterwards".
- Tests that unpack or compare the exact commands a refusal prints; each
  refusal gains the flag command. In `tests/test_cli_recovery_messages.py`:
  `test_program_edit_refusal_names_the_changed_step_and_a_run_command_that_works`,
  `test_committed_script_edit_refusal_prints_invalidate_and_resume_that_recover`
  and `test_a_shared_script_edit_after_invalidating_later_steps_offers_invalidate_that_recovers`.
  In `tests/test_workflow_evaluated_script_fix_retry.py`:
  `test_shared_script_fix_recovers_through_printed_invalidate_and_resume`.
  The tutorial's printed `invalidate` block, with
  `test_tutorial_blocks_run_as_written` in `tests/test_first_hour_e2e.py`.

## 10. Measuring H-G3

No provider call is needed.

- **Planning is a library call.** One read-only function takes a run root and
  a workspace and returns the plan (kept and cancelled commits with their
  attempt directories, the effects that run first, the requests asked again)
  or the refusal. `resume` without the flag is its command-line form and
  writes nothing; no command is added.
- **Per edit,** for two consecutive versions of a workflow: get a journal for
  the first (a retained run root, or a run with stand-ins), plan the second
  against it, and weight each provider commit by recorded tokens
  (`usage.json`), else wall time, else count. Report the cost kept over the
  cost committed, the cost cancelled and any refusal with its code, beside
  whole-run restart (0) and an upper bound: commits whose identity and input
  are unchanged regardless of order. The gap to that bound is what the prefix
  rule and the parallel rule cost. For command-only and stand-in runs, also
  compare the resumed result with a fresh run in a clean clone.
- **Real edits.** An accepted edit is recorded by the lineage itself: both
  artifacts and the journal stay in the run root. An edit that was not
  accepted leaves nothing; recording those is opt-in (decision 5).

## Proposed contract changes

Against evaluated execution unless a row says otherwise. "Before" quotes the
current text; "+" means the current text stays and the quoted text follows it.

| Where | Before | After |
| --- | --- | --- |
| §3, goals | "Resume never runs an effect that committed a result." | "Resume never runs an effect that committed a result, unless an invalidation or an accepted edit cancelled that result (C8, C10)." |
| §7.1 M4 | "that no later `invalidated` range covers (C8)" | "that no later `invalidated` range or `rebased` cut covers (C8, C10)" |
| §7.1, record table | (new row) | "`rebased`. Written: once per accepted edit, by resume preflight, after the edited program's artifact is durable (C10). Content: `program_digest`, `from_offset` (the cut, or null), time" |
| §7.1, terminals | "A terminal is reopened by `invalidated`, or, after a failed terminal, the next `started` record." | "A terminal is reopened by `invalidated` or `rebased`, or, after a failed terminal, the next `started` record." |
| §7.2 | (added) | "A provider's `declaration` part is the digest of its checked effect node without source positions at any depth. A recorded value written under the earlier rule is compared under that rule." |
| §7.3 C7 | "a fresh build is compared with the header, and resume is refused with `resume_program_changed` before any memo record is read." | "a fresh build is compared with the run's current program (§8.4), and resume is refused with `resume_program_changed` unless the author accepts the edit under C10." |
| §7.3 C7 | "refuses at the first divergence with `effect_input_diverged`, before any launch or reconciliation (§8.4)" | + "; `resume --accept-changes` instead applies C8 at that commit" |
| §8.1, the flag | "including a pending start an invalidation retired. It is refused with `resume_preflight_failed`, after every other preflight check and before any write, unless one such attempt needs it:" | "including a pending start an invalidation or a cut retired. The flag also accepts an edited program and a committed effect's changed input (C10). It is refused with `resume_preflight_failed`, after every other preflight check and before any write, unless the program was edited, a committed effect's input diverged, or one such attempt needs it:" |
| §8.1, table | "An `invalidated` range covers the last commit" | "An `invalidated` range or a `rebased` cut covers the last commit" |
| §8.4, comparison | "Compare the fresh program digest first; only after program equality read the requested input file, apply its explicit overrides, bind against that fresh program and compare the input digest. A mismatch refuses with `resume_program_changed` or `resume_inputs_changed` before reading any memo record or mutating run evidence." | "The run's current program is the header's, or the one named by the last `rebased` record; no other memo record is read for this comparison. A different program refuses with `resume_program_changed`, printing what C10 would keep and run again, unless the author passes `resume --accept-changes`. Then read the requested input file, apply its explicit overrides, bind against the fresh program and compare the input digest with the header's; a difference refuses with `resume_inputs_changed`, with or without the flag. Neither refusal mutates run evidence." |
| §8.4, stored program | "Then validate the stored artifact's checked form and header digest; execute that stored artifact after equality is established." | "Then validate every stored program of the lineage, the first against the header digest and each later one against the record that names it; execute the stored current program." |
| §8.4, publication | "Never replace the header or program after journal activity begins." | + "An accepted edit adds a program artifact beside them (C10)." |
| §8.5 | "For a committed result, the continuation is C8." | "For a committed result, the continuation is C8, by `invalidate` or by `resume --accept-changes`." |
| §9.5 | "run/header/program/effect/ordinal-bound ID" | + "The program is the one in force when the request started; a later program of the lineage checks the ID against that one." |
| §10 V1 | "A view is derived from the memo and the program." | "A view is derived from the memo and the run's programs: each row is read under the program in force when it was written, and the run's position comes from the current program." |
| §10 V5 | "`invalidated` for every commit covered by a range record (C8)" | "`invalidated` for every commit a range record or a cut covers and every start one retired (C8, C10)" |
| §11 | "Resume reuses each item's committed prefix and executes only missing effects." | + "A cut (C10), like an invalidation, is a whole journal suffix and does not keep a sibling item's later commits." |
| §17 | (new rows) | The rows of §9 above |
| `specs/cli.md`, the flag | "accepts, for this invocation, the changed declared files of every unfinished command attempt that no clean failure covers (step 10 below); it is refused when there is none." | "accepts, for this invocation, an edited program, a committed step's changed input, and the changed declared files of every unfinished command attempt that no clean failure covers (steps 7 and 10 below); it is refused when nothing needs it." |

**New rule C10 (§8.5):** the first three paragraphs of §3 above, then: "After
publishing the edited program's artifact beside the first, one synchronized
`rebased` record names the program and the cut. It cancels every active
commit and retires every pending start at or after the cut, as a C8 range
does, and reopens the terminal. Every C8 refusal applies to that range, and
an uncommitted attempt of an effect that declared `must_not_repeat` refuses
the edit. The record is written only when the strict replay of §8.4 passes
under the edited program on the journal as it will be. Journal records are
validated against the program in force when they were written. The header
and the first program are never replaced."

**Other spec text.** `specs/cli.md`: preflight steps 7 and 9 to 11 as in §6;
in "Diagnostics", the `resume_program_changed` row and the two committed
`effect_input_diverged` rows gain the plan and the flag command, and a new
diagnostic `changes_accepted` is logged once the record is durable.
`specs/state.md`: the run root gains `closed_program.<digest>.json`, "Memo
records" gains `rebased` with its reducer rule, the view gains `programs` and
the row key `program`, and the host request ID rule changes.
`specs/versioning.md`: a build without this design answers
`memo_inconsistent` once a run has a `rebased` record; profile and schema are
unchanged.

## Probes

No model was called: `experiments/thread_m/no_provider` was first on `PATH`
and logged no attempt. The planning steps wrote nothing in a run root
(asserted by byte comparison) and nothing in the repository.

| Claim | Probe | Result |
| --- | --- | --- |
| What `declaration` digests, and the new rule | `decl_probe.py` (compile only, 13 variants) | The table of §2 |
| Hygiene counters reach the node and the prompt | `hygiene_probe.py` | `%1` becomes `%2` after an unrelated earlier shadow; unchanged after a later one or a comment |
| Runs in flight keep resuming; the rule under an edit | `inflight_probe.py`: a journal written by the current tree, a script named `gemini` as stand-in | The recorded digest equals the old rule. With the rule: all kept with no edit; the provider kept after a comment line; cancelled after a model change |
| The cut, per-program tables, the strict replay after the record | `plan_probe.py`, 20 edits | §3's tables. The tree's `discover_prefix` and `_validate_discovered_prefix` pass under the edited program each time. The union table fails on a class change |
| What an older build does | `older_build_probe.sh` | `memo_inconsistent` from `resume`, `report` and `invalidate`; tree bytes unchanged |
| Host replies under an edit; asking again | `host_probe.py`, target 2.40 | Today the reply is lost under any edit. With the ID checked against the writing program it is kept after a later edit, also with shifted lines. A cut at the reply asks again; the old ID is `host_input_stale` |
| An edit can bypass `must_not_repeat` | `repeat_probe.py` | After a rename, or after dropping the declaration, the strict replay passes and would run the step; the designed check names the attempt |

One finding for the planner: `_Discovery.__call__` records a commit as
consumed before it validates the stored value (result type, host payload).
The lenient pass must take such a commit back, as the probe does.

## What this makes harder

- A run is the product of several programs: every reader needs the lineage,
  and a row's class is no longer a function of the current program.
- "Nothing in the memo is read before the program check" becomes "only
  `rebased` records are".
- Running steps again on a workspace that holds their earlier output becomes
  an everyday operation, not an explicit `invalidate`.
- One early edit discards everything after it, and in a parallel map most of
  the map. That pressure leads to 3c, which needs declared reads and writes.
- The old `declaration` rule stays in the replay comparison until old runs
  age out, and host request IDs depend on which program wrote the request.
- One flag means three things; a user cannot accept one and refuse another.
- A refused `resume` now costs a replay and a rehash of the kept commits'
  files, to print the plan. Each accepted edit keeps a program artifact.
- A build that predates this cannot read a run that accepted an edit.
- This is reuse inside one run. A child program on another clone (roadmap
  Phase 6) gets nothing from it.

## Open decisions

The coordinator rules on each.

| # | Decision | Recommended | Alternative |
| --- | --- | --- | --- |
| 1 | An interpreter the edit adds | Refuse, naming it. A path spelling (`./tool`) is not pinned and is accepted | Pin it in the record: one field, and about ten readers of `header["interpreters"]` change. A `bash` step inserted into a `python` pipeline then needs no workaround |
| 2 | Parallel map | The whole-suffix cut | Keep each item's own prefix when every item has its own `:workspace`. It gives up "a kept commit follows only kept commits" and belongs with 3c; decide after H-G3 shows what the suffix rule costs |
| 3a | An uncommitted `must_not_repeat` attempt | Refuse, by the declaration in force when it started | Accept when the author removed the declaration |
| 3b | A committed `must_not_repeat` step at or after the cut | Cancel and mark it in the plan, as C8 does | Refuse; that protects nothing, since the other route is a new run that repeats it |
| 4 | A committed step's changed file, program unchanged | The flag writes the `invalidated` record C8 defines, so `rebased` always means a program switch and an older build can still read the run | A `rebased` record with the same digest |
| 5 | Recording edits that were not accepted | Opt-in by an environment variable, saving the fresh artifact under `.orchestrate/edits/<run id>/` | On by default: it writes during a refusal, and tests that compare `.orchestrate` bytes around a refusal change |
| 6 | The plan on every refusal | Yes (ruling 2) | A one-line refusal and the plan on request, if the replay proves slow on long journals |
| 7 | Hygiene names in provider input rows | Leave; state the limit in the guide | Label rows by authored name at a new target |
| 8 | Version signal | None, as ruled for the `closure` field | A schema bump, which makes older builds refuse every new run |

## Not verified

- **Coordinators.** No probe put a run reference, agent turn or phased
  provider in a journal. That a committed one before the cut is reused under
  an edited program, and that the C8 guards work at an offset that is not a
  commit's, was read (`validate_evaluated_run_ref`, `validate_turn`,
  `validate_phased_commit`, `check_invalidation_cut`,
  `guard_confined_invalidation`). Only the host request ID was found to bind
  the parent program's digest. **Open prerequisite:** the implementation
  plan's first task runs each class with the test suite's stand-ins, before
  any code.
- The old-rule comparison for a pending provider-class start recovered across
  the change (an agent turn's `recoverable` path, a phased retry).
- Crash windows W1 to W5: argued from M2, M3 and the atomic write, not
  fault-injected.
- Views, `report`, the dashboard and the REPL on a run with several programs:
  designed, not prototyped.
- The plan's cost on a long journal; parallel interleavings other than the
  one fixture.
- `input answer` under an edited program, Python-built runs and the
  reduction cache under a lineage: read, not run.
- The probes used command steps and one stand-in provider, no agent step; for
  the workspace-leftover limit the spike's case is the evidence.
