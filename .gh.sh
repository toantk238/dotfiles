# shellcheck shell=bash
# Sourced by zsh (.zshrc); uses zsh-only $funcstack and print -s.

ghcs() {
  # shellcheck disable=SC2154
  local fn_name="${funcstack[1]}"
  TARGET="shell"
  local GH_DEBUG="$GH_DEBUG"
  local GH_HOST="$GH_HOST"

  read -r -d '' __USAGE <<-EOF
	Wrapper around \`gh copilot suggest\` to suggest a command based on a natural language description of the desired output effort.
	Supports executing suggested commands if applicable.

	USAGE
	 $fn_name [flags] <prompt>

	FLAGS
	 -d, --debug           Enable debugging
	 -h, --help            Display help usage
	     --hostname        The GitHub host to use for authentication
	 -t, --target target   Target for suggestion; must be shell, gh, git
	                       default: "$TARGET"

	EXAMPLES

	- Guided experience
	 $ $fn_name

	- Git use cases
	 $ $fn_name -t git "Undo the most recent local commits"
	 $ $fn_name -t git "Clean up local branches"
	 $ $fn_name -t git "Setup LFS for images"

	- Working with the GitHub CLI in the terminal
	 $ $fn_name -t gh "Create pull request"
	 $ $fn_name -t gh "List pull requests waiting for my review"
	 $ $fn_name -t gh "Summarize work I have done in issues and pull requests for promotion"

	- General use cases
	 $ $fn_name "Kill processes holding onto deleted files"
	 $ $fn_name "Test whether there are SSL/TLS issues with github.com"
	 $ $fn_name "Convert SVG to PNG and resize"
	 $ $fn_name "Convert MOV to animated PNG"
	EOF

  local OPT OPTARG OPTIND
  while getopts "dht:-:" OPT; do
    if [ "$OPT" = "-" ]; then   # long option: reformulate OPT and OPTARG
      OPT="${OPTARG%%=*}"       # extract long option name
      OPTARG="${OPTARG#"$OPT"}" # extract long option argument (may be empty)
      OPTARG="${OPTARG#=}"      # if long option argument, remove assigning `=`
    fi

    case "$OPT" in
    debug | d)
      GH_DEBUG=api
      ;;

    help | h)
      echo "$__USAGE"
      return 0
      ;;

    hostname)
      GH_HOST="$OPTARG"
      ;;

    target | t)
      TARGET="$OPTARG"
      ;;
    esac
  done

  # shift so that $@, $1, etc. refer to the non-option arguments
  shift "$((OPTIND - 1))"

  TMPFILE="$(mktemp -t gh-copilotXXXXXX)"
  trap 'rm -f "$TMPFILE"' EXIT
  if GH_DEBUG="$GH_DEBUG" GH_HOST="$GH_HOST" gh copilot suggest -t "$TARGET" "$@" --shell-out "$TMPFILE"; then
    if [ -s "$TMPFILE" ]; then
      FIXED_CMD="$(cat "$TMPFILE")"
      print -s -- "$FIXED_CMD"
      echo
      eval -- "$FIXED_CMD"
    fi
  else
    return 1
  fi
}

ghce() {
  # shellcheck disable=SC2154
  local fn_name="${funcstack[1]}"
  local GH_DEBUG="$GH_DEBUG"
  local GH_HOST="$GH_HOST"

  read -r -d '' __USAGE <<-EOF
	Wrapper around \`gh copilot explain\` to explain a given input command in natural language.

	USAGE
	 $fn_name [flags] <command>

	FLAGS
	 -d, --debug      Enable debugging
	 -h, --help       Display help usage
	     --hostname   The GitHub host to use for authentication

	EXAMPLES

	# View disk usage, sorted by size
	$ $fn_name 'du -sh | sort -h'

	# View git repository history as text graphical representation
	$ $fn_name 'git log --oneline --graph --decorate --all'

	# Remove binary objects larger than 50 megabytes from git history
	$ $fn_name 'bfg --strip-blobs-bigger-than 50M'
	EOF

  local OPT OPTARG OPTIND
  while getopts "dh-:" OPT; do
    if [ "$OPT" = "-" ]; then   # long option: reformulate OPT and OPTARG
      OPT="${OPTARG%%=*}"       # extract long option name
      OPTARG="${OPTARG#"$OPT"}" # extract long option argument (may be empty)
      OPTARG="${OPTARG#=}"      # if long option argument, remove assigning `=`
    fi

    case "$OPT" in
    debug | d)
      GH_DEBUG=api
      ;;

    help | h)
      echo "$__USAGE"
      return 0
      ;;

    hostname)
      GH_HOST="$OPTARG"
      ;;
    esac
  done

  # shift so that $@, $1, etc. refer to the non-option arguments
  shift "$((OPTIND - 1))"

  GH_DEBUG="$GH_DEBUG" GH_HOST="$GH_HOST" gh copilot explain "$@"
}
