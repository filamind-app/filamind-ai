#!/bin/sh
echo "=== Recent daemon log entries (Gemini errors) ==="
grep -E "Gemini|429|gemini" /var/packages/SaynologyAI/target/var/llama-server.log 2>/dev/null | tail -25

echo ""
echo "=== Direct probe of Gemini API quota ==="
# Get providers.json indirectly via daemon — we need the API key
# But the file is owned by saynologyai. Let's just hit the /v1/models endpoint
# from Gemini directly using a tiny test.

# Read the api key from providers.json (eg2 may not have access — but try)
ls -la /var/packages/SaynologyAI/etc/providers.json 2>/dev/null

echo ""
echo "=== Daemon log last 60 lines (entire) ==="
tail -60 /var/packages/SaynologyAI/target/var/llama-server.log 2>/dev/null

echo ""
echo "=== Daemon process info ==="
ps -ef | grep control_daemon | grep -v grep
