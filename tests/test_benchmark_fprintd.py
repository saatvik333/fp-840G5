# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Do not turn timeouts, retries or a tiny sample into an accuracy claim."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    "benchmark_fprintd", Path(__file__).resolve().parents[1] / "tools/benchmark_fprintd.py"
)
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)


class SummaryTests(unittest.TestCase):
    def row(self, status, group="genuine", profile="warm", presence=None):
        return {
            "profile": profile,
            "group": group,
            "status": status,
            "first_status_ms": None if status == "timeout" else 2000.0,
            "presence_to_status_ms": presence,
        }

    def test_retries_and_timeouts_do_not_disappear_from_denominator(self):
        rows = [
            self.row(s)
            for s in (
                "verify-match",
                "verify-no-match",
                "verify-retry-scan",
                "timeout",
                "verify-unknown-error",
            )
        ]
        result = bench.summarize(rows)["warm"]["genuine"]
        self.assertEqual(result["attempts"], 5)
        self.assertEqual(result["first_attempt_match_rate"], 0.2)
        self.assertEqual(
            (result["no_matches"], result["quality_retries"], result["timeouts"], result["errors"]),
            (1, 1, 1, 1),
        )
        self.assertEqual(result["reported_presence_to_first_status"]["samples"], 0)
        self.assertEqual(result["start_to_first_status_including_human"]["samples"], 4)

    def test_negative_acceptance_and_profiles_kept_separate(self):
        rows = [
            self.row("verify-match", "unenrolled"),
            self.row("verify-no-match", "unenrolled", "reopened"),
        ]
        result = bench.summarize(rows)
        self.assertEqual(result["warm"]["unenrolled"]["matches"], 1)
        self.assertEqual(result["reopened"]["unenrolled"]["matches"], 0)
        self.assertIsNone(result["warm"]["genuine"]["first_attempt_match_rate"])

    def test_quantiles_and_absent_contact_event(self):
        self.assertEqual(
            bench.timing_summary([]), {"samples": 0, "median_ms": None, "p95_ms": None}
        )
        values = list(range(1, 21))
        self.assertEqual(bench.timing_summary(values)["p95_ms"], 19)
        self.assertEqual(bench.timing_summary(values)["median_ms"], 10.5)

    def test_report_is_private_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            bench.write_report(path, {"complete": False})
            self.assertEqual(json.loads(path.read_text()), {"complete": False})
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                bench.write_report(path, {})


class CleanupTests(unittest.TestCase):
    def test_stop_failure_still_releases_and_is_not_hidden(self):
        client = bench.Benchmark.__new__(bench.Benchmark)
        client.claimed = True
        client.stop = Mock(side_effect=RuntimeError("stop failed"))
        client.call = Mock(return_value=((), 2.0))
        with self.assertRaisesRegex(RuntimeError, "stop failed"):
            client.release()
        client.call.assert_called_once_with("Release")
        self.assertFalse(client.claimed)

    def test_only_first_scan_outcome_is_counted(self):
        client = bench.Benchmark.__new__(bench.Benchmark)
        client.loop = Mock()
        client.current = {
            "first_status_ms": None,
            "started": 0.0,
            "presence_at": None,
            "presence_to_status_ms": None,
        }
        with patch.object(bench.time, "monotonic", return_value=1.25):
            client.on_signal(
                None, None, "VerifyStatus", Mock(unpack=lambda: ("verify-retry-scan", False))
            )
            client.on_signal(
                None, None, "VerifyStatus", Mock(unpack=lambda: ("verify-match", True))
            )
        self.assertEqual(client.current["status"], "verify-retry-scan")
        client.loop.quit.assert_called_once()

    def test_ready_feedback_and_presence_use_distinct_clocks(self):
        client = bench.Benchmark.__new__(bench.Benchmark)
        client.loop = Mock()
        client.stage = "ready"
        client.current = {"ready_ms": None, "started": 10.0, "presence_at": None}
        with patch.object(bench.time, "monotonic", return_value=10.015):
            client.on_properties(None, Mock(unpack=lambda: {"finger-needed": True}), [])
        self.assertEqual(client.current["ready_ms"], 15.0)
        client.loop.quit.assert_called_once()
        with patch.object(bench.time, "monotonic", return_value=12.0):
            client.on_properties(None, Mock(unpack=lambda: {"finger-present": True}), [])
        self.assertEqual(client.current["presence_at"], 12.0)
        self.assertEqual(client.current["ready_ms"], 15.0)

    def test_readiness_timeout_does_not_become_a_biometric_rejection(self):
        client = bench.Benchmark.__new__(bench.Benchmark)
        client.current = {"status": "timeout"}
        client.loop = Mock()
        client.GLib = Mock(SOURCE_REMOVE=False)
        client.stage = "ready"
        client.timeout_id = 123
        client.expire()
        self.assertEqual(client.current["status"], "readiness-timeout")
        self.assertEqual(client.current["failure_stage"], "ready")
        self.assertIsNone(client.timeout_id)


if __name__ == "__main__":
    unittest.main()
