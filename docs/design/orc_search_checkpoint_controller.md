# ORC Search Checkpoints: Stop At A Stage, Copy Or Fork A Run

**What this page is.** The design for readiness item R1 of
[roadmap Phase 6](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-6-program-evolution):
a search over workflow programs stops a candidate at a named stage, takes
the workspace as it stands there, and continues a child program from it, so
that the child pays for its changed suffix. The design has two parts. Part 1
is one flag, `--stop-after SITE`, with its contract, and a documented harness
procedure that copies a stopped run whole, with its preconditions. Part 2 is
designed and deferred: a snapshot store, a fork at an earlier step, the
container route and the pause at a usage limit.

**Status.** Draft; in review, not accepted, not implemented. In the terms of
the [documentation conventions](../documentation_conventions.md#status-labels)
this is `Planned`. Nothing here is available in the checkout. Hypothesis H-E2
of the roadmap is what the design serves; it makes no claim that H-E2 holds.

**When to build.** Nothing of this design is built until two things are
known. The first is where a staged seed's workspace lives when it drives a
container task, which the design of the comparison step decides
([roadmap Phase 5b](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-5b-long-horizon-task-family-and-staged-seed),
step 9): the copy procedure copies a directory on the host, and on the
long-horizon tasks the agent's work is inside a container. The second is
whether stage signals predict the final result, which the first paid seed
runs show: stopping weak candidates early pays if they do and not otherwise.
Part 1 is then about 27 hours ([§17](#17-increment-note-for-the-planner)).

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
amended as [§10](#10-contracts-to-amend-when-part-1-is-built) lists.

**Copy safety.** Nothing here is a recipe. The flag, the fields and the
codes are proposals. The probe commands ran on one machine and are evidence,
not examples.

**Terms.** *Journal:* the run's `memo.jsonl`. *Site key:* an effect identity
as the checked site table spells it, with `[*]` in place of each loop or map
index (`machine.site_classes`). *Stage:* a point of a workflow that a study
names by a site key ([§3.4](#34-naming-a-stage)). *Stop:* the end of an
invocation at a named site. *Cut:* a journal byte offset immediately after a
`committed` record at which no attempt is pending. *Copy:* a whole copy of a
stopped run's workspace and run root. *Fork:* a new run root made from a
stored snapshot (Part 2). *Prefix:* the journal bytes before a cut.
*Stand-in:* a local script that plays a provider; no model is called. A
campaign `checkpoint` in the
[cumulative campaigns design](orc_structural_search_cumulative_campaigns.md)
is a different object.

## 1. Conclusion

**Part 1 is one flag and one procedure, with no new file, record or module.**
Probes with stand-ins showed each claim ([§14](#14-probes)).

1. `--stop-after SITE` ends an invocation before the next new attempt once
   an effect at that site has committed in it. It writes no journal row and
   no terminal and exits with status 3; `resume` continues. A run driven this
   way dispatched every step once.
2. The caller recognises a requested stop by the exit status. Anyone else
   recognises it from the journal alone: no terminal, nothing pending, the
   last commit at one of the stage's keys. `report`, the dashboard and the
   monitor do not: they show such a run as `interrupted`, and the monitor's
   classifier labels it `CRASHED`, as they do today for a run stopped by the
   spend cap. That is a known limit, and a harness filters by exit status
   ([§3.3](#33-recognising-a-requested-stop)).
3. A copy of the stopped run made with `cp -a` is a copy of the workspace
   and of the journal at that stop. In the probe it equalled the parent in
   content, modes, times, hard links, a named pipe and a nested repository;
   the child program's plan kept the prefix and cancelled nothing; one step
   was dispatched in the copy; the parent then continued.
4. A child's own attempts are those started at or after the journal length
   the harness logged when it copied. Search cost sums own attempts over
   every run root. A copy continued under another program is tagged
   `inherited` and no readout that selects may use it
   ([§4.7](#47-the-cost-rule-and-the-evidence-tag)).

**What the copy procedure does not reach.** It copies a directory on the
host. On the long-horizon tasks the agent works inside the task container
with nothing mounted, so the procedure does not copy that work. Until the
comparison step's design says where a staged seed's workspace lives, a study
on those tasks gets stops and resumes and no copies, and this page does not
claim that copies at stops serve the first search tree
([§4.1](#41-where-it-applies)).

**Three preconditions carry the procedure,** each from a probed hazard: the
parent and the copy see the workspace at the same absolute path, or the copy
names the parent's path nowhere; the harness ends every process the run's
steps left before it copies; and copies share a run id, so the harness keeps
its own lineage log and does not retry a failed candidate in place.

**Part 2 is specified so that Part 1 does not change when it is built:** the
snapshot store and a fork at an earlier step, the container route, and the
pause at a usage limit. [§9](#9-what-brings-part-2-forward) says what
evidence brings each forward.

## 2. What exists today

Rows E1 to E18 were established at `b399076b`, and E19 and E20 on `main` at
`e0a978ad`, each by the command shown, with stand-ins on a closed `PATH`.
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
| E19 | A stop without a terminal reads as a crash in every reader | Stop a run after a commit through the probe gate; call `load_evaluated_view`, `report`, the dashboard's `RunScanner` and the monitor's `classify_run`; read `state.json` | View, `report` and dashboard: `interrupted`. Monitor: `CRASHED`, reason `evaluated_writer_lock_released_interrupted`. `state.json`: `running` |
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

## Part 1: the flag and the copy procedure

Sections 3 to 5.

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
- **What a stop leaves.** No journal row, no terminal, no other file. The
  `resume` line is printed. A later `resume` continues, with or without the
  flag.
- **Exit status 3.**
- **Completion.** A run whose last effect is the named site completes with
  its terminal and exits 0. A loop site stops the invocation after the next
  matching commit, so a caller that wants the third round counts.
- The flag is not stored and is checked before the spend cap. The spend cap
  is unchanged.

**Place in the code.** One check beside `check_spend_cap`
(`evaluated/spend_cap.py`), called where that one is called
(`runtime.prepare_effect`, `agent_turns.prepare_agent_attempt`) and before a
new host request is issued (`host_input.execute_request`). The stop set
travels as `--max-cost-usd` does, as a field of `RunAuthority` that is not
stored.

### 3.2 Six points fixed here

| Point | Rule | Evidence |
| --- | --- | --- |
| An unknown site | Refused with `stop_after_unknown_site`, exit 2, before any run state is written. `run`: after the build, before the workspace lock is taken and the run root is published (`cli/commands/evaluated.py::run_evaluated_workflow`). The build directory under `.orchestrate/build/` is written first, as for every `run` and `run --dry-run`. `resume`: after the in-memory build of preflight step 7, against the program that will execute (the candidate when a plan token is given), before step 10 compares a token and before step 11 stores an artifact or appends a record | Probe S4: a `run --dry-run` leaves `closed_program.json` and `manifest.json` under `.orchestrate/build/` and no run root; a misspelt site is found against the site table. The placement is read, not probed |
| A parallel map | The flag does not refuse it. Items in flight finish and no new item starts, so an invocation ends after up to `:parallel` matching commits, with nothing pending | Probe S7: five items at `:parallel 2`; 2, 4 and 5 commits after three invocations; each item dispatched once |
| A host request | A request after the boundary is not issued: the stop precedes it. `resume` issues it | Probe S6: the journal holds the commit before the request and nothing else; `resume` then appends `started` and `suspended` and prints the `waiting` line, as a run without the flag does |
| A run-reference child | The stop set is not passed to a child run. A child executes whole inside its parent's effect, and a site inside a child is not in the parent's table, so naming one is an unknown site | Read |
| `py run` | Does not take the flag. A Python-built run is continued with `resume`, which takes it; its site keys are those of the generated `.orc` | Decision |
| The exit status | 3 means that the command line's own stop was reached. The command line documents 0, 1 and 2, and the monitor's 130; none of them is 3. In the code the confined run-reference helper subprocess exits 3 to its parent (`run_ref/confined_session.py`), which is not a status of the command line. Without the status a caller would read standard error to tell a requested stop from a stop at the cap | Read |

### 3.3 Recognising a requested stop

**The caller** has the exit status: 3 is a requested stop, 0 a completed or
waiting run, 1 a failed run or a stop at the spend cap, 2 a refusal before
execution.

**Anyone else** reads the journal. A run stands at a stage when all three
hold:

1. the journal has no terminal in force (a failed terminal that a later
   `started` record reopened does not count);
2. it has no pending start and no unsettled coordinator;
3. the site key of its last `committed` record is one of the stage's keys.

Probe S8: the predicate is true after a requested stop at the site and false
for another site, false after a kill in the middle of the next step (a
pending start) and false for a completed run. It is also true for a run that
the spend cap, or a kill, left immediately after that commit: the bytes are
the same and so is the state, which is an equally valid copy point. The
predicate says where the run stands, not why the invocation ended; a harness
that needs the reason has the exit status and its own log row for the
invocation.

**What the readers show, and the limit.** For a run stopped by the flag
(E19), as for one stopped by the spend cap (E20):

| Reader | Shows |
| --- | --- |
| `report`, and the view's `status` that `report --format json` and the dashboard read | `interrupted` |
| The monitor's classifier | `CRASHED`, reason `evaluated_writer_lock_released_interrupted` |
| `state.json` on disk | `running`: no record is appended at a stop, so the file holds the last published view |

This design changes none of them. A harness filters its runs by exit status
and by the predicate, and a study's workspaces are not registered with the
monitor. An author who uses the flag by hand sees `interrupted` and continues
with `resume`, as after a stop at the cap.

### 3.4 Naming a stage

**A stage is named by a full site key.** The last label of a key is not a
name. The seed `milestones.orc` (`experiments/long_horizon_seed/`; probe K2
compiled its revision `c93a6954` on `main`, and the keys have not changed
since) has these eight keys:

```text
workflow:milestones::run / ready
workflow:milestones::run / spec
workflow:milestones::run / loop:state[*] / plan
workflow:milestones::run / loop:state[*] / report
workflow:milestones::run / loop:state[*] / else / acceptance
… / built / body / loop:#1[*] / else / each=workflow:milestones::milestone / loop:state[*] / change
… / built / body / loop:#1[*] / else / each=workflow:milestones::milestone / loop:state[*] / report
… / built / body / loop:#1[*] / else / each=workflow:milestones::milestone / loop:state[*] / verdict
```

Two keys end in `report`: the round's check and each milestone's check. They
are two stages. The verdict sites carry authored labels (`acceptance`,
`verdict`) and the milestone call frame is named (`each`); the model and the
effort of each role are literals at its call forms. The seed `staged.orc` has
the same shape of keys; `designed.orc` puts its design review and its rounds
under named call frames (`design=workflow:designed::review-design` and
`ACCEPTED / built=workflow:designed::build`); `roles.orc` has `agent` and
`agent_turn` sites from its first effect.

**A harness maps stages per candidate from the candidate's own closed
program.** A study declares each stage as a site key of the seed. For a
candidate the harness reads the candidate's site table and maps each stage:

1. to the stage's key, when the candidate's table holds it;
2. otherwise to the key that the mutation which moved the site recorded for
   it: an operator that moves a site emits the old key and the new one;
3. the mapped key is in the candidate's table with the same effect class,
   and no two stages map to one key. A stage without a key is
   `stage_site_missing`, and one key for two stages is
   `stage_site_ambiguous`: the candidate is refused at admission, before
   spend.

**Which edits keep a key** (probe K1, the key `workflow:main::run / review`
of a four-step program):

| Edit | Key afterwards | Stage found by |
| --- | --- | --- |
| An effort literal; a model literal | `run / review` | Rule 1 |
| Earlier bindings reordered | `run / review` | Rule 1 |
| Prompt wording in the prompt asset | The key does not hold it (read) | Rule 1 |
| The effect wrapped in a `let*` whose inner binding has the same label | `run / review` | Rule 1 |
| The effect wrapped in a `let*` whose inner binding is `r` | `run / r` | Rule 2, or refused |
| The binding renamed | `run / check` | Rule 2, or refused |
| The call moved into a sub-workflow, inner effect labelled `review` | `run / review=workflow:main::judge / review` | Rule 2, or refused |
| The call moved into a sub-workflow, inner effect unlabelled | `run / review=workflow:main::judge / #1` | Rule 2, or refused |

A key that ends in a generated ordinal is admitted for that candidate. It
moves when an unnamed effect is inserted before it (rule I4 of evaluated
execution), so a study prefers labelled sites for its stages. In the first
search space every edit is a literal edit and every map is the identity.

## 4. The copy procedure

This section is a procedure for a search harness. Its code lives with the
harness; the runtime's part is `resume`, the plan and the flag.

### 4.1 Where it applies

The procedure copies a directory on the host: the *evaluation directory*.
That is the workspace itself when the run root lies inside it (the default
`.orchestrate/runs/RUN_ID`), or one directory that holds the workspace and
the run root at fixed relative places, such as `clone/` and `runs/` with
`--state-dir ../runs` (probe C4).

**It does not reach a container task's workspace.** On the long-horizon
tasks the agent runs inside the task's container and nothing is mounted
([long-horizon plan](../plans/2026-11-13-long-horizon-task-family-and-seed-plan.md),
D2). A copy of a host directory then holds the run root and not the agent's
work. Where a staged seed's workspace lives when it drives such a task is
decided by the design of the comparison step (roadmap Phase 5b, step 9). The
procedure needs one of two things from that design:

- the workspace reachable from the host as a directory, mounted at one fixed
  path in every container, with what a step writes outside it either
  refused or accepted as not copied; or
- the container route of Part 2 ([§7](#7-the-container-route)), a commit of
  the container at the stop.

Until then a study on those tasks has stops and resumes and no copies.

### 4.2 The procedure

1. **Advance** the candidate with `--stop-after` for the stage's key. Exit
   status 3 means the stage is reached.
2. **End what the steps left** ([§4.4](#44-ending-what-the-steps-left)) and
   check the preconditions ([§4.3](#43-preconditions)).
3. **Copy** with `cp -a` to a temporary name beside the destination, then
   rename. The destination must not exist.
4. **Log** the copy outside every workspace
   ([§4.5](#45-one-run-id-several-roots)).
5. **Continue either.** The original continues with plain `resume`. A copy
   continues under the same program with plain `resume`, or under a child
   program: the harness writes the child's program files into the copy,
   reads the plan (`rebase.plan_resume`), accepts it when it cancels nothing
   and runs `resume --accept-changes=plan-<token>`.

A copy that is kept untouched is a fork point for as long as it exists. The
harness keeps one untouched copy per candidate and stage that a later child
or a clean retry may start from, and works in copies of it. A completed run
is copied the same way, for a child that appends a step (probe C5).

`cp -a` is the copier. The repository has another,
`orchestrator/workflow/run_ref/checkpoint.py`, a descriptor-pinned copier
with a tree manifest for confined run-reference workspaces. It is not reused:
it leaves out `.git` and `.orchestrate` at the root, which are the task
repository and the run root that a copy here must carry, and it is bounded
and coded for that confinement profile.

### 4.3 Preconditions

The harness refuses a copy, or the continuation of one, with these codes.
Each is a row of its log.

| Condition | Code |
| --- | --- |
| A writer holds `run.lock`, or the journal has a pending start or an unsettled coordinator | `copy_not_stopped` |
| A process the steps left could not be ended, or the tree still changes afterwards (§4.4) | `copy_unquiet` |
| The copy does not see the workspace at the parent's absolute path, and its header or journal, or a link in the workspace, names that path | `copy_names_parent_path` |
| The source, a manifest or the input file of the header's recipe lies outside the copied directory, so its locator is absolute | `copy_program_outside` |
| The program of the source run, or the program that is to continue in a copy, holds a run reference | `copy_run_ref_unsupported` |
| The same, a host request | `copy_host_request_unsupported` |
| The same, an agent or an agent turn | `copy_agent_session_unsupported` |
| The same, a parallel map (`parallel.has_parallel`) | `copy_parallel_map_unsupported` |
| A child program's plan in the copy has a cut or does not keep every commit | `copy_plan_cancels` |
| The destination exists | `copy_destination_exists` |

**The path.** A copy is supported where the parent and the copy see the
workspace at the same absolute path, as two containers do. Elsewhere it is
refused with `copy_names_parent_path` when the parent's path occurs in the
copy's `run.json` or `memo.jsonl`, as given or as resolved, or a link in the
workspace has an absolute target under it. The hazard behind the rule (probe
C6): a provider step returned `<workspace>/notes.txt` and a command appended
to the file it named; the copy's run then wrote `notes.txt` into the parent,
and the copy had no such file. Nothing is rewritten, since the journal's
bytes are covered by its digests. The search does not read file content in
the workspace, so a virtual environment or a build cache that embeds its own
path is the same hazard and is not seen. On the host the refusal is expected
to meet most runs of a real agent, whose file tools take absolute paths and
whose free text feeds later prompts; no provider was called to observe it. The seed's scripted runs also bind the
repository's absolute path as the `repo` input, which puts it in the header.

**The classes.** The class checks read the whole program, not the prefix:
the site table of each program holds `command` and `provider` sites and no
other. E10 and E11 show the prefix cases; the suffix cases are read, not
probed. A candidate that fails a class check still gets the stop and the
resume. It gets no copy, and under an edit it reuses nothing
(`invalidate_coordinator_committed`; the mutant plan's P10). The seed
`roles.orc` is such a candidate.

**What else holds for a copy.** It is made on the machine and by the user
that ran the parent, since the header pins interpreters by absolute path.
State outside the copied directory is shared, not copied: an environment a
step installs into, files under the home directory, remote services. `cp -a`
carries what a step can observe in the directory: content, every mode bit,
modification times, link targets and hard links within the copy, empty
directories, named pipes and nested repositories (probe C1). It does not
carry inode numbers or change times.

### 4.4 Ending what the steps left

A stop makes the journal quiet, not the workspace, and a copy does not carry
processes: a parent that keeps a writer and a copy that has none diverge
whatever the tree looked like at the copy. So quiet is enforced, not
observed. **At every stop, before a copy and before either side continues,
the harness ends every process the run's steps left.**

**How they are found.** The harness starts each invocation as the leader of
a new session, with a variable in its environment that names the root. After
the invocation exits it kills every process in that session and process
group, and every process of the user whose environment carries the variable.
For a container task it ends every process of the task container but its
first, or stops the container. What the runtime does on its own, and what
the two searches find (probe C7):

| Leftover | The runtime | Found by session or group | Found by the variable |
| --- | --- | --- | --- |
| A child that a provider step leaves in the step's own process group | The attempt fails: `provider_exit_nonzero`, error `provider_process_cleanup_failed` | | |
| A child that a command step leaves | The step commits | Yes | Yes |
| A daemon left by either kind of step: its own session, working directory `/`, writing into the workspace by absolute path | The step commits | No | Yes |

In the probe a search by working directory found the command's child and
neither daemon; the variable found all of them; after the kill two walks of
the tree one second apart agreed, and agreed again two seconds later; the
run then resumed and completed.

**Then the harness walks the tree** twice, at least one second apart, and
once more after the copy. The walks confirm that the kill worked. A
difference is `copy_unquiet`: no copy is made at that stop.

**Not found:** a process that left the session and scrubbed its environment,
and work handed to a service that was already running, which is the limit
`specs/state.md` states for the `closure` proof. Rootless container
processes run under subordinate user ids and are ended through the
container.

**What is lost.** A background server or watcher that a later step expected
is gone after the first stop. A program whose later steps depend on a
process an earlier step left running is not copyable, and under this
procedure it is not stoppable either: a study runs it whole.

The parent's leftovers are ended before the copy and a copy starts with
none, so both sides continue from the same state.

### 4.5 One run id, several roots

A copy keeps the parent's run id and header, byte for byte. A new id is not
an option today: with the id of a fork rewritten, the first provider step
diverges (`input parts changed: ['prompt']`), because the rendered prompt
carries the result path and the result path carries the run id (review
probe, §14). Programs can also read the run id (X1, X4), and a host request
id binds it (E16).

| Effect of the shared id | Evidence | The harness |
| --- | --- | --- |
| A root's identity by location is not durable: a workspace is moved or deleted after scoring | Read | Gives each copy a **copy id** and logs, outside every workspace: copy id, evaluation id, the candidate program's digest, the parent's copy id and path, the run id, the cut (the journal's byte length at the copy), the digest of those bytes, the stage. The log is the lineage record and the accounting authority; the driver's join key for a copied run is the copy id |
| The plan tokens of two siblings are equal | E4: the token binds the run id, the journal and the programs, which siblings share | Reads the plan in the root it accepts in. A token is not a root's name |
| The runtime's liveness check counts every root with the id. A command that fails while a sibling's step is alive records `closure: changed` where a lone run records `unchanged`, and a later in-place `resume` is refused where the lone run retries | Probe C8. The direction is safe: a refusal, not a wrong reuse | Does not retry a failed candidate in place. It continues from the candidate's kept copy, which needs no `closure` proof |
| A run reference derives its child's run id from the parent's, under one absolute root shared by every copy; a host request id binds the run id; an agent binding holds it | Read, not probed: whether two siblings collide on disk | Refuses those classes and parallel maps in the whole program (§4.3) |
| Attempt directories have the same run-relative paths in every copy | Read | Reads attempts through the copy's own root and the logged cut |

### 4.6 The controller

The loop over candidates and the rule that stops the weak live in the search
harness. The runtime knows sites and invocation limits; it does not know
candidates, scores or selection (boundary invariant 3).

- **Advancing.** One invocation per stage with the stage's key. The harness
  reads the outcome from the exit status and the journal.
- **How "weak" is decided.** The rule is an input of the study. Its unit is
  the candidate over its whole matched task set at the stage, not a run: a
  candidate stopped on some tasks and kept on others would have a mean over
  the tasks it survived. The rule is applied when every run of the candidate
  set has reached the stage or has failed. An observation is a run's
  committed typed values at the stage, its cost so far and how its
  invocation ended, read from the view. No rule ships; the default keeps
  every candidate. A rule may be used when the stage-signal readout of
  roadmap Phase 5b (step 9) shows that the signal predicts the end, with its
  threshold frozen in the study's criterion before spend. A stopped
  candidate has no whole-program result: it leaves the comparison, is not
  scored zero, and its spend stays in the search cost.
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
  evaluation's own kept copy and continues there under the same program
  (probe C10: each remaining step dispatched once, no partial file). That is
  the same evaluation: it keeps its evaluation id and is not a replicate.
  The abandoned root is kept as the incident's evidence, and its cut-off
  attempt is search cost.

### 4.7 The cost rule and the evidence tag

**Cost.**

- *Own attempts* of a root are those whose `started` record lies at or after
  the cut that the harness logged for it outside the workspace, or all of
  them for a root that is not a copy. The cut is not read from a file in the
  run root, which an agent can edit.
- *Search cost* is the sum of own attempts over every run root of the study,
  failed, cut-off and abandoned ones included. It is priced as deployed cost
  is: metered tokens times the study's frozen price table
  ([driver](orc_structural_search_driver.md#objective-selection-and-local-observations)),
  which is `report`'s pricing and not the spend cap's figure.
- *No figure is the sum of `report` over several roots.* `report` counts
  every attempt directory of one root. In probe C3 the copy's `report` counts
  three attempts and the parent, continued, holds three as well, for four
  calls dispatched in all.
- *Deployed cost* of an execution is `report`'s total for its root, valid
  when the root's journal has no cancelled commit and no failed or cut-off
  attempt.

**The tag.** Every evaluation row carries one, from its lineage record.

| Execution | Tag | Use |
| --- | --- | --- |
| A run from its first step, not a copy | `whole` | Every readout |
| A continuation of a copy of the same evaluation's own earlier state, under the same program and the same evaluation id, after an incident, with the abandoned root kept as the incident's evidence | `whole` | Every readout. Its deployed cost is `report`'s total for the root it finished in; the incident's attempts are search cost |
| A continuation of a copy under a different candidate program, or under a different evaluation id. A copy of a completed run that a child continues is one | `inherited` | Search guidance. Its cost is an estimate, inherited plus own, read as differences among siblings and grouped by prefix digest |

No readout that selects uses an `inherited` execution: the frontier
computation, finalist selection and promotion each refuse an `inherited`
row, and a row without a lineage record, and do not skip it silently
([§10](#10-contracts-to-amend-when-part-1-is-built), the amendment).
Executions that share a prefix digest are one observation of that prefix
(roadmap, H-E2: comparisons are reported over several independent parent
prefixes).

## 5. Acceptance of Part 1

Through the public command line with stand-ins, each run built live at
target 2.40, with no recorded journal fixture.

| Requirement | Measure | Where |
| --- | --- | --- |
| A stopped candidate resumes with no step dispatched twice (R1) | Three runs advanced to a site; one left there; the others advanced to the end. Every identity has one `started` record and the dispatch log one line per step | Default suite |
| Sites | A loop key with `[*]`; a key of an agent turn; a host request after the boundary; a parallel map; an unknown key refused with exit 2 and no run root, and under `--accept-changes=TOKEN` with no artifact and no record written | Default suite |
| Exit status and predicate | Status 3 for a requested stop and for nothing else; the predicate of §3.3 true at the site and false after a kill mid-step, for a completed run and for another site | Default suite |
| A copy at a stop continues (R1, on a host directory) | The run stopped by the flag, the directory copied with `cp -a`: a walk of type, mode, modification time, link count, content and link target is equal; a child program's plan in the copy cancels nothing; the child dispatches exactly the effects its plan lists; no prefix identity has a new attempt; the parent's journal is unchanged and the parent then completes | Default suite; the test plays the harness with `cp -a` and the command line and imports no harness code |
| The cost of a child equals its changed suffix (R1) | The child's own attempts by the journal length at the copy are its dispatches | The same test |
| The procedure's refusals | Each code of §4.3 on a fixture that triggers it, the value that names the parent and the processes of §4.4 included | The harness's own tests, beside its code |
| Unchanged behavior | The spend-cap, edited-program resume, kill and reader suites pass unchanged; a run without the flag writes the same bytes as before | Default suite |

## Part 2: designed, deferred

Sections 6 to 9. Part 2 keeps Part 1's flag, log, cost rule and tag.

## 6. A snapshot store and a fork at an earlier step

Part 2 adds one module beside the runtime, `evaluated/checkpoints.py`, with
`snapshot_workspace`, `restore_workspace`, `advance` and `fork_run`. It reads
the journal with the runtime's readers and is not imported by the runtime.

### 6.1 Checkpoints

A checkpoint is a cut together with a snapshot taken there. A cut can lie
after the last commit of a completed run, before its terminal: a child that
appends a step forks there. `advance` drives a run one commit at a time
(`--stop-after` for every site of the program), and after each invocation
that ended at a cut, with the leftovers of §4.4 ended, it stores a snapshot
and logs the row (cut, snapshot id) outside the workspace, with a copy of
the row in `checkpoints.jsonl` in the run root as evidence. The runtime does
not read that file. No row is written after a failed or interrupted attempt.

### 6.2 What a snapshot must keep

The contract is what the next step can observe, not bytes alone:

| Property | Why a step sees it | Whole copy (`cp -a`) | Git store |
| --- | --- | --- | --- |
| Paths, file content, link targets, empty directories, ignored and untracked files | Directly | Kept | Kept: two trees (the work tree without `.git` and `.orchestrate`; the `.git` directory as plain files) and a list of empty directories |
| Every permission bit | A private key that becomes group-readable; a read-only file that becomes writable | Kept | The executable bit and no other; a manifest blob (path, mode) applied at restore keeps the rest |
| Modification-time order | A build tool compares times: `make` rebuilt a target in the parent and called it up to date in the restore, because files are written in path order | Kept | Not kept by git; the manifest carries the time in nanoseconds and restore applies it |
| Hard links | Two names of one file diverge after restore | Kept within the copy | Not kept; a workspace with a hard link pair is refused |
| Named pipes, sockets, devices | A step opens them | Kept by `cp -a` for pipes | Not stored by git; refused |
| A nested repository, and any other entry named `.git` | The agent's own repository inside the task | Kept | A nested repository is stored as a link without content; a file or directory named `.git` elsewhere is left out without an error; refused |
| Ownership, extended attributes | Rarely | Not checked | Not kept; stated, not checked |

So the git store serves a workspace of regular files, links and directories,
and a whole copy is required for everything the table marks refused. The
harness falls back to Part 1's copy for a stop the store refuses.

**Silent losses, and what closes each:**

| Loss | Handling |
| --- | --- |
| The workspace's `.gitattributes` normalizes line endings | `--attr-source <empty tree>` on every git command (probe F6, both sides) |
| `core.autocrlf` or a user-level attributes file normalizes them all the same | `-c core.autocrlf=false -c core.attributesFile=/dev/null`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_ATTR_NOSYSTEM=1` |
| An entry named `.git`, a pipe, a nested repository: dropped or reduced without an error | One completeness check at snapshot time: the path set of the two trees, the empty directories and the manifest equals the path set of a walk. A difference is `snapshot_incomplete`: the step has no checkpoint |
| An unreadable file, or a nested repository without a commit: `git add` fails | `snapshot_failed` with git's message: the step has no checkpoint. It is not a crash of `advance` |

The second, third and fourth rows, the `make` case and the hard links rest
on the independent review's probes (§14).

Other rules of the store: one index file per workspace, since two workspaces
that snapshot into one store through one index fail on git's index lock; git
2.40 or later, for `--attr-source`; the store lies outside every workspace,
so an agent does not see snapshots of its future or of its siblings.

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
task and prefix. The floor applies to a restore and to a copy as well as to
a snapshot. A finished candidate's workspace is deleted once its final
result and its cost rows are in the log, keeping its run root; a kept copy
is deleted once every child planned from it has started and its own
successor copy exists.

### 6.3 `fork_run`

`fork_run(parent, cut, store, destination)` restores the checkpoint's
snapshot into a new directory and copies the run root cut at that byte: the
header, the program artifacts the prefix names, the journal bytes before the
cut, and the attempt directory of each `started` record of the prefix. It
reads bytes that do not change once written, takes no lock, and builds under
a temporary name. A fork made while the parent was running past the cut, a
fork of a fork, and two forks running beside their parent all worked (review
probes, §14).

A fork is continued as a copy is (§4.2, step 5). The fork point for a child
is found in the fork: fork at the latest checkpoint, read the plan there,
and when it has a cut, discard the fork and fork again at the last
checkpoint before the cut.

Everything of §4 applies to a fork: the preconditions, the ending of
leftovers before a snapshot, the class checks on the whole program, the cost
rule and the tag. A fork has a copy id as a copy has; it is recorded in the
search log and in the first row of the fork's `checkpoints.jsonl`, with the
cut, the prefix digest and the snapshot id. `fork_run` adds these refusals:

| Condition | Code |
| --- | --- |
| No checkpoint row for the cut, or its snapshot is not in the store | `fork_checkpoint_missing` |
| The prefix has a pending start or an unsettled coordinator | `fork_prefix_unsettled` |
| The prefix holds a commit of a class other than `command` or `provider` | `fork_prefix_class_unsupported` |
| The parent is a run-reference child or a confined child | `fork_child_run` |
| Less disk free than the floor | `fork_disk_floor` |
| The destination exists | `fork_destination_exists` |

## 7. The container route

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
  same-path precondition of §4.3 by construction.
- Open prerequisites: how a workflow's steps run inside a task container
  (roadmap Phase 5b, step 9); a fresh network sidecar and relay for a forked
  container (the launcher of the long-horizon plan's step 5).

## 8. The pause at a usage limit, and two options

**The pause.** How a subscription usage limit appears in a provider attempt
is not recorded yet. A call that a limit cuts off is an ordinary failed
attempt today: a `failed` row and a failed terminal, exit 1 (probe C10).
Part 1 does not change when the form is known: exit status 3 means the
command line's own stop and nothing else, and a pause is the absence of the
next invocation, not a flag and not a journal row. Part 2 adds, in the
harness:

- a stop-reason record `{reason, code, site, identity, attempt_dir, exit}`
  whose `reason` is an open set: `boundary`, `completed`, `cap`, `failed`,
  `waiting`, `refused`, with `paused` reserved;
- a classifier, supplied by the study, that turns a `failed` reason and its
  attempt's evidence into `paused` once the recorded form of a limit exists.
  Until then every provider failure pauses the study for a ruling;
- the wait until the limit resets, and the continuation of each cut
  evaluation from its kept copy (§4.6).

**A durable mark for readers.** If Part 2 adds a mark that lets `report` and
the monitor show a requested stop as such, it is written at the end of the
invocation, after the last append, and it is valid when nothing is pending.

**Copies on the host without a refusal.** A harness can keep one path per
lineage tree and rename copies into and out of it, running the siblings of a
tree in turn; a stopped candidate holds no process, and the route needs no
privilege.

## 9. What brings Part 2 forward

| Evidence | What it brings forward |
| --- | --- |
| A fork point is needed after the fact: a child whose first changed step lies before its parent's latest kept copy, in a space where the mutant plan's T3 measures a saving in priced tokens that a study states as worth the work | §6: per-step checkpoints and `fork_run` |
| Whole copies cost too much disk or time: the kept copies of a study exceed the disk budget of §6.2, or a copy takes longer than a stage's start-up budget | §6: the store shares blocks between snapshots; forks are still full copies |
| A measured saving: T3's figures for the space being searched, times the number of evaluations, exceed what copies at stages save by the margin the study's plan sets | §6 |
| The comparison step's design puts the workspace in the container, and the long-horizon launcher exists | §7 |
| The recordings show a limit's form | §8, the pause |
| A study on the host needs copies of real agent runs | §8, the renamed path |

For the first space the saving of sharing prefixes is fixed: 72 planner
calls and 18 first coder calls of the 27-point grid, 90 in all. With one
round and M milestones a run makes 4 + 2M provider calls, so the share is
90 / (27 × (4 + 2M)): 42 percent at M = 2 (the measured stand-in run of
eight calls), 28 percent at M = 4, 17 percent at M = 8, and less with a
second round. Whether stops and copies deliver that saving on the first
study's tasks waits for §4.1's prerequisite.

## Both parts

Sections 10 to 17.

## 10. Contracts to amend when Part 1 is built

| Contract | Change |
| --- | --- |
| [`specs/cli.md`](../../specs/cli.md) | The flag on `run` and `resume`; exit status 3; `stop_after_reached` and `stop_after_unknown_site` in the diagnostics tables; the unknown-site refusal after preflight step 7; the parallel-map and host-request rules; one sentence that a run stopped by the flag reads `interrupted` in `report`, as one stopped by the cap does |
| [Lifecycle guide](../runtime_execution_lifecycle.md) | One section: stopping at a site; the run reads `interrupted`; `resume` continues it |
| [Evaluated execution](workflow_lisp_evaluated_execution.md) | §8.1: the stop beside the spend cap |
| [`specs/observability.md`](../../specs/observability.md) | One sentence: a run stopped by an invocation limit has the view's `interrupted` status and is classified `CRASHED` in a registered workspace. No rule changes |
| [`specs/state.md`](../../specs/state.md) | The `closure` proof says that a live attempt of any run root that carries the same run id counts. No file and no view field is added |
| [Structural search driver](orc_structural_search_driver.md), Execution Contract | "Cross-candidate provider or effect reuse is disabled initially" gains the copy at a stop as the admitted form. "The logged run id and state dir are the join key" gains: for a copied run the copy id. "`resume` … continues the same pinned evaluation after an incident … never as a replicate" gains: so does a continuation from that evaluation's kept copy, and the abandoned root is kept as the incident's evidence |
| [Program-search boundaries](workflow_lisp_program_search_boundaries.md), invariant 1 | The text below |
| [Capability matrix](../capability_status_matrix.md) | One row |

When Part 2 is built, `specs/state.md` gains `checkpoints.jsonl` in the
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
>      committed effect or is completed (a whole copy, or a fork restored
>      from a snapshot of that moment), and continued by public `resume`. A
>      candidate program passes the ordinary compiler in `resume`'s fresh
>      build, and each inherited result is reused only where rule C10 of
>      evaluated execution admits it. The continuation does not write the
>      source run's workspace or run root. A copy keeps the source's run id,
>      so its lineage record holds a copy id of its own, its evaluation id
>      and candidate program, the source's copy id and state root, the
>      journal byte length at which the copy was taken, and the digest of
>      the journal bytes before it.
> - A copy imports committed results as data. It imports no program text and
>   no policy. No `eval`, hot swap, dynamic linking or checkpoint import
>   turns candidate data into executing code.
> - An execution is `inherited` when its journal holds results that were
>   produced under another candidate program or under another evaluation id:
>   a copy continued under a different candidate program or a different
>   evaluation id. An `inherited` execution is search evidence under
>   invariant 4. No readout that selects uses it: the frontier computation,
>   finalist selection and promotion each refuse an `inherited` row, and a
>   row without a lineage record, and do not skip it silently.
> - An execution continued from a copy of its own evaluation's earlier
>   state, under the same candidate program and the same evaluation id,
>   after an incident, is `whole`, provided the abandoned root is kept as
>   the incident's evidence.
> - Executions that share a prefix digest count as one observation of that
>   prefix.
> - The runtime has no path that is specific to a candidate. A limit of one
>   invocation that any run may use (the spend cap, a stop after a named
>   effect site) is part of the public `run` and `resume` contract and knows
>   nothing of candidates, populations or selection.

The last item replaces "The runtime is not changed." The boundaries
document's change note records the amendment. A run continued in place under
an accepted edit also holds results produced under another program; by the
definition above it is `inherited`.

## 11. Soundness and its limits

**What holds.** After a copy or a fork is continued, the active journal is
one that an uninterrupted run of the child program could have written, with
the reused effects returning their recorded results: the replay equivalence
of C10, checked by the unchanged strict replay at acceptance. The workspace
at the first new effect is the parent's at the stop, in the sense of §4.3
for a copy and of §6.2 for a fork, with no process left from earlier steps
on either side.

**What does not.**

- State outside the copied directory is shared (§4.3).
- An effect of the prefix can have read something C5 lists as undeclared
  (clock, network, a file opened by computed name). The copy reuses its
  result as `resume` does.
- A copy exposes its ancestry: a stored program artifact holds the absolute
  path of the parent's source (probe). The contamination scan of a study
  adds the other candidates' directory names, and for Part 2 the store's
  root, to its patterns.
- A stage that lasts longer than the provider's prompt-cache lifetime may
  pay cache-write where an uninterrupted run pays cache-read, which would
  bias a deployed cost taken under staged evaluation. This is a hypothesis;
  nothing here tests it.

## 12. What this makes harder

- A stop on request reads as a crash in `report`, the dashboard and the
  monitor. A harness filters by exit status; an author reads `interrupted`.
- Several run roots carry one run id. The liveness check is no longer per
  run root; plan tokens do not name a root; a registry or a run-reference
  root keyed by run id would confuse them.
- Summing `report` over a study counts each prefix once per root.
- Every copy and every restored fork is a full workspace on disk.
- The program lives in the copied directory, where an agent can read and
  edit it. The harness writes it again before each invocation.
- A stage is a full site key. A mutation that moves a site must say where it
  went, and a study keeps its stages on labelled sites.
- Copies of real agent runs on the host are mostly refused, because values
  hold the workspace's path. Copies wait for a same-path workspace.
- Every process a step leaves is ended at every stop. A program that keeps a
  server between steps cannot be stopped or copied.
- Every copy shares its ancestors' luck. An analysis that treats siblings as
  independent overstates what it knows.
- In Part 2: modes and times need a manifest; one `git init` in a
  subdirectory ends checkpoints in the store for the rest of that run; git
  becomes a dependency of the checkpoint module.
- A change of the digest rule (readiness item R2) strands a copy as it
  strands any run in flight.

## 13. Deliberately left out

- A mark, a record or a reader change for a requested stop.
- Any change to the spend cap.
- A mount namespace, or any other way to give two host directories one path.
- Part 2 as a whole, until §9.
- Copies of candidates with run references, host requests, Agent Sessions or
  parallel maps. They get the stop and the resume.
- Restoring a workspace in place under a live run root, which would lift
  "workspace files are not rolled back" for edit and continue.
- A public `orchestrator copy` or `fork` command.
- A cache of effect results across runs keyed by input digest.
- Any stopping rule.

## 14. Probes

Stand-ins only; no provider was called. The stop was patched into the probe
process at the call sites of §3.1 with the matching rule of §3.1, and the
process exited 3 on a stop. The program under test had four steps (`plan`, a
command `built`, `work`, `review`; three metered provider stand-ins and one
command) in a git workspace. S1 and the F probes ran at `b399076b`; S3 to
S7 and the C probes other than C7 on `main` at `e0a978ad`; S2, S8, K1, K2,
C7 and the build files of S4 on `main` at `1e090cc8`.

| # | Question | Result |
| --- | --- | --- |
| S1 | Does a stopped run resume with no step dispatched twice? | One commit per invocation: four invocations, four dispatches, every one at attempt 1, no journal row for a stop |
| S2 | Does a named site stop the run there? | `--stop-after 'workflow:main::run / built'`: exit 3; the journal ends with `built`'s commit |
| S3 | A loop site | Key `workflow:main::run / loop:pads[*] / padded`: the first invocation ends after the commit of `loop:pads[1] / padded`, the second after `loop:pads[2] / padded`, the third completes; no attempt above 1 |
| S4 | An unknown site, and what a build writes | A misspelt site is found against the site table of the built program. `run --dry-run` leaves `.orchestrate/build/<key>/closed_program.json` and `manifest.json` and no run root |
| S5 | An agent-turn site | Stop after turn `a1` (allocation, start, commit, `settled`); `resume` runs `a2`; two calls of the stand-in in all |
| S6 | A host request after the site | With the stop: the commit before the request and nothing else. `resume`: `started`, `suspended`, the `waiting` line, as in a run without the flag |
| S7 | A parallel map | Five items, `:parallel 2`, every site named: 2, 4 and 5 commits after three invocations, nothing pending at each stop, no attempt above 1 |
| S8 | Does the journal predicate tell where a run stands? | Requested stop after `built`: true for `built`, false for `work`. Killed in the middle of `work`: false. Completed: false. Stopped by the cap after `built`'s commit: true for `built`, exit 1. `report` of the requested stop: `interrupted`; `state.json`: `running` |
| K1 | Which edits keep a site key? | The table of §3.4. An effect without an authored label has the key `run / #1` |
| K2 | The seeds' keys | `milestones`, `staged`, `designed` and `roles` at `c93a6954` compile on `main`; the keys of §3.4; 50, 40, 49 and 50 lines |
| C1 | What does `cp -a` at a stop carry? | 144 entries, run root included: type, mode, modification time, link count, content and link target all equal; the hard link pair shares an inode; modes 600 and 444; the named pipe; the nested repository without a commit; a file dated 2020. 0.03 s for this small workspace |
| C2 | Does a child program in the copy reuse the prefix? | Plan: kept three, cancelled none, no cut. One dispatch, `review` at the child's effort, in the copy; the parent's journal unchanged. The parent then resumed and ran its own `review` |
| C3 | What are the cost figures of the copy? | Own attempts by the cut: one, USD 0.00035. Inherited: two, 0.0007. `report` of the copy: three, 0.00105. The parent, continued, made three provider attempts too; four calls were dispatched in all. The cap's figure for the copy's three: 0.00525 |
| C4 | Does the layout with the run root beside the clone copy? | `--state-dir ../runs`, `result_root: ../runs/<id>`; the evaluation directory copied; plan kept three, cancelled none; one dispatch in the copy's clone |
| C5 | A copy of a completed run, for a child that appends a step | Plan: kept four, cancelled none; the new step dispatched once |
| C6 | Can a copy write into its parent? | Yes: §4.3. The search of the copy's journal finds the parent's path |
| C7 | What do steps leave, and what finds it? | The table of §4.4. Before the kill two walks one second apart differed; after it they agreed, and again two seconds later; the run resumed and completed |
| C8 | Do copies of one run affect each other? | A command fails in a copy with no sibling alive: `closure: unchanged`. The same while a sibling's provider step is alive: `closure: changed` |
| C9 | Which figure does a cap need? | `report` 0.0007, the cap's 0.0035 for two inherited calls. `--max-cost-usd` at `report`'s figure plus 0.0005: `spend_cap_reached` before the stage's call. At `spent()` plus 0.0005: the stage runs |
| C10 | Is a copy of the kept copy a clean retry? | The call is cut off: a `failed` row, a failed terminal, exit 1, a partial file. Capped resume in place: `spend_cap_unmetered`. In a copy of the copy kept at the last stop: `work` and `review` once each at attempt 1, exit 0, no partial file |
| F1 | Does a fork from the git store reproduce the workspace? | Content, executable bit, link targets and empty directories equal: 59 entries, 42 under `.git` |
| F2 | Edited-program resume on a fork | Kept three, cancelled none; one dispatch at attempt 1; the journal is the prefix, one `rebased` record with a null cut, the step, the terminal |
| F3 | A fork's cost | Own: one attempt, the changed call. `report`: the whole program |
| F4 | A fork as a clean retry | As C10, from a checkpoint |
| F5 | The cost of a git snapshot | The table of §6.2; walks of the clone and its restore equal in content, 8,042 entries |
| F6 | Do workspace attributes alter stored bytes? | Without `--attr-source`: `a\nb\nc\n`. With it: `a\r\nb\nc\r\n`, as written |
| F7 | What does the git store not keep? | Mode 600 came back 664; a nested repository is a link entry without content |
| F8 | The container route | The table and list of §7 |

**Probes of the independent reviews that this page relies on and that were
not rerun for it:** a new run id diverges the first provider step (§4.5);
the `make` case, the user-level git configuration, the entries git drops and
the failing `git add` cases, the index lock (§6.2); forks beside a running
parent and a fork of a fork (§6.3); a daemon that changes its working
directory passes a check by working directory and by two walks (§4.4; probe
C7 found the same for the working directory).

## 15. Not verified and open prerequisites

| Item | State | Needed for |
| --- | --- | --- |
| Where a staged seed's workspace lives on a container task | Open: the design of roadmap Phase 5b, step 9 | Any copy on the long-horizon tasks (§4.1) |
| Whether stage signals predict the final result | Open: the first paid seed runs | Stopping weak candidates early (§4.6) |
| The placement of the unknown-site refusal | Read in `run_evaluated_workflow` and the resume preflight; the probe gate refused at the first effect | The first test of the flag |
| A run reference, a host request, an agent or a parallel map in the suffix of a copy | Read, not probed; refused | Lifting a refusal of §4.3 |
| Whether real agent runs put the workspace's path into typed values | Not observed: no provider was called. The expectation rests on how the CLI's file tools take paths | How often `copy_names_parent_path` fires |
| File content in a workspace that embeds the workspace's path | Not searched (§4.3) | A copy at another path |
| Ending the processes of a task container | Not probed | §4.4 on a container task |
| How a subscription usage limit appears in a provider attempt | Not recorded; the long-horizon recordings are finding out | §8 |
| Whether a long stop changes metered cost through the prompt cache | A hypothesis (§11) | Reading the cost of staged runs |
| A program that reads its run id (X1) or a provider's result path (X4) in a copy | Read, not probed | Stating what such a program reuses |
| The manifest of modes and times, the completeness check and the hardened git configuration | Specified from the reviews' probes; not run for this page | Part 2 |
| A sidecar and relay for a forked container | Open: the long-horizon launcher | §7 |

## 16. Open questions for the coordinator

| # | Question | Recommendation |
| --- | --- | --- |
| 1 | The seed's `repo` input holds the repository's absolute path in its scripted runs, which a copy at another path refuses | `repo` becomes `.` or is dropped when the seed is frozen, and the harness places program, manifests and inputs inside the workspace. With a same-path workspace the refusal does not arise |
| 2 | Does the comparison step's design mount the task's work at a fixed path, or keep it in the container? | A mounted directory at one path, if the task's verifier allows it: Part 1's procedure then applies as written and Part 2's container route is not needed for the first study |
| 3 | May a study retry a cut-off call in place without a cap? | No: the workspace holds the cut call's partial files and `report` turns partial. Continue from the evaluation's kept copy |
| 4 | Where does the procedure's code live? | With the search harness under `experiments/`; the default suite pins the runtime's side without importing it |

## 17. Increment note for the planner

This note is planning input, not contract; the plan owns sizes and order.
Nothing is started before the two conditions of "When to build" hold.

| Increment | Contents | Hours |
| --- | --- | --- |
| The flag | The check at three call sites, the field, the flag on `run` and `resume`, the unknown-site refusal at both places, exit status 3, the tests of §5 marked "Default suite" | 11 |
| The procedure | The copy with its preconditions and codes, the log row, the ending of leftover processes, the harness's tests | 9 |
| Contracts | The amendment and the other rows of §10 | 2 |
| Review and fixes | | 5 |
| Part 2, when selected | Snapshot and restore with manifest and completeness check 12; `advance` and checkpoint rows 6; `fork_run` and its refusals 10; tests 6; the container route 16 to 24; the stop-reason record and the limit classifier 6 | |

Part 1 is 27 hours. The flag edits `specs/cli.md` and
`orchestrator/cli/main.py`. No increment needs a recorded journal fixture.
The measurement of how much each mutation reuses belongs to the mutant
plan's task T3 and is not an increment of this design.
