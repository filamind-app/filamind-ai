#!/usr/bin/env python3
"""Download a small Llama-architecture GGUF for testing on Synology."""
import os
import sys

os.chdir(os.path.expanduser("~/saynologyai/models"))

try:
    from huggingface_hub import hf_hub_download
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "huggingface_hub"], check=True)
    from huggingface_hub import hf_hub_download

# Try a few Llama-architecture GGUFs
candidates = [
    ("TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF", "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"),
    ("microsoft/Phi-3-mini-4k-instruct-gguf", "Phi-3-mini-4k-instruct-q4.gguf"),
    ("Qwen/Qwen1.5-0.5B-Chat-GGUF", "qwen1_5-0_5b-chat-q4_k_m.gguf"),
]

for repo, fn in candidates:
    print(f"Trying {repo}/{fn}...")
    try:
        p = hf_hub_download(repo_id=repo, filename=fn, local_dir=".")
        print(f"SUCCESS: {p}")
        size_mb = os.path.getsize(p) / (1024*1024)
        print(f"Size: {size_mb:.1f} MB")
        break
    except Exception as e:
        print(f"Failed: {e}")
        continue
