#!/usr/bin/env python3

import json
import os
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


def log(msg, color=NC):
    line = f"{color}{msg}{NC}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")


def main():
    log("Installing MCP servers configuration...", YELLOW)

    if not SOURCE_FILE.exists():
        log(f"Error: Source file {SOURCE_FILE} not found!", RED)
        sys.exit(1)

    with open(SOURCE_FILE) as f:
        source = json.load(f)

    mcp_servers = source.get("mcpServers")
    if mcp_servers is None:
        log(f"Error: No mcpServers configuration found in {SOURCE_FILE}", RED)
        sys.exit(1)

    if TARGET_FILE.exists():
        backup = str(TARGET_FILE) + ".backup." + datetime.now().strftime("%Y%m%d_%H%M%S")
        log(f"Backing up existing config to {backup}...", YELLOW)
        shutil.copy2(TARGET_FILE, backup)
        with open(TARGET_FILE) as f:
            config = json.load(f)
        log("Merging configuration into existing file...", YELLOW)
        existing = config.get("mcpServers", {})
        config["mcpServers"] = {**existing, **mcp_servers}
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
