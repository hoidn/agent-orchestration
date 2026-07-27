# Workflow Lisp Phased Contract Delivery

- **Status:** proposed (owner-directed 2026-07-27); independent design review
  pending before any implementation planning
- **Kind:** provider elicitation delta — runtime-owned two-turn prompt
  delivery for fragment-backed provider calls
- **Owner:** provider runtime (turn-queue delivery) plus the existing prompt
  composition pipeline; no new frontend declaration surface
- **Motivating consumers:** the migrated
  `workflows/examples/review_revise_design_docs.orc` review call, and every
  fragment-backed `provider-result` on a session-capable provider
- **Related docs:**
  - `docs/design/workflow_lisp_prompt_calculus.md` (Q1 fragments; Q2 `:out`)
  - `docs/design/workflow_lisp_provider_live_binding.md` and
    `docs/design/workflow_lisp_provider_peer_messaging.md` (the target-2.17
    turn-boundary delivery substrate this design reuses)
  - `docs/design/workflow_language_design_principles.md` principles 28, 29,
    and 30 — this design is principle 30's sequencing corollary: the runtime
    owns not only *what* the machine carries but *when* the provider must
    carry each remaining load

## Problem

Composed single-prompt delivery front-loads every mechanical obligation —
schema tokens, artifact serialization, path spelling, one-file-per-value
rules — before the provider begins the judgment it is engaged for, and holds
those obligations in attention throughout. Two costs follow:

1. **Standing attention tax** (principle 30): the contract tail is read on
   every attempt, competing with the task on every attempt.
2. **Retry economics:** a contract near-miss (`review_findings.v1` for
   `ReviewFindings.v1`) fails boundary validation and re-pays the *entire*
   attempt — the reasoning is re-purchased to fix a serialization mistake.

## Decision (proposed)

For a fragment-backed `provider-result` on a provider whose binding declares
interactive session support, the runtime may deliver the composed prompt as
two successive session turns:

- **Turn 1 — task phase:** the injected `:doc` blocks and the substituted
  template prose, exactly as composed today, minus the derived contract
  tail. All authored semantic requirements (outcome meanings, judgment
  criteria, findings expectations) are template prose and therefore arrive
  here.
- **Turn 2 — materialization phase:** the derived contract tail — output
  contract block, `ReturnSpec` result guidance, artifact rows, and any
  residual guidance lines — delivered runtime-owned at the turn boundary
  via the existing target-2.17 turn queue. The provider then materializes
  and emits its artifacts and structured result.

**Materialization-only retry.** If boundary validation rejects the
materialized result, the runtime re-issues turn 2 only — same session,
appended turn carrying the named validation diagnostic (principle 28) and
the re-rendered contract — up to a small authored cap. The task phase is
never re-elicited by a contract violation. Task-phase failures and cap
exhaustion fail the attempt through the existing failure path unchanged.

**Deterministic fallback.** On providers without session support, or when
the call does not opt in, composition is byte-identical to today's single
prompt. One declaration, two renderings, chosen deterministically from the
provider binding — never at runtime discretion.

**Opt-in surface.** First tranche exposes one call-policy flag
(`:delivery :phased`, default `:composed`) on fragment-backed calls only.
Flipping the default is a later, evidence-based decision outside this
design.

## The Cut Rule

The division between phases is **derived, not authored** — no per-slot
annotations, no new author decisions:

- **Semantic obligations** are whatever the fragment author wrote in the
  template. They arrive in turn 1, always.
- **Mechanical obligations** are whatever the machinery derives from the
  declaration: the contract block, result guidance, serialization and
  spelling rules. They arrive in turn 2.

The rule is sharp because Q1/Q2 already made it so: everything mechanical
is rendered from the `ReturnSpec` and slot declarations, never authored.
The `:out` path appears in both phases consistently — in turn 1 where the
author's prose placed it, in turn 2's contract row where the machinery
derives it — and Q2's one-path-authority guarantees they agree.

## Identity, Evidence, Resume

- An attempt's prompt identity covers the **ordered pair** of phase
  renderings; the per-attempt snapshot records both turns. The session
  machinery's existing turn transcript is the evidence carrier — no new
  record kind.
- Materialization retries append to the same attempt's transcript with
  their diagnostics; the retry count joins the attempt record.
- Resume semantics are unchanged: a phased visit is an ordinary session
  visit under the current contract (and under the substrate track's
  at-least-once amendment when that lands — an interrupted phased visit is
  discarded and re-run like any interrupted visit). This design adds no new
  resume state.

## Non-Goals

- No mid-turn steering, model-driven negotiation, or third phase.
- No change to composed rendering, prompt authority, or any renderer.
- No per-slot phase annotations; the cut rule stays derived.
- No claim that phasing improves judgment quality — the compiler-checkable
  claims are byte-accounting, retry containment, and evidence shape; task
  quality is measured at the consumer, not asserted.

## Verification Sketch

- **Byte accounting:** with a deterministic provider double, turn-1 bytes
  plus turn-2 bytes reconstruct the composed rendering exactly (partition,
  no loss, no duplication beyond the consistent `:out` path); the
  non-phased path stays byte-identical to today.
- **Retry containment:** fixture in which the first materialization is
  invalid — expect one task phase, a named diagnostic on the appended
  turn-2 retry, a valid second materialization, and an attempt record
  showing exactly one task-phase execution.
- **Fallback determinism:** the same call compiles and runs unchanged
  against a non-session provider binding.
- **End-to-end:** the review consumer runs phased against a real provider
  with unchanged result authority, terminal routing, and evidence shape.

## Sequencing

Single tranche. Entry needs only landed substrate: Q1 fragments and the
target-2.17 turn queue. No dependency on Q3 (identity) or Q4 (views);
scheduled as Stage Q5 in the language-quality roadmap, which owns its
required order (design review, plan review, TDD, gated closure).
