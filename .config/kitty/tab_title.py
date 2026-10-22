# Generates tab_title_template with this machine's hostname (included via geninclude).
# Local tmux titles ("<host> ❐ ...") drop the host; remote ones keep a short,
# colored "@host" tag so ssh tabs stand out.
import socket

host = socket.gethostname()
sep = " ❐ "
rest = f"title.split('{sep}', 1)[1]"
remote = f"(fmt.fg.orange + '@' + title.split('{sep}', 1)[0][:6] + ' ' + {rest} + fmt.fg.tab)"
expr = (
    f"{rest} if title.startswith('{host}{sep}') "
    f"else {remote} if '{sep}' in title "
    f"else title"
)
print(f'tab_title_template "{{index}}: {{{expr}}}"')
