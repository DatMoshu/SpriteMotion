"""Read UOP containers and the animation data stored in them.

Reimplemented from the format as ClassicUO reads it (UOFileUop, AnimationsLoader);
see research/uo-conventions.md, "UOP animations".

Container (little endian):
  header : u32 magic 0x0050594D ("MYP\\0"), u32 version, u32 timestamp, i64 first table,
           u32 table size, i32 file count
  table  : i32 entry count, i64 next table (0 = last), then per entry:
           i64 offset, i32 header length, i32 compressed length, i32 decompressed length,
           u64 name hash, u32 data hash, i16 compression (0 none, 1 zlib, 3 zlib + BWT)
  data   : at offset + header length, `compressed length` bytes (== decompressed when flag 0)

Names are not stored, only their hash (Bob Jenkins' lookup3 hashlittle2 over the
ASCII name). Animation frames live in AnimationFrame<n>.uop under
    build/animationlegacyframe/<body:06>/<group:02>.bin
one file per body and action group, holding all five stored directions.

Animation bin:
  32-byte header ("AMOU", version, ...), i32 frame count, u32 frame table offset;
  frame table: per frame u16 group, u16 frame id (1-based, running through the five
  directions), 8 unknown bytes, u32 pixel offset (relative to the record start);
  pixel data: 256 x u16 palette, then the same sprite encoding as anim.mul.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

UOP_MAGIC = 0x50594D
COMPRESSION_NONE, COMPRESSION_ZLIB, COMPRESSION_ZLIB_BWT = 0, 1, 3
FRAME_NAME = "build/animationlegacyframe/{body:06d}/{group:02d}.bin"
USE_UOP_ANIMATION = 0x10000     # mobtypes.txt flag: the client draws this body from UOP
MAX_DIRECTIONS = 5
_M32 = 0xFFFFFFFF


def uop_hash(name: str) -> int:
    """64-bit UOP name hash (lookup3 hashlittle2, as used by the UO client)."""
    s = name.encode("ascii")
    length = len(s)
    a = b = c = (length + 0xDEADBEEF) & _M32   # ebx, edi, esi in the client's naming
    ebx, edi, esi = a, b, c
    i = 0

    def word(k: int) -> int:
        return s[k] | s[k + 1] << 8 | s[k + 2] << 16 | s[k + 3] << 24

    def rot(x: int, k: int) -> int:
        return ((x << k) | (x >> (32 - k))) & _M32

    while i + 12 < length:
        edi = (word(i + 4) + edi) & _M32
        esi = (word(i + 8) + esi) & _M32
        edx = (word(i) - esi) & _M32
        edx = ((edx + ebx) & _M32) ^ rot(esi, 4)
        esi = (esi + edi) & _M32
        edi = ((edi - edx) & _M32) ^ rot(edx, 6)
        edx = (edx + esi) & _M32
        esi = ((esi - edi) & _M32) ^ rot(edi, 8)
        edi = (edi + edx) & _M32
        ebx = ((edx - esi) & _M32) ^ rot(esi, 16)
        esi = (esi + edi) & _M32
        edi = ((edi - ebx) & _M32) ^ rot(ebx, 19)
        ebx = (ebx + esi) & _M32
        esi = ((esi - edi) & _M32) ^ rot(edi, 4)
        edi = (edi + ebx) & _M32
        i += 12

    remaining = length - i
    if remaining <= 0:
        return esi << 32     # eax is still 0 here, as in the client
    tail = s[i:] + bytes(12 - remaining)
    ebx = (ebx + (tail[0] | tail[1] << 8 | tail[2] << 16 | tail[3] << 24)) & _M32
    edi = (edi + (tail[4] | tail[5] << 8 | tail[6] << 16 | tail[7] << 24)) & _M32
    esi = (esi + (tail[8] | tail[9] << 8 | tail[10] << 16 | tail[11] << 24)) & _M32
    esi = ((esi ^ edi) - rot(edi, 14)) & _M32
    ecx = ((esi ^ ebx) - rot(esi, 11)) & _M32
    edi = ((edi ^ ecx) - rot(ecx, 25)) & _M32
    esi = ((esi ^ edi) - rot(edi, 16)) & _M32
    edx = ((esi ^ ecx) - rot(esi, 4)) & _M32
    edi = ((edi ^ edx) - rot(edx, 14)) & _M32
    eax = ((esi ^ edi) - rot(edi, 24)) & _M32
    return edi << 32 | eax


@dataclass(frozen=True)
class UopEntry:
    offset: int              # start of the data (header already skipped)
    compressed_length: int
    decompressed_length: int
    compression: int


class UopFile:
    """Hash -> entry table of one UOP container; data is read on demand."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: dict[int, UopEntry] = {}
        with self.path.open("rb") as handle:
            magic, _version, _stamp, table = struct.unpack("<IIIq", handle.read(20))
            if magic != UOP_MAGIC:
                raise ValueError(f"{self.path.name} is not a UOP container (magic {magic:#x}).")
            seen = set()
            while table:
                if table in seen:
                    raise ValueError(f"{self.path.name}: table chain loops at {table}.")
                seen.add(table)
                handle.seek(table)
                count, table = struct.unpack("<iq", handle.read(12))
                raw = handle.read(count * 34)
                for k in range(count):
                    offset, header, clen, dlen, name_hash, _data_hash, flag = struct.unpack_from(
                        "<qiiiQIh", raw, k * 34)
                    if offset == 0:
                        continue
                    self.entries[name_hash] = UopEntry(offset + header, clen, dlen, flag)

    def __contains__(self, name_hash: int) -> bool:
        return name_hash in self.entries

    def read(self, name_hash: int) -> bytes:
        entry = self.entries[name_hash]
        with self.path.open("rb") as handle:
            handle.seek(entry.offset)
            data = handle.read(entry.compressed_length)
        if len(data) != entry.compressed_length:
            raise ValueError(f"{self.path.name}: entry {name_hash:#018x} is truncated.")
        return decompress(data, entry, self.path.name)


def decompress(data: bytes, entry: UopEntry, where: str = "UOP") -> bytes:
    if entry.compression == COMPRESSION_NONE:
        return data
    if entry.compression not in (COMPRESSION_ZLIB, COMPRESSION_ZLIB_BWT):
        raise ValueError(f"{where}: unsupported UOP compression type {entry.compression} "
                         "(supported: 0 none, 1 zlib, 3 zlib+BWT).")
    out = zlib.decompress(data)
    if len(out) != entry.decompressed_length:
        raise ValueError(f"{where}: zlib gave {len(out)} bytes, expected {entry.decompressed_length}.")
    if entry.compression == COMPRESSION_ZLIB_BWT:
        out = bwt_decompress(out)
    return out


def bwt_decompress(buffer: bytes) -> bytes:
    """Undo compression type 3's second layer (applied after zlib), following ClassicUO's BwtDecompress.

    Stage 1 is a move-to-front decode over a sorted 16-bit table (only its first 256
    slots can ever be addressed); stage 2 inverts a Burrows-Wheeler style transform
    whose first 1024 bytes are 256 little-endian symbol counts.
    """
    if len(buffer) < 5:
        raise ValueError("BWT block too short.")
    first = buffer[4]
    values, fb, sb = [], first, 0
    for _ in range(256 * 256):
        values.append(fb + (sb << 8))
        fb = (fb + 1) & 0xFF
        if fb == 0:
            sb += 1
    values.sort()
    mtf = values[:256]
    out = bytearray(len(buffer) - 4)
    n, current, pos = 0, first, 5
    while pos < len(buffer):         # the client never consumes the final byte it reads
        value = mtf[current]
        if current:
            del mtf[current]
            mtf.insert(0, value)
        out[n] = value & 0xFF
        n += 1
        current = buffer[pos]
        pos += 1
    return _bwt_inverse(bytes(out))


def _bwt_inverse(data: bytes) -> bytes:
    if len(data) < 1024:
        raise ValueError("BWT block has no symbol table.")
    counts = struct.unpack_from("<256i", data, 0)
    total = sum(counts)
    if total <= 0:
        return b""
    symbol = list(range(256))
    order = sorted((i for i in range(256) if counts[i] > 0), key=lambda i: (-counts[i], i))
    nonzero = len(order)
    start, end = [0] * 256, [0] * 256
    m = 0
    for f in order:
        symbol[data[m + 1024]] = f
        start[f] = m + 1
        m += counts[f]
        end[f] = m
    out = bytearray(total)
    val = symbol[0]
    for count in range(total):
        out[count] = val
        if start[val] >= end[val]:
            if nonzero > 0:
                nonzero -= 1
                symbol = _shift(symbol, nonzero)
                val = symbol[0]
            else:
                nonzero -= 1
        else:
            idx = data[start[val] + 1024]
            start[val] += 1
            if idx:
                symbol = _shift(symbol, idx)
                symbol[idx] = val
                val = symbol[0]
    return bytes(out)


def _shift(symbols: list[int], count: int) -> list[int]:
    """The client's ShiftLeft: symbols[i] = symbols[i + 1] for i < count."""
    return symbols[1:count + 1] + symbols[count:]
