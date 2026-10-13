# Security reports

This experimental project loads a native library into the system fingerprint
daemon and can enable fingerprint PAM authentication. Findings that affect
authentication, parser bounds, sensor data preservation or installation/recovery
should be reported privately through GitHub's **Report a vulnerability** option
on this repository's Security tab.

Do not include live fingerprints, device serials, pairing keys, passwords or
raw USB/TLS traffic. A synthetic reproducer, affected version, code path and
redacted status information are preferred. Use ordinary issues for compatibility
reports that contain no sensitive exploit or personal material.

The project is currently an alpha; there is no supported stable release or
security-response SLA. Password fallback is retained. The guard protects the
normal daemon's deletion APIs, not arbitrary direct USB access or root programs.
