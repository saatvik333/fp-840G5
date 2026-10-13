# Hardware validation

Verified **2026-10-13** on one EliteBook 840 G5 running Ubuntu 26.04.1 LTS,
amd64, kernel 7.0.0-38-generic. Reader: `138a:00ab`, revision `0164`, silicon
`0x0190:0x0070`, ROM 6.7/build 164/product 48. It already had five flash partitions
and firmware extension 1.2/eight modules. No firmware upload or factory reset
was performed. Public results omit personal identifiers, biometric payloads,
pairing material, raw USB/TLS traffic and vendor decompilation.

| Test | Observed result |
| --- | --- |
| Initial open/list/close | Three successes, about 0.86–0.97 seconds to open |
| Initial chip records | One |
| New right-middle-finger enrollment | `enroll-completed`; metadata survived daemon restart |
| Correct finger | `verify-match` |
| Requested right index against enrolled middle | `verify-no-match` |
| Initial cancellation/reopen | Calibration failure `0x0450` reproduced |
| Patched VerifyStop | Succeeded in 0.063 seconds |
| Match after cancellation, same open session | `verify-match` |
| Release/reclaim | Succeeded in 1.123 seconds |
| Match after reopen | `verify-match`; physical right middle finger confirmed |
| Enrollment cancellation | Two cancellations in one open session; `G_IO_ERROR_CANCELLED` after cleanup |
| Count after cancellation and reopen | Two; original record plus new Linux enrollment retained |
| Patched open/list/close | 0.984 / 0.850 / 0.862 seconds; two records each time |
| Stock fprintd ABI | Eager relocation passed with private library |
| Normal Ubuntu daemon | Lists retained right-middle-finger enrollment |
| Fresh local sudo | `sudo -k id -u` ran as root after `verify-match`; fingerprint-only use confirmed |
| GNOME unlock | Locked state, then `verify-match` and unlocked state; no-password use confirmed |
| Settings | Fingerprint Login visible, confirmed by tester |
| Cleanup | Temporary daemons stopped, original USB ACL restored |

Cancellation now finishes bounded capture/enrollment/match cleanup before returning
cancellation. Opening establishes an idle boundary before calibration. Those
paths need no provisioning, reset or deletion. Some scans were rejected before
a successful retry. No biometric accuracy or spoof-resistance claim follows
from these functional tests. Physical finger attribution is based on instructions
and tester confirmation, not inferred from USB status.

## Automated verification

Six unit suites include 219 Validity cases. Four default delete/clear guard checks
and six mock production-policy/delegation checks pass without hardware. Separate
local loader checks verify the actual HP reset/firmware/common data. Python tests
cover container corruption/truncation and installer refusal of unknown ROM,
silicon, layout, firmware, OS/model, multiple or conflicting readers. Package
auditing rejects vendor-data paths, activation scripts, authentication storage
and private build-home paths. CI uses no vendor downloads or real reader.

The public driver-only package was built in an isolated Ubuntu 26.04 amd64
container from the pinned Docker base image. Its six native unit suites, guard
checks and eager stock-fprintd ABI check passed. Package auditing confirmed that
vendor data and activation scripts are absent. Offline Python tests also cover
truncated device metadata, service override refusal and service-selection
recovery when a PAM update fails.

## Untested paths

Cold boot; suspend/resume; fresh-session login/keyring; GUI enrollment/deletion;
multi-print identification; other devices/OS releases; factory-empty provisioning;
firmware upload; fresh-system root activation with the generalized installer.
CLI enrollment and visible Settings are not reported as GUI enrollment testing.
With one host-known print, fprintd's `any` request still uses verification;
gallery identification needs at least two host-known prints.
