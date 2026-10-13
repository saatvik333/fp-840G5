#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Stage verified HP data beside the local libfprint build; no device I/O."""

import hashlib
import hmac
import json
import shutil

from hp_firmware import FIRMWARE_NAME, RESET_SHA256, ROOT, analyze


def main():
    prefix = ROOT / "build/stage"
    native = ROOT / "sources/libfprint-vcsfw/libfprint/drivers/validity/validity_pair.c"
    if "validity_pair_hp_preflight" not in native.read_text():
        raise SystemExit(
            "The native HP identity/preflight patch must be applied before staging HP 00ab data"
        )
    output = ROOT / "artifacts/derived/sp135736"
    analyze("sp135736", output)
    source = ROOT / "sources/libfprint-validity-data/output"
    target = prefix / "share/libfprint/validity"
    if not source.is_dir():
        raise SystemExit("Generate pinned validity data before staging")
    # Stage only this device and common files; do not install unrelated vendor sets.
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for item in source.glob("*.bin"):
        shutil.copyfile(item, target / item.name)
    shutil.copytree(source / "138a_00ab", target / "138a_00ab")
    reset = (output / "hp-reset-command.bin").read_bytes()
    assert hashlib.sha256(reset).hexdigest() == RESET_SHA256
    # This public corruption-check key is the pinned data generator's key.
    trailer = hmac.new(b"libfprint-validity-data-integrit", reset, hashlib.sha256).digest()
    (target / "138a_00ab/reset.bin").write_bytes(reset + trailer)
    shutil.copyfile(output / FIRMWARE_NAME, target / FIRMWARE_NAME)
    files = {
        str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in target.rglob("*")
        if p.is_file()
    }
    expected = json.loads((ROOT / "vendor-data.lock.json").read_text())["files"]
    if files != expected:
        raise SystemExit("Generated runtime files differ from the pinned vendor-data checksums")
    manifest = {
        "prefix": str(prefix),
        "target": "138a:00ab; factory-empty provisioning is gated in the local native driver",
        "reset_source": "HP sp135736 synaWudfBioUsb.dll body at file offset 0x1b54f4, plus opcode/envelope",
        "reset_sha256_without_hmac": RESET_SHA256,
        "modified_data_file": "138a_00ab/reset.bin",
        "device_access": False,
        "files": files,
    }
    (target / "local-vendor-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (ROOT / "evidence").mkdir(exist_ok=True)
    (ROOT / "evidence/staged-native-data.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Staged verified HP firmware and command data at {target}")


if __name__ == "__main__":
    main()
