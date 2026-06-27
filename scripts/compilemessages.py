#!/usr/bin/env python
"""Compile every locale/*/LC_MESSAGES/*.po into a .mo.

ponytail: stand-in for GNU `msgfmt`, which isn't installed on this box. Handles
the subset of PO we use (plain msgid/msgstr, no plurals/contexts). If gettext
ever lands, `python manage.py compilemessages` supersedes this — delete it then.
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_po(text):
    """Return {msgid: msgstr} for simple entries (incl. the "" header)."""
    entries = {}
    key = val = None
    target = None  # which of key/val the current "..." lines append to

    def flush():
        if key is not None:
            entries[key] = val

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        if line.startswith("msgid "):
            flush()
            key, val, target = _unquote(line[6:]), "", "id"
        elif line.startswith("msgstr "):
            val, target = _unquote(line[7:]), "str"
        elif line.startswith('"'):
            piece = _unquote(line)
            if target == "id":
                key += piece
            else:
                val += piece
    flush()
    return entries


def _unquote(s):
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return s.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")


def write_mo(entries, path):
    keys = sorted(entries)
    offsets, ids, strs = [], b"", b""
    for k in keys:
        kb, vb = k.encode("utf-8"), entries[k].encode("utf-8")
        offsets.append((len(ids), len(kb), len(strs), len(vb)))
        ids += kb + b"\x00"
        strs += vb + b"\x00"
    n = len(keys)
    start = 7 * 4 + 16 * n
    koffsets, voffsets = [], []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, start + o1]
        voffsets += [l2, start + len(ids) + o2]
    out = struct.pack(
        "Iiiiiii", 0x950412DE, 0, n, 7 * 4, 7 * 4 + n * 8, 0, 0
    )
    out += struct.pack("i" * len(koffsets), *koffsets)
    out += struct.pack("i" * len(voffsets), *voffsets)
    out += ids + strs
    path.write_bytes(out)


def main():
    count = 0
    for po in ROOT.glob("locale/*/LC_MESSAGES/*.po"):
        entries = parse_po(po.read_text(encoding="utf-8"))
        write_mo(entries, po.with_suffix(".mo"))
        print(f"compiled {po.relative_to(ROOT)} -> {po.with_suffix('.mo').name}")
        count += 1
    if not count:
        print("no .po files found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
