---
name: justfile-param-completion
description: How zsh Tab-completion of just recipe parameters works in this user's setup (dotfiles .just.sh + just-complete-param). Use when adding or renaming Justfile recipe parameters, when a recipe argument should complete to files/dirs/fixed values, or when debugging `just <recipe> <Tab>`.
---

# Typed completion for Justfile recipe parameters

just has no parameter types. In this setup, the *type* of a recipe parameter
is inferred so `just <recipe> <Tab>` offers the right values.

## Where it lives (dotfiles repo)

- `.just.sh` — zsh wrapper `_just_typed`, `compdef`'d over just's own clap
  completer (`_clap_dynamic_completer_just`, which is the fallback).
- `scripts/just-complete-param.sh` (on PATH as `just-complete-param`) —
  given the words typed so far, prints the parameter name being completed
  (+ a glob line for simple `pattern=`). Mirrors just's argument grouping:
  global flags/overrides, greedy multi-recipe, modules, aliases,
  `[arg(long=/short=)]` options.

## How a parameter gets its completion (first match wins)

1. **Per-project env var** `JUST_COMPLETE_<param>` (hyphens → `_`), usually
   set in the project's direnv `.envrc`. Value = space-separated zsh globs
   and/or plain words, all merged:
   ```sh
   export JUST_COMPLETE_request="$PWD/requests/*.ts(N:t:r)"
   export JUST_COMPLETE_env="dev staging prod"
   ```
   Use `$PWD/...` (absolute, works from subfolders) and `(N)` on every glob
   (else a non-matching glob is offered literally). No spaces inside a glob.
2. **`[arg("p", pattern='.*\.ext')]`** — completes `*.ext` files; just also
   validates it at run time. Only the simple `.*\.ext` form maps to a glob.
3. **Name suffix**: `*_dir`/`*_dirs` → dirs, `*_apk` → `*.apk`,
   `*_file`/`*_files`/`*_path` → any file.
4. Otherwise just's own completer (recipes, files, flags).

## Rules when writing a Justfile

- Name parameters by their type (`config_file`, `out_dir`, `release_apk`)
  so completion works with no extra setup.
- For a value set specific to one repo (e.g. request names), do NOT add a
  case to the dotfiles `.just.sh`; add `JUST_COMPLETE_<param>` to that
  repo's `.envrc` (then `direnv allow`). Dotfiles stay project-agnostic.
- Renaming a parameter means renaming its `JUST_COMPLETE_<param>` too.

## Known limits

- No matching files → zsh shows all files.
- Module aliases: the dump drops the module from the target, so the first
  submodule recipe with that name is used.
- New value-taking global flags in future just versions must be added to
  `value_flags` in the helper.
