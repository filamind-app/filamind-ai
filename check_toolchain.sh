#!/bin/bash
TC=~/saynologyai/toolchain/extracted/x86_64-pc-linux-gnu
echo "=== Toolchain root: $TC ==="
echo "=== Binaries (first 20) ==="
ls $TC/bin/ | head -20
echo ""
echo "=== GCC version ==="
$TC/bin/x86_64-pc-linux-gnu-gcc --version | head -2
echo ""
echo "=== Cross-compile test ==="
mkdir -p ~/saynologyai/test
cat > ~/saynologyai/test/hello.c << 'CEOF'
#include <stdio.h>
int main() { printf("Hello from cross-compiled binary\n"); return 0; }
CEOF
$TC/bin/x86_64-pc-linux-gnu-gcc ~/saynologyai/test/hello.c -o ~/saynologyai/test/hello
echo "Compile exit: $?"
file ~/saynologyai/test/hello
echo ""
echo "=== sysroot contents ==="
ls $TC/x86_64-pc-linux-gnu/sys-root/usr/include/ 2>/dev/null | head -10
