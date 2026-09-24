#!/bin/zsh
#
#export FZF_DEFAULT_COMMAND="rg --no-ignore --hidden --files -g '!.git/' "
# One exclusion per line - add/remove entries here
FZF_EXCLUDES=(
  .git
  .gradle
  .transforms
  .idea
  node_modules
  __pycache__
  .mypy_cache
  Localizable.strings
  Generated
  # build # Android build folder
)

FZF_DEFAULT_COMMAND="fd --type f -HI"
for ex in "${FZF_EXCLUDES[@]}"; do
  FZF_DEFAULT_COMMAND+=" --exclude $ex"
done
export FZF_DEFAULT_COMMAND

export FZF_DEFAULT_OPTS='--height 70% --layout=reverse --border'

export FZF_ALT_C_COMMAND='fd --type directory'

export RG_FZF_OPTS=$(
  cat <<END
-i \\
-g '!Pods/' \\
-g '!Text.swift' \\
-g '!*.pbxproj' \\
-g '!DerivedData/' \\
-g '!Localizable.strings' \\
-g '!Generated/'
END
)

# Usage:
#   rgf <keywords...>                   search all files (unchanged behaviour)
#   rgf <file-filter> <keywords...>     search only files whose path matches <file-filter>
#
# <file-filter> may be either:
#   - a glob  (contains * ? or { and no regex-only chars), e.g. '*.kt'  'src/**/*.swift'
#     -> passed to ripgrep's -g, so '*.kt' matches at any depth
#   - a regex (anything else),                            e.g. '\.kt$'  '^scripts/'  'ViewModel'
#     -> matched case-insensitively against the relative path
# Pass '' as <file-filter> to search all files while still using the two-arg form.
function rgf() {
  local file_filter="" pattern file_cmd
  if (($# >= 2)); then
    file_filter="$1"
    shift
  fi
  pattern="$*"

  if [[ -n "$file_filter" ]]; then
    if [[ "$file_filter" == *[\*\?\{]* && "$file_filter" != *[\\\^\$\+\(\)\|]* ]]; then
      # Glob: let ripgrep filter while listing files.
      file_cmd="rg --files -g \"${file_filter}\" $RG_FZF_OPTS"
    else
      # Regex: list files, then keep only paths matching the regex.
      file_cmd="rg --files $RG_FZF_OPTS | rg -i \"${file_filter}\""
    fi
    # Grep the keywords inside the selected files only.
    rg_cmd=$(
      cat <<END
$file_cmd | \\
xargs -r -d '\\n' rg --color=always --line-number --with-filename \\
--no-heading "${pattern}" \\
$RG_FZF_OPTS
END
    )
  else
    rg_cmd=$(
      cat <<END
rg --color=always --line-number \\
--no-heading "${pattern}" \\
$RG_FZF_OPTS
END
    )
  fi
  fzf_cmd=$(
    cat <<END
fzf --ansi \\
            --color "hl:-1:underline,hl+:-1:underline:reverse" \\
            --delimiter : \\
            --preview 'bat --color=always {1} --highlight-line {2}' \\
            --preview-window 'up,60%,border-bottom,+{2}+3/3,~3' \\
            --bind 'ctrl-w:unix-word-rubout+top,ctrl-u:unix-line-discard+top' \\
            --bind 'change:top' \\
      --bind 'enter:become(nvim {1} +{2})'
END
  )

  full_cmd=$(
    cat <<END
$rg_cmd |
$fzf_cmd
END
  )
  eval "$full_cmd"
}
