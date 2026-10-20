#!/usr/bin/env python3
DESCRIPTION = """Render every ```mermaid block of a markdown file to an image with mmdc.

Examples:
  mermaid_render README.md                    # dark theme, PNGs in README_mermaid/
  mermaid_render README.md --theme light -o img/
  mermaid_render README.md --format svg
  mermaid_render README.md --markdown README.rendered.md   # copy with blocks replaced by images
  mermaid_render README.md --transparent      # no background (default: the theme's own)

Images are named <stem>-<n>.<format>, numbered from 1 in document order. Same
themes as the nvim inline renderer (nvchad_starter lua/my/mermaid_inline.lua):
a high-contrast dark theme, and mermaid's default theme for light. Fills set in
the diagram itself get a readable text color for the theme.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# keep in sync with M.opts.config in nvchad_starter lua/my/mermaid_inline.lua
CONFIG = {
    "dark": {
        "theme": "base",
        "themeVariables": {
            "darkMode": True,
            "background": "#1e1e2e",
            "primaryColor": "#313244",
            "primaryTextColor": "#ffffff",
            "primaryBorderColor": "#89b4fa",
            "secondaryColor": "#45475a",
            "tertiaryColor": "#1e1e2e",
            "lineColor": "#cdd6f4",
            "textColor": "#ffffff",
            "nodeTextColor": "#ffffff",
            "titleColor": "#f9e2af",
            "clusterBkg": "#181825",
            "clusterBorder": "#6c7086",
            "edgeLabelBackground": "#11111b",
            "doneTaskBkgColor": "#585b70",  # gantt; the derived one is light grey under white text
            "doneTaskBorderColor": "#a6adc8",
        },
    },
    "light": {"theme": "default"},
}
BACKGROUND = {"dark": "#1e1e2e", "light": "#ffffff"}

FENCE_OPEN = re.compile(r"^\s*(`{3,})\s*mermaid\s*$")
FENCE_CLOSE = re.compile(r"^\s*(`{3,})\s*$")


def is_dark(r, g, b):
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128


def parse_color(s):
    """r, g, b of a "#rgb" / "#rrggbb" / "rgb(r, g, b)" color; None for anything else (named colors, ...)"""
    m = re.fullmatch(r"#([0-9a-fA-F]+)", s)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return None
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", s)
    if m:
        return tuple(int(x) for x in m.groups())
    return None


def adapt_colors(src, mode):
    """Colors set in the diagram itself ignore the theme's text color, so e.g. a light `style ... fill:`
    would get white text in dark mode. Give such fills a readable text color, and fade sequence
    `rect`/`box` backgrounds that clash with the theme (their text is the theme's)."""
    lines = src.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"\s*([A-Za-z]+)\s", line)
        kw = m and m.group(1)
        if kw in ("style", "classDef") and not re.search(r"[\s,;]color\s*:", line):
            fill = re.search(r"fill\s*:\s*(rgba?\([^)]*\)|#[0-9a-fA-F]+)", line)
            rgb = fill and parse_color(fill.group(1))
            if rgb:
                lines[i] = re.sub(r"[\s;]*$", "", line) + ",color:" + ("#fff" if is_dark(*rgb) else "#000")
        elif kw in ("rect", "box"):
            m = re.match(r"(\s*[A-Za-z]+\s+)rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)[^)]*\)(.*)$", line)
            if m:
                pre, r, g, b, post = m.groups()
                if is_dark(int(r), int(g), int(b)) != (mode == "dark"):
                    lines[i] = f"{pre}rgba({r}, {g}, {b}, 0.2){post}"
    return "\n".join(lines)


def find_blocks(lines):
    """[(start, end, src)]: 0-indexed rows of the ```mermaid fence and the closing fence, and the source between"""
    blocks, start = [], None
    for i, line in enumerate(lines):
        if start is None and FENCE_OPEN.match(line):
            start = i
        elif start is not None and FENCE_CLOSE.match(line):
            blocks.append((start, i, "\n".join(lines[start + 1 : i])))
            start = None
    return blocks


def render(src, out, config_file, args, tmp):
    """None on success, else mmdc's error message"""
    inp = Path(tmp) / (out.stem + ".mmd")
    inp.write_text(src)
    bg = "transparent" if args.transparent else BACKGROUND[args.theme]
    cmd = ["mmdc", "-q", "-i", str(inp), "-o", str(out), "-c", str(config_file), "-b", bg]
    if args.format == "png":
        cmd += ["-s", str(args.scale)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        return None
    err = res.stderr or res.stdout
    m = re.search(r"Error[^\n]*", err)
    return m.group(0) if m else err.strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path, help="markdown file")
    ap.add_argument("-t", "--theme", choices=("dark", "light"), default="dark", help="default: dark")
    ap.add_argument("-o", "--out-dir", type=Path, help="default: <stem>_mermaid/ next to the file")
    ap.add_argument("-f", "--format", choices=("png", "svg", "pdf"), default="png", help="default: png")
    ap.add_argument("-s", "--scale", type=int, default=3, help="png scale factor, keeps text sharp (default: 3)")
    ap.add_argument("--font-size", type=int, default=20, help="px (default: 20, mermaid's own is 16)")
    ap.add_argument("--transparent", action="store_true", help="transparent background")
    ap.add_argument("-m", "--markdown", type=Path, help="also write a copy of the markdown with blocks replaced by images")
    ap.add_argument("-j", "--jobs", type=int, default=4, help="parallel mmdc runs (default: 4)")
    args = ap.parse_args(argv)

    if not shutil.which("mmdc"):
        sys.exit("mermaid_render: mmdc not found (npm i -g @mermaid-js/mermaid-cli)")
    if not args.file.is_file():
        sys.exit(f"mermaid_render: {args.file}: no such file")

    lines = args.file.read_text().split("\n")
    blocks = find_blocks(lines)
    if not blocks:
        print(f"{args.file}: no mermaid blocks", file=sys.stderr)
        return 0

    stem = args.file.stem
    out_dir = args.out_dir or args.file.parent / f"{stem}_mermaid"
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = [out_dir / f"{stem}-{n}.{args.format}" for n in range(1, len(blocks) + 1)]

    config = json.loads(json.dumps(CONFIG[args.theme]))
    config.setdefault("themeVariables", {})["fontSize"] = f"{args.font_size}px"

    with tempfile.TemporaryDirectory(prefix="mermaid_render.") as tmp:
        config_file = Path(tmp) / "config.json"
        config_file.write_text(json.dumps(config))
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            errors = list(
                pool.map(
                    lambda b, out: render(adapt_colors(b[2], args.theme), out, config_file, args, tmp),
                    blocks,
                    outs,
                )
            )

    failed = 0
    for (start, _, _), out, err in zip(blocks, outs, errors):
        if err:
            failed += 1
            print(f"{args.file}:{start + 1}: {err}", file=sys.stderr)
        else:
            print(out)

    if args.markdown:
        result, prev = [], 0
        for (start, end, _), out, err in zip(blocks, outs, errors):
            result += lines[prev:start]
            if err:  # keep the source of blocks that failed to render
                result += lines[start : end + 1]
            else:
                rel = Path(os.path.relpath(out.resolve(), args.markdown.parent.resolve()))
                result.append(f"![mermaid diagram {out.stem.rsplit('-', 1)[1]}]({rel.as_posix()})")
            prev = end + 1
        result += lines[prev:]
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text("\n".join(result))
        print(args.markdown)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
