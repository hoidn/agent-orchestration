# Fix Plan - Multi-Agent Orchestrator Implementation

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

✅ **AT-17-19**: Wait-for functionality
   - Implemented complete wait_for polling primitive in `orchestrator/fsq/wait.py`
   - Blocks until files matching glob pattern found or timeout (AT-17)
   - Returns exit code 124 on timeout with timed_out: true (AT-18)
   - Records files, wait_duration_ms, poll_count in state (AT-19)
   - Integration with step executor for workflow execution
   - Tests: Complete test suite in `test_wait_for.py` (10 tests passing)

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

## Top-10 Priority Items (Next Loops)

1. **AT-37,46,47**: Conditional execution
    - when.equals/exists/not_exists semantics
    - Conditional skip with false when → skipped status

3. **AT-44**: Provider params variable substitution
    - Support nested dicts/lists with proper substitution

## Refactor Track — Contract Hardening (Non‑optional)

1. Execution safety (argv, no shell=True) — spec: dsl.md/providers.md; acceptance: AT‑8, AT‑9, AT‑50
   - Rationale: Align process execution with argv semantics, reduce injection/quoting risk.
   - DoD: All command/provider executions use argv lists; all provider/command tests pass unchanged.
   - Tasks:
     - Replace `shell=True` command paths with `subprocess.run([...])` argv forms.
     - Normalize executor APIs to accept `List[str]` (and keep a safe string→argv adapter only where unavoidable).
     - Update tests to assert argv behavior, not shell parsing.

2. Loader error handling (library/CLI boundary) — spec: versioning.md/dsl.md (strict validation)
   - Rationale: Keep loader reusable; avoid process control inside library code.
   - DoD: Loader raises structured exceptions; CLI maps to exit codes; existing validation tests adapted to expect exceptions.
   - Tasks:
     - Replace internal `sys.exit(2)` with raising a `WorkflowValidationError` carrying messages.
     - Adjust tests to catch exceptions and assert messages/exit semantics.

3. Injection integration + debug record — acceptance: AT‑28–35, AT‑53
   - Rationale: Injector exists; ensure it’s applied and recorded during execution.
   - DoD: For provider steps with `depends_on.inject`, executor composes prompt with resolver+injector; on truncation, record `steps.<Step>.debug.injection{...}`.
   - Tasks:
     - In provider execution flow, resolve required/optional globs (deterministic order), apply injector (list/content, prepend/append).
     - Persist truncation metadata to `StepState.debug.injection` exactly as per spec.
     - Add tests for list/content modes, custom instruction, prepend/append, and truncation record.

4. Output capture spill consistency (JSON overflow + allow_parse_error) — acceptance: AT‑15, AT‑52
   - Rationale: Ensure large JSON with allow_parse_error behaves like text truncation and spills full stream.
   - DoD: Overflow path writes full stdout to `logs/<Step>.stdout` and stores truncated text in state.
   - Tasks:
     - Unify spill logic between text truncation and JSON overflow fallback.
     - Add regression test asserting presence and contents of `logs/<Step>.stdout`.

5. Provider params substitution (nested) — acceptance: AT‑44
   - Rationale: Centralize substitution with namespace/escape rules; support nested dicts/lists.
   - DoD: Single substitution pass over strings in provider_params (recursively), honoring `${run|context|loop|steps.*}` and escapes; tests cover nested structures.
   - Tasks:
     - Introduce a shared substitution utility; apply in provider params handling.
     - Add tests for nested maps/arrays and pointer forms.

## Backlog

- AT-20,21: Timeouts and retries
- AT-37,46,47: Conditional execution (when.equals/exists/not_exists)
- AT-44: Provider params variable substitution
- Observability: debug logging, prompt audit
- Resume capability with checksum validation
- Integration test suite with real provider mocks

## Architecture Alignment Notes

- Following ADR-02b: Strict validation at declared version
- Following ADR-01: Path safety enforced at load time
- Following ADR-03: Provider as managed black box
- Loader/Executor separation per arch.md: validation vs runtime substitution
- **CRITICAL**: Module structure per arch.md now being enforced:
  - ✅ orchestrator/exec/* (output_capture.py, step_executor.py)
  - ✅ orchestrator/deps/* (resolver.py, injector.py)
  - ✅ orchestrator/providers/* (registry.py, executor.py, types.py)
  - ✅ orchestrator/fsq/* (wait.py)
  - ✅ orchestrator/workflow/* (executor.py, pointers.py)
  - ✅ orchestrator/cli/* (main.py, commands/run.py)
  - ✅ orchestrator/security/* (secrets.py) - NEW THIS LOOP
  - ✅ orchestrator/state.py
  - ✅ orchestrator/loader.py

## Next Loop Recommendation

Implement queue management (AT-5,6) for inbox atomicity and user-driven task moves. This provides the foundation for inter-agent communication via filesystem queues.
