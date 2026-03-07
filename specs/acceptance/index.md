# Acceptance Tests (Normative)

- Conformance areas
  - DSL validation: version gating, mutual exclusivity, `goto` target validation, strict unknown-field rejection.
  - Variable substitution: namespaces, escapes, undefined variable handling.
  - Dependency resolution: required vs optional, glob behavior, deterministic ordering.
  - Injection (v1.1.1): modes, default instruction, prepend/append position, truncation record.
  - IO capture: modes, limits, tee semantics, JSON parse behavior and `allow_parse_error`.
  - Providers: argv vs stdin, placeholder validation, unresolved placeholders, parameter merge.
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

## DSL Evolution Rollout Crosswalk

- Task 2 executable proof: `tests/test_loader_validation.py`, `tests/test_runtime_step_lifecycle.py`, `tests/test_workflow_examples_v0.py`, and `workflows/examples/assert_gate_demo.yaml`
- Task 3 executable proof: `tests/test_typed_predicates.py`, `tests/test_conditional_execution.py`, `tests/test_observability_report.py`, `tests/test_workflow_examples_v0.py`, and `workflows/examples/typed_predicate_routing.yaml`
- Task 4 executable proof: `tests/test_scalar_bookkeeping.py`, `tests/test_loader_validation.py`, `tests/test_artifact_dataflow_integration.py`, `tests/test_runtime_step_lifecycle.py`, `tests/test_workflow_examples_v0.py`, and `workflows/examples/scalar_bookkeeping_demo.yaml`
- Later-task roadmap proof ownership remains as written in `docs/plans/2026-03-06-dsl-evolution-execution-plan.md`; those tranches are not accepted until their named test/smoke blocks land with the corresponding implementation.

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
