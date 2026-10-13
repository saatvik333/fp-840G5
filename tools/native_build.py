#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Build and test the pinned native driver; vendor downloads are explicit opt-in."""

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*command, env=None):
    print("[command] " + shlex.join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def pinned_checkout(name, entry):
    directory = ROOT / "sources" / name
    if not directory.exists():
        run("git", "clone", "--no-checkout", "--filter=blob:none", entry["url"], str(directory))
        run("git", "-C", str(directory), "fetch", "--depth", "1", "origin", entry["commit"])
        run("git", "-C", str(directory), "checkout", "--detach", entry["commit"])
    head = subprocess.check_output(
        ["git", "-C", str(directory), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != entry["commit"]:
        raise SystemExit(
            f"{directory}: expected {entry['commit']}, got {head}; preserve and resolve the checkout first"
        )
    print(f"[verified] {name}: {head}", flush=True)
    return directory


def apply_patch(source, patch):
    check = ["git", "-C", str(source), "apply", "--check", str(patch)]
    result = subprocess.run(check, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        run("git", "-C", str(source), "apply", str(patch))
    elif (
        subprocess.run(
            check[:4] + ["--reverse"] + check[4:], capture_output=True, check=False
        ).returncode
        != 0
    ):
        raise SystemExit(
            f"Patch does not apply cleanly or match existing changes: {patch}\n{result.stderr}"
        )
    else:
        print(f"[verified] Patch already applied: {patch.name}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument(
        "--with-vendor-data",
        action="store_true",
        help="Download vendor artifacts and prepare local runtime data",
    )
    parser.add_argument(
        "--accept-vendor-terms",
        action="store_true",
        help="Acknowledge that vendor artifacts have separate terms (see docs/licensing.md)",
    )
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if args.with_vendor_data and not args.accept_vendor_terms:
        parser.error("--with-vendor-data requires --accept-vendor-terms; read docs/licensing.md")
    lock = json.loads((ROOT / "sources.lock.json").read_text())
    source = pinned_checkout("libfprint-vcsfw", lock["libfprint"])
    patches = sorted((ROOT / "patches").glob("libfprint-*.patch"))
    if not patches:
        raise SystemExit("Missing exported local native-driver patch")
    for patch in patches:
        apply_patch(source, patch)

    env = os.environ.copy()
    # Optional project-local tools compensate for this host's absent GLib development executables.
    local_pc = ROOT / "tools/pkgconfig"
    local_bin = ROOT / "tools/.cache/glib-devel/usr/bin"
    if local_pc.is_dir():
        env["PKG_CONFIG_PATH"] = str(local_pc) + os.pathsep + env.get("PKG_CONFIG_PATH", "")
    if local_bin.is_dir():
        env["PATH"] = str(local_bin) + os.pathsep + env["PATH"]
    build = ROOT / "build/libfprint"
    prefix = ROOT / "build/stage"
    configure = [
        "meson",
        "setup",
        str(build),
        str(source),
        "--prefix",
        str(prefix),
        "-Ddrivers=validity,virtual_device,virtual_image",
        "-Ddoc=false",
        "-Dintrospection=false",
        "-Dgtk-examples=false",
        "-Dinstalled-tests=false",
        "-Dudev_rules=disabled",
        "-Dudev_hwdb=disabled",
    ]
    if (build / "meson-private/coredata.dat").exists():
        configure.append("--reconfigure")
    run(*configure, env=env)
    run("meson", "compile", "-C", str(build), "-j", str(args.jobs), env=env)
    run("meson", "test", "-C", str(build), "--suite", "unit-tests", "--print-errorlogs", env=env)
    run("meson", "install", "-C", str(build), "--no-rebuild", env=env)
    if args.with_vendor_data:
        data = pinned_checkout("libfprint-validity-data", lock["libfprint-validity-data"])
        if subprocess.run(
            ["git", "-C", str(data), "diff", "--quiet", "HEAD"], check=False
        ).returncode:
            raise SystemExit("Pinned vendor-data generator has local changes; refusing to run it")
        run(
            sys.executable,
            str(ROOT / "tools/hp_firmware.py"),
            "fetch",
            "--package",
            "sp135736",
            "--accept-vendor-terms",
        )
        run(sys.executable, str(data / "generate_data.py"))
        run(sys.executable, str(ROOT / "tools/stage_native.py"))
    # Firmware is a vendor container, not a data .bin with a corruption-check HMAC.
    # Run native loader verification separately after compiling verify-native-data.c.
    print(f"Native driver staged at {prefix}; no reader opened and no system service changed")
    if not args.with_vendor_data:
        print(
            "Vendor data was not downloaded. Use --with-vendor-data --accept-vendor-terms for a local installation."
        )


if __name__ == "__main__":
    main()
