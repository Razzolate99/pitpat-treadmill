# Treadmill

Python control for the **PitPat-T01** walking treadmill over Bluetooth Low Energy. The official PitPat app is not required.

I made this to mute my treadmill, which has no mute switch. Every button press beeps, and there is no hardware control for that sound. `python cli.py mute` sends the same settings packet the PitPat app uses.

These pads advertise as `PitPat-T01` (and similar DeerRun / Superun names) with service `0xFBA0`. Wi‑Fi and NFC are used by the PitPat app for cloud pairing; belt control is BLE.

## Setup

```powershell
python -m pip install -r requirements.txt
```

Keep the treadmill powered on and in range. Close the PitPat phone app first — BLE is typically one client at a time.

## Commands

Control commands scan for a pad unless you pass `--address AA:BB:CC:DD:EE:FF`. Speed arguments are km/h. `start` and `speed` move the belt — keep the safety key in and stand ready.

| Command | What it does | Example |
| --- | --- | --- |
| `python cli.py status` | Connect and print one snapshot (state, speed, distance, time, incline) | `python cli.py status` |
| `python cli.py watch` | Live status until Ctrl+C. Does not move the belt | `python cli.py watch` |
| `python cli.py start --speed N` | Start the belt. `--speed` is km/h (default `1.0`) | `python cli.py start --speed 1` |
| `python cli.py speed N` | Change speed while already running (km/h) | `python cli.py speed 2.5` |
| `python cli.py pause` | Pause the belt | `python cli.py pause` |
| `python cli.py stop` | Stop the belt | `python cli.py stop` |
| `python cli.py mute` | Try to silence action beeps (does not move the belt) | `python cli.py mute` |
| `python cli.py unmute` | Turn action beeps back on | `python cli.py unmute` |
| `python cli.py scan` | BLE search for a PitPat / DeerRun / Superun pad | `python cli.py scan` |
| `python scan.py` | List nearby BLE devices and flag likely fitness gear. `--seconds` changes scan length (default 20) | `python scan.py --seconds 20` |
| `python gatt_inspect.py` | Dump GATT services and characteristics on the pad | `python gatt_inspect.py` |

## From your own code

```python
import asyncio
from pitpat import Treadmill

async def main():
    async with Treadmill() as mill:
        status = await mill.wait_status()
        print(status.summary())
        await mill.start(1.0)
        await mill.set_speed(2.0)
        await mill.stop()

asyncio.run(main())
```

`start` and `set_speed` move the belt. Keep the safety key in and stand ready.

## Protocol

| Role | UUID |
| --- | --- |
| Service | `0000fba0-0000-1000-8000-00805f9b34fb` |
| Write commands | `0000fba1-...` (23-byte packets) |
| Status notify | `0000fba2-...` (31+ byte packets) |

Commands: `0x00` stop, `0x02` pause, `0x04` start / set speed. Speed is thousandths of km/h (`1000` = 1.0). Mute/unmute uses a settings packet with byte `0xF1` captured from the PitPat app on a BA09-B.

Same family as Superun / DeerRun PitPat pads. Community references: [pacekeeper](https://github.com/peteh/pacekeeper), [hass-pitpat](https://github.com/dernassesmart/hass-pitpat), [pitpat-treadmill-control](https://github.com/azmke/pitpat-treadmill-control).
