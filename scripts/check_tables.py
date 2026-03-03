#!/usr/bin/env python3
"""
check_tables.py — EROFS documentation table checker.

Checks all Markdown files under a given directory for violations of the
on-disk structure table formatting rules:

  Rule 1: Size column must contain a plain byte count, not a C type name.
  Rule 2: Name column must not contain array-length notation like [12].
  Rule 3: Headings must use title case (with exceptions for articles/prepositions).
  Rule 4: ondisk/ files must not mention C struct names (erofs_*) or
          specific tool names (mkfs.erofs, fsck.erofs, dump.erofs, erofsfuse).

Usage:
    python3 check_tables.py <docs-src-dir>

Example:
    python3 check_tables.py /home/user/erofs-docs/src/
"""

import re
import sys
from pathlib import Path

# --- Patterns ---

# C-style type names that are not allowed in the Size column.
C_TYPE_RE = re.compile(
    r"^`?(__le\d+|__be\d+|__u\d+|__s\d+|u\d+|s\d+|uint\d+_t|int\d+_t)`?$",
    re.IGNORECASE,
)

# Array-length notation in the Name column, e.g. uuid[16] or `name[12]`.
ARRAY_NOTATION_RE = re.compile(r"`?\w+\[\d+\]`?")

# Rule 4: C struct names — erofs_<identifier> used as a type/struct name.
# Matches bare words or backtick-quoted identifiers like `erofs_super_block`.
# Excludes occurrences that are part of a URL or file path (contain / or .).
C_STRUCT_RE = re.compile(r"`?(erofs_[a-z][a-z0-9_]*)`?")

# Rule 4: Specific tool names that must not appear in the layout spec.
TOOL_NAME_RE = re.compile(r"\b(mkfs\.erofs|fsck\.erofs|dump\.erofs|erofsfuse)\b")

# Rule 3b: Title case checking.
# Words that may remain lowercase when not the first word of a heading.
LOWERCASE_EXCEPTIONS = frozenset([
    "a", "an", "the",
    "at", "by", "for", "in", "of", "on", "to", "up", "via", "among",
    "and", "but", "or", "nor", "so",
    "vs", "vs.",
])

# Matches a hexadecimal literal like 0x00, 0xFF, 0x1000.
HEX_LITERAL_RE = re.compile(r"^0[xX][0-9A-Fa-f]+$")

# Matches a parenthesised byte-size annotation like (4 bytes) or (16 byte).
BYTE_SIZE_PAREN_RE = re.compile(r"\(\d+\s+bytes?\)", re.IGNORECASE)

# Matches a backtick-quoted span anywhere in a heading token list.
BACKTICK_SPAN_RE = re.compile(r"`[^`]+`")

# Matches a Markdown inline link [text](url) — used to strip the URL part.
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def is_in_ondisk_dir(path):
    """Return True if the file lives under an 'ondisk' directory."""
    return "ondisk" in path.parts


def iter_non_code_lines(lines):
    """
    Yield (1-based lineno, line_text) for lines that are NOT inside a fenced
    code block (``` ... ```).  Also skips Sphinx label lines like (label)=
    at the very start of a file, image references, and lines that are purely
    a hyperlink URL.
    """
    in_fence = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Toggle fenced code block state.
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # Skip Sphinx cross-reference labels, e.g. (erofs_ondisk_format)=
        if stripped.startswith("(") and stripped.endswith(")="):
            continue
        # Skip image references: ![alt](path)
        if stripped.startswith("!["):
            continue
        yield i + 1, line  # 1-based line number


def _is_in_url_or_path(line, match):
    """
    Return True if the match occurs inside a Markdown hyperlink URL or an
    image path, i.e. inside (...) that follows [...].  Also returns True if
    the matched token is part of a longer path (preceded by / or .).
    """
    start = match.start()
    # Check if preceded by / or . (part of a file path or URL segment).
    if start > 0 and line[start - 1] in (".", "/"):
        return True
    # Check if the match is inside a Markdown link destination [text](url).
    # Simple heuristic: find the nearest '(' before the match and check
    # whether there is a matching '](' pattern.
    prefix = line[:start]
    paren_open = prefix.rfind("(")
    bracket_close = prefix.rfind("](")
    if bracket_close != -1 and bracket_close == paren_open - 1:
        return True
    return False


def _normalise_heading(text):
    """
    Prepare heading text for title-case tokenisation:
    1. Replace backtick-quoted spans with spaces (identifiers are exempt).
    2. Replace Markdown inline links [text](url) with just the link text,
       so the URL does not get tokenised as words.
    """
    text = MD_LINK_RE.sub(lambda m: m.group(1), text)
    text = BACKTICK_SPAN_RE.sub(lambda m: " " * len(m.group()), text)
    return text


def check_heading_title_case(path, lines):
    """
    Apply Rule 3b to all Markdown headings in a file.
    Returns a list of violation dicts.
    """
    violations = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        # Extract the heading text (strip leading # and whitespace).
        heading_text = stripped.lstrip("#").strip()
        if not heading_text:
            continue

        # Collect character ranges that are inside a byte-size parenthetical,
        # e.g. "(4 bytes)" — tokens within these ranges are exempt.
        exempt_ranges = []
        for m in BYTE_SIZE_PAREN_RE.finditer(heading_text):
            exempt_ranges.append((m.start(), m.end()))

        # Remove backtick spans and link URLs before tokenising.
        text_for_check = _normalise_heading(heading_text)
        tokens = text_for_check.split()

        # Rebuild token positions so we can check against exempt_ranges.
        # We walk the normalised text to find each token's start offset.
        pos = 0
        for idx, token in enumerate(tokens):
            # Find this token's start in text_for_check.
            token_start = text_for_check.find(token, pos)
            pos = token_start + len(token)

            # Strip surrounding punctuation for the check.
            word = token.strip("()[].,!?;:")
            if not word:
                continue
            # Skip purely non-alphabetic tokens (emoji, numbers, punctuation).
            alpha_chars = [c for c in word if c.isalpha()]
            if not alpha_chars:
                continue
            # Skip hexadecimal literals like 0x00, 0xFF.
            if HEX_LITERAL_RE.match(word):
                continue
            # Skip tokens that fall inside a byte-size parenthetical.
            if any(start <= token_start < end for start, end in exempt_ranges):
                continue
            # Exception words are allowed lowercase unless they are first.
            if idx > 0 and word.lower() in LOWERCASE_EXCEPTIONS:
                continue
            # The first alphabetic character must be uppercase.
            if not alpha_chars[0].isupper():
                violations.append({
                    "rule": "3b",
                    "file": str(path),
                    "line": i + 1,
                    "message": (
                        f'Heading word "{word}" should be capitalised. '
                        f'Heading: "{heading_text}"'
                    ),
                })
    return violations


def check_ondisk_spec(path, lines):
    """
    Apply Rule 4 to a file under src/ondisk/.
    Returns a list of violation dicts.
    """
    # core_ondisk.md is exempt from the C struct name check (Rule 4 exception).
    skip_struct_check = path.name == "core_ondisk.md"

    violations = []
    for lineno, line in iter_non_code_lines(lines):
        # Check for C struct names (unless this file is exempt).
        if not skip_struct_check:
            for m in C_STRUCT_RE.finditer(line):
                # Skip brace-expansion patterns like erofs_inode_{compact,extended}.
                end = m.end()
                if end < len(line) and line[end] == "{":
                    continue
                if not _is_in_url_or_path(line, m):
                    violations.append({
                        "rule": 4,
                        "file": str(path),
                        "line": lineno,
                        "message": (
                            f'"{m.group(1)}" is a C struct name and must not appear '
                            f"in the layout specification."
                        ),
                    })
        # Check for tool names.
        for m in TOOL_NAME_RE.finditer(line):
            violations.append({
                "rule": 4,
                "file": str(path),
                "line": lineno,
                "message": (
                    f'"{m.group(1)}" is an implementation-specific tool name and '
                    f"must not appear in the layout specification."
                ),
            })
    return violations


def parse_table_rows(lines, start_line):
    """
    Given a list of lines and the 0-based index of the header row,
    return (col_indices, data_rows) where:
      col_indices  — dict mapping lowercase column name -> 0-based column index
      data_rows    — list of (1-based line number, list of cell strings)
    """
    header = lines[start_line]
    headers = [h.strip().lower() for h in header.strip().strip("|").split("|")]
    col_indices = {name: idx for idx, name in enumerate(headers)}

    data_rows = []
    i = start_line + 1
    # Skip the separator row (---|---|...)
    if i < len(lines) and re.match(r"^\s*\|?\s*[-:]+\s*\|", lines[i]):
        i += 1
    while i < len(lines):
        line = lines[i]
        if not line.strip().startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        data_rows.append((i + 1, cells))  # 1-based line number
        i += 1
    return col_indices, data_rows


def find_ondisk_tables(lines):
    """
    Scan lines for Markdown table headers that contain both 'size' and 'name'
    columns (case-insensitive). Returns a list of 0-based line indices.
    """
    table_starts = []
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        cols = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if "size" in cols and "name" in cols:
            table_starts.append(i)
    return table_starts


def check_file(path):
    """Check a single Markdown file. Returns a list of violation dicts."""
    violations = []
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    table_starts = find_ondisk_tables(lines)
    for start in table_starts:
        col_indices, data_rows = parse_table_rows(lines, start)
        size_col = col_indices.get("size")
        name_col = col_indices.get("name")

        for lineno, cells in data_rows:
            # Rule 1: Size column must be a plain byte count.
            if size_col is not None and size_col < len(cells):
                size_val = cells[size_col]
                if C_TYPE_RE.match(size_val):
                    violations.append({
                        "rule": 1,
                        "file": str(path),
                        "line": lineno,
                        "message": (
                            f'Size value "{size_val}" looks like a C type name, '
                            f"not a byte count."
                        ),
                    })

            # Rule 2: Name column must not contain array-length notation.
            if name_col is not None and name_col < len(cells):
                name_val = cells[name_col]
                if ARRAY_NOTATION_RE.search(name_val):
                    violations.append({
                        "rule": 2,
                        "file": str(path),
                        "line": lineno,
                        "message": (
                            f'Name value "{name_val}" contains array-length notation. '
                            f"Use bare field name only."
                        ),
                    })

    # Rule 3b: All headings must use title case.
    violations.extend(check_heading_title_case(path, lines))

    # Rule 4: ondisk/ files must not mention C struct names or tool names.
    if is_in_ondisk_dir(path):
        violations.extend(check_ondisk_spec(path, lines))

    return violations, len(table_starts)


def main(src_dir):
    src = Path(src_dir)
    if not src.is_dir():
        print(f"Error: {src_dir} is not a directory.", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(src.rglob("*.md"))
    total_tables = 0
    all_violations = []

    for md_file in md_files:
        violations, n_tables = check_file(md_file)
        total_tables += n_tables
        all_violations.extend(violations)

    # --- Report ---
    print(f"Files scanned  : {len(md_files)}")
    print(f"On-disk tables : {total_tables}")
    print(f"Violations     : {len(all_violations)}")

    if all_violations:
        print()
        for v in all_violations:
            print(f"VIOLATION [Rule {v['rule']}] {v['file']}:{v['line']}")
            print(f"  {v['message']}")
        sys.exit(1)
    else:
        print()
        print("All checks passed.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
