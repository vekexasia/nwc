#!/usr/bin/env python3
"""nw_vpad - drive an already-running game with a virtual gamepad, without stealing focus.

Why a gamepad: injected keyboard and mouse events are delivered to the focused window, so a
keyboard script would type into whatever the operator is using. A virtual gamepad created with
uinput is read by the game through evdev/HID, which does not depend on window focus. That makes
this the only input route that can drive the game while the operator keeps working.

The device presents itself as a Microsoft Xbox 360 pad (vendor 0x045e, product 0x028e) so SDL and
Steam Input have a built-in mapping for it. Nothing here touches the keyboard or the mouse.

Examples:
    # check that the device can be created, then release it (no game input)
    .venv-capture/bin/python Tools/nw_capture/experimental/nw_vpad.py --dry-run

    # walk forward 3 s, stop 2 s, then walk forward again 3 s, with screenshots around it
    .venv-capture/bin/python Tools/nw_capture/experimental/nw_vpad.py \\
        --seq "forward:3,stop:2,forward:3" --shot-prefix /tmp/nw_vpad

    # a single action
    .venv-capture/bin/python Tools/nw_capture/experimental/nw_vpad.py --seq "jump:0.2"

Actions: forward back left right strafe_left strafe_right turn_left turn_right look_up look_down
         sprint jump interact map mount stop
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    from evdev import AbsInfo, UInput, ecodes as e
except ImportError:
    print("ERROR: python-evdev is not installed in this interpreter "
          "(use .venv-capture/bin/python)", file=sys.stderr)
    raise SystemExit(2)

VENDOR, PRODUCT, VERSION = 0x045E, 0x028E, 0x0114     # Microsoft Xbox 360 pad
STICK = 32767
TRIGGER = 255


def build_device(name="Microsoft X-Box 360 pad"):
    caps = {
        e.EV_KEY: [e.BTN_SOUTH, e.BTN_EAST, e.BTN_WEST, e.BTN_NORTH,
                   e.BTN_TL, e.BTN_TR, e.BTN_SELECT, e.BTN_START,
                   e.BTN_THUMBL, e.BTN_THUMBR,
                   e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT],
        e.EV_ABS: [
            (e.ABS_X, AbsInfo(0, -STICK, STICK, 16, 128, 0)),
            (e.ABS_Y, AbsInfo(0, -STICK, STICK, 16, 128, 0)),
            (e.ABS_RX, AbsInfo(0, -STICK, STICK, 16, 128, 0)),
            (e.ABS_RY, AbsInfo(0, -STICK, STICK, 16, 128, 0)),
            (e.ABS_Z, AbsInfo(0, 0, TRIGGER, 0, 0, 0)),
            (e.ABS_RZ, AbsInfo(0, 0, TRIGGER, 0, 0, 0)),
            (e.ABS_HAT0X, AbsInfo(0, -1, 1, 0, 0, 0)),
            (e.ABS_HAT0Y, AbsInfo(0, -1, 1, 0, 0, 0)),
        ],
    }
    return UInput(caps, name=name, vendor=VENDOR, product=PRODUCT,
                  version=VERSION, bustype=e.BUS_USB)


def neutral(ui):
    ui.write(e.EV_ABS, e.ABS_X, 0)
    ui.write(e.EV_ABS, e.ABS_Y, 0)
    ui.write(e.EV_ABS, e.ABS_RX, 0)
    ui.write(e.EV_ABS, e.ABS_RY, 0)
    ui.write(e.EV_ABS, e.ABS_Z, 0)
    ui.write(e.EV_ABS, e.ABS_RZ, 0)
    ui.write(e.EV_ABS, e.ABS_HAT0X, 0)
    ui.write(e.EV_ABS, e.ABS_HAT0Y, 0)
    for key in (e.BTN_SOUTH, e.BTN_EAST, e.BTN_WEST, e.BTN_NORTH, e.BTN_TL, e.BTN_TR,
                e.BTN_SELECT, e.BTN_START, e.BTN_THUMBL, e.BTN_THUMBR,
                e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT):
        ui.write(e.EV_KEY, key, 0)
    ui.syn()


ACTIONS = {
    # action -> list of (kind, code, value)
    "forward":      [(e.EV_ABS, e.ABS_Y, -STICK)],
    "back":         [(e.EV_ABS, e.ABS_Y, STICK)],
    "left":         [(e.EV_ABS, e.ABS_X, -STICK)],
    "right":        [(e.EV_ABS, e.ABS_X, STICK)],
    "strafe_left":  [(e.EV_ABS, e.ABS_X, -STICK)],
    "strafe_right": [(e.EV_ABS, e.ABS_X, STICK)],
    "turn_left":    [(e.EV_ABS, e.ABS_RX, -STICK)],
    "turn_right":   [(e.EV_ABS, e.ABS_RX, STICK)],
    "look_up":      [(e.EV_ABS, e.ABS_RY, -STICK)],
    "look_down":    [(e.EV_ABS, e.ABS_RY, STICK)],
    "dpad_up":      [(e.EV_ABS, e.ABS_HAT0Y, -1)],
    "dpad_down":    [(e.EV_ABS, e.ABS_HAT0Y, 1)],
    "dpad_left":    [(e.EV_ABS, e.ABS_HAT0X, -1)],
    "dpad_right":   [(e.EV_ABS, e.ABS_HAT0X, 1)],
    "sprint":       [(e.EV_KEY, e.BTN_THUMBL, 1)],
    "jump":         [(e.EV_KEY, e.BTN_SOUTH, 1)],
    "interact":     [(e.EV_KEY, e.BTN_WEST, 1)],
    "map":          [(e.EV_KEY, e.BTN_SELECT, 1)],
    "mount":        [(e.EV_KEY, e.BTN_EAST, 1)],
}


def apply_action(ui, action):
    if action == "stop":
        neutral(ui)
        return "released everything"
    if action not in ACTIONS:
        return f"unknown action {action!r} (ignored)"
    neutral(ui)
    for kind, code, value in ACTIONS[action]:
        ui.write(kind, code, value)
    ui.syn()
    return f"{action} = {ACTIONS[action]}"


def shot(prefix, tag):
    if not prefix:
        return None
    if shutil.which("grim") is None:
        return "grim not available"
    path = Path(f"{prefix}-{tag}.png")
    try:
        subprocess.run(["grim", str(path)], check=True, capture_output=True, timeout=20)
    except Exception as error:                       # noqa: BLE001 - report, never fail the run
        return f"grim failed: {error}"
    return str(path)


def parse_seq(spec):
    steps = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        action, _, seconds = part.partition(":")
        steps.append((action.strip(), float(seconds) if seconds else 1.0))
    return steps


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seq", help="comma separated action:seconds steps, e.g. 'forward:3,stop:2'")
    parser.add_argument("--shot-prefix", help="save grim screenshots before/after (prefix path)")
    parser.add_argument("--settle", type=float, default=2.0,
                        help="seconds to wait after creating the device before acting (default 2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="create the device, print it, release it, send no game input")
    parser.add_argument("--name", default="Microsoft X-Box 360 pad")
    args = parser.parse_args(argv)

    if not args.dry_run and not args.seq:
        parser.error("nothing to do: pass --seq or --dry-run")

    ui = build_device(args.name)
    try:
        print(f"device: name={ui.name!r} fw={ui.vendor:04x}:{ui.product:04x}")
        js = sorted(Path("/dev/input").glob("js*"))
        print(f"joystick nodes: {[str(p) for p in js] or 'none'}")
        neutral(ui)
        if args.dry_run:
            print("dry run: device created, neutral state sent, no game input")
            return 0
        print(f"settling {args.settle}s so the game can enumerate the pad")
        time.sleep(args.settle)
        before = shot(args.shot_prefix, "before")
        if before:
            print(f"screenshot before: {before}")
        for action, seconds in parse_seq(args.seq):
            print(f"  {apply_action(ui, action)} -> hold {seconds}s")
            time.sleep(seconds)
        neutral(ui)
        after = shot(args.shot_prefix, "after")
        if after:
            print(f"screenshot after: {after}")
        print("released, done")
        return 0
    finally:
        try:
            neutral(ui)
        finally:
            ui.close()
            print("device removed")


if __name__ == "__main__":
    raise SystemExit(main())
