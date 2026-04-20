# Step IO and Output Capture (Normative)

- Input handling
  - `input_file`: read literal contents; no substitution inside file contents.
    - Under reusable `call`, `input_file` remains workspace-relative and does not become import-local.
  - `asset_file` (v2.5): read literal contents from the authored workflow source tree; provider-only and mutually exclusive with `input_file`.
  - When using a provider, the composed prompt (after optional injection) is passed via argv `${PROMPT}` or piped to stdin per provider template.

- Output handling
  - `output_file`: STDOUT is tee'd to this file and to the orchestrator capture pipeline.
  - Stderr is captured separately and written to logs when non-empty.
  - v2.10 session-enabled provider steps normalize structured provider transport before ordinary output capture:
    - normalized assistant text becomes the step-visible stdout used by `output_capture` and `output_file`
    - raw metadata transport remains on the runtime-owned provider-session spool path under the run root
  - Deterministic artifact contracts:
    - `expected_outputs`: file-per-value contract validation (v1.1+).
    - `output_bundle`: JSON-bundled field extraction/validation (v1.3+).
  - Reusable-call boundary:
    - `output_file`, `expected_outputs.path`, `output_bundle.path`, `consume_bundle.path`, and all deterministic `relpath` outputs stay workspace-relative whether a workflow runs top-level or under `call`.
    - `call` namespaces runtime-owned identities, provenance, and logs; it does not namespace authored output paths.

## Source-Relative vs Workspace-Relative Taxonomy

- Workflow-source-relative reads:
  - `imports`
  - nested import targets
  - `asset_file`
  - `asset_depends_on`

- Workspace-relative runtime reads/writes:
  - `input_file`
  - `depends_on`
  - `output_file`
  - `expected_outputs.path`
  - `output_bundle.path`
  - `consume_bundle.path`
  - authored `state/*`, `artifacts/*`, and other deterministic `relpath` paths

- First-tranche reusable-library rule
  - Do not treat `input_file` or plain `depends_on` as workflow-bundled asset mechanisms.
  - Use the source-relative asset surface for library-owned prompts, rubrics, templates, and schemas.

- Output capture modes
  - `text` (default): store up to 8 KiB in `state.json`. If exceeded, set `truncated: true` and write full stdout to `logs/<Step>.stdout`.
  - `lines`: split on LF; store up to 10,000 lines. On overflow, set `truncated: true` and spill full stdout to `logs/<Step>.stdout`.
  - `json`: parse stdout as JSON up to 1 MiB buffer. Parse failure or overflow → exit 2 unless `allow_parse_error: true`.
  - When `allow_parse_error: true` in json mode, the step completes with `exit_code: 0`, stores raw `output` (subject to 8 KiB limit), omits `json`, and records `debug.json_parse_error`.

- State fields
  - For `lines`/`json`, omit raw `output` to avoid duplication; include `truncated` flag and mode-specific fields.
  - Deterministic artifacts parsed from `expected_outputs` or `output_bundle` are exposed under `steps.<Step>.artifacts` (unless artifact persistence is disabled).

## Recommended Strictness Split

- Heavy implementation/fix steps:
  - Prefer `output_capture: text` (or `lines`) with minimal deterministic artifacts.
- Assessment/review/gate steps:
  - Prefer `output_capture: json` with `allow_parse_error: false`.
- Workflow control flow:
  - Branch on strict published artifacts from assessment/review steps rather than free-form execution prose logs.

## Tee semantics details

- With `output_file` set, the file receives the full stream while state/log limits apply.
- `text`: up to 8 KiB retained in state; full stdout goes to `logs/<StepName>.stdout` when truncated.
- `lines`: up to 10,000 lines retained in state; full stdout goes to `logs/<StepName>.stdout` when truncated.
- `json`: buffer up to 1 MiB for parsing; on overflow or invalid JSON, exit 2 unless `allow_parse_error: true`. The `output_file` always receives the full stream.
- Stderr is captured separately and written to `logs/<StepName>.stderr` when non-empty.
- For v2.10 session-enabled provider steps, `--stream-output` and `--debug` stream only normalized assistant text to console stdout; raw session metadata transport never goes directly to the parent console.

## Line splitting and normalization

- Lines are split on LF (`\n`). CRLF (`\r\n`) is normalized to LF in the `lines[]` entries.
- The raw, unmodified stdout stream is preserved in `logs/<StepName>.stdout` when truncation occurs or when JSON parsing fails.

## Adjudicated Provider IO (v2.11)

- Candidate output validation runs in the candidate workspace. Downstream workflow state is not updated from candidate outputs until selection and promotion complete.
- Selected-output promotion copies only declared deterministic outputs:
  - non-`relpath` `expected_outputs`: the candidate value file at `expected_outputs.path`
  - `relpath` `expected_outputs`: the path-only value file and, when `must_exist_target: true`, the candidate target file named by that value
  - `output_bundle`: the bundle JSON file and, for required bundle `relpath` fields, the candidate target file named by the extracted field value
- Promotion is a staged transaction: prepare a manifest, stage source files, reject duplicate destinations with different sources/roles, compare parent destinations against baseline preimages, replace files with same-filesystem temp-file renames, revalidate the parent output contract, and mark the manifest `committed` only after parent validation succeeds.
- If parent output validation fails after commit, the runtime rolls back files touched by the transaction using recorded backups or absent-destination tombstones. Unsafe rollback conflicts fail with `promotion_rollback_conflict`.
- Resume interprets promotion manifests by state: `prepared` repeats preimage checks and commits, `committing` treats already-staged destinations as committed when hashes match, `rolling_back` completes rollback, `failed` returns the recorded failure without publishing, and `committed` revalidates parent outputs before publication.
- Candidate and evaluator stdout/stderr are runtime-owned logs and sidecars. Adjudicated steps do not populate `output`, `lines`, `json`, `truncated`, or `debug.json_parse_error` from those streams.
