#!/bin/bash
echo "=== Validate install_uifile JSON ==="
python3 -c '
import json
with open("/mnt/c/Users/Eg2/Desktop/saynolgy/spk-source/WIZARD_UIFILES/install_uifile") as f:
    data = json.load(f)
print(f"steps={len(data)}")
for s in data:
    print("  -", s["step_title"], ":", len(s["items"]), "items")
print("VALID")
'

echo ""
echo "=== Validate conf/privilege JSON ==="
python3 -c '
import json
with open("/mnt/c/Users/Eg2/Desktop/saynolgy/spk-source/conf/privilege") as f:
    json.load(f)
print("VALID")
'

echo ""
echo "=== Validate ui/config JSON ==="
python3 -c '
import json
with open("/mnt/c/Users/Eg2/Desktop/saynolgy/spk-source/package/ui/config") as f:
    json.load(f)
print("VALID")
'
