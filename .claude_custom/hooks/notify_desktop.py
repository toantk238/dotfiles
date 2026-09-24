#!/usr/bin/env python3
"""
Notification hook — show a desktop notification when Claude needs a human.

Clicking the notification brings the terminal back:
  1. tmux: switch the attached client to the session/window/pane running Claude
  2. kitty: focus the kitty tab/window hosting that tmux client and raise its
     OS window (using the notification's xdg-activation token, so it works on
     GNOME Wayland)

The hook itself returns immediately; a detached child process waits for the click.
Skipped when the Claude pane is already focused.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from logger import get_logger

logger = get_logger("notify_desktop")

HOOK_DIR = Path(__file__).resolve().parent
KITTEN = HOOK_DIR / "focus_kitty_window.py"
STATE_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "claude-notify"
WAIT_TIMEOUT_SEC = 3600

TITLES = {
    "permission_prompt": "Claude needs permission",
    "idle_prompt": "Claude is waiting for you",
    "elicitation_dialog": "Claude needs input",
}
SKIP_TYPES = {"auth_success"}


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=5, **kw)


def ppid_and_comm(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None, None
    comm = stat[stat.index("(") + 1 : stat.rindex(")")]
    ppid = int(stat[stat.rindex(")") + 2 :].split()[1])
    return ppid, comm


def find_kitty(pid):
    """Walk ancestors of pid; return (kitty_pid, pid of kitty's direct child)."""
    child = None
    while pid and pid > 1:
        ppid, comm = ppid_and_comm(pid)
        if comm is None:
            return None, None
        if comm == "kitty":
            return pid, child
        child, pid = pid, ppid
    return None, None


def tmux(*args):
    r = run(["tmux", *args])
    return r.stdout.strip() if r.returncode == 0 else ""


def locate_terminal():
    """Return a dict describing where Claude runs: tmux target + kitty window."""
    loc = {}
    pane = os.environ.get("TMUX_PANE")
    start_pid = os.getppid()
    if pane and os.environ.get("TMUX"):
        info = tmux("display-message", "-p", "-t", pane,
                    "#{session_name}\t#{window_active}\t#{pane_active}")
        if info:
            session, win_active, pane_active = info.split("\t")
            loc.update(pane=pane, session=session,
                       pane_visible=win_active == "1" and pane_active == "1")
            clients = tmux("list-clients", "-F",
                           "#{client_activity}\t#{client_pid}\t#{client_tty}\t#{session_name}")
            rows = [c.split("\t") for c in clients.splitlines() if c]
            # prefer a client already on this session, else the most recently active one
            rows.sort(key=lambda r: (r[3] == session, int(r[0] or 0)), reverse=True)
            if rows:
                loc.update(client_tty=rows[0][2], client_on_session=rows[0][3] == session)
                start_pid = int(rows[0][1])
    kitty_pid, shell_pid = find_kitty(start_pid)
    if kitty_pid:
        loc.update(kitty_socket=f"unix:/tmp/kitty-{kitty_pid}", kitty_shell_pid=shell_pid)
    return loc


def kitty_window_focused(loc):
    r = run(["kitty", "@", "--to", loc["kitty_socket"], "ls",
             "--match", f"pid:{loc['kitty_shell_pid']}"])
    if r.returncode != 0:
        return False
    for os_win in json.loads(r.stdout):
        for tab in os_win["tabs"]:
            for w in tab["windows"]:
                if w["pid"] == loc["kitty_shell_pid"]:
                    return os_win.get("is_focused") and w.get("is_focused")
    return False


def already_focused(loc):
    if "kitty_socket" not in loc:
        return False
    if "pane" in loc and not (loc.get("pane_visible") and loc.get("client_on_session")):
        return False
    return kitty_window_focused(loc)


def focus(loc, token):
    if "pane" in loc:
        if loc.get("client_tty"):
            run(["tmux", "switch-client", "-c", loc["client_tty"], "-t", loc["pane"]])
        run(["tmux", "select-window", "-t", loc["pane"]])
        run(["tmux", "select-pane", "-t", loc["pane"]])
    if "kitty_socket" in loc:
        cmd = ["kitty", "@", "--to", loc["kitty_socket"], "kitten",
               "--match", f"pid:{loc['kitty_shell_pid']}", str(KITTEN)]
        if token:
            cmd.append(token)
        r = run(cmd)
        if r.returncode != 0:
            logger.warning("kitty focus failed: %s", r.stderr.strip())


def wait_for_click(payload):
    """Detached child: show the notification, focus the terminal on click."""
    loc, title, body, key = payload["loc"], payload["title"], payload["body"], payload["key"]
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    id_file = STATE_DIR / f"{key}.id"
    token_r, token_w = os.pipe()
    cmd = ["timeout", str(WAIT_TIMEOUT_SEC), "notify-send",
           "--app-name=Claude Code", "--icon=utilities-terminal",
           "--urgency=critical" if payload["critical"] else "--urgency=normal",
           "--hint=string:desktop-entry:kitty",
           "--action=default=Focus terminal", "--print-id",
           f"--activation-token-fd={token_w}"]
    if id_file.exists():
        cmd.append(f"--replace-id={id_file.read_text().strip()}")
    cmd += [title, body]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, pass_fds=(token_w,))
    os.close(token_w)
    notif_id = proc.stdout.readline().strip()
    if notif_id:
        id_file.write_text(notif_id)
    action = proc.stdout.read().strip()
    proc.wait()
    with os.fdopen(token_r) as f:
        token = f.read().strip()
    logger.info("notification %s closed, action=%r token=%s", notif_id, action, bool(token))
    if action == "default":
        focus(loc, token)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--wait-click":
        wait_for_click(json.loads(sys.argv[2]))
        return

    data = json.loads(sys.stdin.read() or "{}")
    ntype = data.get("notification_type", "")
    if ntype in SKIP_TYPES:
        return
    loc = locate_terminal()
    if already_focused(loc):
        logger.info("terminal already focused, skip (%s)", ntype)
        return

    where = loc.get("session") or Path(data.get("cwd") or os.getcwd()).name
    payload = {
        "loc": loc,
        "title": f"{TITLES.get(ntype, 'Claude Code')} · {where}",
        "body": data.get("message", ""),
        "key": data.get("session_id", "default"),
        "critical": ntype == "permission_prompt",
    }
    logger.info("notify %s", payload)
    subprocess.Popen([sys.executable, __file__, "--wait-click", json.dumps(payload)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True, cwd=HOOK_DIR)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("notify_desktop failed")
