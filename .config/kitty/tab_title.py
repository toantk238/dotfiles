# Generates tab_title_template with this machine's hostname (included via geninclude).
import socket

host = socket.gethostname()
print(
    "tab_title_template \"{index}: {title.split(' ❐ ', 1)[1] if title.startswith('"
    + host
    + " ❐ ') else ('@' + title.split(' ❐ ', 1)[0][:6] + ' ' + title.split(' ❐ ', 1)[1] if ' ❐ ' in title else title)}\""
)
