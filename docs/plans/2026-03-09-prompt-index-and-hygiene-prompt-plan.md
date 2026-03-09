# Prompt Index And Hygiene Prompt Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add one simple repo-hygiene review prompt that would have surfaced the `executor.py` refactor need, and publish a curated prompt index covering that prompt plus the prompt families actually used by workflows run in the last two days.

**Architecture:** Keep this docs-only and prompt-only. Add one standalone maintenance prompt under `prompts/`, then add a single prompt catalog under `prompts/README.md` that maps canonical prompt files to purpose and recent workflow usage. Collapse near-duplicate workflow prompt variants by selecting the most recent and/or most structured prompt and explicitly naming the superseded variants.

**Tech Stack:** Markdown prompt files, workflow YAML inspection, recent run metadata from `.orchestrate/runs/*/state.json`, focused diff checks.

---

### Task 1: Identify the recent prompt families and dedupe targets

**Files:**
- Read: `.orchestrate/runs/*/state.json`
- Read: `workflows/examples/*.yaml`
- Read: `workflows/library/*.yaml`
- Read: `prompts/workflows/**`

**Step 1: Enumerate recent workflow runs**

Use run state under `.orchestrate/runs/` to list workflows started on or after `2026-03-07`.

**Step 2: Resolve prompt files used by those workflows**

Inspect the relevant workflow YAMLs and any imported library workflows for `input_file` references.

**Step 3: Group obvious duplicates**

Treat the following as likely duplicate families unless a material behavior difference is discovered:
- `dsl_follow_on_plan_impl_loop/*`
- `dsl_follow_on_plan_impl_loop_v2/*`
- `dsl_follow_on_plan_impl_loop_v2_call/*`
- `design_plan_impl_stack_v2_call/*`

Keep the most recent and/or most structured prompt in the index and note which older variants it supersedes.

### Task 2: Add the hygiene prompt

**Files:**
- Create: `prompts/repo_hygiene_review.md`

**Step 1: Write a simple maintenance-focused review prompt**

The prompt should:
- ask for repo hygiene and maintainability findings
- prioritize oversized multi-responsibility files, generated-file hygiene, brittle tests, and architectural drift
- explicitly treat a very large module or class with too many responsibilities as a likely finding
- ask for file references and concrete refactor recommendations

**Step 2: Keep the prompt generic**

Do not bind it to this one repo or to `executor.py` by name. It should be reusable for future hygiene scans.

### Task 3: Add the prompt index

**Files:**
- Create: `prompts/README.md`

**Step 1: Add a short purpose statement**

Explain that this index catalogs canonical prompt files, not every historical variant.

**Step 2: Add the new hygiene prompt**

Include:
- path
- purpose
- when to use it

**Step 3: Add prompts from workflows run in the last two days**

Include canonical prompt files for:
- the review-first DSL fix loop
- the follow-on plan/implementation loop family
- the current design/plan/implementation stack family

Where duplicates exist, keep only the selected canonical file and note the superseded variants.

**Step 4: Make the selection rationale explicit**

For each collapsed family, say why the chosen prompt is canonical:
- newest path model
- structured JSON outputs
- tracked findings
- stronger plan-completeness guidance

### Task 4: Verify and stop

**Files:**
- Verify: `prompts/repo_hygiene_review.md`
- Verify: `prompts/README.md`

**Step 1: Run diff hygiene**

Run:

```bash
git diff --check -- prompts/repo_hygiene_review.md prompts/README.md docs/plans/2026-03-09-prompt-index-and-hygiene-prompt-plan.md
```

Expected:
- clean diff with no whitespace or patch-format issues

**Step 2: Inspect the prompt index render**

Run:

```bash
sed -n '1,260p' prompts/README.md
```

Expected:
- the index is readable
- the recent workflow families are covered
- duplicate families are collapsed intentionally rather than omitted accidentally

**Step 3: Report what was included and what was intentionally excluded**

Call out:
- the canonical chosen prompt files
- the superseded duplicate prompt families
- any recent workflows with no repo prompt files
