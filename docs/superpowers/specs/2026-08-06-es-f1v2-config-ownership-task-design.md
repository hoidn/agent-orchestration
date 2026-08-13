# ES F1v2: Config-Ownership Campaign Task Design

**Status:** Replacement task design for the ES effectiveness study, following the
Task 3A out-of-band scale rejection of F1 (extension-boundary task, measured 615
implementation additions against the required 5,000–10,000 band). Owner-selected
from a brainstormed option space on 2026-08-06 and synthesized on 2026-08-12 with
`docs/plans/2026-08-12-es-f1-scale-rejection-resolution-proposal.md`: this design
is the primary path; that proposal contributes the immediate triage steps
(Section 9) and the recorded fallback (Section 10).

**Authority context:** Subordinate to
`docs/plans/2026-08-03-es-f1-large-scope-refreeze-execution-plan.md` (including
its Section 0 owner amendment) and the authorities that plan lists. The rejection
record is
`/home/ollie/.local/state/orchestrator/es-reference-products/captures/task3a-24d907a-attempt-09/scale-rejection.json`.
This design triggers the plan's out-of-band path: "replace or coherently
redesign F1, repeat the full census and evaluation" — with the redesign scoped
here.

---

## 1. Why F1 failed, and the calibration principle

The rejected F1 asked candidates to build a reloadable-generator extension
boundary. The generator registry rework (PtychoPINN commit `938bf8399`,
2026-07-08, ~4.7k production lines) is **inside** the frozen projection, so the
heavy machinery already existed; a complete, evaluator-passing solution is the
wiring around it — 615 implementation additions, invariant to matrix width,
because routing an architecture through a shared boundary costs a registry row,
not an implementation.

Both failed scale targets to date (A1's and F1's) were guessed bands with no
historical anchor. The corrective principle adopted here:

> **A study task's scale is admissible only when a real completed implementation
> of that task, measured under the study metric, already exists.**

## 2. The replacement task

**F1v2 = the PtychoPINN configuration-ownership campaign.** The repository
itself performed this work on 2026-07-22 → 2026-07-31 — entirely **after** the
frozen source commit `c081b7b6` (2026-07-21), so it is absent from the
history-free projection candidates receive, while its true size and failure
modes are known to the controller.

Task content (stated here in controller terms; the provider-visible brief is
authored solution-neutrally during the refreeze):

1. Centralize execution-configuration ownership behind strict public
   resolution entry points (the `resolve_training_config`-style surface),
   with explicit file-mapping vs. CLI-patch precedence.
2. Make configuration resolution transactional on the torch path: no partially
   applied or ambiently mutated configuration state.
3. Retire tolerant/compatibility configuration loaders; a retired path must be
   removed or fail loudly, not silently coexist with the new authority.
4. Isolate legacy configuration state from modern paths.
5. Validate simulation mappings at the boundary; derive public input field
   names rather than duplicating them.
6. Keep every existing downstream consumer working: both backends, CLI entry
   points, workflow components, and study scripts construct their
   configurations exclusively through the new public resolution surface.

The projection already contains the campaign's true starting point (commit
`5bc4207bb`, 2026-07-16, "add simulation recipes and close config boundaries"),
so candidates begin exactly where the real implementer began.

## 3. Scope calibration (measured, not guessed)

Real campaign totals over 2026-07-22 → 2026-07-31 (production Python,
tests/docs excluded, per the repository's own history):

- **+8,698 production additions / −11,197 production deletions**; +14,565 test
  lines besides.
- 19 commits over 9 days; principal commits: `7d630bcc1`, `3543487d8` (+1,127),
  `97b8458f8` (+2,001), `29834b515` (+1,679), `f5e42fdf5`, `70c2118d5`
  (−2,284), `9afeadcd6`, `b7ecaec2b` (+1,638/−5,169), `24f4a0273`, `7415456c3`,
  `015ca6e93` (+728).
- Multi-surface spread: 15+ files with ≥100 changed lines across
  `ptycho/config/`, `ptycho_torch/config_*`, both backends' `workflows/`,
  `ptycho_torch/cli/`, and `scripts/` (largest: `config_resolution.py` 1,603;
  `ptycho/config/resolution.py` 1,061; `config.py` 758; `cli/shared.py` 749;
  `config_factory.py` 658; `execution_request.py` 507).

The measured 8,698 sits mid-band in the owner-directed 5,000–10,000 inclusive
`implementation_delta_physical_lines.v1` requirement with zero padding. The
band remains **reference-only calibration**: it gates the adapted reference
product during the refreeze and is never a candidate acceptance, ranking, or
stopping predicate (existing plan Section 1 bounds 1–2 carry over verbatim).

Deletions are not banded. Retirement of tolerant loaders is enforced
behaviorally (Section 4, bypass class), not by a deletion-count gate.

## 4. Hidden evaluator: clauses seeded from the observed fix-tail

The real campaign's post-completion fix-tail is the empirical catalog of how
this task fails when done incompletely. Each observed regression seeds a hidden
clause; negative calibration cases reproduce the historical defect and must
fail in the owning clause.

| Observed regression (real commit) | Hidden clause seed |
| --- | --- |
| `fix(config): complete strict public resolution contracts` (`f5e42fdf5`) | Public resolution rejects unknown/ill-typed fields; no tolerant fallback survives |
| `fix(config): preserve sampling bridge fields` (`b6c669af4`) | Bridge/sampling fields survive resolution round-trip byte-exactly |
| `fix(studies): build nested grid-lines training config` (`24ebffbf3`) | Downstream study scripts construct configs solely via the public surface and still run |
| `fix(synthetic): validate rect_s1s2 initialization coherence across config surfaces` (`100d50d2a`) | One initialization contract across all config surfaces; cross-surface divergence rejected |
| `fix(config): require string initialization modes` (`6ab1716ec`) | Mode fields carry one canonical representation; coercion drift rejected |
| Dual-path risk implicit in `70c2118d5`/`b7ecaec2b` retirements | **Bypass oracle:** any surviving ambient read, tolerant loader, or legacy mutation path reachable from a public entry point is a failing bypass |

Structural clauses reuse the existing apparatus concepts one-to-one:

- **Consumer census** — of configuration read/construction sites (replaces the
  generator-consumer census); every production consumer is assigned, none
  invented downstream.
- **Bypass oracle** — AST inventory plus runtime probes for ambient
  configuration access (replaces the legacy-generator bypass oracle).
- **Identity/provenance proofs** — a resolved configuration carries its source
  provenance (file mapping vs. CLI patch) and survives a fresh-process
  round-trip (replaces checkpoint/reload identity proofs).
- **Behavior preservation** — the provider-visible pre-edit pytest selector set
  (fresh-baselined during refreeze) must remain green; existing training-path
  behavior is exercised, not redefined.

## 5. Reference product: adapt, don't author

The Task 3A analogue becomes **adapt-and-measure**: derive the reference
product by adapting the real campaign diff onto the exact successor task seed,
then run the full evaluator and measure under the pinned metric. All existing
Task 3A discipline carries over unchanged: content-addressed external
repository, never delivered to a provider, package-level non-delivery proof,
strict inclusive band, no padding, and rejection of any padding-only change.
The reference is calibration authority only; candidates may take a different
shape and are judged solely by the behavioral clauses.

The history-free projection already withholds the campaign from candidates.
The non-delivery proof must additionally show no provider-visible surface
(brief, prompts, assets, packet templates) names the campaign's commits, ADR
text, or design vocabulary in a way that leaks the reference decomposition.
The post-freeze boundary-architecture doc (`b5a2c710a`) is not in the
projection; the census must confirm the projection contains no equivalent
pre-freeze document that would leak the campaign's design.

## 6. Apparatus impact map

| Surface | Disposition |
| --- | --- |
| Source projection `8f191031` / task-seed derivation | **Unchanged** (same frozen commit; new seed child for new visible task bytes) |
| Metric `implementation_delta_physical_lines.v1`, A1 anchor, census/calibration loaders | **Unchanged** |
| Four-arm topology, providers, prompts skeleton, metering, decision-lock machinery, trial envelope | **Unchanged** (Section 1 bound 6) |
| Task brief, visible selector set, candidate contract | **Rewritten** for F1v2 |
| Hidden evaluator matrix (15-architecture lifecycle) | **Replaced** by the Section 4 clause set |
| Boundary/bypass/identity proof machinery | **Concept-ported** from generator boundary to config ownership |
| Reference product | **Adapted** from real campaign history (Section 5) |
| Refreeze plan Tasks 1–3A artifacts | Re-run against F1v2 content under the same amended plan structure (Tasks 1, 2, 3, 3A, then consolidated Task 4) |

The rejected F1 package is recorded `SUPERSEDED_PRELAUNCH_SCOPE_TOO_SMALL`
alongside its predecessor, with the same machine proofs of zero attempt/
denominator contribution.

## 7. What this approach makes harder later

- Refactor-shaped acceptance is subtler than feature-shaped: reviewers must
  hold the line that the reference's decomposition is not normative.
- The clause set is anchored to one repository's config idioms; F2+ tasks need
  their own historical calibration rather than inheriting this evaluator.
- Any later change to PtychoPINN's public config surface on the live `refactor`
  branch does not affect the frozen study, but makes post-study interpretation
  against the shipped repo less direct.

## 8. Rejected alternatives (recorded for provenance)

- **Earlier-projection replay** (backend-dispatch or torchapi arcs): strictly
  larger rebuild — invalidates the projection identity itself; squashed arcs
  have murkier boundaries; staler dependency tree.
- **Multi-task battery of naturally small tasks:** multiplies the
  non-discriminative regime A1 already demonstrated; single-task apparatus
  would need rework; deferred as the designed F2+ direction once one real
  result exists.
- **Keep F1, drop the band:** cheapest, but spends provider budget on a task
  A1 evidence predicts is one-context-doable; probable null. Retained as the
  owner-activated fallback in Section 10, not as a live alternative.
- **Full nanoBragg port:** no completed historical implementation to measure —
  a third guessed band, the exact failure mode this design eliminates.

## 9. Execution sequence (synthesis)

Ordered; steps 1–2 are prerequisites of step 3 and proceed under existing
authority without a new review pair.

1. **Commit the Task 3A apparatus now.** The +11,694-line evaluator/calibration
   apparatus and the content-addressed rejection evidence are committed with
   the scale rejection recorded as a green terminal disposition that continues
   to block Task 4 and any reference-product promotion. An uncommitted day of
   apparatus work is the largest current operational risk, and every forward
   path reuses these bytes. (Adopted from the resolution proposal, Section 7.)
2. **Run the hours-scale post-mortem.** Analyze the rejection capture's per-row
   metric data: which of the four Task-0 clusters the 615 lines cover and
   whether one mechanism spans them. Its output is evidence beside the capture
   and directly informs F1v2 clause design — in particular, which abstraction
   moves collapse per-site work, so F1v2's bypass clauses can name them.
   (Adopted from the resolution proposal, path C.)
3. **Execute this design as the primary path** under the amended refreeze plan
   structure (Tasks 1, 2, 3, 3A-analogue, consolidated Task 4). The rejected
   F1 package is recorded `SUPERSEDED_PRELAUNCH_SCOPE_TOO_SMALL`.

Why the resolution proposal's path B (drop the LOC band, keep F1) is not the
primary path: its own root finding — "any candidate agent capable enough to be
worth studying will find the compact solution" — predicts that every capable
arm, DIRECT included, solves F1 at ~615 lines, reproducing the A1 tie. The
structural criteria gate the controller's reference, not candidate difficulty.
B is therefore the cheapest path to a probable null, and it reinterprets the
owner's explicit output-size directive as a proxy without owner ratification.
Conversely, this design's scale is measured (8,698), its reference passes the
band by construction, and the config-ownership shape resists the compaction
that defeated F1: per-consumer migration is per-site work, and the one cheap
shortcut — a tolerant compatibility shim — is exactly the bypass class the
Section 4 clauses reject.

## 10. Recorded fallback (owner-activated only)

If the owner explicitly decides the 5,000–10,000 directive was a proxy for
multi-context difficulty rather than an output-size requirement, the fallback
is the resolution proposal's path B: one proportionate amendment dropping the
LOC band, with the four structural criteria (four independently unmet
clusters, three authenticated cross-blob edges, remove-one failures,
non-collapse) as the complete multi-context gate, then `decision_lock.v3` and
ES Task 7 at F1's natural scale. This fallback is not active; activating it
requires an owner decision message and supersedes Sections 2–8 of this design.

## 11. Open decisions for the refreeze

1. Exact visible pytest selector set for the fresh pre-edit baseline (chosen
   during the F1v2 Task-1 analogue, as before).
2. Whether Section 2 item 5's "derive public input field names" is a hard
   clause or a review-level quality signal (recommend: hard clause; the
   duplication it prevents is a measured historical defect source).
3. Timeout envelope: the real campaign took an expert 9 days; the existing
   48 h arm / 60 h trial envelope was scaled for the rejected F1 and should be
   revalidated against the Task 3A-analogue adaptation effort before lock.
