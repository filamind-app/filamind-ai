#!/bin/bash
# Build llama-server for DS1821+ (Ryzen V1500B, AVX2) using the WSL native
# gcc toolchain, with static libstdc++/libgcc so the binary runs on DSM 7.2's
# glibc 2.36 without depending on the build host's libstdc++ version.
# CPU-only, no OpenMP/CURL → minimal runtime deps (glibc, libm, libpthread).
set -e
SRC=~/llama-ds1821
OUT=/mnt/c/Users/Eg2/Desktop/saynolgy/ds1821-llama-server

echo "=== [1/4] deps ==="
which git cmake gcc g++ >/dev/null || { echo "missing build tools"; exit 1; }
gcc --version | head -1

echo "=== [2/4] clone llama.cpp (shallow, pinned b4400; fallback master) ==="
rm -rf "$SRC"
git clone --depth 1 --branch b4400 https://github.com/ggerganov/llama.cpp "$SRC" 2>&1 | tail -2 \
  || git clone --depth 1 https://github.com/ggerganov/llama.cpp "$SRC" 2>&1 | tail -2
cd "$SRC"
echo "checked out: $(git describe --tags --always 2>/dev/null || echo unknown)"

echo "=== [3/4] configure (AVX2 znver1, static stdc++, no OpenMP/CURL) ==="
cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON -DGGML_AVX512=OFF \
  -DGGML_OPENMP=OFF -DLLAMA_CURL=OFF -DGGML_CUDA=OFF \
  -DBUILD_SHARED_LIBS=OFF \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=ON -DLLAMA_BUILD_SERVER=ON \
  -DCMAKE_C_FLAGS="-march=znver1 -mavx2 -mfma -mf16c -O3" \
  -DCMAKE_CXX_FLAGS="-march=znver1 -mavx2 -mfma -mf16c -O3" \
  -DCMAKE_EXE_LINKER_FLAGS="-static-libgcc -static-libstdc++" 2>&1 | tail -6

echo "=== [4/4] build llama-server ==="
cmake --build build --target llama-server -j"$(nproc)" 2>&1 | tail -10

BIN=$(find build -name "llama-server" -type f | head -1)
if [ -z "$BIN" ]; then echo "BUILD FAILED: no llama-server produced"; exit 1; fi
strip "$BIN" || true
cp "$BIN" "$OUT"
echo "=== DONE ==="
ls -lh "$OUT"
file "$OUT"
echo "--- dynamic deps (should be only glibc/libm/libpthread) ---"
ldd "$OUT" || true
