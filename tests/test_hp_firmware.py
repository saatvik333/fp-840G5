# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "hp_firmware", Path(__file__).resolve().parents[1] / "tools/hp_firmware.py"
)
hp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hp)


class HPArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = hp.ROOT / "artifacts/hp/sp135736/src/driver/INF/x64" / hp.FIRMWARE_NAME
        if not cls.path.exists():
            raise unittest.SkipTest("Run tools/hp_firmware.py fetch to obtain the vendor fixture")
        cls.firmware = hp.checked_read(cls.path, hp.FIRMWARE_SHA256)

    def test_vendor_layout_and_cross_package_identity(self):
        fields, _, body, signature = hp.parse_fwext(self.firmware)
        self.assertEqual(fields["FirmwareVersion"], "6.07.0164")
        self.assertEqual(len(body), 196512)
        self.assertEqual(
            hp.sha256(body), "de530c8bdbcc461e27bcd883bee45502689648c74a7294dfc86f74d650a5a80d"
        )
        self.assertEqual(len(signature), 256)
        old = hp.ROOT / "artifacts/hp/sp110163/src/driver/INF/x64" / hp.FIRMWARE_NAME
        if old.exists():
            self.assertEqual(self.firmware, old.read_bytes())

    def test_corruption_fails_package_hash(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.xpfwext"
            path.write_bytes(self.firmware[:-1] + bytes([self.firmware[-1] ^ 1]))
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                hp.checked_read(path, hp.FIRMWARE_SHA256)

    def test_missing_delimiter_and_truncated_body_rejected(self):
        end = self.firmware.index(b"\x1a")
        with self.assertRaisesRegex(ValueError, "Missing"):
            hp.parse_fwext(self.firmware[:end])
        with self.assertRaisesRegex(ValueError, "Truncated"):
            hp.parse_fwext(self.firmware[: end + 1] + b"\0" * 256)

    def test_unexpected_signature_size_rejected(self):
        corrupted = self.firmware.replace(
            b"SignatureLength = 0x0100", b"SignatureLength = 0x0080", 1
        )
        with self.assertRaisesRegex(ValueError, "signature layout"):
            hp.parse_fwext(corrupted)

    def test_reset_is_located_in_real_driver_and_ranges_are_checked(self):
        result = hp.analyze("sp135736")
        self.assertEqual(result["reset_command"]["body_virtual_address"], "0x1801b60f4")
        self.assertEqual(result["reset_command"]["sha256"], hp.RESET_SHA256)
        dll = (hp.ROOT / result["driver"]["path"]).read_bytes()
        with self.assertRaisesRegex(ValueError, "outside"):
            hp.file_offset_to_va(dll, len(dll) - 4, 64)
        with self.assertRaisesRegex(ValueError, "Not a DOS/PE"):
            hp.file_offset_to_va(b"MZ", 0, 1)


class SyntheticContainerTests(unittest.TestCase):
    """Exercise parser failure boundaries without distributing vendor fixtures."""

    def container(self):
        header = (
            b"// Validity Sensors V4 Firmware Extension File\n"
            b"Signed = 0x0001\nSignatureLength = 0x0100\n"
        )
        return header + b"\x00\x1a" + b"synthetic encrypted-body fixture" + bytes(256)

    def test_synthetic_container_split(self):
        fields, header, payload, signature = hp.parse_fwext(self.container())
        self.assertEqual(fields["Signed"], "0x0001")
        self.assertFalse(header.endswith(b"\0"))
        self.assertEqual(payload, b"synthetic encrypted-body fixture")
        self.assertEqual(len(signature), 256)

    def test_invalid_layout_and_truncation(self):
        for content in (
            b"not a container",
            self.container().replace(b"0x0100", b"0x0080"),
            self.container().split(b"\x1a")[0] + b"\x1a" + bytes(256),
        ):
            with self.subTest(length=len(content)), self.assertRaises(ValueError):
                hp.parse_fwext(content)

    def test_non_ascii_header_rejected(self):
        with self.assertRaises(UnicodeDecodeError):
            hp.parse_fwext(self.container().replace(b"File", b"Fil\xff", 1))


if __name__ == "__main__":
    unittest.main()
