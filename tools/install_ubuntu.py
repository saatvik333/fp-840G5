#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Install or roll back the private driver on the validated Ubuntu/HP hardware."""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path("/opt/fp-840g5")
STATE = Path("/var/lib/fp-840g5")
DROPINS = Path("/etc/systemd/system/fprintd.service.d")
NAMES = ("90-fp840g5-native.conf", "91-fp840g5-preserve.conf")
PAM = Path("/etc/pam.d/common-auth")
VENDOR = ROOT / "build/stage/share/libfprint/validity"
OTHER_READERS = {
    "138a:0090",
    "138a:0097",
    "138a:009d",
    "06cb:009a",
    "06cb:00cb",
    "06cb:00b7",
    "06cb:00d2",
}


def run(*command, capture=False):
    command = [str(part) for part in command]
    print("[command] " + shlex.join(command), flush=True)
    return subprocess.run(
        command, check=True, text=True, stdout=subprocess.PIPE if capture else None
    )


def platform_check(
    os_release=Path("/etc/os-release"),
    product=Path("/sys/class/dmi/id/product_name"),
    usb_root=Path("/sys/bus/usb/devices"),
):
    release = dict(
        line.split("=", 1) for line in os_release.read_text().splitlines() if "=" in line
    )
    if (
        release.get("ID", "").strip('"') != "ubuntu"
        or release.get("VERSION_ID", "").strip('"') != "26.04"
    ):
        raise ValueError(
            "This installer supports Ubuntu 26.04 only; other releases are unvalidated"
        )
    if product.read_text().strip() != "HP EliteBook 840 G5":
        raise ValueError("This installer is restricted to HP EliteBook 840 G5")
    found = []
    for node in usb_root.iterdir():
        if not (node / "idVendor").is_file() or not (node / "idProduct").is_file():
            continue
        identity = (
            (node / "idVendor").read_text().strip().lower()
            + ":"
            + (node / "idProduct").read_text().strip().lower()
        )
        if identity in OTHER_READERS:
            raise ValueError(
                "Disconnect other Validity readers before installing this device-specific driver"
            )
        if identity == "138a:00ab":
            if (node / "bcdDevice").read_text().strip().lower() != "0164":
                raise ValueError("Unvalidated USB device revision; installation refused")
            found.append(node)
    if len(found) != 1:
        raise ValueError(f"Expected exactly one 138a:00ab reader; found {len(found)}")
    return found[0]


def metadata_check(result):
    if result.get("error") or result.get("usb_id") != "138a:00ab":
        raise ValueError("USB metadata probe failed")
    queries = result.get("queries", {})
    if any(
        queries.get(name, {}).get("status") != "0x0000"
        for name in ("rom", "flash", "silicon", "firmware")
    ):
        raise ValueError("Reader metadata is incomplete or reports an error")
    rom, flash, silicon, firmware = (
        queries[name] for name in ("rom", "flash", "silicon", "firmware")
    )
    if tuple(
        queries[name].get("payload_bytes") for name in ("rom", "flash", "silicon", "firmware")
    ) != (36, 74, 8, 106):
        raise ValueError("Incomplete or unvalidated metadata record sizes")
    if rom.get("timestamp") != 1415491824:
        raise ValueError("Unvalidated ROM timestamp")
    if (rom.get("major"), rom.get("minor"), rom.get("build"), rom.get("product")) != (
        6,
        7,
        164,
        48,
    ):
        raise ValueError("Unvalidated ROM identity; installation refused")
    if (silicon.get("reserved"), silicon.get("hw_major"), silicon.get("hw_version")) != (
        0,
        "0x0190",
        "0x0070",
    ):
        raise ValueError("Unvalidated silicon identity; installation refused")
    if flash.get("partitions") != 5 or flash.get("bytes") != 1048576:
        raise ValueError("Reader must already have the validated five-partition 1 MiB layout")
    if (firmware.get("major"), firmware.get("minor"), firmware.get("modules")) != (1, 2, 8):
        raise ValueError(
            "Existing firmware extension 1.2/eight modules is required; no provisioning is attempted"
        )


def vendor_check(directory=VENDOR):
    expected = json.loads((ROOT / "vendor-data.lock.json").read_text())["files"]
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Missing local vendor data; follow the separate download step")
    actual = {}
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlinks are not permitted in local vendor data")
        if path.is_file() and path.name != "local-vendor-manifest.json":
            actual[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(
            "Vendor data does not match the pinned file set and checksums; regenerate it"
        )


def package_check(package):
    package = package.resolve(strict=True)
    fields = package.with_suffix(".deb.sha256").read_text().split()
    if len(fields) != 2 or fields[1] != package.name or not re.fullmatch("[0-9a-f]{64}", fields[0]):
        raise ValueError("Expected a checksum file naming exactly this package")
    if hashlib.sha256(package.read_bytes()).hexdigest() != fields[0]:
        raise ValueError("Package checksum mismatch")
    identity = run("dpkg-deb", "--field", package, "Package", "Architecture", capture=True).stdout
    properties = dict(line.split(":", 1) for line in identity.splitlines() if ":" in line)
    if (
        properties.get("Package", "").strip() != "fp840g5-native"
        or properties.get("Architecture", "").strip() != "amd64"
    ):
        raise ValueError("Unexpected package name or architecture")
    from audit_package import audit_package

    audit_package(package)
    return package


def pam_enabled(path=PAM):
    return re.search(r"^auth\s+.*\bpam_fprintd[.]so\b", path.read_text(), re.MULTILINE) is not None


def service_active():
    return (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", "fprintd.service"], check=False
        ).returncode
        == 0
    )


def service_check():
    fragment = run(
        "systemctl", "show", "fprintd.service", "--property=FragmentPath", "--value", capture=True
    ).stdout.strip()
    if fragment not in (
        "/usr/lib/systemd/system/fprintd.service",
        "/lib/systemd/system/fprintd.service",
    ):
        raise ValueError(
            "Expected the standard Ubuntu fprintd unit; custom/masked units require manual review"
        )
    if run(
        "systemctl", "show", "fprintd.service", "--property=DropInPaths", "--value", capture=True
    ).stdout.strip():
        raise ValueError(
            "Existing fprintd drop-ins require review. Roll back prior native integration before this initial-activation installer"
        )
    if run(
        "systemctl",
        "show",
        "fprintd.service",
        "--property=EnvironmentFiles",
        "--value",
        capture=True,
    ).stdout.strip():
        raise ValueError("Custom fprintd environment files require manual review")
    command = run(
        "systemctl", "show", "fprintd.service", "--property=ExecStart", "--value", capture=True
    ).stdout
    if (
        "path=/usr/libexec/fprintd ;" not in command
        or "argv[]=/usr/libexec/fprintd ;" not in command
    ):
        raise ValueError("Custom fprintd launch command requires manual review")
    for name in (
        "python3-validity.service",
        "python-validity.service",
        "open-fprintd.service",
        "fp-840g5-test.service",
    ):
        if subprocess.run(["systemctl", "is-active", "--quiet", name], check=False).returncode == 0:
            raise ValueError(f"{name} owns the reader; stop that stack before installing")


def backup_config():
    if STATE.is_symlink() or (STATE.exists() and STATE.stat().st_uid != 0):
        raise ValueError("Unexpected installer state directory ownership")
    directory = STATE / "backups" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True, mode=0o700)
    directory.chmod(0o700)
    state = {
        "pam_was_enabled": pam_enabled(),
        "dropins": {},
        "created_by": "fp840g5-public-installer",
    }
    shutil.copy2(PAM, directory / "common-auth.before")
    if DROPINS.is_symlink():
        raise ValueError("Unexpected symlink for the service drop-in directory")
    for name in NAMES:
        path = DROPINS / name
        if path.is_symlink():
            raise ValueError("Unexpected service drop-in symlink")
        state["dropins"][name] = path.exists()
        if path.exists():
            shutil.copy2(path, directory / name)
    (directory / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    (STATE / "latest-backup").write_text(str(directory) + "\n")
    return directory


def restore_config(directory):
    state = json.loads((directory / "state.json").read_text())
    if state.get("created_by") != "fp840g5-public-installer":
        raise ValueError("Backup was not made by this installer")
    DROPINS.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        destination = DROPINS / name
        if state["dropins"][name]:
            shutil.copy2(directory / name, destination)
        else:
            destination.unlink(missing_ok=True)
    try:
        if not state["pam_was_enabled"]:
            run("env", "DEBIAN_FRONTEND=noninteractive", "pam-auth-update", "--disable", "fprintd")
            if pam_enabled():
                raise ValueError(
                    "Service selection restored; locally modified PAM needs manual review. No --force used"
                )
    finally:
        run("systemctl", "daemon-reload")


def loaded_library_check():
    pid = int(
        run(
            "systemctl", "show", "fprintd.service", "--property=MainPID", "--value", capture=True
        ).stdout.strip()
    )
    if pid <= 0:
        raise ValueError("Normal fprintd daemon has no running process")
    maps = Path(f"/proc/{pid}/maps").read_text()
    for name in ("libfprint-2.so.2.0.0", "preserve-prints.so"):
        if str(PREFIX / "lib" / name) not in maps:
            raise ValueError(
                "The daemon did not load both the private native library and preservation guard"
            )
    print(
        "[verified] Normal daemon loaded the private native library and preservation guard",
        flush=True,
    )


def install(package, no_pam):
    service_check()
    was_active = service_active()
    masked = False
    backup = None
    changed = False
    successful = False
    try:
        print(
            "[1/6] Temporarily stop and runtime-mask the daemon for metadata preflight", flush=True
        )
        run("systemctl", "stop", "fprintd.service")
        masked = True
        run("systemctl", "mask", "--runtime", "fprintd.service")
        if (
            run(
                "systemctl",
                "show",
                "fprintd.service",
                "--property=LoadState",
                "--value",
                capture=True,
            ).stdout.strip()
            != "masked"
        ):
            raise ValueError("The daemon could not be isolated for the reader probe")
        from probe_reader import probe

        metadata_check(probe(verbose=True))
        print(
            "[verified] Known ROM, silicon, provisioned flash and installed firmware; no serial read",
            flush=True,
        )
        print("[2/6] Save previous fprintd/PAM configuration", flush=True)
        backup = backup_config()
        print("[3/6] Install the driver-only local package and check stock-daemon ABI", flush=True)
        run("dpkg", "-i", package)
        run(
            "env",
            "-u",
            "FP_DEVICE_EMULATION",
            "-u",
            "G_MESSAGES_DEBUG",
            "LD_BIND_NOW=1",
            f"LD_LIBRARY_PATH={PREFIX}/lib",
            "/usr/libexec/fprintd",
            "--help",
        )
        print(
            "[4/6] Install separately obtained vendor data and select the private library",
            flush=True,
        )
        target = PREFIX / "share/libfprint/validity"
        if target.is_symlink():
            raise ValueError("Unexpected vendor-data destination symlink")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(VENDOR, target)
        for path in (target, *target.rglob("*")):
            path.chmod(0o755 if path.is_dir() else 0o644)
            os.chown(path, 0, 0)
        DROPINS.mkdir(parents=True, exist_ok=True)
        changed = True
        document = Path("/usr/share/doc/fp840g5-native")
        for source, name in zip(("fprintd.conf", "preserve-existing.conf"), NAMES, strict=True):
            shutil.copy2(document / source, DROPINS / name)
            (DROPINS / name).chmod(0o644)
        run("systemctl", "unmask", "--runtime", "fprintd.service")
        masked = False
        run("systemctl", "daemon-reload")
        run("systemctl", "start", "fprintd.service")
        loaded_library_check()
        print("[5/6] Configure the standard Ubuntu fingerprint PAM profile", flush=True)
        if not no_pam:
            run("env", "DEBIAN_FRONTEND=noninteractive", "pam-auth-update", "--enable", "fprintd")
            if not pam_enabled():
                raise ValueError(
                    "Ubuntu preserved locally modified PAM files; review with pam-auth-update"
                )
        else:
            print("[skipped] PAM selection left as configured (--no-pam)", flush=True)
        print("[6/6] Check the normal daemon", flush=True)
        run("systemctl", "status", "fprintd.service", "--no-pager")
        successful = True
        print(
            "Driver installed. Enroll an unused finger through Settings or fprintd-enroll.",
            flush=True,
        )
        print(f"Rollback: sudo python3 {ROOT / 'tools/install_ubuntu.py'} --rollback", flush=True)
    except Exception:
        if changed and backup is not None:
            print("[recovery] Restore previous service/PAM selection", flush=True)
            subprocess.run(["systemctl", "stop", "fprintd.service"], check=False)
            try:
                restore_config(backup)
            except (ValueError, OSError, subprocess.CalledProcessError) as recovery:
                print(f"[recovery error] {recovery}; backup retained at {backup}", file=sys.stderr)
        raise
    finally:
        if masked:
            run("systemctl", "unmask", "--runtime", "fprintd.service")
            run("systemctl", "daemon-reload")
        if not successful and was_active:
            run("systemctl", "start", "fprintd.service")


def rollback():
    directory = Path((STATE / "latest-backup").read_text().strip()).resolve(strict=True)
    if not directory.is_relative_to((STATE / "backups").resolve(strict=True)):
        raise ValueError("Unexpected rollback backup path")
    if directory.stat().st_uid != 0:
        raise ValueError("Rollback backup must be root-owned")
    run("systemctl", "stop", "fprintd.service")
    try:
        restore_config(directory)
    finally:
        run("systemctl", "start", "fprintd.service")
    print(
        "Previous service/PAM selection restored. Package/data stay installed; prints were not deleted.",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    version = (ROOT / "VERSION").read_text().strip()
    parser.add_argument(
        "--package", type=Path, default=ROOT / f"build/fp840g5-native_{version}_amd64.deb"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate platform/package/data and show the plan; no changes or USB commands",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Restore the saved service/PAM selection without deleting prints",
    )
    parser.add_argument(
        "--no-pam", action="store_true", help="Install driver while leaving PAM selection unchanged"
    )
    args = parser.parse_args()
    if args.rollback:
        if args.check or args.no_pam:
            parser.error("--rollback cannot be combined with --check or --no-pam")
        if os.geteuid() != 0:
            parser.error("Rollback requires sudo")
        rollback()
        return
    platform_check()
    if run("dpkg", "--print-architecture", capture=True).stdout.strip() != "amd64":
        parser.error("This validated target is amd64")
    package = package_check(args.package)
    vendor_check()
    if args.check:
        print("[plan] Platform, package checksum and local vendor-data checks passed.", flush=True)
        print(
            "[plan] Root install will probe ROM/silicon/flash/firmware, back up configuration,",
            flush=True,
        )
        print(
            "       install the private library/data, select it in fprintd, and enable PAM unless --no-pam.",
            flush=True,
        )
        print("[plan] No system configuration or sensor state was changed.", flush=True)
        return
    if os.geteuid() != 0:
        parser.error("Install requires sudo; use --check without sudo to inspect the plan")
    install(package, args.no_pam)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"[error] {error}", file=sys.stderr)
        sys.exit(1)
