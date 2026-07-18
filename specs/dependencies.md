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
    - Cap the exact UTF-8 injection block at `262144` bytes. The cap includes the instruction, separators, file headers, shown content, inline truncation markers, and aggregate truncation summary; it excludes the prompt composer's outer separator.
    - Reserve at most `512` bytes for the aggregate truncation summary. A custom instruction is therefore limited to `261630` UTF-8 bytes. Rendering stops after the first truncated or omitted canonical file group, never splits a UTF-8 code point, and never returns a block above the cap.
    - On truncation, record `steps.<Step>.debug.injection` with explicit shown, truncated, and omitted details.
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

## Workflow Lisp exact prompt dependencies

Workflow Lisp `provider-result` may add this closed clause:

```lisp
:prompt-dependencies
  (:required (work-order-path target-design-path)
   :optional (prior-findings-path)
   :position prepend
   :instruction "Use these files as authoritative inputs:")
```

- At least one required or optional operand is present. Every operand has a
  declared workspace `relpath` type and lowers to an existing runtime binding;
  strings, globs, dynamic instructions, and path literals are not alternate
  spellings of this surface.
- Optional means that the exact file may be absent. A present optional file is
  read and decoded under the same content contract as a required file.
- `:position` is optional and defaults to `prepend`; the only values are
  `prepend` and `append`. `:instruction` is optional and, when present, is a
  literal UTF-8 string. Without it, required or mixed rows use the existing
  required-dependency instruction and optional-only rows use the existing
  optional-dependency instruction.
- Required and present optional targets are combined, de-duplicated by their
  canonical workspace-relative target, and rendered once in deterministic
  lexicographic target order. Authored order and required/optional role remain
  compiler and evidence provenance, not final prompt order; required wins when
  aliases identify the same target.
- One provider attempt resolves, reads, newline-normalizes, orders, and renders
  one immutable dependency snapshot. Rendering and evidence use that object
  without reopening files. A retry creates a fresh snapshot; an unreadable or
  invalid-UTF-8 selected file fails that attempt rather than being silently
  skipped.
- The typed compiler contract, not the YAML-shaped `depends_on` mapping,
  identifies the exact-path Workflow Lisp surface. The compiler retains it in
  a typed side table keyed by provider-step identity. `runtime_plan` remains a
  topology/checkpoint projection and carries no prompt-dependency paths,
  policy, or content metadata.

YAML `depends_on.inject.mode: content` remains a legacy authoring surface. Its
successful below-cap prompt bytes stay compatible, and it shares the immutable
per-attempt snapshot/render owner, including a fresh snapshot on each retry.
YAML does not acquire the compiler-only typed contract or Workflow Lisp
attempt-evidence side effect.

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
