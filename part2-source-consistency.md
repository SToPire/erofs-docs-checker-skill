# Part 2: Source Code Consistency Analysis

## Goal

Cross-reference the EROFS documentation against the reference C implementation in
`erofs-utils` to verify that field names, byte sizes, bit-flag values, and prose
descriptions in the docs match what the code actually does.  Report every discrepancy
as a finding for the user to decide on.

---

## Step 1 — Clone erofs-utils

Clone the repository into a temporary directory.  Use the variable `TEMP_DIR` for the
clone root throughout this workflow.

```bash
TEMP_DIR=$(mktemp -d)
git clone git@github.com:erofs/erofs-utils.git "$TEMP_DIR/erofs-utils"
```

If the SSH remote is unavailable, fall back to HTTPS:

```bash
git clone https://github.com/erofs/erofs-utils.git "$TEMP_DIR/erofs-utils"
```

Confirm the clone succeeded before proceeding:

```bash
ls "$TEMP_DIR/erofs-utils/include/erofs/"
```

You should see header files such as `defs.h`, `erofs_fs.h`, and others.

---

## Step 2 — Locate the On-Disk Header

The canonical source of truth for on-disk struct definitions is:

```
$TEMP_DIR/erofs-utils/include/erofs/erofs_fs.h
```

Read this file in full with the `Read` tool.  It contains all `erofs_*` struct
definitions, `#define` constants, and bit-flag macros that the documentation is
supposed to describe.

Also check for any supplementary headers that `erofs_fs.h` includes:

```bash
grep '#include' "$TEMP_DIR/erofs-utils/include/erofs/erofs_fs.h"
```

Read those files too if they define additional on-disk types.

---

## Step 3 — Build a Cross-Reference Map

For each struct defined in `erofs_fs.h`, extract:

| Item | Where to find it |
|------|-----------------|
| Struct name | `struct erofs_*` declaration |
| Field names | Member names inside the struct |
| Field C types | Member type annotations (`__le32`, `__u8`, etc.) |
| Field byte sizes | Derived from C type: `__le16` → 2 bytes, `__le32` → 4 bytes, `__u8` → 1 byte, etc. |
| Bit-flag constants | `#define EROFS_*` macros near the struct |

You do not need to write a script for this — read the header with the `Read` tool and
reason about it directly.

---

## Step 4 — Identify Corresponding Documentation Sections

For each struct found in Step 3, locate the documentation section that describes it.
Use `Grep` to search for the struct's conceptual name across `src/ondisk/*.md`:

```bash
grep -rn "superblock\|super block" src/ondisk/
grep -rn "inode" src/ondisk/
# etc.
```

The documentation will not use the C struct name directly (Rule 4), so match by
concept: `erofs_super_block` → "superblock", `erofs_inode_compact` → "compact inode",
`erofs_dirent` → "directory entry", and so on.

---

## Step 5 — Compare Fields

For each (struct, doc-section) pair identified in Step 4, compare:

### 5a — Field count
Does the number of rows in the documentation table match the number of members in the
C struct?  Flag any mismatch.

### 5b — Field names
Does each `Name` cell in the doc table correspond to a member name in the struct?
Minor differences in naming convention (e.g., `checksum` vs `crc`) are worth flagging
even if not definitive violations.

### 5c — Field sizes
Does each `Size` cell (byte count) in the doc table match the byte width implied by
the C type?

| C type | Expected byte size |
|--------|--------------------|
| `__u8`, `__s8` | 1 |
| `__le16`, `__be16`, `__u16`, `__s16` | 2 |
| `__le32`, `__be32`, `__u32`, `__s32` | 4 |
| `__le64`, `__be64`, `__u64`, `__s64` | 8 |
| `__u8[N]` | N |

Flag any doc size that does not match.

### 5d — Bit-flag values
For fields that have associated bit-flag constants (e.g., `feature_compat`,
`feature_incompat`), verify that the flag names and their numeric values in the
documentation match the `#define` macros in the header.

### 5e — Description plausibility
Read the `Description` cell for each field and ask: does this description make sense
given the field name and size?  Flag anything that seems contradictory or implausible.

---

## Step 6 — Report Findings

Record each discrepancy as:

```
FINDING [Part 2] <doc-file>:<line-or-section>
  Struct: <erofs_struct_name>  Field: <field_name>
  <Clear description of the discrepancy between the doc and the code.>
```

If a struct has no discrepancies, record:

```
FINDING [Part 2] <erofs_struct_name>: OK — doc matches code.
```

**All Part 2 findings are advisory.**  Present them to the user and ask for a decision
before suggesting any edits.

---

## Step 7 — Clean Up (Optional)

If the user does not need the clone for Part 3, remove it:

```bash
rm -rf "$TEMP_DIR/erofs-utils"
```

Otherwise, keep `TEMP_DIR` set for use in Part 3.
