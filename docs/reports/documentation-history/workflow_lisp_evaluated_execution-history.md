# Workflow Lisp Evaluated Execution: Historical Sections

Status: **Historical.** Extracted original sections; original tense, review
labels, measurements and acceptance language are evidence, not current
authority or permission to execute/select work. Current owner: [workflow_lisp_evaluated_execution.md](../../design/workflow_lisp_evaluated_execution.md).

## Original delivery metadata

- **Status:** accepted for the first release at gate G1 on 2026-09-29.
  Phase 2 compilation and Phase 3 Tasks 1–17 are complete at target 2.35
  for the admitted first-release classes: commands, portable composed
  providers without context capture, calls/captures and path-mode run
  references. Public `compile`, `--dry-run`, `run`, `resume`, `invalidate`
  and readers (`report`, dashboard, monitor, watchdog probe/watcher) are
  delivered to `main` and `origin/main` at `06130a53`; tested code is
  `ef689a39`. The [Phase 3 plan](../../plans/2026-10-02-workflow-lisp-evaluated-execution-phase-3-plan.md)
  and [closeout report](../2026-10-02-workflow-lisp-evaluated-execution-phase-3-closeout.md)
  own completion, receipts, the original RED full-suite dispositions and
  qualified compatibility/live evidence. Later classes and phases are not
  selected by this closure. Since then the owner retired the flat route
  (2026-10-13, §13), registered bounded parallel map at target 2.37 (§11),
  and registered target 2.38 for agent sessions (first slice implemented,
  §9.2) and confined run-reference children (command, recovery and export
  paths implemented; public confined provider dispatch pending, §8.4 and
  [`specs/versioning.md`](../../../specs/versioning.md#version-gating-summary)).
  The [early Phase 6a pilot](../2026-10-07-evaluated-execution-phase-6a-pilot.md)
  has bounded caller reviews and 21 passing pilot cases at `688695e3`,
  with production corrections at `d6adb627` and `b11e678`. Its full suite
  remains RED; the report owns closeout status. The
  pilot recorded the pre-existing pure-inline shadow result 101 instead of
  lexical 8. The subsequent [pure-capture correction](../2026-10-07-workflow-lisp-pure-capture-correction.md)
  demonstrates lexical 8 and coupled effect-once repair with bounded raw/resume
  historical evidence; final code/spec reviews passed and the bounded prerequisite
  was accepted before interruption. Recovery qualification and delivery are
  recorded in the Phase 4c closeout. This does
  not establish universal admitted-program correctness. Global Phase 6a remains
  open. The subsequent owner selection assigns W3 to 2.36 with one
  `std/improve` API per source import graph and old source caller migration
  on retargeting; the [Phase 4c plan](../../plans/2026-10-07-evaluated-execution-phase-4c-w3-plan.md)
  owns executable qualification and compatibility proof. W3 target registration,
  local bindings/captures/signatures and graph-selected helper are implemented
  at 2.36. The bounded
  extern/capture correction and public proposal/reviewed-change lifecycle
  checks are accepted; Task14B pilot/census evidence has bounded
  independent acceptance. Exact old-artifact/resume proof and affected/full freeze
  are recorded in the [closeout](../2026-10-07-evaluated-execution-phase-4c-w3-closeout.md). This does not close
  [remaining composition limits](../../design/workflow_lisp_composition_first.md#114-evaluated-w3-boundaries)
  or evaluated LSP F2 (**OPEN_NOT_WAIVED**).
  `evaluated_execution_unavailable` remains the refusal of
  `resume --force-restart` on an evaluated run. Old-profile resume now refuses
  with `workflow_execution_profile_retired` before writes
  ([`specs/cli.md`](../../../specs/cli.md#diagnostics)); it no longer refuses
  `run` or `resume` of a 2.35 entry. Normative owners remain `specs/state.md`
  (profile, header, journal, view), `specs/io.md` (command closure and typed
  inputs), `specs/cli.md` (entries, exits, locks) and `specs/versioning.md`
  (admission); this design links to them. Public owners are named in §17/18,
  the [compile tests](../../../tests/test_workflow_lisp_closed_program_compile_cli.py)
  and [target tests](../../../tests/test_workflow_lisp_target_evaluated_execution.py).
  The [Phase 2 closeout](../2026-10-02-workflow-lisp-evaluated-execution-phase-2-closeout.md)
  retains its compiler evidence; the spike under
  `experiments/evaluated_execution_spike/` remains separate historical
  runtime evidence (§18).

## 20. Decision Log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-10-04 | `result_root` is a third optional header fact (§8.4, *Immutable result root*), written by both production publishers, compared on resume (`resume_result_root_changed`) and lazy on historical absence (`result_root_missing` only at a reached X4) | The run root's position under the workspace is recoverable from no other stored fact, and the memo stores run-relative result paths on purpose. The alternative, a workspace input to every reader, was rejected by the owner |
| 2026-10-04 | `depends_on` is computed per value and documented as a superset (C9); narrowing it to the parts actually read is an entry condition of the release that scopes invalidation by C9 | No value, path, reuse decision or invalidation uses `depends_on` in this release; only lineage evidence is wider than real, and C6 read digests carry consumption evidence |
| 2026-10-06 | `__pycache__` directories and their bytecode are outside closure evidence (C5, §7.3) | A process writing a `.pyc` between commit and resume made resume refuse a whole-package closure with `effect_input_diverged`; bytecode is not the bytes of a declared file |
| 2026-10-06 | R2 splits by effect class: a provider receives the absolute path of its attempt's result file; a command and the prompt's path line keep the workspace-relative spelling, and every stored or digested fact keeps its existing relative spelling. Older targets are unchanged | An agent's working directory is not the workspace. A provider may change directory while it works, and a relative destination then names a file the runtime never reads; the attempt ends without a result although the provider wrote one. The prompt and the digests keep the relative spelling so that prompt parity (R4) and whole-workspace relocation (§8.4) hold; commands keep it because the certified adapters and library scripts they run accept only workspace-relative destinations, and they do not change directory |
