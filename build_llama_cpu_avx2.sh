#!/bin/bash
# Build llama.cpp CPU-only for DS1821+ (AMD Ryzen V1500B, znver1 / AVX2 / FMA)
# Output: spk-source/package/bin/llama-server
#
# Prerequisites (one-time):
#   1. WSL2 Ubuntu 22.04+
#   2. Synology v1000 toolchain extracted under ~/synology/toolchain/v1000/
#      Download: https://archive.synology.com/download/ToolChain/toolchain/
#   3. apt install build-essential cmake git
#
# Usage:
#   bash build_llama_cpu_avx2.sh                  # build with latest llama.cpp
#   LLAMA_REF=b5500 bash build_llama_cpu_avx2.sh  # pin to specific ref

set -euo pipefail

# ───── Config ────────────────────────────────────────────────────────────────
TOOLCHAIN_DIR="${TOOLCHAIN_DIR:-$HOME/synology/toolchain/v1000}"
LLAMA_REF="${LLAMA_REF:-master}"          # default: latest. Pin to a tag for repro builds.
SRC_DIR="${HOME}/build/llama.cpp-v1000"
SPK_BIN="$(cd "$(dirname "$0")" && pwd)/spk-source/package/bin"
JOBS="$(nproc)"

# ───── Verify toolchain ──────────────────────────────────────────────────────
if [ ! -d "${TOOLCHAIN_DIR}" ]; then
    echo "ERROR: Synology v1000 toolchain not found at ${TOOLCHAIN_DIR}"
    echo "Download from https://archive.synology.com/download/ToolChain/toolchain/"
    echo "Look for 'DSM 7.2 v1000' (e.g. v1000-gcc1220_glibc236_*.txz)"
    exit 1
fi

CROSS_PREFIX="x86_64-pc-linux-gnu-"
CC="${TOOLCHAIN_DIR}/bin/${CROSS_PREFIX}gcc"
CXX="${TOOLCHAIN_DIR}/bin/${CROSS_PREFIX}g++"
SYSROOT="${TOOLCHAIN_DIR}/${CROSS_PREFIX%?}/sysroot"

for tool in "${CC}" "${CXX}"; do
    [ -x "${tool}" ] || { echo "ERROR: missing ${tool}"; exit 1; }
done
[ -d "${SYSROOT}" ] || { echo "ERROR: missing sysroot ${SYSROOT}"; exit 1; }

echo "=== Toolchain ==="
"${CC}" --version | head -1
echo "Sysroot: ${SYSROOT}"
echo ""

# ───── Clone / update llama.cpp ──────────────────────────────────────────────
if [ ! -d "${SRC_DIR}/.git" ]; then
    echo "=== Cloning llama.cpp ==="
    mkdir -p "$(dirname "${SRC_DIR}")"
    git clone https://github.com/ggerganov/llama.cpp.git "${SRC_DIR}"
fi
cd "${SRC_DIR}"
git fetch --all --tags
git checkout "${LLAMA_REF}"
git pull --ff-only origin "${LLAMA_REF}" 2>/dev/null || true

# ───── Build ─────────────────────────────────────────────────────────────────
echo "=== Building llama.cpp ${LLAMA_REF} for Ryzen V1500B (znver1) ==="
BUILD_DIR="build-v1000"
rm -rf "${BUILD_DIR}"

# CPU flags for Ryzen Embedded V1500B (Zen 1)
#   -march=znver1   → schedule for Zen 1
#   -mavx2 -mfma    → required (V1500B supports both)
#   -mf16c          → fast fp16 conversion
#   No -mavx512*    → V1500B has no AVX-512
CPU_FLAGS="-march=znver1 -mavx2 -mfma -mf16c -O3 -DNDEBUG"

cmake -S . -B "${BUILD_DIR}" \
    -DCMAKE_C_COMPILER="${CC}" \
    -DCMAKE_CXX_COMPILER="${CXX}" \
    -DCMAKE_SYSROOT="${SYSROOT}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_NATIVE=OFF \
    -DGGML_NATIVE=OFF \
    -DGGML_AVX2=ON \
    -DGGML_FMA=ON \
    -DGGML_F16C=ON \
    -DGGML_AVX512=OFF \
    -DGGML_CUDA=OFF \
    -DGGML_OPENBLAS=OFF \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_EXAMPLES=ON \
    -DLLAMA_BUILD_SERVER=ON \
    -DCMAKE_C_FLAGS="${CPU_FLAGS}" \
    -DCMAKE_CXX_FLAGS="${CPU_FLAGS}"

cmake --build "${BUILD_DIR}" --target llama-server -j "${JOBS}"

# ───── Verify + copy ─────────────────────────────────────────────────────────
BIN="${BUILD_DIR}/bin/llama-server"
[ -x "${BIN}" ] || { echo "ERROR: llama-server not produced"; exit 1; }

echo ""
echo "=== Built binary ==="
file "${BIN}"
"${TOOLCHAIN_DIR}/bin/${CROSS_PREFIX}strip" "${BIN}" || true
ls -lh "${BIN}"
echo ""

mkdir -p "${SPK_BIN}"
cp "${BIN}" "${SPK_BIN}/llama-server"
chmod +x "${SPK_BIN}/llama-server"

echo "=== Done ==="
echo "Output: ${SPK_BIN}/llama-server"
echo ""
echo "Next: run bash build_spk.sh to package Filamind.spk for DS1821+"
