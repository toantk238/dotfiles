# CLAUDE.md

Claude Code's own configuration, symlinked into `~/.claude` by `install.sh`
(mapping in `../install.conf.yaml`).

## Layout

- `settings.json` / `settings.win.json`: Linux/macOS and Windows variants of
  `~/.claude/settings.json`. They differ only in hook commands and a few plugin
  flags, so apply every other change to both.
- `settings.local.json`, `.local.mcp.json`: machine-local, not shared.
- `hooks/`: Python hooks run from `hooks/.venv` (see `hooks/README.md`).
- `skills/`: personal skills, each symlinked into `~/.claude/skills/`.
- `install-mcp.py`: registers the MCP servers.

## Hooks

- Run the tests with `just test` in `hooks/` (pytest).
- Each hook logs to `hooks/<name>.log` (size-rotated; level from `HOOKS_LOG_LEVEL`).
- Hooks must fail open: on any error, exit 0 without output so Claude Code
  carries on normally.
