#!/bin/sh
echo "=========================================="
echo " 1. Package version & status"
echo "=========================================="
head -3 /var/packages/SaynologyAI/INFO 2>/dev/null
echo ""
ls -la /var/packages/SaynologyAI/target/bin/control_daemon.py 2>/dev/null
echo ""
grep -m1 'DAEMON_VERSION' /var/packages/SaynologyAI/target/bin/control_daemon.py
echo ""

echo "=========================================="
echo " 2. Processes"
echo "=========================================="
ps -ef | grep -E "control_daemon|llama-server" | grep -v grep
echo ""

echo "=========================================="
echo " 3. Listening ports"
echo "=========================================="
netstat -tlnp 2>/dev/null | grep -E ":818[0-9]|:8181" | head
echo ""

echo "=========================================="
echo " 4. Current config"
echo "=========================================="
cat /var/packages/SaynologyAI/etc/saynologyai.conf 2>/dev/null
echo ""

echo "=========================================="
echo " 5. Last 80 lines of llama-server.log"
echo "=========================================="
tail -80 /var/packages/SaynologyAI/target/var/llama-server.log 2>/dev/null

echo ""
echo "=========================================="
echo " 6. nvidia-smi"
echo "=========================================="
/var/packages/NVIDIARuntimeLibrary/target/nvidia/bin/nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv,noheader 2>/dev/null

echo ""
echo "=========================================="
echo " 7. Direct curl to llama-server (internal :8180)"
echo "=========================================="
curl -s -o /tmp/curl_test.out -w "HTTP %{http_code} (time %{time_total}s)\n" \
    -X POST http://127.0.0.1:8180/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{"stream":false,"messages":[{"role":"user","content":"Say OK"}],"max_tokens":5,"temperature":0.1}'
echo "Response body:"
cat /tmp/curl_test.out 2>/dev/null | head -c 800
echo ""

echo ""
echo "=========================================="
echo " 8. Direct curl to daemon (:8181 - public)"
echo "=========================================="
curl -s -o /tmp/curl_v.out -w "HTTP %{http_code}\n" http://127.0.0.1:8181/api/version
cat /tmp/curl_v.out 2>/dev/null
echo ""

echo ""
echo "=========================================="
echo " 9. Models in volume1/SaynologyAI/models/"
echo "=========================================="
ls -lh /volume1/SaynologyAI/models/ 2>/dev/null
echo ""

echo "=========================================="
echo "10. Daemon-specific recent log (if exists separately)"
echo "=========================================="
ls -la /var/packages/SaynologyAI/target/var/ 2>/dev/null
echo ""
