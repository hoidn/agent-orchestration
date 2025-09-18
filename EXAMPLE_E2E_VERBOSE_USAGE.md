# E2E Test Observability - Usage Example

The new E2E test observability feature (AT-74) allows you to see agent inputs and outputs in real-time during E2E test execution.

## How to Use

### 1. Enable verbose mode with environment variable:
```bash
export ORCHESTRATE_E2E_VERBOSE=1
export ORCHESTRATE_E2E=1  # Enable E2E tests
```

### 2. Run E2E tests with verbose output:
```bash
# Run all E2E tests with verbose output
pytest -m e2e -v

# Run specific E2E test with verbose output
pytest tests/e2e/test_e2e_claude_provider.py::test_e2e_claude_provider_argv_mode -v -s
```

### 3. What you'll see:

When `ORCHESTRATE_E2E_VERBOSE=1` is set, the tests will display:

```
============================================================
  E2E-02: Claude Provider Test (argv mode)
============================================================

----------------------------------------
  Command Execution
----------------------------------------
  Command:
    python /path/to/orchestrate run workflows/claude_test.yaml --debug
  Working dir: /tmp/e2e_workspace

----------------------------------------
  Orchestrator Logs
----------------------------------------
  Created new run: abc123-def456
  Executing step: GenerateWithClaude

----------------------------------------
  Agent Input (Prompt)
----------------------------------------
  File: prompts/ping.md
  Content:
    Reply with OK

----------------------------------------
  Agent Response
----------------------------------------
  OK

----------------------------------------
  State Update: GenerateWithClaude
----------------------------------------
  Exit code: 0
  Output length: 2 chars

----------------------------------------
  Created Artifacts
----------------------------------------
  artifacts/architect/execution_log.txt (2 bytes)
```

### 4. Benefits:

- **Real-time visibility**: See what's happening as tests run
- **Debugging**: Quickly identify where tests fail
- **Understanding**: Learn how the orchestrator interacts with agents
- **Prompt inspection**: See the actual prompts sent to agents
- **Response tracking**: Monitor agent outputs

### 5. Disable verbose mode:

```bash
unset ORCHESTRATE_E2E_VERBOSE
# Or
export ORCHESTRATE_E2E_VERBOSE=0
```

## Integration with CI/CD

For CI/CD pipelines, you can conditionally enable verbose output:

```yaml
# GitHub Actions example
- name: Run E2E Tests
  env:
    ORCHESTRATE_E2E: 1
    ORCHESTRATE_E2E_VERBOSE: ${{ github.event_name == 'workflow_dispatch' && '1' || '0' }}
  run: pytest -m e2e -v
```

This enables verbose output only for manual workflow runs, keeping regular CI runs clean.