# Workflow Lisp Stdlib Lowering: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_stdlib_lowering.md](../../design/workflow_lisp_stdlib_lowering.md).

## Example: `produce-one-of`

Expected lowering:

```text
CorePreSnapshot
CoreProducerStep
CoreSelectVariantOutput
```

Semantic requirements:

- snapshot candidates match union variants
- exactly one candidate changes
- selected bundle validates before commit
- selected variant fields are availability-scoped
- mtime is debug metadata only
