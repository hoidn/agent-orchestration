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

## Top-10 Priority Items (Next Loops)

1. **AT-22-27**: Dependency validation and resolution
   - Required vs optional semantics
   - POSIX glob matching
   - Re-evaluation in loops

2. **AT-28-35,53**: Dependency injection (v1.1.1 feature)
   - List/content modes
   - Deterministic ordering
   - Size caps and truncation metadata

3. **AT-17-19**: Wait-for implementation
   - Polling logic with timeout
   - State tracking (duration_ms, poll_count, files)

4. **AT-3,13**: For-each loops execution
   - Items_from pointer resolution
   - Loop scope variables
   - Loop execution with state tracking

5. **AT-11,12,16**: CLI implementation (run, clean/archive processed)
   - Safety constraints
   - Directory management

6. **AT-41,42,54,55**: Secrets handling
   - Environment composition
   - Masking in logs/state
   - Missing secrets error handling

7. **AT-5,6**: Queue management
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
- Following ADR-03: Provider as managed black box
- Loader/Executor separation per arch.md: validation vs runtime substitution
- **CRITICAL**: Module structure per arch.md now being enforced (orchestrator/exec/* created)

## Next Loop Recommendation

Implement provider registry and execution (AT-8,9,48-51) now that the executor foundation is in place.