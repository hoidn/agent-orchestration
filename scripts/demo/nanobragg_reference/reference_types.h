#ifndef NANOBRAGG_REFERENCE_TYPES_H
#define NANOBRAGG_REFERENCE_TYPES_H

/* Narrow data boundary for the simplified offline reference harness. */

typedef struct {
    int spixels;
    int fpixels;
    int subpixel_steps;
    int detector_thicksteps;
    int oversample_omega;
    int oversample_thick;
    int n_sources;
    int n_phi_values;
    int n_mosaic_domains;
    double subpixel_size;
    double pixel_size;
    double close_distance;
    double thickness;
    double mu;
    double detector_origin[3];
    double fast_axis[3];
    double slow_axis[3];
} reference_fixture_t;

typedef struct {
    double direction[3];
    double wavelength;
    double weight;
} reference_source_t;

typedef struct {
    double weight;
} reference_mosaic_domain_t;

int accumulate_reference_image(
    const reference_fixture_t *fixture,
    const reference_source_t *sources,
    const reference_mosaic_domain_t *domains,
    double *out_image
);

#endif
