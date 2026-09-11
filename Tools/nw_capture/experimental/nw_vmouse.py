#!/usr/bin/env python3
"""Hold a mouse button in the focused game window, with the same focus guard as nw_vkeys.

    .venv-capture/bin/python Tools/nw_capture/experimental/nw_vmouse.py --button right --hold 40 --focus --restore

Mouse events go to the focused window, so this refuses to inject unless the expected window
class is focused, re-checks before each step, and releases everything on exit.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nw_vkeys as vk  # noqa: E402  (active_window, focus_window, GAME_CLASS)

from evdev import UInput, ecodes as e  # noqa: E402

BUTTONS = {"right": e.BTN_RIGHT, "left": e.BTN_LEFT, "middle": e.BTN_MIDDLE}


def build_mouse():
    return UInput({e.EV_KEY: sorted(BUTTONS.values()), e.EV_REL: [e.REL_X, e.REL_Y]},
                  name="nw_vmouse virtual mouse")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--button", default="right", choices=sorted(BUTTONS))
    parser.add_argument("--hold", type=float, default=30.0, help="seconds to keep the button down")
    parser.add_argument("--expect-class", default=vk.GAME_CLASS)
    parser.add_argument("--focus", action="store_true", help="focus the expected window first")
    parser.add_argument("--restore", action="store_true", help="refocus what was active before")
    args = parser.parse_args(argv)

    previous, _ = vk.active_window()
    button = BUTTONS[args.button]
    ui = build_mouse()
    held = False
    try:
        if args.focus:
            vk.focus_window(args.expect_class)
        current, _ = vk.active_window()
        print(f"active window: {current!r} (expected {args.expect_class!r})", flush=True)
        if current != args.expect_class:
            print("ABORT: the game does not have focus; no button was sent", file=sys.stderr)
            return 3
        ui.write(e.EV_KEY, button, 1)
        ui.syn()
        held = True
        print(f"holding {args.button} for {args.hold:.0f}s", flush=True)
        deadline = time.monotonic() + args.hold
        while time.monotonic() < deadline:
            time.sleep(0.5)
            now, _ = vk.active_window()
            if now != args.expect_class:
                print(f"focus lost to {now!r}; releasing", file=sys.stderr)
                break
        return 0
    finally:
        if held:
            ui.write(e.EV_KEY, button, 0)
            ui.syn()
        ui.close()
        if args.focus and args.restore and previous:
            vk.focus_window(previous)
        print(f"released; active window: {vk.active_window()}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
