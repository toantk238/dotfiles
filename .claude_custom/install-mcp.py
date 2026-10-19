#!/usr/bin/env python3

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
LOG_FILE = SCRIPT_DIR / (Path(__file__).stem + ".log")
SOURCE_FILE = SCRIPT_DIR / ".local.mcp.json"
TARGET_FILE = Path.home() / ".claude.json"

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"


sys.stdout.reconfigure(encoding="utf-8")


def log(msg, color=NC):
    line = f"{color}{msg}{NC}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


# npm shims are .cmd files on Windows; Claude Code can't spawn them directly.
WINDOWS_CMD_SHIMS = {"npx", "npm", "codegraph"}


def expand(value):
    """Expand ${VAR:-default} and a leading ~ in a config string."""
    value = re.sub(
        r"\$\{(\w+):-([^}]*)\}",
        lambda m: os.environ.get(m.group(1)) or m.group(2),
        value,
    )
    return os.path.expanduser(value)


def resolve_server(name, server):
    """Return a platform-ready server entry, or None if its prerequisites are missing."""
    server = dict(server)
    platforms = server.pop("_platforms", None)
    if platforms and sys.platform not in platforms:
        log(f"Skipping {name}: not supported on {sys.platform}", YELLOW)
        return None
    requires = server.pop("_requires", None)
    if requires and not Path(expand(requires)).exists():
        log(f"Skipping {name}: {expand(requires)} not found", YELLOW)
        return None
    server["args"] = [expand(a) for a in server.get("args", [])]
    if sys.platform == "win32" and server["command"] in WINDOWS_CMD_SHIMS:
        server["args"] = ["/c", server["command"], *server["args"]]
        server["command"] = "cmd"
    return server


def main():
    log("Installing MCP servers configuration...", YELLOW)

    if not SOURCE_FILE.exists():
        log(f"Error: Source file {SOURCE_FILE} not found!", RED)
        sys.exit(1)

    with open(SOURCE_FILE) as f:
        source = json.load(f)

    if source.get("mcpServers") is None:
        log(f"Error: No mcpServers configuration found in {SOURCE_FILE}", RED)
        sys.exit(1)
    mcp_servers = {}
    for name, server in source["mcpServers"].items():
        resolved = resolve_server(name, server)
        if resolved is not None:
            mcp_servers[name] = resolved

    if TARGET_FILE.exists():
        backup = str(TARGET_FILE) + ".backup." + datetime.now().strftime("%Y%m%d_%H%M%S")
        log(f"Backing up existing config to {backup}...", YELLOW)
        shutil.copy2(TARGET_FILE, backup)
        with open(TARGET_FILE) as f:
            config = json.load(f)
        log("Merging configuration into existing file...", YELLOW)
        existing = config.get("mcpServers", {})
        config["mcpServers"] = {
            **existing,
            **{k: {**existing.get(k, {}), **v} for k, v in mcp_servers.items()},
        }
    else:
        log("Creating new config file...", YELLOW)
        config = {"mcpServers": mcp_servers}

    with open(TARGET_FILE, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    log(f"✓ MCP servers configuration installed successfully!", GREEN)
    log(f"Configuration file: {TARGET_FILE}", GREEN)
    log("\nInstalled MCP servers:")
    for key in config["mcpServers"]:
        log(f"  - {key}")


if __name__ == "__main__":
    main()
