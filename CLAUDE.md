# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a personal dotfiles repository containing shell configurations, development tools, and utility scripts. The repository is organized modularly with individual configuration files for different tools that are sourced by the main `.zshrc` file.

## Common Development Commands

### Git Tool Development
```bash
# No setup needed: git/gittool re-execs itself via `uv run --project git/`,
# so uv creates/syncs git/.venv on first run. Symlinked to ~/.local/bin/gittool.
gittool sync [path]                 # init submodules, attach detached ones to the main branch
gittool verify_before_push [path]   # clean trees + every submodule commit exists on a remote
gittool merge [path] -b <branch> [--ai TOOL|--no-ai]
#   ff / merge commit. Conflicting submodule pointers keep OURS so the merge commits
#   fast; then each such submodule gets THEIR branch of the same name (fallback: the
#   recorded commit) merged into our branch, recorded as a follow-up commit.
#   File conflicts: interactive --ai TOOL (claude, agy, or GITTOOL_AI_TOOLS names) opens
#   in a tmux split / kitty / gnome-terminal / xterm (GITTOOL_TERMINAL=... or inline)
#   with a prepared prompt; exit the tool and gittool commits. Default: ask when a tty.
gittool resolve_conflicts [path] [--ai TOOL|--no-ai]   # resume: commit + deferred submodule merges
gittool remove_submodules [path] --yes   # destructive: deinit + delete all submodules
# path defaults to cwd. LOG_LEVEL=DEBUG for chatter; file log in ~/.local/state/gittool/

# Tests build real repos with the git CLI under tmp_path
uv run --project git pytest

# Manage deps (pyproject.toml + uv.lock in git/)
uv add --project git <pkg>
```

### System Setup
```bash
# Symlink configs into $HOME (dotbot, idempotent; mapping in install.conf.yaml)
./install.sh

# Install all development tools on Linux (Arch-based)
./scripts/linux.sh

# One-off: move node/lua versions from nvm/luaenv to mise
./scripts/migrate_to_mise.sh

# Set up Lua environment
./luaenv/install.sh
```

### Android Development
```bash
# Connect to Android devices wirelessly
./scripts/adb-wireless-connect.sh

# Mirror all connected Android devices
./scripts/scrcpy_all.sh

# Mount ADB connections
./scripts/mount_adb.sh
```

## Code Architecture

### Configuration Structure
- **`.zshrc`**: Main entry point that sources all other configurations
- **Individual `.zsh` files**: Modular configurations for specific tools (e.g., `.pyenv.zsh`, `.nvm.zsh`, `.git.zsh`)
- **`nvim/`**: Complete Neovim configuration with Vim Plug and CoC.nvim
- **`scripts/`**: Utility scripts for various development tasks

### Git Tool Architecture (`git/` directory)
- **`gittool`**: Main entry point (sh/python polyglot that runs itself via uv)
- **`helper/`**: Core functionality modules (pygit2-based)
  - `big_repo.py`: `BigRepo` — main repo + submodules orchestration; every action returns a bool that becomes the exit code
  - `repo.py`: `GitRepo` wrapper over one `pygit2.Repository` (branch attach, merge/fast-forward, conflict snapshot, submodule update)
  - `ai.py`: AI tool registry (claude, agy, `GITTOOL_AI_TOOLS`), conflict prompt, terminal launcher
  - `utils.py`: branch/status helpers and the interactive `Chooser` (injectable for tests)
  - Deferred submodule merges persist in `.git/gittool-pending-submodules.json` between runs
  - `log.py`: Logging (`LOG_LEVEL`, `GITTOOL_LOG_FILE` env vars)
- **`tests/`**: pytest suite; fixtures in `conftest.py` build bare remotes + a recursive clone
- **Deps**: `pyproject.toml` + `uv.lock` (no PyInstaller build anymore)

### Key Design Patterns
1. **Modular Shell Configuration**: Each tool has its own `.zsh` file that's conditionally sourced
2. **Environment Management**: Uses mise for node/go/lua/ruby (falls back to nvm/goenv/luaenv/rvm when mise is absent) and pyenv for python (pyenv-virtualenv envs)
3. **Tool Integration**: Heavy use of modern CLI tools (fzf, ripgrep, eza, delta) with custom configurations
4. **Script Organization**: Utility scripts grouped by functionality (Android, system, development)

## Development Notes

- The repository uses Oh My Zsh with custom plugins and themes
- Git is configured with IntelliJ IDEA integration and delta for diffs
- Neovim is the primary editor with extensive plugin configuration
- Android development tools are prominently featured with custom scripts
- The custom git tool is a Python script run through uv (no build step)