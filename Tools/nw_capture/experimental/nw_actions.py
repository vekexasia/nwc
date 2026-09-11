#!/usr/bin/env python3
"""Scripted action sequence in the focused game: sprint, stand, casts, self-drain.

    .venv-capture/bin/python Tools/nw_capture/experimental/nw_actions.py

Takes the focus (the game needs it for injected input), plays the sequence, releases every
key/button on the way out and restores the window that was active before. It writes a timeline
so a capture taken at the same time can be read per phase:

    .venv-capture/bin/python Tools/nw_capture/experimental/nw_capture_probe.py \
        --probe Tools/nw_capture/experimental/nw_state_probe.js --seconds 45 --label actions

Sprint changes the stamina fields, the spells (Q, R, F) the mana ones, and the right mouse button
player's own health with the Void Gauntlet, which is what identifies the player's Vitals object in
a capture (its health deltas match the numbers on screen).
"""
import json, sys, time
sys.path.insert(0, "/home/andrea/git/personale/new-world-capture/Tools/nw_capture/experimental")
import nw_vkeys as vk
from evdev import UInput, ecodes as e

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
    mark("sprint_start"); down(vk.KEYS["w"]); down(vk.KEYS["shift"]); time.sleep(7)
    up(vk.KEYS["shift"]); up(vk.KEYS["w"]); mark("sprint_end")
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
