#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Check a release .deb for vendor payloads, private paths and activation scripts."""

import argparse
import io
import json
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

FORBIDDEN_SUFFIXES = {".bin", ".xpfwext", ".exe", ".dll", ".pem", ".key", ".pcap", ".pcapng"}
ALLOWED_ROOTS = ("opt/fp-840g5/", "usr/share/doc/fp840g5-native/")


def audit_data(archive):
    names = []
    with tarfile.open(fileobj=io.BytesIO(archive)) as data:
        for member in data.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe package member path")
            name = str(path).removeprefix("./")
            if member.isdir():
                ancestors = {
                    "opt",
                    "opt/fp-840g5",
                    "usr",
                    "usr/share",
                    "usr/share/doc",
                    "usr/share/doc/fp840g5-native",
                    ".",
                }
                if name not in ancestors and not name.startswith(ALLOWED_ROOTS):
                    raise ValueError(f"Unexpected package directory: {name}")
                if "/share/libfprint/validity" in name:
                    raise ValueError("Vendor data directory forbidden in public package")
                continue
            if not name.startswith(ALLOWED_ROOTS) or "/share/libfprint/validity/" in name:
                raise ValueError(f"Unexpected install path: {name}")
            if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                raise ValueError(f"Vendor/private artifact forbidden in public package: {name}")
            if member.issym():
                link = PurePosixPath(member.linkname)
                if link.is_absolute() or ".." in link.parts:
                    raise ValueError("Package symlink must stay within the private prefix")
            elif member.isfile():
                content = data.extractfile(member).read()
                if b"/home/" in content:
                    raise ValueError(f"Private build-home path in package: {name}")
                if b"-----BEGIN PRIVATE KEY-----" in content:
                    raise ValueError("Private-key material in public package")
            else:
                raise ValueError("Unsupported package member type")
            names.append(name)
    if not any(name.endswith("/libfprint-2.so.2.0.0") for name in names):
        raise ValueError("Release package is missing the native library")
    if not any(name.endswith("/preserve-prints.so") for name in names):
        raise ValueError("Release package is missing the preservation guard")
    return names


def audit_package(package):
    control = subprocess.check_output(["dpkg-deb", "--ctrl-tarfile", str(package)])
    with tarfile.open(fileobj=io.BytesIO(control)) as data:
        seen = set()
        for member in data.getmembers():
            path = PurePosixPath(member.name)
            name = str(path).removeprefix("./")
            if path.is_absolute() or ".." in path.parts or name in seen:
                raise ValueError("Unsafe or duplicate package control member")
            seen.add(name)
            if member.isdir() and name == ".":
                continue
            if not member.isfile() or name not in ("control", "md5sums"):
                raise ValueError("Release package must not run maintainer/activation scripts")
    archive = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", str(package)])
    return audit_data(archive)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    files = audit_package(args.package)
    print(
        json.dumps(
            {
                "package": args.package.name,
                "vendor_data_included": False,
                "activation_scripts_included": False,
                "files": files,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
