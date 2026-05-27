#!/bin/sh
export LD_LIBRARY_PATH=/var/packages/NVIDIARuntimeLibrary/target/cuda/lib64:/var/packages/NVIDIARuntimeLibrary/target/nvidia/lib

# Kill any leftover server
pkill -f llama-server-gpu 2>/dev/null
sleep 1

# Start server in background
~/llama-server-gpu \
    --model ~/tinyllama.gguf \
    --n-gpu-layers 99 \
    --ctx-size 1024 \
    --host 127.0.0.1 \
    --port 18181 \
    > /tmp/llama.log 2>&1 &
SERVER_PID=$!
echo "Server PID: $SERVER_PID"

# Wait up to 90 seconds for server to be ready
READY=0
for i in $(seq 1 45); do
    sleep 2
    if grep -q "HTTP server listening\|HTTP server is listening\|server is listening" /tmp/llama.log 2>/dev/null; then
        echo "Server ready after $((i*2))s"
        READY=1
        break
    fi
    if ! kill -0 $SERVER_PID 2>/dev/null; then
        echo "Server crashed at $((i*2))s"
        break
    fi
done

echo ""
echo "=== Server status ==="
if [ "$READY" = "1" ]; then
    echo "READY"
else
    echo "NOT READY"
fi

echo ""
echo "=== Last 30 log lines ==="
tail -30 /tmp/llama.log

echo ""
echo "=== GPU usage AFTER model load ==="
/var/packages/NVIDIARuntimeLibrary/target/nvidia/bin/nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader

if [ "$READY" = "1" ]; then
    echo ""
    echo "=== Running inference: 'Hello' ==="
    TIME_START=$(date +%s%N)
    RESP=$(curl -s --max-time 30 -X POST http://127.0.0.1:18181/completion \
        -H "Content-Type: application/json" \
        -d '{"prompt":"<|user|>\nSay hello in one short sentence.</s>\n<|assistant|>\n","n_predict":40,"temperature":0.5,"stop":["</s>"]}')
    TIME_END=$(date +%s%N)
    ELAPSED_MS=$(( (TIME_END - TIME_START) / 1000000 ))
    echo "Time: ${ELAPSED_MS}ms"
    echo "Response: $RESP" | head -c 800
    echo ""

    echo ""
    echo "=== GPU usage during inference (peak) ==="
    /var/packages/NVIDIARuntimeLibrary/target/nvidia/bin/nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader
fi

kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null
