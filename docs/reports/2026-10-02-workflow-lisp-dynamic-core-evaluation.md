# Dynamic-Core Evaluation: Execution Evidence

Status: DC-0 and DC-1a/b/c implementation, verification and independent review
complete; DC-F owner **continue** on 2026-10-02. DC-2 is active; DC-U/DC-P
dispositions remain pending. This report records actual source inspection,
test collection and coordinator-supplied control execution. The
[evaluation plan](../plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md)
owns selection; the [proposal](../design/workflow_lisp_dynamic_core_proposal.md)
owns candidate semantics. Planned cases below are not passed tests.

## 1. Pinned Controls And Synchronization

Qualification/control pin: `4b69ee00d4c6204dd816b4caa02b9fee1dae25e8`, branch
`design/orc-dynamic-core-evaluation`. At DC-0 session start the coordinator
checked `feat/orc-phase3-execution` at `44c2d559` and
`feat/orc-phase3-r12-control` at `7af8ebf6`; both are integrated. At that check there was no
additional committed shared slice to import. Dirty upstream control work is
excluded. Keep this control pin distinct from later synchronized integration
heads; explicitly re-pin affected comparisons if shared behavior changes.

**DC-1b synchronization, 2026-10-02:** the coordinator merged reviewed integration
`0d7e4bc6f826b6f3002c2806bc7287a6e065ce76` cleanly at
`18a442da95df9de6a3f927ee99c067021c89d11a`. R12 source `0f1bbc46` and integrated
code `a780639c` share stable patch ID
`acf0c682851c47a464aeef5ae2c0840b2cd262cb`; all 14 imported source/test hashes match
the upstream receipt. Metadata was read from
`/tmp/orc-dc1b-execution-0a7ozwwm/upstream.json`. R12-A is complete; Task 6 overall
remains open. No dirty upstream files were imported. Fresh coordinator commands:

```bash
python -m pytest -q tests/test_workflow_lisp_command_templates.py tests/test_workflow_lisp_command_control.py
python -m pytest -q tests/test_workflow_lisp_improve_stdlib.py::test_public_run_returns_the_improvement_through_the_public_entry tests/test_workflow_lisp_procedures.py::test_wcc_m4_lowerer_uses_supplied_resolved_procedure_tuple tests/test_workflow_lisp_procedures.py::test_wcc_effectful_proc_pure_terminal_materializes_root_result
```

Results: **55 passed in 1.90s** and **3 passed in 1.59s**, including a real public
legacy run. Output is in the coordinator tool transcript; no saved log is claimed.
These are synchronization controls, not dynamic boundary evidence, and do not
re-pin the earlier comparison controls or erase the inherited red baseline.

**Second DC-1 synchronization, 2026-10-02:** reviewed integration
`9bb4b207d453fa7b0d9f1b141c9a0bfdd22125ff` was merged at
`d4dc1ea7595a8216026c36f015aec1497fd4e06b`. Integrated implementation
`abb3d5e92cf673118caa2c9ac6a8193125423aba` carries source
`a143378912ef173cc46094f90277d1bfc46f0681`: both Stage 3 constructors retain
the typed snapshot's producer lowering schema. Upstream Task 6 remains open;
this imports a reviewed reusable fix, not a second local implementation.
The eight affected selectors (12 collected parameterizations) passed **12 in
6.13s**, exit 0, using `-q -n 16 --dist=worksteal` in tmux. Exact command,
merge/source pins and result are in
`/tmp/orc-dc1b-execution-0a7ozwwm/producer-integration-result.json`, with output
in `producer-integration.log`. The earlier shared-owner broad run described
below preceded this merge; frozen DC-0 comparison controls remain unchanged.

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
as a fresh execution: obtain `workflow_public_input_contracts` (not the runtime/private input map),
derive strict descriptors from those same compiled contracts with
`transport_descriptor_for_schema`, validate dynamic values before the coercive
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
Qualification found a further limitation: `output_contract` can coerce raw
Bool/Int strings and flatten away extra record fields. Validating the already
normalized `workflow_outputs` therefore cannot prove strict provider output.
The coordinator selected a strict raw-return gate before artifact publication,
using the descriptor from the same compiled boundary. A minimal optional
`document_bytes` argument in `WorkflowExecutor._apply_expected_outputs_contract`
will forward the exact captured bytes to the existing `validate_output_bundle`
and `validate_variant_output_bundle` APIs, which already accept that argument.
Default behavior remains unchanged. The experimental adapter must not copy the
method, reread the result between strict validation and shared validation, or
accept already-coerced state as evidence. The reviewed §6.2 contract fixes the adapter shape below; no boundary success
is claimed from inspection.

**Original DC-1c handoff (implemented; receipts below):** use the existing S-expression reader for a bounded
source frontend and a checked-in `.orc` specimen combining an unannotated helper,
returned/stored/selected closures and two real typed boundary calls. Existing
`defrecord`/`defunion`/`defpath` and prompt/command contracts retain their owners.
Freeze exact source forms and frontend cases after the leaf bridge contract;
execute independent source lowering alongside DC-1b after seam qualification,
then verify the combined composition before DC-F.
Do not postpone authoring evidence behind full Phase 3/W3 or treat an authored
JSON artifact as the requested language improvement.

### DC-1b Reviewed Finite Scope

The following **24 frozen cases** refine E01–E12; this table is the
pre-execution contract, with actual receipts and corrections in §7. Two case
IDs per family, with explicit invalid vectors inside the indicated cases. The
[proposal §6.2](../design/workflow_lisp_dynamic_core_proposal.md#62-fresh-compiled-leaf-boundary-contract)
owns semantics; change the count explicitly if collection exposes accidental
parameter expansion. Use real
compiled leaves and a registered deterministic subprocess provider, without live
paid calls or mocking `ProviderExecutor.prepare_invocation`/`execute`.

| Case | Required observation |
| --- | --- |
| E01a | Valid provider result selects and invokes an ordinary closure |
| E01b | Valid command result selects a closure through the same strict boundary seam |
| E02a | Capture the validated record, store/pass the closure, and use it in a second leaf call |
| E02b | A valid tagged leaf result feeds a returned closure; it retains its snapshot despite later shadowing or another leaf changing the original result file |
| E03a | Failure before external action has zero dispatches; fresh invocation starts from entry |
| E03b | Failure after the first action preserves its observed side effect; fresh invocation repeats it |
| E04a | Unknown/unlinked leaf is refused before dispatch, including an unreachable reference |
| E04b | Failed leaf reports dynamic caller/expression/selected-code context without leaking input values |
| E05a | Exhaustion before the effect node or its required argument evaluations prevents launch |
| E05b | A completed effect does not reset the node budget; a separate invocation has a new budget |
| E06a | A pre-existing runtime-owned bundle cannot satisfy a fresh missing-result invocation |
| E06b | Two successful calls use distinct fresh run/result locations and do not reuse state |
| E07a | Changed ordinary input is bound and observed on the next fresh invocation |
| E07b | Changed document contents are resnapshotted on the next fresh invocation |
| E08a | A successful prefix repeats after a later leaf failure; record exact subprocess dispatch count |
| E08b | Failure may retain an ordinary output/external write; no rollback or cross-run no-repeat claim |
| E09a | Before launch reject missing/extra inputs, Bool-as-Int, numeric strings, wrong nested/tagged fields and closures; accept declared Float normalization from Int |
| E09b | Before publication reject raw Bool/Int strings, missing/extra/nested/inactive fields and non-finite values; valid strict and shared validation use one captured byte snapshot even after file replacement |
| E10a | Closed registry refuses missing/extra/non-leaf bindings; artifact data cannot supply a command/provider/host callable. A read-only invocation refuses an effect reached through a closure before dispatch |
| E10b | Actual workspace/path owner refuses escape/symlink misuse before launch or result consumption; no broader sandbox promise |
| E11a | Existing prompt/document machinery renders declared semantic input and captures a document snapshot; no literal prompt wording assertions |
| E11b | Existing required-output and artifact/path checks reject absent required output and accept a valid handoff |
| E12a | Missing or wrong-path structured result fails; stdout JSON cannot substitute |
| E12b | Malformed/duplicate-key raw JSON refuses and never publishes a successful candidate result |

**APIs and patch ownership.** Only the delegated implementer may edit:

- `experiments/dynamic_core_evaluation/program.py` and `evaluator.py`: preserve
  `/1`; admit `/2` with closed `effects` names and the single effect node,
  registry linking, read-only refusal and existing per-node budget/call context.
- New `experiments/dynamic_core_evaluation/leaf_bridge.py`: qualify one direct
  `ProviderResultExpr`/`CommandResultExpr` leaf; use `compile_stage3_entrypoint`,
  `linked_module_type_environment`, `compiler_normalized_type_descriptor`,
  `workflow_public_input_contracts`, `transport_descriptor_for_schema`,
  `validate_transport_value`, `bind_workflow_inputs`, fresh `StateManager` and
  full `WorkflowExecutor`. Guard strict raw output before shared publication and
  return the immutable validated wire-key `workflow_outputs`; no inverse codec.
- `orchestrator/workflow/executor.py`: exclusively the optional `document_bytes`
  keyword and its forwarding to both existing validators inside
  `_apply_expected_outputs_contract`. No other production behavior, duplicate
  hook body, global monkeypatch or additional execution mode. The coordinator
  explicitly authorized this shared-owner extension; record its reusable diff
  and verification for the upstream owner before final integration.
- New `tests/experiments/test_dynamic_core_boundaries.py`: exactly E01a–E12b;
  fixture source `experiments/dynamic_core_evaluation/fixtures/leaf.orc` and deterministic
  registered provider/command script
  `experiments/dynamic_core_evaluation/fixtures/scripted_leaf.py`. These fixtures retain
  real existing boundary declarations; they contain no candidate controller.

The coordinator assigns these paths to an implementation agent after independent
scope review; this qualification records no invented author. Recheck upstream
before that handoff. No frontend paths are in DC-1b; Design freezes DC-1c while
this adapter executes so visible authored composition follows without a new
planning cycle.

**Verification commands, proposed (not receipts):** run from the worktree root.
The first test run should reproduce concrete absent/refusing behavior before
implementation; a missing module alone is not behavioral RED evidence.

```bash
python -m pytest --collect-only -q tests/experiments/test_dynamic_core_boundaries.py
python -m pytest -q tests/experiments/test_dynamic_core_boundaries.py
python -m pytest -q tests/experiments/test_dynamic_core_evaluation.py tests/test_workflow_evaluated_cli.py
python -m pytest -q tests/test_workflow_output_contract_integration.py::test_command_step_persists_artifacts_when_contract_is_valid tests/test_workflow_output_contract_integration.py::test_provider_step_persists_artifacts_when_contract_is_valid tests/test_workflow_output_contract_integration.py::test_command_step_fails_when_expected_output_missing tests/test_output_contract_collections.py::test_validate_variant_output_bundle_supports_collection_shared_and_variant_fields
```

Collection expects 24 new cases; retain 48 pure plus nine public controls. The
four shared-owner selectors preserve default command/provider/required-output/
variant behavior; the new E09b snapshot assertion exercises opt-in forwarding.
E01/E02 run actual leaf subprocesses and supply candidate integration evidence;
the nine public controls supply the existing orchestrator smoke. Run one
serialized artifact→registered leaf→closure→second leaf demo using the checked-in
fixture and record its exact command/output, not just mocked invocation counts.

Keep the existing 48 pure cases unchanged. Preserve old-target semantics and run
focused shared-owner regressions plus an actual subprocess integration/demo;
unit stubs cannot discharge E01/E02/E09/E11. Record inherited leaf state and
invocation overhead, repeated calls and surviving partial writes as costs.

### DC-1c Source Scope

Reviewed finite handoff; proposal §6.3 and this scope passed independent review
by `/root/design_orc_showcase`. Independent source lowering may execute in
parallel with DC-1b against the frozen artifact/grammar; its combined source/leaf
verification follows DC-1b review and precedes DC-F. No extra owner permission is needed to complete
this already selected feasibility evidence. These are **12 source cases**
S01–S12, not execution receipts or a full language conformance suite:

| Case | Required observation |
| --- | --- |
| S01 | Compile the checked-in `.orc` specimen, serialize/read back its artifact and execute two real registered leaves in order |
| S02 | One unannotated helper body accepts both an integer and an internal record, with no argument-shape specialization |
| S03 | Nested inferred captures retain lexical values after shadowing, including a variable used only by an inner function |
| S04 | A validated result selects a returned closure; store it in a record/list and pass it to an ordinary application helper |
| S05 | Sequential `let*`, selected-arm-only evaluation and strict boolean conditions retain evaluator behavior |
| S06 | Zero-argument functions, empty collections and ordinary record/list/field/index expressions lower without new runtime machinery |
| S07 | Top-level helper forward references and bounded recursion work; helpers cannot implicitly capture public entry inputs, and local names shadow helpers |
| S08 | Unsupported/malformed forms and unbound names, including unreachable helper bodies, refuse with source diagnostics. An ordinary call with wrong arity compiles, fails with `dynamic_call_arity` only when reached, and does not fail in an unselected branch |
| S09 | Missing/extra/out-of-order headers, duplicate or reserved binders, duplicate fields and malformed declarations refuse |
| S10 | Public type names resolve through the compiled leaf type environment; preserve strict input/result validation and reject unknown schemas and callable boundary values |
| S11 | Whitespace/comments and source filename changes preserve the admitted artifact digest; a semantic literal change alters it |
| S12 | An effect reached through an authored closure obeys the existing read-only refusal with zero dispatch |

Exclusive implementation scope: new
`experiments/dynamic_core_evaluation/source.py`,
`experiments/dynamic_core_evaluation/fixtures/composition.orc`,
`experiments/dynamic_core_evaluation/README.md`, and
`tests/experiments/test_dynamic_core_source.py`. Reuse the DC-1b fixtures and
bridge. No production frontend, target, tokenizer, import system, evaluator or
schema grammar is added. The README compares composition excerpts with the real
`std/improve` signature/caller and gives the complete experimental command;
retain the typed route's existing String-context option and label proposed W3
as unimplemented. This specimen does not claim full improve parity or measured
net utility.

Proposed verification, from the worktree root:

```bash
python -m pytest --collect-only -q tests/experiments/test_dynamic_core_source.py
python -m pytest -q tests/experiments/test_dynamic_core_source.py
```

Expect 12 cases; record any deliberate count change before interpreting results.
Execute the README's complete command independently and record its actual
inputs, ordered subprocess effects, result and artifact digest. Source lowering
must call artifact admission; its runnable check must read the serialization
back before execution. Reuse unchanged boundary/pure evidence; broaden checks
only for relevant changes or discovered failures. Full DC-F remains pending
until evidence, independent review and an owner disposition exist.

### Review State

On 2026-10-02 `/root/planning_dynamic_core_sequence` independently reviewed
proposal §6.2: **PASS**. API/source checks cover the compiler-owned descriptors,
public input filtering, same-byte strict/shared output validation before
publication, closed registry and fresh-run semantics. `/root/design_dynamic_core_roadmap` independently passed the 24-case scope after
clarifying immutable-capture evidence and read-only refusal. The separately
assigned `/root/w3_planset_review` reviewer also passed §6.2 and requested the
explicit read-only closure assertion retained in E10a; that review covered the
preceding draft, not the final documentation diff. The coordinator accepted the
final seven-path handoff listed above. At qualification, DC-1c was the immediate
successor; its later implementation receipt is below. No DC-F disposition is recorded.

On 2026-10-02 independent reviews passed after bounded corrections:

- `/root/design_dynamic_core_roadmap` reviewed this report and the plan: **PASS**.
  Corrected A15 to JSON-representable mutations, and added snapshot/digest and
  pure call-context assertions within the same 48 cases.
- `/root/planning_dynamic_core_sequence` reviewed proposal §6.1: **PASS** after
  defining schema normalization before Int64 dynamic formation, including the
  Float-versus-Int/Value `2**63` case. Existing APIs, operation arities, immutable
  captures, closed admission, deterministic budget and shared-owner limits match
  the inspected implementation; no unresolved blocking contract finding remains.

The initial DC-0 disposition selected **DC-1a only** and assigned its three paths to
`/root/design_dynamic_core_roadmap/impl_code_dynamic_core_pure` (Luna 6 xhigh).
The owner tradeoff amendment changes later integration criteria, not the reviewed
48-case pure contract. On 2026-10-02 `/root/design_dynamic_core_roadmap` independently
reviewed the coordinator's plan/report/roadmap gate amendment: **PASS**, after
removing residual site/state-profile prerequisites and keeping optional memo
integration separate from fresh execution. The coordinator independently
reviewed the proposal amendment; its retry wording was narrowed to existing
within-invocation rules, with no cross-run no-repeat guarantee. All three DC gates
remain pending. No production target, live-study allocation
or general shared implementation ownership transfer follows. The later DC-1b
handoff above authorizes only its explicitly bounded shared hook extension.

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

At DC-1a completion, the next step was to qualify the fixed compiled-leaf route
described in §5, using actual shared
input/prompt/output owners and fresh invocations. Keep checking upstream before
that selection/integration. Lost tracking/resume are permitted tradeoffs to
measure, not blockers; no second performer or recovery engine is authorized.
DC-1a completion does not activate DC-2 or select adoption.


## 7. DC-1b / DC-1c Execution And Feasibility Review

The [source frontend](../../experiments/dynamic_core_evaluation/source.py) uses
existing reader/type owners, infers lexical captures and admits the same
versioned artifact. The [runnable specimen and command](../../experiments/dynamic_core_evaluation/README.md)
show ordinary source composition with a real provider followed by a command;
this is an experimental driver, not public `orchestrator run` support.
The [leaf bridge](../../experiments/dynamic_core_evaluation/leaf_bridge.py) uses
fresh compiled workflows through the existing full executor. The only shared
production edit is four added lines accepting/forwarding `document_bytes` in
`WorkflowExecutor._apply_expected_outputs_contract`, so strict raw validation
and the existing publisher consume the same byte snapshot.

Authors: DC-1b remains Luna 6 xhigh
(`/root/design_dynamic_core_roadmap/impl_code_dynamic_core_pure`). The coordinator
implemented the four DC-1c paths after the tool refused another implementation
thread; this is an explicit capacity exception, not a Luna attribution.
Independent source code/conformity review by
`/root/design_dynamic_core_roadmap` (Astra 6 xhigh): **PASS**, including a fresh
**12 passed in 3.52s**. The coordinator separately inspected the bridge, artifact,
evaluator and exact shared-hook diff. After the corrections below, independent
boundary code/conformity review by `/root/design_dynamic_core_roadmap` also
passed: seven strengthened cases passed in 3.56s, with no open findings. No separate Sol code-review result is claimed.

Source regressions reproduced a valid literal effect ID rejected as a reserved
binder and raw recursion errors from deep reader/type inputs. The fixes keep
operation identifiers separate from lexical binders and catch frontend depth
failures once at the source entry boundary. Unknown types preserve the existing
compiler diagnostic; ordinary call arity remains a runtime check. Source tests
cover both selected and unselected bad-arity calls. Concrete RED/GREEN logs are
in `/tmp/orc-dc1b-execution-0a7ozwwm/source-effect-name-red.log`,
`source-pure-reviewed.log`, `source-depth-red.log`, `source-type-depth-red.log`
and `source-type-depth-green.log`. Initial missing-module failures are not
behavioral RED evidence.

The first boundary run collected exactly **24** and passed **24 in 5.60s**
after fixing test assumptions about workspace-relative log paths; the retained
pure module passed **48 in 1.08s**. These author-reported results are in the
session transcript. Independent conformity found coverage gaps despite GREEN:
E11b needed an actual required UTF-8 output file, E11a an original-document
mutation after snapshotting, E02b capture use after a later write, E04b dispatched
failure context, and E09b/E10a/E12b stronger rejection/publication assertions.
These are corrections inside the frozen 24 IDs, not new functionality or a
passed feasibility gate.

Shared default-behavior verification: four narrow command/provider/required-file/
variant selectors passed **4 in 1.17s** (`shared-narrow.log`); the seven affected
modules passed **217 in 6.46s**, exit 0, in tmux with
`python -m pytest -q -n 16 --dist=worksteal` (`shared-broad.log` and
`shared-broad-result.json`, including command and source hashes). That broader
run preceded the second producer-schema import in §1. Counts overlap with the
candidate/public controls and must not be added together. The shared-hook diff
and these receipts form the reusable upstream handoff; no upstream worktree was
modified and no second performer was created.


### Final Combined Verification

Code commit: `53032343663737969456531040bacf7bebc9bdb2`, based on the reviewed
upstream import `d4dc1ea7`. Final source hashes matched before/after verification
and immediately before commit. Logs and the command/hash receipt are under
`/tmp/orc-dc1b-execution-0a7ozwwm/`:

| Check | Fresh result / evidence |
| --- | --- |
| Collect three candidate modules | 84 cases, exit 0; `final-collect.log` |
| Candidate 48 pure + 24 boundary + 12 source, nine public CLI controls, 71 routing checks | **164 passed in 8.18s**, exit 0; `final-candidate.log`, `final-result.json` |
| Exact README shell command, extracted without rewriting | Exit 0; `readme-final-command.sh`, `readme-final.log`; actual provider → command dispatches |
| Final code/conformity review | Independent source and boundary PASS; coordinator inspected final diff and verified unchanged hashes; no open finding |
| Final documentation update | 71 routing cases passed in 1.58s (`final-docs.log`); 21 changed local links/anchors and `git diff --check` passed; independent `/root/design_orc_showcase` review PASS |

The combined pytest command is:

```bash
python -m pytest -q -n 16 --dist=worksteal \
  tests/experiments/test_dynamic_core_evaluation.py \
  tests/experiments/test_dynamic_core_boundaries.py \
  tests/experiments/test_dynamic_core_source.py \
  tests/test_workflow_evaluated_cli.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
```

The README run uses `goal="reject draft"`, `rubric="clarity"` and a declared
input document containing `DOC_A`. Its returned feedback is
`reject draft | clarity | reject draft|clarity|DOC_A | draft`; it executes
**53 nodes**, with seven code definitions in a 2705-byte admitted artifact.
Artifact digest:
`sha256:de1dea648ad510972b3856955ed602f3ce7ffd5c7ffe16ec64318688b1286257`.
It retains **two separate legacy leaf states** in
`/tmp/orc-dynamic-source-fj1tq_qh`. The approval branch is separately covered
by S01 and executes only the provider. These are deterministic local
subprocesses, not a paid-provider quality or performance study.

The final upstream check still found integration `9bb4b207` and source
`0f1bbc46`; no additional reviewed commit was available. The four-line optional
byte-forwarding hook in `53032343` is the reusable upstream handoff; its default
behavior checks and exact source hash are in the receipts above. No external
publication or upstream worktree mutation occurred.

### DC-F Decision Packet

| Feasibility obligation | Evidence |
| --- | --- |
| Ordinary lexical composition | P01–P12 and S01–S12; one helper accepts scalar/record values, inferred captures survive shadowing and later result-file replacement, real provider data selects a stored/passed callable |
| Fresh actual effects | E01–E03/E06–E08 plus README; real shared provider and command owners, fresh run locations, repeated prefix after failure |
| Strict boundary contracts | B01–B12/E09/E11/E12; raw invalid data rejected before publication, one captured validation snapshot, document snapshot survives original mutation, missing/non-UTF-8 required `:out` refuses |
| Closed admission and permissions | A01–A18/E04/E10/S08–S10/S12; malformed artifacts, unlinked/inline hosts/non-leaves and read-only dispatch refuse |
| Bounded execution | D01–D06/E05/S07; deterministic node accounting, recursion exhaustion, completed effect does not reset budget |
| Honest failure semantics | E03/E06/E08/E12; no stale result success, failed later calls repeat the successful prefix on restart; partial writes remain |

Adverse evidence is part of this result: restarting repeats external calls;
ordinary output files are not rolled back or proven fresh; dynamic call/operand
errors can occur after an expensive effect; each leaf retains legacy state and
compiler/startup machinery. There is no candidate resume, static effect analysis,
public target, complete source-map diagnostics or demonstrated net deletion.
The bridge exposes existing `return__…` wire keys. Full improve/search protocols,
the four paired author edits and utility versus the implemented typed baseline
and proposed W3 remain untested here. They belong to DC-2; these omissions do not become delivered
capabilities because feasibility checks passed.

Independent feasibility review: **PASS**. Coordinator recommendation:
**continue to DC-2** to measure those benefits and costs. Owner disposition, **2026-10-02: continue** — the user selected
“Continuar a DC-2 (recomendado)” after this packet was complete and committed
as `40fbdf8f` (code `53032343`). The selected successor is the plan's finite
DC-2 consumer/authoring comparison, preserving frozen controls and upstream
synchronization. DC-U, DC-P and production migration remain unselected.

DC-2 entry synchronization checked integration `9bb4b207` and source
`0f1bbc46`; both remain unchanged and imported. Design and planning are
qualifying only the language additions and finite cases required by the full
consumer protocols; no competing shared performer or recovery work is selected.

## 8. DC-2 Finite Utility Scope

This is the planned handoff after the recorded DC-F continue, not execution
evidence or a DC-U disposition. The
[plan's finite handoff](../plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md#finite-execution-handoff)
owns batch order, exclusive paths and commands; the
[proposal §6.4](../design/workflow_lisp_dynamic_core_proposal.md#64-bounded-complete-consumer-comparison)
owns semantics. No new registry/report is introduced. Freeze **110 new logical
cases**: 12 core/boundary, 11 improve, 77 search, four paired edits and six
diagnostic/restart cases. A case may contain the explicitly listed assertions;
record actual pytest collection separately rather than silently expanding this
inventory or calling assertion counts independent runs.

Retain the §1 qualification pin
`4b69ee00d4c6204dd816b4caa02b9fee1dae25e8` and its **105 controls**: 20 improve,
76 paired-fixture and nine public evaluated CLI cases. Source files for those
controls remain unchanged. Later synchronization/selection commits do not
silently advance this baseline. The typed compact-search comparator is the
historical evaluated spike, and the public original/compact refusals remain
controls. Current public readiness and W1/W3 proposals are separate evidence.
DC-2 executes all 105 controls, since DC-0 collection alone was not full
execution evidence; record the current runtime revision alongside the frozen
source pin. Keep the existing 84 DC-1 candidate cases and their historical IDs
unchanged as regression controls, separately from these 110 planned cases.

Qualification review, 2026-10-02: proposal §6.4 independently **PASS** by
`/root/design_orc_showcase` (Astra 6 xhigh); plan/case handoff independently
**PASS** by `/root/review_code_dynamic_core_utility` (Sol 6.1 high). The latter
verified all three frozen control modules have no diff from `4b69ee00` and
requested the valid-first/missing-later UC06 vector retained below. The
coordinator inspected both contracts and selected DC-2a implementation next.
These are scope reviews, not executed consumer cases or a DC-U disposition.

Fresh comparator execution: **105 passed in 7.93s**, exit 0, in tmux using
`python -m pytest -q -n 16 --dist=worksteal` on the three §1 control modules.
Runtime checkout: `706c10c8f782852c1ffacf48345d70c68072a5c9`, production tree
`bf8cc895758c12f78b98f4531f0997c358f64f41`. The coordinator verified those three
source files have no diff from `4b69ee00` and no uncommitted production changes.
Exact command, file hashes and exit are in
`/tmp/orc-dc2-execution-0jczbaqn/controls-result.json`, with `controls.log`.
This closes the earlier collection-only gap for the retained controls; none
of the 110 new dynamic utility cases is credited by this run.

### Core And Existing Boundary Reuse — 12 Cases

UC01–UC12 live in `tests/experiments/test_dynamic_core_utility_core.py`; the two
final groups cover the compiled bridge. All artifact cases
must pass admission independently of source generation. Runtime negative cases
record code, artifact location, call context and effects already completed.

| ID | Frozen observation |
| --- | --- |
| UC01 | `/3` source artifact survives disk write/read-back; the four new forms are refused in `/1` and `/2`, while existing old-version artifacts still execute |
| UC02 | Appending one item to empty/nonempty immutable lists retains order; mixed ordinary values and an internal closure are valid; the original list stays unchanged |
| UC03 | `list/append` refuses non-list bases and wrong arity; no scalar coercion or homogeneous internal-list signature |
| UC04 | `list/length` returns zero/nonzero Int lengths and refuses non-list operands and wrong arity |
| UC05 | `record-update` retains untouched fields, evaluates replacements and permits an internal closure value without mutating the base |
| UC06 | Updating an absent field or a non-record base fails before evaluating replacement expressions; include a valid first key with an observable replacement followed by a missing key, proving all-key validation precedes any replacement. No silent new keys or base coercion |
| UC07 | Empty updates, duplicate/nonliteral update keys and malformed update nodes fail source/artifact admission, including in unreachable helpers |
| UC08 | Container operands/replacement expressions execute once in source order; their evaluations share the same invocation budget and do not reset it |
| UC09 | Reached `fail` emits its declared reason with location/call context; an unselected failing arm does not fail or dispatch |
| UC10 | Nonliteral, empty or non-String fail reasons and forged nodes with missing/extra fields fail admission |
| UC11 | One direct typed certified-adapter command leaf dispatches through the existing compiler/executor, preserves ordered JSON input and validates its declared result; `/3` read-only evaluation refuses with zero dispatch |
| UC12 | A missing/mismatched adapter binding and invalid typed inputs refuse before dispatch; malformed raw adapter output is rejected before exposure, using the existing strict result check |

No loop, match, dynamic import, Boolean combinator, mutation or host callback
is added. Recursion and strict `if` express controller policy. Collection-copy
costs, `/3` compatibility and the retained adapter/compiler machinery belong in
the complexity accounting.

**DC-2a complete, 2026-10-02, code `e7da6fd2`:** Luna 6 xhigh implemented
only the four candidate modules and new UC module. Independent conformity by
`/root/design_dynamic_core_roadmap` (Astra 6 xhigh) and code/quality review by
`/root/review_code_dynamic_core_utility` (Sol 6.1 high) both passed, with fresh
12-case checks and no open finding. The coordinator inspected the diff and
verified unchanged hashes before committing. Early RED included malformed test
fixtures; those were corrected separately from actual missing `/3` forms and
the existing candidate adapter refusal. No claim that every initial failure
proved missing functionality is made.

Coordinator receipts in `/tmp/orc-dc2-execution-0jczbaqn/`: `core-collect.log`
collected **12**, `core-final.log` passed **96 in 4.51s** (12 new + 84 retained,
`-q -n 16 --dist=worksteal` in tmux), and the exact existing README command
passed in `core-demo.log`/`core-demo.sh`. `core-result.json` holds commands,
exits and equal before/after source hashes. The `/3` example still executes
provider → command in **53 nodes**, returning the same captured goal/rubric/
DOC_A feedback; its new versioned digest is
`sha256:399dea840313beaa532c51247011943ca0dfba3b736f7a6e4adc2dd3efb87774`.
The earlier `/2` digest in §7 remains historical at its recorded code pin.

UC11/UC12 execute a real certified adapter and strict refusal paths through the
existing compiler and executor. No shared production file changed. The latest
upstream check still found integration `9bb4b207`; no new import was available.
These results complete DC-2a only: DC-2b improve is now executing; the other
98 utility cases and the full-consumer demonstration remain pending.

### Full Improve — 11 Fresh-Run Cases

`fixtures/improve.orc` is the shared ordinary-definition fragment.
`fixtures/utility_leaves.orc` preserves typed `Draft`, `Feedback`, `Blocker`
and existing imported `Decision`/`Improvement` schemas. The utility improve
test module reuses the frozen review/revise probe behavior. Explicit driver
assembly combines helper definitions with the caller/header; assembled versus
inline source is tooling evidence, not a dynamic module/import feature.

| ID | Frozen observation |
| --- | --- |
| UI01 | Initial `approve`, limit 3: APPROVED retains the initial candidate and evidence, one review and no revise |
| UI02 | Initial `block`, limit 3: one revision then BLOCKED retains `block+r`, score 1 and the refusal reason |
| UI03 | Initial `draft`, limit 3: EXHAUSTED retains the third revised candidate, score 3, and all three ordered review/revise pairs |
| UI04 | `malformed` review payload fails its typed contract before decision consumption; no revise occurs |
| UI05 | `fail`, limit 2: the final permitted revise failure is a runtime failure, never successful EXHAUSTED |
| UI06 | An ordinary dynamic review wrapper agrees with the typed imported-wrapper control at `draft`, limit 2; no dynamic-import capability is claimed |
| UI07 | `approve`, limit 3: explicitly assembled shared helper and inline definitions agree with typed imported/inline control outcomes and ordered hook inputs |
| UI08 | `block`, limit 3: the same assembled/inline and typed-control comparison |
| UI09 | `draft`, limit 3: the same assembled/inline and typed-control comparison |
| UI10 | Limit 0 is rejected before either hook; report the dynamic failure stage alongside the typed compile-time refusal |
| UI11 | BLOCKED passes the precise dynamic result boundary and agrees with the existing public typed-run output after explicit wire normalization; no public dynamic launch is claimed |

Compare full payloads, latest candidate, per-hook ordered arguments and complete
operation order, not only final tags. Keep the two typed committed-iteration
resume cases as lost-capability controls exercised in UD05/UD06. Keep six
old-target admission cases and the selected-hook effect-summary case unchanged;
the candidate does not inherit those static guarantees.

### Full Paired Search — 77 Cases

`fixtures/search.orc` contains the authored controller. Reuse the exact
`SCENARIOS`, `BUDGETS`, `_scenario_answers` and `_reference` owners in
`tests/experiments/test_mlevolve_pair_fixture.py`; do not copy policy into a
Python dynamic-controller implementation. Reuse its scripted JSON leaves and
`experiments/mlevolve_pair/commands_compact.json` through the certified adapter.
`utility_leaves.orc` retains `Candidate`, `Evaluation`, `Trial` and
`SearchResult` domain schemas.

**US01 contains exactly 72 pairs:** budgets **0, 1, 2, 3, 5, 6, 9, 12** crossed
with `invalid_seed_a`, `invalid_seed_b`, `invalid_seeds_both`,
`invalid_candidate_below_best`, `valid_tie_best`, `every_candidate_invalid`,
`repair_fails_then_succeeds`, `only_a_improves`,
`invalid_candidate_solved_score`. Use parameter IDs containing US01, scenario
and budget. Each pair compares the entire Python result, trace, ordered command
inputs and evaluation spend. The policy includes seed ranking, strict ties,
one repair on the failed branch, stalls, one fusion and complete parent history.

| ID | Additional observation, one logical case each |
| --- | --- |
| US02 | Existing nonscripted local leaf functions at budget 12 reproduce the Python ten-evaluation solved trace, including repair, ties and fusion |
| US03 | Budget 17 returns domain `invalid_budget` with zero dispatch; 0 and 1 remain in US01 rather than being counted twice |
| US04 | A real schema-invalid candidate bundle fails publication before evaluation consumes it; record the successful prefix separately |
| US05 | A real schema-invalid evaluation bundle fails publication, whereas a correctly typed `valid=false` result follows the repair policy; neither becomes an implicit solved score |
| US06 | A test-only reduced controller iteration bound reaches `loop_bound_exhausted`, agreeing with the same reduced-bound typed compact spike; this outcome is distinct from evaluation-budget exhaustion and VM-budget failure |

US06 changes only the test specimen's internal bound; no public configuration
or Python-reference outcome is invented. Invalid non-Int boundary inputs stay
strict boundary failures. The two existing Python-reference tests and two
public-refusal tests remain separate controls, not additional dynamic pairs.

### Four Paired Edits And Six Diagnostic/Restart Cases

`tests/experiments/test_dynamic_core_utility_edits.py` generates bounded edited
copies in temporary workspaces; maintain the four pairs there rather than
adding eight permanent specimen families. Small setup functions may be reused
from the consumer test modules; no general fixture framework is required.
Both sides execute each edited behavior with the same local leaves and retain
their useful domain declarations and strict transport schemas.

| ID | Concrete authored change or failure experiment |
| --- | --- |
| UE01 | Add `origin: String` to the improve candidate, initialized as `seed`, preserved by revision and observed in the final value; count boundary and internal-state edit sites separately |
| UE02 | Rename review feedback/evidence `note` to `message`, preserving its content and updating the producing schema/probe and actual consumers on both sides |
| UE03 | Capture an additional `rubric: String` used by review independently of `goal`; compare typed explicit context plumbing with a dynamic lexical capture, and credit the already-supported typed single-String context and proposed W3 alternative |
| UE04 | Extract the feedback-to-revision-input expression into an ordinary pure helper while keeping the same boundary payload and ordered effects; compare with the existing executable typed pure-helper form rather than an intentionally verbose baseline |
| UD01 | Unbound lexical name is rejected before dispatch; compare diagnostic stage/location with the corresponding typed source error |
| UD02 | A wrong ordinary call arity before any effect and the same mistake after one successful review record their distinct effect counts; repair the one mistake and rerun |
| UD03 | A missing internal field reached after one successful review records its late diagnostic, partial outputs and one-site repair; compare typed detection without deleting the field contract |
| UD04 | Deliberately insufficient VM budget after a completed effect records deterministic exhaustion and the completed prefix; it is neither a controller outcome nor a resume point |
| UD05 | Interrupt after the first successful review/revise pair, restart fresh and compare with typed committed-iteration resume: full final value agrees, but dynamic prefix calls repeat and existing external outputs remain |
| UD06 | Repeat the interruption/restart comparison with the typed String-input control and captured dynamic goal; demonstrate preserved context plus repeated dynamic work without claiming a context-record-only typed baseline |

For each UE case record the exact before/after source, touched semantic sites,
duplicated facts, concepts required, observed repair attempts and outcome.
Record implementation/programming time only if measured with a stated method;
there is no live author study. For each UD case record error code, stage,
location/call context, number/order of completed effects, remaining leaf/output
artifacts, repaired result and restart calls. UD05/UD06 must prove the prefix
completed before interruption; do not count a pre-dispatch failure as restart
cost. No paid-provider quality, money or latency conclusion follows from these
deterministic local calls.

### DC-U Evidence Packet

After these cases execute and independent review completes, append receipts to
this same section. Separate supported, adverse, missing and untested findings.
List added source/admission/evaluator/driver paths; retained domain validators,
specialization, command/provider and state owners; actually displaced owners
(possibly none); `/1`–`/3` identities; old-target compatibility; and each leaf's
retained legacy state/startup work. LOC alone does not establish net complexity.
The best implemented typed control, historical spike and proposed W1/W3 must
remain separately labeled. Credit W1/W3's plausible reduction in constructor
repetition/context plumbing without pretending it executes or requiring its
implementation here.

The full-consumer README command is part of DC-2d and must run before closeout,
in addition to narrow/combined checks. Record fresh commands/exits/revisions
and independent review, then recommend continue, bounded revision or typed
fallback. **DC-U owner disposition remains pending**; passing these cases
does not select DC-3, a public target or adoption.
