# Device: DVA 3221

This branch builds Filamind AI for the **Synology DVA 3221** NVR-class NAS.

## Hardware

| | Value |
|---|---|
| **CPU** | Intel Atom C3538 — 4 cores, SSE 4.2 baseline (no AVX) |
| **RAM** | 64 GB (well above Synology's official 32 GB ceiling) |
| **GPU** | NVIDIA GeForce GTX 1650, **4 GB VRAM**, compute capability 7.5 |
| **CUDA** | 10.1.243 (driver 440.44, December 2019) |
| **cuDNN** | 7.6.3 |
| **DSM** | 7.2.1 (kernel 4.4.302+, build 69057) |
| **Platform string** | `synology_denverton_dva3221` |
| **Architecture** | `denverton` |

## Inference engine

- **llama.cpp b1620** (commit `fe680e3d1`) — last known-good with CUDA 10.1.
- Cross-compiled with Synology denverton toolchain (gcc 12.2, glibc 2.36).
- Targets **sm_75** (Turing) — must NOT enable PTX fallback (build break).
- Compatibility shim in `ggml-cuda.cu` maps CUDA-11+ macros to CUDA-10.x equivalents.

## Build

```bash
git checkout device/dva3221
bash build_llama_gpu.sh        # produces spk-source/package/bin/llama-server
bash build_spk.sh              # produces Filamind.spk at repo root
```

## What's different on this branch vs `main`

- `spk-source/INFO` has `arch="x86_64"` + `model="synology_denverton_dva3221"`.
- `install_dep_packages="NVIDIARuntimeLibrary>=1.0.0-0001"` — required for CUDA libs.
- `start-stop-status` exports `LD_LIBRARY_PATH` pointing at NVIDIARuntimeLibrary.
- Pre-built `llama-server` and `llama-main` binaries committed under `spk-source/package/bin/`.
- VRAM-safe defaults (`safe_defaults_for`) tuned for 4 GB VRAM.

## Models supported

llama.cpp b1620 supports these architectures:
- ✅ Llama / Llama 2 (all sizes)
- ✅ Mistral 7B v0.1 / v0.2
- ✅ CodeLlama (all sizes)
- ✅ Phi-2
- ✅ TinyLlama
- ✅ Mixtral 8x7B (with CPU offload — won't fit 4 GB VRAM)
- ✅ AceGPT 7B (Arabic — Llama 2 base)
- ✅ Noon 7B (Arabic — Llama 2 base)
- ✅ OpenHermes 2.5 (Mistral base)
- ✅ Falcon

**NOT supported** (b1620 predates them):
- ❌ Llama 3 / 3.1 / 3.2 / 3.3
- ❌ Qwen 2 / 2.5 / 3
- ❌ Gemma 1 / 2 / 3
- ❌ Phi-3 / 3.5 / 4
- ❌ Mistral 7B v0.3 / Mixtral 8x22B
- ❌ DeepSeek-V2 / V3 / R1
- ❌ Aya Expanse, Command-R

For the modern model families above, use the **`device/ds1821-plus`** branch.

## Performance

- TinyLlama 1.1B Q4_K_M — fully on GPU (601 MiB VRAM) — **~74 tok/s** decoding
- Mistral 7B Q4_K_M — partial offload (24 layers) — **~25 tok/s**
- Llama 2 13B Q4_K_M — partial offload (12 layers) — **~10 tok/s**
- CodeLlama 7B Q4_K_M — partial offload — **~20 tok/s**
