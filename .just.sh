#compdef just
source <(JUST_COMPLETE=zsh just)

# Typed completion for recipe parameters. just has no parameter types, so the
# type comes from the parameter name, or from a simple
# `[arg("p", pattern='.*\.ext')]`. just-complete-param (scripts/) works out
# which parameter is being typed; anything else goes to just's own completer.
_just_typed() {
  [[ $PREFIX == -* ]] && { _clap_dynamic_completer_just "$@"; return }
  local -a out=("${(@f)$(just-complete-param "${(@Q)words[2,CURRENT-1]}")}")
  local pname=${out[1]-} glob=${out[2]-}
  # Per-project values, e.g. from a direnv .envrc:
  #   export JUST_COMPLETE_request="$PWD/requests/*.ts(N:t:r)"
  # One variable per parameter; space-separated globs or words are merged.
  local spec_var=JUST_COMPLETE_${pname//-/_}
  if [[ -n $pname && -n ${(P)spec_var-} ]]; then
    local -a vals=( ${=~${(P)spec_var}} )
    compadd -a vals; return
  fi
  if [[ -n $glob ]]; then _files -g "$glob"; return; fi
  case $pname in
    *_dir|*_dirs)          _files -/ ;;
    *_apk)                 _files -g '*.apk' ;;
    *_file|*_files|*_path) _files ;;
    *)                     _clap_dynamic_completer_just "$@" ;;
  esac
}
compdef _just_typed just
