#!/usr/bin/env python3
"""Control a Lumenate Nova light mask over BLE from a Mac (or any bleak host).

Protocol reverse-engineered in docs/PROTOCOL.md. The Nova's flicker waveform is
driven by the *host*: we stream compact "strobe frames" (period/on-time in µs) to
the strobe characteristic with write-without-response; the device flashes at the
last frame's parameters until a new frame arrives.

Requires: pip install bleak
"""
from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner

# --- GATT UUIDs (see docs/PROTOCOL.md) ---
ADV_NAME = "Lumenate Nova"

SVC_STROBE = "b568de7c-b6c6-42cb-8303-fcc9cb25007c"
CHR_STROBE = "f2c51a4e-2a46-4bef-b18f-cb00c716cfa6"  # write-without-response
CHR_SENSOR = "12345678-9abc-4def-8012-3456789abcde"  # notify: 3x int16 LE

SVC_COMMAND = "47bbfb1e-670e-4f81-bfb3-78daffc9a783"
CHR_COMMAND = "3e25a3bf-bfe1-4c71-97c5-5bdb73fac89e"  # write: [cmdId, arg]
CHR_REMOTE = "964fbffe-6940-4371-8d48-fe43b07ed00b"   # notify: [0x01, event]

SVC_OFFLINE = "3e8ec328-a4b8-4273-a380-47d219f64e9b"
CHR_OFFLINE_MODE = "2a84aaff-6738-4629-894c-346357b89a0c"    # write: [mode]
CHR_OFFLINE_HEADER = "51bfc219-feab-4227-8b93-8af8cc5306d4"  # read/notify: 16 bytes

CHR_BATTERY = "00002a19-0000-1000-8000-00805f9b34fb"
CHR_MODEL = "00002a24-0000-1000-8000-00805f9b34fb"
CHR_SERIAL = "00002a25-0000-1000-8000-00805f9b34fb"
CHR_FIRMWARE = "00002a26-0000-1000-8000-00805f9b34fb"
CHR_HARDWARE = "00002a27-0000-1000-8000-00805f9b34fb"

# Command ids (enum defpackage.c)
CMD_WELCOME_LEDS = 0x01

# Offline session modes (enum defpackage.h)
OFFLINE_RELAXED, OFFLINE_EXPLORE, OFFLINE_SLEEP, OFFLINE_NOT_SET = 0, 1, 2, 255

# Remote button events (enum EnumC4278k2)
REMOTE_EVENTS = {0: "POWER", 1: "BRIGHTNESS_UP", 2: "BRIGHTNESS_DOWN"}

U32_MAX = 0xFFFFFFFF


def _u32(x: float) -> int:
    return max(0, min(U32_MAX, int(round(x))))


def strobe_frame(frequency_hz: float, duty: float, color: float = 0.0) -> bytes:
    """Build a 12-byte symmetric strobe frame [period_us, on_us, color] (LE uint32).

    frequency_hz: flashes per second (observed 7-14 Hz in real sessions)
    duty:         fraction of each period the LEDs are lit, 0..1 (observed 0.01-0.70)
    color:        reserved; observed 0 in all captured sessions
    """
    if frequency_hz <= 0 or duty <= 0:
        return struct.pack("<III", 0, 0, 0)
    period_us = 1_000_000.0 / frequency_hz
    on_us = period_us * max(0.0, min(1.0, duty))
    return struct.pack("<III", _u32(period_us), _u32(on_us), _u32(color * 1_000_000.0))


def strobe_frame_lr(
    freq_l: float, duty_l: float, freq_r: float, duty_r: float, color: float = 0.0
) -> bytes:
    """Build a 40-byte asymmetric (per-eye) strobe frame. Second-pulse fields are 0."""
    def half(f, d):
        if f <= 0 or d <= 0:
            return (0, 0, 0, 0, 0)
        p = 1_000_000.0 / f
        on = p * max(0.0, min(1.0, d))
        return (_u32(p), _u32(on), 0, 0, _u32(color * 1_000_000.0))
    l, r = half(freq_l, duty_l), half(freq_r, duty_r)
    return struct.pack("<IIIII IIIII", *l, *r)


def decode_strobe_frame(data: bytes) -> str:
    ints = struct.unpack("<" + "I" * (len(data) // 4), data)
    if not ints or ints[0] == 0:
        return "OFF"
    period, on = ints[0], ints[1]
    return f"{1e6/period:.2f} Hz, duty {on/period*100:.1f}% (period {period}us on {on}us)"


@dataclass
class NovaInfo:
    model: str = ""
    serial: str = ""
    firmware: str = ""
    hardware: str = ""
    battery: int | None = None


class Nova:
    """A connected Lumenate Nova."""

    def __init__(self, client: BleakClient):
        self.client = client

    # ---- discovery / connection ----
    @staticmethod
    async def discover(timeout: float = 10.0):
        """Return a list of (BLEDevice, adv) for advertising Novas."""
        found = {}

        def cb(dev, adv):
            name = adv.local_name or dev.name or ""
            if ADV_NAME.lower() in name.lower() or SVC_STROBE in [
                u.lower() for u in adv.service_uuids
            ]:
                found[dev.address] = (dev, adv)

        scanner = BleakScanner(detection_callback=cb)
        await scanner.start()
        await asyncio.sleep(timeout)
        await scanner.stop()
        return list(found.values())

    @classmethod
    async def connect(cls, address: str | None = None, timeout: float = 15.0) -> "Nova":
        """Connect to a Nova by address, or the first one discovered."""
        if address is None:
            devs = await cls.discover(timeout=min(timeout, 10.0))
            if not devs:
                raise RuntimeError(
                    "No 'Lumenate Nova' advertising. Power it on and make sure it is "
                    "NOT connected to the phone app (LED should be flashing white)."
                )
            address = devs[0][0].address
        client = BleakClient(address, timeout=timeout)
        await client.connect()
        return cls(client)

    async def disconnect(self):
        await self.client.disconnect()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        try:
            await self.stop()
        finally:
            await self.disconnect()

    # ---- info ----
    async def read_info(self) -> NovaInfo:
        info = NovaInfo()
        async def rd(uuid):
            try:
                return (await self.client.read_gatt_char(uuid))
            except Exception:
                return b""
        info.model = (await rd(CHR_MODEL)).decode(errors="replace")
        info.serial = (await rd(CHR_SERIAL)).decode(errors="replace")
        info.firmware = (await rd(CHR_FIRMWARE)).decode(errors="replace")
        info.hardware = (await rd(CHR_HARDWARE)).decode(errors="replace")
        bat = await rd(CHR_BATTERY)
        info.battery = bat[0] if bat else None
        return info

    # ---- strobe ----
    async def set_strobe(self, frequency_hz: float, duty: float = 0.5, color: float = 0.0):
        """Set a steady flicker. The device holds it until changed."""
        await self.client.write_gatt_char(
            CHR_STROBE, strobe_frame(frequency_hz, duty, color), response=False
        )

    async def set_strobe_lr(self, freq_l, duty_l, freq_r, duty_r, color=0.0):
        await self.client.write_gatt_char(
            CHR_STROBE, strobe_frame_lr(freq_l, duty_l, freq_r, duty_r, color), response=False
        )

    async def write_frame(self, frame: bytes):
        await self.client.write_gatt_char(CHR_STROBE, frame, response=False)

    async def stop(self):
        """Blank the LEDs (write an all-zero frame)."""
        try:
            await self.client.write_gatt_char(CHR_STROBE, strobe_frame(0, 0), response=False)
        except Exception:
            pass

    async def stream(self, frames, rate_hz: float = 10.0):
        """Stream an iterable of (frequency_hz, duty[, color]) tuples at rate_hz."""
        dt = 1.0 / rate_hz
        for f in frames:
            freq, duty = f[0], f[1]
            color = f[2] if len(f) > 2 else 0.0
            await self.set_strobe(freq, duty, color)
            await asyncio.sleep(dt)

    # ---- commands ----
    async def welcome_leds(self, arg: int = 0):
        """Trigger the greeting/identify LED animation."""
        await self.client.write_gatt_char(
            CHR_COMMAND, bytes([CMD_WELCOME_LEDS, arg & 0xFF]), response=True
        )

    async def start_offline_session(self, mode: int = OFFLINE_RELAXED):
        """Start a stored on-device session (RELAXED/EXPLORE/SLEEP)."""
        await self.client.write_gatt_char(CHR_OFFLINE_MODE, bytes([mode & 0xFF]), response=True)

    async def read_offline_header(self):
        data = await self.client.read_gatt_char(CHR_OFFLINE_HEADER)
        magic, version, count, active = struct.unpack("<IIII", data[:16])
        return {"magic": magic, "version": version, "sessionCount": count,
                "activeSessionIndex": active}

    # ---- notifications ----
    async def subscribe_remote(self, callback):
        """callback(event_name: str) on each button press."""
        def cb(_, data: bytearray):
            if len(data) >= 2 and data[0] == 0x01:
                callback(REMOTE_EVENTS.get(data[1], f"UNKNOWN({data[1]})"))
        await self.client.start_notify(CHR_REMOTE, cb)

    async def subscribe_sensor(self, callback):
        """callback((x, y, z)) — 3x signed int16 LE."""
        def cb(_, data: bytearray):
            if len(data) >= 6:
                callback(struct.unpack("<hhh", bytes(data[:6])))
        await self.client.start_notify(CHR_SENSOR, cb)

    async def subscribe_battery(self, callback):
        def cb(_, data: bytearray):
            if data:
                callback(data[0])
        await self.client.start_notify(CHR_BATTERY, cb)
