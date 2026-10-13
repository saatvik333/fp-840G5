# HP EliteBook 840 G5 fingerprint support for Linux

Experimental native **libfprint + fprintd** support for the **138a:00ab** Validity
reader. Enrollment, matching, wrong-finger rejection, cancellation, fresh `sudo`
authentication and GNOME screen unlock passed on an Ubuntu 26.04.1 EliteBook 840 G5.

This project builds on the native Validity/VCSFW driver in
[libfprint !626](https://gitlab.freedesktop.org/libfprint/libfprint/-/merge_requests/626),
with HP-specific fixes, reproducible builds and a preservation guard.
[NOTICE.md](NOTICE.md) credits the upstream work. It uses Ubuntu's normal
fingerprint stack; python-validity and replacement fprintd daemons are not installed.

**Project code is open source; HP firmware remains proprietary.** The Windows host
driver and firmware-container format were analyzed. The firmware payload remains
encrypted and was not decrypted/decompiled. Vendor payloads are obtained separately
on your computer and excluded from Git and public packages. See [licensing](docs/licensing.md).

## Validated installation target

| Requirement | Value |
| --- | --- |
| Laptop / OS | HP EliteBook 840 G5, Ubuntu 26.04 amd64 |
| USB ID / revision | `138a:00ab` / `0164` |
| Silicon | `0x0190:0x0070`, captured G5 `0xd51` variant |
| ROM | 6.7, build 164, product 48 |
| Existing flash | Five partitions, 1 MiB |
| Installed firmware extension | 1.2, eight modules |

Check `lsusb` first. Other variants, including `06cb:00b7`, are unvalidated.
The installer refuses unknown identities, empty flash and missing firmware;
it does not provision or flash a factory-empty reader. This is an **alpha release**
based on an unmerged upstream proposal.

## Install from source

Run locally on the matching Ubuntu laptop. Keep the reader clear during setup.
Read [vendor licensing](docs/licensing.md) before the separate download step.

```bash
sudo apt update
sudo apt install --no-install-recommends \
  build-essential git meson ninja-build pkgconf 7zip dpkg-dev \
  libglib2.0-dev libgusb-dev libssl-dev libcairo2-dev \
  python3-usb fprintd libpam-fprintd

git clone https://github.com/saatvik333/fp-840G5.git
cd fp-840G5
git checkout v0.1.0-alpha.2

python3 tools/native_build.py --with-vendor-data --accept-vendor-terms
python3 tools/compile_checks.py --with-vendor-data
python3 tools/build_ubuntu_package.py
python3 tools/install_ubuntu.py --check
sudo python3 tools/install_ubuntu.py
```

Commands are verbose. Building opens no reader and changes no system service.
`--check` validates platform/package/data without USB commands or system changes.
Root installation runs a metadata-only preflight, saves configuration, installs
under `/opt/fp-840g5`, selects the library through two standard fprintd drop-ins,
and enables Ubuntu's fingerprint PAM profile. Distribution libraries and existing
`/var/lib/fprint` metadata are preserved. `--no-pam` leaves PAM selection unchanged.

The [prerelease](https://github.com/saatvik333/fp-840G5/releases/tag/v0.1.0-alpha.2)
also provides a **driver-only .deb**, SHA-256 checksums and complete corresponding
source. The package contains no vendor firmware/data and does not activate itself.
See [installation details](docs/install.md) for that route and existing-print behavior.

## Enroll and use

Open **Settings → System → Users → Fingerprint Login** and enroll an unused finger.
The local-terminal alternative is:

```bash
fprintd-list "$USER"
fprintd-enroll -f right-middle-finger "$USER"
fprintd-verify -f right-middle-finger "$USER"
sudo -k id -u
```

Wait for the prompt before touching. Ubuntu's tested sudo profile allows one
attempt for ten seconds, followed by password fallback. A rejected scan may need
a retry. Fingerprint PAM skips known remote sessions; test sudo in a local terminal.

The guard denies whole-storage clear and foreign/malformed record deletion,
while permitting native Linux print management. Native-format records can still
be pruned by stock fprintd when storage is full. Format validation is not
cryptographic ownership proof. See [preservation details](docs/install.md#existing-fingerprints).

## Tests and limits

Six native unit suites pass, including **219 Validity cases**, plus four default
preservation API checks and six policy/delegation tests. [Hardware results](docs/validation.md)
record the cancellation failure reproduced and fixed. CI builds/tests source
without vendor downloads or hardware access.

Cold boot, suspend/resume, fresh-session login/keyring, GUI enrollment/deletion,
multi-print identification and factory-empty provisioning remain untested end to
end. The generalized community installer is also awaiting fresh-system root
activation testing. Settings visibility and fingerprint-only sudo/screen unlock
were confirmed on the test laptop. Some scans needed retries; this is functional
validation on one reader, not a biometric accuracy measurement.

## Rollback

```bash
sudo python3 tools/install_ubuntu.py --rollback
```

This restores saved service/PAM selection while retaining package/data and all
prints. It does not downgrade an earlier package version. [Rollback details](docs/install.md#rollback).

## Contribute

For a source-only build with no HP downloads:

```bash
python3 tools/native_build.py
python3 tools/compile_checks.py
python3 -m unittest discover -s tests -v
```

Read [CONTRIBUTING.md](CONTRIBUTING.md), [host-driver findings](docs/firmware.md),
[source pins](sources.lock.json), and [the patch](patches/libfprint-hp840g5.patch).
Project code is **LGPL-2.1-or-later**; vendor software retains its own terms.
