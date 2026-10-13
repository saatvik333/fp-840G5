#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Check the Git index for excluded artifacts and obvious credential material."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_ROOTS = {"artifacts", "sources", "build", "dist", "evidence", ".venv"}
FORBIDDEN_SUFFIXES = {
    ".bin",
    ".exe",
    ".dll",
    ".deb",
    ".so",
    ".a",
    ".pem",
    ".key",
    ".pcap",
    ".pcapng",
    ".xpfwext",
    ".pyc",
}
PATTERNS = (
    re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=\r\n]{32,}"),
    re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{40,}"),
)


def main():
    listing = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"])
    paths = [Path(p.decode()) for p in listing.split(b"\0") if p]
    if not paths:
        raise SystemExit("No tracked public files to audit")
    for path in paths:
        if path.parts[0] in FORBIDDEN_ROOTS or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            raise SystemExit(f"Forbidden artifact is tracked: {path}")
        if (path.parts[0] == "tools" and path.suffix == ".sh") or path.name in (
            "fprintd_test_control.py",
            "rea-session.mjs",
            "inspect_target.py",
        ):
            raise SystemExit(f"Private lab helper is tracked: {path}")
        content = subprocess.check_output(["git", "-C", str(ROOT), "show", ":" + path.as_posix()])
        if b"\0" in content or len(content) > 2_000_000:
            raise SystemExit(f"Unexpected binary or raw analysis dump: {path}")
        if any(pattern.search(content) for pattern in PATTERNS):
            raise SystemExit(
                f"Potential credential material found in {path}; contents are not printed"
            )
    print(
        f"[verified] {len(paths)} tracked text files; generated/vendor/private artifact roots excluded"
    )
    print(
        "[scope] Pattern/allowlist audit complements manual review; it is not exhaustive secret detection"
    )


if __name__ == "__main__":
    main()
