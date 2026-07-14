# Tracked-Plan Pilot Identity-Retirement Architect Decision Request

**Status:** Decided 2026-07-14 — Path A approved (conditional
`reviewed_internal_identity_retirement`, evidence collection only). See the
Architect Decision Record below. Source edit remains prohibited until the
complete pre-edit gate commits.

**Decision owner:** Project architect.

**Decision scope:** Select the compatibility path for the internal
`tracked-plan-phase` migration and assign the human ownership needed to unblock
or deliberately defer it. This document is a decision request, not a state-store
owner attestation, retirement record, source-edit authorization, or runtime
input.

## Executive Decision

The tracked-plan procedure-first pilot is stopped before Task 1A. Converting
`tracked-plan-phase` from an internal `defworkflow` call boundary to an inline
`defproc` would retire persisted internal workflow, call-frame, checkpoint,
program-point, presentation, state-allocation, and source-map identities.

The architect must select one of three paths:

1. **Conditionally pursue reviewed internal identity retirement.** Name a
   genuine human owner for every known state store, authorize the required
   scan/quiescence process, and proceed only if those owners attest that no
   supported live/nonterminal run or old-identity consumer remains.
2. **Require strict compatibility without a source-crossing migration.** Leave
   `tracked-plan-phase` unchanged and close this pilot, or charter an
   identity-preserving redesign only when no supported old run must cross
   changed source.
3. **Require the general atomic state upgrader.** This is mandatory if the
   migration remains desired and any supported old run must cross changed
   source, even when the redesign preserves persisted identity names.

Missing ownership, incomplete store scope, an unknown consumer, or a supported
old run selects strict compatibility. An architectural preference for
retirement does not override that fail-closed rule.

## Current Facts

The following facts were established without modifying the pilot source,
creating evidence placeholders, or changing any state store:

- The generic identity-compatibility prerequisites passed their focused,
  broad, production-compile, specification, and quality gates. The audited
  handoff is commit `f5adcb79`.
- The pilot is the current roadmap selector but is recorded at commit
  `45eadbdc` as `STOP: missing known-store owner attestation`.
- Roadmap and capability routing were aligned to that stop in `3186ca47`.
- The pilot source
  `workflows/examples/design_plan_impl_review_stack_v2_call.orc` and frozen
  baseline `tests/baselines/procedure_first/tracked_plan_phase.json` remain
  unchanged.
- The old internal callee is
  `examples/design_plan_impl_review_stack_v2_call::tracked-plan-phase`. The
  retained public boundary is
  `examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack`.
- The canonical repository store
  `/home/ollie/Documents/agent-orchestration/.orchestrate/runs` is nonempty. At
  the read-only preflight it contained 4,165 immediate run directories,
  322,629 files, and approximately 6.2 GiB. No genuine named-human owner
  attestation existed for it.
- The dedicated new-ID evidence store
  `/home/ollie/Documents/agent-orchestration/.orchestrate/procedure-first-pilot-evidence/tracked-plan-phase/workspace/.orchestrate/runs`
  and its parent chain did not exist. Its required empty/isolation proof and
  owner attestation are therefore not yet available.
- `/tmp` contained 355 helper-shaped
  `design-plan-impl-stack-*` scratch directories. None were removed. The
  SHA-256 of their sorted absolute-path list was
  `b535f9a6c4debe837ba9d606420380c572c915f2e7492c46a366f37533b24b24`.
- Absence from external stores is not asserted. EasySpin, PtychoPINN, the paper
  repository, CI artifacts, backups, copied workspaces, and other locations
  remain unknown unless concrete roots are enumerated, scanned, and attested.

These counts are discovery facts, not evidence that the old identities are or
are not still supported.

## Governing Constraints

The accepted authority is
`docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`.
Its relevant rules are:

- `strict_compatibility` is the default.
- `reviewed_internal_identity_retirement` applies only to an internal,
  non-public, non-promoted/non-live callee with a retained public wrapper and
  no supported old-state consumer in every attested known store.
- An unowned store or unknown consumer fails closed to strict compatibility.
- A non-enumerated external store remains unknown, not absent.
- The retirement record is evidence only. It cannot rename state, bypass root
  checksums, remap identities, or make an old run resume under changed source.
- A genuine store owner—not an agent or inferred username—must supply each
  timestamped attestation and hold the named root quiescent through final
  validation and review.
- If a supported old run must cross the source change, the general atomic
  upgrader is required.

The current roadmap order must remain:

1. complete this pilot or deliberately recharter it;
2. complete projection-integrity hardening;
3. execute procedure-first migration waves;
4. execute Stage 6 YAML retirement;
5. deliver provider live binding; and
6. deliver the Workflow Lisp language server.

Projection-integrity hardening is not an alternative way around this decision.

## Decisions Required

### Decision 1: Compatibility path

Select exactly one:

- [x] **A — Conditionally pursue `reviewed_internal_identity_retirement`.**
      This authorizes evidence collection only. It does not authorize the
      source edit.
- [ ] **B — Require `strict_compatibility` without a source-crossing
      migration.** Close the unchanged pilot, or charter an identity-preserving
      redesign only if no supported old run must cross changed source.
- [ ] **C — Require the general atomic state upgrader.** This path is mandatory
      if migration remains desired and any supported old run must cross changed
      source. Defer the pilot until the upgrader is designed, implemented, and
      independently accepted.

**Rationale:**

> The pilot exists to exercise the reviewed retirement class on the narrowest
> eligible candidate. The callee is internal-only with the public stack
> wrapper retained, the generic prerequisites are complete and independently
> audited (`f5adcb79`), and the architect does not require any old run of the
> `design-plan-impl-review-stack` family to resume across the source change.
> Path A authorizes evidence collection only; every downstream gate remains
> fail-closed, and any supported old-run or consumer match reverts the pilot
> to strict compatibility. (Decision supplied directly by the architect in an
> interactive session on 2026-07-14.)

### Decision 2: Known-store scope and accountable owners

For Path A, enumerate every concrete store intentionally used for this family.
At minimum, assign accountable owners below. An architect may name an owner but
must not sign on that person's behalf.

| Store or class | Canonical root | Genuine human owner | Include and scan? | Notes |
| --- | --- | --- | --- | --- |
| Repository run store | `/home/ollie/Documents/agent-orchestration/.orchestrate/runs` | Ollie (ohoidn@stanford.edu) | Yes | Existing nonempty store |
| Dedicated new-ID evidence store | `/home/ollie/Documents/agent-orchestration/.orchestrate/procedure-first-pilot-evidence/tracked-plan-phase/workspace/.orchestrate/runs` | Ollie (ohoidn@stanford.edu) | Yes | Must be created empty and proven isolated before use |
| EasySpin workspace/run store | Not intentionally used for this family (architect record, 2026-07-14) | n/a — not enumerated | No | Absence is not asserted; remains unknown |
| PtychoPINN workspace/run store | Not intentionally used for this family (architect record, 2026-07-14) | n/a — not enumerated | No | Absence is not asserted; remains unknown |
| Paper-repository workspace/run store | Not intentionally used for this family (architect record, 2026-07-14) | n/a — not enumerated | No | Absence is not asserted; remains unknown |
| CI, backup, copied, or other stores | None intentionally used for this family (architect record, 2026-07-14) | n/a — not enumerated | No | Do not assert global absence |

Path A may be approved only after both of the following are recorded literally:

- [x] Every intentionally used known root is enumerated above, with no
      `_Decide_`, `_Required_`, or other unresolved entry remaining.
- `external_store_absence: not_asserted`

If the scope-completeness checkbox cannot be selected or any table entry
remains unresolved, Path A is ineligible and strict compatibility remains
selected. The literal external-absence statement records the boundary of the
claim; it is not evidence about non-enumerated stores.

For every included root, the named owner must provide an independently
attributable, timestamped statement that:

- the attestation applies to that exact canonical root and recorded scan;
- no supported live/nonterminal run or consumer of the queried old identities
  remains there; and
- the root will remain quiescent from the pre-edit scan through final validator
  execution and independent review.

### Decision 3: Scratch-directory disposition

Select one requested disposition. Disposal remains contingent on separately
attributable owner confirmation and recorded evidence; this architect decision
does not itself confirm provenance or authorize deletion.

- [x] Request owner-confirmed disposal of the 355
      `/tmp/design-plan-impl-stack-*` directories after the owner supplies a
      fresh, attributable provenance/shape confirmation.
- [ ] Some or all directories are durable or potentially supported stores;
      enumerate and scan them instead of deleting them.
- [ ] Ownership remains ambiguous; keep the pilot stopped under strict
      compatibility.

**Requested accountable owner and rationale:**

> Requested owner: Ollie (ohoidn@stanford.edu). The directories are
> helper-shaped scratch produced by stack runs; disposal keeps the evidence
> window clean. Disposal remains contingent on the owner's fresh,
> attributable provenance/shape confirmation; if that confirmation fails,
> fall back to enumerate-and-scan rather than deletion.

**Confirming owner and evidence reference (completed by or from separately
attributable owner evidence, not by architectural inference):**

> Pending — intentionally not completed by this decision. Awaits the owner's
> separately attributable confirmation and its recorded evidence reference.

### Decision 4: Quiescence authority

For Path A, identify who can prevent mutations to each legacy root during the
evidence window and who owns the dedicated root's permitted new-ID runs.

| Responsibility | Named human | Enforcement mechanism | Window |
| --- | --- | --- | --- |
| Legacy-store quiescence | Ollie (ohoidn@stanford.edu) | Hold: no new orchestrator runs launched in this repository, and run-launching agent sessions paused, for the window | Pre-edit scan through final review |
| Dedicated new-ID store ownership | Ollie (ohoidn@stanford.edu) | Store created empty by the pilot harness and used exclusively for the pilot's permitted new-ID runs | Creation through final review |
| Final dedicated-store attestation | Ollie (ohoidn@stanford.edu) | Timestamped owner attestation supplied after the clean and interruption/resume runs | After clean and interruption/resume runs |

If quiescence cannot be credibly enforced, Path A is not eligible.

## Consequences By Decision

| Selected path | Immediate roadmap result | What becomes selectable | What remains prohibited |
| --- | --- | --- | --- |
| A — Conditional retirement | Resume Task 1A only after owners and scope are recorded | Harness hygiene, root isolation, scans, genuine attestations, immutable pre-edit evidence | Pilot source edit until the complete pre-edit gate commits successfully |
| B — Strict compatibility without source crossing | Record either closure of the unchanged pilot or an identity-preserving redesign charter that proves no supported old run must cross changed source | The exact next roadmap selector named in the decision record, or no migration | Identity retirement, the current Task 2 source edit, and any changed-source resume without the general upgrader |
| C — General upgrader | Recharter the roadmap before the pilot; mandatory if migration remains desired and any supported old run must cross changed source | The named upgrader design/specification/planning tranche | Family-specific remap, checksum bypass, baseline refresh, or partial state rewrite |

Under no path may an agent fabricate an owner, paraphrase an attestation,
silently delete ambiguous state, refresh the frozen old baseline, or infer
external absence.

## Architect Decision Record

Complete all applicable fields:

- **Selected path:** A
- **Decision rationale:** Exercise the reviewed retirement class on this
  narrowest eligible internal candidate; no old run of this family needs to
  resume across the source change; prerequisites are complete and audited
  (`f5adcb79`); Path A authorizes evidence collection only and every
  downstream gate remains fail-closed.
- **Repository-store owner:** Ollie (ohoidn@stanford.edu)
- **Dedicated-store owner:** Ollie (ohoidn@stanford.edu)
- **Additional enumerated roots and owners:** None. EasySpin, PtychoPINN, and
  paper-repository workspaces are recorded as not intentionally used for this
  family; no CI, backup, or copied stores were intentionally used.
- **Known-root scope complete:** yes
- `external_store_absence: not_asserted`
- **Scratch-directory requested disposition and owner:** Owner-confirmed
  disposal of the 355 `/tmp/design-plan-impl-stack-*` directories requested;
  requested owner Ollie (ohoidn@stanford.edu); contingent on his separate
  fresh provenance confirmation.
- **Scratch confirming owner/evidence reference:** Pending — awaits the
  owner's separately attributable confirmation; not completed by this
  decision.
- **Quiescence authority and mechanism:** Ollie (ohoidn@stanford.edu); hold —
  no new orchestrator runs launched in this repository and run-launching
  agent sessions paused from the pre-edit scan through final validator
  execution and independent review; the dedicated store is used exclusively
  for the pilot's permitted new-ID runs.
- **Roadmap disposition and exact next selected plan:**
  `docs/plans/2026-07-13-procedure-first-pilot-plan.md` remains the current
  selector, resumed at Task 1A (harness hygiene, root isolation, scans,
  genuine attestations, immutable pre-edit evidence). The pilot source edit
  remains prohibited until the complete pre-edit gate commits successfully.
- **If Path B, choose exactly one:** n/a
- **If Path C, upgrader owner and exact roadmap change request:** n/a
- **Conditions that must be re-reviewed:** any scan match of a supported
  live/nonterminal run or old-frame consumer in an attested store (reverts to
  strict compatibility); any break of the quiescence hold during the window
  (requires re-scan); failed scratch provenance confirmation (falls back to
  enumerate-and-scan, no deletion); discovery of any additional intentionally
  used root (reopens scope and this decision).
- **Architect name:** Ollie (ohoidn@stanford.edu), decision supplied directly
  in an interactive session and transcribed verbatim by the session agent.
- **Decision date/time and timezone:** 2026-07-14T12:52:57-07:00 (PDT)
- **Decision status:** APPROVE

## Acceptance And Handoff

An `APPROVE` decision is actionable only when its selected path is complete
enough to route work:

- Path A must contain no unresolved entries; must name accountable owners for
  every enumerated concrete root; must affirm that every intentionally used
  known root is enumerated; and must include the literal
  `external_store_absence: not_asserted`. The named owners must still supply
  their own attestations after the corresponding scans; architect approval is
  not a substitute. Any missing item fails closed to strict compatibility.
- Path B must choose exactly one disposition: close/abandon the unchanged
  pilot, or charter an identity-preserving redesign that requires no supported
  old run to cross changed source. It must name the exact next roadmap selector.
- Path C must identify the upgrader owner, authorize an exact roadmap-level
  design and planning tranche, and name that tranche as the next selector.
- Every path must record its roadmap disposition and exact next selected plan,
  including an explicit no-migration/closed state when there is no next plan.

After decision, update
`docs/plans/2026-07-13-procedure-first-pilot-plan.md` and
`docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md` to record
the selected route. Do not edit the pilot source or create attestation evidence
as part of recording this architectural decision.

## References

- `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`
- `docs/design/workflow_lisp_procedure_first_reuse_contract.md`
- `docs/plans/2026-07-13-procedure-first-pilot-plan.md`
- `docs/plans/2026-07-13-procedure-migration-identity-compatibility-plan.md`
- `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- `tests/baselines/procedure_first/tracked_plan_phase.json`
- `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
