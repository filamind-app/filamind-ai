# SaynologyAI v0.9.0 — i18n Audit

Audit of every visible string across the web UI, with the proposed `data-i18n`
key for each location and a list of dynamic JS strings that need `window.t(...)`
or template-rendered translations.

The new keyspace lives in `i18n/en.json` + `i18n/ar.json` under these top-level
groups: **`app · auth (setup/login) · chat · settings · sampling · resources ·
models · providers · system · connection · agents · admin · profile · errors ·
actions · placeholders · confirms`**. Total leaf keys: **361 EN / 361 AR**.

The previous file shipped 91 keys; this audit adds **~270 new keys** including
all 12 built-in agent name/description/system_prompt triples.

---

## 1 · HTML files still hard-coding English

### `index.html`

| Line | Element | Hard-coded text | Proposed `data-i18n` key |
|---:|---|---|---|
| 619 | `.new-chat` button (text node) | `New chat` | `chat.new_chat` |
| 624 | `#btnSettings` | `⚙ Settings` | `app.settings` (keep icon outside span) |
| 625 | `#btnTheme[title]` | `Toggle theme` | `data-i18n-title="app.toggle_theme"` |
| 631 | `#btnToggleSidebar[title]` | (none, add one) | `data-i18n-title="app.toggle_sidebar"` |
| 634 | `#modelName` | `Checking server…` | `chat.checking` (already set via JS, but initial text needs key) |
| 636 | `#modeName` | `Chat` | rendered by JS, already covered via `chat.modes.*` |
| 637 | `#providerSelect[title]` | `Provider` | `data-i18n-title="providers.label"` |
| 639 | `#btnRegen[title]` | `Regenerate last response` | `data-i18n-title="chat.regenerate"` |
| 640 | `#btnLang[title]` | `Language` | `data-i18n-title="app.language"` |
| 660 | `#inputBox[placeholder]` | `Message SaynologyAI...` | `data-i18n-placeholder="chat.placeholder"` |
| 663 | `#btnSend[title]` | `Send (Enter)` | `data-i18n-title="chat.send"` |
| 666 | `.input-foot` text | `SaynologyAI runs locally on … your NAS.` | split into `app.runs_locally_prefix` + `app.your_nas` |
| 673 | `<h2>` modal head | `Settings` | `settings.title` |
| 674 | close button text `✕` | none (symbol) | keep |
| 677-684 | Tabs (`General`, `Sampling`, `Providers`, `Resources`, `Models`, `System`, `Agents`, `Connection`) | hard-coded | `settings.general` / `settings.sampling` / `settings.providers` / `settings.resources` / `settings.models` / `settings.system` / `settings.modes` / `settings.connection` |
| 689 | `<label>` | `System prompt (overrides mode preset if set)` | `settings.system_prompt` |
| 690 | `#cfgSystem[placeholder]` | `You are a helpful assistant...` | `data-i18n-placeholder="settings.system_prompt_placeholder"` |
| 691 | `.hint` | `Persistent instructions sent to the model …` | `settings.system_prompt_hint` |
| 695 | `<label>` | `Max response tokens` | `settings.max_tokens` |
| 697 | `.hint` | `512 is a good default. …` | `settings.max_tokens_hint` |
| 700 | `<label>` | `Seed` | `settings.seed` |
| 702 | `.hint` | `-1 = random` | `settings.seed_hint` |
| 710 | `<label>` | `Temperature` | `sampling.temperature` |
| 717 | `<label>` | `Top-P (nucleus)` | `sampling.top_p` |
| 726 | `<label>` | `Top-K` | `sampling.top_k` |
| 730 | `<label>` | `Min-P` | `sampling.min_p` |
| 739 | `<label>` | `Repeat penalty` | `sampling.repeat_penalty` |
| 746 | `<label>` | `Repeat last N` | `sampling.repeat_last_n` |
| 752 | `<label>` | `Frequency penalty` | `sampling.freq_penalty` |
| 759 | `<label>` | `Presence penalty` | `sampling.pres_penalty` |
| 767 | `<label>` | `Stop sequences (comma-separated)` | `sampling.stop_sequences` |
| 768 | `#cfgStop[placeholder]` | `</s>,User:,Human:` | `data-i18n-placeholder="sampling.stop_placeholder"` |
| 771 | `<label>` | `Mirostat` | `sampling.mirostat` |
| 773-775 | `<option>` x3 | `Off`, `Mirostat v1`, `Mirostat v2 (recommended)` | `sampling.mirostat_off` / `mirostat_v1` / `mirostat_v2` |
| 780 | `<label>` | `Mirostat τ (target entropy)` | `sampling.mirostat_tau` |
| 783 | `<label>` | `Mirostat η (learning rate)` | `sampling.mirostat_eta` |
| 792 | `<label>` | `Cloud AI providers` | `providers.title` |
| 793 | `.hint` | `Configure API keys …` | `providers.intro` |
| 797 | `#btnSaveProviders` | `Save providers` | `providers.save` |
| 804 | `<label>` | `These settings are applied by restarting …` | `resources.apply_hint` |
| 808 | `<label>` | `Context size (tokens)` | `resources.ctx_size` |
| 810 | `.hint` | `4096 / 8192 / 16384 / 32768. …` | `resources.ctx_size_hint` |
| 813 | `<label>` | `GPU layers` | `resources.gpu_layers` |
| 815 | `.hint` | `999 = all layers on GPU. …` | `resources.gpu_layers_hint` |
| 820 | `<label>` | `Batch size` | `resources.batch` |
| 824 | `<label>` | `U-batch size` | `resources.ubatch` |
| 830 | `<label>` | `Threads` | `resources.threads` |
| 834 | `<label>` | `Threads (batch)` | `resources.threads_batch` |
| 840 | `<label>` | `Parallel slots` | `resources.parallel` |
| 842 | `.hint` | `Concurrent requests.` | `resources.parallel_hint` |
| 845 | `<label>` | `Port` | `resources.port` |
| 847 | `.hint` | `Changing the port requires …` | `resources.port_hint` |
| 851-853 | `<label>` | `Lock model in RAM (mlock)` + hint | `resources.mlock` + `resources.mlock_hint` |
| 857-859 | `<label>` | `Disable mmap …` + hint | `resources.no_mmap` + `resources.no_mmap_hint` |
| 863 | `<label>` | `Extra llama-server arguments` | `resources.extra_args` |
| 864 | `#resExtra[placeholder]` | `e.g. --rope-freq-base 10000` | `data-i18n-placeholder="resources.extra_args_placeholder"` |
| 865 | `.hint` | `Advanced: extra command-line flags …` | `resources.extra_args_hint` |
| 868 | `<label>` | `Search directories for .gguf files (colon-separated)` | `resources.model_dirs` |
| 869 | `#resModelDirs[placeholder]` | `/volume1/MyModels` | `data-i18n-placeholder="resources.model_dirs_placeholder"` |
| 870 | `.hint` | `Defaults already include …` | `resources.model_dirs_hint` |
| 873 | `#btnApplyResources` | `Apply & restart` | `settings.apply_restart` |
| 874 | `#btnSafeDefaults` + title | `Reset to safe defaults` + tooltip | `resources.safe_defaults` + `data-i18n-title="resources.safe_defaults_title"` |
| 878 | `.hint` (VRAM/GTX 1650 block) | long English explainer | `resources.vram_hint` |
| 884 | `<label>` | `Installed models` | `models.installed` |
| 886 | `.hint` `Loading…` | initial placeholder | `models.loading` |
| 889 | `.hint` (long file-station copy) | `Click any model to switch. …` | `models.click_to_switch` |
| 893 | `<label>` | `Download a model from Hugging Face` | `models.download_section` |
| 894 | `.hint` | `Curated GGUF models …` | `models.download_hint` |
| 897 | `.hint` `Loading catalog…` | initial placeholder | `models.loading_catalog` |
| 900 | `<summary>` | `Download a custom URL instead` | `models.custom_url_summary` |
| 902 | `<label>` x2 | `GGUF URL` / `Filename` | `models.gguf_url` / `models.filename` |
| 902-903 | `[placeholder]` x2 | `https://…` / `my-model.gguf` | `models.gguf_url_placeholder` / `models.filename_placeholder` |
| 905 | `<button>` | `Start download` | `models.start_download` |
| 912 | `<label>` | `Live system info` | `system.live_info` |
| 914 | `Loading…` text | initial placeholder | `system.loading` |
| 918-921 | Buttons | `Refresh`, `Show recent log`, `Run diagnostic`, `Force restart engine` | `system.refresh` / `system.show_log` / `system.run_diagnostic` / `system.force_restart` |
| 936 | `<label>` | `Server URL` | `connection.server_url` |
| 937 | `#cfgServer[placeholder]` | `auto (same origin)` | `data-i18n-placeholder="connection.server_url_placeholder"` |
| 938 | `.hint` | `Leave empty when opening …` | `connection.server_url_hint` |
| 941 | `<label>` | `Status polling interval (seconds)` | `connection.poll_interval` |
| 943 | `.hint` | `How often to ping the server. …` | `connection.poll_interval_hint` |
| 946 | `<label>` | `Streaming responses (experimental)` | `connection.streaming` |
| 947 | `.hint` | `When enabled, the assistant's reply …` | `connection.streaming_hint` |
| 953 | `<label>` | `Agents (chat personas)` | `agents.title` |
| 954 | `.hint` | `Each agent has a system prompt …` | `agents.intro` |
| 958 | `<summary>` | `➕ Create new agent` | `agents.create_new` (keep `➕` outside span) |
| 961 | `<label>` x2 | `ID (slug)` / `Icon` | `agents.id_label` / `agents.icon_label` |
| 961-962 | `[placeholder]` x2 | `my_helper` / `🤖` | `agents.id_placeholder` / `agents.icon_placeholder` |
| 964 | `<label>` + ph | `Name` / `My Helper` | `agents.name_label` / `agents.name_placeholder` |
| 965 | `<label>` + ph | `Description` / `What does this agent do?` | `agents.description_label` / `agents.description_placeholder` |
| 966 | `<label>` + ph | `System prompt` / `You are a helpful assistant who…` | `agents.system_prompt_label` / `agents.system_prompt_placeholder` |
| 968-969 | `<label>` x2 | `Temperature` / `Max tokens` | `agents.temperature_label` / `agents.max_tokens_label` |
| 971 | `#btnCreateAgent` | `Create agent` | `agents.create_btn` |
| 978-979 | Modal foot | `Cancel`, `Save` | `actions.cancel` / `actions.save` |

### `login.html`, `setup.html`, `admin.html`, `profile.html`

These four are already mostly translated via `data-i18n`. **Remaining items**:

- `profile.html:193` — hard-coded `Copy` button text inside a template string (covered by new `profile.copy` key).
- `admin.html:139` — hard-coded `Created.` alert HTML. Use `admin.user_created`.
- `admin.html:106` — fallback `Delete` (already covered by `admin.delete`).
- `admin.html:115` — fallback `Delete user {username}?` (already covered by `admin.confirm_delete` / new `confirms.delete_user`).
- `profile.html:170` — `confirm("Revoke this key?")` — use new `profile.revoke_confirm` / `confirms.revoke_key`.
- `setup.html` / `login.html` — fully covered via existing `data-i18n`.

---

## 2 · JS dynamic strings (template-built UI inside `index.html`)

These need either `window.t(...)` lookups or rerouting through helper functions.

| Line | Code site | English literal | Proposed key |
|---:|---|---|---|
| 1237, 1241 | `renderConvList` | `Today` / `Older` section labels | `chat.today` / `chat.older` |
| 1252 | `renderConvItem` | `title="Delete"` | `chat.delete_conv` |
| 1263 | `renderMessages` welcome | `${m.icon} ${m.name} mode` | mode name comes from agent translation; `chat.mode_label_suffix` for the trailing `mode` word |
| 1264-1265 | `renderMessages` welcome | `How can I help you today?` / `Local model on your NAS GPU. Conversations stay in your browser.` | `chat.welcome_title` / `chat.welcome_sub` |
| 1278 | `renderMessage` | `You` / `SaynologyAI` | `chat.you` / `chat.assistant` |
| 1289 | `renderMessage` | `📋 Copy` button text | `chat.copy` |
| 1430 | `sendMessage` | `${tokenCount} tokens · ${elapsed}s · ${tps} tok/s` | `chat.tokens_meta` (token templating) |
| 1431 | fallback when empty reply | `(empty response)` | `chat.empty_response` |
| 1435 | error template | `⚠️ **Connection error**\n\n…\n\nIs the model running? Check Package Center → SaynologyAI Chat → Run.` | `chat.connection_error_title` + `chat.connection_error_hint` (split into two for cleaner markdown) |
| 1473, 1478 | `updateSendButton` `title` | `Stop` / `Send` | `chat.stop` / `chat.send` |
| 1487 | `refreshServerStatus` | `Streaming…` | `chat.streaming` |
| 1491 | server hint fallback | `your NAS` | `app.your_nas` |
| 1501 | fallback model id | `Local model` | (kept English — appears alongside id; low value to translate) |
| 1512 | `markOnline` | `Connected` | `chat.connected` |
| 1528 | `markLoading` | `Loading model…` | `chat.loading_model` |
| 1534 | `markOffline` | `Server offline` | `chat.server_offline` |
| 1555 | `loadModelList` | `No .gguf files found in any search directory.` | `models.none_found` |
| 1556 | `loadModelList` | `Searched:` | `models.searched` |
| 1560 | `loadModelList` | `● Currently loaded` / `${size} MB` | `models.currently_loaded_dot` + `models.size_mb` |
| 1569 | `loadModelList` catch | `⚠ Could not reach control API: …. Open the chat URL from DSM (icon) for full functionality.` | `models.control_api_unreachable` (with `{error}`) |
| 1574 | `selectModel` confirm | `Switch to model:\n{path}\n\nResource settings (context size, GPU layers) will be auto-adjusted for the model size. The engine will restart and the chat will be briefly offline.` | `confirms.switch_model` / `models.switch_confirm` |
| 1592 | `selectModel` alert | `Could not switch model:` | `models.switch_failed` |
| 1598 | `applySafeDefaults` confirm | `Auto-tune memory settings for the currently loaded model and restart the engine?` | `confirms.safe_defaults` |
| 1599, 1605, 1609 | status strings | `Applying…` / `✓ Applied: …` / `✗ <err>` | `settings.applying` / `settings.applied` / `errors.generic` (with prefix glyph kept literal) |
| 1634 | catalog button | `Download` | `models.download` |
| 1641 | catalog catch | `⚠ ${e.message}` | use `errors.generic` |
| 1661-1664 | download subtitles | `Downloaded · saved as ${d.name}` / `Failed: ${error}` | `models.download_saved_as` (`{name}`) / `models.download_failed` (`{error}`) |
| 1677, 1685, 1690 | download btn states | `Starting…` / `Queued` / `Download` | `models.starting` / `models.queued` / `models.download` |
| 1689 | startDownload alert | `Download failed:` | `models.download_failed_alert` |
| 1696 | `startCustomDownload` alert | `Paste a URL first.` | `models.url_required` |
| 1719 | resources status | `Loaded current settings.` | `settings.loaded_current` |
| 1721 | resources status | `Could not load (${err})` | `resources.could_not_load` |
| 1726 | resources status | `Saving…` | `settings.saving` |
| 1748, 1750 | resources status | `✓ Saved. Engine restarting…` / `✓ Applied.` | `resources.engine_restarting` / `settings.applied` |
| 1752 | resources status | `✗ Failed: ${err}` | `errors.save_failed` |
| 1767-1773 | `loadSystemInfo` HTML | `CPU`, `cores`, `load 1m`, `RAM`, `free`, `GPU`, `VRAM`, `Utilization`, `Temp`, `not detected via control daemon` | `system.cpu`, `system.cores`, `system.load_1m`, `system.ram`, `system.free`, `system.gpu`, `system.vram`, `system.utilization`, `system.temperature`, `system.gpu_not_detected` |
| 1776 | `loadSystemInfo` catch | `Could not load system info:` | `system.load_failed` |
| 1788 | `loadLog` catch | `Could not load log:` | `system.log_failed` |
| 1794-1797 | `PROVIDER_LABELS` | `Local (GPU)` / `ChatGPT` / `Claude` / `Gemini` | `providers.local` / `providers.openai` / `providers.anthropic` / `providers.gemini` |
| 1857-1861 | `renderProviderForms` help | `Get a key from …` x3 | `providers.help_openai` / `providers.help_anthropic` / `providers.help_gemini` |
| 1866-1873 | provider form labels | `Enable`, `API key`, `Default model`, `(set — leave empty to keep)`, `Paste your API key` | `providers.enable` / `providers.api_key` / `providers.default_model` / `providers.api_key_set` / `providers.api_key_placeholder` |
| 1883 | providers status | `Saving…` | `settings.saving` |
| 1897-1898 | providers status | `✗ Save failed` / `✓ Saved` | `errors.save_failed` / `settings.saved` |
| 1922, 1929 | diagnose output | `Running diagnostic…` / `Diagnostic failed:` | `system.running_diagnostic` / `system.diagnostic_failed` |
| 1992 | `renderAgentsTab` | `built-in` / `custom` badges | `agents.builtin_badge` / `agents.custom_badge` |
| 1994 | `renderAgentsTab` | `Delete` button | `agents.delete_btn` |
| 1997 | `renderAgentsTab` | `System prompt` label | `agents.system_prompt_label` |
| 2000-2002 | `renderAgentsTab` | `Temperature` / `Max tokens` / `Save` | `agents.temperature_label` / `agents.max_tokens_label` / `agents.save_btn` |
| 2019 | `deleteAgent` confirm | `Delete this agent?` | `confirms.delete_agent` / `agents.delete_confirm` |
| 2034 | `createNewAgent` status | `ID and name required.` | `agents.id_name_required` |
| 2035, 2042-2043 | status text | `Creating…` / `✗ <err>` / `✓ Created` | `agents.creating` / `errors.generic` / `agents.created` |
| 2059 | `copyMessage` | `✓ Copied` | `chat.copied` |
| 2141 | footer | `· daemon ${ver}` | `app.version_label` |
| 2207 | force-restart confirm | `Kill the inference engine and start it fresh? In-flight requests will be lost.` | `confirms.force_restart` / `system.force_restart_confirm` |

### `index.html` agent name resolution

`loadLang()` (line 2080) already loops `STATE.modes` and looks up
`chat.modes.<agent.id>`. The new `en.json` / `ar.json` extend this map to all 12
built-in agent ids (`chat`, `coder`, `writer`, `researcher`, `translator`,
`tutor`, `storyteller`, `email`, `brainstormer`, `summarizer`, `math`,
`marketer`) so every sidebar tile and topbar mode-pill is translated for free.

Built-in agent **descriptions** and **system_prompts** are localized under
`agents.builtin.<id>.{name,description,system_prompt}`. The daemon currently
seeds these from `DEFAULT_AGENTS` in `control_daemon.py`. Two integration
options for v0.9.1:

1. **Daemon-side**: when `/api/agents` is queried, read the user's `language`
   from the session and substitute `name`/`description`/`system_prompt` from
   `i18n/<lang>.json`'s `agents.builtin` block if the agent is a builtin.
2. **Client-side**: extend `loadLang()` in `index.html` to also overwrite
   `m.description` and `m.system` from `agents.builtin.<id>` when the agent is
   builtin (cheaper, no daemon change).

Either path needs only the keys produced here.

### `profile.html`

| Line | Code site | English literal | Proposed key |
|---:|---|---|---|
| 170 | `confirm("Revoke this key?")` | hard-coded | `confirms.revoke_key` / `profile.revoke_confirm` |
| 163 | `created ${date}` | hard-coded `created` | `profile.key_created_at` |
| 193 | `<button>Copy</button>` | hard-coded | `profile.copy` |

### `admin.html`

| Line | Code site | English literal | Proposed key |
|---:|---|---|---|
| 139 | `<div>Created.</div>` | hard-coded alert | `admin.user_created` |

---

## 3 · RTL gotchas (Arabic)

The shipped CSS already handles the main RTL cases:
`html[dir="rtl"]` is set automatically by `i18n.js` based on language. Sidebar
border flips, message rows reverse, user-menu dropdown anchors on the left.

### Icons that **must mirror** in Arabic (direction-of-motion)

- **Back / forward arrows** — currently the regenerate icon (`btnRegen`, SVG
  `polyline 23 4 23 10 17 10` + `1 20 1 14 7 14`) reads naturally LTR. In RTL
  this directional polygon should be flipped with `transform: scaleX(-1)` when
  `html[dir="rtl"]`. Add: `html[dir="rtl"] #btnRegen svg { transform: scaleX(-1); }`.
- **Send arrow** in `#btnSend` SVG — points upward, no horizontal direction —
  **no flip needed**.
- **New-chat plus** — symmetric — **no flip needed**.
- **Sidebar hamburger** (3 horizontal lines) — symmetric — **no flip needed**.
- **Conversation list delete `×`** — symmetric — **no flip needed**.

### Icons that **should NOT mirror**

- **Brand mark `S`** — letter, never flip.
- **User avatar initials** — letters, never flip.
- **Status dot** — circular, no flip.
- **Mode emoji** (💬 💻 ✍️ 🔬 🌐 🎓 📖 📧 💡 📋 🧮 📣) — emoji glyphs render
  the same in RTL and should not be transformed.
- **Code-block content (`<pre>`)** — must remain LTR even inside RTL flow.
  Add: `html[dir="rtl"] .msg-content pre { direction: ltr; text-align: left; }`.
- **API key codeblocks / model paths** — same as above: keep LTR.

### Other RTL polish recommendations

- Number formatting: keep western digits (`٠١٢…` would confuse path strings
  and tokens-per-second). The current JS uses raw numbers — leave as-is.
- The progress bar `<div style="width:${pct}%">` is direction-agnostic but
  visually feels backwards in RTL. Consider `html[dir="rtl"] .progress { direction: ltr; }`
  if the user wants left-to-right fills.
- Tabs (`.tabs`) currently flow LTR with `gap: 4px`. In RTL they flow RTL
  automatically thanks to the parent `direction: rtl;` — good.
- The `#btnLang` pill currently shows literal "EN" or "عربي" — keep as-is;
  it's a self-identifying language switcher.

---

## Key counts

| Group | EN keys | Notes |
|---|---:|---|
| app | 14 | brand, nav, footer chrome |
| setup | 8 | unchanged from v0.7 |
| login | 6 | unchanged from v0.7 |
| chat | 36 (+ 5 mode arrays of 4) | new: dynamic states, suggestions, error templates |
| settings | 22 | tab labels + general tab fields/hints |
| sampling | 15 | full Mirostat coverage |
| resources | 30 | every field + hint + vram_hint |
| models | 26 | catalog, downloads, custom URL, confirms |
| providers | 14 | per-provider help + form labels |
| system | 19 | diagnostic + sysinfo block |
| connection | 7 | server URL + poll + streaming |
| agents | 23 (+ 12 builtin × 3 fields) | every builtin name/desc/sys_prompt |
| admin | 15 | + role labels |
| profile | 22 | revoke confirm + key-copy chip |
| errors | 9 | generic catch-all bucket |
| actions | 14 | reusable verbs |
| placeholders | 9 | reusable input placeholders |
| confirms | 7 | dialog confirmations |
| **Total leaf keys** | **361** | matches AR exactly |

---

## Confidence on Arabic translations

**High confidence (idiomatic, native MSA/Egyptian)**:
- All UI chrome strings (nav, buttons, labels, hints).
- `chat.*` welcome/empty/status copy.
- `setup.*`, `login.*`, `admin.*`, `profile.*` flows.
- `errors.*`, `actions.*`, `confirms.*`.
- 8 of 12 agent name/description triples (chat, coder, writer, researcher,
  translator, tutor, summarizer, math).

**Medium confidence — translated naturally but borrowed terms remain**:
- `sampling.*`, `resources.*` — kept `Top-P`, `Top-K`, `Min-P`, `Mirostat`,
  `mlock`, `mmap`, `Tokens`, `Seed`, `GPU`, `VRAM`, `Batch`, `Token` as Latin
  inline; surrounding labels are Arabic. This matches how Arabic developer
  audiences actually speak.
- `providers.*` brand names (`Claude`, `ChatGPT`, `Gemini`, `OpenAI`) kept in
  Latin script — these are products, not concepts.
- "Mirostat τ (target entropy)" → "Mirostat τ (الإنتروبيا المستهدفة)" — the
  Greek letter + technical noun is preserved; the gloss is Arabicized.

**Lower confidence — needed creative choices**:
- **`agents.builtin.brainstormer.system_prompt`** — "no preamble, no caveats"
  rendered as "بدون مقدّمات، بدون تحفّظات" — accurate but slightly stiff; a
  native marketer might prefer "من غير لفّ ودوران".
- **`agents.builtin.storyteller.system_prompt`** — "Show, don't tell" rendered
  as "أرِ ولا تسرد". This is the standard literary-Arabic translation but feels
  formal; an Egyptian creative-writing teacher might say "ورّي ما تحكيش".
  Kept the MSA form for consistency.
- **`agents.builtin.marketer.system_prompt`** — "Hook, benefit, proof, call to
  action" rendered as "الجذب، ثم الفائدة، ثم البرهان، ثم الدعوة لاتخاذ إجراء".
  Marketing-Arabic often borrows "هوك" and "كول تو أكشن" directly; I chose the
  literal sequence for clarity. Worth A/B testing with native copywriters.
- **`agents.builtin.email.system_prompt`** — "No filler or jargon" → "لا حشو،
  ولا مصطلحات معقّدة". "Jargon" has no clean Arabic equivalent; "مصطلحات
  معقّدة" (complex terminology) is the closest.

**Translation philosophy applied**:
1. Preserve programming terms (`API`, `Token`, `GPU`, `VRAM`, `JSON`, `gguf`,
   `Bearer`, `endpoint`, `mlock`, `mmap`) as Latin inline — Arabic developer
   audiences do this naturally.
2. Use MSA for written sentences (suggestions, hints, errors) — keeps the tone
   professional and works for both Egyptian and Gulf readers.
3. Match the casual punch of the English in agent system_prompts — short
   imperative sentences rather than the longer Arabic literary form.
4. Keep `{token}` placeholders intact for templating (`{username}`, `{name}`,
   `{path}`, `{error}`, `{status}`).

---

## Tricky keys worth a follow-up

- **`models.size_mb` / `models.size_gb`** — currently `ميجا` / `جيجا`. If your
  audience expects `MB` / `GB` literally, change these two strings.
- **`chat.tokens_meta`** — `{count} رمز · {seconds} ث · {tps} رمز/ث`. The word
  `رمز` for "token" is the academic Arabic for "symbol". Many Arabic devs say
  `توكن` instead. Replace if a more conversational tone is preferred.
- **`agents.builtin.*.name`** — the English uses snappy two-word names
  (`Code Master`, `Patient Tutor`). Some Arabic equivalents grew longer
  (`خبير البرمجة`, `المعلّم الصبور`). UI grid may need to handle longer labels;
  sidebar `mode-btn` font-size is 12px which should still fit.
- **`chat.welcome_sub`** — mentions "GPU في جهاز الـ NAS". Some users might
  prefer "كرت الشاشة في الـ NAS"; current copy uses GPU intentionally as a
  brand-consistent technical term.
