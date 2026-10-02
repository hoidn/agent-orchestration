# Workflow Lisp Execution: Facts About The Current System

- **Status:** historical evidence at the code checkpoint below, including its
  then-open repairs; it proposes nothing. Current capabilities and remaining
  work belong to the [capability matrix](../capability_status_matrix.md) and
  [Workflow Lisp Evaluated Execution](../design/workflow_lisp_evaluated_execution.md),
  which incorporates this evidence and subsequent compiler delivery.
- **Date and code:** 2026-09-29. Code and documents were read from the branch
  `feat/orc-shared-defect-repairs` at `98ba8f0a`, which is `main` plus the
  repairs of the
  [shared defect repairs plan](../plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md).
  Paths are relative to the repository root unless they start with `/`.
- **Scratch programs:** the programs quoted in this report are complete. The
  scratch directory that held the others was on a memory disk and is not
  kept.

## Method

**Ran.** Everything ran in `/dev/shm/repairs-tmp/exec-design-research/` with
`PYTHONPATH=<worktree>`. No pytest ran, and nothing was written in the worktree.

- **A.** `python -m orchestrator compile workflows/examples/improve_experiment_proposal.orc --entry-workflow improve_experiment_proposal::run-experiment` with `--emit-runtime-plan --emit-core-ast --emit-debug-yaml --emit-source-map`. The route reported was `wcc_m4`, lowering schema 2. The same compile was repeated on a copy of the file in another directory, and on that copy with two blank lines added.
- **D.** 11 `.orc` programs run with `python -m orchestrator run … --dry-run`, and 3 of them also with `compile --emit-executable-ir`. The three messages were reproduced a second time by the integrator (D.4).
- **E.** Dry-runs of node-count, overflow and float probes. Real runs of `ovfin.orc` and `fltin.orc`. Python probes of `evaluate_pure_expr`, `validate_output_bundle`, `bind_workflow_inputs` and `canonical_json_for_pure_value`.
- **F.** Three real runs with a command probe and no provider: a loop calling `command-result`, a loop calling a `defproc` that wraps it, and `list/map-effect`.
- **C, B, G.** Only `grep`, `sed` and `wc`.

**Read.** Everything else. Each statement cites the file and line it comes from.

**What each spec covers (skimmed):**

| Spec | Covers |
| --- | --- |
| `specs/state.md` | Run id, `state.json` schema 2.1 and its keys (`:7-57`), and the key formats for branches, cases, loops and call frames (`:112-129`). It also has one section per feature: derived pure replay (`:160`), host input (`:233`), provider attempts, prompt dependencies and attempt identity (`:310-513`), phased delivery (`:514`), run-ref (`:571`), trial (`:629`), supervision (`:789`), peer group (`:823`), adjudication (`:1087`) |
| `specs/io.md` | Input and output capture, `expected_outputs` and `output_bundle` contracts, strict JSON (`:27-35`), the bound result path, and the rule that the result file must be absent before a call (`:152-194`) |
| `specs/providers.md` | Provider attempt lifecycle and at-least-once recovery (`:7-19`), prompt delivery, templates |
| `specs/cli.md` | `run`, `resume`, `input get/answer/cancel`, `report`, `dashboard`, `monitor` |
| `specs/dsl.md` | The `.orc`-only frontend boundary (`:3-20`), the Core workflow schema, and structured control with its "first tranche" limits (`:238-266`) |

---

## A. The core calculus as an executable form

### A.1 Constructs in `orchestrator/workflow_lisp/wcc/model.py`

Every node carries a `WccNodeMetadata` with these fields: `node_id`,
`type_ref`, `scope_id`, `source_span`, `form_path`, `expansion_stack`,
`effect_summary`, `proof_context`, `allocation_requests`, `phase_scope`
(`model.py:45-58`).

| Construct | Fields besides metadata | Meaning | In §10.1 of the design? |
| --- | --- | --- | --- |
| `WccLiteralAtom` `:219` | `value: str\|int\|bool`, `literal_kind` | literal; enum values have `literal_kind="enum"` (`elaborate.py:2656-2676`) | yes (`atom`) |
| `WccNameAtom` `:226` | `name` | variable reference | yes (`atom`) |
| `WccFieldAccessAtom` `:232` | `base`, `fields` | field projection | yes (`atom`) |
| `WccRecordAtom` `:245` | `type_name`, `fields`, `resolved_type` | record construction | yes (`atom`) |
| `WccPhaseTargetAtom` `:239` | `target_name` | `phase-target` lookup, typed `String` | code only |
| `WccOpaqueFrontendValue` `:265` | `expr: object` (a frontend AST node) | a surface expression passed through unexamined: `loop-state` seed and update, relpath seed, `list`, `list/map`, `path/join-under`, `provider-bundle-path`, variant tags (`elaborate.py:2677-2696, 2731-2763`) | code only |
| `WccPureOp` `:257` | `operator`, `args`, `field_names` | pure operator application, including `record-update` | code only |
| `WccInject` `:274` | `union_name`, `variant_name`, `fields`, `resolved_type` | variant introduction | yes |
| `WccSelect` / `WccSelectArm` `:286-308` | `condition`, `then_arm`, `else_arm` (each has `prefix: tuple[WccLet]` and `value`) | `if` in value position | code only |
| `WccPerform` `:575` | `perform_kind`, `target_name`, `prompt_name`, `positional_args`, `keyword_args`, `returns_type_name`, `operation_payload` | an effect: one node kind with a kind string (A.2) | yes (`perform`) |
| `WccCall` `:597` | `callee_name`, `specialized_callee_name`, `args`, `specialization_captures`, `proc_ref_*` | procedure call. The callee body is **not** inside the node | yes |
| `WccSpecializationCapture` `:587` | `owner_kind`, `argument_index`, `source_name`, `value` | value routed to a specialization | code only |
| `WccProviderSupervision` `:624` (+ `Member` `:615`) | `members` (each has `normalized_body: WccBody`), `supervisor_name`, `worker_name`, `settlement_body`, `observation_metadata` | `with-live-providers` | code only |
| `WccProviderPeerGroup` `:644` (+ `Member` `:634`) | `members` (+ `lexical_capture_names`), `settlement_body` | `with-live-provider-peers` | code only |
| `WccLet` `:784` | `bound_name`, `bound_type_ref`, `bound_value`, `body` | sequencing. The bound value may be a value, `WccPerform`, `WccCall`, supervision or peer group (`:651-657`) | yes |
| `WccCase` / `WccCaseArm` `:688-700` | `subject: WccAtom`, `arms` (`variant_name`, `binding_name`, `binding_type_ref`, `body`) | variant elimination | yes |
| `WccIf` `:703` | `condition`, `condition_shape`, `then_body`, `else_body`, `then/else_proof_context` | control `if` over strict `Bool` | code only |
| `WccJoin` / `WccJoinParam` `:721-733` | `join_name`, `params`, `body`, `continuation` | second-class join point | yes |
| `WccJump` `:736` | `join_name`, `args` | jump to a join point | yes |
| `WccRecJoin` `:763` | `loop_name`, `params`, `budget`, `body`, `exhaustion`, `initial_state`, `roles`, `exhaustion_diagnostic_code`, `single_iteration_effect_kinds`, `effect_cardinality_diagnostic_code` | bounded loop | yes (`rec-join`) |
| `WccLoopContinue` `:749` / `WccLoopDone` `:756` | `target_name`, `state_args` / `result`, `state` | next iteration or leave the loop. These are not `jump`s | code only |
| `WccLoopRole` `:743` | `frame_role="loop_frame"`, `iteration_role="loop_iteration"` | names of resume scopes | code only |
| `WccHalt` `:778` | `result` | terminal result | yes |
| `WccPhaseScope` `:61` | `ctx_expr`, `phase_name`, … | `with-phase`. Carried on metadata, not a node (`elaborate.py:1535-1547`) | code only |

How the code departs from the design:

- **Construct count.** The design caps the calculus at ten constructs and says "additions require amending this document" (`docs/design/workflow_lisp_core_calculus_middle_end.md:353-354`). The code has 9 body and binding node kinds plus 9 value kinds.
- **Join fields.** The design's §13.1 fields `live_in`, `live_out` and "defunctionalized step identity" (`…middle_end.md:648-656`) are not on `WccJoin`. Live sets are computed separately (`analysis.py:84-155`).
- **`allocation_requests`.** The elaborator never gives it a value; it stays empty (`elaborate.py:3740-3741`).
- **`effect_summary`.** On an effect node this holds the summary of the whole enclosing body, not a row for that node (`elaborate.py:324`, `:4512-4519`).

### A.2 Effects in WCC

Effects use one node kind, `WccPerform`, with a `perform_kind` string. Three
other node kinds also carry effects: `WccCall`, `WccProviderSupervision` and
`WccProviderPeerGroup`. The elaborator is
`_elaborate_effect_expr_to_binding_value` (`elaborate.py:4492-5295`).

| `perform_kind` or node | Surface form | Payload | Line |
| --- | --- | --- | --- |
| `command_result` | `command-result` | `target_name` = command boundary; `positional_args` = argv; `adapter_name`, `adapter_inputs`, `return_spec` | `elaborate.py:4933-4979` |
| `provider_result` | `provider-result` | `target_name` = provider extern, `prompt_name`, `positional_args` = `:inputs`. The dict payload holds `return_spec`, `prompt_application` (fills as atoms), `model`, `effort`, `delivery`, `materialization_attempts`, `timeout_sec`, `session_artifact`, `context_expr`, `capture_context` and `prompt_dependencies` | `elaborate.py:4764-4903` |
| `workflow_call` | `call` | `keyword_args` = bindings; target resolved through compile-time aliases | `elaborate.py:5149-5183` |
| `request_input` | `request-input` | one positional question; returns `HUMAN_REPLY_TYPE_NAME` | `elaborate.py:4904-4932` |
| `resource_transition` | `resource-transition` | the frontend `ResourceTransitionExpr` itself | `elaborate.py:5127-5137` |
| `materialize_view` | `materialize-view` | the frontend `MaterializeViewExpr` itself | `elaborate.py:5138-5148` |
| `run_ref` | `run-ref` | `WccRunRefPayload`: source request, closed program, `site_digest`, result type and descriptor digest, input descriptors | `elaborate.py:4520-4614`; `model.py:314-443` |
| `trial` | `trial` | `WccTrialPayload`: 2 to 16 arms of run-ref payloads, `reps`, `max_concurrency`, `evaluation`, `budget` | `elaborate.py:4615-4737`; `model.py:446-572` |
| `run_provider_phase` | `run-provider-phase` (std/phase) | `WccRunProviderPhasePayload` | `elaborate.py:4980-5020` |
| `produce_one_of` | `produce-one-of` | `WccProduceOneOfPayload`; its candidates are frontend objects | `elaborate.py:5021-5064` |
| `resume_or_start` | `resume-or-start` | `WccResumeOrStartPayload`; `start_value` is a `WccBindingValue` | `elaborate.py:5065-5115` |
| `finalize_selected_item` | `finalize-selected-item` | the frontend expression itself | `elaborate.py:5116-5126` |
| `WccCall` | procedure call | args and captures; the callee is elaborated later (A.4) | `elaborate.py:5184-5294` |
| `WccProviderSupervision` | `with-live-providers` | each member body is a full `WccBody` | `elaborate.py:4276-4389` |
| `WccProviderPeerGroup` | `with-live-provider-peers` | same shape | `elaborate.py:4392-4489` |
| none | `list/map-effect` | Rewritten during typecheck into a `LoopRecurExpr` whose state is `remaining` and `results` (`list_map_effect_cap_exceeded`), which then elaborates to `WccRecJoin` | `typecheck_structural_values.py:621-673` |
| none | `with-phase` | `WccPhaseScope` on metadata | `elaborate.py:1535-1547` |

- `review-revise-loop` and `backlog-drain` have no elaboration rule of their own. They arrive as stdlib expansion (`form_registry.py:605-617`, `:730-740`).
- Six forms are registered as `TEMP_COMPILER_INTRINSIC`: `run-provider-phase`, `produce-one-of`, `resume-or-start`, `resource-transition`, `finalize-selected-item` and `materialize-view` (`form_registry.py:662-752`).

### A.3 ANF invariants

`normalize_wcc_body_to_anf` (`wcc/anf.py:123`):

| Position | Required after ANF | Line |
| --- | --- | --- |
| `WccPerform` positional and keyword args; `WccCall.args` and captures; `WccJump.args`; `WccRecJoin.budget` and `initial_state`; `WccLoopContinue.state_args`; `WccLoopDone`; `WccIf.condition` | literal, name or field access only (`_is_atomic_effect_arg`) | `anf.py:158-251, 334-395` |
| `WccCase.subject`, `WccHalt.result`, record and inject fields, `WccPureOp.args` | any atom type, including record, phase target and opaque frontend value | `anf.py:39-46, 135-150, 252-258, 292-330` |
| `WccSelect` | left as it is ("non-hoisting value barrier") | `anf.py:287-291` |
| `WccPerform.operation_payload` (provider policy, prompt fills, dependency rows) | **not normalized** | `anf.py:334-354` touches only the args |
| supervision and peer-group bodies | normalized recursively | `anf.py:266-280` |

- **Generated names** have the form `__wcc_anf_<sha256(node_id, purpose)[:10]>` (`anf.py:57-67`).
- **No validator runs after ANF.** `analysis.py:84-140` raises only on unknown node kinds.
- **Tests check the invariant:** `tests/test_workflow_lisp_wcc_m1.py:299,353`, `_m2.py:513`, `_m3.py:884`, `_m4.py:650`.

### A.4 What execution needs that is not in WCC

The pipeline is elaborate, then ANF, then `analyze_wcc_body`, then
`_defunctionalize_body` (`defunctionalize.py:746-760`, `:2117`). Effects are
lowered by converting WCC back into frontend objects and calling the older
`lowering/` emitters (`_lower_effectful_binding`,
`defunctionalize.py:6190-6411`).

| Item | In WCC? | Where computed, and from what |
| --- | --- | --- |
| Output contract from the type | Only the type (`type_ref`, `returns_type_name`, `return_spec`) | `derive_prompt_guided_structured_result_contract(result_type, workflow_name, step_id=<step name>, …)` at `lowering/effects.py:257` (command) and `:478` (provider) |
| Result bundle path / `__write_root__` | No | `allocate_generated_result_bundle` (`lowering/generated_paths.py:112-139`) creates the hidden input `__write_root__<step_id>__result_bundle` with resume scope `STEP_VISIT`. At run time it is bound to `.orchestrate/workflow_lisp/entry/<run_id>/<workflow>/<input>.json` (`state_layout.py:177-192, 252-297`), a path with no iteration part. Calls add a generated inline-Python step, `…__managed_write_roots`, that writes the callee's write roots (`generated_paths.py:142-183`) |
| Prompt assembly | Extern names and fill atoms | The prompt source file comes from the prompt extern manifest (`lowering/core.py:307-310`, used at `effects.py:548-550`). `typed_prompt_inputs` rows use state refs (`effects.py:643-653, 701-711`). Fragment contract (`:552-591`). Phase preludes add steps and `consumes` (`:654-691`) |
| Prompt dependency snapshots | Rows, as atoms in the payload | `_lower_prompt_dependencies` (`effects.py:789`) fills `compiler_prompt_dependency_contracts` (`defunctionalize.py:709-710`) |
| Provider call policy | Atoms, not normalized | Rendered to strings at `effects.py:509-526`. The provider id comes from the extern env (`:505`). `provider_context` at `:527-534`; `provider_session` at `:712-730` |
| Timeouts | Atom | Must resolve to a literal, else `provider_result_timeout_literal_required` (`effects.py:535-547`) |
| Retries | No | `.orc` lowering never emits `retries`. The key is only allowed through, at `defunctionalize.py:4897-4935` |
| Source provenance | Yes: span, form path and expansion stack on every node | Attached to steps by `_record_step_origin` (`lowering/origins.py:566`). Origin keys have the form `"<wf>::<entity_kind>::<name>"` (`origins.py:346-352`) |
| Checkpoint points | No | Built during defunctionalization from WCC `node_id`/`scope_id` plus the step id (`defunctionalize.py:1909-1987`, `:1990`, `:2055`); resume policy per kind at `:1669-1906`. None are emitted for inline procedure calls (`:2245`) or for effects inside loop bodies (`:2915-2935`). The compiled example has 7 points and none for its two provider calls inside a loop |
| Step names | No | Prefix = workflow name (`defunctionalize.py:684`), plus `__<binding>` (`:2995-2998`), plus `__scope_<sha256(scope_id)[:10]>` (`:3001-3010`). An inlined procedure becomes `<prefix>__<callee>_<ordinal>`, with the ordinal taken from the mutable counter `context.inline_call_counters` (`:6690-6715`) |
| Presentation keys | No | `orchestrator/workflow/lowering.py:600-640, 770-792` and `runtime_plan.py:459-461`. Iteration rows are `"<frame>[<i>].<nested>"`; the runtime id is `"<loop_node_id>#<i>.<suffix>"` (`state_projection.py:14-15, 68-80`) |
| Callee bodies of `WccCall` | No | Re-elaborated during defunctionalization under `owner_name = procedure.definition.name` (`defunctionalize.py:6755-6773`) |
| Loop bodies | Yes | Converted back to surface expressions (`_frontend_expr_from_wcc_loop_body`, `defunctionalize.py:7035`), then lowered by `lowering/control_loops.py:335` |
| Value references | Names | Pure bindings are resolved at compile time into state-reference strings or inlined expressions (`defunctionalize.py:2130-2455`). Effects receive them as `${root.steps.<step>.artifacts.return__value__<field>}` |

### A.5 Identity

| Identity | Built from | Line |
| --- | --- | --- |
| WCC `scope_id` | `sha256(schema, owner_name, lexical_owner_chain)[:16]` | `model.py:84-93` |
| WCC `node_id` | `sha256(schema, owner_name, chain, node_kind, role)[:16]`. No span. The role can contain the specialized callee name | `model.py:104-138`, `elaborate.py:5248` |
| Loop name | `__wcc_loop_<binding>_<scope digest>` | `elaborate.py:2428` |
| `program_point_id` | `pp:` + sha256(schema, wf, kind, origin key, digest of {`wcc_node_id`, `wcc_scope_id`, `step_id`, storage scope})[:24] | `defunctionalize.py:1299-1338`; `lexical_checkpoints.py:80-87` |
| `checkpoint_id` | `ckpt:` + sha256(schema, wf, program point, `<node or scope>:<step_id>`, lowering schema, storage scope)[:24] | `defunctionalize.py:1305-1345`; `lexical_checkpoints.py:90-106` |
| Binding schema digest | sha256 of {wf, kind, step_id, **`repr(type_ref)`**, form_path} | `defunctionalize.py:1263-1281` |
| Parametric specialization name | `sha1(base + repr(type_ref) per binding)[:12]` | `procedures.py:341-353, 390-391` |
| `loop-state` record name | sha1 over a repr of (owner, **span path, line, column**, form path, fields) | `loop_state.py:375-394` |
| Compiler pure names / condition bindings | sha1 over (role, form path, **span offset**, ordinal) / sha1 over (…, start and end offsets) | `functions.py:1335-1346`; `conditionals.py:1109-1125` |

- **Types carry file paths.** `repr(TypeRef)` includes the type's definition, which carries a `SourceSpan` whose position holds a file path (`type_env.py:188-230`, `definitions.py:93-125`, `spans.py:8-23`). The docstring of `UnionTypeRef` says its repr "is digested into specialization and checkpoint identities" (`type_env.py:206-215`).
- **The source map holds absolute paths**, for example `/home/ollie/…/improve_experiment_proposal.orc`.

Two examples from the compiled example (`improve.plan.json`):

- **Command step.**
  - Step id: `root.improve_experiment_proposal_run_experiment__match_result.improve_experiment_proposal_run_experiment__match_result__approved.improve_experiment_proposal_run_experiment__match_result__approved__improve_experiment_proposal_execute_1__launch_experiment`
  - Presentation key: `improve_experiment_proposal::run-experiment__match_result.APPROVED.improve_experiment_proposal::run-experiment__match_result__approved__improve_experiment_proposal::execute_1__launch_experiment`
  - Checkpoint: `ckpt:4b02bda700d1e84813a9cd5f`; program point `pp:686a9e83d8d675dd61c58186`.
- **Loop frame.**
  - Step id: `root.improve_experiment_proposal_run_experiment__result___proc_ref_call_parametric_call_std_improve_improve_20ba009c874a_6b46538eaadb_1__loop`
  - Presentation key: `improve_experiment_proposal::run-experiment__result__%proc-ref-call.%parametric_call.std.improve.improve.20ba009c874a.6b46538eaadb_1__loop`
  - Back-edge checkpoint: `ckpt:d8a9637d97b1469668e86fda`.

Measured by recompiling:

| Change | Step ids | Checkpoint ids | Binding schema digests |
| --- | --- | --- | --- |
| Same file copied to another directory | changed (`…improve_20ba009c874a_6b46538eaadb_1__seed` became `…improve_05d33360ccf9_212d85c0f59c_1__seed`) | changed | changed |
| Two blank lines added | changed (`…__pure_procedure_arg_ec79dd275b0f…` became `…_950d8aefb6f1…`) | changed | changed |

The design requires that "formatting-only edits do not change step identity or
resume identity" (`…middle_end.md:342-343`).

The example reaches its three `launch_experiment` commands through one inlined
procedure called from three `match` arms. All three share one WCC `node_id`
(`sha256:3e27f6a71b8df…`) and one `scope_id`. Only the step-name ordinals
`execute_1`, `_2` and `_3` tell them apart. The reason is that the callee is
re-elaborated under its own owner name (`defunctionalize.py:6755-6764`).

---

## B. How effects are executed today

### B.0 Dispatch and commit

- **Step loop.** `_execute_step_loop` (`executor.py:5096-5755`) processes one node at a time:
  - increments `step_visits[step_name]` (`:5558`, `:6200-6213`) and persists it (`:6183-6198`);
  - sets the single cursor with `state_manager.start_step`, which writes `current_step` = {name, index, type, status, step_id, visit_count} and rewrites the state file (`:5692`; `state.py:1651-1677`);
  - dispatches (`:5705`) and routes (`:5713-5745`).
- **Dispatchers.** There are two:
  - `_run_top_level_step` (`executor.py:7713-7908`).
  - `_execute_nested_loop_step` (`:7910-8214`) runs loop bodies. It has no branch for `FOR_EACH`, `REPEAT_UNTIL_FRAME`, `RUN_REF` or `TRIAL`; those fall to `{"status": "skipped"}` (`:8070-8071`). Supervision and peer groups return `*_nested_atomicity_unavailable` (`:8042-8069`).
- **Common top-level commit.** `_execute_top_level_publish_and_persist` (`:8216-8426`) records published artifacts, then calls `OutcomeRecorder.persist_step_result`. That writes `state["steps"][step_name]` (`outcomes.py:83`), calls `state_manager.update_step` (`:114`), and then runs the post-persist shadow checkpoint hook (`executor.py:478`, `:15382-15420`).
- **Guarded commit.** `finalize_step_with_dataflow` first checks that `current_step`'s name, step_id and visit_count match (`state.py:1282-1359`, guard at `:1302-1334`).
- **Nested commit.** Writes `state["steps"]["<loop>[<i>].<nested>"]` and calls `update_loop_step` (`loops.py:105-106`).
- **Heartbeat thread.** Rewrites the state file while a step runs (`executor.py:5866-5910`; `state.py:1679-1689`).

### B.1 Per effect kind

| Effect | Function | Inputs beyond the node's config | Returns | Contract validation | Tied to the step loop? | Retries and what is kept per attempt |
| --- | --- | --- | --- | --- | --- | --- |
| command | `_execute_command_with_context` `executor.py:8526-8705`. The process itself runs in `StepExecutor.execute_command` `exec/step_executor.py:59-216`, built from workspace, logs dir and secrets only (`:46-57`) | Variables built by `RuntimeContext` over `state["steps"]` (`:8551-8566`); workspace pre-snapshot (`:8567`, `:13023-13062`); output paths substituted from state (`:11736-11788`); bundle made absent before launch (`:7457-7491`); `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` (`:11955-11973`) | `ExecutionResult.to_state_dict()`: exit code, output, error. **Not the resolved argv** (`step_executor.py:28-37`) | `_apply_expected_outputs_contract` `executor.py:12195-12276`, only when the exit code is 0 (`:12209-12211`) | Reads state; the caller commits | `RetryPolicy.for_command` (`exec/retry.py:43-65`): none by default, else exit codes 1 and 124. The bundle is cleared on each attempt (`:8652`). Nothing is kept per attempt. `logs/<step>.stderr` is keyed by step name and overwritten (`output_capture.py:90-94`) |
| provider (composed) | `_execute_composed_provider_with_context` `:9580-11187`. Leaves: `ProviderExecutor.prepare_invocation` and `.execute` (`providers/executor.py:226`, `:1186`) | Prompt files and assets (`:9766-9774`), dependencies (`:9794-9823`), typed prompt values from state (`:9841`), `state["_resolved_consumes"]` (`:9980`), session id (`:11582-11637`), `current_step.managed_jobs` (`:9634-9660`), `step_visits` (`:10822-10866`) | Result dict (`:10946-10973`) | `:11085`, then prompt-attempt result binding (`:11106-11184`) | Attempt scope reads `current_step` and `step_visits` (`:8781-8841`); `allocate_provider_attempt` writes state (`state.py:528-613`); the caller commits (`:8333-8346`) | Policy chosen at `:10128-10138`: 0 for sessions and managed jobs, else exit codes 1 and 124 (`retry.py:31-40`). An ordinal is persisted only when there is a prompt-dependency contract or context capture (`:10184-10205`, `:10436-10450`): `provider_attempt_allocations[scope.key]`, plus `workflow_lisp/prompt_dependencies/<step>/<visit>/attempt-NNNNNN.json` (`prompt_dependency_evidence.py:1053-1055`). The scope key hashes run_id, resume scope, runtime step id, enclosing step (name, id, visit_count) and loop iteration (`provider_attempts.py:205-295`) |
| provider (phased) | `PhasedProviderAttemptCoordinator(… executor=self …)` `:9274-9312` | same as composed | result dict | in the coordinator bindings | **Commits state itself** (`provider_phased_delivery/runtime_bindings.py:1533-1554`), then tags the result so the caller skips its commit (`:1561-1566`; `executor.py:8223-8230`) | `materialization_attempts` 1 to 3 (`:9144-9150`) |
| adjudicated provider | `AdjudicationRunner.execute_adjudicated_provider_with_context` (`adjudication_runner.py:47`), sequential | The `AdjudicationRuntime` protocol: `state_manager`, `current_step`, `resume_mode`, `_persist_control_flow_state`, … (`adjudication_runtime.py:46`) | Result and an `adjudication` block | `adjudication/promotion.py:66, 279, 802` | Caller commits | Per-visit directory `adjudication/<frame>/<step>/<visit>` (`adjudication/paths.py:38`) |
| workflow call | `CallExecutor.execute_call` `calls.py:905-1325` | Frame id `"{step_id}::visit::{visit_count}"`, prefixed by the parent frame (`:220-249`); projection (`:91-137`); `call_frames` retry lineage (`:63-81`) | `child_state["workflow_outputs"]` (`:1311-1324`) | The child's epilogue: `resolve_workflow_outputs` follows `root.steps.<key>.artifacts.<name>` refs (`signatures.py:130-152`) | **A full child `WorkflowExecutor`** (`:1253-1278`) whose nested state goes into the parent's `call_frames` (`:1279`; `call_frame_state.py:258-259`) | No retry. On resume a failed frame gets a new frame id (`:139-164`) |
| request_input | `_execute_request_input` `executor.py:13836-14048` | `current_step` as the enclosing step (`:13893-13916`); loop projection (`:13920-13966`); `root.human_input` (`:13968-13980`) | StepResult | `validate_contract_value` (`:14000-14002`) | Suspends the process (`HumanInputSuspended`, `:13988`); commits itself (`human_input.py:403-440`), guarded against the cursor (`:219-225`); replaces `state` wholesale (`executor.py:14032-14033`) | One outstanding request per run (`human_input.py:240-241`) |
| resource_transition | `execute_resource_transition` (`steps/resource_transition.py:13-117`) calls `execute_transition(declaration, resource, request_values, expected_version, backend)` (`transition_executor.py:65-248`) | Bindings from state refs (`executor.py:14096-14127`) | `{result, version, replayed}` | `validate_contract_value` (`:14166-14197`) | Uses only the `StepRuntime` protocol (`steps/runtime.py:11-164`); the caller commits | No retry. Content-derived idempotency key (`transition_executor.py:91-96`); audit row per outcome; pending-replay sidecar (`:226-238`) |
| materialize_view | `steps/materialize_view.py:20-196` | Value and target from state refs; `state_manager.frame_id` (`:35-55`) | artifacts | `:163-166` | Caller commits | Reuse by evidence key (`:127-144`) |
| pure_projection (for contrast) | `steps/pure_projection.py:19-157` | Bindings from state refs (`:69-73`) | artifacts | `:115` | Caller commits; replay witness (`executor.py:15341-15377`) | Bundle reuse by payload and bindings digest (`:86-112`), except under the replay profile |
| run_ref | `_execute_run_ref` `executor.py:6945-7109` → `prepare_run_ref_settlement` (`run_ref/runtime.py:2759-2786`) | `step_visits` (`:6955-6969`); `parent_state=state`; `RunRefVisitKey(parent_run_id, frame ids, step_id, visit_count)` (`:6270-6354`) | Envelope written as the bundle (`:6996-6999`) | `:7008-7028` | **Commits itself** (`:7046-7101`), sets `current_step = None` (`:7095`). Top level only | `run-ref-attempts.jsonl` (`runtime.py:78`); ordinal = highest recorded for the visit + 1 (`:1640-1643`); input digest recorded (`:1491-1501`) |
| trial | `_execute_trial` `executor.py:6715-6943` → `execute_trial_cells` (`trial/runtime.py:439`) | same as run_ref | Envelope | `:6842-6859` | **Commits itself** (`:6874-6935`). Top level only | Cells run on a thread pool (`trial/runtime.py:855`); `trial-events.jsonl` (`:6451`) |
| provider_supervision | `_execute_provider_supervision` `:15634-15708` → `ProviderSupervisionCoordinator(WorkflowProviderSupervisionBindings(self, …))` | `step_visits`; the bindings get `self` (17 uses of `state_manager`) | Group result | `provider_supervision/bindings.py:1176-1199` | **Commits itself** after re-reading `current_step` and requiring type `provider_supervision`, status running (`:15838-15850`). Refused inside loops | Visit-scoped; interrupted rerun (`:15699`) |
| provider_peer_group | `_execute_provider_peer_group` `:15710-15788` | same | Group result | `provider_peer_group/bindings.py:1078-1085` | Same (`:15905-16019`) | Same |
| loops | `LoopExecutor.execute_repeat_until` (`loops.py:718-1433`) and `execute_for_each` (`:1434-1806`); body runs in `_execute_typed_loop_body` (`:213-369`) | `repeat_until` and `for_each` progress; projection | Frame result in `state["steps"][loop]` | frame outputs | Writes progress (`:419-466`) and iteration rows (`:94-111`) | `max_iterations`; resume from `completed_iterations` (`:780-853`) |
| wait_for | `StepExecutor.execute_wait_for` (`exec/step_executor.py:241`) | filesystem glob | wait result | none | Caller commits | none |

Only three performers are independent of executor state:
`StepExecutor.execute_command`,
`ProviderExecutor.prepare_invocation`/`execute`, and `execute_transition`.
The prompt assembly, contract paths, publishing and consumes around them are
`WorkflowExecutor` methods. Even the narrowed protocols (`StepRuntime`,
`LoopRuntime` at `executor_runtime.py:115-275`, `AdjudicationRuntime`) include
`state_manager` or `current_step`.

---

## C. Who reads run state

### C.1 Per-run files

| File under `RUN_ROOT` | Keyed by | Source |
| --- | --- | --- |
| `state.json` (schema 2.1) | root keys | `specs/state.md:7-57`; `state.py:744-756` |
| `state.json.step_<Step>.bak` | step name | `specs/state.md:304` |
| `logs/<Step>.stdout`, `.stderr`, `.prompt.txt`; `orchestrator.log` | presentation key | `specs/state.md:308` |
| `provider_sessions/<step_id>__v<visit>.*` | step id + visit | `specs/state.md:59-75` |
| `managed_jobs/<step>/` | step | `specs/state.md:98` |
| `provider-peer-group/<node>/…/<visit>/…` | node + visit | `specs/state.md:101-107` |
| `adjudication/<frame>/<step_id>/<visit>/` | frame + step + visit | `specs/state.md:1093` |
| `workflow_lisp/checkpoints/{records,index}/…`, shadow, restore and default-resume reports | checkpoint id | `lexical_checkpoints.py:2236, 2245`; `state.py:782-790` |
| `summaries/` (`index.json`, `live.json`, `run-summary.md`, `typed-terminal-summary.json`, `live-current-step.json`) | run | `observability/report.py:143-147` |
| `run.lock`, `monitor_process.json`, `prompt-inputs/` | run | `run_lock.py:70-75`; `monitor/process.py:14`; `prompt_session_lookup.py:137` |

### C.2 Consumers outside the executor

| Consumer | File:line | Keys read | Depends on step names / positions |
| --- | --- | --- | --- |
| `orchestrator report` (from state alone) | `cli/commands/report.py:84-313`; `prompt_context_report.py:159, 425, 464, 1547`; `judgment_views.py:147-160` | every `steps` row (status, type, debug, trial, output, artifacts, error, outcome, step_id), `current_step`, `status`, `updated_at`, `transition_count`, `bound_inputs`, `workflow_outputs`, `finalization`, `error`, `runtime_observability`, `provider_attempt_allocations`, `step_visits` | Names; rows in insertion order (`:170-191`). **Writes `state.json`** with plain `write_text`, without `run.lock` or temp-and-rename, when it infers a terminal status (`:284-297`) |
| Status snapshot with the compiled bundle (used by the dashboard) | `observability/report.py:319-517` | `steps[presentation_key]`, `step_visits`, `current_step`, `status`, `error.type`, `bound_inputs`, `workflow_outputs`, `finalization` | Names and order: walks `projection.ordered_execution_node_ids()` (`:337-346`). Stale after 300 s with no `current_step` (`:27, 245-316`) |
| Dashboard projection | `dashboard/projection.py:40-560, 700-716`; `dashboard/compiled_workflow.py:46-90, 227-234` | `steps`, `artifact_versions`, `artifact_consumes`, `call_frames[*].state.artifact_*`, `current_step` heartbeat, the flat `persisted_workflow_surface.json`, and `logs/<name>.*` and `provider_sessions/<id>__v<n>.*` files | Names (file names come from step name, id and visit) and order |
| Dashboard cursor (also used by the monitor) | `dashboard/cursor.py:39-212` | `current_step`, `call_frames[*]` (`call_step_id`, `state.current_step`), `repeat_until[<name>]`, `for_each[<name>]`, `finalization` | Names |
| Dashboard server | `dashboard/server.py:1229-1310, 1462-1503, 1982-2030, 2278-2300, 2444-2460, 3137-3156` | `current_step`, `steps[current].debug.structured_repeat_until`, `repeat_until[current]`, `call_frames`, `artifact_consumes`, `bound_inputs`, `summaries/*` | Names; draws the flat surface's `repeat_until.steps` tree |
| Dashboard and monitor scanners | `dashboard/scanner.py:40-140`; `monitor/scanner.py:22-75` | `run_id`, whole state | Neither |
| Monitor classifier | `monitor/classifier.py:17-92` | `status`, `updated_at`, `current_step` heartbeat, including nested frames | Neither |
| Monitor email | `monitor/messages.py:29-128` | `workflow_file`, `status`, `workflow_outputs`, `error`, `current_step`, `steps[*]`; `logs/<step>.*` | Names and order: the last failed step is found by `reversed(list(steps.items()))` (`:79-84`) |
| `orchestrator resume` (CLI) | `cli/commands/resume.py:320-592` | `schema_version`, `workflow_file`, `run_ref_root`, `context` (lowering schema, `:418-459`), `workflow_checksum`, `bound_inputs`, `status`, `steps` | Names; takes `run.lock` (`:541-544`) |
| Resume integrity audit | `workflow/resume_projection_integrity.py:132-200` | `steps[key].step_id`, `current_step`, `call_frames` (recursively) against `projection.enumerate_resume_slots` | Names: each row must match a slot of the current flat projection |
| `ResumePlanner` | `workflow/resume_planner.py:48-160, 380-660` | `steps`, `current_step` (including `index`), `step_visits`, `for_each`, `repeat_until` | Names and positions: restarts at the first `ordered_execution_node_ids()` entry whose row is missing or not terminal (`:98-120`) |
| `orchestrator input get/answer/cancel` | `cli/commands/human_input.py:24-57`; `workflow/human_input.py:108-316` | `human_input` (`enclosing_step` {step_id, step_name, visit_count}, `loop_iteration` {kind, loop_step_id, iteration}, `runtime_step_id`); the guard reads `current_step`, `step_visits`, `for_each`, `repeat_until` (`:142-186`) | Names and positions. Takes `run.lock` and writes `state.json` |
| `orchestrator prompt` session lookup | `prompt_session_lookup.py:108-125, 205-221, 332-360` | `artifact_versions.omp_session[-1]` with `producer == step_id`, `producer_name == step name`, `step_index`; `provider_sessions/*` | Names and positions |
| Trial SDK | `workflow/trial/sdk.py:365-411` | `status`, `error`, `steps[*].status`, `steps[*].trial` | Neither (needs one completed row carrying `trial`) |
| Run-ref child reader | `workflow/run_ref/child.py:1061-1107` | child `status`, `workflow_outputs` | Neither |
| Language server | `orchestrator/lsp/` | none (no match) | Not a consumer |
| Watchdog probe (run by `workflows/library/generic_run_watchdog/watchdog.orc:192-194`) | `workflows/library/scripts/probe_orchestrator_run.py:57-175` | `status`, `updated_at`, `workflow_file`, top-level `steps[*]` | Names. Reports `FAILED` if any top-level row failed (`:93-94`) |
| Watchdog repair prompt | `workflows/library/prompts/generic_run_watchdog/repair_run_failure.md:35-38` | `steps` and `call_frames[*].state.steps` | Tells the agent where to look |
| Usage-limit watcher | `scripts/watch_workflow_usage_limit.sh:168-380` | `status`, `updated_at`, `current_step`, `workflow_file`, `bound_inputs` (to relaunch), `workflow_outputs.drain_status`, plus a regex over the whole state | Neither |
| Experiment coordinator | `scripts/experiments/conventional_coordinator.py:1139-1165` | `status`, `workflow_outputs` | Neither |

`RunState.from_dict` (used by resume and human input) requires
`schema_version`, `run_id`, `workflow_file`, `workflow_checksum`, `started_at`,
`updated_at` and `status`, and it validates `human_input`,
`provider_attempt_allocations` and `result_persistence_profile`
(`state.py:201-248`).

### C.3 Shared test helpers

| Helper | Modules importing it | Reads state? |
| --- | --- | --- |
| `tests/workflow_bundle_helpers.py` | 70 | No. It builds flat step lists from `bundle.projection`, including `repeat_until.steps` (`:122-225`, `:501-584`) |
| `tests/workflow_fixture_loader.py` | 66 | No |
| `tests/golden_state.py` | 2 | Yes: `steps[name]`, where a `[` in the key marks an iteration row (`:103-149`, `:183-195`) |
| `tests/workflow_lisp_characterization.py` | 2 | Yes. Its fake command executor picks behavior by step-name suffix (`:802-816`). The goldens are keyed by generated presentation keys (`…/golden/top_level_match_attempt.behavior.json:35-36`) |
| `tests/e2e/reporter.py` | 2 | `steps[step_name]` |

Of 476 `test_*.py` modules, 120 index `steps[...]`, 106 mention `state.json`,
55 `current_step`, 37 `step_visits`, 33 `call_frames` and 31
`artifact_versions`.

---

## D. Nested structured control

### D.1 The rule

| Message | Raised at | Condition |
| --- | --- | --- |
| `structured if/else is only supported on top-level steps in v2.2` | `validation.py:2113-2117` | `not top_level and not allow_nested` |
| `structured match is only supported on top-level steps in v2.6` | `validation.py:2352-2356` | same |
| `structured repeat_until is only supported on top-level steps in v2.7` | `validation.py:2606-2610` | same |

- **Versions in the messages.** They are constants, not the target: `statements.py:9-12`. At 2.33 the messages still say v2.2, v2.6 and v2.7.
- **Who may nest:**
  - `if` may be nested with `allow_nested_structured`, with a compiler-owned nested-if step id, or with a dedicated runtime-proof name (`validation.py:1351-1354`).
  - `match` may be nested under the same conditions except the step-id one (`:1374-1375`).
  - `repeat_until` always passes `allow_nested=False` (`:1406`).
- **Where bodies are validated:** branch and case bodies use `top_level=False` without the allowance (`:2081`, `:2290`, `:2544`). A `repeat_until` body uses `allow_nested_structured=True` (`:2688-2689`), so `if` and `match` are allowed inside a loop but a loop is not.
- **Other limits inside a loop body:** it may not contain `goto`, nested `for_each` or nested `repeat_until` (`:2650-2668`). `max_visits` "is only supported on top-level steps before stable internal IDs land" (`:1445-1447`).
- **The spec gives no reason.** It calls these "first tranche restrictions: top-level only" (`specs/dsl.md:238-239`, `:247-248`, `:262-266`). Refs have three scopes, `root`, `self` and `parent` (`specs/dsl.md:509-518`).

### D.2 Why the runtime assumes it

**Lowering.** `if` and `match` are flattened. `_lower_if_step` and
`_lower_match_step` (`workflow/lowering.py:722-830`, `:832-…`) emit, in order:
a marker per branch, the branch's child nodes, and a join node. The children
are registered into the enclosing region (`:812-814`, `:932-956`), keys are
`<stmt>.<branch>.<step>` (`:751`, `:984-985`), and branches are routed by
transfers (`:792-803`). `repeat_until` stays one node whose body gets no
`compatibility_index` (`:594-665`, `:510-534`).

**Keys.** Each key carries exactly one iteration ordinal:
`"{frame}[{i}].{nested}"` and `"{loop_node_id}#{i}.{suffix}"`
(`state_projection.py:14-15, 68-80`).

**Execution.**
- A join finds out which branch ran by reading the marker rows in `state["steps"]` (`executor.py:15160-15199`).
- Loop progress is stored once per loop: `state["repeat_until"][frame_key]`, with no outer-iteration part (`loops.py:450-465`).
- A loop's parent scope is recovered by a single `rsplit(".", 1)` on the step id (`loops.py:1817-1853`).

**Resume** restarts only at nodes that have a `compatibility_index` or a
`finalization_index` (`resume_planner.py:48-67`). A loop's body is re-entered
through its frame (`loops.py:371-389`).

What would break. This is read from the code; nothing was executed past validation.

| Nesting | What breaks |
| --- | --- |
| Loop in a loop body | The body dispatcher has no loop case, so the inner loop is **silently skipped** (`executor.py:8070-8071`). The one-ordinal keys cannot name it, the inner loop's progress record would be overwritten on each outer iteration (`loops.py:450-465`), and its body nodes cannot be resume targets (`resume_planner.py:63-67`) |
| Loop in a top-level branch | Lowering could register the frame in the enclosing region. The obstacles found are the one-level parent-scope recovery (`loops.py:1817-1853`), the `root`/`parent`/`self` ref grammar, and `max_visits` (`validation.py:1447`). **Whether it would run correctly is not established** |
| `if` or `match` in a branch | Lowering already flattens it (`lowering.py:812-814`). Only validation rejects it (`validation.py:1351-1375`) |

### D.3 How the WCC route meets the rule

- **A `case` becomes a structured `match` step** (`defunctionalize.py:3310-3496`).
  - The subject needs a producing step (`:3349-3361`, `wcc_lowering_route_unsupported`).
  - The arms are **hoisted** to top-level siblings placed *before* the match step (`return [*hoisted_steps, match_step]`, `:3486`). Each hoisted step is guarded by `when` on the producer's `variant` and by `requires_variant` (`:3043-3075`).
  - Hoisting happens only when one of these holds: the arm contains an `if` or `match` (`:3210-3214`, `:3430-3447`), the workflow is a generated private workflow, or compatibility-bridge inputs are present (`:723-725`).
- **An `if` becomes a structured `if` step** with nested `then` and `else` lists, and is never hoisted (`:3499-3712`).
- **A `rec-join` becomes `repeat_until`.** The body goes back to surface syntax (`:2920`) and is lowered by `lowering/control_loops.py:335`. Only one state parameter is supported (`:2809-2820`). A `rec-join` inside a loop body raises an uncaught `TypeError: unsupported WCC join binding during loop defunctionalization: WccRecJoin` (`:7205`).
- **Diagnostic code.** Shared-validation text is mapped to `workflow_boundary_type_invalid`, "provenance matched by message text fallback" (`lowering/origins.py:930-938`). The message does not say it is a compiler defect, although the design says it is one (`…middle_end.md:684-686`).

### D.4 Programs that hit the three messages (target 2.33)

Each program has the header `(workflow-lisp (:language "0.1") (:target-dsl "2.33") (defmodule <name>) (export entry) …)`.
The command, run from `/dev/shm/repairs-tmp/exec-design-research/secD`, is
`PYTHONPATH=<worktree> python -m orchestrator run <name>.orc --entry-workflow <name>::entry --command-boundaries-file commands.json <inputs> --dry-run`.
`commands.json` binds `tick` and `probe` as `external_tool`s. Each program
exits with code 2. The integrator reran all three and got the same exit codes;
the messages were re-checked for `d1` and `d3`.

1. `d1_if_in_if`, run with `--input a=true --input b=true`:
   ```lisp
   (defrecord Count (n Int))
   (defworkflow entry ((a Bool) (b Bool)) -> Count
     (if a
       (if b (command-result tick :argv ("python" "tick.py") :returns Count)
             (record Count :n 1))
       (record Count :n 0)))
   ```
   Output: `d1_if_in_if.orc:11:7: [workflow_boundary_type_invalid] Step 'd1_if_in_if::entry__then': structured if/else is only supported on top-level steps in v2.2`

2. `d2_match_in_if`, run with `--input a=true`:
   ```lisp
   (defunion Probe (YES (n Int)) (NO))
   (defworkflow entry ((a Bool)) -> Count
     (if a
       (match (command-result probe :argv ("python" "probe.py") :returns Probe)
         ((YES y) (command-result tick :argv ("python" "tick.py") :returns Count))
         ((NO n) (record Count :n 0)))
       (record Count :n 1)))
   ```
   Output: `Step 'd2_match_in_if::entry__then__match___wcc_effect_subject_1c40962faf830970': structured match is only supported on top-level steps in v2.6`

3. `d3_loop_in_if`, run with `--input go=true`:
   ```lisp
   (defworkflow entry ((go Bool)) -> Out
     (if go
       (loop/recur :max 3 :state (record Count :n 0)
         (fn (state)
           (let* ((c (command-result tick :argv ("python" "tick.py") :returns Count)))
             (if (< c.n 2) (continue (record Count :n c.n)) (done (record Out :n c.n))))))
       (record Out :n 0)))
   ```
   Output: `Step 'd3_loop_in_if::entry__then__loop': structured repeat_until is only supported on top-level steps in v2.7`

Other shapes that were run:

| Shape | Result |
| --- | --- |
| The loop of `d3` in a `match` arm | exit 2, message 3 |
| A loop bound with `let*` inside a loop body | exit 1, uncaught `TypeError … WccRecJoin` (`defunctionalize.py:7205`) |
| `match` in a `match` arm | exit 0. The inner match is hoisted ahead of the outer match, with a `requires_variant` guard |
| `if` in a `match` arm | exit 0. Hoisted |
| `match` in a loop body | exit 0. The markers and join sit in the frame's `body_node_ids` |
| The loop in a separate `defworkflow`, `call`ed from the `if` branch | exit 0: a call boundary gives the loop its own top level |
| The same loop in a `defproc` with `:lowering private-workflow` | exit 2, `proc_private_workflow_boundary_invalid` |
| A `match` arm holding an `if` and a loop | exit 2 at `--dry-run`: `[pure_result_replay_unavailable] … unknown result member; this is a compiler defect` (case d of the brief) |

---

## E. Pure expressions

### E.1 Operator catalog (`orchestrator/workflow/pure_expr.py:79-137`)

The frontend reads the same catalog (`workflow_lisp/typecheck_pure_ops.py:160`, `form_registry.py:18, 293`, `expressions.py:2981, 3078`).

| Operator | Group | Accepted types | Result | Lines (static / eval) |
| --- | --- | --- | --- | --- |
| `=` `!=` | equality | same type, one of String, Int, Bool, Symbol or enum. Float is refused (`pure_expr_float_equality_forbidden`), and so are unions | Bool | `1141-1161` / `1647-1659` |
| `<` `<=` `>` `>=` | ordering | Int×Int or Float×Float, not mixed | Bool | `1163-1178` / `1661-1678` |
| `and` `or` (≥2), `not` | boolean | Bool | Bool | `1180-1187` / `1680-1692` |
| `+` `*` (≥2), `-` (exactly 2, no unary minus), `min` `max` (≥2) | arithmetic | Int only | Int | `1189-1192` / `1694-1711` |
| `string/concat` (≥2) | string | String; a path operand is refused | String | `1194-1202` / `1713-1718` |
| `string/empty?`, `symbol/name` | string | String / Symbol | Bool / String | `1204-1210` |
| `some?`, `or-else` | option | `Optional[T]`; `Optional[T]`, `T` | Bool / `T` | `1212-1235` |
| `record-update` | record | surface head only; it becomes a `record_update` node (`:554-568`). As an `op` node it is refused (`:1268`) | – | – |
| `list/empty?` `list/head` `list/rest` `list/append` `list/length` | list (schema ≥2) | `List[T]` | Bool, `Optional[T]`, `List[T]`, `List[T]`, Int | `1237-1266` / `1743-1803` |

- **Node kinds** other than `op` (`pure_expr.py:25-49`):
  - schema 1: `literal`, `binding`, `field_access`, `if`, `record`, `union`, `record_update`;
  - schema 2 adds `list`, `list_map`, `path_join_under`, `list_nonempty_head`;
  - schema 3 adds `let`.
- **No conversion operators** exist between Int, Float and String.
- **The type rules exist in four places:** static typing (`:1137-1272`), evaluation (`:1640-1809`), the frontend check (`typecheck_pure_ops.py:152-477`) and `defunctionalize.py:4180`.
- **Integer overflow.** Values are Python integers checked against signed 64-bit bounds (`:22-23`). `_checked_int` (`:2017-2024`) raises `pure_expr_overflow` with `{min, max, value}`. The check runs after each partial result of `+` and `*`, after `-`, on `list/length` (`:1700-1707`, `:1803`), and on every Int that enters (`:1821-1824`).
  - A literal overflow fails at compile time (ran: `ovf.orc` gives `[pure_expr_overflow]`).
  - An input overflow fails at run time as a step error (ran: `--input n=9223372036854775807`).

### E.2 Float

| Source | Admitted by | NaN and infinity |
| --- | --- | --- |
| Workflow input `type: float` | `bind_workflow_inputs` → `validate_contract_value`, which uses `float(raw)` (`signatures.py:39-90`; `output_contract.py:1021-1029`, `:1214-1225`) | **Accepted** (ran: `nan`, `inf`, `1e400`). The run with `x=nan` completed, and `state.json` holds `"x": NaN` |
| `output_bundle` field `type: float` (command or provider) | `validate_output_bundle` (`output_contract.py:535`); `_load_bundle_json` rejects `NaN` and `Infinity` **only if the contract contains a `value` field** (`:563-565`, `:703`, `:1412-1421`) | **Accepted** for plain float fields (ran: JSON `NaN`, `Infinity`, `"nan"`, `"inf"`, `1e400`) |
| `expected_outputs` file `type: float` | `_parse_output_value`, `float(raw)` (`output_contract.py:992, 1021`) | Accepted |
| `type: value` leaf | `_validate_transportable_value` (`output_contract.py:1278-1296`; `specs/io.md:27-35`) | Rejected |
| Private typed transport | `type_descriptor.py:799-837` (Float at `:823-831`) | Rejected: "is not a finite Float" |
| `.orc` literal | The reader matches only `-?(\d+\.\d*\|\d*\.\d+)`, so no exponent, inf or nan (`reader.py:19, 364-365`). Elsewhere: "float literals are only supported in `defworkflow` parameter defaults" (`expressions.py:1188-1202`). Result-guidance examples also accept floats (`result_guidance.py:233-238`) | Always finite |
| Pure evaluator | `_coerce_value` checks the type only (`pure_expr.py:1825-1828`) | NaN and inf pass through. `canonical_json_for_pure_value` uses `allow_nan=False` (`:157-166`), so an uncaught `ValueError` is raised at the digest and bundle writes (`steps/pure_projection.py:74-77`, `:149`). The `derived_pure_replay.v1` profile skips both (`:43-77`) |

- **Operators that accept Float:** only the four orderings, with Float on both sides. Every ordering against NaN returns `false` (ran). Elsewhere a Float can only be carried: bound, stored in records and unions, returned from `if` arms and `or-else`.
- **Serialization.**
  - `state.json` is written with `json.dumps(…, indent=2)`, which keeps the default `allow_nan=True` and writes floats with Python `repr` (`state.py:752`). NaN is written as the non-standard token `NaN` and is read back by plain `json.load` (`:508`).
  - Pure bundles and digests use canonical JSON with `allow_nan=False` (`pure_expr.py:157-166`). So do `persisted_surface.py:168, 1413`, `prompt_identity.py:205` and `transition_contract.py:187`.
  - `provider_phased_delivery/frames.py:39` and `coordinator.py:168` use `allow_nan=True`.
- **Why float literals are accepted only in defaults.** No document gives a reason.
  - The guard came in commit `a47703e4` (2026-06-02). Its message calls it "the float-literal parser guard from the prior review revision".
  - Before that commit, a float literal in an expression crashed with `TypeError("unsupported expression datum")` (`a47703e4^:…/expressions.py:542`).
  - The frontend specification lists `floats 0.25` as a lexical atom with no restriction (`docs/design/workflow_lisp_frontend_specification.md:727`).

### E.3 The 256-node bound

- **Definition and enforcement.** Defined at `pure_expr.py:21` and enforced only in `validate_pure_expr_payload` (`:220-231`). No caller overrides `max_nodes`.
- **When it runs.**
  - At compile time: `lowering/pure_projection.py:413`, `wcc/defunctionalize.py:5849, 6101`, `executable_ir.py:1720, 1942` and `transition_contract.py:285-329`.
  - At run time, on **every evaluation**, because `evaluate_pure_expr` validates first (`:257`). Its callers are `steps/pure_projection.py:114`, `transition_executor.py:174-443`, and the peer-group and supervision bindings.
- **What counts** (`_validate_expr_node`, `:459-726`).
  - Each expression mapping counts 1, leaves included. Type descriptors and `bindings` declarations do not count.
  - `let` counts 1, plus each bound value once, plus the body.
  - `list_map` counts its body once. The bound limits payload size, not evaluation cost.
- **Reuse through `let*`** depends on how the value was bound (ran).
  - A binding to an operator expression is **copied at each use**: `letuse85.orc` compiles, `letuse86.orc` fails, which fits 1 + 3·uses nodes. The copying is at `lowering/pure_projection.py:628-658`.
  - A nested `let*` inside an expression was also copied at 2.33 (`nestedlet100.orc` fails). The branch that emits a `let` node is gated at ≥2.30 (`:532-575`) and was not reached on this route.
  - A binding to a pure procedure call gets its own `pure_projection` step, and each use counts 1 (`procuse100.orc` compiles).
- **Diagnostic.**
  - At compile time: `[pure_expr_payload_too_large] pure-expression payload exceeds the maximum node count`. The count and the limit are dropped (`lowering/pure_projection.py:1610-1627`).
  - At run time, the step failure keeps `{node_count, max_nodes}` (`steps/pure_projection.py:124-134`).
- **Origin.** `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps/workflow-lisp-generic-core-g1-pure-expression-core/implementation_architecture.md:328-330` says: "Compile-time bounds: maximum node count per payload (initial bound 256 nodes, enforced with `pure_expr_payload_too_large`)." **No reason is given.** The design states only the principle "bounded payload size fixed at compile time" (`docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md:555`). The implementing commit is `309c8645`. No spec states the bound.

### E.4 Criteria for adding to the pure surface

- From `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`:
  - §7 `:459-462`: "every pure operator is total over its typed domain or fails closed with a typed diagnostic"; "No ambient effects in pure expressions: no IO, filesystem, clock, randomness, provider, workflow, command, or network effects."
  - §7 `:468-469`: "Surface growth is census-driven. New operators and helpers require a verified adapter behavior or fixture that the existing surface cannot express."
  - §8.4 `:549-555`: "no recursion into user code; no loops except structural traversal of the payload; no IO; no ambient state; and bounded payload size fixed at compile time."
  - §10.2 `:645-654`: "no division/modulo until justified; no float equality; no path string concatenation; no deep record equality; no union equality; no collection operators; and no regex or broad string processing." The collection exclusion was later relaxed by the target-2.18 list surface.
  - §10.3 `:658-665`: "strict typing and no implicit coercion; 64-bit integer arithmetic with fail-closed overflow diagnostics; deterministic evaluation independent of step order; … one runtime interpreter is the authoritative semantics."
  - §10.5 `:684`: "Every operator has a G0 census or fixture justification."
- From `docs/lisp_workflow_drafting_guide.md` §9A (`:1916-1942`): "There is deliberately no division, float equality, path-string concatenation, collection operators, regex, time, randomness, or IO. If a workflow seems to need one of those, that is a design question for the adapter-retirement target …, not a reason to fall back to a command step or grow the surface informally." The guide's operator table leaves out the five list operators.
- From `docs/design/workflow_lisp_frontend_specification.md` §10.2 (`:1593-1624`): "Supported operators are exact and closed". It also says "Maximal runtime-visible pure regions lower through WCC/schema 2 into one generated `pure_projection` step" (`:1598-1601`).

---

## F. Concurrency that exists

### F.1 Supervision and peer groups

| | `with-live-providers` (2.16) | peer group (2.17) |
| --- | --- | --- |
| How many at once | At most 2 provider processes (worker and supervisor) on `ThreadPoolExecutor(max_workers=2)` (`provider_supervision/coordinator.py:283-296`) | 2 to 8 members (`provider_peer_group/models.py:374, 1330`) on `ThreadPoolExecutor(len(members))` (`coordinator.py:223-226`), started through terminal adapters (`:504-533`) |
| Scheduler | A coordinator inside one node. Attempt allocation, prompt snapshots and path preflight run one after another before launch (`coordinator.py:225-281`); it settles once (`:371-397`) | A single-writer coordinator draining one event queue. "Member threads and endpoint listeners may not mutate `StateManager`, attempts, ledgers, artifacts, variables, or terminal group state" (`docs/design/workflow_lisp_provider_peer_messaging.md:514-535`) |
| What member threads do | Only `provider_executor.execute(…, cwd=executor.workspace)` (`provider_supervision/bindings.py:1151-1168`). The design says "the executor is not reentrant" (`docs/design/workflow_lisp_provider_live_binding.md:301-303`) | Launch with `cwd=executor.workspace` (`provider_peer_group/bindings.py:1003`) |
| Results | One path per visit, member and turn, under the run root, which must be absent before launch (`bindings.py:547-597`) | `provider-peer-group/<node>/visits/{visit}/members/<m>/provisional-result.json`, which must be absent (`paths.py:247-301`; `specs/io.md:188-194`) |
| State | One `current_step` of type `provider_supervision`, asserted at start and before finalizing (`bindings.py:507-528`); one settlement (`:1243-1280`); visit metadata files (`executor.py:3216-3288`) | One group `current_step`; visit metadata (`executor.py:3331-3407`) |
| Resume after interruption | Detected at `resume_planner.py:480-599` as `rerun_interrupted_visit`. The partial visit is discarded and its ordinal kept as spent (`executor.py:3772-3862`). A fresh visit follows; members are not resumed individually (`live_binding.md:213, 319`) | Same guard (`executor.py:4623-4668`). "The whole form owns one checkpoint" (`peer_messaging.md:575-595`) |

### F.2 `trial` and `run-ref`

- **run-ref runs nothing concurrently.**
  - The child is a blocking `subprocess.run` (`run_ref/runtime.py:524-566`).
  - It runs in a fresh `git clone --no-local` with a detached checkout, at a path that must not already exist (`run_ref/source.py:1029-1100`), under `run_ref_root/…/visit-<digest>/…` (`runtime.py:1525-1560`).
  - The child has its own state root and its own run lock (`child.py:1060-1078`).
  - The result comes back as stdout JSON carrying `workflow_outputs` (`child.py:1085-1127`).
  - The child's workspace delta is recorded as evidence and not applied to the parent (`runtime.py:2591-2613`).
- **trial runs up to `max_concurrency` arm cells at once** on a thread pool (`trial/runtime.py:853-939`).
  - Each cell is one run-ref child in its own clone. Evaluators also run concurrently, each in `evaluator_workspace/<label>` (`trial/evaluation.py:642-700`).
  - Workers post proposals to a queue. The coordinator thread writes the ledger and commits in cell order (`trial/runtime.py:776-822, 943-1003`).
  - An interrupted arm is a failed attempt: it gets a fresh ordinal and runs again (`docs/design/workflow_lisp_trial_runs.md:310-317`).
- **Adjudicated provider** runs its candidates one after another, each in a copied workspace (`adjudication_candidates.py:20-29`; `adjudication/baseline.py:112-120`).

### F.3 `list/map-effect`

- **It runs in sequence.** The typechecker rewrites it into a `loop/recur` with state `remaining` and `results` (`typecheck_structural_values.py:579-672`). The spec says it adds no scheduling node (`frontend_specification.md:1637-1650`).
  - Run: three calls happened in input order, and `repeat_until[…].completed_iterations = [0,1,2]`.
- **How each call is keyed.**
  - A direct call: `steps["grt/entry::run__loop[<i>].grt/entry::run__body.else.grt/entry::run__body__else____list_map_effect_result__probe"]`.
  - A call through a procedure also gets a call frame `root.grt_entry_run__loop#<i>.grt_entry_run__loop__iteration.<call step>::visit::1` (`calls.py:229-249`).

### F.4 Two effects at once in one workspace

- **Yes: supervision (2 processes) and peer groups (2 to 8)**, all launched with `cwd=executor.workspace`.
  - Result files are kept apart by distinct run-root paths per visit, member and turn, each required absent (`specs/io.md:166-194`).
  - State is written only by the coordinator.
  - Member writes to the workspace are not isolated. "filesystem transactionality or rollback of member workspace writes" is a non-goal (`live_binding.md:218`).
- **Other threads in one process.** The heartbeat thread rewrites `state.json` (`executor.py:5880-5895`). Async summary provider calls run in daemon threads (`observability/summary.py:80-89`).
- **Across runs, nothing stops two runs from sharing a workspace.**
  - A strict xfail records that concurrent runs share the promoted-call result path, and that the second run's pre-launch removal deletes the first run's file (`tests/test_workflow_result_file_freshness.py:419-446`).
  - The workspace lock is Task 12 of the repairs plan and is not implemented (`docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md:422-440`).

### F.5 Writing `state.json`

- **Every write is a whole rewrite** of `RunState` (`state.py:744-756`).
- **Atomic replace:** a temp file `.orc-tmp-<pid>-<rand>.tmp` opened with `O_EXCL`, then `os.replace`, with **no fsync** (`_common/io_atomic.py:13-16, 54-75, 181-194`).
- **Within one process**, writes are serialized by `threading.RLock` (`state.py:461, 497-526, 528-613, 1162-1179`).
- **Across processes**, a non-blocking `flock` on `run.lock` (`run_lock.py:51-92`) is taken by run, resume and human input. `orchestrator report` is the exception: it writes without the lock (C.2).
- **Two effects finishing at once** in one process: the lock orders both writes onto one in-memory state, so nothing is torn or lost. But the cursor has one slot: `current_step` holds a single step (`specs/state.md:56-57`), and `update_step` clears it only when the name matches (`state.py:1173-1177`). Two processes writing without the lock: the last whole-file replace wins.

---

## G. Where steps write

| Mechanism | What it declares | Where the write lands | Checks |
| --- | --- | --- | --- |
| `defpath … :under` (`docs/lisp_workflow_drafting_guide.md:695-725`) | A type contract on relpath values. Allocates nothing | Wherever the value points | At run time, `_validate_relpath_value`: inside the workspace, inside `:under`, `must_exist_target` (`output_contract.py:1478-1543`). No comparison across steps |
| `:path :out` prompt fill (2.21) | One output file whose path comes from a fill | A path the author chooses | Compile time: names disjoint from the structured result (`validation.py:7163-7217`). Run time: rendered path equals expected, destinations pairwise disjoint (`output_contract.py:207-306`; `executor.py:12243-12257`). All of this is **within one call** |
| Generated `__write_root__<step_id>__result_bundle` (`generated_paths.py:113-135`; `defunctionalize.py:3366`) | Entry-level result file | `.orchestrate/workflow_lisp/entry/<run_id>/<wf>/<input>.json` (`state_layout.py:177-192`; bound at `executor.py:4035-4060`). **Names the run, not the iteration**: run 1 reused one file for iterations 0 to 2 | Removed before every command and composed provider call. Errors: `stale_bundle_removal_failed`, `missing_bundle_file` (`executor.py:7457-7491`; `specs/io.md:152-172`) |
| Promoted-call write root (`generated_paths.py:138-178`) | Result file of a procedure call | `.orchestrate/workflow_lisp/calls/<wf>/<call>/<iteration>/<callee>/<input>.json`. **Names the iteration, not the run**: run 2 produced `/0/`, `/1/`, `/2/` | Same removal. Shared across runs (the xfail above) |
| Supervision and peer provisional bundles | Visit, member and turn templates | Run root | Must be absent |
| `writes` effect | `WriteEffect(subject=tuple[str, …])` (`workflow_lisp/effects.py:33, 453`), a symbol, not a path | – | Appears only in effect summaries; its only consumer outside `effects.py` is `typecheck_resource_view.py:404` |

There is **no general check, at compile time or at run time, that two steps
do not write the same path.** The checks that exist are narrower:

- **Call write roots** (`validation.py:3690-3766`) compare the syntactic binding (same literal or same ref) across `call` sites. Inside a loop they reject a binding that stays the same on every visit. Paths are not resolved.
- **`score_ledger_path`** is compared only with the same step's own outputs (`validation.py:3250-3292`).
- **Artifact names**, not paths, are checked by `publish_artifact` (`validation.py:5449-5470`) and by `session_artifact_collision` (`lowering/effects.py:715`).
- **The WCC "source owner collision" errors** concern provenance keys (`defunctionalize.py:4461, 4709, 5749, 5994`).
- **`StateLayout.allocate`** is a pure function with no registry (`state_layout.py:204-249`). A second allocation with the same path template overwrites the first in `generated_path_spans` without an error (`generated_paths.py:78`; `defunctionalize.py:1167`).
- **Match arms share one union bundle path** on purpose (`lowering/control_match.py:366`).
- **Authored paths** are never compared with generated paths or with each other across steps.

---

## Facts That Would Make the Proposal Hard

These are things a runtime that evaluates WCC directly would have to rebuild,
or that depend on steps being flat.

**Identity**
1. **A WCC `node_id` is not a site across inlining.** One procedure body inlined at N call sites gives N effects with the same `node_id` and `scope_id`. Only the step-name ordinals `execute_1/_2/_3` tell them apart, and those come from a mutable counter (A.5; `defunctionalize.py:6690-6715, 6755-6764`). Callee bodies are not in the WCC program: they are elaborated during defunctionalization (A.4). An identity made of site plus activation path needs call sites that WCC does not record today.
2. **Current identities change under formatting edits and file moves.** Step ids, checkpoint ids and binding digests all changed when blank lines were added or the file was moved. The inputs are `repr(TypeRef)` (which contains source paths), span offsets and span line/column (A.5, measured). This breaks the design's own rule (`…middle_end.md:342-343`).
3. **Visit counts are built into every durable identity:**
   - provider attempt scopes (`provider_attempts.py:205-295`);
   - human input (`human_input.py:108-186`);
   - run-ref and trial visit keys (`executor.py:6270-6354`);
   - call frames `…::visit::<n>` (`calls.py:220-249`);
   - `{visit}` paths for supervision and peer groups;
   - `provider_sessions/<step_id>__v<visit>`.

   All of these read `step_visits[presentation_key]`.
4. **Keys hold one iteration ordinal.** `frame[i].step` and `loop#i.suffix` (`state_projection.py:14-15, 68-80`). Loop progress is one record per loop (`loops.py:450-465`). Parent scope is recovered by a single `rsplit` (`loops.py:1817-1853`). Iteration identity is spread over `steps[...]`, `repeat_until.<loop>` and call-frame ids, and no single activation-path key exists (F.3).

**Execution configuration exists only after WCC, keyed by step**

5. The following are computed in `lowering/effects.py`, `generated_paths.py` and `defunctionalize.py`, not in WCC, and all are keyed by step name or step id:
   - output contracts and result bundle paths;
   - prompt source files, typed prompt input rows and fragment contracts;
   - prompt dependency contracts;
   - provider policy rendering and timeouts;
   - checkpoint points and resume policies;
   - `managed_write_roots` steps.

   WCC holds only the type and the atoms (A.4).
6. **Some payloads are frontend AST, not calculus:** `resource_transition`, `materialize_view`, `finalize_selected_item`, `produce_one_of` candidates, and `WccOpaqueFrontendValue` (loop state, lists, `path/join-under`, bundle path) (A.1, A.2). Provider policy and prompt fills in `operation_payload` are not ANF-normalized (A.3). Nothing checks ANF invariants at run time, only in tests.
7. **Loop bodies are never executed from WCC.** They are converted back to surface syntax and lowered by the older loop lowerer. A nested `rec-join` crashes with a `TypeError` (A.4, D.3). `list/map-effect` has no WCC node; it is a typecheck rewrite to a loop (A.2).
8. **No effect site list exists.** `effect_summary` on a node is the whole body's summary, and `allocation_requests` is always empty (A.1).
9. **Values reach effects as step-name templates,** `${root.steps.<step>.artifacts.return__value__<field>}` (A.4). Workflow outputs are resolved through `root.steps.<key>.artifacts.<name>` refs (`signatures.py:130-140`).

**Runtime entanglement**

10. **Every effect resolves its inputs through refs into `state["steps"]`.** Performers take the whole `state`, and there is no path that reads values from an environment (B). Only three leaves are independent of the executor: `StepExecutor.execute_command`, `ProviderExecutor.prepare_invocation/execute` and `execute_transition` (B.1).
11. **Six effect kinds commit state themselves under cursor guards:** phased provider, run-ref, trial, request_input, supervision and peer group (B.1). Four of them run only at top level, and the loop-body dispatcher silently skips nested loops, run-ref and trial (`executor.py:8042-8071`).
12. **A workflow call is a full child `WorkflowExecutor`** with nested state in `call_frames` (`calls.py:1224-1279`).
13. **Resume is positional.** It restarts at the first `ordered_execution_node_ids()` entry whose `steps[presentation_key]` row is missing or not terminal, and only at nodes with a `compatibility_index` (`resume_planner.py:48-120`). The integrity audit requires every row to match a slot in the current flat projection (`resume_projection_integrity.py:132-200`).
14. **Commands record no resolved input and nothing per attempt.** The result does not include argv, logs are keyed by step name and overwritten (B.1), and `.orc` lowering emits no `retries`. Only resource transitions (idempotency key) and run-ref (input digest) record anything derived from their input.

**Consumers of run state**

15. The following all depend on `steps` keyed by presentation key, on `current_step`, on `step_visits`, on the `repeat_until`/`for_each` maps and on the flat projection order (C.2): report, dashboard, monitor, human input, prompt session lookup, watchdog probe and prompt, and the usage-limit script. Liveness is read only from `current_step` heartbeats. Log and session files are named after steps. The order of rows in `steps` carries meaning.
16. **Tests are keyed to flat, named steps.** 120 of 476 test modules index `steps[...]`. The goldens use generated presentation keys, and the characterization harness chooses fake command behavior by step-name suffix (C.3).

**Concurrency and state writes**

17. **One cursor per state document.** The executor is not reentrant (`live_binding.md:96-99, 301-303`). Concurrency exists only inside one node whose coordinator is the single writer (F.1). A memo holding several effects in flight has nowhere to record them in today's state.
18. **`state.json` is rewritten whole on every change, heartbeats included, with no fsync** (F.5). A memo stored there would be rewritten in full on every heartbeat. `orchestrator report` also writes the file without the run lock (C.2).
19. **Trial and run-ref have their own ledgers and ordinals** with commit ordering by a coordinator (F.2). An evaluator would have to treat each of them as one opaque effect or re-key those ledgers.

**Values and floats**

20. **The pure evaluator works on serialized payloads,** with explicit `bindings`, type descriptors and a 256-node bound checked on every evaluation. It does not work on WCC terms (E.3). The bound counts a maximal pure region, with operator-expression `let*` bindings copied per use. A lexical environment would change what the bound means. The operator type rules exist in four copies (E.1).
21. **NaN and infinity enter through `type: float` inputs and bundle fields,** and are stored as `NaN` in `state.json`. Canonical JSON (`allow_nan=False`) raises `ValueError` on them (E.2). A memo keyed on canonical-JSON input digests would fail on such values unless the boundary rejects them first.

**Workspace**

22. **Result paths are positional.** The entry bundle path names the run but not the iteration, and the promoted-call write root names the iteration but not the run. Both are removed before each call (G). A memo keyed by effect identity needs result paths derived from that identity.
23. **Workspace writes are not modeled.** No check makes different steps write disjoint paths. Live-provider members share the workspace with no isolation. No workspace lock exists, and runs in one workspace collide (F.4, G). Evaluating again from the entry can trust only validated bundles, never workspace files.

---

## H. Two Experiments On The Search Controller

The controller is the `.orc` program of a paired comparison of one search
written in `.orc` and in Python: two branches, repair of an invalid
candidate, a stall count per branch and one fusion. Its state is a record of
14 fields. The Python version runs and solves its task in 10 evaluations.

Both experiments ran on a copy of the program, outside its author's
worktree.

| Experiment | Result |
| --- | --- |
| Compile with the repairs branch in place of `main` | The same refusal: `pure_expr_payload_too_large` at the state update of the repair branch. 361 nodes against 256 |
| Compile with the bound raised to 100,000 | A different refusal: `structured repeat_until is only supported on top-level steps in v2.7`, for the search loop, which sits in the `else` branch of the check of the budget |

The size bound was hiding the rule of section D. Raising the bound does not
make the program run.

Forms its author tried before the final one, with what each met:

| Form | Met |
| --- | --- |
| One helper with effects for both branches, called inside `continue` | `TypeError: unsupported WCC elaboration node: ProcedureCallExpr` |
| The helper bound before `continue` | The size bound |
| Explicit cases inside the helper | `ValueError: pure boolean conditions require WCC pure-projection lowering` |
| A conditional that contains commands, bound to a name | `workflow_return_not_exportable`, unsupported `let*` binding |
| Explicit cases in the loop, each ending in `continue`, one copy of the code per branch | The size bound |

Other limits the same work met:

| Limit | Kind |
| --- | --- |
| A computed record is refused as a command input: `command_adapter_input_not_projectable` in `:inputs`, `workflow_return_not_exportable` in `:argv` | Transport |
| `(list/length state.history)` is refused as a command argument | Position |
| A decimal literal is refused in an expression | Surface |
| A command that writes no result in its second iteration receives the result of the first | Runtime defect; the repairs plan removes the stale file before each call |
| No parallel map over commands | Absent capability |
