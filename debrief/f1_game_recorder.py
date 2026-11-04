#!/usr/bin/env python3
"""F1 Data Room lap recorder for the EA SPORTS F1 games (F1 23, F1 24, F1 25).

Saves every lap you drive as a CSV that the F1 Data Room debrief reads.
Needs only Python 3 (no extra packages).

1. In the game: Settings > Telemetry Settings > UDP Telemetry: On,
   UDP Broadcast Mode: Off, UDP IP Address: 127.0.0.1 (or this PC's IP if the
   game runs on a console), UDP Port: 20777, UDP Send Rate: 60 Hz, UDP Format: 2025
   (or your game's year).
2. Run:  python f1_game_recorder.py            (laps go to ./laps/)
3. Drive. Each completed lap is saved as laps/lap_<n>_<m>m<ss.mmm>s.csv.
4. Send us your best lap. Stop the recorder with Ctrl+C.

Columns: Time (s into the lap), Distance (m), Speed (km/h), Throttle (0-1),
Brake (0-1), Gear. Only your own car is recorded; nothing is sent anywhere.
"""
from __future__ import annotations

import socket
import struct
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 20777
OUT = Path("laps")
HEADER = struct.Struct("<HBBBBBQfIIBB")      # F1 23/24/25 packet header, 29 bytes
LAP_DATA, CAR_TELEMETRY = 2, 6
N_CARS = 22


def per_car(packet: bytes, trailer: int) -> int:
    return (len(packet) - HEADER.size - trailer) // N_CARS


def main() -> None:
    OUT.mkdir(exist_ok=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))
    print(f"Listening on UDP {PORT}. Drive a lap; laps are saved to {OUT.resolve()}. Ctrl+C to stop.")
    lap_num, lap_ms, lap_dist = None, 0, 0.0
    rows: list[tuple] = []
    telem = None
    while True:
        packet, _ = sock.recvfrom(4096)
        if len(packet) < HEADER.size:
            continue
        fmt, _yr, _maj, _min, _ver, pid, _uid, _t, _frame, _oframe, player, _sec = HEADER.unpack_from(packet)
        if fmt < 2023:
            continue
        if pid == CAR_TELEMETRY:
            size = per_car(packet, 3)
            o = HEADER.size + player * size
            speed, throttle, _steer, brake, _clutch, gear = struct.unpack_from("<HfffBb", packet, o)
            telem = (speed, throttle, brake, gear)
        elif pid == LAP_DATA and telem is not None:
            size = per_car(packet, 2)
            o = HEADER.size + player * size
            _last_ms, cur_ms = struct.unpack_from("<II", packet, o)
            d_off, n_off = (18, 31) if fmt == 2023 else (20, 33)   # F1 24 added minute fields
            dist = struct.unpack_from("<f", packet, o + d_off)[0]
            num = packet[o + n_off]
            if lap_num is not None and num != lap_num:
                if rows and num == lap_num + 1:
                    save(lap_num, rows, lap_ms)
                rows = []
            lap_num = num
            if dist >= 0 and (not rows or dist > rows[-1][1]):
                speed, throttle, brake, gear = telem
                rows.append((cur_ms / 1000, dist, speed, throttle, brake, gear))
                lap_ms, lap_dist = cur_ms, dist


def save(n: int, rows: list[tuple], last_ms: int) -> None:
    if len(rows) < 200 or rows[0][1] > 50:   # too short, or recording began mid-lap
        return
    m, s = divmod(rows[-1][0], 60)
    path = OUT / f"lap_{n}_{int(m)}m{s:06.3f}s.csv"
    with open(path, "w") as f:
        f.write("Time,Distance,Speed,Throttle,Brake,Gear\n")
        for r in rows:
            f.write(f"{r[0]:.3f},{r[1]:.2f},{r[2]},{r[3]:.3f},{r[4]:.3f},{r[5]}\n")
    print(f"saved {path} ({len(rows)} samples)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped")
