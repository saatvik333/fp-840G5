# Licensing and vendor downloads

The native patch and original project tools are **LGPL-2.1-or-later**. Existing
libfprint copyrights and license notices are preserved. See [LICENSE](../LICENSE)
and [NOTICE.md](../NOTICE.md).

HP's firmware, Windows driver, reset payload and other recovered vendor data
are not open source and are not relicensed by this project. Both inspected HP
SoftPaq installers embed an EULA denying general redistribution. Consequently
the repository, source release and public Debian package omit those payloads,
vendor decompilation dumps and personal hardware captures. The
[sourced publication review](publication-license-review.md) records the checked
packages, hashes, license scope and terms.

Before using `--with-vendor-data --accept-vendor-terms`, review the
[HP EULA](https://support.hp.com/us-en/document/ish_4416646-4390016-16),
[HP software website terms](https://www.hp.com/country/us/en/termsofuse.html),
and the [pinned runtime-data license/provenance](https://gitlab.freedesktop.org/ggiesen/libfprint-validity-data/-/blob/687c5ea51392582d5bcb1e4fa86eea0832a50c5f/README.md).
Only obtain/use those files where you have the applicable rights. The flag
acknowledges their separate terms; it does not grant additional rights or waive
HP's restrictions. Do not republish your generated vendor-data directory.

The downloader obtains **sp135736 directly from HP**, verifies the pinned
package and DLL SHA-256 values, extracts it with 7-Zip without running any
Windows executable, and checks the firmware/reset hashes. Runtime common data
is generated from the pinned upstream data checkout; its MIT generator license
does not establish a blanket redistribution grant for vendor payloads.

The public `.deb` contains only the open-source library/guard and documentation.
Matching complete patched library source, our guard, build scripts and license
notices are offered at the same release. Upstream opaque capture/image test
fixtures are omitted from that source archive with an exclusion manifest; all
source needed for the released library remains. A supplied generator provides
synthetic input for the upstream image-assembly unit test. There are no personal templates,
device serials, pairing keys, SSH material or passwords in the public artifacts.
