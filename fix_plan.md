# Fix Plan - Multi-Agent Orchestrator Implementation

## Completed

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

## Top-10 Priority Items (Next Loops)

1. **AT-1,2,45,52**: Output capture modes (text/lines/json) with truncation
   - Implement executor module
   - Handle state/log truncation at 8 KiB
   - Full tee to output_file

2. **AT-14,15**: JSON oversize handling (>1 MiB fails unless allow_parse_error)
   - Implement in executor's output capture

3. **AT-8,9,48-51**: Provider execution (argv vs stdin modes)
   - Provider registry and template composition
   - Placeholder substitution and validation

4. **AT-22-27**: Dependency validation and resolution
   - Required vs optional semantics
   - POSIX glob matching
   - Re-evaluation in loops

5. **AT-28-35,53**: Dependency injection (v1.1.1 feature)
   - List/content modes
   - Deterministic ordering
   - Size caps and truncation metadata

6. **AT-17-19**: Wait-for implementation
   - Polling logic with timeout
   - State tracking (duration_ms, poll_count, files)

7. **AT-3,13**: For-each loops execution
   - Items_from pointer resolution
   - Loop scope variables
   - Loop execution with state tracking

8. **AT-11,12,16**: CLI implementation (run, clean/archive processed)
   - Safety constraints
   - Directory management

9. **AT-41,42,54,55**: Secrets handling
    - Environment composition
    - Masking in logs/state
    - Missing secrets error handling

10. **AT-5,6**: Queue management
    - Inbox atomicity (*.tmp → rename)
    - User-driven moves to processed/failed

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
- Loader/Executor separation per arch.md: validation vs runtime substitution

## Next Loop Recommendation

Implement executor module with output capture (AT-1,2,45,52) as the StateManager is now in place to record execution results.