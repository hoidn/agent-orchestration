# Example: Multi-Agent Inbox Processing (Informative)

```yaml
version: "1.1.1"
name: "multi_agent_feature_dev"
strict_flow: true

providers:
  claude:
    command: ["claude", "-p", "${PROMPT}", "--model", "${model}"]
    defaults:
      model: "claude-sonnet-4-20250514"

steps:
  # Architect creates design documents
  - name: ArchitectDesign
    agent: "architect"
    provider: "claude"
    input_file: "prompts/architect/design_system.md"
    output_file: "artifacts/architect/design_log.md"
    
  # Check what architect created
  - name: ValidateArchitectOutput
    command: ["test", "-f", "artifacts/architect/system_design.md"]
    on:
      failure:
        goto: ArchitectFailed
        
  # Check for engineer tasks in inbox
  - name: CheckEngineerInbox
    command: ["find", "inbox/engineer", "-name", "*.task", "-type", "f"]
    output_capture: "lines"
    on:
      success:
        goto: ProcessEngineerTasks
      failure:
        goto: CreateEngineerTasks
        
  # Create tasks from architect output
  - name: CreateEngineerTasks
    command: ["bash", "-c", "
      echo 'Implement the system described in:' > inbox/engineer/implement.tmp &&
      ls artifacts/architect/*.md >> inbox/engineer/implement.tmp &&
      mv inbox/engineer/implement.tmp inbox/engineer/implement.task
    "]
    on:
      success:
        goto: CheckEngineerInbox
        
  # Process each engineer task
  - name: ProcessEngineerTasks
    for_each:
      items_from: "steps.CheckEngineerInbox.lines"
      as: task_file
      steps:
        - name: ImplementWithClaude
          agent: "engineer"
          provider: "claude"
          input_file: "prompts/engineer/generic_implement.md"
          output_file: "artifacts/engineer/impl_log_${loop.index}.md"
          depends_on:
            required:
              - "artifacts/architect/system_design.md"
              - "artifacts/architect/api_spec.md"
            optional:
              - "docs/coding_standards.md"
              - "artifacts/architect/examples.md"
            inject:
              mode: "list"
              instruction: "Implement the system based on these architecture documents:"
          on:
            failure:
              goto: HandleMissingDependencies
          
        - name: WriteStatus
          command: ["echo", '{"success": true, "task": "${task_file}", "impl": "src/impl_${loop.index}.py"}']
          output_file: "artifacts/engineer/status_${loop.index}.json"
          output_capture: "json"
          
        - name: MoveToProcessed
          command: ["bash", "-c", "mkdir -p processed/${run.timestamp_utc}_${loop.index} && mv ${task_file} processed/${run.timestamp_utc}_${loop.index}/"]
          
        - name: CreateQATask
          when:
            equals:
              left: "${steps.WriteStatus.json.success}"
              right: "true"
          command: ["echo", "Review src/impl_${loop.index}.py from ${task_file}"]
          output_file: "inbox/qa/review_${loop.index}.task"
          depends_on:
            required:
              - "src/impl_${loop.index}.py"

  # Error handlers
  - name: ArchitectFailed
    command: ["echo", "ERROR: Architect did not create required design files"]
    on:
      success:
        goto: _end
        
  - name: HandleMissingDependencies  
    command: ["echo", "ERROR: Required architect artifacts missing for engineer"]
    on:
      success:
        goto: _end
```

