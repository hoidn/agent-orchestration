Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read `project_brief`, `current_project_roadmap`, `current_tranche_manifest`, and `roadmap_change_request` before acting.

Revise the current roadmap and tranche manifest narrowly around the structured roadmap change request. Do not regenerate the roadmap from scratch. Preserve completed and unaffected pending tranche status unless the request explicitly requires superseding or reordering entries.

For the output contract's `updated_project_roadmap_path` and `updated_tranche_manifest_path`, read the paths recorded in those files and write the updated roadmap Markdown and manifest JSON to those current-checkout-relative targets. Leave the pointer files containing only the paths.
