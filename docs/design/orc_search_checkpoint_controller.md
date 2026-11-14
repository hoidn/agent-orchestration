# ORC Search Checkpoints: Stop At A Stage, Copy Or Fork A Run

**What this page is.** The design for readiness item R1 of
[roadmap Phase 6](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-6-program-evolution):
a search over workflow programs stops a candidate at a named stage, takes
the workspace as it stands there, and continues a child program from it, so
that the child pays for its changed suffix. The design has two parts with
separate acceptance. Part 1 is to be built: a stop at a named effect site,
and a harness procedure that copies a stopped run whole. Part 2 is designed
and deferred: a snapshot store, a fork at an earlier step, the container
route and the pause at a usage limit.

**Status.** Draft; in review, not accepted, not implemented. In the terms of
the [documentation conventions](../documentation_conventions.md#status-labels)
this is `Planned`: a roadmap position exists, the governing design is not
accepted, and implementation must not begin. Nothing here is available in
the checkout. Hypothesis H-E2 of the roadmap is what the design serves; it
makes no claim that H-E2 holds.

**What owns the behavior today.** [Evaluated execution](workflow_lisp_evaluated_execution.md)
(the journal, rules C8 and C10, §8.1 to §8.5), the
[CLI contract](../../specs/cli.md) ("Resume preflight precedence", "Spend
cap"), [State](../../specs/state.md) (the run root, the derived view) and
[Observability](../../specs/observability.md) (the monitor) own `run`,
`resume` and their readers. The
[program-search boundaries](workflow_lisp_program_search_boundaries.md) and
the [structural search driver](orc_structural_search_driver.md) own what a
search may do with a run. The
[mutant generator plan](../plans/2026-11-13-phase-6-mutant-generator-plan.md#task-t3-reuse-figures-5-h)
(task T3) owns the measurement of how much a mutation reuses: steps,
provider calls and, where a run has them, priced tokens. Where this page and
those documents differ, they win until this design is accepted and they are
amended as [§10](#10-contracts-to-amend) lists.

**Copy safety.** Nothing here is a recipe. The flag, the file names, the
fields and the codes are proposals. The probe commands ran on one machine
and are evidence, not examples.

**Terms.** *Journal:* the run's `memo.jsonl`. *Site key:* an effect identity
as the checked site table spells it, with `[*]` in place of each loop or map
index (`machine.site_classes`). *Stage:* a point of a workflow that a search
names, mapped per candidate to site keys ([§3.3](#33-naming-a-stage-across-the-edits-a-search-makes)).
*Stop:* the end of an invocation at a named site, with nothing in flight.
*Cut:* a journal byte offset immediately after a `committed` record at which
no attempt is pending. *Copy:* a whole copy of a stopped run's workspace and
run root. *Fork:* a new run root made from a stored snapshot (Part 2).
*Prefix:* the journal bytes before a cut. *Stand-in:* a local script that
plays a provider; no model is called. A campaign `checkpoint` in the
[cumulative campaigns design](orc_structural_search_cumulative_campaigns.md)
is a different object.

## 1. Conclusion

**Part 1 meets the three R1 gates at stage boundaries with one flag, one
small file and no new module.** Probes with stand-ins showed each
([§14](#14-probes)).

1. `--stop-after SITE` ends an invocation before the next new attempt once
   an effect at that site has committed in it. It writes no journal row and
   no terminal, exits with a code of its own, and `resume` continues. A run
   driven this way dispatched every step once.
2. A requested stop must not read as a crash. Today it does: `report` and
   the dashboard say `interrupted` and the monitor's classifier says
   `CRASHED`. The journal still gets no row. The stopping writer leaves a
   mark, `stop.json`, in the run root; the one function every reader calls
   reads it and reports `stopped` while the journal has the length the mark
   names. `resume`, plan tokens and identities do not read it
   ([§3.4](#34-a-requested-stop-is-not-a-crash)).
3. A copy of the stopped run made with `cp -a` is a copy of the workspace
   and of the journal at that stop. In the probe it equalled the parent in
   content, modes, times, hard links, a named pipe and a nested repository;
   the child program's plan kept the prefix and cancelled nothing; one step
   was dispatched in the copy; the parent then continued.
4. A child's own attempts are those started at or after the journal length
   the harness logged when it copied. Search cost sums own attempts over
   every run root. A copied run yields a tagged estimate of deployed cost
   and is not promotion evidence ([§4.7](#47-the-cost-rule)).

**Part 2 is not built before the first search space.** A fork at an earlier
step saves a fixed number of calls there (90 of the 27-point grid's calls:
42 percent at the measured two-milestone run, 28 at four milestones, 17 at
eight), and copies made at stops serve that tree. The snapshot store, the
fork, the container route and the usage-limit pause are specified so that
they can be built without changing Part 1; [§9](#9-what-brings-part-2-forward)
says what evidence brings them forward.

**Hazards the harness must close, each with a probe:** a copy can write into
its parent's workspace when a committed value holds the parent's absolute
path; a stop is a copy point only when the workspace is quiet; copies share
a run id, which blunts the runtime's liveness check between live siblings.

## 2. What exists today

Rows E1 to E18 were established at `b399076b`, and E19 and E20 on `main` at
`e0a978ad`, each by the command shown, with stand-ins on a closed `PATH`.
The independent review reproduced E7, E8, E9, E13 and E14 at `a9f9e410`.
"Read" marks a fact taken from code or a contract and not run.

| # | Finding | Command | Outcome |
| --- | --- | --- | --- |
| E1 | `resume` of a completed run changes nothing | `orchestrator resume RUN_ID` on a completed run of four command steps | Exit 0, the recorded value, no dispatch, journal bytes unchanged, 0.56 s |
| E2 | Under an edited program `resume` prints a read-only plan | Change the argument of step three; `orchestrator resume RUN_ID` | Exit 2, `resume_program_changed`; kept `s1`, `s2`; cancelled `s3`, `s4`; the cut at `s3`; a `--accept-changes=plan-<token>` command; journal bytes unchanged |
| E3 | The plan is a library call | `rebase.plan_resume(run_root, workspace)` | A `Plan` with `record`, `cut`, `kept`, `cancelled`, `runs_first` and `token`; no lock taken, journal bytes unchanged |
| E4 | A copy of the whole workspace, run root inside, is a working run | `cp -a ws ws2`; `resume` in `ws2` | Unchanged program: exit 0 with the recorded value. Edited program: the same plan and the same token as in the original |
| E5 | Edited-program resume on that copy reuses the prefix | `resume RUN_ID --accept-changes=TOKEN` in `ws2` | One `rebased` record; `s3` and `s4` dispatched once in `ws2`, at attempt 2; `s1` and `s2` not dispatched; the original's journal unchanged |
| E6 | A copy made after the parent finished has the parent's final workspace | Read the file every step appends to, in `ws2` after E5 | `s1 s2 s3 s4 s3 s4`; a fresh run of the edited program gives `s1 s2 s3 s4` |
| E7 | A run root cannot take another name | `cp -a runs/RUN_ID runs/RUN_ID-b`; `resume RUN_ID-b` | Exit 2, `memo_inconsistent`: run id differs from its root |
| E8 | A run root cannot move relative to its workspace | Copy the run root to another directory; `resume RUN_ID --state-dir DIR` from the same workspace | `resume_result_root_changed` |
| E9 | A changed input is refused | Edit the `--input-file` of a completed run; `resume` | `resume_inputs_changed`, naming the input |
| E10 | A committed run reference breaks a copied run | Copy a completed run whose one effect is a run reference; `resume` in the copy | Exit 2, `run_ref_evidence_invalid: child_request_binding_invalid`. The child request records the parent's absolute run root |
| E11 | An Agent Session cannot continue from another directory | Stop a two-turn agent run after turn one; copy the workspace; `resume` the copy, then the original | The copy: `agent_policy_mismatch` (the allocation binds the working directory), no dispatch. The original then runs turn two |
| E12 | Nothing records workspace state per step | List the run root and the keys of every journal row | The run root holds `run.json`, `closed_program.json`, `memo.jsonl`, `state.json`, `run.lock` and `effects/`. A `started` or `committed` row holds digests of the files a command declares and of the input parts. No row or file describes the workspace |
| E13 | An invocation limit already stops a run cleanly | `tests/test_workflow_evaluated_spend_cap.py::test_cap_stops_before_the_next_provider_call_and_a_higher_cap_resumes` | Passes: the capped run stops before its second provider call with no row for the refusal, and the resume completes with two dispatches in all |
| E14 | After a provider call is cut off, a capped resume is refused | Make the second provider call exit 1 with no result line; `resume RUN_ID --max-cost-usd 1` | `spend_cap_unmetered`, cause `attempt_unmetered`. The workspace holds the cut call's partial files |
| E15 | `report` and the cap count every attempt directory under the run root | `report --format json`, and `providers.usage.spent`, on a run root that holds copied attempts | Both include the copied attempts |
| E16 | The run id is a value a program can read, and the header fixes the run root's place | Read: evaluated execution §4.4 (X1, X4) and §8.4; `host_input._request_id` | X1 gives a program its run id; `result_root` ends in the run id; a host request id binds the run id and the header digest |
| E17 | Serial steps run in the workspace directory | The probes' stand-ins logged their working directory. Read: the drafting guide documents a launch directory (`:workspace`) for parallel-map items, and no serial form was found in it | Every serial stand-in ran in the workspace root |
| E18 | The locks belong to a workspace and a run root, and a copy has its own | Start a run with a slow step; during it start a second `run` in the same workspace, and a `run` in a copy of the workspace | Same workspace: `workspace_run_already_active`. The copy: runs to its value while the first is still running |
| E19 | A stop without a terminal reads as a crash in every reader | Stop a run after its first commit through the probe gate; call `load_evaluated_view`, `report`, the dashboard's `RunScanner` and the monitor's `classify_run`; read `state.json` | View, `report` and dashboard: `interrupted`. Monitor: `CRASHED`, reason `evaluated_writer_lock_released_interrupted`. `state.json`: `running` |
| E20 | A run stopped by the spend cap reads the same | `run … --max-cost-usd 0.000005`; `report` | Exit 1, `spend_cap_reached`; `report` says `interrupted` |

What ties a run to its place, taken together: the run root's name is the run
id (E7); the header records where the run root lies relative to the
workspace (E8); a run reference records the parent's absolute run root
(E10); an agent allocation records the working directory (E11); the header
pins each bare interpreter by absolute path (read from `run.json`). The rows
of command and provider steps hold no absolute workspace path of their own:
they were reused at another path (E4, E5). A committed value can hold one
(probe C6). A step's workspace effects live in the workspace directory
itself, and no record says what they were (E6, E12).

## Part 1: built now

Sections 3 to 5. Their acceptance is §5.

## 3. `--stop-after SITE`

### 3.1 The contract

`orchestrator run … --stop-after SITE` and
`orchestrator resume RUN_ID … --stop-after SITE`; the flag repeats.

- **Site.** `SITE` is a site key of the program the invocation executes.
- **Stop.** Where a new attempt would be reserved, the invocation refuses
  with `stop_after_reached` once a `committed` record of an identity whose
  site key is named lies at or after the journal length the invocation found
  at its start. An effect reused from the memo is not stopped, and a retry of
  a failed attempt is a new attempt and runs.
- **What a stop leaves.** No journal row and no terminal; the mark of
  [§3.4](#34-a-requested-stop-is-not-a-crash); the `resume` line. A later
  `resume` continues, with or without the flag.
- **Exit status 3,** which no other outcome uses: 0 is a completed or
  waiting run, 1 a failed run or a stop at the spend cap, 2 a refusal before
  execution. A harness branches on the status and reads the mark; it does
  not parse standard error.
- **Completion.** A run whose last effect is the named site completes with
  its terminal and exits 0. A loop site stops the invocation after the next
  matching commit, so a caller that wants the third round counts.
- The flag is not stored and is checked before the spend cap.

**Place in the code.** One check beside `check_spend_cap`
(`evaluated/spend_cap.py`), called where that one is called
(`runtime.prepare_effect`, `agent_turns.prepare_agent_attempt`) and before a
new host request is issued (`host_input.execute_request`). The stop set
travels as `--max-cost-usd` does, as a field of `RunAuthority` that is not
stored.

### 3.2 Six points fixed here

| Point | Rule | Evidence |
| --- | --- | --- |
| An unknown site | Refused with `stop_after_unknown_site`, exit 2, before any write. `run`: after the build and before `publish_run_authority` (`cli/commands/evaluated.py::run_evaluated_workflow`), so no run root exists and `--dry-run` reports it too. `resume`: after the fresh build of preflight step 7, against the program that will execute (the candidate when a plan token is given), before step 11 stores an artifact or appends a record | The site table is available at both places (read). Probe S4 matched a misspelt site against the table; the probe gate refused at the first effect, not before publication |
| A parallel map | The flag does not refuse it. Items in flight finish and no new item starts, so an invocation ends after up to `:parallel` matching commits, with nothing pending | Probe S7: five items at `:parallel 2`; 2, 4 and 5 commits after three invocations; each item dispatched once |
| A host request | A request after the boundary is not issued: the stop precedes it. `resume` issues it | Probe S6: the journal holds the commit before the request and nothing else; `resume` then appends `started` and `suspended` and prints the `waiting` line, as a run without the flag does |
| A run-reference child | The stop set is not passed to a child run. A child executes whole inside its parent's effect, and a site inside a child is not in the parent's table, so naming one is an unknown site | Read |
| `py run` | Does not take the flag. A Python-built run is continued with `resume`, which takes it; its site keys are those of the generated `.orc` | Decision |
| The exit status | 3, as above | Decision; no command returns 3 today (read) |

### 3.3 Naming a stage across the edits a search makes

A site key is an effect identity: the path of authored labels, call frames
and loop segments to the effect (evaluated execution §6). The flag takes
exact keys. A search names a *stage* by the authored label of its effect,
the last segment of the key, and the harness maps the stage to each
candidate's keys:

- the keys of a stage are the keys of the candidate's site table that end in
  ` / <label>`. There can be several: one definition called from two places
  has two;
- a literal edit (the first search space) changes no key. A structural edit
  (the mutant plan's `graft` and `conversation`) changes activation paths,
  and the label survives where the labelled binding does;
- a candidate with no key for a stage is refused at admission
  (`stage_site_missing`), before spend;
- a generated ordinal is not a name. `#1` moves when an unnamed effect is
  inserted before it (rule I4).

**Required of the seed before it is frozen.** The two typed verdicts of
`milestones.orc` are unnamed effects whose keys end in `#1`: the milestone
review and the acceptance review. Each is bound to a name. Probe L1: with
the bindings `verdict` and `acceptance` the seed compiles on `main` and the
two keys end in ` / verdict` and ` / acceptance`; the file grows from 49
lines to 51. The path before the label still holds generated segments
(`loop:#1[*] / else / #1=…`, from the map form), which is why a stage is
matched by its label and not by a whole key.

### 3.4 A requested stop is not a crash

**Finding (E19).** Every reader derives a run's status from the header, the
program, the journal and whether a writer holds `run.lock`
(`views.load_evaluated_view`). A run stopped on request has no terminal and
no writer, so it reads `interrupted`, and the monitor reports `CRASHED`. A
run stopped by the spend cap reads the same today (E20); a search makes it
the normal state of every candidate. After the invocation exits, the journal of a stopped run,
of a capped run and of a run killed after a commit are the same bytes.

**Decision: no journal row; one mark file.** The invocation that ends on an
invocation limit writes `stop.json` in the run root, atomically, under the
run writer lock:

```json
{"code": "stop_after_reached", "site": "<site key or null>", "identity": "<identity or null>",
 "memo_bytes": 2235, "time": 1794623875.19}
```

- `code` is an open set. This design writes it for `stop_after_reached`,
  `spend_cap_reached` and `spend_cap_unmetered`; `site` and `identity` are
  null for a code that names no site.
- The mark is valid while the journal file has exactly `memo_bytes` bytes.
  Any later record, or a torn tail, makes it stale; nothing removes it.
- `load_evaluated_view` reads it after its capture of the three authority
  files. When the status would be `interrupted` and the mark is valid, the
  view has `status: "stopped"` and `stopped: {code, site, identity}`. A
  missing, unreadable or stale mark changes nothing.
- The mark is evidence of how the last writer left. `resume`, `invalidate`,
  plan tokens, effect identities and input digests do not read it.

**What each reader shows** (probe S8, with the reader change patched onto
`load_evaluated_view` in the probe process):

| Reader | Today | With the mark |
| --- | --- | --- |
| The view's `status` (`report --format json`, the dashboard, the monitor all read it) | `interrupted` | `stopped`, with `stopped: {code, site, identity}` |
| `report` | `- status: interrupted` | `- status: stopped`, and one line naming the code, the site and the `resume` command |
| Dashboard run record | `interrupted` | `stopped` |
| Monitor classifier | `CRASHED` | No event: its table has no row for `stopped`, and a requested stop is not notified |
| `state.json` on disk | `running` | `running`. No record is appended at a stop, so the file is not rewritten; it holds the last published view, as after any writer that exits without a terminal, and no reader trusts its status |
| The same run after a later record, with the old mark left in place | | `interrupted` and `CRASHED` again when no writer runs: the mark is stale |
| A run killed in the middle of a step | `interrupted`, `CRASHED` | The same |
| A run whose writer is alive | `running` | `running` |

A study's workspaces are not registered with the monitor; the row above is
for an author who uses the flag by hand.

**Why not a journal row.** A `stopped` record would make the reducer accept
a new kind, so every strict reader changes and an older build answers
`memo_inconsistent` for the run, as it does for a `rebased` record (Edit And
Continue §4, "Older builds"). It would put a fact about one invocation into
the authority for results: the flag is not stored, and the stopped journal
is today exactly what a kill after that commit leaves, which is what a copy
relies on. The mark needs none of this: probe S9 computed the plan token of a
child program with the mark present and with it moved away and got the same
token, and resumed with the mark present.

**Rejected marks.** A field in `state.json` read back by readers: the view
would then depend on an earlier view, against "a view is reconstructed from
the header, the program and the journal". A line in `run.lock`: every writer
would have to truncate it on acquisition, which touches each lock path.

### 3.5 What the stop reason must allow

How a subscription usage limit appears in a provider attempt is not known
yet; a recording task of the long-horizon work is finding out. Part 1 does
not change when it is known, because of four choices:

- a limit is not a requested stop. Exit status 3 and `stop_after_reached`
  mean that the command line's own stop was reached, and nothing else;
- `code` in the mark is an open set, and `site` and `identity` may be null.
  If the runtime ever refuses a call cleanly at a limit, that is one more
  preflight code with the same mark and the same readers;
- a call that a limit cuts off is an ordinary failed attempt today: a
  `failed` row and a failed terminal, exit 1 (probe C10). The harness's
  stop reason is a record `{reason, code, site, identity, attempt_dir, exit}`
  whose `reason` is an open set: `boundary`, `completed`, `cap`, `failed`,
  `waiting`, `refused`, with `paused` reserved. A classifier that the study
  supplies turns a `failed` reason and its attempt's evidence into `paused`
  once the recorded form of a limit exists; until then every provider
  failure pauses the study for a ruling;
- a pause is the absence of the next invocation. It is not a flag and not a
  journal row.

## 4. The harness procedure: stop, copy, continue either

### 4.1 The procedure

The unit that is copied is the *evaluation directory*: the workspace itself
when the run root lies inside it (the default `.orchestrate/runs/RUN_ID`),
or one directory that holds the workspace and the run root at fixed relative
places, such as `clone/` and `runs/` with `--state-dir ../runs` (probe C4).
The second layout keeps the driver's placement of run records outside the
clone.

1. **Advance** the candidate with `--stop-after` for the stage's keys. Exit
   status 3 and a valid mark mean the stage is reached.
2. **Check** that the run is stopped and the workspace quiet
   ([§4.2](#42-when-a-copy-at-a-stop-is-valid), [§4.3](#43-quiet)).
3. **Copy** with `cp -a` to a temporary name beside the destination, then
   rename. The destination must not exist.
4. **Check the copy** ([§4.4](#44-the-parents-path)) and **log** it outside
   every workspace ([§4.5](#45-one-run-id-several-roots)).
5. **Continue either.** The original continues with plain `resume`. A copy
   continues under the same program with plain `resume`, or under a child
   program: the harness writes the child's program files into the copy,
   reads the plan (`rebase.plan_resume`), accepts it when it cancels nothing
   and runs `resume --accept-changes=plan-<token>`.

A copy that is kept untouched is a fork point for as long as it exists: a
copy of it is as valid tomorrow as at the stop. The harness keeps one
untouched copy per candidate and stage that a later child or a clean retry
may start from, and works in copies of it.

### 4.2 When a copy at a stop is valid

The harness refuses a copy, or the continuation of one, with these codes.
Each is a row of its log.

| Condition | Code |
| --- | --- |
| A writer holds `run.lock`, or the journal has a pending start or an unsettled coordinator | `copy_not_stopped` |
| The workspace is not quiet (§4.3) | `copy_unquiet` |
| The parent's absolute path occurs in the copy's header or journal, or a link in the workspace points into the parent by absolute path (§4.4) | `copy_names_parent_path` |
| The source, a manifest or the input file of the header's recipe lies outside the copied directory, so its locator is absolute | `copy_program_outside` |
| The program of the source run, or the program that is to continue in a copy, holds a run reference | `copy_run_ref_unsupported` |
| The same, a host request | `copy_host_request_unsupported` |
| The same, an agent or an agent turn | `copy_agent_session_unsupported` |
| The same, a parallel map (`parallel.has_parallel`) | `copy_parallel_map_unsupported` |
| A child program's plan in the copy has a cut or does not keep every commit | `copy_plan_cancels` |
| The destination exists | `copy_destination_exists` |

- The class checks read the whole program, not the prefix: the site table
  of each program (`machine.site_classes`) holds `command` and `provider`
  sites alone. E10 and E11 show the prefix cases; the suffix cases are read,
  not probed (§4.5).
- A candidate that fails a class check still gets the stop and the resume.
  It gets no copy, and under an edit it reuses nothing
  (`invalidate_coordinator_committed`; the mutant plan's P10). The seed
  `roles.orc` is such a candidate: its first binding is an `agent` form.
- A copy is made on the machine and by the user that ran the parent: the
  header pins interpreters by absolute path.
- State outside the copied directory is shared, not copied: an environment
  a step installs into, files under the home directory, remote services.
- A copy made with `cp -a` carries what the next step can observe in the
  directory: content, every mode bit, modification times, link targets and
  hard links within the copy, empty directories, named pipes and nested
  repositories (probe C1). It does not carry inode numbers or change times.

### 4.3 Quiet

A stop makes the journal quiet, not the workspace: a committed step can
leave a writer behind (probe C7). Before it copies, the harness checks:

1. no process of this user has its working directory inside the copied
   directory. Directories are compared by device and inode, climbing from the
   process's working directory, because under a mount namespace the spelling
   differs (probe C6);
2. two walks of the directory taken at least one second apart agree on every
   path, type, size and modification time;
3. after the copy, a third walk of the source agrees with the second, and
   the copy's walk agrees with it.

The runtime's `attempt_processes.run_process_alive(run_id)` is not used
alone: it is true while any root with the same run id has a live attempt
(probe C8).

When a check fails the harness waits and repeats it, for at most a bound the
study fixes. A stop that stays unquiet is not a copy point: the candidate
may continue in place, no sibling starts from that stop, and the candidate's
last earlier copy stays its retry point. Where the study's design needs a
copy at that stage, the candidate is an incident there: it is not weak and
it is not scored.

### 4.4 The parent's path

**Hazard (probe C6).** A committed value can hold the parent workspace's
absolute path. A later step that uses the value then acts on the parent's
files from inside the copy. In the probe a provider step returned
`<workspace>/notes.txt` and a command appended to the file it named: the
copy's run wrote `notes.txt` into the parent, and the copy had no such file.

**Refused.** Before anything continues in a copy, the harness searches the
copy's `run.json` and `memo.jsonl` for the parent directory's absolute path,
as given and as resolved, and walks the workspace for links with an absolute
target under it. A hit is `copy_names_parent_path`. Nothing is rewritten:
the journal's bytes are covered by its digests. The search does not cover
file content in the workspace; a virtual environment or a build cache that
embeds its own absolute path is the same hazard and is not seen.

**How the harness avoids the refusal: one fixed path.** Each candidate runs
with its evaluation directory bound at one path, the same for every
candidate, through a mount namespace (`bwrap --bind <directory> <fixed
path>`). Values, caches and environments then hold the fixed path, which in
each namespace is that candidate's own directory. In the probe the parent's
value was `<fixed path>/notes.txt`, the search of the copy found nothing,
the copy's run wrote into the copy, and the parent later wrote into itself.
This is hygiene, not isolation: the real directories stay reachable to a
process that looks for them.

**The seed.** Its scripted runs bind the repository's absolute path as the
`repo` input, so the header holds it and a copy at another path is refused.
`repo` becomes `.` or is dropped, and the harness places the program, the manifests
and the inputs inside the workspace.

### 4.5 One run id, several roots

A copy keeps the parent's run id and header, byte for byte. A new id is not
an option today: the independent review rewrote the id of a fork and found
that the first provider step diverges (`input parts changed: ['prompt']`),
because the rendered prompt carries the result path and the result path
carries the run id. A new id would need a change to the input identity of
provider steps. Programs can also read the run id (X1, X4), and a host
request id binds it (E16).

What the shared id does, and what the harness does about it:

| Effect | Evidence | The harness |
| --- | --- | --- |
| A root's identity by location is not durable: a workspace is moved or deleted after scoring | Read | Gives each copy a **copy id** and logs, outside every workspace: copy id, evaluation id, the parent's copy id and path, the run id, the cut (the journal's byte length at the copy), the digest of those bytes, the stage. The log is the lineage record and the accounting authority; the driver's join key for a copied run is the copy id |
| The plan tokens of two siblings are equal | E4 and the review: the token binds the run id, the journal and the programs, which siblings share | Reads the plan in the root it accepts in. A token is not a root's name |
| The runtime's liveness check counts every root with the id. A command that fails while a sibling's step is alive records `closure: changed` where a lone run records `unchanged`, and a later in-place `resume` is refused where the lone run retries | Probe C8. The direction is safe: a refusal, not a wrong reuse | Does not retry a failed candidate in place. It continues from the candidate's kept copy, which needs no `closure` proof. Its own quiet check is scoped to the directory |
| A run reference derives its child's run id from the parent's, under one absolute root shared by every copy; a host request id binds the run id; an agent binding holds it | Read, not probed: whether two siblings collide on disk | Refuses those classes and parallel maps in the whole program (§4.2) |
| Attempt directories have the same run-relative paths in every copy | Read | Reads attempts through the copy's own root and the logged cut |

### 4.6 The controller

The loop over candidates and the rule that stops the weak live in the search
harness. The runtime knows sites and invocation limits; it does not know
candidates, scores or selection (boundary invariant 3).

- **Advancing.** One invocation per stage with the stage's keys. The harness
  reads the outcome from the exit status, the mark and the journal.
- **How "weak" is decided.** The rule is an input of the study. Its unit is
  the candidate over its whole matched task set at the stage, not a run: a
  candidate stopped on some tasks and kept on others would have a mean over
  the tasks it survived. The rule is applied when every run of the candidate
  set has reached the stage or has failed. An observation is a run's
  committed typed values at the stage, its cost so far and its stop reason,
  read from the view. No rule ships; the default keeps every candidate. A
  rule may be used when the stage-signal readout of roadmap Phase 5b (step
  9) shows that the signal predicts the end, with its threshold frozen in
  the study's criterion before spend. A stopped candidate has no
  whole-program result: it leaves the comparison, is not scored zero, and
  its spend stays in the search cost.
- **An invocation's cap.** The spend cap counts every attempt directory
  under the run root at its own conservative price, so in a copy it counts
  the inherited calls, at about five times `report`'s figure for
  `claude-haiku-5-5` (probe C9: USD 0.0035 against 0.0007 for the same two
  calls). Both figures are right for their purpose: the cap takes the larger
  of the CLI's cost and the price at the model's highest tier
  (`specs/cli.md`, "Spend cap"), and `report` prices the tokens. Nothing in
  the runtime changes. The harness computes the inherited figure with
  `providers.usage.spent` and adds a stage allowance stated at the same
  price. A cap built from `report`'s figure is reached before the stage's
  first call (probe C9).
- **The study's ceiling.** The harness reserves a stage's allowance before
  each invocation and settles it afterwards, as the long-horizon plan's D4
  does for an attempt.
- **The subscription's limit** (owner decision 18). A run stopped at a stage
  holds no process and costs nothing while the study waits. A candidate that
  waits is not weak for that reason.
- **A call that is cut off.** The attempt fails, its partial files stay, and
  a capped resume in place is refused (E14). The harness copies the
  candidate's kept copy and continues there under the same program (probe
  C10: each remaining step dispatched once, no partial file). The new root
  carries the same evaluation id: it continues the evaluation and is not a
  replicate. The abandoned root is kept as the incident's evidence, and its
  cut-off attempt is search cost. Whether a study may instead retry in place
  without a cap, in the dirty workspace, is a choice of its plan; this
  design recommends against it.

### 4.7 The cost rule

- **Own attempts** of a root are those whose `started` record lies at or
  after the cut that the harness logged for it outside the workspace, or all
  of them for a root that is not a copy. The cut is not read from a file in
  the run root, which an agent can edit.
- **Search cost** is the sum of own attempts over every run root of the
  study: failed, cut-off and abandoned ones included.
- **No figure is the sum of `report` over several roots.** `report` counts
  every attempt directory of one root, so a parent and two copies report
  nine attempts for five dispatched calls (review probe).
- **A copied or forked run yields a deployed-cost estimate,** inherited plus
  own, which is what `report` prints for it. The estimate is valid when the
  root's journal has no cancelled commit and no failed or cut-off attempt.
  It is tagged `inherited` (the amendment of §10), grouped by prefix digest,
  and read as differences among siblings.
- **Finalist selection and promotion use independent whole runs,** whose
  cost is `report`'s total. A copied or forked run is not such evidence
  ([§10](#10-contracts-to-amend), the amendment).
- Runs that share a prefix digest are one observation of that prefix
  (roadmap, H-E2: comparisons are reported over several independent parent
  prefixes).

## 5. Acceptance of Part 1

Through the public command line with stand-ins, each run built live at
target 2.40, with no recorded journal fixture.

| Requirement | Measure |
| --- | --- |
| A stopped candidate resumes with no step dispatched twice (R1) | Three candidates advanced to a stage; one dropped by a rule the test supplies; the others advanced to the end. Every identity has one `started` record and the dispatch log one line per step |
| The copy reproduces the parent's workspace at the stop (R1, at stage boundaries) | A walk of type, mode, modification time, link count, content and link target, in the stopped parent and in the copy, is equal; the workspace holds tracked, untracked and ignored files, a private file, a read-only file, a hard link pair, a link, an empty directory and a commit made by a step |
| The cost of a child equals its changed suffix (R1) | The child dispatches exactly the effects its plan lists; its own attempts by the logged cut are those dispatches; no prefix identity has a new attempt; the parent's journal is unchanged and the parent then completes |
| Sites | A loop key with `[*]`; a key of an agent turn; a host request after the boundary; a parallel map; an unknown key refused with exit 2 and no run root, and under `--accept-changes=TOKEN` with no artifact and no record written |
| Readers | For a run stopped by the flag and for one stopped by the cap: the view, `report` and the dashboard record say `stopped` and the monitor emits no event; with a stale mark, after a kill and with no mark they say what they say today |
| The mark is not authority | The plan token and the outcome of `resume` are the same with the mark, without it and with a damaged one |
| Hazards | Each code of §4.2 on a fixture that triggers it, including the value that names the parent and the writer left behind |
| Unchanged behavior | The spend-cap, edited-program resume and kill suites pass unchanged except where they assert `interrupted` for a capped run; a run without the flag writes the same bytes as before |

The tests of the flag, the mark and the readers belong to the default suite.
The test of the procedure plays the harness with `cp -a` and the command
line and imports no harness code.

## Part 2: designed, deferred

Sections 6 to 9. Part 2 keeps Part 1's flag, mark, log and cost rule. It
replaces the whole copy by a stored snapshot where that pays.

## 6. A snapshot store and a fork at an earlier step

Part 2 adds one module beside the runtime, `evaluated/checkpoints.py`, with
`snapshot_workspace`, `restore_workspace`, `advance` and `fork_run`. It reads
the journal with the runtime's readers and is not imported by the runtime.

### 6.1 Checkpoints

A checkpoint is a cut together with a snapshot taken there. A cut can lie
after the last commit of a completed run, before its terminal: a child that
appends a step forks there (review probe; probe C5 does the same with a
copy). `advance` drives a run one commit at a time (`--stop-after` for every
site of the program), and after each invocation that ended at a cut with the
workspace quiet (§4.3) it stores a snapshot and logs the row (cut, snapshot
id) outside the workspace, with a copy of the row in `checkpoints.jsonl` in
the run root as evidence. The runtime does not read that file (review probe:
garbage in it and its absence both resume). No row is written after a failed
or interrupted attempt.

### 6.2 What a snapshot must keep

The contract is what the next step can observe, not bytes alone:

| Property | Why a step sees it | Whole copy (`cp -a`) | Git store |
| --- | --- | --- | --- |
| Paths, file content, link targets, empty directories, ignored and untracked files | Directly | Kept | Kept: two trees (the work tree without `.git` and `.orchestrate`; the `.git` directory as plain files) and a list of empty directories |
| Every permission bit | A private key that becomes group-readable; a read-only file that becomes writable | Kept | The executable bit alone; a manifest blob (path, mode) applied at restore keeps the rest |
| Modification-time order | A build tool compares times: in the review's probe `make` rebuilt a target in the parent and called it up to date in the restore, because files are written in path order | Kept | Not kept by git; the manifest carries the time in nanoseconds and restore applies it |
| Hard links | Two names of one file diverge after restore | Kept within the copy | Not kept; a workspace with a hard link pair is refused |
| Named pipes, sockets, devices | A step opens them | Kept by `cp -a` for pipes | Not stored by git; refused |
| A nested repository, and any other entry named `.git` | The agent's own repository inside the task | Kept | A nested repository is stored as a link without content; a file or directory named `.git` elsewhere is left out without an error; refused |
| Ownership, extended attributes | Rarely | Not checked | Not kept; stated, not checked |

So the git store serves a workspace of regular files, links and directories,
and a whole copy is required for everything the table marks refused. The
harness falls back to Part 1's copy for a stop the store refuses.

**Silent losses, and what closes each** (review probes at `a9f9e410`; this
revision did not rerun them):

| Loss | Handling |
| --- | --- |
| The workspace's `.gitattributes` normalizes line endings | `--attr-source <empty tree>` on every git command (probe F6, both sides) |
| `core.autocrlf` or a user-level attributes file normalizes them all the same | `-c core.autocrlf=false -c core.attributesFile=/dev/null`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_ATTR_NOSYSTEM=1` |
| An entry named `.git`, a pipe, a nested repository: dropped or reduced without an error | One completeness check at snapshot time: the path set of the two trees, the empty directories and the manifest equals the path set of a walk. A difference is `snapshot_incomplete`: the step has no checkpoint |
| An unreadable file, or a nested repository without a commit: `git add` fails | `snapshot_failed` with git's message: the step has no checkpoint. It is not a crash of `advance` |

Other rules of the store: one index file per workspace, since two workspaces
that snapshot into one store through one index fail on git's index lock
(review probe); git 2.40 or later, for `--attr-source`; the store lies
outside every workspace, so an agent does not see snapshots of its future or
of its siblings.

**Cost,** on a 250 MB clone of this repository (4,691 work-tree files), same
ext4 disk (probe F5):

| Case | Seconds | Store growth |
| --- | --- | --- |
| First snapshot of the clone | 7.3 | 151 MB |
| Next snapshot, nothing changed | 0.17 | none |
| Five files edited, one new 20 MB file, one commit by the agent | 0.74 | 20 MB |
| A new 500 MB file that does not compress | 24.8 | 477 MB |
| The snapshot after that, file unchanged | 0.36 | none |
| First snapshot in a restored fork (cold stat cache) | 3.8 | none |
| Restore into an empty directory | 1.7 | |

**Disk is bound by workspaces, not by the store.** A restored fork is a full
copy, as a Part 1 copy is. With 56 GB free and a floor of 20 GB, 36 GB hold
about 144 workspaces of that clone; the 27-point tree needs up to 39 per
task and prefix. The floor applies to a restore and to a copy, not only to a
snapshot. A finished candidate's workspace is deleted once its final result
and its cost rows are in the log, keeping its run root; a kept copy is
deleted once every child planned from it has started and its own successor
copy exists.

### 6.3 `fork_run`

`fork_run(parent, cut, store, destination)` restores the checkpoint's
snapshot into a new directory and copies the run root cut at that byte: the
header, the program artifacts the prefix names, the journal bytes before the
cut, and the attempt directory of each `started` record of the prefix. It
reads bytes that do not change once written, takes no lock, and builds under
a temporary name. The review forked while the parent was running past the
cut, forked a fork, and ran two forks beside their parent.

A fork is continued as a copy is (§4.1, step 5). The fork point for a child
is found in the fork: fork at the latest checkpoint, read the plan there,
and when it has a cut, discard the fork and fork again at the last
checkpoint before the cut.

Everything of §4 applies to a fork: the quiet check before a snapshot, the
search for the parent's path, the class checks on the whole program, the
cost rule. A fork has a copy id as a copy has; it is recorded in the search
log and in the first row of the fork's `checkpoints.jsonl`, with the cut,
the prefix digest and the snapshot id. `fork_run` adds these refusals:

| Condition | Code |
| --- | --- |
| No checkpoint row for the cut, or its snapshot is not in the store | `fork_checkpoint_missing` |
| The prefix has a pending start or an unsettled coordinator | `fork_prefix_unsettled` |
| The prefix holds a commit of a class other than `command` or `provider` | `fork_prefix_class_unsupported` |
| The parent is a run-reference child or a confined child | `fork_child_run` |
| Less disk free than the floor | `fork_disk_floor` |
| The destination exists | `fork_destination_exists` |

## 7. The container route

A long-horizon task runs in a task container under rootless Podman through
the Harbor harness, with the agent inside it
([long-horizon plan](../plans/2026-11-13-long-horizon-task-family-and-seed-plan.md), D2).
Measured with Podman 4.9.3, rootless, overlay storage, on a local 8 MB image
(probe F8):

| Case | Seconds | Image size |
| --- | --- | --- |
| `podman commit` after 50 MB written | 0.72 | 60.5 MB |
| `podman commit` again after 5 MB more | 0.87 | 65.8 MB; its top layer is 57.7 MB |
| `podman commit` after 1.1 GB and 20,000 small files more | 10.8 | 1.13 GB |
| Start a container from a committed image | 0.2 | |

- Each commit stores the container's whole difference from its base image.
  Ten snapshots of a container that has written 1 GB cost about 10 GB and
  100 s, so this route affords snapshots at stages, and those of a stopped
  candidate are deleted.
- Not captured (probes): a running process; a `tmpfs` mount; a bind-mounted
  directory. `podman container checkpoint` answers "checkpointing a
  container requires root". `podman commit` pauses the container when
  `--pause` is given (its manual page: the default is false).
- A path inside a container is the same in every container, which is the
  fixed path of §4.4 by construction.
- Open prerequisites: how a workflow's steps run inside a task container
  (long-horizon plan, step 9); a fresh network sidecar and relay for a
  forked container (the launcher of its step 5).

## 8. The pause at a usage limit

The harness's classifier of §3.5 gains its rule when the long-horizon
recordings show the form of a limit: which exit status, stream fields or
passthrough log lines mark an attempt as cut by a limit and when the limit
resets. The harness then stops launching until the reset and continues each
cut candidate from its kept copy or checkpoint (§4.6). Nothing in the flag,
the mark or the procedure changes.

## 9. What brings Part 2 forward

| Evidence | What it brings forward |
| --- | --- |
| A fork point is needed after the fact: a child whose first changed step lies before its parent's latest kept copy, in a space where the mutant plan's T3 measures a saving in priced tokens that a study states as worth the work | §6: per-step checkpoints and `fork_run` |
| Whole copies cost too much disk or time: the kept copies of a study exceed the disk budget of §6.2, or a copy takes longer than a stage's start-up budget | §6: the store shares blocks between snapshots; forks are still full copies |
| A measured saving: T3's figures for the space being searched, times the number of evaluations, exceed the copy-at-stage tree's by the margin the study's plan sets | §6 |
| The long-horizon launcher exists and step 9's design is accepted | §7 |
| The recordings show a limit's form | §8 |

For the first space the saving of a fork at an earlier step over nothing is
fixed: 72 planner calls and 18 first coder calls of the 27-point grid, 90 in
all. With one round and M milestones a run makes 4 + 2M provider calls, so
the share is 90 / (27 × (4 + 2M)): 42 percent at M = 2 (the measured
stand-in run of eight calls), 28 percent at M = 4, 17 percent at M = 8, and
less with a second round. Copies at the stages after the planner's last call
and after the coder's first call give the same tree.

## Both parts

Sections 10 to 17.

## 10. Contracts to amend

On acceptance of Part 1:

| Contract | Change |
| --- | --- |
| [`specs/cli.md`](../../specs/cli.md) | The flag on `run` and `resume`; exit status 3; `stop_after_reached` and `stop_after_unknown_site` in the diagnostics tables; the unknown-site refusal in the resume preflight (step 7); the parallel-map and host-request rules; `report`'s line for a stopped run; "Spend cap": its refusals write the mark and the run reads `stopped` |
| [`specs/state.md`](../../specs/state.md) | The run-root table gains `stop.json` (evidence of how the last writer left; not authority). The derived view gains `status: stopped` and the field `stopped`. The `closure` proof says that a live attempt of any run root that carries the same run id counts |
| [`specs/observability.md`](../../specs/observability.md) | The monitor emits no event for `stopped`; `CRASHED` stays the view's `interrupted` |
| [Evaluated execution](workflow_lisp_evaluated_execution.md) | §8.1: the stop beside the spend cap, and the liveness sentence above. §10: the view's `stopped` |
| [Structural search driver](orc_structural_search_driver.md), Execution Contract | "Cross-candidate provider or effect reuse is disabled initially" gains the copy at a stop as the admitted form. "The logged run id and state dir are the join key" gains: for a copied run the copy id. "`resume` … continues the same pinned evaluation after an incident … never as a replicate" gains: so does a continuation from a kept copy, and the abandoned root is kept as the incident's evidence |
| [Program-search boundaries](workflow_lisp_program_search_boundaries.md), invariant 1 | The text below |
| [Capability matrix](../capability_status_matrix.md), [lifecycle guide](../runtime_execution_lifecycle.md) | One row; one section on stopping at a site |

On acceptance of Part 2: `specs/state.md` gains `checkpoints.jsonl` in the
run-root table (evidence, not read by the runtime).

**Amendment to boundary invariant 1,** to be applied as written. It replaces
the third item of the list, "Candidate execution starts as a new registered
run … executing code.":

> - Candidate execution starts in one of three ways, each recorded by that
>   experiment's lineage record:
>   1. as a new registered run: a root run launched by an external
>      controller through public `run`, recorded with its run id and state
>      root;
>   2. as a child where an admitted child route exists;
>   3. for search, as the continuation of a copy: a copy of a registered
>      run's workspace and run root, taken while that run is stopped after a
>      committed effect (a whole copy, or a fork restored from a snapshot of
>      that moment), and continued by public `resume` under the candidate
>      program. The candidate program passes the ordinary compiler in
>      `resume`'s fresh build, and each inherited result is reused only where
>      rule C10 of evaluated execution admits it. The continuation does not
>      write the source run's workspace or run root. A copy keeps the
>      source's run id, so its lineage record holds a copy id of its own,
>      the source's copy id and state root, the journal byte length at which
>      the copy was taken, and the digest of the journal bytes before it.
> - A copy imports committed results as data. It imports no program text and
>   no policy. No `eval`, hot swap, dynamic linking or checkpoint import
>   turns candidate data into executing code.
> - An execution whose lineage record holds a source copy, or whose journal
>   holds a `rebased` or `invalidated` record, is search evidence under
>   invariant 4. It does not establish frontier membership, finalist
>   selection or promotion. Every evaluation row carries a tag: `inherited`
>   for such an execution, `whole` for every other. A readout refuses an
>   `inherited` row, and a row without a lineage record, where it selects
>   finalists or promotes, and does not skip it silently. Executions that
>   share a prefix digest count as one observation of that prefix.
> - The runtime has no path that is specific to a candidate. A limit of one
>   invocation that any run may use (the spend cap, a stop after a named
>   effect site) is part of the public `run` and `resume` contract and knows
>   nothing of candidates, populations or selection.

The last item replaces "The runtime is not changed." The boundaries
document's change note records the amendment.

## 11. Soundness and its limits

**What holds.** After a copy or a fork is continued, the active journal is
one that an uninterrupted run of the child program could have written, with
the reused effects returning their recorded results: the replay equivalence
of C10, checked by the unchanged strict replay at acceptance. The workspace
at the first new effect is the parent's at the stop, in the sense of §4.2
for a copy and of §6.2 for a fork.

**What does not.**

- State outside the copied directory is shared (§4.2).
- An effect of the prefix can have read something C5 lists as undeclared
  (clock, network, a file opened by computed name). The copy reuses its
  result as `resume` does.
- A copy exposes its ancestry: a stored program artifact holds the absolute
  path of the parent's source (probe). The contamination scan of a study
  adds the other candidates' directory names, and for Part 2 the store's
  root, to its patterns.
- A stage that lasts longer than the provider's prompt-cache lifetime may
  pay cache-write where an uninterrupted run pays cache-read, which would
  bias a deployed-cost estimate taken under staged evaluation. This is the
  review's hypothesis; nothing here tests it.

## 12. What this makes harder

- A stop on request reads as a crash to any reader that does not go through
  `load_evaluated_view`, and to an older build.
- `stop.json` is a second file beside the journal that tools may come to
  trust. It is evidence, valid for one journal length.
- Several run roots carry one run id. The liveness check is no longer per
  run root; plan tokens do not name a root; a registry or a run-reference
  root keyed by run id would confuse them.
- Summing `report` over a study counts each prefix once per root.
- Every copy and every restored fork is a full workspace on disk.
- The program lives in the copied directory, where an agent can read and
  edit it. The harness writes it again before each invocation.
- Stages are labels. A search space must keep the labels of its stages, and
  the seed spends two lines on them.
- A value, a link or a file that holds the workspace's absolute path ends
  copying for that run unless the fixed path is used, and the fixed path
  puts the orchestrator inside a mount namespace.
- Every copy shares its ancestors' luck. An analysis that treats siblings as
  independent overstates what it knows.
- In Part 2: modes and times need a manifest; one `git init` in a
  subdirectory ends checkpoints in the store for the rest of that run; git
  becomes a dependency of the checkpoint module.
- A change of the digest rule (readiness item R2) strands a copy as it
  strands any run in flight.

## 13. Deliberately left out

- Part 2 as a whole, until §9.
- Copies of candidates with run references, host requests, Agent Sessions or
  parallel maps. They get the stop and the resume.
- Restoring a workspace in place under a live run root, which would lift
  "workspace files are not rolled back" for edit and continue.
- A public `orchestrator copy` or `fork` command.
- A cache of effect results across runs keyed by input digest.
- Any stopping rule.
- A change to the spend cap's exit status.

## 14. Probes

Stand-ins only; no provider was called. S1 and the F probes ran at
`b399076b`, S1 again on `main` at `8a61b143`; the other S probes, the C
probes and L1 ran on `main` at `e0a978ad`. The stop was patched into the
probe process at the three call sites of §3.1, with the matching rule of
§3.1; on a stop the probe wrapper wrote `stop.json` and exited 3 (S1 used an
earlier form of the patch, which stopped after any commit). The reader
change was patched onto `load_evaluated_view` in the probe process. The
program under test had four steps (`plan`, a command `built`, `work`,
`review`; three metered provider stand-ins and one command) in a git
workspace.

| # | Question | Result |
| --- | --- | --- |
| S1 | Does a stopped run resume with no step dispatched twice? | One commit per invocation: four invocations, four dispatches, every one at attempt 1, no journal row for a stop |
| S2 | Does a named site stop the run there? | `--stop-after 'workflow:main::run / plan'`: the journal holds `plan`'s start and commit; the mark names the site, the identity and 2,235 journal bytes |
| S3 | A loop site | Key `workflow:main::run / loop:pads[*] / padded`: the first invocation ends after the commit of `loop:pads[1] / padded`, the second after `loop:pads[2] / padded`, the third completes; no attempt above 1 |
| S4 | An unknown site | Found against the site table of the built program |
| S5 | An agent-turn site | Stop after turn `a1` (allocation, start, commit, `settled`); `resume` runs `a2`; two calls of the stand-in in all |
| S6 | A host request after the site | With the stop: the commit before the request and nothing else. `resume`: `started`, `suspended`, the `waiting` line, as in a run without the flag |
| S7 | A parallel map | Five items, `:parallel 2`, every site named: 2, 4 and 5 commits after three invocations, nothing pending at each stop, no attempt above 1 |
| S8 | What do readers show? | The table of §3.4 |
| S9 | Does the mark enter a plan or a resume? | The child program's plan token is the same with `stop.json` present and moved away; `resume` with the mark present continues |
| C1 | What does `cp -a` at a stop carry? | 144 entries, run root included: type, mode, modification time, link count, content and link target all equal; the hard link pair shares an inode; modes 600 and 444; the named pipe; the nested repository without a commit; a file dated 2020. 0.03 s for this small workspace |
| C2 | Does a child program in the copy reuse the prefix? | Plan: kept three, cancelled none, no cut. One dispatch, `review` at the child's effort, in the copy; the parent's journal unchanged. The parent then resumed and ran its own `review` |
| C3 | What are the cost figures of the copy? | Own attempts by the cut: one, USD 0.00035. Inherited: two, 0.0007. `report`: three, 0.00105. The cap's figure for the three: 0.00525 |
| C4 | Does the layout with the run root beside the clone copy? | `--state-dir ../runs`, `result_root: ../runs/<id>`; the evaluation directory copied; plan kept three, cancelled none; one dispatch in the copy's clone |
| C5 | A copy of a completed run, for a child that appends a step | Plan: kept four, cancelled none; the new step dispatched once |
| C6 | Can a copy write into its parent? | Yes: §4.4. The search of the copy's journal finds the parent's path. Under one fixed path through `bwrap --bind` it finds nothing and the copy writes into itself. A process inside the namespace shows the fixed spelling as its working directory and the real directory's device and inode |
| C7 | Is a stopped run's workspace quiet? | With a writer left by the committed step: nothing pending in the journal; two walks one second apart differ; one process has its working directory in the workspace. After the writer ended: equal, none |
| C8 | Do copies of one run affect each other? | A command fails in a copy with no sibling alive: `closure: unchanged`. The same while a sibling's provider step is alive: `closure: changed`; no process has its working directory in the failing copy while `run_process_alive` is true |
| C9 | Which figure does a cap need? | `report` 0.0007, the cap's 0.0035 for two inherited calls. `--max-cost-usd` at `report`'s figure plus 0.0005: `spend_cap_reached` before the stage's call. At `spent()` plus 0.0005: the stage runs |
| C10 | Is a copy of the kept copy a clean retry? | The call is cut off: a `failed` row, a failed terminal, exit 1, a partial file. Capped resume in place: `spend_cap_unmetered`. In a copy of the copy kept at the last stop: `work` and `review` once each at attempt 1, exit 0, no partial file |
| L1 | Do labels name the seed's verdicts? | §3.3 |
| F1 | Does a fork from the git store reproduce the workspace? | Content, executable bit, link targets and empty directories equal: 59 entries, 42 under `.git`. The review found the same with 63 entries and found modes, times and hard links not kept |
| F2 | Edited-program resume on a fork | Kept three, cancelled none; one dispatch at attempt 1; the journal is the prefix, one `rebased` record with a null cut, the step, the terminal |
| F3 | A fork's cost | Own: one attempt, the changed call. `report`: the whole program |
| F4 | A fork as a clean retry | As C10, from a checkpoint |
| F5 | The cost of a git snapshot | The table of §6.2; walks of the clone and its restore equal in content, 8,042 entries |
| F6 | Do workspace attributes alter stored bytes? | Without `--attr-source`: `a\nb\nc\n`. With it: `a\r\nb\nc\r\n`, as written |
| F7 | What does the git store not keep? | Mode 600 came back 664; a nested repository is a link entry without content |
| F8 | The container route | The table and list of §7 |

Probes of the independent review that this page relies on and did not rerun
are marked "review probe" where they are used: the new run id (§4.5), the
`make` case and the silent losses (§6.2), the index lock (§6.2), the nine
attempts (§4.7), and the forks of §6.3.

## 15. Not verified and open prerequisites

| Item | State | Needed for |
| --- | --- | --- |
| The placement of the unknown-site refusal before publication and before an accepted plan is written | Read in `run_evaluated_workflow` and the resume preflight; the probe gate refused later | Part 1; the first test of the flag |
| The reader change inside `load_evaluated_view`, the dashboard's pages and `report`'s extra line | The view, the dashboard's run record and `report`'s status line were probed through a patch; the pages and the extra line were not | Part 1 |
| The mark written under the writer lock, and for the spend cap's refusals | Specified; the probe wrapper wrote it after the command returned, for the stop alone | Part 1 |
| A run reference, a host request, an agent or a parallel map in the suffix of a copy | Read, not probed; refused | Lifting a refusal of §4.2 |
| The fixed path with a real provider CLI, and the dashboard or monitor reading through it | One stand-in probe (C6) | Using the fixed path in a study |
| File content in a workspace that embeds the workspace's path | Not searched (§4.4) | A study without the fixed path |
| How a subscription usage limit appears in a provider attempt | Not recorded; the long-horizon recordings are finding out | §8 |
| Whether a long stop changes metered cost through the prompt cache | A hypothesis (§11) | Reading deployed-cost estimates of staged runs |
| A program that reads its run id (X1) or a provider's result path (X4) in a copy | Read, not probed | Stating what such a program reuses |
| The manifest of modes and times, the completeness check and the hardened git configuration | Specified from the review's probes; not run here | Part 2 |
| How a workflow's steps run inside a task container; a sidecar and relay for a forked container | Open design work of the long-horizon plan | §7 |

## 16. Open questions for the coordinator

| # | Question | Recommendation |
| --- | --- | --- |
| 1 | Do the spend cap's refusals write the mark, so that a capped run reads `stopped`? | Yes. It is one code path, and a study caps every invocation. It changes what `report` says for a capped run, which `specs/cli.md` must state |
| 2 | Does the seed label its two verdict effects at the cost of two lines against its limit of fewer than 50? | Yes, before the freeze: labelling changes the keys. The seed is expected at 46 lines after the surface-coherence rewrite |
| 3 | Is the fixed path part of the first study's harness, or does the study accept `copy_names_parent_path` refusals? | The fixed path. Agents report absolute paths in free text readily, so without it most copies of real runs would be refused |
| 4 | May a study retry a cut-off call in place without a cap? | No: the workspace is dirty and `report` turns partial. Continue from the kept copy |
| 5 | Where does the procedure's code live? | With the search harness under `experiments/`; the acceptance test of §5 pins the runtime's side without importing it |

## 17. Increment note for the planner

This note is planning input, not contract; the plan owns sizes and order.

| Increment | Contents | Hours |
| --- | --- | --- |
| Part 1, the flag | The check at three call sites, the field, the flag on `run` and `resume`, the unknown-site refusal at both places, exit status 3, tests of §5's "Sites" row | 12 |
| Part 1, the mark and the readers | `stop.json` under the writer lock for the three codes, the reader rule in `load_evaluated_view`, `report`'s line, the three specs, tests of §5's "Readers" and "not authority" rows | 8 |
| Part 1, the procedure | The copy with its checks and codes, the log row, the fixed path, the acceptance test of the three R1 rows and the hazards | 12 |
| Part 1, contracts | The amendment and the other rows of §10 | 3 |
| Part 1, review and fixes | | 6 |
| Part 2, when selected | Snapshot and restore with manifest and completeness check 12; `advance` and checkpoint rows 6; `fork_run` and its refusals 10; tests 6; the container route 16 to 24; the limit classifier 6 | |

The flag edits `specs/cli.md` and `orchestrator/cli/main.py`, which the
one-target cut also edits. No increment needs the cut, provided the tests
record no journal fixture. The reach measurement that an earlier revision
listed here belongs to the mutant plan's task T3. The container route and
the limit classifier need the long-horizon launcher and its recordings.
