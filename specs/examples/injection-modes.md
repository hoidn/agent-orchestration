# Example: Dependency Injection Modes (Informative)

```yaml
version: "1.1.1"
name: "injection_modes_demo"

steps:
  # Simple injection with defaults
  - name: SimpleReview
    provider: "claude"
    input_file: "prompts/generic_review.md"
    depends_on:
      required:
        - "src/*.py"
      inject: true
    
  # List mode with custom instruction
  - name: ImplementFromDesign
    provider: "claude"
    input_file: "prompts/implement.md"
    depends_on:
      required:
        - "artifacts/architect/*.md"
      inject:
        mode: "list"
        instruction: "Your implementation must follow these design documents:"
        position: "prepend"
    
  # Content mode for data processing
  - name: ProcessJSON
    provider: "data_processor"
    input_file: "prompts/transform.md"
    depends_on:
      required:
        - "data/input.json"
      inject:
        mode: "content"
        instruction: "Transform this JSON data according to the rules below:"
        position: "prepend"
    
  # Append mode for context
  - name: GenerateReport
    provider: "claude"
    input_file: "prompts/report_template.md"
    depends_on:
      optional:
        - "data/statistics/*.csv"
      inject:
        mode: "content"
        instruction: "Reference data for your report:"
        position: "append"
    
  # Pattern expansion with injection (non-recursive)
  - name: ReviewAllCode
    provider: "claude"
    input_file: "prompts/code_review.md"
    depends_on:
      required:
        - "src/*.py"
        - "tests/*.py"
      inject:
        mode: "list"
        instruction: "Review all these Python files for quality and consistency:"
    # For recursive discovery, generate a file list first and iterate.
    
  # No injection (classic mode)
  - name: ManualCoordination
    provider: "claude"
    input_file: "prompts/specific_files_mentioned.md"
    depends_on:
      required:
        - "data/important.csv"
      inject: false
```

