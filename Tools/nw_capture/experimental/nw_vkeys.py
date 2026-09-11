#!/usr/bin/env python3
"""nw_vkeys - hold keyboard keys in the focused game window, with a focus guard.

Keyboard events go to the focused window, so this tool refuses to inject unless the focused window
is the expected game window, re-checks before every step, and releases everything on exit. It never
touches other keys than the ones the sequence names.

    .venv-capture/bin/python Tools/nw_capture/experimental/nw_vkeys.py --seq "w:6,release:2,w:6"
    .venv-capture/bin/python Tools/nw_capture/experimental/nw_vkeys.py --seq "w:6" --shot-prefix /tmp/nw_keys
    # --focus CLASS: focus that window class first (default: off, only verify)
    # --restore:   after the sequence, focus the window that was active before (only with --focus)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    from evdev import UInput, ecodes as e
except ImportError:
    print("ERROR: python-evdev missing (use .venv-capture/bin/python)", file=sys.stderr)
    raise SystemExit(2)

GAME_CLASS = "steam_app_1063730"
KEYS = {
    "w": e.KEY_W, "a": e.KEY_A, "s": e.KEY_S, "d": e.KEY_D,
    "space": e.KEY_SPACE, "shift": e.KEY_LEFTSHIFT, "ctrl": e.KEY_LEFTCTRL,
    "e": e.KEY_E, "q": e.KEY_Q, "tab": e.KEY_TAB, "esc": e.KEY_ESC,
    "1": e.KEY_1, "2": e.KEY_2, "3": e.KEY_3, "4": e.KEY_4, "5": e.KEY_5,
    "r": e.KEY_R, "f": e.KEY_F, "m": e.KEY_M, "enter": e.KEY_ENTER,
}


def active_window():
    try:
        out = subprocess.run(["hyprctl", "activewindow", "-j"], capture_output=True, text=True,
                             timeout=10).stdout
        data = json.loads(out)
        return data.get("class", ""), data.get("address", "")
    except Exception:                                    # noqa: BLE001 - treat as unknown focus
        return "", ""


def focus_window(window_class):
    """Hyprland 0.56 exposes Lua dispatchers; keep the legacy form as a fallback."""
    for dispatcher in (f'hl.dsp.focus({{window="class:{window_class}"}})',
                       f"focuswindow class:{window_class}"):
        try:
            result = subprocess.run(["hyprctl", "dispatch", dispatcher],
                                    capture_output=True, text=True, timeout=10)
            if "error" not in (result.stdout + result.stderr).lower():
                break
        except Exception:                                # noqa: BLE001
            continue
    time.sleep(0.6)


def build_keyboard():
    keys = sorted(set(KEYS.values()))
    return UInput({e.EV_KEY: keys}, name="nw_vkeys virtual keyboard")


def shot(prefix, tag):
    if not prefix or shutil.which("grim") is None:
        return None
    path = Path(f"{prefix}-{tag}.png")
    try:
        subprocess.run(["grim", str(path)], check=True, capture_output=True, timeout=20)
        return str(path)
    except Exception as error:                           # noqa: BLE001
        return f"grim failed: {error}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seq", required=True,
                        help="comma separated key:seconds or 'release:seconds', e.g. 'w:6,release:2,w:6'")
    parser.add_argument("--expect-class", default=GAME_CLASS,
                        help="focused window class required before injecting (default: the game)")
    parser.add_argument("--focus", action="store_true",
                        help="focus --expect-class first instead of only verifying")
    parser.add_argument("--restore", action="store_true",
                        help="with --focus, refocus the window that was active before")
    parser.add_argument("--keep-focus", action="store_true",
                        help="with --focus, refocus the game before each step instead of aborting")
    parser.add_argument("--shot-prefix", help="grim screenshots before/after")
    parser.add_argument("--wait-focus", type=float, default=0.0,
                        help="seconds to wait for the expected window to become focused")
    args = parser.parse_args(argv)

    previous_class, previous_address = active_window()
    restored = False
    ui = build_keyboard()
    held = set()
    try:
        print(f"keyboard: name={ui.name!r} fw={ui.vendor:04x}:{ui.product:04x}")
        if args.focus:
            focus_window(args.expect_class)
        current_class, _ = active_window()
        if current_class != args.expect_class and args.wait_focus > 0:
            deadline = time.monotonic() + args.wait_focus
            print(f"waiting up to {args.wait_focus:.0f}s for {args.expect_class!r} "
                  f"to be focused (now {current_class!r})", flush=True)
            while time.monotonic() < deadline:
                time.sleep(0.5)
                current_class, _ = active_window()
                if current_class == args.expect_class:
                    print("focus acquired", flush=True)
                    break
        print(f"active window: {current_class!r} (expected {args.expect_class!r})")
        if current_class != args.expect_class:
            print("ABORT: the game does not have focus; no key was sent", file=sys.stderr)
            return 3
        before = shot(args.shot_prefix, "before")
        if before:
            print(f"screenshot before: {before}")

        for step in args.seq.split(","):
            step = step.strip()
            if not step:
                continue
            name, _, seconds = step.partition(":")
            seconds = float(seconds) if seconds else 1.0
            current_class, _ = active_window()
            if current_class != args.expect_class and args.keep_focus:
                print(f"  focus was on {current_class!r}; taking it back for this step")
                focus_window(args.expect_class)
                current_class, _ = active_window()
            if current_class != args.expect_class:
                for code in held:
                    ui.write(e.EV_KEY, code, 0)
                ui.syn()
                print(f"ABORT mid-sequence: focus moved to {current_class!r}, keys released",
                      file=sys.stderr)
                return 4
            if name in ("release", "stop"):
                for code in held:
                    ui.write(e.EV_KEY, code, 0)
                ui.syn()
                held.clear()
                print(f"  release -> {seconds}s")
            elif name in KEYS:
                code = KEYS[name]
                ui.write(e.EV_KEY, code, 1)
                ui.syn()
                held.add(code)
                print(f"  hold {name} -> {seconds}s")
            else:
                print(f"  unknown key {name!r} (ignored)")
                continue
            time.sleep(seconds)

        after = shot(args.shot_prefix, "after")
        if after:
            print(f"screenshot after: {after}")
        print("done")
        return 0
    finally:
        if held:
            for code in held:
                ui.write(e.EV_KEY, code, 0)
            ui.syn()
        ui.close()
        print("keyboard removed")
        if args.restore and previous_class:
            focus_window(previous_class)
            print(f"focus restored to {previous_class!r}")


if __name__ == "__main__":
    raise SystemExit(main())
