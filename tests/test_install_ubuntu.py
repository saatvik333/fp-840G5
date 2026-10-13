# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Safety boundaries for unknown or unprovisioned hardware; no USB/system writes."""

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("install_ubuntu", ROOT / "tools/install_ubuntu.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def known_metadata():
    return {
        "usb_id": "138a:00ab",
        "queries": {
            "rom": {
                "status": "0x0000",
                "major": 6,
                "minor": 7,
                "build": 164,
                "product": 48,
                "payload_bytes": 36,
                "timestamp": 1415491824,
            },
            "flash": {"status": "0x0000", "partitions": 5, "bytes": 1048576, "payload_bytes": 74},
            "silicon": {
                "status": "0x0000",
                "reserved": 0,
                "hw_major": "0x0190",
                "hw_version": "0x0070",
                "payload_bytes": 8,
            },
            "firmware": {
                "status": "0x0000",
                "major": 1,
                "minor": 2,
                "modules": 8,
                "payload_bytes": 106,
            },
        },
    }


class MetadataBoundaryTests(unittest.TestCase):
    def test_known_provisioned_reader_allowed(self):
        installer.metadata_check(known_metadata())

    def test_rejects_factory_empty_unknown_or_error_responses(self):
        cases = [
            ("flash", "partitions", 0),
            ("flash", "partitions", 4),
            ("flash", "bytes", 2097152),
            ("rom", "build", 165),
            ("rom", "product", 49),
            ("silicon", "hw_version", "0x0060"),
            ("firmware", "modules", 0),
            ("firmware", "minor", 3),
            ("rom", "status", "0x04b0"),
            ("rom", "timestamp", 0),
            ("rom", "payload_bytes", 16),
            ("firmware", "payload_bytes", 10),
            ("flash", "payload_bytes", 14),
        ]
        for group, field, value in cases:
            with self.subTest(group=group, field=field, value=value):
                data = known_metadata()
                data["queries"][group][field] = value
                with self.assertRaises(ValueError):
                    installer.metadata_check(data)
        for data in ({}, {"error": "short response"}, {"usb_id": "138a:00ab", "queries": {}}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                installer.metadata_check(data)

    def test_every_missing_identity_field_rejected(self):
        source = known_metadata()
        for group, values in source["queries"].items():
            for field in values:
                data = copy.deepcopy(source)
                del data["queries"][group][field]
                with self.subTest(group=group, field=field), self.assertRaises(ValueError):
                    installer.metadata_check(data)


class PlatformBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.os = self.root / "os-release"
        self.os.write_text('ID=ubuntu\nVERSION_ID="26.04"\n')
        self.product = self.root / "product_name"
        self.product.write_text("HP EliteBook 840 G5\n")
        self.usb = self.root / "usb"
        self.usb.mkdir()
        self.reader("1-2", "138a", "00ab")

    def reader(self, name, vendor, product, revision="0164"):
        node = self.usb / name
        node.mkdir()
        for field, value in [("idVendor", vendor), ("idProduct", product), ("bcdDevice", revision)]:
            (node / field).write_text(value + "\n")

    def check(self):
        return installer.platform_check(self.os, self.product, self.usb)

    def test_known_platform_allowed(self):
        self.assertEqual(self.check(), self.usb / "1-2")

    def test_wrong_model_os_revision_and_multiple_readers_rejected(self):
        self.product.write_text("HP EliteBook 840 G6")
        with self.assertRaises(ValueError):
            self.check()
        self.product.write_text("HP EliteBook 840 G5")
        self.os.write_text('ID=ubuntu\nVERSION_ID="24.04"')
        with self.assertRaises(ValueError):
            self.check()
        self.os.write_text('ID=ubuntu\nVERSION_ID="26.04"')
        (self.usb / "1-2/bcdDevice").write_text("0165")
        with self.assertRaises(ValueError):
            self.check()
        (self.usb / "1-2/bcdDevice").write_text("0164")
        self.reader("1-3", "138a", "00ab")
        with self.assertRaises(ValueError):
            self.check()

    def test_other_validity_sensor_rejected(self):
        self.reader("1-3", "06cb", "00b7")
        with self.assertRaises(ValueError):
            self.check()


class VendorBoundaryTests(unittest.TestCase):
    def test_empty_or_extra_vendor_files_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                installer.vendor_check(root)
            (root / "extra.bin").write_bytes(b"not vendor data")
            with self.assertRaises(ValueError):
                installer.vendor_check(root)

    def test_vendor_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "link").symlink_to("/dev/null")
            with self.assertRaises(ValueError):
                installer.vendor_check(root)


class RecoveryBoundaryTests(unittest.TestCase):
    def test_service_selection_restored_even_if_pam_update_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dropins = root / "dropins"
            dropins.mkdir()
            backup = root / "backup"
            backup.mkdir()
            for name in installer.NAMES:
                (dropins / name).write_text("new library selection")
            (backup / "state.json").write_text(
                json.dumps(
                    {
                        "created_by": "fp840g5-public-installer",
                        "pam_was_enabled": False,
                        "dropins": dict.fromkeys(installer.NAMES, False),
                    }
                )
            )

            def fail_pam(*command, **kwargs):
                if "pam-auth-update" in command:
                    raise subprocess.CalledProcessError(1, command)

            with (
                patch.object(installer, "DROPINS", dropins),
                patch.object(installer, "run", side_effect=fail_pam) as commands,
                self.assertRaises(subprocess.CalledProcessError),
            ):
                installer.restore_config(backup)
            self.assertFalse(any(dropins.iterdir()))
            commands.assert_any_call("systemctl", "daemon-reload")

    def test_existing_service_overrides_require_review(self):
        for override in (
            "/etc/systemd/system/fprintd.service.d/custom.conf",
            "/etc/systemd/system/fprintd.service.d/90-fp840g5-native.conf",
        ):
            with (
                self.subTest(override=override),
                patch.object(
                    installer,
                    "run",
                    side_effect=[
                        subprocess.CompletedProcess(
                            [], 0, "/usr/lib/systemd/system/fprintd.service\n"
                        ),
                        subprocess.CompletedProcess([], 0, override + "\n"),
                    ],
                ),
                self.assertRaises(ValueError),
            ):
                installer.service_check()


if __name__ == "__main__":
    unittest.main()
