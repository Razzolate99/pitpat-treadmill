"""Scan for nearby BLE devices and flag likely treadmill / fitness machines."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

from bleak import BleakScanner
from bleak.backends.scanner import AdvertisementData
from bleak.backends.device import BLEDevice

FTMS = "00001826-0000-1000-8000-00805f9b34fb"
WILINK = "0000fe00-0000-1000-8000-00805f9b34fb"
DEVICE_INFO = "0000180a-0000-1000-8000-00805f9b34fb"
HEART_RATE = "0000180d-0000-1000-8000-00805f9b34fb"
RSC = "00001814-0000-1000-8000-00805f9b34fb"

FITNESS_HINTS = (
    "tread",
    "walk",
    "pad",
    "run",
    "fit",
    "ks-",
    "king",
    "merach",
    "urevo",
    "deerrun",
    "yesoul",
    "sportstech",
    "icon",
    "ifit",
    "proform",
    "horizon",
    "sole",
    "zwift",
    "ftms",
    "jj-bt",
    "fithome",
    "renpho",
    "goplus",
    "sunny",
    "schwinn",
    "nordic",
    "peloton",
    "lifespan",
    "egofit",
    "xiaomi",
    "mijia",
)


def _short_uuid(uuid: str) -> str:
    u = uuid.lower()
    if u.startswith("0000") and u.endswith("-0000-1000-8000-00805f9b34fb"):
        return f"0x{u[4:8].upper()}"
    return uuid


def classify(name: str, service_uuids: list[str]) -> str:
    uuids = {u.lower() for u in service_uuids}
    labels: list[str] = []
    if FTMS in uuids:
        labels.append("FTMS (standard treadmill/fitness)")
    if WILINK in uuids:
        labels.append("Wilink/WalkingPad")
    if HEART_RATE in uuids:
        labels.append("Heart Rate")
    if RSC in uuids:
        labels.append("Running Speed and Cadence")
    lowered = (name or "").lower()
    if any(h in lowered for h in FITNESS_HINTS):
        labels.append("name looks like fitness gear")
    return ", ".join(labels) if labels else ""


def format_device(device: BLEDevice, adv: AdvertisementData) -> str:
    name = device.name or adv.local_name or "(no name)"
    uuids = list(adv.service_uuids or [])
    tag = classify(name, uuids)
    uuid_s = ", ".join(_short_uuid(u) for u in uuids) or "-"
    mfg = "-"
    if adv.manufacturer_data:
        parts = []
        for company_id, payload in adv.manufacturer_data.items():
            parts.append(f"{company_id}({payload.hex()})")
        mfg = "; ".join(parts)
    marker = "  << LIKELY TREADMILL/FITNESS" if tag else ""
    return (
        f"{device.address}  RSSI={adv.rssi:>4}  {name}{marker}\n"
        f"    services: {uuid_s}\n"
        f"    manufacturer: {mfg}\n"
        f"    flags: {tag or '-'}"
    )


async def scan(seconds: float) -> None:
    seen: dict[str, tuple[BLEDevice, AdvertisementData]] = {}

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        prev = seen.get(device.address)
        if prev is None or (adv.rssi or -999) > (prev[1].rssi or -999) or (
            not (prev[0].name or prev[1].local_name) and (device.name or adv.local_name)
        ):
            seen[device.address] = (device, adv)

    print(f"Scanning BLE for {seconds:.0f}s starting {datetime.now().isoformat(timespec='seconds')}...")
    print("Turn the treadmill on (and pairing/NFC mode if it has one).\n")

    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    await asyncio.sleep(seconds)
    await scanner.stop()

    if not seen:
        print("No BLE advertisements heard. Bluetooth may be off, or nothing nearby is advertising.")
        return

    ranked = sorted(
        seen.values(),
        key=lambda pair: (
            0 if classify(pair[0].name or pair[1].local_name or "", list(pair[1].service_uuids or [])) else 1,
            -(pair[1].rssi or -999),
        ),
    )

    print(f"Found {len(ranked)} BLE device(s):\n")
    for device, adv in ranked:
        print(format_device(device, adv))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan for BLE treadmill / fitness devices")
    parser.add_argument("--seconds", type=float, default=20, help="How long to scan")
    args = parser.parse_args()
    asyncio.run(scan(args.seconds))


if __name__ == "__main__":
    main()
