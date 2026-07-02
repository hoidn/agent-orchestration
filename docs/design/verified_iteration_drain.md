# Verified-Iteration Drain

Status: designed (pilot; does not replace the `lisp_frontend_*` drain family)
Created: 2026-07-02
Implementation plan: `docs/plans/2026-07-02-verified-iteration-drain.md`

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

### Workflow boundary — `workflows/examples/verified_iteration_drain.yaml`

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

### `workflows/library/scripts/prepare_verified_iteration.py`

- `(--drain-state-root, --artifact-work-root, --target-design-path,
  --check-commands-path, --iteration) -> work-order.json` (output_bundle:
  `base_sha` string, `work_order_path` relpath).
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
2. **Coarser resume granularity.** A mid-iteration crash re-runs the
   iteration from its base snapshot rather than resuming a micro-step.
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
