#!/bin/sh
echo "=== 1. Version & processes ==="
head -3 /var/packages/SaynologyAI/INFO 2>/dev/null
grep -m1 DAEMON_VERSION /var/packages/SaynologyAI/target/bin/control_daemon.py
ps -ef | grep -E "control_daemon|llama-server" | grep -v grep
echo ""

echo "=== 2. Daemon status JSON ==="
curl -s http://127.0.0.1:8181/api/version
echo ""
echo "=== 3. Direct probe llama-server :8180 ==="
curl -s -o /tmp/m.out -w "HTTP %{http_code}\n" http://127.0.0.1:8180/v1/models
head -c 300 /tmp/m.out 2>/dev/null; echo
echo ""

echo "=== 4. Current config ==="
grep -E "MODEL_PATH|CTX_SIZE|N_GPU_LAYERS|BATCH_SIZE" /var/packages/SaynologyAI/etc/saynologyai.conf
echo ""

echo "=== 5. Last 50 lines of llama-server.log ==="
tail -50 /var/packages/SaynologyAI/target/var/llama-server.log 2>/dev/null
echo ""

echo "=== 6. GPU ==="
/var/packages/NVIDIARuntimeLibrary/target/nvidia/bin/nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null
echo ""

echo "=== 7. Recent ports ==="
netstat -tln 2>/dev/null | grep -E ":818[0-9]"
