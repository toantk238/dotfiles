"""
Kitty kitten: focus a kitty window and raise its OS window.

Invoked by notify_desktop.py via:
  kitty @ --to <socket> kitten --match pid:<shell_pid> focus_kitty_window.py [activation_token]

Unlike `kitty @ focus-window`, this passes the xdg-activation token received from
the notification click, so GNOME/Wayland actually raises the window instead of
showing a "kitty is ready" notice.
"""


def main(args):
    pass


def handle_result(args, answer, target_window_id, boss):
    from kitty.fast_data_types import focus_os_window

    token = args[1] if len(args) > 1 else ""
    window = boss.window_id_map.get(target_window_id)
    if window is None:
        return
    boss.set_active_window(window, switch_os_window_if_needed=False)
    focus_os_window(window.os_window_id, True, token)


handle_result.no_ui = True
