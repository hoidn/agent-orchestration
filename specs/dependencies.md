# Dependencies and Injection (Normative)

- Resolution and validation
  - `depends_on.required`: POSIX globs must each match ≥1 path after substitution; otherwise exit 2 with error context.
  - `depends_on.optional`: missing matches are allowed and omitted without error.
  - Patterns resolve relative to WORKSPACE; symlinks are followed; dotfiles matched only when explicitly specified; case sensitivity follows the host FS.
  - Globstar `**` is not supported in v1.1.
  - When reusable `call` lands, plain `depends_on` keeps these same workspace-relative semantics inside imported workflows; it does not become import-local automatically.

- Injection (v1.1.1)
  - Shorthand: `inject: true` ≡ `{ mode: 'list', position: 'prepend' }` with default instruction.
  - Modes
    - `list`: prepend/append instruction + bullet list of matched relative file paths.
    - `content`: include file contents with headers `=== File: <relative/path> (<shown_bytes>/<total_bytes>) ===`.
    - `none`: no injection (default).
  - Ordering and size
    - Deterministic lexicographic ordering of resolved paths.
    - Cap total injected material at ~256 KiB. On truncation, record `steps.<Step>.debug.injection` with truncation details.
  - Target and mutability
    - Injection modifies only the composed prompt delivered to the provider. Source files are never modified.

- Path safety
  - Reject absolute paths and any path containing `..`.
  - Follow symlinks; if the resolved real path escapes WORKSPACE, reject the path.
  - Enforce at load time and before FS operations. See `security.md#path-safety`.

## Planned Source-Relative Asset Surface (Task 10 contract; v2.5 execution)

- `depends_on` remains the workspace-relative runtime dependency surface.
  - Use it for authored files that are expected to exist in the execution workspace at run time.
  - Inside imported workflows, it still resolves from WORKSPACE and can consume caller-bound write roots or other runtime-produced files.

- `asset_depends_on` is the separate workflow-source-relative asset surface for reusable provider workflows.
  - Shape: `asset_depends_on: ["relative/file.md", "schemas/review.json"]`
  - Scope: provider steps only.
  - Paths are exact workflow-source-relative files; the first tranche does not add globs, optional assets, or injection knobs.
  - Resolution base is the directory containing the authored workflow file, not WORKSPACE.
  - Validation must reject traversal outside that workflow source tree.

- Taxonomy rule
  - Do not overload plain `depends_on` with import-local semantics.
  - Use `asset_depends_on` only for bundled source assets owned by the reusable workflow itself.
  - Source-relative asset reads and workspace-relative runtime dependencies are intentionally different contract families.

## Injection examples

Basic injection (shorthand):

```yaml
depends_on:
  required:
    - "artifacts/architect/*.md"
  inject: true
```

Advanced injection:

```yaml
depends_on:
  required:
    - "artifacts/architect/*.md"
  optional:
    - "docs/standards.md"
  inject:
    mode: "list"
    instruction: "Review these architecture files:"
    position: "prepend"
```

Content mode formatting and truncation records are defined with examples in the monolithic v1.1.1 spec and preserved in this module.

## Migration and Best Practices

### Migrating from v1.1 to v1.1.1
Existing workflows with `depends_on` continue to work unchanged. To adopt injection:

**Before (v1.1):**
```yaml
# Had to maintain file list in both places
depends_on:
  required:
    - "artifacts/architect/*.md"
input_file: "prompts/implement.md"  # Must list files manually
```

**After (v1.1.1):**
```yaml
# Single source of truth
version: "1.1.1"
depends_on:
  required:
    - "artifacts/architect/*.md"
  inject: true  # Automatically informs provider
input_file: "prompts/generic_implement.md"  # Can be generic
```

### Benefits of Injection
- **DRY Principle**: Declare files once in YAML.
- **Pattern Support**: Globs like `*.md` expand automatically.
- **Maintainability**: Change file lists in one place.
- **Flexibility**: Generic prompts work across projects.
