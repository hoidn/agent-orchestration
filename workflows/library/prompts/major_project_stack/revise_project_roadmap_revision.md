Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read `project_brief`, `roadmap_change_request`, `roadmap_revision_report`, `updated_project_roadmap`, and `updated_tranche_manifest` before acting.

Revise only the roadmap and manifest issues identified by review. Preserve unaffected tranche ordering, statuses, and artifacts.

For the output contract's `updated_project_roadmap_path` and `updated_tranche_manifest_path`, read the paths recorded in those files and write the revised roadmap Markdown and manifest JSON to those current-checkout-relative targets. Leave the pointer files containing only the paths.
