# Claude Code profiles: run claude with separate logins/state per profile.
#
# Each profile is a CLAUDE_CONFIG_DIR under ~/.claude-profiles/<name>. It owns
# its own .credentials.json (the Claude login AND MCP OAuth logins such as
# Figma/Atlassian/Slack) and .claude.json (account + UI state). Two profiles
# may log in to the same Claude account: each /login is its own OAuth grant.
#
# Two modes:
#   shared (default)  everything in CLAUDE_PROFILE_SHARED links back to
#                     ~/.claude: same settings, hooks, skills, plugins, memory,
#                     chat history; user-scope MCP servers copied per launch.
#   custom            only .claude_custom is installed, from the ~/.claude/*
#                     entries in install.conf.yaml (same mapping as dotbot),
#                     plus MCP servers via .claude_custom/install-mcp.py.
#                     Own history/memory; CLAUDE_PROFILE_CUSTOM_SHARED
#                     (default: plugins) still links to ~/.claude.
#
#   claude-profile new work [--custom]  create a profile
#   claude-profile setup work           (re)install .claude_custom into it,
#                                       switching it to custom mode
#   claude-profile setup --all          re-apply to every custom profile
#                                       (./install.sh runs this)
#   claude-profile work [args...]       run claude in it (alias: ccp work)
#   claude-profile use work             pin it to this dir: .envrc + direnv allow
#   claude-profile ls                   list profiles, mode, login, MCP logins
#   claude-profile rm work              delete a profile (asks first)
#
# `claude` / `c` follow $CLAUDE_PROFILE, which direnv sets on cd via
# `use claude_profile <name>` (.config/direnv/direnvrc), so plain `c` inside a
# pinned tree runs that profile. `ccp <name>` overrides it for one run.
# First run of a profile: /login, then /mcp -> figma -> Authenticate. Both
# persist in that profile only. "default" means plain ~/.claude.
#
# <profile>/profile.env (plain KEY=VALUE lines, no quotes/spaces) is exported for that profile by the
# claude wrapper and by direnv. New profiles get
# ENABLE_CLAUDEAI_MCP_SERVERS=false: claude.ai connectors (incl. Figma) belong
# to the Claude *account*, so a profile sharing an account would otherwise see
# the default profile's Figma connection instead of its own plugin login.

: "${CLAUDE_PROFILE_ROOT:=$HOME/.claude-profiles}"
CLAUDE_PROFILE_SHARED=(
  settings.json settings.local.json CLAUDE.md
  agents hooks skills commands output-styles plugins
  projects file-history plans todos history.jsonl
)
(( ${+CLAUDE_PROFILE_CUSTOM_SHARED} )) || CLAUDE_PROFILE_CUSTOM_SHARED=(plugins)
_claude_profile_dotdir="${${(%):-%x}:A:h}"
_claude_profile_env_default='# KEY=VALUE, exported when claude runs in this profile.
# claude.ai connectors follow the Claude account, not the profile: keep them
# off so MCP logins (Figma, ...) come only from this profile.
ENABLE_CLAUDEAI_MCP_SERVERS=false'

_claude_profile_mode() {
  [[ -f "$1/.profile-mode" ]] && print -r -- "$(<"$1/.profile-mode")" || print shared
}

# ln -s $1 $2 unless it is already that link; never clobbers real files.
_claude_profile_ln() {
  local src="$1" dst="$2"
  if [[ -L "$dst" ]]; then
    [[ "$(readlink "$dst")" == "$src" ]] && return 0
    rm -f -- "$dst"
  elif [[ -e "$dst" ]]; then
    print -u2 "claude-profile: $dst exists and is not a link; leaving it"
    return 0
  fi
  mkdir -p -- "${dst:h}" && ln -s -- "$src" "$dst"
}

# "<path under ~/.claude>\t<absolute source>" for each ~/.claude/* link in
# install.conf.yaml, so profiles get exactly what install.sh gives ~/.claude.
_claude_profile_custom_links() {
  local line conf="$_claude_profile_dotdir/install.conf.yaml"
  while IFS= read -r line; do
    [[ "$line" =~ '^[[:space:]]+~/\.claude/([^:[:space:]]+):[[:space:]]*([^[:space:]#]+)' ]] || continue
    print -r -- "${match[1]}"$'\t'"$_claude_profile_dotdir/${match[2]}"
  done < "$conf"
}

_claude_profile_link() {
  local dir="$1" mode item rel src dst
  mkdir -p -- "$dir" && chmod 700 "$dir" || return
  [[ -e "$dir/profile.env" ]] || print -r -- "$_claude_profile_env_default" > "$dir/profile.env"
  mode="$(_claude_profile_mode "$dir")"
  if [[ "$mode" == shared ]]; then
    for item in "${CLAUDE_PROFILE_SHARED[@]}"; do
      src="$HOME/.claude/$item"
      [[ -e "$src" || -L "$src" ]] && _claude_profile_ln "$src" "$dir/$item"
    done
    return 0
  fi
  # custom: drop shared-mode links into ~/.claude that this mode doesn't keep
  for dst in "$dir"/*(N@) "$dir"/.*(N@); do
    [[ "$(readlink "$dst")" == "$HOME/.claude/"* ]] || continue
    (( ${CLAUDE_PROFILE_CUSTOM_SHARED[(Ie)${dst:t}]} )) || rm -f -- "$dst"
  done
  for item in "${CLAUDE_PROFILE_CUSTOM_SHARED[@]}"; do
    src="$HOME/.claude/$item"
    [[ -e "$src" || -L "$src" ]] && _claude_profile_ln "$src" "$dir/$item"
  done
  while IFS=$'\t' read -r rel src; do
    [[ -e "$src" ]] || { print -u2 "claude-profile: missing $src"; continue }
    _claude_profile_ln "$src" "$dir/$rel"
  done < <(_claude_profile_custom_links)
}

# Per launch: copy onboarding flags so a new profile skips the intro, and in
# shared mode mirror user-scope MCP servers (claude mcp add -s user) from
# ~/.claude.json. OAuth tokens for them stay per profile either way.
_claude_profile_sync_state() {
  python3 - "$HOME/.claude.json" "$1/.claude.json" "$(_claude_profile_mode "$1")" <<'PY'
import json, os, sys
src, dst, mode = sys.argv[1:]
def load(p):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}
base, prof = load(src), load(dst)
new = dict(prof)
if mode == "shared":
    new["mcpServers"] = base.get("mcpServers", {})
for k in ("hasCompletedOnboarding", "lastOnboardingVersion", "theme"):
    if k in base and k not in new:
        new[k] = base[k]
if new != prof:
    tmp = dst + ".tmp"
    with open(tmp, "w") as f:
        json.dump(new, f, indent=2)
    os.replace(tmp, dst)
PY
}

# Switch a profile to custom mode and install .claude_custom + MCP servers.
_claude_profile_setup() {
  local dir="$1"
  mkdir -p -- "$dir" && chmod 700 "$dir" || return
  if [[ "$(_claude_profile_mode "$dir")" == shared && -f "$dir/.claude.json" ]]; then
    # Servers mirrored from ~/.claude.json; custom mode installs its own.
    python3 -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); d.pop("mcpServers",None); json.dump(d,open(p,"w"),indent=2)' "$dir/.claude.json"
  fi
  print custom > "$dir/.profile-mode"
  _claude_profile_link "$dir" && _claude_profile_sync_state "$dir" || return
  if [[ -f "$_claude_profile_dotdir/.claude_custom/.local.mcp.json" ]]; then
    CLAUDE_CONFIG_DIR="$dir" python3 "$_claude_profile_dotdir/.claude_custom/install-mcp.py" >/dev/null \
      && print "  mcp servers installed from .claude_custom/.local.mcp.json" \
      || print -u2 "claude-profile: install-mcp.py failed (see .claude_custom/install-mcp.log)"
  else
    print -u2 "claude-profile: no .claude_custom/.local.mcp.json on this machine; skipped MCP servers"
  fi
  print "  linked:"
  find "$dir" -type l -printf '    %P -> %l\n' | sort
}

# $1 = config dir, $2 = its .claude.json (default profile keeps it in $HOME).
_claude_profile_who() {
  python3 - "${2:-$1/.claude.json}" "$1/.credentials.json" <<'PY'
import json, sys
def load(p):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}
acct = load(sys.argv[1]).get("oauthAccount") or {}
mcp = load(sys.argv[2]).get("mcpOAuth") or {}
names = sorted({k.split("|")[0].split(":")[-1] for k, v in mcp.items()
                if isinstance(v, dict) and v.get("accessToken")})
print(f"{acct.get('emailAddress', '(not logged in)'):<32} mcp: {', '.join(names) or '-'}")
PY
}

# Called by the claude() wrapper in .claude.sh. Maps $CLAUDE_PROFILE (set by
# direnv `use claude_profile <name>`, or by `claude-profile <name>`) to its
# config dir and prints it; prints nothing for "default"/unset. A profile
# named for the first time is created on the spot (shared mode).
_claude_profile_dir() {
  local name="$CLAUDE_PROFILE" dir
  [[ -z "$name" || "$name" == default ]] && return 0
  dir="$CLAUDE_PROFILE_ROOT/$name"
  [[ -d "$dir" ]] || print -u2 "claude-profile: creating profile '$name' ($dir)"
  _claude_profile_link "$dir" && _claude_profile_sync_state "$dir" || return
  print -r -- "$dir"
}

_claude_profile_valid_name() {
  if [[ ! "$1" =~ '^[A-Za-z0-9_.-]+$' ]] || [[ "$1" == (default|ls|list|new|add|rm|remove|use|setup|help) ]]; then
    print -u2 "claude-profile: bad profile name '$1' (letters, digits, . _ -; not a subcommand name)"
    return 1
  fi
}

claude-profile() {
  local cmd="${1:-ls}" name dir
  case "$cmd" in
    -h|--help|help)
      sed -n '/^# Claude Code profiles/,/^$/p' "$_claude_profile_dotdir/.claude-profile.sh" | sed 's/^# \{0,1\}//'
      ;;
    ls|list)
      printf '%-12s %-7s ' default -; _claude_profile_who "$HOME/.claude" "$HOME/.claude.json"
      for dir in "$CLAUDE_PROFILE_ROOT"/*(N/); do
        printf '%-12s %-7s ' "${dir:t}" "$(_claude_profile_mode "$dir")"; _claude_profile_who "$dir"
      done
      ;;
    new|add)
      name="$2"
      _claude_profile_valid_name "$name" || return
      dir="$CLAUDE_PROFILE_ROOT/$name"
      if [[ "$3" == --custom ]]; then
        _claude_profile_setup "$dir" || return
      else
        _claude_profile_link "$dir" && _claude_profile_sync_state "$dir" || return
      fi
      print "profile '$name' ready ($(_claude_profile_mode "$dir")): $dir"
      print "next: claude-profile $name   then /login and /mcp -> figma -> Authenticate"
      ;;
    setup)
      name="$2"
      if [[ "$name" == --all ]]; then
        # Re-apply to every custom profile (install.sh runs this).
        local -i n=0
        for dir in "$CLAUDE_PROFILE_ROOT"/*(N/); do
          [[ "$(_claude_profile_mode "$dir")" == custom ]] || continue
          print "${dir:t}:"; _claude_profile_setup "$dir" >/dev/null || return; (( n++ ))
        done
        print "$n custom profile(s) updated"
        return
      fi
      _claude_profile_valid_name "$name" || return
      dir="$CLAUDE_PROFILE_ROOT/$name"
      _claude_profile_setup "$dir" || return
      print "profile '$name' set up from .claude_custom: $dir"
      ;;
    rm|remove)
      name="$2"; dir="$CLAUDE_PROFILE_ROOT/$name"
      if [[ -z "$name" || ! -d "$dir" ]]; then
        print -u2 "claude-profile: no profile '$name'"; return 1
      fi
      read -q "?Delete profile '$name' (its logins and state; shared files are untouched)? [y/N] " || { print; return 1 }
      print
      # Remove the links first so nothing they point at can be followed.
      find "$dir" -type l -delete && rm -rf -- "$dir"
      ;;
    use)
      # Pin a profile to the current directory tree via direnv.
      name="$2"
      if [[ -z "$name" ]]; then
        print -u2 "usage: claude-profile use <name|default>"; return 1
      fi
      if [[ "$name" != default && ! -d "$CLAUDE_PROFILE_ROOT/$name" ]]; then
        print -u2 "claude-profile: no profile '$name' (create it: claude-profile new $name)"
        return 1
      fi
      local envrc="$PWD/.envrc"
      if [[ -f "$envrc" ]] && grep -q '^use claude_profile ' "$envrc"; then
        sed -i "s/^use claude_profile .*/use claude_profile $name/" "$envrc"
      else
        print -r -- "use claude_profile $name" >> "$envrc"
      fi
      print "$envrc: use claude_profile $name"
      (( $+commands[direnv] )) && direnv allow "$PWD"
      ;;
    *)
      name="$cmd"; shift
      if [[ "$name" != default && ! -d "$CLAUDE_PROFILE_ROOT/$name" ]]; then
        print -u2 "claude-profile: no profile '$name' (create it: claude-profile new $name)"
        return 1
      fi
      CLAUDE_PROFILE="$name" claude "$@"
      ;;
  esac
}

alias ccp="claude-profile"

_claude_profile_complete() {
  local -a profiles
  profiles=(default "$CLAUDE_PROFILE_ROOT"/*(N/:t))
  if (( CURRENT == 2 )); then
    _alternatives \
      'commands:command:((ls\:"list profiles" new\:"create a profile" setup\:"install .claude_custom into a profile" rm\:"delete a profile" use\:"pin a profile to this dir (direnv)" help\:"show usage"))' \
      "profiles:profile:(${profiles[*]})"
  elif (( CURRENT == 3 )) && [[ "${words[2]}" == (rm|remove) ]]; then
    _values profile "${profiles[@]:#default}"
  elif (( CURRENT == 3 )) && [[ "${words[2]}" == setup ]]; then
    _values profile --all "${profiles[@]:#default}"
  elif (( CURRENT == 3 )) && [[ "${words[2]}" == use ]]; then
    _values profile "${profiles[@]}"
  elif (( CURRENT == 4 )) && [[ "${words[2]}" == (new|add) ]]; then
    _values option --custom
  else
    _normal
  fi
}
(( $+functions[compdef] )) && compdef _claude_profile_complete claude-profile
