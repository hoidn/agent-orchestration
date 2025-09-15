while :; do cat prompts/ralph_orchestrator_PROMPT.md | claude -p --dangerously-skip-permissions --verbose --output-format stream-json ; done

