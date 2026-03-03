# Part 3: Image Build and Binary Verification

## Goal

Build `mkfs.erofs` from the cloned `erofs-utils` source, construct minimal EROFS
images that exercise specific documented features, then use `hexdump` (or `xxd`) to
read raw bytes from those images and verify that the on-disk layout matches what the
documentation describes.  Report every discrepancy as a finding for the user to decide
on.

---

## Prerequisites

This part assumes `TEMP_DIR` is already set and `erofs-utils` has been cloned there
(see Part 2, Step 1).  If starting fresh:

```bash
TEMP_DIR=$(mktemp -d)
git clone git@github.com:erofs/erofs-utils.git "$TEMP_DIR/erofs-utils"
```

---

## Step 1 — Build mkfs.erofs

```bash
cd "$TEMP_DIR/erofs-utils"
./autogen.sh
./configure
make -j$(nproc)
```

Confirm the binary was produced:

```bash
ls -lh "$TEMP_DIR/erofs-utils/mkfs/mkfs.erofs"
```

If `./autogen.sh` is missing, try `autoreconf -fi` instead.  If `./configure` fails
due to missing dependencies, install them (e.g., `liblz4-dev`, `libzstd-dev`,
`liblzma-dev`) and re-run.

---

## Step 2 — Read the Man Page

Before constructing any image, read the man page to understand the available options:

```bash
man "$TEMP_DIR/erofs-utils/man/mkfs.erofs.1"
```

Or read it directly with the `Read` tool:

```
Read: $TEMP_DIR/erofs-utils/man/mkfs.erofs.1
```

Pay attention to:
- How to set the block size (`-b`)
- How to enable/disable specific features (`--features`)
- How to create an image from a directory (`mkfs.erofs <image> <source-dir>`)

---

## Step 3 — Identify What to Verify

Before building any image, decide which documented fields or structures you want to
verify.  Good candidates are:

| Structure | Key fields to verify |
|-----------|---------------------|
| Superblock | `magic`, `checksum`, `blkszbits`, `root_nid`, `inos`, `build_time` |
| Compact inode | `i_format`, `i_xattr_icount`, `i_mode`, `i_nlink`, `i_size` |
| Extended inode | same fields plus `i_uid`, `i_gid`, `i_mtime` |
| Directory entry | `nid`, `nameoff`, `file_type` |

Choose at least the superblock for every verification run, as it is always present at
a fixed offset.

---

## Step 4 — Prepare a Minimal Source Directory

Create a minimal directory tree to pack into the image.  Keep it small so the layout
is predictable:

```bash
SRCDIR=$(mktemp -d)
echo "hello" > "$SRCDIR/hello.txt"
mkdir "$SRCDIR/subdir"
echo "world" > "$SRCDIR/subdir/world.txt"
```

---

## Step 5 — Build the Image

```bash
IMAGE="$TEMP_DIR/test.erofs"
"$TEMP_DIR/erofs-utils/mkfs/mkfs.erofs" "$IMAGE" "$SRCDIR"
```

Note the exact command line used — it determines which features are active and
therefore which parts of the layout are exercised.

To test a specific feature, pass the appropriate flag.  For example, to enable
chunk-based files:

```bash
"$TEMP_DIR/erofs-utils/mkfs/mkfs.erofs" --features=chunked-file "$IMAGE" "$SRCDIR"
```

---

## Step 6 — Verify the Superblock

The EROFS superblock is located at byte offset **1024** (0x400) from the start of the
image.  Its documented size is 128 bytes.

### 6a — Dump the superblock region

```bash
hexdump -C -s 1024 -n 128 "$IMAGE"
```

Or with `xxd`:

```bash
xxd -s 1024 -l 128 "$IMAGE"
```

### 6b — Check the magic number

According to the documentation, the first 4 bytes of the superblock (offset 0x400–0x403)
must be the EROFS magic: `0xE0F5E1E2` stored in little-endian order, i.e. bytes
`E2 E1 F5 E0`.

Extract just those bytes:

```bash
hexdump -C -s 1024 -n 4 "$IMAGE"
```

Expected output:
```
00000400  e2 e1 f5 e0                                       |....|
```

Flag any mismatch.

### 6c — Check blkszbits

`blkszbits` is documented at a specific byte offset within the superblock.  Read the
documentation to find the exact offset, then extract that byte:

```bash
# Example: if blkszbits is at superblock offset 0x26 (absolute 0x426):
hexdump -C -s $((1024 + 0x26)) -n 1 "$IMAGE"
```

The default block size for `mkfs.erofs` is 4096 bytes, so `blkszbits` should be
`12` (0x0C).

### 6d — Check other superblock fields

For each field you chose to verify in Step 3, look up its byte offset in the
documentation table, compute the absolute file offset as `1024 + field_offset`, and
extract the appropriate number of bytes with `hexdump`.

Compare the raw bytes against the expected value, taking endianness into account
(all multi-byte integer fields in EROFS are little-endian unless the doc says
otherwise).

---

## Step 7 — Verify Inode Layout

Inodes begin at the block pointed to by `root_nid` in the superblock.  The exact
location depends on the image, so read `root_nid` from the superblock first.

### 7a — Read root_nid

`root_nid` is a 16-bit little-endian field.  Find its offset in the superblock from
the documentation, then:

```bash
# Example: root_nid at superblock offset 0x18 (absolute 0x418), 2 bytes LE:
python3 -c "
import struct, sys
data = open('$IMAGE','rb').read()
root_nid = struct.unpack_from('<H', data, 0x400 + 0x18)[0]
print(f'root_nid = {root_nid} (0x{root_nid:x})')
"
```

### 7b — Locate the root inode

The inode slot size is 32 bytes.  The inode for `root_nid` is located at:

```
inode_offset = root_nid * 32
```

```bash
python3 -c "
import struct
data = open('$IMAGE','rb').read()
root_nid = struct.unpack_from('<H', data, 0x400 + 0x18)[0]
inode_off = root_nid * 32
print(f'root inode at offset 0x{inode_off:x}')
"
```

### 7c — Dump the root inode

```bash
python3 -c "
import struct
data = open('$IMAGE','rb').read()
root_nid = struct.unpack_from('<H', data, 0x400 + 0x18)[0]
inode_off = root_nid * 32
import subprocess
subprocess.run(['hexdump','-C','-s',str(inode_off),'-n','64','$IMAGE'])
"
```

Compare the dumped bytes against the compact inode layout table in the documentation.

---

## Step 8 — Report Findings

For each field verified, record the result:

```
FINDING [Part 3] <doc-file>:<section>
  Field: <field_name>  Expected: <expected_value>  Actual: <hex_bytes_from_image>
  <Description of match or mismatch.>
```

If the field matches:

```
FINDING [Part 3] <field_name>: OK — image bytes match documentation.
```

**All Part 3 findings are advisory.**  Present discrepancies to the user and ask for
a decision before suggesting any documentation edits.

---

## Step 9 — Clean Up

```bash
rm -rf "$SRCDIR" "$IMAGE"
# Remove the erofs-utils clone only if Part 2 is also done:
rm -rf "$TEMP_DIR"
```
