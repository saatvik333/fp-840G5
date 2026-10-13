# Firmware container and host-driver findings

The analyzed binary was HP's proprietary **Windows host driver DLL**,
`synaWudfBioUsb.dll`. Its firmware-container structure was also inspected.
The firmware body remains encrypted: no decrypted firmware source or independent
RSA signature validation is claimed.

[HP sp135736 metadata](https://ftp.hp.com/pub/softpaq/sp135501-136000/sp135736.html)
lists the EliteBook 840 G5. Its Windows driver is 5.5.28.1099; sp110163 is
5.5.27.1099. Both contain byte-identical `6_07f_hp_cmit_mis_qm.xpfwext` files.
The tool checks pinned installer and DLL SHA-256 values before deriving payloads.

| Container property | Value |
| --- | --- |
| SHA-256 | `2b68b33668215cfc2a08c80a1f2c0e66c4c02927895d70a7d5f237e5201d5d2f` |
| Firmware declaration | 6.07.0164 |
| Encryption / target / product | 2 / 1 / `0x30` |
| Start address | `0x51002000` |
| Extension | 1.2, build 15 |
| Encrypted body / signature | 196,512 / 256 bytes |

An ASCII header precedes NUL/`0x1a` delimiters, the encrypted body and trailing
signature. Verified package hashes and signature layout do not independently
validate the reader's RSA signature.

The HP reset command is 11,973 bytes: a five-byte envelope plus an 11,968-byte
body at sp135736 DLL file offset `0x1b54f4` / virtual address `0x1801b60f4`.
The older DLL's body is at file offset `0x1b5504`. The locally derived command has
SHA-256 `7f379b1648326f031753d2d0a974bae75bc59a95f847b9c6478a124f32b3c17a`.
The pinned data project's 00ab set inherited a Lenovo reset; local staging
replaces it with the verified HP command. Neither binary is redistributed here.

Absent-extension status wire bytes `b0 04` mean little-endian **0x04b0**. The
patch fixes that constant and rejects unexpected/truncated responses before an
upload. Data/firmware lookup now honors the private installation prefix. A
captured-G5 factory-empty identity gate exists in the patch but is untested on
hardware; the public installer refuses factory-empty readers.

The Windows encryption-2 update path uses 2,048-byte chunks. The native driver's
4,096-byte path was neither changed nor upload-tested. The successful hardware
integration uses firmware already installed on the reader. Raw vendor
decompilation, reset/data blobs and firmware remain local, outside public assets.

See [source pins](../sources.lock.json), [upstream credit](../NOTICE.md),
[the patch](../patches/libfprint-hp840g5.patch) and [hardware validation](validation.md).
