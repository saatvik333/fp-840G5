#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Generate nonbiometric image data for the upstream frame-assembly unit test."""

import argparse
import hashlib
import struct
import zlib
from pathlib import Path


def chunk(kind, payload):
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload))
    )


def generate(native_source):
    width, height = 64, 117
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            value = hashlib.sha256(struct.pack("<II", x, y)).digest()[0]
            rows.extend((value, value, value))
    image = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )
    destination = native_source / "tests/vfs5011/capture.png"
    if destination.exists():
        raise ValueError("Refusing to replace an existing upstream fixture")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(image)
    print(f"[fixture] Created synthetic frame-assembly input: {destination}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-source", type=Path, default=Path("libfprint"))
    generate(parser.parse_args().native_source)
