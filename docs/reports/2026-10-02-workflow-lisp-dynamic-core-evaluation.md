# Dynamic-Core Evaluation: Execution Evidence

Status: DC-0 and DC-1a complete and independently reviewed; DC-1b qualification
is next. No DC-F/DC-U/DC-P disposition. This report records actual source inspection,
test collection and coordinator-supplied control execution. The
[evaluation plan](../plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md)
owns selection; the [proposal](../design/workflow_lisp_dynamic_core_proposal.md)
owns candidate semantics. Planned cases below are not passed tests.

## 1. Pinned Controls And Synchronization

Qualification/control pin: `4b69ee00d4c6204dd816b4caa02b9fee1dae25e8`, branch
`design/orc-dynamic-core-evaluation`. At this session's start the coordinator
checked `feat/orc-phase3-execution` at `44c2d559` and
`feat/orc-phase3-r12-control` at `7af8ebf6`; both are integrated. There is no
additional committed shared slice to import. Dirty upstream control work is
excluded. Keep this control pin distinct from later synchronized integration
heads; explicitly re-pin affected comparisons if shared behavior changes.

| Control | Exact owner and evidence limit |
| --- | --- |
| Typed improve | `orchestrator/workflow_lisp/stdlib_modules/std/improve.orc` at target 2.33; `tests/test_workflow_lisp_improve_stdlib.py` and `tests/workflow_lisp_improve_stdlib_sources.py` own command-backed full helper outcomes and public legacy run/resume. Internal bundle execution and public execution are separately identified below |
| Python search | `experiments/mlevolve_pair/search.py::run_search` plus `leaves.py`; ordered calls/results from `tests/experiments/test_mlevolve_pair_fixture.py::_reference`. This control has no matching durable recovery |
| Typed compact search | `experiments/mlevolve_pair/search_compact.orc` and `commands_compact.json`; the 72-case test uses the **historical evaluated spike** through `tests.experiments.test_evaluated_execution_spike`, not a delivered public 2.35 runtime. Public original/compact sources retain diagnostic controls |
| Current evaluated runtime | `tests/test_workflow_evaluated_cli.py`: nine collected cases cover input binding, no-authority dry-run, pure completion/failure and returned record fields. No effectful/resume readiness claim |
| W1/W3 authoring comparator | `docs/design/workflow_lisp_write_once.md` and `experiments/orc_repetition_census/variants/reviewed_change_{a,b}.orc.txt`; illustrative/measurement variants remain labeled. Do not require their implementation or infer public runtime evidence from their existence |

Fresh collection, from the worktree root:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest --collect-only -q -p no:cacheprovider \
  tests/test_workflow_lisp_improve_stdlib.py \
  tests/experiments/test_mlevolve_pair_fixture.py \
  tests/test_workflow_evaluated_cli.py
```

Result: exit **0**, **105 tests collected in 1.25s**: improve 20, paired fixture
76 (72 spike comparisons + two Python references + two public diagnostics), pure
CLI 9. Collection establishes identifiers, not behavior. No broad suite was run.

Coordinator fresh execution at the same pin: the two `test_python_reference_*`
tests and the three parameterizations of
`test_improve_returns_the_candidate_its_outcome_is_about`: **5 passed in 2.26s**,
exit **0**. Exact command/head and output are in
`/tmp/orc-dc0-execution-rgo7l3b2/{result.json,control.log}`. This is deterministic
Python behavior and internal typed bundle behavior, not dynamic evidence.

Coordinator also ran
`test_public_run_returns_the_improvement_through_the_public_entry` and
`test_resume_after_a_committed_iteration_exhausts_without_replaying_committed_hooks`
in `tests/test_workflow_lisp_improve_stdlib.py`: **2 passed in 2.29s**, exit **0**;
exact command/head and output are in
`/tmp/orc-dc0-execution-rgo7l3b2/{public-result.json,public-control.log}`. These
prove the old route's public helper result and committed-hook reuse, not dynamic
feasibility. The seven fresh controls are distinct; the remaining collected cases
were not rerun here.

The earlier 26/54/1497-plus-six integration counts in the plan remain historical
baseline integration evidence; do not add overlapping selectors or turn the six
known red characterizations into a green full-suite claim.

## 2. Source Trace: Reuse And Missing Owners

Callers were inspected with repository `rg` over each named API and its imports;
no shared production owner is changed by qualification.

| Owner / actual call flow | Reuse boundary and consequence |
| --- | --- |
| `reader.py::read_sexpr_text` → compiler, normalized descriptors and closed target detection | Existing source spans/lexical reader can be reused if the reviewed candidate uses S-expressions; do not create a second tokenizer |
| `pure_expr.py::evaluate_pure_operator` → pure evaluation and frontend literal checks | Reuse primitive semantics through an explicit runtime-value adapter; do not recreate arithmetic. Its typed operand interface does not prove dynamic records/functions |
| evaluated `values.py` → `machine.py`, `calls.py`, authority and CLI | Values freeze data with descriptors and dependency evidence. Every typed expression/result is coerced; this is the typed control, not a dynamic value implementation to rename |
| evaluated `machine.py::evaluate_closed_program` → `runtime.py::execute_pure_run`, package export and unit fixtures | Requires `ClosedProgram`; calls use fixed `callee`, typed projections and checked frames. Its `EffectHandler` callback is a unit seam, not an attempt, performer, memo-replay or provider implementation |
| `calls.py::call_environment/call_result` → machine and call tests | Preserve old nominal/path/union transport and proof receipts. Candidate ordinary lexical calls need their own experimental value/frame delta, not typed specialization under another name |
| `closed/program.py::ClosedProgram.from_artifact` → typed build, authority/read-back and tests | Strict `closed-program/1`, `table/1`, typed P5 and static site checks remain unchanged. Candidate admission must validate its own version independently of compiler generation |
| `type_descriptor.py::validate_transport_value` → output contracts, portable context, workflow validation/executor, trial settlement/adjudication | Existing strict nested record/union/list/JSON kernel: exact fields, strict Bool, finite data, no host values/cycles. Float accepts an Int and converts to float; preserve/document that numeric rule rather than claiming no numeric conversion. Generic `validate_contract_value` additionally decodes/coerces strings and is not the direct strict dynamic-data entry |
| evaluated `memo.py` → pure terminal runtime, memo/authority tests | Durable append/reduction and suffix invalidation exist, but `site_class` accepts exact/static-loop-wildcard identities. A future resumable dynamic candidate would require an owner-reviewed bridge; the selected fresh candidate does not use this memo |
| evaluated `authority.py` → CLI and authority tests | Publication/read-back hardcodes `ClosedProgram`, `table/1`, typed bound inputs and `evaluated_execution.v1`. Retain it for typed runs; the candidate neither passes a dynamic artifact as typed authority nor needs a competing journal |
| evaluated `closure.py::resolve_command_evidence`, `closure_evidence.py`, `interpreters.py` | Files, directories, symlinks, package evidence and interpreter pins exist. They do not implement lexical closures or a complete command attempt/commit path |
| Phase 3 Task 6: `evaluated/{commands,attempts}.py`, runtime dispatch, R12 materialization | These performer/attempt modules are absent at the pin. `lowering/command_transport_decisions.py` and substitution kernel support are committed, while `closed/command_templates.py` and evaluated request consumption are still pending upstream |
| Phase 3 Task 7: `evaluated/{prompts,providers}.py` | Absent. Reuse existing prompt/typed-fill/output/provider owners through upstream delivery; no local provider shim, duplicate prompt renderer or invented snapshot semantics |
| Phase 3 Task 8: runtime/authority/memo preflight, public resume/invalidate | Full replay/attempt/retry preflight is absent. Pure `runtime.py` appends only terminal outcomes; `machine._perform` without a handler refuses `closed_effect_handler_missing`. Existing low-level suffix reduction is not end-to-end recovery |
| Phase 3 Task 12: `evaluated/inputs.py` and checked document transport | Absent. Needed only for chosen command document fixtures; scalar command smoke can precede it. Original typed grammar/order/absent-empty requirements stay with its upstream owner |

**Ownership consequence:** reuse real boundary and dispatch owners, checking
upstream Tasks 6–7/12 before dependent work. The owner's later tradeoff amendment
accepts absent effect tracking/resumability: Task 8 and dynamic memo/site/authority
bridges are therefore optional future work, not DC-F prerequisites. Keep the
inventory above as source facts without treating every missing capability as a
blocker. Do not duplicate performers or mistake a test callback for transport.

## 3. Consumers And Contract Inventory

`std/improve` imports/exported protocols are `Decision[F B]`,
`Improvement[S F B]` and `improve`; four type parameters, `inputs I`, selected
`ProcRef` hooks and `S is-record` are internal authoring mechanisms under test.
APPROVE/REVISE/BLOCKED and APPROVED/BLOCKED/EXHAUSTED payload distinctions are
behavioral obligations, not disposable type noise. Typed effect-summary tests
remain a lost-static-guarantee control, not a feature inherited by ordinary
functions. Honor declared execution permissions without promising inferred
static purity for ordinary dynamic functions.

The maintained proposal example imports `std/improve`. The shipped
`experiments/orc_vs_single_call/workflows/reviewed_change.orc` instead has its own
review loop at target 2.28; only the census variants use the helper. Its `Change`,
`Revision`, `Review` and `Outcome` domains, required `ReviewReport` path, typed
`:value List[String]` findings and composed provider prompts must be preserved
when used as a comparison. Do not claim the shipped file already uses W3.

Owner clarification during qualification: preserve **most existing type-to-I/O
contract machinery** while making high-level composition substantially more
Scheme-like/dynamic. The reuse path is concrete:

| Existing pipeline | Retained owner |
| --- | --- |
| Authored record/union/path declarations → normalized descriptors | `workflow_lisp/type_env.py`, `normalized_type_descriptor.py::compiler_normalized_type_descriptor`; boundary declarations remain useful, internal helper specialization is the candidate deletion |
| Declared result → generated input/output contract, projection/lineage metadata | `workflow_lisp/contracts.py::{derive_structured_result_contract,derive_prompt_guided_structured_result_contract,derive_workflow_signature_contracts}` and `workflow/type_descriptor.py::{transport_schema_for_descriptor,compiled_boundary_rows}` |
| Schema/field guidance → model output instructions | `workflow/prompting.py::PromptComposer.apply_output_contract_prompt_suffix` through existing contract renderers; no handwritten parallel JSON schema/instruction engine |
| Typed input → canonical value rendering / document delivery / output-role obligations | `workflow_lisp/typed_prompt_inputs.py::{select_prompt_fragment_renderer,render_typed_prompt_inputs}` and existing prompt calculus, dependency and `:doc`/`:out` owners |
| Result file/data → strict decoding, validation, projection and transport | `contracts/output_contract.py`, `workflow/type_descriptor.py::validate_transport_value`, existing result/bundle materialization and provider/command boundaries |

The JSON artifact in DC-1a is an **internal experimental seam**, not the final
language or authoring showcase. A later source-level `.orc`/Scheme-like composition
proof must reuse this pipeline and show closures with real typed prompt/result
boundaries before authoring benefit or readiness is claimed. No second schema
engine or rewrite of the existing contract pipeline is selected.

Boundary integration retains reusable schema identity, generated output guidance,
canonical value rendering, `:doc` dependency snapshots, `:path :out` required UTF-8
files and runtime-owned bundle paths. Typed path safety, fresh dependency bytes,
`publishes`/`consumes` lineage and result validation before publication keep their
existing owners. A path field alone proves neither authorship/freshness nor that
a consumer read it; a successful JSON schema check does not replace file checks.
Direct validator unit checks are possible now; actual provider/document/output
validation remains required through the shared adapters before DC-F. Durable
commit/replay evidence is not required for the non-resuming candidate.

## 4. Frozen Consumer Cases For DC-U

The complete 20-test improve control comprises 13 runtime/protocol cases, six
older-target admission cases and one specialized effect-summary case. Runtime
cases: three outcomes (initial approval, revision then blocked, third revision
exhausted); invalid review output; final permitted revision failure; imported
review wrapper; three inline/imported order comparisons; zero-limit no-hook
rejection; public blocked result; public committed-iteration resume; public
String-input committed-iteration resume. Retain the six old-target controls and
effect-summary assertion without claiming their typed checks are dynamic syntax.

Search freezes budgets **0, 1, 2, 3, 5, 6, 9, 12** crossed with exactly nine
scenario IDs: `invalid_seed_a`, `invalid_seed_b`, `invalid_seeds_both`,
`invalid_candidate_below_best`, `valid_tie_best`, `every_candidate_invalid`,
`repair_fails_then_succeeds`, `only_a_improves`, `invalid_candidate_solved_score`.
The 72 pairs compare full values/trace/spend and ordered command inputs against
Python. Keep the two Python reference traces and two public refusal cases as
separate controls; none is a dynamic run. Before DC-U also retain the plan's
explicit loop-exhaustion and schema-invalid-versus-valid-false distinctions;
passing the existing 72 alone does not establish those extra obligations.

The four paired author edits stay fixed: add a state field, change review payload,
capture context and extract a helper. They belong after DC-F; no live agent study,
new provider budget, full stdlib migration or W1/W3 implementation starts here.

## 5. DC-1 Scope And Review

### DC-1a: Pure Values, Closures, Admission And Budget

Exact new code/test paths, exclusively owned by the assigned candidate
implementer after independent qualification review:

- `experiments/dynamic_core_evaluation/program.py`: strict experimental JSON
  artifact admission/read-back, program-owned code references and schema bindings.
- `experiments/dynamic_core_evaluation/evaluator.py`: immutable dynamic values,
  lexical call frames, iterative node evaluation and deterministic step budget;
  calls existing primitive and boundary validators.
- `tests/experiments/test_dynamic_core_evaluation.py`: program specimens built
  directly as artifact data and the 48 cases below. No separate fixture forest,
  parser, `.orc` frontend, CLI, shared production edit or new dependency.

The reviewed Design amendment owns exact schema/node/operator/error spellings.
Artifact version `workflow-lisp/dynamic-spike/1` is not a production target;
inputs/results use existing normalized transport descriptors. Path contracts,
effects, imports and durable state are outside this sub-batch. Definitions may
reference each other/self; immutable runtime captures carry code identifiers and
values, never Python callables. One node-entry debit, with `N` allowing exactly
`N` evaluated nodes, is enforced by an iterative work stack.

Freeze **48 collected leaf cases** for this sub-batch; the implementation may
parameterize the IDs but must record any reviewed count change rather than
silently shrinking coverage. Additional assertions inside a case do not add to
the count. Expected outcomes are prospective:

| Group / count | Frozen case IDs and expected observation |
| --- | --- |
| Values/calls P01–P12 / 12 | P01 one helper body accepts both scalar and record inputs; P02 returned closure retains captured value; P03 closure stored/selected from an internal list invokes; P04 closure passed as argument invokes; P05 definition-site snapshot survives shadowing; P06 strict `if` executes only selected arm; P07 applying noncallable refuses; P08 wrong argument count refuses; P09 non-Bool condition refuses; P10 missing record field refuses; P11 invalid index refuses; P12 wrong primitive operand refuses |
| Boundaries B01–B12 / 12 | B01 nested record/list/tagged payload round-trip; B02 string masquerading as Bool refuses; B03 missing record field refuses; B04 extra record field refuses; B05 inactive union payload refuses; B06 wrong nested leaf refuses with its path; B07 nonfinite input refuses; B08 closure result refuses at declared result boundary; B09 cyclic input refuses; B10 host-object input refuses; B11 Int→Float uses existing documented normalization before dynamic formation, including Float(2**63) accepted while Int/Value(2**63) refuses; B12 null accepted only by an explicit nullable/JSON schema, refused by Bool |
| Admission A01–A18 / 18 | A01 valid artifact read-back with immutable snapshot and digest unchanged by JSON whitespace/key order; A02 unknown version; A03 unknown top-level field; A04 unbound name in an uncalled body; A05 forged code reference; A06 capture-count mismatch; A07 unknown schema reference; A08 malformed descriptor; A09 path schema refused in this slice; A10 effect node refused; A11 host-call node refused; A12 import node refused; A13 unknown primitive; A14 duplicate definition parameter; A15 malformed JSON and duplicate-key JSON text refuse; A16 unknown node field; A17 entry/input-signature mismatch; A18 duplicate record field. A02–A18 must refuse before any evaluation |
| Budget D01–D06 / 6 | D01 exact-budget success; D02 one-less-budget failure at deterministic expression path; D03 self-application reaches budget exhaustion rather than host recursion failure and records caller/pointer/selected-code call context; D04 repeated fresh evaluation consumes the same budget/prefix and pure call context; D05 function creation charges capture expressions; D06 left-to-right call argument evaluation charges each reached node once. No effect resets or memo-hit claims follow from this pure batch |

Admission mutations must be submitted independently to read-back, not only
constructed by the valid builder. Runtime errors retain operation/value kind and
artifact-expression location; this batch cannot prove authored source spans.
A10–A12 prove a closed pure vocabulary, not read-only enforcement for admitted
effectful functions. P03 selects from ordinary input/local data, not committed
effect data. Those distinctions remain open at DC-F.

Required execution commands after author/reviewer scope acceptance:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest --collect-only -q -p no:cacheprovider \
  tests/experiments/test_dynamic_core_evaluation.py
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider \
  tests/experiments/test_dynamic_core_evaluation.py
```

A bounded demo must load a serialized candidate artifact, validate declared data
inputs, evaluate closure composition, and validate its output. Record its exact
invocation from the implemented API in this report; do not call it production
`orchestrator run` support. Existing pure public smoke remains a separate shared
control. No broad suite is needed for isolated experiment-only code absent a
relevant failure; any shared-owner delta needs a new transfer and impacted checks.

### DC-1b: Real Boundaries And Fresh Execution

Owner amendment after qualification, 2026-10-02: loss of effect tracking and
resumability is acceptable when other advantages offset it. Evaluate one simpler
candidate that restarts from entry. The original twelve families are revised
below; no pure test count changes and no recovery implementation is selected.

| Family | Required observation / disposition |
| --- | --- |
| E01 | Select a closure using a freshly validated provider result, without requiring a memo commit |
| E02 | Capture that validated value and invoke a subsequent real effect |
| E03 | Interrupt before/after an external action; a fresh restart repeats the prefix. Record dispatches, partial writes and repeat cost; do not require reconstruction or reuse |
| E04 | Retain intelligible dynamic call context in diagnostics; stable journal identity/loop-site resolution is optional future recovery work |
| E05 | Effects do not reset the current invocation's budget. Restart begins a new invocation; memo-hit/replay accounting is outside this candidate |
| E06 | An orphan or stale runtime-owned result bundle cannot satisfy a fresh invocation's result obligation; no journal/commit implementation is required. This does not add freshness or authorship to an ordinary `:out` file contract |
| E07 | Fresh program/schema/input/file changes execute and validate as fresh inputs. Cross-revision reuse refusal is an old-route comparison, not a candidate requirement |
| E08 | Record that interruption may repeat external work on restart. No must-not-repeat/retry-resume guarantee is claimed; deployment suitability must account for this loss |
| E09 | Invalid input rejects before launch and invalid output before exposure to workflow code |
| E10 | Only linked operations may dispatch, respecting actual execution permissions. Static effect summaries and purity inference are recorded as lost guarantees |
| E11 | Document snapshots, required outputs, path containment and artifact handoff use the existing contract owners |
| E12 | Missing/wrong-path/malformed provider bundles refuse without returning a successful value |

These are twelve scenario families, not twelve claimed pytest cases. Freeze the
concrete independent assertions and selected adapter APIs before this sub-batch
starts. Check upstream progress and reuse existing transport/contract code; do
not rebuild a performer, memo, authority or recovery subsystem. Task 8 and the
dynamic memo/site bridge cease to be entry requirements. DC-1a alone still
cannot establish real boundaries or activate DC-2.

DC-U preserves fresh-run domain outcomes/order and the four author edits. The
typed control's committed-hook reuse and static effect-summary assertions now
measure deliberately lost capabilities, not mandatory parity. Compare repeated
external work/cost after failure with the composition and maintenance gains;
missing resume/effect tracking alone must not reject the candidate. Existing
typed targets and pinned runs keep their contracts.

**Next finite qualification:** fresh command/provider dispatch already exists
in `StepExecutor.execute_command` and `ProviderExecutor.prepare_invocation` /
`execute`; these low-level APIs alone do not own the complete workflow boundary.
`WorkflowExecutor` owns prompt composition and document snapshots, absent
runtime result-bundle preparation, required `:out` checks and joint result
validation/publication. Its existing API takes a real `LoadedWorkflowBundle`
and `StateManager`, rather than a dynamic artifact or standalone effect request.

Qualify a minimal adapter that invokes a fixed, compiled `.orc` boundary leaf
as a fresh execution: obtain `workflow_runtime_input_contracts`, use
`bind_workflow_inputs`, initialize a fresh run with those bound inputs, call
`WorkflowExecutor.execute(on_error="stop")` without resume, and consume its
validated `workflow_outputs`. This can exercise real registered provider and
command transport through current owners without waiting for Tasks 6–8 or
copying their prospective evaluated performers. Freeze exact leaves, bindings,
failure cases and paths before implementing the adapter. Dynamic closures stay
in the candidate; only the declared boundary leaf uses the existing compiler.
The retained legacy leaf state and invocation overhead count as costs, and this
seam proves neither dynamic `.orc` authoring nor production readiness or net
deletion. A subprocess-only callback cannot substitute for the complete boundary.

### Review State

On 2026-10-02 independent reviews passed after bounded corrections:

- `/root/design_dynamic_core_roadmap` reviewed this report and the plan: **PASS**.
  Corrected A15 to JSON-representable mutations, and added snapshot/digest and
  pure call-context assertions within the same 48 cases.
- `/root/planning_dynamic_core_sequence` reviewed proposal §6.1: **PASS** after
  defining schema normalization before Int64 dynamic formation, including the
  Float-versus-Int/Value `2**63` case. Existing APIs, operation arities, immutable
  captures, closed admission, deterministic budget and shared-owner limits match
  the inspected implementation; no unresolved blocking contract finding remains.

The coordinator selected **DC-1a only** and assigned its three paths to
`/root/design_dynamic_core_roadmap/impl_code_dynamic_core_pure` (Luna 6 xhigh).
The owner tradeoff amendment changes later integration criteria, not the reviewed
48-case pure contract. On 2026-10-02 `/root/design_dynamic_core_roadmap` independently
reviewed the coordinator's plan/report/roadmap gate amendment: **PASS**, after
removing residual site/state-profile prerequisites and keeping optional memo
integration separate from fresh execution. The coordinator independently
reviewed the proposal amendment; its retry wording was narrowed to existing
within-invocation rules, with no cross-run no-repeat guarantee. All three DC gates
remain pending. No production target, live-study allocation
or shared implementation ownership transfer is selected by this qualification.

## 6. DC-1a Execution Evidence

Implemented only [artifact admission](../../experiments/dynamic_core_evaluation/program.py),
[pure evaluation](../../experiments/dynamic_core_evaluation/evaluator.py) and the
[48-case module](../../tests/experiments/test_dynamic_core_evaluation.py).
The candidate reuses the existing primitive catalog and normalized boundary
validator. Production code and existing targets are unchanged. Public `.orc`
authoring, actual candidate effects and full DC-F feasibility remain unproved.

Author: `/root/design_dynamic_core_roadmap/impl_code_dynamic_core_pure` (Luna 6
xhigh). Independent conformity: `/root/design_dynamic_core_roadmap`, PASS.
Independent quality: `/root/token_accounting_review`, PASS after correction and
fresh B06 recheck (1 passed in 1.07s). Two malformed-artifact diagnostic escapes
and ambiguous field-path parsing were corrected; the latter parser was deleted,
retaining the safe kernel diagnostic instead. Call contexts are linked and
materialized for diagnostics, with a linear call trace rather than retaining a
full activation copy per call.

The author's initial 48 missing-module failures establish absent implementation,
not behavioral RED evidence. The review reproduced malformed-definition and
Unicode admission escapes; the later B06 field-name defect had a concrete failing
regression followed by GREEN. These review/author observations are in session
transcripts; no saved log path is invented for them.

Coordinator verification from the worktree root, with bytecode/cache disabled:

- Collection: **48 cases**, exit 0 (`candidate-collect.log`).
- Candidate plus existing public pure CLI: **57 passed in 10.27s**, exit 0
  (`candidate-final.log`). The later candidate-only diagnostic correction does
  not affect the nine public CLI controls; no production file changed.
- After that final correction: **48 passed in 1.11s**, exit 0
  (`candidate-recheck.log`); this is the final candidate result, not 48 additional
  distinct cases. Exact command and final three-file SHA256 values are in
  `candidate-recheck-results.json`.
- Independent serialized demo: exit 0 (`candidate-demo-final.log`). Write and
  read back an artifact, return a capturing closure, invoke it and validate its
  output. The same unspecialized helper accepts `7` and a record; both runs
  produce `next=42` in 17 steps with artifact digest
  `sha256:bf2a00d5e85e8aa0cc81621ace8fe5fea329ec1e7eee1ffec2c2a921b14f753d`.
- Documentation routing: **71 passed in 1.57s**. Changed links/anchors and
  `git diff --check` passed; typed Phase 3 task checkboxes remain unchanged.

These local logs, commands, file-hash receipts and `dynamic-demo.py` are under
`/tmp/orc-dc0-execution-rgo7l3b2/`. The independently reproducible checked-in
behavioral controls remain the test module. No broad suite was needed for this
isolated experiment; the earlier inherited red baseline is not reclassified.
The public CLI controls are the orchestrator smoke, while the serialized demo
is candidate integration evidence, not public dynamic-language support.

Next: qualify the fixed compiled-leaf route described in §5, using actual shared
input/prompt/output owners and fresh invocations. Keep checking upstream before
that selection/integration. Lost tracking/resume are permitted tradeoffs to
measure, not blockers; no second performer or recovery engine is authorized.
DC-1a completion does not activate DC-2 or select adoption.
