# Filamind AI — Changelog · سجل التغييرات

> **Note:** The project was originally released under the name *SaynologyAI* through v1.2.2. From v1.2.4 onwards it is **Filamind AI**. Historical entries below have **not** been retroactively renamed — they refer to the release that actually shipped under that name.
>
> **ملاحظة:** صدر المشروع باسم *SaynologyAI* حتى الإصدار v1.2.2. من v1.2.4 فصاعداً اسمه **Filamind AI**. لم أُعدّل المداخل التاريخية أدناه — تعكس الاسم الذي شُحن به الإصدار فعلاً.

Local LLM chat for Synology NAS. Two reference devices:
- **DVA 3221** (Intel Atom C3538, NVIDIA GTX 1650 4 GB, 64 GB RAM, DSM 7.2.1, CUDA 10.1) — GPU build on branch `device/dva3221`.
- **DS1821+** (AMD Ryzen V1500B with AVX2, 62 GB RAM, no GPU) — CPU build on branch `device/ds1821-plus`.

تطبيق محادثة ذكاء اصطناعي محلي لـ Synology NAS.

**Maintainer · المطوّر:** Abdelmonem Awad — eg2@live.com
**Repository · الريبو:** https://github.com/filamind-app/filamind-ai

Following [Keep a Changelog](https://keepachangelog.com/) — تصنيفات: **Added · Changed · Fixed · Security · Removed · Deprecated**.

---

## [1.2.6] — 2026-05-27

إصلاح فشل التثبيت على الأجهزة بدون GPU · Fix install failure on GPU-less devices.

### Fixed
- **DS1821+ (and any non-DVA Synology) install failed at `preinst`** with `No NVIDIA GPU detected (/dev/nvidia0 missing) — End preinst ret=[1]`. The pre-install hook unconditionally required an NVIDIA GPU + the NVIDIARuntimeLibrary package, which is correct for the DVA-3221 build but completely wrong for the CPU-only DS1821+ build. Root cause: a single `scripts/preinst` was shipped on both device branches without specialization.
- **`preinst` is now capability-aware** — reads the `model="…"` field from the staging INFO file and:
  - `synology_denverton_dva3221` → still requires NVIDIA + the runtime library (with a friendlier error pointing users to the CPU build link if no GPU).
  - any other model (incl. `synology_v1000_1821+`) → CPU-only path, only checks that `python3` is present.
- Error messages on the GPU path now tell users explicitly which SPK to download if they're on the wrong device.

### Notes
- The fix is identical across `main`, `device/dva3221`, and `device/ds1821-plus` — a single smart preinst replaces what would otherwise need per-branch divergence.
- Diagnostic that found the root cause: `sudo tail /var/log/synopkg.log` on the failing NAS showed `Begin preinst` immediately followed by `End preinst ret=[1]`, with `No NVIDIA GPU detected` in `/var/log/messages`.

---

## [1.2.5] — 2026-05-27

بنية الإصدارات + DSM Package Source + صفحة "حول التطبيق" داخل الـ UI · Release infrastructure + DSM Package Source + in-app About tab.

### Added
- **New Settings → About tab** showing everything a user needs to know about their install:
  - Installed package version + DSM version + git revision + build date.
  - Inference engine description (e.g. `llama.cpp b1620 + CUDA 10.1 (GPU)` on DVA 3221, `llama.cpp latest + CPU AVX2` on DS1821+).
  - **"Check for updates"** button — calls GitHub Releases API, shows the latest version with release notes and a download link if an update is available.
  - **Embedded release history** rendered from the packaged `CHANGELOG.md`.
  - Quick-links: source code, issue tracker, full changelog, discussions, maintainer email.
- **`/api/version`** endpoint enriched — returns `daemon_version`, `package_version`, `displayname`, `model`, `arch`, `dsm_version`, `engine`, `build_date`, `git_sha`, `git_branch`, `maintainer`, plus repo / release URLs.
- **`/api/changelog`** endpoint — serves the bundled `CHANGELOG.md` (text/markdown). The build script now copies `CHANGELOG.md` into the package so the file is available offline at `/var/packages/FilamindAI/target/CHANGELOG.md`.
- **`/api/check-update`** endpoint — hits `api.github.com/repos/filamind-app/filamind-ai/releases/latest`, compares to the running version, returns `{current, latest, update_available, release_url, release_notes, spk_download, published_at}`. Cached for 1 hour so a chatty UI doesn't spam GitHub.
- **`docs/` folder** that GitHub Pages publishes at `https://filamind-app.github.io/filamind-ai/` — this URL is a valid **third-party DSM Package Source**. Users add it once to **Package Center → Settings → Package Sources** and DSM offers one-click updates from then on.
- **`docs/_build_packages_json.py`** — generator that emits `packages.json` in the format DSM expects, with separate entries for `synology_denverton_dva3221` (DVA 3221) and `synology_v1000_1821+` (DS1821+).
- **`.github/workflows/release.yml`** — triggered on `v*.*.*` tag pushes. Builds both device SPKs, computes SHA-256 sums, extracts the matching section from `CHANGELOG.md` as release notes, attaches everything to a GitHub Release, and re-publishes `packages.json` to Pages.
- **`BUILD_INFO`** file emitted inside the package by `build_spk.sh` — captures `BUILD_DATE`, `GIT_SHA`, `GIT_BRANCH`, `DAEMON_VERSION` so the About tab can show provenance even on a freshly-installed SPK with no network access.
- 28 new i18n keys under `about.*` translated into both English and Arabic (natural Arabic phrasing, e.g. "حول التطبيق" for tab title, "أنت على أحدث إصدار" for up-to-date state).

### Changed
- **`build_spk.sh`** now bundles `CHANGELOG.md` and writes `BUILD_INFO` automatically. No-op if `git` isn't available — `BUILD_INFO` still gets a `BUILD_DATE` line.
- **CI `Build SPK` job** runs on pull requests too (artifact upload limited to push-to-main). Catches packaging regressions before merge.

### How users discover updates from now on

After installing this version (manually, once), three things change:

1. **In-app banner / About tab** — opens `/api/check-update` on demand, surfaces a green "Update available" card with a one-click SPK download.
2. **DSM Package Center** — if the user added `https://filamind-app.github.io/filamind-ai/` as a Package Source, DSM shows the package under **Community** with an Update button when a newer version is published.
3. **GitHub Releases page** — every tag push produces a release with attached SPKs for every supported device + SHA256SUMS.

### Migration / install notes
- **Already on 1.2.4?** Settings → System → Restart, or wait for the next package upgrade. About tab works immediately.
- **Fresh install + Package Source URL:** add the URL *before* installing if you want DSM to know about updates from day one.

---

## [1.2.4] — 2026-05-27

إعادة تسمية المشروع إلى **Filamind AI** + بنية ريبو GitHub + بدء دعم DS1821+ · Rebranded to **Filamind AI** + GitHub repo bootstrap + DS1821+ second-device support.

### Changed
- **Project renamed** SaynologyAI → **Filamind AI**.
  - Package identifier: `SaynologyAI` → `FilamindAI`.
  - Install path: `/var/packages/SaynologyAI/` → `/var/packages/FilamindAI/`.
  - Config file: `saynologyai.conf` → `filamindai.conf`.
  - Session cookie: `saynologyai_session` → `filamindai_session`.
  - DSM app name: `SYNO.SDS.SaynologyAI.Application` → `SYNO.SDS.FilamindAI.Application`.
  - Web display name and chat title: **Filamind AI**.
  - 9 icon PNGs renamed `SaynologyAI-NN.png` → `FilamindAI-NN.png` under `package/ui/images/`.
  - `localStorage` keys: `saynologyai_*` → `filamindai_*` (with one-time fallback read of legacy keys so an existing browser keeps its conversations/settings).

### Added
- **GitHub repository** — [`filamind-app/filamind-ai`](https://github.com/filamind-app/filamind-ai), Apache 2.0 license.
- **Bilingual `README.md`** with installation, build, architecture diagram, supported-device matrix.
- **`CONTRIBUTING.md`** documenting the per-device branch model and PR conventions.
- **Comprehensive `.gitignore`** — excludes `*.gguf` (~1.1 GB total), `*.spk`, compiled binaries, configs/DBs with secrets.
- **Second-device branch `device/ds1821-plus`** — initial structure for DS1821+ (Ryzen V1500B, 62 GB RAM, no GPU). CPU-only build with `-march=znver1`. Unlocks Llama 3.x, Qwen 2.5, Gemma 2/3, Phi-3/4, Aya Expanse, DeepSeek, Mixtral, and 70B-class models that the DVA 3221's b1620 CUDA build can't load.
- **Branch `device/dva3221`** — preserves the existing build (CUDA 10.1, sm_75, llama.cpp b1620, NVIDIARuntimeLibrary dependency).

### Migration · الهجرة
- `postinst` script auto-imports config + DBs from a pre-existing `/var/packages/SaynologyAI/etc/` if a fresh FilamindAI install detects one — so admin users, agents, providers, and API keys survive the rebrand without manual copying.
- **Model files** in `/volume1/SaynologyAI/models/` continue to be discovered (it remains in the daemon's search-path list as a legacy fallback). New installs prefer `/volume1/FilamindAI/models/`.
- **Browsers** with v1.2.x state in `localStorage` automatically read the legacy `saynologyai` key once on first load and re-save under `filamindai`.

### License
- **Apache 2.0** replaces the previous proprietary-style notice. Top-level `LICENSE` file is the full Apache 2.0 text; in-package `LICENSE` / `LICENSE_enu` are short user-readable summaries shown by the DSM install wizard.

### Notes
- The DSM Package Center sees `SaynologyAI` and `FilamindAI` as **different packages**. To migrate cleanly: install FilamindAI (it auto-imports state), verify, then uninstall the old SaynologyAI package.
- `package.tgz` / `Filamind.spk` are build artifacts and are now `.gitignore`-d. Built SPKs ship via GitHub Releases instead of the repo tree.

---

## [1.2.3] — 2026-05-27

زر "نسخ المفتاح فقط" بارز + زر نسخ البادئة لكل مفتاح حالي · Prominent "Copy key only" button + per-key prefix copy.

### Added
- **Highlighted "Copy key only" panel** on the new-key reveal. Replaces the small icon button with a primary, full-size, accent-tinted box: large dashed-outline code field showing the full `sk-…` key and a prominent **"Copy key only"** primary button. Hard to miss now.
- **"Copy prefix" button** on every existing key card — copies the 8-char visible prefix (e.g. `sk-AbCdEf`) as a quick reference. The full key cannot be recovered (it's hashed at rest by design), so prefix-copy is the realistic "key copy" action for existing keys. Tooltip on the button explains this.

### Changed
- New-key reveal layout: alert → primary "Copy key only" panel → optional curl/Python snippets (collapsed by default now — the key copy is the first thing you see).
- `.api-key-card .key-actions` wraps to multiple lines on narrow screens instead of overflowing.

### Internationalization
- New keys: `profile.copy_key_only`, `profile.copy_prefix`, `profile.copy_prefix_hint` (EN + AR).

---

## [1.2.2] — 2026-05-27

إصلاح أزرار النسخ على HTTP · Copy buttons fixed on plain-HTTP LAN access.

### Fixed
- **Copy buttons did nothing** when the chat was accessed over plain `http://nas-ip:8181/` (typical LAN setup). Root cause: browsers gate `navigator.clipboard.writeText()` to **secure contexts only** (HTTPS, `localhost`, or `127.0.0.1`). On an HTTP LAN origin the API is `undefined`, so every copy click silently failed.
- **Fix:** added a `copyToClipboard()` / `copyToClipboardSafe()` helper that:
  1. Tries the modern `navigator.clipboard.writeText()` first (still preferred on HTTPS).
  2. On failure or insecure context, falls back to creating a hidden `<textarea>`, selecting its content, and calling `document.execCommand("copy")` — the legacy path browsers still keep alive precisely for HTTP intranet apps like this one.
- All four call-sites were patched: profile-page connection card (`data-copy-target` handler), per-key "Copy curl" buttons, new-key ready-to-paste snippets, plus `window.copyCode` (code-block toolbar) and `window.copyMessage` (assistant message toolbar) in the chat UI.
- Visual feedback now distinguishes success (`✓` + green button via `.copied`) from failure (`✗` + red button via `.copy-failed`).

### Why this wasn't caught earlier
The dev environment used `http://localhost:...` which **is** a secure context per the spec, so `navigator.clipboard` worked there. Only LAN-IP access exposes the issue. Lesson: any future Web API gated by secure contexts gets the same dual-path treatment up-front.

---

## [1.2.1] — 2026-05-27

قسم "تفاصيل الاتصال" + نسخ متعدد + قصاصات جاهزة للأدوات الخارجية · "Connection details" section + multi-copy + ready-to-paste snippets for external clients.

### Added
- **New "Connection details" card** at the top of the profile page exposing everything an external client needs to talk to this NAS as a drop-in OpenAI endpoint:
  - **Base URL** — auto-built from the current host (`http(s)://<host>/v1`), one-click copy.
  - **Authorization header** template (`Authorization: Bearer YOUR_API_KEY`) with a copy button.
  - **Endpoints** — `/v1/chat/completions`, `/v1/models`, `/v1/completions`, each individually copyable.
  - **Default model parameter** (`auto`) with explanation that cloud providers expect their own model IDs.
- **Five expandable code snippets** with their own copy buttons:
  - **curl** — full payload with `max_tokens` example.
  - **Python (OpenAI SDK)** — `from openai import OpenAI` pattern.
  - **JavaScript (OpenAI SDK)** — Node/ESM ready.
  - **LangChain (Python)** — `ChatOpenAI(base_url=..., api_key=...)`.
  - **OpenWebUI / LibreChat / Continue / Cursor** — config-file ready blocks for each of the four most popular clients in one snippet.
- **Compatible-tools chip list** — visual cue that the endpoint works with: OpenWebUI, LibreChat, Continue.dev, Cursor, LangChain, LlamaIndex, AnythingLLM, Jan, Msty, BoltAI, ChatBox, TypingMind.
- **Per-key "Copy curl" button** on every existing key card — copies a curl template prefilled with the key prefix and a `YOUR_FULL_KEY` placeholder, ready to paste into a script.
- **Ready-to-paste snippets on new-key reveal** — when you generate a key, the result panel now shows:
  - The full `sk-…` key in a copyable field (one-time-only).
  - A curl command with the full key already embedded.
  - A Python OpenAI SDK call with the full key already embedded.
- **New-key naming hint** — placeholder text suggests labels like "Cursor", "n8n", "Home Assistant" so revocation later is unambiguous.

### Changed
- **API-keys card** now sits *below* the connection-details card so the docs are seen first.
- **Per-key card layout** — actions grouped into a `.key-actions` flex container; revoke is now `btn-sm btn-danger` to balance the new copy button.
- **Code-block direction is forced LTR** even when the UI is in Arabic RTL mode — fixes mirrored `curl`/`{` characters that confused copy-paste before.

### Security
- New copy targets are read via `getElementById` and `textContent` (never `innerHTML`), so a malicious key name or prefix can't inject script. `escapeHtml()` helper added for any user-controlled fields rendered into the key list.
- Auth header template uses placeholder `YOUR_API_KEY` so screenshots and screen-sharing of the connection card never expose a real key — actual keys appear only in the new-key reveal panel which is shown once.

### Internationalization
- 18 new keys under `profile.*` translated to both English and Arabic (natural, not literal): `connection_title`, `connection_desc`, `base_url`, `base_url_hint`, `auth_header`, `auth_header_hint`, `endpoints`, `default_model`, `default_model_hint`, `code_examples`, `snippet_curl/python/js/langchain/openwebui`, `snippet_curl_ready`, `snippet_python_ready`, `compatible_tools`, `copy_curl`, `full_key`, `new_key_hint`.

---

## [1.2.0] — 2026-05-27

نقل المحدّدات تحت الشات + قسم API محسّن + نماذج عربية محلية + بدايات MCP · Selectors moved below chat input + improved API section + Arabic local models + MCP scaffolding.

### Added
- **Chat toolbar below the input** (`.chat-toolbar`) hosting Agent / Provider / Model selectors plus three new action buttons: **Tools**, **Files**, **MCP**. Topbar is now cleaner — only the conversation mode pill remains there.
  - `renderAgentSelectBottom`, `renderProviderSelectBottom`, `renderModelSelectBottom` keep the bottom dropdowns in sync with state.
  - Responsive collapse below 640 px so the bar wraps neatly on mobile / sidebar-narrow layouts.
- **Tools menu** (lightweight `showSimpleMenu` modal): one-click insertions for current date / current time / ISO timestamp / templates (email draft, meeting notes, code review checklist).
- **Files menu** — placeholder UI with roadmap note pointing to v1.3 RAG-per-agent.
- **MCP menu** — placeholder UI explaining v1.3 will ship filesystem / HTTP-fetch / calculator allow-listed tools per the Model Context Protocol spec.
- **Per-provider help cards** in **Settings → Providers**. Each provider (OpenAI / Anthropic / Gemini) now shows:
  - "Get API key" button linking directly to that provider's console (`platform.openai.com/api-keys`, `console.anthropic.com/settings/keys`, `aistudio.google.com/apikey`).
  - Expandable 4-step "How to get a key" walkthrough.
  - Key format hint (`sk-…`, `sk-ant-…`, `AIza…`).
  - Pricing tier note + link to that provider's pricing page.
  - **`base_url` field** for self-hosted gateways and proxies (defaults preserved when blank).
- **MCP tab** in Settings with a roadmap card listing planned tool servers: filesystem (allow-listed paths), HTTP fetch (allow-listed hosts), calculator, time/date, conversation context.
- **3 Arabic-supporting local models** added to the Model Catalog so users can search/download GGUFs that speak Arabic natively:
  - **AceGPT 7B Chat (Q4_K_M)** — Llama-2 based, Arabic + English, ~3.8 GB.
  - **Noon 7B (Q4_K_M)** — Llama-2 based, MBZUAI Arabic instruction model, ~3.8 GB.
  - **OpenHermes 2.5 Mistral 7B (Q4_K_M)** — Mistral-base with strong Arabic capability, ~4.0 GB.
  - All three are compatible with b1620 (llama/mistral architectures). Catalog cards include Arabic descriptions.
- **i18n keys** for every new surface: `toolbar.*` (Agent / Provider / Model / Tools / Files / MCP labels), `tools.*` (menu items + descriptions), `providers.*` with per-provider sub-objects (`openai`, `anthropic`, `gemini` × `step1`–`step4`, `format`, `pricing`, `console`, `base_url`), `mcp.*` (tab + roadmap), `connection.*` (base URL / timeouts).
- **Arabic translations are natural, not literal**: "خبير البرمجة" (Code Master), "احصل على مفتاح API" (Get API key), "كيف أحصل على مفتاح؟" (How do I get a key?).

### Changed
- **Top bar simplified** — provider dropdown removed; one mode pill remains. Switching providers is now done via the bottom toolbar dropdown closer to where you actually compose the message.
- **DEFAULT_PROVIDERS model lists expanded** — OpenAI now lists 15 chat-capable models (gpt-4o family + o1 family + gpt-4-turbo + gpt-3.5-turbo), Anthropic 9 (3.5 Sonnet/Haiku, 3 Opus/Sonnet/Haiku, plus claude-sonnet-4 / claude-opus-4 / claude-haiku-4.5), Gemini 14 chat-capable models.
- **`/api/diagnose` admin reports daemon version** in its envelope for easier triage.

### Security
- New help/link buttons all use `rel="noopener noreferrer"` and explicit `target="_blank"`.
- `base_url` field is validated server-side: must parse as `https://` (or `http://` for loopback only) — prevents accidentally pointing at random TCP services or RFC1918 ranges (consistent with the SSRF mitigation for the model downloader).

---

## [1.1.3] — 2026-05-27

تلميحات أوضح للأخطاء + إنقاذ الإعدادات الخطرة عند الإقلاع · Friendlier error hints + auto-rescue of unsafe configs at boot.

### Added
- **`hint` field on chat-router errors** — when a cloud call fails the daemon now appends a one-line explanation the UI can show inline:
  - `429` → "You hit the provider's rate limit. Wait a minute or switch to another provider."
  - `401` / `403` → "API key rejected — check Settings → Providers."
  - `400` with `model not found` → "This model name is no longer valid. Pick a different one in the model selector."
  - Plus localized Arabic strings.
- **`_force_safe_settings_on_startup()`** — on daemon start, if `saynologyai.conf` has values that would OOM the GTX 1650 (e.g. `N_GPU_LAYERS=999` paired with a 4 GB+ model), values are clamped to the `safe_defaults_for(model_path)` recommendation and the original is backed up to `saynologyai.conf.unsafe-<timestamp>`. Recovers users who hand-edited the file or carried over aggressive settings from a prior version.

### Fixed
- **Gemini 429 returning HTTP 502 with no hint** — the chat router was swallowing the upstream error category. Now `429 → 429 + hint` instead of `502 + generic`.

---

## [1.1.2] — 2026-05-27

تنظيف قائمة نماذج Gemini · Gemini model list cleanup.

### Fixed
- **`fetch_live_models()` for Gemini was including non-chat models** (TTS, audio, image, embedding, Imagen, Veo, AQA, vision-tuning). Users who picked one got a confusing `400 "Multiturn chat is not enabled for models/gemini-2.5-flash-preview-tts"`.
- Filter now requires `supportedGenerationMethods` to include `generateContent` AND rejects any model whose name contains `-tts`, `-audio`, `-image`, `embedding`, `imagen`, `veo`, `aqa`, or `-vision-tuning`.
- OpenAI and Anthropic live-model lists similarly trimmed to chat-completion-capable IDs.

### Changed
- Settings → Providers model dropdown now refreshes from `/api/providers/<name>/models` on open, falling back to the static `DEFAULT_PROVIDERS` list if the live call fails (offline / rate-limited).

---

## [1.1.1] — 2026-05-27

إصلاح نموذج Gemini المُنتهي · Deprecated Gemini model fix.

### Fixed
- **`gemini-2.0-flash-exp` returned 404** after Google retired the preview alias on 2026-05-24. Users with that as their saved `default_model` got `HTTP 502 gemini_http_404` on every message.
- **`DEPRECATED_MODELS` table** added to the daemon mapping retired aliases → current GA equivalents:
  - `gemini-2.0-flash-exp` → `gemini-2.5-flash`
  - `gemini-1.5-pro-latest` → `gemini-1.5-pro`
  - `gpt-4-vision-preview` → `gpt-4o`
- **`migrate_providers()`** runs on daemon start: any `default_model` matching a deprecated alias is rewritten in-place in `providers.json`.
- **`call_gemini()`** auto-falls-back: if the requested model 404s and is in `DEPRECATED_MODELS`, it retries once with the mapped target and logs the substitution.

---

## [1.1.0] — 2026-05-27

ضبط VRAM آمن + إصلاح التكرار + لمسات تشبه Claude · VRAM-safe model switching + anti-repetition + Claude-style UI polish.

### Fixed
- **Model switching now actually works.** `safe_defaults_for` was too optimistic for 3-4 GB models on a 4 GB card: 7B-Q4 weights (~3.8 GB) + KV cache + scratch buffer regularly exceeded VRAM, causing OOM during load. New tuning:
  - 3-4 GB models → `N_GPU_LAYERS=24` (partial CPU offload), `CTX_SIZE=2048`
  - ≥4 GB models → `N_GPU_LAYERS=12`, `CTX_SIZE=1536`
  - 2-3 GB models → all on GPU, `CTX_SIZE=2048`
- **Excessive repetition** — defaults bumped to `repeat_penalty=1.25`, `repeat_last_n=256`, `min_p=0.05`, `max_tokens=400`. Friendly Assistant system prompt now explicitly instructs against repetition and rambling.
- **No more infinite restart loop** on a broken model. Daemon detects OOM / unknown-architecture in the llama-server log tail and stops retrying after 2 failed loads. Reason is exposed via `/api/status`.

### Added
- **Inline load-failure banner** in the chat. When a model fails to load it now shows the reason ("GPU ran out of memory", "Architecture 'phi3' not supported") with one-click links to "Choose a smaller model" or "Use Cloud Claude/ChatGPT/Gemini".
- **Per-code-block toolbar** in assistant messages — language label + Copy button (Claude-style). Code blocks are LTR even in Arabic UI.
- **Markdown tables** rendered with borders + striped headers.
- **Edit user messages** — pencil icon on your own turn lets you rewrite the message and resend, truncating the conversation from that point.
- **`POST /api/clear-failure`** (admin) — wipes the failure record for a model so a retry is allowed before the cooldown.
- **`/api/status` enriched** with `load_state` (idle/loading/ready/failed), `load_error`, and per-model `failures` map.
- i18n keys for `errors.*`, `actions.*`, `confirms.*` filled in EN + AR.

### Changed
- Status check now uses `/api/status` (richer info) and falls back to `/v1/models` only if it can't reach the daemon API.
- Local `/api/chat` now sends `repeat_penalty=1.25` + `repeat_last_n=256` + `min_p=0.05` automatically.

### How to use Claude instead
If a local model keeps failing, the easier path is Cloud Claude:
1. Settings → Providers → enable **Anthropic** → paste your `console.anthropic.com` key → Save.
2. In the topbar, switch the provider dropdown to **Claude** for the conversation.
3. Same UI, same agents, same export/search — but the model is Anthropic's.

---

## [1.0.0] — 2026-05-27

أول إصدار مستقر · First stable release.

### Added · إضافة
- **Full Arabic localization** — 361 i18n keys translated natively into Arabic with RTL layout support. Sidebar, modals, errors, confirms, agent prompts — all translated.
- **ترجمة عربية كاملة** — 361 مفتاحاً مترجماً ترجمة طبيعية مع دعم RTL.
- **Conversation export** — download any chat as Markdown or JSON from the topbar.
- **تصدير المحادثات** بصيغة Markdown أو JSON.
- **Conversation search** — full-text search across all stored conversations (sidebar search box).
- **بحث نصي كامل** عبر كل المحادثات المحفوظة.
- **PWA support** — `manifest.json`, theme color, icons → installable as a standalone app on Android/iOS/Desktop.
- **Voice input** — Web Speech API integration, language follows UI (`ar-SA` / `en-US`).
- **إدخال صوتي** بلغة الواجهة.
- **Slash commands** — `/summarize`, `/translate`, `/explain`, `/improve`, `/code`, `/brainstorm` expand into structured prompts.

### Security · أمان
- **Restricted `agent.model_path`** to `.gguf` files inside configured model search dirs — prevents arbitrary file read via llama-server's `--model` flag.
- **حماية من قراءة ملفات النظام** عبر تقييد مسارات النماذج.
- **SSRF mitigation** in model downloader — blocks RFC1918 / loopback / link-local hosts.
- **CSRF protection** — Origin/Referer validation on every state-mutating endpoint (Bearer-authed API clients exempt).
- **Race-safe admin creation** — `BEGIN IMMEDIATE` transaction prevents two simultaneous setup posts both succeeding.
- **Tight file permissions** during providers.json writes (`umask 0o077` + `O_CREAT 0o600`).
- **Owner-or-admin guard** on agent updates; built-in agents are admin-only to edit.

### Fixed · إصلاح
- File-handle leak in `start_llama` when llama-server restarted (parent never closed `logf`).
- `applyI18nDom` now applies `data-i18n-placeholder` and `data-i18n-title` attributes too.

---

## [0.9.0] — 2026-05-26

نظام الوكلاء (Agents) · Agents framework.

### Added
- **12 built-in agents** seeded in SQLite on first run: Friendly Assistant, Code Master, Writer, Researcher, Translator, Tutor, Storyteller, Email Helper, Brainstormer, Summarizer, Math & Reasoning, Copywriter.
- **CRUD API** for agents: `GET/POST /api/agents`, `PUT/DELETE /api/agents/<id>`.
- **`agent_id` field** in `/api/chat` body — daemon injects the agent's `system_prompt`, sampling defaults, and optionally swaps to its pinned model.
- **Settings → Agents tab** — browse, edit (built-ins editable, deletable only for custom), create new with custom system prompt + icon + sampling.
- 12 وكيل مبني مسبقاً بشخصيات متخصصة.

### Changed
- Renamed Settings tab "Modes" → "Agents". UI sidebar buttons still show top agents (server-driven now).

---

## [0.8.2] — 2026-05-27

إصلاح slot busy · Slot busy fix.

### Fixed
- **`max_tokens` default lowered from 2048 → 512** so small models don't ramble for minutes and hold the engine slot.
- **Daemon retries on `500 slot unavailable`** with 1.5 s backoff up to 5 attempts.
- **Abort previous in-flight request** when user sends a new message.
- **Strip error placeholder messages** (those starting with ⚠️) from chat history before sending — they were poisoning small models.
- **History capped at 20 turns** to stay inside context window.

### Added
- "Force restart engine" button in Settings → System.

---

## [0.8.1] — 2026-05-27

ضبط VRAM تلقائي · VRAM auto-tune.

### Added
- **`safe_defaults_for(model_path)`** picks `CTX_SIZE` and `N_GPU_LAYERS` based on model file size — prevents OOM when switching to large models on 4 GB VRAM.
- "Reset to safe defaults" button in Settings → Resources.
- Diagnostic endpoint retries 3× with backoff and includes last 3.5 KB of llama-server log.

---

## [0.8.0] — 2026-05-27

موفّرو السحابة · Cloud providers + `mirostat` bug fix.

### Added
- **Cloud provider integration** in `/api/chat` router: OpenAI (gpt-4o family), Anthropic Claude (3.5 Sonnet/Haiku, 3 Opus/Sonnet/Haiku), Google Gemini (2.0 Flash, 1.5 Pro/Flash/Flash-8B).
- Per-provider settings in **Settings → Providers**: enable toggle + API key + base URL + default model.
- Provider selector in topbar — switch between Local / ChatGPT / Claude / Gemini per conversation.
- API keys stored in `/var/packages/SaynologyAI/etc/providers.json` (admin-only, redacted in UI).

### Fixed
- **`mirostat` field crashes llama.cpp b1620** with `json.exception.type_error.302`. Root cause: bug in `oaicompat_completion_params_parse` (server.cpp line 2396) — fixed upstream in PR #4668 / b1697. Workaround: daemon's `_sanitize_v1_body` drops the `mirostat` key (and `penalize_nl` / `ignore_eos`) entirely before forwarding to llama-server.

---

## [0.7.4] — 2026-05-26

تعطيل streaming الافتراضي · Streaming disabled by default.

### Changed
- **`stream: false` is the new default** for `/v1/chat/completions`. The diagnostic showed b1620 + streaming + certain sampling combinations triggered 500 errors. Non-streaming is reliable.
- Toggle to re-enable streaming under **Settings → Connection**.

---

## [0.7.3] — 2026-05-26

أدوات تشخيص · Diagnostic tooling.

### Added
- **`GET /api/diagnose`** (admin-only) sends a hardcoded test payload to llama-server, retries 3×, returns last 3.5 KB of log.
- **`GET /api/version`** unauthenticated endpoint exposes `daemon_version`.
- Daemon logs the sanitized body of every `/v1/*` POST it forwards (truncated to 800 chars).
- Version badge `· daemon X.Y.Z` in the chat footer so users can tell what's actually running.

### Changed
- **Hard-whitelist sanitizer** rebuilds the chat body from scratch, keeping only known-safe fields with correct types. Drops anything unknown.

---

## [0.7.2] — 2026-05-26

داعمون موارد + كاتالوج · Daemon sanitizer + Model Catalog.

### Added
- **Models Catalog** — 7 curated GGUF models known to work with b1620: TinyLlama 1.1B (Q4/Q8), Phi-2, Mistral 7B v0.2, OpenHermes 2.5, CodeLlama 7B, Llama-2 7B Chat. Each card shows family / size / VRAM estimate / description / one-click download.
- **`POST /api/download-model`** kicks off a background download to `/volume1/SaynologyAI/models/`. Progress visible in `GET /api/downloads`.
- "Download a custom URL" expander for arbitrary GGUF links.

### Fixed
- Daemon now coerces JSON types in incoming `/v1/*` bodies (bool / int / float / string-list) so bad client data can't crash llama.cpp's strict nlohmann::json parser.

---

## [0.7.1] — 2026-05-26

إصلاح 500 type error في الواجهة · UI side type-error fix.

### Fixed
- Chat UI now sends only minimal sampling fields by default and conditionally adds non-default values, with explicit `Number()` / `parseInt()` coercions. (Effective for fresh browsers; old localStorage data still leaked bad types until v0.7.2's daemon-side sanitizer.)

---

## [0.7.0] — 2026-05-26

نظام المستخدمين الكامل · Full multi-user system.

### Added
- **SQLite-backed users database** in `/var/packages/SaynologyAI/etc/users.db`.
- **Authentication** — passwords hashed with PBKDF2-HMAC-SHA256 (200 000 iterations + random salt), HMAC-SHA256-signed cookie sessions (7-day TTL).
- **Roles** — `admin` (full control) and `user` (chat + read-only system info).
- **Pages** — `/setup.html` (first-run admin creation), `/login.html`, `/admin.html` (user management), `/profile.html` (own settings + password + API keys).
- **API tokens** — `sk-…` keys generated per user, hashed at rest, usable as `Authorization: Bearer …` against `/v1/*`.
- **Internationalisation** — `i18n.js` loader + `i18n/en.json` / `i18n/ar.json`. Settings → Profile lets each user pick language and theme; Arabic flips the layout to RTL.
- **User-menu dropdown** in chat topbar with Profile / Admin / Sign-out links.

### Changed
- Resources control fully moved into the chat UI's Settings tabs. Wizard is now a single screen (port + optional model path).

---

## [0.6.0] — 2026-05-26

نقل التحكم إلى الواجهة عبر Python daemon · Resource control via Python daemon.

### Added
- **`control_daemon.py`** — Python supervisor that owns the `llama-server` child process, exposes `/api/config`, `/api/models`, `/api/select-model`, `/api/status`, `/api/system`, `/api/log`, `/api/restart`, and reverse-proxies `/v1/*` to the internal llama-server (now on loopback port 8180).
- **Settings tabs** in the chat UI: Resources, Models, System.
- Settings changes apply by writing `saynologyai.conf` and signalling the supervisor to restart llama-server.

### Changed
- Wizard fields shrunk — runtime tuning moved into the UI.

---

## [0.5.0] — 2026-05-26

5 أوضاع شات + كل الإعدادات · 5 chat modes + complete settings.

### Added
- Five chat modes (Chat / Code / Writer / Researcher / Translator) — each with its own system prompt, default sampling, and suggestions.
- **12 sampling parameters** exposed: temperature, Top-P/K/Min, repeat penalty, repeat-last-N, frequency/presence penalty, stop sequences, Mirostat (off/v1/v2 + τ + η), max tokens, seed.
- Mode-aware welcome screen with starter prompts.
- Per-message timing meta (`N tokens · Xs · Y tok/s`).
- Settings panel with 5 tabs (General · Sampling · Models · Connection · Modes).

### Fixed
- Server-status check now has a 3 s timeout, pauses during streaming, and treats `/v1/models` 200 as alive.

---

## [0.4.1] — 2026-05-26

إصلاح License screen + تبسيط Wizard.

### Fixed
- Empty License screen + wizard stalling after "I Agree". Caused by combobox/singleselect types in `install_uifile` JSON.
- Simplified wizard to text-field-only inputs.
- Added `LICENSE` / `LICENSE_enu` files at SPK root.

---

## [0.4.0] — 2026-05-26

واجهة Claude الجديدة · Claude-style chat UI.

### Added
- Single-file `web/index.html` with Claude-inspired design: warm-beige background, sidebar with conversation history, message bubbles, streaming with typing cursor, dark mode, Markdown rendering with code highlighting.
- Conversations persisted in `localStorage`.
- Built-in suggestions, regenerate, copy, dark/light toggle.

### Changed
- llama-server now serves the custom UI via `--path /var/packages/SaynologyAI/target/web` (replaces the default llama.cpp UI).

---

## [0.3.1] — 2026-05-26

أيقونة احترافية + بيانات المطوّر · Professional icon + maintainer info.

### Added
- New icon designed with Pillow: rounded-square, indigo→violet gradient, central chat bubble + sparkle. Sizes 16/24/32/48/64/72/96/128/256.
- Maintainer fields in INFO set to `Abdelmonem Awad` / `eg2@live.com`.

---

## [0.3.0] — 2026-05-26

أيقونات DSM + ui/config صحيح · DSM icon + ui/config integration.

### Added
- Multi-size app icons under `package/ui/images/`.
- `ui/config` follows the working third-party DSM 7.2 format (mirrors Jellyfin / JDownloader): icon path = `images/SaynologyAI-{0}.png`, URL routes to llama-server's port.
- Expanded description with 3-step setup, 5 features, recommended models list.

### Fixed
- "No icon in DSM desktop" — root cause was the previous `ui/config` JSON shape; corrected.

---

## [0.2.2] — 2026-05-26

إصلاح "Invalid file format" · Install errors fixed.

### Fixed
- DSM 7.2 rejected the SPK with "Invalid file format" or "Not supported on this platform". Causes:
  - `arch=denverton` → corrected to `arch="x86_64"` + `model="synology_denverton_dva3221"`.
  - Random base64 garbage in `package_icon=` → replaced with a real 64×64 PNG + added `package_icon_256`.
  - `firmware` field duplicated with `os_min_ver` → kept only `os_min_ver="7.2-64561"`.
  - `install_dep_packages` without version constraint blocked the install on Hub lookup → pinned to `NVIDIARuntimeLibrary>=1.0.0-0001`.
- `extractsize` and `checksum` fields computed correctly. Tar format set to `ustar`.

---

## [0.2.0] — 2026-05-26

أول SPK مع GPU · First GPU-accelerated SPK.

### Added
- Cross-compiled `llama-server` (5.4 MB) with CUDA 10.1 support, targeting `sm_75` (GTX 1650 / Turing).
- `start-stop-status` launches llama-server with `LD_LIBRARY_PATH` pointing at `/var/packages/NVIDIARuntimeLibrary/target`.
- Auto-discovery of `.gguf` files under `/volume1/SaynologyAI/models/`, `/volume1/AI/models/`, package's own `models/` dir, or wizard-configured paths.

### Achievements
- End-to-end inference verified: TinyLlama 1.1B Q4_K_M loaded fully on GPU (601 MiB VRAM), 23/23 layers offloaded, ~74 tok/s decoding, `cublasInit` succeeded.

### Engineering hurdles solved on the way
- **Cross-compile for `denverton`** — downloaded Synology DSM 7.2 toolchain (gcc 12.2, glibc 2.36, kernel 4.4.302).
- **CUDA 10.1 + GCC 12 incompatibility** — used `gcc-9` as `nvcc`'s host compiler and patched `host_config.h`.
- **llama.cpp b1620's cuBLAS code uses CUDA 11+ macros** (`CUBLAS_TF32_TENSOR_OP_MATH`, `CUBLAS_COMPUTE_16F`). Added a compatibility shim in `ggml-cuda.cu` mapping them to CUDA 10.x equivalents.
- **Initial binary linked against system's CUDA 12 libs** (`/usr/local/cuda`) → temporarily unlinked during the build so the linker picked up the NAS sysroot's `libcudart.so.10.1`.
- **`Illegal instruction` on the Atom CPU** — patched `Makefile` to use `-march=x86-64 -msse4.2` instead of `-march=native` (the Atom C3538 has no AVX).

---

## [0.1.0] — 2026-05-26

أول SPK يعمل (CPU فقط) · First working SPK (CPU-only).

### Added
- Synology Package Center-installable `.spk` (1.5 MB).
- `llama-server` cross-compiled for the Synology denverton toolchain, CPU-only, SSE 4.2 baseline.
- Minimal `INFO`, `scripts/` lifecycle hooks, `conf/privilege`, `WIZARD_UIFILES/install_uifile`.
- Auto-discovery of GGUF models in standard paths.

---

## Project Milestones · معالم المشروع

| # | Milestone | Outcome |
|---|-----------|---------|
| 1 | SSH reconnaissance of DVA 3221 | Found GTX 1650 4 GB, CUDA 10.1 installed via `NVIDIARuntimeLibrary` package, `/dev/nvidia*` world-readable, `Python 3.8.15` available |
| 2 | Binary analysis of Surveillance Station | Located `libcuda.so` paths, confirmed package-dependency model possible |
| 3 | Synology toolchain setup | Downloaded denverton toolchain (gcc 12.2 + glibc 2.36) into WSL, verified `Hello, world` cross-compile runs on NAS |
| 4 | "Hello GPU" prototype | `dlopen("libnvidia-ml.so.1")` succeeded → first custom binary querying GTX 1650 via NVML |
| 5 | llama.cpp cross-compile with CUDA | First TinyLlama GPU inference end-to-end (74 tok/s) |
| 6 | SPK packaging | Resolved DSM 7.2's strict INFO/icon/dep validation; package installed cleanly |
| 7 | Multi-user web app | Auth, profile, admin, agents — full app rather than a wrapper |
| 8 | Cloud provider abstraction | One chat UI fronting Local + OpenAI + Anthropic + Gemini via a single `/api/chat` router |
| 9 | Full Arabic + RTL | 361 translated keys, agents speak Arabic, mirrored layout |

---

## Known Limitations · حدود الإصدار الحالي

- **llama.cpp b1620** (Dec 2023) — won't load newer architectures: Qwen2, Phi-3, Gemma 2, Llama 3. Loadable: Llama 1/2/3.0, TinyLlama, Mistral 7B v0.1/v0.2, Mixtral, Phi-2, Falcon, CodeLlama. Upgrading llama.cpp requires CUDA 11+ which DSM doesn't ship.
- **Single inference slot** — one llama-server process, `PARALLEL=1`. Multi-instance pool designed but not shipped (v1.1 target).
- **No streaming on local provider by default** — b1620 streaming was flaky; toggle in Settings → Connection.
- **GTX 1650 has 4 GB VRAM** — a 7B Q4 model fills the card; 13B+ models need CPU offload (~3-5 tok/s on the Atom). Auto-tune sets `CTX_SIZE`/`N_GPU_LAYERS` based on file size.

---

## v1.3.0 — Planned · المخطّط لـ v1.3.0

**Target window:** 2026-06-15 → 2026-07-15.
**Headline theme:** *Make the assistant act, not just answer* — MCP tool execution, RAG over NAS files, multi-model concurrency.

### 1) MCP tool servers (real, not placeholders)
The v1.2.0 UI shipped MCP as a roadmap card. v1.3 ships the actual protocol implementation so the LLM can **call tools mid-conversation** instead of only producing text.

- **`mcp_runtime.py`** new module — implements Model Context Protocol server interface (JSON-RPC 2.0 over stdio + WebSocket).
- **Built-in tool servers, allow-listed by an admin:**
  - `filesystem.read_file(path)` / `filesystem.list_dir(path)` — restricted to `/volume1/SaynologyAI/sandbox/` + any paths the admin adds in Settings → MCP.
  - `http.fetch(url, method, headers, body)` — restricted to hosts on the admin allow-list (default: empty). RFC1918 / loopback always blocked (same SSRF guard as the model downloader).
  - `calculator.eval(expression)` — pure expression evaluator (no Python `eval`, uses `simpleeval` library).
  - `datetime.now(tz)` / `datetime.parse(s)` — small utility set.
  - `nas.system_info()` — CPU / RAM / GPU snapshot for ops questions.
- **Tool-call loop** — daemon parses `tool_calls` in the assistant response, executes each call against the allow-listed runtime, appends the `tool` role message, sends back to the model. Capped at 8 hops per turn to prevent runaway loops.
- **Per-agent tool allow-list** — each agent in the agents DB gets a `tools` JSON array. Built-in "Researcher" agent gets `http.fetch`+`datetime`, "Code Master" gets `filesystem.read_file`+`calculator`, etc.
- **UI** — Settings → MCP tab becomes interactive: enable/disable servers, edit allow-lists, see live call log of the last 50 tool invocations.
- **Security:**
  - Every tool call audit-logged with caller (user + agent), arguments, result size, duration.
  - Per-user rate limit: 60 tool calls / hour (admin configurable).
  - Path traversal blocked (`..` rejected, `realpath()` must stay under root).
  - Outbound HTTP allow-list checked against the **resolved** IP, not the hostname (defeats DNS rebinding).

### 2) RAG per agent
The "Files" button placeholder ships as a real feature. Upload documents → chunk → embed → retrieve relevant chunks at chat time and inject into context.

- **Embedding model** — pinned slot on a second `llama-server` instance (port 8190, loaded with `bge-small-en-v1.5` or `multilingual-e5-small` for Arabic). ~150 MB VRAM budget on the GTX 1650.
- **Vector store** — SQLite + `sqlite-vss` extension (already compiled for Synology denverton in our toolchain) or fallback to flat numpy index for ≤10k chunks.
- **Per-agent corpus** — `POST /api/agents/<id>/files` accepts `.pdf`, `.txt`, `.md`, `.docx` (≤25 MB each). Chunked at ~512 tokens with 64-token overlap. Stored under `/volume1/SaynologyAI/rag/<agent_id>/`.
- **Retrieval at chat time** — when the active agent has any indexed files, the daemon embeds the user's query, fetches top-K (default 4) chunks, prepends them to the system prompt as `<context>...</context>`, and shows a "📎 Retrieved from N source(s)" pill above the assistant turn.
- **UI** — Files button on the chat toolbar opens an agent-scoped file manager: upload, list, delete, re-index, view chunks.
- **Multilingual** — `multilingual-e5-small` chosen specifically so Arabic queries match Arabic documents.

### 3) Model Pool (concurrent inference)
Currently one `llama-server` process holds the GPU. v1.3 ships an LRU pool to handle two-or-three agents in parallel without unloading models.

- **Pool ports** — `8180` / `8190` / `8200` / `8210`.
- **VRAM budget** — daemon tracks per-slot consumption; refuses to load a model that would exceed `4096 - used` MiB.
- **LRU eviction** — least-recently-used slot is unloaded when a new model is requested and the budget is exhausted.
- **Routing** — `/api/chat` looks up `(model, agent)` → slot, spawns/reuses, proxies. Slot busy → queue (max 4 deep) → 503 with `Retry-After`.
- **Embedding slot is sticky** — never evicted while RAG is enabled.
- **Status panel** — Settings → System shows slot table (port, model, VRAM, last-used, queue depth).

### 4) Conversation forking & branching
Inspired by Claude.ai's "edit message" UX, but visualized as a tree.

- **Fork from any assistant message** — "branch" icon on every assistant turn creates a sibling conversation rooted at that point.
- **Tree navigator** — sidebar shows the active conversation as a vertical list with branch indicators; click any node to switch branches.
- **Storage** — extend the existing conversation store with a `parent_id` + `branch_point_message_id` column.

### 5) Markdown LaTeX rendering
Bundle `katex` (the lightweight one, ~270 KB) so `$E=mc^2$` and `$$\int_0^\infty ...$$` render in chat. Lazy-loaded only when a math sequence is detected.

### 6) Scheduled prompts (cron-like)
- Settings → Schedules — APScheduler running inside the daemon.
- A schedule = `(cron expression, agent_id, prompt template, destination)`.
- Destinations: append to a chat thread, email (via SMTP config), webhook POST.
- Use cases: "every Monday at 09:00 summarize unread emails", "every hour fetch home-assistant temperature and warn if >30°C".

### 7) Backup / restore archive
One-click export bundling:
- `users.db`, `agents.db`, `providers.json` (keys redacted by default, toggle to include).
- `conversations/*.json`.
- `rag/<agent>/*` indexed vectors (optional, large).
- `saynologyai.conf`.
Produces a single `.saynologyai-backup-YYYY-MM-DD.tar.gz`. Restore wizard validates schema versions and migrates on the fly.

### 8) Custom slash-command registry
Beyond the current 6 built-ins (`/summarize`, `/translate`, `/explain`, `/improve`, `/code`, `/brainstorm`):
- User-defined commands in Settings → Slash commands.
- Each command = `(trigger, scope: global|agent, template with {input} placeholder, optional model override)`.
- Auto-import from Continue.dev / Cursor command files.

### 9) Voice output (TTS)
Pair with the existing Web Speech voice input.
- Browser-side `speechSynthesis` first (zero install, decent Arabic via Microsoft Naayf / Hoda).
- Optional: ship Piper TTS as an SPK addon for higher quality offline.

### Stretch goals (may slip to v1.4)
- **Multi-agent chains** — agent A's output feeds agent B (`/api/pipelines`).
- **Image input** — when a vision-capable cloud model is selected, allow image attachments.
- **Mobile-native PWA tweaks** — iOS Add-to-Home polish, share extension.

### Out of scope (intentionally)
- **No streaming** for local inference until we upgrade past llama.cpp b1620 (blocked by CUDA 10.1).
- **No fine-tuning UI** — too heavy for 4 GB VRAM; remains a Colab/external workflow.
- **No multi-user RBAC beyond admin/user** — current two-role model is sufficient for home use.

---

## Roadmap · ما بعد v1.3

Lower-priority items kept on the long list:

- **Markdown footnotes & GFM task lists** in chat rendering.
- **Conversation pinning** to top of sidebar.
- **Per-message "share as image"** export.
- **Webhook receiver** — let external services push events into a conversation thread.
- **iOS Shortcuts integration** — Bearer-token tile for one-tap voice → assistant.

---

*Generated and maintained alongside the application. Each release tag corresponds to a built `.spk` file; not all minor patch versions were shipped as separate SPK files.*

*يُحدَّث هذا الملف مع كل إصدار. كل tag يقابل ملف `.spk` بُني فعلاً.*
