#!/bin/bash
set -e
TC=~/saynologyai/toolchain/extracted/x86_64-pc-linux-gnu
GCC=$TC/bin/x86_64-pc-linux-gnu-gcc
SRC=/mnt/c/Users/Eg2/Desktop/saynolgy/hello_gpu.c
OUT=~/saynologyai/build/hello_gpu

mkdir -p ~/saynologyai/build

echo "=== Cross-compiling hello_gpu ==="
$GCC -O2 -Wall -o $OUT $SRC -ldl
echo "Compile exit: $?"
echo ""
echo "=== Binary info ==="
file $OUT
ls -lh $OUT
echo ""
echo "=== Dynamic dependencies ==="
$TC/bin/x86_64-pc-linux-gnu-readelf -d $OUT | grep NEEDED

cp $OUT /mnt/c/Users/Eg2/Desktop/saynolgy/hello_gpu
echo ""
echo "Copied to: /mnt/c/Users/Eg2/Desktop/saynolgy/hello_gpu"
