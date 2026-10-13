# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Reject incomplete reader identities before they can reach root activation."""

import importlib.util
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("probe_reader", ROOT / "tools/probe_reader.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class MetadataDecodingTests(unittest.TestCase):
    def setUp(self):
        self.payloads = {
            "rom": struct.pack("<IIBBxB", 1415491824, 164, 6, 7, 48) + bytes(24),
            "flash": struct.pack("<7H", 1, 2, 256, 0, 4096, 0, 5) + bytes(60),
            "silicon": struct.pack("<IHH", 0, 0x0070, 0x0190),
            "firmware": struct.pack("<HHHI", 1, 2, 8, 1579571365) + bytes(96),
        }

    def test_complete_identity_decoded(self):
        results = {name: probe.decode(name, b"\0\0" + data) for name, data in self.payloads.items()}
        self.assertEqual(results["rom"]["product"], 48)
        self.assertEqual(results["flash"]["bytes"], 1048576)
        self.assertTrue(results["silicon"]["captured_g5_variant"])
        self.assertEqual(results["firmware"]["modules"], 8)

    def test_truncated_and_trailing_records_rejected(self):
        for name, payload in self.payloads.items():
            for data in (b"", b"\0", b"\0\0" + payload[:-1], b"\0\0" + payload + b"\0"):
                with self.subTest(name=name, length=len(data)), self.assertRaises(ValueError):
                    probe.decode(name, data)

    def test_error_status_does_not_decode_identity(self):
        for name in self.payloads:
            result = probe.decode(name, b"\xb0\x04")
            self.assertEqual(result["status"], "0x04b0")
            self.assertNotIn("major", result)


if __name__ == "__main__":
    unittest.main()
