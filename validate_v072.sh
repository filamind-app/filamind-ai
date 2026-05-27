#!/bin/bash
set -e
echo "=== Validate daemon Python syntax ==="
python3 -c "
import ast
ast.parse(open('/mnt/c/Users/Eg2/Desktop/saynolgy/spk-source/package/bin/control_daemon.py').read())
print('daemon: syntax OK')
"
echo "=== Validate JSON files ==="
python3 -c "
import json
for p in [
    '/mnt/c/Users/Eg2/Desktop/saynolgy/spk-source/package/ui/config',
    '/mnt/c/Users/Eg2/Desktop/saynolgy/spk-source/package/web/i18n/en.json',
    '/mnt/c/Users/Eg2/Desktop/saynolgy/spk-source/package/web/i18n/ar.json',
    '/mnt/c/Users/Eg2/Desktop/saynolgy/spk-source/WIZARD_UIFILES/install_uifile',
    '/mnt/c/Users/Eg2/Desktop/saynolgy/spk-source/conf/privilege',
]:
    json.load(open(p))
    print(p.split('/')[-1] + ': OK')
"
