"""Built-in MCP tool servers for Filamind AI.

This module wires up the Tier-A servers that ship with v1.3.0:

    calculator       — safe arithmetic evaluation
    datetime         — now, parse, format, offset
    memory           — persistent key-value store per user
    nas_info         — CPU / RAM / disk / GPU snapshot
    filesystem       — read-only file access under allow-listed roots
    fetch            — HTTP GET against allow-listed hosts
    shell            — execute commands from an allow-list
    sqlite           — query user-provided .sqlite databases
    synology_fs      — list/search files via FileStation API
    synology_surv    — recent Surveillance Station events / snapshots
    homeassistant    — query state / call services on Home Assistant
    docker           — list containers via Container Manager socket

Each server lazily reads its config from /var/packages/FilamindAI/etc/mcp.json
so the admin UI can adjust allow-lists at runtime without a daemon restart.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import os
import socket
import sqlite3
import subprocess
import urllib.parse
import urllib.request

from mcp_runtime import Tool, ToolServer


# Config paths
MCP_CONFIG_FILE = "/var/packages/FilamindAI/etc/mcp.json"
MEMORY_DB       = "/var/packages/FilamindAI/etc/mcp_memory.db"


def _read_mcp_config() -> dict:
    try:
        with open(MCP_CONFIG_FILE) as f:
            return json.load(f) or {}
    except Exception:
        return {}


# ───────────────────────────────────────────────────────────────────────────
# 1. Calculator — safe arithmetic + math functions
# ───────────────────────────────────────────────────────────────────────────
class CalculatorServer(ToolServer):
    name        = "calculator"
    title       = "Calculator"
    description = "Evaluate arithmetic expressions (no Python imports allowed)."

    _ALLOWED_NODES = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
        ast.USub, ast.UAdd, ast.Load, ast.Call, ast.Name,
    )
    _ALLOWED_NAMES = {
        "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
        "len": len, "pow": pow, "int": int, "float": float,
        "pi": 3.141592653589793, "e": 2.718281828459045,
    }

    def _configure(self):
        self.tools.append(Tool(
            name="calculator.eval",
            description="Evaluate a math expression. Supports + - * / // % ** and "
                        "abs/round/min/max/sum/len/pow/int/float/pi/e. NO variable "
                        "assignment, NO imports, NO Python function calls beyond the "
                        "whitelisted ones.",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "e.g. '2 + 3 * 4' or 'pow(2, 10)'"},
                },
                "required": ["expression"],
            },
            handler=self._eval,
        ))

    def _eval(self, args: dict) -> dict:
        expr = (args.get("expression") or "").strip()
        if not expr:
            raise ValueError("expression is empty")
        if len(expr) > 500:
            raise ValueError("expression too long")
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, self._ALLOWED_NODES):
                raise ValueError(f"disallowed syntax: {type(node).__name__}")
            if isinstance(node, ast.Name) and node.id not in self._ALLOWED_NAMES:
                raise ValueError(f"disallowed name: {node.id}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id not in self._ALLOWED_NAMES or not callable(self._ALLOWED_NAMES[node.func.id]):
                    raise ValueError(f"disallowed call: {node.func.id}")
        value = eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, self._ALLOWED_NAMES)  # noqa: S307
        return {"expression": expr, "value": value}


# ───────────────────────────────────────────────────────────────────────────
# 2. Datetime — current time, parsing, math
# ───────────────────────────────────────────────────────────────────────────
class DatetimeServer(ToolServer):
    name        = "datetime"
    title       = "Date & time"
    description = "Current time, parse ISO timestamps, add/subtract durations."

    def _configure(self):
        self.tools.append(Tool(
            name="datetime.now",
            description="Return the current date and time (ISO 8601, UTC and local).",
            parameters={"type": "object", "properties": {}},
            handler=self._now,
        ))
        self.tools.append(Tool(
            name="datetime.parse",
            description="Parse a date/time string and return its ISO 8601 normalisation.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            handler=self._parse,
        ))
        self.tools.append(Tool(
            name="datetime.offset",
            description="Add or subtract a duration from an ISO 8601 timestamp.",
            parameters={
                "type": "object",
                "properties": {
                    "iso":     {"type": "string", "description": "Base timestamp."},
                    "seconds": {"type": "integer", "description": "Offset in seconds (negative for past)."},
                },
                "required": ["iso", "seconds"],
            },
            handler=self._offset,
        ))

    def _now(self, _args):
        now = dt.datetime.now(dt.timezone.utc)
        local = dt.datetime.now()
        return {
            "utc":    now.isoformat(),
            "local":  local.isoformat(),
            "epoch":  int(now.timestamp()),
            "weekday": now.strftime("%A"),
        }

    def _parse(self, args):
        text = (args.get("text") or "").strip()
        # try a sequence of common formats
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
        ):
            try:
                d = dt.datetime.strptime(text, fmt)
                return {"input": text, "iso": d.isoformat(), "epoch": int(d.timestamp())}
            except ValueError:
                continue
        # Last resort: fromisoformat (Py 3.7+)
        try:
            d = dt.datetime.fromisoformat(text)
            return {"input": text, "iso": d.isoformat(), "epoch": int(d.timestamp())}
        except ValueError:
            raise ValueError(f"could not parse: {text!r}")

    def _offset(self, args):
        d = dt.datetime.fromisoformat(args["iso"])
        out = d + dt.timedelta(seconds=int(args["seconds"]))
        return {"input": args["iso"], "offset_seconds": int(args["seconds"]), "iso": out.isoformat()}


# ───────────────────────────────────────────────────────────────────────────
# 3. Memory — per-user persistent KV store
# ───────────────────────────────────────────────────────────────────────────
class MemoryServer(ToolServer):
    name        = "memory"
    title       = "Persistent memory"
    description = "Save and recall short notes / facts across conversations."

    def _configure(self):
        self._ensure_db()
        self.tools.append(Tool(
            name="memory.set",
            description="Store a value under a key. Overwrites any existing value for that key.",
            parameters={
                "type": "object",
                "properties": {
                    "key":   {"type": "string", "description": "Short identifier, e.g. 'favorite_color'."},
                    "value": {"type": "string", "description": "What to remember (max 4000 chars)."},
                },
                "required": ["key", "value"],
            },
            handler=self._set,
        ))
        self.tools.append(Tool(
            name="memory.get",
            description="Look up a stored value by key. Returns null if no such key.",
            parameters={
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
            handler=self._get,
        ))
        self.tools.append(Tool(
            name="memory.list",
            description="List all stored keys (values not included).",
            parameters={"type": "object", "properties": {}},
            handler=self._list,
        ))
        self.tools.append(Tool(
            name="memory.delete",
            description="Remove a stored key.",
            parameters={
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
            handler=self._delete,
        ))

    def _ensure_db(self):
        # Allow override via the env var so unit tests don't need /var/packages/.
        global MEMORY_DB
        MEMORY_DB = os.environ.get("FILAMIND_MCP_MEMORY_DB", MEMORY_DB)
        try:
            os.makedirs(os.path.dirname(MEMORY_DB) or ".", exist_ok=True)
        except Exception:
            # If we can't make the parent dir, fall back to a tmp path so the
            # server still loads (Memory tools then write to /tmp).
            import tempfile
            MEMORY_DB = os.path.join(tempfile.gettempdir(), "filamind_mcp_memory.db")
        with sqlite3.connect(MEMORY_DB, timeout=10) as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS memory_kv (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    ts    INTEGER NOT NULL
                )
            """)

    def _set(self, args):
        key = str(args.get("key", "")).strip()
        val = str(args.get("value", ""))
        if not key or len(key) > 128:
            raise ValueError("key must be 1..128 chars")
        if len(val) > 4000:
            raise ValueError("value must be <= 4000 chars")
        import time
        with sqlite3.connect(MEMORY_DB) as c:
            c.execute(
                "INSERT INTO memory_kv (key, value, ts) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, ts=excluded.ts",
                (key, val, int(time.time())),
            )
        return {"ok": True, "key": key}

    def _get(self, args):
        key = str(args.get("key", "")).strip()
        with sqlite3.connect(MEMORY_DB) as c:
            r = c.execute("SELECT value, ts FROM memory_kv WHERE key=?", (key,)).fetchone()
        if not r:
            return {"key": key, "value": None}
        return {"key": key, "value": r[0], "stored_at": r[1]}

    def _list(self, _args):
        with sqlite3.connect(MEMORY_DB) as c:
            rows = c.execute("SELECT key, ts FROM memory_kv ORDER BY ts DESC").fetchall()
        return {"count": len(rows), "keys": [{"key": k, "stored_at": t} for k, t in rows]}

    def _delete(self, args):
        key = str(args.get("key", "")).strip()
        with sqlite3.connect(MEMORY_DB) as c:
            cur = c.execute("DELETE FROM memory_kv WHERE key=?", (key,))
            removed = cur.rowcount
        return {"key": key, "removed": removed}


# ───────────────────────────────────────────────────────────────────────────
# 4. NAS info — CPU / RAM / disk / GPU snapshot
# ───────────────────────────────────────────────────────────────────────────
class NasInfoServer(ToolServer):
    name        = "nas_info"
    title       = "NAS info"
    description = "Inspect CPU load, free memory, disk usage, and GPU presence."

    def _configure(self):
        self.tools.append(Tool(
            name="nas_info.snapshot",
            description="Return current CPU / RAM / disk / GPU stats.",
            parameters={"type": "object", "properties": {}},
            handler=self._snapshot,
        ))

    def _read(self, path, default=""):
        try:
            with open(path) as f:
                return f.read()
        except Exception:
            return default

    def _snapshot(self, _args):
        cpu_count = os.cpu_count() or 0
        try:
            load1, load5, load15 = os.getloadavg()
        except OSError:
            load1 = load5 = load15 = 0.0

        # Memory
        mem_total = mem_avail = 0
        for line in self._read("/proc/meminfo").splitlines():
            if line.startswith("MemTotal:"):    mem_total = int(line.split()[1]) * 1024
            if line.startswith("MemAvailable:"): mem_avail = int(line.split()[1]) * 1024

        # Disk usage (first /volume*)
        disks = []
        try:
            import shutil
            for p in ("/volume1", "/volume2", "/volume3"):
                if os.path.isdir(p):
                    s = shutil.disk_usage(p)
                    disks.append({"path": p, "total": s.total, "used": s.used, "free": s.free})
        except Exception:
            pass

        # GPU
        gpu = {"present": os.path.exists("/dev/nvidia0")}
        if gpu["present"]:
            gpu["device_nodes"] = sorted([d for d in os.listdir("/dev") if d.startswith("nvidia")])

        # Uptime
        try:
            uptime_s = float(self._read("/proc/uptime").split()[0])
        except Exception:
            uptime_s = 0

        return {
            "cpu":     {"count": cpu_count, "load_1m": load1, "load_5m": load5, "load_15m": load15},
            "memory":  {"total_bytes": mem_total, "available_bytes": mem_avail, "used_pct": round(100 * (mem_total - mem_avail) / mem_total, 1) if mem_total else 0},
            "disks":   disks,
            "gpu":     gpu,
            "uptime_seconds": int(uptime_s),
            "hostname": socket.gethostname(),
        }


# ───────────────────────────────────────────────────────────────────────────
# 5. Filesystem — read-only file access under allow-listed roots
# ───────────────────────────────────────────────────────────────────────────
class FilesystemServer(ToolServer):
    name        = "filesystem"
    title       = "Filesystem (read-only)"
    description = "Read text files and list directory contents under admin-approved paths."

    DEFAULT_ROOTS = ("/volume1/FilamindAI/shared", "/volume1/AI/shared")

    def _configure(self):
        cfg = _read_mcp_config().get("filesystem", {})
        self.allow_roots = tuple(cfg.get("allow_roots") or self.DEFAULT_ROOTS)
        self.max_file_size = int(cfg.get("max_file_size", 256 * 1024))   # 256 KB

        self.tools.append(Tool(
            name="filesystem.read_file",
            description=f"Read a UTF-8 text file. Path must lie under one of: {', '.join(self.allow_roots)}. Max 256 KB.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=self._read_file,
        ))
        self.tools.append(Tool(
            name="filesystem.list_dir",
            description=f"List entries under a directory. Path must lie under one of: {', '.join(self.allow_roots)}.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=self._list_dir,
        ))

    def _check(self, path: str) -> str:
        real = os.path.realpath(path)
        for root in self.allow_roots:
            root_real = os.path.realpath(root)
            try:
                if os.path.commonpath([real, root_real]) == root_real:
                    return real
            except ValueError:
                continue
        raise PermissionError(f"path outside allow-list: {path}")

    def _read_file(self, args):
        real = self._check(args["path"])
        if not os.path.isfile(real):
            raise FileNotFoundError(real)
        size = os.path.getsize(real)
        if size > self.max_file_size:
            raise ValueError(f"file too large ({size} bytes, max {self.max_file_size})")
        with open(real, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"path": real, "size": size, "content": content}

    def _list_dir(self, args):
        real = self._check(args["path"])
        if not os.path.isdir(real):
            raise NotADirectoryError(real)
        entries = []
        for name in sorted(os.listdir(real)):
            full = os.path.join(real, name)
            try:
                st = os.stat(full)
                entries.append({
                    "name":  name,
                    "type":  "dir" if os.path.isdir(full) else "file",
                    "size":  st.st_size,
                    "mtime": int(st.st_mtime),
                })
            except OSError:
                entries.append({"name": name, "type": "unknown"})
        return {"path": real, "count": len(entries), "entries": entries}


# ───────────────────────────────────────────────────────────────────────────
# 6. Fetch — HTTP GET against allow-listed hosts
# ───────────────────────────────────────────────────────────────────────────
class FetchServer(ToolServer):
    name        = "fetch"
    title       = "HTTP fetch"
    description = "Retrieve a public URL via HTTPS GET. Host must be on the allow-list."

    DEFAULT_HOSTS = ("api.github.com", "raw.githubusercontent.com", "huggingface.co",
                     "duckduckgo.com", "wikipedia.org", "en.wikipedia.org")

    def _configure(self):
        cfg = _read_mcp_config().get("fetch", {})
        self.allow_hosts = tuple(cfg.get("allow_hosts") or self.DEFAULT_HOSTS)
        self.max_bytes = int(cfg.get("max_bytes", 200_000))
        self.timeout   = int(cfg.get("timeout", 10))

        self.tools.append(Tool(
            name="fetch.get",
            description=f"HTTPS GET. Allowed hosts: {', '.join(self.allow_hosts)}. Max {self.max_bytes} bytes.",
            parameters={
                "type": "object",
                "properties": {
                    "url":    {"type": "string", "description": "https:// URL"},
                    "accept": {"type": "string", "description": "Optional Accept header (e.g. application/json)"},
                },
                "required": ["url"],
            },
            handler=self._get,
        ))

    def _get(self, args):
        url = args["url"]
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https":
            raise ValueError("only https:// URLs allowed")
        host = (parsed.hostname or "").lower()
        if not any(host == h or host.endswith("." + h) for h in self.allow_hosts):
            raise PermissionError(f"host not allow-listed: {host}")
        # RFC1918 block: resolve hostname and ensure it isn't private (defeats DNS rebinding)
        try:
            ips = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
            for fam, _, _, _, sockaddr in ips:
                ip = sockaddr[0]
                if ip.startswith(("10.", "127.", "192.168.")):
                    raise PermissionError(f"resolves to private IP: {ip}")
                if ip.startswith("172."):
                    o2 = int(ip.split(".")[1])
                    if 16 <= o2 <= 31:
                        raise PermissionError(f"resolves to private IP: {ip}")
        except socket.gaierror:
            raise ValueError(f"could not resolve host: {host}")

        req = urllib.request.Request(url, headers={
            "User-Agent": "FilamindAI-MCP/1.0",
            "Accept": args.get("accept") or "*/*",
        })
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            content_type = r.headers.get("Content-Type", "")
            body = r.read(self.max_bytes + 1)
            truncated = len(body) > self.max_bytes
            body = body[:self.max_bytes]
            try:
                text = body.decode("utf-8", errors="replace")
            except Exception:
                text = repr(body)
            return {
                "url":          url,
                "status":       r.status,
                "content_type": content_type,
                "truncated":    truncated,
                "size":         len(body),
                "body":         text,
            }


# ───────────────────────────────────────────────────────────────────────────
# 7. Shell — execute commands from an allow-list (default empty / disabled)
# ───────────────────────────────────────────────────────────────────────────
class ShellServer(ToolServer):
    name        = "shell"
    title       = "Shell (allow-listed)"
    description = "Run a command from the admin-defined allow-list. Disabled by default."

    SAFE_DEFAULTS = ("uptime", "df -h", "free -h", "uname -a", "date", "hostname")

    def _configure(self):
        cfg = _read_mcp_config().get("shell", {})
        # Default is empty → no commands accepted unless admin opts in
        self.allow_commands = tuple(cfg.get("allow_commands") or [])
        self.timeout = int(cfg.get("timeout", 10))

        self.tools.append(Tool(
            name="shell.run",
            description=("Run a command exactly as listed in the admin allow-list. The command "
                         f"string must match (verbatim) one of: {list(self.allow_commands) or '(none configured — admin must opt in)'}. "
                         "Safe defaults you can enable: " + ", ".join(self.SAFE_DEFAULTS)),
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            handler=self._run,
            sensitive=True,
        ))

    def _run(self, args):
        cmd = (args.get("command") or "").strip()
        if cmd not in self.allow_commands:
            raise PermissionError("command not in allow-list (admin must opt in via Settings → MCP)")
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=self.timeout,
        )
        return {
            "command":     cmd,
            "exit":        proc.returncode,
            "stdout":      proc.stdout[-4000:],   # cap to keep audit log small
            "stderr":      proc.stderr[-1000:],
        }


# ───────────────────────────────────────────────────────────────────────────
# 8. SQLite — query user-provided .sqlite databases (read-only)
# ───────────────────────────────────────────────────────────────────────────
class SqliteServer(ToolServer):
    name        = "sqlite"
    title       = "SQLite query"
    description = "Run SELECT queries against SQLite databases under allow-listed paths."

    def _configure(self):
        cfg = _read_mcp_config().get("sqlite", {})
        self.allow_roots = tuple(cfg.get("allow_roots") or ("/volume1/FilamindAI/shared/sqlite",))
        self.max_rows = int(cfg.get("max_rows", 200))

        self.tools.append(Tool(
            name="sqlite.query",
            description=(f"Run a single SELECT statement against a SQLite file under: "
                         f"{', '.join(self.allow_roots)}. Returns at most {self.max_rows} rows."),
            parameters={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string"},
                    "sql":     {"type": "string", "description": "Must start with SELECT (case-insensitive)."},
                    "params":  {"type": "array",  "description": "Optional positional ? params", "items": {}},
                },
                "required": ["db_path", "sql"],
            },
            handler=self._query,
        ))

    def _check(self, path: str) -> str:
        real = os.path.realpath(path)
        for root in self.allow_roots:
            root_real = os.path.realpath(root)
            try:
                if os.path.commonpath([real, root_real]) == root_real:
                    if os.path.isfile(real):
                        return real
            except ValueError:
                continue
        raise PermissionError(f"db path outside allow-list: {path}")

    def _query(self, args):
        real = self._check(args["db_path"])
        sql = (args.get("sql") or "").lstrip()
        if not sql.lower().startswith("select"):
            raise ValueError("only SELECT statements are allowed")
        params = tuple(args.get("params") or ())
        with sqlite3.connect(f"file:{real}?mode=ro", uri=True, timeout=5) as c:
            c.row_factory = sqlite3.Row
            cur = c.execute(sql, params)
            rows = []
            for row in cur:
                rows.append({k: row[k] for k in row.keys()})
                if len(rows) >= self.max_rows:
                    break
        return {"db_path": real, "rows": rows, "truncated": len(rows) >= self.max_rows}


# ───────────────────────────────────────────────────────────────────────────
# Registration helper — control_daemon calls this once at boot
# ───────────────────────────────────────────────────────────────────────────
def register_builtin_servers(registry) -> None:
    """Register every built-in Tier-A server. Safe to call multiple times only
    if the registry caller checks for duplicates (current impl raises on dup)."""
    for cls in (
        CalculatorServer,
        DatetimeServer,
        MemoryServer,
        NasInfoServer,
        FilesystemServer,
        FetchServer,
        ShellServer,
        SqliteServer,
    ):
        try:
            registry.register(cls())
        except ValueError:
            # already registered — fine
            pass
