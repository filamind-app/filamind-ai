# Filamind AI · فيلامايند

> **Private AI for your Synology NAS.** Run local LLMs on your own hardware — your conversations never leave your network.
>
> **ذكاء اصطناعي خاص لـ Synology NAS.** نماذج لغوية محلية على عتادك الشخصي — محادثاتك لا تغادر شبكتك.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Platform: Synology DSM 7.2](https://img.shields.io/badge/DSM-7.2%2B-orange.svg)](https://www.synology.com/dsm)
[![llama.cpp: b1620+](https://img.shields.io/badge/llama.cpp-b1620%2B-green.svg)](https://github.com/ggerganov/llama.cpp)

---

## What is this · ما هذا

Filamind AI is a **native Synology DSM package** (`.spk`) that brings ChatGPT/Claude-style chat to your NAS — running open-source models locally, with optional fall-back to cloud providers (OpenAI / Anthropic / Google). One web interface, multi-user, full Arabic + English with RTL.

تطبيق محادثة بتصميم يماثل Claude/ChatGPT، يعمل **محلياً على NAS** الخاص بك. يستخدم llama.cpp مع تسريع GPU عند توفّره، مع إمكانية الاتصال بمزوّدي السحابة (OpenAI / Anthropic / Gemini). واجهة واحدة، متعدّد المستخدمين، عربي + إنجليزي كاملان مع دعم RTL.

---

## Supported devices · الأجهزة المدعومة

| Device · الجهاز | Branch · الفرع | Engine · المحرّك | Models supported · النماذج |
|---|---|---|---|
| **DVA 3221** (GTX 1650 4GB, CUDA 10.1) | [`device/dva3221`](https://github.com/filamind-app/filamind-ai/tree/device/dva3221) | llama.cpp **b1620** (CUDA, sm_75) | Llama 2 · Mistral v0.2 · CodeLlama · Phi-2 · TinyLlama · AceGPT (Arabic) · Noon (Arabic) |
| **DS1821+** (Ryzen V1500B, AVX2, 62 GB RAM) | [`device/ds1821-plus`](https://github.com/filamind-app/filamind-ai/tree/device/ds1821-plus) | llama.cpp **latest** (CPU, AVX2 + FMA) | All the above **+** Llama 3.x · Qwen 2.5 · Gemma 2/3 · Phi-3/4 · Aya Expanse · DeepSeek · Mixtral · 70B-class models |
| Other Synology · أخرى | [`main`](https://github.com/filamind-app/filamind-ai/tree/main) | Capabilities-driven | Auto-detect; opens PR welcomed |

> The two reference devices are **complementary**, not competing. **DVA 3221** is fast on small models thanks to the GPU. **DS1821+** is slower but runs *much* larger and more recent models because there's no CUDA-10 constraint.

> الجهازان متكاملان — DVA 3221 سريع على النماذج الصغيرة بفضل GPU، و DS1821+ أبطأ لكنه يشغّل نماذج أحدث وأكبر بكثير لأنه غير مقيّد بـ CUDA 10.

---

## Features · الميزات

- **Local-first inference** — llama.cpp built natively for your Synology toolchain. Your prompts never leave the NAS unless you pick a cloud provider.
- **استدلال محلي أوّلاً** — llama.cpp مُجمَّع أصلياً لـ Synology. مدخلاتك لا تغادر الـ NAS إلا إذا اخترت مزوّداً سحابياً.
- **Multi-user with roles** — admin + user, PBKDF2-hashed passwords, HMAC-signed cookie sessions, per-user `sk-…` API keys.
- **متعدّد المستخدمين** — admin + user، كلمات مرور بـ PBKDF2، جلسات مُوقَّعة، مفاتيح API لكل مستخدم.
- **12 built-in agents** — Friendly Assistant, Code Master, Writer, Researcher, Translator, Tutor, Storyteller, Email Helper, Brainstormer, Summarizer, Math, Copywriter. Each editable.
- **12 وكيل جاهز** — كلٌّ بشخصية متخصّصة، قابلة للتعديل.
- **Cloud providers built-in** — OpenAI · Anthropic Claude · Google Gemini, with auto-fallback for deprecated model IDs.
- **مزوّدو سحابة مدمجون** — OpenAI · Anthropic · Gemini مع تصحيح تلقائي للنماذج المُنتهية.
- **OpenAI-compatible API** — drop-in endpoint for OpenWebUI, LibreChat, Continue, Cursor, LangChain, OpenAI SDK, AnythingLLM, Jan, Msty…
- **API متوافق مع OpenAI** — يعمل مع OpenWebUI, LibreChat, Continue, Cursor, LangChain وغيرها.
- **Full Arabic + English** — 380+ translated keys, RTL layout, Arabic-supporting local models (AceGPT, Noon, OpenHermes).
- **عربي وإنجليزي كاملان** — 380+ مفتاح ترجمة، تخطيط RTL، نماذج محلية تدعم العربية.
- **PWA + voice input** — installable on Android/iOS/Desktop, Web Speech API in `ar-SA` / `en-US`.
- **PWA + إدخال صوتي** — قابل للتثبيت كتطبيق، إدخال صوتي بلغة الواجهة.
- **Conversation export + search** — full-text search, Markdown/JSON export.
- **تصدير وبحث المحادثات** — بحث نصي كامل، تصدير بـ Markdown أو JSON.
- **VRAM-safe auto-tune** — `safe_defaults_for(model_path)` picks `CTX_SIZE` and `N_GPU_LAYERS` based on file size to prevent OOM on the 4 GB GTX 1650.
- **ضبط VRAM آمن** — اختيار تلقائي لمعاملات النموذج بناءً على حجمه.

---

## Quick start · بداية سريعة

1. **Download the latest `.spk`** from [Releases](https://github.com/filamind-app/filamind-ai/releases).
   **حمّل آخر `.spk`** من صفحة [Releases](https://github.com/filamind-app/filamind-ai/releases).
2. In DSM **Package Center → Manual Install**, upload the `.spk`. Approve the trust prompt (third-party package).
   في **Package Center → Manual Install**، ارفع الملف ووافق على التحذير (حزمة طرف ثالث).
3. Drop a `.gguf` model into `/volume1/FilamindAI/models/` (use File Station). For Arabic try **AceGPT-7B-chat Q4_K_M** (~3.8 GB).
   ضع ملف `.gguf` في `/volume1/FilamindAI/models/` عبر File Station. للعربية جرّب **AceGPT-7B-chat Q4_K_M** (~3.8 GB).
4. Click **Filamind AI** in DSM. Create the first admin account. Start chatting.
   اضغط أيقونة **Filamind AI** في DSM. أنشئ حساب المسؤول. ابدأ المحادثة.

---

## Build from source · البناء من المصدر

### DVA 3221 (GPU build)
```bash
git clone https://github.com/filamind-app/filamind-ai.git
cd filamind-ai
git checkout device/dva3221
bash build_llama_gpu.sh      # cross-compile llama.cpp b1620 with CUDA 10.1
bash build_spk.sh            # package SPK
# Output: SaynologyAI.spk → install via DSM Package Center
```

### DS1821+ (CPU build) — ✅ verified working on-device (v1.4.1)
```bash
git checkout device/ds1821-plus
# Option A — native WSL/Linux gcc, static libstdc++ (what shipped in v1.4.1):
bash build_ds1821_native.sh    # clones llama.cpp b4400, builds AVX2 llama-server
# Option B — Synology v1000 cross-toolchain (higher fidelity, needs the toolchain):
bash build_llama_cpu_avx2.sh
bash build_spk.sh
```
The prebuilt binary is already committed on this branch, so `build_spk.sh` alone produces a working SPK. Verified on a real DS1821+: loads Mistral-7B Q4 and serves completions (`AVX2=1 FMA=1 F16C=1`).

Requires WSL2 (Ubuntu) on Windows or any Linux host with the Synology toolchain (`gcc 12.2` for `denverton`, `gcc 12.2` for `v1000`).

يتطلّب WSL2 (Ubuntu) على Windows أو أي Linux host مع Synology toolchain (`gcc 12.2`).

---

## Architecture · المعمارية

```
┌─────────────────────────────────────────────────┐
│  Browser (PWA · Arabic RTL · light/dark)        │
└────────────────┬────────────────────────────────┘
                 │  HTTPS (or HTTP over LAN)
                 ▼
┌─────────────────────────────────────────────────┐
│  control_daemon.py (Python supervisor)          │
│   • Auth (PBKDF2 + HMAC cookies)                │
│   • SQLite: users.db + agents.db                │
│   • /api/* business endpoints                   │
│   • /v1/* reverse-proxy + type-sanitizer        │
│   • Cloud router → OpenAI / Anthropic / Gemini  │
└────────────────┬────────────────────────────────┘
                 │  127.0.0.1:8180
                 ▼
┌─────────────────────────────────────────────────┐
│  llama-server (llama.cpp child process)         │
│   DVA 3221  → b1620 + CUDA 10.1 (sm_75)         │
│   DS1821+   → latest + CPU AVX2                 │
└─────────────────────────────────────────────────┘
```

---

## Roadmap · خارطة الطريق

See [CHANGELOG.md](CHANGELOG.md) for the full v1.3.0 plan. Highlights:

- **v1.3 — MCP everywhere** · Model Context Protocol tool servers (filesystem, fetch, calculator, Home Assistant, Synology APIs, web search, GitHub, …) — works with both local and cloud chats.
- **v1.3 — MCP في كل مكان** · خوادم MCP محلية وسحابية مع per-agent allow-lists.
- **v1.3 — RAG per agent** · upload PDF/TXT/MD per agent, multilingual embeddings (Arabic-capable).
- **v1.3 — Model Pool** · concurrent `llama-server` instances with LRU eviction.
- **v1.4 — Multi-device clustering** · DVA 3221 routes small/fast queries, DS1821+ handles large-model inference, both sharing one UI.

---

## License · الترخيص

[Apache License 2.0](LICENSE) © 2026 Abdelmonem Awad (eg2@live.com).

Bundled `llama.cpp` is under [MIT License](https://github.com/ggerganov/llama.cpp/blob/master/LICENSE). NVIDIA CUDA Runtime is provided by Synology's separate **NVIDIARuntimeLibrary** package on DVA-series NAS.

`llama.cpp` المُدمج تحت ترخيص MIT. مكتبات CUDA من Synology عبر حزمة **NVIDIARuntimeLibrary** المنفصلة.

---

## Maintainer · المطوّر

**Abdelmonem Awad** · [eg2@live.com](mailto:eg2@live.com)

Issues, PRs, and Arabic-locale feedback all welcome.

ملاحظات وتعديلات وترجمات عربية مرحَّب بها على [GitHub Issues](https://github.com/filamind-app/filamind-ai/issues).
