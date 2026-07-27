# M0 Decision Brief: Retained Failures, Typecheck Divergences, And Frontloaded Defaults

- **Status:** investigation brief with recommended rulings and recorded
  defaults, produced 2026-07-26 to frontload the substrate track's open
  owner decisions. Owner countersign happens at M0 component-plan review;
  every default below names the evidence that reopens it. Fresh command
  output cited here was produced on this checkout on 2026-07-26.
- **Consumes:** `docs/plans/2026-07-26-substrate-maintenance-track.md`
  (decision list), `specs/io.md` (bundle/exit contract),
  `docs/plans/2026-07-07-typecheck-family-completion.md` (divergence
  anchors).
- **Not frontloaded here:** the Q2 and L1 amendment reviews — they are
  review acts that spend provider budget and belong to the Q/L execution
  session, not this brief.

## 1. Retained Baseline Failures — Fresh Evidence

Command (2026-07-26):

```bash
python -m pytest -q \
  tests/test_workflow_output_contract_integration.py::test_provider_valid_output_bundle_overrides_raw_nonzero_exit \
  tests/test_workflow_semantic_ir.py::test_semantic_ir_adds_typed_prompt_input_lineage_without_runtime_evidence \
  tests/test_workflow_semantic_ir.py::test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys \
  tests/test_workflow_semantic_ir.py::test_compiled_bundle_semantic_ir_preserves_command_boundary_classification
```

Result: **2 failed, 2 passed**. The retained set is now two, matching the
frozen pre-Stage-8 baseline recorded in the Stage-8 and Q0 plans; the
track's "four" dates from track creation and is stale.

### 1a. `test_semantic_ir_adds_typed_prompt_input_lineage_without_runtime_evidence` — PASSES

Recommended ruling: drop from the retained set; no code action. Fixed at
some point between Stage 6 and tonight (the Stage-8 plan already recorded
only two retained identities).

### 1b. `test_compiled_bundle_semantic_ir_preserves_command_boundary_classification` — PASSES

Recommended ruling: identical to 1a.

### 1c. `test_provider_valid_output_bundle_overrides_raw_nonzero_exit` — FAILS (`assert 2 == 0`)

The test asserts that a validated output bundle overrides a nonzero
provider exit ("bundle is authority even if agent tooling exits nonzero").
That is the pre-2.x contract. The current normative contract says the
opposite: `specs/io.md:44-48` — the bundle is semantic authority for the
structured result, but "if the command exits non-zero" the step fails and
bundle validation is skipped; the live sibling test
`test_nonzero_exit_skips_output_bundle_validation` (same module) asserts
exactly the current behavior and passes. The failing test also runs on the
YAML-era dict-workflow harness (`tests/workflow_fixture_loader.py`
`WorkflowLoader`, `"version": "1.3"` mapping workflows).

Recommended ruling: **retire the test node** with rationale
"asserts the retired bundle-overrides-exit contract; contradicted by
`specs/io.md:44-48`; current behavior owned by
`test_nonzero_exit_skips_output_bundle_validation`". Porting it to `.orc`
with an inverted assertion would only duplicate the sibling.

### 1d. `test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys` — FAILS (`form_path` present)

The test blanket-bans the string `form_path` anywhere in
`executable_ir.json`. The hit is inside a workflow `provenance` record
(`form_path`/`line`/`path`/`workflow_name`), which is a deliberate
first-class executable-IR field serialized at
`orchestrator/workflow/executable_ir.py:712`
(`"provenance": _provenance_json_value(ir.provenance)`) and consumed by
runtime origin logging (`orchestrator/workflow/frontend_origins.py:451`).
The test's other exclusions (`_surface_step`, `_surface_workflow`,
`typed_workflow`) still hold — the surface-AST-leak ban remains valid; the
blanket substring scan predates the provenance field.

Recommended ruling: **update the test** to keep the surface-AST/internal
exclusions and permit `form_path` only inside `provenance` records (e.g.
strip `provenance` values before the substring scan). Companion doc
action: record the `provenance` field in the executable-IR contract row of
the owning design doc if it is not yet named there.

## 2. Typecheck-Family Deferred Divergences — Current State And Default Rulings

Code state verified 2026-07-26: the dispatch-local copies were retired in
favor of the `typecheck_effects` owners —
`orchestrator/workflow_lisp/typecheck.py:27-28` imports
`validate_command_argv` and `validate_semantic_command_adapter_usage`
under the old local names, and no `_typecheck_expected_extern_operand`
dispatch local remains in the package. The recorded anchors are
`docs/plans/2026-07-07-typecheck-family-completion.md:212-216` (size-gap
census: extern-operand dispatch 1,456ch vs owner 453ch), `:242-243` and
`:392-393` (the STOP-and-record decision rules), and
`orchestrator/workflow_lisp/procedures.py:194` (`GeneratedLocalProcedure`,
the `let-proc` hidden-procedure metadata). The precise deferred content of
each divergence is only summarized in the track's parenthetical; the
defaults below are therefore conditioned on a small verification fixture
each, not asserted from memory. [INFERENCE: divergence semantics
reconstructed from the anchors above.]

1. **Extern-operand narrow/wide fork.** The retired dispatch local was ~3x
   the owner's size, so the live owner is the *wide* (more permissive)
   variant. Default ruling: the owner's wide semantics stand. M0
   micro-task: recover the retired local from git history (commit
   "Retire dispatch-local extern operand typecheck for owner version"),
   enumerate its extra rejection branches, and add a RED fixture for any
   rejection the specs actually require; if none is spec-required, close
   with the diff attached. Reopens on: a spec-required rejection proven
   missing.
   - **CLOSED (2026-07-27).** The retired local
     (`_typecheck_expected_extern_operand`) was recovered from `481cd284^`
     (`typecheck_dispatch.py:2481`; deleted by `481cd284`, not by a
     commit named "Retire dispatch-local extern operand typecheck").
     The 3x size gap is entirely the old closure convention's explicit
     parameter plumbing; the AST diff against the live owner
     (`typecheck_effects.typecheck_expected_extern_operand`,
     `typecheck_effects.py:42`) leaves exactly **one** rejection branch
     the owner lacks: the retired guard short-circuited only `NameExpr`
     operands, so an out-of-env `EnumMemberExpr` (a two-segment dotted
     spelling such as `providers.review`) recursed into general
     typechecking and was rejected as a provider/prompt operand.
     Judgment: **not spec-required**. The normative `provider-result`
     surface (`docs/design/workflow_lisp_frontend_specification.md`
     §22.4: `(provider-result <compiler-known Provider extern> :prompt
     <compiler-known Prompt extern> ...)`, example spellings
     `providers.worker`/`prompts.work`) requires *accepting* two-segment
     dotted extern operands, which elaborate to `EnumMemberExpr`
     (`expressions.py` `_elaborate_symbol`: an unbound two-segment
     dotted identifier becomes `EnumMemberExpr`); the narrow rejection
     would break that surface and the extensive existing
     `providers.review`-style usage (fresh evidence:
     `tests/test_workflow_lisp_procedures.py::test_direct_provider_result_procedure_effects_do_not_require_hidden_bundle_writes`
     passes, compiling `provider-result providers.execute`). The wide
     short-circuit admits nothing unsound: undeclared externs are still
     rejected downstream by the declared-extern gates
     (`provider_result_provider_invalid` /
     `provider_result_prompt_invalid`, `typecheck_effects.py:661-688`).
     The retired local's narrow `NameExpr`-only semantics remain live,
     deliberately (`b3fb33d8`), at its only original call sites
     (`run-provider-phase` / `produce-one-of` via
     `typecheck_drain_phase._expected_extern_operand:233`), so no
     rejection was lost anywhere; the fork is a call-site partition. No
     RED fixture; the owner's wide semantics stand.
2. **Dead semantic-adapter local.** Default ruling: delete the dead copy
   (deletion bound) — the owner is live via the `typecheck.py:28` alias.
   M0 micro-task: reference-check that nothing imports the dead local,
   then delete. Reopens on: a live reference or behavioral diff surfacing
   during deletion.
3. **Let-proc hidden-context gate.** Default ruling: hidden-context
   eligibility stays exact-type-only for `let-proc`-generated procedures,
   per the promoted-entry hidden-context contract (RunCtx exact-type
   eligibility). M0 micro-task: one fixture proving a `let-proc` generated
   procedure neither gains nor loses hidden-context eligibility relative
   to its authored equivalent. Reopens on: that fixture exposing a real
   asymmetry.

## 3. Frontloaded Defaults (Recorded 2026-07-26)

Registered in the substrate track's decision list; restated here with
re-entry evidence. The pattern: every future gate checks evidence against
the default instead of holding a fresh meeting; only the named evidence
reopens an item.

- **ML-3 (bundle-transfer journal collapse): RULED — deferred until the
  provider-isolation freeze lifts.** ML-1/ML-2/ML-4 do not depend on it.
  Re-entry: the freeze lift itself (an owner act on the track's
  out-of-scope bound); no other trigger.
- **M2 depth: DEFAULT — (a) pure-result replay only.** Component (b)
  (effect-identity memo keys, memo-first resume) re-enters only on named
  evidence from post-ML operation: recovery re-spend diagnostics traced to
  positional-resume invalidation rather than genuine content change, in at
  least three distinct runs, or one run where positional invalidation
  forces a full-workflow re-execution. Absent that evidence, M2's design
  document covers (a) only and the depth decision is closed at M2 entry.
- **M4 go/no-go: DEFAULT — go for the `executor.py`/`validation.py` split**
  iff, at M4 entry, the modules still violate the local module rule (they
  are 10.1k/6.7k lines today; only intervening deletions could change
  this). Re-entry of "no-go": the modules arriving at M4 entry under the
  rule, or M3 evidence that the split seams are still unstable.
- **Neutral-IR boundary redraw: DEFAULT — not part of M4.** It joins only
  through its own accepted design act that explicitly re-rules the track's
  "WCC middle-end modules (stable)" out-of-scope bound. Re-entry: that
  design act; adjacency to M4 is not a trigger.

## 4. Net Decision-Queue Effect

Before: six open decision groups gating M0 items 2/4 and future phase
entries. After: items (1)/(2) carry recommended rulings awaiting M0
component-plan countersign; (3)/(4)/(6) are recorded defaults with named
re-entry evidence; (5) is ruled. No open item requires a synchronous owner
meeting; M0's component plan can be drafted immediately against this
brief.
