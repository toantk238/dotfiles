# Tab titles, used from kitty.conf as {custom} (kitty calls draw_title).
# Local tmux titles ("<host> ❐ ...") drop the host; remote tabs get a short
# "host" badge, background-colored per host, so ssh tabs stand out. The host
# comes from the remote tmux title, else from the foreground ssh command line.
import os
import re
import socket
import zlib

from kitty.fast_data_types import add_timer, get_boss, remove_timer
from kittens.ssh.utils import get_connection_data

SEP = " ❐ "
LOCAL_HOST = socket.gethostname()
# Badge backgrounds: Monokai's distinct hues, readable with dark bold text on
# both the active (grey) and inactive (dark) tab.
PALETTE = ["f92672", "a6e22e", "66d9ef", "e6db74", "fd971f", "ae81ff"]
BADGE_FG = "272822"
WIDTH = 12


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
# the tab's last title change. Poll destinations and redraw when one changes.
_seen = {}


def _poll(timer_id=None):
    boss = get_boss()
    for tm in boss.all_tab_managers:
        changed = False
        for tab in tm:
            dest = ssh_destination(tab.id)
            if _seen.get(tab.id) != dest:
                _seen[tab.id] = dest
                changed = True
        if changed:
            tm.mark_tab_bar_dirty()


# kitty re-runs this module on config reload; keep a single timer alive.
_boss = get_boss()
if _boss is not None:
    if getattr(_boss, "_ssh_tab_timer", None) is not None:
        remove_timer(_boss._ssh_tab_timer)
    _boss._ssh_tab_timer = add_timer(_poll, 1.0, True)


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


def draw_title(data):
    title, fmt = data["title"], data["fmt"]
    tmux_host, _, rest = title.partition(SEP) if SEP in title else ("", "", title)
    remote = tmux_host if tmux_host and tmux_host != LOCAL_HOST else ""
    if not remote:
        remote = ssh_destination(data["tab_id"])
        # kitten ssh titles the tab with its own command line until the remote sets one.
        if remote and rest.startswith(("ssh ", "kitten")):
            rest = ""
    if not remote:
        return rest
    bg = PALETTE[zlib.crc32(remote.encode()) % len(PALETTE)]
    badge = f"{getattr(fmt.bg, '_' + bg)}{getattr(fmt.fg, '_' + BADGE_FG)}{fmt.bold} {short(remote)} {fmt.nobold}{fmt.bg.tab}{fmt.fg.tab}"
    return f"{badge} {rest}".rstrip()
