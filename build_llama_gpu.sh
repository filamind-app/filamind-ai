#!/bin/bash
# Build llama.cpp with CUDA via Makefile (simpler than CMake for this version)
set -e

CUDA_HOME=/root/saynologyai/cuda-tk/extracted/builds/cuda-toolkit
NAS_SYSROOT=~/saynologyai/nas-sysroot
LLAMA_SRC=~/saynologyai/llama.cpp-cuda10

echo "=== Using gcc-9 + nvcc 10.1 ==="
gcc-9 --version | head -1
$CUDA_HOME/bin/nvcc --version | head -4

# Patch host_config.h
HOST_CONFIG=$CUDA_HOME/include/crt/host_config.h
sed -i 's/__GNUC__ > [0-9]\+/__GNUC__ > 999/g' "$HOST_CONFIG"
sed -i 's/^#error -- unsupported GNU version!/\/\/ #error -- unsupported GNU version!/g' "$HOST_CONFIG"

# Build
cd $LLAMA_SRC
make clean

# Temporarily hide /usr/local/cuda (CUDA 12) so linker picks our CUDA 10
SAVED_CUDA=""
if [ -L /usr/local/cuda ]; then
    SAVED_CUDA=$(readlink /usr/local/cuda)
    sudo rm /usr/local/cuda
    echo "Temporarily removed /usr/local/cuda symlink (was -> $SAVED_CUDA)"
fi
# Restore on exit
trap '[ -n "$SAVED_CUDA" ] && sudo ln -sf "$SAVED_CUDA" /usr/local/cuda 2>/dev/null' EXIT

echo ""
echo "=== Building llama.cpp with Makefile + CUDA 10 ==="
PATH=$CUDA_HOME/bin:$PATH \
CUDA_DOCKER_ARCH=sm_75 \
make LLAMA_CUBLAS=1 \
     LLAMA_NO_AVX=1 \
     LLAMA_NO_AVX2=1 \
     LLAMA_NO_AVX512=1 \
     LLAMA_NO_FMA=1 \
     LLAMA_NO_F16C=1 \
     CUDA_PATH=$CUDA_HOME \
     CUDA_VERSION=10.1 \
     NVCC=$CUDA_HOME/bin/nvcc \
     NVCCFLAGS="-ccbin=/usr/bin/g++-9 -std=c++14 -arch=sm_75 -Xcompiler -march=x86-64" \
     CC=gcc-9 \
     CXX=g++-9 \
     CFLAGS="-march=x86-64 -mtune=generic -msse4.2" \
     CXXFLAGS="-march=x86-64 -mtune=generic -msse4.2" \
     LDFLAGS="-L$NAS_SYSROOT/cuda/lib64 -L$NAS_SYSROOT/usr/lib -L$CUDA_HOME/targets/x86_64-linux/lib -static-libgcc -static-libstdc++ -Wl,--no-as-needed -Wl,-rpath-link,$NAS_SYSROOT/cuda/lib64:$NAS_SYSROOT/usr/lib" \
     -j$(nproc) main server 2>&1 | tail -30

echo ""
echo "=== Result ==="
ls -lh $LLAMA_SRC/main $LLAMA_SRC/server 2>/dev/null
file $LLAMA_SRC/server 2>/dev/null
echo "Dynamic deps:"
ldd $LLAMA_SRC/server 2>&1 | head -15
