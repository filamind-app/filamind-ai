#!/usr/bin/env python3
"""Filamind AI control daemon.

Multi-user web app:
- Supervises llama-server (internal port 8180)
- Reverse-proxies /v1/*, /health, /props, /slots to llama-server (auth-protected)
- Serves the chat UI + login / setup / admin / profile pages
- SQLite-backed users + API keys
- Cookie sessions (HMAC-signed)
- i18n catalogs (en, ar)

Auth model
----------
* First-run: any visit when there is no admin user goes to /setup.html.
* Login required for all /api/* (except /api/auth/*) and the chat page.
* Roles: 'admin' (full control) and 'user' (chat + read system info only).
* API tokens authorise Bearer-token access for programmatic clients.
"""
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

# ───── Paths ────────────────────────────────────────────────────────────────
INSTALL_DIR  = "/var/packages/FilamindAI/target"
NVIDIA_PKG   = "/var/packages/NVIDIARuntimeLibrary/target"
ETC_DIR      = "/var/packages/FilamindAI/etc"
CONFIG_FILE  = ETC_DIR + "/filamindai.conf"
LEGACY_CONFIG_FILE = "/var/packages/SaynologyAI/etc/saynologyai.conf"  # back-compat read on first run
SECRET_FILE  = ETC_DIR + "/secret.key"
DB_FILE      = ETC_DIR + "/users.db"
MCP_DB_FILE  = ETC_DIR + "/mcp.db"
WEB_DIR      = INSTALL_DIR + "/web"
LLAMA_BIN    = INSTALL_DIR + "/bin/llama-server"
LOG_FILE     = INSTALL_DIR + "/var/llama-server.log"
INTERNAL_PORT = 8180

# MCP runtime — loaded lazily so the daemon still starts if the module is missing.
_MCP_REGISTRY = None
def _get_mcp_registry():
    """Lazy-init the MCP registry. Returns None on import error (tools then unavailable)."""
    global _MCP_REGISTRY
    if _MCP_REGISTRY is not None:
        return _MCP_REGISTRY
    try:
        import sys as _sys
        _sys.path.insert(0, INSTALL_DIR + "/bin")
        from mcp_runtime import MCPRegistry          # noqa: WPS433 — runtime import is intentional
        from mcp_servers import register_builtin_servers
        os.makedirs(ETC_DIR, exist_ok=True)
        _MCP_REGISTRY = MCPRegistry(MCP_DB_FILE)
        register_builtin_servers(_MCP_REGISTRY)
        return _MCP_REGISTRY
    except Exception as _e:  # noqa: BLE001
        sys.stderr.write(f"[mcp] runtime unavailable: {_e}\n")
        return None

DEFAULT_CFG = {
    "MODEL_PATH":    "",
    "MODEL_DIRS":    "",
    "LISTEN_HOST":   "0.0.0.0",
    "LISTEN_PORT":   "8181",
    "N_GPU_LAYERS":  "999",
    "CTX_SIZE":      "8192",
    "BATCH_SIZE":    "512",
    "UBATCH_SIZE":   "256",
    "THREADS":       "4",
    "THREADS_BATCH": "4",
    "USE_MLOCK":     "0",
    "USE_NO_MMAP":   "1",
    "PARALLEL":      "1",
    "EXTRA_ARGS":    "",
}

STATE = {
    "llama_proc": None,
    "lock": threading.Lock(),
    "current_model": "",
    "last_start_ts": 0,
    "request_restart": False,
    "shutting_down": False,
    "downloads": {},          # id → {url,name,total,received,status,error,started}
    "downloads_lock": threading.Lock(),
    "model_failures": {},     # path → {"reason": str, "count": int, "ts": float}
    "load_state": "idle",     # idle | loading | ready | failed
    "load_error": "",
}

MAX_LOAD_ATTEMPTS = 2
LOAD_FAIL_COOLDOWN_S = 60

# Curated GGUF catalog — only models confirmed to work with llama.cpp b1620.
# All URLs are HuggingFace `resolve/main` direct links.
MODEL_CATALOG = [
    {
        "id": "tinyllama-1.1b-chat-q4",
        "name": "TinyLlama 1.1B Chat (Q4_K_M)",
        "family": "Llama",
        "size_mb": 668,
        "params": "1.1B",
        "vram_mb": 900,
        "description": "Smallest reliable chat model. Fast on the GTX 1650. Good for quick answers and testing.",
        "url": "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "filename": "tinyllama-1.1b-chat-q4_k_m.gguf",
        "tags": ["small", "fast"]
    },
    {
        "id": "phi-2-q4",
        "name": "Phi-2 (Q4_K_M)",
        "family": "Phi",
        "size_mb": 1620,
        "params": "2.7B",
        "vram_mb": 1900,
        "description": "Microsoft's small but capable model. Strong reasoning for its size. Note: Phi-2 (not Phi-3).",
        "url": "https://huggingface.co/TheBloke/phi-2-GGUF/resolve/main/phi-2.Q4_K_M.gguf",
        "filename": "phi-2-q4_k_m.gguf",
        "tags": ["small", "reasoning"]
    },
    {
        "id": "mistral-7b-instruct-v02-q4",
        "name": "Mistral 7B Instruct v0.2 (Q4_K_M)",
        "family": "Mistral",
        "size_mb": 4140,
        "params": "7B",
        "vram_mb": 4400,
        "description": "Solid general-purpose 7B model. Fills most of the GTX 1650 VRAM at default context. Good balance of quality and speed.",
        "url": "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "filename": "mistral-7b-instruct-v0.2-q4_k_m.gguf",
        "tags": ["7B", "balanced", "recommended"]
    },
    {
        "id": "openhermes-25-mistral-7b-q4",
        "name": "OpenHermes 2.5 Mistral 7B (Q4_K_M)",
        "family": "Mistral",
        "size_mb": 4140,
        "params": "7B",
        "vram_mb": 4400,
        "description": "Mistral-7B fine-tuned for assistant-style chat. Often beats Llama-2 chat in side-by-side tests.",
        "url": "https://huggingface.co/TheBloke/OpenHermes-2.5-Mistral-7B-GGUF/resolve/main/openhermes-2.5-mistral-7b.Q4_K_M.gguf",
        "filename": "openhermes-2.5-mistral-7b-q4_k_m.gguf",
        "tags": ["7B", "chat", "recommended"]
    },
    {
        "id": "codellama-7b-instruct-q4",
        "name": "CodeLlama 7B Instruct (Q4_K_M)",
        "family": "Llama",
        "size_mb": 4080,
        "params": "7B",
        "vram_mb": 4300,
        "description": "Llama-2 fine-tune for code generation and Q&A. Use the Code mode in the chat for best results.",
        "url": "https://huggingface.co/TheBloke/CodeLlama-7B-Instruct-GGUF/resolve/main/codellama-7b-instruct.Q4_K_M.gguf",
        "filename": "codellama-7b-instruct-q4_k_m.gguf",
        "tags": ["7B", "code"]
    },
    {
        "id": "llama-2-7b-chat-q4",
        "name": "Llama 2 7B Chat (Q4_K_M)",
        "family": "Llama",
        "size_mb": 4080,
        "params": "7B",
        "vram_mb": 4300,
        "description": "Meta's classic Llama-2 chat model. Familiar baseline, well-aligned for assistant use.",
        "url": "https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q4_K_M.gguf",
        "filename": "llama-2-7b-chat-q4_k_m.gguf",
        "tags": ["7B", "classic"]
    },
    {
        "id": "acegpt-7b-chat-q4",
        "name": "AceGPT 7B Chat — Arabic (Q4_K_M)",
        "family": "Llama",
        "size_mb": 4080,
        "params": "7B",
        "vram_mb": 4300,
        "description": "Llama-2 7B fine-tuned by FreedomIntelligence specifically for Arabic. Strong Arabic comprehension and generation — the best small-footprint Arabic model that works with this build.",
        "url": "https://huggingface.co/TheBloke/AceGPT-7B-chat-GGUF/resolve/main/acegpt-7b-chat.Q4_K_M.gguf",
        "filename": "acegpt-7b-chat-q4_k_m.gguf",
        "tags": ["7B", "arabic", "recommended-ar"]
    },
    {
        "id": "noon-7b-q4",
        "name": "Noon 7B Arabic (Q4_K_M)",
        "family": "Llama",
        "size_mb": 4080,
        "params": "7B",
        "vram_mb": 4300,
        "description": "Naseej Lab's Llama-2 Arabic fine-tune. Conversational Arabic with cultural awareness.",
        "url": "https://huggingface.co/TheBloke/noon-7b-GGUF/resolve/main/noon-7b.Q4_K_M.gguf",
        "filename": "noon-7b-q4_k_m.gguf",
        "tags": ["7B", "arabic"]
    },
    {
        "id": "openhermes-2.5-mistral-7b-q4-ar",
        "name": "OpenHermes 2.5 Mistral 7B (Q4_K_M) — multilingual",
        "family": "Mistral",
        "size_mb": 4140,
        "params": "7B",
        "vram_mb": 4400,
        "description": "Already in the catalog under 'recommended', but worth flagging again: handles Arabic decently and is one of the most reliable 7B chat models for b1620.",
        "url": "https://huggingface.co/TheBloke/OpenHermes-2.5-Mistral-7B-GGUF/resolve/main/openhermes-2.5-mistral-7b.Q4_K_M.gguf",
        "filename": "openhermes-2.5-mistral-7b-q4_k_m.gguf",
        "tags": ["7B", "arabic", "multilingual"]
    },
    {
        "id": "tinyllama-1.1b-chat-q8",
        "name": "TinyLlama 1.1B Chat (Q8_0 — higher quality)",
        "family": "Llama",
        "size_mb": 1170,
        "params": "1.1B",
        "vram_mb": 1400,
        "description": "Same as TinyLlama Q4, but Q8 quantisation — noticeably higher quality at a bit more VRAM.",
        "url": "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q8_0.gguf",
        "filename": "tinyllama-1.1b-chat-q8_0.gguf",
        "tags": ["small", "quality"]
    },
]

SESSION_TTL = 7 * 24 * 3600   # 7 days
SESSION_COOKIE = "filamindai_session"

# ───── Logging ──────────────────────────────────────────────────────────────
def log(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [daemon] {msg}\n")
    except Exception:
        print(msg)


# ───── Secret key ───────────────────────────────────────────────────────────
def load_or_create_secret():
    try:
        with open(SECRET_FILE, "rb") as f:
            return f.read()
    except FileNotFoundError:
        os.makedirs(ETC_DIR, exist_ok=True)
        key = secrets.token_bytes(48)
        with open(SECRET_FILE, "wb") as f:
            f.write(key)
        os.chmod(SECRET_FILE, 0o600)
        return key

SECRET = load_or_create_secret()


# ───── Database ─────────────────────────────────────────────────────────────
DB_LOCK = threading.Lock()

def db():
    conn = sqlite3.connect(DB_FILE, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def _chmod_quiet(path, mode):
    """Best-effort chmod — never raise (perms are defence-in-depth, not load-bearing)."""
    try:
        os.chmod(path, mode)
    except Exception:
        pass


def db_init():
    os.makedirs(ETC_DIR, exist_ok=True)
    _chmod_quiet(ETC_DIR, 0o700)   # etc/ holds users.db, secret.key, providers.json
    with DB_LOCK, db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            display_name TEXT,
            language TEXT DEFAULT 'en',
            theme TEXT DEFAULT 'light',
            created_at INTEGER NOT NULL,
            last_login INTEGER
        );
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            key_hash TEXT NOT NULL,
            prefix TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            last_used INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS user_prefs (
            user_id INTEGER PRIMARY KEY,
            data TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            icon TEXT,
            description TEXT,
            system_prompt TEXT,
            model_path TEXT,
            temperature REAL DEFAULT 0.7,
            top_p REAL DEFAULT 0.95,
            top_k INTEGER DEFAULT 40,
            max_tokens INTEGER DEFAULT 512,
            tags TEXT,
            is_builtin INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at INTEGER,
            updated_at INTEGER,
            tools TEXT,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        );
        """)
        # Migration for installs created before the agents.tools column existed.
        try:
            cols = [r[1] for r in c.execute("PRAGMA table_info(agents)").fetchall()]
            if "tools" not in cols:
                c.execute("ALTER TABLE agents ADD COLUMN tools TEXT")
        except Exception:
            pass
        # Seed default agents (only insert if missing — don't overwrite user edits)
        now = int(time.time())
        for a in DEFAULT_AGENTS:
            c.execute("""INSERT OR IGNORE INTO agents
                (id, name, icon, description, system_prompt, model_path,
                 temperature, top_p, top_k, max_tokens, tags, is_builtin, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (a["id"], a["name"], a.get("icon",""), a.get("description",""),
                 a["system_prompt"], a.get("model_path"),
                 a.get("temperature", 0.7), a.get("top_p", 0.95), a.get("top_k", 40),
                 a.get("max_tokens", 512), a.get("tags",""), now, now))
    # Lock down the DB file (+ its WAL/SHM sidecars) — contains password & API-key
    # hashes; must not be world-readable to co-resident DSM packages/users.
    for suffix in ("", "-wal", "-shm"):
        _chmod_quiet(DB_FILE + suffix, 0o600)


def agent_to_dict(row):
    if row is None: return None
    return {
        "id": row["id"], "name": row["name"], "icon": row["icon"] or "🤖",
        "description": row["description"] or "",
        "system_prompt": row["system_prompt"] or "",
        "model_path": row["model_path"] or "",
        "temperature": row["temperature"], "top_p": row["top_p"], "top_k": row["top_k"],
        "max_tokens": row["max_tokens"],
        "tags": (row["tags"] or "").split(",") if row["tags"] else [],
        "is_builtin": bool(row["is_builtin"]),
        "tools": (json.loads(row["tools"]) if _row_has(row, "tools") and row["tools"] else []),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }

def _row_has(row, key):
    try:
        return key in row.keys()
    except Exception:
        return False

def list_agents():
    with db() as c:
        rows = c.execute("SELECT * FROM agents ORDER BY is_builtin DESC, name").fetchall()
        return [agent_to_dict(r) for r in rows]

def get_agent(agent_id):
    with db() as c:
        r = c.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        return agent_to_dict(r)

def has_admin():
    with db() as c:
        r = c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()
        return r[0] > 0


# ───── Password / token utilities ───────────────────────────────────────────
def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000)
    return salt, h.hex()

def verify_password(password, salt, h_hex):
    _, h = hash_password(password, salt)
    return secrets.compare_digest(h, h_hex)

def b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

def b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))

def sign_session(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    msg = b64u_encode(raw)
    sig = hmac.new(SECRET, msg.encode("ascii"), hashlib.sha256).digest()
    return msg + "." + b64u_encode(sig)

def verify_session(token: str):
    try:
        msg, sig = token.split(".", 1)
        expected = hmac.new(SECRET, msg.encode("ascii"), hashlib.sha256).digest()
        actual = b64u_decode(sig)
        if not hmac.compare_digest(expected, actual):
            return None
        payload = json.loads(b64u_decode(msg).decode("utf-8"))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None

def generate_api_key():
    """Return (display_key, key_hash, prefix). The display_key is shown once."""
    raw = secrets.token_urlsafe(32)
    full = "sk-" + raw
    h = hashlib.sha256(full.encode("utf-8")).hexdigest()
    return full, h, full[:10]

def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# ───── User helpers ─────────────────────────────────────────────────────────
def user_to_dict(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "display_name": row["display_name"] or row["username"],
        "language": row["language"] or "en",
        "theme": row["theme"] or "light",
        "created_at": row["created_at"],
        "last_login": row["last_login"],
    }

def get_user(username=None, user_id=None):
    with db() as c:
        if username:
            r = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        else:
            r = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return r

def create_user(username, password, role="user", display_name=None):
    salt, h = hash_password(password)
    now = int(time.time())
    with DB_LOCK, db() as c:
        cur = c.execute(
            "INSERT INTO users (username, password_hash, salt, role, display_name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (username, h, salt, role, display_name or username, now),
        )
        return cur.lastrowid


# ───── Config IO (same as before) ───────────────────────────────────────────
def read_config():
    cfg = dict(DEFAULT_CFG)
    try:
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                cfg[k.strip()] = v
    except FileNotFoundError:
        pass
    except Exception as e:
        log(f"Config read error: {e}")
    return cfg

def write_config(cfg):
    lines = [
        "# Filamind AI configuration (managed by the UI)",
        "",
        f'MODEL_PATH="{cfg.get("MODEL_PATH","")}"',
        f'MODEL_DIRS="{cfg.get("MODEL_DIRS","")}"',
        f'LISTEN_HOST="{cfg.get("LISTEN_HOST","0.0.0.0")}"',
        f'LISTEN_PORT="{cfg.get("LISTEN_PORT","8181")}"',
        f'PARALLEL="{cfg.get("PARALLEL","1")}"',
        f'N_GPU_LAYERS="{cfg.get("N_GPU_LAYERS","999")}"',
        f'CTX_SIZE="{cfg.get("CTX_SIZE","8192")}"',
        f'BATCH_SIZE="{cfg.get("BATCH_SIZE","512")}"',
        f'UBATCH_SIZE="{cfg.get("UBATCH_SIZE","256")}"',
        f'THREADS="{cfg.get("THREADS","4")}"',
        f'THREADS_BATCH="{cfg.get("THREADS_BATCH","4")}"',
        f'USE_MLOCK="{cfg.get("USE_MLOCK","0")}"',
        f'USE_NO_MMAP="{cfg.get("USE_NO_MMAP","1")}"',
        f'EXTRA_ARGS="{cfg.get("EXTRA_ARGS","")}"',
        "",
    ]
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines))
    os.replace(tmp, CONFIG_FILE)


# ───── Model discovery ──────────────────────────────────────────────────────
def search_dirs(cfg):
    dirs = []
    mp = cfg.get("MODEL_PATH", "")
    if mp and os.path.isdir(mp):
        dirs.append(mp)
    for d in (cfg.get("MODEL_DIRS") or "").split(":"):
        if d:
            dirs.append(d)
    dirs.extend([
        INSTALL_DIR + "/models",
        "/volume1/FilamindAI/models",
        "/volume1/SaynologyAI/models",           # legacy — keep so old installs still find models
        "/volume1/AI/models",
        "/volume1/homes/admin/FilamindAI/models",
        "/volume1/homes/admin/SaynologyAI/models",  # legacy
    ])
    seen = []
    for d in dirs:
        if d and d not in seen:
            seen.append(d)
    return seen

def find_model(cfg):
    """Auto-discover a model. Prefer the SMALLEST .gguf — safest on a 4 GB GPU
    so a fresh install doesn't crash trying to load a 7B model."""
    mp = cfg.get("MODEL_PATH", "")
    if mp and os.path.isfile(mp):
        return mp
    candidates = []
    for d in search_dirs(cfg):
        if not os.path.isdir(d):
            continue
        try:
            for name in os.listdir(d):
                if not name.endswith(".gguf"):
                    continue
                p = os.path.join(d, name)
                try:
                    candidates.append((os.path.getsize(p), p))
                except OSError:
                    pass
        except OSError:
            continue
    if candidates:
        candidates.sort(key=lambda x: x[0])   # smallest first
        return candidates[0][1]
    return None

def list_models(cfg):
    out, seen = [], set()
    for d in search_dirs(cfg):
        if not os.path.isdir(d):
            continue
        try:
            for name in sorted(os.listdir(d)):
                if not name.endswith(".gguf"):
                    continue
                p = os.path.join(d, name)
                if p in seen:
                    continue
                seen.add(p)
                try: size = os.path.getsize(p)
                except OSError: size = 0
                out.append({
                    "name": name, "path": p, "dir": d,
                    "size_bytes": size, "size_mb": round(size / 1024 / 1024, 1),
                    "current": p == STATE["current_model"],
                })
        except OSError:
            continue
    return out


# ───── llama-server supervision ─────────────────────────────────────────────
def start_llama(cfg):
    with STATE["lock"]:
        p = STATE["llama_proc"]
        if p is not None and p.poll() is None:
            return False
        model = find_model(cfg)
        if not model:
            log(f"No GGUF model in: {search_dirs(cfg)}")
            return False
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = ":".join([
            NVIDIA_PKG + "/cuda/lib64",
            NVIDIA_PKG + "/nvidia/lib",
            INSTALL_DIR + "/lib",
            env.get("LD_LIBRARY_PATH", ""),
        ])
        args = [
            LLAMA_BIN, "--model", model,
            "--host", "127.0.0.1", "--port", str(INTERNAL_PORT),
            "--n-gpu-layers",  cfg.get("N_GPU_LAYERS", "999"),
            "--ctx-size",      cfg.get("CTX_SIZE", "8192"),
            "--batch-size",    cfg.get("BATCH_SIZE", "512"),
            "--threads",       cfg.get("THREADS", "4"),
            "--threads-batch", cfg.get("THREADS_BATCH", "4"),
            "--parallel",      cfg.get("PARALLEL", "1"),
            "--path",          WEB_DIR,
        ]
        if cfg.get("USE_MLOCK") == "1":  args.append("--mlock")
        if cfg.get("USE_NO_MMAP") == "1": args.append("--no-mmap")
        extra = (cfg.get("EXTRA_ARGS") or "").strip()
        if extra: args.extend(extra.split())
        log(f"Starting: {' '.join(args)}")
        STATE["last_start_ts"] = time.time()
        STATE["current_model"] = model
        try: logf = open(LOG_FILE, "ab")
        except Exception: logf = subprocess.DEVNULL
        STATE["llama_proc"] = subprocess.Popen(args, env=env, stdout=logf, stderr=logf, start_new_session=True)
        # Close the parent's fd — Popen inherited it and we don't need it any more.
        # Fixes a slow file-handle leak across restart cycles.
        if logf is not subprocess.DEVNULL:
            try: logf.close()
            except Exception: pass
        return True

def stop_llama():
    with STATE["lock"]:
        p = STATE["llama_proc"]
        if p is None or p.poll() is not None:
            STATE["llama_proc"] = None
            return
        try: os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except ProcessLookupError: pass
        try: p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try: os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except ProcessLookupError: pass
            try: p.wait(timeout=3)
            except subprocess.TimeoutExpired: pass
        STATE["llama_proc"] = None

def _detect_load_failure(tail):
    """Inspect llama-server log tail for known failure signatures."""
    low = tail.lower()
    if "out of memory" in low or "cuda error 2" in low or "cuda error: out of memory" in low:
        return ("oom", "GPU ran out of memory loading the model. Try a smaller model or lower context size.")
    if "unknown model architecture" in low:
        m = re.search(r"unknown model architecture:\s*'([^']+)'", tail)
        arch = m.group(1) if m else "?"
        return ("unsupported_arch", f"Model architecture '{arch}' is not supported by this llama.cpp build (b1620). Choose a Llama / Mistral / Phi-2 family model.")
    if "failed to load model" in low or "error loading model" in low:
        return ("load_error", "Model failed to load. Check the log for details.")
    return None


def supervisor():
    while not STATE["shutting_down"]:
        cfg = read_config()
        if STATE["request_restart"]:
            STATE["request_restart"] = False
            stop_llama()
            time.sleep(0.5)
            STATE["load_state"] = "loading"
            STATE["load_error"] = ""

        proc = STATE["llama_proc"]
        if proc is None or proc.poll() is not None:
            # Did it die during/after load? Inspect log.
            if proc is not None and proc.poll() is not None and STATE.get("current_model"):
                try:
                    with open(LOG_FILE, "rb") as f:
                        f.seek(0, 2); sz = f.tell()
                        f.seek(max(0, sz - 4000))
                        tail = f.read().decode("utf-8", "replace")
                    fail = _detect_load_failure(tail)
                    if fail:
                        model = STATE["current_model"]
                        rec = STATE["model_failures"].setdefault(model, {"count": 0})
                        rec["reason"] = fail[1]
                        rec["kind"]   = fail[0]
                        rec["count"] += 1
                        rec["ts"]     = time.time()
                        STATE["load_state"] = "failed"
                        STATE["load_error"] = fail[1]

                        # OOM auto-recovery: halve ctx + reduce layers, retry once.
                        if fail[0] == "oom" and rec["count"] == 1:
                            try:
                                cur_ctx = int(cfg.get("CTX_SIZE", "2048") or 2048)
                                cur_layers = int(cfg.get("N_GPU_LAYERS", "999") or 999)
                            except ValueError:
                                cur_ctx, cur_layers = 2048, 999
                            new_ctx = max(512, cur_ctx // 2)
                            new_layers = max(8, min(cur_layers, 16))
                            if new_ctx != cur_ctx or new_layers != cur_layers:
                                cfg["CTX_SIZE"] = str(new_ctx)
                                cfg["N_GPU_LAYERS"] = str(new_layers)
                                write_config(cfg)
                                log(f"OOM auto-recovery: ctx {cur_ctx}→{new_ctx}, layers {cur_layers}→{new_layers}. Retrying.")
                                STATE["load_state"] = "loading"
                                STATE["load_error"] = ""
                                STATE["last_start_ts"] = time.time() - 6  # bypass cooldown
                                # Don't increment past 1 — give the new settings a fair shot
                                rec["count"] = 0
                                continue

                        if rec["count"] >= MAX_LOAD_ATTEMPTS:
                            log(f"Model {model} failed {rec['count']}x ({fail[0]}). Cooling down.")
                            time.sleep(2)
                            continue
                except Exception:
                    pass

            # Cooldown check: don't keep retrying a model that just failed
            model_now = cfg.get("MODEL_PATH") or ""
            rec = STATE["model_failures"].get(model_now)
            if rec and rec.get("count", 0) >= MAX_LOAD_ATTEMPTS \
               and (time.time() - rec.get("ts", 0)) < LOAD_FAIL_COOLDOWN_S:
                time.sleep(3)
                continue

            if time.time() - STATE["last_start_ts"] > 5:
                STATE["load_state"] = "loading"
                if start_llama(cfg):
                    # Wait briefly to see if it stays alive
                    time.sleep(2)
                    if STATE["llama_proc"] and STATE["llama_proc"].poll() is None:
                        STATE["load_state"] = "ready"
        time.sleep(2)


# ───── Model downloader ─────────────────────────────────────────────────────
def download_worker(download_id):
    info = STATE["downloads"][download_id]
    url = info["url"]
    target_dir = "/volume1/FilamindAI/models"
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        info["status"] = "failed"; info["error"] = f"Cannot create dir: {e}"
        return
    final_path = os.path.join(target_dir, info["name"])
    tmp_path = final_path + ".part"

    info["status"] = "running"
    info["dest"] = final_path
    # Re-validate at fetch time (the URL was checked when queued, but guard again).
    if not _is_safe_download_url(url):
        info["status"] = "failed"; info["error"] = "blocked_host"
        return
    try:
        with SAFE_OPENER.open(url, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            info["total"] = total
            with open(tmp_path, "wb") as f:
                while True:
                    if info.get("cancel"):
                        info["status"] = "cancelled"
                        try: os.remove(tmp_path)
                        except Exception: pass
                        return
                    chunk = resp.read(1024 * 64)
                    if not chunk:
                        break
                    f.write(chunk)
                    info["received"] += len(chunk)
        os.replace(tmp_path, final_path)
        info["status"] = "done"
        info["finished"] = time.time()
    except Exception as e:
        info["status"] = "failed"
        info["error"] = str(e)
        try: os.remove(tmp_path)
        except Exception: pass

def start_download(url, name):
    download_id = secrets.token_hex(8)
    with STATE["downloads_lock"]:
        STATE["downloads"][download_id] = {
            "id": download_id,
            "url": url,
            "name": name,
            "status": "starting",
            "received": 0,
            "total": 0,
            "error": "",
            "started": time.time(),
            "cancel": False,
        }
    t = threading.Thread(target=download_worker, args=(download_id,), daemon=True)
    t.start()
    return download_id


# ───── Reverse proxy ────────────────────────────────────────────────────────
def _sanitize_v1_body(raw: bytes) -> bytes:
    """Hard-whitelist the request body. llama.cpp b1620 is strict; anything
    weird in the body (wrong type, unknown key) can trigger a 500. We rebuild
    the body from scratch keeping only known-good fields with correct types."""
    try:
        src = json.loads(raw.decode("utf-8"))
        if not isinstance(src, dict):
            return raw
    except Exception:
        return raw

    out = {}

    # messages: list of {role:str, content:str}
    msgs = src.get("messages")
    if isinstance(msgs, list):
        clean = []
        for m in msgs:
            if not isinstance(m, dict): continue
            role = m.get("role")
            content = m.get("content")
            if not isinstance(role, str) or not isinstance(content, str): continue
            if role not in ("system", "user", "assistant", "tool"): continue
            clean.append({"role": role, "content": content})
        if clean: out["messages"] = clean

    # prompt (used by legacy /completion path)
    if isinstance(src.get("prompt"), str):
        out["prompt"] = src["prompt"]

    # model
    if isinstance(src.get("model"), str):
        out["model"] = src["model"]

    def _bool(v, default):
        if isinstance(v, bool): return v
        if v is None: return default
        try: return bool(int(v))
        except Exception:
            return bool(v)
    def _int(v, default=None):
        try:
            if isinstance(v, bool): return int(v)
            return int(v)
        except Exception: return default
    def _float(v, default=None):
        try:
            if isinstance(v, bool): return float(v)
            return float(v)
        except Exception: return default

    # Bool field with explicit default of False to match llama.cpp.
    # NOTE: b1620 has a bug where `mirostat`, `penalize_nl`, `ignore_eos` are
    # declared with bool defaults in `oaicompat_completion_params_parse`, so
    # ANY numeric value crashes the server with json.exception.type_error.302
    # (fixed in PR #4668 / b1697). For b1620 we DROP these keys entirely so
    # the parser uses its safe default branch.
    if "stream" in src:        out["stream"]        = _bool(src.get("stream"), False)
    if "cache_prompt" in src:  out["cache_prompt"]  = _bool(src.get("cache_prompt"), False)
    # Drop: penalize_nl, ignore_eos, mirostat (b1620 type-error.302 trap)

    # Float
    for k in ("temperature", "top_p", "min_p", "tfs_z", "typical_p",
              "repeat_penalty", "presence_penalty", "frequency_penalty",
              "mirostat_tau", "mirostat_eta"):
        if k in src:
            v = _float(src[k])
            if v is not None: out[k] = v

    # Int (NOTE: mirostat dropped — see comment above)
    for k in ("top_k", "repeat_last_n", "max_tokens", "n_predict",
              "n_keep", "n_probs", "min_keep", "seed"):
        if k in src:
            v = _int(src[k])
            if v is not None: out[k] = v

    # stop: list of strings
    s = src.get("stop")
    if isinstance(s, str) and s:
        out["stop"] = [s]
    elif isinstance(s, list):
        out["stop"] = [str(x) for x in s if x]

    return json.dumps(out, ensure_ascii=False).encode("utf-8")


DAEMON_VERSION = "1.4.0"
REPO_OWNER     = "filamind-app"
REPO_NAME      = "filamind-ai"
REPO_URL       = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
RELEASES_API   = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
RELEASES_URL   = f"{REPO_URL}/releases"
CHANGELOG_RAW  = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/CHANGELOG.md"

# Per-package on-disk paths for static metadata (set at build time)
INFO_FILE      = "/var/packages/FilamindAI/INFO"        # available on running NAS
CHANGELOG_FILE = INSTALL_DIR + "/CHANGELOG.md"          # shipped in package
BUILD_INFO     = INSTALL_DIR + "/BUILD_INFO"            # optional: git sha + date

# Cached results — refreshed once per hour to avoid hammering GitHub.
_UPDATE_CACHE = {"checked_at": 0, "data": None}
_UPDATE_CACHE_TTL = 3600   # seconds


# ───── Release / version helpers ────────────────────────────────────────────
def _read_text(path, default=""):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return default


def _parse_info_field(content, key):
    """Pull a `key="value"` line out of the SPK INFO file."""
    import re
    m = re.search(r'^' + re.escape(key) + r'="([^"]*)"', content, re.M)
    return m.group(1) if m else None


def _read_build_info():
    """Optional BUILD_INFO file written at SPK build time. Format: KEY=VALUE per line."""
    info = {}
    raw = _read_text(BUILD_INFO)
    for line in raw.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()
    return info


def _semver_compare(a, b):
    """Return -1/0/1 comparing two version strings like 1.2.5 vs 1.2.4-0029.
    Tolerant: strips leading 'v', splits on dashes, compares numeric parts."""
    def normalize(s):
        s = (s or "").lstrip("v").strip()
        s = s.split("-")[0]   # drop -0029 build suffix
        parts = []
        for p in s.split("."):
            try: parts.append(int(p))
            except ValueError: parts.append(0)
        while len(parts) < 3: parts.append(0)
        return parts[:3]
    na, nb = normalize(a), normalize(b)
    return (na > nb) - (na < nb)


def _get_version_info():
    """Rich version + build + device info served by /api/version."""
    info_content = _read_text(INFO_FILE)
    build = _read_build_info()
    dsm_version = ""
    try:
        # /etc.defaults/synoinfo.conf is shipped by DSM; harmless on dev hosts.
        synoinfo = _read_text("/etc.defaults/synoinfo.conf")
        import re
        m = re.search(r'^productversion="([^"]+)"', synoinfo, re.M)
        if m: dsm_version = m.group(1)
        m = re.search(r'^buildnumber="([^"]+)"', synoinfo, re.M)
        if m: dsm_version += f"-{m.group(1)}"
    except Exception:
        pass

    # GPU detection (best-effort)
    engine = "llama.cpp (cpu)"
    try:
        if os.path.exists("/dev/nvidia0"):
            engine = "llama.cpp b1620 + CUDA 10.1 (GPU)"
        else:
            # Detect AVX2 vs SSE-only for the CPU build description
            cpu = _read_text("/proc/cpuinfo")
            if "avx2" in cpu:
                engine = "llama.cpp latest + CPU AVX2"
    except Exception:
        pass

    return {
        "daemon_version":  DAEMON_VERSION,
        "package_name":    _parse_info_field(info_content, "package") or "FilamindAI",
        "package_version": _parse_info_field(info_content, "version") or DAEMON_VERSION,
        "displayname":     _parse_info_field(info_content, "displayname") or "Filamind AI",
        "model":           _parse_info_field(info_content, "model") or "",
        "arch":            _parse_info_field(info_content, "arch") or "",
        "maintainer":      _parse_info_field(info_content, "maintainer") or "Abdelmonem Awad",
        "dsm_version":     dsm_version,
        "engine":          engine,
        "build_date":      build.get("BUILD_DATE", ""),
        "git_sha":         build.get("GIT_SHA", ""),
        "git_branch":      build.get("GIT_BRANCH", ""),
        "repo_url":        REPO_URL,
        "releases_url":    RELEASES_URL,
        "changelog_url":   f"{REPO_URL}/blob/main/CHANGELOG.md",
    }


def _check_for_update():
    """Hit GitHub Releases API (cached) and return update status."""
    import time, urllib.request
    now = time.time()
    if _UPDATE_CACHE["data"] and (now - _UPDATE_CACHE["checked_at"]) < _UPDATE_CACHE_TTL:
        return _UPDATE_CACHE["data"]

    out = {
        "current":          DAEMON_VERSION,
        "latest":           None,
        "update_available": False,
        "release_url":      None,
        "release_name":     None,
        "release_notes":    None,
        "published_at":     None,
        "spk_download":     None,
        "error":            None,
        "checked_at":       int(now),
    }
    try:
        req = urllib.request.Request(
            RELEASES_API,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": f"FilamindAI/{DAEMON_VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode("utf-8"))
        latest = data.get("tag_name", "")
        out["latest"]         = latest
        out["release_url"]    = data.get("html_url")
        out["release_name"]   = data.get("name") or latest
        out["release_notes"]  = data.get("body") or ""
        out["published_at"]   = data.get("published_at")
        # First .spk asset wins
        for a in data.get("assets", []):
            if a.get("name", "").endswith(".spk"):
                out["spk_download"] = a.get("browser_download_url")
                break
        if latest and _semver_compare(latest, DAEMON_VERSION) > 0:
            out["update_available"] = True
    except Exception as e:
        out["error"] = str(e)[:200]

    _UPDATE_CACHE["data"] = out
    _UPDATE_CACHE["checked_at"] = now
    return out


def _is_safe_model_path(path):
    """A model_path is safe only if it's a real .gguf file inside one of the
    configured search dirs. Stops file-read via --model with /etc/shadow etc."""
    if not isinstance(path, str) or not path or "\0" in path: return False
    if not path.endswith(".gguf"): return False
    try:
        real = os.path.realpath(path)
    except Exception:
        return False
    if not os.path.isfile(real): return False
    for d in search_dirs(read_config()):
        try:
            base = os.path.realpath(d)
        except Exception:
            continue
        if real == base or real.startswith(base + os.sep):
            return True
    return False


def _host_resolves_to_blocked_ip(host):
    """Resolve `host` and return True if ANY resolved address is non-public.

    Uses socket.getaddrinfo so it normalises every IP-literal encoding the
    string-based check used to miss: decimal (2130706433), hex (0x7f.1),
    octal, and IPv6 literals incl. IPv4-mapped (::ffff:127.0.0.1). Fails
    CLOSED — an unresolvable host is treated as blocked."""
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return True
    _cgnat = ipaddress.ip_network("100.64.0.0/10")
    for info in infos:
        ip_str = info[4][0]
        # Strip IPv6 zone id if present (e.g. fe80::1%eth0)
        ip_str = ip_str.split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return True
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return True
        if ip.version == 4 and ip in _cgnat:
            return True
    return False


def _is_safe_download_url(url):
    """Block SSRF: refuse non-http(s) schemes and any host that resolves to a
    private / loopback / link-local / CGNAT / reserved address."""
    try:
        u = urllib.parse.urlparse(url)
    except Exception:
        return False
    if u.scheme not in ("http", "https"):
        return False
    host = u.hostname or ""
    if not host:
        return False
    return not _host_resolves_to_blocked_ip(host)


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate every redirect target against the SSRF guard before
    following it — defeats the 'public URL 302s to 169.254.169.254' bypass."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_safe_download_url(newurl):
            raise urllib.error.HTTPError(
                newurl, code, "redirect to blocked host", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Opener that validates redirects. Used by the model downloader.
SAFE_OPENER = urllib.request.build_opener(_ValidatingRedirectHandler)


def _csrf_ok(handler):
    """CSRF check for state-mutating requests.

    Bearer-authenticated API clients are exempt (no ambient cookie → no CSRF
    surface). Everyone else must carry an Origin (or Referer) whose host:port
    EXACTLY matches the Host header. Uses real URL parsing — not the old
    substring match that `https://evil/%2f%2f<host>` could defeat. Fails
    CLOSED when no Origin/Referer is present."""
    if handler.headers.get("Authorization", "").startswith("Bearer "):
        return True
    host_hdr = (handler.headers.get("Host", "") or "").strip().lower()
    if not host_hdr:
        return False

    def netloc_of(u):
        try:
            return (urllib.parse.urlparse(u).netloc or "").lower()
        except Exception:
            return ""

    origin = (handler.headers.get("Origin", "") or "").strip()
    referer = (handler.headers.get("Referer", "") or "").strip()
    if origin and origin.lower() != "null":
        return netloc_of(origin) == host_hdr
    if referer:
        return netloc_of(referer) == host_hdr
    return False


# ───── Request-size cap + login throttle ────────────────────────────────────
MAX_BODY_BYTES = 16 * 1024 * 1024   # hard cap on any JSON request body (anti-OOM)

_LOGIN_ATTEMPTS = {}                 # client_ip -> [timestamps]
_LOGIN_LOCK = threading.Lock()
_LOGIN_WINDOW = 300                  # seconds
_LOGIN_MAX = 10                      # failed-or-not attempts per window per IP


def _login_throttled(ip):
    """True if this IP has exceeded the login attempt budget in the window."""
    now = time.time()
    with _LOGIN_LOCK:
        bucket = _LOGIN_ATTEMPTS.setdefault(ip, [])
        bucket[:] = [t for t in bucket if t > now - _LOGIN_WINDOW]
        if len(bucket) >= _LOGIN_MAX:
            return True
        bucket.append(now)
        return False

# ───── Pre-built agents (seeded on first run) ───────────────────────────────
DEFAULT_AGENTS = [
    {
        "id": "chat",
        "name": "Friendly Assistant", "icon": "💬",
        "description": "Warm, conversational AI for general questions.",
        "system_prompt": "You are a helpful, friendly, and conversational AI assistant. Reply in a natural, warm tone. Be concise — usually one or two short paragraphs. Never repeat yourself or pad the answer. If the question is simple, answer in one sentence and stop.",
        "temperature": 0.6, "top_p": 0.9, "max_tokens": 400,
        "tags": "general,chat",
    },
    {
        "id": "coder",
        "name": "Code Master", "icon": "💻",
        "description": "Expert programmer. Clean, idiomatic code with concise explanations.",
        "system_prompt": "You are an expert software engineer. Write clean, idiomatic code in the requested language. Add brief comments only where non-obvious. Prefer modern best practices. When debugging, explain the root cause concisely. Always use Markdown code fences with language tags.",
        "temperature": 0.3, "top_p": 0.9, "max_tokens": 1024,
        "tags": "code,programming,debug",
    },
    {
        "id": "writer",
        "name": "Writer & Editor", "icon": "✍️",
        "description": "Drafting, editing, and polishing prose with vivid language.",
        "system_prompt": "You are an experienced writer and editor. Help with drafting, structuring, and polishing prose. Use vivid language when fitting, but keep clarity first. When asked for feedback, point to specific lines and suggest concrete improvements.",
        "temperature": 0.85, "top_p": 0.95, "max_tokens": 1024,
        "tags": "writing,editing,prose",
    },
    {
        "id": "researcher",
        "name": "Researcher", "icon": "🔬",
        "description": "Careful, step-by-step analysis. Cites reasoning openly.",
        "system_prompt": "You are a careful research assistant. Think step by step. When uncertain, say so. Cite reasoning openly. For complex questions, break them down before answering. Avoid speculation that is not clearly labeled.",
        "temperature": 0.4, "top_p": 0.9, "max_tokens": 1024,
        "tags": "research,analysis,reasoning",
    },
    {
        "id": "translator",
        "name": "Polyglot Translator", "icon": "🌐",
        "description": "Accurate translation preserving tone and intent.",
        "system_prompt": "You are a professional translator. Translate the user's text accurately. Preserve tone, formality, and intent. If the target language is not specified, ask. Provide ONLY the translation unless context is requested.",
        "temperature": 0.3, "top_p": 0.9, "max_tokens": 1024,
        "tags": "translate,language",
    },
    {
        "id": "tutor",
        "name": "Patient Tutor", "icon": "🎓",
        "description": "Explains concepts simply with examples and analogies.",
        "system_prompt": "You are a patient tutor. Explain concepts in plain language with concrete examples and analogies. Adapt to the learner's level. After each explanation, ask if anything needs clarification. Never assume prior knowledge.",
        "temperature": 0.5, "top_p": 0.9, "max_tokens": 768,
        "tags": "education,teaching",
    },
    {
        "id": "storyteller",
        "name": "Storyteller", "icon": "📖",
        "description": "Vivid narrative fiction with strong sensory detail.",
        "system_prompt": "You are a creative storyteller. Write vivid, sensory-rich fiction. Use dialogue and pacing to keep readers engaged. Build characters with specific quirks. Show, don't tell.",
        "temperature": 0.95, "top_p": 0.95, "max_tokens": 1024,
        "tags": "creative,fiction,story",
    },
    {
        "id": "email",
        "name": "Email Helper", "icon": "📧",
        "description": "Professional, friendly email drafts for any situation.",
        "system_prompt": "You write professional emails. Match the requested tone (formal, friendly, direct). Keep it concise. Start with the point, support with one or two sentences, end with a clear next step. No filler or jargon.",
        "temperature": 0.5, "top_p": 0.9, "max_tokens": 512,
        "tags": "email,professional",
    },
    {
        "id": "brainstormer",
        "name": "Brainstormer", "icon": "💡",
        "description": "Generates many diverse ideas quickly.",
        "system_prompt": "You are a brainstorming partner. When asked for ideas, give a numbered list of at least 7 diverse options. Range from safe and obvious to wild and unconventional. Each idea is one short sentence. No preamble, no caveats — just ideas.",
        "temperature": 1.0, "top_p": 0.95, "max_tokens": 768,
        "tags": "ideas,creative,ideation",
    },
    {
        "id": "summarizer",
        "name": "Summarizer", "icon": "📋",
        "description": "Compresses long text into clear bullets.",
        "system_prompt": "You compress text. Read what the user provides, then output a tight summary as bullet points. Capture the core argument, key facts, and conclusion. Do not add information that is not in the source. Stay under 200 words unless asked otherwise.",
        "temperature": 0.3, "top_p": 0.9, "max_tokens": 512,
        "tags": "summary,compress",
    },
    {
        "id": "math",
        "name": "Math & Reasoning", "icon": "🧮",
        "description": "Step-by-step problem solving with careful reasoning.",
        "system_prompt": "You are a careful mathematician. Solve problems step by step. Show every step explicitly. Verify your answer at the end. If a question is ambiguous, restate your assumptions. Use plain notation (no LaTeX commands unless the user asked).",
        "temperature": 0.2, "top_p": 0.9, "max_tokens": 1024,
        "tags": "math,logic,reasoning",
    },
    {
        "id": "marketer",
        "name": "Copywriter", "icon": "📣",
        "description": "Punchy marketing copy and product descriptions.",
        "system_prompt": "You write marketing copy. Hook, benefit, proof, call to action — in that order. Short sentences. Strong verbs. No hype words like 'revolutionary' or 'cutting-edge'. Match the user's product voice.",
        "temperature": 0.8, "top_p": 0.95, "max_tokens": 512,
        "tags": "marketing,copy,ads",
    },
]


def safe_defaults_for(model_path):
    """Pick CTX_SIZE / N_GPU_LAYERS conservatively for a 4 GB GTX 1650.
    Empirically tuned: 7B Q4 (~3.8 GB on disk) + KV cache + scratch buffer
    routinely exceeds 4 GB VRAM if all layers go to GPU. Better to keep ~30%
    on CPU and use a small context than to crash on load."""
    try:
        size_gb = os.path.getsize(model_path) / (1024 ** 3)
    except OSError:
        size_gb = 0
    if size_gb < 1.0:
        return {"CTX_SIZE": "8192", "N_GPU_LAYERS": "999"}
    if size_gb < 2.0:
        return {"CTX_SIZE": "4096", "N_GPU_LAYERS": "999"}
    if size_gb < 3.0:
        return {"CTX_SIZE": "2048", "N_GPU_LAYERS": "999"}
    if size_gb < 4.0:
        # ~3.8 GB 7B-Q4 models — partial CPU offload to leave room for KV cache
        return {"CTX_SIZE": "2048", "N_GPU_LAYERS": "24"}
    # >= 4 GB: model alone fills VRAM, offload heavily to CPU
    return {"CTX_SIZE": "1536", "N_GPU_LAYERS": "12"}

# ───── Cloud providers ──────────────────────────────────────────────────────
PROVIDERS_FILE = ETC_DIR + "/providers.json"

DEFAULT_PROVIDERS = {
    "openai": {
        "enabled": False, "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "models": [
            "gpt-5", "gpt-5-mini", "gpt-5-nano",
            "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
            "gpt-4o", "gpt-4o-mini",
            "gpt-4-turbo", "gpt-4",
            "o3", "o3-mini",
            "o1", "o1-mini",
            "gpt-3.5-turbo",
        ],
    },
    "anthropic": {
        "enabled": False, "api_key": "",
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-5-haiku-20241022",
        "models": [
            "claude-sonnet-4-5",
            "claude-opus-4-1",
            "claude-haiku-4-5",
            "claude-3-7-sonnet-latest",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ],
    },
    "gemini": {
        "enabled": False, "api_key": "",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-2.5-flash",
        "models": [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash-thinking-exp",
            "gemini-2.0-pro-exp",
            "gemini-1.5-pro",
            "gemini-1.5-pro-002",
            "gemini-1.5-flash",
            "gemini-1.5-flash-002",
            "gemini-1.5-flash-8b",
            "gemini-exp-1206",
            "learnlm-1.5-pro-experimental",
        ],
    },
}

# Mapping of deprecated provider model names → current stable equivalents.
# Used in `migrate_providers()` (one-shot on startup) and as a fallback in the
# provider adapters when a 404 comes back for a known-deprecated model.
DEPRECATED_MODELS = {
    "gemini-2.0-flash-exp": "gemini-2.5-flash",
    "gemini-pro":            "gemini-2.5-flash",
    "gemini-1.5-flash-8b":   "gemini-1.5-flash",
}

def migrate_providers():
    """Replace deprecated default_models in providers.json, and expand the
    models list with any new defaults the user is missing."""
    try:
        with open(PROVIDERS_FILE) as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return
    changed = False
    for name, p in (data or {}).items():
        if not isinstance(p, dict): continue
        cur = p.get("default_model", "")
        if cur in DEPRECATED_MODELS:
            p["default_model"] = DEPRECATED_MODELS[cur]
            changed = True
        models = p.get("models", [])
        if isinstance(models, list):
            new_models = [DEPRECATED_MODELS.get(m, m) for m in models if m]
            # Append any defaults the user is missing
            defaults = DEFAULT_PROVIDERS.get(name, {}).get("models", [])
            for m in defaults:
                if m not in new_models:
                    new_models.append(m)
            seen, deduped = set(), []
            for m in new_models:
                if m not in seen:
                    seen.add(m); deduped.append(m)
            if deduped != models:
                p["models"] = deduped
                changed = True
    if changed:
        save_providers(data)
        log("Migrated deprecated provider default models and expanded model lists")


def fetch_live_models(provider_name, p):
    """Query the provider's API for its current list of models.
    Returns a list of CHAT-capable model id strings."""
    if provider_name == "gemini":
        url = f"{p['base_url'].rstrip('/')}/models?key={urllib.parse.quote(p.get('api_key',''))}"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        # Gemini exposes many non-chat models that claim `generateContent`
        # (TTS, image generation, embeddings, audio, vision-only). Filter
        # them out — we only want plain chat models in the UI dropdown.
        NON_CHAT_SUBSTRINGS = (
            "-tts", "-audio", "image-gen", "imagen", "veo", "aqa",
            "embedding", "embed", "-vision-tuning",
        )
        out = []
        for m in data.get("models", []):
            name = (m.get("name") or "").replace("models/", "")
            methods = m.get("supportedGenerationMethods", [])
            if not name or "generateContent" not in methods:
                continue
            low = name.lower()
            if any(s in low for s in NON_CHAT_SUBSTRINGS):
                continue
            out.append(name)
        # Sort: stable 2.5 > 2.0 > 1.5 > experimental
        def sort_key(n):
            n2 = n.lower()
            score = 0
            if "2.5" in n2: score -= 30
            elif "2.0" in n2: score -= 20
            elif "1.5" in n2: score -= 10
            if "exp" in n2 or "preview" in n2 or "learnlm" in n2: score += 5
            return (score, n)
        return sorted(set(out), key=sort_key)
    if provider_name == "openai":
        req = urllib.request.Request(
            f"{p['base_url'].rstrip('/')}/models",
            headers={"Authorization": f"Bearer {p.get('api_key','')}"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        out = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            if mid and ("gpt" in mid or mid.startswith(("o1", "o3", "o4"))):
                out.append(mid)
        return sorted(set(out))
    if provider_name == "anthropic":
        req = urllib.request.Request(
            f"{p['base_url'].rstrip('/')}/models",
            headers={"x-api-key": p.get("api_key", ""), "anthropic-version": "2023-06-01"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        return sorted(set(m.get("id", "") for m in data.get("data", []) if m.get("id")))
    return []

def load_providers():
    try:
        with open(PROVIDERS_FILE) as f:
            data = json.load(f)
        for k, v in DEFAULT_PROVIDERS.items():
            if k not in data:
                data[k] = dict(v)
            else:
                for kk, vv in v.items():
                    data[k].setdefault(kk, vv)
        return data
    except FileNotFoundError:
        return {k: dict(v) for k, v in DEFAULT_PROVIDERS.items()}
    except Exception:
        return {k: dict(v) for k, v in DEFAULT_PROVIDERS.items()}

def save_providers(cfg):
    os.makedirs(ETC_DIR, exist_ok=True)
    tmp = PROVIDERS_FILE + ".tmp"
    # Tight umask while creating the tmp file so the API key never appears with
    # group/other-readable perms even briefly.
    old_umask = os.umask(0o077)
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f, indent=2)
    finally:
        os.umask(old_umask)
    os.replace(tmp, PROVIDERS_FILE)
    try: os.chmod(PROVIDERS_FILE, 0o600)
    except Exception: pass


def _safe_filename(s):
    s = re.sub(r"[^A-Za-z0-9_\-؀-ۿ]+", "_", s).strip("_")
    return s[:60] or "conversation"

def _redact_providers(cfg):
    """Strip API keys (and other secrets) before returning to the UI."""
    out = {}
    for name, p in cfg.items():
        c = dict(p)
        key = c.get("api_key") or ""
        c["api_key"] = "" if not key else ("•" * 6 + key[-4:])
        c["has_key"] = bool(key)
        out[name] = c
    return out

# ───── Provider adapters ────────────────────────────────────────────────────
def _http_json(url, body, headers, timeout=120):
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode("utf-8", "replace"))

def call_openai(p, model, messages, params):
    body = {
        "model": model,
        "messages": messages,
        "temperature": float(params.get("temperature", 0.7)),
        "max_tokens": int(params.get("max_tokens", 2048)),
    }
    if params.get("top_p") is not None: body["top_p"] = float(params["top_p"])
    raw = json.dumps(body).encode("utf-8")
    data = _http_json(p["base_url"].rstrip("/") + "/chat/completions", raw, {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {p['api_key']}",
    })
    return {
        "content": data["choices"][0]["message"]["content"],
        "model": data.get("model", model),
        "usage": data.get("usage", {}),
    }

def call_anthropic(p, model, messages, params):
    system = None
    msgs = []
    for m in messages:
        if m["role"] == "system":
            system = (system + "\n\n" + m["content"]) if system else m["content"]
        elif m["role"] in ("user", "assistant"):
            msgs.append({"role": m["role"], "content": m["content"]})
    body = {
        "model": model,
        "max_tokens": int(params.get("max_tokens", 2048)),
        "messages": msgs,
        "temperature": float(params.get("temperature", 0.7)),
    }
    if system: body["system"] = system
    if params.get("top_p") is not None: body["top_p"] = float(params["top_p"])
    raw = json.dumps(body).encode("utf-8")
    data = _http_json(p["base_url"].rstrip("/") + "/messages", raw, {
        "Content-Type": "application/json",
        "x-api-key": p["api_key"],
        "anthropic-version": "2023-06-01",
    })
    content = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            content += block.get("text", "")
    return {
        "content": content,
        "model": data.get("model", model),
        "usage": {
            "prompt_tokens":     data.get("usage", {}).get("input_tokens", 0),
            "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
        },
    }

def call_gemini(p, model, messages, params, _retry_with=None):
    contents = []
    system_instruction = None
    for m in messages:
        if m["role"] == "system":
            system_instruction = {"parts": [{"text": m["content"]}]}
        else:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
    body = {
        "contents": contents,
        "generationConfig": {
            "temperature": float(params.get("temperature", 0.7)),
            "maxOutputTokens": int(params.get("max_tokens", 2048)),
        },
    }
    if params.get("top_p") is not None: body["generationConfig"]["topP"] = float(params["top_p"])
    if system_instruction: body["systemInstruction"] = system_instruction
    try_model = _retry_with or model
    url = f"{p['base_url'].rstrip('/')}/models/{try_model}:generateContent?key={urllib.parse.quote(p['api_key'])}"
    raw = json.dumps(body).encode("utf-8")
    try:
        data = _http_json(url, raw, {"Content-Type": "application/json"})
    except urllib.error.HTTPError as e:
        # Auto-fallback for deprecated model names
        if e.code == 404 and _retry_with is None:
            fb = DEPRECATED_MODELS.get(model, "gemini-2.5-flash")
            if fb and fb != model:
                log(f"Gemini 404 for {model}, retrying with {fb}")
                return call_gemini(p, model, messages, params, _retry_with=fb)
        raise
    content = ""
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            content += part.get("text", "")
    um = data.get("usageMetadata", {})
    return {
        "content": content,
        "model": model,
        "usage": {
            "prompt_tokens":     um.get("promptTokenCount", 0),
            "completion_tokens": um.get("candidatesTokenCount", 0),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# MCP in-chat tool-calling (v1.4.0)
# ───────────────────────────────────────────────────────────────────────────
# Canonical message format throughout the loop is OpenAI's:
#   {"role": "system"|"user"|"assistant"|"tool",
#    "content": str|None,
#    "tool_calls": [{"id", "type":"function", "function":{"name","arguments"(json str)}}],  # assistant only
#    "tool_call_id": str, "name": str}                                                       # tool role only
# Each *_turn() converts to its provider's wire shape, sends ONE request, and
# returns a normalized dict:
#   {"finish": "stop"|"tool_calls", "text": str,
#    "tool_calls": [{"id","name","args"}], "model": str, "usage": dict}
# ═══════════════════════════════════════════════════════════════════════════

def _openai_turn(p, model, messages, params, tools):
    body = {
        "model": model,
        "messages": messages,
        "temperature": float(params.get("temperature", 0.7)),
        "max_tokens": int(params.get("max_tokens", 1024)),
    }
    if params.get("top_p") is not None:
        body["top_p"] = float(params["top_p"])
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    data = _http_json(p["base_url"].rstrip("/") + "/chat/completions",
                      json.dumps(body).encode("utf-8"),
                      {"Content-Type": "application/json",
                       "Authorization": f"Bearer {p['api_key']}"})
    msg = data["choices"][0]["message"]
    usage = data.get("usage", {})
    mdl = data.get("model", model)
    tcs = msg.get("tool_calls") or []
    if tcs:
        calls = []
        for tc in tcs:
            fn = tc.get("function", {})
            try:
                a = json.loads(fn.get("arguments") or "{}")
            except Exception:
                a = {}
            calls.append({"id": tc.get("id", ""), "name": fn.get("name", ""), "args": a})
        return {"finish": "tool_calls", "text": msg.get("content") or "",
                "tool_calls": calls, "assistant_msg": {
                    "role": "assistant", "content": msg.get("content"),
                    "tool_calls": tcs}, "model": mdl, "usage": usage}
    return {"finish": "stop", "text": msg.get("content") or "",
            "tool_calls": [], "model": mdl, "usage": usage}


def _anthropic_turn(p, model, messages, params, tools):
    system = None
    msgs = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system = (system + "\n\n" + m["content"]) if system else m["content"]
        elif role == "assistant" and m.get("tool_calls"):
            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                try:
                    inp = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    inp = {}
                blocks.append({"type": "tool_use", "id": tc.get("id", ""),
                               "name": fn.get("name", ""), "input": inp})
            msgs.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            # Anthropic carries tool results inside a user turn.
            tr = {"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""),
                  "content": m.get("content", "")}
            if msgs and msgs[-1]["role"] == "user" and isinstance(msgs[-1]["content"], list):
                msgs[-1]["content"].append(tr)
            else:
                msgs.append({"role": "user", "content": [tr]})
        elif role in ("user", "assistant"):
            msgs.append({"role": role, "content": m["content"]})
    body = {
        "model": model,
        "max_tokens": int(params.get("max_tokens", 1024)),
        "messages": msgs,
        "temperature": float(params.get("temperature", 0.7)),
    }
    if system:
        body["system"] = system
    if params.get("top_p") is not None:
        body["top_p"] = float(params["top_p"])
    if tools:
        body["tools"] = tools
    data = _http_json(p["base_url"].rstrip("/") + "/messages",
                      json.dumps(body).encode("utf-8"),
                      {"Content-Type": "application/json",
                       "x-api-key": p["api_key"],
                       "anthropic-version": "2023-06-01"})
    text = ""
    calls = []
    native_blocks = []
    for block in data.get("content", []):
        native_blocks.append(block)
        if block.get("type") == "text":
            text += block.get("text", "")
        elif block.get("type") == "tool_use":
            calls.append({"id": block.get("id", ""), "name": block.get("name", ""),
                          "args": block.get("input", {}) or {}})
    um = data.get("usage", {})
    usage = {"prompt_tokens": um.get("input_tokens", 0),
             "completion_tokens": um.get("output_tokens", 0)}
    mdl = data.get("model", model)
    if data.get("stop_reason") == "tool_use" and calls:
        # Re-encode the assistant turn in canonical OpenAI shape for history.
        tool_calls = [{"id": c["id"], "type": "function",
                       "function": {"name": c["name"],
                                    "arguments": json.dumps(c["args"])}} for c in calls]
        return {"finish": "tool_calls", "text": text, "tool_calls": calls,
                "assistant_msg": {"role": "assistant", "content": text or None,
                                  "tool_calls": tool_calls},
                "model": mdl, "usage": usage}
    return {"finish": "stop", "text": text, "tool_calls": [], "model": mdl, "usage": usage}


def _gemini_turn(p, model, messages, params, tools):
    contents = []
    system_instruction = None
    for m in messages:
        role = m["role"]
        if role == "system":
            system_instruction = {"parts": [{"text": m["content"]}]}
        elif role == "assistant" and m.get("tool_calls"):
            parts = []
            if m.get("content"):
                parts.append({"text": m["content"]})
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                try:
                    a = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    a = {}
                parts.append({"functionCall": {"name": fn.get("name", ""), "args": a}})
            contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            try:
                resp_obj = json.loads(m.get("content") or "{}")
            except Exception:
                resp_obj = {"result": m.get("content", "")}
            if not isinstance(resp_obj, dict):
                resp_obj = {"result": resp_obj}
            contents.append({"role": "user", "parts": [{"functionResponse": {
                "name": m.get("name", ""), "response": resp_obj}}]})
        else:
            grole = "user" if role == "user" else "model"
            contents.append({"role": grole, "parts": [{"text": m["content"]}]})
    body = {
        "contents": contents,
        "generationConfig": {
            "temperature": float(params.get("temperature", 0.7)),
            "maxOutputTokens": int(params.get("max_tokens", 1024)),
        },
    }
    if params.get("top_p") is not None:
        body["generationConfig"]["topP"] = float(params["top_p"])
    if system_instruction:
        body["systemInstruction"] = system_instruction
    if tools:
        body["tools"] = [{"function_declarations": tools}]
    url = f"{p['base_url'].rstrip('/')}/models/{model}:generateContent?key={urllib.parse.quote(p['api_key'])}"
    data = _http_json(url, json.dumps(body).encode("utf-8"),
                      {"Content-Type": "application/json"})
    text = ""
    calls = []
    raw_parts = []
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            raw_parts.append(part)
            if "text" in part:
                text += part.get("text", "")
            elif "functionCall" in part:
                fc = part["functionCall"]
                calls.append({"id": "gem_" + fc.get("name", ""), "name": fc.get("name", ""),
                              "args": fc.get("args", {}) or {}})
    um = data.get("usageMetadata", {})
    usage = {"prompt_tokens": um.get("promptTokenCount", 0),
             "completion_tokens": um.get("candidatesTokenCount", 0)}
    if calls:
        tool_calls = [{"id": c["id"], "type": "function",
                       "function": {"name": c["name"],
                                    "arguments": json.dumps(c["args"])}} for c in calls]
        return {"finish": "tool_calls", "text": text, "tool_calls": calls,
                "assistant_msg": {"role": "assistant", "content": text or None,
                                  "tool_calls": tool_calls},
                "model": model, "usage": usage}
    return {"finish": "stop", "text": text, "tool_calls": [], "model": model, "usage": usage}


def _local_turn(p, model, messages, params, tools):
    """b1620 has no native tool calling, so we emulate it via the prompt: tool
    schemas are injected into a system addendum and the model is asked to emit a
    <tool_call>{...}</tool_call> block. Best-effort — local models follow this
    far less reliably than cloud models, which is surfaced honestly in the UI."""
    msgs = [dict(m) for m in messages]
    if tools:
        spec = json.dumps([{"name": t["function"]["name"],
                            "description": t["function"]["description"],
                            "parameters": t["function"]["parameters"]}
                           for t in tools], ensure_ascii=False)
        instr = ("\n\nYou can call tools. Available tools (JSON):\n" + spec +
                 "\n\nTo call a tool, reply with ONLY this exact line and nothing else:\n"
                 "<tool_call>{\"name\": \"<tool>\", \"arguments\": {...}}</tool_call>\n"
                 "After you receive a <tool_result>, use it to answer normally.")
        if msgs and msgs[0]["role"] == "system":
            msgs[0] = {"role": "system", "content": (msgs[0]["content"] or "") + instr}
        else:
            msgs.insert(0, {"role": "system", "content": instr.strip()})
    body = {
        "stream": False,
        "messages": [{"role": m["role"] if m["role"] in ("system", "user", "assistant") else "user",
                      "content": m.get("content") or (
                          "<tool_result>" + (m.get("_tool_text") or "") + "</tool_result>"
                          if m["role"] == "tool" else "")}
                     for m in msgs],
        "temperature": float(params.get("temperature", 0.7)),
        "max_tokens": min(int(params.get("max_tokens", 512)), 1024),
        "repeat_penalty": 1.25, "repeat_last_n": 256, "min_p": 0.05,
    }
    if params.get("top_p") is not None:
        body["top_p"] = float(params["top_p"])
    req = urllib.request.Request(f"http://127.0.0.1:{INTERNAL_PORT}/v1/chat/completions",
                                 data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=600)
    j = json.loads(resp.read().decode("utf-8"))
    out = j["choices"][0]["message"].get("content") or ""
    usage = j.get("usage", {})
    mdl = j.get("model", "local")
    m = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", out, re.S)
    if tools and m:
        try:
            obj = json.loads(m.group(1))
            name = obj.get("name", "")
            args = obj.get("arguments", {}) or {}
            if name:
                tc = [{"id": "loc_" + name, "type": "function",
                       "function": {"name": name, "arguments": json.dumps(args)}}]
                return {"finish": "tool_calls", "text": out[:m.start()].strip(),
                        "tool_calls": [{"id": "loc_" + name, "name": name, "args": args}],
                        "assistant_msg": {"role": "assistant", "content": out, "tool_calls": tc},
                        "model": mdl, "usage": usage}
        except Exception:
            pass
    return {"finish": "stop", "text": out, "tool_calls": [], "model": mdl, "usage": usage}


_TURN_FN = {"openai": _openai_turn, "anthropic": _anthropic_turn,
            "gemini": _gemini_turn, "local": _local_turn}


def run_tool_loop(provider, p, model, messages, params, registry, allow,
                  user_id=None, agent_id=None, hop_limit=8):
    """Drive a multi-hop chat: call provider → if it wants tools, execute them
    via the MCP registry → feed results back → repeat until a text answer or the
    hop limit. Returns {content, model, usage, tool_trace}."""
    turn_fn = _TURN_FN.get(provider)
    if not turn_fn:
        raise ValueError(f"no turn fn for provider {provider}")
    tools = registry.tools_for_provider(provider, allow) if registry else None
    history = [dict(m) for m in messages]
    trace = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    final_model = model
    for hop in range(1, hop_limit + 1):
        r = turn_fn(p, model, history, params, tools)
        final_model = r.get("model", model)
        u = r.get("usage", {})
        total_usage["prompt_tokens"] += int(u.get("prompt_tokens", 0) or 0)
        total_usage["completion_tokens"] += int(u.get("completion_tokens", 0) or 0)
        if r["finish"] != "tool_calls" or not r["tool_calls"]:
            return {"content": r["text"], "model": final_model,
                    "usage": total_usage, "tool_trace": trace}
        # Record the assistant's tool-call turn, then execute each call.
        history.append(r["assistant_msg"])
        for call in r["tool_calls"]:
            try:
                res = registry.call(call["name"], call["args"],
                                    user_id=user_id, agent_id=agent_id, hop=hop)
                ok = res.get("ok", False)
                payload = res.get("result") if ok else {"error": res.get("error")}
            except Exception as e:
                ok = False
                payload = {"error": str(e)[:300]}
            content_str = json.dumps(payload, ensure_ascii=False, default=str)
            trace.append({"tool": call["name"], "args": call["args"],
                          "ok": ok, "result": payload})
            tool_msg = {"role": "tool", "tool_call_id": call["id"],
                        "name": call["name"], "content": content_str}
            if provider == "local":
                tool_msg["_tool_text"] = content_str
            history.append(tool_msg)
    # Hop limit hit — return whatever text we have plus a note.
    return {"content": (r.get("text") or "") +
            "\n\n_(Reached the tool-call limit of "
            f"{hop_limit} hops.)_", "model": final_model,
            "usage": total_usage, "tool_trace": trace}


def proxy(handler, path):
    target = f"http://127.0.0.1:{INTERNAL_PORT}{path}"
    cl = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(cl) if cl > 0 else None
    sanitized = False
    if body and handler.command == "POST" and path.startswith("/v1/"):
        body = _sanitize_v1_body(body)
        sanitized = True
        # Log a preview so we can debug type errors from llama.cpp
        try:
            preview = body.decode("utf-8")
            if len(preview) > 800: preview = preview[:800] + "…"
            log(f"PROXY {handler.command} {path} body=[sanitized] {preview}")
        except Exception:
            log(f"PROXY {handler.command} {path} body=[binary, {len(body)}B]")

    req = urllib.request.Request(target, data=body, method=handler.command)
    for k, v in handler.headers.items():
        if k.lower() in ("host", "connection", "content-length", "cookie",
                         "transfer-encoding", "accept-encoding"):
            continue
        req.add_header(k, v)
    if body is not None and not req.get_header("Content-type"):
        req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=600)
    except urllib.error.HTTPError as e:
        try: data = e.read()
        except Exception: data = b""
        if sanitized:
            try: log(f"PROXY error {e.code} from llama-server: {data.decode('utf-8','replace')[:400]}")
            except Exception: pass
        handler.send_response(e.code)
        for k, v in e.headers.items():
            if k.lower() in ("connection", "transfer-encoding", "content-length"): continue
            handler.send_header(k, v)
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        try: handler.wfile.write(data)
        except Exception: pass
        return
    except Exception as e:
        msg = f"Bad gateway: {e}".encode()
        handler.send_response(502)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(msg)))
        handler.end_headers()
        try: handler.wfile.write(msg)
        except Exception: pass
        return
    handler.send_response(resp.status)
    for k, v in resp.headers.items():
        if k.lower() in ("connection", "transfer-encoding", "content-length"): continue
        handler.send_header(k, v)
    handler.end_headers()
    try:
        while True:
            chunk = resp.read(2048)
            if not chunk: break
            handler.wfile.write(chunk)
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        pass


# ───── System info ──────────────────────────────────────────────────────────
def system_info():
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):     info["ram_total_mb"] = int(line.split()[1]) // 1024
                elif line.startswith("MemAvailable:"):info["ram_avail_mb"] = int(line.split()[1]) // 1024
                elif line.startswith("MemFree:"):    info["ram_free_mb"]  = int(line.split()[1]) // 1024
    except Exception: pass
    info["ram_used_mb"] = info.get("ram_total_mb", 0) - info.get("ram_avail_mb", 0)
    try:
        with open("/proc/loadavg") as f:
            info["load_1m"] = float(f.read().split()[0])
    except Exception: pass
    info["cpu_count"] = os.cpu_count() or 0
    try:
        out = subprocess.check_output(
            [NVIDIA_PKG + "/nvidia/bin/nvidia-smi",
             "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL, timeout=3
        ).decode().strip()
        parts = [p.strip() for p in out.split(",")]
        info["gpu"] = {
            "name": parts[0], "vram_used_mb": int(parts[1]), "vram_total_mb": int(parts[2]),
            "utilization": int(parts[3]), "temperature": int(parts[4]),
        }
    except Exception:
        info["gpu"] = None
    return info


# ───── HTTP handler ─────────────────────────────────────────────────────────
PUBLIC_PATHS = {
    "/login.html", "/setup.html",
    "/api/auth/login", "/api/auth/setup", "/api/auth/status",
    "/api/i18n",
}

class Handler(BaseHTTPRequestHandler):
    server_version = "FilamindAI/1.2"
    def log_message(self, fmt, *args): return

    # ---- helpers ----
    def _send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, code, text, mime="text/plain; charset=utf-8"):
        body = text.encode("utf-8") if isinstance(text, str) else text
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_redirect(self, location, set_cookie=None, clear_cookie=False):
        self.send_response(303)
        self.send_header("Location", location)
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        if clear_cookie:
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
        self.end_headers()

    def _read_body(self):
        try:
            cl = int(self.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            return {}
        if cl <= 0:
            return {}
        # Never allocate more than the cap, even if Content-Length lies big.
        raw = self.rfile.read(min(cl, MAX_BODY_BYTES)).decode("utf-8", "replace")
        if cl > MAX_BODY_BYTES:
            return {}   # oversized → treat as empty; downstream returns 400
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _get_session_user(self):
        # Cookie
        raw = self.headers.get("Cookie", "")
        if raw:
            try:
                c = SimpleCookie(); c.load(raw)
                if SESSION_COOKIE in c:
                    p = verify_session(c[SESSION_COOKIE].value)
                    if p:
                        return get_user(user_id=p.get("uid"))
            except Exception:
                pass
        # Bearer (API key)
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            key = auth[7:].strip()
            kh = hash_api_key(key)
            with db() as c:
                r = c.execute("SELECT user_id FROM api_keys WHERE key_hash=?", (kh,)).fetchone()
                if r:
                    c.execute("UPDATE api_keys SET last_used=? WHERE key_hash=?", (int(time.time()), kh))
                    return get_user(user_id=r["user_id"])
        return None

    def _require_user(self, role=None):
        u = self._get_session_user()
        if not u:
            self._send_json(401, {"error": "auth_required"})
            return None
        if role and u["role"] != role:
            self._send_json(403, {"error": "forbidden", "needed": role})
            return None
        return u

    # ---- OPTIONS ----
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    # ---- GET ----
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        # Public paths
        if path == "/api/auth/status":
            u = self._get_session_user()
            return self._send_json(200, {
                "authenticated": u is not None,
                "user": user_to_dict(u),
                "has_admin": has_admin(),
                "daemon_version": DAEMON_VERSION,
            })
        if path == "/api/version":
            return self._send_json(200, _get_version_info())
        if path == "/api/changelog":
            # Serve the shipped CHANGELOG.md as text. Falls back to GitHub raw URL note.
            md = _read_text(CHANGELOG_FILE)
            if not md:
                md = (f"# Filamind AI\n\nFull changelog: {REPO_URL}/blob/main/CHANGELOG.md\n"
                      f"(Local copy not bundled in this build.)\n")
            return self._send_text(200, md, "text/markdown; charset=utf-8")
        if path == "/api/check-update":
            return self._send_json(200, _check_for_update())
        # ─── MCP read endpoints ──────────────────────────────────────────
        if path == "/api/mcp/servers":
            u = self._require_user()
            if not u: return
            r = _get_mcp_registry()
            if r is None:
                return self._send_json(503, {"error": "mcp_unavailable", "servers": []})
            return self._send_json(200, {"servers": r.servers()})
        if path == "/api/mcp/tools":
            u = self._require_user()
            if not u: return
            r = _get_mcp_registry()
            if r is None:
                return self._send_json(503, {"error": "mcp_unavailable", "tools": []})
            return self._send_json(200, {"tools": r.list_tools()})
        if path == "/api/mcp/audit":
            u = self._require_user("admin")
            if not u: return
            r = _get_mcp_registry()
            if r is None:
                return self._send_json(503, {"error": "mcp_unavailable", "entries": []})
            return self._send_json(200, {"entries": r.recent_audit(limit=100)})
        if path == "/api/diagnose":
            u = self._require_user("admin")
            if not u: return
            return self._send_json(200, self._diagnose())
        if path == "/api/auth/me":
            u = self._require_user()
            if not u: return
            return self._send_json(200, user_to_dict(u))
        if path == "/api/i18n":
            qs = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            lang = (qs.get("lang", ["en"])[0]).split("-")[0].lower()
            if lang not in ("en", "ar"): lang = "en"
            try:
                with open(os.path.join(WEB_DIR, "i18n", f"{lang}.json")) as f:
                    return self._send_text(200, f.read(), "application/json; charset=utf-8")
            except Exception:
                return self._send_json(404, {"error": "lang_not_found"})

        # First-run redirect
        if not has_admin() and path not in ("/setup.html",) and not path.startswith("/api/auth/setup"):
            if not path.startswith("/api/") and (path.endswith(".html") or path == "/"):
                return self._send_redirect("/setup.html")

        # Login redirect
        if path == "/" or path == "/index.html":
            if self._get_session_user() is None:
                return self._send_redirect("/login.html")
            return self._serve_static("/index.html")

        if path in ("/admin.html", "/profile.html"):
            u = self._get_session_user()
            if not u: return self._send_redirect("/login.html")
            if path == "/admin.html" and u["role"] != "admin":
                return self._send_redirect("/index.html")

        # Auth-required API endpoints
        if path.startswith("/api/"):
            return self._handle_api_get(path)

        # llama.cpp introspection endpoints leak engine internals — /slots in
        # particular exposes other users' in-flight prompts/completions on the
        # shared single-process engine. Restrict to admins.
        if path in ("/slots", "/metrics", "/props"):
            if not self._require_user("admin"): return
            return proxy(self, self.path)
        # Proxy (chat-facing): any authenticated user
        if path.startswith("/v1/") or path in ("/health", "/completion"):
            if self._get_session_user() is None:
                return self._send_json(401, {"error": "auth_required"})
            return proxy(self, self.path)

        return self._serve_static(path)

    def _handle_api_get(self, path):
        if path == "/api/config":
            if not self._require_user("admin"): return
            return self._send_json(200, read_config())
        if path == "/api/models":
            if not self._require_user(): return
            return self._send_json(200, {"models": list_models(read_config()), "current": STATE["current_model"], "search_dirs": search_dirs(read_config())})
        if path == "/api/status":
            if not self._require_user(): return
            p = STATE["llama_proc"]
            running = p is not None and p.poll() is None
            return self._send_json(200, {
                "running": running,
                "model": STATE["current_model"],
                "pid": (p.pid if p else 0),
                "uptime_s": int(time.time() - STATE["last_start_ts"]) if STATE["last_start_ts"] else 0,
                "load_state": STATE.get("load_state", "idle"),
                "load_error": STATE.get("load_error", ""),
                "failures":   {k: {"count": v.get("count", 0), "reason": v.get("reason", ""), "kind": v.get("kind", "")}
                               for k, v in STATE.get("model_failures", {}).items()},
            })
        if path == "/api/system":
            if not self._require_user(): return
            return self._send_json(200, system_info())
        if path == "/api/log":
            if not self._require_user("admin"): return
            try:
                with open(LOG_FILE, "rb") as f:
                    f.seek(0, 2); sz = f.tell()
                    f.seek(max(0, sz - 16000)); data = f.read()
                return self._send_text(200, data, "text/plain; charset=utf-8")
            except Exception as e:
                return self._send_json(500, {"error": str(e)})
        if path == "/api/users":
            if not self._require_user("admin"): return
            with db() as c:
                rows = c.execute("SELECT * FROM users ORDER BY id").fetchall()
                return self._send_json(200, {"users": [user_to_dict(r) for r in rows]})
        if path == "/api/api-keys":
            u = self._require_user()
            if not u: return
            with db() as c:
                rows = c.execute("SELECT id, name, prefix, created_at, last_used FROM api_keys WHERE user_id=? ORDER BY id DESC", (u["id"],)).fetchall()
                return self._send_json(200, {"keys": [dict(r) for r in rows]})
        if path == "/api/catalog":
            if not self._require_user(): return
            return self._send_json(200, {"models": MODEL_CATALOG})
        if path == "/api/agents":
            if not self._require_user(): return
            return self._send_json(200, {"agents": list_agents()})
        if path.startswith("/api/agents/"):
            if not self._require_user(): return
            aid = path.rsplit("/", 1)[1]
            a = get_agent(aid)
            if not a: return self.send_error(404)
            return self._send_json(200, a)
        if path == "/api/providers":
            u = self._require_user()
            if not u: return
            providers = load_providers()
            if u["role"] == "admin":
                # Admins see config (keys redacted) so they can manage settings
                return self._send_json(200, {"providers": _redact_providers(providers)})
            # Regular users only see which providers are enabled + the model lists
            slim = {}
            for name, p in providers.items():
                slim[name] = {"enabled": p.get("enabled", False),
                              "default_model": p.get("default_model", ""),
                              "models": p.get("models", []),
                              "has_key": bool(p.get("api_key"))}
            return self._send_json(200, {"providers": slim})
        if path == "/api/downloads":
            if not self._require_user(): return
            with STATE["downloads_lock"]:
                items = list(STATE["downloads"].values())
            for it in items:
                t = it.get("total", 0) or 0
                r = it.get("received", 0) or 0
                it["progress"] = round(r * 100.0 / t, 1) if t > 0 else 0.0
            return self._send_json(200, {"downloads": items})
        return self.send_error(404)

    # ---- POST ----
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        # ── Centralized CSRF gate ──────────────────────────────────────────
        # Every mutating POST must be same-origin (or Bearer-authed). This
        # closes the gaps where individual endpoints (/api/users, /api/login,
        # /api/config, /api/profile, /api/mcp/*) forgot to call _csrf_ok.
        if not _csrf_ok(self):
            return self._send_json(403, {"error": "csrf_blocked"})
        # Auth endpoints
        if path == "/api/auth/setup":
            return self._auth_setup()
        if path == "/api/auth/login":
            return self._auth_login()
        if path == "/api/auth/logout":
            return self._auth_logout()
        if path == "/api/auth/change-password":
            return self._auth_change_password()

        # Profile
        if path == "/api/profile":
            return self._update_profile()

        # Admin user mgmt
        if path == "/api/users":
            return self._create_user_api()

        # Resources
        if path == "/api/config":
            if not self._require_user("admin"): return
            data = self._read_body()
            cfg = read_config()
            for k, v in data.items():
                if k in DEFAULT_CFG:
                    cfg[k] = str(v)
            write_config(cfg)
            STATE["request_restart"] = True
            return self._send_json(200, {"ok": True, "restart_pending": True})
        if path == "/api/restart":
            if not self._require_user("admin"): return
            STATE["request_restart"] = True
            return self._send_json(200, {"ok": True})

        # ─── MCP write/call endpoints ────────────────────────────────────
        # Toggle a server: POST /api/mcp/servers/<name>/toggle  body {"enabled": true|false}
        if path.startswith("/api/mcp/servers/") and path.endswith("/toggle"):
            u = self._require_user("admin")
            if not u: return
            name = path[len("/api/mcp/servers/"):-len("/toggle")]
            r = _get_mcp_registry()
            if r is None:
                return self._send_json(503, {"error": "mcp_unavailable"})
            data = self._read_body() or {}
            try:
                r.set_enabled(name, bool(data.get("enabled", True)))
                return self._send_json(200, {"ok": True, "name": name, "enabled": bool(data.get("enabled", True))})
            except Exception as e:
                return self._send_json(400, {"error": str(e)[:200]})

        # Call a tool: POST /api/mcp/call  body {"tool": "...", "args": {...}}
        if path == "/api/mcp/call":
            user = self._require_user()
            if not user: return
            r = _get_mcp_registry()
            if r is None:
                return self._send_json(503, {"error": "mcp_unavailable"})
            data = self._read_body() or {}
            tool_name = (data.get("tool") or "").strip()
            args      = data.get("args") or {}
            if not tool_name:
                return self._send_json(400, {"error": "tool name required"})
            try:
                out = r.call(tool_name, args, user_id=user["id"])
                status = 200 if out.get("ok") else 400
                return self._send_json(status, out)
            except Exception as e:
                # rate-limit / hop-limit / tool-not-found → 400 with message
                return self._send_json(400, {"ok": False, "error": str(e)[:200], "type": type(e).__name__})
        if path == "/api/select-model":
            if not self._require_user("admin"): return
            if not _csrf_ok(self): return self._send_json(403, {"error": "csrf_blocked"})
            data = self._read_body()
            mp = data.get("path")
            if not _is_safe_model_path(mp):
                return self._send_json(400, {"error": "model_not_found_or_unsafe"})
            cfg = read_config()
            cfg["MODEL_PATH"] = mp
            applied = {}
            if not data.get("keep_resources"):
                defaults = safe_defaults_for(mp)
                cfg.update(defaults)
                applied = defaults
            write_config(cfg)
            # Reset failure counter for this model — explicit user retry
            STATE["model_failures"].pop(mp, None)
            STATE["load_state"] = "loading"
            STATE["load_error"] = ""
            STATE["request_restart"] = True
            return self._send_json(200, {"ok": True, "model": mp, "applied_defaults": applied})
        if path == "/api/safe-defaults":
            if not self._require_user("admin"): return
            cfg = read_config()
            mp = cfg.get("MODEL_PATH") or STATE.get("current_model") or ""
            if not mp:
                return self._send_json(400, {"error": "no_model"})
            defaults = safe_defaults_for(mp)
            cfg.update(defaults)
            write_config(cfg)
            STATE["request_restart"] = True
            return self._send_json(200, {"ok": True, "applied": defaults})
        if path == "/api/clear-failure":
            if not self._require_user("admin"): return
            d = self._read_body()
            mp = (d.get("model") or "").strip()
            if mp:
                STATE["model_failures"].pop(mp, None)
            else:
                STATE["model_failures"].clear()
            STATE["load_state"] = "idle"; STATE["load_error"] = ""
            return self._send_json(200, {"ok": True})

        # API keys
        if path == "/api/api-keys":
            return self._create_api_key()
        # Refresh provider model list from the upstream API (admin only)
        if path.startswith("/api/providers/") and path.endswith("/refresh-models"):
            if not self._require_user("admin"): return
            if not _csrf_ok(self): return self._send_json(403, {"error": "csrf_blocked"})
            name = path.split("/")[3]
            providers = load_providers()
            p = providers.get(name)
            if not p:
                return self._send_json(404, {"error": "unknown_provider"})
            if not p.get("api_key"):
                return self._send_json(400, {"error": "api_key_missing"})
            try:
                live = fetch_live_models(name, p)
            except urllib.error.HTTPError as e:
                try: err = e.read().decode("utf-8", "replace")
                except Exception: err = ""
                return self._send_json(502, {"error": f"{name}_http_{e.code}", "detail": err[:300]})
            except Exception as e:
                return self._send_json(500, {"error": str(e)})
            if live:
                providers[name]["models"] = live
                save_providers(providers)
            return self._send_json(200, {"ok": True, "count": len(live), "models": live})

        # Providers config (admin only)
        if path == "/api/providers":
            if not self._require_user("admin"): return
            d = self._read_body()
            providers = load_providers()
            for name in ("openai", "anthropic", "gemini"):
                if name not in d: continue
                update = d[name] or {}
                if "enabled" in update:       providers[name]["enabled"]       = bool(update["enabled"])
                # Empty string from UI → keep existing key. Real value → replace.
                if update.get("api_key"):     providers[name]["api_key"]       = str(update["api_key"]).strip()
                if update.get("base_url"):    providers[name]["base_url"]      = str(update["base_url"]).strip()
                if update.get("default_model"): providers[name]["default_model"] = str(update["default_model"]).strip()
                if isinstance(update.get("models"), list):
                    providers[name]["models"] = [str(x).strip() for x in update["models"] if str(x).strip()]
            save_providers(providers)
            return self._send_json(200, {"ok": True})

        # Unified chat endpoint with provider routing
        if path == "/api/chat":
            return self._chat_router()
        # Agents CRUD
        if path == "/api/agents":
            u = self._require_user()
            if not u: return
            if not _csrf_ok(self): return self._send_json(403, {"error": "csrf_blocked"})
            d = self._read_body()
            aid  = (d.get("id") or "").strip().lower().replace(" ", "_")
            name = (d.get("name") or "").strip()
            if not aid or not name:
                return self._send_json(400, {"error": "name_and_id_required"})
            if not re.match(r"^[a-z0-9_\-]+$", aid):
                return self._send_json(400, {"error": "invalid_id"})
            # Only admins can pin a custom model_path (it controls llama-server's
            # --model flag and so is effectively a file-read primitive).
            model_path = d.get("model_path") or None
            if model_path and u["role"] != "admin":
                return self._send_json(403, {"error": "model_path_admin_only"})
            if model_path and not _is_safe_model_path(model_path):
                return self._send_json(400, {"error": "unsafe_model_path"})
            now = int(time.time())
            try:
                with DB_LOCK, db() as c:
                    c.execute("""INSERT INTO agents
                        (id, name, icon, description, system_prompt, model_path,
                         temperature, top_p, top_k, max_tokens, tags, is_builtin,
                         created_by, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
                        (aid, name, d.get("icon","🤖"), d.get("description",""),
                         d.get("system_prompt",""), model_path,
                         float(d.get("temperature", 0.7)), float(d.get("top_p", 0.95)),
                         int(d.get("top_k", 40)), int(d.get("max_tokens", 512)),
                         ",".join(d.get("tags") or []) if isinstance(d.get("tags"), list) else (d.get("tags","")),
                         u["id"], now, now))
            except sqlite3.IntegrityError:
                return self._send_json(400, {"error": "id_exists"})
            return self._send_json(200, {"ok": True, "agent": get_agent(aid)})

        # Conversation export — stateless, requires CSRF
        if path == "/api/export-conv":
            if not self._require_user(): return
            if not _csrf_ok(self): return self._send_json(403, {"error": "csrf_blocked"})
            d = self._read_body()
            fmt = (d.get("format") or "markdown").lower()
            title = (d.get("title") or "Conversation").strip()
            messages = d.get("messages") or []
            if fmt == "json":
                body = json.dumps({"title": title, "messages": messages,
                                   "exported_at": int(time.time())}, ensure_ascii=False, indent=2)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Disposition",
                    f'attachment; filename="{_safe_filename(title)}.json"')
                self.send_header("Content-Length", str(len(body.encode("utf-8"))))
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))
                return
            # default: markdown
            lines = [f"# {title}", ""]
            for m in messages:
                if not isinstance(m, dict): continue
                role = m.get("role", "")
                content = m.get("content", "")
                if role == "system":
                    lines.append(f"_(System: {content})_")
                else:
                    name = "**You**" if role == "user" else "**Assistant**"
                    lines.append(f"### {name}")
                    lines.append("")
                    lines.append(str(content))
                lines.append("")
            body = "\n".join(lines)
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Disposition",
                f'attachment; filename="{_safe_filename(title)}.md"')
            self.send_header("Content-Length", str(len(body.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return

        # Model download (admin only)
        if path == "/api/download-model":
            if not self._require_user("admin"): return
            if not _csrf_ok(self): return self._send_json(403, {"error": "csrf_blocked"})
            d = self._read_body()
            url = (d.get("url") or "").strip()
            name = (d.get("name") or "").strip()
            if not _is_safe_download_url(url):
                return self._send_json(400, {"error": "invalid_or_unsafe_url"})
            if not name or "/" in name or ".." in name:
                # derive a sane name from the URL
                name = (url.rsplit("/", 1)[-1]).split("?")[0]
            if not name.endswith(".gguf"):
                name += ".gguf"
            did = start_download(url, name)
            return self._send_json(200, {"id": did, "status": "starting"})

        # Proxy /v1
        if path.startswith("/v1/") or path == "/completion":
            if self._get_session_user() is None:
                return self._send_json(401, {"error": "auth_required"})
            return proxy(self, self.path)

        return self.send_error(404)

    # ---- DELETE ----
    def do_DELETE(self):
        path = self.path.split("?", 1)[0]
        if not _csrf_ok(self):
            return self._send_json(403, {"error": "csrf_blocked"})
        if path.startswith("/api/users/"):
            if not self._require_user("admin"): return
            uid = int(path.rsplit("/", 1)[1])
            with DB_LOCK, db() as c:
                # don't allow deleting the last admin
                r = c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()
                u = c.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
                if u and u["role"] == "admin" and r[0] <= 1:
                    return self._send_json(400, {"error": "cannot_delete_last_admin"})
                c.execute("DELETE FROM users WHERE id=?", (uid,))
            return self._send_json(200, {"ok": True})
        if path.startswith("/api/api-keys/"):
            u = self._require_user()
            if not u: return
            kid = int(path.rsplit("/", 1)[1])
            with DB_LOCK, db() as c:
                c.execute("DELETE FROM api_keys WHERE id=? AND user_id=?", (kid, u["id"]))
            return self._send_json(200, {"ok": True})
        if path.startswith("/api/downloads/"):
            if not self._require_user("admin"): return
            did = path.rsplit("/", 1)[1]
            with STATE["downloads_lock"]:
                if did in STATE["downloads"]:
                    STATE["downloads"][did]["cancel"] = True
                    if STATE["downloads"][did]["status"] not in ("running", "starting"):
                        del STATE["downloads"][did]
            return self._send_json(200, {"ok": True})
        if path.startswith("/api/agents/"):
            u = self._require_user()
            if not u: return
            if not _csrf_ok(self): return self._send_json(403, {"error": "csrf_blocked"})
            aid = path.rsplit("/", 1)[1]
            a = get_agent(aid)
            if not a: return self._send_json(404, {"error": "not_found"})
            if a["is_builtin"]:
                return self._send_json(400, {"error": "builtin_protected"})
            with DB_LOCK, db() as c:
                c.execute("DELETE FROM agents WHERE id=?", (aid,))
            return self._send_json(200, {"ok": True})
        return self.send_error(404)

    def do_PUT(self):
        path = self.path.split("?", 1)[0]
        if not _csrf_ok(self):
            return self._send_json(403, {"error": "csrf_blocked"})
        if path.startswith("/api/agents/"):
            u = self._require_user()
            if not u: return
            if not _csrf_ok(self): return self._send_json(403, {"error": "csrf_blocked"})
            aid = path.rsplit("/", 1)[1]
            a = get_agent(aid)
            if not a: return self._send_json(404, {"error": "not_found"})
            # Built-ins are admin-only; user-created agents are owner-or-admin
            if a["is_builtin"] and u["role"] != "admin":
                return self._send_json(403, {"error": "builtin_admin_only"})
            d = self._read_body()
            # model_path is admin-only and must point to a known GGUF
            if "model_path" in d and d["model_path"]:
                if u["role"] != "admin":
                    return self._send_json(403, {"error": "model_path_admin_only"})
                if not _is_safe_model_path(d["model_path"]):
                    return self._send_json(400, {"error": "unsafe_model_path"})
            fields = {}
            for k in ("name", "icon", "description", "system_prompt", "model_path"):
                if k in d and isinstance(d[k], str):
                    fields[k] = d[k]
            for k in ("temperature", "top_p"):
                if k in d:
                    try: fields[k] = float(d[k])
                    except Exception: pass
            for k in ("top_k", "max_tokens"):
                if k in d:
                    try: fields[k] = int(d[k])
                    except Exception: pass
            if "tags" in d:
                if isinstance(d["tags"], list):
                    fields["tags"] = ",".join(d["tags"])
                elif isinstance(d["tags"], str):
                    fields["tags"] = d["tags"]
            if not fields:
                return self._send_json(400, {"error": "no_fields"})
            fields["updated_at"] = int(time.time())
            sets = ", ".join(f"{k}=?" for k in fields)
            with DB_LOCK, db() as c:
                c.execute(f"UPDATE agents SET {sets} WHERE id=?", (*fields.values(), aid))
            return self._send_json(200, {"ok": True, "agent": get_agent(aid)})
        return self.send_error(404)

    # ---- Auth handlers ----
    def _auth_setup(self):
        d = self._read_body()
        username = (d.get("username") or "").strip()
        password = d.get("password") or ""
        display  = d.get("display_name") or username
        if len(username) < 3 or len(password) < 6:
            return self._send_json(400, {"error": "invalid_credentials", "msg": "Username ≥3 chars, password ≥6 chars."})
        # Race-safe admin creation: take DB-level lock so two concurrent setups
        # can't both succeed.
        salt, h = hash_password(password)
        now = int(time.time())
        try:
            with DB_LOCK, db() as c:
                c.execute("BEGIN IMMEDIATE")
                r = c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()
                if r[0] > 0:
                    return self._send_json(400, {"error": "already_setup"})
                cur = c.execute(
                    "INSERT INTO users (username, password_hash, salt, role, display_name, created_at) "
                    "VALUES (?, ?, ?, 'admin', ?, ?)",
                    (username, h, salt, display, now))
                uid = cur.lastrowid
        except sqlite3.IntegrityError:
            return self._send_json(400, {"error": "username_taken"})
        token = sign_session({"uid": uid, "exp": int(time.time() + SESSION_TTL)})
        cookie = f"{SESSION_COOKIE}={token}; Path=/; Max-Age={SESSION_TTL}; HttpOnly; SameSite=Lax"
        body = json.dumps({"ok": True, "user": user_to_dict(get_user(user_id=uid))}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _auth_login(self):
        ip = self.client_address[0] if self.client_address else "?"
        if _login_throttled(ip):
            return self._send_json(429, {"error": "too_many_attempts",
                                         "hint": "Wait a few minutes before trying again."})
        d = self._read_body()
        username = (d.get("username") or "").strip()
        password = d.get("password") or ""
        u = get_user(username=username)
        # Always run a password hash so a missing user takes the same time as a
        # wrong password — closes the username-enumeration timing oracle.
        if not u:
            hash_password(password)   # burn equivalent PBKDF2 time, discard
            return self._send_json(401, {"error": "bad_credentials"})
        if not verify_password(password, u["salt"], u["password_hash"]):
            return self._send_json(401, {"error": "bad_credentials"})
        with DB_LOCK, db() as c:
            c.execute("UPDATE users SET last_login=? WHERE id=?", (int(time.time()), u["id"]))
        token = sign_session({"uid": u["id"], "exp": int(time.time() + SESSION_TTL)})
        cookie = f"{SESSION_COOKIE}={token}; Path=/; Max-Age={SESSION_TTL}; HttpOnly; SameSite=Lax"
        body = json.dumps({"ok": True, "user": user_to_dict(u)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _auth_logout(self):
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
        self.end_headers()
        self.wfile.write(body)

    def _auth_change_password(self):
        u = self._require_user()
        if not u: return
        d = self._read_body()
        old = d.get("old_password") or ""
        new = d.get("new_password") or ""
        if len(new) < 6:
            return self._send_json(400, {"error": "weak_password"})
        if not verify_password(old, u["salt"], u["password_hash"]):
            return self._send_json(401, {"error": "wrong_old_password"})
        salt, h = hash_password(new)
        with DB_LOCK, db() as c:
            c.execute("UPDATE users SET salt=?, password_hash=? WHERE id=?", (salt, h, u["id"]))
        return self._send_json(200, {"ok": True})

    def _update_profile(self):
        u = self._require_user()
        if not u: return
        d = self._read_body()
        fields = {}
        for k in ("display_name", "language", "theme"):
            if k in d and isinstance(d[k], str):
                fields[k] = d[k][:120]
        if not fields:
            return self._send_json(400, {"error": "no_fields"})
        sets = ", ".join(f"{k}=?" for k in fields)
        with DB_LOCK, db() as c:
            c.execute(f"UPDATE users SET {sets} WHERE id=?", (*fields.values(), u["id"]))
        return self._send_json(200, {"ok": True})

    def _create_user_api(self):
        if not self._require_user("admin"): return
        d = self._read_body()
        username = (d.get("username") or "").strip()
        password = d.get("password") or ""
        role     = d.get("role") if d.get("role") in ("admin", "user") else "user"
        display  = d.get("display_name") or username
        if len(username) < 3 or len(password) < 6:
            return self._send_json(400, {"error": "invalid_credentials"})
        try:
            uid = create_user(username, password, role=role, display_name=display)
        except sqlite3.IntegrityError:
            return self._send_json(400, {"error": "username_taken"})
        return self._send_json(200, {"ok": True, "user": user_to_dict(get_user(user_id=uid))})

    def _create_api_key(self):
        u = self._require_user()
        if not u: return
        d = self._read_body()
        name = (d.get("name") or "").strip()[:60] or f"key-{int(time.time())}"
        full, kh, prefix = generate_api_key()
        now = int(time.time())
        with DB_LOCK, db() as c:
            cur = c.execute("INSERT INTO api_keys (user_id, name, key_hash, prefix, created_at) VALUES (?, ?, ?, ?, ?)",
                            (u["id"], name, kh, prefix, now))
            kid = cur.lastrowid
        return self._send_json(200, {"id": kid, "name": name, "key": full, "prefix": prefix, "created_at": now})

    def _chat_router(self):
        """Unified chat endpoint. Routes between local llama-server and cloud APIs.
        If `agent_id` is supplied, the agent's system_prompt + sampling defaults
        + preferred model are applied (user-supplied params still override)."""
        u = self._require_user()
        if not u: return
        d = self._read_body()
        provider = (d.get("provider") or "local").lower()
        messages = d.get("messages") or []
        if not isinstance(messages, list) or not messages:
            return self._send_json(400, {"error": "no_messages"})
        clean = []
        for m in messages:
            if isinstance(m, dict) and isinstance(m.get("role"), str) and isinstance(m.get("content"), str):
                if m["role"] in ("system", "user", "assistant"):
                    clean.append({"role": m["role"], "content": m["content"]})
        if not clean:
            return self._send_json(400, {"error": "no_valid_messages"})

        # Apply agent
        agent = None
        if d.get("agent_id"):
            agent = get_agent(d["agent_id"])
        if agent:
            # Inject the agent's system prompt only if the caller didn't already
            if not any(m["role"] == "system" for m in clean):
                clean.insert(0, {"role": "system", "content": agent["system_prompt"]})
            # If the agent pins a specific local model, switch to it (admin-style)
            if provider == "local" and agent.get("model_path") and os.path.isfile(agent["model_path"]):
                cur_cfg = read_config()
                if cur_cfg.get("MODEL_PATH") != agent["model_path"]:
                    cur_cfg["MODEL_PATH"] = agent["model_path"]
                    cur_cfg.update(safe_defaults_for(agent["model_path"]))
                    write_config(cur_cfg)
                    STATE["request_restart"] = True

        # Sampling defaults: caller > agent > engine defaults
        params = {
            "temperature": d.get("temperature", (agent or {}).get("temperature", 0.7)),
            "max_tokens":  d.get("max_tokens",  (agent or {}).get("max_tokens", 512)),
            "top_p":       d.get("top_p")       if d.get("top_p") is not None else (agent or {}).get("top_p"),
        }
        model = (d.get("model") or "").strip()

        try:
            # ─── MCP in-chat tool-calling (v1.4.0) ───────────────────────
            # When the UI/agent enables tools, drive the multi-hop tool loop
            # for whichever provider is active. Falls through to the plain
            # single-shot paths below when tools are off.
            if d.get("use_tools"):
                registry = _get_mcp_registry()
                if registry is not None:
                    allow = agent.get("tools") if (agent and agent.get("tools")) else None
                    if provider == "local":
                        if STATE.get("load_state") == "failed" and STATE.get("load_error"):
                            return self._send_json(503, {"error": "model_load_failed",
                                "detail": STATE["load_error"], "model": STATE.get("current_model", "")})
                        pp, use_model = {}, "local"
                    else:
                        providers = load_providers()
                        pp = providers.get(provider)
                        if not pp:
                            return self._send_json(400, {"error": "unknown_provider", "provider": provider})
                        if not pp.get("enabled"):
                            return self._send_json(400, {"error": "provider_disabled", "provider": provider})
                        if not pp.get("api_key"):
                            return self._send_json(400, {"error": "api_key_missing", "provider": provider})
                        use_model = model or pp.get("default_model", "")
                    out = run_tool_loop(provider, pp, use_model, clean, params, registry,
                                        allow, user_id=u["id"])
                    return self._send_json(200, {
                        "content":  out["content"],
                        "model":    out["model"],
                        "usage":    out["usage"],
                        "provider": provider,
                        "tool_trace": out["tool_trace"],
                    })

            if provider == "local":
                # If the engine is in a known-failed state, fail fast instead of
                # timing out — and tell the user why.
                if STATE.get("load_state") == "failed" and STATE.get("load_error"):
                    return self._send_json(503, {
                        "error": "model_load_failed",
                        "detail": STATE["load_error"],
                        "model": STATE.get("current_model", ""),
                    })
                # Reduce repetition with stronger penalty defaults
                body_dict = {
                    "stream": False,
                    "messages": clean,
                    "temperature": float(params["temperature"]),
                    "max_tokens": min(int(params["max_tokens"]), 1024),
                    "repeat_penalty": 1.25,
                    "repeat_last_n": 256,
                    "min_p": 0.05,
                }
                if params.get("top_p") is not None:
                    body_dict["top_p"] = float(params["top_p"])
                body_bytes = json.dumps(body_dict).encode("utf-8")
                last_err_body = b""
                for attempt in range(5):
                    try:
                        req = urllib.request.Request(
                            f"http://127.0.0.1:{INTERNAL_PORT}/v1/chat/completions",
                            data=body_bytes, method="POST",
                            headers={"Content-Type": "application/json"})
                        resp = urllib.request.urlopen(req, timeout=600)
                        j = json.loads(resp.read().decode("utf-8"))
                        return self._send_json(200, {
                            "content": j["choices"][0]["message"]["content"],
                            "model":   j.get("model", "local"),
                            "usage":   j.get("usage", {}),
                            "provider": "local",
                        })
                    except urllib.error.HTTPError as e:
                        try: last_err_body = e.read()
                        except Exception: last_err_body = b""
                        msg = last_err_body.decode("utf-8", "replace")
                        if e.code == 500 and "slot" in msg.lower():
                            time.sleep(1.5)
                            continue
                        return self._send_json(e.code, {"error": "llama_error", "detail": msg[:500]})
                # exhausted retries
                return self._send_json(503, {"error": "slot_busy",
                    "detail": "The model engine is still processing a previous request. Please wait a few seconds and try again."})

            providers = load_providers()
            p = providers.get(provider)
            if not p:
                return self._send_json(400, {"error": "unknown_provider", "provider": provider})
            if not p.get("enabled"):
                return self._send_json(400, {"error": "provider_disabled", "provider": provider})
            if not p.get("api_key"):
                return self._send_json(400, {"error": "api_key_missing", "provider": provider})

            use_model = model or p.get("default_model", "")
            if provider == "openai":
                result = call_openai(p, use_model, clean, params)
            elif provider == "anthropic":
                result = call_anthropic(p, use_model, clean, params)
            elif provider == "gemini":
                result = call_gemini(p, use_model, clean, params)
            else:
                return self._send_json(400, {"error": "unsupported_provider"})

            return self._send_json(200, {
                "content": result["content"],
                "model":   result["model"],
                "usage":   result["usage"],
                "provider": provider,
            })
        except urllib.error.HTTPError as e:
            try: err = e.read().decode("utf-8", "replace")
            except Exception: err = ""
            log(f"chat_router {provider} HTTP {e.code}: {err[:300]}")
            hint = ""
            if e.code == 429:
                hint = ("Rate limit / daily quota exceeded for your API key. "
                        "Free Gemini keys are throttled (e.g. ~10 RPM, 50–250 RPD depending on model). "
                        "Wait ~1 hour, switch to gemini-2.5-flash-lite (higher free quota), "
                        "or enable billing in Google AI Studio. "
                        "For OpenAI/Anthropic: add credits to your account.")
            elif e.code == 400 and "multiturn" in err.lower():
                hint = ("The selected Gemini model is a non-chat model (likely TTS/audio/image generation). "
                        "Open Settings → Providers and pick a model whose name does NOT contain 'tts', "
                        "'image', 'audio', or 'embedding' — e.g. gemini-2.5-flash, gemini-2.5-pro, gemini-1.5-flash.")
            elif e.code == 401 or e.code == 403:
                hint = "API key is missing, invalid, or doesn't have access to this model. Re-check the key in Settings → Providers."
            return self._send_json(502, {"error": f"{provider}_http_{e.code}",
                                          "detail": err[:500], "hint": hint})
        except Exception as e:
            log(f"chat_router {provider} error: {e}")
            return self._send_json(500, {"error": str(e), "provider": provider})

    def _diagnose(self):
        """Send a known-good minimal request to llama-server and report what happened.
        Waits a bit if the server seems to be starting up."""
        result = {"daemon_version": DAEMON_VERSION, "internal_port": INTERNAL_PORT,
                  "model": STATE["current_model"]}
        p = STATE["llama_proc"]
        result["llama_running"] = (p is not None and p.poll() is None)
        result["llama_pid"]     = p.pid if p else 0

        # Recent crash info if process died
        if p and p.poll() is not None:
            result["llama_exit_code"] = p.returncode

        body = json.dumps({
            "stream": False,
            "messages": [{"role": "user", "content": "Reply with the single word OK."}],
            "max_tokens": 5,
            "temperature": 0.1,
        }).encode("utf-8")

        last_err = "unknown"
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{INTERNAL_PORT}/v1/chat/completions",
                    data=body, method="POST",
                    headers={"Content-Type": "application/json"})
                resp = urllib.request.urlopen(req, timeout=60)
                content = resp.read().decode("utf-8", "replace")
                result["test"] = {"status": resp.status, "body": content[:500],
                                  "attempts": attempt + 1}
                break
            except urllib.error.HTTPError as e:
                try: txt = e.read().decode("utf-8", "replace")
                except Exception: txt = ""
                result["test"] = {"status": e.code, "body": txt[:500], "attempts": attempt + 1}
                break
            except Exception as e:
                last_err = str(e)
                time.sleep(3)
        else:
            result["test"] = {"status": "exception", "body": last_err, "attempts": 3,
                              "hint": "Server is not accepting connections. Model may be still loading or crashed during load."}

        # Tail of llama-server log to help diagnose load failures (OOM etc.)
        try:
            with open(LOG_FILE, "rb") as f:
                f.seek(0, 2); sz = f.tell()
                f.seek(max(0, sz - 4000))
                tail = f.read().decode("utf-8", "replace")
            result["recent_log"] = tail[-3500:]
        except Exception:
            pass
        return result

    # ---- Static ----
    def _serve_static(self, path):
        if path == "/" or path == "":
            path = "/index.html"
        if ".." in path:
            return self.send_error(403)
        full = WEB_DIR + path
        if not os.path.isfile(full):
            return self.send_error(404)
        mime = "application/octet-stream"
        for ext, m in [
            (".html","text/html; charset=utf-8"), (".js","application/javascript; charset=utf-8"),
            (".css","text/css; charset=utf-8"), (".json","application/json; charset=utf-8"),
            (".png","image/png"), (".svg","image/svg+xml"), (".ico","image/x-icon"),
            (".txt","text/plain; charset=utf-8"),
        ]:
            if full.endswith(ext): mime = m; break
        try:
            with open(full, "rb") as f: data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, str(e))


class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ───── Main ─────────────────────────────────────────────────────────────────
def _force_safe_settings_on_startup(cfg):
    """If the existing config would clearly OOM on the currently-discovered
    model, force-rewrite the config with safe defaults before we ever start
    llama-server. This rescues users whose config was saved by an older
    daemon version with aggressive ctx/layers."""
    model = find_model(cfg)
    if not model:
        return cfg, False
    try:
        size_gb = os.path.getsize(model) / (1024 ** 3)
    except OSError:
        size_gb = 0
    if size_gb < 2.5:
        return cfg, False   # small models can keep generous settings

    defaults = safe_defaults_for(model)
    try:
        cur_ctx = int(cfg.get("CTX_SIZE", "4096") or 4096)
    except ValueError:
        cur_ctx = 4096
    try:
        cur_layers = int(cfg.get("N_GPU_LAYERS", "999") or 999)
    except ValueError:
        cur_layers = 999
    safe_ctx = int(defaults["CTX_SIZE"])
    safe_layers = int(defaults["N_GPU_LAYERS"])

    if cur_ctx > safe_ctx or cur_layers > safe_layers:
        log(f"Startup: model {model} is {size_gb:.1f} GB but config has ctx={cur_ctx}, layers={cur_layers}. "
            f"Forcing safer defaults {defaults} to avoid OOM.")
        cfg.update(defaults)
        write_config(cfg)
        return cfg, True
    return cfg, False


def main():
    db_init()
    migrate_providers()
    cfg = read_config()
    if not os.path.exists(CONFIG_FILE):
        write_config(cfg)
    cfg, _ = _force_safe_settings_on_startup(cfg)
    port = int(cfg.get("LISTEN_PORT", "8181"))

    def cleanup(*_):
        log("Shutting down…")
        STATE["shutting_down"] = True
        stop_llama()
        os._exit(0)
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGHUP, lambda *_: STATE.update(request_restart=True))

    threading.Thread(target=supervisor, daemon=True).start()

    log(f"control_daemon v0.7 starting on :{port} (internal llama :{INTERNAL_PORT})")
    server = ThreadedServer(("0.0.0.0", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
