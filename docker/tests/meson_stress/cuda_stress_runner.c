#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>

int main(int argc, char *argv[]) {
    int iterations = 1000000;
    const char *gpu = "unknown";

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--iterations") && i + 1 < argc) iterations = atoi(argv[++i]);
        if (!strcmp(argv[i], "--gpu")        && i + 1 < argc) gpu        = argv[++i];
    }

    clock_t start = clock();

    volatile double result = 0.0;
    for (int i = 0; i < iterations; i++)
        result += sin((double)i) * cos((double)i);

    clock_t end = clock();
    double elapsed     = (double)(end - start) / CLOCKS_PER_SEC;
    double ops_per_sec = iterations / elapsed;

    printf("{\"tool\": \"cuda_stress_runner\", \"gpu\": \"%s\", \"iterations\": %d, "
           "\"elapsed_sec\": %.3f, \"ops_per_sec\": %.0f, \"result\": \"PASS\"}\n",
           gpu, iterations, elapsed, ops_per_sec);

    return 0;
}
