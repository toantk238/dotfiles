# Tab titles, used from kitty.conf as {custom} (kitty calls draw_title).
# Local tmux titles ("<host> ❐ ...") drop the host; remote tabs get a short
# "host" badge, background-colored per host, so ssh tabs stand out. The host
# comes from the remote tmux title, else from the foreground ssh command line.
import os
import re
import socket
import zlib

from kitty.fast_data_types import get_boss, get_options, remove_timer, wcswidth
from kitty.child import process_data_cache
from kittens.ssh.utils import get_connection_data

SEP = " ❐ "
LOCAL_HOST = socket.gethostname()
# Badge backgrounds: Monokai's distinct hues, readable with dark bold text on
# both the active and inactive tab.
PALETTE = ["f92672", "a6e22e", "66d9ef", "e6db74", "fd971f", "ae81ff"]
BADGE_FG = "272822"
WIDTH = 12
# A remote tmux window named after the shell ("13 ● 1 zsh") adds nothing, nor
# does the window index left dangling once it is gone.
SHELL_SUFFIX = re.compile(r"(\s+●\s+\d+)?\s+(zsh|bash|fish|sh)$")


def ssh_destination(tab_id):
    tab = get_boss().tab_for_id(tab_id)
    w = tab.active_window if tab else None
    if w is None:
        return ""
    for p in w.child.foreground_processes:
        cmd = list(p["cmdline"] or ())
        if cmd and os.path.basename(cmd[0]).lower() == "ssh":
            # kitten ssh runs "ssh ... -- user@host <bootstrap>"; plain ssh is parsed.
            if "--" in cmd[:-1]:
                dest = cmd[cmd.index("--") + 1]
            else:
                conn = get_connection_data(cmd)
                dest = conn.hostname if conn else "ssh"
            return dest.rpartition("@")[2]
    return ""


# The tab bar only redraws on title/focus changes, but ssh often starts after
# the tab's last title change. ssh_tab_watcher.py re-checks a tab when a command
# starts or ends in it (shell integration). Anything it misses (ssh run inside
# local tmux, windows opened before the watcher was loaded) is fixed on demand
# with the refresh_ssh_badges.py kitten (ctrl+alt+b): nothing polls.
#
# kitty runs this file more than once (config reload, and kittens such as
# sort_tabs.py load it via load_custom_draw_tab_module), each time in a fresh
# namespace. State lives on boss so every copy reads and updates the same dicts.
_boss = get_boss()
_state = _boss.__dict__.setdefault("_ssh_tab_state", {}) if _boss is not None else {}
# Tab id -> ssh destination ("" when local), as last checked.
_seen = _state.setdefault("seen", {})
# Badge color per open remote host (palette index). Hosts keep their hashed
# color while it is free and otherwise take an unused one, so open hosts only
# share a color once there are more hosts than palette entries.
_colors = _state.setdefault("colors", {})


def _hash_color(host):
    return zlib.crc32(host.encode()) % len(PALETTE)


def _assign_colors(hosts):
    old = dict(_colors)
    for h in list(_colors):
        if h not in hosts:
            del _colors[h]
    for h in hosts:
        if h in _colors:
            continue
        used = set(_colors.values())
        free = [i for i in range(len(PALETTE)) if i not in used]
        pref = _hash_color(h)
        _colors[h] = pref if pref in free or not free else free[0]
    return _colors != old


def _update(tabs):
    """Re-check ssh destinations of `tabs`, then recolor and redraw as needed."""
    boss = get_boss()
    # Each foreground_processes call scans all of /proc on kitty's main thread
    # (~15ms with ~1500 processes); share one scan across the tabs checked.
    prev = process_data_cache.start_caching(refresh=True)
    try:
        for tab in tabs:
            dest = ssh_destination(tab.id)
            if _seen.get(tab.id) != dest:
                _seen[tab.id] = dest
                tm = tab.tab_manager_ref()
                if tm is not None:
                    tm.mark_tab_bar_dirty()
    finally:
        process_data_cache.stop_caching(prev)
    # Hosts come from titles and the cached destinations: no further scans.
    hosts = []
    for tm in boss.all_tab_managers:
        for tab in tm:
            host = remote_host(tab.title, tab.id)[0]
            if host and host not in hosts:
                hosts.append(host)
    if _assign_colors(hosts):
        for tm in boss.all_tab_managers:
            tm.mark_tab_bar_dirty()


def refresh_all():
    _update([tab for tm in get_boss().all_tab_managers for tab in tm])


def refresh_tab(tab_id):
    tab = get_boss().tab_for_id(tab_id)
    if tab is not None:
        _update([tab])


# Drop the poll timer older versions of this file started, and hand the
# watcher refresh_tab (any copy works: they share _state).
if _boss is not None:
    if getattr(_boss, "_ssh_tab_timer", None) is not None:
        remove_timer(_boss._ssh_tab_timer)
        _boss._ssh_tab_timer = None
    _boss._ssh_tab_refresh = refresh_tab


def short(host):
    # IPs stay whole; hostnames lose their domain and, past WIDTH chars, keep
    # the start plus a short trailing "-segment" ("MobileH…mini").
    if host.replace(".", "").isdigit():
        return host
    name = host.split(".")[0]
    if len(name) <= WIDTH:
        return name
    tail = re.split("[-_]", name)[-1]
    if 0 < len(tail) <= 5 and tail != name:
        return name[: WIDTH - 1 - len(tail)] + "…" + tail
    return name[: WIDTH - 1] + "…"


def remote_host(title, tab_id):
    """Return (remote host or "" when local, title without the host prefix)."""
    tmux_host, _, rest = title.partition(SEP) if SEP in title else ("", "", title)
    remote = tmux_host if tmux_host and tmux_host != LOCAL_HOST else ""
    if not remote:
        # Use the destination last checked: draw_title runs on every tab bar
        # redraw and must not scan /proc itself.
        remote = _seen[tab_id] if tab_id in _seen else ssh_destination(tab_id)
        # kitten ssh titles the tab with its own command line until the remote sets one.
        if remote and rest.startswith(("ssh ", "kitten")):
            rest = ""
    return remote, rest


def fit(text, width):
    """Shorten text to `width` cells, cutting more from the left than the right:
    the end (window, path, branch) is usually the most specific part."""
    if width <= 0:
        return ""
    if wcswidth(text) <= width:
        return text
    if width == 1:
        return "…"
    head_w = (width - 1) // 3
    head, used = "", 0
    for ch in text:
        if used + wcswidth(ch) > head_w:
            break
        head += ch
        used += wcswidth(ch)
    tail, used = "", wcswidth(head) + 1
    for ch in reversed(text):
        if used + wcswidth(ch) > width:
            break
        tail = ch + tail
        used += wcswidth(ch)
    return f"{head.rstrip()}…{tail.lstrip()}"


def draw_title(data):
    fmt = data["fmt"]
    remote, rest = remote_host(data["title"], data["tab_id"])
    # Room left after the template's "{index}: " prefix and the spaces the
    # separator style pads each tab with (the edge spaces of tab_separator).
    sep = get_options().tab_separator
    pad = len(sep) - len(sep.strip(" "))
    limit = data["max_title_length"]
    room = limit - pad - len(f"{data['index']}: ") if limit > 0 else 0
    if not remote:
        return fit(rest, room) if room else rest
    label = short(remote)
    rest = SHELL_SUFFIX.sub("", rest)
    if room:
        rest = fit(rest, room - wcswidth(label) - 3)  # badge padding + gap
    color = PALETTE[_colors.get(remote, _hash_color(remote))]
    badge = f"{getattr(fmt.bg, '_' + color)}{getattr(fmt.fg, '_' + BADGE_FG)}{fmt.bold} {label} {fmt.nobold}{fmt.bg.tab}{fmt.fg.tab}"
    # Inactive tabs also show the title in the host color; on the active tab's
    # lighter background red/purple get too low-contrast, so it keeps the default.
    if rest and not _is_active(data["tab_id"]):
        rest = f"{getattr(fmt.fg, '_' + color)}{rest}{fmt.fg.tab}"
    return f"{badge} {rest}".rstrip()


def _is_active(tab_id):
    tab = get_boss().tab_for_id(tab_id)
    tm = tab.tab_manager_ref() if tab else None
    return tm is not None and tm.active_tab is tab
