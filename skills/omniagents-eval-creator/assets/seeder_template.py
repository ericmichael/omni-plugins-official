#!/usr/bin/env python3
"""DB-fixture seeder template.

Builds evaluations/fixtures/dbs/<NAME>.db by driving the launcher's
omni-projects-mcp cli over stdio. The pattern mirrors the live launcher
flow so the fixture stays in sync with whatever schema the cli expects.

Replace every <PLACEHOLDER>. Re-run any time the schema or seed text
changes:

    python evaluations/fixtures/dbs/build_<NAME>.py
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import sqlite3
import string
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict


_ID_ALPHABET = string.ascii_letters + string.digits + "_-"


def _nano(n: int = 12) -> str:
    """nanoid-like ID (URL-safe, default 12 chars). Mirrors the launcher's format."""
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(n))


# Override the launcher's default 6-column pipeline with these. Drop the
# PR / Review / etc. affordances so the agent just walks Backlog → Active → Done.
_SIMPLE_COLUMNS = ("Backlog", "Active", "Done")


_LAUNCHER_DEFAULT_MCP_CLI = (
    Path.home()
    / "Omni" / "Workspace" / "launcher"
    / "packages" / "projects-mcp" / "dist" / "cli.js"
)
_OUTPUT_DB = Path(__file__).parent / "<NAME>.db"


# ─── Seed content ────────────────────────────────────────────────────

_PROJECT_LABEL = "<PROJECT NAME>"

_TICKET_TITLE = "<TICKET TITLE — used by until_sql / assert_sql>"
_TICKET_DESCRIPTION = """\
<Plain-words description of the work the agent must do. This is the
agent's complete task spec — be concrete about what 'done' looks like
and what verifiers will be applied. Include reproducible steps.>

Acceptance — all <N> layers required:
  1. <verifier 1>
  2. <verifier 2>
  3. <verifier 3>

Verification: <how the eval framework will check>.
"""


# ─── MCP cli plumbing (do not edit unless the cli interface changes) ─


def _resolve_mcp_cli() -> Path:
    env_path = os.environ.get("OMNI_PROJECTS_MCP_CLI")
    if env_path:
        p = Path(env_path).expanduser()
        if p.is_file():
            return p
        sys.exit(f"OMNI_PROJECTS_MCP_CLI={env_path!r} does not point to a file")
    if _LAUNCHER_DEFAULT_MCP_CLI.is_file():
        return _LAUNCHER_DEFAULT_MCP_CLI
    sys.exit(
        "omni-projects-mcp cli not found. Set OMNI_PROJECTS_MCP_CLI or build "
        f"the launcher at {_LAUNCHER_DEFAULT_MCP_CLI}"
    )


class _StdioRpc:
    def __init__(self, proc: subprocess.Popen) -> None:
        self._proc = proc
        self._next_id = 0

    def call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self._next_id += 1
        request = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._proc.stdin.write(json.dumps(request) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError(f"MCP cli closed stdout before responding to {method}")
        msg = json.loads(line)
        if "error" in msg:
            raise RuntimeError(f"MCP error on {method}: {msg['error']}")
        return msg.get("result", {})

    def tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = self.call("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content") or []
        if not content:
            return result
        text = content[0].get("text", "")
        return json.loads(text) if text else {}


def _spawn_cli(cli_path: Path, db_path: Path, pages_dir: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [
            "node", str(cli_path),
            "--db-path", str(db_path),
            "--pages-dir", str(pages_dir),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _shutdown_cli(proc: subprocess.Popen) -> None:
    try:
        if proc.stdin:
            proc.stdin.close()
    except Exception:
        pass
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _replace_pipeline_with_simple(db_path: Path, project_id: str) -> None:
    """Overwrite the cli's auto-seeded pipeline with the simple 3-column shape."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM pipeline_columns WHERE project_id = ?", (project_id,))
        for sort_order, label in enumerate(_SIMPLE_COLUMNS):
            conn.execute(
                "INSERT INTO pipeline_columns "
                "(id, project_id, label, description, sort_order, gate) "
                "VALUES (?, ?, ?, NULL, ?, 0)",
                (f"col_{_nano()}", project_id, label, sort_order),
            )
        conn.execute("UPDATE _change_seq SET seq = seq + 1")
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    cli_path = _resolve_mcp_cli()
    if _OUTPUT_DB.exists():
        _OUTPUT_DB.unlink()

    scratch = Path(tempfile.mkdtemp(prefix="<NAME>_seed_"))
    pages_dir = scratch / "pages"
    pages_dir.mkdir()

    # Phase 1: create the project (gets schema migrations + root page).
    proc = _spawn_cli(cli_path, _OUTPUT_DB, pages_dir)
    try:
        rpc = _StdioRpc(proc)
        rpc.call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "<NAME>-seeder", "version": "0"},
        })
        project = rpc.tool("create_project", {"label": _PROJECT_LABEL})
        project_id = project["id"]
        print(f"phase 1 — created project: id={project_id} default_pipeline={project['pipeline']}")
    finally:
        _shutdown_cli(proc)

    # Phase 2: replace the pipeline with the simple 3-column shape.
    _replace_pipeline_with_simple(_OUTPUT_DB, project_id)
    print(f"phase 2 — replaced pipeline with: {list(_SIMPLE_COLUMNS)}")

    # Phase 3: seed the ticket. Auto-lands in Backlog (the new first column).
    proc = _spawn_cli(cli_path, _OUTPUT_DB, pages_dir)
    try:
        rpc = _StdioRpc(proc)
        rpc.call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "<NAME>-seeder", "version": "0"},
        })
        ticket = rpc.tool("create_ticket", {
            "project_id": project_id,
            "title": _TICKET_TITLE,
            "description": _TICKET_DESCRIPTION,
            "priority": "high",
        })
        print(f"phase 3 — created ticket: id={ticket['id']} column={ticket['column']}")
    finally:
        _shutdown_cli(proc)

    shutil.rmtree(scratch, ignore_errors=True)
    print(f"wrote {_OUTPUT_DB} ({_OUTPUT_DB.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
