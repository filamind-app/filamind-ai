"""Filamind AI MCP runtime (v1.3.0).

Lightweight in-process registry for Model Context Protocol style tool servers.
Each "server" is a Python class registering one or more tools. Tools are JSON-
described and JSON-callable; the runtime audit-logs every call.

This module is intentionally NOT a full MCP-over-stdio implementation — it
fulfils the same role for an in-process daemon. A future v1.4 can wrap an
adapter that speaks the wire protocol so external Node/Python MCP servers can
be plugged in too.

Architecture
------------
ToolServer        : base class; subclasses describe tools + implement call()
MCPRegistry       : holds servers, looks up by tool name, audit-logs every call
Tool descriptors  : OpenAI/Anthropic-compatible JSON-Schema shapes

Security
--------
Per-tool allow-lists live in the server instances themselves (e.g. filesystem
roots, fetch hosts, shell commands). The registry enforces a per-user rate
limit (default 60 calls/hour) and a per-turn hop limit (8) so a runaway model
cannot loop forever.

Audit log table
---------------
    CREATE TABLE mcp_audit (
        id          INTEGER PRIMARY KEY,
        ts          INTEGER NOT NULL,   -- unix seconds
        user_id     INTEGER,            -- nullable for system calls
        agent_id    INTEGER,            -- nullable
        tool        TEXT NOT NULL,
        args_json   TEXT NOT NULL,      -- redacted if 'sensitive'
        result_size INTEGER NOT NULL,
        duration_ms INTEGER NOT NULL,
        ok          INTEGER NOT NULL,   -- 1 success / 0 failure
        error       TEXT                -- truncated error message if !ok
    );
"""

from __future__ import annotations

import json
import time
import sqlite3
import threading
from typing import Any, Callable


# ─── Errors ────────────────────────────────────────────────────────────────
class MCPError(Exception):
    """Base class for any runtime-rejected call (limit hit, missing tool, etc.)."""


class ToolNotFound(MCPError):
    pass


class ToolDisabled(MCPError):
    pass


class RateLimited(MCPError):
    pass


class HopsExceeded(MCPError):
    pass


# ─── Tool descriptor + base server ─────────────────────────────────────────
class Tool:
    """Lightweight tool descriptor.

    Parameters JSON-schema is what cloud providers expect verbatim, so keep it
    minimal and standard (type, properties, required).
    """
    __slots__ = ("name", "description", "parameters", "handler", "sensitive")

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable[[dict], Any],
        sensitive: bool = False,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler
        self.sensitive = sensitive   # if True, args are redacted in the audit log

    def as_openai(self) -> dict:
        """OpenAI chat-completions native tools format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def as_anthropic(self) -> dict:
        """Anthropic Messages API tools format (input_schema instead of parameters)."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def as_gemini(self) -> dict:
        """Google Gemini function_declarations format."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolServer:
    """Subclass and register tools via self.tools.append(Tool(...))."""
    name: str = ""        # registry key, lowercase, no spaces
    title: str = ""       # human-readable
    description: str = ""

    def __init__(self):
        self.tools: list[Tool] = []
        self.enabled: bool = True
        self._configure()

    def _configure(self):
        """Override in subclasses to add tools / read config."""
        raise NotImplementedError

    def list(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "server": self.name,
                "sensitive": t.sensitive,
            }
            for t in self.tools
        ]

    def find(self, tool_name: str) -> Tool | None:
        for t in self.tools:
            if t.name == tool_name:
                return t
        return None


# ─── Registry ──────────────────────────────────────────────────────────────
class MCPRegistry:
    """Single instance owned by control_daemon. Thread-safe (the daemon is
    single-threaded HTTPServer + workers, but tool calls touch sqlite)."""

    def __init__(self, db_path: str, hop_limit: int = 8, rate_limit_per_hour: int = 60):
        self.db_path = db_path
        self.hop_limit = hop_limit
        self.rate_limit_per_hour = rate_limit_per_hour
        self._servers: dict[str, ToolServer] = {}
        self._lock = threading.RLock()
        self._init_db()
        self._rate_buckets: dict[int, list[float]] = {}  # user_id → [ts, ts, ...]

    # ─── DB ──────────────────────────────────────────────────────────────
    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS mcp_audit (
                    id          INTEGER PRIMARY KEY,
                    ts          INTEGER NOT NULL,
                    user_id     INTEGER,
                    agent_id    INTEGER,
                    tool        TEXT NOT NULL,
                    server      TEXT NOT NULL,
                    args_json   TEXT NOT NULL,
                    result_size INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    ok          INTEGER NOT NULL,
                    error       TEXT
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_mcp_audit_ts      ON mcp_audit(ts DESC)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_mcp_audit_user_ts ON mcp_audit(user_id, ts DESC)")
            c.execute("""
                CREATE TABLE IF NOT EXISTS mcp_servers (
                    name        TEXT PRIMARY KEY,
                    enabled     INTEGER NOT NULL DEFAULT 1,
                    config_json TEXT NOT NULL DEFAULT '{}'
                )
            """)

    # ─── Registration ────────────────────────────────────────────────────
    def register(self, server: ToolServer) -> None:
        with self._lock:
            if not server.name:
                raise ValueError("server.name is empty")
            if server.name in self._servers:
                raise ValueError(f"server already registered: {server.name}")
            # Persist enabled state if first time
            with self._conn() as c:
                row = c.execute("SELECT enabled FROM mcp_servers WHERE name=?", (server.name,)).fetchone()
                if row is None:
                    c.execute("INSERT INTO mcp_servers(name, enabled) VALUES (?, 1)", (server.name,))
                else:
                    server.enabled = bool(row["enabled"])
            self._servers[server.name] = server

    def servers(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "name":        s.name,
                    "title":       s.title,
                    "description": s.description,
                    "enabled":     s.enabled,
                    "tool_count":  len(s.tools),
                    "tools":       s.list(),
                }
                for s in self._servers.values()
            ]

    def set_enabled(self, server_name: str, enabled: bool) -> None:
        with self._lock:
            s = self._servers.get(server_name)
            if not s:
                raise ToolNotFound(f"server: {server_name}")
            s.enabled = bool(enabled)
            with self._conn() as c:
                c.execute("UPDATE mcp_servers SET enabled=? WHERE name=?", (1 if enabled else 0, server_name))

    def find_tool(self, tool_name: str) -> tuple[ToolServer, Tool]:
        with self._lock:
            for s in self._servers.values():
                t = s.find(tool_name)
                if t:
                    return s, t
        raise ToolNotFound(tool_name)

    def list_tools(self, allow: list[str] | None = None) -> list[dict]:
        """Return flat tool list. If `allow` is provided, only tools whose
        `<server>.<tool>` (or just `<tool>`) is in the list are returned."""
        with self._lock:
            out = []
            for s in self._servers.values():
                if not s.enabled:
                    continue
                for t in s.tools:
                    if allow is not None and t.name not in allow and f"{s.name}.{t.name}" not in allow:
                        continue
                    out.append({
                        "name":        t.name,
                        "description": t.description,
                        "parameters":  t.parameters,
                        "server":      s.name,
                    })
            return out

    # ─── Tool exporters per cloud provider ───────────────────────────────
    def tools_for_provider(self, provider: str, allow: list[str] | None = None) -> list[dict]:
        """Return tool definitions in the wire format the given provider expects."""
        with self._lock:
            tools = []
            for s in self._servers.values():
                if not s.enabled:
                    continue
                for t in s.tools:
                    if allow is not None and t.name not in allow and f"{s.name}.{t.name}" not in allow:
                        continue
                    if provider == "openai":
                        tools.append(t.as_openai())
                    elif provider == "anthropic":
                        tools.append(t.as_anthropic())
                    elif provider == "gemini":
                        tools.append(t.as_gemini())
                    elif provider == "local":
                        # Local b1620 has no native tool calling; we pass the
                        # raw OpenAI shape and rely on prompt-based simulation
                        # in the daemon's request builder.
                        tools.append(t.as_openai())
                    else:
                        tools.append(t.as_openai())
            return tools

    # ─── Call execution ──────────────────────────────────────────────────
    def call(
        self,
        tool_name: str,
        args: dict,
        *,
        user_id: int | None = None,
        agent_id: int | None = None,
        hop: int = 1,
    ) -> dict:
        """Execute one tool call. Caller passes `hop` (1..hop_limit) for the
        runaway-loop guard. Returns {ok, result|error, server, tool, duration_ms}."""
        if hop > self.hop_limit:
            raise HopsExceeded(f"hop limit {self.hop_limit} exceeded")

        # Rate limit by user_id (skip if anonymous / system call)
        if user_id is not None:
            now = time.time()
            with self._lock:
                bucket = self._rate_buckets.setdefault(user_id, [])
                cutoff = now - 3600
                bucket[:] = [t for t in bucket if t > cutoff]
                if len(bucket) >= self.rate_limit_per_hour:
                    raise RateLimited(f"{self.rate_limit_per_hour}/hour")
                bucket.append(now)

        server, tool = self.find_tool(tool_name)
        if not server.enabled:
            raise ToolDisabled(server.name)

        t0 = time.time()
        ok, result, error = True, None, None
        try:
            result = tool.handler(args or {})
        except Exception as e:  # noqa: BLE001 — tool authors are trusted in-process
            ok, error = False, str(e)[:400]
        duration_ms = int((time.time() - t0) * 1000)

        # Audit log
        try:
            args_redacted = "<redacted>" if tool.sensitive else json.dumps(args or {}, ensure_ascii=False)[:2000]
            res_repr      = json.dumps(result, ensure_ascii=False, default=str) if ok else None
            result_size   = len(res_repr) if res_repr else 0
            with self._conn() as c:
                c.execute(
                    """INSERT INTO mcp_audit
                       (ts, user_id, agent_id, tool, server, args_json,
                        result_size, duration_ms, ok, error)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        int(t0), user_id, agent_id, tool.name, server.name,
                        args_redacted, result_size, duration_ms, 1 if ok else 0, error,
                    ),
                )
        except Exception:
            pass

        return {
            "ok":          ok,
            "tool":        tool.name,
            "server":      server.name,
            "duration_ms": duration_ms,
            "result":      result if ok else None,
            "error":       error if not ok else None,
        }

    # ─── Audit log queries ───────────────────────────────────────────────
    def recent_audit(self, limit: int = 50, user_id: int | None = None) -> list[dict]:
        q = "SELECT * FROM mcp_audit"
        args: tuple = ()
        if user_id is not None:
            q += " WHERE user_id=?"
            args = (user_id,)
        q += " ORDER BY ts DESC LIMIT ?"
        args = args + (limit,)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]
