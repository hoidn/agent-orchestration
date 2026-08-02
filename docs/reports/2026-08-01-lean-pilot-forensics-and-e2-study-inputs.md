# Lean Pilot Post-Hoc Forensics And Post-E2 Study Inputs

- **Status:** post-hoc forensic analysis and recorded study-design inputs;
  changes no locked pilot record, amends no accepted plan, selects no tranche
- **Date:** 2026-08-01
- **Provenance:** owner-directed recording in the 2026-08-01 interactive
  session, following review of the incorporated E-series roadmap
- **Analyzed evidence root:**
  `/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/pilot-2026-07-27/a1-v7/`
  (pilot lock
  `sha256:b8d69ba2f3d2b2e7bc6d9181d776db0b7abacd2035f851cd44be613dac6d8503`)
- **Companion records:**
  [deterministic report](2026-07-26-orc-effectiveness-lean-pilot.md),
  [owner-decision handoff](2026-07-31-orc-effectiveness-lean-pilot-owner-decision.md),
  [final evidence review](../../artifacts/review/lean-pilot-a1-v7-final-evidence-review.md),
  [accepted E2 trial component plan](../plans/2026-08-01-workflow-lisp-e2-trial-component-plan.md)
- **Program state at recording:** E1 is complete with `PASS_E1` at
  `577715f1`; the target-2.25 E2 plan is accepted at `c6046d38` with its
  Task-10 fixed study contracted as a platform mechanism proof
  (DIRECT/COORDINATOR/ORC over deterministic fixture repositories, explicit
  treatment-specific failure accounting, no effectiveness claim). `PASS_E2`
  makes selected E3 eligible only through review of that first fixed study.

Purpose: record (1) the mechanism behind the pilot's four
`PROTOCOL_FAILURE` outcomes, (2) the corrected reading of the
`DIRECT` 3/3 headline, and (3) the study inputs these facts imply for the
post-`PASS_E2` study program — the E3-gating first-fixed-study review and
any subsequent effectiveness study. The locked pilot outcomes stand
unchanged under the pilot's precommitted no-retry rule; this report adds
interpretation and forward inputs only.

## Forensic Findings

### F1. All four nonviable arms died on one identical guard event

Every nonviable arm (ORC in blocks `b-b5e157fc7ffaca68` and
`b-ed345c592d9b1d50`; COORDINATOR in `b-ed345c592d9b1d50` and
`b-5970f312e6698e50`) terminated on a byte-identical
`product_manifest_guard` event:

```json
{"event_kind": "product_manifest_guard", "phase": "discover",
 "mutation_disposition": "MUTATED",
 "before_digest": "sha256:7da9b1a7c7500873e6d8ff895ac0d1e4532e2c50077a59e04b4542c5b428e3f5",
 "after_digest":  "sha256:e641492e1d72cb072255949ff448a3b6e6d34933f8eb1b029717f3929fe69f3a"}
```

(each arm's `workspace/.pilot/runtime/controller-events.jsonl`, final event).
Identical before/after digests across both treatments and all blocks
establish one systematic mutation, not independent agent misbehavior.

### F2. The mutation is tool-cache noise, not product work

Every preserved arm workspace, including viable ones, contains
`.pytest_cache/` at the workspace root. The guard's exclusion list was only
`[".orchestrate", ".pilot/runtime", "logs"]` (`control.json`), and
`PYTHONDONTWRITEBYTECODE=1` in the frozen treatment environment removed
`__pycache__` as a source, leaving pytest's cache as the ambient mutation
channel. Block-3 blinded reviewers independently flagged "pytest cache
artifacts" inside the diffs of both the DIRECT and ORC products.

[INFERENCE, marked as such]: the discovery-phase agent ran pytest —
plausibly the visible check itself
(`python -m pytest -q tests/test_smoke_entrypoint.py`) — which is consistent
with the discovery prompt (it forbids *editing* files, not running checks)
and with identical cache bytes across arms. The primary evidence above does
not depend on this inference.

### F3. Corrected decomposition of "DIRECT won 3/3"

- Blocks 1-2 `DIRECT_VS_ORC`: `A_WIN (A_ONLY)` — forfeits under F1/F2, not
  behavioral comparisons.
- Block 3 `DIRECT_VS_ORC`: both products passed hidden acceptance at full
  score (per label map `evidence/label-maps/b-5970f312e6698e50.json`:
  `candidate-3cca13b2595a` = DIRECT, `candidate-82407e4546dd` = ORC). Both
  reviewers: "Both candidates pass hidden acceptance at full score, so the
  distinction rests on maintainability and scope" (review digests
  `sha256:881cf86d…` and `sha256:b10b517f…`). DIRECT won a
  maintainability/scope preference; ORC was penalized for a broad parser
  surface with `NotImplementedError` branches.
- The zeros-returning COORDINATOR product in block 3 is the untouched
  baseline scaffold: that arm failed at discover and never reached
  implement. It is not evidence of gamed implementation.
- Efficiency signals point in opposite directions: ORC used 7 provider calls
  versus DIRECT's 1, but ORC's median wall clock was ~2.4x faster
  (235,971 ms vs 569,897 ms); cost/token columns are `UNKNOWN`.

Net: the pilot supports "no demonstrated orchestration benefit on a
one-context task, with real protocol-surface fragility," not "demonstrated
behavioral inferiority." This matches the owner-decision record's wording
("the observed pilot did not favor `.orc`") and narrows over-readings of the
3/3 headline.

### F4. The forfeit class is platform debt, structurally retired by E1

The in-band guard brackets existed because the runtime could not observe
phase purity externally (`G0_BLOCKED`,
[control-plane feasibility report](2026-07-23-experiment-control-plane-feasibility.md)).
Landed E1 `run-ref` replaces enforcement-in-band with recorded
workspace-delta evidence classified at adjudication time, and the accepted
E2 plan runs platform-owned checks in the completed arm workspace, which
removes this failure class structurally rather than by widening exclusion
lists.

## Recorded Post-`PASS_E2` Study Inputs

These inputs do not amend the accepted E2 plan or its Task-10
DIRECT/COORDINATOR/ORC arm set. They are recorded for (a) the reviewers of
the first fixed study, whose E3-gating reading should separate apparatus
artifacts from treatment outcomes as F1-F3 required for the pilot, and
(b) the preregistration of any subsequent effectiveness study. Inputs 3-5
are already structurally absorbed by the accepted E2 design (post-arm
platform checks without in-band guards; deterministic fixture pins;
committed-cell reuse with fresh-ordinal rerun of incomplete cells) and are
retained as review checkpoints only.

1. **Candidate arm set is a 2x2 factorial over QA placement, plus DIRECT**,
   preregistered before any platform run:
   - DIRECT (no orchestrated QA);
   - design-QA arm (owner-proposed 2026-08-01): design, design
     review/revision, then one single-shot implementation call with no
     post-implementation fix;
   - product-QA arm: implement, independent review, one fix;
   - the rich pilot topology (both QA placements).
   The factorial framing attributes orchestration value to pre-execution
   design QA, post-execution product QA, or their interaction, rather than
   a one-dimensional rich-vs-lean contrast. Within-`.orc` contrasts isolate
   topology without a new coordinator-parity arm;
   language-vs-decomposition isolation continues to ride on the existing
   DIRECT/COORDINATOR/ORC pairs. Two evidence flags the preregistration
   must carry: (a) the only viable pilot ORC run exercised its
   post-implementation fix round, so the design-QA arm removes the one
   affordance the sole ORC success used — an informative, precommitted
   risk; (b) the pilot's block-3 maintainability penalty traces to
   plan-phase scope elaboration, so design-review criteria must include an
   explicit parsimony clause (reject designs whose surface exceeds the
   task). Arms differ structurally in call budget, so the recorded budget
   policy (equal-cost versus equal-structure) plus mandatory cost columns
   arbitrate efficiency claims.
2. **Real in-loop acceptance checks in treatment workflows** replace
   shape-only smoke floors (the pilot's block-3 baseline scaffold passes the
   pilot smoke test unmodified; a fix loop can only fix what its checks
   catch).
3. **No in-band purity guards** (absorbed): phase-integrity claims rest on
   recorded workspace-delta evidence with the delta classification policy
   (for example, tool-cache paths as ignorable) precommitted, not decided
   after outcomes exist.
4. **Environment hygiene precommitted** (absorbed for fixture repos): cache
   suppression (`-p no:cacheprovider`) or a complete exclusion inventory;
   ambient mutation sources enumerated before launch — mandatory again the
   moment realistic, non-fixture repositories enter a study.
5. **Retry/discard semantics preregistered** (absorbed): infrastructure
   failure versus treatment outcome classified by rule, not ex post.
6. **Cost and token accounting mandatory for effectiveness comparisons** —
   no `UNKNOWN` columns; the pilot left call-count and wall-clock pointing
   in opposite directions with no cost column to arbitrate.
7. **Task selection beyond A1 for any effectiveness claim:** the aging
   nanoBragg benchmark alone caps external validity (public source,
   training-data familiarity shared across arms), and Task-10 fixtures prove
   mechanism, not effectiveness. The designed prospective candidate remains
   the PtychoPINN reloadable-generator extension-boundary task (F1), under
   the superseded design's conditions and a `decision_lock.v1` numeric rule
   as required by the
   [lean-pilot design](../superpowers/specs/2026-07-26-orc-effectiveness-lean-pilot-design.md).

## Claims Not Made

- No locked pilot outcome is reinterpreted, resumed, or re-adjudicated; the
  recorded `PROTOCOL_FAILURE` outcomes stand under the precommitted rule.
- No effectiveness conclusion is made in either direction.
- Nothing here amends the accepted E2 plan (`c6046d38`), its Task-10 arm
  set, or any exit gate; post-`PASS_E2` arm sets and decision rules are
  final only in their own reviewed plans.
- The F2 pytest attribution beyond the recorded guard events is marked
  [INFERENCE] and is not load-bearing for any input above.
