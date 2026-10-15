# specs/dependencies.md: Historical Sections

Status: **Historical.** Original tense, versioned acceptance language, receipts
and commands are preserved as evidence, not current execution or work selection.
Current owner: [dependencies.md](../../../specs/dependencies.md).

## Historical operational record 3

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
