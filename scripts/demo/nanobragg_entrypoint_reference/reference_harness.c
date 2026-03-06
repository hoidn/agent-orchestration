#include "reference_harness.h"

#define main nanobragg_reference_main
#include "../../../../nanoBragg/golden_suite_generator/nanoBragg.c"
#undef main

int nanobragg_run(int argc, char **argv) {
    return nanobragg_reference_main(argc, argv);
}
