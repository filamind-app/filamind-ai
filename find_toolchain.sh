#!/bin/bash
curl -s https://archive.synology.com/download/ToolChain/toolchain/7.2-72806/ > /tmp/page.html
echo "=== Denverton entries ==="
grep -oE 'href="[^"]*\.txz"' /tmp/page.html | grep -iE 'denverton'
echo ""
echo "=== All Intel x86 platforms in 7.2-72806 ==="
grep -oE 'Intel%20x86[^"]*' /tmp/page.html | sort -u
echo ""
echo "=== File listing (architectures) ==="
grep -oE '[a-z]+-gcc1220[^"]*\.txz' /tmp/page.html | sort -u | head -40
