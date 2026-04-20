#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char *argv[]) {
    char version[64] = "unknown";
    const char *expected = NULL;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--expected") && i + 1 < argc)
            expected = argv[++i];
    }

    FILE *fp = fopen("/usr/local/cuda/version.txt", "r");
    if (fp) {
        fgets(version, sizeof(version), fp);
        fclose(fp);
    }
    version[strcspn(version, "\n")] = 0;

    int pass = 1;
    if (expected && strstr(version, expected) == NULL)
        pass = 0;

    printf("{\"tool\": \"cuda_version_checker\", \"installed\": \"%s\", \"expected\": \"%s\", \"result\": \"%s\"}\n",
           version,
           expected ? expected : "any",
           pass ? "PASS" : "FAIL");

    return pass ? 0 : 1;
}
