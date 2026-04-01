# PtychoPINN Lines 256 Workflow Drafting Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Draft a new PtychoPINN workflow that converts the single `arch_improvement_lines_256.md` prompt into a deterministic session workflow with one baseline run, a bounded experiment loop, and a strict 30-minute budget for each experiment run.

**Architecture:** Keep the workflow deterministic wherever possible. The workflow should own baseline generation, metric extraction, ledger updates, output checks, and git keep/discard control. Only one provider step should remain non-deterministic: choosing and applying the next coherent candidate change, staging the candidate files, and creating the candidate commit. Use a high but finite `repeat_until` cap to approximate the prompt's "loop forever" semantics, because the DSL does not support a truly unbounded loop.

**Tech Stack:** Orchestrator DSL `2.7`, command steps with Bash/Python helpers, Codex provider step, PtychoPINN `scripts/studies/run_lines_256_arch_experiment.py`, TSV ledger under `state/lines_256_arch_improvement/`.

---

## Design Notes To Preserve During Drafting

- Do not translate the prompt literally into one giant provider step.
- Keep the session state explicit and deterministic:
  - `protected_local_paths`
  - `session_id`
  - accepted branch state (`accepted_ref`, `accepted_amp_ssim`)
  - candidate metadata
  - harvested run results
- Treat baseline as session bootstrap, not as part of the candidate loop.
- Do not model the current accepted state as a "champion" concept in the prompt. The workflow should carry forward only the current accepted ref and its `amp_ssim`.
- Because `run_lines_256_arch_experiment.py` is synchronous, do not add a polling `wait_for` step unless the downstream runner changes to detached execution later.
- Keep the 30-minute budget on the deterministic run step with `timeout_sec: 1800`.
- Prefer one new prompt file. Additional prompt files are a smell unless they remove real ambiguity.

## Proposed Target Files

**Create:**
- `../tmp/PtychoPINN/workflows/agent_orchestration/lines_256_arch_improvement_session_loop.yaml`
- `../tmp/PtychoPINN/prompts/workflows/lines_256_arch_improvement/experiment_step.md`

**Modify:**
- `../tmp/PtychoPINN/prompts/index.md`
- optionally `../tmp/PtychoPINN/docs/studies/index.md` if PtychoPINN keeps workflow references there

**Smoke checks:**
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run ../tmp/PtychoPINN/workflows/agent_orchestration/lines_256_arch_improvement_session_loop.yaml --dry-run --stream-output`

## Recommended Workflow Shape

Top-level structure:

1. `ValidateStudyInputs`
2. `CaptureProtectedLocalPaths`
3. `EnsureResultsLedger`
4. `CreateSession`
5. `RunBaseline`
6. `HarvestBaselineOutputs`
7. `AppendBaselineLedgerRow`
8. `ExperimentLoop` (`repeat_until` with high literal cap such as `100`)
   - `ReadAcceptedState`
   - `ExperimentStep`
   - `RunCandidateExperiment`
   - `HarvestCandidateOutputs`
   - `AppendCandidateLedgerRow`
   - `KeepOrDiscardCandidate`

The loop exit should be operational, not semantic:
- stop on explicit blocker from `ExperimentStep`
- stop on candidate overlap with protected paths
- stop on manual session cap
- otherwise continue

Do not treat "no improvement" as loop termination. It is just a discard.

### Task 1: Draft The Workflow Contract Skeleton

**Files:**
- Create: `../tmp/PtychoPINN/workflows/agent_orchestration/lines_256_arch_improvement_session_loop.yaml`

**Step 1: Draft the top-level workflow shape**

Start with:
- `version: "2.7"`
- one `codex` provider definition
- a top-level `context` entry for the loop cap if useful for documentation, but use a literal on `repeat_until.max_iterations`

Encode the deterministic session state roots under:
- `state/lines_256_arch_improvement/`
- `outputs/lines_256_arch_improvement/`

**Step 2: Define the deterministic setup steps**

Include command steps for:
- validating the two authoritative study docs and the thin wrapper path
- capturing `git status --short --untracked-files=no`
- creating `state/lines_256_arch_improvement/results.tsv` with the exact required header
- minting a `session_id`

**Step 3: Draft baseline execution and harvesting**

Model baseline as:
- deterministic command step calling `scripts/studies/run_lines_256_arch_experiment.py`
- `timeout_sec: 1800`
- deterministic harvest step that verifies:
  - output root exists
  - metrics file or fallback summary exists
  - comparison PNG exists in the session gallery
  - `amp_ssim` is extractable

**Step 4: Run dry-run validation**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run \
  ../tmp/PtychoPINN/workflows/agent_orchestration/lines_256_arch_improvement_session_loop.yaml \
  --dry-run --stream-output
```

Expected:
- workflow loads
- no schema errors
- no unresolved prompt path errors

### Task 2: Draft The Single Provider Prompt

**Files:**
- Create: `../tmp/PtychoPINN/prompts/workflows/lines_256_arch_improvement/experiment_step.md`
- Modify: `../tmp/PtychoPINN/prompts/index.md`

**Step 1: Write the provider prompt with a narrow role**

The prompt should instruct the agent to:
- read the authoritative study docs
- read the accepted state and protected local paths supplied by the workflow
- make one coherent architecture/training-config change
- restrict edits to the allowed editable surface
- stage only candidate files
- create exactly one candidate commit
- write candidate metadata to a deterministic JSON path supplied by the workflow

The prompt should explicitly not own:
- TSV append
- metric extraction
- baseline setup
- keep/discard git reset logic

**Step 2: Define the prompt inputs expected from YAML**

Make the workflow inject or provide:
- the study docs
- the accepted `ref` and accepted `amp_ssim`
- the protected tracked-dirty file list
- the exact candidate metadata path

Candidate metadata should include:
- candidate commit hash
- intended candidate file list
- one-line experiment note
- exact run command to execute

**Step 3: Update prompt catalog references**

Add a short entry to `../tmp/PtychoPINN/prompts/index.md` so the prompt family is discoverable.

### Task 3: Draft The Candidate Run / Harvest / Decision Loop

**Files:**
- Modify: `../tmp/PtychoPINN/workflows/agent_orchestration/lines_256_arch_improvement_session_loop.yaml`

**Step 1: Add the `repeat_until` body**

Use one structured loop containing deterministic state transitions plus the single provider step:
- `ReadAcceptedState`
- `ExperimentStep`
- `RunCandidateExperiment`
- `HarvestCandidateOutputs`
- `AppendCandidateLedgerRow`
- `KeepOrDiscardCandidate`

Set `RunCandidateExperiment.timeout_sec: 1800`.

**Step 2: Keep harvesting deterministic**

The harvest step should:
- read the candidate output root
- extract `amp_ssim`
- verify or mark the comparison PNG
- classify the candidate result as one of:
  - `keepable`
  - `discard_metric`
  - `discard_equal_or_worse`
  - `crash`
  - `blocker`

Write that classification to a deterministic state file or JSON artifact for the next step.

**Step 3: Encode keep/discard in a command step**

The keep/discard step should:
- compare candidate `amp_ssim` against accepted `amp_ssim`
- if strictly better:
  - keep the candidate commit
  - update accepted ref and accepted metric state
- otherwise:
  - append the ledger row first
  - run the exact reset/restore sequence from the loop doc
  - verify protected local paths are unchanged

**Step 4: Make loop continuation explicit**

Loop continuation should depend on:
- not blocked
- still below the high iteration cap

Do not stop just because the candidate was discarded.

### Task 4: Draft Supporting Deterministic File Contracts

**Files:**
- Modify: `../tmp/PtychoPINN/workflows/agent_orchestration/lines_256_arch_improvement_session_loop.yaml`

**Step 1: Choose deterministic state files**

Prefer a small set of stable files such as:
- `state/lines_256_arch_improvement/session_id.txt`
- `state/lines_256_arch_improvement/protected_local_paths.json`
- `state/lines_256_arch_improvement/accepted_state.json`
- `state/lines_256_arch_improvement/candidate_metadata.json`
- `state/lines_256_arch_improvement/candidate_result.json`

**Step 2: Keep string-heavy state in JSON files**

Because commit hashes, file lists, and freeform notes are string-rich, avoid over-modeling them as scalar artifacts. Use deterministic JSON files and relpath outputs instead.

**Step 3: Add explicit output checks**

For each deterministic step that produces a path or state file, add `expected_outputs` so the workflow fails loudly on missing files rather than silently drifting.

### Task 5: Verify The Draft End-To-End

**Files:**
- Modify: `../tmp/PtychoPINN/workflows/agent_orchestration/lines_256_arch_improvement_session_loop.yaml`
- Modify: `../tmp/PtychoPINN/prompts/workflows/lines_256_arch_improvement/experiment_step.md`

**Step 1: Validate prompt file resolution**

Run:

```bash
test -f ../tmp/PtychoPINN/prompts/workflows/lines_256_arch_improvement/experiment_step.md
```

Expected:
- exit `0`

**Step 2: Run workflow dry-run validation**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run \
  ../tmp/PtychoPINN/workflows/agent_orchestration/lines_256_arch_improvement_session_loop.yaml \
  --dry-run --stream-output
```

Expected:
- workflow validation successful

**Step 3: Run one controlled smoke session if the downstream checkout is safe**

Only after dry-run passes and only if the downstream repo state is appropriate, launch one interactive smoke session in tmux and confirm:
- baseline executes with the 30-minute timeout in place
- candidate step emits candidate metadata
- harvest and ledger append steps run

If that is too risky for the first pass, stop at dry-run and document the manual launch command.

### Task 6: Record The Final Rationale

**Files:**
- Modify: `../tmp/PtychoPINN/workflows/agent_orchestration/lines_256_arch_improvement_session_loop.yaml`
- optionally modify: `../tmp/PtychoPINN/docs/studies/index.md`

**Step 1: Add concise comments only where they prevent confusion**

Use short comments to explain:
- why baseline is outside the candidate loop
- why candidate harvest is deterministic
- why the loop is capped even though the conceptual process is "forever"

**Step 2: Document the operational caveat**

Note that:
- the workflow approximates "forever" with a high finite cap
- restarting or resuming a session is the intended way to continue long-running study work

**Step 3: Commit in narrow slices**

Suggested commits:

```bash
git add ../tmp/PtychoPINN/prompts/workflows/lines_256_arch_improvement/experiment_step.md ../tmp/PtychoPINN/prompts/index.md
git commit -m "feat: add lines_256 experiment workflow prompt"
```

```bash
git add ../tmp/PtychoPINN/workflows/agent_orchestration/lines_256_arch_improvement_session_loop.yaml
git commit -m "feat: add lines_256 architecture improvement workflow"
```

```bash
git add ../tmp/PtychoPINN/docs/studies/index.md
git commit -m "docs: document lines_256 experiment workflow"
```
