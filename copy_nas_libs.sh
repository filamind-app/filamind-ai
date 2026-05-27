#!/bin/bash
# Copy NVIDIA libraries from the Synology NAS to a WSL sysroot for cross-compiling
# llama.cpp against CUDA 10.1. Credentials come from environment variables — never
# hard-code them in this file (it is in a public-ish git repo).
#
# Usage:
#   export NAS_HOST=eg2@192.168.0.253
#   export NAS_PORT=2222
#   export NAS_PASS='your-password'        # OR set up SSH key auth and unset NAS_PASS
#   bash copy_nas_libs.sh
#
# If NAS_PASS is empty, scp uses your default SSH agent / key.

set -e

SYSROOT="${SYSROOT:-$HOME/filamindai/nas-sysroot}"
mkdir -p "$SYSROOT/usr/lib" "$SYSROOT/cuda/lib64" "$SYSROOT/include"

NAS="${NAS_HOST:?Set NAS_HOST, e.g. export NAS_HOST=user@nas-ip}"
PORT="${NAS_PORT:-2222}"

# Resolve transport: prefer SSH key auth; fall back to sshpass only if NAS_PASS is set.
if [ -n "${NAS_PASS:-}" ]; then
    if ! command -v sshpass &> /dev/null; then
        echo "Installing sshpass..."
        sudo apt-get install -y sshpass 2>&1 | tail -2
    fi
    SCP="sshpass -e scp"
    export SSHPASS="$NAS_PASS"
else
    SCP="scp"
fi

SCP_OPTS=(-P "$PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)

echo "=== Copying NAS NVIDIA libraries from $NAS:$PORT ==="

echo "--> Copying cuda/lib64..."
$SCP "${SCP_OPTS[@]}" \
    "$NAS:/volume1/@appstore/NVIDIARuntimeLibrary/cuda/lib64/*.so*" \
    "$SYSROOT/cuda/lib64/" 2>&1 | tail -3

echo "--> Copying nvidia/lib (driver libs)..."
$SCP "${SCP_OPTS[@]}" \
    "$NAS:/volume1/@appstore/NVIDIARuntimeLibrary/nvidia/lib/*.so*" \
    "$SYSROOT/usr/lib/" 2>&1 | tail -3

unset SSHPASS

echo ""
echo "=== Result ==="
echo "cuda/lib64 files: $(ls $SYSROOT/cuda/lib64/ 2>/dev/null | wc -l)"
echo "usr/lib   files: $(ls $SYSROOT/usr/lib/ 2>/dev/null | wc -l)"
echo ""
echo "Key libraries present:"
for lib in libcuda.so libcudart.so libnvidia-ml.so libcudnn.so libcublas.so; do
    found=$(find "$SYSROOT" -name "$lib*" 2>/dev/null | head -1)
    if [ -n "$found" ]; then echo "  ✓ $lib  ($found)"
    else echo "  ✗ $lib MISSING"; fi
done
