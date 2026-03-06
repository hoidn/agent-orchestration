# Visible fixture schema

These fixtures are visible smoke inputs for the bounded nanoBragg accumulation task. They are intentionally incomplete and do not include hidden expected output tensors.

Each fixture file uses only JSON primitive types and arrays. The schema is:
- `case_id`: short case name
- `detector`: object with detector dimensions and subpixel settings
- `oversample`: object describing omega/thickness oversampling switches and counts
- `sources`: array of source-vector and wavelength records
- `phi_values`: array of rotation values for the scoped case
- `mosaic_domains`: array of simplified mosaic-domain descriptors
- `geometry`: object containing per-pixel coordinate inputs and scalar detector terms used by the bounded subsystem
- `expected`: object containing only visible smoke expectations such as tensor shape and optional trace-tap coordinates

These fixtures are for local smoke checks only. Hidden parity expectations live outside the visible seed.
