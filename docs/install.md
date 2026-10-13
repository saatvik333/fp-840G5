# Install, authenticate and roll back

## Before installation

Use the hardware table in [README](../README.md). The installer supports Ubuntu
26.04 amd64 and the captured `138a:00ab` EliteBook 840 G5 with existing firmware.
Other operating systems can build the source but have not been runtime-validated.
Run locally with the reader clear. The installer refuses active python-validity,
open-fprintd or temporary test daemons and custom/masked fprintd units.
This alpha installer handles initial activation: existing fprintd drop-ins are
refused, including a previous native integration. Roll back that integration
before changing package versions; automatic in-place upgrades are not supported.

Build and obtain vendor data as your regular user; only final installation needs
sudo. Read [licensing](licensing.md) before using `--accept-vendor-terms`.

## Source build

Follow [README](../README.md#install-from-source). GLib development tools, GUsb,
OpenSSL 3, Cairo, Meson, Ninja and a C compiler are required. The preservation
policy test uses GLib 2.80 or later. Source commits are pinned and the exported
patch is applied before testing. `compile_checks.py --with-vendor-data` checks
native data loaders and compiles hardware helpers without running them.

## Driver-only release package

Install README's prerequisites and clone/check out the matching release. Prepare
the separately licensed data and run its loader checks:

```bash
python3 tools/native_build.py --with-vendor-data --accept-vendor-terms
python3 tools/compile_checks.py --with-vendor-data
```

Download `fp840g5-native_0.1.0~alpha1_amd64.deb` and its `.deb.sha256` from the
[release](https://github.com/saatvik333/fp-840G5/releases/tag/v0.1.0-alpha.1),
placing both in `build/`. This route still builds/tests local source while
preparing data. Then:

```bash
python3 tools/install_ubuntu.py --check
sudo python3 tools/install_ubuntu.py
```

`dpkg -i` alone does not fetch vendor data, select the library or enable PAM.
The installer checks the package checksum/name/architecture and payload rules,
checks local vendor-data hashes, then probes ROM/silicon/flash/firmware metadata.
It temporarily runtime-masks fprintd during that probe and removes the mask on
completion or failure. It backs up configuration, installs the private library
and local data, selects the normal fprintd stack and enables its PAM profile.
Use `--no-pam` to retain your current PAM selection.

## Existing fingerprints

Existing `/var/lib/fprint` metadata is retained. Another OS's sensor identifiers
may be uninterpretable to this driver and are not silently converted into Linux
enrollment. Choose an unused finger for the first test.

The guard denies synchronous/asynchronous full-storage clear, and deletion of
foreign, malformed or unrecognized-format records. Individual stored Validity
prints with a validated native `FP1-` identity are permitted. Stock fprintd can
therefore manage Linux prints, including pruning host-unknown **native-format**
records when storage is full; that API call cannot be distinguished from an
explicit native deletion. Foreign/Windows-format records remain blocked. If
this protection prevents data-full enrollment, enrollment fails instead of
erasing those records.

Format validation is not cryptographic ownership verification. The guard does
not cover separate programs accessing USB directly. The validated installer
performs no factory reset or firmware upload.

## Authentication

Settings and the CLI use stock fprintd. The tested Ubuntu sudo profile allowed
one attempt for ten seconds, followed by password fallback. GNOME uses its
standard fingerprint PAM service for unlocking. Wait for a prompt before touching.

Known SSH remote sessions are skipped by `pam_fprintd`; test `sudo -k id -u` in
a local terminal. An administrator working remotely can launch it through the
already logged-in user's local manager:

```bash
systemd-run --user --pty --wait --collect sudo -k id -u
```

This grants no new authorization; a matching fingerprint is still required.
Fresh-session login and keyring behavior remain untested here. A fingerprint
supplies no password for decrypting a password-based login keyring.

## Rollback

```bash
sudo python3 tools/install_ubuntu.py --rollback
```

Backups are root-protected under `/var/lib/fp-840g5/backups/`. Rollback restores
the previous two service drop-ins or their absence, and disables the fingerprint
PAM profile if it was previously disabled. `pam-auth-update` is used without
`--force`; locally modified PAM files require manual review and are preserved.
Sensor templates and host enrollment metadata are retained. Package/runtime
files stay installed; rollback changes configuration, not the package version.

The generalized installer has offline boundary checks. Hardware testing used the
preceding private activation procedure; this general installer has not yet been
run through fresh-system root activation end to end.
