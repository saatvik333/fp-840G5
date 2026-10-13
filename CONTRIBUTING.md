# Contributing

Contributions to native driver correctness, cancellation/recovery, integration
and validation are welcome. Read [validation](docs/validation.md) before extending
support claims. Changes use LGPL-2.1-or-later, preserve upstream attribution and
include dated modification notices where required by the upstream license.

## Reproduce the source checks

Install a C toolchain, Meson, Ninja, pkgconf, GLib development tools (2.80+ for
the policy tests), GUsb, OpenSSL 3 and Cairo. Python 3.11+ is required.

```bash
python3 tools/native_build.py
python3 tools/compile_checks.py
python3 -m unittest discover -s tests -v
ruff check tools/*.py tests
```

These default commands require no vendor downloads or physical reader. The
vendor fixture tests skip when separately obtained artifacts are absent; the
synthetic parser/preflight/preservation tests still run. CI follows this path.

The patched source is under ignored `sources/libfprint-vcsfw`. Export a driver
change with:

```bash
git -C sources/libfprint-vcsfw diff --check
git -C sources/libfprint-vcsfw diff --binary > patches/libfprint-hp840g5.patch
```

Keep the exact base commit in [sources.lock.json](sources.lock.json). The package
builder requires the complete source diff to match the patch. Describe the
trigger, behavior change and meaningful checks in your pull request. Do not
report unit tests as hardware validation.

## Hardware reports

Use the issue template with model, OS/kernel, USB ID and metadata/status results.
Separate requested finger from confirmed physical finger. Report cancellation,
reopen, delayed touch, suspend/resume and fresh-boot results individually. Do not
upload fingerprint templates/images, device serials, pairing keys, passwords,
SSH material, raw USB/TLS captures, vendor binaries or vendor decompilation.
Do not enable raw protocol debug logging for an ordinary issue report.

The compiled `reader-smoke` and `enroll-cancel-smoke` helpers actively operate
hardware and are not automatic test runners. Use them only after metadata
preflight, stop competing daemons, keep the reader clear and preserve existing
records. Factory-empty provisioning and firmware upload remain unvalidated.

## Releases

Build the driver-only Ubuntu package with `tools/build_ubuntu_package.py`, audit
it with `tools/audit_package.py`, and create matching complete corresponding
source with `tools/make_release.py`. Never upload the local vendor-data directory
or a package containing it. Source and binary must be available together under
the same release with licenses and checksums. See [licensing](docs/licensing.md).
