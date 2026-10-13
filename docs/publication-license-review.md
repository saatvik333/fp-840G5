# Publication licensing and provenance review

Verified 2026-10-13 from the pinned source checkouts, both downloaded HP installers,
and HP's official terms. This review concerns redistribution rights found in those
materials; it does not establish a jurisdiction-specific interoperability exception.

Publish the original project tools, native patch, and independently written
research under **LGPL-2.1-or-later**. Publish a driver-only binary release together
with its corresponding source. Keep vendor firmware, command/data blobs,
decompiled vendor code, and the existing blob-bearing package out of public Git
history and release assets.

| Material | Verified license/provenance and publication treatment |
| --- | --- |
| Native libfprint changes | Commit `1cf22b89c335b1b63efcccb1113234be9ba2e9d0` declares `LGPLv2.1+`; the modified Validity C/header files and unit tests explicitly allow LGPL 2.1 or later. Preserve existing copyright and warranty notices. [Project license declaration](https://gitlab.freedesktop.org/ggiesen/libfprint/-/blob/1cf22b89c335b1b63efcccb1113234be9ba2e9d0/meson.build), [representative header](https://gitlab.freedesktop.org/ggiesen/libfprint/-/blob/1cf22b89c335b1b63efcccb1113234be9ba2e9d0/libfprint/drivers/validity/validity_pair.c). |
| Original tools and narrative | These can use the project's LGPL-2.1-or-later license. This does not relicense third-party files fetched by the tools. Credit the pinned upstream implementation and protocol references. |
| Python reference | Commit `128a9ebc9e7e21b12d606b636d839906473dee18` is MIT. Retain its copyright and permission notice if copying substantial code; referencing protocol facts alone does not require vendoring its source. [Pinned license](https://github.com/SimpleX-T/python-validity/blob/128a9ebc9e7e21b12d606b636d839906473dee18/LICENSE). |
| Runtime data generator | Commit `687c5ea51392582d5bcb1e4fa86eea0832a50c5f` supplies MIT notices for generator/packaging and Python origins. Its README explicitly leaves HP payload redistribution terms unestablished. Do not interpret MIT as permission to redistribute recovered vendor payloads. [License](https://gitlab.freedesktop.org/ggiesen/libfprint-validity-data/-/blob/687c5ea51392582d5bcb1e4fa86eea0832a50c5f/LICENSE), [scope and provenance](https://gitlab.freedesktop.org/ggiesen/libfprint-validity-data/-/blob/687c5ea51392582d5bcb1e4fa86eea0832a50c5f/README.md). |

## HP package evidence

Neither extracted package tree nor its 7-Zip archive listing contains a standalone
license file. **Both installer executables contain an embedded ASCII HP EULA**,
including the clause: “You do not have the right to distribute the Software Product.”

| Official installer | SHA-256 of the inspected executable | File offset of that clause |
| --- | --- | --- |
| [sp135736.exe](https://ftp.hp.com/pub/softpaq/sp135501-136000/sp135736.exe), driver 5.5.28.1099 | `be83e4cab0db523e66818b9eee9b8bd2c0e9144821bf96cdc162bb73d62ad311` | `0x4d91c` |
| [sp110163.exe](https://ftp.hp.com/pub/softpaq/sp110001-110500/sp110163.exe), driver 5.5.27.1099 | `5c5af715975797a0259136390159e0f45149592f16ed6c7e6617d9384e1854d5` | `0x48f79` |

Both embedded agreements reserve HP/supplier rights, restrict transfer to a
one-time transfer of the whole product, and limit reverse engineering subject to
applicable-law exceptions. HP's official EULA includes firmware and drivers in
its scope; its website terms require agreement to supplied licenses and prohibit
redistribution without an express grant. No separate firmware/reset redistribution
grant was found. User-side download/extraction avoids redistribution by this
project but does not waive HP's terms. [HP EULA](https://support.hp.com/us-en/document/ish_4416646-4390016-16),
[HP website terms, software section](https://www.hp.com/country/us/en/termsofuse.html).

## Patch and source archive inspection

The audited patch had SHA-256
`19f0cb07ed0ebdf501ae957c1551b7b8c3e6b5f4dac27def4d7a0378d1a97af4`.
It modifies 12 C/header/Meson/test files and adds no firmware container, reset
body, vendor executable, certificate/key blob, or long vendor hex payload. Its
small command/status constants and synthetic test fixtures are host protocol
implementation data. It removes no upstream copyright/license notices.
Dated modification notices (2026-10-13) were added to all 12 modified files
before the release patch was exported, addressing LGPL section 2(b).
[Audited patch](../patches/libfprint-hp840g5.patch), [LGPL 2.1](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html).

The pinned native tracked tree has no standalone `.bin`, `.fw`, `.xpfwext`,
`.exe`, `.dll`, `.deb`, `.so`, or `.a` artifact. Its binary fixtures comprise
22 PNGs, four JPGs, and 26 PCAPNGs. The Validity capture is 6,432 bytes with 58
packets of at most 132 bytes; neither inspected HP reset nor firmware marker
appears in it. This is not a blanket provenance clearance for every opaque
device recording. Unused packet captures and sample images may be omitted from
the source archive with an exclusion manifest; retain everything required to
compile the actual released library. [Pinned fixture/test tree](https://gitlab.freedesktop.org/ggiesen/libfprint/-/tree/1cf22b89c335b1b63efcccb1113234be9ba2e9d0/tests),
[fixture selection](https://gitlab.freedesktop.org/ggiesen/libfprint/-/blob/1cf22b89c335b1b63efcccb1113234be9ba2e9d0/tests/meson.build).

LGPL sections 0, 1, 2, 4 and 6 require notices, the license text, and corresponding
source for the distributed modified library. Offer the exact patched source,
all compiled modules/interface headers, and build/install scripts beside the
driver-only package at the same release. Include the guard's source and build
recipe; retain shared-library replacement/relinking rights. A patch plus a remote
upstream URL alone is not the same as supplying the complete corresponding
source from the binary's distribution location. Preserve other upstream notices
in the source archive rather than claiming every file originated here.
[Pinned upstream license](https://gitlab.freedesktop.org/ggiesen/libfprint/-/blob/1cf22b89c335b1b63efcccb1113234be9ba2e9d0/COPYING), [official LGPL text](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html).

The previous local package copied the staged vendor-data directory, including
firmware and the HP reset, into the archive. Exclude that package; inspect the new
driver-only package's file list before publishing. Keep `artifacts/`, generated
data, downloaded source/data checkouts, build caches, vendor decompilation and
raw analysis dumps out of the public project snapshot. The public installer may
fetch/extract them separately on the user's machine after explicit acknowledgement;
clearly describe the runtime components as proprietary. Sanitized factual
summaries, hashes, offsets and source links can remain in the research narrative.
[Staging code](../tools/stage_native.py), [package builder](../tools/build_ubuntu_package.py).
