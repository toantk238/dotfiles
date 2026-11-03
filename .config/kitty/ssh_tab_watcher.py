# Global watcher (kitty.conf: watcher ssh_tab_watcher.py). When shell
# integration reports a command starting or ending in a window, re-check that
# tab's ssh destination so tab_bar.py's host badge updates without polling.
from kitty.fast_data_types import add_timer

# At "start" the shell has not exec'd the command yet; give ssh a moment to
# become the foreground process before looking.
DELAY = 0.3


def on_cmd_startstop(boss, window, data):
    refresh = getattr(boss, "_ssh_tab_refresh", None)
    tab = window.tabref() if refresh else None
    if tab is None:
        return
    tab_id = tab.id
    add_timer(lambda timer_id: refresh(tab_id), DELAY, False)
