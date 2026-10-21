#!/usr/bin/env python3
DESCRIPTION = """Save and restore whole kitty instances (OS windows, tabs, splits, cwd, programs).

Examples:
  kitty-session dump              # save every kitty instance except the one you run this in
  kitty-session dump --all        # include the current instance too
  kitty-session list              # show what is saved
  kitty-session restore           # relaunch every saved instance (one kitty process each)

Each instance becomes one <dir>/instance-<n>.kitty-session file (default dir:
~/kitty-sessions/saved). The layout comes from `kitty @ ls --output-format session`;
on top of it, the program each window was running (nvim, sesh, tmux, ...) is
saved and, on restore, typed into the window once its shell shows a prompt, so
you land back in that shell when it exits.
A tmux client is restored as `tmux new-session -A` on the session it was showing
at dump time, which re-attaches or recreates it.

The current instance is found by walking up the process tree; from inside tmux
it follows the tmux client of the current session, because the tmux server's
KITTY_* variables point at whichever kitty started the server.
"""
import argparse
import glob
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_DIR = Path.home() / 'kitty-sessions' / 'saved'
UNSERIALIZE_FLAG = 'kitty-unserialize-data='
CMD_VAR = 'kitty_session_cmd'
RESTORE_TIMEOUT = 30  # seconds to wait for restored shells to reach their prompt
SHELLS = {'zsh', 'bash', 'fish', 'sh', 'dash', 'nu', 'xonsh'}


def comm(pid: int) -> str:
    try:
        return Path(f'/proc/{pid}/comm').read_text().strip()
    except OSError:
        return ''


def ppid(pid: int) -> int:
    try:
        stat = Path(f'/proc/{pid}/stat').read_text()
    except OSError:
        return 0
    return int(stat.rsplit(')', 1)[1].split()[1])


def cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f'/proc/{pid}/cmdline').read_bytes()
    except OSError:
        return []
    return [a.decode(errors='replace') for a in raw.split(b'\0') if a]


def children(pid: int) -> list[int]:
    try:
        tasks = Path(f'/proc/{pid}/task').iterdir()
        return [int(c) for t in tasks for c in (t / 'children').read_text().split()]
    except OSError:
        return []


def kitty_ancestor(pid: int) -> int | None:
    while pid > 1:
        name = comm(pid)
        if name == 'kitty':
            return pid
        if name == 'tmux: server':
            # Inside tmux: hop to the client showing our session, it lives in our kitty.
            client = run(['tmux', 'display-message', '-p', '#{client_pid}'])
            return kitty_ancestor(int(client)) if client.isdigit() else None
        pid = ppid(pid)
    return None


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ''


def running_kitties() -> list[int]:
    pids = []
    for sock in glob.glob('/tmp/kitty-*'):
        pid = sock.rsplit('-', 1)[1]
        if pid.isdigit() and comm(int(pid)) == 'kitty':
            pids.append(int(pid))
    return sorted(pids)


def kitty_ls(pid: int, fmt: str) -> str:
    return subprocess.run(
        ['kitty', '@', '--to', f'unix:/tmp/kitty-{pid}', 'ls', '--output-format', fmt],
        capture_output=True, text=True, check=True,
    ).stdout


def tmux_clients() -> dict[int, tuple[str, str]]:
    """client pid -> (session name, session path)"""
    out = run(['tmux', 'list-clients', '-F', '#{client_pid}\t#{session_name}\t#{session_path}'])
    ans = {}
    for line in out.splitlines():
        pid, name, path = line.split('\t')
        ans[int(pid)] = (name, path)
    return ans


def is_shell(argv: list[str]) -> bool:
    return bool(argv) and os.path.basename(argv[0]).lstrip('-') in SHELLS


def startup_command(window: dict, clients: dict[int, tuple[str, str]]) -> str | None:
    """Shell command that brings back what the window was running, None for an idle shell."""
    if not is_shell(window['cmdline']):
        return None  # launched with an explicit program, the native session line already has it
    procs = [(p['pid'], p['cmdline']) for p in window['foreground_processes']]
    if not procs:
        # kitty sometimes reports nothing (e.g. `tmux a`), so look at the shell's children
        procs = [(c, cmdline(c)) for c in children(window['pid'])]
    procs = [(pid, argv) for pid, argv in procs if argv and not is_shell(argv) and pid != window['pid']]
    for pid, _ in procs:
        if pid in clients:
            name, path = clients[pid]
            return shlex.join(['tmux', 'new-session', '-A', '-s', name, '-c', path])
    return shlex.join(procs[0][1]) if procs else None


def map_unserialize_data(text: str, fn) -> str:
    """Rewrite every `launch` line's kitty-unserialize-data dict with fn(data) -> (data, extra launch args)."""
    lines = []
    for line in text.splitlines():
        if line.startswith('launch '):
            args = shlex.split(line[len('launch '):])
            if args and args[0].startswith(UNSERIALIZE_FLAG):
                data, extra = fn(json.loads(args[0][len(UNSERIALIZE_FLAG):]))
                args[0] = UNSERIALIZE_FLAG + json.dumps(data)
                line = 'launch ' + shlex.join(args[:1] + extra + args[1:])
        lines.append(line)
    return '\n'.join(lines) + '\n'


def build_session(pid: int, clients: dict[int, tuple[str, str]]) -> str:
    windows = {
        w['id']: w
        for ow in json.loads(kitty_ls(pid, 'json'))
        for t in ow['tabs']
        for w in t['windows']
    }

    def add_command(data: dict) -> tuple[dict, list[str]]:
        w = windows.get(data.get('id'))
        cmd = startup_command(w, clients) if w else None
        if cmd and not data.get('cmd_at_shell_startup'):
            data['cmd_at_shell_startup'] = cmd
        return data, []

    return map_unserialize_data(kitty_ls(pid, 'session'), add_command)


def as_window_var(data: dict) -> tuple[dict, list[str]]:
    # Don't let shell integration run the command: it does so from zsh's first precmd,
    # inside p10k instant prompt, where tmux fails ("not a terminal") or never draws.
    # Park it in a user var instead and type it once the shell is at its prompt.
    cmd = data.pop('cmd_at_shell_startup', None)
    if isinstance(cmd, list):
        cmd = shlex.join(cmd)
    return data, ['--var', f'{CMD_VAR}={cmd}'] if cmd else []


def type_commands(pids: list[int]) -> None:
    """Send each restored window its saved command as soon as its shell is at a prompt."""
    done: set[tuple[int, int]] = set()
    deadline = time.monotonic() + RESTORE_TIMEOUT
    while time.monotonic() < deadline:
        pending = 0
        for pid in pids:
            try:
                state = json.loads(kitty_ls(pid, 'json'))
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                pending += 1  # socket not up yet
                continue
            for w in (w for ow in state for t in ow['tabs'] for w in t['windows']):
                cmd = w['user_vars'].get(CMD_VAR)
                if not cmd or (pid, w['id']) in done:
                    continue
                if not w['at_prompt']:
                    pending += 1
                    continue
                subprocess.run(
                    ['kitty', '@', '--to', f'unix:/tmp/kitty-{pid}', 'send-text', '--match', f'id:{w["id"]}', '--stdin'],
                    input=cmd + '\r', text=True, check=False,
                )
                done.add((pid, w['id']))
        if not pending:
            return
        time.sleep(0.3)
    print(f'gave up after {RESTORE_TIMEOUT}s on windows whose shell never reached a prompt', file=sys.stderr)


def dump(args: argparse.Namespace) -> None:
    current = None if args.all else kitty_ancestor(os.getpid())
    targets = [p for p in running_kitties() if p != current]
    if not targets:
        sys.exit('No other kitty instance with remote control found.')
    clients = tmux_clients()
    sessions = {p: build_session(p, clients) for p in targets}  # build all before touching old files

    args.dir.mkdir(parents=True, exist_ok=True)
    for old in args.dir.glob('instance-*.kitty-session'):
        old.unlink()
    for n, (pid, text) in enumerate(sessions.items(), 1):
        path = args.dir / f'instance-{n}.kitty-session'
        path.write_text(text)
        print(f'kitty {pid} -> {path}')
    if current:
        print(f'skipped current kitty {current}')


def saved_files(d: Path) -> list[Path]:
    files = sorted(d.glob('instance-*.kitty-session'))
    if not files:
        sys.exit(f'Nothing saved in {d}, run `kitty-session dump` first.')
    return files


def list_saved(args: argparse.Namespace) -> None:
    for f in saved_files(args.dir):
        print(f.name)
        for line in f.read_text().splitlines():
            if line == 'new_tab' or line.startswith('new_os_window'):
                print(f'  {line}')
            elif line.startswith('cd '):
                print(f'    {line}')
            elif line.startswith('launch '):
                arg = shlex.split(line[len('launch '):])[0]
                if arg.startswith(UNSERIALIZE_FLAG):
                    cmd = json.loads(arg[len(UNSERIALIZE_FLAG):]).get('cmd_at_shell_startup')
                    print(f'    run: {cmd or "(shell)"}')
                else:
                    print(f'    {line}')


def restore(args: argparse.Namespace) -> None:
    # Restoring from inside tmux must not leak this pane's tmux into the new instances.
    env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
    pids = []
    for f in saved_files(args.dir):
        session = map_unserialize_data(f.read_text(), as_window_var)
        proc = subprocess.Popen(
            ['kitty', '--session', '-'],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, env=env, text=True,
        )
        with proc.stdin or open(os.devnull, 'w') as stdin:
            stdin.write(session)
        pids.append(proc.pid)
        print(f'started kitty {proc.pid} for {f}')
    type_commands(pids)


def main() -> None:
    if not shutil.which('kitty'):
        sys.exit('kitty not found in PATH')
    parser = argparse.ArgumentParser(description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-d', '--dir', type=Path, default=DEFAULT_DIR, help=f'session directory (default: {DEFAULT_DIR})')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('dump', help='save the other running kitty instances')
    p.add_argument('--all', action='store_true', help='also save the instance this runs in')
    p.set_defaults(func=dump)
    sub.add_parser('restore', help='relaunch every saved instance').set_defaults(func=restore)
    sub.add_parser('list', help='show saved instances').set_defaults(func=list_saved)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
