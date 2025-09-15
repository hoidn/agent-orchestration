# Dependencies and Injection (Normative)

- Resolution and validation
  - `depends_on.required`: POSIX globs must each match ≥1 path after substitution; otherwise exit 2 with error context.
  - `depends_on.optional`: missing matches are allowed and omitted without error.
  - Patterns resolve relative to WORKSPACE; symlinks are followed; dotfiles matched only when explicitly specified; case sensitivity follows the host FS.
  - Globstar `**` is not supported in v1.1.

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
