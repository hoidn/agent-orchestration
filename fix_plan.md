# Fix Plan - Multi-Agent Orchestrator Implementation

## Status Summary
- **DSL Version**: v1.1.1 (target)
- **State Schema**: v1.1.1
- **Implementation**: Not started (no Python code exists)
- **Priority**: Build core loader and validator first

## Top-10 Priority Items

### 1. ✅ [AT-7] Core DSL Loader & Schema Validation
**Status**: COMPLETED (2025-01-15)
**Acceptance**: Reject unknown fields, enforce version gating
**Spec**: `specs/dsl.md`, `specs/versioning.md`
**DoD**:
- [x] Load YAML workflow files
- [x] Strict schema validation (reject unknown fields)
- [x] Version field enforcement (1.1 vs 1.1.1 feature gating)
- [x] Mutual exclusivity checks (provider vs command)
- [x] Goto target validation
**Implementation**: `orchestrator/workflow/loader.py` with strict validation
**Tests**: 18 unit tests in `tests/test_loader.py` - all passing

### 2. ✅ [AT-10] Provider/Command Exclusivity
**Status**: COMPLETED (2025-01-15)
**Acceptance**: Step with both `provider` and `command` rejected
**Spec**: `specs/dsl.md`
**DoD**:
- [x] Validation error when both present
- [x] Clear error message
**Evidence**: Test `test_provider_command_mutual_exclusivity` passes

### 3. ✅ [AT-38/39] Path Safety Validation
**Status**: COMPLETED (2025-01-15)
**Acceptance**: Reject absolute paths and parent escapes
**Spec**: `specs/security.md#path-safety`
**DoD**:
- [x] Reject absolute paths at load time
- [x] Reject `..` in paths
- [x] Symlink escape detection (runtime check needed for dynamic paths)
- [x] Tests for edge cases
**Evidence**: Tests `test_absolute_path_rejected`, `test_parent_escape_rejected`, `test_dependency_path_safety` all pass

### 4. ✅ [AT-1/2] Basic Output Capture (text/lines/json)
**Status**: COMPLETED (2025-09-15)
**Acceptance**: Capture modes populate state correctly
**Spec**: `specs/io.md`
**DoD**:
- [x] Text capture with 8KB limit
- [x] Lines capture with 10K limit
- [x] JSON capture with 1MB limit
- [x] State structure correct
**Implementation**: `orchestrator/exec/` module with StepExecutor and OutputCapture
**Tests**: 22 unit tests in `tests/test_executor.py` - all passing
**Evidence**: Tests `test_acceptance_at1_lines_capture` and `test_acceptance_at2_json_capture` validate AT-1 and AT-2

### 5. ✅ [AT-28-35] Dependency Injection (v1.1.1)
**Status**: COMPLETED (2025-09-15)
**Acceptance**: `inject` modes work with version gating
**Spec**: `specs/dependencies.md#injection`
**DoD**:
- [x] Version 1.1.1 required for inject (validation complete)
- [x] List mode works (AT-29)
- [x] Content mode works (AT-30)
- [x] Size caps enforced (~256KB)
- [x] Truncation metadata recorded
- [x] Custom instruction support (AT-31)
- [x] Append position support (AT-32)
- [x] No injection by default (AT-35)
**Implementation**: `orchestrator/deps/injector.py` with full injection support
**Tests**: 9 comprehensive tests in `tests/test_injection.py` - all passing
**Evidence**: Tests for AT-28, AT-29, AT-30, AT-31, AT-32, AT-35 all pass

### 6. ✅ [AT-4] State Persistence
**Status**: COMPLETED (2025-09-15)
**Acceptance**: Write/read state.json with schema v1.1.1
**Spec**: `specs/state.md`
**DoD**:
- [x] Atomic writes with tmp+rename
- [x] Backup creation
- [x] Checksum validation
- [x] Schema version in state
**Implementation**: `orchestrator/state/` module with StateManager and StateFileHandler
**Tests**: 17 unit tests in `tests/test_state.py` - all passing
**Evidence**: Test `test_acceptance_at4_state_persistence` validates complete cycle

### 7. ✅ [AT-8/9/48/49/50/51] Provider Templates
**Status**: COMPLETED (2025-09-15)
**Acceptance**: argv vs stdin modes work correctly
**Spec**: `specs/providers.md`
**DoD**:
- [x] Template + params merge
- [x] argv mode with ${PROMPT}
- [x] stdin mode without ${PROMPT}
- [x] Missing placeholders → exit 2
- [x] stdin mode + ${PROMPT} → validation error
- [x] Provider params substitution
**Implementation**: `orchestrator/providers/` module with TemplateResolver
**Tests**: 12 unit tests in `tests/test_providers.py` - all passing

### 8. ✅ [AT-48/49] Placeholder Validation
**Status**: COMPLETED (2025-09-15)
**Acceptance**: Missing placeholders fail correctly
**Spec**: `specs/providers.md`
**DoD**:
- [x] Missing placeholder → exit 2
- [x] stdin mode + ${PROMPT} → validation error
- [x] Error context includes missing_placeholders
**Evidence**: Tests `test_acceptance_at48_missing_placeholders` and `test_acceptance_at49_stdin_mode_with_prompt_rejected` pass

### 9. ✅ [AT-22-27] Dependency Resolution
**Status**: COMPLETED (2025-09-15)
**Acceptance**: Required/optional globs work
**Spec**: `specs/dependencies.md`, `specs/variables.md`
**DoD**:
- [x] POSIX glob matching
- [x] Missing required → exit 2
- [x] Missing optional → continue
- [x] Variable substitution in patterns

### 10. ⬜ [AT-17-19] Wait-For Implementation
**Status**: Blocked by #1
**Acceptance**: Polling with timeout
**Spec**: `specs/queue.md`
**DoD**:
- [ ] Poll until match or timeout
- [ ] Exit 124 on timeout
- [ ] Record wait metrics in state

## Backlog (Remaining Acceptance Tests)

### Core DSL & Control Flow
- [ ] AT-3: Dynamic for-each loops
- [ ] AT-13: Pointer grammar (steps.X.json.path)
- [ ] AT-37: Conditional skip with `when`
- [ ] AT-43: Loop state indexing
- [ ] AT-46/47: when.exists/not_exists conditions

### I/O & Capture
- [ ] AT-14/15: JSON oversize handling
- [ ] AT-20: Timeout enforcement
- [ ] AT-21: Step retries
- [ ] AT-45: STDOUT capture thresholds
- [ ] AT-52: Output tee semantics

### Queue Management
- [ ] AT-5: Inbox atomicity
- [ ] AT-6: Queue management
- [ ] AT-36: Wait-for exclusivity

### CLI Operations
- [ ] AT-11: Clean processed
- [ ] AT-12: Archive processed
- [ ] AT-16: CLI safety checks

### Secrets & Environment
- [ ] AT-41: Missing secrets handling
- [ ] AT-42: Secrets masking
- [ ] AT-54: Secrets source
- [ ] AT-55: Secrets + env precedence

### Variables
- [ ] AT-44/51: Provider params substitution
- [ ] AT-50: Provider argv without ${PROMPT}
- [ ] AT-53: Injection shorthand

### Error Handling
- [ ] AT-26: Optional dependencies
- [ ] AT-27: Dependency error handler
- [ ] AT-40: Deprecated override rejection

## Implementation Notes

### Current State Analysis
- **No Python implementation exists** - starting from scratch
- **No test framework set up** - need pytest structure
- **No workflow examples** in workflows/ directory
- **Architecture defined** in arch.md with clear module structure

### Immediate Next Steps
1. Create orchestrator/ module structure per arch.md
2. Implement workflow loader with strict validation
3. Add unit tests for loader validation
4. Create minimal example workflows

### Technical Decisions
- Use Python 3.11+ with dataclasses
- PyYAML for parsing
- Pydantic or custom validators for schema
- Pytest for testing
- Follow module structure from arch.md section 4

### 2025-09-15 Loop 5: Provider Template Implementation
**Acceptance Tests Completed**: AT-8, AT-9, AT-48, AT-49, AT-50, AT-51
**Files Created**:
- `orchestrator/providers/__init__.py` - Provider module exports
- `orchestrator/providers/template_resolver.py` - TemplateResolver for command building
- `tests/test_providers.py` - 12 comprehensive unit tests for providers
- `workflows/examples/test_providers.yaml` - Example workflow demonstrating providers

**Key Implementation Details**:
- Template + defaults + provider_params merging (step params win)
- argv mode: ${PROMPT} substituted into command arguments
- stdin mode: prompt delivered via stdin, ${PROMPT} forbidden in template
- Variable substitution in provider_params (AT-51)
- Missing placeholders cause exit 2 with error.context.missing_placeholders
- Invalid ${PROMPT} in stdin mode causes validation error
- Escape sequences: $$ → $, $${ → ${
- Provider execution integrated with StepExecutor

**Test Results**: All 12 provider tests passing, total 87 tests passing

**Next Priority**: Implement wait-for (AT-17-19) or for-each loops (AT-3)

## Evidence Log

### 2025-01-15 Initial Assessment
- Searched for *.py files: None found
- Searched for workflows: None found
- No fix_plan.md existed - created this file
- Specs are comprehensive and well-defined
- arch.md provides clear implementation guidance

### 2025-01-15 Loop 1: Core DSL Loader Implementation
**Acceptance Tests Completed**: AT-7, AT-10, AT-38, AT-39, AT-40, AT-28 (validation only)
**Files Created**:
- `orchestrator/workflow/types.py` - DSL type definitions with dataclasses
- `orchestrator/workflow/loader.py` - YAML loader with strict validation
- `tests/test_loader.py` - 18 unit tests covering validation scenarios
- `workflows/examples/` - Example workflows for testing

**Key Implementation Details**:
- Strict unknown field rejection per version (AT-7)
- Provider/command/wait_for/for_each mutual exclusivity (AT-10)
- Path safety validation for absolute and parent escape (AT-38/39)
- Version gating for inject feature (AT-28)
- Deprecated command_override rejection (AT-40)
- Goto target validation ensuring all targets exist

**Test Results**: All 18 unit tests passing + 4 integration tests passing

**Next Priority**: Implement state manager (AT-4) or basic executor for output capture (AT-1/2)

### 2025-09-15 Loop 2: State Persistence Implementation
**Acceptance Test Completed**: AT-4
**Files Created**:
- `orchestrator/state/__init__.py` - State module exports
- `orchestrator/state/run_state.py` - StateManager, RunState, StepState classes
- `orchestrator/state/persistence.py` - StateFileHandler for atomic operations
- `tests/test_state.py` - 17 comprehensive unit tests for state persistence
- `workflows/examples/test_state_persistence.yaml` - Example workflow demonstrating state features

**Key Implementation Details**:
- Run ID format: YYYYMMDDTHHMMSSZ-<6char> with UTC timestamps
- Schema version 1.1.1 in all state files
- Atomic writes using temp file + rename pattern
- Workflow checksum validation for resume safety
- Backup management (keep last 3 with --backup-state flag)
- Support for loop state indexing (steps.<LoopName>[i].<StepName>)
- For-each loop state tracking with items/indices

**Test Results**: All 17 state tests passing, including AT-4 acceptance test

**Next Priority**: Implement basic executor (AT-1/2) to enable actual workflow execution

### 2025-09-15 Loop 3: Basic Executor and Output Capture Implementation
**Acceptance Tests Completed**: AT-1, AT-2
**Files Created**:
- `orchestrator/exec/__init__.py` - Executor module exports
- `orchestrator/exec/output_capture.py` - OutputCapture with mode-specific limits
- `orchestrator/exec/step_executor.py` - StepExecutor for command execution
- `tests/test_executor.py` - 22 unit tests covering all capture modes
- `workflows/examples/test_output_capture.yaml` - Example workflow demonstrating capture modes

**Key Implementation Details**:
- Text mode: 8 KiB limit with truncation to logs/StepName.stdout
- Lines mode: 10,000 lines limit with CRLF normalization
- JSON mode: 1 MiB parse buffer with allow_parse_error flag support
- Output file tee semantics (full stream to file, limited in state)
- Stderr capture to logs/StepName.stderr when non-empty
- Missing secrets cause exit code 2 with error context
- JSON parse errors cause exit code 2 unless allow_parse_error=true

**Test Results**: All 22 executor tests passing, including AT-1 and AT-2

**Next Priority**: Implement provider templates (AT-8/9) or dependency resolution (AT-22-27)

### 2025-09-15 Loop 4: Dependency Resolution and Variable Substitution
**Acceptance Tests Completed**: AT-22, AT-23, AT-24, AT-25, AT-26, AT-27
**Files Created**:
- `orchestrator/workflow/substitution.py` - Variable substitution with namespace support
- `orchestrator/deps/__init__.py` - Dependency module exports
- `orchestrator/deps/resolver.py` - DependencyResolver with glob matching
- `tests/test_dependencies.py` - 18 unit tests for dependencies and substitution
- `workflows/examples/test_dependencies.yaml` - Example workflow demonstrating dependencies

**Key Implementation Details**:
- POSIX glob pattern matching with deterministic lexicographic ordering
- Required dependencies fail with exit 2 and DependencyError if missing
- Optional dependencies are omitted silently when missing
- Variable substitution in dependency patterns (${context.*}, ${steps.*}, etc.)
- Path safety validation: reject absolute paths and .. traversal
- Symlink escape detection: filter out symlinks that escape WORKSPACE
- Environment namespace rejection: ${env.*} variables cause validation error
- Escape sequences: $$ -> $, $${ -> ${
- Loop dependencies re-evaluated each iteration

**Test Results**: All 18 dependency tests passing, total 75 tests passing

**Next Priority**: Implement wait-for (AT-17-19) or for-each loops (AT-3)

### 2025-09-15 Loop 6: Dependency Injection Implementation
**Acceptance Tests Completed**: AT-28, AT-29, AT-30, AT-31, AT-32, AT-35
**Files Created**:
- `orchestrator/deps/injector.py` - DependencyInjector for prompt composition
- `tests/test_injection.py` - 9 comprehensive tests for injection modes
- `workflows/examples/injection-content-mode.yaml` - Example workflow with content injection
- `prompts/generic_implement.md` - Generic prompt for use with injection

**Key Implementation Details**:
- Shorthand `inject: true` ≡ `{mode: "list", position: "prepend"}` with default instruction
- List mode: prepends/appends bullet list of file paths
- Content mode: includes file contents with headers showing `(shown_bytes/total_bytes)`
- Deterministic lexicographic ordering of injected files
- Size cap of ~256 KiB with graceful truncation
- Custom instruction overrides default "The following files are available..."
- Position control: prepend (default) or append to prompt
- Truncation metadata recorded in `steps.<Step>.debug.injection`
- Integration with TemplateResolver for provider execution

**Test Results**: All 9 injection tests passing, total 96 tests passing

**Next Priority**: Implement wait-for (AT-17-19) or for-each loops (AT-3)