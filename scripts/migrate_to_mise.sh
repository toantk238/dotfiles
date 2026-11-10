#!/usr/bin/env bash
# One-off: copy existing nvm/luaenv installs into mise (no re-download),
# build ruby with mise and reinstall the gems you had under rvm.
# Copies (not `mise link`), so the old managers' dirs can be deleted afterwards.
# Run after installing mise. Safe to re-run.
set -euo pipefail
command -v mise >/dev/null || { echo "install mise first: sudo pacman -S mise"; exit 1; }

installs="${MISE_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/mise}/installs"
copy_into_mise() { # <tool> <version> <src dir>
  local dst="$installs/$1/$2"
  [ -e "$dst" ] && return
  mkdir -p "$installs/$1" && cp -a "$3" "$dst" && echo "copied $1@$2"
}
for d in "$HOME"/.nvm/versions/node/v*; do
  [ -d "$d" ] && copy_into_mise node "${d##*/v}" "$d"
done
for d in "$HOME"/.luaenv/versions/*; do
  [ -d "$d" ] && copy_into_mise lua "${d##*/}" "$d"
done
mise reshim

mise install   # anything in ~/.config/mise/config.toml still missing

# Ruby: rvm rubies hard-code their prefix, so mise builds its own; then reinstall
# the gems you had under rvm. Only gems that ship executables (fastlane, pod,
# solargraph, rubocop, ...) and fastlane plugins; their dependencies follow.
ruby_version=$(mise current ruby 2>/dev/null || true)
for rvm_root in /usr/local/rvm "$HOME/.rvm"; do
  gems="$rvm_root/gems/ruby-$ruby_version"
  [ -n "$ruby_version" ] && [ -d "$gems/specifications" ] || continue
  # shellcheck disable=SC2016
  names=$(env -u GEM_HOME -u GEM_PATH mise exec ruby -- ruby -e '
    specs = Dir[File.join(ARGV[0], "specifications", "*.gemspec")].filter_map { |f| Gem::Specification.load(f) }
    puts specs.select { |s| s.executables.any? || s.name.start_with?("fastlane-plugin-") }.map(&:name).uniq
  ' "$gems")
  if [ -n "$names" ]; then
    echo "reinstalling gems from $gems into mise ruby $ruby_version:" $names
    # shellcheck disable=SC2086
    env -u GEM_HOME -u GEM_PATH mise exec ruby -- gem install --conservative --no-document $names
  fi
done
mise reshim

mise ls
echo "Once happy, the old ~/.nvm ~/.goenv ~/.luaenv ~/.rvm dirs can be removed,"
echo "and NVM_LAZY_LOAD dropped from ~/.env.zsh."
if [ -d /usr/local/rvm ]; then
  echo "System-wide rvm: sudo rm -rf /usr/local/rvm /etc/profile.d/rvm.sh /etc/rvmrc && sudo groupdel rvm"
fi
