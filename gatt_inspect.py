"""Dump GATT services/characteristics for a PitPat treadmill."""

from __future__ import annotations

import argparse
import asyncio

from bleak import BleakClient, BleakScanner

from pitpat import DEFAULT_ADDRESS

PITPAT_HINTS = ("pitpat", "t01", "deerrun", "superun")
FBA0 = "0000fba0-0000-1000-8000-00805f9b34fb"


async def find_device(address: str | None) -> str:
    if address:
        return address
    print("Scanning for PitPat-T01...")
    devices = await BleakScanner.discover(timeout=12.0, return_adv=True)
    for device, adv in devices.values():
        name = (device.name or adv.local_name or "").lower()
        uuids = {u.lower() for u in (adv.service_uuids or [])}
        if any(h in name for h in PITPAT_HINTS) or FBA0 in uuids:
            print(f"Found {device.name}  {device.address}")
            return device.address
    raise SystemExit("No PitPat treadmill found. Power it on and retry.")


async def inspect(address: str | None) -> None:
    addr = await find_device(address)
    print(f"Connecting to {addr}...")
    async with BleakClient(addr) as client:
        print(f"Connected. MTU={client.mtu_size}\n")
        for service in client.services:
            print(f"Service {service.uuid}  {service.description}")
            for char in service.characteristics:
                props = ",".join(char.properties)
                print(f"  Char {char.uuid}  [{props}]  {char.description}")
                for desc in char.descriptors:
                    print(f"    Desc {desc.uuid}  {desc.description}")
            print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect PitPat treadmill GATT")
    parser.add_argument(
        "--address",
        default=DEFAULT_ADDRESS,
        help="BLE address. If omitted, scan for a PitPat / DeerRun / Superun pad",
    )
    args = parser.parse_args()
    asyncio.run(inspect(args.address))


if __name__ == "__main__":
    main()
