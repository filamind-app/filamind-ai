#!/bin/bash
set -e
ICON64=$(cat /tmp/icon_64.b64)
ICON256=$(cat /tmp/icon_256.b64)

cat > /mnt/c/Users/Eg2/Desktop/saynolgy/spk-source/INFO <<EOF
package="SaynologyAI"
version="0.3.1-0006"
os_min_ver="7.2-64561"
arch="x86_64"
model="synology_denverton_dva3221"
maintainer="Abdelmonem Awad"
maintainer_url="mailto:eg2@live.com"
distributor="Abdelmonem Awad"
distributor_url="mailto:eg2@live.com"
support_url="mailto:eg2@live.com"
displayname="SaynologyAI Chat"
displayname_enu="SaynologyAI Chat"
description="Local LLM chat powered by your NAS GPU.\n\nSaynologyAI runs large language models like Llama and TinyLlama directly on the NVIDIA GPU of your DVA 3221, with full privacy — no data leaves your network.\n\n• Built-in chat UI accessible from DSM (click the SaynologyAI icon)\n• Native GPU acceleration via CUDA 10.1 on GTX 1650 (sm_75)\n• OpenAI-compatible HTTP API on port 8181 for use with other tools\n• Auto-discovers .gguf model files in /volume1/SaynologyAI/models/, /volume1/AI/models/, or any custom path you configure\n• Runs as a native DSM package, fully managed via Package Center\n\nAfter installation:\n1. Place a GGUF model file in /volume1/SaynologyAI/models/ (use File Station)\n2. Start the package — the chat will be available on port 8181\n3. Click the SaynologyAI Chat icon in DSM to open the web interface\n\nRecommended models: TinyLlama 1.1B Q4_K_M (smallest, fast), Llama 3.2 3B Q4 (balanced), Llama 2 7B Q4 (best quality, fills 4GB VRAM).\n\nDeveloped by Abdelmonem Awad (eg2@live.com)."
description_enu="Local LLM chat powered by your NAS GPU. Runs Llama-family models on the NVIDIA GTX 1650 of the DVA 3221 with full privacy. Built-in web chat UI + OpenAI-compatible API on port 8181. Developed by Abdelmonem Awad (eg2@live.com)."
dsmuidir="ui"
dsmappname="SYNO.SDS.SaynologyAI.Application"
install_dep_packages="NVIDIARuntimeLibrary>=1.0.0-0001"
start_dep_services=""
ctl_stop="yes"
support_center="no"
silent_install="no"
silent_upgrade="no"
silent_uninstall="no"
thirdparty="yes"
create_time="20260526-22:00:00"
package_icon="${ICON64}"
package_icon_256="${ICON256}"
EOF

echo "=== INFO (no icons) ==="
grep -v "^package_icon" /mnt/c/Users/Eg2/Desktop/saynolgy/spk-source/INFO
