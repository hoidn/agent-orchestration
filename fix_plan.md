# Fix Plan - Multi-Agent Orchestrator Implementation

## Status Summary
- **Core Acceptance Tests**: 70/72 completed (97.2%)
- **E2E Validation Tests**: 0/3 completed (0%)
- **Test Suite**: 283 tests passing
- **Estimated Iterations to Full Completion**:
  - 2 iterations for AT-68, AT-71
  - 2-3 iterations for E2E-01 through E2E-03
  - **Total: 4-5 iterations**

## Completed

✅ **AT-1,2,45,52**: Output capture modes (text/lines/json) with truncation
   - Implemented in `orchestrator/exec/output_capture.py` per arch.md module structure
   - Text mode: 8 KiB limit with spill to logs
   - Lines mode: 10,000 lines limit with CRLF normalization
   - JSON mode: 1 MiB buffer limit, parse error handling with allow_parse_error flag
   - Tee semantics: output_file receives full stream while state limits apply
   - Tests: Complete test suite in `test_output_capture.py` (17 tests passing)

✅ **AT-14,15**: JSON oversize handling
   - JSON >1 MiB fails with exit 2 unless allow_parse_error=true
   - With allow_parse_error, stores truncated text and succeeds
   - Tests: `test_at14_json_oversize_fails`, `test_at15_json_parse_error_allowed`

✅ **AT-7**: No env namespace - `${env.*}` rejected by schema validator
   - Implemented in `orchestrator/loader.py` with regex pattern check
   - Tests: `test_at7_env_namespace_rejected`, `test_at7_env_in_provider_params_rejected`

✅ **AT-10**: Provider/Command exclusivity - Validation error when both present
   - Implemented mutual exclusivity check in step validation
   - Test: `test_at10_provider_command_exclusivity`

✅ **AT-36**: Wait-For Exclusivity - wait_for cannot combine with command/provider/for_each
   - Implemented exclusivity validation
   - Test: `test_at36_wait_for_exclusivity`

✅ **AT-38**: Path Safety (Absolute) - absolute paths rejected at validation
   - Implemented path safety checks
   - Test: `test_at38_absolute_path_rejected`

✅ **AT-39**: Path Safety (Parent Escape) - `..` or symlinks escaping rejected
   - Implemented parent traversal detection
   - Test: `test_at39_parent_escape_rejected`

✅ **AT-40**: Deprecated override - `command_override` usage rejected
   - Implemented deprecation check
   - Test: `test_at40_deprecated_override_rejected`

✅ **AT-4**: Status schema - Write/read status.json with v1 schema
   - Implemented complete StateManager in `orchestrator/state.py`
   - Atomic writes with temp file + rename
   - Backup support with rotation (keep last 3)
   - Checksum validation for workflow integrity
   - State repair from backups
   - Tests: Full test suite in `test_state_manager.py` (10 tests passing)

✅ **AT-67**: Tee on JSON parse failure
   - When `output_capture: json` fails to parse and `allow_parse_error: false`, `output_file` still receives full stdout while state/log limits apply
   - Implementation already correct: tee happens before mode-specific processing in `output_capture.py:118-119`
   - Test: Added comprehensive test `test_at67_tee_on_json_parse_failure` covering parse errors and buffer overflows
   - Verified with 3 test cases: invalid JSON, large invalid JSON, and buffer overflow scenarios

✅ **AT-43**: Loop state indexing - Results stored as `steps.<LoopName>[i].<StepName>`
   - Implemented in StateManager.update_loop_step()
   - Test: `test_at4_loop_state_indexing`

✅ **Core Loader Foundation**
   - Strict unknown field rejection
   - Version gating (1.1, 1.1.1 support)
   - Goto target validation
   - Provider template validation
   - For-each loop structure validation

✅ **AT-8,9,48-51**: Provider execution (argv vs stdin modes)
   - Implemented provider registry in `orchestrator/providers/registry.py`
   - Provider template validation with stdin mode ${PROMPT} check
   - Provider executor with argv/stdin input modes
   - Placeholder substitution and validation
   - Parameter merging (defaults overlaid by step params)
   - Missing placeholder detection with error context
   - Tests: Full test suite in `test_provider_execution.py` and `test_provider_integration.py` (20 tests passing)

✅ **AT-22-27**: Dependency validation and resolution
   - Implemented complete dependency resolver in `orchestrator/deps/resolver.py`
   - POSIX glob matching with deterministic lexicographic ordering
   - Required vs optional file semantics (missing required fails with exit 2)
   - Variable substitution in patterns before resolution
   - Path safety validation (absolute paths and .. traversal rejected)
   - Symlink escape detection
   - Support for re-evaluation in loops with different variables
   - Tests: Complete test suite in `test_dependency_resolution.py` (14 tests passing)

✅ **AT-28-35,53**: Dependency injection (v1.1.1 feature)
   - Implemented dependency injector in `orchestrator/deps/injector.py`
   - List mode: prepends/appends file paths with instruction
   - Content mode: includes file contents with headers showing size info
   - Shorthand support: `inject: true` equals list mode with prepend
   - Custom instruction and position (prepend/append) support
   - Size cap at ~256 KiB with truncation metadata recording
   - Deterministic ordering preserved from resolver
   - Tests: Complete test suite in `test_dependency_injection.py` (11 tests passing)

✅ **AT-17-19,60-62**: Wait-for functionality with path safety
   - Implemented complete wait_for polling primitive in `orchestrator/fsq/wait.py`
   - AT-17: Blocks until files matching glob pattern found or timeout
   - AT-18: Returns exit code 124 on timeout with timed_out: true
   - AT-19: Records files, wait_duration_ms, poll_count in state
   - AT-60: Engine executes wait_for steps and records all fields; downstream steps run on success
   - AT-61: Runtime path safety - absolute paths or .. in wait_for.glob rejected with exit 2
   - AT-62: Symlinks escaping WORKSPACE are excluded; returned paths are relative
   - Integration with step executor for workflow execution
   - Tests: Complete test suites in `test_wait_for.py` (10 tests), `test_at60_wait_for_integration.py` (4 tests), `test_at61_at62_wait_for_path_safety.py` (6 tests)

✅ **AT-3,13**: For-each loops execution
   - Items_from pointer resolution implemented in `orchestrator/workflow/pointers.py`
   - WorkflowExecutor created with for-each support in `orchestrator/workflow/executor.py`
   - Loop scope variables (${item}, ${loop.index}, ${loop.total}) support added
   - State manager integration fixed (using correct API methods)
   - Test suite: Complete with 12 tests passing in `test_for_each_execution.py`
   - Example workflow created in `workflows/examples/for_each_demo.yaml`

✅ **AT-11,12,16**: CLI implementation (clean/archive processed)
   - Implemented complete CLI module in `orchestrator/cli/`
   - Main entry point with argparse in `orchestrator/cli/main.py`
   - Run command with safety checks in `orchestrator/cli/commands/run.py`
   - AT-11: --clean-processed empties directory (with safety validation)
   - AT-12: --archive-processed creates zip on success
   - AT-16: Safety checks prevent cleaning outside WORKSPACE
   - Archive destination validation prevents placing inside processed_dir
   - Tests: Complete test suite in `test_cli_safety.py` (15 tests passing)
   - Created executable script `orchestrate` for command-line usage

✅ **AT-41,42,54,55**: Secrets handling implementation
   - Implemented SecretsManager in `orchestrator/security/secrets.py` per arch.md module structure
   - AT-41: Missing secrets cause exit 2 with missing_secrets context
   - AT-42: Best-effort masking of secret values as '***' in logs and state
   - AT-54: Secrets sourced exclusively from orchestrator environment
   - AT-55: Step env overrides secrets when keys collide; still masked
   - Empty strings count as present secrets
   - Integrated into StepExecutor and ProviderExecutor
   - Tests: Complete test suite in `test_secrets.py` (16 tests passing)

✅ **AT-5,6**: Queue management implementation
   - Implemented QueueManager in `orchestrator/fsq/queue.py` per arch.md module structure
   - AT-5: Atomic inbox operations with *.tmp → rename() → *.task pattern
   - AT-6: User-driven task lifecycle management (move to processed/failed with timestamps)
   - Helper functions for clean_directory and archive_directory (used by CLI)
   - Convenience functions: write_task, move_to_processed, move_to_failed
   - Path safety validation ensures operations stay within WORKSPACE
   - Tests: Complete test suite in `test_queue_operations.py` (20 tests passing)

✅ **AT-20,21**: Timeouts and retries
   - Implemented retry policy in `orchestrator/exec/retry.py` per arch.md module structure
   - AT-20: Timeout enforcement with exit code 124 recording
   - AT-21: Provider steps retry on exit codes 1/124 by default; commands only when retries field set
   - RetryPolicy class with separate policies for providers vs commands
   - Integration into WorkflowExecutor with retry loop and delay
   - Step-level retry configuration overrides global/CLI settings
   - Tests: Complete test suite in `test_retry_behavior.py` and `test_retry_integration.py` (15 tests passing)

✅ **AT-37,46,47**: Conditional execution
   - Implemented ConditionEvaluator in `orchestrator/workflow/conditions.py`
   - Created VariableSubstitutor in `orchestrator/variables/substitution.py` for variable resolution
   - AT-37: when.equals with string comparison and variable substitution
   - AT-46: when.exists with POSIX glob pattern matching and path safety
   - AT-47: when.not_exists as inverse of exists condition
   - Integrated into WorkflowExecutor for both top-level steps and for-each loops
   - False conditions result in step skipped with exit_code 0 and skipped: true
   - Tests: Complete test suite in `test_conditional_execution.py` (18 tests passing)

## Completed (Continued)

✅ **AT-44**: Provider params variable substitution with nested structures
   - Integrated VariableSubstitutor into provider params handling in `orchestrator/providers/executor.py`
   - Updated provider types to support nested Dict[str, Any] structures
   - Fixed workflow executor to properly call provider executor API (prepare_invocation + execute)
   - Added deep merge support for nested defaults in `orchestrator/providers/registry.py`
   - Created comprehensive test suite in `test_at44_provider_params_nested.py` (8 tests passing)
   - Fixed integration issues with retry behavior tests
   - Full test suite passing (200 tests)

## Completed (Continued 2)

✅ **Execution safety (argv mode, no shell=True)** — spec: dsl.md/providers.md; acceptance: AT‑8, AT‑9, AT‑50
   - Replaced `shell=True` in StepExecutor with argv array execution using shlex.split() for security
   - Both string and list command formats are supported
   - String commands are parsed into argv arrays using shlex for proper quoting/escaping
   - List commands are passed directly to subprocess.run() without shell
   - Variable substitution works correctly with both formats
   - Tests: Complete test suite in `test_execution_safety.py` (11 tests passing)
   - DoD: All command/provider executions use safe argv mode; shell injection prevented

## Completed (Continued 4)

✅ **AT-56,57,58,59: Error handling and control flow** — COMPLETED — acceptance: AT-56, AT-57, AT-58, AT-59
   - AT-56: Strict flow stop - non-zero exit halts run when no applicable goto and on_error=stop (default)
   - AT-57: on_error continue - With --on-error continue, run proceeds after non-zero exit
   - AT-58: Goto precedence - on.success/on.failure goto targets execute before strict_flow applies
   - AT-59: Goto always ordering - on.always evaluated after success/failure handlers, ordering respected
   - Implemented complete control flow in orchestrator/workflow/executor.py with _handle_control_flow() method
   - Fixed critical YAML parsing bug: 'on' key was being converted to boolean True
   - Created custom PreservingLoader to prevent automatic boolean conversion
   - Fixed infinite loop issue with conditional execution
   - Handled for-each loop results (lists) vs regular steps (dicts) in control flow
   - Tests: 8 comprehensive tests in test_at56_at57_error_handling.py all passing
   - Full test suite: 254 tests passing (no regressions)
   - DoD: Error handling and control flow fully functional per specifications

## Top-10 Priority Items (Next Loops)

## Refactor Track — Contract Hardening (Non‑optional)

1. ✅ ~~Execution safety (argv, no shell=True)~~ — COMPLETED

2. ✅ ~~Loader error handling (library/CLI boundary)~~ — COMPLETED
   - Replaced sys.exit(2) calls with WorkflowValidationError exception
   - Created orchestrator/exceptions.py with structured exception classes
   - Updated CLI to catch exceptions and map to exit codes
   - Updated all loader tests to expect exceptions instead of SystemExit
   - DoD: Loader now usable as a library; 210 tests passing

3. ✅ Injection integration + debug record — COMPLETED — acceptance: AT‑28–35, AT‑53
   - Fixed API mismatch between DependencyResolver and WorkflowExecutor
   - DependencyResolution now has `is_valid`, `files`, and `errors` properties
   - Resolver returns validation state instead of raising ValueError
   - Fixed prompt loading for dependencies without injection (AT-35)
   - Fixed test setup to write workflow files to disk for StateManager
   - Tests: All 11 tests in `test_injection_integration.py` passing
   - Updated dependency resolution tests to match new API behavior
   - DoD: Provider steps with `depends_on.inject` now compose prompts with injection; truncation metadata recorded in `steps.<Step>.debug.injection`; 222 tests passing

4. ✅ Output capture spill consistency — COMPLETED — acceptance: AT‑15, AT‑52
   - Fixed JSON buffer overflow with allow_parse_error to spill full stdout to logs
   - Added log spilling at orchestrator/exec/output_capture.py:213-214
   - Created regression test `test_at52_json_overflow_spills_to_logs`
   - Unified spill logic: text truncation, lines overflow, and JSON overflow all write to logs/<Step>.stdout
   - Tests: 18 tests passing in test_output_capture.py; full suite 223 tests passing
   - DoD: JSON overflow with allow_parse_error=true now behaves consistently with text/lines modes

5. ✅ Resume command implementation — COMPLETED — acceptance: AT‑4
   - Implemented complete CLI resume command in orchestrator/cli/commands/resume.py
   - Added resume parameter support to WorkflowExecutor.execute() method
   - Handles partial for-each loop resumption (skips completed iterations)
   - Supports --repair flag for state recovery from backups
   - Supports --force-restart flag to ignore state and start fresh
   - Validates workflow checksum to detect modifications
   - Tests: 8 comprehensive tests in test_resume_command.py all passing
   - Full test suite: 231 tests passing (no regressions)
   - DoD: Resume command fully functional; reads state.json, validates checksum, resumes from last incomplete step

## Completed (Continued 3)

6. **AT-63: Undefined variable handling** — COMPLETED — acceptance: AT-63
   - Integrated VariableSubstitutor properly into WorkflowExecutor command execution
   - Added error detection with exit code 2 and error.context.undefined_vars
   - Prevents command execution when undefined variables detected (safety feature)
   - Fixed custom loop variable handling (e.g., for_each with "as: filename")
   - Added state manager persistence for command steps
   - Tests: 5 comprehensive tests in test_at63_undefined_variables.py all passing
   - Full test suite: 236 tests passing (no regressions)
   - DoD: Undefined variables in commands yield exit 2 with proper error context; no process execution occurs

## Completed (Continued 3)

✅ **AT-64: ${run.root} variable support** — COMPLETED — acceptance: AT-64
   - Added run_root field to RunState dataclass with proper serialization
   - StateManager now persists run_root path (.orchestrate/runs/<run_id>) in state.json
   - WorkflowExecutor properly uses run_root from state for variable substitution
   - Variable substitution extended to handle output_file paths
   - Fixed context passing to ensure variables work in both command and provider execution
   - Created comprehensive test suite in test_at64_run_root_variable.py (5 tests)
   - Full test suite: 241 tests passing (no regressions)
   - DoD: ${run.root} variable resolves to .orchestrate/runs/<run_id> and is usable in commands, paths, and provider params

✅ **AT-65: Loop scoping of steps.* variables** — COMPLETED — acceptance: AT-65
   - Modified _create_loop_context() to pass iteration_state instead of full state (orchestrator/workflow/executor.py:371, 809)
   - Updated context creation to include only current iteration's step results (line 835)
   - Fixed variable building in _execute_command_with_context() to use scoped steps from context (lines 438-449)
   - Fixed variable building in _execute_provider_with_context() for both stdin/argv modes (lines 609-620, 652-663)
   - Created comprehensive test suite in test_at65_loop_scoping.py (5 tests)
   - Tests verify: current iteration isolation, outer steps undefined in loops, iteration independence, nested step references
   - Full test suite: 246 tests passing (no regressions)
   - DoD: Inside for_each, ${steps.<Name>.*} refers only to current iteration's results; outer steps are undefined

## Completed (Continued 4)

✅ **AT-66: env literal semantics** — COMPLETED — acceptance: AT-66
   - Environment variables are passed literally without ${} variable substitution
   - Verified behavior is already correctly implemented in WorkflowExecutor
   - Step env values passed directly to step_executor and provider_executor unchanged
   - Works correctly for command steps, provider steps, for_each loops, and with secrets
   - Created comprehensive test suite in test_at66_env_literal_semantics.py (5 tests)
   - Full test suite: 259 tests passing (no regressions)
   - DoD: Environment variables maintain literal values including ${...} patterns as required by spec

✅ **AT-72: Provider state persistence** — COMPLETED — acceptance: AT-72
   - Provider results are properly persisted to state.json after execution
   - State persistence includes exit_code, captured output per mode, and any error/debug fields
   - State is preserved through reload (state_manager.load())
   - Tests: Complete test suite in test_at72_provider_state_persistence.py (3 tests)
   - Full test suite: 272 tests passing (no regressions)
   - DoD: Provider execution results are fully persistent and recoverable from state.json

✅ **AT-69: Debug backups** — COMPLETED — acceptance: AT-69
   - --debug flag enables state backups (implies backup_enabled=True in StateManager)
   - StateManager creates state.json.step_<Step>.bak files before each step execution
   - Backup rotation keeps only last 3 backups
   - WorkflowExecutor calls backup_state() before each step when debug=True
   - Handles both regular steps and steps within for_each loops (with indexed names)
   - Tests: Complete test suite in test_at69_debug_backups.py (6 tests passing)
   - Full test suite: 279 tests passing (no regressions)
   - DoD: Debug backups working exactly as specified with rotation

✅ **AT-70: Prompt audit & masking** — COMPLETED — acceptance: AT-70
   - With --debug, composed prompt text is written to logs/<Step>.prompt.txt
   - Known secret values are masked as '***' in the audit file
   - Works with both provider steps with and without dependency injection
   - Implemented in WorkflowExecutor._write_prompt_audit() method
   - Integrates with SecretsManager for masking secret values
   - Tests: Complete test suite in test_at70_prompt_audit.py (4 tests passing)
   - Full test suite: 283 tests passing (no regressions)
   - DoD: Prompt audit logs created in debug mode with proper masking

## Priority Order (Updated)

### Phase 1: Core Acceptance Tests (2 remaining of 72)
1. **AT-68: Resume force-restart** — Verify/test --force-restart flag (partially implemented)
2. **AT-71: Retries + goto** — Integration of retry exhaustion with on.failure.goto (not implemented)

### Phase 2: E2E Validation Tests (Non-normative, release gate)
5. **E2E-01: Test Presence** — Create basic e2e test infrastructure
   - pytest marker already registered in pyproject.toml
   - Need at least one @pytest.mark.e2e test that skips gracefully
   - Guard with ORCHESTRATE_E2E env var or CLI availability checks
6. **E2E-02: Claude Provider E2E** — Real argv mode test with claude CLI
   - Test claude provider with ${PROMPT} in argv mode
   - Create simple prompt, verify execution and output capture
   - Skip if claude not available or ORCHESTRATE_E2E not set
7. **E2E-03: Codex Provider E2E** — Real stdin mode test with codex CLI
   - Test codex provider with stdin mode prompt delivery
   - Verify execution and artifact creation
   - Skip if codex not available or ORCHESTRATE_E2E not set

## Backlog
- Additional E2E scenarios (loops, dependencies, error recovery)
- Performance benchmarks
- Documentation improvements

## Architecture Alignment Notes

- Following ADR-02b: Strict validation at declared version
- Following ADR-01: Path safety enforced at load time
- Following ADR-03: Provider as managed black box
- Loader/Executor separation per arch.md: validation vs runtime substitution
- **CRITICAL**: Module structure per arch.md now being enforced:
  - ✅ orchestrator/exec/* (output_capture.py, step_executor.py, retry.py)
  - ✅ orchestrator/deps/* (resolver.py, injector.py)
  - ✅ orchestrator/providers/* (registry.py, executor.py, types.py)
  - ✅ orchestrator/fsq/* (wait.py, queue.py)
  - ✅ orchestrator/workflow/* (executor.py, pointers.py, conditions.py)
  - ✅ orchestrator/variables/* (substitution.py) - NEW THIS LOOP
  - ✅ orchestrator/cli/* (main.py, commands/run.py)
  - ✅ orchestrator/security/* (secrets.py)
  - ✅ orchestrator/state.py
  - ✅ orchestrator/loader.py

✅ **AT-60: Wait-for integration** — COMPLETED — acceptance: AT-60
   - Implemented complete wait_for step execution in WorkflowExecutor._execute_wait_for()
   - Calls StepExecutor.execute_wait_for() which uses the fsq.wait.WaitFor module
   - Records all required fields: files, wait_duration_ms, poll_count, timed_out
   - Added wait_for specific fields to StepResult dataclass in state.py
   - State is persisted to state.json atomically via StateManager
   - Downstream steps can run on success and access wait_for results via variables
   - Tests: 4 comprehensive integration tests in test_at60_wait_for_integration.py all passing
   - Full test suite: 263 tests passing (no regressions)
   - DoD: Engine executes wait_for steps and properly records all metrics to state

✅ **AT-61,62: Wait-for path safety** — COMPLETED — acceptance: AT-61, AT-62
   - AT-61: Runtime validation in WaitFor.execute() rejects absolute paths and .. with exit 2
   - AT-62: Symlinks escaping WORKSPACE excluded; paths returned relative to WORKSPACE
   - Added _validate_path_safety() method to check glob patterns at runtime
   - Modified _find_matching_files() to exclude symlinks that resolve outside workspace
   - Preserves original symlink paths (not resolved) for symlinks within workspace
   - Error context includes path_safety_error type with glob_pattern detail
   - Tests: 6 comprehensive tests in test_at61_at62_wait_for_path_safety.py all passing
   - Full test suite: 269 tests passing (no regressions)
   - DoD: Wait-for enforces path safety at runtime and properly handles symlinks

✅ **AT-72: Provider state persistence** — COMPLETED — acceptance: AT-72
   - Provider step results are now persisted to state.json with all fields
   - Added state_manager.update_step() call after provider execution in WorkflowExecutor
   - Persistence includes: exit_code, captured output per mode, error, and debug fields
   - After reload (state_manager.load()), provider results remain present and unchanged
   - Fixed critical bug where provider results were only stored in memory but not persisted to disk
   - Tests: 3 comprehensive tests in test_at72_provider_state_persistence.py all passing
   - Full test suite: 272 tests passing (no regressions)
   - DoD: Provider steps persist state correctly just like command steps

## Next Loop Recommendation

With prompt audit (AT-70) complete, the next highest-priority items are:
1. **AT-68: Resume force-restart** — Verify/test --force-restart flag functionality (partial implementation exists)
2. **AT-71: Retries + on.failure goto** — After exhausting retries, on.failure.goto should trigger
3. **E2E-01: Test presence** — Create at least one E2E test that skips gracefully when CLIs unavailable
4. **E2E-02 & E2E-03: Provider E2E tests** — Real CLI tests for claude and codex providers
