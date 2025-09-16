# Fix Plan - Multi-Agent Orchestrator Implementation

## Completed (This Loop)

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

3. **AT-4**: State file management (write/read state.json)
   - Implement state manager
   - Atomic writes with backup rotation

4. **AT-8,9,48-51**: Provider execution (argv vs stdin modes)
   - Provider registry and template composition
   - Placeholder substitution and validation

5. **AT-22-27**: Dependency validation and resolution
   - Required vs optional semantics
   - POSIX glob matching
   - Re-evaluation in loops

6. **AT-28-35,53**: Dependency injection (v1.1.1 feature)
   - List/content modes
   - Deterministic ordering
   - Size caps and truncation metadata

7. **AT-17-19**: Wait-for implementation
   - Polling logic with timeout
   - State tracking (duration_ms, poll_count, files)

8. **AT-3,13,43**: For-each loops execution
   - Items_from pointer resolution
   - Loop scope variables
   - State indexing `steps.<LoopName>[i].<StepName>`

9. **AT-11,12,16**: CLI implementation (run, clean/archive processed)
   - Safety constraints
   - Directory management

10. **AT-41,42,54,55**: Secrets handling
    - Environment composition
    - Masking in logs/state
    - Missing secrets error handling

## Backlog

- AT-5: Inbox atomicity (*.tmp → rename)
- AT-6: Queue management (user-driven moves)
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

Implement state manager (AT-4) as it's foundational for all execution tracking and enables testing of the executor module in subsequent loops.