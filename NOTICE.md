# Attribution and scope

Project additions and modifications: Copyright (C) 2026 Saatvik Sharma.
They are available under LGPL-2.1-or-later; see [LICENSE](LICENSE).

This project builds on the native Validity/VCSFW driver proposed by Gianni Giesen
and the libfprint contributors in
[libfprint merge request !626](https://gitlab.freedesktop.org/libfprint/libfprint/-/merge_requests/626).
It is a patch and installation project, not an independently recovered firmware
implementation. The pinned libfprint source retains its existing copyright and
license notices. Dated notices identify our modified files.

The [libfprint-validity-data project](https://gitlab.freedesktop.org/ggiesen/libfprint-validity-data)
provides the separately downloaded data generator. Its generator/packaging and
vendor payloads have different licensing considerations. The
[python-validity work](https://github.com/uunicorn/python-validity) and
[HP-specific reference branch](https://github.com/SimpleX-T/python-validity)
were protocol references; python-validity is not installed by these tools.

HP and Synaptics/Validity retain rights in their proprietary Windows drivers,
firmware and extracted payloads. They are not covered by this project's license
and are not included in public repository or release packages. See
[licensing](docs/licensing.md) for the separate download policy.

The public Debian package contains the open-source libfprint library and our
preservation guard. Matching complete corresponding source is supplied alongside
the binary release, including the patched libfprint modules and build scripts.
The shared library remains replaceable under `/opt/fp-840g5/lib`.

This community project is not affiliated with or endorsed by HP, Synaptics,
Validity, Ubuntu or the upstream libfprint project. Product names identify the
hardware and software being supported.
