# Example: File Dependencies in Complex Workflows (Informative)

This example demonstrates dependency patterns, variables, and loops.

```yaml
version: "1.1"
name: "data_pipeline_with_dependencies"

context:
  dataset: "customer_2024"
  model_version: "v3"

steps:
  # Validate all input data exists
  - name: ValidateInputs
    command: ["echo", "Checking inputs..."]
    depends_on:
      required:
        - "config/pipeline.yaml"
        - "data/${context.dataset}/*.csv"  # Variable substitution
        - "models/${context.model_version}/weights.pkl"
      optional:
        - "cache/${context.dataset}/*.parquet"
    
  # Process each CSV file
  - name: ProcessDataFiles
    command: ["find", "data/${context.dataset}", "-name", "*.csv"]
    output_capture: "lines"
    
  - name: TransformFiles
    for_each:
      items_from: "steps.ProcessDataFiles.lines"
      as: csv_file
      steps:
        - name: ValidateAndTransform
          provider: "data_processor"
          input_file: "${csv_file}"
          output_file: "processed/${loop.index}.parquet"
          depends_on:
            required:
              - "${csv_file}"
              - "config/transformations.yaml"
            optional:
              - "processed/${loop.index}.cache"
              
        - name: GenerateReport
          provider: "claude"
          input_file: "prompts/analyze_data.md"
          output_file: "reports/analysis_${loop.index}.md"
          depends_on:
            required:
              - "processed/${loop.index}.parquet"
              
  # Final aggregation needs all processed files
  - name: AggregateResults
    provider: "aggregator"
    input_file: "prompts/aggregate.md"
    output_file: "reports/final_report.md"
    depends_on:
      required:
        - "processed/*.parquet"
      optional:
        - "reports/analysis_*.md"
```

