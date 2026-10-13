#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Fetch and inspect pinned HP VFS7552 artifacts offline; never open a USB device."""

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_NAME = "6_07f_hp_cmit_mis_qm.xpfwext"
FIRMWARE_SHA256 = "2b68b33668215cfc2a08c80a1f2c0e66c4c02927895d70a7d5f237e5201d5d2f"
RESET_SHA256 = "7f379b1648326f031753d2d0a974bae75bc59a95f847b9c6478a124f32b3c17a"
PACKAGES = {
    "sp110163": {
        "directory": "sp110001-110500",
        "version": "5.5.27.1099",
        "sha256": "5c5af715975797a0259136390159e0f45149592f16ed6c7e6617d9384e1854d5",
        "driver_sha256": "d2e3e724710807cf75f03314cd942bf29d37fbab4b222ee1cf2ff38695d55efe",
        "reset_body_offset": 0x1B5504,
    },
    "sp135736": {
        "directory": "sp135501-136000",
        "version": "5.5.28.1099",
        "sha256": "be83e4cab0db523e66818b9eee9b8bd2c0e9144821bf96cdc162bb73d62ad311",
        "driver_sha256": "f17152a49542dbb8a1ea32ee9008271a2328a264d4dac49e0cc3dc890b791886",
        "reset_body_offset": 0x1B54F4,
    },
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def checked_read(path, expected):
    data = path.read_bytes()
    actual = sha256(data)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {path}: {actual}, expected {expected}")
    return data


def parse_fwext(data):
    """Split the vendor's text header, encrypted body and trailing RSA signature."""
    marker = data.find(b"\x1a")
    if marker < 0 or marker > 65536:
        raise ValueError("Missing or oversized firmware header")
    header = data[:marker].rstrip(b"\x00")
    text = header.decode("ascii")
    if not text.startswith("// Validity Sensors V4 Firmware Extension File"):
        raise ValueError("Unrecognized firmware extension format")
    fields = dict(re.findall(r"^([A-Za-z][A-Za-z0-9]*)\s*=\s*(\S+)\s*$", text, re.MULTILINE))
    signature_size = int(fields.get("SignatureLength", "0"), 0)
    if signature_size != 256 or fields.get("Signed") != "0x0001":
        raise ValueError("Unexpected signature layout")
    if len(data) - marker - 1 <= signature_size:
        raise ValueError("Truncated firmware body")
    return fields, header, data[marker + 1 : -signature_size], data[-signature_size:]


def file_offset_to_va(data, offset, length):
    """Resolve a fully file-backed PE range; do not infer firmware load addresses."""
    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError("Not a DOS/PE image")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if pe + 24 > len(data) or data[pe : pe + 4] != b"PE\x00\x00":
        raise ValueError("Invalid PE header")
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    if optional_size < 32 or optional + optional_size + count * 40 > len(data):
        raise ValueError("Truncated PE section table")
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic == 0x20B:
        base = struct.unpack_from("<Q", data, optional + 24)[0]
    elif magic == 0x10B:
        base = struct.unpack_from("<I", data, optional + 28)[0]
    else:
        raise ValueError("Unsupported PE optional header")
    for index in range(count):
        pos = optional + optional_size + index * 40
        virtual_size, rva, size, start = struct.unpack_from("<IIII", data, pos + 8)
        if start <= offset and offset + length <= start + size and offset + length <= len(data):
            if offset - start + length > virtual_size:
                raise ValueError("Selected bytes extend into section file padding")
            return base + rva + offset - start
    raise ValueError("Selected bytes are outside file-backed PE sections")


def fetch(package):
    meta = PACKAGES[package]
    destination = ROOT / "artifacts/hp"
    destination.mkdir(parents=True, exist_ok=True)
    base = f"https://ftp.hp.com/pub/softpaq/{meta['directory']}/{package}"
    exe = destination / f"{package}.exe"
    if exe.exists():
        checked_read(exe, meta["sha256"])
    else:
        partial = exe.with_suffix(".exe.partial")
        try:
            with (
                urllib.request.urlopen(base + ".exe", timeout=60) as response,
                partial.open("wb") as stream,
            ):
                print(f"[download] {base}.exe", flush=True)
                received = 0
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
                    received += len(chunk)
                    print(f"[download] {received} bytes received", flush=True)
            checked_read(partial, meta["sha256"])
            partial.replace(exe)
        finally:
            partial.unlink(missing_ok=True)
    for suffix in ("cva", "html"):
        path = destination / f"{package}.{suffix}"
        if not path.exists():
            with urllib.request.urlopen(base + "." + suffix, timeout=60) as response:
                path.write_bytes(response.read())
    extracted = destination / package
    if not (extracted / "src/driver/INF/x64" / FIRMWARE_NAME).exists():
        archiver = shutil.which("7z") or shutil.which("7zz")
        if archiver is None:
            raise RuntimeError("Install 7zip (7z or 7zz) to extract the SoftPaq without running it")
        subprocess.run([archiver, "x", "-y", f"-o{extracted}", str(exe)], check=True)
    return analyze(package)


def analyze(package, output=None):
    meta = PACKAGES[package]
    directory = ROOT / "artifacts/hp"
    exe = directory / f"{package}.exe"
    checked_read(exe, meta["sha256"])
    driver_dir = directory / package / "src/driver/INF/x64"
    firmware_path = driver_dir / FIRMWARE_NAME
    firmware = checked_read(firmware_path, FIRMWARE_SHA256)
    fields, header, payload, signature = parse_fwext(firmware)
    dll_path = driver_dir / "synaWudfBioUsb.dll"
    dll = dll_path.read_bytes()
    if "driver_sha256" in meta and sha256(dll) != meta["driver_sha256"]:
        raise ValueError("Driver DLL does not match the pinned extracted artifact")
    offset = meta["reset_body_offset"]
    reset = b"\x06\x02\x00\x00\x01" + dll[offset : offset + 11968]
    if sha256(reset) != RESET_SHA256:
        raise ValueError("HP reset payload is not present at the verified DLL range")
    va = file_offset_to_va(dll, offset, 11968)
    result = {
        "package": package,
        "source": f"https://ftp.hp.com/pub/softpaq/{meta['directory']}/{package}.exe",
        "package_sha256": meta["sha256"],
        "driver": {"path": str(dll_path.relative_to(ROOT)), "sha256": sha256(dll)},
        "firmware": {
            "path": str(firmware_path.relative_to(ROOT)),
            "sha256": sha256(firmware),
            "fields": fields,
            "header_bytes": len(firmware) - len(payload) - len(signature),
            "payload_bytes": len(payload),
            "payload_sha256": sha256(payload),
            "signature_bytes": len(signature),
            "signature_sha256": sha256(signature),
            "signature_verified": False,
            "payload_decrypted": False,
        },
        "reset_command": {
            "body_file_offset": offset,
            "body_virtual_address": hex(va),
            "body_bytes": 11968,
            "wire_prefix_hex": "0602000001",
            "command_bytes": len(reset),
            "sha256": sha256(reset),
        },
        "limitations": [
            "Static extraction; no reader was opened or flashed.",
            "HP package checksum verified; the sensor's RSA signature was not verified locally.",
            "Encrypted firmware payload remains encrypted; no firmware source recovery claimed.",
        ],
    }
    if output:
        output.mkdir(parents=True, exist_ok=True)
        for name, content in (
            (FIRMWARE_NAME, firmware),
            ("firmware.encrypted.bin", payload),
            ("firmware.signature.bin", signature),
            ("firmware-header.txt", header),
            ("hp-reset-command.bin", reset),
        ):
            (output / name).write_bytes(content)
        (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fetch", "analyze"))
    parser.add_argument("--package", choices=PACKAGES, default="sp135736")
    parser.add_argument(
        "--output", type=Path, help="Optional directory for derived binary artifacts"
    )
    parser.add_argument(
        "--accept-vendor-terms",
        action="store_true",
        help="Acknowledge separate HP/vendor terms; see docs/licensing.md",
    )
    args = parser.parse_args()
    if args.action == "fetch":
        if not args.accept_vendor_terms:
            parser.error(
                "Fetching vendor software requires --accept-vendor-terms; read docs/licensing.md"
            )
        fetch(args.package)
    result = analyze(args.package, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
