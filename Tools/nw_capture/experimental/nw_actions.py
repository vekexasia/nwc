#!/usr/bin/env python3
r"""Scripted action sequence in the focused game: sprint, stand, casts, self-drain.

    .venv-capture/bin/python Tools/nw_capture/experimental/nw_actions.py

Takes the focus (the game needs it for injected input), plays the sequence, releases every
key/button on the way out and restores the window that was active before. It writes a timeline
so a capture taken at the same time can be read per phase:

    .venv-capture/bin/python Tools/nw_capture/experimental/nw_capture_probe.py \
        --probe Tools/nw_capture/experimental/nw_state_probe.js --seconds 45 --label actions

Shift is the dodge and a dodge is what consumes stamina, so the run phase is marked separately
around a single tap of shift. The spells are Q, R and F and they consume mana. The right mouse button
drains the player's own health with the Void Gauntlet, which is what identifies the player's Vitals
object in a capture (its health deltas match the numbers on screen).
"""
import json, sys, time
sys.path.insert(0, "/home/andrea/git/personale/new-world-capture/Tools/nw_capture/experimental")
import nw_vkeys as vk
from evdev import UInput, ecodes as e


# This script injects input and takes the focus, so asking for help must not play the sequence.
if any(a in ("-h", "--help") for a in sys.argv[1:]):
    print(__doc__)
    raise SystemExit(0)
TL = []
def mark(p): TL.append((int(time.time()*1000), p)); print(">>", p, flush=True)

ui = UInput({e.EV_KEY: [vk.KEYS["w"], vk.KEYS["shift"], vk.KEYS["space"], e.BTN_RIGHT,
                        vk.KEYS["q"], vk.KEYS["r"], vk.KEYS["f"]]}, name="nw_actions")
held = set()
def down(k): ui.write(e.EV_KEY, k, 1); ui.syn(); held.add(k)
def up(k): ui.write(e.EV_KEY, k, 0); ui.syn(); held.discard(k)
prev, _ = vk.active_window()
try:
    vk.focus_window(vk.GAME_CLASS); time.sleep(1.2)
    if vk.active_window()[0] != vk.GAME_CLASS:
        print("ABORT: no focus", file=sys.stderr); raise SystemExit(3)
    mark("run_start"); down(vk.KEYS["w"]); time.sleep(1.0)
    mark("dodge"); down(vk.KEYS["shift"]); time.sleep(0.2); up(vk.KEYS["shift"])
    time.sleep(5.8); up(vk.KEYS["w"]); mark("run_end")
    mark("stand1"); time.sleep(4)
    mark("cast1"); down(vk.KEYS["q"]); time.sleep(0.2); up(vk.KEYS["q"]); time.sleep(2.5)
    mark("cast2"); down(vk.KEYS["r"]); time.sleep(0.2); up(vk.KEYS["r"]); time.sleep(2.5)
    mark("cast3"); down(vk.KEYS["f"]); time.sleep(0.2); up(vk.KEYS["f"]); time.sleep(2.0)
    mark("drain_start"); down(e.BTN_RIGHT); time.sleep(10); up(e.BTN_RIGHT)
    mark("drain_end"); time.sleep(5)
    mark("end")
finally:
    for k in list(held):
        try: up(k)
        except Exception: pass
    ui.close()
    json.dump(TL, open("/tmp/nwc/actions_timeline.json", "w"))
    if prev:
        try: vk.focus_window(prev)
        except Exception: pass
    print("released; focus now:", vk.active_window(), flush=True)
