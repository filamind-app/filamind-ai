#!/bin/bash
# Copy NVIDIA libraries from NAS to WSL as sysroot for cross-compilation
set -e

SYSROOT=~/saynologyai/nas-sysroot
mkdir -p $SYSROOT/usr/lib
mkdir -p $SYSROOT/cuda/lib64
mkdir -p $SYSROOT/include

NAS="${NAS_HOST:?Set NAS_HOST}"
PORT=2222
PASS="${NAS_PASS:-}"

echo "=== Copying NAS NVIDIA libraries ==="

# Install sshpass if not present
if ! command -v sshpass &> /dev/null; then
    echo "Installing sshpass..."
    sudo apt-get install -y sshpass 2>&1 | tail -2
fi

# Copy NVIDIA runtime library (cuda + nvidia subdirs)
echo "--> Copying cuda/lib64 from NAS..."
sshpass -p "$PASS" scp -P $PORT -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "$NAS:/volume1/@appstore/NVIDIARuntimeLibrary/cuda/lib64/*.so*" \
    $SYSROOT/cuda/lib64/ 2>&1 | tail -3

echo "--> Copying nvidia/lib (driver libs) from NAS..."
sshpass -p "$PASS" scp -P $PORT -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "$NAS:/volume1/@appstore/NVIDIARuntimeLibrary/nvidia/lib/*.so*" \
    $SYSROOT/usr/lib/ 2>&1 | tail -3

echo ""
echo "=== Result ==="
echo "cuda/lib64 files:"
ls $SYSROOT/cuda/lib64/ | wc -l
echo "usr/lib files:"
ls $SYSROOT/usr/lib/ | wc -l
echo ""
echo "Key libraries present:"
for lib in libcuda.so libcudart.so libnvidia-ml.so libcudnn.so libcublas.so; do
    found=$(find $SYSROOT -name "$lib*" 2>/dev/null | head -1)
    if [ -n "$found" ]; then echo "  ✓ $lib  ($found)"
    else echo "  ✗ $lib MISSING"; fi
done
