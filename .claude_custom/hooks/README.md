# Claude Code hooks

Symlinked to `~/.claude/hooks` and wired up in `../settings.json` /
`../settings.win.json`.

| Hook | Event | What it does |
| --- | --- | --- |
| `pre_tool_reviewer.py` | PreToolUse (all but AskUserQuestion) | Allows every tool call except a few dangerous Bash commands, which need the user's own approval. |
| `ask_user_question_handler.py` | PreToolUse (AskUserQuestion) | Answers Claude's question with Haiku, retrying with Fable plus more context; falls through to the user if neither can answer. |
| `stop_router.py` | Stop | Decides whether Claude should continue: static rules first, then Haiku, then Fable for questions Haiku defers on. Otherwise hands back to the user. |
| `notify_desktop.py` | Notification | Desktop notification; clicking it focuses the tmux pane / kitty window. |
| `notify_slack.sh` | Notification | Posts the notification to Slack (`SLACK_BOT_TOKEN`). |
| `context-mode-cache-heal.mjs` | SessionStart | Repairs the context-mode plugin cache. |
| `debug.py` | (any, wire up by hand) | Dumps the hook payload to `debug_hook.log`. |

Shared code: `common.py` (transcript parsing, `call_claude`), `logger.py`
(per-hook rotating logs, tagged with the answering model inside `model_context`).

```sh
just test       # run the test suite
just tail-log   # follow every hook log
```
