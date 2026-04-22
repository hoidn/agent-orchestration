# Cross-Tranche Family Prompt Edits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach the major-project roadmap and big-design prompts to surface repeated cross-tranche families, require explicit reuse/consolidation decisions, and allow a tranche to refactor prior tranche-local machinery into shared helpers when that is the smallest safe design.

**Architecture:** This is a prompt-only workflow-authoring change. The roadmap prompt should record likely cross-tranche families as hypotheses and checkpoints, not as hardcoded abstractions. The big-design prompt should confirm or reject those hypotheses against concrete repo evidence and decide whether the selected tranche is a pilot, consolidation point, later family member, or justified local fork.

**Tech Stack:** Markdown prompt assets under `workflows/library/prompts/major_project_stack/`, generated workflow prompt map checks, orchestrator dry-run validation, and focused pytest workflow/prompt contract checks.

---

## Intention

The prompt edits should prevent the failure mode seen in the EasySpin oracle tranches: after a pilot tranche proves a repeated lifecycle, later tranches copy nearly identical lifecycle mechanics instead of extracting shared helpers. The desired behavior is not "abstract everything upfront." The desired behavior is:

- Roadmap phase records likely repeated families and consolidation checkpoints.
- First pilot tranche may build local machinery.
- Second or later family member must explicitly decide whether to reuse, refactor into shared helpers, or justify a local fork.
- A tranche may touch prior tranche-local files when the purpose is a small behavior-preserving refactor needed by the current tranche.
- Designs preserve prior command surfaces and add regression checks when they refactor prior tranche machinery.

These prompts must stay project-agnostic. Do not mention EasySpin, oracle artifacts, T08, T09, or any other domain-specific tranche names in the reusable prompt text.

## Non-Goals

- Do not change the workflow DSL, manifest schema, or runtime.
- Do not require every similar-looking tranche to share code.
- Do not force abstraction during a first pilot when the repeated shape is not proven.
- Do not add tests that assert literal prompt wording.
- Do not alter active workflow run state.

## Files

- Modify: `workflows/library/prompts/major_project_stack/draft_project_roadmap.md`
  - Responsibility: make roadmap drafting identify likely cross-tranche families and checkpoint timing.
- Modify: `workflows/library/prompts/major_project_stack/review_project_roadmap.md`
  - Responsibility: reject roadmaps that miss obvious repeated-family relationships or prevent necessary consolidation.
- Modify: `workflows/library/prompts/major_project_stack/revise_project_roadmap.md`
  - Responsibility: preserve and repair family hypotheses, tranche briefs, and checkpoint language during roadmap revisions.
- Modify: `workflows/library/prompts/major_project_stack/draft_big_design.md`
  - Responsibility: make selected-tranche designs classify family fit and decide reuse/refactor/local-fork boundaries.
- Modify: `workflows/library/prompts/major_project_stack/review_big_design.md`
  - Responsibility: reject designs that blindly duplicate prior tranche mechanics or refactor prior machinery unsafely.
- Modify: `workflows/library/prompts/major_project_stack/revise_big_design.md`
  - Responsibility: preserve and repair cross-tranche reuse decisions during design revisions.
- If present and intentionally used for local workflow launches, sync matching prompt copies under `/home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/`.

## Task 1: Add Family Hypotheses To Roadmap Drafting

**Files:**
- Modify: `workflows/library/prompts/major_project_stack/draft_project_roadmap.md`

- [ ] **Step 1: Add roadmap family-hypothesis guidance**

Insert after the existing paragraph that starts `Do not let evidence, prior artifacts, status labels...`:

```md
For broad multi-tranche projects, identify likely cross-tranche families before finalizing the tranche list. A family is a set of tranches that appears to share a repeated lifecycle, artifact type, validation gate, command surface, downstream consumer, or implementation pattern, even if each member has different domain content.

Record family relationships as hypotheses, not as final abstractions. For each likely family, state:
- candidate member tranches
- the shared lifecycle or repeated mechanics
- which tranche is the likely pilot
- when a later tranche should run a consolidation checkpoint before copying the pilot shape
- which parts are expected to remain domain-specific

Do not hardcode shared helpers before there is evidence. It is acceptable for the first pilot tranche to build local machinery. The roadmap should, however, prevent the second or later family member from blindly copying pilot mechanics by requiring an explicit reuse/consolidation decision.
```

- [ ] **Step 2: Add a roadmap-required-output bullet**

Under `The roadmap must:`, add:

```md
- identify cross-tranche family hypotheses and reuse/consolidation checkpoints when several tranches share a repeated lifecycle, artifact type, validation gate, command surface, implementation pattern, or downstream consumer
```

- [ ] **Step 3: Add tranche-brief guidance**

Near the existing tranche brief instruction, add:

```md
When a tranche belongs to a likely cross-tranche family, its brief should mention the family relationship, prior or future related tranches, and whether the tranche is expected to be a pilot, consolidation point, later family member, or intentionally separate despite superficial similarity.
```

- [ ] **Step 4: Check wording**

Run:

```bash
rg -n "cross-tranche|family|pilot|consolidation" workflows/library/prompts/major_project_stack/draft_project_roadmap.md
```

Expected: the new guidance appears, with no project-specific examples or domain-specific tranche names.

## Task 2: Add Family Checks To Roadmap Review

**Files:**
- Modify: `workflows/library/prompts/major_project_stack/review_project_roadmap.md`

- [ ] **Step 1: Add reject bullets**

Under `Reject or block the roadmap if:`, add:

```md
- a broad roadmap has repeated tranche shapes or lifecycle mechanics but does not identify candidate cross-tranche families, pilot tranches, and reuse/consolidation checkpoints
- a second or later tranche in an apparent family is allowed to copy prior mechanics without requiring a design-time decision to reuse, refactor, or justify a local fork
- the roadmap prevents a later tranche from refactoring prior tranche-local machinery into shared helpers when that refactor is necessary to avoid duplicated durable infrastructure
```

- [ ] **Step 2: Review for overreach**

Read the full reject list. Confirm the new bullets require visibility and checkpoints, not premature shared-helper design.

## Task 3: Preserve Family Decisions During Roadmap Revision

**Files:**
- Modify: `workflows/library/prompts/major_project_stack/revise_project_roadmap.md`

- [ ] **Step 1: Add revision guidance**

After the paragraph that starts `Keep the broad project brief immutable provenance`, add:

```md
If review findings concern repeated tranche shapes, cross-tranche family relationships, pilot/consolidation timing, or reuse boundaries, update the roadmap, generated tranche briefs, and manifest consistency as needed. Treat family relationships as roadmap hypotheses and checkpoints, not as implementation plans. Do not hardcode shared helpers unless the roadmap review specifically requires a prerequisite consolidation tranche.
```

- [ ] **Step 2: Verify revision prompt scope**

Run:

```bash
sed -n '1,120p' workflows/library/prompts/major_project_stack/revise_project_roadmap.md
```

Expected: the prompt still forbids implementation and full tranche designs.

## Task 4: Add Family Fit To Big-Design Drafting

**Files:**
- Modify: `workflows/library/prompts/major_project_stack/draft_big_design.md`

- [ ] **Step 1: Add `Cross-Tranche Reuse And Family Fit` guidance**

Insert after the paragraph that starts `If the project roadmap defines layout or ownership conventions`:

```md
If the roadmap identifies this tranche as part of a cross-tranche family, or repo inspection shows that this tranche repeats a lifecycle, artifact type, validation gate, command surface, implementation pattern, or downstream handoff from an earlier tranche, include a `Cross-Tranche Reuse And Family Fit` section.

In that section, classify the tranche as one of:
- first pilot
- second instance needing a reuse/consolidation decision
- later family member expected to consume shared machinery
- intentionally separate local fork

State the evidence for the classification, the closest prior tranche or artifact shape, which mechanics should be reused or refactored into shared helpers, which parts remain tranche-specific, and which prior command surfaces or artifacts must remain compatible.

A tranche may refactor prior tranche-local machinery into shared helpers when that refactor is needed for the current tranche. Keep the refactor limited to mechanics the current tranche will consume, preserve prior tranche behavior and command surfaces, and require regression checks for the prior tranche.
```

- [ ] **Step 2: Add an `Address where relevant` bullet**

Under `Address where relevant:`, add:

```md
- cross-tranche reuse and family fit: whether this tranche is a pilot, consolidation point, later family member, or justified local fork; what prior machinery is reused or refactored; and what compatibility checks protect earlier tranches
```

- [ ] **Step 3: Check that the design prompt remains design-only**

Run:

```bash
sed -n '1,160p' workflows/library/prompts/major_project_stack/draft_big_design.md
```

Expected: the prompt still says not to implement, edit source files, edit tests, or write the implementation plan. The new language allows designing a prior-tranche refactor, not performing it during design.

## Task 5: Add Family Checks To Big-Design Review

**Files:**
- Modify: `workflows/library/prompts/major_project_stack/review_big_design.md`

- [ ] **Step 1: Add reject bullets**

Under `Reject designs that:`, add:

```md
- omit cross-tranche family analysis when the roadmap or repository evidence shows a repeated lifecycle, artifact type, validation gate, command surface, implementation pattern, or downstream handoff
- duplicate prior tranche-local mechanics for a second or later family member without deciding whether to reuse, refactor into shared helpers, or justify a local fork
- refactor prior tranche machinery without preserving prior command surfaces, behavior, and regression checks
```

- [ ] **Step 2: Update the approval boundary**

Replace:

```md
Approve when the design fixes the implementation shape, ownership boundaries, major contracts, and acceptance gates. Leave exhaustive enumerations and command-level details to the plan unless they change architecture, provenance, claims, or gate semantics.
```

with:

```md
Approve when the design fixes the implementation shape, ownership boundaries, cross-tranche reuse boundary where relevant, major contracts, and acceptance gates. Leave exhaustive enumerations and command-level details to the plan unless they change architecture, provenance, claims, reuse boundaries, or gate semantics.
```

- [ ] **Step 3: Check for excessive pickiness**

Read the final prompt and confirm it does not require reuse for every superficial similarity. It should require analysis and justification, not mandatory abstraction.

## Task 6: Preserve Family Decisions During Big-Design Revision

**Files:**
- Modify: `workflows/library/prompts/major_project_stack/revise_big_design.md`

- [ ] **Step 1: Add revision guidance**

After the paragraph that starts `Preserve the project roadmap unless the review finding identifies a necessary conflict`, add:

```md
If review findings concern cross-tranche family fit, repeated mechanics, reuse boundaries, or prior-tranche refactoring, revise the selected design to make that decision explicit. The design may propose refactoring prior tranche-local machinery into shared helpers when the current tranche needs that machinery, but it must preserve prior command surfaces and require regression checks for prior behavior.
```

- [ ] **Step 2: Verify revise prompt does not mutate roadmap**

Run:

```bash
sed -n '1,140p' workflows/library/prompts/major_project_stack/revise_big_design.md
```

Expected: the prompt still preserves the roadmap unless a review finding identifies a necessary conflict.

## Task 7: Sync Local Prompt Copies If Needed

**Files:**
- Optional sync target: `/home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/draft_project_roadmap.md`
- Optional sync target: `/home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/review_project_roadmap.md`
- Optional sync target: `/home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/revise_project_roadmap.md`
- Optional sync target: `/home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/draft_big_design.md`
- Optional sync target: `/home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/review_big_design.md`
- Optional sync target: `/home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/revise_big_design.md`

- [ ] **Step 1: Check whether local synced copies exist**

Run:

```bash
for f in draft_project_roadmap.md review_project_roadmap.md revise_project_roadmap.md draft_big_design.md review_big_design.md revise_big_design.md; do
  test -f "/home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/$f" && echo "$f"
done
```

Expected: prints any EasySpin-local workflow prompt copies currently present.

- [ ] **Step 2: Propagate exact source prompt contents to any intended synced copy**

For each existing intended copy, copy the source prompt content exactly. Use `apply_patch` or a deliberate file-sync command during implementation; do not stage EasySpin changes unless explicitly requested.

- [ ] **Step 3: Verify source and copy match**

Run:

```bash
for f in draft_project_roadmap.md review_project_roadmap.md revise_project_roadmap.md draft_big_design.md review_big_design.md revise_big_design.md; do
  if test -f "/home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/$f"; then
    diff -u "workflows/library/prompts/major_project_stack/$f" "/home/ollie/Documents/EasySpin/workflows/library/prompts/major_project_stack/$f"
  fi
done
```

Expected: no diff for synced copies.

## Task 8: Verification

**Files:**
- Read/check: `docs/workflow_prompt_map.md`
- Read/check: `workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml`
- Read/check: `workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml`
- Test: `tests/test_major_project_workflows.py`
- Test: `tests/test_workflow_examples_v0.py`

- [ ] **Step 1: Check prompt map consistency**

Run:

```bash
python scripts/workflow_prompt_map.py --check
```

Expected: exit 0.

- [ ] **Step 2: Run focused workflow tests**

Run:

```bash
pytest tests/test_major_project_workflows.py tests/test_workflow_examples_v0.py -q
```

Expected: all selected tests pass. If failures are unrelated to prompt text, record exact failure output before deciding whether to broaden or defer.

- [ ] **Step 3: Run major-project stack dry-run validation**

Run:

```bash
python -m orchestrator run workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml --dry-run
```

Expected: workflow validation successful.

- [ ] **Step 4: Run drain workflow dry-run validation**

Run:

```bash
python -m orchestrator run workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml --dry-run
```

Expected: workflow validation successful.

- [ ] **Step 5: Manual prompt review checklist**

Confirm:

- The prompt text is project-agnostic and does not mention EasySpin, oracle tranches, T08, T09, T10, or T11.
- The roadmap prompt records family relationships as hypotheses and checkpoints, not mandatory shared helpers.
- The design prompt permits prior-tranche refactoring only when the current tranche needs it.
- Review prompts reject blind duplication and unsafe prior-tranche refactors.
- No tests assert literal prompt wording.

## Commit

- [ ] **Step 1: Inspect staged diff**

Run:

```bash
git diff -- workflows/library/prompts/major_project_stack
git status --short
```

Expected: only the intended prompt files are modified in the source repo, plus optional untracked/modified synced copies in target repos if explicitly propagated.

- [ ] **Step 2: Stage only source prompt changes**

Run:

```bash
git add \
  workflows/library/prompts/major_project_stack/draft_project_roadmap.md \
  workflows/library/prompts/major_project_stack/review_project_roadmap.md \
  workflows/library/prompts/major_project_stack/revise_project_roadmap.md \
  workflows/library/prompts/major_project_stack/draft_big_design.md \
  workflows/library/prompts/major_project_stack/review_big_design.md \
  workflows/library/prompts/major_project_stack/revise_big_design.md
```

- [ ] **Step 3: Commit**

Run:

```bash
git commit -m "Teach major project prompts cross-tranche reuse"
```

Expected: commit succeeds with only the intended prompt files.
