# Workflow Lisp Repairs Follow-Up Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to execute selected tasks, with
> `superpowers:test-driven-development` for behavior changes. Reviews are
> made by a reviewer of a model family other than the implementer's.

**Goal:** Repair the defects that the
[shared defect repairs plan](2026-09-29-workflow-lisp-shared-defect-repairs-plan.md)
recorded and left open, where the repair is in the present execution route
and does not depend on the choice at gate G1 of the
[evaluated execution plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md).

**Architecture:** Each task repairs one recorded defect in the stage that
owns it. A strict `xfail` test pins most of them already; the repair turns
the pin into a plain test.

**Tech Stack:** Python, the workflow runtime and its resume path, pytest.

**Spec:** `specs/state.md` (resume), `specs/cli.md`, the composition-first
design, section 11 (known defects and rules).

## Status, Authorities, And Scope

Status: the owner confirmed the four tasks on 2026-09-29. Nothing here
changes what a target accepts; each task changes what a run does after an
interruption, or what a diagnostic says.

Out of scope: every defect whose cause is that a value exists at run time
only as the output of a step (the known-defect cells of the totality matrix,
name capture in `bind-proc` and `let-proc` values). Those wait for gate G1.

## Global Constraints

- A committed effect never runs again. Every test of resume counts the
  invocations of every command.
- Targets that exist accept and lower exactly what they do at the base.
  Build artifacts are byte-identical, apart from the digest of the compiler's
  own code that artifacts of trials and run references hold.
- Tests run through the public run and resume entries, with command-backed
  procedures and stand-in providers. No test asserts prompt text.
- No broad or full-suite run while other agents are running. One full run
  at closeout, alone.
- New modules under 500 lines, new functions under cyclomatic complexity 12.
- Commit by pathspec. Commit messages carry no tool or assistant attribution.

## Review Focus

1. A repair of resume must not let a committed effect run twice in the
   shapes that work today: root commands, a first call of a workflow, a
   provider visit.
2. A loop whose body calls a workflow: interrupt in the first, second and
   last iteration, inside the callee and between callees.
3. A state written before the repair must resume after it, or be refused
   with a located diagnostic.

---

### Task 1: Resume Of An Interrupted Effect In A Later Call Of One Workflow

- [ ] Complete

Follow-ups F10 (first shape), F9 and F19.

**Read/trace:** `orchestrator/workflow_lisp/lexical_checkpoint_restore.py`,
`orchestrator/workflow_lisp/lexical_checkpoint_default_resume.py`,
`orchestrator/workflow/calls.py`, `tests/test_workflow_resume_known_defects.py`,
the review and the fix report of Task 11 of the repairs plan.
**Update:** those owners; `specs/state.md`.

An interrupted command in a second or later call of the same called
workflow, such as a loop iteration, is refused on resume with
`lexical_checkpoint_completed_effect_invalid`: resume finds a checkpoint
record that the frame of the first call wrote. With `must_not_repeat` the
same program is refused with that code and no location, where the rule asks
for `lexical_restore_pending_effect_unsafe` at the step. Inside any called
workflow the `must_not_repeat` refusal has no source location.

1. The three strict `xfail` tests of `tests/test_workflow_resume_known_defects.py`
   for these shapes are the failing tests. Add: a loop of four iterations
   interrupted in each; two different call sites of one workflow; a callee
   that calls a callee.
2. Repair. A checkpoint record belongs to one frame; a record of another
   frame of the same workflow is not a record of this one.
3. The refusal and the rerun diagnostic carry the source location inside a
   called workflow, from the entry build's source trace.
4. Remove the marks of the pins that pass. State the rule in `specs/state.md`
   without the two exceptions that the repair removes.

### Task 2: Resume Of An Interrupted Command After A Provider Group

- [ ] Complete

Follow-up F10 (second shape), F18.

**Read/trace:** the same owners; `orchestrator/workflow/provider_supervision/`,
the peer group runtime; the run reference resume path.

An interrupted command whose nearest earlier effect is a provider group is
refused with `lexical_default_resume_prior_boundary_not_restorable`: the
group writes no checkpoint record. A FAILED run reference reruns on resume
without a `workflow_effect_rerun` row.

1. The strict `xfail` test for the group is the failing test. Add the same
   shape with a peer group, and a failed run reference.
2. Repair: the group's committed result is a boundary that resume can
   restore from. The failed run reference records its rerun.

### Task 3: The Usage-Limit Script Follows Each Attempt

- [ ] Complete

Follow-up F4.

**Read/trace:** `scripts/watch_workflow_usage_limit.sh`,
`tests/test_watch_workflow_usage_limit.py`, the review of Task 14 of the
repairs plan, finding 2.

The script reads the pane once per poll. A refusal printed later than one
poll is not retried; an old refusal can be read as new.

1. Failing tests: a refusal that arrives after two polls is retried; an old
   refusal in the pane is not taken for the result of a new attempt; the
   exit marker scrolled out of the captured lines.
2. Repair: each attempt prints a marker that is unique to it, and the script
   waits for that marker.
3. Set the poll interval of the tests back to two seconds.

### Task 4: Small Repairs

- [ ] Complete

Follow-ups F1, F31, F13.

1. An `AssertionError` raised after typecheck is reported as
   `compiler_defect`, as other internal exceptions are (F1). Failing test:
   a scalar effectful call in a `loop-state :like` field.
2. `_validate_required_provider_params` under cyclomatic complexity 12 (F31).
3. The refusal by the per-run writer lock (`run_already_active`) exits 2, as
   the refusal by the workspace lock does (F13). State it in `specs/cli.md`.

## Closeout

- [ ] Full suite, alone, compared with the failure set of the base.
- [ ] Whole-branch review.
- [ ] Merge to `main` by fast-forward; push.
