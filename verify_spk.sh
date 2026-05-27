#!/bin/bash
set -e
WORK=$(mktemp -d)
cd "$WORK"
tar xf /mnt/c/Users/Eg2/Desktop/saynolgy/SaynologyAI.spk
tar xzf package.tgz
echo "=== INFO version ==="
grep "^version=" INFO
echo "=== index.html search ==="
grep -c "build body with minimal fields" web/index.html || echo "0"
grep -c "parseInt(s.mirostat) > 0" web/index.html || echo "0"
echo "=== sendMessage body block ==="
grep -nA15 "Build body with minimal fields" web/index.html | head -20
cd /
rm -rf "$WORK"
