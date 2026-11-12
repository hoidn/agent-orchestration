# Workflow Lisp Edit And Continue: Feasibility Spike

**What this page is.** The feasibility report for Phase 3 ("Edit and
continue") of the [current roadmap](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md),
with a proposed revision of the execution contract. It answers the roadmap's
seven spike questions from the code and from probes that call no model.

**Status.** Feasibility spike. The coordinator accepted its verdict on
2026-11-11 with the [rulings below](#coordinator-rulings-2026-11-11); the
contract revision it proposes is not accepted until an implementation plan
lands it. Part 3a is implemented by its
[plan](../plans/2026-11-11-roadmap-phase-3a-script-fix-retry-plan.md), and its
contract text (§7.1, C4, §8.1, §8.5, §17) now lives in evaluated execution and
`specs/cli.md`, which govern; this page's 3a text is the proposal they
replaced. 3b is not implemented. The prototype this page reports was throwaway
and is deleted.

**What owns the behavior today.** [Evaluated execution](workflow_lisp_evaluated_execution.md)
(§7.3 C4 and C7, §8.1, §8.4, §8.5) and the [CLI contract](../../specs/cli.md)
("Resume preflight precedence", "Diagnostics"). A run resumes only under the
program it started with. A failed command whose `failed` record says
`closure: unchanged` is retried with its current script; any other unfinished
command with changed files needs `resume --accept-changes`. Follow those rules
and the recovery lines the CLI prints.

**Copy safety.** Transcripts are evidence, not recipes: the `ORC_SPIKE_*`
variables existed only in the prototype. Probe scripts and the prototype diff
are in the session scratch directory `/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/spike-phase3/`
(`ident/ident.py`, `exit/case_*.sh`, `prototype.patch`), which is not durable.

## Verdict

**3a (retry a failed step after its script is fixed): feasible as stated,** in
a form that keeps what the retry-baseline rule protects. **3b (resume an edited
program by reusing the journal prefix it reproduces): feasible as stated,** with
three conditions the roadmap does not list. The provider input digest must stop
including source positions: today one comment line above a provider call makes
its recorded result unusable under an edited program. The cancelled part of the
journal keeps every refusal that `invalidate` has. The Python surface needs its
own way to resume, because `resume` rebuilds a stored copy of the generated
source and never sees an edit to the Python file. Each part relaxes a refusal
and keeps the property the refusal protected; 3b makes routine one limit
`invalidate` already has (files left in the workspace by cancelled steps are
not rolled back). Stable generated names are not a precondition for 3b. 3a can
ship first.

Terms used below. **Journal:** the run's `memo.jsonl`. **Commit:** a
`committed` record that no later record cancels. **Closure:** the files a
command boundary declares; **evidence:** their content digests, stored in each
attempt's `started` record. **Retry baseline:** the evidence in the latest
`started` record of a command that has no commit. **Cut:** the journal offset
from which commits are cancelled. **Stand-in:** a local script named `codex`,
first on `PATH`, that writes a fixed result; no model is called.

## 1. Why the retry-baseline rule exists

1. C4 promises that a command's closure is read-only, so a commit binds file
   bytes its attempt did not write. The enforcing check (rehash before commit,
   `command_closure_written`) runs only when an attempt produces a valid result.
2. An attempt that writes its own script and then fails or is killed escapes
   that check. Without a baseline the next resume would hash the changed bytes
   as fresh evidence, run them and commit under them.
3. The rule cannot tell the author's fix from the attempt's own write (both are
   "bytes differ from `started`"), so it refuses both, with no override.

Evidence. The rule entered the design in one review round (`9fa10443`,
2026-09-29) with the evidence row "A command modifies its declared script and
exits: C4 fails it; resume ... launches nothing until original implementation
evidence is restored", marked "a contract counterexample, not a demonstrated
production failure". The code followed in `304b3bbf` (`_retry_baseline`,
`_check_retry_implementation` in `evaluated/effect_inputs.py`). The fixtures
that pin it change the script from inside the command: in
`tests/test_workflow_evaluated_recovery.py` the command appends `# changed by
its own attempt` and is then killed. No fixture has the author edit a file.
`finish_effect` in `runtime.py` rehashes only after a valid result, so today
the journal cannot say whether a failed attempt touched its closure.

**A version of 3a that keeps the protection.** The rule protects this: no
attempt's own closure write becomes the implementation of its retry without
anyone saying so. Two changes keep that and admit the author's fix.

1. Rehash the closure when an attempt fails too, and store the outcome in its
   `failed` record (`closure`: `unchanged` or `changed`). After `unchanged`, a
   later difference was made after the attempt ended, so resume starts the next
   attempt with the current bytes. Its `started` record holds the new evidence
   and becomes the baseline; failed attempts stay as evidence under the digests
   in their own `started` records. No new record kind.
2. An attempt with no `failed` record (killed, crashed, Ctrl-C) or with
   `closure: changed` keeps today's refusal unless the author accepts the
   change on the command line.

A retry is then protected exactly as a first attempt is: another step may still
write the script between attempts, which C4's local check does not cover today
either. `must_not_repeat` is untouched. The sentence that changes is "No
override or additional approval surface is introduced" (§8.1).

## 2. Identity stability under edits

An effect's identity is its activation path plus its site; the site ends in the
binding's label (§6, I3 and I4). In `.orc` the label is the authored `let*`
name, or `#k` for the k-th unnamed effect of its scope. The Python frontend
names every binding from a counter per definition, in trace order (`_e0`,
`_loop0`; `_NameAllocator.next` in `orchestrator/py/trace.py`). Probe
`ident/ident.py` compiles 13 edits of one pipeline on both surfaces.
"Insert a step" means a named one unless stated.

| Edit | `.orc`: identities that change | Python: identities that change |
| --- | --- | --- |
| Blank lines, a comment, a pure binding | none | none (same program digest) |
| Insert a step before, between or after steps | none | every effect traced after it |
| Insert a step inside a loop body | none | the loop (named after its body is traced) and everything after |
| Insert an unnamed effect before an unnamed one in one scope | the later one (`#1` to `#2`) | the later one |
| Rename a binder | that effect | none: variable names are not used |
| Change a literal argument | none; that effect's input changes | none; same |
| Wrap a step in a conditional | that step (`c` to `c / body / then / #1`) | that step and every later one |
| Reorder two independent steps | none; journal order differs | the two swap names |
| Move a step into a helper procedure | that step (gains a call frame) | that step |
| Insert a step in a branch that is not taken | none | every effect traced after it |

**Positional names cost little under prefix reuse, because both are
positional.** A counter shifts only names traced after the insertion, and in a
serial program those effects also follow it in the journal, where the cut
cancels them anyway. On the Python surface the prototype kept `a` and `b` and
re-ran `c` and `d` after a step was inserted before `c`, the best any naming
rule could do. Names lose reuse only for code traced but not executed before
the next commit: a step inserted in the branch not taken kept 1 commit of 4.
A swapped name is no soundness risk, since reuse also needs an equal input.

**A naming rule that survives insertion.** Name each Python effect after what
it calls, with a suffix for repeats and an optional explicit label. It needs no
frame inspection and reads better in `report`. Branch `feat/p2-names`
(`801a72ae`, not merged when this was written) implements it as `_<callee>`,
`_<callee>_<k>` and `name=`. `.orc` needs at most a lint for unnamed effects.
The rule strands no existing run: a `py run` header records the generated
`.orc` copy under `.orchestrate/python/<hash>/generated/`, and `resume`
rebuilds that copy. It changes every Python program digest, so frozen build
pins must be refreshed. `.orc` identities do not change.

**A defect that matters more than names.** The provider input part
`declaration` digests the effect node after `strip_provenance`
(`resolve_provider_input` in `evaluated/providers.py`), which removes the
position record `@` from the effect node only. Operand nodes under `inputs`,
prompt fills and policy keep file, line and column. A resume under the same
program executes the stored program and never notices. Under an edited program
every provider below a shifted line diverges (`exit/case_prov.sh`, stand-in):

```text
== append a step after the provider ==
edit accepted: 3 committed steps kept; run again: none          (provider calls: 0)
== same, plus one comment line above the provider ==
first divergence: workflow:prov::run / p: ... (input parts changed: ['declaration'] ...
edit accepted: 1 committed steps kept; run again: p, s3         (provider calls: 1)
```

## 3. What replay must change for 3b

The engineering review found four checks that assume one program; the resume
path has ten. **Lineage** is the ordered list of programs a run has
executed under.

| # | Check today | Where | Under prefix reuse |
| --- | --- | --- | --- |
| 1 | Fresh program digest equals the header's, before any memo record is read | `prepare_evaluated_resume` in `cli/commands/evaluated.py` | Compare with the run's current program: the header's, or the one named by the last lineage record, which is in the journal. "Before any memo record" narrows to "only lineage records are read" |
| 2 | Stored program, interpreter pins and bound inputs match the header | `_validate_program_binding`, `_validate_interpreter_pins` in `authority.py` | Unchanged for the first program. An edit that adds an interpreter pins it in the lineage record; one that changes bound inputs keeps `resume_inputs_changed` |
| 3 | Every journal row's identity resolves to a site of the program | `_Reducer.site_class` in `memo_reducer.py` (all identity-bearing rows, each `depends_on` entry) | Rows are checked against the program that wrote them: the reducer switches site table at each lineage record. A union of tables is wrong when an identity changes class |
| 4 | Commits are reached in journal order with equal `depends_on` | `_Discovery._check_order`, `__call__` in `replay.py` | Becomes the test for reuse; a violation ends the reusable prefix |
| 5 | Every active commit and pending start is reached; a completed terminal equals the evaluated result | `_Discovery.finish`, `execute_pure_resume`, `_replayed_halt_result` | What is not reused lies at or after the cut and is cancelled by the lineage record, which reopens the terminal. The strict checks then hold again, unchanged |
| 6 | A reached commit's resolved input equals the recorded one | `_reuse_effect_commit` in `effect_inputs.py` | Becomes the test for reuse; needs the `declaration` fix first |
| 7 | Only an `invalidated` record lifts a retry baseline | `_retry_baseline` | A cut lifts it too |
| 8 | Readers and `invalidate` load the header's program | `load_run_authority` (15 call sites), `load_run_authority_from_bytes` (4: views and `report`, capture, child runs) | Both loaders resolve the lineage. Before that the prototype's `report` failed with `memo_inconsistent`; after it `invalidate` worked on a rebased run |
| 9 | The header's rebuild recipe is immutable | `resume_request`, §8.4 | Enough for `.orc` edited in place. A Python run's recipe names the generated copy: after an edit to `pipe.py`, `resume` printed the old result (`exit/pyprobe`). The lineage record carries the new recipe; a Python entry builds it |
| 10 | An agent turn's predecessor chain and a host request's stored payload match the checked node | `_advance_agent_cursor`, `validate_checked_request` | Become tests for reuse |

**Mechanism** (rule C10 below). Replay the edited program against the active
journal with stored values; a commit is reused when checks 4, 6 and 10 pass.
The cut is the smallest offset among active commits not reused and pending
starts the edited program does not reach next. One synchronized `rebased`
record switches the program and cancels everything at or after the cut.
Planning is read-only, a torn record is not a record (M3), and one record
leaves no window between a program switch and a cancellation.

**Parallel map.** Item commits interleave. The [Phase 5 plan](../plans/2026-10-07-evaluated-execution-phase-5-plan.md)
keeps invalidation as a whole offset suffix there, because siblings share a
workspace and no record says what they read. The cut follows the same rule and
the existing order relation computes it unchanged. Probe `exit/case_par.sh`
(journal order `pre, [1].f, [1].g, [2].f, [2].g, [0].f, [0].g, post`):

```text
== edit the step after the map
edit accepted: 7 committed steps kept; run again: post
== edit the second step of the item body
edit accepted: 2 committed steps kept; run again: [1] / g, [2] / f, [2] / g, [0] / f, [0] / g, post
```

The second case cancels `[2].f` and `[0].f`, whose inputs did not change,
because they committed after the first diverged commit. Adding an item to the
list kept all seven map and `pre` commits and ran only the new item and `post`.

**Coordinators and host input.** A committed run reference, agent turn or
phased provider call is never cancelled (K8). One at or after the cut refuses
the edit with `invalidate`'s codes; the author restores the source or starts a
new run. For pipelines on Agent Sessions an edit is therefore accepted only
when it changes steps after the last committed turn. A committed host reply is
an ordinary commit that `invalidate` can cancel today; a cut would ask the
person again, so the plan printed before acceptance must list it. A retired
pending start of a `must_not_repeat` effect must refuse: today its restriction
applies "when its identity is reached again", and after a rename it never is.

## 4. Soundness

**Argument.** Let P′ be the edited program and R the reused commits. Replay of
P′ reaches exactly R, in the journal's structured order, each with the input it
recorded, before anything else. Evaluation is a function of program, inputs
and committed results (§8.3), so an uninterrupted run of P′ in which those
effects returned those results would have written the same commits in the same
order. Each reused effect was preceded in the original run by the same effects
with the same inputs as in that run, so what it read from the workspace was
written by the same history. Everything else is cancelled and runs again. Pure
code is re-evaluated on every replay and never memoized.

| Case | What happens | Disposition |
| --- | --- | --- |
| A re-run step reads a file left by a later, cancelled step, or repeats a non-idempotent write | It sees a workspace no uninterrupted run would. `exit/case_leftover.sh`: resume after the edit returns 102, a fresh run of the edited program 2; with no edit, `invalidate` plus `resume` returns 101 today | Author's risk, as for `invalidate`; the printed plan says so. Rollback is a non-goal (§3) |
| Reuse out of journal order | Mixes old and new results for effects coupled through files (`depends_on` of the reader is empty in `exit/case_c.sh`) | Not offered; deferred as 3c |
| An edit to pure code that changes no effect input | Sound. Prototype: 4 commits kept, result 4 became 104 | Accept |
| An edit to a manifest | A changed stable command, closure list, provider id or prompt source changes an input part and diverges its effects; a changed `must_not_repeat` or unused entry cancels nothing | Accept; check 6 covers it |
| A changed interpreter binary; an undeclared read (environment, clock, network, undeclared files) | Not in any effect input: C3 logs `interpreter_changed`, C5 puts the rest outside the promise | Unchanged policy |
| The edit changes a committed effect's result type | The stored value no longer fits | A divergence, not an inconsistent memo |
| A pure fault in the edited program before its first new effect | Planning fails | Refuse before any write |

Replay equivalence holds for the reused part without qualification, and for
the re-run part up to what cancelled steps left in the workspace. That
qualification is `invalidate`'s; what is new is how often it applies. For agent
steps it is the normal case: a re-run agent sees its cancelled attempt's edits.

## 5. Prototype

Built on a detached worktree of `main` (`55d39f01`) and removed: 106 changed
lines in six modules and one new module of 93 lines. `ORC_SPIKE_ACCEPT_EDIT`
stood for accepting an edited program, `ORC_SPIKE_ACCEPT_FILES` for accepting
a changed script explicitly.

**(a) Fix the script of a failed third step.** Today `resume` refuses
(`effect_input_diverged`, "retry implementation files changed"). In the
prototype a plain `resume` ran attempt 2 of step three and attempt 1 of step
four; steps one and two did not run again. Negatives (`exit/case_a_neg.sh`): a
step that appended to its own script and failed recorded `"closure":"changed"`
and still refused; a step killed in flight and then edited refused until the
change was accepted explicitly.

**(b) Insert an effect before step two of a completed run.**

```text
edit accepted: 1 committed steps kept; run again: workflow:four::run / s2, workflow:four::run / s3, workflow:four::run / s4
```

The new step ran, then attempts 2 of steps two to four; step one did not run
again. The journal gained one `rebased` record and the run root a second
program artifact; a second `resume` returned the terminal and ran nothing.

**(c) A dependence through a file.** `a` writes `handoff.txt`, `b` reads it by
name, and no value flows between them. After `a`'s argument was edited, resume
returned 14, a fresh run of the edited program returned 14, and `a`, `b` and
`c` all ran again.

**Other edits** (`exit/case_more.sh`). Reordering two independent steps and
renaming a binder kept the commits before the change; removing step three kept
two; a failed step three plus an inserted step needed one resume; a step
killed in flight and then renamed had its pending start retired.

**Existing tests against the prototype.** The 112
`tests/test_workflow_evaluated_*.py` modules with
`test_cli_recovery_messages.py`, `test_first_hour_e2e.py` and
`test_resume_command.py`: 2,884 passed and 7 failed; the 7 pass on the
unmodified tree. Every kill, recovery, invalidate and parallel module passed,
including the closure-mutation kill cells. The broad sample was not run.

- Two pin the refusal 3a removes: `test_resume_preflights_failed_attempt_baseline_before_tail_repair`
  and `test_failed_step_script_edit_refusal_names_the_file_and_a_run_command_that_works`.
- Four in `tests/test_workflow_evaluated_resume.py` pin preflight order: two
  cases of `test_preflight_refusals_preserve_all_evidence` ("memo was read
  before preflight finished", which is check 1) and two of
  `test_program_comparison_precedes_invalid_file_inputs_and_artifact` (the
  prototype loaded the stored artifact early; an implementation need not).
- `test_terminal_helper_captures_three_files_once_without_source_or_preparation`:
  the prototype's lineage lookup re-read the run root from a loader that works
  on captured bytes.

## 6. Cost and order

| Item | 3a | 3b |
| --- | --- | --- |
| Production code | about 60 lines: `runtime.py`, `effect_inputs.py`, `memo_reducer.py`, the `resume` flag, `cli/recovery.py` | about 500 to 700 lines: one new module (plan, refusals, publication); `memo_reducer.py` (record, per-program site tables); `authority.py` (lineage in both loaders, pins, recipe); `cli/commands/evaluated.py`; a Python resume entry; `providers.py`; `views.py` and `report`; `cli/recovery.py` |
| Journal | one optional field on `failed` | one record kind, `rebased`; one program artifact per accepted edit |
| New refusal codes | none | none required: `resume_program_changed` remains the refusal without acceptance, and the cut reuses the `invalidate_*` codes |
| Contract text | design §7.1, C4, §8.1, §8.5, one §17 row; `specs/cli.md` three diagnostic rows, the flag, preflight step 10; `specs/state.md` | design §3, §7.1, C7, §8.3 to §8.5, §17; `specs/cli.md` preflight steps 7 to 10 and diagnostics; `specs/state.md` records and run root; `specs/versioning.md` (older builds cannot read a rebased run) |
| Tests | about 10 | about 40: the exit cases, each edit class of §2 on both surfaces, four crash windows around the record, interleaved parallel commits, each coordinator class, host input, a lineage of three programs, readers |
| Effort | 1 week with its design text | design 1 to 2 weeks, build 3 to 4 weeks |

**What must land first.** For 3b, the `declaration` fix with decision 4;
without it 3b reuses commands but few providers, and provider cost is what
H-G3 measures. For 3b's tests, the open parallel-map items of roadmap Phase 2
(public kill and resume) as the baseline; the design does not depend on them.
Stable names are not required; if adopted, adopt before 3b's Python fixtures
are written. Token metering (Phase 2) serves the measurement; wall time is a
fallback.

**3a can ship before 3b.** It touches the retry check only, needs no lineage
or identity work, and composes with 3b (the mixed case in §5 used both).

## 7. Measuring H-G3

**What edit histories exist.** Fewer than the roadmap assumes. Git history of
sources on admitted targets is short: `workflows/examples/design_review_execute_agents.orc`
has 6 revisions, `experiments/compare/studies/prr_direct_orc/direct.orc` and
`experiments/orc_repl_feature/repl_feature.orc` 5,
`experiments/mlevolve_pair/search_compact.orc` and
`workflows/library/verified_iteration_drain/drain.orc` 4. The longest history
(21 revisions) is on a retired target. Git also holds commits, not the edits
made between two runs. The snapshot under `experiments/thread_m/inputs/` has
135 journals (133 scanned: 228 provider commits, about 50 hours of wall time,
no `invalidated` record) with no header or program beside any of them. They
give cost weights, not replayable runs.

**Computing the reuse share without provider calls.** For two consecutive
versions of a workflow:

1. Get a journal for the first version: a retained run root with its header
   and program, or a run of that version with stand-in providers.
2. Run the read-only planning step of §3 with the second version against it;
   it returns the kept and cancelled commits, or a refusal.
3. Weight each provider commit by recorded tokens once Phase 2 records them,
   else by wall time (`committed.time` minus `started.time`), else count calls.
4. Report per edit the cost kept over the cost committed and any refusal,
   beside whole-run restart (0) and an upper bound (commits whose identity and
   input are unchanged regardless of order). For "soundly", compare resumed
   command-only and stand-in runs with a fresh run in a clean clone.

To get real edits, record them where they occur: when `resume` finds a changed
program, save both program digests and the fresh artifact under the
workspace's `.orchestrate/`, outside the run root. The consumer thread then
produces the history git does not hold.

## Proposed contract changes

Against [evaluated execution](workflow_lisp_evaluated_execution.md); "Before"
quotes the current text.

**§8.1, retry baseline (3a).** Before: "Changed, missing or unreadable
evidence stops resume with `effect_input_diverged` before another `started` or
launch. Restoring the original bytes/targets permits the ordinary next-attempt
rule, still subject to `must_not_repeat`. No override or additional approval
surface is introduced. An invalidation may cancel committed results, but
cannot forgive a newer uncommitted attempt's closure mismatch."
After: "Missing or unreadable evidence stops resume with
`effect_input_diverged` before another `started` or launch. Changed evidence
stops it the same way unless the change is accepted: either the latest attempt
has a `failed` record whose `closure` is `unchanged`, which shows the attempt
did not write its own closure, or the author accepts the change on the command
line. An accepted change permits the ordinary next-attempt rule, still subject
to `must_not_repeat`; the new attempt's `started` record holds the new
evidence, and earlier attempts remain evidence under their own. Restoring the
original bytes/targets always permits it. An invalidation may cancel committed
results, but does not accept a newer uncommitted attempt's closure change."

**§7.3 C4 (3a).** Before: "Before retrying an uncommitted attempt, compare the
current implementation-file evidence with its `started` evidence and refuse
any change (§8.1), even if no failure record survived." After: "Rehash also
when a started attempt fails, and record in its `failed` record whether the
declared files were unchanged. Before retrying an uncommitted attempt, compare
the current implementation-file evidence with its `started` evidence and
refuse a change that §8.1 does not accept; a missing failure record never
counts as acceptance."

**§8.5 (3a).** Before: "restore its `started` evidence under C4". After:
"resume accepts the change under §8.1 or the author restores its `started`
evidence".

**§7.3 C7 (3b).** Before: "a fresh build is compared with the header, and
resume is refused with `resume_program_changed` before any memo record is
read." After: "a fresh build is compared with the run's current program
(§8.4), and resume is refused with `resume_program_changed` unless the author
accepts the edit under C10."

**§8.4 (3b).** Before: "A mismatch refuses with `resume_program_changed` or
`resume_inputs_changed` before reading any memo record or mutating run
evidence." After: "The run's current program is the header's, or the one named
by the last `rebased` record; no other memo record is read for this
comparison. A different input digest refuses with `resume_inputs_changed`. A
different program refuses with `resume_program_changed`, printing what C10
would keep and run again, unless the author accepts the edit. Neither refusal
mutates run evidence."

**§8.5, new rule C10 (3b).** "Resume under an accepted edit replays the edited
program against the active journal with stored values. A commit is reused when
it is reached at its identity in the order relation of resume replay, with
equal `depends_on` and an equal resolved input. The cut is the smallest offset
among active commits not reused and pending starts the edited program does not
reach next. After publishing the edited program's artifact beside the first,
one synchronized `rebased` record names the program digest, the cut or null,
pins for interpreters the edit adds and the rebuild recipe if it changed. It
cancels every active commit and retires every pending start at or after the
cut, as a C8 range does, lifts their retry baselines and reopens the terminal.
Every C8 refusal applies to that range, and a retired pending start of a
`must_not_repeat` effect refuses. Journal records are validated against the
program in force when they were written. The header and the first program are
never replaced."

**Smaller edits.** §7.1 gains the `rebased` record and the `closure` field of
`failed`. §3's goal "Resume never runs an effect that committed a result"
gains "unless an invalidation or an accepted edit cancelled it (C8, C10)". In
§17 the row "Retry after a closure change" gains the author-edit case, and new
rows hold the three exit cases and the crash windows of the `rebased` record.
The provider `declaration` part is defined to exclude source positions.

## Open decisions for the owner

1. **3a acceptance.** Recommended: automatic after a failure that left the
   closure unchanged, explicit for an interrupted attempt. Alternatives:
   always explicit (no journal change, one more command for the commonest
   edit), or keep refusing interrupted attempts.
2. **3b acceptance.** Recommended: always explicit, since a cut discards paid
   results; the refusal prints the plan. Alternative: automatic when the cut
   cancels no commit.
3. **One flag or several.** Recommended: one, `resume --accept-changes`, for
   an interrupted attempt's changed script, an edited program and a changed
   bound file of a committed step (today `invalidate` then `resume`).
4. **Runs in flight when `declaration` changes.** Accept the old digest for
   commits replayed under the program that wrote them, or let those runs
   refuse at their first provider commit.
5. **Python entry.** A `py` form of resume that rebuilds from the Python file,
   or 3b for `.orc` only at first.
6. **A committed human reply at or after the cut.** Ask again, listed in the
   plan (recommended), or refuse as for coordinators.
7. **Workspace leftovers.** Document as the author's risk (recommended), or
   also warn when the workspace is a git tree with changes.
8. **An edited child of an uncommitted run reference.** Recommended: keep
   refusing; out of scope.

## Coordinator rulings, 2026-11-11

The owner's standing instruction is that the coordinator decides everything
except provider budget and records it. These rulings answer the eight
decisions above; each can be reversed before its code lands.

| # | Ruling | Cost if wrong |
| --- | --- | --- |
| 1 | As recommended: automatic after a failure that left the closure unchanged, explicit for an interrupted attempt | An author who wanted to inspect before retrying gets a retry on plain `resume`; the old bytes are still in the attempt's evidence |
| 2 | As recommended: an edited program is always accepted explicitly, and the refusal prints what would be kept and run again | One more flag for edits that cancel nothing |
| 3 | One flag, `resume --accept-changes`. In 3a it covers only an interrupted attempt's changed script; the edited program and a committed step's changed file come with 3b | A user cannot accept one kind of change and refuse another in one command |
| 4 | Direction for the 3b design: a run in flight must not be stranded by the `declaration` fix. Prefer accepting the old digest for commits replayed under the program that wrote them; the design may choose refusal only if it shows that costs more than about 50 lines or a second digest rule in the checker | Two digest rules to keep until old runs age out |
| 5 | `.orc` only at first. A Python form of resume waits for the consumer thread to ask for it | A Python author must edit the generated `.orc` copy or restart |
| 6 | As recommended: ask the human again, and list it in the plan | A reply is requested twice |
| 7 | As recommended: workspace leftovers are the author's risk, stated in the guide | A re-run step reads a file a cancelled later step left (the 102-against-2 case of §4) |
| 8 | As recommended: keep refusing an edited child of an uncommitted run reference | None for the selected scope |

Consequences: the [Phase 2 plan](../plans/2026-11-11-roadmap-phase-2-qualification-metering-names-plan.md)'s
task C3 (callee-derived `.orc` site labels on a new target) is dropped, since
3b does not match effects by name. 3a is planned first and separately; 3b gets
its own design after 3a.

## What this makes harder

- A run can be the product of several programs: its audit trail needs the
  lineage, and `report` must say which program each attempt ran under.
- A build that predates the change cannot read a rebased run, or one whose
  `failed` records carry `closure`.
- Resume reads lineage records before it compares programs, so tests that pin
  "nothing in the memo is read before the program check" change.
- Re-running steps on a workspace that holds their earlier output becomes an
  everyday operation instead of an explicit `invalidate`.
- Reuse follows journal order, so one early edit discards everything after it.
  That pressure leads to 3c, which needs declared reads and writes.
- This is reuse inside one run. A child program on another clone (roadmap
  Phase 6) gets nothing from it.

## Not verified

- Run-reference children, agent turns, phased providers and durable host input
  were read, not run: no probe put a coordinator or a host request at or after
  a cut.
- Whether hygiene ever gives a binding a counter-based lexical name that
  changes a provider's `declaration` without an authored rename. Even fully
  stripped, `declaration` covers operand names, so renaming a pure binding
  that a provider reads re-runs that provider.
- The per-program site tables of check 3: the prototype used a union.
- Effort figures are estimates from the prototype's size and past changes.
