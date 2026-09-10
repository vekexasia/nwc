#!/usr/bin/env python3
"""Walk test: drive the running game with the virtual pad while tracing the candidate
coordinate field, then report where the ledger and the log are.

    .venv-capture/bin/python Tools/nw_capture/experimental/nw_walktest.py \
        --seq "forward:6,stop:3,forward:6" --capture 40

Order: the capture probe attaches first, then the pad plays the sequence, then the capture is
allowed to finish. No focus is taken: the pad does not need it and the screenshots use grim.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
VENV = REPO / ".venv-capture/bin/python"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--seq", default="forward:6,stop:3,forward:6",
                        help="pad sequence, see nw_vpad.py")
    parser.add_argument("--capture", type=float, default=40.0, help="capture seconds")
    parser.add_argument("--arm-wait", type=float, default=10.0,
                        help="seconds to wait for the probe to arm before driving the pad")
    parser.add_argument("--wait-focus", type=float, default=0.0,
                        help="seconds to wait for the game window to be focused before injecting")
    parser.add_argument("--shot-prefix", default="/tmp/nw_walktest/screen")
    args = parser.parse_args(argv)

    Path(args.shot_prefix).parent.mkdir(parents=True, exist_ok=True)
    seq_seconds = sum(float(s.partition(":")[2] or 1) for s in args.seq.split(",") if s.strip())
    need = args.arm_wait + args.wait_focus + seq_seconds + 30
    if args.capture < need:
        print(f"capture raised from {args.capture:.0f}s to {need:.0f}s to cover wait+sequence")
        args.capture = need
    capture = subprocess.Popen([str(VENV), str(HERE / "nw_capture_probe.py"),
                                "--probe", str(HERE / "nw_field_probe.js"),
                                "--seconds", str(args.capture), "--label", "walktest"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(f"capture started (pid {capture.pid}); waiting {args.arm_wait}s for the probe to arm")
    time.sleep(args.arm_wait)

    print(f"playing pad sequence: {args.seq}")
    pad = subprocess.run([str(VENV), str(HERE / "nw_vkeys.py"), "--seq", args.seq,
                          "--shot-prefix", args.shot_prefix,
                          "--wait-focus", str(args.wait_focus)],
                         capture_output=True, text=True)
    print(pad.stdout.strip() or pad.stderr.strip())

    print("waiting for the capture to finish")
    out, _ = capture.communicate(timeout=args.capture + 120)
    print(out.strip())
    print(f"screenshots: {args.shot_prefix}-before.png {args.shot_prefix}-after.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
