# Scan speed and accuracy review

Reviewed 2026-10-13 against the pinned native driver and the live Ubuntu daemon.
This describes the **unreleased alpha.3 candidate** on `improve-scan-feedback`,
not a change to the existing alpha.2 release or the test laptop's installation.

There is no evidence that this is the fastest or most accurate implementation
possible. Capture and biometric matching run on the sensor using the existing
vendor firmware. The host implementation prepares commands, transports them,
handles capture failures and validates the matched record. These fixes preserve
the matching command, calibration iterations, enrollment completion criteria
and record/finger correlation checks. No matching threshold was relaxed.

## Findings and changes

| Finding | Change | Verification |
| --- | --- | --- |
| Verification did not publish ready/presence states | Report `NEEDED` after capture acknowledgement; report `PRESENT` for a physical type-2 event or confirmed usable geometry | Source-path review; hardware property/event retest pending |
| Non-empty flagged captures were silently treated as no finger | Classify empty, usable, retryable and invalid captures separately; clean up before reporting `REMOVE_FINGER` | Regression failed with the old policy and passes with the fix |
| Truncated/bad capture replies could enter an endless no-finger loop | Check command status, the 16-byte payload and its declared 12-byte body | Null, truncation, extra-byte, bad-status and length-mismatch cases pass |
| Every attempt/re-arm rebuilt the same calibrated IDENTIFY command | Cache its plaintext per calibration/open session; invalidate on recalibration, close, failed open and reconnect | Compare cache to uncached bytes, change calibration, invalidate and compare again |
| Hex dumps were formatted even when discarded | Check the debug log level before constructing capture/response/identify dumps | Native suites, optimized build and package checks pass |
| Prompt timing included operator delay and retries could hide failed first scans | Add a benchmark that records one placement per trial, separate outcomes and optional ready-state gating | Eight offline benchmark tests; live baseline was incomplete |

Retry completion uses libfprint's `report(retry)` followed by `complete(NULL)`.
The verify and identify tests run real libfprint actions against a fake device,
check one retry report, preserve its error domain and confirm finger-state reset.
A malformed capture produces a protocol error. Flawed/malformed frames skip
matching and follow capture-stop, match cleanup and LED-off before the result.
Existing cancellation and print-preservation tests still pass.

The cache contains the capture command only. Each send still copies the plaintext
and creates a fresh TLS record. It does not cache a scan, match outcome, encrypted
record or calibration across a close/reopen.

## Measurements and limits

The original installation was built with optimization level 3. Its live fprintd
Claim round trip was approximately **1.25 seconds**, including opening,
calibration and daemon overhead. `VerifyStart` took approximately **5 ms**.
This does not mean a scan or match takes 5 ms.

The synthetic, optimized host benchmark used 100,000 iterations and a 13,653-byte
command. Uncached command construction averaged about **37 microseconds**;
an already-populated cache lookup averaged below **0.01 microseconds**. This
removes repeated host preparation, roughly 0.04 ms per command in this fixture.
The first construction, USB transport, acquisition, matching and human delay
are excluded. This is not an end-to-end fingerprint speedup claim.

The incomplete live baseline had two matches, two no-matches and one timeout in
five warm genuine trials, and five no-matches in five unenrolled-finger trials.
The first three prompted reopened genuine trials had two matches and one timeout.
An additional armed trial was not given a touch instruction and is excluded.
Physical attribution was supplied by the tester. These are observations for one
person and one enrollment, not population false-accept/false-reject rates. The
sample cannot attribute every failed scan to driver code or enrollment quality.

No candidate hardware scan, sudo/unlock result, Windows comparison, cold-boot,
suspend or multi-user accuracy measurement has been performed yet. A full
latency comparison needs independent contact/acquisition timing; this sensor's
confirmed presence feedback can arrive only after acquisition completes.

## Reproduce without a reader

```bash
python3 tools/native_build.py
python3 tools/compile_checks.py
build/benchmark-capture 100000
python3 -m unittest discover -s tests -v
```

The command benchmark uses generated calibration values, opens no device and
prints timings and byte counts only. Results depend on build optimization and
host load; do not compare debug and release builds as if they were the same.

## Hardware retest after installing the candidate

Run in a local Ubuntu session using `/usr/bin/python3` with `python3-gi` installed.
Choose one currently enrolled finger and a distinct finger the tester confirms
is unenrolled. Example:

```bash
/usr/bin/python3 tools/benchmark_fprintd.py \
  --enrolled-finger right-index-finger \
  --unenrolled-finger right-middle-finger \
  --genuine-trials 5 --negative-trials 5 --wait-ready \
  --output evidence/scan-review-retest-1.json
```

The benchmark checks current host enrollment, claims the normal fprintd device,
and requests the same enrolled finger for both positive and negative placements.
Warm trials keep one claim; reopened trials release and reclaim each time.
Keep the reader clear, press Enter, then touch only at `TOUCH NOW`; lift after
each result. A retry ends that first attempt. An unexpected negative acceptance,
pre-prompt outcome or readiness failure stops the run for diagnosis. Results
survive interruptions; existing reports are never overwritten and use mode 0600.

With `--wait-ready`, the fresh `finger-needed` event gates the touch prompt.
Readiness and reported presence are separate clocks; absent presence is recorded
as missing data. The current alpha.2 does not provide verification readiness:
omit that flag for a legacy diagnostic run, whose prompt has weaker timing.
No enrollment, deletion, firmware or PAM configuration is changed by this tool.
Do not publish raw device captures or biometric data with a report.

The property and retry semantics follow the [fprintd device API](https://fprint.freedesktop.org/fprintd-dev/Device.html).
Enrollment quality and different contact conditions must be evaluated separately
before claiming a biometric accuracy improvement.
