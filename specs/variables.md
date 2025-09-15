# Variable Model and Substitution (Normative)

- Namespaces (precedence)
  - Run: `${run.id}`, `${run.root}`, `${run.timestamp_utc}`
  - Loop: `${item}`, `${loop.index}`, `${loop.total}`
  - Step results: `${steps.<name>.exit_code}`, `${steps.<name>.output|lines|json}`, `${steps.<name>.duration_ms}`
  - Context: `${context.<key>}`

- Where variables are substituted
  - Provider templates and `provider_params` values
  - Raw `command` arrays
  - File paths (e.g., `input_file`, `output_file`)
  - Conditions (`when.equals.left/right`)
  - Dependency globs in `depends_on` and `wait_for.glob`

- Where variables are not substituted
  - File contents: files referenced by `input_file`, `output_file`, or other file parameters are passed literally.
  - To include dynamic content inside a file, first generate it in a prior step, then reference that file.

- Undefined variables and coercion
  - Referencing an undefined variable is an error; the step fails with exit 2 and records error context.
  - Conditions compare values as strings; numbers/booleans are coerced to strings before comparison.

- Escapes
  - `$$` renders a literal `$`.
  - `$${` renders the literal sequence `${`.

- Environment and secrets
  - Orchestrator does not perform variable substitution inside `env` values.
  - Secrets are sourced from the orchestrator environment and masked in logs. See `security.md` for normative rules.
  - The `${env.*}` namespace is disallowed in workflows; the loader must reject such references.

## Dynamic Content Pattern

To include dynamic content in files, use a pre-processing step:

```yaml
steps:
  # Step 1: Create dynamic prompt with substituted variables
  - name: PreparePrompt
    command: ["bash", "-c", "echo 'Analyze ${context.project_name}' > temp/prompt.md"]
    
  # Step 2: Use the prepared prompt
  - name: Analyze
    provider: "claude"
    input_file: "temp/prompt.md"
```

Template processing for file contents is not supported; files are passed literally without variable substitution.
