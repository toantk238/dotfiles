# Design: `.gemini_custom` — AGY Hooks + Slack Notifications

**Date:** 2026-06-30
**Status:** Approved, ready for implementation

## Overview

Create `.gemini_custom/` in the dotfiles repo as a standalone mirror of `.claude_custom/`, adapted for the Antigravity CLI (`agy`). Provides the same three behaviors: Slack notifications, AI-powered pre-tool security review, and AI stop-router auto-proceed — plus the three utility hooks (PostToolUse graph update, SessionStart graph status, UserPromptSubmit debug).

## Architecture

### Approach: Full standalone copy (Approach A)

`.gemini_custom/` is fully self-contained — no shared code with `.claude_custom/`. Independence lets each ecosystem evolve without risk. The only meaningful code change is `call_claude()` → `call_agy()` in `common.py`. All other logic is identical.

Install uses symlinks:
- `~/.gemini/antigravity-cli/settings.json` → `.gemini_custom/settings.json`
- `~/.gemini/hooks/` → `.gemini_custom/hooks/`

### Directory layout

```
.gemini_custom/
├── GEMINI.md                   # AGY system prompt (equivalent of CLAUDE.md)
├── settings.json               # AGY CLI settings + hooks config
├── hooks/
│   ├── common.py               # call_agy() instead of call_claude()
│   ├── logger.py               # verbatim copy from .claude_custom
│   ├── notify_slack.sh         # verbatim copy from .claude_custom
│   ├── pre_tool_reviewer.py    # verbatim copy, uses call_agy() via common
│   ├── stop_router.py          # verbatim copy, uses call_agy() via common
│   ├── debug.py                # verbatim copy from .claude_custom
│   ├── pyproject.toml          # Python deps (same as .claude_custom)
│   └── .envrc                  # SLACK_BOT_TOKEN, DEVICE_NAME env vars
└── install.sh                  # symlink setup script
```

## Components

### `common.py` — `call_agy()`

The sole behavioral difference from `.claude_custom/hooks/common.py`. Replaces `call_claude()`:

```python
def call_agy(prompt: str, model: str = "gemini-flash", timeout: int = 60) -> str:
    result = subprocess.run(
        ["agy", "--print", "--model", model],
        input=prompt,
        capture_output=True, text=True, timeout=timeout, check=True
    )
    return result.stdout.strip()
```

Transcript utilities (`read_transcript`, `get_original_user_request`, `get_last_assistant_message`) are copied verbatim — AGY's hook payload uses the same `transcript_path` and `last_assistant_message` fields.

### `settings.json` — Hook configuration

All 6 hooks from `.claude_custom/settings.json`, paths updated to `~/.gemini/hooks/`:

| Hook | Matcher | Command |
|------|---------|---------|
| `Notification` | (all) | `notify_slack.sh` → `claude-code` Slack channel |
| `PreToolUse` | `Bash` | `pre_tool_reviewer.py` via `.venv/bin/python` |
| `Stop` | (all) | `stop_router.py`, timeout 30s, `asyncRewake: true` |
| `PostToolUse` | `Edit\|Write\|Bash` | `code-review-graph update --skip-flows` |
| `UserPromptSubmit` | (all) | `debug.py` |
| `SessionStart` | (all) | `code-review-graph status` |

Slack channel: `claude-code` (same as `.claude_custom` — all AI agent activity in one place).

### `notify_slack.sh` — Slack notification

Identical to `.claude_custom/hooks/notify_slack.sh`. Reads `session_id`, `tool_name`, `message` from stdin JSON. Prepends `[device | tmux_session]` prefix. Posts to `claude-code` channel via `$SLACK_BOT_TOKEN`.

### `pre_tool_reviewer.py` — AI security reviewer

Identical logic to `.claude_custom`. Fast-path rules for always-approve (read tools, safe bash prefixes) and always-block (rm -rf outside safe dirs, curl-pipe, writes to sensitive paths). Falls through to `call_agy()` for ambiguous cases.

### `stop_router.py` — AI auto-proceed router

Identical logic to `.claude_custom`. Reads transcript to get original request and last assistant message. Calls `call_agy()` to decide: `PROCEED` (inject approval context), `ANSWER` (inject answer context), or `HUMAN_NEEDED` (exit 0, hand off). Repeat-detection via temp state file prevents infinite loops.

### `install.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ln -sf "$SCRIPT_DIR/settings.json" "$HOME/.gemini/antigravity-cli/settings.json"
ln -sf "$SCRIPT_DIR/hooks" "$HOME/.gemini/hooks"
cd "$SCRIPT_DIR/hooks" && python3 -m venv .venv && .venv/bin/pip install -q -e .
echo "Done. Verify with: agy /hooks"
```

## Risk: AGY `hooks` key in `settings.json`

The AGY CLI `settings.json` reference does not document a `hooks` key. The superpowers plugin registers hooks via a standalone `hooks.json` in the plugin directory. If AGY does not load hooks from `settings.json`:

- **Fallback:** Extract the `hooks` object into `~/.gemini/antigravity-cli/hooks.json` (same content, extracted). Update `install.sh` to symlink `hooks.json` separately.
- **Detection:** After install, run `agy /hooks` in the CLI. If hooks are not listed, switch to the `hooks.json` fallback.

## Data Flow

```
AGY lifecycle event
    │
    ▼
Hook dispatcher (AGY runtime)
    │
    ├─ Notification ──► notify_slack.sh ──► Slack #claude-code
    │
    ├─ PreToolUse(Bash) ──► pre_tool_reviewer.py
    │                           ├─ fast-path rules → APPROVE/BLOCK
    │                           └─ call_agy() → APPROVE/BLOCK
    │
    ├─ Stop ──► stop_router.py
    │               ├─ static rules → inject context
    │               ├─ call_agy() → PROCEED/ANSWER/HUMAN_NEEDED
    │               └─ repeat detection → exit 0
    │
    ├─ PostToolUse ──► code-review-graph update
    ├─ SessionStart ──► code-review-graph status
    └─ UserPromptSubmit ──► debug.py
```

## Environment Variables

Same as `.claude_custom`:
- `SLACK_BOT_TOKEN` — Slack bot token (from `~/.env.zsh`)
- `DEVICE_NAME` — optional device label for Slack prefix (from `~/.env.zsh`)
