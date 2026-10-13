#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Measure first-attempt outcomes and fprintd timings without changing enrolled prints."""

import argparse
import json
import math
import os
import pwd
import statistics
import time
from pathlib import Path

FINGERS = tuple(
    f"{hand}-{finger}"
    for hand in ("left", "right")
    for finger in ("thumb", "index-finger", "middle-finger", "ring-finger", "little-finger")
)
RETRIES = {
    "verify-retry-scan",
    "verify-swipe-too-short",
    "verify-finger-not-centered",
    "verify-remove-and-retry",
    "verify-too-fast",
}


def timing_summary(values):
    values = sorted(values)
    if not values:
        return {"samples": 0, "median_ms": None, "p95_ms": None}
    return {
        "samples": len(values),
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(values[math.ceil(0.95 * len(values)) - 1], 3),
    }


def summarize(attempts):
    result = {}
    for profile in sorted({row["profile"] for row in attempts}):
        result[profile] = {}
        for group in ("genuine", "unenrolled"):
            rows = [r for r in attempts if r["profile"] == profile and r["group"] == group]
            matches = sum(r["status"] == "verify-match" for r in rows)
            no_matches = sum(r["status"] == "verify-no-match" for r in rows)
            result[profile][group] = {
                "attempts": len(rows),
                "matches": matches,
                "no_matches": no_matches,
                "quality_retries": sum(r["status"] in RETRIES for r in rows),
                "timeouts": sum(r["status"] == "timeout" for r in rows),
                "errors": sum(
                    r["status"]
                    not in RETRIES
                    | {
                        "verify-match",
                        "verify-no-match",
                        "timeout",
                    }
                    for r in rows
                ),
                "first_attempt_match_rate": matches / len(rows) if rows else None,
                "capture_arming": timing_summary(
                    [r["ready_ms"] for r in rows if r.get("ready_ms") is not None]
                ),
                "start_to_first_status_including_human": timing_summary(
                    [r["first_status_ms"] for r in rows if r["first_status_ms"] is not None]
                ),
                "reported_presence_to_first_status": timing_summary(
                    [
                        r["presence_to_status_ms"]
                        for r in rows
                        if r["presence_to_status_ms"] is not None
                    ]
                ),
            }
    return result


class Benchmark:
    def __init__(self, Gio, GLib, device):
        self.Gio, self.GLib, self.device = Gio, GLib, device
        self.claimed = False
        self.active = False
        self.current = None
        self.loop = None
        self.timeout_id = None
        self.wait_ready = False
        self.stage = None
        self.device.connect("g-signal", self.on_signal)
        self.device.connect("g-properties-changed", self.on_properties)

    def call(self, method, value=None):
        args = self.GLib.Variant("(s)", (value,)) if value is not None else None
        start = time.monotonic()
        reply = self.device.call_sync(method, args, self.Gio.DBusCallFlags.NONE, 135000, None)
        elapsed = round((time.monotonic() - start) * 1000, 3)
        print(f"[method] {method}: {elapsed:.3f} ms", flush=True)
        return reply.unpack() if reply else (), elapsed

    def claim(self, username):
        # Release even if a transport error obscures a successful Claim response.
        self.claimed = True
        return self.call("Claim", username)[1]

    def stop(self):
        if self.active:
            try:
                return self.call("VerifyStop")[1]
            except self.GLib.Error as error:
                if (
                    self.Gio.DBusError.get_remote_error(error)
                    != "net.reactivated.Fprint.Error.NoActionInProgress"
                ):
                    raise
            finally:
                self.active = False
        return None

    def release(self):
        elapsed = None
        try:
            self.stop()
        finally:
            if self.claimed:
                try:
                    elapsed = self.call("Release")[1]
                finally:
                    self.claimed = False
        return elapsed

    def on_signal(self, proxy, sender, name, parameters):
        if (
            name != "VerifyStatus"
            or self.current is None
            or self.current["first_status_ms"] is not None
        ):
            return
        status, done = parameters.unpack()
        now = time.monotonic()
        row = self.current
        row["status"] = status
        row["done"] = done
        row["first_status_ms"] = round((now - row["started"]) * 1000, 3)
        if row["presence_at"] is not None:
            row["presence_to_status_ms"] = round((now - row["presence_at"]) * 1000, 3)
        print(
            f"[scan] {status}; done={done}; start-to-status={row['first_status_ms']:.3f} ms",
            flush=True,
        )
        # A retry is an unsuccessful first attempt, never silently another scan.
        self.loop.quit()

    def on_properties(self, proxy, changed, invalidated):
        if self.current is None:
            return
        properties = changed.unpack()
        if properties.get("finger-needed") is True and self.current["ready_ms"] is None:
            self.current["ready_ms"] = round((time.monotonic() - self.current["started"]) * 1000, 3)
            if self.stage == "ready":
                self.loop.quit()
        if properties.get("finger-present") is True and self.current["presence_at"] is None:
            self.current["presence_at"] = time.monotonic()

    def expire(self):
        self.timeout_id = None
        self.current["failure_stage"] = self.stage
        if self.stage == "ready":
            self.current["status"] = "readiness-timeout"
        print(f"[scan] Timeout waiting for {self.stage}; no scan result.", flush=True)
        self.loop.quit()
        return self.GLib.SOURCE_REMOVE

    def wait(self, seconds):
        self.timeout_id = self.GLib.timeout_add_seconds(seconds, self.expire)
        try:
            self.loop.run()
        finally:
            if self.timeout_id is not None:
                self.GLib.source_remove(self.timeout_id)
                self.timeout_id = None

    def trial(self, profile, group, number, enrolled_finger):
        # Drain queued properties/signals from Stop before setting up the next attempt.
        context = self.GLib.MainContext.default()
        while context.pending():
            context.iteration(False)
        row = {
            "profile": profile,
            "group": group,
            "number": number,
            "status": "timeout",
            "done": False,
            "first_status_ms": None,
            "presence_to_status_ms": None,
            "ready_ms": None,
            "operator_prompted": False,
            "presence_at": None,
            "started": time.monotonic(),
        }
        self.current = row
        self.loop = self.GLib.MainLoop()
        self.stage = "ready"
        self.active = True
        try:
            row["verify_start_ms"] = self.call("VerifyStart", enrolled_finger)[1]
            if self.wait_ready and row["ready_ms"] is None and row["first_status_ms"] is None:
                self.wait(5)
                if row.get("failure_stage") == "ready":
                    return row
            if row["first_status_ms"] is not None:
                return row
            self.stage = "scan"
            self.loop = self.GLib.MainLoop()
            row["operator_prompted"] = True
            print("TOUCH NOW: place the requested finger flat on the reader.", flush=True)
            self.wait(self.timeout)
        finally:
            if self.timeout_id is not None:
                self.GLib.source_remove(self.timeout_id)
                self.timeout_id = None
            self.current = None
            self.stage = None
            row["verify_stop_ms"] = self.stop()
            row.pop("started")
            row.pop("presence_at")
        return row


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_EXCL refuses overwriting an earlier measurement or following a symlink.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=pwd.getpwuid(os.getuid()).pw_name)
    parser.add_argument("--enrolled-finger", required=True, choices=FINGERS)
    parser.add_argument("--unenrolled-finger", required=True, choices=FINGERS)
    parser.add_argument("--genuine-trials", type=int, default=5)
    parser.add_argument("--negative-trials", type=int, default=5)
    parser.add_argument(
        "--profiles", nargs="+", choices=("warm", "reopened"), default=["warm", "reopened"]
    )
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument(
        "--wait-ready",
        action="store_true",
        help="Wait for fresh finger-needed feedback before TOUCH NOW (requires the improved driver)",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.enrolled_finger == args.unenrolled_finger:
        parser.error("Choose distinct enrolled and unenrolled fingers")
    if (
        not all(1 <= n <= 100 for n in (args.genuine_trials, args.negative_trials))
        or not 5 <= args.timeout <= 60
    ):
        parser.error("Trial counts must be 1..100 and timeout 5..60 seconds")
    if len(set(args.profiles)) != len(args.profiles):
        parser.error("Profiles must not be repeated")
    if args.output.exists():
        parser.error("Output already exists; choose a new path to preserve previous measurements")
    # Lazy import keeps offline summary tests independent of D-Bus and hardware.
    from gi.repository import Gio, GLib

    manager = Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SYSTEM,
        Gio.DBusProxyFlags.NONE,
        None,
        "net.reactivated.Fprint",
        "/net/reactivated/Fprint/Manager",
        "net.reactivated.Fprint.Manager",
        None,
    )
    paths = manager.call_sync("GetDevices", None, Gio.DBusCallFlags.NONE, 15000, None).unpack()[0]
    if len(paths) != 1:
        raise SystemExit(f"Expected exactly one reader; found {len(paths)}")
    device = Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SYSTEM,
        Gio.DBusProxyFlags.NONE,
        None,
        "net.reactivated.Fprint",
        paths[0],
        "net.reactivated.Fprint.Device",
        None,
    )
    bench = Benchmark(Gio, GLib, device)
    bench.timeout = args.timeout
    bench.wait_ready = args.wait_ready
    enrolled = bench.call("ListEnrolledFingers", args.username)[0][0]
    if args.enrolled_finger not in enrolled or args.unenrolled_finger in enrolled:
        raise SystemExit(
            "The chosen positive/negative fingers disagree with current host enrollment"
        )
    report = {
        "schema": 1,
        "enrolled_finger": args.enrolled_finger,
        "unenrolled_finger": args.unenrolled_finger,
        "ground_truth": "operator-supplied finger attribution",
        "timing_limit": "Start-to-status includes human reaction and capture. Presence-to-status uses an optional driver event, not a physical contact clock.",
        "accuracy_limit": "One-person functional sample; no population FAR/FRR or spoof-resistance estimate.",
        "attempts": [],
        "claims_ms": [],
        "releases_ms": [],
        "complete": False,
    }
    print(
        "Each trial is ONE placement. Lift after the result; never retry within a trial.",
        flush=True,
    )
    print("No enrollment, deletion, firmware or authentication policy is changed.", flush=True)
    try:
        for profile in args.profiles:
            for group, finger, count in (
                ("genuine", args.enrolled_finger, args.genuine_trials),
                ("unenrolled", args.unenrolled_finger, args.negative_trials),
            ):
                for number in range(1, count + 1):
                    print(f"\n[{profile}] {group} {number}/{count}: use {finger}.", flush=True)
                    input("Keep reader CLEAR, then press Enter to arm this trial: ")
                    if not bench.claimed:
                        report["claims_ms"].append(
                            {"profile": profile, "ms": bench.claim(args.username)}
                        )
                    row = bench.trial(profile, group, number, args.enrolled_finger)
                    report["attempts"].append(row)
                    print("LIFT your finger. This trial is finished.", flush=True)
                    if profile == "reopened":
                        report["releases_ms"].append({"profile": profile, "ms": bench.release()})
                    if not row["operator_prompted"]:
                        raise RuntimeError(
                            "Reader failed to arm or returned an outcome before the touch prompt; stop for diagnosis"
                        )
                    if group == "unenrolled" and row["status"] == "verify-match":
                        raise RuntimeError(
                            "Unexpected acceptance: stop and confirm which physical finger was used"
                        )
                    if row["status"] in ("verify-disconnected", "verify-unknown-error"):
                        raise RuntimeError("Device error: stop for diagnosis")
            if bench.claimed:
                report["releases_ms"].append({"profile": profile, "ms": bench.release()})
        report["complete"] = True
    except BaseException as error:
        report["interrupted_by"] = type(error).__name__
        report["error"] = str(error)
        raise
    finally:
        try:
            bench.release()
        finally:
            report["summary"] = summarize(report["attempts"])
            write_report(args.output, report)
            print(f"\n[report] {args.output}", flush=True)
            print(json.dumps(report["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
