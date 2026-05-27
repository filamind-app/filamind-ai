#!/bin/bash
# Patch llama.cpp ggml-cuda.cu for CUDA 10.x compatibility
set -e

FILE=~/saynologyai/llama.cpp-cuda10/ggml-cuda.cu

# Check if already patched
if grep -q "CUDART_VERSION < 11000" "$FILE"; then
    echo "Already patched."
    exit 0
fi

# Insert CUDA 10 compat defines after #include <cuda_fp16.h>
python3 - <<'PYEOF'
import re
path = "/root/saynologyai/llama.cpp-cuda10/ggml-cuda.cu"
with open(path) as f:
    content = f.read()

patch = '''#include <cuda_fp16.h>
#if CUDART_VERSION < 11000
// CUDA 10.x compatibility: provide missing cuBLAS 11 identifiers
#define CUBLAS_COMPUTE_16F          CUDA_R_16F
#define CUBLAS_COMPUTE_32F          CUDA_R_32F
#define CUBLAS_COMPUTE_32F_FAST_16F CUDA_R_32F
#define CUBLAS_TF32_TENSOR_OP_MATH  CUBLAS_DEFAULT_MATH
#endif
'''
old = '#include <cuda_fp16.h>'
if content.count(old) != 1:
    raise SystemExit(f"Expected exactly one occurrence of '{old}', found {content.count(old)}")

content = content.replace(old, patch.rstrip())
with open(path, 'w') as f:
    f.write(content)
print("Patched.")
PYEOF

echo "Verifying patch..."
grep -A1 "CUDART_VERSION < 11000" "$FILE" | head -5
