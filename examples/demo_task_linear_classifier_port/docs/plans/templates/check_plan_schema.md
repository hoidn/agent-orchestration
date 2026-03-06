# Check Plan Schema

Write check plans as JSON:

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
