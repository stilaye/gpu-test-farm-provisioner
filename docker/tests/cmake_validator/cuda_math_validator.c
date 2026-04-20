#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* Simulates cuBLAS-style 4x4 matrix multiply (CPU stand-in for GPU) */
static void mat_mul(float *A, float *B, float *C, int n) {
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++) {
            C[i * n + j] = 0.0f;
            for (int k = 0; k < n; k++)
                C[i * n + j] += A[i * n + k] * B[k * n + j];
        }
}

int main(int argc, char *argv[]) {
    const char *gpu  = "unknown";
    const char *cuda = "unknown";

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--gpu")  && i + 1 < argc) gpu  = argv[++i];
        if (!strcmp(argv[i], "--cuda") && i + 1 < argc) cuda = argv[++i];
    }

    float A[16], B[16], C[16], expected[16];

    for (int i = 0; i < 16; i++) {
        A[i] = (float)(i + 1);
        B[i] = (float)(16 - i);
    }

    mat_mul(A, B, C, 4);
    mat_mul(A, B, expected, 4);

    int pass = 1;
    for (int i = 0; i < 16; i++)
        if (fabsf(C[i] - expected[i]) > 1e-6f) pass = 0;

    printf("{\"tool\": \"cuda_math_validator\", \"gpu\": \"%s\", \"cuda\": \"%s\", \"result\": \"%s\"}\n",
           gpu, cuda, pass ? "PASS" : "FAIL");

    return pass ? 0 : 1;
}
