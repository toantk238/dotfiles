---
name: dotfiles-machine-local
description: Use when a change to this user's dotfiles is wanted on only one machine (a personal font size, work-only alias, API token, host-specific PATH, a tool only installed here), or when tempted to commit a tweak that would change behaviour on the user's other computers.
---

# Machine-local overrides

## Overview
The repo holds what **every** machine should share. Whatever only this one machine wants
lives in untracked files that the shared config loads if they exist.
Committing a single-machine tweak to a shared file changes every other machine's setup.

## Where things go

| Kind of override | File (never committed) | Loaded by |
|---|---|---|
| Secrets, tokens, env vars (`SLACK_WEBHOOK`, `JAVA_HOME`) | `~/.env.zsh` | top of `.zshrc` (and Claude hooks via `source ~/.env.zsh`) |
| Aliases, functions, PATH tweaks that must win | `~/.zshrc.local` | last line of `.zshrc` |
| kitty font size, opacity, extra maps | `~/.config/kitty/local.conf` (gitignored, lives inside the linked dir) | `globinclude local.conf` at the end of `kitty.conf` |
| tmux | `~/.tmux.conf.local` is shared (oh-my-tmux). Put per-host bits behind `if-shell` | oh-my-tmux |
| Claude Code | `~/.claude/settings.local.json`, `~/.claude/CLAUDE.md` (not linked) | Claude Code |

These files may not exist yet. Create them (`touch ~/.zshrc.local`; `chmod 600 ~/.env.zsh` because it holds secrets).
They live outside the repo, except `kitty/local.conf`, which is covered by `.gitignore`.

## Decide: shared or local?
- Every machine of that OS wants it → shared, guarded per **dotfiles-cross-platform**.
- Only this machine, or it holds a secret or a host name → local file above.
- Unsure → local. Promoting it to shared later is easy. Undoing a global change on another machine is not.

## Common mistakes
| Mistake | Fix |
|---|---|
| A token pasted into `.functions.sh` or `settings.json` | `~/.env.zsh`, then reference `$VAR` |
| A personal font change in `kitty.conf` | `~/.config/kitty/local.conf` |
| A long-lived branch per machine (`feature/macosx`) | shared changes guarded on master, the rest local |
| Defining an alias in `~/.env.zsh` that `.functions.sh` then overrides | aliases go in `~/.zshrc.local`, which loads last |
