# Kitten: sort the current OS window's tabs, local first, then remote grouped
# by host (alphabetically). Order within a group is kept. Uses the same host
# detection as the tab badges in tab_bar.py.
from kitty.boss import Boss
from kitty.tab_bar import load_custom_draw_tab_module
from kittens.tui.handler import result_handler


def main(args):
    pass


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss: Boss):
    tm = boss.active_tab_manager
    if tm is None or len(tm.tabs) < 2:
        return
    remote_host = load_custom_draw_tab_module()["remote_host"]
    active = tm.active_tab

    def key(tab):
        host = remote_host(tab.title, tab.id)[0].lower()
        return (host != "", host)

    wanted = sorted(tm.tabs, key=key)  # stable: keeps order within a group
    # Swap into place one slot at a time so kitty's C-side tab order stays in sync.
    for i, tab in enumerate(wanted):
        j = tm.tabs.index(tab)
        if j != i:
            tm.swap_tabs(i, j)
    if active is not None:
        tm._set_active_tab(tm.tabs.index(active))
    tm.mark_tab_bar_dirty()
