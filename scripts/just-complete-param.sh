#!/usr/bin/env bash
# Tells the shell which just recipe parameter is being completed, so the
# completion can be typed by parameter name (see .just.sh).
#
# Usage: just-complete-param <words typed so far, excluding "just" and the current word>
# Prints the parameter name, plus a glob on a second line when the parameter
# has a simple `[arg(..., pattern='.*\.ext')]`. Prints nothing when the next
# word is not a parameter value (recipe name, flag value, unknown recipe...).
#
# It mirrors just's own argument grouping (checked against just 1.58):
#   - global flags and `var=value` overrides come before the first recipe
#   - a recipe greedily takes up to all its positional parameters, then the
#     next word starts another recipe; a +/* parameter takes everything left
#   - `[arg(long=/short=)]` parameters are options anywhere after the recipe;
#     with `value=` they are flags and take no value
#   - module recipes as `mod recipe` or `mod::recipe`; aliases
set -uo pipefail

# -f/-d change which justfile gets dumped, so they are needed before the dump.
just_opts=()
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  case ${args[i]} in
    -f|--justfile|-d|--working-directory) just_opts+=("${args[i]}" "${args[i+1]-}"); ((i++)) ;;
    --justfile=*|--working-directory=*) just_opts+=("${args[i]}") ;;
  esac
done

just "${just_opts[@]}" --dump --dump-format json 2>/dev/null |
# Words go through the env: as jq arguments, words like --set would be read
# as jq options.
JCP_WORDS=$(printf '%s\n' "$@") \
jq -r '
  # Global flags taking one value, from `just --help`. --set takes two.
  def value_flags: [
    "--alias-style","--ceiling","--chooser","--color","--command-color",
    "--cygpath","--dotenv-command","-F","--dotenv-filename","-E",
    "--dotenv-path","--dump-format","--evaluate-format","--group",
    "--indentation","--jobs","-f","--justfile","--justfile-name",
    "--list-heading","--list-prefix","--shell","--shell-arg","--tempdir",
    "--timestamp-format","-d","--working-directory"];
  # Flags after which every word is theirs, not a recipe.
  def rest_flags: ["-c","--command","-s","--show","--usage"];

  . as $root
  | def positional($r): [$r.parameters[] | select(.long == null and .short == null)];
    def option($r; $w):
      first($r.parameters[]
        | select(($w | startswith("--")) and .long != null and $w == "--" + .long
              or ($w | startswith("--") | not) and .short != null and $w == "-" + .short));
    # Resolve "a::b::c" from a scope; null when not found.
    def lookup($scope; $path):
      ($path | split("::")) as $segs
      | reduce $segs[:-1][] as $s ($scope; if . == null then null else .modules[$s] end)
      | if . == null then null
        else (.aliases[$segs[-1]].target // $segs[-1]) as $n
          # The dump drops the module from alias targets (`alias x := m::r`
          # shows target "r"), so fall back to the first submodule recipe.
          | if ($n | contains("::")) then lookup(.; $n)
            else .recipes[$n] // first(.modules[]? | .. | objects | .recipes?[$n]? // empty) end
        end;
    # Step the parser one word. State: global flags phase, then recipes.
    def step($w):
      if .done then .
      elif .skip > 0 then .skip -= 1
      elif .recipe == null then
        if .flags and ($w | startswith("-")) then
          if (rest_flags | index($w)) then .done = true | .result = null
          elif $w == "--set" then .skip = 2
          elif (value_flags | index($w)) then .skip = 1
          else . end
        elif .flags and ($w | test("^[A-Za-z_][A-Za-z0-9_-]*=")) then .
        else .flags = false
          | ((.scope.modules[$w]) // null) as $mod
          | if $mod != null then .scope = $mod
            else lookup(.scope; $w) as $r
              | if $r == null then .done = true | .result = null
                else .recipe = $r | .pos = 0 | .pending = null end
            end
        end
      elif .pending != null then .pending = null
      elif ($w | startswith("-")) and option(.recipe; ($w | sub("=.*"; ""))) != null then
        option(.recipe; ($w | sub("=.*"; ""))) as $o
        | if ($w | contains("=")) or $o.value != null then . else .pending = $o end
      else positional(.recipe) as $p
        | if .pos < ($p | length) then .pos += 1
          elif ($p | length) > 0 and $p[-1].kind != "singular" then .
          else .recipe = null | .scope = $root | step($w)   # starts the next recipe
          end
      end;

    reduce ($ENV.JCP_WORDS | split("\n") | map(select(. != "")))[] as $w (
      {flags: true, skip: 0, scope: $root, recipe: null, pending: null, pos: 0, done: false, result: null};
      step($w))
  | if .done or .skip > 0 then empty
    elif .pending != null then .pending
    elif .recipe == null then empty
    else positional(.recipe) as $p
      | if .pos < ($p | length) then $p[.pos]
        elif ($p | length) > 0 and $p[-1].kind != "singular" then $p[-1]
        else empty end
    end
  | .name, ((.pattern // [])[0] // "" | capture("^\\.\\*\\\\\\.(?<e>[A-Za-z0-9]+)$")? | "*." + .e)
'
