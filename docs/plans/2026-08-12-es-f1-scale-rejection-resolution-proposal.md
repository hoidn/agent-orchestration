# ES F1 Scale-Rejection Resolution Proposal

**Status:** Superseded on the core recommendation. The owner had already
selected a replacement-task design on 2026-08-06 —
[ES F1v2 config-ownership campaign](../superpowers/specs/2026-08-06-es-f1v2-config-ownership-task-design.md)
(committed `cd9d3910`) — which this proposal's author had not discovered when
writing sections 4–5. Section 10 records the comparison. Sections 1–3
(evidence and root finding) stand and agree with F1v2 §1; section 7
(apparatus disposition) remains live and undecided. This document creates no
gate, no review obligation, and no roadmap-level unit.

**Date:** 2026-08-12
**Author:** assistant session (orchestration:2), at owner request
**Decision required from:** owner
**Line references:** as of HEAD `f2b5751a` (docs unmodified in working tree)

## 1. What happened

ES F1 refreeze Task 3A (viability and oracle-calibration proof) reached its
strict terminal gate and was rejected out of band:

- Complete evaluator, both proof passes, and A/B determinism passed.
- Canonical metric (`implementation_delta_physical_lines.v1`): **615
  implementation additions**, 298 deletions, base 5,030 physical lines,
  postimage 5,347 (net +317). Required band: **5,000–10,000 inclusive**.
- Rejection recorded content-addressed: capture `ES_F1_TASK3A_SCALE_REJECTION`,
  `~/.local/state/orchestrator/es-reference-products/captures/task3a-24d907a-attempt-09/scale-rejection.json`,
  SHA-256 `79883e9e098463fc5f7a927ab7762cc8172408cc62763d68ee6cf538ad9a0692`.
- Lineage: reference commit `24d907ab`, task seed `4b5abdda`, projection
  `8f191031`. No `reference-product.json` was created. Task 0 record,
  governing plan, and `boundary_proofs.py` unmodified.
- Verified state: 270 calibration tests passed plus one intentional red — the
  load-bearing gate test that requires the absent in-band reference product.
  The Task 3A apparatus (+11,694/−10 lines across `f1_evaluator.py`,
  `reference_calibration.py`, and their test modules) is uncommitted.

The controller behaved correctly: it refused to invent work to cross the
threshold (refreeze plan lines 842–846), refused to weaken the red gate, and
halted fail-closed.

## 2. The deadlock

The refreeze plan (lines 933–937) prescribes the consequence of a below-band
reference: "Replace or coherently redesign the task, rerun the projection-wide
census, and restart the reviewed pre-run amendment and package freeze." The
standing owner steering forbids opening a new amendment review pair. Both
constraints are honored simultaneously only by a full stop, which is where the
controller is. Only the owner can resolve it: the 5,000–10,000 gate "is
nevertheless exact and inclusive because the owner explicitly selected it as
the pre-run calibration contract" (lines 1040–1041). An owner-selected
criterion can be owner-re-selected.

## 3. Root finding

**"Solution-neutral" and "must cost 5,000–10,000 delta lines" are mutually
inconsistent for this task shape.** The band implicitly priced per-architecture
duplication across the 15-row matrix (~15 × ~400 lines ≈ 6,000); a competent
general mechanism parameterizes the matrix in ~600 lines. Two independent
honest measurements corroborate the family's natural scale:

| Reference | Honest delta | Band |
| --- | --- | --- |
| A1 anchor | 667 lines (refreeze plan line 154) | — |
| F1 Task 3A complete reference | 615 additions | 5,000–10,000 |

Any candidate agent capable enough to be worth studying will find the compact
solution, so the band is unreachable in any honest variant of this shape —
that is a finding about the task design, not a failure of the reference.

Two clauses sharpen the option space:

- Candidates were never LOC-judged: "Candidate contracts and outcomes remain
  free of LOC, cluster-count, file-count, and churn acceptance criteria"
  (lines 845–846). The band gates only the controller's own pre-run reference.
  Amending it touches zero candidate-facing bytes.
- The owner-selected operational multi-context criterion already contains four
  structural components independent of LOC: four independently unmet clusters,
  three authenticated cross-blob edges, remove-one failures for every
  implemented cluster slice, and the non-collapse requirement (lines 832–836;
  component plan lines 1026–1030).

## 4. Option space

| Path | Summary | Cost | Principal risk |
| --- | --- | --- | --- |
| A | Redesign F1 so largeness is irreducible (heterogeneous clusters no single abstraction factors) | New seed + projection census + Task 3A rerun; days–weeks | Second rejection: both measurements say ~0.6k; engineering irreducibility is the problem that just failed |
| B | Amend the criterion: drop the LOC band; the four structural criteria become the sole multi-context gate | One proportionate review pass (roadmap lines 158–163), then decision_lock.v3 → ES Task 7 | Study no longer tests "large scope" as literally directed |
| C | Diagnose first: post-mortem the 615-line reference against the four-cluster structure using the rejection capture's per-row metric data | Hours; no owner commitment | None — informs every other path |
| D | Replace F1 wholesale with a task of intrinsic largeness (e.g., cross-subsystem port/migration) | Highest: task discovery + full census/freeze cycle | Same irreducibility problem plus fairness/neutrality re-proof |
| E | Run ES Task 7 at existing (A1) scale now; large scope becomes a follow-on study | Small; Task 3A apparatus is built and reusable | A1 pilot forfeited (refreeze plan lines 95–97); forfeit cause must be shown scale-independent first |

## 5. Recommendation

**C now, then B.**

1. **C (hours):** controller post-mortems the rejection capture: which of the
   four Task-0 clusters the 615 lines actually cover, and whether one
   mechanism spans them. Expected outcome given A1 = 667: the
   general-mechanism hypothesis confirms and the band is unreachable in any
   honest shape of this family.
2. **B (primary):** owner authorizes one scope amendment replacing the LOC
   band with the four structural criteria as the complete multi-context gate.
   Rationale: the band was a proxy for "forces multi-context work"; the
   structural criteria measure that property directly, are already reviewed,
   and inflating a LOC proxy by task redesign invites exactly the
   invented-work failure mode the plan prohibits.
3. **A/D in reserve** only if the scientific question intrinsically requires
   5,000–10,000-line deltas (e.g., context-exhaustion behavior is itself the
   object of study). Then C's post-mortem specifies what irreducibility the
   redesign must engineer.

## 6. Amendment mechanics (path B)

Edits, all doc-level, one proportionate review pass total:

1. Refreeze plan — remove the 5,000–10,000 reference-size condition from the
   operational criterion (lines 832–846) and from completion criterion 3
   (lines 2240–2243); record the Task 3A scale rejection as the criterion's
   measured outcome with its capture digest.
2. Component plan — same criterion update at lines 154–158 and 1019–1030.
3. Task 3A closure — terminal state becomes "content-addressed rejection
   recorded; general-mechanism finding adopted"; the gate test recognizes that
   disposition while continuing to block promotion of any reference product
   that does not exist in-band.

Explicitly unchanged: four-arm treatment topology; no live allocation before
owner adoption; `decision_lock.v3` requirement; candidate contracts (already
LOC-free); the four structural multi-context criteria; no new projection
census (the census binds the frozen consumer set, which no B edit touches).

## 7. Task 3A apparatus disposition (any path)

The +11,694-line evaluator/calibration apparatus and the rejection evidence
should be committed under every path except full abandonment: the plan treats
scale rejection as a canonical terminal outcome, all forward paths reuse the
apparatus, and an uncommitted day of work is the largest current operational
risk. Commit shape: gate test updated to accept the recorded rejection
disposition as a green terminal state that still blocks Task 4/promotion, so
the tree commits green without falsely closing Task 3A.

## 8. Open questions for the owner

1. Is the 5,000–10,000-line delta itself the object of study, or was it a
   proxy for multi-context difficulty? (Decides B vs. A/D.)
2. What caused the A1 pilot forfeit, and was it scale-dependent? (Gates E.)
3. Should the C post-mortem land as a short appendix to the refreeze plan or
   as a standalone evidence file? (Default: evidence file beside the capture.)

## 9. Draft steering message (withdrawn)

The path C→B steering message originally drafted here is withdrawn together
with path B; see section 10.

## 10. Supersession record (2026-08-12)

Path B above ("drop the LOC band, rely on the four structural criteria") is
withdrawn: attempt-09's 615-line reference passed the complete evaluator and
both proof passes, demonstrating that the structural criteria are satisfiable
at one-context scale — structure does not enforce discriminative difficulty,
which is the band's real function. A band-less F1 study would run in the
regime A1 (667 lines) already showed non-discriminative: a predictable null
spending the one-shot frozen study. F1v2 resolves the same rejection with a
measured historical anchor (+8,698 production additions, mid-band, zero
padding) instead of a third guessed band, and seeds the hidden evaluator from
the real campaign's fix-tail. It is the superior resolution; see its §8 for
the recorded rejection of path B.

Carried forward from this proposal into F1v2 execution:

1. **Section 7 apparatus disposition** — the +11,694-line Task 3A apparatus
   has been uncommitted since 2026-08-05; F1v2 §6 keeps the metric, census,
   and calibration loaders, so commit it under the rejection-terminal-state
   shape before the port begins.
2. **Governance costing** — F1v2's "replace or coherently redesign" path runs
   under the collapsed refreeze pipeline (`f2b5751a`) with proportionate
   review passes; it must not regrow the pre-remediation gate stack.
3. **Census recurrence guard** — F1v2 §4's configuration-consumer census must
   inherit the class-level disposition rule from the 2026-08-04/05 governance
   remediation; configuration read sites outnumber generator consumers, and a
   per-site quota would reproduce the audited ratchet at larger scale.
4. **Leak scope addition** — the F1v2 non-delivery proof should note the
   residual channel of provider training data memorizing the public campaign
   history, alongside the visible-surface checks it already specifies.
