# Type/Runtime Boundary Report Follow-ups Plan

> **Execution status (active at Task 5, 2026-07-09):** Tasks 1-3 are completed in `81b1b935` (report routing), `1833d59b` (frontend terminology anchor), and `b22103f5` (live-design-doc terminology sweep). Task 4 is completed in `e1822cf4` plus the date correction `ab4668b0`; its fail-closed report ownership check is cleared. The published audit selects cases 2, 3, and 5 for Task 5, owned respectively by `tests/test_workflow_lisp_structured_results.py`, `tests/test_output_contract.py`, and `tests/test_workflow_lisp_source_map.py`. Task 5 is next; Task 6 follows as historical reconciliation/status.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the actionable items from the dispositioned report `docs/reports/2026-06-19-workflow-lisp-type-runtime-boundary-issues.md` (2026-07-08 disposition): route the report, run the recommendations 1–2 terminology sweep, and run the recommendation 8 negative-coverage audit with its Phase-1-plan reconciliation.

**Architecture:** Two documentation workstreams (routing, terminology) plus one test workstream (coverage audit → wire gaps → reconcile the Phase-1 fixture deletion). No production code changes anywhere in this plan — the only non-doc artifacts are new/wired tests and fixtures.

**Tech Stack:** Markdown, pytest.

## Entry gate and coordination

- The dispositioned report exists (done 2026-07-08).
- **Original ordering constraint:** Tasks 4–6 were intended to complete **before** `docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md` Task 3 (orphaned-fixture deletion) executed.
- Tasks 1–3 are documentation-only, independent, and can land any time.

**Execution coordination (verified 2026-07-09):** The Phase-1 fixture deletion has landed, and the three candidate fixtures named below are absent from the current checkout. The Tasks 4–5 audit remains valid: prefer existing behavioral coverage over recreating old fixtures, and have Task 5 create a minimal fixture only for a genuine uncovered case without assuming an absent fixture can be reused. Task 6 is now historical reconciliation/status, not a replay of the deletion.

## Global Constraints

- Run all commands from the repo root `/home/ollie/Documents/agent-orchestration`.
- The working tree may contain the user's in-flight work. **Stage by explicit path only.** Never `git add -A`, `git add -u`, or `git commit -a`.
- Commit messages: short imperative sentence, repo style. No conventional-commit prefixes, no mention of Claude/Claude Code, no Co-Authored-By trailers.
- No worktrees. Never `--no-verify`.
- Narrowest pytest selectors first; fresh output is the verification evidence. After adding or changing a test module, run `pytest --collect-only <module>` on it.
- Do not add tests that assert literal prompt or message text — assert behavior and diagnostic *codes*, not phrasing.
- `docs/design/workflow_lisp_structural_parametric_constraints.md` is superseded and retained as a historical record ("do not extend") — the terminology sweep must **not** edit it.
- If a step's verification fails twice, stop and report.

---

### Task 1: Route the report from the documentation hubs

The report is referenced by zero documents today; `docs/index.md` routes no `docs/reports/` entries at all.

**Files:**
- Modify: `docs/design/README.md`
- Modify: `docs/index.md` (only if Step 1 finds a fitting section)

- [x] **Step 1: Find the routing style**

```bash
grep -n "workflow_lisp_parametric_type_system" docs/design/README.md docs/index.md
grep -n "diagnostic\|report" docs/design/README.md | head -5
```
Identify the entry style used for the parametric type system doc (one-line link + when-to-read hook).

- [x] **Step 2: Add the routing line(s)**

In `docs/design/README.md`, next to (or in the same grouping as) the parametric type system entry, add one line in matching style:

```markdown
- `docs/reports/2026-06-19-workflow-lisp-type-runtime-boundary-issues.md` — historical diagnostic of the type/runtime contract-projection boundary; dispositioned 2026-07-08. Read its "Disposition Of Recommendations" table for what is absorbed, actionable, or gated — pointers there govern.
```

If `docs/index.md` has a section where design-adjacent reports fit (per Step 1), add the equivalent one-liner there too; if it has none, skip it — do not invent a new section for one entry.

- [x] **Step 3: Commit**

```bash
git add docs/design/README.md docs/index.md
git commit -m "Route type runtime boundary report from design docs index"
```

---

### Task 2: Terminology anchor in the frontend specification

The frontend spec is the normative authority; it gets the canonical definition, then its own occurrences are rewritten.

**Files:**
- Modify: `docs/design/workflow_lisp_frontend_specification.md` (4 `proof-gated` occurrences as of 2026-07-08)

**Decision rule (applies here and in Task 3), per occurrence of `proof-gated`:**
- The sentence describes what an **author** writes or reads (surface syntax, authoring model, examples, guidance) → rewrite using "refined match binders" / "refined pattern matching". The author-facing claim is: inside a `(match …)` arm, the binder *is* the variant payload; variant-specific fields are simply in scope in that arm.
- The sentence describes **compiler/runtime internals** (typechecker, lowering, WCC metadata, shared validation, source maps, resume evidence, parity) → keep proof terminology unchanged.
- First internal use in the doc gets the pairing note, once: "proof metadata (the compiler-internal representation of refined match binders)".
- Ambiguous → treat as internal (keep), and record it in the commit message.

- [x] **Step 1: List the occurrences with context**

```bash
grep -n -B1 -A1 "proof-gated" docs/design/workflow_lisp_frontend_specification.md
```

- [x] **Step 2: Add the canonical definition**

In the spec section that introduces `match` / variant access (locate with `grep -n "match" docs/design/workflow_lisp_frontend_specification.md | head`), add a short definition paragraph establishing: author-facing term = *refined match binders*; internal term = *proof metadata*; the wording model to copy is `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md` (the one doc already using it).

- [x] **Step 3: Apply the decision rule to the 4 occurrences.**

- [x] **Step 4: Verify**

```bash
grep -n "proof-gated" docs/design/workflow_lisp_frontend_specification.md
```
Expected: every remaining occurrence (possibly zero) sits in an internal-mechanics sentence; record the residual count and classification in the commit message.

- [x] **Step 5: Commit**

```bash
git add docs/design/workflow_lisp_frontend_specification.md
git commit -m "Adopt refined match binder terminology in frontend specification"
```

---

### Task 3: Terminology sweep across the remaining live design docs

**Files (occurrence counts as of 2026-07-08):**
- Modify: `docs/design/workflow_lisp_parametric_type_system.md` (1)
- Modify: `docs/design/workflow_lisp_compile_time_parametric_specialization.md` (2)
- Modify: `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md` (5)
- Modify: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md` (6)
- Do NOT modify: `docs/design/workflow_lisp_structural_parametric_constraints.md` (superseded historical record; its 3 occurrences stay)

- [x] **Step 1:** For each of the four docs, list occurrences (`grep -n -B1 -A1 "proof-gated" <doc>`) and apply the Task 2 decision rule. Where a doc needs the internal-pairing note, point it at the frontend spec's definition rather than restating it.

- [x] **Step 2: Verify the sweep result repo-wide**

```bash
grep -rn "proof-gated" docs/design/*.md
grep -rc "proof-gated" orchestrator/ --include="*.py" | grep -v ":0" | head
```
Expected: design-doc hits only in the superseded constraints doc and in internal-mechanics sentences; Python-source hits (comments/docstrings) are internal by definition — leave them, record the count.

- [x] **Step 3: Commit**

```bash
git add docs/design/workflow_lisp_parametric_type_system.md docs/design/workflow_lisp_compile_time_parametric_specialization.md docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md
git commit -m "Sweep refined match binder terminology across live design docs"
```

---

### Task 4: Negative-coverage audit (recommendation 8)

Map each of the six audit cases to existing behavioral coverage; the deliverable is the completed audit table appended to the report's recommendation 8 amendment.

**Files:**
- Modify: `docs/reports/2026-06-19-workflow-lisp-type-runtime-boundary-issues.md` (append the table under the recommendation 8 amendment)

- [x] **Step 0: Fail closed on report ownership overlap**

Before reading the report as a publication target, run:

```bash
report=docs/reports/2026-06-19-workflow-lisp-type-runtime-boundary-issues.md
git status --porcelain -- "$report"
```

If this prints anything, the report contains another owner's work. Do not edit,
stage, or commit it, and do not proceed to Tasks 5–6. Audit discovery may be
captured temporarily in
`/tmp/workflow-lisp-boundary-negative-coverage-audit-$(git rev-parse --short HEAD).md`,
headed `EVIDENCE ONLY — NOT PUBLISHED`, but that note is not report authority.
Pause report publication until the existing owner commits or explicitly
reconciles the overlapping work. Once the report is clean, re-read its current
contents before applying the audit; do not replay a patch prepared against the
older version.

- [x] **Step 1: Run the per-case discovery**

| # | Case | Where to look |
|---|---|---|
| 1 | variant field access outside its match arm | `pytest tests/test_workflow_lisp_variant_proofs.py -q --collect-only`; `grep -n "raises(LispFrontendCompileError" tests/test_workflow_lisp_variant_proofs.py` — confirm at least one test compiles source that projects a variant field outside its arm and asserts a diagnostic code |
| 2 | repeated field names collide after lowering | `grep -rn "collide\|collision\|duplicate.*field" tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_structured_results.py` |
| 3 | active variant's required output-bundle field omitted at runtime | `grep -rn "missing.*field\|required.*bundle\|output_bundle" tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_materialize_view_runtime.py \| head` |
| 4 | inactive variant field provided → rejected/ignored per contract | same suites as case 3, plus `grep -rn "inactive\|wrong.*variant" tests/ --include="test_workflow_lisp*.py" \| head` |
| 5 | source-map attribution from runtime output failure to authored union field | `grep -rn "union\|variant" tests/test_workflow_lisp_source_map.py \| head`; check whether any test follows a *runtime* failure (not compile) back to an authored field |
| 6 | stdlib drain projection passing only via name-specific handling, caught by generic route | inspect `docs/plans/2026-07-07-drain-migration-g8-retirement.md` Phase 1 consumer-parity and generic-route checks; record **owned-elsewhere** only if the live plan actually covers this case, otherwise mark it as a genuine gap |

For each case record: covered (test id) / gap / owned-elsewhere (pointer).

- [x] **Step 2: Check the three orphaned fixtures against the gaps**

For `if_variant_proof_missing.orc` (case 1), `review_loop_result_contract_invalid.orc` (contract case; classify against 3/4), and `backlog_drain_hidden_compatibility_bridge_reread_invalid.orc` (bridge case; classify against case 6 using the live drain-plan evidence gathered in Step 1), check the current path first. If a fixture exists, read it and confirm that it still compiles into the intended failure. If it is absent, inspect its tracked history with `git log -- <path>` and `git show <deletion-commit>^:<path>` only to understand the intended case; do not restore it for the audit. If the case is covered, record "deletion landed — case covered by <test id>". If the case is a genuine gap, pass the case and current contract to Task 5 for a minimal reproduction rather than assuming the deleted fixture remains reusable.

- [x] **Step 3: Publish the completed table only onto a clean report**

Re-run the Step-0 status command immediately before editing. Append the table
under the recommendation 8 amendment, headed `Audit result (2026-07-08):`, one
row per case with status and evidence. Then review and stage only the report:

```bash
report=docs/reports/2026-06-19-workflow-lisp-type-runtime-boundary-issues.md
git diff --check -- "$report"
git diff -- "$report"
git add -- "$report"
git diff --cached --check -- "$report"
git diff --cached -- "$report"
```

Inspect the complete report diff before staging and the complete cached report
diff afterward. If unrelated paths were already staged, preserve them and use
an explicit-path commit for the report; never clear or absorb another owner's
staging.

- [x] **Step 4: Commit**

```bash
git commit --only docs/reports/2026-06-19-workflow-lisp-type-runtime-boundary-issues.md \
  -m "Record negative coverage audit for boundary report cases"
```

---

### Task 5: Wire the genuine gaps (one commit per case)

The cleanly published Task-4 audit selects exactly three gaps for this task:

| Case | Owning suite | Required coverage |
|---|---|---|
| 2. Same-name fields across union variants | `tests/test_workflow_lisp_structured_results.py` | Prove valid same-name fields remain variant-scoped and collision-free through lowering; do not reject them merely for sharing a name across distinct variants. |
| 3. Missing active-variant required field at runtime | `tests/test_output_contract.py` | Exercise `variant_required_field_missing` through runtime output-bundle validation. |
| 5. Runtime failure source-map attribution | `tests/test_workflow_lisp_source_map.py` | Map a runtime output failure back to the authored union field. |

Implement one case and one commit at a time. Cases 1 and 4 are already covered;
case 6 remains owned by the drain-migration plan.

**Files (per gap):**
- Test: the owning suite from the selected-gap table above.
- Fixture: create a minimal current-contract fixture under `tests/fixtures/workflow_lisp/invalid/` only when the owning suite's established pattern needs one; otherwise use the suite's existing source/helper pattern. Do not restore a deleted orphan wholesale or assume its historical contents remain reusable.

Coverage recipe (mirror each owning suite's surrounding helper usage):

- Case 2: construct a union with the same field name in distinct variants,
  derive/lower its structured result contract, and assert that both fields
  remain variant-scoped and collision-free. This is positive coverage; do not
  turn valid cross-variant names into a compile-time rejection.
- Case 3: construct an active-variant bundle with one required field omitted
  and assert the runtime violation type `variant_required_field_missing`.
- Case 5: exercise the owning suite's runtime-output-failure origin path and
  assert attribution to the authored union field using stable source-map
  structure, not literal diagnostic wording.

- [ ] **Step 1:** Build the smallest current-contract reproduction. For case 2,
  confirm the valid authoring and lowering path succeeds. For cases 3 and 5,
  run the failure path once and confirm the real violation/origin structure —
  never guess a diagnostic or violation code.
- [ ] **Step 2:** Add the test using the suite's existing helpers; `pytest <suite> --collect-only -q` then run the new test → PASS.
- [ ] **Step 3:** Commit: `git add <suite> <fixture-if-new>` / `git commit -m "Cover <case> at typed runtime boundary"`.

---

### Task 6: Record historical reconciliation/status for the Phase-1 fixture deletion

**Files:**
- Inspect: `docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md` (Task 3 fixture list)
- Modify: none

- [ ] **Step 1:** Verify the landed deletion commit and current path status. Reconcile each fixture-related Task 4 audit and Task 5 wiring outcome as either existing coverage with the historical deletion left intact, or a new minimal current-contract fixture created after that deletion.
- [ ] **Step 2:** Record that status in the final execution handoff only after
  the Task-4 report publication and every applicable Task-5 gap commit are
  complete. Do not edit the historical Phase-1 deletion list or rerun its
  `git rm`; do not create a standalone reconciliation commit.

---

### Final gate

- [ ] `grep -rn "proof-gated" docs/design/*.md` → hits only in the superseded constraints doc and internal-mechanics sentences.
- [ ] `pytest tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_structured_results.py tests/test_output_contract.py tests/test_workflow_lisp_source_map.py -q` → PASS.
- [ ] Report: residual `proof-gated` classification per doc, the audit table outcome per case, fixtures wired vs confirmed-deletable, and the Phase-1 reconciliation made.

## Roadmap (not in this plan)

Recommendations 9–11 of the report remain design-gated: unified typed-return semantics (9) and generalizing the function-over-workflow reuse model (11) each need a frontend-specification update before implementation; interpreter-like evaluation (10) is roadmap-level. Drafting those spec updates is design work — schedule it separately if/when prioritized.
