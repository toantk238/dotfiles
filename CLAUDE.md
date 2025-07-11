# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a personal dotfiles repository containing shell configurations, development tools, and utility scripts. The repository is organized modularly with individual configuration files for different tools that are sourced by the main `.zshrc` file.

## Common Development Commands

### Git Tool Development
```bash
# Build the custom git helper tool
cd git
pip install -r common/requirements.txt
pyinstaller gittool.spec

# Git tool usage
./dist/gittool sync <path>
./dist/gittool verify_before_push <path>
./dist/gittool merge <path> -b <branch>
./dist/gittool resolve_conflicts <path>
```

### System Setup
```bash
# Install all development tools on Linux (Arch-based)
./scripts/linux.sh

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
- **`gittool.py`**: Main entry point for the custom git helper
- **`common/`**: Core functionality modules
  - `big_repo.py`: Handle large repositories
  - `git_submodule.py`: Submodule management
  - `git_util.py`: Git utilities
  - `log.py`: Logging functionality
- **Build output**: `dist/gittool` (executable), `build/` (temporary files)

### Key Design Patterns
1. **Modular Shell Configuration**: Each tool has its own `.zsh` file that's conditionally sourced
2. **Environment Management**: Uses pyenv, nvm, goenv, and luaenv for language version management
3. **Tool Integration**: Heavy use of modern CLI tools (fzf, ripgrep, eza, delta) with custom configurations
4. **Script Organization**: Utility scripts grouped by functionality (Android, system, development)

## Development Notes

- The repository uses Oh My Zsh with custom plugins and themes
- Git is configured with IntelliJ IDEA integration and delta for diffs
- Neovim is the primary editor with extensive plugin configuration
- Android development tools are prominently featured with custom scripts
- The custom git tool is built with Python and PyInstaller for distribution