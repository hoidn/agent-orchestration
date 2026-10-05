# Dynamic-Core Evaluation: Execution Evidence

Status: DC-0 and DC-1a/b/c implementation, verification and independent review
complete; DC-F owner **continue** on 2026-10-02. All 110 DC-2 cases have executed
and final code and independent document/utility reviews passed. DC-U owner
**continue** on 2026-10-02 selects bounded DC-3 readiness qualification;
DC-P remains pending.
This report records actual source inspection,
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

**DC-2 synchronization, 2026-10-02:** integration
`f572a82a896c50002f1da2ee701aaaaf8661ea3c` merged cleanly at
`a55a035dc1c1b1d6df206faca886479638dd4aac`; source control branch remains
`0f1bbc46`. Independent code review by `/root/review_code_dynamic_core_utility`
(Sol 6.1 high) passed with 17 narrow tests. This two-file slice extracts the
captured-byte validation owners in `output_contract.py` and their tests; it
preserves public wrapper behavior and the candidate's existing byte-forwarding
hook. No local replacement was implemented and no dirty upstream work imported.

Fresh coordinator integration: **17 passed in 2.39s**, then **127 passed in
7.38s**, exit 0, using tmux and `-q -n 16 --dist=worksteal` for the combined
output-contract, candidate boundary/core, typed improve and evaluated CLI
modules. These include real public helper run/resume. Commands, exact runtime
revision and unchanged before/after owner hashes are in
`/tmp/orc-dc2-execution-0jczbaqn/upstream-result.json`; outputs are
`upstream-narrow.log` and `upstream-integrated.log`. Frozen control sources and
their qualification pin remain unchanged; this behavior-preserving extraction
does not re-pin controls, finish Task 6 or pass a dynamic gate.

**Pre-DC-2d synchronization, 2026-10-02:** integration `c3162d42` merged cleanly
at `820a12a96d0ec44ca46667674b5570de472ff29f`. It includes `a6487768` (opt-in
pinned attempt capture), `8ce38bb2` (R12-B compiler-local scopes, source
`52b612ff`) and their independently reviewed upstream receipts. Integration
assessment by `/root/review_code_dynamic_core_utility` (Sol 6.1 high) found no
interaction conflict: the candidate's existing executor/byte hook is untouched,
capture defaults remain legacy, and command-scope annotations are opt-in. The
coordinator inspected the merged diff; the imported exec/compiler trees match
upstream. No local performer or capture implementation was added.

Fresh narrow checks passed **11 in 2.52s**; the affected combined run passed
**254 in 10.79s**, exit 0, in tmux with `-q -n 16 --dist=worksteal`. This covers
capture/secrets, command scopes/control, dynamic boundaries/core/improve/search,
typed improve and evaluated CLI. Exact commands, revision and equal before/after
owner hashes are in `/tmp/orc-dc2-execution-0jczbaqn/scope-import-result.json`,
with `scope-import-narrow.log` and `scope-import-impacted.log`. Control sources
remain unchanged at their frozen pin; the current runtime is recorded separately.
The upstream 949-pass/5-inherited-failure broad receipt is historical, not a new
global PASS. R12-B/C and Task 6 remain open; no dynamic gate advances here.

**Pre-DC-U synchronization, 2026-10-02:** reviewed integration `b7d82fa1`
merged at `bcc4ee1385877289e1ecb0012ae1f40b07d44bfc`, including the reviewed
attempt-allocation work and interpreter-pin design. The coordinator's narrow
attempt checks passed **11 in 2.56s**; output is in the tool transcript, with
no saved log claimed. The combined 370-case receipt in §8 ran on this integration.
This imports shared progress rather than implementing it here. The frozen
comparator remains `4b69ee00d4c6204dd816b4caa02b9fee1dae25e8`; record the moving
runtime separately and continue periodic upstream checks. Neither import nor
green checks finish typed Task 6, approve DC-U or erase historical failures.
The gate-time recheck still found upstream integration
`b7d82fa18a5ebbe84797c0036fb4178712f81d27` and source
`0f1bbc46b4f4d8cdcdbbe509264566594f016bfd`. The integration is an ancestor;
the source patch is already integrated as `a780639c`, with the equal stable
patch ID recorded above. No additional shared patch was available to import.

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

Implemented only artifact admission, pure evaluation and the 48-case module.
Their historical owners are retained at `6844e05e`:
`experiments/dynamic_core_evaluation/{program,evaluator}.py` and
`tests/experiments/test_dynamic_core_evaluation.py` (read with
`git show 6844e05e:PATH`). The later cutover moves are not this historical proof.
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

The historical source frontend, `experiments/dynamic_core_evaluation/source.py`
at `53032343` (`git show 53032343:experiments/dynamic_core_evaluation/source.py`),
uses existing reader/type owners, infers lexical captures and admits the same
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

This preserves the finite handoff after the recorded DC-F continue; the
execution and utility packet follow its case inventory below. It is not a
DC-U owner disposition. The
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

**DC-2b complete, 2026-10-02, code `18121c76`:** Luna 6 xhigh implemented
the three assigned files; independent conformity by
`/root/design_dynamic_core_roadmap` (Astra 6 xhigh) and quality review by
`/root/review_code_dynamic_core_utility` (Sol 6.1 high) passed. The shared helper
reads decision tags and transmits payloads opaquely; caller hooks own explicit
wire/domain reconstruction. This preserves the typed helper's generic payload
behavior without adding a decoder. An independent inline caller definition set
and shared-fragment assembly are distinct source owners, not dynamic imports.

Author collection found **11**; final author narrow check passed **11 in
8.72s** after deleting unused/duplicated test setup. Conformity independently
passed the same eleven before that test-only cleanup; final quality confirmed
the cleanup and exact hashes. Fresh coordinator check passed **11 in 8.73s**,
exit 0, including real local command leaves and the public typed-run comparison.
`/tmp/orc-dc2-execution-0jczbaqn/improve-result.json` records the exact command,
runtime revision and equal before/after hashes; output is `improve-final.log`.
Initial behavioral RED used an EXHAUSTED stub where APPROVED was required;
subsequent fixture syntax/wire-input corrections are not missing-feature proof.

UI04 identifies the actual schema refusal and absent publication; UI05 verifies
the completed three-call prefix and final revision's exit 3; UI10 verifies no
leaf attempt. Context capture is exercised by the wrapper case. These results
complete improve protocol parity, not utility or adoption: the 77 search and
10 author-edit/diagnostic observations remain pending. The pre-search upstream
check found only documentation receipt `5ffad6ba` after `f572a82a`; that receipt
was merged without changing runtime or frozen comparison sources.

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

**DC-2c complete, 2026-10-02, code `e31e8282`:** implementation by
`/root/impl_code_dynamic_core_search` (Luna 6 xhigh), conformity by
`/root/design_dynamic_core_roadmap` (Astra 6 xhigh), and code/quality review by
`/root/review_code_dynamic_core_utility` (Sol 6.1 high), all complete with no
open finding. The policy is authored entirely in `.orc`; real certified adapters
and the precise `SearchResult` boundary are retained. The shared-module setup
handoff was limited to loading the same existing bindings for inactive leaves.

Collection found **77** search cases. Author full matrix: **77 in 5.77s**;
independent conformity's focused US02–US06: **5 in 5.37s**. After all corrections,
fresh coordinator combined search/improve checks passed **88 in 6.62s**, exit 0,
with unchanged before/after hashes. Receipt and output:
`/tmp/orc-dc2-execution-0jczbaqn/search-result.json` and `search-final.log`.
The later upstream integration reran both consumers in its affected check above.

All 72 scripted pairs compare the full result/history and ordered requests;
the real local-leaf case matches the ten-evaluation solved trace and every
request payload. Schema-invalid bundles refuse publication, distinct from
typed `valid=false`; lowered controller exhaustion matches the equally modified
historical compact spike. No public evaluated effect-run claim follows. Early
fixture review corrected missing real-call logging and strengthened failed
publication and actual-program schema assertions; the initial functional RED
was an `invalid_budget` stub where two seed evaluations were required.
These observations complete 100 of 110 new utility cases; the ten paired
author-edit/diagnostic observations and the DC-U decision remain pending.

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

### DC-2d Execution And Final Review

The four paired edits and six diagnostic/restart cases executed with actual
compiled local command leaves. Their exact source pairs, effect logs, error
locations, repair observations and retained leaf state are under
`/tmp/orc-dc2-execution-0jczbaqn/edits-reviewed-vutxmuny/**/evidence/{UE01–UE04,UD01–UD06}/receipt.json`.
These are coordinator-observed temporary artifacts; the checked-in test module
recreates them. No author-time, money, quality or performance study was run.

The first combined run precedes two bounded evidence corrections: UD01 now
asserts/records the full repaired value and calls; UE03 classifies preexisting
`Brief` forwarding as retained behavior. The existing implementer applied both;
no candidate semantics, production code or demo changed. Author:
`/root/impl_code_dynamic_core_utility` (Luna 6 xhigh); final code commit
`4728b14e`. Independent conformity by `/root/design_dynamic_core_roadmap`
(Astra 6 xhigh) passed; final code/quality review by
`/root/review_code_dynamic_core_utility` (Sol 6.1 high) passed with all findings
closed. The coordinator inspected the corrected diff and receipts. Independent
review of utility and all seven documentation changes by
`/root/design_dynamic_core_roadmap` (Astra 6 xhigh): **PASS**, with no blocking
findings. It supports considering the bounded readiness scope below; it does not
select the owner disposition. Documentation verification is recorded below.

| Check | Observed receipt and limit |
| --- | --- |
| Collection and impacted integration | 370 cases collected; **370 passed in 12.54s**, exit 0, with `-q -n 16 --dist=worksteal` in tmux. `final-result.json`, `final-collect.log`, `final-combined.log` under `/tmp/orc-dc2-execution-0jczbaqn/`; equal before/after code hashes. Runtime `bcc4ee13`, production tree `a3728ccdce03c80f2c238cd965b67d8645ee81a8`. This precedes the two review corrections. |
| Distinct counted cases | 110 new: 12 UC + 11 UI + 77 US + 4 UE + 6 UD; 84 retained DC-1 candidate cases; all 105 frozen-source controls; 71 routing checks. Earlier narrow and batch counts overlap and are not additional coverage. |
| Exact full-consumer README command | Exit 0; `final-demo.sh`, `final-demo-result.json`, `final-demo.log` under the same receipt root. Disk-written/read-back `/3` artifact; **196 steps**, **4 calls** (review → revise → review → revise); EXHAUSTED `{title: "draft+r+r", score: 2}`. Digest `sha256:7f5dd633505995ca32c18a84d03afa218bf831cf0890364a65f8a911ff3b4dd7`. Experimental driver, no public dynamic launch or paid calls. |
| Final affected recheck | **10 passed in 8.89s**, exit 0, after both evidence corrections; `edits-reviewed-result.json` and `edits-reviewed.log` under the same receipt root. Equal before/after final test SHA256 `79fdc2b83ee095b70f869d908ad3944f65fd666ab216b3d739c0410155527958`. The earlier 370-case run remains integration evidence, supplemented by this final affected check; do not report 370 at the corrected hash. |
| Final code and utility review | Code/conformity and independent document/utility review PASS as above. Earlier DC-2a/b/c reviews remain valid within their scopes. |
| Documentation verification | **71 passed in 3.51s**, exit 0, in tmux with `-q -n 16 --dist=worksteal` on `tests/test_workflow_lisp_drain_roadmap_routing.py`; 20 changed local links/anchors and `git diff --check` passed. Exact command, document hashes and results are in `dc-u-docs-result.json` and `dc-u-docs.log` under the same receipt root. This verification record was added after the check. |

The combined command is the eleven-module command in the
[plan](../plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md#finite-execution-handoff),
with `--basetemp /tmp/orc-dc2-execution-0jczbaqn/final-pytest-ijyf7x7p`.
The supplied JSON records the executable, command, exit, runtime revision and
hashes; pytest's own log supplies the 12.54s duration. This is an impacted check,
not a full-repository green result. The inherited red baseline remains red.

### DC-U Evidence Packet

**Assessment:** ordinary functions and lexical capture are demonstrated useful
composition mechanisms. Full fresh-run consumer parity is established by the
finite matrix. The four author edits show a mixed result: less internal callable
plumbing, but no general reduction in edits or repair cost. Boundary adaptation,
late failures, repeated external work and compatibility are material costs.
The present branch removes **zero production owners**; it does not establish
net implementation simplification.

| Supported evidence | Scope and interpretation |
| --- | --- |
| Complete fresh-run protocols | UI01–UI11 preserve full improve outcomes, payloads, latest candidates and failure/order behavior; US01's 72 pairs and US02–US06 preserve search values/history, ordered requests, spend and exhaustion. The typed compact control is a historical evaluated spike; public typed helper run/resume and pure CLI controls are separate. |
| Ordinary reusable functions | One unspecialized improve helper forwards active payloads opaquely and accepts ordinary hook values; source functions capture, return, store and pass callables without internal generic parameters or ProcRefs. S/P/UC and full consumers prove the mechanism, not public module reuse. |
| Existing boundary pipeline | Real compiled domain schemas, adapter/provider/command dispatch, strict captured-output validation, document/output checks and public result boundaries retain their existing owners. Neither `Value` nor a handwritten validator substitutes for the full consumer result contract. |
| Honest runnable comparison | Four edited pairs run complete expected values and leaf inputs. Typed pure `defproc`, immutable record update and single-String context are executable controls. W1/W3 remain plausible proposed improvements, not executed evidence. |

| Edit | Observed authoring and repair consequence |
| --- | --- |
| UE01 — add `origin` | Both sides change three boundary categories (schema, review argv, revision argv/result) and forward the field at both leaves. Typed internal change initializes the candidate field; the dynamic caller also reconstructs the returned field and forwards ordinary record data. The initially incomplete dynamic caller fails before dispatch; one scripted repair batch yields matching EXHAUSTED `draft+r`, score 1, origin `seed`, with review/revise calls. No dynamic edit-count win. |
| UE02 — `note` → `message` | Both sides retain real feedback/evidence contracts. The typed generic helper already forwards payloads opaquely, needing one consumer projection edit. The dynamic caller changes six normalization/input sites because it reconstructs `return__…` keys; two observed repair steps each follow a successful review. Both APPROVED evidence and EXHAUSTED value/calls agree after repair. This is adverse adapter/diagnostic evidence, not a generic-helper advantage. |
| UE03 — independent rubric capture | Review captures goal/rubric and revise captures only goal; both sides deliver `draft tidy clarity` then `draft tidy fb0:clarity`, returning EXHAUSTED `draft+r`, score 1. The typed `Brief` carrier/forwarding already exists and is retained behavior; the actual rubric declaration/consumption/caller value changes are edits. The dynamic caller still duplicates goal at closure construction. No repairs were observed; typed String context and proposed W3 narrow the unique-gain claim. |
| UE04 — extract pure helper | Both ordinary dynamic helper and existing typed pure `defproc` extract the feedback projection and preserve exactly review/revise payloads and the EXHAUSTED value. Neither requires a new boundary contract or recorded repair. Helper extraction is already available in the incumbent; it is not uniquely enabled by this candidate. |

Touched sites are semantic categories from actual source pairs, not a LOC score
or a controlled human effort measurement. `observed_repairs` describe scripted
fixture repairs, not measured author attempts. Timing remains **unmeasured**.

| Adverse diagnostic/restart evidence | Actual effects and comparison |
| --- | --- |
| UD01 — unknown name | Dynamic `dynamic_source_invalid` and typed `name_unknown` reject with source location before dispatch: zero calls on both sides. Replacing the missing name with dynamic goal/typed `brief.goal` yields identical full EXHAUSTED `draft+r`, score 1, and ordered review/revise calls, asserted in the final corrected receipt. |
| UD02 — wrong arity | Dynamic `dynamic_call_arity` occurs before the first effect (0 calls, 38 steps) or after a completed review (1 call, 92 steps), depending on the reached call. Artifact paths/call context identify the failure. Typed `procedure_arity_mismatch` catches both before execution. Removing one extra argument yields matching full value and review/revise inputs. |
| UD03 — missing field | Dynamic `dynamic_field_missing` occurs after 1 successful review (89 steps), leaving its output/state; typed `record_field_unknown` rejects before effects. A one-site repair restores the matching EXHAUSTED value and two-hook run. |
| UD04 — VM exhaustion | Budget 80 fails with `dynamic_budget_exhausted` after 1 completed review; its output remains. Raising the source budget to 1000 runs fresh review/revise and restores the typed value. This repeats the first effect; neither controller exhaustion nor a resume point is claimed. |
| UD05/UD06 — interruption and restart | The observer interrupts only after real successful review/revise leaves. Dynamic fresh restart repeats those 2 prefix calls and runs all 6 completion calls: **8 total leaf runs**, with all first-run states retained. Typed public committed-iteration resume makes **6 total calls**, reusing the 2-call committed prefix. Full final EXHAUSTED `draft+r+r+r`, score 3 agrees. UD06 preserves captured goal and uses the incumbent's actual String-input control. |

The lost static effect-summary guarantee remains an exercised typed control,
not candidate functionality. Late diagnostics preserve operation and call
context but generally report artifact paths; complete source mapping is absent.
Completed external writes are not rolled back. The two extra local leaf runs
quantify repeated work in these interruption cases only; no paid cost estimate
or general latency conclusion follows.

| Complexity owner | Actual retained / added / removed responsibility |
| --- | --- |
| Boundary declarations, type environment and contract compiler | Retained production `type_env`, normalized descriptors, contract derivation, strict transport validation, prompt/input/output and artifact-lineage machinery. Domain declarations remain on both sides. No validator or schema owner removed. |
| Typed compiler/evaluator and old targets | Retained generic specialization, ProcRef/proof plumbing, typed P5/closed admission, static effect summaries, memo/authority/resume and all old-target compatibility. Dynamic fixtures bypass internal specialization; they do not delete its production owner. |
| Experimental admission/source/evaluator | Added `program.py`, `source.py`, `evaluator.py` responsibility for dynamic values/frames/captures, source checks, runtime operations/diagnostics and per-invocation budget. `/1`, `/2`, `/3` are three admitted artifact vocabularies; older versions retain their original admission rules. |
| Leaf bridge and driver | Added `leaf_bridge.py`, explicit source-fragment assembly, registry linking and caller wire-to-domain reconstruction. Retained full compiler/startup and independent legacy run state/checkpoints for each actual leaf. This is not public imports or a second performer/state authority. |
| Consumer/test owners | Added improve/search definition fragments, typed utility leaves, four utility test modules and runnable README. Existing controls and maintained production consumers remain. Shared output-byte forwarding and reviewed upstream fixes extend/reuse existing owners. |
| Actual displacement | **Zero production owners removed.** Internal helper nominal declarations/context signatures/ProcRefs are absent in experimental source; future deletion depends on a selected migration and old-target/run disposition. No net-deletion or total-complexity win is established. |

| Missing or untested evidence | Consequence for the gate |
| --- | --- |
| Public dynamic target, imports, full source maps, inspection/readers and selected release qualification | DC-3 readiness obligations; source assembly and a successful experimental driver do not satisfy them. Shared work stays with upstream owners. |
| Migration/deletion and existing-run disposition | Needed to judge actual net production complexity and select one destination; compatibility machinery remains today. |
| Live-provider quality/cost, human author time, general performance | Not measured or allocated. Scripted leaves and pytest duration cannot establish these claims. |
| Candidate effect tracking/resume | Explicitly absent by accepted experiment scope; their observed costs require owner acceptance, not automatic restoration. Recovery/parallel/child-run expansion needs its own selected scope. |

**Proposed disposition: continue only to bounded DC-3 readiness qualification,**
following independent review. The ordinary function model warrants that next
examination; the evidence does not justify
production adoption or a claim that total complexity already fell. A bounded
revision is appropriate if the owner wants the demonstrated wire-reconstruction
or late-error costs reduced before readiness; stop retains the typed route and
qualified W3 fallback if those costs outweigh uniform composition.

The proposed successor uses the existing DC-3 checklist: settle target/artifact,
import/stdlib and old-run contracts with their current owners; name one
maintained-consumer destination; inventory credible removable machinery and
retained compatibility; select and qualify only the needed shared runtime,
public execution/inspection and boundary slice. Preserve the explicitly
non-resuming profile, current schemas and periodic upstream reuse. Write the
bounded plan and owner amendments before production edits. No paid/live calls,
parallel or child-run expansion, migration or retirement follows from this
recommendation; any such scope needs its own authorization.

**DC-U owner disposition, 2026-10-02: CONTINUE.** The user explicitly accepted
the reviewed recommendation and selected bounded **DC-3 readiness qualification**:
concrete design/plan, actual removal/compatibility inventory, one maintained
consumer destination and needed shared-runtime/public-route qualification.
Qualify the design before writing the bounded implementation plan; specific
production tasks are not preallocated by this decision. DC-3 is selected
qualification work, not implemented capability or an accepted production design.
DC-P remains pending. This selects no adoption, migration, paid/live calls,
parallel or child-run expansion; Phase 6b/7 remain unselected.

Routing effect: four prose tranches remain; DC-0/DC-1/DC-2 are complete and
bounded DC-3 qualification is selected. The existing major-project selector
reads its explicitly supplied JSON manifest; frontend selector projection reads
its own migration manifest. A scan of `workflows/library` and `state` found no
machine entry for this dynamic planset or the follow-on research roadmap.
Machine tranche-count and ready/pending/completed/blocked deltas are all **0**;
the five research units and allocations remain unchanged, and no active run
state is mutated. The human next work is the selected DC-3 design/plan
qualification, not a newly machine-selected item.

## 9. DC-3 Readiness Qualification

Entry synchronization still found integration `b7d82fa1` and source
`0f1bbc46`, already present through the integration/equivalent patch recorded
above. Shared command/provider/document performers remain upstream work; no
replacement performer is implemented here. The owner decision activates design
and bounded planning, not a claim that the production route exists.

### Native Root Contract Feasibility

At `ac9079e2143d765506f1775e895e0579ca984b54`,
`/root/impl_code_dynamic_core_search` (Luna 6 xhigh) ran two temporary probes
using existing Stage-1 module compilation, linked type environments,
`derive_prompt_guided_structured_result_contract(..., whole_value=True)` and
`validate_output_bundle(..., document_bytes=...)`. Both commands exited 0; the
coordinator inspected their scripts and raw output. No repository implementation
or external dispatch was added.

| Probe | Actual observation at targets 2.34 and 2.35 |
| --- | --- |
| `probe.py` | A root record containing a nested record and active union returns intact under `__result__` for both variants. Missing/extra nested fields, wrong scalar and inactive-variant fields refuse through the existing strict structural validator. The additional provider-context pair checks are incidental and do not select context capture for DC-3. |
| `direct-root-union.py` | A bare union also derives one root `__result__` field at JSON pointer `""`; both variants return intact. Missing required, extra and inactive-variant fields refuse. No inverse projection or caller normalizer is used. |

Scripts, exact commands, HEAD and raw output are under
`/tmp/orc-dc3-whole-value-ac9079e2/`: `COMMAND.txt`, `raw-output.txt`,
`direct-root-union.COMMAND.txt` and `direct-root-union.raw-output.txt`.
Script SHA256 values are
`a2587862105a79a4174683ec62d8f516c62a805c41e8d7f007da9617a4d72fff` and
`aa525ecc9408a270c852771fcc8474cbaa39b2e95f5190df97c49275d1edf9c7`.
An initial malformed temporary union fixture is retained as
`direct-root-union.initial-parse-error.txt`; it was corrected before the successful
run and is not evidence of a repository defect.

The generic scalar validator still converts `"7"` to integer `7`. These probes
prove direct structural result reuse, not universal strict policy, required-file
publication, actual provider execution or public dynamic support. Q1's remaining
integration obligations and Q2–Q5 remain to be implemented and qualified; typed
closed artifacts keep their existing flattened result-contract rules.

### Shared Interpreter Authority Import

Reviewed Phase 3 integration `163f286d80dc27849897cbc28fa62200f4438ba4`
(code `f9619237`) was merged as `cc896d41ec146f5a91006c914897caae4ab802b1`.
It pins each emitted bare command interpreter before typed run publication and
validates exact pin coverage/shape on read-back without observing the filesystem.
The coordinator inspected the production diff and ran fresh checks at that merge:

- Collection: 38 authority/interpreter/CLI cases.
- Nine narrow authority cases passed in 1.19s.
- All 38 affected cases passed in 6.25s with
  `pytest -q -n 16 --dist=worksteal`, including the public pure-run CLI smoke.

Exact commands, HEAD, stable before/after source hashes and raw output are in
`/tmp/orc-dc3-integration-z6_e0z2j/{collect,narrow,affected}.{json,log}`.
This qualifies the imported typed authority change, not a dynamic performer.
The moving source `0f1bbc46` is represented by equivalent integrated patch
`a780639c` (stable patch ID `acf0c682851c47a464aeef5ae2c0840b2cd262cb`); it is
not a literal ancestor. The frozen comparison remains `4b69ee00`.
Shared command/provider/document performers remain pending upstream.

### Shared Command Performer Import

Reviewed integration `fc9c57d3131ee721a12c3d87fd5c603f42a3d903` (performer
`d6d9469c`) was merged as `ddec5698d6d6bbf72e8847e050c7ee5f1f185ae8`.
Independent Sol review found no introduced import blockers; the coordinator
inspected the complete production diff. Fresh checks collected all 27 new cases,
passed those 27 in 3.43s, then passed 157 affected cases in 6.83s with
`pytest -q -n 16 --dist=worksteal`. These include actual compiled command
dispatch, captured outputs and contract/path checks. Exact commands, HEAD,
stable before/after hashes and logs are under
`/tmp/orc-dc3-integration-z6_e0z2j/command-{collect,narrow,affected}.{json,log}`.

`perform_command(node, argv, *, attempt_files, workspace_files, input_document,
timeout_sec)` performs one dispatch without reading or writing memo/state;
its result is still `(EvaluatedValue, digest)`. It expects a checked declaration
and prevalidated canonical input bytes. Attempt allocation, closure/interpreter
checks, request rendering and lifecycle remain caller responsibilities. This
import does not qualify the native strict dynamic seam or public effect execution.
Provider/prompt/document request owners remain pending shared work.

Review also reproduced an inherited flattened-contract omission: with
`Ready(n:Int) | Skipped(empty:Empty)`, the result
`{"variant":"Ready","n":7,"empty":{}}` is accepted and projects away `empty`.
Empty records have no flattened leaf, so the shared contract omits that inactive
field. This is a known limitation for the shared typed contract owner, not full
result-conformity evidence or a new regression attributed to this import. The
local reproduction is `/tmp/orc-phase3-command-performer-review.py`; the dynamic
Q1 whole-value checks must reject the inactive field. No independent replacement
performer or change to the frozen `4b69ee00` comparator was introduced.

### Reviewed Readiness Handoff

Astra Design authored proposal §9; a distinct Astra reviewer passed the final
`53f865b345ccc38fa7f0402fb158d39e8d5e0f116f04dfcf7eb1c5b1a09edf11` version.
Review removed the unsupported compiled-library import promise and made the
port/archive disposition of active spike tests explicit. Reading three source
examples and checking links are syntax/document evidence, not target 3.0 execution.

The [bounded implementation plan](../plans/2026-10-02-workflow-lisp-dynamic-core-readiness-plan.md)
was authored by Astra Planning and independently passed Sol conformity and quality
on `cdf614d1bde9fac34ef41cb10dc103ca05f054397e193bdd2df65b6f58d2f3ae`.
Its only review correction separates DC-P's external owner decision from
completion of the readiness handoff. Subsequent status/import receipts are factual
updates. Task 1 has started under Luna Implementation; Tasks 2–3 can progress
without missing performers, while the atomic core/frontend/state/direct-effect
cutover depends on Task 4's actual shared seam. Q1–Q5 remain open.

The reviewed contract names one future application destination and preserves old
targets/runs. It permits fresh branch qualification, not adoption, migration,
paid/live calls, parallel or child-run expansion. No production owner has yet
been removed by this design/plan handoff.

Coordinator handoff verification at `ddec5698`: 71 routing checks passed in
3.45s, all 27 changed/new document links resolved, and `git diff --check` passed.
Exact command and stable document hashes are retained in
`/tmp/orc-dc3-integration-z6_e0z2j/dc3-handoff-docs-result.json`; this receipt
was appended after those checks without changing their checked contracts.

### Task 1 — Exact Typed Routing

At `c1df8106`, Luna Implementation replaced the shared numeric `>= 2.35`
route predicate with exact registered typed-target selection. No target 3.0
registration or other caller change was needed. New tests reject unregistered
2.36/3.0 at real public compile/run entry without build/run roots or effects,
and check all earlier supported targets plus malformed/future versions.

The route regression failed before the change (1 failed, 2 public refusal cases
already passed). Afterwards three narrow cases passed and 73 affected cases
passed in 6.00s, including retained 2.34 and public pure 2.35 execution.
Independent Sol conformity and quality passed with no findings; the reviewer
collected the final 39-case module after a formatting-only test revision.
Coordinator fresh integration: all four new/pure-smoke cases passed in 3.56s.

Reviewed SHA256: `syntax.py`
`7570a2e8191161b2fa7fec8233acbbea71baef2e80dd6592d2df9577285832a5`;
target test `3a504d2557bfb5696986a61f51d13e60f254f9f0aa41d138640053cbeab26a4b`.
Author RED/GREEN/collection/broad logs are `/tmp/orc-dc3-target-*.log`; exact
coordinator command/HEAD/stable hashes are
`/tmp/orc-dc3-integration-z6_e0z2j/target-root.{json,log}`. Task 1 is complete;
Q1–Q5 and public dynamic availability remain pending.

### Independent Preparation And Continued Synchronization

A read-only Sol check of Task 3 traced the actual module path. Stage-1 compilation
already skips procedure bodies, so a spy on that elaborator alone is insufficient
evidence. The bounded task now explicitly owns selection before macro expansion
and declaration elaboration in `compiler.py`/`modules.py`, reusing existing graph,
export/scope and type-reference helpers. Its negative control includes an invalid
unselected declaration. Actual compiled-bundle/dynamic-source loading remains
Task 6 work if absent from the preliminary seam; no dummy loader substitutes.

Upstream `948f97b9d5b0aea921680bbbb3777e1dc2fe4b58` was imported at
`575f2de186d81614c36275087ed5637f36ee101e`. The sole change allows independent
prompt-assembly/parity preparation under the existing accepted design; provider
execution and Task 7 closeout remain dependent on their actual runtime owners.
The coordinator inspected the one-line plan delta and ran `git diff --check`;
no production source or machine selection changed, so existing code verification
remains applicable. Shared runtime availability and Q1–Q5 remain incomplete.

### Task 2 — Strict Native-Root Boundary Kernel

The coordinator assigned the dynamic-specific strict policy to the existing
output-contract/type-descriptor owners after checking the upstream worktrees
for overlap. No shared performer was independently reimplemented.
`validate_output_bundle(..., strict_transport_values=True)` uses the existing
whole-value `__result__` contract and descriptor validator for native values;
`require_int64=True` supplies the candidate's range without changing old defaults.
The experimental strict JSON decoder moved into the shared output owner and
its experiment caller imports that implementation. There is no second decoder
or inverse `return__…` converter. These APIs and this committed delta are the
reusable handoff for the upstream owner; they are not a claim of upstream adoption.

Fifteen new checks cover records, applied unions, strict scalars, optional and
nested `Value` integer bounds, Int-to-Float normalization, duplicate/nonfinite
JSON, inactive empty-record fields, path containment and captured-byte stability.
A required report is checked separately. This proves **Q1 kernel preparation**,
not atomic combined publication or direct command/provider readiness.

Luna Implementation observed seven initial failures for the absent strict option.
The initial candidate passed 254 output/runtime checks in 6.38s and 256 generated
contract/artifact checks in 14.16s. Independent Sol review required removing the
received duplicate key from the new error and retaining nested-range coverage;
the correction passed 139 affected checks in 2.76s and collected 15 final cases.
Final conformity and separate quality reviews passed. Coordinator integration
passed 17 cases in 1.53s, including a real checked command dispatch and the
experimental malformed-result publication refusal. No full-repository green
claim follows from these affected checks.

Reviewed SHA256 values:

- `output_contract.py`: `55e3517158f42c8fd364084544afb7a58bb1d81e204cef481da56419435ce585`.
- `type_descriptor.py`: `f2267ca73286ad75a2168219b06c4fa27c9c7c184dd4359b756f5a2ab647c7da`.
- Experimental `program.py`: `6169c9cad72da5081e198d287ac9bb2b833c8a1acefa39a79136fe46b19c036f`.
- New boundary tests: `7df20e8d9958896bc83e77c899ebf1d686f6a36d6bc729985e77d2b6d301b6fe`.

Author logs are `/tmp/orc-dc3-boundaries-*-20261002.txt`; the broad selectors were
`test_workflow_dynamic_boundaries`, `test_output_contract`, its `value`,
`collections`, `nested_transport` companions, `test_workflow_output_contract_integration`,
and the experimental `test_dynamic_core_evaluation` / `test_dynamic_core_boundaries`
modules. The second batch used `test_workflow_lisp_build_artifacts` and
`test_workflow_lisp_structured_results`; both used `pytest -q -n 16 --dist=worksteal`.
Exact coordinator command, HEAD `575f2de1`, stable hashes and output are in
`/tmp/orc-dc3-integration-z6_e0z2j/boundaries-root.{json,log}`.
The last upstream check still found `948f97b9` / source `0f1bbc46`.
Task 2 is complete; Task 3 can proceed independently of the missing direct seam.

### Task 4 Dependency Audit During Task 3

A finite Sol review at local `4d348937` / upstream `948f97b9` distinguished
missing integration from missing filenames. Existing memo-free owners include
`ProviderExecutor.prepare_invocation/execute`, `render_prompt_fragment_base`,
`render_typed_prompt_inputs`, `PromptComposer`, content snapshots and
`WorkspaceFiles`. The command performer dispatches once but still projects and
coerces to `EvaluatedValue`; it does not select the new strict native-root policy.
Its current real command callers are component tests, while the public evaluated
runtime remains pure-only.

Still needed from the shared owners: qualified resolved request/snapshot/attempt
assembly and strict native result/required-file validation before return (including the
registered stdout materialization path), plus external-document operand/bytes/token
transport. Merely writing supplied bytes to `inputs.json` is not that transport.
The independent upstream prompt-preparation allocation can advance these owners;
this branch will not duplicate them. Task 4 has an API inventory, not a PASS.

The coordinator applied one sequencing clarification: Task 4 qualifies actual
shared delivery with real dispatch and the existing consumer; Task 8 constructs
and verifies the second real dynamic caller before the atomic cutover integrates.
That removes the circular requirement to produce Task 8's caller before starting
it. Both real callers and the same final proofs remain required; there is no
new backend, simulated consumer, scope expansion or accepted release.
Independent Sol conformity and quality review passed this sequencing clarification.

### Shared Prompt-File Capture Import

Reviewed upstream `8430b87f6eda35c028f3beaa208b0c580f8d1c32` (source
`ec3a557b0642c84336bd2abd11bfdc79dd6869c1`) integrated at `046a8b9d`.
Prompt sources, assets and content dependencies can now return the raw digest
from the same captured bytes used for decoded text. Existing text-only APIs
retain their defaults; optional absence differs from an empty present file.
Hashes cover full raw bytes before newline normalization or prompt truncation.

Independent Sol review found one stale test: the unreadable-dependency case
intercepted `Path.read_text`, bypassed by the new raw reader. The coordinator
reproduced its failure at the provider-preparation spy in an exact detached
`ec3a557b` checkout (1 failed in 2.30s), then moved the injection to `Path.open`.
All publication/category/operation/no-preparation assertions remain unchanged.
This fixes fault injection, not a production validation bypass.
Independent Sol conformity and quality rechecks passed the integrated code and
test correction with no remaining findings.

At `046a8b9d` plus that test correction, six new cases collected, eight narrow
cases passed in 1.27s, and 242 affected cases passed in 6.21s. Affected selectors:
`test_workflow_evaluated_prompt_files`, `test_prompt_dependency_content_snapshot`,
`test_prompt_contract_injection`, `test_workflow_lisp_provider_prompt_dependencies`
and its `_e2e` module. The latter exercises the public path without paid calls.
Exact commands, stable hashes and raw output are in
`/tmp/orc-dc3-integration-z6_e0z2j/prompt-{collect,narrow,affected}.{json,log}`.
The disposable verification checkout was removed after use. Provider assembly,
strict dynamic publication and Task 4/Q3 remain pending; the frozen comparison
revision is unchanged.

### Task 3 — Selective Source Declarations

Integrated at `17a69df0`. The private source-only entry reuses the existing graph,
scopes and Stage-1 pipeline, selecting type/schema/prompt dependencies before
macro collection or full declaration elaboration. The existing single-form
elaborator owns dependency syntax. Tests import `std/improve` schemas without its
typed helper and exclude an invalid unselected declaration. Selected executable
declarations and indirect `ProcRef` dependencies refuse with the import chain.

Luna's initial implementation passed six cases but exceeded its bounded batch;
Sol Revision removed the duplicate declaration parser and completed coverage.
Independent Sol review and coordinator inspection found and corrected private
self-qualified dependencies, alias visibility widening and the untraced root-
inference read. Each correction has a behavioral regression. One proposed alias-
slash positive also failed the existing baseline; the final test uses existing
alias-dot/canonical syntax and does not count that fixture error as a product bug.
Final conformity and subsequent quality review passed without findings.

Fresh evidence: 23 new cases collected and passed; 336 affected cases passed in
14.84s, covering modules, definitions, improve, build/artifact path safety,
retained targets and public CLI. Coordinator verification passed all 24 selected
cases in 2.61s with stable hashes. Commands, hashes and raw output:
`/tmp/orc-dc3-modules-revision-receipt-02.json` and corresponding logs;
`/tmp/orc-dc3-integration-z6_e0z2j/modules-root.{json,log}`. The affected command
uses `pytest -q -n 16 --dist=worksteal`; no full-repository green claim follows.

Q2 is **partial**: source selection preserves canonical ownership, complete spans,
prompt/path bases and consistent read snapshots. Public target 3.0, source-free
execution and compiled-bundle refusal through the future loader remain Task 6.
At this boundary upstream still points to reviewed `8430b87f` / source `0f1bbc46`;
all reviewed applicable delivery is integrated. Task 4 still needs shared resolved
request/attempt assembly, strict native result and required-file validation before
return, and external document transport. State publication remains caller-owned. The dependent Tasks 5–8 cutover cannot start under
the reviewed sequencing; no duplicate performer or implicit adoption is selected.


### Shared Command/Provider Runtime Import

The coordinator rechecked upstream on 2026-10-03. Reviewed integration
`b5b07cebb47892bd3fef3c862cab13263b39059b` merged at
`a672985d340064beb9000299caff8c2a3284a3e0`. During verification, upstream delivered
portable provider implementation `7e2282a428d8b1e75dd128823df1d669fbca4283`
(source `5af1888a5877dfc0346ed73209a275c521bc43b6`) and reviewed plan receipt
`21b78d16a250c796475bfe6e9b24544ea9ea5875`; both integrated at
`103dc8cd14907202438673d80812c662e167cfd5`. Independent Sol conformity and
quality review passed both imports. The R12 control source remains `0f1bbc46`,
represented by the equivalent integrated patch recorded above. No dirty upstream
work was imported. Frozen DC-2 comparator
`4b69ee00d4c6204dd816b4caa02b9fee1dae25e8` and comparison sources are unchanged.

This imports the reviewed command runtime/R12 renderer (`304b3bbf`), pure prompt
assembly (`da94c8c8`), provider IO carriage/activation (`d795200e` / `04733927`)
and portable provider performer/lifecycle (`7e2282a4`). Public target 2.35 now
runs pure programs, commands and portable composed providers. Provider evidence
uses controlled local process transport through the real executor; it is not a
paid call or later live-vendor qualification. Commands retain local C4 checks and
pinned interpreter launch; providers bind captured C6 reads and C9 operands and
validate required output files. Public resume, path run-reference dispatch,
complete profile readers and combined typed Tasks 6/7/full release acceptance
remain unfinished. The accepted `resume_request` design is not public-resume
implementation evidence.

Fresh coordinator verification:

| Import/check | Observed result and limit |
| --- | --- |
| Initial `b5b07ceb` collection/narrow | 153 cases collected; 44 passed in 5.19s, including public command, prompt parity/capture and dynamic preparation controls |
| Initial affected suite | 1,008 passed and two failed in 20.99s; this result remains historical and is not rewritten as PASS |
| Baseline/correction | Both failures reproduced at exact upstream `b5b07ceb`: obsolete whole-object identity assertions in `test_workflow_lisp_closed_preparation_integrity`. The test-only correction preserves the semantic-key/shared-prepared-body checks and explicitly rejects repeated comparison/elaboration. Independent Sol conformity/quality passed; coordinator passed the two corrected cases plus the dependency-chain guard: three in 1.35s |
| Provider collection/narrow | 40 new cases collected in 3.24s; 41 narrow cases passed in 30.02s, including public provider/command processes and complete request parity |
| Final affected suite | 644 passed in 18.79s across 41 explicit modules: all evaluated modules, dynamic routing/root/module preparation, seven experimental dynamic modules and the complete corrected 22-case preparation module. This is affected-scope integration evidence, not a full-repository green claim |

Exact commands, source snapshots, stable before/after hashes and raw output are
in `/tmp/orc-dc3-upstream-20261003-zqov7cv6/`: `config.json`,
`provider-config.json`, and `{collect,narrow,affected,correction,provider-collect,provider-narrow,provider-affected}.{json,log}`.
Baseline reproduction and correction evidence are under
`/tmp/orc-dc3-upstream-test-revision-20261003`; the disposable baseline worktree
was removed after verification. Broad checks use `pytest -q -n 16 --dist=worksteal`
in tmux. These verification receipts preceded the factual documentation update.

#### Actual Shared API Handoff And Remaining Task 4 Gaps

| Delivered owner/API | Actual input/result ownership and dynamic consequence |
| --- | --- |
| `commands.py::render_command_argv(node, operands)` | Operands are `Sequence[EvaluatedValue]`; renders checked transport plans to string tokens. `inline_command_document` serializes checked certified operands to canonical JSON |
| `commands.py::perform_command(node, argv, *, attempt_files, workspace_files, input_document=None, timeout_sec=None)` | One real dispatch with caller-owned files and declaration contracts; returns `(EvaluatedValue, digest)`. No memo access inside the performer. Optional canonical bytes can be written to exclusive `inputs.json` by this low-level hook, but public runtime does not supply that hook or the external document path token |
| `prompts.py::assemble_provider_prompt(checked_node, evaluated_operands, *, source_text, dependency_snapshot, result_path)` | Pure assembly from typed evaluated operands and already captured inputs; reuses existing input/dependency/output-contract rendering |
| `providers.py::resolve_provider_io(node, operands, *, workspace, reader)` / `resolve_provider_input(node, operands, *, workspace, reader, result_path)` | Typed evaluated operands and the checked physical reader select source/dependency bytes; the resolved request contains prompt, policy, input digest parts and required output-file rows |
| `providers.py::perform_provider(node, resolved, identity, *, executor, attempt_files, workspace_files, result_path)` | One preparation/dispatch with exclusive prompt/stream/result evidence. Validates required output files, then returns the shared projected typed result/digest. Runtime owns synchronized attempts, memo commits/reuse and terminal publication |
| `commands.py::validate_effect_result(node, result_bytes, result_path, workspace_files)` | Common command/provider captured-byte validator and typed projection/coercion; returns `(EvaluatedValue, digest, artifacts)`. It does not expose the existing `strict_transport_values=True` opt-in or a native whole-value result |

Task 4 inventory/registration is complete; **Task 4 is not PASS**. The two
remaining shared-owner slices are concrete:

- **Native resolved-value/strict-result seam:** shared request rendering must
  accept resolved native boundary values rather than `EvaluatedValue` operands.
  The existing whole-value/strict captured-byte kernel from Task 2 must pass
  through shared request/performer owners, including
  required-file validation before return, without constructing typed values or
  reconstructing flattened output. The typed performer currently retains its
  default projection policy; extra-field projection in provider tests is not
  strict dynamic boundary evidence. Route this bounded extraction to its owner
  under the existing transfer protocol; do not add a second executor or fabricate
  typed program/memo state.
- **External Task 12 document transport:** `evaluated/inputs.py` and
  `tests/test_workflow_evaluated_input_documents.py` are not delivered. Closed
  document nodes still require certified adapters and empty argv; public runtime
  appends canonical inline JSON. External-tool `:argv` plus `:inputs` needs
  once-only operands, attempt-owned canonical bytes and the declared path token.
  The low-level file-writing hook alone does not deliver that public protocol.

Tasks 5–8 have not started under the reviewed atomic-cutover sequencing. Q1–Q5,
public dynamic target 3.0 and DC-P remain unqualified; no adoption, application
migration or repinning follows from this synchronization.


### Shared Typed Resume/Invalidation Import

The coordinator rechecked and imported reviewed upstream
`e17bd61faf1ea7a2b255e1b3dc3edb2396b455f4` at
`d3b68c0a2e2665684c81759abcc270c89a91ee81` on 2026-10-04, from development
baseline `12f1e8ab5cac624d212fe9aac6ea4d40449ca480`. This includes typed Task 8
request/public-resume preflight (`29c52006`), replay/retry (`6d3a6494`), public
invalidation and acceptance (`0a937167`), completion receipt (`12f6c325`) and the
retained-descriptor authority/writer correction (`e17bd61f`). Independent Sol
conformity/quality review passed the import, including two mechanical test
resolutions that preserve dynamic exact-target routing and prepared-body reuse.
No dirty upstream work was imported. The frozen DC-2 comparator remains
`4b69ee00d4c6204dd816b4caa02b9fee1dae25e8`.

Ordinary public target-2.35 resume now rebuilds the persisted request in memory,
compares the semantic program before bound inputs, then checks/replays the active
committed prefix before mutable continuation. Completed commits are reused
without redispatch; pending command/provider retries retain closure and captured
input checks. Historical missing rebuild recipes refuse with
`resume_request_missing`; malformed present recipes are `memo_inconsistent`.
`--force-restart` remains unavailable. Public
`invalidate <run_id> <identity> [--state-dir <runs-root>]` uses checked stored
authority under the writer lock, without rebuilding sources or dispatching, to
append one active suffix invalidation. The next ordinary resume reruns that
suffix. Inactive identities, historical profiles and suffixes containing a
coordinator refuse. The descriptor correction keeps publication checks attached
to retained directory/file authority rather than reopening an unchecked path.

Fresh coordinator verification:

| Check | Observed result and limit |
| --- | --- |
| New-case collection | 142 cases collected in 3.16s |
| Narrow integration | 112 passed in 14.92s, including public compile/run/resume/invalidate/resume, reserved descriptor controls, and dynamic routing/preparation boundaries |
| Affected integration | 936 passed and 55 failed in 59.09s across 991 cases; this run remains RED |
| Exact pre-import baseline | All 55 failed selectors reproduced in `tests/test_prompt_resume_child.py` at `12f1e8ab`: 55 failed and two passed in 10.16s at the pinned executable version-probe gate. The failed-selector comparison found no new failures; it does not turn the affected run green |

Exact commands, hashes, raw output and the failed-selector disposition are in
`/tmp/orc-dc3-resume-upstream-20261004/`: `config.json`,
`{collect,narrow,affected,legacy-base}.{json,log}` and
`failure-disposition.json`. Broad verification uses
`pytest -q -n 16 --dist=worksteal` in tmux. These overlapping checks are not summed
and do not establish a full-repository PASS. The drafting guide points to the
real public CLI smoke selector in
`tests/test_workflow_evaluated_invalidate_smoke.py`; provider evidence remains
controlled local transport, not paid/live-vendor qualification.

Typed Task 8 is complete within this delivery scope. Path run-reference dispatch,
complete profile readers, external Task 12 input-document bytes/path-token
transport, later command/provider campaigns and full Phase 3 acceptance remain
pending. Dynamic recovery remains unsupported and the proposed dynamic profile
is fresh-run only. Under existing Task 4 ownership, native resolved-value and
strict-result adaptation in the three existing performer owners is authorized
and in progress; it is not yet delivered or qualified by this receipt. External
Task 12 is still missing, **Task 4 is not PASS**, and dynamic Tasks 5–8 remain
unstarted. Q1–Q5, DC-P, public dynamic target 3.0, adoption and maintained
application migration remain unqualified.


### Shared Native Performer Sub-Slice

Under the existing Task 4 ownership transfer, the bounded native adaptation of
`evaluated/{commands,prompts,providers}.py` is independently Sol-reviewed PASS.
It builds on the strict whole-root boundary kernel at `4d348937`, retaining the
existing performer/reader/validator owners. Integration commit:
`ee4ae46bebaa7c17536bb7cf5a2ab8fab5c463e3`. Native qualification uses the
imported `e17bd61f` baseline; the frozen comparator is unchanged.

The existing command/provider performers and captured-byte result validator
accept `native_result=True`. Before dispatch this mode requires a single
required `__result__` field at the root pointer with a strictly transportable
descriptor. It validates captured bytes with the strict whole-value policy and
returns the native root and digest without typed projection or coercion. The
result is read once through caller-owned attempt files. Provider required-file
validation and artifact-name overlap checks complete before returning. Typed
defaults retain their prior projected result behavior.

Private plain validated-value provider preparation reuses captured source and
dependency reads and pure prompt assembly. `WorkflowIOReader` is a path-only
carrier suitable for the defining module's owner; an alternate reader is not
required. The dynamic caller must strictly validate inputs before using this
preparation or `render_variable_value` for argv. No separate argv template
extraction, second executor, fake typed values or typed memo is introduced.

Coordinator affected verification of the reviewed result/preparation sub-slice,
before the final inline serialization extraction:
**867 passed in 45.66s**, with stable before/after hashes, across the explicit
53-module selection in
`/tmp/orc-dc3-native-seam-20261003/coordinator-affected.{json,log}`. The command
uses `pytest -q -n 16 --dist=worksteal` in tmux. This is affected-scope evidence,
not a full-repository claim; the preceding upstream import's 55 baseline failures
remain recorded as RED above.

The final extraction delivers
`commands.py::_serialize_inline_command_document(fields: Sequence[tuple[str, Any]]) -> bytes`
for ordered, already-validated plain fields. The typed wrapper preserves
absent-document, slot-offset and operand-count rules. Sol incremental conformity
and quality review passed, retaining the prior review. Twenty new module cases
collected; three document cases passed, and the native module plus typed command
selectors passed 44 cases in 9.21s (`focused.log`). Final coordinator verification
passed **870 cases in 83.94s** across the same explicit 53-module selection,
including public recovery smoke, typed/dynamic boundaries and experimental
consumers. Before/after hashes are stable and match commit `ee4ae46b` contents;
exact commands/hashes/output are in
`/tmp/orc-dc3-native-seam-20261003/coordinator-final.{json,log}`. The earlier 867
result remains a separate pre-extraction receipt; these overlapping counts are
not summed.

The real-dispatch document check uses the existing `input_document` byte
primitive and a manually supplied path. It qualifies that primitive, not authored
Task 12 grammar, absent/empty semantics or automatic document path-token append.
The serialization kernel is certified inline transport; external `inputs.json`
transport is still missing. **Task 4 is not PASS** until that actual Task 12
delivery and its integrated qualification complete. Task 8 owns the actual
dynamic caller, strict input checks, imported-asset module ownership and native publication; those are
future cutover obligations, not circular prerequisites to Task 4's shared-seam
qualification. Tasks 5–8 remain unstarted, dynamic recovery is unsupported, and
Q1–Q5/DC-P/public target/adoption/migration remain unqualified.

The final clean upstream cutoff `4ca7a0fbf721c392753ae8745db45aa82a6b4427`
is integrated at `eb9c9e30e05c54e425082d15ad1147171dbc094e`, extending
`e17bd61f` with persisted evaluated run-reference root/resume-selection checks.
Independent Sol review found that standard `/dev/stdin`, `/dev/stdout` and
`/dev/stderr` aliases were still accepted as durable paths. The merge corrects
this in the shared locator validator, rejecting those aliases and `/dev/fd`,
including descendants, without path IO; the existing malformed-header test
covers all six additional spellings. This reusable correction is the two-file
delta from `4ca7a0fb` to `eb9c9e30` in `evaluated/authority.py` and
`tests/test_workflow_evaluated_run_ref_root.py`. It is not yet applied to the
upstream branch.

The regression failed before the correction and passed after it; independent
conformity and quality review then passed. Eight cases collected and passed
in 14.04s; the final 54-module affected suite passed **878 cases in 57.40s**,
with stable hashes matching the integrated code. Exact commands and output are
in `/tmp/orc-dc3-native-seam-20261003/cutoff-corrected-{collect,narrow,affected}.{json,log}`;
the causal check is `alias-{red,green}.log` in the same directory. These checks
supersede the earlier 878-case pre-correction run for this import and are not
summed with overlapping native checks. No Task 9 completion, Task 12 delivery
or new dynamic gate follows. Tasks 5–8 still await Task 12 and its integrated
qualification; no shared document transport was independently reimplemented.

### Shared Children/Readers/Input-Document Import

Current synchronization, 2026-10-04: reviewed shared Phase 3 delivery through
`a024397b` is merged onto dynamic head `bc171620`; its frozen merge tree is
`e0ac189d`. This moving runtime import leaves the frozen typed comparator
`4b69ee00d4c6204dd816b4caa02b9fee1dae25e8` and earlier experiment results unchanged.
The shared merge plus native adapter is committed at `866dcd99`; the initial
280-case receipt below remains separate from final combined qualification.

The retained [Phase 3 plan](../plans/2026-10-02-workflow-lisp-evaluated-execution-phase-3-plan.md#task-9-run-reference-coordinator-and-evaluated-children)
has reviewed completion receipts for Task 9 path children/coordinators, Task 10
derived report/dashboard views and Task 11 monitor/probe/watchdog readers.
Those receipts retain their qualified broad failures and controlled transport
limits. Shared Task 12 deliveries `4bcf5424`, `5bdb2497` and `a024397b` add authored
external `:argv` plus `:inputs`, checked recursive contracts and operand order,
canonical document bytes, exclusive attempt-owned `inputs.json` publication and
one workspace-relative path token. Absent versus empty documents and certified
inline transport remain distinct. Committed reuse neither reads nor regenerates
the old generated file. The actual split owners are
[command grammar](../../tests/test_workflow_lisp_command_input_documents.py),
[checked closed documents](../../tests/test_workflow_lisp_closed_input_documents.py),
[runtime contracts](../../tests/test_workflow_evaluated_input_document_contracts.py)
and [attempt transport](../../tests/test_workflow_evaluated_input_document_attempts.py).

Independent Sol static review passed on frozen merge tree `e0ac189d`; fresh
coordinator narrow verification passed **280 cases in 48.37s**. This qualifies the
imported typed selection, not the dynamic document caller, complete Phase 3 or
live providers. Upstream subsequently delivered public input-document/replay
checks at `ebaf78ed` and its Task 12 closeout at `98b3f3d9`, integrated separately
at `970ac933`. This test/document-only import leaves runtime code unchanged.
Fresh collection found 29 cases; all 29 passed in 118.92s, exit 0, including
public compile/run/replay. Exact commands and source hashes are in
`/dev/shm/orc-dc3-20261004-import-task12-closeout/`. These additional checks are
separate from the earlier campaign; full Phase 3 qualification remains open.

The shared native document seam is qualified at `866dcd99`. Existing
`inputs.py::_prepare_command_document_fields` accepts plain values/descriptors
through the shared validators, `commands.py::_serialize_command_document`
preserves canonical external versus signature-ordered certified bytes, and
`commands.py::_command_document_argv` uses caller-owned attempt files for the
external path token. Their typed wrappers retain the actual typed consumers;
no typed node/value, fake memo or parallel performer is required for the native
request. Independent Sol final conformity and quality review passed.

Fresh root verification collected **2554 cases** and passed **2553 with one
expected failure in 223.11s**, exit 0, using `pytest -q -n 16 --dist=worksteal` in
tmux. All source hashes were unchanged and verified against current source.
Exact selections, commands, before/after hashes and outputs are in
`/dev/shm/orc-dc3-20261004-combined/{collect,affected}.{json,log}`. This affected
campaign includes the real-dispatch native seam, retained typed document
consumers, public recovery/child/reader checks and experimental controls; it is
not full-repository or live-provider evidence. Its counts are not summed with
the overlapping 280-case import receipt.

**Readiness Task 4 PASS** releases the atomic Tasks 5–8 cutover. Task 5 is selected
next, not implemented, followed by Task 9's readiness evidence. Task 8 still owns
the actual dynamic caller, strict boundary inputs, imported asset ownership and
publication. Public `3.0` remains unregistered, Q1–Q5 remain open and DC-P has not
adopted the candidate; no maintained application migration or paid/live campaign
is claimed.

### Pure Core Cutover And Phase 3 Totality Import

On 2026-10-04 the atomic Tasks 5–8 work moved to
`feat/orc-dynamic-core-cutover`; `design/orc-dynamic-core-evaluation` stays at
`3a7f8efd` until that whole unit is qualified. Pure program admission is reviewed
at `5388ccca`; the iterative evaluator move is reviewed at `a1eced06`. Existing
experiment consumers temporarily depend on removed owners inside this isolated
cutover; they must receive the planned replacements before integration.

The pure evaluator applies declared workflow defaults and boundary validation,
uses one invocation budget, preserves frozen ordinary closures and uses persisted
source maps. Its shared validator opts into redacted runtime map-key diagnostics;
old callers retain their previous policy. Independent conformity and quality
reviews passed after corrections to diagnostic provenance, literal failure reasons
and exception-chain redaction. Final pure collection/execution: **57/57 PASS in
1.19s**. Before the last diagnostic-only changes, the shared-owner affected run
collected and passed **483 cases in 7.61s**, with unchanged source hashes. These
overlapping counts are not additive. Logs and source freezes are under
`/dev/shm/orc-dc3-task5-evaluator/` and
`/dev/shm/orc-dc3-task5-evaluator-affected/`.

The next upstream check found reviewed Phase 3 Task 13A at `93a33ae2`: public
totality checks and bounded typed composition repairs. Its six committed owners
and ordered independent review receipts matched their recorded hashes. It is
merged at `ead7716f`. Fresh combined collection/execution passed **546/546 cases
in 128.98s**, exit 0, including the imported public matrix, dynamic declaration
selection/core/boundary/performer checks and retained target routing. All 517
runtime/test hashes were unchanged. Exact commands, selectors and hashes are in
`/dev/shm/orc-dc3-import-13a/{collect,affected}.{json,log}`. This completes that
import, not Phase 3 Tasks 13B–D or the remaining phase qualification.

**Task 5 remains in progress:** shared static effect admission is next. The
public dynamic frontend, fresh-run authority, direct effects and complete
replacement consumers remain Tasks 6–8; Q1–Q5/DC-P remain open. Neither the pure
core nor this upstream import establishes a runnable public dynamic target.

### Task 5 Static Effect Admission Gate

`982d5463` completes the reviewed core/admission handoff on the isolated cutover
branch. Declaration checks now have two real callers: the existing typed checker
retains its value/site/P5 checks and flattened result contract, while dynamic
admission independently checks module bindings, native root contracts, all
effect operands and imported prompt provenance. All included bodies are checked.
Both actual certified command lanes remain: raw argv without a document, and
the declared document protocol. Reserved primitive type names keep their meaning;
explicit imported/local type associations remain supported.

Independent conformity PASS preceded quality APPROVED. The author collected
256 changed-test cases and passed 328 focused cases in 7.00s. Fresh coordinator
verification collected and passed **1484 cases in 145.22s**, exit 0, across 29
modules, including real public typed execution. All 540 runtime/test hashes were
unchanged. Evidence is in `/dev/shm/orc-dc3-effect-admission-affected/`; the exact
eight-file source freeze is `/dev/shm/dc3-effect-admission-code.sha256`. Counts
overlap and are not additive. The declaration-first check may change which of
multiple simultaneous invalid-fill errors is reported first; no valid-program
behavior or governing diagnostic guarantee changes.

The upstream check before this handoff still found `93a33ae2`, already imported.
Task 6 source/build/CLI work is selected. Effect execution, fresh-run authority,
replacement experiment consumers and Q1–Q5/DC-P remain pending; this admission
gate creates no runnable public dynamic target or independently releasable cut.


### Task 6A Source And Build Gate

`7407e518` adds reviewed direct dynamic source lowering and closed builds on
`feat/orc-dynamic-core-cutover`. Ordinary module imports, untyped helpers and
inferred captures link through the existing module graph; selected old-target
boundary declarations retain their owners. Declared workflow inputs/defaults and
results remain schema boundaries. Persisted expression maps support source-free
pure execution and diagnostics. Builds reuse existing requests, manifests and
immutable source/configuration traces, with descriptor-rooted publication and
read-back. The old experimental source compiler is removed inside the atomic cut.

Independent conformity PASS preceded quality APPROVED after fixing Int64 argv
literal admission and reserved workflow names. The affected run also caught a
legacy artifact-byte regression from serializing an absent budget; the existing
omit-if-absent metadata corrected it without changing the golden test. Final
source collection passed **37 cases**; focused verification passed **217 cases**.
Fresh coordinator collection/execution passed **876/876 cases in 39.86s**, exit 0,
across 22 affected modules, including retained public CLI routes. All 535
runtime/test hashes stayed unchanged. Exact selectors, commands, outputs and the
12-file reviewed freeze are in `/dev/shm/orc-dc3-frontend-a-final/`; the initial
compatibility failure is retained in `/dev/shm/orc-dc3-frontend-a-affected/`.
Counts overlap and are not additive.

The upstream check still found `93a33ae2`, already imported. Task 6B public
compile/dry-run wiring is selected. Target `3.0` is recognized by the internal
source/build route; public compile/run currently refuse before typed or legacy
fallback. Fresh-run authority and direct effects remain Tasks 7–8, so this is
not a public runnable candidate or full Q2/Q1–Q5 completion. The stable evaluation
branch remains at `3a7f8efd`; DC-P and application migration remain unselected.


### Task 6B Public Compile And Dry-Run Gate

`dbcda91d` adds exact target-3.0 public compile and nonexecuting dry-run on the
isolated cutover branch. Compile publishes the checked dynamic artifact and
supports machine diagnostics/source-map export. Dry-run uses the existing
strict entry/default/path validator and command/provider binding checks without
evaluating a body or allocating a run/attempt. Explicit CLI options are recorded
separately from retained parser defaults; direct service options also refuse
unsupported requests before publication. JSON input files retain their logical
types, while CLI text overrides use declared schemas. The existing result
carrier now preserves native scalars; actual dynamic terminal results await
Task 7's fresh authority.

Independent conformity PASS preceded quality APPROVED after closing the compile
service's unsupported-option omission. The broad check initially found 23
failures: 22 mocked-run cases supplied incomplete source headers, and one parity
case observed a compiler call now preceded by source refusal. Exact baseline
`100bf66f` passed all 85 cases in those three modules. The stub headers were made
valid without changing behavior assertions. Full CLI/LSP failed-compilation
capture and nonempty diagnostic parity remain tested using a valid header and a
real semantic error; a separate early-read case proves normalized diagnostic
parity and no backend/state/publication. `fe1a6bf8` records the independently
reviewed design boundary; no configuration/import loading or fabricated capture
was added to the early refusal.

Final revision verification passed **151 cases in 5.18s**, with **101 collected**
across the two added/extended diagnostic modules. Coordinator final collection
and execution passed **724/724 cases in 30.46s**, exit 0, across 26 affected
modules. All 540 runtime/test hashes remained unchanged. Exact commands,
selectors, outputs and the ten-file reviewed freeze are in
`/dev/shm/orc-dc3-frontend-b-final/`; initial failures and baseline controls are in
`/dev/shm/orc-dc3-frontend-b-affected/` and
`/dev/shm/orc-dc3-frontend-b-baseline/`. The disposable baseline worktree was
removed after verification. Overlapping counts are not additive.

The next upstream fetch still found reviewed `93a33ae2` and main `be327102`;
there was no new shared delivery to import. Task 7 fresh authority and readers
is selected. Public runs still refuse `dynamic_fresh_run_unsupported` before
publication until that owner lands. Direct effects/replacement consumers remain
Task 8 and full Q1–Q5/DC-P remain open. This branch qualification does not adopt
the profile or migrate the maintained search consumer.

### Task 7A Fresh Authority And Pure Run Gate

`9ad5059e` connects the candidate public run route to real source-free pure
evaluation. Before evaluation, the fresh owner publishes the checked program,
immutable header and authoritative initial state under existing workspace/writer
locks. Exact schemas, pins, source references, ordered effect rows and atomic
transitions are checked by one dynamic state owner. Native `0`, `false` and
`null` results survive terminal publication and the public result carrier.
State-write/allocation failure stops the writer; collisions do not adopt earlier
files. Local effect-row tests qualify those transitions, not command/provider
dispatch.

Read-only profile selection precedes resume/invalidation locks and legacy
`RunState` conversion. Dynamic runs refuse recovery with the declared diagnostic
codes and fresh-run/repeated-work guidance. Visible dynamic artifact markers
also prevent a mixed header from reaching typed recovery. Existing state-only
legacy repair remains with its established loader. The new validated view uses
writer-lock liveness, not an invented heartbeat, to distinguish interruption.

The first 26-module check collected 883 cases and recorded **2 failed, 881
passed in 32.46s**. Both failures passed on exact baseline `e60c6a99`: **2 passed
in 2.42s**. The revision preserves legacy repair and profile diagnostics without
changing their assertions. Independent conformity review additionally reproduced
a mixed-authority write, runtime-key disclosure in stored-value diagnostics, and
a rejection-code/guidance mismatch; all four findings were corrected using the
existing selection, validation and diagnostic owners.

Final narrow verification passed **175 cases in 10.44s**, including 172 dynamic
cases and three retained compatibility cases; **172 dynamic cases were
collected**. Independent recheck passed **12 cases in 2.60s**, followed by
conformity PASS and quality APPROVED. Coordinator collection and final execution
passed **893/893 cases in 33.22s**, exit 0, across 26 modules, with all 542
runtime/test hashes unchanged before/after and at integration. Evidence is in
`/dev/shm/orc-dc3-fresh-state-final/`, the initial failure packet in
`/dev/shm/orc-dc3-fresh-state-affected/`, and the baseline log in
`/dev/shm/dc3-7a-baseline.log`. The ten-file author freezes are
`/dev/shm/orc-dc3-task7a-freeze.json` and
`/dev/shm/orc-dc3-task7a-revision-freeze.json`. Overlapping counts are not additive;
the clean disposable baseline worktree was removed after verification.

The subsequent fetch still found upstream `93a33ae2` and main `be327102`.
Task 7B public report/dashboard/monitor/probe/watcher integration is selected.
Reached effects currently fail explicitly as `dynamic_effect_unsupported` and
publish a failed terminal; actual command/provider dispatch remains Task 8.
Task 9 owns the external-kill campaign, full Q1–Q5 and DC-P handoff. The stable
evaluation branch remains at `3a7f8efd` until the atomic cutover is qualified;
this receipt does not authorize adoption or application migration.


### Task 7B Public Readers Gate

`2b080244` qualifies profile-aware public report/dashboard/monitor/probe/watcher
readers on the isolated cutover branch. The strict profile owner validates
program/header/state pins before projection; missing, corrupt or mixed dynamic
authority fails closed. Report JSON/Markdown, dashboard responses,
`monitor --once --dry-run` and a probe subprocess inspect real pure public runs
after source/input deletion, preserving native `0`, `false`, `null` and bound
inputs. A source-free pure failure is also observed. Reached effect rows preserve
ordinal, definition/location, error, explicit result and stdout/stderr paths;
these rows are local state-owner fixtures, not actual effect dispatch.

Writer-lock liveness distinguishes active and interrupted runs without a
heartbeat or invented future graph. Dashboard exposes `resumable: false`; actual
action boundaries and a controlled isolated watcher refuse dynamic recovery.
Terminal/interrupted/corrupt roots trigger no automatic resume/restart, and an
active writer is observed without action. Recursive directory/file snapshots,
including symlink identity, establish read-only behavior around public readers
and refusals. Watcher transport/provider tools are controlled local fixtures;
no notification or live provider is sent.

The initial 20-module aggregate collected 438 cases and recorded **12 failed,
425 passed, one expected failure in 144.15s**. Exact baseline `478a2f1d` collected
416 cases across 19 modules and recorded **3 failed, 412 passed, one expected
failure in 97.62s**: the three retained `StateManager` authority errors were
pre-existing and are corrected here too. The other initial failures were two
legacy scanner symlink diagnostics and seven retained watcher deadline
regressions. Revisions corrected all without editing retained tests or their
deadlines. Independent conformity review also closed non-object typed-header
ownership and preserved `DynamicStateError` for actual dynamic markers. The
final header check recorded **1 failed, 1 passed in 5.69s**, then **2 passed in
5.67s**; the new reader module collected **29 cases**.

Independent Sol conformity PASS preceded separate quality APPROVED on all 14
matching author hashes; the narrow review passed **4 cases in 12.76s**. The
canonical coordinator final collection/execution covered 25 modules: **719
collected, 718 passed, one expected failure in 134.33s**, exit 0, using
`-q -n 16 --dist=worksteal` in tmux. All 543 source/test/script hashes stayed
unchanged; the coordinator inspected all 14 diffs and verified those hashes at
`2b080244`. Exact selectors, commands, outputs and reviewed-file evidence are in
`/dev/shm/orc-dc3-readers-final2/`; the author freeze is
`/dev/shm/orc-dc3-task7b-revision-freeze.json`. Initial and baseline packets are
`/dev/shm/orc-dc3-readers-affected/` and `/dev/shm/orc-dc3-readers-baseline/`. The
clean baseline worktree was removed. The earlier 717-case final run preceded the
last patch; the final2 packet above is canonical. Overlapping counts are not
additive.

The post-commit fetch still found Phase 3 `93a33ae2` and main `be327102`, with no
new shared delivery; only shared Task 13A is imported and full Phase 3 remains
unfinished. Task 7 is complete; Task 8A direct command integration is selected
and in progress. Actual command/provider effects remain Task 8; the external-kill
campaign and full Q1–Q5/DC-P handoff remain Task 9. The stable evaluation branch
stays at `3a7f8efd` until the complete Tasks 5–8 unit passes, and frozen DC-2
`4b69ee00d4c6204dd816b4caa02b9fee1dae25e8` remains unchanged. No adoption,
migration or live/paid calls are authorized by this receipt.


### Task 8A Direct Command Gate

`2153279e` qualifies real direct command effects through the public service/CLI
on the isolated target-3.0 candidate branch. Dynamic evaluation calls the shared
native strict performer for external argv, certified inline and external input
documents, preserving captured bytes and absent-versus-empty document behavior.
Pinned interpreter and closure evidence are checked before and after execution;
operands run once in written order under one invocation budget. No leaf workflow
or `WorkflowExecutor` is constructed. Attempt file descriptors remain owned
through publication and close on `BaseException`.

The strict `Int64` check is opt-in and preserves retained typed defaults. Runtime
keys/raw values are redacted from diagnostic output, while source, call, ordinal,
steps, safe violation kind and static expected input/output contracts remain
inspectable. Task 8A's **17 command and 26 performer cases** cover the actual
command path; they do not qualify dynamic providers or imported consumer assets.

The first two public command checks were RED specifically because effects were
unsupported. The first command revision passed **14 cases in 3.25s**; related
checks passed **200 in 10.08s**. The initial coordinator aggregate passed **630
cases in 36.58s**. Independent review then found three P2 issues: map input-key
disclosure, attempt descriptors left open until traceback garbage collection,
and missing structured input/output error metadata. Narrow RED checks led to
corrections: **132 passed in 8.22s**, with **43 command/performer cases collected**;
the final input diagnostic correction passed **43 in 4.19s** after its RED check.
The final reviewer passed **4 targeted cases in 1.53s** and separately exercised
an invalid certified input: expected `Int`, a safe diagnostic path and no child
execution. Conformity PASS preceded quality APPROVED on all nine matching file
hashes.

Canonical coordinator final collection/execution covered 20 modules: **634
collected in 3.81s; 634 passed in 36.97s**, exit 0, using
`-q -n 16 --dist=worksteal` in tmux. All 546 source/test/script hashes stayed
unchanged before/after and at `2153279e`; the coordinator inspected all nine
diffs. Exact commands, modules, logs and receipts are in
`/dev/shm/orc-dc3-commands-final2/`, with the nine-file author freeze in
`/dev/shm/orc-dc3-task8a-final-freeze.json`. The earlier 634-case run in 37.37s
preceded the last patch; final2 is canonical. Broad runs passed, so no failure
baseline worktree was needed. Overlapping counts are not additive.

The next fetch still found Phase 3 `93a33ae2` and main `be327102`, with no new
shared import. Task 8B provider/direct imported-asset integration is selected and
in progress; Task 8C owns stdlib/full improve/search/edit port and historical
experiment retirement. Task 8 and the atomic Tasks 5–8 cutover remain incomplete.
External kills and full Q1–Q5/DC-P handoff remain Task 9; live/paid provider
qualification is absent. Stable evaluation stays at `3a7f8efd`, frozen DC-2
`4b69ee00d4c6204dd816b4caa02b9fee1dae25e8` is unchanged, and adoption/migration
remain unselected.


### Task 8B Direct Provider Gate

`a8f8132a` qualifies the direct provider caller on the isolated target-3.0
candidate. A registered local executable `codex` stand-in captures the real
request/options and returns a declared native union; its result selects an
ordinary closure that runs an actual command, under one 37-node invocation
budget. Imported prompt `:doc` inputs and required reports use shared snapshot,
path and publication owners. No per-effect leaf workflow, memo or
`WorkflowExecutor` is constructed. Strict failures preserve attempt evidence,
publish no successful result and prevent the following command. Ordinary stdout
is not a result bundle.

The provider module's **18 collected/passing cases** cover native union
publication, fresh document snapshots, declared fill/policy/path refusals,
wrong Bool/inactive union fields/Int64 overflow, missing bundles and required
reports, and safe diagnostics. Independent review found one P2 binding bug:
an admitted extern alias was looked up only by provider ID. The correction
uses the definition owner's exact configuration key first, with provider-ID
fallback. Durable regressions additionally cover admitted null policy,
source-free imported library assets over a caller decoy, public dry-run with
no allocation/dispatch, and nonexecutable-provider refusal in run and dry-run.

The exact production selectors are in
`tests/test_workflow_dynamic_providers.py`:
`test_public_provider_selects_closure_and_runs_later_command`,
`test_public_provider_resnapshots_imported_document_on_fresh_run`,
`test_admitted_provider_extern_alias_uses_definition_owner_binding`,
`test_admitted_provider_without_policy_uses_shared_empty_policy`,
`test_sourcefree_imported_provider_asset_uses_library_owner`,
`test_public_provider_dryrun_never_launches_or_allocates`,
`test_provider_without_execute_permission_refuses_before_dispatch`,
`test_provider_fill_policy_and_path_refusals_precede_dispatch`, and
`test_provider_failure_never_publishes_success_or_runs_next_command`.

Independent revised verification passed **6 selected cases in 1.87s** and
collected **18**; conformity PASS preceded a separate subsequent quality PASS.
The coordinator's final 29-module gate collected **817 in 4.61s** and passed
**817 in 50.96s**, exit 0 (`51.19s` wrapper wall time), using
`-q -n 16 --dist=worksteal` in tmux. All **556** source/test/script hashes were
unchanged before/after and at the committed revision. The 18 provider cases,
three targeted regressions and independent selection overlap the aggregate;
counts are not additive. Exact modules/commands and raw evidence are in
`/dev/shm/orc-dc3-providers-final/{collect,affected}.{json,log}`; ordered review
is in `/dev/shm/orc-dc3-task8b-review.md`.

The earlier long-basetemp aggregate collected 811 and recorded 762 passed,
48 failed and one error from AF_UNIX/tmux socket path length. A representative
short-root retry passed, followed by the whole revised short-root gate above.
This was an evidence-environment issue, not a code baseline failure.

The reviewed four-file freeze, unchanged at `a8f8132a`, is
`/dev/shm/orc-dc3-task8b-revised-freeze.json`:

| File | SHA256 |
| --- | --- |
| `orchestrator/workflow/dynamic/evaluator.py` | `d38f901f4a805f3cdacef97f77d97044ff33f440b06ffe52307f5289df429b96` |
| `orchestrator/workflow/dynamic/runtime.py` | `30e43808ee8aa26e081126a7ee5dd04179091addac249dffc7f161422cd2daf6` |
| `tests/test_workflow_dynamic_providers.py` | `f6e8fe72d028486f2e34637b84e25fa9b9d6fd237b86ec1c52e9d5703d9d10b8` |
| `tests/fixtures/workflow_lisp/dynamic/provider_probe.py` | `b09fd77bdca34e84d91ea057e235397059177e7d8b133ed5a882870302460464` |

Registered `omp_json_stdout` remains owned by the unchanged shared materializer;
the affected provider-materialization selectors qualify that compatibility.
This receipt claims no direct dynamic OMP end-to-end test or live/paid provider
qualification. The latest fetch still found main `be327102` and Phase 3
`93a33ae2`, with no new shared import. Task 8C1 stdlib/imported improve is in
progress; 8C2 search/edits, 8C3 experiment retirement and Task 9's external-kill
and full Q1–Q5 evidence remain pending. Task 8 and the atomic Tasks 5–8 cutover
are incomplete. Stable evaluation stays at `3a7f8efd`; frozen DC-2
`4b69ee00d4c6204dd816b4caa02b9fee1dae25e8` is unchanged. No adoption, default
target change, migration or DC-P disposition follows from this bounded gate.


### Task 8C1 Imported Improve Gate

`ba181ff8` qualifies the real [std/dynamic/improve library](../../orchestrator/workflow_lisp/stdlib_modules/std/dynamic/improve.orc)
and [complete native consumer](../../tests/fixtures/workflow_lisp/dynamic/improve.orc),
with real imports, canonical `std/improve` domain schemas, separate goal/rubric
captures and no authored wire reconstruction. The typed five-argument helper
remains unchanged. [Production improve tests](../../tests/test_workflow_dynamic_improve.py)
preserve UI01–UI11 plus eight additional cases: **19 PASS**. They cover complete
approval/blocked/exhaustion results and requests, final-revision failure,
invalid/unreached hooks, nonpositive limits, imported/inline parity and actual
subprocess compile/dry-run/run/source-free report.

Ordered independent conformity and quality reviews passed; fresh review selected
**6 PASS / 19 collected**. The eight-module gate collected **256 in 2.38s** and
passed **256 in 24.93s** (25.19s wrapper), exit 0; **551** before/after hashes
match committed `ba181ff8`. New cases and eight retained typed checks overlap
this aggregate. Exact six-file freeze, review and selector/smoke receipts:
`/dev/shm/orc-dc3-task8c1-freeze.json`, `/dev/shm/orc-dc3-task8c1-review.md`,
`/dev/shm/c1v/receipt.md` and `/dev/shm/orc-dc3-improve-affected/`.

Prerequisite `802a6087` fixed three-variant canonical-JSON key ordering in the
shared schema owner, without a consumer workaround: **969 PASS in 49.04s**,
34 modules. Its stable 578-file worktree footprint included paused untracked C1;
it does not describe the shared fix commit. Review/evidence:
`/dev/shm/orc-dc3-union-order-review.md` and `/dev/shm/orc-dc3-union-order-affected/`.

C2 search/edits/cost is in progress; C3 retirement and Task 9 remain pending.
Task 8, atomic Tasks 5–8, full Q1–Q5 and DC-P remain incomplete. Latest upstream
heads remain main `be327102` / Phase 3 `93a33ae2`; stable evaluation `3a7f8efd`
and frozen DC-2 `4b69ee00d4c6204dd816b4caa02b9fee1dae25e8` are unchanged.
No adoption, migration or live/paid qualification follows.


### Task 8C2 Search, Edits And Restart-Cost Evidence

`b916c92e` qualifies the complete [native search consumer](../../tests/fixtures/workflow_lisp/dynamic/search.orc),
[search tests](../../tests/test_workflow_dynamic_search.py) and
[paired edits/cost tests](../../tests/test_workflow_dynamic_edits.py), with a real
[imported feedback helper](../../tests/fixtures/workflow_lisp/dynamic/feedback.orc).
Full native results and exact requests preserve ranking, strict improvement,
repair, stalls/fusion/history and budget/score/loop stops. Four source edits
retain boundary contracts; failures retain completed prefixes and safe errors.
The maintained search application remains unchanged.

`/dev/shm/c2v/case-map.json` maps **87 originals = US77 + UE4 + UD6** to 87
production cases, including all 72 US01 suffixes. With C1, the combined corpus
is **106 PASS in 21.28s**; coordinator verification collected **425 in 3.10s**
and passed **425 in 42.37s**, 12 modules, exit 0. All **586** before/after
hashes match committed `b916c92e`. Counts overlap and are not additive.
Ordered independent conformity and subsequent quality reviews passed; fresh
review selected **2 PASS / 87 collected**. Exact freeze/map/receipts:
`/dev/shm/c2v/`, `/dev/shm/orc-dc3-consumers-affected/` and
`/dev/shm/orc-dc3-task8c2-review.md`.

UD05/UD06 use a failed native terminal after two completed effects, then a
corrected fresh run that repeats them; typed resume reuses its prefix. External
kill proof remains Task 9. C3 reconciliation/retirement is next, pending;
Task 8, atomic cutover, full Q1–Q5 and DC-P remain incomplete. Stable evaluation
`3a7f8efd` and frozen DC-2 `4b69ee00d4c6204dd816b4caa02b9fee1dae25e8` stay
unchanged. Upstream `cee2aba1` / `4acd38ec` scopes await separate qualification;
this receipt supplies no import PASS. No adoption, migration or live/paid calls
follow.
