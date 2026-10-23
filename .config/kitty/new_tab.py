# Kitten: new tab "like this one", placed right after the current tab. When
# the tab runs kitten ssh, open the same ssh connection; otherwise behave like
# new_tab_with_cwd. kitty's own
# new_tab_with_cwd only clones ssh when a cwd was reported, which a remote
# tmux (or a tab started directly as kitten ssh) never does.
from kitty.boss import Boss
from kitty.constants import kitten_exe
from kittens.tui.handler import result_handler


def main(args):
    pass


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss: Boss):
    w = boss.window_id_map.get(target_window_id)
    cmd = w.ssh_kitten_cmdline() if w else []
    if not cmd:
        boss.new_tab_with_cwd("!neighbor")
        return
    if cmd[0] == "kitten":
        cmd[0] = kitten_exe()
    boss.launch("--type=tab", "--location=after", *cmd)
