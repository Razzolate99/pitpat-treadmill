"""Command-line control for a PitPat-T01 treadmill over BLE."""

from __future__ import annotations

import argparse
import asyncio
import sys

from pitpat import DEFAULT_ADDRESS, Treadmill, find_treadmill


async def cmd_scan() -> None:
    print("Scanning...")
    device = await find_treadmill()
    print(f"{device.name}  {device.address}")


async def with_treadmill(address: str | None, action) -> None:
    async with Treadmill(address) as mill:
        print(f"Connected to {mill.address}")
        await action(mill)


async def cmd_status(mill: Treadmill) -> None:
    status = mill.status or await mill.wait_status()
    print(status.summary())
    unit = "km/h" if status.metric else "mph"
    print(
        f"firmware {status.firmware}  max {status.max_kph:.1f} {unit}  "
        f"max incline {status.max_incline} deg  hr {status.heart_rate}"
    )


async def cmd_watch(mill: Treadmill) -> None:
    print("Live status (Ctrl+C to quit). Belt will not start from this command.")
    mill.on_status(lambda s: print(s.summary(), flush=True))
    if mill.status:
        print(mill.status.summary())
    while True:
        await asyncio.sleep(1)


async def cmd_start(mill: Treadmill, speed: float) -> None:
    print(f"Starting at {speed:.1f} km/h — stand on the belt / keep the safety key in.")
    await mill.start(speed)
    await asyncio.sleep(1.5)
    status = mill.status or await mill.wait_status()
    print(status.summary())


async def cmd_speed(mill: Treadmill, speed: float) -> None:
    print(f"Setting speed to {speed:.1f} km/h")
    await mill.set_speed(speed)
    await asyncio.sleep(1.0)
    status = mill.status or await mill.wait_status()
    print(status.summary())


async def cmd_pause(mill: Treadmill) -> None:
    await mill.pause()
    await asyncio.sleep(1.0)
    status = mill.status or await mill.wait_status()
    print(status.summary())


async def cmd_stop(mill: Treadmill) -> None:
    await mill.stop()
    await asyncio.sleep(1.0)
    status = mill.status or await mill.wait_status()
    print(status.summary())


async def cmd_mute(mill: Treadmill) -> None:
    print("Sending mute packet (does not move the belt).")
    await mill.mute()
    await asyncio.sleep(1.5)
    status = mill.status or await mill.wait_status()
    print(status.summary())
    print("Press + / - on the remote to check whether action beeps are silenced.")


async def cmd_unmute(mill: Treadmill) -> None:
    print("Sending unmute packet (does not move the belt).")
    await mill.unmute()
    await asyncio.sleep(1.5)
    status = mill.status or await mill.wait_status()
    print(status.summary())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control a PitPat-T01 treadmill over Bluetooth")
    parser.add_argument(
        "--address",
        default=DEFAULT_ADDRESS,
        help="BLE address. If omitted, scan for a PitPat / DeerRun / Superun pad",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="Find the treadmill")
    sub.add_parser("status", help="Connect and print one status update")
    sub.add_parser("watch", help="Print live status until Ctrl+C")
    start = sub.add_parser("start", help="Start the belt (moves the treadmill)")
    start.add_argument("--speed", type=float, default=1.0, help="km/h (default 1.0)")
    speed = sub.add_parser("speed", help="Change speed while running")
    speed.add_argument("kph", type=float, help="target km/h")
    sub.add_parser("pause", help="Pause the belt")
    sub.add_parser("stop", help="Stop the belt")
    sub.add_parser("mute", help="Try to silence action beeps")
    sub.add_parser("unmute", help="Turn action beeps back on")
    return parser


async def async_main() -> None:
    args = build_parser().parse_args()
    if args.command == "scan":
        await cmd_scan()
        return

    async def run(mill: Treadmill) -> None:
        if args.command == "status":
            await cmd_status(mill)
        elif args.command == "watch":
            await cmd_watch(mill)
        elif args.command == "start":
            await cmd_start(mill, args.speed)
        elif args.command == "speed":
            await cmd_speed(mill, args.kph)
        elif args.command == "pause":
            await cmd_pause(mill)
        elif args.command == "stop":
            await cmd_stop(mill)
        elif args.command == "mute":
            await cmd_mute(mill)
        elif args.command == "unmute":
            await cmd_unmute(mill)

    await with_treadmill(args.address, run)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
