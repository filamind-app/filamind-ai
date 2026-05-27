#!/bin/sh
echo "=== jellyfin app ==="
ls /var/packages/jellyfin/target/app/ 2>&1
echo
echo "=== jellyfin app config ==="
cat /var/packages/jellyfin/target/app/config 2>&1
echo
echo "=== jellyfin INFO fields ==="
grep -E "dsmuidir|dsmappname|displayname|^app_" /var/packages/jellyfin/INFO 2>&1
echo
echo "=== All ui/config or app/config files with 'url' type ==="
for f in /var/packages/*/target/ui/config /var/packages/*/target/app/config; do
    if [ -f "$f" ] && grep -q 'url' "$f" 2>/dev/null; then
        echo "--- $f ---"
        head -20 "$f"
        echo "..."
    fi
done
