# Kitten: new tab "like this one", placed right after the current tab.
# - kitten ssh tab: open the same ssh connection. kitty's own new_tab_with_cwd
#   only clones ssh when a cwd was reported, which a remote tmux (or a tab
#   started directly as kitten ssh) never does.
# - local tmux tab: start in the active pane's directory. kitty only sees the
#   tmux client's cwd, since tmux doesn't pass the shell's OSC 7 through.
# - anything else: plain new_tab_with_cwd.
import subprocess

from kitty.boss import Boss
from kitty.constants import kitten_exe
from kittens.tui.handler import result_handler


def main(args):
    pass


def ppid(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            return int(f.read().rpartition(")")[2].split()[1])
    except (OSError, ValueError, IndexError):
        return 0


def tmux_pane_path(window_pid):
    # Find the tmux client running inside this kitty window by walking each
    # client's parents up to the window's shell.
    try:
        out = subprocess.run(
            ["tmux", "list-clients", "-F", "#{client_pid} #{pane_current_path}"],
            capture_output=True, text=True, timeout=2,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    for line in out.splitlines():
        pid, _, path = line.partition(" ")
        p = int(pid) if pid.isdigit() else 0
        while p > 1:
            if p == window_pid:
                return path
            p = ppid(p)
    return ""


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss: Boss):
    w = boss.window_id_map.get(target_window_id)
    if w is None:
        boss.new_tab_with_cwd("!neighbor")
        return
    cmd = w.ssh_kitten_cmdline()
    if cmd:
        if cmd[0] == "kitten":
            cmd[0] = kitten_exe()
        boss.launch("--type=tab", "--location=after", *cmd)
        return
    path = tmux_pane_path(w.child.pid)
    if path:
        boss.launch("--type=tab", "--location=after", "--cwd", path)
    else:
        boss.new_tab_with_cwd("!neighbor")
