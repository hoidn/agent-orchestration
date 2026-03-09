# Generated File Hygiene Cleanup Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce repo status noise by ignoring generated runtime/cached files and untracking generated artifacts that should not live in git.

**Architecture:** Treat this as repository hygiene, not product behavior change. Add narrow ignore rules for Python caches, runtime state/output directories, and packaging byproducts. Remove already tracked generated files from the git index without deleting local working copies. Leave genuine in-progress source/docs changes untouched.

**Tech Stack:** `.gitignore`, git index cleanup, shell cleanup commands, `git status`, `git check-ignore`.

---

### Task 1: Add ignore rules for generated files

**Files:**
- Modify: `.gitignore`

**Step 1: Ignore Python caches and packaging byproducts**

Add ignore rules for:
- `__pycache__/`
- `*.py[cod]`
- `orchestrator.egg-info/`
- `.pytest_cache/`

**Step 2: Ignore runtime-generated workflow outputs**

Add ignore rules for:
- `.orchestrate/`
- `artifacts/`
- `state/`
- `logs/`
- `tmp/`

**Step 3: Verify ignore file formatting**

Run:

```bash
git diff --check -- .gitignore
```

Expected:
- no formatting problems

### Task 2: Untrack generated files already committed by mistake

**Files:**
- Remove from index only: tracked `*.pyc`, `__pycache__`, generated `artifacts/work/*`, generated `state/*.txt`

**Step 1: Untrack Python cache artifacts**

Run `git rm --cached` on the tracked `*.pyc` / `__pycache__` entries currently in the repo.

**Step 2: Untrack generated workflow state/output files**

Run `git rm --cached` on:
- `artifacts/work/dsl-evolution-implementation-report-resume.md`
- `artifacts/work/dsl-evolution-implementation-report.md`
- `state/execution_report_path.txt`
- `state/plan_path.txt`

**Step 3: Keep local files in place**

Do not delete user data or run outputs unless they are cache-only files.

### Task 3: Remove safe local cache directories and verify status

**Files:**
- No source edits; local filesystem cleanup only

**Step 1: Remove safe cache-only directories**

Delete local cache-only paths such as `__pycache__/`, `.pytest_cache/`, and `orchestrator.egg-info/`.

**Step 2: Verify ignore coverage**

Run:

```bash
git check-ignore -v .orchestrate/runs/20260307T084343Z-mbzxdl/state.json artifacts/review/2026-03-07-dsl-evolution-implementation-review.md state/implementation_cycle.txt orchestrator/__pycache__/__init__.cpython-313.pyc
```

Expected:
- each path is matched by the new ignore rules

**Step 3: Verify status cleanliness**

Run:

```bash
git status --short
```

Expected:
- generated runtime/cached noise is gone
- any remaining dirt is limited to genuine source/docs work
