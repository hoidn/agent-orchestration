# Acceptance Tests (Normative)

- Conformance areas
  - DSL validation: version gating, mutual exclusivity, `goto` target validation, strict unknown-field rejection.
  - Variable substitution: namespaces, escapes, undefined variable handling.
  - Dependency resolution: required vs optional, glob behavior, deterministic ordering.
  - Injection (v1.1.1): modes, default instruction, prepend/append position, truncation record.
  - IO capture: modes, limits, tee semantics, JSON parse behavior and `allow_parse_error`.
  - Providers: argv vs stdin, placeholder validation, unresolved placeholders, parameter merge.
  - Adjudicated providers (v2.11): version gating, candidate isolation, same-trust-boundary evaluator evidence, selection, promotion, ledger ownership, and stdout suppression.
  - Deterministic artifact contracts: `expected_outputs`/`output_bundle` validation, typed parsing, publish/consume lineage, and contract violation handling.
  - Wait-for: exclusivity, timeout semantics, state metrics.
  - State integrity: atomic writes, backups, resume/repair, checksum.
  - CLI safety: `--clean-processed` & `--archive-processed` constraints.
  - Security: path safety, secrets handling and masking.

- Mapping to modules
  - See `dsl.md`, `variables.md`, `dependencies.md`, `io.md`, `providers.md`, `queue.md`, `state.md`, `cli.md`, `security.md`, `observability.md`.

- Future acceptance (planned)
  - v1.2 lifecycle: per-item success/failure moves; idempotency and resume.
  - Future JSON stdout validation assertions: schema pass/fail, require-pointer assertions, variable substitution in schema path.

## Canonical List (v1.1 + v1.1.1)

1. Lines capture: `output_capture: lines` → `steps.X.lines[]` populated
2. JSON capture: `output_capture: json` → `steps.X.json` object available
3. Dynamic for-each: `items_from: "steps.List.lines"` iterates correctly
4. Status schema: Write/read status.json with v1 schema
5. Inbox atomicity: `*.tmp` → `rename()` → visible as `*.task`
6. Queue management is user-driven: Steps explicitly move tasks to `processed/{ts}/` or `failed/{ts}/` (orchestrator does not move individual tasks)
7. No env namespace: `${env.*}` rejected by schema validator
8. Provider templates: Template + defaults + params compose argv correctly (argv mode)
9. Provider stdin mode: provider with `input_mode: "stdin"` receives prompt via stdin and does not require `${PROMPT}`
10. Provider/Command exclusivity: Validation error when a step includes both `provider` and `command`
11. Clean processed: `--clean-processed` empties directory
12. Archive processed: `--archive-processed` creates zip on success
13. Pointer Grammar: `items_from: "steps.X.json.files"` iterates over nested `files` array
14. JSON Oversize: >1 MiB JSON fails with exit 2
15. JSON Parse Error Flag: The same step succeeds if `allow_parse_error: true` is set
16. CLI Safety: `run --clean-processed` fails if processed dir is outside WORKSPACE
17. Wait for files: `wait_for` blocks until matches or timeout
18. Wait timeout: exits 124 and sets `timed_out: true`
19. Wait state tracking: records `files`, `wait_duration_ms`, `poll_count`
20. Timeout (provider/command): enforces `timeout_sec` and records 124
21. Step retries: provider steps retry on 1/124 per policy; raw commands only when `retries` set
22. Dependency Validation: missing required fails with exit 2
23. Dependency Patterns: POSIX glob matching
24. Variable in Dependencies: substitution before validation
25. Loop Dependencies: re-evaluated each iteration
26. Optional Dependencies: missing optional omitted without error
27. Dependency Error Handler: `on.failure` catches validation failures (exit 2)
28. Basic Injection: `inject: true` prepends default instruction + file list
29. List Mode Injection: correctly lists all resolved file paths
30. Content Mode Injection: includes file contents with truncation metadata
31. Custom Instruction: `inject.instruction` overrides default text
32. Append Position: `inject.position: "append"` places injection after prompt content
33. Pattern Injection: globs resolve to full list before injection
34. Optional File Injection: missing optional files omitted from injection
35. No Injection Default: without `inject`, prompt unchanged
36. Wait-For Exclusivity: step combining `wait_for` with `command`/`provider`/`for_each` is rejected
37. Conditional Skip: false `when` → `skipped` with `exit_code: 0`
38. Path Safety (Absolute): absolute paths rejected at validation
39. Path Safety (Parent Escape): `..` or symlinks escaping WORKSPACE rejected
40. Deprecated override: `command_override` usage rejected
41. Secrets missing: missing declared secret yields exit 2 and `missing_secrets`
42. Secrets masking: secret values masked as `***` where feasible
43. Loop state indexing: results stored as `steps.<LoopName>[i].<StepName>`
44. Provider params substitution: variable substitution supported in `provider_params`
45. STDOUT capture threshold: `text` > 8 KiB truncates state and spills to logs
46. When exists: `when.exists` true when ≥1 match exists
47. When not_exists: `when.not_exists` true when 0 matches exist
48. Provider unresolved placeholders: `${model}` missing value → exit 2 with `missing_placeholders:["model"]`
49. Provider stdin misuse: `input_mode:"stdin"` with `${PROMPT}` → validation error (`invalid_prompt_placeholder`)
50. Provider argv without `${PROMPT}`: runs and does not pass prompt via argv
51. Provider params substitution: supports `${run|context|loop|steps.*}`
52. Output tee semantics: `output_file` receives full stdout while limits apply to state/logs
53. Injection shorthand: `inject:true` ≡ `{mode:"list", position:"prepend"}`
54. Secrets source: read exclusively from orchestrator environment; empty strings accepted
55. Secrets + env precedence: `env` wins on conflicts; still masked as secret
56. `expected_outputs` schema: loader rejects missing `name|path|type`, invalid `type`, duplicate `name`, invalid `inject_output_contract` type, and invalid `persist_artifacts_in_state` type
57. Output contract success: validated values persist under `steps.<Step>.artifacts.<name>` with typed parsing (`enum|integer|float|bool|relpath`)
58. Output contract required/optional: missing file fails by default; `required:false` allows omission without populating artifact key
59. Output contract sequencing: contract validation runs only when execution exit code is `0`
60. Output contract preserves execution failures: non-zero execution results are not replaced by contract errors
61. Contract violation shape: failed step exposes `error.type:"contract_violation"` and `error.context.violations[]`
62. Provider prompt contract suffix: provider steps with `expected_outputs` append deterministic `Output Contract` block by default
63. Prompt suffix opt-out: `inject_output_contract:false` disables provider suffix injection
64. Command compatibility: command steps accept `inject_output_contract` with no behavior change
65. Artifact mirror opt-out: `persist_artifacts_in_state:false` still enforces `expected_outputs` but omits `steps.<Step>.artifacts` from `state.json`
80. v1.2 loader gating: top-level `artifacts` rejected below `version: "1.2"`
81. v1.2 loader gating: step `publishes`/`consumes` rejected below `version: "1.2"`
82. v1.2 publish contract: `publishes.from` must reference local `expected_outputs.name`
83. v1.2 publish contract: `publishes` pointer/type must match artifact registry contract
84. v1.2 consume contract: producer filters must reference steps that publish requested artifact
85. v1.2 runtime publish ledger: successful publisher appends deterministic version record under `artifact_versions`
86. v1.2 runtime consume policy: `latest_successful` resolves newest matching artifact publication
87. v1.2 runtime freshness: `since_last_consume` fails on stale artifact version
88. v1.2 runtime materialization: successful consume writes selected value to canonical artifact pointer file
89. v1.2 runtime failure shape: missing/stale consume preflight fails with `exit_code:2` and `error.type:"contract_violation"` before step process execution
90. v1.2 provider consumes injection: provider steps with `consumes` inject deterministic `Consumed Artifacts` block by default
91. v1.2 provider consumes opt-out: `inject_consumes:false` disables consumed-artifacts prompt injection
92. v1.2 provider consumes position: `consumes_injection_position: append` places consumed-artifacts block after prompt body
93. v1.2 consumes prompt provenance: injected values must match resolved consume selection (latest publication under producer/policy filters)
94. v1.2 loader guardrail: reject steps that combine `publishes` with `persist_artifacts_in_state:false`
95. v1.2 prompt consume scope: `prompt_consumes` injects only listed consumed artifacts
96. v1.2 prompt consume back-compat: omitting `prompt_consumes` injects all resolved consumed artifacts
97. v1.2 prompt consume suppression: `prompt_consumes: []` injects no consumed-artifacts block
98. v1.2 scalar artifact schema: `artifacts.<name>.kind: scalar` supports `enum|integer|float|bool` and rejects relpath-only fields
99. v1.2 scalar runtime consume: scalar consume preflight enforces freshness without pointer-file materialization
100. v1.3 loader gating: step `output_bundle`/`consume_bundle` rejected below `version: "1.3"`
101. v1.3 loader exclusivity: step cannot declare both `expected_outputs` and `output_bundle`
102. v1.3 output bundle runtime: successful step validates/extracts `output_bundle.fields[*]` into `steps.<Step>.artifacts`
103. v1.3 output bundle runtime failure: missing/invalid bundle yields `exit_code:2` with `error.type:"contract_violation"`
104. v1.3 consume bundle runtime: successful consume preflight writes JSON bundle to `consume_bundle.path`
105. v1.3 consume bundle subset: `consume_bundle.include` limits emitted keys to selected consumed artifacts
106. v1.3 strict review gating policy: workflow branch decisions consume strict published assessment/review artifacts, not raw execution prose logs
107. v1.5 loader gating: step `assert` rejected below `version: "1.5"`
108. v1.5 assert exclusivity: `assert` cannot be combined with `provider|command|wait_for|for_each`
109. v1.5 assert runtime: false assertion fails with `exit_code:3` and `error.type:"assert_failed"`
110. v1.5 assert routing: `on.failure.goto` can recover from `assert_failed`
111. v1.6 typed predicates: `when` and `assert` accept `artifact_bool|compare|all_of|any_of|not`
112. v1.6 structured refs: bare `steps.*`, `self.*`, `parent.*`, and untyped `context.*` are rejected in typed predicates
113. v1.6 single-visit boundary: loader rejects structured refs that target provably multi-visit step identities
114. v1.6 normalized outcomes: observable step results expose `outcome.{status,phase,class,retryable}` for reports and typed routing
115. v1.6 runtime predicate failure shape: dynamically unavailable structured refs fail with `exit_code:2` and `error.type:"predicate_evaluation_failed"`
116. v1.7 loader gating: `set_scalar` and `increment_scalar` are rejected below `version: "1.7"`
117. v1.7 scalar bookkeeping validation: loader rejects bookkeeping steps that do not target a declared top-level scalar artifact
118. v1.7 local scalar result surface: successful bookkeeping steps persist their produced value under `steps.<Step>.artifacts`
119. v1.7 scalar lineage composition: `publishes.from` can publish bookkeeping outputs and advance `artifact_versions` without any direct registry mutation path
120. v1.8 loader gating: `max_transitions` and `max_visits` are rejected below `version: "1.8"`
121. v1.8 top-level-only guard scope: nested/`for_each` `max_visits` usage is rejected until stable internal IDs land
122. v1.8 visit accounting: skipped steps do not consume visit budget and command/provider retries do not consume extra visits
123. v1.8 transition accounting: routed back-edge loops increment `transition_count` and fail the target step pre-execution when `max_transitions` is exceeded
124. v1.8 resume-safe counters: `transition_count` and `step_visits` persist in `state.json` and remain available on resume
125. v1.8 guard terminality: `cycle_guard_exceeded` stops the run even when the guarded step declares `on.failure.goto`
126. v2.0 loader gating: authored step `id` is rejected below `version: "2.0"`
127. v2.0 scoped refs: `self.steps.*` and `parent.steps.*` are valid only at `version: "2.0"`+, while bare `steps.*` remains invalid in structured predicates
128. v2.0 stable identity: authored ids preserve `step_id` values across sibling insertion; compiler-generated ids are not promised stable across checksum-changing edits
129. v2.0 qualified lineage: `for_each` producer/consumer lineage uses qualified internal identities rather than bare display names
130. v2.0 schema boundary: resume rejects pre-v2.0 state unless an explicit upgrader exists
131. v2.1 loader gating: top-level `inputs` and `outputs` are rejected below `version: "2.1"`
132. v2.1 input binding: `run --input/--input-file` binds typed workflow inputs before execution and persists them under `bound_inputs`
133. v2.1 input read surfaces: workflow steps may read bound inputs through `${inputs.<name>}` and typed `ref: inputs.<name>`
134. v2.1 output export contracts: loader rejects missing `outputs.<name>.from`, and successful runs export validated `workflow_outputs`
135. v2.1 workflow-output failure shape: unresolved export refs or invalid exported values fail the run with a run-level `contract_violation` error scoped to `workflow_outputs`
136. v2.2 loader gating: structured `if` / `then` / `else` is rejected below `version: "2.2"`
137. v2.2 branch-local visibility: downstream refs may target only the statement node outputs, not branch-local inner step names
138. v2.2 lowering stability: authored statement/branch ids preserve lowered `step_id` ancestry across sibling insertion
139. v2.2 non-taken branches: lowered non-selected branch nodes are recorded explicitly as skipped
140. v2.2 statement outputs: selected branch outputs materialize onto the statement node as `steps.<Statement>.artifacts`
141. v2.2 conservative routing boundary: `goto` / `_end` is rejected inside structured `if/else` branches in the first tranche
142. v2.3 loader gating: top-level `finally` is rejected below `version: "2.3"`
143. v2.3 stable cleanup identity: authored finalization `id` preserves lowered cleanup-step `step_id` ancestry across sibling insertion
144. v2.3 resume-safe finalization: resume restarts from the first unfinished `finally` step instead of replaying completed cleanup
145. v2.3 failure classification: cleanup failure after body success fails the run with `finalization_failed`, while cleanup failure after body failure remains secondary diagnostic state
146. v2.3 deferred workflow outputs: `workflow_outputs` remain unmaterialized until finalization succeeds and are suppressed on finalization failure
147. v2.5 caller/callee version boundary: the first `call` tranche rejects mixed-version caller/callee execution
148. v2.5 typed `with:` binding: call-site bindings are checked against declared callee `inputs`
149. v2.5 declared export boundary: only declared callee `outputs` cross back to the caller and surface as `steps.<CallStep>.artifacts.<name>`
150. v2.5 reusable-library write-root rule: reusable workflows that hard-code DSL-managed write roots instead of exposing typed `relpath` inputs are rejected
151. v2.5 call-site write-root rule: missing required write-root bindings and colliding bound write roots are rejected
152. v2.5 path taxonomy: `asset_file` / `asset_depends_on` / nested imports resolve from the workflow source tree, while `input_file` / `depends_on` / outputs remain WORKSPACE-relative; source-asset traversal is rejected
153. v2.5 caller-visible producer identity: exported call outputs enter caller-visible lineage with the outer call step as the external producer
154. v2.5 preserved internal provenance: exported call outputs retain callee-internal origin metadata as secondary provenance/debug information
155. v2.5 callee-private defaults: imported `providers`, `artifacts`, and `context` defaults stay private to the call frame unless explicitly bound or exported
156. v2.5 call-scoped freshness: callee-internal `artifact_versions`, `artifact_consumes`, and `since_last_consume` freshness bookkeeping use call-frame-qualified identities rather than bare names
157. v2.5 finalization-aware exports: caller-visible callee outputs materialize only after callee body and callee finalization both succeed, and stay suppressed when callee finalization fails
158. v2.5 call-frame diagnostics/reporting: status and report surfaces expose call-frame identity/import/export state without leaking undeclared callee-private artifacts into caller-visible state
159. v2.6 loader gating: structured `match` is rejected below `version: "2.6"`
160. v2.6 enum boundary: `match.ref` must resolve to an enum artifact or input, and `match.cases` must cover every allowed enum value
161. v2.6 case-local visibility: downstream refs may target only the statement node outputs, not case-local inner step names
162. v2.6 lowering stability: authored statement/case ids preserve lowered `step_id` ancestry across sibling insertion
163. v2.6 non-selected cases: lowered non-selected case nodes are recorded explicitly as skipped
164. v2.6 statement outputs: selected case outputs materialize onto the statement node as `steps.<Statement>.artifacts`
165. v2.6 conservative routing boundary: `goto` / `_end` is rejected inside structured `match` cases in the first tranche
166. v2.7 loader gating: structured `repeat_until` is rejected below `version: "2.7"`
167. v2.7 loop-frame boundary: `repeat_until.condition` must read declared loop-frame outputs via `self.outputs.*` and reject direct `self.steps.<Inner>...` refs
168. v2.7 resume-safe iteration bookkeeping: resume restarts from the first unfinished nested step in the current iteration without replaying completed iteration work
169. v2.7 condition replay safety: if one iteration's condition already evaluated before interruption, resume advances without replaying that settled iteration
170. v2.7 loop-frame outputs: the latest selected iteration outputs materialize on `steps.<RepeatUntilStatement>.artifacts`
171. v2.10 scalar `string`: typed workflow boundaries, scalar artifacts, expected outputs, and output bundles preserve exact string values without trimming
172. v2.10 provider-session loader guards: `provider_session` and `session_support` are gated at `version: "2.10"`, remain root-top-level only, enforce fresh/resume tagged-union validation, reject retries, and reserve the runtime-owned fresh `publish_artifact` local key
173. v2.10 resume binding guard: the reserved `session_id_from` consume must match exactly one consume contract, use `freshness: any` or omit freshness, and stay excluded from prompt injection and `consume_bundle`
174. v2.10 session runtime publication: successful fresh session steps atomically persist their final step result, same-visit artifact-lineage updates, and exact-match `current_step` clearance before the session metadata record is finalized
175. v2.10 interrupted-visit quarantine: `orchestrate resume` quarantines interrupted session-enabled visits keyed by `current_step.step_id` plus `visit_count`, preserves older same-name terminal results, clears `current_step`, and records a durable run-level quarantine error with metadata/spool paths
176. v2.10 provider-session observability: report/status surfaces expose run-level quarantine context and step-level `provider_session` summaries without printing raw metadata transport to console stdout
177. v2.11 loader gating: `adjudicated_provider` is rejected below `version: "2.11"` and is mutually exclusive with every other execution form, provider sessions, and stdout-derived capture surfaces
178. v2.11 candidate/evaluator validation: candidates are non-empty with unique stable ids and known providers; evaluator provider/prompt/rubric/evidence fields obey the same-trust-boundary and evidence-limit contract
179. v2.11 baseline isolation: every candidate attempt starts from one immutable frame/step/visit baseline using the fixed copy policy, required excluded paths fail before provider launch, and safe/unsafe symlink behavior is deterministic
180. v2.11 evidence packet contract: scoring packets contain complete bounded UTF-8 score-critical evidence, reject declared secret values, persist packet hashes, and exclude stdout/stderr, transport logs, and bounded prompt previews
181. v2.11 evaluator parsing and selection: evaluator stdout is strict JSON with matching candidate id, finite score in `[0.0, 1.0]`, and non-empty summary; invalid candidate outputs are ineligible, highest score wins, and ties use candidate order
182. v2.11 promotion transaction: selected outputs are promoted only through staged manifest-backed replacement with destination preimage checks, duplicate-destination rejection, rollback metadata, parent output revalidation, and publish withholding until commit
183. v2.11 score ledger ownership: run-local ledgers and workspace-visible mirrors use stable candidate/score keys and owner tuples; mirror conflicts, dynamic ledger/output collisions, and invalid JSONL ownership fail before publication
184. v2.11 stdout suppression and observability: adjudicated step results do not expose candidate/evaluator stdout as `output`, `lines`, `json`, `truncated`, or parse-error debug state, while reports may expose selected candidate, score, ledger paths, promotion status, and failure type
185. v2.11 resume/retry contract: logical deadlines, candidate/evaluator retry scopes, resume idempotency, promotion-state reconciliation, and `adjudication_resume_mismatch` are covered by implementation tests before full production rollout

## DSL Evolution Rollout Crosswalk

- Task 2 executable proof: `tests/test_loader_validation.py`, `tests/test_runtime_step_lifecycle.py`, `tests/test_workflow_examples_v0.py`, and `workflows/examples/assert_gate_demo.yaml`
- Task 3 executable proof: `tests/test_typed_predicates.py`, `tests/test_conditional_execution.py`, `tests/test_observability_report.py`, `tests/test_workflow_examples_v0.py`, and `workflows/examples/typed_predicate_routing.yaml`
- Task 4 executable proof: `tests/test_scalar_bookkeeping.py`, `tests/test_loader_validation.py`, `tests/test_artifact_dataflow_integration.py`, `tests/test_runtime_step_lifecycle.py`, `tests/test_workflow_examples_v0.py`, and `workflows/examples/scalar_bookkeeping_demo.yaml`
- Task 5 executable proof: `tests/test_control_flow_foundations.py`, `tests/test_loader_validation.py`, `tests/test_state_manager.py`, `tests/test_resume_command.py`, `tests/test_retry_behavior.py`, `tests/test_workflow_examples_v0.py`, and `workflows/examples/cycle_guard_demo.yaml`
- Task 6 executable proof: `tests/test_loader_validation.py`, `tests/test_state_manager.py`, `tests/test_resume_command.py`, `tests/test_artifact_dataflow_integration.py`, `tests/test_at65_loop_scoping.py`, and `workflows/examples/for_each_demo.yaml` dry-run verification
- Task 7 executable proof: `tests/test_loader_validation.py`, `tests/test_cli_safety.py`, `tests/test_state_manager.py`, `tests/test_resume_command.py`, `tests/test_output_contract.py`, `tests/test_workflow_output_contract_integration.py`, `tests/test_workflow_examples_v0.py`, and `workflows/examples/workflow_signature_demo.yaml`
- Task 8 executable proof: `tests/test_loader_validation.py`, `tests/test_structured_control_flow.py`, `tests/test_state_manager.py`, `tests/test_resume_command.py`, `tests/test_workflow_examples_v0.py`, and `workflows/examples/structured_if_else_demo.yaml`
- Task 9 executable proof: `tests/test_structured_control_flow.py`, `tests/test_resume_command.py`, `tests/test_observability_report.py`, `tests/test_workflow_examples_v0.py`, and `workflows/examples/finally_demo.yaml`
- Task 10 contract-boundary stability proof: `pytest tests/test_loader_validation.py -k "call or import or version" -v`, plus a forward-proof cross-check that each acceptance item 147-158 is mapped to Task 11 coverage below.
- Task 10 -> Task 11 reusable-call proof map:

| Acceptance | Task 11 proof ownership |
| --- | --- |
| 147 | `tests/test_subworkflow_calls.py` coverage bullet for caller/callee same-version rejection; verification command `pytest tests/test_subworkflow_calls.py tests/test_loader_validation.py tests/test_artifact_dataflow_integration.py tests/test_state_manager.py tests/test_resume_command.py -k "call or call_frame or resume" -v` |
| 148 | `tests/test_subworkflow_calls.py` coverage bullet for typed `with:` binding against callee inputs; same Task 11 call-frame verification command |
| 149 | `tests/test_subworkflow_calls.py` coverage bullet for caller-visible outputs surfacing as `steps.<CallStep>.artifacts.<name>`; `tests/test_workflow_examples_v0.py -k call_subworkflow -v`; dry-run `python -m orchestrator run workflows/examples/call_subworkflow_demo.yaml --dry-run` |
| 150 | `tests/test_subworkflow_calls.py` coverage bullet for reusable-workflow rejection when DSL-managed write roots remain fixed instead of parameterized typed `relpath` inputs; same Task 11 call-frame verification command |
| 151 | `tests/test_subworkflow_calls.py` coverage bullet for call-site rejection when required write-root inputs are missing or colliding; same Task 11 call-frame verification command |
| 152 | Task 11 Step 2 coverage for source-relative asset resolution plus path-traversal rejection in `tests/test_dependency_resolution.py`, `tests/test_dependency_injection.py`, `tests/test_provider_execution.py`, `tests/test_provider_integration.py`, and `tests/test_secrets.py`; verification command `pytest tests/test_dependency_resolution.py tests/test_dependency_injection.py tests/test_prompt_contract_injection.py tests/test_provider_execution.py tests/test_provider_integration.py tests/test_secrets.py -k "asset or import or call or path or context" -v` |
| 153 | `tests/test_subworkflow_calls.py` bullet for exported call outputs entering caller-visible lineage with the outer call step as producer, backed by `tests/test_artifact_dataflow_integration.py`; verified by the Task 11 call-frame verification command |
| 154 | `tests/test_subworkflow_calls.py` bullet for preserved callee-internal provenance plus `tests/test_state_manager.py` coverage for persisted export metadata; verified by the Task 11 call-frame verification command |
| 155 | `tests/test_subworkflow_calls.py` bullet for private provider/artifact/context namespaces and callee-default isolation plus the Task 11 asset/import/path/context verification command |
| 156 | `tests/test_subworkflow_calls.py`, `tests/test_artifact_dataflow_integration.py`, and `tests/test_state_manager.py` coverage for call-scoped `artifact_versions` / `artifact_consumes` / freshness bookkeeping; verified by the Task 11 call-frame verification command |
| 157 | `tests/test_subworkflow_calls.py` and `tests/test_resume_command.py` coverage for deferred export until callee finalization completes plus suppression on finalization failure; verified by the Task 11 call-frame verification command, the `call_subworkflow_demo` run command, and `pytest tests/test_resume_command.py -k call_subworkflow_smoke -v` |
| 158 | `tests/test_resume_command.py` and `tests/test_state_manager.py` coverage for call-frame identities, deferred export state, and operator-facing diagnostics, plus the `call_subworkflow_demo` run/resume commands |

- Task 11 executable proof: `tests/test_subworkflow_calls.py`, `tests/test_loader_validation.py`, `tests/test_artifact_dataflow_integration.py`, `tests/test_state_manager.py`, `tests/test_resume_command.py`, `tests/test_dependency_resolution.py`, `tests/test_dependency_injection.py`, `tests/test_prompt_contract_injection.py`, `tests/test_provider_execution.py`, `tests/test_provider_integration.py`, `tests/test_secrets.py`, `tests/test_workflow_examples_v0.py`, and `workflows/examples/call_subworkflow_demo.yaml`
- Task 12 executable proof: `tests/test_loader_validation.py`, `tests/test_structured_control_flow.py`, `tests/test_workflow_examples_v0.py`, and `workflows/examples/match_demo.yaml`
- Task 13 executable proof: `tests/test_loader_validation.py`, `tests/test_structured_control_flow.py`, `tests/test_resume_command.py`, `tests/test_workflow_examples_v0.py`, and `workflows/examples/repeat_until_demo.yaml`
- Task 15 executable proof: `tests/test_adjudicated_provider_loader.py`, `tests/test_adjudicated_provider_baseline.py`, `tests/test_adjudicated_provider_promotion.py`, `tests/test_adjudicated_provider_scoring.py`, `tests/test_adjudicated_provider_runtime.py`, `tests/test_adjudicated_provider_outcomes.py`, `tests/test_workflow_examples_v0.py -k adjudicated`, and `workflows/examples/adjudicated_provider_demo.yaml` dry-run verification

## Future Acceptance (v1.2)

1. Success path: item moved to `processed/<ts>/...` per `success.move_to`.
2. Failure path: item moved to `failed/<ts>/...` per `failure.move_to`.
3. Recovery within item: recovered failure treated as success; success move.
4. Goto escape: escape marks failure and triggers failure move.
5. Path safety: invalid `move_to` rejected.
6. Variable substitution: `${run.timestamp_utc}` and `${loop.index}` resolve correctly.
7. Idempotency/resume: lifecycle actions not applied twice; `action_applied: true` recorded.
8. Missing source: record lifecycle error; result unchanged.
9. State recording: per-iteration `lifecycle` object present.

## Future Acceptance (JSON Stdout Validation)

1. Schema pass; 2. Schema fail with `json_schema_errors`; 3. Parse fail; 4. Parse allowed is incompatible with schema; 5. Require pointer exists; 6. Require equals; 7. Require type; 8. Multiple requirements; 9. Variable substitution in schema path; 10. Large JSON overflow behavior.
