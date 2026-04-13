# Security and Path Safety (Normative)

- Path safety
  - Reject absolute paths and any path containing `..` during validation.
  - Follow symlinks; if the resolved path escapes WORKSPACE, reject the path.
  - Apply checks at load time and before filesystem operations.
  - Dashboard file routes may serve only files under the selected resolved workspace root or the selected scanned run root after validation.
  - Dashboard route references must be workspace-relative or run-relative; dashboard HTML must not expose raw absolute filesystem links.
  - Dashboard paths recorded in state, logs, artifacts, provider metadata, and lineage are untrusted data. State-provided `run_root` must not define the server's file-serving authority.
  - Reusable-call additions:
    - `imports` and nested import targets resolve relative to the authored workflow file and must remain within WORKSPACE.
    - `asset_file` and `asset_depends_on` resolve from the directory containing the authored workflow file and must remain within that workflow source tree.
    - `input_file`, `depends_on`, `output_file`, `expected_outputs.path`, `output_bundle.path`, `consume_bundle.path`, and deterministic `relpath` outputs remain WORKSPACE-relative under `call`.

Note: These safety checks apply to paths the orchestrator resolves (e.g., `input_file`, `output_file`, `depends_on`, `wait_for`). Child processes invoked by `command`/`provider` can read/write any locations permitted by the OS; use OS/user sandboxing if stricter isolation is required.

- Reusable-call operational-risk boundary (Task 10 contract; v2.5 execution)
  - The first `call` tranche is intentionally non-isolating.
  - The loader/runtime must not claim proof of arbitrary child-process filesystem effects from imported `command` / `provider` steps.
  - Every DSL-managed reusable-workflow write root that must remain distinct across invocations is expected to be surfaced as a typed workflow `input` with `type: relpath`.
  - Call sites are expected to bind distinct per-invocation values for those write-root inputs whenever repeated or concurrent calls could otherwise alias the same managed paths.
  - Reusable workflows that hard-code DSL-managed write roots instead of parameterizing them as typed `relpath` inputs are outside the first shippable reusable-library subset and should be rejected once Task 11 implements `call`.
  - This contract covers orchestrator-managed paths only. Undeclared child-process reads/writes remain an accepted operational risk until a later execution-boundary change exists.

- Secrets handling
  - `secrets: string[]` declares environment variable names that MUST be present in the orchestrator environment.
  - Missing secrets cause step failure (exit 2) and populate `error.context.missing_secrets`.
  - Empty-string values count as present.
  - Precedence: if a key exists in both `env` and `secrets`, the child receives the `env` value and it is masked in logs as a secret.
  - Masking: best-effort replacement of known secret values with `***` in logs, state, and prompt audit.

- Environment inheritance
  - Child processes inherit the orchestrator environment, then secrets are overlaid, then step `env` is applied (step `env` wins on conflicts).

- Cross-platform note
  - Examples use POSIX tools (`bash`, `find`, `mv`, `test`). On Windows, use WSL or adapt to PowerShell equivalents.

- Dashboard content isolation
  - Dashboard previews render approved file bodies as escaped text or escaped JSON only; prompt, log, provider transport, state, backup, artifact, HTML, and SVG payloads must not execute in the dashboard origin.
  - Preview and raw responses set `X-Content-Type-Options: nosniff`.
  - Dashboard HTML routes set a restrictive Content Security Policy with `default-src 'none'`, `base-uri 'none'`, `object-src 'none'`, `frame-ancestors 'none'`, and `script-src 'none'`, plus only the minimal style/image allowances needed by the server-rendered UI.
  - Raw file responses default to `Content-Disposition: attachment` and `text/plain; charset=utf-8` for textual files or `application/octet-stream` for non-text files.
  - Dashboard routes must be read-only: they must not mutate workflow YAML, run state, logs, artifacts, backups, provider session files, or workspace source files, and must not execute operator commands.
