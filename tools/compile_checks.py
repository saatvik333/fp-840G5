#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Compile offline loaders and the native reader smoke check against the built library."""

import argparse
import os
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/libfprint"
LIB = BUILD / "libfprint"
SOURCE = ROOT / "sources/libfprint-vcsfw/libfprint"


def run(command):
    print("[command] " + shlex.join([str(p) for p in command]), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-vendor-data",
        action="store_true",
        help="Also verify previously staged local HP data; no download or device I/O",
    )
    args = parser.parse_args()
    packages = ["glib-2.0", "gio-2.0", "gobject-2.0", "gmodule-2.0", "gusb", "openssl"]
    flags = shlex.split(
        subprocess.check_output(["pkg-config", "--cflags", "--libs", *packages], text=True)
    )
    include = [
        "-I" + str(p) for p in (BUILD, LIB, SOURCE.parent, SOURCE, SOURCE / "drivers/validity")
    ]
    link = ["-L" + str(LIB), "-lfprint-2", "-Wl,-rpath," + str(LIB), "-lm", *flags]
    run(
        [
            "cc",
            "-g",
            *include,
            "tools/verify-native-data.c",
            "-o",
            "build/verify-native-data",
            "-Wl,--start-group",
            LIB / "libfprint-drivers.a",
            LIB / "libfprint-private.a",
            LIB / "libnbis.a",
            "-Wl,--end-group",
            *link,
        ]
    )
    if args.with_vendor_data:
        run([ROOT / "build/verify-native-data"])
    run(["cc", "-g", *include, "tools/reader_smoke.c", "-o", "build/reader-smoke", *link])
    run(
        [
            "cc",
            "-Wall",
            "-Wextra",
            "-Werror",
            *include,
            "tools/enroll_cancel_smoke.c",
            "-o",
            "build/enroll-cancel-smoke",
            *link,
        ]
    )
    run(
        [
            "cc",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            *include,
            "tools/preserve_prints.c",
            "-o",
            "build/preserve-prints.so",
            "-ldl",
            *link,
        ]
    )
    run(
        [
            "cc",
            "-Wall",
            "-Wextra",
            "-Werror",
            *include,
            "tools/check_preserve_prints.c",
            "-o",
            "build/check-preserve-prints",
            *link,
        ]
    )
    guard_env = dict(
        os.environ, LD_PRELOAD=str(ROOT / "build/preserve-prints.so"), G_DEBUG="fatal-criticals"
    )
    guard_env.pop("FP840G5_ALLOW_NATIVE_PRINT_DELETE", None)
    subprocess.run([ROOT / "build/check-preserve-prints"], env=guard_env, check=True, timeout=10)
    run(
        [
            "cc",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            *include,
            "tools/mock_print_deletes.c",
            "-o",
            "build/mock-print-deletes.so",
            *link,
        ]
    )
    run(
        [
            "cc",
            "-Wall",
            "-Wextra",
            "-Werror",
            *include,
            "tools/check_preserve_prints_policy.c",
            "-o",
            "build/check-preserve-prints-policy",
            ROOT / "build/mock-print-deletes.so",
            *link,
        ]
    )
    policy_env = dict(
        guard_env,
        FP840G5_ALLOW_NATIVE_PRINT_DELETE="1",
        LD_PRELOAD=guard_env["LD_PRELOAD"] + ":" + str(ROOT / "build/mock-print-deletes.so"),
    )
    subprocess.run(
        [ROOT / "build/check-preserve-prints-policy"], env=policy_env, check=True, timeout=15
    )
    print(
        "[verified] Preservation API/policy checks passed; hardware helpers compiled without opening a reader.",
        flush=True,
    )
    if args.with_vendor_data:
        print("[verified] Staged native data and firmware loaders passed.", flush=True)


if __name__ == "__main__":
    main()
