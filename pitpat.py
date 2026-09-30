"""PitPat-T01 BLE protocol (service 0xFBA0).

Packet layout is the community-documented PitPat / Superun / DeerRun format:
23-byte commands on FBA1, 31+ byte status notifications on FBA2.
"""

from __future__ import annotations

import asyncio
import struct
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

SERVICE_UUID = "0000fba0-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fba1-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000fba2-0000-1000-8000-00805f9b34fb"

START_BYTE = 0x6A
CMD_LENGTH = 0x17
END_BYTE = 0x43
HEARTBEAT = bytes([0x6A, 0x05, 0xFD, 0xF8, 0x43])
# Captured from the PitPat app on a BA09-B (same FBA0 service as T01).
SOUND_OFF = bytes.fromhex("6a17f1000000000000000000100000000000000001f743")
SOUND_ON = bytes.fromhex("6a17f1000000000000000000000000000000000001e743")
# Protocol constant from the public PitPat / pacekeeper packet format, not an account id.
DEFAULT_USER_ID = 58965456623
DEFAULT_WEIGHT_KG = 80
DEFAULT_ADDRESS: str | None = None

NAME_HINTS = ("pitpat", "t01", "deerrun", "superun")


class Command(IntEnum):
    STOP = 0
    PAUSE = 2
    START_OR_SET = 4


class BeltState(IntEnum):
    STOPPED = 0
    RUNNING = 1
    PAUSED = 2
    STARTING = 3
    UNKNOWN = 99


@dataclass
class Status:
    state: BeltState
    current_kph: float
    target_kph: float
    max_kph: float
    distance_km: float
    incline: int
    target_incline: int
    max_incline: int
    heart_rate: int
    steps: int
    calories: int
    duration_s: float
    firmware: int
    wifi_connected: bool
    metric: bool
    buzzer_on: bool | None
    raw: bytes

    def summary(self) -> str:
        unit = "km/h" if self.metric else "mph"
        dist = "km" if self.metric else "mi"
        if self.buzzer_on is None:
            sound = "unknown"
        else:
            sound = "on" if self.buzzer_on else "muted"
        return (
            f"{self.state.name:<9}  "
            f"{self.current_kph:4.1f}/{self.target_kph:4.1f} {unit}  "
            f"{self.distance_km:5.2f} {dist}  "
            f"{self.steps} steps  "
            f"{self.calories} kcal  "
            f"{self.duration_s:5.0f}s  "
            f"incline {self.incline} deg  "
            f"wifi={'yes' if self.wifi_connected else 'no'}  "
            f"sound={sound}"
        )


def make_packet(
    command: Command,
    speed_kph: float = 0.0,
    incline: int = 0,
    ramp: int | None = None,
    metric: bool = True,
) -> bytes:
    """Build a 23-byte PitPat control packet.

    Speed is encoded as thousandths (1.0 km/h -> 1000).
    `ramp` is 1 for start/stop/pause and 5 when changing speed while running.
    """
    speed_raw = int(round(speed_kph * 1000))
    if speed_raw < 0 or speed_raw > 65535:
        raise ValueError("speed out of range")
    if incline < 0 or incline > 255:
        raise ValueError("incline out of range")
    if ramp is None:
        ramp = 5 if speed_raw else 1

    packet = bytearray(23)
    packet[0] = START_BYTE
    packet[1] = CMD_LENGTH
    packet[6] = (speed_raw >> 8) & 0xFF
    packet[7] = speed_raw & 0xFF
    packet[8] = ramp
    packet[9] = incline
    packet[10] = DEFAULT_WEIGHT_KG
    cmd = int(command)
    packet[12] = cmd & 0xF7 if metric else cmd | 0x08
    uid = DEFAULT_USER_ID
    for i in range(8):
        packet[13 + i] = (uid >> (56 - i * 8)) & 0xFF
    checksum = 0
    for b in packet[1:21]:
        checksum ^= b
    packet[21] = checksum
    packet[22] = END_BYTE
    return bytes(packet)


def parse_status(data: bytes | bytearray) -> Status | None:
    if len(data) < 31:
        return None
    current = struct.unpack_from(">H", data, 3)[0] / 1000.0
    target = struct.unpack_from(">H", data, 5)[0] / 1000.0
    distance = struct.unpack_from(">I", data, 7)[0] / 1000.0
    incline = data[11]
    target_incline = data[12] & 0x3F
    heart_rate = data[13]
    steps = struct.unpack_from(">I", data, 14)[0]
    calories = struct.unpack_from(">H", data, 18)[0]
    duration_ms = struct.unpack_from(">I", data, 20)[0]
    firmware = data[25]
    flags = data[26]
    max_speed = struct.unpack_from(">H", data, 27)[0] / 1000.0
    max_incline = data[29]
    bits = flags & 0x18
    if bits == 0x18:
        state = BeltState.STARTING
    elif bits == 0x08:
        state = BeltState.RUNNING
    elif bits == 0x10:
        state = BeltState.PAUSED
    elif bits == 0x00:
        state = BeltState.STOPPED
    else:
        state = BeltState.UNKNOWN
    duration_s = duration_ms / 1000.0 if firmware > 19 else float(duration_ms)
    buzzer_on = None
    if len(data) > 47:
        buzzer_on = bool(data[47] & 0x01)
    return Status(
        state=state,
        current_kph=current,
        target_kph=target,
        max_kph=max_speed,
        distance_km=distance,
        incline=incline,
        target_incline=target_incline,
        max_incline=max_incline,
        heart_rate=heart_rate,
        steps=steps,
        calories=calories,
        duration_s=duration_s,
        firmware=firmware,
        wifi_connected=bool(flags & 0x01),
        metric=not bool(flags & 0x80),
        buzzer_on=buzzer_on,
        raw=bytes(data),
    )


async def find_treadmill(timeout: float = 12.0) -> BLEDevice:
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for device, adv in devices.values():
        name = (device.name or adv.local_name or "").lower()
        uuids = {u.lower() for u in (adv.service_uuids or [])}
        if any(h in name for h in NAME_HINTS) or SERVICE_UUID in uuids:
            return device
    raise RuntimeError("No PitPat treadmill found. Power it on and retry.")


class Treadmill:
    """Async BLE client for a PitPat-T01 (and Superun/DeerRun clones)."""

    def __init__(self, address: str | None = None) -> None:
        self.address = address or DEFAULT_ADDRESS
        self._client: BleakClient | None = None
        self._status: Status | None = None
        self._status_event = asyncio.Event()
        self._listeners: list[Callable[[Status], None]] = []
        self._heartbeat = False

    @property
    def status(self) -> Status | None:
        return self._status

    def on_status(self, callback: Callable[[Status], None]) -> None:
        self._listeners.append(callback)

    async def connect(self, timeout: float = 20.0) -> None:
        if self._client and self._client.is_connected:
            return
        address = self.address
        if not address:
            device = await find_treadmill()
            address = device.address
            self.address = address
        self._client = BleakClient(address, timeout=timeout)
        await self._client.connect()
        await self._client.start_notify(NOTIFY_UUID, self._on_notify)

    async def disconnect(self) -> None:
        if self._client is None:
            return
        try:
            if self._client.is_connected:
                await self._client.stop_notify(NOTIFY_UUID)
                await self._client.disconnect()
        except BleakError:
            pass
        self._client = None

    async def __aenter__(self) -> Treadmill:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.disconnect()

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        parsed = parse_status(data)
        if parsed is None:
            return
        self._status = parsed
        self._status_event.set()
        for listener in self._listeners:
            listener(parsed)
        if self._heartbeat:
            client = self._client
            if client and client.is_connected:
                asyncio.create_task(self._write(HEARTBEAT))

    async def _write(self, payload: bytes) -> None:
        if self._client is None or not self._client.is_connected:
            raise RuntimeError("not connected")
        await self._client.write_gatt_char(WRITE_UUID, payload, response=True)

    async def wait_status(self, timeout: float = 8.0) -> Status:
        self._status_event.clear()
        try:
            await asyncio.wait_for(self._status_event.wait(), timeout=timeout)
        except TimeoutError as exc:
            raise TimeoutError("no status notification from treadmill") from exc
        assert self._status is not None
        return self._status

    async def start(self, speed_kph: float = 1.0, incline: int = 0) -> None:
        await self._write(make_packet(Command.START_OR_SET, speed_kph, incline, ramp=1))

    async def set_speed(self, speed_kph: float, incline: int = 0) -> None:
        await self._write(make_packet(Command.START_OR_SET, speed_kph, incline, ramp=5))

    async def pause(self) -> None:
        await self._write(make_packet(Command.PAUSE, ramp=1))

    async def stop(self) -> None:
        await self._write(make_packet(Command.STOP, ramp=1))

    async def mute(self) -> None:
        await self._write(SOUND_OFF)

    async def unmute(self) -> None:
        await self._write(SOUND_ON)
