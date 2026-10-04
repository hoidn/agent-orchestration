# Verified-Iteration Drain

Status: implemented; Workflow Lisp production primary (does not replace the
`lisp_frontend_*` drain family)
Created: 2026-07-02
Implementation plan: `docs/plans/2026-07-02-verified-iteration-drain.md`

The promoted authoring and launch surface is
`workflows/library/verified_iteration_drain/drain.orc`, entry
`verified_iteration_drain/drain::drain`. Its final typed parity report is
`artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final/verified_iteration_drain.json`.
The historical YAML twin was retired after its Stage 6 Task 6 reference and
supported-run deletion gates passed.

The sections below describe the implemented baseline. The
[accepted history-input extension](#accepted-extension-prepare-selected-history-input)
changes the canonical consumer in both execution routes; its implementation
and verification remain pending in Phase 3 Tasks 13D/14. Historical parity
evidence above does not verify that extension.

## Problem

The existing drain family keeps a second, typed copy of reality — run-state
event vocabularies, recovery routes/reasons, retry bundles, step-back
diagnoses, materialized evidence copies — that must be plumbed to providers
and reconciled after them. Every incident class observed in the 2026-07-01/02
runs (stale evidence, reconciliation drift, state-machine inconsistency,
livelock, file-list scope fences, revision churn) was a defect of that second
copy, not of provider judgment. This design deletes the second copy.

## Design Principles

- **P1 — Single source of truth: the repo.** Authority is the working tree,
  git history, and the result of running checks. Everything else is a view.
- **P2 — Views are regenerated, never reconciled.** Derived context is either
  append-only measured fact or regenerated from scratch each iteration.
  Nothing is updated in place, so nothing can drift.
- **P3 — Judgment is fused.** One provider session per iteration owns
  select → plan → implement → self-verify. No judgment handoffs mid-decision,
  so no evidence plumbing between deciders.
- **P4 — Deterministic control touches only measurables.** Loop continuation,
  stall detection, and acceptance are functions of the iteration diff, check
  exit codes, and three small enums. No routes, reasons, fingerprints, or
  event taxonomies.
- **P5 — Gates on outcomes, not process.** Checks (deterministic) and review
  (judgment on the diff vs the target design) gate acceptance. Plans,
  classifications, and revisions are the worker's private business.
- **P6 — No destructive automation in a shared tree.** Rejection changes
  recorded status, never the tree. Repair is the next iteration's first duty.
- **P7 — Bounded autonomy, honest exits.** Fixed iteration budget, stall rule
  on measured non-progress, and three terminal states — `DONE`,
  `BLOCKED_ON_USER`, `STALLED` — each publishing a summary. Every exit is
  recoverable by `orchestrator resume` or a fresh run, because the state is
  the repo.
- **P8 — Scope fenced by invariants, not file lists.** The fixed check suite
  plus the target design's non-goals bound the worker. There is no other
  fence (lesson of the 2026-07-02 six-file-slice stall).

## The Loop

One `repeat_until` step, five inner steps, no sub-workflow calls:

```
Prepare   (command)  base = git rev-parse HEAD; regenerate work-order.json
Work      (provider) one agentic session; commits verified work by explicit
                     path; writes verdict CONTINUE | DONE | BLOCKED_ON_USER
                     and a one-line note; may write BLOCKED-<topic>.md notes
Verify    (command)  run the fixed check commands; GREEN | RED; package the
                     iteration diff (git log + diff base..HEAD) for review
Review    (provider) iteration diff vs target design → APPROVE | FINDINGS
                     (runs only when commits landed and checks are GREEN)
ReviewDone(provider) target design acceptance criteria met? APPROVE | REJECT
                     (runs only when the worker claims DONE)
Record    (command)  derive iteration status from measurables, append one
                     ledger line + one status token, regenerate summary.json,
                     emit drain_status
```

### Iteration status (derived, never asserted)

`Record` computes exactly one status per iteration from
(commits_landed, verify, review, done_review, worker_verdict, blocked notes):

| status | condition |
|---|---|
| `DONE` | verdict DONE ∧ verify GREEN ∧ done-review APPROVE ∧ review ∈ {APPROVE, SKIPPED} |
| `ACCEPTED` | commits ∧ verify GREEN ∧ review APPROVE |
| `CHECKS_RED` | verify RED |
| `FINDINGS` | review FINDINGS, or done-review REJECT |
| `BLOCKED_ON_USER` | verdict BLOCKED_ON_USER ∧ at least one `BLOCKED-*.md` exists |
| `NO_CHANGE` | everything else (including a blocked claim without notes) |

The rows are not mutually exclusive; evaluation order is normative and part of
this contract: `CHECKS_RED` → `FINDINGS` (review FINDINGS, or verdict DONE
with done-review ≠ APPROVE) → `DONE` (verdict DONE ∧ done-review APPROVE) →
`BLOCKED_ON_USER` (verdict BLOCKED_ON_USER ∧ ≥1 `BLOCKED-*.md`) → `ACCEPTED`
(commits ∧ review APPROVE) → `NO_CHANGE`. Example that the order decides: a
DONE claim whose done-review is REJECT records `FINDINGS`, never `ACCEPTED`,
even when the diff itself was approved — because ledger tokens are append-only
(P2), a misordered evaluation would be a permanent misrecord.

### Loop control (all measured)

- `drain_status = DONE` when status is DONE.
- `drain_status = BLOCKED_ON_USER` when status is BLOCKED_ON_USER.
- `drain_status = STALLED` when the last `stall_limit` (default 3, must be
  ≥ 1) status tokens are all in {NO_CHANGE, CHECKS_RED, FINDINGS}.
- otherwise `CONTINUE`; `on_exhausted` (max_iterations) publishes `STALLED`.

`CHECKS_RED` never mutates the tree (P6). The next iteration's work order
states that restoring green checks is the mandatory first task; the stall
rule bounds how long a red tree can persist.

## State Surfaces (exhaustive)

| surface | location | writer | reader | nature |
|---|---|---|---|---|
| git history | repo | worker (explicit-path commits) | everyone | authority |
| check results | recomputed | Verify step | Record, worker | measurement, regenerated |
| `ledger.md` | `artifacts/work/<root>/ledger.md` | Record only | worker, reviewer, humans | append-only prose; advisory, never machine-routed |
| `statuses.txt` | `state/<root>/statuses.txt` | Record only | Record (stall window) | append-only enum tokens; the only machine-consumed memory |
| `BLOCKED-*.md` | `artifacts/work/<root>/blocked/` | worker | humans (via summary) | prose escalation notes |
| `drain-summary.json` | `artifacts/work/<root>/drain-summary.json` | Record | user, downstream | regenerated whole each iteration (P2) |
| per-iteration files | `state/<root>/iterations/<n>/` | steps | same iteration + next work order | verdict, note, decisions, diff package, check log |

There is no run_state.json, no event vocabulary, no recovery route, no retry
bundle, no fingerprint. The stall window reads `statuses.txt`, which records
only what was measured.

## Component Contracts (IDL-style)

### Workflow boundary — `workflows/library/verified_iteration_drain/drain.orc`

- Inputs: `target_design_path` (relpath under docs/design, must exist),
  `check_commands_path` (relpath, JSON list of shell commands — fixed at
  launch, owned by the target design, never worker-declared),
  `drain_state_root` (under state), `artifact_work_root` (under
  artifacts/work), `stall_limit` (int, default 3), `worker_provider` /
  `reviewer_provider` (enum codex|claude, defaults claude), model/effort
  scalars.
- Outputs: `drain_status` enum CONTINUE|DONE|BLOCKED_ON_USER|STALLED (loop
  output; CONTINUE never escapes in practice), `drain_summary_path`.
- Dependencies: git available in the workspace; the three scripts below; the
  three prompts below. No imports of other workflow files.

Launch new runs through Workflow Lisp with the provider, prompt, and command
extern manifests under `workflows/examples/inputs/workflow_lisp_migrations/`.
The deleted `workflows/examples/verified_iteration_drain.yaml` is a historical
migration source only; the retained `.orc` workflow is the sole live family
route.

### `workflows/library/scripts/prepare_verified_iteration.py`

- `(--drain-state-root, --artifact-work-root, --target-design-path,
  --check-commands-path, --iteration) -> work-order.json` (output_bundle:
  `base_sha` string, `work_order_path` relpath, `ledger_path` relpath).
- Behavior: records `git rev-parse HEAD` as the iteration base; creates the
  iteration dir, ledger file, and blocked-notes dir if absent; regenerates
  `work-order.json` naming every path the worker needs (target design,
  ledger, blocked dir, check commands, verdict/note target paths, previous
  iteration's findings and check log when present). Fail-fast (nonzero) if
  the workspace is not a git repository or required inputs are missing.
- Consumed by: Work (injected as content), Verify/Record (base_sha).

### `workflows/library/scripts/run_verified_iteration_checks.py`

- `(--check-commands-path, --base-sha, --iteration-dir) ->
  checks-result.json` (output_bundle: `verify_status` enum GREEN|RED,
  `commits_landed` enum true|false, `review_package_path` relpath,
  `checks_log_path` relpath).
- Behavior: runs each command via the shell from the repo root, streaming
  output to `checks-log.txt`; GREEN iff all exit 0. Writes
  `review-package.md` = `git log --oneline base..HEAD` + `git diff base..HEAD`
  (empty package when no commits). Exit 0 whether GREEN or RED (status is
  data); nonzero only on setup errors (missing/invalid check-commands file).
- Consumed by: Review gating conditions, Record.

### `workflows/library/scripts/record_verified_iteration.py`

- `(--iteration, --base-sha, --checks-result-path, --review-decision-path,
  --done-review-decision-path, --worker-verdict-path, --worker-note-path,
  --blocked-notes-dir, --ledger-path, --statuses-path, --stall-limit,
  --summary-path, --drain-status-path) -> drain-status.txt` (expected_outputs
  enum) + ledger/statuses appends + regenerated summary.
- Behavior: implements the status table and loop-control rules above.
  Decision files that don't exist (their step was skipped) read as SKIPPED.
  Missing verdict file is impossible by contract (Work's expected_outputs
  enforce it) and is a hard error here. Appends exactly one ledger line:
  `iter <n> | <STATUS> | <base7>..<head7> | <worker note>`. Never rewrites
  prior lines or tokens.
- Consumed by: repeat_until condition and outputs.

### Prompts — `workflows/library/prompts/verified_iteration_drain/`

- `work.md` — the worker owns selection, planning, implementation, and
  self-verification for one iteration; checks green before new work is
  accepted; explicit-path staging only; BLOCKED notes for genuine user
  decisions; verdict + note contract. Task-local; no loop mechanics.
- `review_iteration.md` — reviewer judges the packaged diff against the
  target design (correctness, design conformance, weakened-verification);
  APPROVE or FINDINGS with a findings file.
- `review_done.md` — reviewer judges whether the target design's acceptance
  criteria hold in the current checkout; APPROVE or REJECT with reasons.

## Why Each Failure Class Is Structurally Absent

- **Stale evidence** — evidence is whatever Verify measures this iteration
  against the current tree; nothing cached is authoritative (P1/P2).
- **State tracking / reconciliation** — no typed mirror exists to reconcile;
  the only machine memory is an append-only list of measured status tokens.
- **State-machine inconsistency** — machine state is a loop counter and a
  stall window over measured tokens; recorded beliefs never route control.
- **Deadlock / livelock** — livelock requires two components with
  inconsistent views; the stall rule is a pure function of the last K
  measured outcomes and cannot disagree with itself.
- **Inflexible scope** — the worker owns scope each iteration; the only
  fences are the check suite and the design's non-goals (P8).
- **Revision churn** — there is no revision pipeline to churn; a changed
  approach is just the next iteration, and non-convergence surfaces as
  consecutive non-ACCEPTED tokens that trip the stall rule.

## Trade-offs Accepted

1. **Per-decision audit lineage is coarser.** No classification/revision
   bundles; the audit trail is ledger + git + review files.
2. **Resume granularity is per inner step, not per iteration.** A
   mid-iteration crash resumes at the iteration's first non-terminal inner
   step (Prepare/Work/Verify/Review/ReviewDone/Record), not from the
   iteration's base snapshot. Record's ledger and status-token appends are
   idempotent per iteration (a re-invocation whose ledger line already landed
   skips both appends and only regenerates the summary/status surfaces), so a
   resumed run cannot double-record an iteration even though Record itself
   may be re-invoked.
3. **Trusts one competent worker, gates its outcomes.** Weak workers produce
   NO_CHANGE/FINDINGS tokens and trip the stall rule rather than being
   corrected by machinery.
4. **No explicit dependency edges.** "Pick the most valuable unblocked work"
   subsumes prerequisite ordering for a serial drain. Parallel gap execution
   would need scheduling this design deliberately omits.
5. **Check-suite health couples to the shared tree.** If the fixed checks
   cannot be green for reasons outside the target (e.g. unrelated in-flight
   migration edits), the drain stalls honestly. Choose check commands the
   target design owns.

## Non-Goals

- Replacing the `lisp_frontend_*` drain family (pilot in parallel; compare
  iterations-to-completion and incident count on a real target).
- Roadmap/approval gating (compose an existing gate workflow before this one
  if needed).
- Automated rollback, revert, or any tree mutation by the harness.
- Multi-worker parallelism.

## Accepted Extension: Prepare-Selected History Input

This target design preserves completed-resume without runtime versioning.
The single canonical `drain.orc` remains at target 2.15; the public evaluated
fixture copies its revised source and changes only the target to 2.35, with
the required manifests/closures. There is no alternate drain, script or
target-dependent behavior. This extension changes both routes' source,
prompts, freshness and inventory; runs already started are not migrated or
rewritten. Existing program/closure compatibility and resume refusals still
apply to those runs.

Prepare reads the current raw bytes of the cumulative `ledger.md` once per
execution and publishes or reuses
`<artifact_work_root>/ledger-inputs/<sha256-of-raw-bytes>.md` before returning
a valid result. `PrepareResult` keeps its three existing fields and adds
`ledger_input_path` as a fourth field of the existing `LedgerPath` type, with
its existing root and `must_exist` constraint. The output bundle has exactly
`base_sha`, `work_order_path`, `ledger_path` and `ledger_input_path`;
`work-order.json` also names the new input and keeps `ledger_path` as the
publication destination.

| Surface | Writer | Reader | Contract |
| --- | --- | --- | --- |
| `ledger.md` | Prepare initializes; Record appends | Prepare, humans | Cumulative append-only advisory publication |
| `ledger-inputs/<digest>.md` | Prepare only | Work, iteration-review | Complete captured context, never rewritten by the workflow |
| `work-order.json` | Prepare | Work and existing iteration consumers | Names the selected input and separate publication path |

Work and iteration-review pass `prepared.ledger_input_path` to their required
prompt dependency and their prompts identify this selected history as
read-only context. Record still receives `prepared.ledger_path`. Verify,
Record and done-review retain their contracts; done-review gains no new C6
dependency. Git and checks remain decision authority; neither history copy
is another state machine or replay authority.

The unit of capture is Prepare. Its stored committed result selects the
history for that iteration; retry of Work does not recapture a later edit to
the cumulative ledger. A later authorized Prepare captures current bytes.
The target design remains a direct dependency fresh at each provider attempt.
The cost is that external history edits during a prepared iteration do not
refresh its retry context, and more files must be retained while their
consumers may resume. Old copies and attempt evidence remain available;
there is no new cleanup or retention service.

C6 reads and hashes the actual input file; the digest in its filename does
not authenticate it. External mutation before an evaluated consumer commits
can be recaptured by that consumer under existing C6 rules, without
authorizing the workflow to rewrite the copy. After a consumer commits,
changed or missing input still refuses before new effects. C6/C7, C8 and
command-local C4 do not change, and evaluated completed-resume checks are
not added to legacy.

### Publication Under Prepare

Keep publication in the standalone Prepare script using stdlib
`tempfile`/`os`/`hashlib`: create an exclusive private temporal in the same
directory, write and close all bytes, publish with `os.link` without replacing
the final name, then remove only the temporal owned by this attempt. Reuse an
existing final only after reading it as a regular file without following a
symlink and comparing identical bytes. No runtime import, package closure
expansion or replacement fallback is selected. Unsupported hard links or
other IO errors fail the command before a valid result/provider start.

| Publication state | Required behavior |
| --- | --- |
| Final absent | Publish complete captured bytes before returning its path; no own temporal remains after normal success |
| Final regular with equal bytes | Reuse without rewriting or truncating; other Prepare outputs retain their existing rules |
| Final differs, is a symlink/wrong type, or cannot be read | Fail explicitly, leave final and prior evidence intact; no valid result or later provider |
| Recoverable exception before publication | Final stays absent; remove only the own temporal when possible; retry publishes normally |
| Abrupt interruption before publication | An incomplete temporal may remain, never a selected final; retry ignores it and does not adopt or clean another attempt's files |
| Interruption after publication but before bundle/commit | Final stays complete; retry reuses it for equal captured bytes or publishes another name for new bytes, retaining the old copy |
| Final appears between staging and publication | Exclusive link fails; apply equal-byte reuse or refusal without replacing the new destination |

An interruption while regenerating work order/bundle follows existing
uncommitted-command recovery; it cannot return a partial history as success.
This guarantees complete publication without workflow replacement, not
power-loss durability, a transaction over all Prepare outputs or isolation
from concurrent external edits. Task 15 keeps its distinct recovery gates.
Refusal/read-only snapshots include the whole tree, locks and temporals;
the existing `omit_memo` exception remains limited to an authorized append.

### Bounded Evaluated Recapture

Recapturing history with existing C8 requires all of the following:

1. This iteration's Prepare has an identifiable active commit, and Record
   has not executed, including any append without a commit.
2. No `pending_starts` or unsettled coordinator remains; the writer is
   stopped and its normal lock acquired. Work may be unstarted or have a
   durable `failed` closing its start. Absence of a commit alone is not enough.
3. The prefix before Prepare retains valid inputs/authority, with no other
   active divergence; the selected suffix has no committed coordinator.
   Program, inputs, retry and C4 checks remain applicable.
4. The operator chooses to rerun Prepare in full and its suffix, including
   measuring git base and regenerating work order. This does not roll back
   external or failed-worker changes or a Record publication.

Use `orchestrator invalidate RUN_ID PREPARE_IDENTITY`, then
`orchestrator resume RUN_ID`, with the exact canonical identity as one
argument and the same `--state-dir` where applicable. `from_commit` anchors
the Prepare offset and cancels the entire later active suffix. The new
Prepare attempt selects current history; old files/evidence remain.
Invalidating only Work leaves Prepare memoized. A Work without a commit
refuses `invalidate_not_committed`; invalidation does not close an open
start, fabricate a `failed` or edit the memo. Record already executed,
divergent prefix, pending attempt or coordinator cases are outside this
recapture recipe. Legacy keeps `invalidate_profile_unsupported`; only its
normal flow or a new run can authorize another Prepare.

### Preservation Evidence

Verify both routes over the revised common source, keeping the original
source, oracles and receipts as historical evidence. Keep exact four-field
Prepare bundle and work-order path/dataflow checks, plus all previous command
ordering/fields. The continue→done scenario retains roles, ledger iterations `[0,1]`, statuses
`[ACCEPTED,DONE]`, all 19 former paths and exactly the two distinct history
inputs whose names/digests/bytes follow the actual reads; an `issubset`
inventory is insufficient. The retry DONE scenario retains three provider
executions, worker ordinals `[1,2]`, fresh target-design bytes, prior snapshots,
unchanged selected history and idempotent completed-resume artifacts/counts.

Prove publication/retry states above, actual producer/read path-content
evidence, external cumulative-ledger edits between Prepare and Work retry,
changed/missing captured-input refusal and post-Prepare/pre-Work C8 recapture.
Reject a noncommitted Work as an invalidation anchor; do not promise the
recipe for excluded states. Legacy controls do not replace public evaluated
compile/run/resume evidence. The [Phase 3 plan](../plans/2026-10-02-workflow-lisp-evaluated-execution-phase-3-plan.md#task-13d-canonical-verified-drain-history-input)
owns the bounded implementation and verification; this design does not
claim those checks have passed.
