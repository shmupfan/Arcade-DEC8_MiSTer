#!/usr/bin/env python3
"""Print an INPUTS string for d8_oracle.lua that plays a real game: coin,
start, then fire held while the player sweeps the four directions, with the
second button every ~12 s and a fresh coin + start every ~30 s in case the
game ended. Deterministic, so captures are reproducible.

Usage: tools/play_inputs.py <lastmisn|gondo|srdarwin> <start_frame> <end_frame>
Field names are MAME 0.288's (sim/mame/d8_oracle.lua resolves them).
"""
import sys

FIELDS = {
    "lastmisn": dict(coin="COIN:Coin 1", start="IN2:1 Player Start", fire="IN0:P1 Button 1",
                     second="IN0:P1 Button 2", dirs="IN0"),
    "gondo": dict(coin="COIN:Coin 1", start="IN3:1 Player Start", fire="IN2:P1 Button 1",
                  second="IN2:P1 Button 2", dirs="IN0"),
    "srdarwin": dict(coin="COIN:Coin 1", start="IN0:1 Player Start", fire="IN0:P1 Button 1",
                     second="IN0:P1 Button 2", dirs="IN0"),
}


def main(argv):
    game, start, end = argv[0], int(argv[1]), int(argv[2])
    f = FIELDS[game]
    ev = []

    def press(fr, field, dur=6):
        ev.append(f"{fr}:{field}:1")
        ev.append(f"{fr + dur}:{field}:0")

    # IP_ACTIVE_LOW fields: set_value(1) = pressed, 0 = released (MAME
    # ioport_field::set_value handles the polarity)
    press(start, f["coin"])
    press(start + 60, f["coin"])
    press(start + 120, f["start"])
    f0 = start + 300
    ev.append(f"{f0}:{f['fire']}:1")
    dirs = ["P1 Left", "P1 Up", "P1 Right", "P1 Down"]
    fr, i = f0 + 30, 0
    while fr < end - 60:
        d = dirs[i % len(dirs)]
        ev.append(f"{fr}:{f['dirs']}:{d}:1")
        ev.append(f"{fr + 45}:{f['dirs']}:{d}:0")
        if i % 12 == 11:
            press(fr + 50, f["second"])
        if i % 30 == 29:
            press(fr + 52, f["coin"])
            press(fr + 70, f["start"])
        fr += 60
        i += 1
    print(";".join(ev))


if __name__ == "__main__":
    main(sys.argv[1:])
