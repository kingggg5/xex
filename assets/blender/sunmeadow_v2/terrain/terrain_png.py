"""Minimal, dependency-free PNG codec for the terrain pipeline (numpy + zlib only).

Why not PIL/cv2/bpy: Blender's interpreter has no PIL, and the per-cell data maps must be written with
exactly IHDR/IDAT/IEND (no gAMA/cHRM/sRGB/iCCP chunks; spec §3.4) so browsers never colour-manage them.
Supports 8-bit grey/RGB/RGBA and 16-bit grey/RGB, non-interlaced. Row 0 of every array is the image top.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np

_SIG = b'\x89PNG\r\n\x1a\n'
_COLOR_TYPES = {1: 0, 3: 2, 4: 6}           # channels -> PNG colour type
_CHANNELS = {0: 1, 2: 3, 6: 4, 4: 2}


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)


def write_png(path: str | Path, array: np.ndarray, bits: int = 8, level: int = 9) -> Path:
    """Write an (H, W) or (H, W, C) uint8/uint16 (or float 0..1) array; row 0 = image top."""
    path = Path(path)
    arr = np.asarray(array)
    if arr.ndim == 2:
        arr = arr[..., None]
    h, w, c = arr.shape
    if c not in _COLOR_TYPES:
        raise ValueError(f'unsupported channel count {c}')
    if arr.dtype.kind == 'f':
        scale = 65535.0 if bits == 16 else 255.0
        arr = np.clip(np.rint(np.clip(arr, 0.0, 1.0) * scale), 0, scale)
    dtype = '>u2' if bits == 16 else 'u1'
    if bits == 16 and c == 4:
        raise ValueError('16-bit RGBA is not needed by the pipeline')
    raw = np.ascontiguousarray(arr.astype(dtype)).reshape(h, w * c)
    filtered = np.concatenate([np.zeros((h, 1), np.uint8), raw.view(np.uint8).reshape(h, -1)], axis=1)
    ihdr = struct.pack('>IIBBBBB', w, h, bits, _COLOR_TYPES[c], 0, 0, 0)
    payload = _SIG + _chunk(b'IHDR', ihdr) + _chunk(b'IDAT', zlib.compress(filtered.tobytes(), level)) + _chunk(b'IEND', b'')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def chunks(path: str | Path) -> list[str]:
    data = Path(path).read_bytes()
    if data[:8] != _SIG:
        raise ValueError(f'{path} is not a PNG')
    out, pos = [], 8
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        out.append(data[pos + 4:pos + 8].decode('ascii'))
        pos += 12 + length
    return out


def _unfilter(raw: np.ndarray, h: int, stride: int, bpp: int) -> np.ndarray:
    out = np.zeros((h, stride), np.uint8)
    prev = np.zeros(stride, np.int32)
    pos = 0
    for y in range(h):
        ftype = raw[pos]
        line = raw[pos + 1:pos + 1 + stride].astype(np.int32)
        pos += 1 + stride
        if ftype == 0:
            cur = line
        elif ftype == 2:
            cur = (line + prev) & 0xff
        else:
            cur = np.zeros(stride, np.int32)
            for x in range(stride):
                a = cur[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                if ftype == 1:
                    v = line[x] + a
                elif ftype == 3:
                    v = line[x] + ((a + b) >> 1)
                elif ftype == 4:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    v = line[x] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))
                else:
                    raise ValueError(f'bad PNG filter {ftype}')
                cur[x] = v & 0xff
        out[y] = cur
        prev = cur
    return out


def read_png(path: str | Path) -> np.ndarray:
    """Read a non-interlaced PNG to (H, W[, C]) uint8/uint16; row 0 = image top. Slow filters are rare in our files."""
    data = Path(path).read_bytes()
    if data[:8] != _SIG:
        raise ValueError(f'{path} is not a PNG')
    pos, idat, ihdr = 8, [], None
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if tag == b'IHDR':
            ihdr = struct.unpack('>IIBBBBB', body)
        elif tag == b'IDAT':
            idat.append(body)
        pos += 12 + length
    if ihdr is None:
        raise ValueError('missing IHDR')
    w, h, bits, ctype, _, _, interlace = ihdr
    if interlace:
        raise ValueError('interlaced PNG not supported')
    c = _CHANNELS[ctype]
    bpp = c * (2 if bits == 16 else 1)
    raw = np.frombuffer(zlib.decompress(b''.join(idat)), np.uint8)
    rows = _unfilter(raw, h, w * bpp, bpp)
    if bits == 16:
        arr = rows.view('>u2').astype(np.uint16).reshape(h, w, c)
    else:
        arr = rows.reshape(h, w, c)
    return arr[..., 0] if c == 1 else arr
