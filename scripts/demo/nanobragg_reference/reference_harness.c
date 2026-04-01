#include "reference_types.h"

#include <math.h>
#include <stdio.h>

static double dot3(const double a[3], const double b[3]) {
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

static void cross3(const double a[3], const double b[3], double out[3]) {
    out[0] = a[1] * b[2] - a[2] * b[1];
    out[1] = a[2] * b[0] - a[0] * b[2];
    out[2] = a[0] * b[1] - a[1] * b[0];
}

static double normalize3(double v[3]) {
    double mag = sqrt(dot3(v, v));
    if (mag > 0.0) {
        v[0] /= mag;
        v[1] /= mag;
        v[2] /= mag;
    }
    return mag;
}

int accumulate_reference_image(
    const reference_fixture_t *fixture,
    const reference_source_t *sources,
    const reference_mosaic_domain_t *domains,
    double *out_image
) {
    int spixel;
    int fpixel;
    int thick_tic;
    int subS;
    int subF;
    int source;
    int phi_tic;
    int mos_tic;
    int idx;
    double odet[3];
    double steps;

    if (fixture == NULL || out_image == NULL) {
        return 1;
    }
    if (fixture->spixels <= 0 || fixture->fpixels <= 0) {
        return 2;
    }
    if (fixture->subpixel_steps <= 0 || fixture->detector_thicksteps <= 0) {
        return 3;
    }
    if (fixture->n_sources <= 0 || fixture->n_phi_values <= 0 || fixture->n_mosaic_domains <= 0) {
        return 4;
    }

    cross3(fixture->fast_axis, fixture->slow_axis, odet);
    if (normalize3(odet) == 0.0) {
        return 5;
    }

    steps = (double)(fixture->subpixel_steps * fixture->subpixel_steps);

    for (spixel = 0; spixel < fixture->spixels; ++spixel) {
        for (fpixel = 0; fpixel < fixture->fpixels; ++fpixel) {
            double I = 0.0;
            double omega_pixel = 0.0;
            double capture_fraction = fixture->thickness == 0.0 ? 1.0 : 0.0;

            for (thick_tic = 0; thick_tic < fixture->detector_thicksteps; ++thick_tic) {
                double Odet = ((double)thick_tic) * (fixture->thickness / fixture->detector_thicksteps);
                capture_fraction = fixture->thickness == 0.0 ? 1.0 : 0.0;

                for (subS = 0; subS < fixture->subpixel_steps; ++subS) {
                    for (subF = 0; subF < fixture->subpixel_steps; ++subF) {
                        double Fdet = fixture->subpixel_size * (fpixel * fixture->subpixel_steps + subF)
                                    + fixture->subpixel_size / 2.0;
                        double Sdet = fixture->subpixel_size * (spixel * fixture->subpixel_steps + subS)
                                    + fixture->subpixel_size / 2.0;
                        double pixel_pos[3];
                        double diffracted[3];
                        double airpath;

                        pixel_pos[0] =
                            Fdet * fixture->fast_axis[0]
                            + Sdet * fixture->slow_axis[0]
                            + Odet * odet[0]
                            + fixture->detector_origin[0];
                        pixel_pos[1] =
                            Fdet * fixture->fast_axis[1]
                            + Sdet * fixture->slow_axis[1]
                            + Odet * odet[1]
                            + fixture->detector_origin[1];
                        pixel_pos[2] =
                            Fdet * fixture->fast_axis[2]
                            + Sdet * fixture->slow_axis[2]
                            + Odet * odet[2]
                            + fixture->detector_origin[2];

                        diffracted[0] = pixel_pos[0];
                        diffracted[1] = pixel_pos[1];
                        diffracted[2] = pixel_pos[2];
                        airpath = normalize3(diffracted);
                        if (airpath == 0.0) {
                            return 6;
                        }

                        if (omega_pixel == 0.0 || fixture->oversample_omega) {
                            omega_pixel =
                                fixture->pixel_size * fixture->pixel_size
                                / (airpath * airpath)
                                * fixture->close_distance / airpath;
                        }

                        if (capture_fraction == 0.0 || fixture->oversample_thick) {
                            double parallax = dot3(diffracted, odet);
                            double thickstep = fixture->thickness / fixture->detector_thicksteps;
                            if (parallax == 0.0) {
                                return 7;
                            }
                            capture_fraction =
                                exp(-thick_tic * thickstep * fixture->mu / parallax)
                                - exp(-(thick_tic + 1) * thickstep * fixture->mu / parallax);
                        }

                        for (source = 0; source < fixture->n_sources; ++source) {
                            for (phi_tic = 0; phi_tic < fixture->n_phi_values; ++phi_tic) {
                                for (mos_tic = 0; mos_tic < fixture->n_mosaic_domains; ++mos_tic) {
                                    double contribution = sources[source].weight * domains[mos_tic].weight;
                                    if (fixture->oversample_thick) {
                                        contribution *= capture_fraction;
                                    }
                                    if (fixture->oversample_omega) {
                                        contribution *= omega_pixel;
                                    }
                                    I += contribution;
                                }
                            }
                        }
                    }
                }
            }

            idx = spixel * fixture->fpixels + fpixel;
            out_image[idx] = I / steps;
            if (!fixture->oversample_thick) {
                out_image[idx] *= capture_fraction;
            }
            if (!fixture->oversample_omega) {
                out_image[idx] *= omega_pixel;
            }
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    fprintf(stderr, "reference_harness.c is a library-backed maintenance tool; use run_reference_case.py\n");
    return 0;
}
