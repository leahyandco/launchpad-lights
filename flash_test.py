# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["mido", "python-rtmidi"]
# ///
"""Quick Launchpad Mini flash test.

Usage: uv run flash_test.py [seconds]   (default 20, Ctrl+C to stop early)
Press any pad/button while it runs and it gets echoed to the console.
"""
import sys
import time

import mido

PALETTE = [(3, 0), (3, 1), (3, 2), (3, 3), (2, 3), (1, 3), (0, 3), (0, 1)]


def vel(r, g):
    return 16 * g + r + 12


def find(names):
    return next((n for n in names if "launchpad" in n.lower()), None)


outs, ins = mido.get_output_names(), mido.get_input_names()
print("MIDI outputs:", outs)
print("MIDI inputs: ", ins)
out_name, in_name = find(outs), find(ins)
if not out_name:
    sys.exit("No Launchpad output port found. Check USB / Novation driver.")
try:
    out = mido.open_output(out_name)
    inp = mido.open_input(in_name) if in_name else None
except Exception as e:
    sys.exit(f"Couldn't open {out_name!r}: {e}\nLikely held by Ableton, Novation Components or another MIDI app.")
print(f"Opened {out_name!r}")


def pad(x, y, r, g):
    out.send(mido.Message("note_on", note=16 * y + x, velocity=vel(r, g)))


def side(y, r, g):
    out.send(mido.Message("note_on", note=16 * y + 8, velocity=vel(r, g)))


def top(i, r, g):
    out.send(mido.Message("control_change", control=104 + i, value=vel(r, g)))


def reset():
    out.send(mido.Message("control_change", control=0, value=0))


def echo():
    for m in inp.iter_pending() if inp else ():
        if m.type == "note_on":
            kind = f"side {m.note // 16}" if m.note % 16 == 8 else f"pad x={m.note % 16} y={m.note // 16}"
        elif m.type == "control_change":
            kind = f"top {m.control - 104}"
        else:
            continue
        val = m.velocity if m.type == "note_on" else m.value
        print(f"{kind} {'pressed' if val else 'released'}")


duration = float(sys.argv[1]) if len(sys.argv) > 1 else 20
try:
    reset()
    print("All LEDs full...")
    out.send(mido.Message("control_change", control=0, value=0x7F))
    time.sleep(1.0)
    reset()

    print("Colour flood: red, amber, green, yellow...")
    for r, g in [(3, 0), (3, 3), (0, 3), (2, 3)]:
        for y in range(8):
            for x in range(8):
                pad(x, y, r, g)
            side(y, r, g)
            top(y, r, g)
        time.sleep(0.4)

    print("Rainbow wave (press buttons to see them echoed)...")
    end = time.time() + duration
    t = 0
    while time.time() < end:
        for y in range(8):
            for x in range(8):
                pad(x, y, *PALETTE[(x + y + t) % len(PALETTE)])
            side(y, *(PALETTE[(y + t) % len(PALETTE)]))
            top(y, *(PALETTE[(y - t) % len(PALETTE)]))
        echo()
        t += 1
        time.sleep(0.08)
except KeyboardInterrupt:
    pass
finally:
    reset()
    out.close()
    if inp:
        inp.close()
    print("Cleared, done.")
