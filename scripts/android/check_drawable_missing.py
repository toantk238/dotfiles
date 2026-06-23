#!/usr/bin/env python3
"""
Check for image files (.png, .jpg, .webp) that are missing from sibling
density-specific drawable folders in an Android project.

Usage:
    python check_drawable_missing.py <path_to_android_project_or_res_folder>
    python check_drawable_missing.py .   # search from current directory
"""

import sys
import os
from collections import defaultdict

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# Density qualifiers to strip when grouping sibling folders
DENSITY_QUALIFIERS = {
    "ldpi", "mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi", "nodpi", "tvdpi", "anydpi"
}


def get_group_key(folder_name: str) -> str | None:
    """
    Return a group key for a drawable folder by stripping density qualifiers.
    Returns None if the folder is not a drawable folder.

    Examples:
        drawable-hdpi      -> drawable
        drawable-xhdpi     -> drawable
        drawable-night-hdpi -> drawable-night
        drawable           -> drawable
        drawable-v21       -> None (version qualifier only, no density sibling)
        drawable-nodpi     -> drawable  (nodpi is included)
    """
    if not folder_name.startswith("drawable"):
        return None

    parts = folder_name.split("-")
    # parts[0] is always "drawable"
    qualifiers = parts[1:]

    density_found = False
    remaining = []
    for q in qualifiers:
        if q.lower() in DENSITY_QUALIFIERS:
            density_found = True
        else:
            remaining.append(q)

    # Only group folders that contain a density qualifier
    if not density_found and len(qualifiers) > 0:
        return None  # e.g. drawable-v21, drawable-night (no density) — standalone

    return "-".join(["drawable"] + remaining)


def find_res_dirs(root: str) -> list[str]:
    """Walk the tree and return all 'res' directories."""
    res_dirs = []
    for dirpath, dirnames, _ in os.walk(root):
        # Skip hidden dirs and common non-source dirs
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {"build", ".gradle", ".idea", "node_modules"}]
        if os.path.basename(dirpath) == "res":
            res_dirs.append(dirpath)
            dirnames.clear()  # don't recurse further into res/
    return res_dirs


def check_res_dir(res_dir: str) -> list[str]:
    """Return a list of problem descriptions for a single res/ directory."""
    # Map group_key -> { folder_name -> set of image filenames }
    groups: dict[str, dict[str, set[str]]] = defaultdict(dict)

    try:
        entries = os.listdir(res_dir)
    except PermissionError:
        return []

    for entry in entries:
        full_path = os.path.join(res_dir, entry)
        if not os.path.isdir(full_path):
            continue
        key = get_group_key(entry)
        if key is None:
            continue
        images = {
            f for f in os.listdir(full_path)
            if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
        }
        if images:
            groups[key][entry] = images

    problems = []
    for _, folders in groups.items():
        if len(folders) < 2:
            continue  # nothing to compare against

        # Union of all image names across all sibling folders
        all_images: set[str] = set()
        for imgs in folders.values():
            all_images |= imgs

        for folder_name in sorted(folders):
            present = folders[folder_name]
            missing = sorted(all_images - present)
            if missing:
                folder_path = os.path.join(res_dir, folder_name)
                for img in missing:
                    # Find which sibling(s) have it
                    has_it = [f for f, imgs in folders.items() if img in imgs and f != folder_name]
                    problems.append(
                        f"  MISSING  {folder_path}/{img}\n"
                        f"           (present in: {', '.join(sorted(has_it))})"
                    )

    return problems


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    root = os.path.abspath(root)

    if not os.path.isdir(root):
        print(f"Error: '{root}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning: {root}\n")

    # If the user pointed directly at a res/ folder, use it; otherwise find all res/ dirs
    if os.path.basename(root) == "res":
        res_dirs = [root]
    else:
        res_dirs = find_res_dirs(root)

    if not res_dirs:
        print("No res/ directories found.")
        sys.exit(0)

    total_problems = 0
    for res_dir in sorted(res_dirs):
        problems = check_res_dir(res_dir)
        if problems:
            print(f"[{res_dir}]")
            for p in problems:
                print(p)
            print()
            total_problems += len(problems)

    if total_problems == 0:
        print("All drawable folders are consistent. No missing images found.")
    else:
        print(f"Found {total_problems} missing image(s) across {len(res_dirs)} res/ dir(s).")
        sys.exit(1)


if __name__ == "__main__":
    main()
