# Changelog

All notable changes to the Multi-Agent Orchestrator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - 2025-09-18

### Added

#### Core Features
- **Output Capture Modes** (specs/io.md): Full support for `text`, `lines`, and `json` capture modes with proper truncation and tee semantics
  - Text mode: 8 KiB state limit with spill to logs
  - Lines mode: 10,000 lines limit with CRLF normalization
  - JSON mode: 1 MiB buffer limit with parse error handling
  - Tee semantics: `output_file` receives full stdout while state limits apply

- **Provider System** (specs/providers.md): Complete provider template system with argv and stdin input modes
  - Provider registry with template validation
  - Parameter merging (defaults + step-specific params)
  - Placeholder substitution with missing value detection
  - Support for nested parameter structures

- **Dependency System** (specs/dependencies.md): File dependency resolution and injection
  - POSIX glob pattern matching with deterministic ordering
  - Required vs optional file semantics
  - Dependency injection modes (list/content) with v1.1.1 gating
  - Size caps (~256 KiB) with truncation metadata
  - Path safety validation

- **Wait-For Functionality** (specs/queue.md): File system queue polling
  - Blocks until files match pattern or timeout
  - Records `files`, `wait_duration_ms`, `poll_count`, `timed_out`
  - Path safety with symlink escape detection
  - Exit code 124 on timeout

- **For-Each Loops** (specs/dsl.md): Dynamic iteration over items
  - `items_from` pointer resolution
  - Loop scope variables (`${item}`, `${loop.index}`, `${loop.total}`)
  - State indexing as `steps.<LoopName>[i].<StepName>`

- **Conditional Execution** (specs/dsl.md): Step conditions with variable substitution
  - `when.equals`: String comparison
  - `when.exists`: File pattern matching
  - `when.not_exists`: Inverse of exists
  - Skipped steps with `exit_code: 0`

- **Control Flow** (specs/dsl.md): Goto targets and error handling
  - `on.success`, `on.failure`, `on.always` handlers
  - Goto target validation
  - `--on-error continue` option for resilient workflows

- **Secrets Management** (specs/security.md): Environment variable handling with masking
  - Secrets sourced from orchestrator environment
  - Missing secrets cause exit 2 with context
  - Best-effort masking as `***` in logs and state
  - Step env overrides with continued masking

- **State Management** (specs/state.md): Persistent workflow state
  - Atomic writes with temp file + rename
  - Backup support with rotation (keep last 3)
  - Checksum validation for workflow integrity
  - Resume capability with partial completion support

- **CLI Commands** (specs/cli.md): Full command-line interface
  - `run`: Execute workflows with options
  - `resume`: Continue from last incomplete step
  - `--clean-processed`: Empty directory (with safety checks)
  - `--archive-processed`: Create zip on success
  - `--debug`: Enable verbose logging and backups
  - `--force-restart`: Start fresh ignoring state

- **Variable System** (specs/variables.md): Comprehensive variable substitution
  - Namespaces: `${run.*}`, `${context.*}`, `${steps.*}`, `${loop.*}`
  - Special variables: `${run.root}` for run directory
  - Loop scoping: `${steps.*}` isolated per iteration
  - Undefined variable detection with error context

- **Queue Management** (specs/queue.md): File system queue operations
  - Atomic inbox with `*.tmp` → `*.task` rename
  - User-driven task lifecycle (processed/failed directories)
  - Timestamp-based organization

### Security
- **Path Safety** (specs/security.md): Comprehensive path validation
  - Reject absolute paths and `..` traversal
  - Symlink escape detection
  - WORKSPACE boundary enforcement
- **Execution Safety**: All commands run with argv arrays (no `shell=True`)
- **Prompt Literal Contents**: Input files read without variable substitution

### Testing
- **E2E Test Infrastructure**: Segregated end-to-end tests with real provider CLIs
  - Claude provider (argv mode) validation
  - Codex provider (stdin mode) validation
  - Graceful skipping when CLIs unavailable

### Fixed
- Command output_capture string-to-enum conversion for proper mode handling
- Prompt literal contents preservation (no variable substitution in input files)
- Provider state persistence to state.json
- Resume functionality with force-restart option
- Retry exhaustion with goto handlers
- Error handling and control flow precedence
- Loop scoping for steps.* variables
- Environment variable literal semantics
- JSON overflow handling with allow_parse_error

## [1.1.0] - Previous Release

Initial DSL version with basic workflow execution.

## [1.0.0] - Initial Release

Foundation release with core orchestrator functionality.