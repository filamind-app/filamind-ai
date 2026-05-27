# Device: DS1821+

This branch builds Filamind AI for the **Synology DS1821+** 8-bay NAS.

## Hardware

| | Value |
|---|---|
| **CPU** | AMD Ryzen Embedded **V1500B** — 4 cores / 8 threads, ~2.2 GHz |
| **CPU features** | AVX, **AVX2**, FMA, F16C, AES-NI, SHA-NI, BMI1, BMI2, SSE 4.2 |
| **CPU codename** | Zen 1 (Naples-derived embedded) — `gcc -march=znver1` |
| **RAM** | 62 GB (default 4 GB, max 32 GB officially — this unit is heavily upgraded) |
| **GPU** | **None** — no NVIDIA card, no integrated graphics for AI |
| **DSM** | 7.2.1 (kernel 4.4.302+) |
| **Platform string** | `synology_v1000_1821+` |
| **Architecture** | `v1000` |
| **Storage** | 8 bays, large array (~110 TB raw in this reference unit) |

## Inference engine

- **llama.cpp latest** (b5000+) — no CUDA constraint, so we ride the upstream release.
- Cross-compiled with Synology v1000 toolchain (gcc 12.2, glibc 2.36).
- `-march=znver1 -mavx2 -mfma -mf16c` for the Ryzen V1500B.
- Pure CPU inference. No GPU.

## Build

```bash
git checkout device/ds1821-plus
bash build_llama_cpu_avx2.sh   # produces spk-source/package/bin/llama-server
bash build_spk.sh              # produces Filamind.spk
```

## What's different on this branch vs `main` and `device/dva3221`

- `spk-source/INFO`:
  - `arch="x86_64"`
  - `model="synology_v1000_1821+"`
  - **`install_dep_packages=""`** — no NVIDIARuntimeLibrary needed.
- `start-stop-status` does NOT export CUDA library paths.
- `safe_defaults_for()` ignores VRAM ceiling — large models constrained only by free RAM (~47 GB available on this unit).
- Default model recommendations bias toward larger / more modern weights (see below).

## Models supported

With a current llama.cpp release, **everything llama.cpp supports works**, including:

| Family | Sizes that fit (Q4_K_M) | Estimated speed |
|---|---|---|
| Llama 3 / 3.1 / 3.2 / 3.3 | 1B · 3B · 8B · 70B | 1B→25 tok/s · 8B→9 tok/s · 70B→1 tok/s |
| Qwen 2.5 / 3 | 0.5B · 1.5B · 3B · 7B · 14B · 32B · 72B | 7B→8 tok/s · 32B→2 tok/s |
| Mistral / Mixtral | 7B v0.3 · 8x7B · 8x22B | 7B→8 tok/s · 8x7B→4 tok/s |
| Gemma 2 / 3 | 2B · 9B · 27B | 9B→6 tok/s · 27B→2.5 tok/s |
| Phi-3 / 3.5 / 4 | 3.8B · 14B | 14B→4 tok/s |
| Aya Expanse | 8B · 32B (excellent Arabic) | 8B→8 tok/s · 32B→2 tok/s |
| DeepSeek-V2-Lite · V3-distill · R1-distill | varies | model-dependent |
| Command-R / R-Plus | 35B · 104B | 35B→2 tok/s |
| Yi-1.5 | 6B · 9B · 34B | 9B→6 tok/s · 34B→2 tok/s |

> Speeds are rough estimates for Q4_K_M quantization on a 4-core/8-thread Ryzen V1500B at ~2.2 GHz. Real workloads vary ±30%.

## Performance vs DVA 3221

| | DVA 3221 (GPU) | DS1821+ (CPU) |
|---|---|---|
| Mistral 7B Q4 (b1620) | ~25 tok/s | n/a |
| Mistral 7B Q4 (latest) | n/a | ~8 tok/s |
| Llama 3 8B Q4 | ❌ unsupported | ~7 tok/s |
| Llama 3.3 70B Q4 | ❌ won't fit VRAM | ~1 tok/s |
| AceGPT 7B Q4 (Arabic) | ~20 tok/s | ~7 tok/s |
| Aya Expanse 8B (Arabic) | ❌ unsupported | ~8 tok/s |

**Use-case split:** DVA 3221 for *fast small models*, DS1821+ for *modern + large models*.

## Status

⚠️ **Build script `build_llama_cpu_avx2.sh` is not yet committed.** This branch holds the
INFO/scripts/docs delta from `main`; the actual binary will be added once the V1500B
build is verified end-to-end. Open an issue if you want to help validate it.
