#!/bin/bash
# Build llama.cpp CPU-only with Synology toolchain
set -e

LLAMA_SRC=~/saynologyai/llama.cpp-cuda10
BUILD_DIR=~/saynologyai/build/llama-cpu
TOOLCHAIN=/mnt/c/Users/Eg2/Desktop/saynolgy/synology-toolchain.cmake

# Need cmake
if ! command -v cmake &> /dev/null; then
    echo "Installing cmake..."
    sudo apt-get install -y cmake 2>&1 | tail -2
fi

mkdir -p $BUILD_DIR
cd $BUILD_DIR

echo "=== Configuring llama.cpp (CPU-only) ==="
cmake $LLAMA_SRC \
    -DCMAKE_TOOLCHAIN_FILE=$TOOLCHAIN \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_CUBLAS=OFF \
    -DLLAMA_NATIVE=OFF \
    -DLLAMA_AVX=OFF \
    -DLLAMA_AVX2=OFF \
    -DLLAMA_AVX512=OFF \
    -DLLAMA_FMA=OFF \
    -DLLAMA_F16C=OFF \
    -DLLAMA_SSE3=ON \
    -DBUILD_SHARED_LIBS=OFF \
    2>&1 | tail -20

echo ""
echo "=== Building (this takes ~5-10 min) ==="
cmake --build . --config Release -j$(nproc) --target server main 2>&1 | tail -10

echo ""
echo "=== Binaries ==="
ls -lh bin/ 2>/dev/null
file bin/server 2>/dev/null
file bin/main 2>/dev/null
