# Check Strategy and Check Plan Guidance

Use two verification artifacts:

- `check_strategy`: plan-time description of intended visible verification, including checks that may need to be created during implementation
- `check_plan`: runtime JSON of currently runnable checks

Write `check_plan` as JSON:

```json
{
  "checks": [
    {
      "name": "descriptive-check-name",
      "argv": ["command", "arg1", "arg2"],
      "timeout_sec": 900,
      "required": true
    }
  ]
}
```

Rules:
- `argv` must be an array of strings.
- `timeout_sec` must be a positive integer.
- `required` determines whether failure blocks approval.
- Prefer deterministic project-local commands.
- `check_strategy` may describe checks that will become runnable later.
- `check_plan` must contain only checks that are runnable now.
