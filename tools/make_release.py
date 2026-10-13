#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Make an audited driver-only release and complete corresponding source archive."""

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from audit_package import audit_package

ROOT = Path(__file__).resolve().parents[1]


def extract_git(directory, destination):
    archive = subprocess.check_output(
        ["git", "-C", str(directory), "archive", "--format=tar", "HEAD"]
    )
    excluded = []
    with tarfile.open(fileobj=io.BytesIO(archive)) as data:
        members = []
        for member in data.getmembers():
            if Path(member.name).suffix.lower() in (".pcap", ".pcapng", ".png", ".jpg", ".jpeg"):
                excluded.append(member.name)
            else:
                members.append(member)
        data.extractall(destination, members=members, filter="data")
    return excluded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    public_status = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"])
    if public_status:
        raise SystemExit("Commit the reviewed public source before making a release")
    source = ROOT / "sources/libfprint-vcsfw"
    lock = json.loads((ROOT / "sources.lock.json").read_text())
    head = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    patch = ROOT / "patches/libfprint-hp840g5.patch"
    delta = subprocess.check_output(["git", "-C", str(source), "diff", "--binary"])
    if head != lock["libfprint"]["commit"] or delta != patch.read_bytes():
        raise SystemExit("Complete native source must match the released pin and patch")
    audit_package(args.package)
    version = (ROOT / "VERSION").read_text().strip()
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    binary = output / args.package.name
    shutil.copy2(args.package, binary)
    shutil.copy2(args.package.with_suffix(".deb.sha256"), output / (binary.name + ".sha256"))
    archive_path = output / f"fp840g5-native-{version}-source.tar.gz"
    with tempfile.TemporaryDirectory(
        prefix="corresponding-source-", dir=ROOT / "build"
    ) as temporary:
        tree = Path(temporary) / f"fp840g5-native-{version}"
        tree.mkdir()
        extract_git(ROOT, tree)
        native = tree / "libfprint"
        native.mkdir()
        excluded = extract_git(source, native)
        modified = subprocess.check_output(
            ["git", "-C", str(source), "diff", "--name-only"], text=True
        ).splitlines()
        for name in modified:
            shutil.copy2(source / name, native / name)
        (tree / "SOURCE-MANIFEST.json").write_text(
            json.dumps(
                {
                    "project_commit": subprocess.check_output(
                        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
                    ).strip(),
                    "libfprint_base_commit": head,
                    "patch_sha256": hashlib.sha256(delta).hexdigest(),
                    "omitted_upstream_test_fixtures": excluded,
                    "source_files": {
                        str(p.relative_to(native)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in native.rglob("*")
                        if p.is_file() and not p.is_symlink()
                    },
                },
                indent=2,
            )
            + "\n"
        )
        (tree / "BUILD-CORRESPONDING-SOURCE.md").write_text(
            "# Build the included complete library source\n\n"
            "The libfprint/ directory is the exact patched library source. All library\n"
            "modules, interface headers, Meson files, COPYING and attribution are retained.\n"
            "Opaque image/packet test fixtures were omitted; see SOURCE-MANIFEST.json.\n"
            "The assembly unit test can use deterministic synthetic image data\n"
            "generated locally; no captured fingerprint image is redistributed.\n\n"
            "Install README development prerequisites, then build from this directory:\n\n"
            "```bash\npython3 tools/generate_test_fixture.py\n"
            "meson setup build/included libfprint --prefix=/opt/fp-840g5 --libdir=lib "
            "--buildtype=release -Ddrivers=validity,virtual_image,virtual_device,virtual_device_storage "
            "-Ddoc=false -Dintrospection=false "
            "-Dgtk-examples=false -Dinstalled-tests=false -Dudev_rules=disabled -Dudev_hwdb=disabled\n"
            "meson compile -C build/included\nmeson test -C build/included --suite unit-tests\n```\n\n"
            "The preservation guard source is tools/preserve_prints.c; its build/link\n"
            "recipe is in tools/build_ubuntu_package.py. The library uses replaceable\n"
            "shared linking, and source/build/installation scripts are supplied here.\n"
            "Vendor runtime files remain separate and are not in this source archive.\n"
        )
        with tarfile.open(archive_path, "w:gz") as archive:

            def normalized(member):
                member.uid = member.gid = 0
                member.uname = member.gname = "root"
                return member

            archive.add(tree, arcname=tree.name, filter=normalized)
    assets = [binary, archive_path]
    (output / "SHA256SUMS").write_text(
        "".join(
            hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
            for path in assets
        )
    )
    print(
        "[verified] Driver-only binary, checksum sidecar, full corresponding source and SHA256SUMS prepared"
    )
    for path in [*assets, output / (binary.name + ".sha256"), output / "SHA256SUMS"]:
        print(path)


if __name__ == "__main__":
    main()
