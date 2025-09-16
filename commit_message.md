## Commit Message

```
refactor: Reorganize CLAUDE.md structure with Python packaging setup

- Add comprehensive project setup section with pyproject.toml configuration
- Move Ralph loop commands to dedicated section for better organization
- Add virtual environment and editable install instructions
- Clarify pytest usage without sys.path manipulation
- Add explicit warning against using run_tests.py path hacks
- Maintain existing repo map and working method guidance

This reorganization improves onboarding experience and enforces proper
Python packaging practices for the orchestrator module.
```

## Files Changed

### Modified Files
- `CLAUDE.md` - Restructured with new setup instructions and clearer organization
- `prompts/ralph_orchestrator_PLAN_PROMPT.md` - Added commit step to planning outputs
- `prompts/ralph_orchestrator_PROMPT.md` - Enhanced testing requirements and refactoring discipline

### New Files
- `prompts/generic_implement.md` - Generic implementation prompt template
- `prompts/ralph_orchestrator_FIX_PROMPT.md` - Debug/repair mode prompt for broken tests