#!/usr/bin/env python3
import sys
import base64
import urllib.request
from urllib.parse import urlparse


def convert_to_base64(uri: str) -> str:
    parsed = urlparse(uri)

    if parsed.scheme in ("http", "https"):
        with urllib.request.urlopen(uri) as response:
            data = response.read()
    elif parsed.scheme in ("file", ""):
        path = parsed.path if parsed.scheme == "file" else uri
        with open(path, "rb") as f:
            data = f.read()
    else:
        raise ValueError(f"Unsupported URI scheme: {parsed.scheme!r}")

    return base64.b64encode(data).decode("utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <image-uri>", file=sys.stderr)
        print("  <image-uri>  file path, file:// URI, or http(s):// URL", file=sys.stderr)
        sys.exit(1)

    print(convert_to_base64(sys.argv[1]))
