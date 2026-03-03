---
name: erofs-docs-checker
description: Use when editing, reviewing, or validating EROFS on-disk layout documentation (src/ondisk/). Checks table formatting, heading conventions, and semantic consistency. Invoke before committing changes to on-disk format docs.
---

# EROFS Documentation Checker

Verify on-disk layout documentation in `src/ondisk/*.md` files. Report violations with file:line and clear description.

## Part 1: Document Checking

### Rule 1 — Size Column Must Use Byte Counts

Tables with `Size` column must contain plain integers (e.g., `4`, `16`), not C types like `__le32` or `__u8`.

**Check:** Find tables with `Size` column. Flag values matching `__(le|be|u|s)\d+`.

**Violation:**
```
| Size    | Name    |
|---------|---------|
| __le32  | magic   |  ← use "4" instead
```

### Rule 2 — Name Column Must Not Have Array Notation

Tables with `Name` column must not contain `[N]` suffixes (e.g., `uuid[16]`). Size is already in the `Size` column.

**Check:** Find tables with `Name` column. Flag values matching `\w+\[.*\]`.

**Violation:**
```
| Name          |
|---------------|
| `uuid[16]`    |  ← use "`uuid`" instead
```

### Rule 3 — Heading Must Use Title Case

Headings must use title case. Exceptions: articles (`a`, `an`, `the`), short prepositions (`at`, `by`, `for`, `in`, `of`, `on`, `to`, `up`, `via`), conjunctions (`and`, `but`, `or`, `nor`, `so`) when not the first word. Backtick-quoted identifiers, hex literals, and `(N bytes)` annotations are exempt.

**Check:** Find all `#` headings. Split into tokens. Skip backtick-quoted, hex (`0x[0-9A-Fa-f]+`), and parenthetical byte-size tokens. Flag tokens not starting with uppercase (unless exception word).

**Violation:**
```
## inline xattr region layout   ← capitalize each word
```

### Rule 4 — No C Struct Names or Tool Names

Files in `src/ondisk/` must not mention C struct names (`erofs_*`) or tools (`mkfs.erofs`, `fsck.erofs`, `dump.erofs`, `erofsfuse`). Keep spec implementation-neutral.

**Exceptions:** Code blocks, image paths, URLs, Sphinx labels like `(erofs_ondisk_format)=`, and `core_ondisk.md` (bridge file) for struct names only.

**Check:** Scan non-code-block lines in `src/ondisk/*.md`. Flag `erofs_[a-z][a-z0-9_]*` and tool names.

**Violation:**
```
The superblock is defined by `erofs_super_block`.  ← remove struct name
```

### Rule 5 — Semantic Review

Read each file and check:
1. **Accuracy** — Do field descriptions match names/sizes?
2. **Consistency** — Do sections agree on field descriptions?
3. **Completeness** — Are description cells meaningful (not blank/reserved)?
4. **Clarity** — Is prose clear for implementers?
5. **Tone** — Is it spec-like (not tutorial/informal)?

Record as `FINDING [Rule 5] file:section: description` (advisory, not violation).

### Workflow

1. Use `Glob` to find `src/ondisk/*.md`
2. Read each file with `Read`
3. Apply Rules 1-4 (scripted checks)
4. Apply Rule 5 (LLM semantic review)
5. Report summary: total files, violations by rule, findings

### Helper Script

Run `scripts/check_tables.py` in this skill directory:
```bash
python3 scripts/check_tables.py src/ondisk/
```

Or perform checks manually per rules above.

---

## Part 2: Source Code Consistency Analysis

Full specification: **[part2-source-consistency.md](part2-source-consistency.md)**

Cross-references documentation against the reference C implementation in `erofs-utils`, verifying field names, byte sizes, bit-flag values, and description plausibility.

---

## Part 3: Image Build and Binary Verification

Full specification: **[part3-binary-verification.md](part3-binary-verification.md)**

Builds `mkfs.erofs` from source, constructs minimal EROFS images, and uses `hexdump`/`xxd` to verify raw bytes match documentation.
