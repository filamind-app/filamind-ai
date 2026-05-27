# Contributing to Filamind AI

Thanks for considering a contribution! This project is small but the supported-device matrix has sharp edges — please read this once before opening a PR.

شكراً لاهتمامك بالمساهمة. مصفوفة الأجهزة المدعومة دقيقة — اقرأ هذا الملف مرة قبل فتح PR.

---

## Repo layout · هيكل الريبو

```
.
├── main                       # Shared code (UI, daemon, agents, providers)
├── device/dva3221             # DVA 3221 — GPU build (CUDA 10.1, llama.cpp b1620)
├── device/ds1821-plus         # DS1821+ — CPU build (AVX2, latest llama.cpp)
├── spk-source/                # SPK package source (INFO, scripts, package/)
├── build_*.sh                 # Build scripts (per-device variants)
├── CHANGELOG.md               # Bilingual changelog (Keep a Changelog format)
├── README.md                  # Bilingual readme
└── LICENSE                    # Apache 2.0
```

`main` holds platform-independent code. **Device-specific files** (INFO arch, build scripts, llama-server binary) live in `device/*` branches and are merged into `main` only when the change is portable.

`main` يحوي الكود غير المعتمد على الجهاز. الملفات الخاصة بكل جهاز (INFO arch، build script، binary) تعيش في فروع `device/*`.

---

## Where to put your change

| If you're touching… | Go to branch |
|---|---|
| `package/web/**`, `package/bin/control_daemon.py`, `package/web/i18n/**` | `main` (then we merge to device branches) |
| `build_llama_gpu.sh`, anything CUDA-specific | `device/dva3221` |
| `build_llama_cpu_avx2.sh`, CPU-only tuning | `device/ds1821-plus` |
| `INFO`, `scripts/*` | depends — UI changes go to `main`, arch-specific go to device branch |
| `CHANGELOG.md`, `README.md`, `LICENSE` | `main` |

---

## Build · البناء

```bash
# Requires WSL2 (Ubuntu) on Windows, or any Linux host
bash check_toolchain.sh            # verify toolchain
bash build_spk.sh                  # package whatever's in spk-source/
```

For full llama-server rebuild:
- `build_llama_gpu.sh` — DVA 3221 (CUDA 10.1, sm_75)
- `build_llama_cpu_avx2.sh` — DS1821+ (Ryzen V1500B, znver1)

Output: `Filamind.spk` at repo root.

---

## Commit & PR guidelines · إرشادات الكوميت والـ PR

- **Conventional commits encouraged** — `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `build:`, `i18n:`.
- **Bilingual messages welcome** — `fix(daemon): clear failure cache · إصلاح ذاكرة الفشل`.
- **Bump version + add CHANGELOG entry** for any user-visible change. Follow [Keep a Changelog](https://keepachangelog.com/) with sections `Added`/`Changed`/`Fixed`/`Security`/`Removed`/`Deprecated`.
- **i18n: every new UI string gets both `en.json` and `ar.json` keys.** PRs with only English will be sent back. Arabic must be natural, not literal.
- **Security-sensitive changes** (auth, file paths, network) require a SECURITY.md note explaining the threat model.

---

## Adding a new device · إضافة جهاز

If you want to support a different Synology model (e.g. DS923+, DS220+, DS1019+):

1. Open an issue first with the model + `uname -a` + `cat /proc/cpuinfo | head -30` + `lspci` output.
2. We'll confirm which Synology toolchain matches (`v1000` / `denverton` / `apollolake` / `geminilake` / `braswell`).
3. Create branch `device/<model>` from `main`.
4. Add `build_llama_<device>.sh` tuned for that CPU's flags.
5. Update README's "Supported devices" table.
6. PR with at least one screenshot of the chat running on the new device.

---

## Security disclosure · الإبلاغ عن ثغرات

If you find a security issue, email **eg2@live.com** rather than filing a public issue. Allow 14 days for a fix before public disclosure.

---

## License · الترخيص

By submitting a PR you agree to license your contribution under [Apache License 2.0](LICENSE), the project license. Contributors retain copyright; the Apache patent grant applies.
