# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
import importlib.util
import io
import tarfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "audit_package", Path(__file__).resolve().parents[1] / "tools/audit_package.py"
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def fixture(extra=None):
    files = {
        "./opt/fp-840g5/lib/libfprint-2.so.2.0.0": b"ELF test fixture",
        "./opt/fp-840g5/lib/preserve-prints.so": b"ELF test fixture",
    }
    if extra:
        files.update(extra)
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as data:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            data.addfile(member, io.BytesIO(content))
    return output.getvalue()


class PackagePublicationTests(unittest.TestCase):
    def test_driver_only_archive_accepted(self):
        self.assertEqual(len(audit.audit_data(fixture())), 2)

    def test_vendor_data_and_authentication_storage_rejected(self):
        for path in (
            "./opt/fp-840g5/share/libfprint/validity/reset.bin",
            "./usr/share/doc/fp840g5-native/vendor.dll",
            "./var/lib/fprint/user/template",
            "./home/user/key.pem",
            "../escape",
            "/absolute",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                audit.audit_data(fixture({path: b"forbidden fixture"}))

    def test_private_material_and_lab_paths_rejected(self):
        for content in (
            b"-----BEGIN PRIVATE KEY-----",
            b"/home/example/private",
        ):
            with self.subTest(content=content), self.assertRaises(ValueError):
                audit.audit_data(fixture({"./usr/share/doc/fp840g5-native/test": content}))

    def test_control_archive_cannot_hide_activation_scripts(self):
        def control_archive(name, kind=tarfile.REGTYPE, duplicate=False):
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w") as data:
                for _ in range(2 if duplicate else 1):
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    if kind == tarfile.SYMTYPE:
                        member.linkname = "postinst"
                    data.addfile(member, io.BytesIO())
            return output.getvalue()

        for name, kind, duplicate in (
            ("./postinst", tarfile.REGTYPE, False),
            ("./control", tarfile.SYMTYPE, False),
            ("./control", tarfile.REGTYPE, True),
            ("../control", tarfile.REGTYPE, False),
            ("/control", tarfile.REGTYPE, False),
        ):
            with (
                self.subTest(name=name, kind=kind, duplicate=duplicate),
                patch.object(
                    audit.subprocess,
                    "check_output",
                    side_effect=[control_archive(name, kind, duplicate), fixture()],
                ),
                self.assertRaises(ValueError),
            ):
                audit.audit_package(Path("fixture.deb"))
        with patch.object(
            audit.subprocess,
            "check_output",
            side_effect=[control_archive("./control"), fixture()],
        ):
            self.assertEqual(len(audit.audit_package(Path("fixture.deb"))), 2)


if __name__ == "__main__":
    unittest.main()
