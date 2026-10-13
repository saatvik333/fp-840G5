#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (C) 2026 Saatvik Sharma
"""Query only ROM, silicon, flash layout and firmware metadata on 138a:00ab."""

import argparse
import json
import struct
import sys

READ_COMMANDS = (
    ("rom", b"\x01"),
    ("flash", b"\x3e"),
    ("silicon", b"\x75"),
    ("firmware", b"\x43\x02"),
)


def decode(name, response):
    if len(response) < 2:
        raise ValueError(f"Truncated {name} status")
    status = struct.unpack_from("<H", response)[0]
    payload = response[2:]
    result = {"status": f"0x{status:04x}", "payload_bytes": len(payload)}
    if status != 0:
        return result
    if name == "rom":
        if len(payload) != 36:
            raise ValueError("Expected the captured 36-byte ROM metadata")
        stamp, build, major, minor, product = struct.unpack_from("<IIBBxB", payload)
        result.update(timestamp=stamp, build=build, major=major, minor=minor, product=product)
    elif name == "flash":
        if len(payload) < 14:
            raise ValueError("Truncated flash metadata")
        manufacturer, model, blocks, _, size, _, partitions = struct.unpack_from("<7H", payload)
        if len(payload) != 14 + partitions * 12:
            raise ValueError("Truncated or trailing flash partition records")
        result.update(
            jedec=f"{manufacturer:04x}:{model:04x}", bytes=blocks * size, partitions=partitions
        )
    elif name == "silicon":
        if len(payload) != 8:
            raise ValueError("Unexpected silicon metadata size")
        reserved, version, major = struct.unpack("<IHH", payload)
        result.update(reserved=reserved, hw_major=f"0x{major:04x}", hw_version=f"0x{version:04x}")
        result["captured_g5_variant"] = reserved == 0 and major == 0x0190 and version == 0x0070
    elif name == "firmware":
        if len(payload) < 10:
            raise ValueError("Truncated firmware metadata")
        major, minor, modules, stamp = struct.unpack_from("<HHHI", payload)
        if len(payload) != 10 + modules * 12:
            raise ValueError("Truncated or trailing firmware module records")
        result.update(major=major, minor=minor, modules=modules, timestamp=stamp)
    return result


def probe(bus=None, address=None, verbose=False):
    import usb.core
    import usb.util

    candidates = [
        d
        for d in usb.core.find(find_all=True, idVendor=0x138A, idProduct=0x00AB)
        if (bus is None or d.bus == bus) and (address is None or d.address == address)
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected exactly one 138a:00ab reader; found {len(candidates)}")
    device = candidates[0]
    result = {
        "usb_id": "138a:00ab",
        "bus": device.bus,
        "address": device.address,
        "mutation_commands_sent": 0,
        "queries": {},
    }
    claimed = False
    try:
        config = device.get_active_configuration()
        interface = config[(0, 0)]
        endpoints = {ep.bEndpointAddress: ep for ep in interface}
        if not {0x01, 0x81}.issubset(endpoints):
            raise RuntimeError("Expected bulk endpoints 01/81 are absent")
        if any(
            usb.util.endpoint_type(endpoints[e].bmAttributes) != usb.util.ENDPOINT_TYPE_BULK
            for e in (0x01, 0x81)
        ):
            raise RuntimeError("Command endpoints are not bulk endpoints")
        if device.is_kernel_driver_active(0):
            raise RuntimeError("A kernel driver owns the reader; the probe will not detach it")
        usb.util.claim_interface(device, 0)
        claimed = True
        for name, command in READ_COMMANDS:
            if verbose:
                print(
                    f"[probe] {name}: sending metadata query {command.hex()}",
                    file=sys.stderr,
                    flush=True,
                )
            if device.write(0x01, command, timeout=3000) != len(command):
                raise RuntimeError("Short USB command write")
            response = bytes(device.read(0x81, 16384, timeout=3000))
            result["queries"][name] = decode(name, response)
            if verbose:
                print(
                    f"[probe] {name}: status={result['queries'][name]['status']}, {len(response)} response bytes",
                    file=sys.stderr,
                    flush=True,
                )
    except (usb.core.USBError, RuntimeError, ValueError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        if claimed:
            usb.util.release_interface(device, 0)
        usb.util.dispose_resources(device)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bus", type=int)
    parser.add_argument("--address", type=int)
    parser.add_argument("--verbose", action="store_true", default=True)
    parser.add_argument("--quiet", dest="verbose", action="store_false")
    args = parser.parse_args()
    data = probe(args.bus, args.address, args.verbose)
    print(json.dumps(data, indent=2))
    sys.exit(1 if "error" in data else 0)
