#!/usr/bin/env python3
"""
Move Android string resources from one module to another.
Scans every XML file with <string> items in each values folder (not just
strings.xml); the destination file mirrors the source filename (created if
missing, appended otherwise).
Handles all language variants and preserves CDATA sections, special characters.
Uses regex-based approach to preserve exact formatting.
"""

import argparse
from pathlib import Path
import re
import sys
from typing import List, Optional


LANGUAGE_FOLDERS = [
    'values',
    'values-zh',
    'values-zh-rTW',
    'values-vi',
    'values-in',
]


class StringMover:
    """Handles moving string resources between Android modules."""

    def __init__(self, source_module: str, dest_module: str):
        self.source_module = Path(source_module)
        self.dest_module = Path(dest_module)

    def get_res_dir(self, module: Path, lang_folder: str) -> Path:
        """Get the path to the resource folder for a given module and language folder."""
        return module / 'src' / 'main' / 'res' / lang_folder

    def find_source_xml_files(self, lang_folder: str) -> List[Path]:
        """List all XML files in the source language folder that contain <string> items."""
        res_dir = self.get_res_dir(self.source_module, lang_folder)
        if not res_dir.is_dir():
            return []

        xml_files = []
        for xml_file in sorted(res_dir.glob('*.xml')):
            content = self.read_file(xml_file)
            if content and re.search(r'<string\s+name=', content):
                xml_files.append(xml_file)
        return xml_files

    def read_file(self, file_path: Path) -> Optional[str]:
        """Read file content as text."""
        if not file_path.exists():
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading {file_path}: {e}", file=sys.stderr)
            return None

    def write_file(self, file_path: Path, content: str):
        """Write content to file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def find_string_element(self, content: str, key: str) -> Optional[str]:
        """
        Find and extract a string element by key name.
        Returns the matched string element with its exact formatting.
        """
        # Pattern to match <string name="key"...>...</string> including CDATA
        # (?:[ \t]*) captures leading whitespace (indentation)
        # re.DOTALL makes . match newlines for multiline content
        pattern = r'([ \t]*<string\s+name="' + re.escape(key) + r'"[^>]*>.*?</string>[ \t]*\n?)'

        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1)
        return None

    def remove_string_element(self, content: str, key: str) -> Optional[str]:
        """
        Remove a string element from content by key name.
        Returns modified content, or None if key not found.
        """
        pattern = r'[ \t]*<string\s+name="' + re.escape(key) + r'"[^>]*>.*?</string>[ \t]*\n?'

        new_content = re.sub(pattern, '', content, count=1, flags=re.DOTALL)

        # Check if anything was actually removed
        if new_content == content:
            return None

        return new_content

    def insert_string_element(self, content: str, string_element: str) -> str:
        """
        Insert a string element into content before </resources> tag.
        """
        # If content is None or empty, create a new resources structure
        if not content or content.strip() == '':
            return f'''<?xml version="1.0" encoding="utf-8"?>
<resources>
{string_element}</resources>
'''

        # Find the </resources> closing tag
        closing_tag_pattern = r'(</resources>)'
        match = re.search(closing_tag_pattern, content)

        if not match:
            # No closing tag found, append at the end
            return content + string_element

        # Insert before </resources>
        pos = match.start()
        return content[:pos] + string_element + content[pos:]

    def move_key(self, key: str, lang_folder: str) -> Optional[str]:
        """
        Move a single key for a specific language folder.
        Searches every XML file with <string> items in the source folder.
        The destination file keeps the same filename as the source file:
        created if it doesn't exist, appended to otherwise.
        Returns the filename the key was moved in, or None if not found.
        """
        for source_path in self.find_source_xml_files(lang_folder):
            source_content = self.read_file(source_path)
            if source_content is None:
                continue

            # Find the string element in this source file
            string_element = self.find_string_element(source_content, key)
            if string_element is None:
                continue

            # Remove from source
            new_source_content = self.remove_string_element(source_content, key)
            if new_source_content is None:
                continue

            # Destination mirrors the source filename
            dest_path = self.get_res_dir(self.dest_module, lang_folder) / source_path.name

            # Read destination (or create empty)
            dest_content = self.read_file(dest_path)
            if dest_content is None:
                dest_content = '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n</resources>\n'

            # Remove existing key from destination if present (overwrite)
            dest_content = self.remove_string_element(dest_content, key) or dest_content

            # Insert into destination
            new_dest_content = self.insert_string_element(dest_content, string_element)

            # Write both files
            self.write_file(source_path, new_source_content)
            self.write_file(dest_path, new_dest_content)

            return source_path.name

        return None

    def move_keys(self, keys: List[str]):
        """Move multiple keys across all language folders."""
        results = {}

        for key in keys:
            print(f"\n{'='*60}")
            print(f"Moving key: {key}")
            print(f"{'='*60}")

            results[key] = []

            for lang_folder in LANGUAGE_FOLDERS:
                moved_file = self.move_key(key, lang_folder)

                if moved_file:
                    results[key].append(f"{lang_folder}/{moved_file}")
                    print(f"  ✓ {lang_folder:<20} - Moved successfully ({moved_file})")
                else:
                    print(f"  ✗ {lang_folder:<20} - Not found or error")

        # Summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")

        for key, moved_locations in results.items():
            if moved_locations:
                print(f"✓ {key}")
                print(f"  Moved in: {', '.join(moved_locations)}")
            else:
                print(f"✗ {key}")
                print(f"  Not found in any language")


def main():
    parser = argparse.ArgumentParser(
        description='Move Android string resources from one module to another',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Move a single key
  %(prog)s /path/to/source /path/to/dest my_string_key

  # Move multiple keys
  %(prog)s /path/to/source /path/to/dest key1 key2 key3

Language folders handled:
  values, values-zh, values-zh-rTW, values-vi, values-in

All XML files containing <string> items are scanned (not just strings.xml).
The destination file keeps the same filename as the source file: it is
created if missing, otherwise the string is appended to it.

Note: This script preserves CDATA sections and special characters exactly.
"""
    )

    parser.add_argument(
        'source_module',
        help='Path to the source module'
    )

    parser.add_argument(
        'dest_module',
        help='Path to the destination module'
    )

    parser.add_argument(
        'keys',
        nargs='+',
        help='String key(s) to move'
    )

    args = parser.parse_args()

    # Validate paths
    source_path = Path(args.source_module)
    dest_path = Path(args.dest_module)

    if not source_path.exists():
        print(f"Error: Source module path does not exist: {source_path}", file=sys.stderr)
        sys.exit(1)

    # Destination path will be created if needed
    print(f"Source module: {source_path}")
    print(f"Destination module: {dest_path}")
    print(f"Keys to move: {', '.join(args.keys)}")

    # Move keys
    mover = StringMover(args.source_module, args.dest_module)
    mover.move_keys(args.keys)


if __name__ == '__main__':
    main()
