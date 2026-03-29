#!/usr/bin/env python
"""
XML Unescape & Pretty Print Tool
- Reads from Wayland clipboard (wl-paste)
- Unescapes multi-level XML entities
- Properly formats and indents XML using lxml
- Outputs with syntax highlighting
"""

import html
import subprocess
import sys
import re

try:
    from lxml import etree
    HAS_LXML = True
except ImportError:
    HAS_LXML = False


# ============================================
# ANSI Colors
# ============================================
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    TAG = "\033[38;5;81m"         # Cyan
    BRACKET = "\033[38;5;245m"   # Gray
    ATTR_NAME = "\033[38;5;215m" # Orange
    ATTR_VAL = "\033[38;5;150m"  # Green
    TEXT = "\033[38;5;223m"      # Light yellow
    DECL = "\033[38;5;140m"      # Purple


def get_clipboard() -> str:
    """Read clipboard using wl-paste"""
    try:
        result = subprocess.run(
            ["wl-paste", "--no-newline"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except FileNotFoundError:
        print(f"\033[31mError: wl-paste not found. Install: sudo apt install wl-clipboard\033[0m")
        sys.exit(1)
    except subprocess.CalledProcessError:
        print(f"\033[31mError: Clipboard empty\033[0m")
        sys.exit(1)


def unescape(text: str) -> str:
    """Unescape HTML entities until stable"""
    prev = None
    while prev != text:
        prev = text
        text = html.unescape(text)
    return text


def format_xml_lxml(xml_str: str) -> str:
    """Format XML using lxml (best quality)"""
    try:
        # Parse with recovery mode for malformed XML
        parser = etree.XMLParser(remove_blank_text=True, recover=True)
        root = etree.fromstring(xml_str.encode('utf-8'), parser)
        return etree.tostring(root, pretty_print=True, encoding='unicode', xml_declaration=True)
    except Exception as e:
        print(f"\033[33mWarning: lxml parse failed: {e}\033[0m")
        return None


def format_xml_manual(xml_str: str) -> str:
    """Format XML manually with regex (fallback)"""
    
    # Normalize whitespace
    xml_str = xml_str.strip()
    
    # Tokenize: split into tags and text
    tokens = re.split(r'(<[^>]+>)', xml_str)
    tokens = [t for t in tokens if t.strip()]
    
    result = []
    indent = 0
    
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        
        # XML declaration
        if token.startswith('<?'):
            result.append(token)
        
        # Closing tag
        elif token.startswith('</'):
            indent = max(0, indent - 1)
            result.append('  ' * indent + token)
        
        # Self-closing tag
        elif token.endswith('/>'):
            result.append('  ' * indent + token)
        
        # Opening tag
        elif token.startswith('<'):
            result.append('  ' * indent + token)
            indent += 1
        
        # Text content
        else:
            # Check if previous was opening tag - inline text
            if result and not result[-1].strip().endswith('>'):
                result[-1] += token
            else:
                # Put text on same line as previous opening tag
                if result:
                    last = result[-1]
                    if re.search(r'<[^/][^>]*>$', last.strip()):
                        result[-1] = last + token
                        indent -= 1  # Will be followed by closing tag
                        continue
                result.append('  ' * indent + token)
    
    return '\n'.join(result)


def format_xml_regex(xml_str: str) -> str:
    """Better regex-based XML formatter"""
    
    xml_str = xml_str.strip()
    
    # Step 1: Remove all existing whitespace between tags
    xml_str = re.sub(r'>\s+<', '><', xml_str)
    
    # Step 2: Insert newlines
    xml_str = re.sub(r'(<[^>]+>)', r'\n\1\n', xml_str)
    
    # Step 3: Split and clean
    lines = [l.strip() for l in xml_str.split('\n') if l.strip()]
    
    # Step 4: Merge text with tags (e.g., <tag>text</tag> on one line)
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Opening tag followed by text followed by closing tag
        if (i + 2 < len(lines) and 
            re.match(r'^<[^/?!][^>]*>$', line) and  # opening tag
            not lines[i+1].startswith('<') and      # text
            re.match(r'^</', lines[i+2])):          # closing tag
            
            merged.append(line + lines[i+1] + lines[i+2])
            i += 3
        else:
            merged.append(line)
            i += 1
    
    # Step 5: Indent
    result = []
    indent = 0
    
    for line in merged:
        # Closing tag or self-contained line with closing
        if line.startswith('</'):
            indent = max(0, indent - 1)
            result.append('  ' * indent + line)
        
        # Self-closing tag or declaration
        elif line.startswith('<?') or line.endswith('/>'):
            result.append('  ' * indent + line)
        
        # Line with opening and closing tag (e.g., <tag>text</tag>)
        elif re.match(r'^<[^/][^>]*>.*</[^>]+>$', line):
            result.append('  ' * indent + line)
        
        # Opening tag only
        elif line.startswith('<'):
            result.append('  ' * indent + line)
            indent += 1
        
        # Text only
        else:
            result.append('  ' * indent + line)
    
    return '\n'.join(result)


def format_xml(xml_str: str) -> str:
    """Format XML with best available method"""
    
    if HAS_LXML:
        result = format_xml_lxml(xml_str)
        if result:
            return result
    
    return format_xml_regex(xml_str)


def colorize(xml_str: str) -> str:
    """Add syntax highlighting"""
    
    # XML declaration
    xml_str = re.sub(
        r'(<\?xml[^?]*\?>)',
        f'{C.DECL}\\1{C.RESET}',
        xml_str
    )
    
    # Attributes: name="value"
    def color_attrs(match):
        name = match.group(1)
        eq = match.group(2)
        val = match.group(3)
        return f'{C.ATTR_NAME}{name}{C.RESET}{C.BRACKET}{eq}{C.RESET}{C.ATTR_VAL}{val}{C.RESET}'
    
    xml_str = re.sub(r'(\s[\w:-]+)(=)("[^"]*"|\'[^\']*\')', color_attrs, xml_str)
    
    # Tags: <tag> </tag> <tag/>
    def color_tag(match):
        full = match.group(0)
        
        # Extract parts
        m = re.match(r'^(<)(/?)([\w:-]+)(.*?)(>)$', full, re.DOTALL)
        if not m:
            return full
        
        b1, slash, name, rest, b2 = m.groups()
        
        return f'{C.BRACKET}{b1}{slash}{C.RESET}{C.TAG}{C.BOLD}{name}{C.RESET}{rest}{C.BRACKET}{b2}{C.RESET}'
    
    xml_str = re.sub(r'</?[\w:-]+[^>]*/?>', color_tag, xml_str)
    
    # Text content between > and 
    xml_str = re.sub(
        r'(>)([^<]+)(<)',
        f'\\1{C.TEXT}\\2{C.RESET}\\3',
        xml_str
    )
    
    return xml_str


def main():
    print(f"\n{C.BOLD}\033[36m══════ XML Unescape Tool ══════{C.RESET}\n")
    
    # Read clipboard
    raw = get_clipboard()
    print(f"\033[90mRead {len(raw)} chars from clipboard{C.RESET}")
    
    # Unescape
    print(f"\033[90mUnescaping...{C.RESET}")
    unescaped = unescape(raw)
    
    # Format
    print(f"\033[90mFormatting...{C.RESET}")
    if HAS_LXML:
        print(f"\033[90mUsing lxml{C.RESET}")
    else:
        print(f"\033[33mTip: Install lxml for better formatting: pip install lxml{C.RESET}")
    
    formatted = format_xml(unescaped)
    
    # Colorize and output
    print(f"\n{C.BOLD}\033[36m══════ Result ══════{C.RESET}\n")
    print(colorize(formatted))
    
    # Stats
    print(f"\n\033[90m{'─' * 40}{C.RESET}")
    print(f"\033[90m{len(raw)} chars → {len(formatted)} chars, {formatted.count(chr(10))+1} lines{C.RESET}")


if __name__ == "__main__":
    main()
