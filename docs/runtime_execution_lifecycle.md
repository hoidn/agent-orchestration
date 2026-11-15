# Runtime Execution Lifecycle

This document describes what the orchestrator does at runtime for a workflow run.
It focuses on execution order and state transitions, not DSL authoring style.

Normative behavior is defined by `specs/`. This file is explanatory.

## Frontend And Compatibility Boundary

Ordinary `run` accepts only a workflow path whose suffix compares
case-insensitively as `.orc`. YAML/YML and every other non-`.orc` path fail
with `.orc required` before a run root or `state.json` is created. There is no
production YAML parser. The [bounded Python frontend](python_workflow_drafting_guide.md)
uses `py check/build/run` to publish retained `.orc` and invokes this same
compiler/runtime. It introduces no Python executor or resume command.

The [typed Python frontend](python_workflow_drafting_guide.md) is an upstream
source generator: `py build` and `py check` import and trace trusted Python into
retained ordinary `.orc`; `py run` delegates that source to the runtime below.
Python callbacks never execute in the runtime. Ordinary `resume RUN_ID` uses the
saved generated source/configuration snapshots without importing Python, under
the same program, input and closure freshness checks.

Executable entries through 2.34 are retired. `resume` admits only a supported
evaluated header and refuses old profiles, including force-restart, before
changing their run contents. Invalidation has the same old-profile boundary;
see [CLI](../specs/cli.md#executable-support-boundary). Source compiles at one
target, 2.40, and a run recorded at 2.35–2.39 is read-only (see
[Resume](#resume)). `report` and the
dashboard read evaluated runs only and refuse older runs with
`workflow_execution_profile_retired`; the old readers are kept at the git tag
`archive/retired-run-readers-2026-11-11`. Native `prompt resume [--in-place]` is a separate retained session
bridge; it does not resume old workflow execution.

## Execution Profiles

Evaluated execution is the sole current workflow runtime. Historical flat
states remain readable; nothing converts a run between profiles.

| Profile | Targets | Authority on disk | Sections |
| --- | --- | --- | --- |
| Flat (historical, read-only) | through 2.34 | `state.json` (schema `2.1`, optionally `derived_pure_replay.v1`) | [Historical protocol](#execution-timeline); no creation, replay, repair or translation in this package |
| Evaluated | 2.40: bounded parallel map, bounded Agent Sessions and command-only confined run-ref children, procedure authoring, bounded phased providers and serial typed host input. Runs recorded at 2.35–2.39 are read-only | `run.json` + `closed_program.json` + `memo.jsonl` (schema `3.0`, `evaluated_execution.v1`); `state.json` is a derived view | [Evaluated Profile (Target 2.35)](#evaluated-profile-target-235); [Agent Sessions guide](lisp_workflow_drafting_guide.md#agent-sessions-target-238); [confined-command recipe](lisp_workflow_drafting_guide.md#confined-workflow-children-target-238-command-only) (public confined providers remain closed); [2.39 procedure contracts](lisp_workflow_drafting_guide.md#procedure-contracts-at-target-239) (same profile); [2.39 phased delivery](lisp_workflow_drafting_guide.md#authoring-phased-contract-delivery-target-239) (commit/settlement and exact-attempt recovery; paid-provider qualification unselected) |

The linked flat record preserves the historical protocol for interpreting
old state, not commands to execute with this package. Recovery requires an
exact retained release/environment and evidence for that run family; the
[retirement contract](design/workflow_lisp_executor_retirement.md#7-recovery-policy-and-one-deletion-gate)
states the limits. The normative format owner is [State](../specs/state.md), with the evaluated profile in its
[target-2.35 section](../specs/state.md#evaluated-execution-persistence-profile-target-235);
the evaluated profile's design is
[evaluated execution](design/workflow_lisp_evaluated_execution.md).

<a id="execution-timeline"></a>
<a id="run-artifacts"></a>
<a id="step-state-machine"></a>
<a id="provider-step-runtime-order"></a>
<a id="consumepublish-runtime-semantics-v12"></a>
<a id="control-flow-resolution-order"></a>
<a id="retry-and-timeout-behavior"></a>
<a id="for_each-runtime-shape"></a>
<a id="failure-taxonomy-common"></a>

The retired flat timeline/state machine/provider/call protocol is preserved for historical interpretation. No creation, replay, repair or translation is supported; historical recovery needs demonstrated exact-release/environment evidence under the retirement contract. See the [preserved record](reports/documentation-history/docs-runtime_execution_lifecycle-history.md#historical-operational-record-1).

## Evaluated Profile (Target 2.35)

A program is compiled to a checked closed program and evaluated;
there is no flat IR, no `step_id`, no `call_frames`, no heartbeat and no
`transition_count` for it. Normative keys and transitions are in
[State](../specs/state.md#evaluated-execution-persistence-profile-target-235);
entries, exits and locks in [CLI](../specs/cli.md#evaluated-execution-target-235)
and its [resume preflight precedence](../specs/cli.md#resume-preflight-precedence);
command closure and typed inputs in
[Step IO](../specs/io.md#evaluated-command-and-provider-io-target-235); the design is
[evaluated execution §§7–10](design/workflow_lisp_evaluated_execution.md#7-the-effect-memo).
The [drafting guide recipe](lisp_workflow_drafting_guide.md#a-complete-235-recipe-compile-run-resume-report-invalidate)
shows the commands on one public fixture.

### Run

Four phases; the exact order inside each is normative in
[writer sequence and durability](../specs/state.md#writer-sequence-and-durability)
and [CLI](../specs/cli.md#evaluated-execution-target-235).

```text
1) Build and bind, with no lock: build the closed program from source, roots, entry and
   the four manifests (publishing the same build directory `compile` writes under
   .orchestrate/build/<key>/), then bind the typed inputs (--input / --input-file).
   --dry-run returns here: exit 0, no lock, no run root (exit 2 on a compile or binding
   error)
2) Take the workspace lock, then the run writer lock; publish run authority durably
   before any effect, in this order: empty memo.jsonl, closed_program.json, run.json
   (program/input digests, bound inputs, representation, pinned interpreters, the
   rebuild recipe `resume_request`, `run_ref_root`, `result_root`), each synchronized
3) Evaluate the program from its entry. Each reached effect is identified by its site and
   activation path; its input is resolved (argv/closure/contract and implementation-file
   digests for a command; prompt source, dependency and policy digests for a provider;
   config and inputs for a run reference). An active commit in the memo for that identity
   is reused and nothing is dispatched. Otherwise: synchronized `started` row with the
   next attempt ordinal, exclusive creation of effects/<sha256(identity)>/attempt-N/,
   one dispatch (or target-2.40 host request suspension), validation of the result against the declared type, rehash of the
   command's closure, then `committed` or `failed`; a path run reference adds `settled`
   after its child completes (or by reconciliation on the next resume). After every
   synchronized record, including `started`, state.json is atomically replaced
4) If deliberately suspended for host input, return exit 0 with no terminal and release locks. Otherwise append the `terminal` record (`completed` with the value, or `failed` with the code),
   replace the view, release the locks. Exit 0 or 1
```

### Run artifacts

- `.orchestrate/runs/<run_id>/run.json`: immutable header (authority)
- `closed_program.json`: the checked program (authority; digest in the header)
- `memo.jsonl`: append-only journal of `started`, `committed`, `failed`, `settled`,
  `invalidated`, `suspended` and `terminal` rows (authority)
- `effects/<sha256(identity)>/attempt-N/`: `result.json`, `stdout.txt`, `stderr.txt`,
  `prompt.txt` (provider), `inputs.json` (typed external document); a run-reference
  attempt holds only `result.json`
- `state.json`: derived view, replaced after every synchronized row; never authority
- `run.lock`, `run-ref-attempts.jsonl` (coordinator ledger)
- `.orchestrate/build/<key>/manifest.json`: build metadata, not a resume recipe

### Status and effect rows

Run `status` comes from the last record and the writer lock, not from a
heartbeat ([derived view](../specs/state.md#evaluated-execution-persistence-profile-target-235)):
`suspended` for an active durable request even while its writer holds the lock;
otherwise `completed`/`failed` from the terminal; otherwise `settling` when a writer
holds the lock and replay reaches `halt`, `running` when a writer holds the
lock, `interrupted` when none does. A stored `state.json`
can say `interrupted` after external host settlement, because settlement never
executes continuation; otherwise readers reconstruct it from writer absence. Effect rows,
keyed by identity in order of first `started`, are `running`, `completed`,
`settling` (coordinator between `committed` and `settled`), `suspended`, `failed` or
`invalidated`; `current_step` is the effect in flight, `workflow_outputs` the
terminal value. A failed attempt is retried on the next resume with the next
ordinal, never by rewriting the old one.

### Resume

A run recorded at target 2.35–2.39 is not continued. `resume`, with or without
`--accept-changes`, reads the stored program's `target` first and refuses with
`run_target_retired`, exit 2, before any lock or write; `invalidate`,
`input answer` and `input cancel` refuse the same way, and REPL attach refuses
with the same code (inside a session it prints the refusal and continues). Finish such
a run with the release tagged `v0.2.1`, or start a new run from
[migrated source](lisp_workflow_drafting_guide.md#migrating-from-an-older-target).
`report`, the dashboard and the monitor still read it.

```text
1) Load and validate the header (profile, schema, run id, shapes of the recipe and roots)
   without reading the program or the memo; a header without a recipe refuses
   `resume_request_missing`; `--force-restart` refuses `evaluated_execution_unavailable`
2) Compare an explicit --run-ref-root with the header (`resume_run_ref_root_changed`), then
   the run root's relation to the workspace (`resume_result_root_changed`)
3) Rebuild the program in memory from the recipe and compare digests
   (`resume_program_changed`, which prints the plan an acceptance would apply and its
   `--accept-changes=plan-…` command, or why no plan can be accepted); re-read the input
   file, apply the overrides, bind and compare (`resume_inputs_changed`). Fresh build and
   binding publish nothing
4) Load the stored artifact and pins (`interpreter_changed` is a warning; a missing pin
   refuses); read the complete memo prefix, ignoring a torn tail
5) Replay the committed prefix in journal order, checking each resolved input
   (`effect_input_diverged` at the first divergence; for a committed step it prints the plan,
   as in 3) before any launch, reconciliation or tail repair; a completed terminal that
   replay reaches returns without writing. With `--accept-changes=plan-TOKEN` steps 3 and 5
   recompute the plan instead and compare it with the token: a plan that changed since it
   was printed refuses, names what changed and prints the new one; the plan it names is
   applied (the edited program stored, one `rebased` or `invalidated` record appended and
   synced), then evaluation continues as in 6
6) Continue evaluation as in Run from the first uncommitted effect; retried attempts take
   the next ordinal. A command retried with changed declared files needs its last attempt's
   `failed` row to say `closure: unchanged` (not a parallel-map item), or
   `resume --accept-changes`; the flag is refused when no unfinished command attempt needs it
   (a killed step whose files did not change resumes without it)
```

Every refusal in steps 1–5 exits 2 and writes nothing; exit 1 is a run that
executed and failed. A failure after an accepted plan's record exits 2 and
says that the change may be, or is, in force and that nothing was
dispatched; `report --run-id RUN_ID` lists the run's programs and `resume`
continues under the one in force.

### Invalidation

`orchestrator invalidate RUN_ID IDENTITY [--state-dir DIR]` takes the writer
lock, validates the whole suffix from the chosen active commit in journal
order, and appends one synchronized `invalidated` row (`from_commit` is the
commit's byte offset); the next resume runs those effects again as new
attempts, earlier commits stay. It never resumes, forces, cascades by value
dependence or bypasses C4; a suffix containing a committed coordinator is
refused whole; a chosen identity without an active commit refuses
`invalidate_not_committed`.

### Edit a prompt and continue

You can change a provider step's prompt in the middle of a run and continue
the same run, as long as the prompt lives in its own file. Bind each prompt
to a file in the prompt manifest, `prompts.json`:

```json
{"prompts.one": {"asset_file": "one.md"},
 "prompts.two": {"asset_file": "two.md"},
 "prompts.three": {"asset_file": "three.md"}}
```

and refer to it from the step with `:prompt prompts.two`. A prompt written
inline in the source, as a `defprompt` string, is part of the program:
editing it is an edit of the workflow, which `resume` plans and you accept,
as in [Edit the workflow and continue](#edit-the-workflow-and-continue).

The examples below are copied from runs of
[`tests/test_workflow_evaluated_prompt_edit_continue.py`](../tests/test_workflow_evaluated_prompt_edit_continue.py)'s
fixture, with a stand-in `codex` on a closed `PATH` (no model is called):
a workflow `main.orc` whose three provider steps, in a `let*`, use those
three prompts through the provider `providers.review`, bound in the provider
manifest `providers.json`:

```json
{"providers.review": "codex"}
```

The run command is:

```bash
orchestrator run main.orc --provider-externs-file providers.json \
  --prompt-externs-file prompts.json --input message=hi
```

`orchestrator report` shows the run id (`run_id`), the status, the step that
failed and, under "Steps", every step's identity, such as
`workflow:main::run / two`.

**The step failed, or has not run yet.** Edit its prompt file and resume.
The step runs again as a new attempt with the new prompt; steps that already
committed are reused, not run again.

```bash
orchestrator resume 20261112T035933Z-d60jut
# [effect_rerun] workflow:main::run / two attempts=[1]
```

**The step already committed.** Editing its prompt file makes `resume`
refuse, exit 2, without running anything. After the refusal it prints the
plan: which committed steps are kept and which run again, and the command
that accepts it:

```console
$ orchestrator resume 20261113T233911Z-syxq6s
[effect_input_diverged] workflow:main::run / two: effect input diverged (input parts changed: ['prompt', 'source:asset_file:two.md']; dependency identities changed: False; previous sha256:989954aad2660b434a1761da73a9864ca982bccd6a1e65e4895926fb9ff55ced, current sha256:200612d9e356b012d37c02c1b88d8b3bae3d1222e6b90bb01998aa4e41963544)
step workflow:main::run / two was committed with other inputs; changed: prompt, source:asset_file:two.md; files: none recorded
if accepted, this run cancels from the changed step, as invalidate does:
  kept      1 committed step:
    workflow:main::run / one
  cancelled 2 committed steps, which run again when reached:
    workflow:main::run / two   (provider cost unknown)
    workflow:main::run / three   (provider cost unknown)
  retired   none
  the cut is at workflow:main::run / two: its input changed (parts: prompt, source:asset_file:two.md; files: none)
  asked again: none
  unfinished steps retried: none
  runs first: workflow:main::run / two
  files that cancelled steps wrote in the workspace are not rolled back
to accept this plan:
    orchestrator resume 20261113T233911Z-syxq6s --accept-changes=plan-a8e93e45-2a455c78-e66bdb84-8925d117
to run this step and every later one again (workspace files are not rolled back):
    orchestrator invalidate 20261113T233911Z-syxq6s 'workflow:main::run / two'
    orchestrator resume 20261113T233911Z-syxq6s
```

Run the printed `--accept-changes=plan-…` command. It prints the plan it
applied once its record is durable, then continues: `one` is reused, `two`
and `three` run again as attempt 2 with their current prompt files, and the
result is the last line, on standard output:

```console
$ orchestrator resume 20261113T233911Z-syxq6s --accept-changes=plan-a8e93e45-2a455c78-e66bdb84-8925d117
[changes_accepted] plan-a8e93e45-2a455c78-e66bdb84-8925d117: record invalidated at journal byte 6753
accepted: this run cancels from the changed step, as invalidate does:
  kept      1 committed step:
    workflow:main::run / one
  cancelled 2 committed steps, which run again when reached:
    workflow:main::run / two   (provider cost unknown)
    workflow:main::run / three   (provider cost unknown)
  retired   none
  the cut is at workflow:main::run / two: its input changed (parts: prompt, source:asset_file:two.md; files: none)
  asked again: none
  unfinished steps retried: none
  runs first: workflow:main::run / two
  files that cancelled steps wrote in the workspace are not rolled back
run     20261113T233911Z-syxq6s  /home/you/review/.orchestrate/runs/20261113T233911Z-syxq6s
start   workflow:main::run / two  attempt 2
commit  workflow:main::run / two  attempt 2
start   workflow:main::run / three  attempt 2
commit  workflow:main::run / three  attempt 2
{"ok":true}
```

The token (`plan-…`) names that one plan: the run's journal, the programs,
the cut and the steps it cancels, not the contents of the files. Editing
`two.md` again before you run the command leaves the plan and the token as
they were, and the command is accepted: accepting a plan reruns from the cut
with the files as they are at that moment, here the newest `two.md`. A
change that moves the cut, such as an edit of `one.md`, or another record
in the run, makes the command refuse, exit 2, without writing anything; the
refusal says what changed and prints the new plan with a new token:

```text
[effect_input_diverged] the plan token names another plan: the cut moved; it is now at workflow:main::run / one: its input changed (parts: prompt, source:asset_file:one.md; files: none); the cancelled steps, the questions asked again, or the unfinished steps or their files changed
```

The two commands after it, `invalidate` then `resume`, do the same in two
steps. To undo the edit instead, restore the file's old contents and resume.

**A command step failed because of its script.** The same works for the
script of a command step: fix the script and resume. When the step failed,
the runtime rehashed its declared files and recorded `closure: unchanged` on
its `failed` row, so the retry runs with the fixed script and its
`[effect_rerun]` line ends with `changed_files=<script>`. A step that was
killed, that changed its own declared files, or that is an item of a
parallel map is refused (`effect_input_diverged`) until you resume with
`--accept-changes`, which the refusal prints. When the script is shared with
a step that already committed, the refusal prints `invalidate` for that step
and then `resume`. [`tests/test_workflow_evaluated_script_fix_retry.py`](../tests/test_workflow_evaluated_script_fix_retry.py)
pins these cases.

**Limits.**

- Neither an accepted plan nor `invalidate` rolls back files in the
  workspace. Anything the cancelled steps wrote stays until the steps run
  again and overwrite it.
- If a step after the edited one is a committed agent turn or run reference,
  no plan can be accepted and `invalidate` refuses
  (`invalidate_coordinator_committed`); start a new run.

[`tests/test_workflow_evaluated_prompt_edit_continue.py`](../tests/test_workflow_evaluated_prompt_edit_continue.py)
pins the failed, not-yet-run, committed-then-invalidate, restore and inline
cases above; the `invalidate_coordinator_committed` limit is pinned for agent turns by
[`tests/test_workflow_evaluated_agent_invalidate.py`](../tests/test_workflow_evaluated_agent_invalidate.py).

### Edit the workflow and continue

An edit of the workflow source (a step added, removed or changed, an inline
prompt, a manifest entry) changes the program. `resume` refuses with
`resume_program_changed`, exit 2, writes nothing, and prints which effect
sites changed, the plan and the command that accepts it. Here the inline
`defprompt` of step `two` was edited after `two` failed:

```console
$ orchestrator resume 20261113T233925Z-8f9x24
[resume_program_changed] current program differs from the run's program in force
effect sites that differ from the recorded program:
  changed workflow:main::run / two
if accepted, this run continues under the edited program:
  kept      1 committed step:
    workflow:main::run / one
  cancelled none
  retired   none
  the cut: none, nothing is cancelled
  asked again: none
  unfinished steps retried: none
  runs first: workflow:main::run / two
to accept this plan:
    orchestrator resume 20261113T233925Z-8f9x24 --accept-changes=plan-295f671c-b0941668-0551d8b6-7c5958d1
restore the source as it was and resume:
    orchestrator resume 20261113T233925Z-8f9x24
or start a new run, in which every step runs again:
    orchestrator run main.orc --provider-externs-file providers.json --prompt-externs-file prompts.json --input message=hi --run-ref-root /home/you/.local/state/orchestrator/run-ref
```

Following the first command, the run continues under the edited program:

```console
$ orchestrator resume 20261113T233925Z-8f9x24 --accept-changes=plan-295f671c-b0941668-0551d8b6-7c5958d1
[changes_accepted] plan-295f671c-b0941668-0551d8b6-7c5958d1: record rebased at journal byte 3418
accepted: this run continues under the edited program:
  kept      1 committed step:
    workflow:main::run / one
  cancelled none
  retired   none
  the cut: none, nothing is cancelled
  asked again: none
  unfinished steps retried: none
  runs first: workflow:main::run / two
run     20261113T233925Z-8f9x24  /home/you/inline/.orchestrate/runs/20261113T233925Z-8f9x24
start   workflow:main::run / two  attempt 2
[effect_rerun] workflow:main::run / two attempts=[1]
commit  workflow:main::run / two  attempt 2
start   workflow:main::run / three  attempt 1
commit  workflow:main::run / three  attempt 1
{"ok":true}
```

A committed step is kept only if every step before it is kept and its
identity and inputs are unchanged under the edited program; the first one
that is not is the cut, and it and every later commit run again. With no
cut nothing runs again (`the cut: none`), and what runs first is the next
step not yet committed, or nothing when the run is complete. `report
--run-id RUN_ID` then lists the run's programs under "Programs", each with
the time it was accepted (`since …`) and, when it cancelled anything, its
cut (in `--format json`, `run.programs[*].cut`, the journal offset it
cancelled from, `null` when nothing was cancelled), and which program each
step ran under.

What the plan says it cannot do, with its code after `no plan can be
accepted:`, has its own way forward:

- **A committed agent turn, run reference or phased provider at or after the
  cut** (`invalidate_coordinator_committed`): start a new run.
- **A step declared `must_not_repeat` whose commit the plan would cancel**
  (`lexical_restore_pending_effect_unsafe`): the refusal prints
  `invalidate RUN_ID 'IDENTITY'` for it; run that if repeating the step is
  safe, then `resume` prints a new plan.
- **A pending run reference or phased provider the plan would not keep**
  (`resume_program_changed`, "the pending attempt of IDENTITY would not be
  kept"): restore the source and resume, so that the attempt settles under
  the program that started it, then edit again.
- **A pending agent turn the plan would not keep**
  (`invalidate_agent_session_advanced`): restore the source, `resume` so the
  turn is reconciled under the run's own program, then edit again.
- **A run-reference child.** A child never changes program. Running
  `resume` in a path-mode child's workspace (under the run-reference root)
  after editing the child's source prints `no plan can be accepted:
  [resume_program_changed] a run-reference child changes program only with
  its parent; resume its parent run RUN_ID`: restore the child's source and
  resume the parent run it names. Such a child runs no command or provider,
  so `invalidate` there refuses with `invalidate_not_committed`. A confined
  child (target 2.38) has committed steps, and its workspace exists only
  while its parent runs; its refusal reads "a confined run-reference child
  never changes program; resume its parent run" without the id (the parent
  is the run whose run-reference step started it). If a file one of its
  committed steps read was changed, `resume` there refuses
  `effect_input_diverged` and still prints `invalidate` lines: do not run
  them in the child, since the parent re-reads the child's journal; restore
  the file and resume the parent, or start a new parent run.

A kill during the acceptance leaves the run under the old program or under
the new one, never between; `resume` (or the same command) continues. A kill
while the edited program is being stored can leave a temporary file
`.closed_program.<digest>.json.<16 hex digits>.tmp` in the run directory. No
command reads it; it is harmless and may be deleted while no `resume` of
that run is running.

### Plan an edit without changing the run

Plain `resume` is the planning command: under an edit it prints the plan and
writes nothing. The same plan is a library call, for scripts that compare
edits: `orchestrator.workflow.evaluated.rebase.plan_resume(run_root,
workspace)` returns the plan, or raises the refusal (`PlanRefusal`, or the
coded error of the check that refused). It reads the run and the workspace
and takes no lock. Plan against the run's own workspace, not a clean clone:
files earlier steps left can move the cut earlier, and a clean clone would
overstate what is kept. Copied from a run of the fixture above, after
`two.md` was edited:

```python
from pathlib import Path
from orchestrator.workflow.evaluated.rebase import plan_resume

plan = plan_resume(Path.cwd() / ".orchestrate" / "runs" / "20261113T233951Z-w5hv0y", Path.cwd())
print(plan.record, plan.token)
print("kept:", [entry.data["identity"] for entry in plan.kept])
print("cancelled:", [entry.data["identity"] for entry in plan.cancelled])
print("runs first:", list(plan.runs_first))
```

```console
$ python plan.py
invalidated plan-5eeb3808-2a455c78-5a572204-8925d117
kept: ['workflow:main::run / one']
cancelled: ['workflow:main::run / two', 'workflow:main::run / three']
runs first: ['workflow:main::run / two']
```

No file under `.orchestrate` changed. `plan.record` is `rebased` for an
edited program and `invalidated` for a changed input under the run's own
program. [`tests/test_workflow_evaluated_edit_resume_plan.py`](../tests/test_workflow_evaluated_edit_resume_plan.py)
and [`tests/test_workflow_evaluated_edit_resume_accept.py`](../tests/test_workflow_evaluated_edit_resume_accept.py)
pin the plan and its acceptance.

### Readers

`report`, the dashboard scanner, the monitor classifier and scanner, the
watchdog probe and the usage-limit watcher share one read-only projection,
`orchestrator/workflow/evaluated/views.py::load_evaluated_view`, which
reconstructs the view from header, program and memo when `state.json` is
missing, stale or unparseable. Readers never append, repair or rebuild; a
preview or an explicit output of a reader is the reader's file, not a
mutation of the observed run. `monitor --once --dry-run` reads and
classifies; it is not an installed service and sends nothing.

The shared watchdog probe remains a reader. The watchdog workflow's executable
route is retired; keeping its probe does not preserve that runtime.

## Runtime vs Authoring Boundary

This file describes runtime behavior.
For writing workflows and prompt patterns, use:
- `docs/orchestration_start_here.md`
- [Workflow Lisp guide](lisp_workflow_drafting_guide.md)
- [Typed Python guide](python_workflow_drafting_guide.md)

Use `docs/workflow_drafting_guide.md` only to translate or audit historical
YAML/YML definitions.

## Durable host request lifecycle (Target 2.40)

1. Reaching `request-input` prepares a typed question without dispatching a
   provider. A synchronized start freezes its ID, contracts, evidence, creation
   time and deadline before attempt views. One suspension row stops evaluation
   and returns exit `0`; no continuation or terminal runs.
2. Read-only pending/report/dashboard validates checked memo authority. Missing
   request view files do not change the request; elapsed wall-clock deadline
   remains observational until resume. A start without a suspension needs resume
   recovery, preserving its ordinal, ID and deadline, before host settlement.
3. Host answer/cancel takes the run writer lock and ordinary read-only resume
   preflight, then validates typed value, attribution, evidence and acceptance
   time. It commits only the inline reply. The resulting `interrupted` state
   means resume is needed. An identical retry reuses the commit without a row.
4. Resume validates the prefix and consumes the reply with full generic/branch
   provenance. Without a reply it exits suspended again, or commits runtime
   `EXPIRED` at/after the frozen deadline and continues immediately. All writer
   operations serialize with invalidation under the same lock.

Question/doc/producer inputs remain content-bound. Show-only file bytes are
presentation snapshots with an explicit recorded override for drift; the
existing semantic/path checks cannot be waived. Earlier suffix invalidation
retires later pending request IDs; no direct pending-request invalidation door
exists. The [state](../specs/state.md#evaluated-durable-host-input-target-240),
[IO](../specs/io.md#evaluated-host-input-io-target-240) and
[CLI](../specs/cli.md#evaluated-host-input-target-240) contracts define exact
publication, recovery and refusal behavior. Follow the [Lisp recipe](lisp_workflow_drafting_guide.md#durable-host-input)
or [Python recipe](python_workflow_drafting_guide.md) for executable commands.

Python-authored runs retain generated `.orc`/manifest rebuild paths. Resume
never imports the author module or rereads a build-time prompt template;
generated inputs must remain available and unmodified. Runtime document inputs
keep their ordinary divergence checks. Source maps provide initial diagnostic
attribution, while runtime reports name generated source and effect/request IDs.
