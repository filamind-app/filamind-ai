#!/usr/bin/env python3
"""Generate `packages.json` for Synology DSM's third-party Package Source feature.

Called by .github/workflows/release.yml after a release SPK is published. The
script doesn't talk to GitHub itself — it just emits the JSON document DSM
expects to receive when it fetches a Package Source URL.

Usage:
    python3 docs/_build_packages_json.py <version>

The DSM Package Source JSON format used here is the de-facto third-party
format that community sources (Jellyfin, JDownloader, SynoCommunity etc.) have
used for years. DSM filters this list client-side by `model[]` and `arch`.
"""
import json
import sys
import textwrap


def build(version: str) -> dict:
    base_url = "https://github.com/filamind-app/filamind-ai/releases/download/v" + version

    # Bilingual changelog — DSM displays this when the user clicks the version.
    changelog = textwrap.dedent(f"""\
        Filamind AI v{version}

        • Bilingual chat (Arabic + English with full RTL)
        • Local LLM via llama.cpp, optional cloud fallback (OpenAI / Anthropic / Gemini)
        • Multi-user with admin + user roles, per-user API keys, PBKDF2 password hashing
        • Self-update notifications inside the app

        Full changelog: https://github.com/filamind-app/filamind-ai/blob/main/CHANGELOG.md
    """).strip()

    common = {
        "dname":          "Filamind AI",
        "desc":           "Local LLM chat for your Synology NAS — runs Llama/Mistral models on your hardware with full privacy. OpenAI-compatible API, multi-user, Arabic + English.",
        "price":          0,
        "download_count": 0,
        "recent_download_count": 0,
        "qinst":          True,
        "qstart":         True,
        "qupgrade":       True,
        "depsers":        None,
        "conflictpkgs":   None,
        "start":          True,
        "maintainer":     "Abdelmonem Awad",
        "maintainer_url": "https://github.com/filamind-app/filamind-ai",
        "distributor":    "Abdelmonem Awad",
        "distributor_url": "https://github.com/filamind-app/filamind-ai",
        "changelog":      changelog,
        "thumbnail": [
            "https://raw.githubusercontent.com/filamind-app/filamind-ai/device/dva3221/spk-source/package/ui/images/FilamindAI-128.png",
            "https://raw.githubusercontent.com/filamind-app/filamind-ai/device/dva3221/spk-source/package/ui/images/FilamindAI-256.png",
        ],
        "snapshot":       [],
        "category":       0,
        "subcategory":    0,
        "type":           0,
        "beta":           False,
    }

    packages = [
        # ── DVA 3221 (denverton + CUDA 10.1 GPU) ────────────────────────
        {
            **common,
            "package":      "FilamindAI",
            "version":      f"{version}-0030",
            "link":         f"{base_url}/Filamind-{version}-dva3221.spk",
            "size":         3600000,    # approximate; DSM doesn't enforce strict equality
            "md5":          "",         # populated server-side by some sources; optional
            "deppkgs":      "NVIDIARuntimeLibrary>=1.0.0-0001",
            "model":        ["synology_denverton_dva3221"],
            "arch":         "x86_64",
        },
        # ── DS1821+ (v1000 / Ryzen V1500B, CPU AVX2) ────────────────────
        {
            **common,
            "package":      "FilamindAI",
            "version":      f"{version}-0030",
            "link":         f"{base_url}/Filamind-{version}-ds1821-plus.spk",
            "size":         3600000,
            "md5":          "",
            "deppkgs":      "",
            "model":        ["synology_v1000_1821+"],
            "arch":         "x86_64",
        },
    ]

    return {"packages": packages, "keyrings": []}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: _build_packages_json.py <version>", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(build(sys.argv[1]), indent=2, ensure_ascii=False))
