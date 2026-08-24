/*
 * Native launcher for the fake OMP binary (Task 5 fix round).
 *
 * The confined helper execs the verified private copy through a descriptor
 * (execveat with AT_EMPTY_PATH), which the kernel refuses for shebang
 * scripts (the interpreter is handed an empty script path -> ENOENT). The
 * production pinned binary is a native ELF, so this is a test-only seam:
 * the launcher is the fd-exec'd ELF and hands control to the real fake
 * python implementation with the script path embedded at compile time.
 *
 * Compile (once per session, by the test harness):
 *   cc -O1 -o fake_launcher fake_launcher.c -DOMP_FAKE_SCRIPT=\"<abs path>\"
 */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#ifndef OMP_FAKE_SCRIPT
#error OMP_FAKE_SCRIPT must be defined at compile time
#endif

int main(int argc, char **argv) {
    char **nargv = malloc(sizeof(char *) * (size_t)(argc + 2));
    if (nargv == NULL) {
        return 127;
    }
    nargv[0] = "python3";
    nargv[1] = OMP_FAKE_SCRIPT;
    for (int i = 1; i < argc; i++) {
        nargv[i + 1] = argv[i];
    }
    nargv[argc + 1] = NULL;
    execvp("python3", nargv);
    perror("fake_launcher: execvp python3");
    return 127;
}
