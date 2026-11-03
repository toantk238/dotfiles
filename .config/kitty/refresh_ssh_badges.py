# Kitten: re-check every tab's ssh destination and redraw the host badges
# (tab_bar.py). On-demand fallback for what ssh_tab_watcher.py cannot see.
from kitty.boss import Boss
from kitty.tab_bar import load_custom_draw_tab_module
from kittens.tui.handler import result_handler


def main(args):
    pass


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss: Boss):
    load_custom_draw_tab_module()["refresh_all"]()
