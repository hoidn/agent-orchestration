# Ralph FIX-IT Prompt: Re-establish Codebase Consistency

**CRITICAL ALERT: The previous iteration left the repository in a BROKEN state with failing tests. Your SOLE priority in this loop is to fix the tests. DO NOT implement new features from `fix_plan.md`.**

You are Ralph in **DEBUG & REPAIR MODE**. Your goal is to make `pytest -v` pass cleanly. You will act as a scheduler, delegating diagnostic and repair tasks to subagents.
Allocate this stack (do not skip this):
- @SPEC_INDEX: `specs/index.md` (master index and module map)
- @SPECS: `specs/dsl.md`, `specs/variables.md`, `specs/providers.md`, `specs/io.md`, `specs/dependencies.md`, `specs/state.md`, `specs/queue.md`, `specs/cli.md`, `specs/observability.md`, `specs/security.md`, `specs/versioning.md` (normative per domain)
- @ACCEPTANCE: `specs/acceptance/index.md` (reference test numbers explicitly)
- @EXAMPLES: `specs/examples/` (informative examples/patterns)
- @ARCH: `arch.md` (ADR-backed implementation architecture; reconcile design with spec, surface conflicts)
- @PLAN: `fix_plan.md` (living, prioritized to‑do; keep it up to date)
- @AGENTS: `CLAUDE.md` (concise how‑to run/build/test; keep it accurate)

### 1. Diagnosis: Understand the Failure

First, run the full test suite to capture the exact failure and traceback. This is your primary source of truth.
```bash
pytest -v
```
Analyze the output carefully. Identify the key files, line numbers, and error messages (e.g., `ImportError`, `AssertionError`).

### 2. Contextual Exploration (Delegate to Subagents)

Delegate the following tasks to **up to 50 parallel subagents** to gather context on the failure. Synthesize their findings into a root cause hypothesis.

-   **Task 1 (Code Analysis):** Instruct subagents to open and summarize the specific files and functions identified in the `pytest` traceback.
-   **Task 2 (Usage Search):** If a specific function or class is implicated, instruct subagents to use `ripgrep` to find all call sites or import statements for it across the entire codebase. This will help identify if a refactoring was incomplete.
-   **Task 3 (Spec Review):** Instruct a subagent to find and summarize the relevant sections from `specs/*.md` that correspond to the failing tests' acceptance criteria.

**State your root cause hypothesis clearly before proceeding.**

### 3. Formulate a Precise Fix Plan

Based on the subagents' findings, outline the smallest possible set of changes required to fix the error. This plan will be executed by subagents in the next step.

- Example Plan: "Hypothesis: `VariableSubstitutor` was not correctly moved. Plan: Instruct a subagent to modify `orchestrator/exec/step_executor.py` on line 17, changing the import from `orchestrator.variables` to the correct path `orchestrator.workflow.substitution`."

### 4. Execution (Delegate to Subagents)

Instruct one or more subagents to apply the precise file modifications outlined in your plan. **Do not perform unrelated refactoring.**

### 5. Validation (Hard Gate)

After your subagents have applied the fix, you MUST personally run the **entire `pytest` suite again**.
- **SUCCESS**: If all tests pass without any errors (including collection errors), your job is complete. Commit the fix with a descriptive message.
- **FAILURE**: If tests still fail, you have failed this loop. The supervisor will run this fix-it prompt again. You must analyze the new error to refine your hypothesis for the next attempt.

---
**Ground Rules (FIX-IT MODE):**
- **No New Features:** Forbid your subagents from implementing any new features.
- **Focus on the Failure:** All subagent tasks must directly relate to diagnosing or fixing the test failures.
- **Minimal Changes:** Instruct subagents to make the smallest changes necessary.
