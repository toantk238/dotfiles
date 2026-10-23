---
name: dotfiles-cross-platform
description: Use when editing this user's dotfiles repo (.zshrc, .*.sh tool files, .config/*, install.conf.yaml, scripts/) or porting a change made on one machine to another, especially anything touching macOS vs Linux paths, Homebrew, clipboard, keybindings, launchctl/systemctl, or kitty config.
---

# Cross-platform dotfiles (macOS + Linux, Windows partial)

## Overview
One `master` branch serves every machine. A change made for one OS must never break another,
so OS differences live in **guards** or **per-OS files**, never in per-OS branches.

## Choose the mechanism

| Situation | Mechanism | Example |
|---|---|---|
| A few lines differ in a shell file | `osis Darwin` / `osis Linux` block | `.ios.sh`, `lctl()` in `.functions.sh` |
| A tool may be missing | `exists <cmd>` guard | `if exists xdg-open; then alias open=xdg-open; fi` |
| Several equivalent tools | `if exists A; elif exists B` chain | clipboard: `pbcopy` → `wl-copy` → `lemonade` in `.forgit.sh` |
| Same tool, different binary name (`fd`/`fdfind`, `bat`/`batcat`) | pick once into a variable: `if exists fd; then _fd=fd; elif exists fdfind; then _fd=fdfind; fi` | — |
| Binary path differs | `command -v`, never hardcode `/usr/bin` or `/opt/homebrew/bin` | `command docker-compose "$@"` |
| Install location differs | try each path with `[ -s path ]` | `_nvm_source` in `.nvm.sh` |
| Tool config supports includes | per-OS file the tool picks itself | kitty: `include ${KITTY_OS}.conf` → `.config/kitty/macos.conf` / `linux.conf` |
| Tool config has no includes | `<name>.linux.<ext>` + `<name>.macos.<ext>`, linked by dotbot `if:` | `.config/lemonade.{linux,macos}.toml` |
| Setup step only makes sense on one OS | guard the dotbot shell command | `'[ "$(uname)" != Linux ] \|\| gnome/apply.sh'` |
| Only this one machine wants it | not here, use **dotfiles-machine-local** | personal font size, tokens |

`osis` and `exists` are defined at the top of `.functions.sh`, which `.zshrc` sources first.

## dotbot per-OS link
A target may appear once per `- link:` block, so use one block per OS:
```yaml
- link:
    ~/.config/foo.toml:
      path: .config/foo.linux.toml
      if: '[ "$(uname)" = Linux ]'
- link:
    ~/.config/foo.toml:
      path: .config/foo.macos.toml
      if: '[ "$(uname)" = Darwin ]'
```
A directory that is already linked whole (`~/.config/kitty`) can't receive per-OS links into it.
Use that tool's own include mechanism instead.

## Adding a new tool file
1. Create `.<tool>.sh` with the body wrapped in `exists <tool>` (or `osis`) so it is a no-op elsewhere.
2. `source "$dot_dir/.<tool>.sh"` in `.zshrc` next to similar tools.
3. Configs go in `.config/<tool>` and get linked in `install.conf.yaml`.

## Verify before committing
- `zsh -n <file>` for every edited shell file. `bash -n` for `scripts/*.sh`.
- kitty: `kitty +runpy "from kitty.config import load_config; o=load_config('.config/kitty/kitty.conf'); print(o.kitty_mod, o.font_family)"`
- dotbot: `HOME=$(mktemp -d) uvx dotbot -d . -c install.conf.yaml --only link` and inspect the links.
- Ask yourself: what does this line do on the *other* OS?

## Common mistakes (all seen in the retired feature/macosx and feature/ios17 branches)
| Mistake | Fix |
|---|---|
| Replacing `kitty_mod ctrl+shift` with `super+shift` in `kitty.conf` | put it in `macos.conf` |
| `editor /opt/homebrew/bin/nvim` in the shared config | per-OS file, or rely on `$EDITOR` |
| Commenting out a function because `/usr/bin/x` is missing on macOS | `command x` / `command -v x` |
| Deleting `source` lines for tools not installed on this machine | guard the tool file with `exists` |
| Unconditional `alias open=xdg-open` (shadows macOS `open`) | `exists xdg-open` guard |
| Keeping an OS branch alive by merging master into it | port to master behind guards, then delete the branch |
