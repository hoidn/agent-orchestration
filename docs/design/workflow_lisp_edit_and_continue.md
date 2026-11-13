# Workflow Lisp Edit And Continue: Resume Under An Edited Program

**What this page is.** The design for part 3b of
[roadmap Phase 3](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-3-edit-and-continue):
a run continues under an edited workflow and keeps the committed results
whose identity and inputs the edit did not change.

**Status.** Proposed revision of [evaluated execution](workflow_lisp_evaluated_execution.md),
accepted by the coordinator on 2026-11-12 as the basis for an implementation plan after two
review rounds. Not implemented: the contract changes only when the plan lands them. It applies rulings 2 to 8 of the
[feasibility spike](workflow_lisp_edit_and_continue_spike.md#coordinator-rulings-2026-11-11)
and the rulings recorded under [Decisions](#decisions).

**What owns the behavior today.** Evaluated execution (§7.3 C7, §8.1, §8.4,
§8.5) and the [CLI contract](../../specs/cli.md) ("Resume preflight
precedence", "Diagnostics"). Until an implementation plan lands this page, a
run resumes only under the program it started with, and
`resume --accept-changes` covers only an unfinished command attempt's changed
files. Follow those documents and the recovery lines the CLI prints.

**Copy safety.** Nothing here is a recipe: the record, file names, token and
printed lines are proposals. Probe scripts are in the session scratch
directory
`/tmp/claude-1000/-home-ollie-Documents-agent-orchestration/1b39a3a8-0e47-42a7-a277-a660e3320ba1/scratchpad/design-3b/`,
which is not durable; [Probes](#probes) lists what each showed.

**Terms.** *Journal:* the run's `memo.jsonl`. *Commit:* a `committed` record
that nothing later cancels. *Pending start:* a `started` record with no
`committed` or `failed` record. *Lineage:* the ordered programs a run has
executed under; the last is the *current program*. *Cut:* the journal offset
from which an accepted plan cancels. *Plan:* what an acceptance would keep,
cancel, ask again and retry. *Plan token:* a digest that names one plan.
*Stand-in:* a local script that plays a provider; no model is called.

## 1. Summary

Replay the edited program against the journal, keep the commits it
reproduces in journal order, and cancel everything from the first one it
does not (§3). One `rebased` record names the edited program and the cut
(§4). Plain `resume` refuses and prints the plan with its token;
`resume --accept-changes=TOKEN` applies exactly that plan, and the bare flag
keeps its present meaning (§5, §6). Every refusal precedes any write. First,
a provider's `declaration` digest stops carrying source positions (§2).

## 2. The `declaration` prerequisite

**Defect.** `resolve_provider_input` (`evaluated/providers.py`) digests its
node after `strip_provenance`, which here removes the position record `@`
from the effect node only. Operand nodes under `inputs` and `policy` keep
`@`: the source file's absolute path, line and column. A comment line above a
provider changes its digest under an edited program.

**New rule.** `declaration` is the digest of the class's **subject** as it
stands after the position stripping that defines the program digest. The
subject is the site's node for a provider and a phased provider, and
`provider_view(node, agent)` (`evaluated/agent_turns.py`) for an agent turn.
That stripping is schema-aware and never touches a key inside literal data.
Probe: the node so stripped has no `@` left and digests like "every `@`
removed at any depth". No other class digests a node with positions:
commands digest argv, contract, closure and file evidence; host requests
digest position-free contracts (probe).

| Edit | Today | New rule |
| --- | --- | --- |
| Comment or blank lines; a step or pure binding inserted on an earlier line | changes | same |
| Keyword arguments reordered (`:effort` before `:model`) | changes | same; the program digest is also the same |
| A binder that `:inputs` reads is renamed, or replaced by a pure alias | changes | changes |
| A literal changes (`:model`); an operand changes shape (`s1` to `(+ s1 0)`) | changes | changes |
| The provider's own label changes | changes | changes; its identity changes too |
| The provider moves into a procedure, its node otherwise unchanged | changes | same; its identity changes, so the step runs again |

A renamed input binder must change the digest, because the name is prompt
text: each input row is rendered as `## Typed Prompt Input: <name>`. A
changed prompt file does not touch `declaration`; it changes the `source:`
and `prompt` parts (C6).

**Hygiene names: a stated limit.** When `:inputs` reads a binder that shadows
another in the same definition, the compiler names it by counter (`%1`), and
an unrelated shadow added earlier shifts it to `%2` (probe). The name is in
the node and in the prompt text, so the provider runs again: sound, since the
prompt did change, but reuse is lost. The names stay (decision 7): the review
found no counter name in any input row of the 178 provider-class sites of the
182 distinct programs retained in the repository.

**Runs in flight (spike ruling 4): the old digest is accepted.** Wherever a
provider-class digest recorded in the journal is compared with a freshly
resolved one, the fresh `declaration` is computed by the rule the recorded
value satisfies:

```text
current = new_rule(subject)
if recorded == current: use current
elif recorded == old_rule(written_subject) and new_rule(written_subject) == current: use recorded
else: use current                       # a real difference; diverges as today
```

`written_subject` is the subject in the program in force when the record was
written (§4); under an unchanged program it is `subject`. The substitution is
made in the parts, before the input digest is taken. New records always use
the new rule. The comparison points are:

1. `_reuse_effect_commit` (`evaluated/effect_inputs.py`): a commit on replay,
   for providers, phased providers and agent turns;
2. `_recovered_attempt` (`evaluated/agent_turn_recovery.py`): a pending agent
   turn recovered at its own ordinal;
3. the kept-pending test of §3 for a coordinator attempt.

Every other check compares two recorded values (a receipt with its row, a
phased proof with its row, a commit with its start) and needs nothing.

Probes, on journals written by the current tree. A provider: all commits
kept with no edit; kept after a comment line (today it is cancelled);
cancelled after its model changes. An Agent Sessions run of four turns: each
recorded digest equals the old rule over `provider_view(node, agent)` and not
over the site node; under the new rule the run refuses at its first turn with
no edit at all; with the rule above it resumes with all six commits reused.
A committed turn cannot be invalidated (K8), so without the rule such a run
is stranded. **Rejected:** refusing runs in flight at their first
provider-class commit. Comparison point 2 and a phased provider were read,
not run (see [Not verified](#not-verified)).

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
evaluated. Exactly these failures there mean "not reusable" and make the
effect the next to run in its thread: the order check, the dependency check,
the value fit and the host payload check. Any other `memo_inconsistent`
stays a refusal. `_Discovery` records a commit as consumed, and a pending
start as reached, before it runs those checks, so the planning pass takes
both back when one fails. Condition 5 is checked afterwards in journal-offset
order and stops at the first difference, as C7's preflight does today.

**The cut can lie earlier than the edit.** Condition 5 rehashes the declared
files of the kept commits in the workspace as it is now. When a later step,
now cancelled, rewrote a file that an earlier commit bound (the normal case
for agent steps), that earlier commit differs and the cut moves to it. The
plan names the commit at the cut and what differed (§6).

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
| Manifest: an unused entry | all | none |
| Prompt file or script of a committed step (program unchanged) | commits before the first effect that binds it | from that effect, by C8 (§6) |
| A step becomes another class at the same identity | commits before it | from it; attempt ordinals continue |

**Parallel map.** The cut is one journal offset, compared with each commit's
offset, as C8's range is (decision 2). Probe, journal order
`pre, [1].f, [1].g, [2].f, [2].g, [0].f, [0].g, post`:

| Edit | Kept | Cancelled |
| --- | --- | --- |
| The step after the map | 7 | `post` |
| Add an item | 7 | `post`; the new item runs |
| The second body step `g` | `pre`, `[1].f` | `[1].g`, `[2].f`, `[2].g`, `[0].f`, `[0].g`, `post` |

The third row cancels `[2].f` and `[0].f`, whose inputs did not change,
because they committed after `[1].g`, which is not reused. For an edit to
body step *j* of a map with *n* items run *k* at a time, the cut keeps at
most about *k* items' first *j*−1 steps, so about 1−*k*/*n* of the map is
lost. The cut is never worse than `invalidate` at the same commit. §7 states
what this rule does not guarantee in a map, and the alternative H-G3 compares.

## 4. The record and the lineage

**Record.** `{"record": "rebased", "program_digest": "sha256:…",
"from_offset": <byte offset or null>, "time": <seconds>}`, exactly these
keys: the edited program's digest and the cut. The digest differs from the
program in force; a record that names the same program is `memo_inconsistent`.

**Artifact.** The edited program is stored in the run root as
`closed_program.<64 hex digits of its digest>.json`. A file of that name that
loads, passes the checker and has that digest is kept as it is and reused.
Its bytes need not equal a fresh build's: the digest ignores positions and
the bytes hold them (probe: one program, with and without a comment line, has
one digest and two byte strings). A file of that name that does not verify is
`memo_inconsistent`. Otherwise the artifact is published without replacing:
temporary file, sync, a link or rename that fails if the name exists, then a
directory sync. `run.json` and `closed_program.json` are never rewritten; the
header's `program_digest`, `workflow_checksum` and recipe describe the first
program. An edit that returns to an earlier program stores it under its
digest name like any other.

**Lineage.** The first program, then the program of each complete `rebased`
record in journal order. Files that no record names are not lineage. Both
loaders in `evaluated/authority.py` resolve it: `RunAuthority.program` is the
current program and a new field holds the earlier ones in order. The
captured-bytes loader reads the header, the first program and the journal as
today, then each named artifact once. A named artifact that is missing or
does not verify is `memo_inconsistent`; nothing is rebuilt from source. So is
a later program that uses an unpinned bare interpreter, or whose parameters
cannot bind the header's `bound_inputs` in checked form: resume binds those
inputs to the program in force, so such a lineage can never continue. The
cost: `report`, the dashboard and the monitor cannot show such a run, and
`invalidate` refuses it. Only a record that no command writes can produce one
(the plan refuses the edit first); if a later change ever allows a new
parameter with a default, this check relaxes together with resume's input
check. Every reader that loads authority verifies each later program once per
read (one parse and digest per program, not per row), so a long-lived reader
never trusts a check made before an artifact changed; a dashboard page that
scans twice pays it twice.

**Every row is read under the program that wrote it.** A row's program is
derived from its position: the number of `rebased` records before it. No row
changes shape. The reducer takes the current program's site table, as today,
and the earlier programs' tables in order.

- It validates each row with the table of the row's program. At a `rebased`
  record it requires that `from_offset` is null or the offset of an active
  commit or pending start, that no coordinator commit lies at or after it,
  and the agent rule of C8; it applies the cut and moves to the next table.
  Every commit and pending start that stays must be a site of the new
  program with the same class. After the last record the table in force is
  the caller's. The record reopens a terminal, completed or failed.
- A record whose table was not supplied is `memo_inconsistent`; so is a
  journal whose records do not end at the caller's table. Nothing is guessed.
- The snapshot keeps the records' offsets and the tables. A class lookup over
  a historical row asks the snapshot for the class at that row. The row's own
  position decides, never the identity's latest row: an identity can change
  class across a record, and a pending agent turn whose identity is a command
  in the next program still falls under the agent rule of C8. Four lookups
  change: `check_invalidation_cut` (`memo_reducer_agents.py`), `_site_class`
  (`agent_guards.py`), `unproven_command_retries` (`attempts.py`) and
  `_effect_rows` (`views.py`).

Probe. Switching one table at each record, as an earlier form of this design
did, cannot read old rows: `invalidate` reaching back past a record after a
rename, and a second edit whose cut precedes the first record, both end in
`memo_inconsistent: identity does not resolve to a checked effect site`.
With each row read under its own program both reduce and the strict replay
passes. A union of tables is also wrong: it answers `memo_inconsistent:
effect class disagrees with the checked site` when a step changes class.

**Call sites.** The tree has 36 reductions: 27 calls of `read_memo` and 9 of
`reduce_memo`. Four of them change, all calls of `reduce_memo`, and the
planner adds a fifth.

- The one inside `read_memo` changes: `read_memo` resolves the earlier tables
  itself from the artifacts beside the journal it reads, each verified to its
  name. Its 27 callers and the 26 derivations of a site table
  (`site_classes(...)`) stay as they are.
- The three direct reductions of captured bytes for a run that can be edited
  (`views.py` twice, `capture.py` once) pass the tables of the authority they
  hold, because they must not read the run root again.
- New: the in-memory pass of §6 reduces the journal as it will be, in
  `rebase.py`, with tables it supplies itself, because the edited program's
  artifact is stored only at the write.
- The five reductions of a child run (`run_ref/evaluated_child.py`,
  `run_ref/confined_recovery.py`) pass one table as today: an edit never
  reaches a child (§5), and a `rebased` record there fails closed.

Not fewer: the captured-bytes callers and the planner cannot go through
`read_memo`. Not more: passing tables through 27 callers adds nothing that
the artifacts do not already fix. `read_memo` runs at every effect start, so
it must not load an artifact twice: a program's table is cached in the
process under its verified digest, of which it is a pure function. The plan
measures this before it builds on it: the time per effect of a run of a few
hundred command steps after one accepted edit, against the same run with no
edit.

**The reduction cache** (`_LAST` in `memo_reducer.py`) compares the caller's
table and a byte prefix and saves the fold without its table. Under a lineage
it compares every table the saved fold has used with the same positions of
the new input, and saves the record offsets with the state. Unchanged, it
would refold after every edit, or continue a fold under tables it was not
made with. `tests/memo_fold_guard.py` changes with it: `FoldGuard.check`
re-reduces a tip with all of the tip's tables, and the start-view guard
passes the authority's earlier tables. For a journal without a record both
do what they do today. The `start_reached` shortcut of
`publish_evaluated_view` is unaffected: a `rebased` record is not a `started`
row, and its own view is replayed in full.

**Write order,** under the run writer lock, after every refusal check: store
the artifact; truncate a torn tail (M3); append and synchronize the record;
publish the view under the new program; evaluate. The record is written only
in resume preflight, so the program in force never changes during an
evaluation.

| Crash | On disk | Next `resume` |
| --- | --- | --- |
| W1, before the artifact has its name, or before the directory sync | Perhaps a temporary file; the name may be absent | As before the attempt: refuses, and prints the plan again |
| W2, artifact durable, no record | A verified artifact no record names | Same. Accepting again reuses the file, also when the source was reformatted since. Restoring the source resumes under the old program. Another edit stores its own artifact |
| W3, a torn `rebased` line | Not a record (M3) | Same as W2; the next writer truncates the line |
| W4, record complete, sync failed or unacknowledged | The record survives or not | Survives: W5. Not: W2. The process stops with exit 2, dispatches nothing, and says that the change may be in force and that `report` lists the run's programs |
| W5, record durable, view stale or acknowledgment lost | Program switched and cut applied | Plain `resume` continues under the edited program. The old token no longer matches. Restoring the old source is now an edit, with its own plan |
| W6, any later point | An ordinary journal under the edited program | §8.3 of evaluated execution, unchanged |

No state has the program switched and the cut not applied: one record does
both. A durable record always has a durable artifact, because the record is
appended after the directory sync.

**Readers without the lock** (`input get`, `report`, the dashboard, the
monitor) can run while an acceptance writes. They can see the old lineage, an
artifact that no record names yet (which they ignore), or the new record. A
reader that captures the journal once and then resolves the artifacts it
names sees one consistent run, since each artifact is durable before its
record. A reader that loaded authority first and reads the journal later can
meet a `rebased` record that its tables do not end at. It then loads the
lineage again, once, and reduces again; if that also fails it reports
`memo_inconsistent` with the reason that the run is being rebased. It never
writes.

**Older builds.** Profile and schema do not change; journals are read forward
only, as for the `closure` field (decision 8). A build without this design
answers `memo_inconsistent` ("record kind is missing or unknown") from
`resume` (exit 2), `invalidate` (exit 2) and `report` (exit 1) and writes
nothing (probe). With the source still edited it refuses
`resume_program_changed` first.

## 5. Refusals that stay

Each is decided before the artifact or the record is written. Without a
matching token the first line is `resume_program_changed` (or
`effect_input_diverged` for an unchanged program), and the recovery lines
give the condition below as the reason no plan can be accepted.

| Condition | Code with `--accept-changes=TOKEN` |
| --- | --- |
| The edited source does not compile, or reaches a confined run-reference site | The compile diagnostics; `refuse_confined_run_ref_sites`, as today |
| The entry workflow's canonical name, the target or the representation differs from the current program's | `resume_program_changed`, naming which; a run keeps its entry and target |
| The bound inputs differ, also when the edit adds, removes or retypes an entry input | `resume_inputs_changed`; no token accepts inputs |
| The edit uses a bare interpreter the header did not pin (decision 1) | `resume_program_changed`, naming it. An edit may stop using a pinned interpreter. A recorded pin that is missing: `resume_interpreter_missing` |
| The recomputed plan is not the plan the token names (decision 9) | The refusal plain `resume` gives now, with what changed and the new plan (§6); `resume_preflight_failed` when nothing needs accepting |
| A committed run reference, agent turn or phased provider call at or after the cut (K8) | `invalidate_coordinator_committed` |
| An agent turn attempt at or after the cut that is pending, dispatched, advanced or of uncertain outcome | `invalidate_agent_session_advanced` |
| A pending run-reference or phased-provider attempt that is not kept (§3); a kept one is recovered by K4 and the phased rules, unchanged | `resume_program_changed`: restore the source and resume, so the attempt settles under the program that started it |
| A confined child with a committed effect whose parent attempt is at or after the cut | The refusal of `guard_confined_invalidation` |
| An uncommitted attempt with a retry baseline, anywhere in the journal, at a site that declares `must_not_repeat` in the program that wrote the attempt or in the edited program (decision 3a) | `lexical_restore_pending_effect_unsafe` |
| A commit in the cancelled range at a site that declares `must_not_repeat` in the program that wrote the commit or in the edited program (decision 3b) | `lexical_restore_pending_effect_unsafe`; the recovery lines print `invalidate RUN_ID 'IDENTITY'` |
| A pure fault in the strict replay under the edited program | That `pure_expr_*` code |
| A header without a rebuild recipe; the other header and root checks | Unchanged (preflight steps 1 to 6) |

- **Interpreter pins.** The header's pins equal the bare interpreters of the
  first program, as today. A later program of the lineage may use only pinned
  interpreters and need not use all of them. Today's check is an equality and
  refuses an edit that removes the only `sh` step (probe).
- **`must_not_repeat`, defined completely.** Today the refusal reads the
  current node when the step is reached. Under an edit a renamed step is a
  new identity, and a manifest that drops the declaration makes the node
  repeatable; in both cases the tree's strict replay passes and would run the
  step again (probe). So both rows above read the journal, the program that
  wrote the row and the edited program. The edited program counts for a
  commit too: an edit that adds the declaration to a committed step and
  changes an earlier one is caught only by that reading (probe). A committed
  such step is never cancelled by a plan,
  for a `rebased` record or for the `invalidated` record of §6. The author's
  route is the explicit command: `invalidate RUN_ID 'IDENTITY'`, then the
  resume, which prints a new plan. Probe: after the tree's `invalidate` the
  step is no longer in the cancelled range and has no retry baseline.
  `_retry_baseline` (`attempts.py`) treats a commit that a cut cancels as it
  treats one a range cancels: the baseline is lifted. Since a cut cancels
  only commits that neither program declares `must_not_repeat`, and the
  strict replay of §6 runs before the write, no `must_not_repeat` refusal can
  occur after the record.
- **Host input (spike ruling 6).** A `request_input` commit at or after the
  cut is cancelled like any commit, the plan lists it under "asked again",
  and the next resume issues a new request with a new ID; the old ID is
  refused as `host_input_stale` (probe, with C8 on the current tree). A
  pending request is kept when its question, contracts and dependencies are
  unchanged; else the cut withdraws it. **Required change:** `_request_id`
  binds the current program's digest, so today a committed reply fails
  validation under any edited program, also one edited after it (probe). The
  ID is checked against the program in force when the request started; the
  probe then keeps the reply. `input answer` and `input cancel` take no flag:
  while the source is edited and not accepted they refuse
  `resume_program_changed`, and the plan says that a pending question cannot
  be answered until the edit is accepted or the source restored.
- **Run-reference children (spike ruling 8).** The flag, the token and the
  edit are never passed to a child run. A child whose own program changed
  refuses under its own header, as today.
- **Python-built runs (spike ruling 5).** `resume` rebuilds the generated
  `.orc` copy the header names. An edit to the `.py` file is not seen and
  nothing refuses; the guide must say so.

## 6. Preflight and the command line

**Form.** `orchestrator resume RUN_ID [--accept-changes[=TOKEN]] …`: one flag
with an optional value (argparse `nargs="?"`; probe).

- `--accept-changes` alone keeps exactly its present meaning: the changed
  declared files of unproven unfinished command attempts (§8.1 of evaluated
  execution). It never accepts an edited program or a cancellation.
- `--accept-changes=TOKEN` accepts the plan that token names, and nothing
  else: the program switch, the cancellations, the questions asked again and
  the unfinished command attempts the plan lists.
- The flag is written after the run id. `resume --accept-changes RUN_ID`,
  which is accepted today, becomes a usage error (exit 2): the parser prints
  `argument --accept-changes: expected a plan token; write the run id before
  --accept-changes` and never takes a run id for a token. Printed commands
  already write the flag last, with `=`.

**Token.** `plan-` and four fields of eight hex digits, each the start of a
SHA-256 over canonical JSON:

1. *journal:* the run id, the journal's complete byte length and the digest
   of its last complete record;
2. *program:* the current program's digest and the fresh program's;
3. *cut:* the record kind to write (`rebased` or `invalidated`) and the cut;
4. *sets:* the cancelled commits and the retired pending starts, as identity
   and attempt in journal order; the requests asked again, with their request
   IDs; the unproven command attempts, each with the digest of its declared
   files as rehashed now when replay reaches it, and with identity and
   attempt alone when it does not.

All four must match. The token is not stored and is not a secret. It is
recomputed under the writer lock and compared at one place, immediately
before the write. A field that differs names what changed, and the refusal
says so before it prints the new plan: the journal has new records; the
program changed again; the cut moved, with the commit now at the cut and
what differed there (a declared file, an input part); the cancelled steps,
the questions, or the unfinished steps or their files changed. An unproven
attempt that replay does not reach cannot be rehashed before it runs: the
acceptance covers its files as they are when it is reached, and the plan
says exactly that. Probe: all fields equal when recomputed; the cut and sets
fields differ after a declared script changed (the plan then cancelled 4
commits, not 2); the program, cut and sets fields after the source was
edited again; the journal field after another process appended a record; the
sets field after an unfinished attempt's script was rewritten.

| Situation | Plain `resume` | `--accept-changes` | `--accept-changes=TOKEN` |
| --- | --- | --- | --- |
| Nothing to accept | Runs | Refused, `resume_preflight_failed`, as today | Refused, `resume_preflight_failed` |
| Only unproven command attempts with changed files | `effect_input_diverged`; prints the bare flag | Accepts them, as today | Refused: the token names no current plan; prints that refusal |
| An edited program | Refuses at step 7 and prints the plan with its token | The same refusal: the bare flag accepts no plan | Accepts when the recomputed plan matches |
| A committed step's changed input, program unchanged | Refuses at step 10, as today, and prints the plan with its token | The same refusal | Accepts when the recomputed plan matches |
| An edit or a changed input, and unproven attempts | Refuses; the plan lists the attempts in a section of their own | The same refusal | Accepts both when it matches |

**Steps.** 1 to 6 of "Resume preflight precedence" are unchanged. Then:

7. Fresh build; compile errors refuse. Decode only the journal's complete
   lines of kind `rebased`: the current program's digest is the last one
   named, else the header's. No artifact is loaded. Equal digest: continue as
   today.
   - *Different, without a token* (plain `resume`, the bare flag, and
     `input answer`): refuse `resume_program_changed` here, as today, before
     inputs, stored programs or any other record is read. The plan is then
     computed for the refusal's text, read-only, by running steps 8 to 10 on
     the fresh program. If one of them fails, the refusal says why no plan
     can be shown, with that step's code and message, and prints no token.
     Its own code and exit status do not change.
   - *Different, with a token:* the fresh program is the candidate; check its
     entry, target, representation and bare interpreters, and go on.

   This scan precedes the journal's validation, so a malformed earlier line
   can yield `resume_program_changed` before step 10 yields
   `memo_inconsistent`. Both refuse without a write, and with a token step 10
   always runs before the write.
8. Fresh inputs against the fresh program; `resume_inputs_changed` against the
   header's digest.
9. Stored authority: every program of the lineage, command transport and
   interpreter pins (§5).
10. Memo replay.
    - *Unchanged program, no divergence at a committed effect:* as today.
    - *Unchanged program, a committed effect diverged, no token:* refuse
      `effect_input_diverged`, as today; the plan is printed with it.
    - *With a token:* compute the plan. For a candidate program it is §3's.
      For an unchanged program the cut is the first diverged commit and the
      record is the `invalidated` range that `invalidate` would write. Check
      §5 on the plan. Reduce the journal in memory as it will be after the
      record and run today's strict replay on it, under the program that will
      be current; that pass includes the retry-baseline rule for unfinished
      commands. Then the single gate: the token must equal the plan's, else
      refuse as the table above says, naming what changed.
    - Last, the not-needed refusal of the table above.
11. Write (§4, or the `invalidated` record), log `[changes_accepted]` with the
    token and the plan, then evaluate.

Nothing but step 10's gate stands between a request and the write, and the
bare flag never reaches it with a plan.

**The plan** follows the refusal's first line and is logged again on
acceptance. Lists stop at 20 lines, then `... and N more`.

```text
[resume_program_changed] current program differs from the run's program
effect sites that differ from the recorded program:
  added   workflow:four::run / x
if accepted, this run continues under the edited program:
  kept      1 committed step: workflow:four::run / s1
  cancelled 3 committed steps, which run again when reached:
    workflow:four::run / s2   (provider cost USD 0.42)
    workflow:four::run / s3
    workflow:four::run / s4
  the cut is at workflow:four::run / s2: the edited program runs x before it
  asked again: none
  unfinished steps retried: none
  runs first: workflow:four::run / x
  files that cancelled steps wrote in the workspace are not rolled back
    orchestrator resume RUN_ID --accept-changes=plan-d4c8d05d-d53925b1-e032a8fe-1831ac40
```

Cost is the cancelled attempts' `usage.json`, priced as `report` prices it,
where metered. The "unfinished steps" section lists every unproven command
attempt the acceptance covers, with the reason line the present refusal
gives. One that replay reaches is listed "with its files as they are now";
one it does not reach, such as a start the cut retires, "with its files as
they are when it is reached". The lines for restoring the source and for a
new run follow as today. When §5 refuses, its code and reason replace the
plan and no token is printed. The `effect_input_diverged` refusal for a
committed step prints the same plan and token beside `invalidate`.

**Idempotence.** After acceptance the fresh build equals the current program:
plain `resume` continues or returns the recorded terminal with no write, and
the token no longer names a plan. Accepting twice never writes two records.

## 7. Soundness and its limits

**Protected invariant: replay equivalence.** After an accepted plan the active
journal is one that an uninterrupted run of the edited program could have
produced, with reused effects returning their recorded results. It holds
because the strict replay of §8.4 passes on the journal as it will be: every
active commit is reached at its identity, in order, with equal dependencies
and equal resolved input; every pending start is the next effect of its
thread; nothing else is active. The planner is not trusted for this; the
unchanged strict check is. `plan_probe.py` ran that check, from the current
tree, on its 20 edits (§3), and it passed each time.

**What the prefix guarantees.** Kept commits are downward closed: an effect P′
evaluates before a kept one is itself kept, and it lies earlier in the
journal. So **every kept commit was committed before any cancelled commit
was**. In serial code a kept effect's attempt also ended before any cancelled
effect started, so it cannot have read a cancelled effect's files. The
exception is a process that outlives its attempt, which C4 and C5 already
place outside the promise.

**Not covered.**

- **A parallel map's attempts in flight.** A kept commit can have been made
  while a now-cancelled sibling was running, and can have read its files. In
  the probe's fixture item `a`'s `f` is slow: it starts first and commits
  after every step of the other two items. An edit to that step alone cuts
  at its commit and keeps the four commits of the other items, all made
  while the old step was running (review probe). An uninterrupted run of the
  edited program would have run the new step beside them. `invalidate` has
  this property today. The alternative rule moves the cut back to the
  earliest `started` offset of a cancelled attempt, repeated until stable:
  then every kept commit was committed before any cancelled attempt started.
  It costs nothing in serial code. In the fixture it costs one more commit
  for the edit to `g` of §3 and all four sibling commits for the edit to item
  `a`'s `f`. It is not chosen (decision 2); H-G3 compares the two.
- **Workspace files of cancelled effects.** A step that runs again sees files
  a cancelled later step left, and repeats its own writes (the spike's case:
  102 after the edit, 2 from a fresh run). This is `invalidate`'s limit made
  routine. It is the author's risk (spike ruling 7), stated in the printed
  plan and the guide. For agent steps it is the normal case.
- **Undeclared reads** (C5): environment, clock, network, files opened by
  computed name, the model behind a provider id. Such an effect may be reused
  with a result a fresh run would not give, as today.

**Why 3c stays out.** Keeping a commit that follows a cancelled one needs to
know what it read. `depends_on` records values only, and a file dependence
leaves no trace (the handoff fixture of §17); the spike's value-only rule
mixed old and new results. Per-item reuse in a parallel map is the same
question.

## 8. Readers, metering and code shape

- **View.** When the journal has a `rebased` record, the view gains `programs`
  (per lineage program: digest, the record's time or the header's
  `started_at`, the cut) and each row gains `program`, the index of the
  program in force when its latest attempt started. A row whose attempts are
  partly provider-class and partly not (its identity changed class across a
  record) also gains `metered_attempts`, the ordinals of its provider-class
  attempts, which `report` meters instead of every attempt; without it a step
  that became a command would drop its cancelled provider cost from `report`.
  Without such a record none of these keys exists, so views of existing runs
  are byte-identical. Rows stay
  for identities the current program no longer has. A commit a cut covers and
  a start a cut retired show `invalidated`.
- **`report` and the dashboard** print the program list and each row's
  program. Cost totals sum every attempt of every row, and the spend cap sums
  every attempt directory under the run root (`spent` in
  `providers/usage.py`), so cancelled attempts stay counted and an edit
  refunds nothing.
- **`invalidate`** works on a run with several programs: C8 is about offsets
  and may reach back past a `rebased` record (probe, §4). It never changes
  the program.
- **The REPL and the recovery text** (`_stored_context` in
  `cli/commands/evaluated.py`) read the current program through the loader,
  not `closed_program.json` against the header's digest.
- **Code shape.** Planning, the refusals of §5, the token and the write live
  in one new module, `evaluated/rebase.py`. The `rebased` handler, the
  per-row class and the cache key live beside the reducer in a new
  `memo_reducer_lineage.py`, as the agent rules do, because `memo_reducer.py`
  is near the module limit. Functions already over the complexity limit get
  no new branch: the write happens before `execute_pure_resume` is called;
  `host_input._settle` gets the lineage from the loader; `_request_id` takes
  the writing program's digest as an argument; `_Reducer.started` and
  `committed` keep calling `site_class`; the `program` key is set in
  `_effect_rows`; `_retry_baseline`'s range test becomes one helper that also
  knows a cut; `checked_resume_prefix` takes an optional snapshot for the
  in-memory pass.

## 9. Evidence, exit test and regression baseline

Case table in the style of evaluated execution §17; each row is measured
through the public `run` and `resume` entries with stand-in scripts.

| Requirement | Measure |
| --- | --- |
| Insert before step two (exit case b) | A completed four-step run; insert an effect before step two. Plain `resume` exits 2 with `resume_program_changed`, prints the plan and its token and changes no byte. The printed command exits 0; started are the new step and steps two to four at attempt 2; step one was dispatched once. One `rebased` record and a second artifact. A second `resume` exits 0 with no write; the same token is refused |
| A file dependence under an edit (exit case c) | `a` writes a file that `b` reads by name; edit `a`'s argument and accept. The result equals a fresh run of the edited program in a clean clone; `a`, `b` and `c` ran again |
| Each edit kind | Every row of §3's tables: the kept and cancelled sets, and for command-only fixtures the final value against a fresh run in a clean clone. No kept commit has a cancelled one before it in the journal |
| Where an edit refuses | An edited program without a token refuses `resume_program_changed` before inputs, stored programs or other records are read, also when the stored artifact is corrupt or the input file is missing; the refusal then says why no plan is shown. With a token those states refuse with their own codes |
| The printed plan is the accepted plan | After the refusal, change a declared script so that the cut moves, edit the source again, append a record from another process, or rewrite an unfinished step's script: the old token is refused before any write, and the refusal names what changed and prints the new plan. The bare flag never accepts an edited program or a cancellation, with or without an unproven attempt |
| Positions | A comment line above a provider, accepted: the provider is not dispatched |
| Runs in flight | A journal recorded before the `declaration` change with a committed provider, a committed agent turn and a committed phased provider resumes with no edit and dispatches nothing |
| Record durability | Kill at W1 to W5 of §4: each recovered run is entirely under the old program, or entirely under the new one with the cut applied; nothing is dispatched before the record is durable. An artifact left at W2 is reused after the source is reformatted |
| Lineage | Three accepted edits, one returning to the first program: `report`, the dashboard, `invalidate` and a completed resume read the run; a deleted or altered artifact is `memo_inconsistent` |
| Old rows under a later program | After an edit that renames a step: `invalidate` of a commit that lies before the record succeeds and the run resumes; a second edit whose cut lies before the first record is accepted |
| A class change across a record | A pending agent turn under one program whose identity is a command in the next: a later cut or `invalidate` over that attempt refuses `invalidate_agent_session_advanced`. Each row is classified by the program that wrote it |
| A reader without the lock | `input get`, `report` and the dashboard, run while an acceptance writes: each returns the old run or the new one, or reports that the run is being rebased; none writes |
| The flag's position | `resume --accept-changes RUN_ID` is a usage error (exit 2) that names the fix; every printed command parses |
| Interpreters | An edit that removes the only step of a pinned interpreter is accepted and the run stays readable; one that adds a bare interpreter refuses |
| Refusals | Each row of §5, with a token and without: its code, exit 2, run tree bytes unchanged |
| `must_not_repeat` | A committed such step at or after the cut refuses; after `invalidate` of that step the new plan is accepted and the step runs once more. An edit that adds the declaration to a committed step and changes an earlier step refuses the same way. An uncommitted attempt of such a step refuses after a rename and after the declaration is dropped. No refusal follows a durable record |
| Host input | An edit after a committed reply keeps it; an edit before it asks again, lists it in the plan and refuses the old request ID |
| One command | An edit together with a failed step's fixed script: one resume with the token. A committed step's changed prompt file: one resume, and the journal that `invalidate` then `resume` writes |
| Kills under an edited program | The kill suite's windows on a run that has a `rebased` record: the final value of the uninterrupted edited run, and no kept commit dispatched twice |
| An older build | A journal fixture with a `rebased` record, reduced without that record kind: `memo_inconsistent`, no write |

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
files in the same order. Every test of the bare flag passes unchanged.

**Change.**

- `tests/memo_fold_guard.py`, the guard those suites run under: it re-reduces
  with all of a fold's tables (§4). Its checks on journals without a record
  do not change.
- `tests/test_workflow_evaluated_resume.py`, both edited-program tests keep
  their code, exit status and unchanged-bytes assertions, because without a
  token the refusal is still decided at step 7.
  `test_program_comparison_precedes_invalid_file_inputs_and_artifact` passes
  as written: its missing input file stops the plan's step 8, before any
  stored program is loaded, and the refusal says why no plan is shown.
  `test_preflight_refusals_preserve_all_evidence` (case `program`) forbids
  `load_run_authority` for the whole call; the plan loads the stored
  programs after the decision, finds the corrupt artifact and says so. Its
  guard is restated to end at the decision.
- Tests that unpack or compare the exact commands a refusal prints; each
  refusal gains the token command. In `tests/test_cli_recovery_messages.py`:
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
  attempt directories, the effects that run first, the requests asked again,
  the token) or the refusal. `resume` without a token is its command-line
  form and writes nothing; no command is added.
- **Per edit,** for two consecutive versions of a workflow: get a journal for
  the first (a retained run root, or a run with stand-ins), plan the second
  against it, and weight each provider commit by recorded tokens
  (`usage.json`), else wall time, else count. Plan against the run's own
  workspace, not a clean clone: leftovers can move the cut earlier (§3), and
  a clean clone would overstate reuse. Report the cost kept over the cost
  committed, the cost cancelled and any refusal with its code, beside
  whole-run restart (0), the start-offset cut of §7, and an upper bound:
  commits whose identity and input are unchanged regardless of order. The gap
  to that bound is what the prefix rule and the parallel rule cost. For
  command-only and stand-in runs, also compare the resumed result with a
  fresh run in a clean clone.
- **Real edits.** An accepted edit is recorded by the lineage itself: both
  artifacts and the journal stay in the run root. Recording edits that were
  not accepted is outside this design (decision 5).

## Proposed contract changes

"Before" quotes the current text; "+" means the current text stays and the
quoted text follows it. Rows without a document name are evaluated execution.

| Where | Before | After |
| --- | --- | --- |
| §3, goals | "Resume never runs an effect that committed a result." | "Resume never runs an effect that committed a result, unless an invalidation or an accepted plan cancelled that result (C8, C10)." |
| §7.1 M4 | "that no later `invalidated` range covers (C8)" | "that no later `invalidated` range or `rebased` cut covers (C8, C10)" |
| §7.1, record table | (new row) | "`rebased`. Written: once per accepted edit, by resume preflight, after the edited program's artifact is durable (C10). Content: `program_digest`, `from_offset` (the cut, or null), time" |
| §7.1, terminals | "A terminal is reopened by `invalidated`, or, after a failed terminal, the next `started` record." | "A terminal is reopened by `invalidated` or `rebased`, or, after a failed terminal, the next `started` record." |
| §7.2 | (added) | "A provider-class effect's `declaration` part is the digest of its checked node (for an agent turn, of that node seen as a provider node) without source positions. A recorded value written under the earlier rule is compared under that rule." |
| §7.3 C3 | "The run header records its resolved path and digest." | + "These pins are the bare interpreters of the run's first program. A later program of the run (C10) may use only pinned interpreters and need not use all of them." |
| §7.3 C4 | "A resume that finds a committed effect's declared file changed also refuses (C7)." | "A resume that finds a committed effect's declared file changed also refuses (C7), unless the author accepts the printed plan (C10)." |
| §7.3 C7 | "a fresh build is compared with the header, and resume is refused with `resume_program_changed` before any memo record is read." | "a fresh build is compared with the run's current program (§8.4), and resume is refused with `resume_program_changed` unless the author accepts the printed plan (C10)." |
| §7.3 C7 | "refuses at the first divergence with `effect_input_diverged`, before any launch or reconciliation (§8.4)" | + "; an accepted plan instead cancels from that commit as C8 does (C10)" |
| §8.1, table | "Stop with `effect_input_diverged`, located at the site, showing both digests, which parts of the input differ and which files" | + "; in resume preflight the refusal prints the plan, and an accepted plan cancels from that commit (C10)" |
| §8.1, table | "An `invalidated` range covers the last commit" | "An `invalidated` range or a `rebased` cut covers the last commit" |
| §8.1, the flag | "including a pending start an invalidation retired." | "including a pending start an invalidation or a cut retired. With a plan token (`--accept-changes=TOKEN`) the flag also accepts the plan that token names, and nothing else (C10); without one it accepts no edited program and no cancellation." |
| §8.1, last sentence | "A start that did commit and was later invalidated does not pin that explicitly authorized re-execution to old bytes." | "A start that did commit and was later invalidated, or cancelled by a cut, does not pin that explicitly authorized re-execution to old bytes." |
| §8.3 | "Because evaluation is a function of the program, the inputs and the committed results" | "Because evaluation is a function of the run's current program, the inputs and the committed results" |
| §8.4, comparison | "Compare the fresh program digest first; only after program equality read the requested input file, apply its explicit overrides, bind against that fresh program and compare the input digest. A mismatch refuses with `resume_program_changed` or `resume_inputs_changed` before reading any memo record or mutating run evidence." | "The run's current program is the header's, or the one named by the last `rebased` record; no other memo record is read for this comparison. A different program refuses with `resume_program_changed`, printing the plan C10 computes and its token, unless the author passes that token. Then read the requested input file, apply its explicit overrides, bind against the fresh program and compare the input digest with the header's; a difference refuses with `resume_inputs_changed`, with or without a token. Neither refusal mutates run evidence." |
| §8.4, stored program | "Then validate the stored artifact's checked form and header digest; execute that stored artifact after equality is established." | "Then validate every stored program of the lineage, the first against the header digest and each later one against the record that names it; execute the stored current program." |
| §8.4, replay | "An active later commit that replay cannot reach is inconsistent, not permission to launch past it." | + "Under a candidate program it is in the plan's cancelled range (C10)." |
| §8.4, one interpreter | "This preflight and evaluation share one interpreter; they are not separate resume planners." | + "Planning an accepted change (C10) uses that interpreter and those checks to find the cut; the strict replay then runs unchanged on the journal as it will be." |
| §8.4, publication | "Never replace the header or program after journal activity begins." | + "An accepted edit adds a program artifact beside them (C10)." |
| §8.5 | "For a committed result, the continuation is C8." | "For a committed result, the continuation is C8, by `invalidate` or by accepting the plan resume prints." |
| §9.5 | "run/header/program/effect/ordinal-bound ID" | + "The program is the one in force when the request started; a later program of the lineage checks the ID against that one." |
| §10 V1 | "A view is derived from the memo and the program." | "A view is derived from the memo and the run's programs: each row is read under the program in force when it was written, and the run's position comes from the current program." |
| §10 V5 | "`invalidated` for every commit covered by a range record (C8)" | "`invalidated` for every commit a range record or a cut covers and every start one retired (C8, C10)" |
| §11 | "Resume reuses each item's committed prefix and executes only missing effects." | + "A cut (C10), like an invalidation, is a whole journal suffix and does not keep a sibling item's later commits." |
| §12, codes | "At resume, before any record is read (§8.4, C3)" | "At resume, before any record other than `rebased` is read (§8.4, C3); `resume_program_changed` also when a plan cannot be accepted or its token does not match (C10)" |
| §12, codes | "an invalid range anchor/suffix (C8), or memo/terminal checks failing (V3)" | "an invalid range anchor/suffix (C8), an invalid `rebased` record or one whose program artifact is missing or does not verify (C10), or memo/terminal checks failing (V3)" |
| §12, codes | "An uncommitted attempt of a `must_not_repeat` boundary (§8.1); the present code, kept" | + "; also a plan that would run a `must_not_repeat` step again (C10)" |
| §12, codes | "The explicit continuation (C8)" | + "; `invalidate_coordinator_committed` also a plan whose cancelled range holds a committed coordinator (C10)" |
| §12, codes | (new row) | "`changes_accepted`. A diagnostic at resume, once the record of an accepted plan is durable (C10)" |
| §17 | (new rows) | The rows of §9 above |
| `specs/cli.md`, synopsis | "[--accept-changes]" | "[--accept-changes[=TOKEN]]" |
| `specs/cli.md`, the flag | "accepts, for this invocation, the changed declared files of every unfinished command attempt that no clean failure covers (step 10 below); it is refused when there is none." | + "`--accept-changes=TOKEN` accepts the plan that token names: an edited program, the commits it cancels, the questions asked again and the unfinished command attempts it lists (steps 7 and 10). It is refused when the recomputed plan is another one. The bare flag accepts no edited program and no cancellation. The flag is written after `RUN_ID`: `resume --accept-changes RUN_ID` is a usage error (exit `2`) that prints `expected a plan token; write the run id before --accept-changes`." |
| `specs/cli.md`, step 7 | "compile errors refuse; `resume_program_changed` when the fresh digest differs." | "compile errors refuse. The run's current program is the header's, or the one named by the journal's last `rebased` record, the only records read here. `resume_program_changed` when the fresh digest differs and no plan token is given; the plan is then computed read-only and printed with the refusal, or the reason no plan can be shown. With `--accept-changes=TOKEN` the fresh program is the candidate of step 10; `resume_program_changed` when its entry, target, representation or bare interpreters do not fit the run." |
| `specs/cli.md`, step 9 | "Stored authority: the artifact's checked form and header digest" | "Stored authority: the checked form of every program of the lineage, the first against the header digest and each later one against the `rebased` record that names it (a missing or unverified artifact is `memo_inconsistent`)" |
| `specs/cli.md`, step 9 | "and interpreter pins (`resume_interpreter_missing`;" | "and interpreter pins (equal to the first program's bare interpreters, a superset of every later program's; `resume_interpreter_missing`;" |
| `specs/cli.md`, step 10 | "Memo replay: reduce the journal (`memo_inconsistent`), replay the active committed prefix in journal order re-resolving every input" | "Memo replay: reduce the journal (`memo_inconsistent`). With `--accept-changes=TOKEN`, for a candidate program or a divergence at a committed effect: compute the plan (rule C10) and its refusals, check it by this step's replay over the journal as it will be, and compare its token; a token that names another plan refuses, with what changed and the new plan. Without a token a divergence at a committed effect refuses `effect_input_diverged` as today, and the plan is printed with it. Otherwise replay the active committed prefix in journal order re-resolving every input" |
| `specs/cli.md`, step 11 | "Only then is a torn tail repaired (a failure there is still a refusal, exit `2`) and evaluation continued." | "Only then is an accepted plan written (the program artifact, a torn-tail repair, then the `rebased` or `invalidated` record) or a torn tail repaired, and evaluation continued. A failure there still exits `2`; after the artifact is stored the message says that the change may be in force." |
| `specs/cli.md`, Diagnostics, `resume_program_changed` | "`resume` after restoring the source; or a fresh `run`, in which every step runs again" | "`resume --accept-changes=TOKEN` when a plan can be accepted; `resume` after restoring the source; or a fresh `run`, in which every step runs again". The names column adds: "then the plan (kept, cancelled with recorded cost, the commit at the cut and what differed, asked again, unfinished steps retried, what runs first), or the reason no plan can be accepted" |
| `specs/cli.md`, Diagnostics, committed `effect_input_diverged` (both rows) | "`invalidate RUN_ID 'IDENTITY'` then `resume`" | "`resume --accept-changes=TOKEN`, which does both; or `invalidate RUN_ID 'IDENTITY'` then `resume`" |
| `specs/cli.md`, Diagnostics, `resume_preflight_failed` | "`--accept-changes` with no unfinished command attempt to accept (last in step 10)" | + ", or with a token when nothing needs accepting" |
| `specs/cli.md`, Diagnostics, raiser of `resume_program_changed` | "`resume` fresh build and inputs" | + "; `resume_program_changed` also from `resume --accept-changes=TOKEN` whose plan changed or cannot be accepted" |
| `specs/cli.md`, Diagnostics, raiser of `lexical_restore_pending_effect_unsafe` | "`resume` at an uncommitted `must_not_repeat` command" | + "; `resume` whose plan would run a `must_not_repeat` step again (exit 2)" |
| `specs/cli.md`, Diagnostics, recovery lines of `lexical_restore_pending_effect_unsafe` | "the step that must not repeat, and that a new run performs it again, so whether the interrupted attempt took effect should be checked first" | + "; for a committed step that a plan would cancel: the step, and `invalidate RUN_ID 'IDENTITY'` as the explicit way to let it run again" |
| `specs/cli.md`, Diagnostics, raiser of `invalidate_coordinator_committed` | "`invalidate`" | "`invalidate`; `resume` whose plan's cancelled range holds a committed coordinator" |
| `specs/cli.md`, Diagnostics, raiser of `invalidate_agent_session_advanced` | "`invalidate` over an agent turn attempt whose native session advanced or may have advanced" | + "; `resume` whose plan's cancelled range holds such an attempt" |
| `specs/cli.md`, Diagnostics, codes | (new row) | "`changes_accepted`. Raised by: `resume --accept-changes=TOKEN`, once its record is durable. Exit: diagnostic. Effect: logged with the token, followed by the plan" |
| `specs/state.md`, run root | "authority for the program." | "authority for the run's first program; never replaced." New row: "`closed_program.<digest>.json`. A program the run switched to, named by the 64 hex digits of its digest: authority for the records after the `rebased` record that names it. A file no record names is not authority" |
| `specs/state.md`, memo records | (new row) | "`rebased`. Keys: `program_digest`, `from_offset` (integer or null), `time`. Switches the run to the named program, which differs from the one in force and whose artifact is in the run root; cancels every active commit and retires every pending start at or after `from_offset`; reopens a terminal. Records before it are reduced under the earlier program" |
| `specs/state.md`, view `steps` | "`invalidated` (covered by a range record)" | "`invalidated` (covered by a range record or a cut)". New keys: "`programs`: present only when the journal has a `rebased` record; one `{digest, time, cut}` per program in lineage order" and the row keys "`program`: the index of the program in force when the row's latest attempt started" and "`metered_attempts`: on a row whose attempts are partly provider-class and partly not, the ordinals of its provider-class attempts, which `report` meters instead of `1` to `attempt`" |
| `specs/state.md`, request identity | "`program_digest`, dynamic `identity` and attempt ordinal." | + "`program_digest` is that of the program in force when the request started." |
| `specs/versioning.md`, after the `closure` sentence | (new sentence) | "An accepted edit appends a `rebased` record and adds a program artifact to the run root (State, 'Memo records'). Neither changes `evaluated_execution.v1` or schema `3.0`: a build that predates the record answers `memo_inconsistent` (from `resume`, `invalidate` and `report`) for such a run and writes nothing, and journals without the record reduce as before." |

**New rule C10 (§8.5):** the first three paragraphs of §3 above, then: "After
storing the edited program's artifact beside the first, one synchronized
`rebased` record names the program and the cut. It cancels every active
commit and retires every pending start at or after the cut, as a C8 range
does, and reopens the terminal. Every C8 refusal applies to that range. A
plan never cancels a commit of a step that is `must_not_repeat` under the
program that wrote the commit or under the edited program, and is never
accepted while such a step has an uncommitted attempt. A plan is accepted only by the
token the refusal printed for it, and only when the strict replay of §8.4
passes under the edited program on the journal as it will be. Journal
records are validated against the program in force when they were written.
The header and the first program are never replaced."

## Probes

No model was called: `experiments/thread_m/no_provider` was first on `PATH`
and logged no attempt. The one exception is the suite test that wrote the
Agent Sessions journal: it sets its own closed `PATH` with the suite's fake
CLIs. The planning steps write nothing (asserted by byte comparison in
`plan_probe.py`); three probes also run the tree's `invalidate` or
`input answer` on their own scratch runs. Nothing was written in the
repository. The reviewer reran `plan_probe.py` and `inflight_probe.py`, got
the same tables, and reproduced the lineage, agent-turn and `must_not_repeat`
results with probes of their own.

| Claim | Probe | Result |
| --- | --- | --- |
| What `declaration` digests, and the new rule | `decl_probe.py` (compile only, 13 variants); `round2_probe.py` | The table of §2. The node after the program digest's stripping holds no `@` and digests like "no `@` at any depth" |
| Hygiene counters reach the node and the prompt | `hygiene_probe.py` | `%1` becomes `%2` after an unrelated earlier shadow; unchanged after a later one or a comment |
| A provider run in flight; the rule under an edit | `inflight_probe.py`: a journal written by the current tree, a script named `gemini` as stand-in | The recorded digest equals the old rule. With the rule: all kept with no edit; the provider kept after a comment line; cancelled after a model change |
| An Agent Sessions run in flight, no edit | `agent_probe.py`: the tmp tree of the suite's `test_clean_run_commits_four_turns_on_two_native_sessions`, run with the suite's fake `codex` and `claude` on its closed `PATH` | Recorded digests equal the old rule over `provider_view(node, agent)`, not over the site node. New rule alone, or the rule over the site node: `effect_input_diverged` at the first turn. The rule over the subject: all six commits reused |
| The cut and the strict replay after the record | `plan_probe.py`, 20 edits | §3's tables. The tree's `discover_prefix` and `_validate_discovered_prefix` pass under the edited program each time. A union of tables fails on a class change |
| Old rows under a later program | `round2_probe.py` | `invalidate` before a record after a rename, and a second edit cutting before the first record: `memo_inconsistent` with one table switched per record; both reduce, and the strict replay passes, with each row read under its own program. A record with no table supplied fails closed. The probe's cut rule classifies by an identity's latest row, so a class change across a record is not shown |
| The plan token and the flag's form | `round3_probe.py`; `round2_probe.py` | All four fields are equal when recomputed. After a declared script changes the cut and sets fields differ; after the source is edited again the program, cut and sets fields; after a record is appended the journal field; after an unfinished attempt's script is rewritten the sets field. argparse reads the bare flag, the flag with `=TOKEN`, and rejects `--accept-changes RUN_ID` |
| Interpreter pins; artifact bytes | `round2_probe.py` | Removing the only `sh` step fails today's equality and passes the subset rule. One program with and without a comment line: equal digest, different artifact bytes |
| `must_not_repeat` | `repeat_probe.py`; `round2_probe.py` | An uncommitted attempt: after a rename or a dropped declaration the strict replay passes and would run the step; the designed check names it. A committed step in the cancelled range is found by the check; after the tree's `invalidate` it is not, and its retry baseline is lifted. An edit that adds the declaration to a committed step is caught only when the edited program is read too (`round3_probe.py`) |
| What an older build does | `older_build_probe.sh` | `memo_inconsistent` from `resume`, `report` and `invalidate`; tree bytes unchanged |
| Host replies under an edit; asking again | `host_probe.py`, target 2.40 | Today the reply is lost under any edit. With the ID checked against the writing program it is kept after a later edit, also with shifted lines. A cut at the reply asks again; the old ID is `host_input_stale` |

## What this makes harder

- A run is the product of several programs: every reader needs the lineage,
  and a row's class is a function of where the row lies in the journal.
- "Nothing in the memo is read before the program check" becomes "only
  `rebased` records are".
- Running steps again on a workspace that holds their earlier output becomes
  an everyday operation, not an explicit `invalidate`.
- One early edit discards everything after it, and in a parallel map most of
  the map. That pressure leads to 3c, which needs declared reads and writes.
- The accepting command cannot be typed from memory or scripted ahead: it
  carries a token from the latest refusal, and any change in between means
  reading a new plan.
- One flag has two forms with different reach, the bare form is refused
  whenever a plan is pending, and `resume --accept-changes RUN_ID` stops
  being valid.
- A reader without the lock can meet a record written between its two reads
  and must load the lineage again.
- The old `declaration` rule stays at every comparison point until old runs
  age out, and host request IDs depend on which program wrote the request.
- A committed `must_not_repeat` step blocks every edit that reaches it until
  it is invalidated by hand.
- A refused `resume` costs a replay and a rehash of the kept commits' files,
  to print the plan. Each accepted edit keeps a program artifact.
- A build that predates this cannot read a run that accepted an edit.
- This is reuse inside one run. A child program on another clone (roadmap
  Phase 6) gets nothing from it.

## Decisions

Rulings of the coordinator on the questions this design raised.

| # | Ruling | Reason | Cost if wrong |
| --- | --- | --- | --- |
| 1 | An edit that adds a bare interpreter is refused. One that stops using a pinned interpreter is allowed: later programs are checked as a subset of the pins | C3 resolves interpreters once per run, and about ten readers take pins from the header. Removing a shell step is an ordinary edit | An author who inserts a step with a new interpreter spells it by path (`./tool`, not pinned) or starts a new run |
| 2 | Parallel maps: one whole-suffix cut, by commit offset. The cut at the earliest cancelled start is recorded as the alternative H-G3 measures | Parity with C8; one offset in one record | Kept results that read a cancelled sibling's files while it ran (§7); or reuse lost against the per-item rule of 3c |
| 3a | An uncommitted attempt of a `must_not_repeat` step refuses the edit, judged by the declaration in force when the attempt started | Otherwise the edit itself is the way around the declaration | A run stopped on such a step stays stopped, as today |
| 3b | A committed `must_not_repeat` step at or after the cut refuses. The route is an explicit `invalidate` of that step, then the plan | The plan can change before acceptance, and "must not repeat" should not be overridden by a flag whose main use is something else | Two commands where one would do, for an author who wants the step repeated |
| 4 | A committed step's changed file with an unchanged program: the accepted resume writes the `invalidated` record of C8 | `rebased` then always means a program switch, and an older build can still read the run | Resume writes two record kinds |
| 5 | Recording edits that were not accepted is outside this design. The H-G3 measurement plan decides; if built it is opt-in and outside the run root | Not needed for 3b, and it must never touch run evidence | H-G3 sees only accepted edits until its plan adds a recorder |
| 6 | The plan is printed on every refusal | The author decides from it, and it costs about what resume's replay costs today | A slow refusal on a long journal |
| 7 | Hygiene-generated names stay in provider inputs; the guide states the limit | None found in 178 provider-class sites of 182 retained programs | A provider runs again after an unrelated shadowing edit |
| 8 | No version signal; `specs/versioning.md` gets the sentence above | An older build fails closed, and a schema bump would cut every new run off from older builds | An older build reports `memo_inconsistent` and not "written by a newer build" |
| 9 | A program switch or a cancellation is accepted only with the plan token the refusal printed; a changed plan is refused before any write. The bare flag keeps its present meaning | Between the refusal and the acceptance the source, a declared file or another process can move the cut, and automation that passes the bare flag for a script fix must not accept an edit | One more refusal when anything changed in between. Each of the token's four fields has 32 bits: a change confined to one field passes with a chance of 1 in 2^32 |

## What the implementation plan's first task must prove

Each item is a claim. A test or probe shows it before the code that relies
on it is written; an item that fails returns its question to design. The
order puts first what could send the design back.

1. **The lineage form in the tree.** `read_memo` resolves tables from
   verified artifacts without an import cycle. Reading each row under its own
   program covers every class lookup over historical rows: the four named in
   §4, any other a search finds, and an identity that changes class across a
   record. The `_LAST` key and `tests/memo_fold_guard.py` change as §4 says.
   The planner's own reduction works before the artifact exists. A rebased
   run pays no more per effect than an unedited one after the first read.
2. **The old-digest rule at all three comparison points,** on journals the
   tree writes, resumed with no edit and dispatching nothing: a committed
   provider; a committed agent turn; a pending agent turn through
   `_recovered_attempt`; a committed phased provider; a kept pending
   coordinator attempt.
3. **Coordinators under an edit,** with the suite's stand-ins: a run
   reference, an agent turn and a phased provider, each before the cut (kept
   and reconciled) and at or after it (refused with the C8 codes); a cut at a
   pending start's offset; `guard_confined_invalidation`.
4. **Preflight precedence.** Without a token an edited program refuses at
   step 7 with `resume_program_changed`, as the two resume tests of §9 pin.
   With a token the write has exactly one gate, and the bare flag never
   passes it with a plan.
5. **The token's coverage.** Every input of the planning function is bound by
   a field or derived from something that is, including the files of unproven
   attempts that replay reaches; a mismatch names what changed.
6. **Publication without replacing,** which the tree's atomic write does not
   offer, and then the outcomes of §4 under a kill at each of W1 to W5.
7. **The `must_not_repeat` rows of §5,** with the declaration read from the
   writing program and from the edited one, for committed and uncommitted
   attempts, and no refusal after a durable record.
8. **Readers on runs with several programs:** views, `report`, the dashboard,
   the REPL, `input answer` and `input get`, including a reader without the
   lock racing an acceptance.
9. **Metering and cost.** Cancelled attempts stay counted by the spend cap and
   by `report`, shown with a metered stand-in; the plan's cost on a long
   journal.

## Not verified

What this design states without having run it. Each item is an open
prerequisite; the list above says which claim the plan must show for it.

- **Coordinators under an edit** (item 3). No probe edited a program whose
  journal holds a run reference, agent turn or phased provider. That a
  committed one before the cut is reused, and that the C8 guards work at an
  offset that is not a commit's, was read (`validate_evaluated_run_ref`,
  `validate_turn`, `validate_phased_commit`, `check_invalidation_cut`,
  `guard_confined_invalidation`). Only the host request ID was found to bind
  the parent program's digest.
- **The old-digest rule** at `_recovered_attempt` and for a phased provider
  (item 2): read, not run. That it stays within about ten lines per
  comparison point is an estimate.
- **The lineage form in the tree** (item 1). The probes subclass the reducer
  and classify by an identity's latest row. The import structure, the count
  of call sites and lookups, the cache and fold-guard changes and the cost
  per effect were read and counted, not built or measured.
- **The refusal point** (item 4): that
  `test_program_comparison_precedes_invalid_file_inputs_and_artifact` passes
  as written is reasoned from its fixture.
- **The token** (item 5) was probed for four kinds of change; that its fields
  cover every way a plan can change is argued, not shown.
- **Crash windows W1 to W5** (item 6): argued from M2, M3 and a no-replace
  publication; not fault-injected.
- **Readers** (item 8): views, `report`, the dashboard, the REPL,
  `input answer` and the unlocked race are designed, not prototyped.
- **Metering** (item 9): that cancelled attempts stay counted was read from
  `spent` and `run_usage`; the probes' stand-in provider is unmetered.
- The start-offset cut and parallel interleavings other than the fixture's
  were not run. Python-built runs were read only. For the workspace-leftover
  limit the spike's case is the evidence.
