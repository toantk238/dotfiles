#!/usr/bin/env zsh
# Open files in nvim inside a new kitty window.
# Used as the Exec of ~/.local/share/applications/nvim-new.desktop (xdg-open / yazi "open").
# Files are passed as separate args so paths with spaces stay intact.

source "$HOME/.all.env"
exec kitty nvim -- "$@"
