# ORC Search Checkpoints: Stop At A Stage, Snapshot The Workspace, Fork A Run

**What this page is.** The design for readiness item R1 of
[roadmap Phase 6](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#phase-6-program-evolution):
a search over workflow programs stops a candidate at a named stage, keeps a
snapshot of its workspace at every committed step, and starts a child program
from a parent's step so that the child pays for its changed suffix.

**Status.** Proposed; not accepted and not implemented. Nothing here is
available in the checkout. Hypothesis H-E2 of the roadmap is what the design
serves; it makes no claim that H-E2 holds.

**What owns the behavior today.** [Evaluated execution](workflow_lisp_evaluated_execution.md)
(the journal, rules C8 and C10, §8.1 to §8.5) and the
[CLI contract](../../specs/cli.md) ("Resume preflight precedence", "Spend
cap") own `run`, `resume` and the plan that `resume` prints under an edited
program. The [program-search boundaries](workflow_lisp_program_search_boundaries.md)
and the [structural search driver](orc_structural_search_driver.md) own what
a search may do with a run. Where this page and those documents differ, they
win until this design is accepted and they are amended as
[§3.7](#37-footprint-and-contract-changes) lists.

**Copy safety.** Nothing here is a recipe. The flag, the file name, the
record fields and the function names are proposals. The probe commands ran
on one machine and are evidence, not examples.

**Terms.** *Journal:* the run's `memo.jsonl`. *Site key:* an effect identity
as the checked site table spells it, with `[*]` in place of each loop or map
index (`machine.site_classes`). *Cut:* a journal byte offset that lies
immediately after a `committed` record. *Snapshot:* the stored content of a
workspace. *Checkpoint:* a cut together with the snapshot taken there.
*Fork:* a new run root made from a checkpoint. *Prefix:* the journal bytes
before a cut. *Stand-in:* a local script that plays a provider; no model is
called. A campaign `checkpoint` in the
[cumulative campaigns design](orc_structural_search_cumulative_campaigns.md)
is a different object, the saved state of a campaign.

## 1. Conclusion

The three acceptance checks of R1 are met by one invocation flag and one
module, with no change to the journal, the memo records, the run header or
`resume`. Probes with stand-ins showed each check ([§6](#6-probes)).

1. **Stop.** `--stop-after SITE` refuses the next new attempt once an effect
   at that site has committed in the invocation. The refusal has the shape of
   the spend cap's: no journal row, no terminal, and `resume` continues. A
   run driven one commit at a time dispatched each of four steps once.
2. **Checkpoint.** While a run is stopped after a commit, the controller
   stores the workspace in a git object store outside every workspace and
   appends one row (cut, snapshot) to `checkpoints.jsonl` beside the journal.
   The runtime does not read that file.
3. **Fork.** A fork restores a checkpoint's snapshot into a new directory and
   copies the run root cut at that byte: header, program artifacts, journal
   prefix and the prefix's attempt directories. The fork keeps the parent's
   run id and header. The existing `resume`, with
   `--accept-changes=plan-<token>` when the child program differs, continues
   it; the plan then cancels nothing. In the probe the child dispatched its
   one changed step, at attempt 1, in a workspace equal to the parent's at
   that step in every file, link, executable bit and empty directory.
4. **Cost.** The child's own attempts are those whose `started` record lies
   at or after the cut. `report` on the child prints the cost of the whole
   program, prefix included, which is the candidate's deployed cost; the
   search pays the own attempts.

The first implementation covers a git repository workspace and serial
programs made of command and provider steps. A container task workspace is
measured and outlined here and waits for the long-horizon launcher and for
the design of how a workflow's steps run inside a task container.

Four findings limit what R1 buys, and the coordinator should read them before
scheduling it ([§9](#9-open-questions-for-the-coordinator)):

- A dimension that is a bound input cannot be varied in a fork: `resume`
  refuses a changed input (probe). The searched value must be program text.
- The long-horizon seed's scripted runs bind the repository's absolute path
  as an input and keep the program outside the workspace. A fork needs the
  program files inside the workspace and no absolute workspace path in an
  input.
- For the first search space (an effort level per role) a role acts early, so
  the shared prefix is short: a hand count on the seed's site table gives a
  saving of about 17 to 28 percent of provider calls for a full grid. The
  stop at a stage and the clean retry after a call is cut off are the larger
  gains there. Suffix mutations keep more.
- Boundary invariant 1 names public `run` as the way a candidate execution
  starts. A fork is a second way and needs an amendment before code.

## 2. What exists today

Each row was established at commit `b399076b` by the command shown, in a
scratch directory, with stand-ins on a closed `PATH`. "Read" marks a fact
taken from code or a contract and not run.

| # | Finding | Command | Outcome |
| --- | --- | --- | --- |
| E1 | `resume` of a completed run changes nothing | `orchestrator resume RUN_ID` on a completed run of four command steps | Exit 0, the recorded value, no dispatch, journal bytes unchanged, 0.56 s |
| E2 | Under an edited program `resume` prints a read-only plan | Change the argument of step three; `orchestrator resume RUN_ID` | Exit 2, `resume_program_changed`; kept `s1`, `s2`; cancelled `s3`, `s4`; the cut at `s3`; a `--accept-changes=plan-<token>` command; journal bytes unchanged |
| E3 | The plan is a library call | `rebase.plan_resume(run_root, workspace)` | A `Plan` with `record`, `cut`, `kept`, `cancelled`, `runs_first` and `token`; no lock taken, journal bytes unchanged |
| E4 | A copy of the whole workspace, run root inside, is a working run | `cp -a ws ws2`; `resume` in `ws2` | Unchanged program: exit 0 with the recorded value. Edited program: the same plan and the same token as in the original |
| E5 | Edited-program resume on that copy reuses the prefix | `resume RUN_ID --accept-changes=TOKEN` in `ws2` | One `rebased` record; `s3` and `s4` dispatched once in `ws2`, at attempt 2; `s1` and `s2` not dispatched; the original's journal unchanged |
| E6 | The copy's workspace is the parent's final state, not the state at the cut | Read the file every step appends to, in `ws2` after E5 | `s1 s2 s3 s4 s3 s4`; a fresh run of the edited program gives `s1 s2 s3 s4` |
| E7 | A run root cannot take another name | `cp -a runs/RUN_ID runs/RUN_ID-b`; `resume RUN_ID-b` | Exit 2, `memo_inconsistent`: run id differs from its root |
| E8 | A run root cannot move relative to its workspace | Copy the run root to another directory; `resume RUN_ID --state-dir DIR` from the same workspace | `resume_result_root_changed` |
| E9 | A changed input is refused | Edit the `--input-file` of a completed run; `resume` | `resume_inputs_changed`, naming the input |
| E10 | A committed run reference breaks a copied run | Copy a completed run whose one effect is a run reference; `resume` in the copy | Exit 2, `run_ref_evidence_invalid: child_request_binding_invalid`. The child request records the parent's absolute run root |
| E11 | An Agent Session cannot continue from another directory | Stop a two-turn agent run after turn one; copy the workspace; `resume` the copy, then the original | The copy: `agent_policy_mismatch` (the allocation binds the working directory), no dispatch. The original then runs turn two |
| E12 | Nothing records workspace state per step | List the run root and the keys of every journal row | The run root holds `run.json`, `closed_program.json`, `memo.jsonl`, `state.json`, `run.lock` and `effects/`. A `started` or `committed` row holds digests of the files a command declares (`implementation_files`) and of the input parts. No row or file describes the workspace |
| E13 | An invocation limit already stops a run cleanly | `tests/test_workflow_evaluated_spend_cap.py::test_cap_stops_before_the_next_provider_call_and_a_higher_cap_resumes` | Passes: the capped run stops before its second provider call with no row for the refusal, and the resume completes with two dispatches in all |
| E14 | After a provider call is cut off, a capped resume is refused | Make the second provider call exit 1 with no result line; `resume RUN_ID --max-cost-usd 1` | `spend_cap_unmetered`, cause `attempt_unmetered`. The workspace holds the cut call's partial files |
| E15 | `report` and the cap count every attempt directory under the run root | `report --format json`, and `providers.usage.spent`, on a fork that holds copied attempts | Both include the copied attempts |
| E16 | The run id is a value a program can read, and the header fixes the run root's place | Read: evaluated execution §4.4 (X1, X4) and §8.4; `host_input._request_id` | X1 gives a program its run id; `result_root` ends in the run id; a host request id binds the run id and the header digest |
| E17 | Serial steps run in the workspace directory | The probes' stand-ins logged their working directory. Read: the drafting guide documents a launch directory (`:workspace`) for parallel-map items, and no serial form was found in it | Every serial stand-in ran in the workspace root |
| E18 | The locks belong to a workspace and a run root, and a copy has its own | Start a run with a slow step; during it start a second `run` in the same workspace, and a `run` in a copy of the workspace | Same workspace: `workspace_run_already_active`. The copy: runs to its value while the first is still running |

What these give a search today: a copy made with `cp` is a fork of the
journal (E4, E5). It is not a fork of the workspace (E6), its cancelled
attempts stay counted in its cost (E5, E15), it keeps its name and place
(E7, E8), and it breaks on a run reference or an Agent Session (E10, E11).

What ties a run to its place, taken together: the run root's name is the run
id (E7); the header records where the run root lies relative to the
workspace (E8); a run reference records the parent's absolute run root
(E10); an agent allocation records the working directory (E11); the header
pins each bare interpreter by absolute path (read from `run.json`). The rows
of command and provider steps hold no absolute workspace path: they were
reused at another path (E4, E5 and probe P3). A step's workspace effects
live in the workspace directory itself, wherever the step wrote them, and no
record says what they were (E6, E12).

## 3. The design

### 3.1 A checkpoint is a cut and a snapshot

A checkpoint exists where the journal ends with a `committed` record and no
attempt is pending. The controller makes one while the run is stopped:

1. it stores the workspace ([§3.3](#33-workspace-snapshots));
2. it appends one row to `checkpoints.jsonl` in the run root:
   `{"kind": "snapshot", "cut": <byte offset after the commit>, "snapshot": "<id>"}`.

A fork's file starts with one row
`{"kind": "fork", "cut": <offset>, "prefix_sha256": "<digest of the bytes before the cut>", "snapshot": "<id>"}`
followed by the parent's snapshot rows up to that cut, so a fork can itself
be forked at an inherited step.

The file is evidence. The runtime does not read it, and a run without it, or
with a store that was deleted, resumes as before. A step without a snapshot
row cannot be forked at. No row is written after a failed or interrupted
attempt, because the workspace then holds partial work.

Why a file and not journal records: the reducer refuses an unknown record
kind, so every reader would change and an older build would refuse the run;
and a snapshot is not an effect result (rule M4).

### 3.2 Stopping at a stage boundary

**Flag.** `orchestrator run … --stop-after SITE` and
`orchestrator resume RUN_ID --stop-after SITE`; the flag repeats.

- `SITE` is a site key of the program the invocation executes. A value that
  is not in that program's site table is refused with exit 2 before any
  effect starts, so a misspelt boundary cannot let a run spend to its end.
- Where a new attempt would be reserved, the invocation refuses with
  `stop_after_reached` once a `committed` record of an identity matching a
  named site lies at or after the journal length the invocation found at its
  start. An effect reused from the memo is not stopped.
- The refusal is a preflight refusal like `spend_cap_reached`: no journal
  row, no terminal, exit 1, and the `resume` line. A later `resume` continues.
- A run whose last effect is the boundary completes with its terminal.
- The flag is not stored. It is checked before the spend cap.

**Place in the code.** The check sits beside `check_spend_cap`
(`evaluated/spend_cap.py`) and is called at the same two places:
`runtime.prepare_effect` and `agent_turns.prepare_agent_attempt`. The stop
set travels as `--max-cost-usd` does, as a field of `RunAuthority` that is
not stored. A host request (`request_input`) does not pass those places and
is not stopped.

**What a stage boundary is.** A boundary is a site key. The compiled program
lists them: `machine.site_classes(program)`. The long-horizon seed
(`milestones.orc` on branch `spike/long-horizon-seed`) compiles on `main` and
has eight sites. Six of them carry a typed stage result and are candidates
for a boundary:

```text
workflow:milestones::run / ready                       guides written
workflow:milestones::run / spec                        targets written
workflow:milestones::run / loop:state[*] / plan        a round's plan
… / built / body / loop:#1[*] / else / #1=workflow:milestones::milestone / loop:state[*] / #1
                                                       a milestone's review verdict
workflow:milestones::run / loop:state[*] / report      a round's visible check
workflow:milestones::run / loop:state[*] / else / #1   the acceptance verdict
```

A boundary should be an authored label. A generated ordinal such as `#1`
moves when a mutation inserts an unnamed effect before it (rule I4 of
evaluated execution), and the candidate then lacks the site and is refused
at launch, before spend.

**Why the existing means do not serve.**

| Means | Why it is not the stop |
| --- | --- |
| `--max-cost-usd` | It stops before provider-class starts on a dollar figure, cannot name a site, needs metered templates, and refuses after a cut-off attempt (E14). It stays the budget of an invocation |
| Killing the process when a `commit` line is printed | The next `started` record can already be durable; resume then dispatches that step a second time (evaluated execution §8.3) |
| `request-input` at each boundary | It changes the candidate: its effects, its digest and its line count; the deployed program would wait for a host |

### 3.3 Workspace snapshots

#### Git repository workspace (first implementation)

The snapshot is a commit object in a bare git store that lies outside every
workspace. The store is shared by all runs of a study, so a child's blobs are
its parent's.

- **What is stored.** Three entries under one tree: `work`, the workspace
  directory with every file, tracked, untracked or ignored, without `.git`
  and without `.orchestrate`; `git`, the content of the workspace's `.git`
  directory stored as ordinary files; and `empty.json`, the list of empty
  directories of both. The task repository's own object database is not
  written to, so an agent cannot see a snapshot through `git log --all`.
- **How.** `git --attr-source <empty tree> add -A -f` with `GIT_DIR` set to
  the store, once with the workspace as work tree and once with its `.git`
  directory as work tree, each with its own index file in the store; then
  `write-tree`, `mktree`, `commit-tree` and a ref. Restore is `read-tree` and
  `checkout-index -a` into an empty directory, then the empty directories.
- **Byte for byte means:** the same set of paths; for a regular file the same
  bytes and the same executable bit; for a symbolic link the same target; the
  same empty directories. `.orchestrate/` is outside the comparison, since
  the run root is copied by the fork. The comparison is made immediately
  after the fork: the first git command in a restored repository rewrites
  the stat fields of `.git/index`, which changes that file's bytes and no
  content (probe).
- **How it is checked.** A walk independent of git: SHA-256 of every regular
  file, each link target, each executable bit and each empty directory, in
  the stopped parent and in the fresh fork. Equal tree ids of two snapshots
  are a second, cheaper check.
- **Attributes.** `--attr-source` with the empty tree turns off the
  workspace's `.gitattributes`. Without it a file with mixed line endings
  under `* text eol=crlf` was stored normalized and lost bytes; with it the
  bytes were exact (probe, both sides).
- **Not reproduced.** Permission bits other than the executable bit (a file
  of mode 600 came back 664), ownership, timestamps, extended attributes and
  hard-link identity. A build tool that compares timestamps can behave
  differently in a fork.
- **Refused.** A nested repository is recorded by git as a link without its
  content (probe), so a snapshot whose tree holds such an entry is refused
  and the step has no checkpoint. Devices, sockets and pipes are not stored
  by git (read); a workspace that holds one is refused the same way.
- **Not captured at all.** Running processes; anything outside the workspace
  directory, such as the Python environment, caches under the home directory
  and a provider's native session files; the state of remote services.
- **Cost** on this machine, on a 250 MB clone of this repository (4,691
  work-tree files; the store on the same ext4 disk, where a copy cannot
  share blocks):

  | Case | Seconds | Store growth |
  | --- | --- | --- |
  | First snapshot of the clone | 7.3 | 151 MB |
  | Next snapshot, nothing changed | 0.17 | none |
  | Five files edited, one new 20 MB file, one commit by the agent | 0.74 | 20 MB |
  | A new 500 MB file that does not compress | 24.8 | 477 MB |
  | The snapshot after that, file unchanged | 0.36 | none |
  | First snapshot in a restored fork (cold stat cache) | 3.8 | none |
  | Restore into an empty directory | 1.7 | |

  With `core.compression 0` the first snapshot of the clone together with
  the 500 MB file took 16.0 s and 745 MB, against 32 s and 648 MB. A file
  that does not change costs nothing after its first snapshot. A workspace
  that writes large new binary files at every step is the wrong fit for this
  route.

#### Container task workspace (outline; not in the first implementation)

A long-horizon task runs in a task container under rootless Podman through
the Harbor harness, with the agent inside the container
([long-horizon plan](../plans/2026-11-13-long-horizon-task-family-and-seed-plan.md), D2).
Measured here with Podman 4.9.3, rootless, overlay storage, on a local
8 MB image:

| Case | Seconds | Image size |
| --- | --- | --- |
| `podman commit` after 50 MB written | 0.72 | 60.5 MB |
| `podman commit` again after 5 MB more | 0.87 | 65.8 MB; its top layer is 57.7 MB |
| `podman commit` after 1.1 GB and 20,000 small files more | 10.8 | 1.13 GB |
| Start a container from a committed image | 0.2 | |

- **The cost is cumulative.** Each commit stores the container's whole
  difference from its base image, not the difference from the last commit.
  Ten snapshots of a container that has written 1 GB cost about 10 GB and
  100 s. With 55 GB free this route affords snapshots at stage boundaries,
  not at every step, and the snapshots of a stopped candidate must be
  deleted. Restarting the container from each committed image would make the
  layers incremental; that was not tried.
- **Not captured** (probes): a running process (the fork had none of the
  parent's); a `tmpfs` mount; a bind-mounted directory. `podman container
  checkpoint` answers "checkpointing a container requires root".
- **Pause.** `podman commit` does not pause the container unless `--pause` is
  given (its manual page: the default is false). The controller snapshots a
  stopped run and passes `--pause`.
- **Other routes, not tried:** an overlay mount of one lower directory with
  an upper directory per fork; a bind-mounted work directory stored through
  the git route, which would leave system changes inside the container
  unrecorded.
- **Open prerequisites.** How a workflow's steps run inside a task container
  is open design work of the long-horizon plan (its step 9). A fork must
  also start a fresh network sidecar and relay, which belong to the launcher
  of that plan's step 5. The row format of [§3.1](#31-a-checkpoint-is-a-cut-and-a-snapshot)
  holds an image id in place of a commit id; nothing else in this design
  changes.

**Why git first.** The runtime's workspace is a host directory and serial
steps run in it (E17). The seed-set tasks and the seed's scripted scenarios
are git repositories. Per-step snapshots are affordable there (0.2 to 0.7 s)
and are not in a container. The container route has two open prerequisites
owned by another plan.

### 3.4 The controller

The controller is one function of the new module, `advance`, plus a decision
rule that the search supplies. The module knows runs, sites, cuts and
snapshots. It does not know candidates as a population, scores or selection
(boundary invariant 3): the loop over candidates and the rule live in the
search harness.

**`advance(workspace, run, until, …)`** runs one candidate to a boundary:

1. it invokes the public `run` or `resume` in a subprocess with
   `--stop-after` for every site of the program, so the invocation ends
   after one commit (for a container workspace: for the sites in `until`
   alone);
2. it reads the journal; when the last effect record is a commit and nothing
   is pending, it makes the checkpoint of §3.1;
3. it repeats until the last committed site is in `until`, the run has a
   terminal, or the invocation ended for another reason;
4. it returns why the run stopped, read from the journal first and the
   diagnostic code second: `boundary`, `completed`, `cap`
   (`spend_cap_reached`), `failed` with the code and the attempt directory,
   or `waiting` on a host request.

An invocation of the probe's program costs about half a second of start-up
(E1) and replays the prefix; for agent steps of minutes this is noise. The
journal is the controller's state: after a crash it reads the journals again
and continues. Each candidate has its own workspace and so its own locks, so
candidates advance side by side (E18).

**How "weak" is decided.** The rule is an input:
`decide(observations) -> the runs that continue`. An observation is a run's
committed typed values at the boundary (a verdict variant, a check report's
counts), its cost so far and its stop reason, all read from the run's view.
The module ships no rule; the default keeps every run. A stopping rule may
be used in a study when the stage-signal readout of roadmap Phase 5b (step 9:
the visible check's pass fraction and the agents' typed verdicts against the
final verifier result) shows that the signal predicts the end, and its
threshold is frozen in the study's criterion before spend. The rule is
applied when every run of the rung has reached the boundary or has failed. A
stopped candidate has no whole-program result: it leaves the comparison, is
not scored zero, and its spend stays in the search cost.

**Budgets.** Three limits act, and stopping a weak candidate saves the first
two.

- *An invocation's cap.* `advance` passes `--max-cost-usd`. The cap counts
  every attempt directory under the run root, so in a fork it counts the
  inherited prefix (E15): the controller passes the prefix's figure plus the
  stage's allowance.
- *The study's ceiling.* The harness reserves a stage's allowance before each
  invocation and settles it afterwards, as the long-horizon plan's D4 does
  for an attempt.
- *The subscription's usage limit* (owner decision 18: no API key; runs share
  the limit with the owner's sessions and pause at it). A run stopped at a
  boundary holds no process and costs nothing while the study waits, so a
  pause is the absence of the next invocation. A candidate that waits is not
  weak for that reason.

**A call cut off by a limit.** The attempt fails, its partial files stay in
the workspace, and a capped resume in place is refused (E14). The controller
does not resume such a run in place. It forks the run at its last checkpoint
under the same program and continues the fork: the retry then starts from
the clean workspace of the last commit, and the cap works again because the
cut attempt is not in the fork (probe P5). The cut attempt's usage, a lower
bound, is search cost. Telling a usage limit from another provider failure
needs the forms the long-horizon launcher records; that classifier is an
input of the harness and an open prerequisite
([§7](#7-not-verified-and-open-prerequisites)).

### 3.5 Fork semantics

**`fork_run(parent_workspace, run_id, cut, store, child_workspace)`** reads
bytes that do not change once written (the header, program artifacts, the
journal before the cut, attempt directories of finished attempts, the
snapshot; rules M1 to M3 and §8.2 of evaluated execution), so it takes no
lock. Every probe forked a stopped or completed parent; a fork from a parent
that is running past the cut follows from those rules and was not probed.
It builds the child under a temporary name and renames it into place.

| Part | In the fork |
| --- | --- |
| Run id, `run.json` | The parent's, byte for byte. A program can read its run id (X1), the result root ends in it (X4) and a host request id binds it and the header digest (E16), so a new id would change values and lose the prefix |
| Program artifacts | Copied: the first program and each one a `rebased` record of the prefix names |
| Journal | The bytes before the cut. This is the journal a kill immediately after that commit would have left |
| Attempt directories | Copied for every `started` record of the prefix. A later step can name a committed result file (X4) |
| Workspace | Restored from the checkpoint's snapshot into the new directory; the run root sits at the header's `result_root` under it |
| `checkpoints.jsonl` | The fork row and the parent's snapshot rows up to the cut |
| `state.json`, locks, build cache | Not copied; each is rebuilt or created by the first invocation |
| Snapshot store | Shared, outside the workspace. Later snapshots of the parent are not reachable from the child's directory |
| The parent | Unchanged |

**Identity.** A fork is a branch of a run: its identity is its run id
together with its run root's location. The fork row's `prefix_sha256` equals
the digest of the same bytes in the parent and in every sibling, and is the
key by which an analysis groups runs that share a prefix. The search log
joins on the state directory, which is already the driver's rule for
external runs.

**Continuing a fork.**

- *Same program* (a repeat of the suffix, or the clean retry of §3.4): plain
  `resume`. Nothing is written but the new attempts.
- *Child program:* the harness writes the child's program files into the
  fork's workspace, reads the plan (`rebase.plan_resume`) and accepts its
  token with `resume --accept-changes=plan-<token>`.
- **The plan of a fork cancels nothing.** The harness accepts a fork's plan
  when its cut is null and it keeps every commit of the prefix. A plan with a
  cut means the child differs before the fork point: the harness discards
  that fork and forks again at the last checkpoint before the plan's cut.
  The fork point for a child is found the same way: plan the child against
  the parent's journal, and take the last checkpoint before the first
  attempt the plan would cancel.

**Effect identities and the program digest.** A fork changes no identity:
identities do not contain the run root, and attempt ordinals continue from
the prefix. The header's `program_digest` is the first program of the
lineage, the root ancestor's. The child's program is the one named by the
`rebased` record that the acceptance appends after the prefix; `report`
lists both and marks each row with its program. Input digests are computed
again in the child's workspace and were equal for command and provider steps
at another path (probe P3). A provider's result path read by a program (X4)
holds the workspace's absolute path; an effect that reads it has a different
input in a fork, and the plan then has a cut (read, not probed).

**Metering.**

- *Own attempts* of a run are those whose `started` record lies at or after
  its fork row's cut, or all of them when it has no fork row. *Inherited*
  attempts are the others. `own_usage(run_root)` sums the first set with
  `providers.usage.summed_usage`.
- *Search cost* is the sum of own attempts over every run root of a study:
  parents, children and abandoned branches. Each attempt is paid once.
- *Deployed cost* of a candidate, the cost axis of the Pareto comparison
  ([driver](orc_structural_search_driver.md#objective-selection-and-local-observations)),
  is what `report` prints for its run: inherited prefix plus own suffix. It
  is the cost of running that program whole with the prefix's outcomes. The
  prefix cost is thus attributed to every candidate that inherits it and
  paid once by the search.
- Among siblings the prefix cost is a common term, and so is the prefix's
  luck. Their quality observations are not independent: comparisons are
  reported over several independent parent prefixes (roadmap, H-E2), grouped
  by `prefix_sha256`.

**Refused, before any write.**

| Condition | Why |
| --- | --- |
| No checkpoint row for the cut, or its snapshot is not in the store | There is no workspace to restore |
| The prefix has a pending start or an unsettled coordinator | The snapshot would hold work in flight |
| The prefix holds a commit of a class other than `command` or `provider` | A run reference fails in a copy (E10); an agent allocation binds the working directory, and two branches would share one native session (E11); a phased provider and a host request were not probed |
| The parent is a run-reference child or a confined child (`rebase._run_ref_parent`, `authority.confined`) | Its parent run re-reads its journal with one program; a branch would be unknown to that ledger |
| The header's `result_root` leaves the workspace (a leading `..`) | The child's run root would fall outside its own directory |
| The program has a parallel map (`parallel.has_parallel`) | The stop inside a batch was not probed |
| The child workspace directory exists | A fork writes into a new directory |

**Layout a fork needs** (the harness's duty, checked by the refusals above
and by the plan):

- the program source, the manifests and any input file lie inside the
  workspace, so the header's locators are relative. A locator outside the
  workspace is stored absolute and would make every fork read the parent's
  files;
- no bound input and no prompt holds the workspace's absolute path;
- the run root lies under the workspace (the default
  `.orchestrate/runs/RUN_ID`);
- the harness writes the program files again before each invocation, since
  an agent can edit files in its workspace.

### 3.6 Soundness and its limits

**What holds.** After a fork is continued, the active journal is one that an
uninterrupted run of the child program could have written, with the reused
effects returning their recorded results: this is the replay equivalence of
C10, checked by the unchanged strict replay at acceptance. The workspace at
the first new effect equals the parent's at the cut in the sense of §3.3. In
the probe a fork continued under the parent's program ended with the work
tree of an uninterrupted run.

**What does not.**

- State outside the workspace is shared, not forked: an environment a step
  installs into, files under the home directory, remote services.
- An effect of the prefix can have read something C5 lists as undeclared
  (clock, network, a file opened by computed name). The fork reuses its
  result as `resume` does.
- A fork exposes its ancestry: a stored program artifact holds the absolute
  path of the parent's source (probe). This is hygiene, not isolation
  (boundary invariant 6). The contamination scan of a study adds the store's
  root and the other candidates' directory names to its patterns.
- A fork's evidence guides a search. Promotion and frontier membership of a
  finalist rest on independent whole runs, as boundary invariant 4 requires
  of whole-program evidence.

### 3.7 Footprint and contract changes

New: one module, `orchestrator/workflow/evaluated/checkpoints.py`, with
`snapshot_workspace`, `restore_workspace`, `advance`, `fork_run` and
`own_usage`; one test module. It imports the journal readers and is not
imported by the runtime.

Changed: `evaluated/spend_cap.py` (the stop check), `evaluated/authority.py`
(one field that is not stored), `cli/main.py` and
`cli/commands/evaluated.py` and `cli/commands/resume.py` (the flag, along the
path of `--max-cost-usd`), `cli/recovery.py` (one row).

Each new thing, and why an existing one cannot serve:

| New | Existing candidate | Why it does not serve |
| --- | --- | --- |
| `--stop-after` | `--max-cost-usd`, a kill, `request-input` | §3.2 |
| `checkpoints.jsonl` | A journal record; the search log | A journal record changes the reducer and every reader. The log can hold the lineage, but a run that is copied or read alone would not know which attempts it inherited |
| The snapshot store | The task repository's own `.git` | An agent would see every snapshot, a child would see its parent's later ones, and `.git` itself would not be captured |
| `fork_run` | `cp -a` and `resume --accept-changes` | E6 and E5: the copy has the parent's final workspace, and its cancelled attempts stay in its cost; a committed coordinator after the cut refuses the plan |
| `advance` | A shell loop in each harness | The snapshot must be taken between a commit and the next start, and the stop reason read from the journal, once and in one place |

Contract text to amend when this design is accepted:

- [Program-search boundaries](workflow_lisp_program_search_boundaries.md),
  invariant 1: a candidate execution also starts as a fork of a registered
  run, continued by public `resume` under the candidate program through the
  ordinary compiler and rule C10. "No checkpoint import turns candidate data
  into executing code" stays true: a fork imports results, and each one is
  reused under C10's checks or not at all.
- [Structural search driver](orc_structural_search_driver.md), Execution
  Contract: "cross-candidate provider or effect reuse is disabled initially"
  gains the fork as the one admitted form; `--state-dir` outside the clone
  is not usable with a fork.
- [CLI contract](../../specs/cli.md): the flag, its refusal for an unknown
  site, `stop_after_reached` in the diagnostics tables.
- [Evaluated execution](workflow_lisp_evaluated_execution.md) §8.1: one
  sentence beside the spend cap.
- The [capability matrix](../capability_status_matrix.md): one row.

## 4. What this makes harder

- Two run roots can carry one run id. A registry, a dashboard listing or a
  run-reference root keyed by run id alone would confuse them; today those
  cases are refused or live in separate workspaces.
- `checkpoints.jsonl` is a second file beside the journal. Tools may come to
  trust it; it stays evidence, and a reader that needs authority checks the
  prefix digest against the journal.
- The program must live in the workspace, where an agent can read and edit
  it. The harness rewrites it before each invocation; within an invocation
  the runtime has already loaded it.
- Boundaries are site keys. A mutation that renames or reorders unnamed
  effects moves them, so a search space must keep its boundary labels fixed.
- `git` becomes a dependency of the checkpoint module, not of the runtime.
- State outside the workspace makes forks unequal without any signal. A task
  that installs into a shared environment needs the container route.
- Every fork shares its ancestors' luck. An analysis that treats siblings as
  independent overstates what it knows.
- A change of the digest rule (readiness item R2) strands a fork as it
  strands any run in flight.

## 5. Deliberately left out

- The container route's implementation (outline and costs in §3.3).
- Programs with a parallel map, Agent Sessions, run references, phased
  providers or host requests in the prefix. Each is refused by name.
- Restoring a snapshot in place under a live run root, which would lift
  "workspace files are not rolled back" for edit and continue. The store
  would serve it; the write order under the run lock is not designed here.
- A public `orchestrator fork` command. The library call is enough for a
  harness; a command is added when an author asks for one.
- A cache of effect results across runs keyed by input digest.
- Hard links for copied attempt directories, and garbage collection of the
  store beyond deleting a study's store with its work root.
- Any stopping rule.

## 6. Probes

All probes ran at `b399076b` with stand-ins; no provider was called. The
stop was patched in for the probe at the spend cap's call sites:

```python
def check(authority, snapshot, node, **kw):          # replaces runtime.check_spend_cap for the probe
    done = set(snapshot.active_commits)
    base = state.setdefault("base", done)
    if done - base:                                   # one commit made by this invocation
        raise Stop("stopped before a new attempt")    # code stage_boundary_reached, preflight = True
    return real(authority, snapshot, node, **kw)
```

The program under test had four steps (`plan`, a command `built`, `work`,
`review`; three metered provider stand-ins and one command) in a git
workspace. The stand-in wrote files, an ignored file, a binary file, an
executable, a symbolic link and an empty directory, and made a commit in the
task repository on its second call.

| # | Question | What was run | Result |
| --- | --- | --- | --- |
| P1 | Does a stopped run resume with no step dispatched twice? | `run`, then `resume` three times, each through the patch | Four invocations; each printed `stage_boundary_reached` (the probe's name for the proposed `stop_after_reached`) or completed; four dispatches, every one at attempt 1; no journal row for a stop |
| P2 | Does a fork reproduce the parent's workspace at step k? | Snapshot after each stop; `fork` at the commit of `work`; compare the independent walk of the fork with the walk saved when the parent was stopped there | Equal: 59 entries, 42 of them under `.git`; `git log` in the fork shows the agent's commit |
| P3 | Does edited-program resume on the fork reuse the prefix? | Change `review`'s effort in the fork; `resume`; accept the token | Plan: kept three, cancelled none, "the cut: none". One dispatch, `review`, at attempt 1, its workspace counter at 3 as in an uninterrupted run. Journal: the prefix, one `rebased` record with a null cut, `review`, the terminal |
| P4 | Is the child's cost its changed suffix? | `report --format json` on parent and child; sum `usage.json` by `started` offset against the cut | Own: one attempt, 3,000 input and 100 output tokens, USD 0.00035, the `review` call. Inherited: the two earlier provider calls. `report` total: USD 0.00075 on both, three provider attempts |
| P5 | Is a same-program fork a clean retry after a cut-off call? | Second provider call exits 1 leaving a partial file; fork at the last checkpoint; `resume --max-cost-usd 1` in the fork | `work` and `review` each dispatched once at attempt 1; exit 0; no partial file; the work tree equals an uninterrupted run's except the stand-in script edited between the two runs |
| P6 | What does a git snapshot cost? | The table of §3.3 on a clone of this repository; restore and compare the walks | Walks equal: 8,042 entries, 3,348 under `.git`; the restored repository answers `git status` and `git log` |
| P7 | Do workspace attributes alter stored bytes? | A file with mixed line endings under `* text eol=crlf`, with and without `--attr-source` | Without: stored as `a\nb\nc\n`. With: `a\r\nb\nc\r\n`, as written |
| P8 | What is not reproduced? | A file of mode 600; a nested repository | Restored as 664; stored as a link entry without content |
| P9 | What does a container snapshot cost and miss? | The table and list of §3.3 | As stated there |
| P10 | Can the seed's boundaries be named today? | `orchestrator compile milestones.orc` from the spike branch on `main`; `machine.site_classes` | Compiles; the eight site keys of §3.2 |

E1 to E15 of §2 are probes of the same kind.

## 7. Not verified and open prerequisites

| Item | State | Needed for |
| --- | --- | --- |
| How a subscription usage limit appears in a provider attempt (exit status, stream fields) | Not recorded anywhere; the long-horizon plan's D5 lists provider faults as not recorded | The harness's classifier of §3.4; until then every provider failure pauses the study for a ruling |
| How a workflow's steps run inside a task container | Open design work of the long-horizon plan, step 9 | The container route |
| A fresh sidecar and relay for a forked container | Belongs to the launcher of the long-horizon plan, step 5 | The container route |
| The stop inside a parallel map | Read from the spend cap's rule (items in flight finish, no new item starts); not probed | Lifting the parallel-map refusal |
| A phased provider or a host request in a fork's prefix | Not probed | Lifting those refusals |
| An effect that reads a provider's result path (X4) in a fork | Read, not probed | Stating how much reuse such a program loses |
| A fork of a fork | Designed (§3.1); not probed | The first implementation's test |
| A fork from a parent that is running past the cut | Follows from rules M1 to M3; not probed | Forking while a parent continues |
| Overlay mounts and restart-per-stage for containers | Not tried | Cheaper container snapshots |
| The saving for the first search space | A hand count, below | The reach check of §8 measures it |

**The hand count.** In the seed a round is one plan, then per milestone a
work call, a check command and a review call, then a check and the
acceptance review. With one round and M milestones a run makes 4 + 2M
provider calls. The planner acts first, the coder at the fourth call and the
reviewer at the fifth, so a tree over three levels per role shares three
calls among the nine settings of one planner level and one more among the
three settings of one coder level. For M = 4 the 27-point grid costs 324
calls alone and 234 as a tree, a saving of 28 percent; for M = 8, 540 and
450, 17 percent. Late calls are probably dearer than early ones, which
lowers the saving in tokens.

## 8. Evidence required and increments

**Acceptance (roadmap R1), through the public command line with stand-ins,
each run built live at target 2.40 with no recorded journal fixture:**

| Requirement | Measure |
| --- | --- |
| A stopped candidate resumes with no step dispatched twice | Three candidates advanced to a boundary; one dropped by a rule supplied by the test; the others advanced to the end. Every identity has one `started` record, and the stand-ins' dispatch log has one line per step |
| A fork at step k reproduces the parent's workspace at k | The independent walk of §3.3, taken in the stopped parent at k and in the fork immediately after `fork_run`, is equal; the workspace holds tracked, untracked, ignored, binary and executable files, a link, an empty directory and a commit made by a step |
| The cost of a child equals its changed suffix | The child dispatches exactly the effects its plan lists under "runs first" and after; `own_usage` equals the stand-ins' fixed usage for those calls; no prefix identity has a new attempt |
| Refusals | Each row of §3.5's table refuses with its reason and writes nothing; `--stop-after` with an unknown site exits 2 before any effect |
| Clean retry | P5 as a test |
| Unchanged behavior | The spend-cap, edited-program resume and kill suites pass unchanged; a run without the flag and without `checkpoints.jsonl` writes the same bytes as before |

**Increments.**

| # | Increment | Hours | Needs first |
| --- | --- | --- | --- |
| I1 | `--stop-after`: the check, the field, the flag on `run` and `resume`, the unknown-site refusal, the diagnostics row, `specs/cli.md`, tests (P1 as a test; a loop site; an agent-turn site; a completed run) | 12 | Nothing. It edits `specs/cli.md` and `orchestrator/cli/main.py`, which the one-target cut also edits: land it after the cut or expect a rebase |
| I2 | The reach check, zero spend: apply each declared mutation of the first space to a stand-in run of the seed, read `rebase.plan_resume`, report the share of provider calls each keeps | 6 | The seed on `main` (long-horizon plan, step 8), with its effort levels as program text (§9, question 2) |
| I3 | `snapshot_workspace` and `restore_workspace` for git, with the independent walk as the test and the refusals of §3.3 | 8 | Nothing |
| I4 | `advance`: the loop, the checkpoint rows, the stop reason from the journal | 8 | I1, I3 |
| I5 | `fork_run`, its refusals, the fork row, `own_usage`, the choice of fork point from a plan | 10 | I3 |
| I6 | The acceptance test module of the table above, including a fork of a fork | 6 | I4, I5 |
| I7 | The contract amendments of §3.7 and a section in the lifecycle guide | 4 | Acceptance of this design |
| I8 | Independent review and fixes | 8 | I1 to I6 |
| I9 | Container route: `podman commit --pause` at boundaries, image ids in the rows, a fork as a new compose project, a byte ceiling on the store | 16 to 24 | The long-horizon launcher (step 5) and the step 9 design |
| I10 | The usage-limit classifier and the pause in the harness | 6 | The launcher's recordings of provider faults |

I1 to I8 are 62 hours. None of them needs the one-target cut, provided the
tests record no journal fixture. I9 and I10 need the long-horizon launcher.

## 9. Open questions for the coordinator

| # | Question | Recommendation |
| --- | --- | --- |
| 1 | Amend boundary invariant 1 so that a fork is an admitted start of a candidate execution? | Yes, with the sentence of §3.7, and keep promotion on independent whole runs. Without the amendment R1's third check cannot be built |
| 2 | The first space varies effort per role. As bound inputs these cannot be varied in a fork (E9). Program text or inputs? | Program text: the frozen seed writes each role's effort as a literal at its call sites and a mutation rewrites the literal. The long-horizon plan's step 8 asks for "an effort input per role"; that sentence should change before the seed is frozen |
| 3 | The seed's scripted runs bind the repository's absolute path as the `repo` input and keep the program outside the workspace | Before the seed is frozen: `repo` is `.` or is dropped, and the harness places program, manifests and inputs inside the workspace |
| 4 | Parent and forks share a run id | Accept. The alternative, a rewritten header with a new id, changes the values of X1 and X4 and the host request ids, and loses the prefix |
| 5 | Is the fork worth building for the first space, given a saving near a fifth? | Build I1 and run I2 first. Build I3 to I6 if I2 shows a saving the owner finds worth 32 hours, or because of the clean retry after a cut-off call, which a study on the subscription will need: the driver design's Execution Contract records a session limit that ended 16 of 20 evaluations of one live run |
| 6 | Snapshot at every commit or at boundaries? | Every commit for git (0.2 to 0.7 s on this repository); boundaries for containers |
| 7 | Where does the loop over candidates live? | In the search harness under `experiments/`; the module offers `advance` and takes no rule (boundary invariant 3) |
| 8 | Refuse parallel maps and coordinator classes in the first implementation? | Yes. The seed has neither |
| 9 | Store size under 55 GB free | One store per study outside every workspace, deleted with the study; `advance` refuses to snapshot under 20 GB free, the stop the long-horizon plan already uses |
