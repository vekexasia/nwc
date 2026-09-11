#!/usr/bin/env python3
"""Live view during a capture: tail the probe log, decode, serve it on a local page.

    # 1. capture with the live probe (one probe, three kinds of samples)
    .venv-capture/bin/python Tools/nw_capture/experimental/nw_capture_probe.py \
        --probe "$PWD/Tools/nw_capture/experimental/nw_live_probe.js" --seconds 60 --label live

    # 2. while it runs, follow that log
    .venv-capture/bin/python Tools/nw_capture/experimental/nw_live.py \
        --log Tools/nw_capture/logs/<run>_live.log --port 8765
    # then open http://127.0.0.1:8765/

What it shows: world position per object (ALC worldPosAbs), health and mana per Vitals object, and the
player names from PlayerComponent. With entity-keyed join samples, e1 is the player by default; otherwise
the page can identify the player by walking or by picking a table row.
The decoders are the same ones used offline; this only adds the tailing.
"""
from __future__ import annotations

import argparse
import functools
import json
import math
import os
import signal
import struct
import subprocess
import sys
import threading
import time
import uuid
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "offline"))
from decode_cooldowns import parse_cooldowns  # noqa: E402
from decode_mount import parse_mount  # noqa: E402
from decode_pose import pose_from_payload  # noqa: E402
from decode_rmi import DAMAGE_TYPES, parse_chat, parse_chat_batch, parse_damage_dealt, parse_damage_taken  # noqa: E402
from decode_stamina import parse_stamina  # noqa: E402
from decode_vitals import parse_full_state, parse_members  # noqa: E402  the shared, verified payload model

HERE_PAGE = HERE / "nw_live.html"
sys.path.insert(0, str(HERE.parents[1] / "nw_assets"))
try:
    import namebook  # noqa: E402  crc32(lowercase id) -> id, built from the game's datasheets
    NAMES = namebook.load()
except Exception:                     # noqa: BLE001 - the book is optional
    NAMES = {}


@functools.lru_cache(maxsize=1 << 16)
def book_hits(payload_hex: str, sheet_prefixes: tuple) -> tuple:
    """Datasheet ids found as 4-byte crc32 windows in a payload, restricted to sheets we expect.

    ponytail: a window scan, not a field decode; with 265k ids the chance of a stray match per window
    is 6e-5, and the sheet filter cuts what is left. Decode the field tables when a false name shows.
    """
    raw = bytes.fromhex(payload_hex)
    found = []
    for index in range(len(raw) - 3):
        entry = NAMES.get(raw[index:index + 4].hex())
        if entry and entry["sheet"].startswith(sheet_prefixes) and entry["id"] not in found:
            found.append(entry["id"])
    return tuple(found)


def name_of(crc_hex: str) -> str:
    """Short readable form of a datasheet id: 'Ability_VoidGauntlet_Scream' -> 'VoidGauntlet Scream'."""
    entry = NAMES.get(crc_hex)
    if not entry:
        return crc_hex
    if entry.get("text"):
        return entry["text"]          # the English string of the sheet's DisplayName
    parts = [p for p in entry["id"].split("_") if p.lower() not in ("ability", "mount", "mtx")]
    return " ".join(parts) or entry["id"]


def text_of(identifier: str) -> str:
    """English name of a datasheet id when the book has it, else the id."""
    import zlib
    entry = NAMES.get(f"{zlib.crc32(identifier.lower().encode()):08x}")
    return entry["text"] if entry and entry.get("text") else identifier


def decode_abs(payload_hex: str):
    """worldPosAbs: two big-endian float32 then a quantised u16 elevation in [-100, 1000]."""
    raw = bytes.fromhex(payload_hex)
    if len(raw) < 10:
        return None
    x, y, elevation = struct.unpack(">ffH", raw[:10])
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    if not (-1e6 < x < 1e6 and -1e6 < y < 1e6):
        return None
    # The u16 is quantised into [-100, 1000] (reader 0x142a433d0: 1/65535 then the range base), the
    # mapping decode_position.py uses and that sat a median 1.38 units from the community markers.
    return {"x": round(x, 2), "y": round(y, 2), "elev_raw": elevation,
            "elevation": round(-100.0 + elevation * 1100.0 / 65535.0, 1)}


class LiveState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.objects: dict[str, dict] = {}
        self.me: dict = {"object": None, "method": None}
        self.self_uuid: str | None = None   # PlayerManagerSelfIdentificationMsg: the character uuid

        self.history: dict[str, list[tuple[float, float, float]]] = {}
        self.auto_strikes: dict[str, int] = {}
        self.auto_debug: dict = {}
        self.last_auto = 0.0
        self.me_path = Path(os.environ.get("NW_LIVE_ME", "/tmp/nwc/nw_live_me.json"))
        self.max_path = self.me_path.with_name("nw_live_max.json")
        try:
            self.maxima = json.loads(self.max_path.read_text())
        except Exception:
            self.maxima = {}
        if self.me_path.exists():
            try:
                loaded = json.loads(self.me_path.read_text())
                if loaded.get("object"):
                    self.me = loaded          # survives a server restart; the id holds while the game runs
            except Exception:
                pass
        self.feed: list[dict] = []      # health changes, newest last: the damage feed
        self.chat_log: list[dict] = []  # ChatComponent RMIs, newest last
        self.calibration: dict | None = None   # {"until": ts, "started": ts, "moved": {key: distance}}
        self.counters = {"position": 0, "health": 0, "mana": 0, "player": 0, "lines": 0, "skipped": 0}
        self.started = time.time()
        self.last_line_at: float | None = None

    @staticmethod
    def _is_entity_key(key: str) -> bool:
        return key.startswith("e") and key[1:].isdigit()

    def _join_default(self, key: str) -> None:
        if not self._is_entity_key(key) or self.me.get("method") in ("walk", "picked"):
            return
        if self.me.get("object") == "e1" and self.me.get("method") == "join-default":
            return
        self.me = {"object": "e1", "method": "join-default", "at": time.time()}
        self._save_me()

    def _slot(self, key: str) -> dict:
        self._join_default(key)
        return self.objects.setdefault(key, {"object": key})

    def _save_me(self) -> None:
        try:
            self.me_path.parent.mkdir(parents=True, exist_ok=True)
            self.me_path.write_text(json.dumps(self.me))
        except Exception:
            pass

    def _follow(self, key: str, position: dict) -> None:
        """Hand the identification over when the state object is recreated.

        The game rebuilds these state objects, so the calibrated pointer goes stale while the entity
        stays. The identity fields we have are either per-record bookkeeping or readers shared by
        dozens of fields, so there is no stable id to key on: this follows the entity by continuity
        instead, and the page is told when it happens.
        """
        me = self.me
        calibrated = me.get("object")
        if not calibrated or key == calibrated:
            return
        if self._is_entity_key(calibrated):
            return                        # entity keys are stable: a quiet player is standing still, not gone
        last = self.objects.get(calibrated) or {}
        reference = last.get("position")
        if reference is None or (time.time() - (last.get("position_at") or 0)) < 15:
            return                        # the calibrated object is still talking: keep it
        # The candidate is talking right now (we are handling its position), and the object may well be
        # one we have seen before: the game reuses state objects, so "already seen" says nothing.
        distance = abs(position["x"] - reference["x"]) + abs(position["y"] - reference["y"])
        if distance > 25:
            return
        me["object"] = key
        me["followed_from"] = calibrated
        me["followed_at"] = time.time()
        me["follow_distance"] = round(distance, 1)
        self._save_me()

    def position(self, key: str, position: dict) -> None:
        if not all(math.isfinite(position.get(k, 0.0)) for k in ("x", "y")):
            return
        with self.lock:
            self._follow(key, position)
            if self.me.get("object") == key:
                self.me["at"] = time.time()
            now = time.time()
            history = self.history.setdefault(key, [])
            history.append((now, position["x"], position["y"]))
            while history and now - history[0][0] > 8.0:
                history.pop(0)
            previous = self._slot(key).get("position") if not self._slot(key).get("static") else None
            self._slot(key).update({"position": position, "position_at": time.time(), "static": False})
            self.counters["position"] += 1
            window = self.calibration
            if window is not None and previous is not None:
                step = abs(position["x"] - previous["x"]) + abs(position["y"] - previous["y"])
                if step < 500:      # a teleport or a bad read is not a step
                    window["moved"][key] = window["moved"].get(key, 0.0) + step

    def pick(self, key: str) -> dict:
        """Say who you are without walking: the entity key clicked in the table."""
        with self.lock:
            slot = self.objects.get(key)
            self.me = {"object": key, "method": "picked", "at": time.time(),
                       "name": slot.get("name") if slot else None}
            self._save_me()
            return dict(self.me)

    def reset(self) -> dict:
        """Forget every entity (a new game session reuses the keys); identity and maxima are kept."""
        with self.lock:
            dropped = len(self.objects)
            self.objects.clear()
            self.feed.clear()
            self.chat_log.clear()
            self.calibration = None
            return {"dropped": dropped}

    def pick_by_name(self, name: str) -> dict:
        """The same, by character name: the join attaches names to entities, so a name is enough."""
        with self.lock:
            for key, slot in self.objects.items():
                if (slot.get("name") or "").lower() == name.lower():
                    return self.pick(key)
            return {"error": f"no entity named {name!r} seen yet",
                    "seen": sorted(slot.get("name") for slot in self.objects.values() if slot.get("name"))}

    def start_calibration(self, seconds: float = 3.0) -> None:   # manual override, kept for the page
        """Watch the next seconds of movement: the object that walks is the player."""
        with self.lock:
            self.calibration = {"started": time.time(), "until": time.time() + seconds, "moved": {}}

    def finish_calibration(self) -> dict:
        with self.lock:
            window = self.calibration
            self.calibration = None
            if window is None:
                return dict(self.me)
            moved = sorted(window["moved"].items(), key=lambda kv: -kv[1])
            if not moved or moved[0][1] < 3.0:
                return {"object": self.me.get("object"), "method": None,
                        "note": "no object moved more than 3 units: nothing identified"}
            best = moved[0][0]
            margin = moved[0][1] / moved[1][1] if len(moved) > 1 and moved[1][1] > 1e-6 else None
            self.me = {"object": best, "method": "walk", "distance": round(moved[0][1], 1),
                       "margin_over_next": None if margin is None else round(margin, 2),
                       "at": time.time()}
            self._save_me()
            return dict(self.me)

    def calibration_active(self) -> bool:
        with self.lock:
            return self.calibration is not None and time.time() < self.calibration["until"]

    def vitals(self, key: str, decoded: dict) -> None:
        with self.lock:
            slot = self._slot(key)
            slot["vitals_at"] = time.time()
            decoded = {k: v for k, v in decoded.items() if math.isfinite(v)}
            if "health" in decoded:
                previous = slot.get("health")
                slot["health"] = round(decoded["health"], 1)
                self.counters["health"] += 1
                self._remember_max(key, slot, "health")
                # the player's own hits come exact from the OnDamage RMI; state deltas cover everyone else
                if previous is not None and abs(slot["health"] - previous) >= 0.5 and key != "e1":
                    self.feed.append({"at": time.time(), "key": key, "name": slot.get("name"),
                                      "delta": round(slot["health"] - previous, 1), "health": slot["health"]})
                    del self.feed[:-60]
            if "mana" in decoded:
                slot["mana"] = round(decoded["mana"], 2)
                self.counters["mana"] += 1
                self._remember_max(key, slot, "mana")

    # ponytail: HealthMax is a Vitals member we have not decoded (members 7..12), so the bar's ceiling
    # is the highest value seen, kept across server restarts in a small file keyed by entity key.
    def _remember_max(self, key: str, slot: dict, what: str) -> None:
        field = what + "_max"
        best = max(slot.get(field) or 0.0, self.maxima.get(key, {}).get(field, 0.0), slot[what])
        if best != slot.get(field):
            slot[field] = best
            self.maxima.setdefault(key, {})[field] = best
            try:
                self.max_path.parent.mkdir(parents=True, exist_ok=True)
                self.max_path.write_text(json.dumps(self.maxima))
            except Exception:
                pass

    def pose(self, key: str, decoded: dict) -> None:
        """ALC presentation: slayer state ids (layer 0 locomotion, layer 1 weapon) and the heading."""
        with self.lock:
            slot = self._slot(key)
            table = slot.setdefault("pose", {})
            for layer, value in decoded.get("pose", {}).items():
                table[str(layer)] = value["name"]
            for layer, value in decoded.get("pose", {}).items():
                slot.setdefault("pose_id", {})[str(layer)] = value["id"]
            for layer, value in decoded.get("sequence", {}).items():
                slot.setdefault("pose_seq", {})[str(layer)] = value
            if "heading" in decoded:
                slot["heading"] = decoded["heading"]
            if "stance" in decoded:
                slot["stance"] = decoded["stance"]
            slot["pose_at"] = time.time()
            self.counters["pose"] = self.counters.get("pose", 0) + 1

    def kind(self, key: str, player: bool) -> None:
        """Player character or not, from the Vitals full state (member 0 field bit 1: 100+ on every
        named player, 0 on pets, camps and mobs, 76 vs 76 entities over three logs). A pet wears its
        owner's PlayerComponent name, so the name alone cannot tell."""
        with self.lock:
            self._slot(key)["npc"] = not player

    def interacting(self, key: str, active: bool) -> None:
        """InteractReplicatedState (2930) `01 01 01` while an entity is in an interaction (gathering, and
        riding counts too), `01 01 00` after: a bot stood gathering for an hour with the flag at 1."""
        with self.lock:
            self._slot(key)["interacting"] = active

    def tags(self, key: str, field: str, ids: list, keep: int = 8) -> None:
        """Ids read through the name book: vitals row (what a mob is), items worn, status effects."""
        with self.lock:
            slot = self._slot(key)
            current = slot.setdefault(field, [])
            for value in map(text_of, ids):
                if value in current:
                    current.remove(value)
                current.append(value)
            del current[:-keep]

    def info(self, key: str, **fields) -> None:
        """Level (ProgressionComponent 899 member 0 bit 0, u32: 12 -> 1066 hp, 69 -> 18k hp on named
        players), faction id (FactionComponent 3152 member 2 bit 0, u8: javelindata_factiondata says
        1 Syndicate, 2 Marauders, 3 Covenant), mana from ManaComponent 1652 (the stamina shape), and the
        gatherable flag (GatherableController 12 present)."""
        with self.lock:
            self._slot(key).update({k: v for k, v in fields.items() if v is not None})

    def position_static(self, key: str, x: float, y: float) -> None:
        """PositionInTheWorld (13): the spawn position, sent once. Kept only for entities without an ALC
        track (camps, gatherables, placed objects); a moving entity's ALC position replaces it."""
        if not (math.isfinite(x) and math.isfinite(y) and 0 < x < 20000 and 0 < y < 20000):
            return
        with self.lock:
            slot = self._slot(key)
            if "position" not in slot:
                slot.update({"position": {"x": round(x, 2), "y": round(y, 2)}, "position_at": time.time(), "static": True})

    def mount(self, key: str, decoded: dict) -> None:
        """MountComponentReplicatedState: mounted flag (owner and remote shapes) and mount stamina."""
        with self.lock:
            slot = self._slot(key)
            for name in ("mounted", "mount_stamina"):
                if name in decoded:
                    slot[name] = decoded[name]
            if decoded.get("mount_id") and decoded["mount_id"] != "00000000":
                slot["mount_name"] = name_of(decoded["mount_id"])
            if decoded.get("mounted") is False:
                slot.pop("mount_name", None)      # "on X" only while riding
            slot["mount_at"] = time.time()

    def hit(self, entry: dict) -> None:
        """A per-hit damage RMI: exact amounts, unlike the health deltas sampled from state."""
        with self.lock:
            self.feed.append({"at": time.time(), **entry})
            del self.feed[:-200]

    def chat(self, message: dict) -> None:
        with self.lock:
            self.chat_log.append({"at": time.time(), **message})
            del self.chat_log[:-60]
            # the player's own name is not in any state chunk of e1; a chat line from the self uuid gives it
            if self.self_uuid and message.get("sender_id") == self.self_uuid:
                self._slot("e1")["name"] = message["name"]

    def cooldowns(self, key: str, entries: list) -> None:
        """CooldownTimersComponentReplicatedState deltas: one (id, start, expiry) per slot."""
        with self.lock:
            slot = self._slot(key)
            table = slot.setdefault("cooldowns", {})
            for entry in entries:
                table[str(entry["slot"])] = {"id": entry["id"], "name": name_of(entry["id"]),
                                             "start": round(entry["start"], 3), "expiry": round(entry["expiry"], 3)}
            self.counters["cooldown"] = self.counters.get("cooldown", 0) + len(entries)

    def stamina(self, key: str, decoded: dict) -> None:
        """StaminaComponentReplicatedState: the bar itself, about 60 Hz while it moves."""
        with self.lock:
            slot = self._slot(key)
            slot["stamina_at"] = time.time()
            if "stamina" in decoded:
                slot["stamina"] = round(decoded["stamina"], 1)
                self.counters["stamina"] = self.counters.get("stamina", 0) + 1
            if "stamina_max" in decoded:
                slot["stamina_max"] = decoded["stamina_max"]
            for name in ("winded_s", "regen_delay_s"):
                if name in decoded:
                    slot[name] = decoded[name]

    def player(self, key: str, name: str, character_id: str) -> None:
        with self.lock:
            slot = self._slot(key)
            slot["name"] = name
            slot["character_id"] = character_id
            self.counters["player"] += 1

    def skip(self) -> None:
        with self.lock:
            self.counters["skipped"] += 1

    def _me_view(self) -> dict:
        """The identification plus whether it is still alive, so the page can say so."""
        me = dict(self.me)
        slot = self.objects.get(me.get("object") or "")
        latest = max(slot.get("position_at") or 0, me.get("at") or 0) if slot else (me.get("at") or 0)
        me["position_age_s"] = None if not latest else round(time.time() - latest, 1)
        me["stale"] = bool(me.get("object")) and (me["position_age_s"] is None or me["position_age_s"] > 45)
        return me

    HISTORY_WINDOW = 8.0          # seconds of movement the auto tracker looks at
    AUTO_EVERY = 2.0              # how often it re-evaluates
    AUTO_MIN_MOVE = 25.0          # in 8s a walking player covers tens of units; a wandering mob does not
    AUTO_MARGIN = 1.6             # ...and beat the next candidate by this much (mobs wander too)
    AUTO_CONFIRMATIONS = 2        # ...twice in a row, so one lucky window does not decide it
    AUTO_KEEP_FRACTION = 0.4      # if the current "me" still moves this much of the best, keep it

    def _auto_identify(self, now: float) -> None:
        """Pick the player without being told: the object that is walking is the one being walked.

        Scoped on purpose: this only ever decides *identity*, never the coordinates, and every decision
        is reported with its margin so a wrong pick is visible in the page instead of silent.
        """
        if self.me.get("method") in ("walk", "picked", "join-default"):
            return          # explicit or join identity must not be replaced by movement heuristics
        if now - self.last_auto < self.AUTO_EVERY:
            return
        self.last_auto = now
        moved: dict[str, float] = {}
        for key, history in self.history.items():
            if len(history) < 2:
                continue
            displacement = max(
                abs(point[1] - history[0][1]) + abs(point[2] - history[0][2]) for point in history)
            if displacement >= self.AUTO_MIN_MOVE:
                moved[key] = displacement
        self.auto_debug = {
            "candidates": {key: round(value, 1) for key, value in sorted(
                moved.items(), key=lambda kv: -kv[1])[:4]},
            "window_s": self.HISTORY_WINDOW,
            "min_move": self.AUTO_MIN_MOVE,
            "margin_needed": self.AUTO_MARGIN,
            "strikes": {key: value for key, value in self.auto_strikes.items() if value},
        }
        if not moved:
            return
        best = max(moved, key=moved.get)
        best_distance = moved[best]
        runner_up = max((value for key, value in moved.items() if key != best), default=0.0)
        current = self.me.get("object")
        if current and moved.get(current, 0.0) >= self.AUTO_KEEP_FRACTION * best_distance:
            return                                  # the one we already follow is moving: keep it
        if runner_up > 0 and best_distance < self.AUTO_MARGIN * runner_up:
            self.auto_strikes[best] = 0             # ambiguous window: nothing decided
            return
        self.auto_strikes[best] = self.auto_strikes.get(best, 0) + 1
        for key in list(self.auto_strikes):
            if key != best:
                self.auto_strikes[key] = 0
        if self.auto_strikes[best] < self.AUTO_CONFIRMATIONS:
            return
        self.me = {"object": best, "method": "auto", "distance": round(best_distance, 1),
                   "margin_over_next": round(best_distance / runner_up, 2) if runner_up else None,
                   "at": now, "previous": current}
        self._save_me()

    def tick(self) -> None:
        with self.lock:
            self.counters["lines"] += 1
            self.last_line_at = time.time()

    def snapshot(self) -> dict:
        with self.lock:
            self._auto_identify(time.time())
            return {
                "now": time.time(),
                "uptime_s": round(time.time() - self.started, 1),
                "last_line_age_s": None if self.last_line_at is None else round(time.time() - self.last_line_at, 2),
                "counters": dict(self.counters),
                "me": self._me_view(),
                "auto": dict(self.auto_debug),
                # inside the lock already: calibration_active() would take it again
                "calibrating": self.calibration is not None and time.time() < self.calibration["until"],
                "objects": {k: v for k, v in sorted(self.objects.items())},
                "feed": self.feed[-30:],
                "chat": self.chat_log[-30:],
            }


def apply_line(line: str, state: LiveState) -> None:
    """One JSONL line from a probe log. Unknown shapes are counted, never guessed at."""
    try:
        entry = json.loads(line)
    except Exception:
        state.skip()
        return
    kind = entry.get("type")
    items = entry.get("items") or []
    if kind == "pos_samples":
        for item in items:
            if len(item) < 4:
                continue
            ts, tag, key, payload_hex = item[0], item[1], item[2], item[3]
            if tag != "ABS":
                continue
            position = decode_abs(payload_hex)
            if position is None:
                state.skip()
            else:
                state.position(key, position)
    elif kind == "join_samples":      # stamina and cooldowns; position, vitals and names have their own shapes
        for item in items:
            if len(item) < 7 or len(item[6]) != 2 * item[5]:
                continue
            if item[3] == 11:
                # only records that carry a state id; the position of the same record is in pos_samples
                if (decoded := pose_from_payload(bytes.fromhex(item[6]))):
                    state.pose(f"e{item[1]}", decoded)
            elif item[3] == 4297:
                decoded = parse_stamina(bytes.fromhex(item[6]))
                if decoded:
                    state.stamina(f"e{item[1]}", decoded)
            elif item[3] == 2932:
                entries = parse_cooldowns(bytes.fromhex(item[6]))
                if entries:
                    state.cooldowns(f"e{item[1]}", entries)
            elif item[3] == 5620:
                decoded = parse_mount(bytes.fromhex(item[6]))
                if decoded:
                    state.mount(f"e{item[1]}", decoded)
            elif item[3] == 15 and item[6][2:4] == "ff" and int(item[6][:2], 16) & 1 and item[5] >= 10:
                full = parse_full_state(bytes.fromhex(item[6]))
                player = struct.unpack(">f", bytes.fromhex(item[6][12:20]))[0] > 0
                state.kind(f"e{item[1]}", player)
                if full:
                    # mobs: the base max is the max; players: the live max sits above it (gear, attributes)
                    state.info(f"e{item[1]}", level=full.get("level"),
                               health_max=None if player else full["health_base_max"], health_base_max=full["health_base_max"])
                if NAMES:
                    state.tags(f"e{item[1]}", "vitals_ids", book_hits(item[6], ("vitals", "gatherables")), keep=2)
            elif item[3] == 899 and item[6][:4] in ("0101", "0301") and item[5] >= 6:
                # the wire value is the level minus one: level-70 players read 69 on the page
                state.info(f"e{item[1]}", level=int(item[6][4:12], 16) + 1)
            elif item[3] == 3152 and item[6][:2] == "04" and item[5] >= 3 and int(item[6][2:4], 16) & 1:
                state.info(f"e{item[1]}", faction=int(item[6][4:6], 16))
            elif item[3] == 1652:
                decoded = parse_stamina(bytes.fromhex(item[6]))
                if "stamina" in decoded:
                    state.info(f"e{item[1]}", mana=round(decoded["stamina"], 1), mana_max=decoded.get("stamina_max"))
            elif item[3] == 129 and item[6][:4] == "010f" and item[5] >= 42:
                # AttributeComponent full state: five (points u32, id u32) pairs, ids 4..0, then a u8.
                # There is no count: read as count + (id, value) the fifth value fell on a varint and
                # STR came out as 7 or garbage (50 records of the player: 5, 5, 225, 5, 5 on ids 4..0).
                # Id order STR, DEX, INT, FOC, CON as in the attribute datasheets; the 225 sits on id 2.
                raw = bytes.fromhex(item[6])
                pairs = [struct.unpack_from("<II", raw, 2 + 8 * i) for i in range(5)]
                if [i for _, i in pairs] == [4, 3, 2, 1, 0]:
                    names = ("STR", "DEX", "INT", "FOC", "CON")
                    state.info(f"e{item[1]}", attributes={names[i]: v for v, i in pairs})
            elif item[3] == 13 and item[5] >= 10 and item[6][:2] == "01" and int(item[6][2:4], 16) & 3 == 3:
                x, y = struct.unpack(">ff", bytes.fromhex(item[6][4:20]))
                state.position_static(f"e{item[1]}", x, y)
            elif item[3] == 12:
                state.info(f"e{item[1]}", gatherable=True)
            elif item[3] == 3183 and NAMES:
                weapons = [i for i in book_hits(item[6], ("itemdefinitions_",)) if i[:2].lower() in ("1h", "2h")]
                if weapons:
                    state.tags(f"e{item[1]}", "weapons", weapons, keep=4)
            elif item[3] == 4176 and NAMES:
                titles = book_hits(item[6], ("playertitles",))
                if titles:
                    state.tags(f"e{item[1]}", "titles", titles, keep=1)
            elif item[3] == 4236 and NAMES:
                effects = book_hits(item[6], ("statuseffects",))
                if effects:
                    state.tags(f"e{item[1]}", "effects", effects, keep=12)
            elif item[3] == 2930 and item[5] == 3 and item[6][:4] == "0101":
                state.interacting(f"e{item[1]}", item[6][4:6] == "01")
    elif kind == "rmi_samples":       # typed messages: chat for now, the rest is listed by decode_rmi.py
        for item in items:
            if len(item) < 3 or not item[2]:
                continue
            if item[1] == 4118:
                message = parse_chat(bytes.fromhex(item[2]))
                if message:
                    state.chat(message)
            elif item[1] == 293:
                for message in parse_chat_batch(bytes.fromhex(item[2])):
                    state.chat(message)
            elif item[1] == 1628 and len(item[2]) >= 34:
                state.self_uuid = str(uuid.UUID(hex=item[2][2:34]))
            elif item[1] == 3601:
                taken = parse_damage_taken(bytes.fromhex(item[2]))
                if taken:
                    state.hit({"key": "e1", "delta": -round(sum(e["amount"] for e in taken["entries"])),
                               "types": [DAMAGE_TYPES.get(e["type"], str(e["type"])) for e in taken["entries"]]})
            elif item[1] == 2071:
                dealt = parse_damage_dealt(bytes.fromhex(item[2]))
                if dealt and dealt["entries"]:
                    state.hit({"key": "dealt", "name": "you hit", "delta": -round(sum(e["amount"] for e in dealt["entries"])),
                               "types": [DAMAGE_TYPES.get(e["type"], str(e["type"])) for e in dealt["entries"]],
                               "dot": dealt["attack"] == "0" * 16})
    elif kind == "vitals_samples":
        for item in items:
            if len(item) < 3:
                continue
            decoded = parse_members(bytes.fromhex(item[2]))
            if decoded:
                state.vitals(item[1], decoded)
            else:
                state.skip()
    elif kind == "player_samples":
        for item in items:
            if len(item) < 4:
                continue
            state.player(item[1], item[2], item[3])
    elif kind == "state_calls":       # the older probes log this shape; accept them too
        for item in items:
            if len(item) < 5 or not item[4]:
                continue
            ts, name, _consumed, key, payload_hex = item[0], item[1], item[2], item[3], item[4]
            if name == "CONTROL-worldPosAbs-reader":
                position = decode_abs(payload_hex)
                if position is not None:
                    state.position(key, position)
            elif name == "Vitals-stage-90-mask":
                decoded = parse_members(bytes.fromhex(payload_hex))
                if decoded:
                    state.vitals(key, decoded)
    else:
        state.skip()
    state.tick()


def newest_log(directory: Path) -> Path | None:
    """The most recently modified .log in a directory, so a new capture is picked up on its own."""
    logs = sorted(directory.glob("*.log"), key=lambda p: p.stat().st_mtime if p.exists() else 0)
    return logs[-1] if logs else None


def tail(path: Path, state: LiveState, stop: threading.Event, poll: float = 0.2) -> None:
    """Follow an append-only JSONL log from a byte offset, keeping partial lines for the next pass.

    ``path`` may be a directory: then the newest ``*.log`` in it is followed, and a newer file
    replaces it, so one server can watch capture after capture.
    """
    offset = 0
    pending = b""
    directory = path if path.is_dir() else None
    if directory is not None:
        path = newest_log(directory) or path
        print(f"following the newest log in {directory}: {path}", flush=True)
    while not stop.is_set():
        if directory is not None:
            candidate = newest_log(directory)
            if candidate is not None and candidate != path:
                print(f"new capture: {candidate}", flush=True)
                # Keep session state: names arrive once and must survive log rotation.
                path, offset, pending = candidate, 0, b""
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            time.sleep(poll)
            continue
        if size < offset:            # a new capture replaced the file
            offset, pending = 0, b""
        if size > offset:
            with open(path, "rb") as handle:
                handle.seek(offset)
                chunk = handle.read()
            offset += len(chunk)
            chunk = pending + chunk
            lines = chunk.split(b"\n")
            pending = lines.pop() if lines and not chunk.endswith(b"\n") else b""
            for raw in lines:
                if raw.strip():
                    apply_line(raw.decode("utf-8", "replace"), state)
        time.sleep(poll)


class Capture:
    """Start and stop the join-probe capture from the page.

    The child gets SIGINT back to default (a shell background job leaves it ignored, which is why a
    capture started that way could not be stopped early), so stop is a SIGINT that the runner turns
    into a clean detach. The capture lock and the stale-agent check stay in nw_capture_probe.py.
    """
    PROBE = HERE / "nw_join_probe.js"
    RUNNER = HERE / "nw_capture_probe.py"
    LOCK = Path(os.environ.get("NW_CAPTURE_LOCK", "/tmp/nw-capture.lock"))

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.started_at: float | None = None
        self.seconds = 0
        self.log = open("/dev/null", "w")

    def status(self) -> dict:
        running = self.process is not None and self.process.poll() is None
        if self.process is not None and not running:
            self.exit_code = self.process.returncode
            self.process = None
        try:
            owner = self.LOCK.read_text().strip()
        except OSError:
            owner = ""
        return {"running": running, "since": self.started_at if running else None, "seconds": self.seconds,
                "lock": owner, "exit_code": getattr(self, "exit_code", None)}

    def start(self, seconds: int) -> dict:
        if self.status()["running"]:
            return {"error": "a capture started from here is already running"}
        seconds = max(30, min(int(seconds), 4 * 3600))
        out = Path("/tmp/nwc"); out.mkdir(parents=True, exist_ok=True)
        self.log = open(out / "live_capture.out", "w")
        self.process = subprocess.Popen(
            [sys.executable, str(self.RUNNER), "--probe", str(self.PROBE), "--seconds", str(seconds),
             "--label", "live", "--wait", "30"],
            cwd=str(HERE.parents[2]), stdout=self.log, stderr=subprocess.STDOUT,
            start_new_session=True, preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
        self.started_at, self.seconds = time.time(), seconds
        return self.status()

    def watch(self, seconds: int = 7200) -> None:
        """Start a capture whenever the game is running and none is: the player's own full states
        (name, gear, attributes) arrive at spawn, so the capture has to be up before the world loads."""
        def loop():
            while True:
                try:
                    game = subprocess.run(["pgrep", "-x", "NewWorld.exe"], capture_output=True, text=True).stdout.strip()
                    status = self.status()
                    if game and not status["running"] and not status["lock"] and (
                            self.started_at is None or time.time() - self.started_at > 30):
                        print(f"auto-capture: game pid {game.split()[0]}, starting", flush=True)
                        self.start(seconds)
                except Exception as error:      # noqa: BLE001 - the watcher must survive
                    print(f"auto-capture: {error}", flush=True)
                time.sleep(5)
        threading.Thread(target=loop, daemon=True).start()

    def stop(self) -> dict:
        if not self.status()["running"]:
            return {"error": "no capture started from here is running", **self.status()}
        self.process.send_signal(signal.SIGINT)      # the runner's KeyboardInterrupt path: clean detach
        return self.status()


def make_handler(state: LiveState, capture: Capture | None = None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):    # quiet
            pass

        def _answer(self, answer: dict) -> None:
            body = json.dumps(answer, allow_nan=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            if self.path.startswith("/pick"):
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if query.get("name"):
                    self._answer(state.pick_by_name(query["name"][0]))
                elif query.get("key"):
                    self._answer(state.pick(query["key"][0]))
                else:
                    self._answer({"error": "pass key= or name="})
            elif self.path.startswith("/reset"):
                self._answer(state.reset())
            elif self.path.startswith("/capture/start") and capture is not None:
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                self._answer(capture.start(int(query.get("seconds", ["1800"])[0])))
            elif self.path.startswith("/capture/stop") and capture is not None:
                self._answer(capture.stop())
            elif self.path.startswith("/calibrate"):
                state.start_calibration(3.0)
                time.sleep(3.2)
                body = json.dumps(state.finish_calibration()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def do_GET(self):
            if self.path.startswith("/state"):
                # allow_nan=False: a non-finite number would make the browser's JSON.parse fail, which
                # is exactly what showed up as "cannot reach the server" in the page.
                snapshot = state.snapshot()
                if capture is not None:
                    snapshot["capture"] = capture.status()
                body = json.dumps(snapshot, allow_nan=False).encode()
                ctype = "application/json"
            elif self.path in ("/", "/index.html"):
                body = HERE_PAGE.read_bytes()
                ctype = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass   # the browser navigated away mid-request (clicking a link does this)

    return Handler


def check_page_script() -> str:
    """The page's inline script must parse. A stray redeclaration killed it silently once."""
    import re
    import shutil
    import subprocess as sp
    import tempfile

    html = HERE_PAGE.read_text()
    match = re.search(r"<script>(.*?)</script>", html, re.S)
    if match is None:
        return "the page has no inline script?"
    node = shutil.which("node")
    if node is None:
        return "node not found: page script not checked"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
        handle.write(match.group(1))
        path = handle.name
    try:
        result = sp.run([node, "--check", path], capture_output=True, text=True)
        if result.returncode != 0:
            raise AssertionError("page script does not parse: " + result.stderr.strip().splitlines()[-1])
    finally:
        Path(path).unlink(missing_ok=True)
    return "page script parses"


def self_check() -> int:
    """The tailer must follow an appended log and must not consume a half-written line."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "synthetic.log"
        state = LiveState()
        log.write_text("")
        stop = threading.Event()
        thread = threading.Thread(target=tail, args=(log, state, stop), kwargs={"poll": 0.05}, daemon=True)
        thread.start()
        with open(log, "a") as handle:
            handle.write(json.dumps({"type": "pos_samples", "items": [[1, "ABS", "0xabc",
                struct.pack(">ffH", 8786.66, 3003.97, 58).hex()]]}) + "\n")
            handle.write(json.dumps({"type": "vitals_samples", "items": [[2, "0xabc",
                "0101461b88f3"]]}) + "\n")
            handle.write(json.dumps({"type": "player_samples", "items": [[3, "0xabc", "stormvind", "682b"]]}) + "\n")
        time.sleep(0.3)
        snapshot = state.snapshot()
        slot = snapshot["objects"].get("0xabc")
        assert slot is not None, snapshot
        assert abs(slot["position"]["x"] - 8786.66) < 0.01, slot
        assert abs(slot["position"]["y"] - 3003.97) < 0.01, slot
        assert slot["position"]["elev_raw"] == 58, slot
        assert abs(slot["health"] - 9954.2) < 0.1, slot
        assert slot["name"] == "stormvind", slot
        # a half-written line must wait for its newline
        with open(log, "a") as handle:
            handle.write('{"type": "vitals_samples", "items": [[4, "0xabc", "020142803317"')
        time.sleep(0.3)
        assert "mana" not in state.snapshot()["objects"]["0xabc"], "partial line was consumed"
        with open(log, "a") as handle:
            handle.write(']]}\n')
        time.sleep(0.3)
        assert abs(state.snapshot()["objects"]["0xabc"]["mana"] - 64.1) < 0.1, state.snapshot()
        # calibration: the object that walks is the one that moved most, and the margin is reported
        state2 = LiveState()
        state2.me_path = Path(tmp) / "me.json"    # never overwrite the real identification
        state2.start_calibration(10.0)
        state2.position("0xwalker", {"x": 100.0, "y": 100.0, "elev_raw": 1})
        state2.position("0xidle", {"x": 500.0, "y": 500.0, "elev_raw": 1})
        for step in range(1, 7):
            state2.position("0xwalker", {"x": 100.0 + 5 * step, "y": 100.0, "elev_raw": 1})
            state2.position("0xidle", {"x": 500.0 + 0.2 * step, "y": 500.0, "elev_raw": 1})
        picked = state2.finish_calibration()
        assert picked["object"] == "0xwalker", picked
        assert picked["distance"] == 30.0, picked
        assert picked["margin_over_next"] and picked["margin_over_next"] > 10, picked
        # a NaN must never reach the JSON: the browser cannot parse it
        state3 = LiveState()
        state3.me_path = Path(tmp) / "me3.json"
        nan_payload = struct.pack(">f", float("nan")).hex()
        state3.vitals("0xnan", {"health": float("nan"), "mana": 12.5})
        state3.position("0xnan", {"x": float("inf"), "y": 1.0, "elev_raw": 1})
        blob = json.dumps(state3.snapshot(), allow_nan=False)      # must not raise
        assert "NaN" not in blob and "Infinity" not in blob, blob
        assert state3.snapshot()["objects"]["0xnan"].get("mana") == 12.5, state3.snapshot()

        # reset drops the entities and keeps who you are
        state13 = LiveState()
        state13.me_path = Path(tmp) / "me13.json"; state13.max_path = Path(tmp) / "max13.json"; state13.maxima = {}
        state13.player("e1", "Tester", "id"); state13.me = {"object": "e1", "method": "picked"}
        assert state13.reset() == {"dropped": 1} and not state13.objects and state13.me["object"] == "e1"

        # the reference position of alc-protocol-reference.md 2.4 decodes to elevation 72.1
        assert decode_abs("460ab4d245436963280c")["elevation"] == 72.1, decode_abs("460ab4d245436963280c")

        # level, faction and mana ride on their own states
        state15 = LiveState()
        state15.me_path = Path(tmp) / "me15.json"; state15.max_path = Path(tmp) / "max15.json"; state15.maxima = {}
        apply_line(json.dumps({"type": "join_samples", "items": [
            [1, 36, 70, 899, "0x0", 6, "010100000040"], [2, 36, 49, 3152, "0x0", 6, "040f03000100"],
            [3, 36, 62, 1652, "0x0", 18, "010f42c8000042c80000000000003f800000"], [4, 36, 49, 3152, "0x0", 3, "040201"]]}), state15)
        e36 = state15.objects["e36"]
        assert e36["level"] == 65 and e36["faction"] == 3 and e36["mana"] == 100.0 and e36["mana_max"] == 100.0, e36
        apply_line(json.dumps({"type": "join_samples", "items": [[5, 36, 1, 129, "0x0", 100,
            "010f05000000040000000500000003000000e10000000200000005000000010000000500000000000000070001a90a000001a90a05"
            + "0000000000000000000000000000000000000000000000ee01000200000003000000dc000000000000000200000002"]]}), state15)
        assert state15.objects["e36"]["attributes"] == {"STR": 5, "DEX": 5, "INT": 225, "FOC": 5, "CON": 5}, state15.objects["e36"]

        # a static position stays until an ALC one arrives, and never overrides one
        apply_line(json.dumps({"type": "join_samples", "items": [[1, 41, 1, 13, "0x0", 15, "0103460ab2be4582dc881d0603ff09"], [2, 41, 0, 12, "0x0", 3, "010108"]]}), state15)
        e41 = state15.objects["e41"]
        assert e41["static"] is True and e41["gatherable"] is True and abs(e41["position"]["x"] - 8876.7) < 0.1, e41
        state15.position("e41", {"x": 8880.0, "y": 4180.0, "elev_raw": 0, "elevation": 0.0})
        assert state15.objects["e41"]["static"] is False and state15.objects["e41"]["position"]["x"] == 8880.0

        # chat RMIs land in the chat log
        state17 = LiveState()
        state17.me_path = Path(tmp) / "me17.json"; state17.max_path = Path(tmp) / "max17.json"; state17.maxima = {}
        apply_line(json.dumps({"type": "rmi_samples", "items": [[1, 4118,
            "515ac85acc363edc31df13d046e908f82433643331383031302d623431362d346230622d386266372d366565323532313836643664"
            "085065746157617474020000000000046369616f00000000000000000000011137363536313139393532323337343831380103"]]}), state17)
        assert state17.snapshot()["chat"][0]["text"] == "ciao" and state17.snapshot()["chat"][0]["name"] == "PetaWatt", state17.chat_log
        apply_line(json.dumps({"type": "rmi_samples", "items": [[1, 2071,
            "fea3936321dfc8b931df13d046e908f8c45391666544b3fd990779b848b78ee4fdb34465669153c4b171e15b7545ea13200002054490da403f2aec560e43c455f53f2dc11a"],
            [2, 3601, "fc65cc3aebb909fc31df13d046e908f8fdb34465669153c422003d0e40134611e0a24531fef7429df16d010543a7ba103ef9b7f8"]]}), state17)
        assert [f["delta"] for f in state17.feed] == [-1552, -336], state17.feed
        apply_line(json.dumps({"type": "rmi_samples", "items": [[3, 1628, "053d318010b4164b0b8bf76ee252186d6d5c3e1369"], [4, 4118,
            "515ac85acc363edc31df13d046e908f82433643331383031302d623431362d346230622d386266372d366565323532313836643664"
            "085065746157617474020000000000046369616f00000000000000000000011137363536313139393532323337343831380103"]]}), state17)
        assert state17.objects["e1"]["name"] == "PetaWatt", state17.objects.get("e1")

        # every health change is a feed entry with its delta
        state14 = LiveState()
        state14.me_path = Path(tmp) / "me14.json"; state14.max_path = Path(tmp) / "max14.json"; state14.maxima = {}
        state14.player("e9", "Kaneda", "id")
        state14.vitals("e9", {"health": 1042.5}); state14.vitals("e9", {"health": 680.5}); state14.vitals("e9", {"health": 680.5})
        assert [f["delta"] for f in state14.feed] == [-362.0] and state14.feed[0]["name"] == "Kaneda", state14.feed
        assert state14.snapshot()["feed"] == state14.feed

        # the bar ceiling is the highest value seen and survives a restart
        state11 = LiveState()
        state11.me_path = Path(tmp) / "me11.json"; state11.max_path = Path(tmp) / "max11.json"; state11.maxima = {}
        state11.vitals("e1", {"health": 10519.7}); state11.vitals("e1", {"health": 8071.0})
        assert state11.objects["e1"]["health_max"] == 10519.7, state11.objects["e1"]
        state12 = LiveState()
        state12.me_path = Path(tmp) / "me12.json"; state12.max_path = Path(tmp) / "max11.json"
        state12.maxima = json.loads(state12.max_path.read_text())
        state12.vitals("e1", {"health": 8000.0})
        assert state12.objects["e1"]["health_max"] == 10519.7, state12.objects["e1"]

        # the stamina state rides on join_samples (typeIndex 4297); other types there are ignored
        state10 = LiveState()
        state10.me_path = Path(tmp) / "me10.json"
        apply_line(json.dumps({"type": "join_samples", "items": [
            [1, 5, 16, 15, "0x0", 3, "010100"],
            [2, 5, 62, 4297, "0x0", 10, "0109425c00003f800000"]]}), state10)
        assert state10.objects["e5"]["stamina"] == 55.0 and state10.objects["e5"]["regen_delay_s"] == 1.0, state10.objects
        apply_line(json.dumps({"type": "join_samples", "items": [
            [3, 5, 41, 2932, "0x0", 27, "010101011b0fa51101a0260002fe31ed13a78b0002fe31eba6f914"]]}), state10)
        cd = state10.objects["e5"]["cooldowns"]["0"]
        assert cd["id"] == "1b0fa511" and abs(cd["expiry"] - cd["start"] - 23.9) < 0.01, cd
        # a real poseA record (11:47:00.7, jump): groupMask 1, mask with bits 0,1,13,14,15,26,27,28 -> the label
        from encode_alc_state import encode_mask_varint
        mask = encode_mask_varint((1 << 0) | (1 << 1) | (1 << 13))
        record = (bytes([0x01]) + mask + bytes([0x4b, 0x1c, 0x0e])).hex()
        apply_line(json.dumps({"type": "join_samples", "items": [[4, 5, 16, 11, "0x0", len(record) // 2, record]]}), state10)
        assert state10.objects["e5"]["pose"] == {"0": "jump"} and state10.objects["e5"]["pose_id"] == {"0": 14}, state10.objects["e5"]
        mask = encode_mask_varint((1 << 0) | (1 << 1) | (1 << 11))
        record = (bytes([0x01]) + mask + bytes([0x4b, 0x1c, 0x46, 0x96])).hex()
        apply_line(json.dumps({"type": "join_samples", "items": [[5, 5, 16, 11, "0x0", len(record) // 2, record]]}), state10)
        assert state10.objects["e5"]["heading"] == -104.3, state10.objects["e5"]
        mask = encode_mask_varint((1 << 0) | (1 << 1) | (1 << 43))
        record = (bytes([0x01]) + mask + bytes([0x4b, 0x1c, 0x89])).hex()
        apply_line(json.dumps({"type": "join_samples", "items": [[5, 5, 16, 11, "0x0", len(record) // 2, record]]}), state10)
        assert state10.objects["e5"]["stance"] == "crouched", state10.objects["e5"]
        apply_line(json.dumps({"type": "join_samples", "items": [
            [6, 5, 62, 5620, "0x0", 11, "02100118d443b5eded1434"],
            [7, 8, 62, 5620, "0x0", 12, "0c0100000000030400000000"]]}), state10)
        assert state10.objects["e5"]["mounted"] is True and state10.objects["e8"]["mounted"] is False, state10.objects
        apply_line(json.dumps({"type": "join_samples", "items": [
            [8, 8, 41, 15, "0x0", 50, "01ff4687c51f43050000000bb0f4b46539ba9e0000000000000000ff01" + "00" * 21],
            [8, 5, 41, 15, "0x0", 56, "01ff44090000000000000000b0f7b6e66155040000000000000000ff00" + "00" * 27],
            [9, 5, 30, 2930, "0x0", 3, "010101"], [10, 8, 30, 2930, "0x0", 6, "010200000001"]]}), state10)
        assert state10.objects["e8"]["npc"] is False and state10.objects["e5"]["npc"] is True, state10.objects
        assert state10.objects["e5"]["interacting"] is True and "interacting" not in state10.objects["e8"], state10.objects

        # entity keys use the verified join identity unless the user has chosen one
        state7 = LiveState()
        state7.me_path = Path(tmp) / "me7.json"
        state7.me = {"object": None, "method": None}
        state7.player("e158", "Where Arda", "682b")
        assert state7.me["object"] == "e1" and state7.me["method"] == "join-default", state7.me
        state7.pick("e158")
        state7.player("e1", "stormvind", "player")
        assert state7.me["object"] == "e158" and state7.me["method"] == "picked", state7.me
        state7.me = {"object": "e220", "method": "walk"}
        state7.player("e1", "stormvind", "player")
        assert state7.me["object"] == "e220" and state7.me["method"] == "walk", state7.me

        # rotation changes the file, not the session state: names and values remain available
        rotation_dir = Path(tmp) / "rotating"
        rotation_dir.mkdir()
        first = rotation_dir / "first.log"
        first.write_text("")
        state8 = LiveState()
        state8.me_path = Path(tmp) / "me8.json"
        state8.me = {"object": None, "method": None}
        stop8 = threading.Event()
        thread8 = threading.Thread(target=tail, args=(rotation_dir, state8, stop8),
                                    kwargs={"poll": 0.05}, daemon=True)
        thread8.start()
        try:
            with open(first, "a") as handle:
                handle.write(json.dumps({"type": "pos_samples", "items": [[1, "ABS", "e158",
                    struct.pack(">ffH", 8786.66, 3003.97, 58).hex()]]}) + "\n")
                handle.write(json.dumps({"type": "vitals_samples", "items": [[2, "e158",
                    "0101461b88f3"]]}) + "\n")
                handle.write(json.dumps({"type": "player_samples", "items": [[3, "e158",
                    "Where Arda", "682b"]]}) + "\n")
            deadline = time.time() + 2.0
            while state8.objects.get("e158", {}).get("name") != "Where Arda" and time.time() < deadline:
                time.sleep(0.05)
            first_snapshot = state8.snapshot()
            first_slot = first_snapshot["objects"]["e158"]
            assert first_slot["name"] == "Where Arda" and "health" in first_slot, first_snapshot
            second = rotation_dir / "second.log"
            second.write_text("")
            with open(second, "a") as handle:
                handle.write(json.dumps({"type": "pos_samples", "items": [[4, "ABS", "e1",
                    struct.pack(">ffH", 9000.0, 3000.0, 59).hex()]]}) + "\n")
            deadline = time.time() + 2.0
            while "e1" not in state8.objects and time.time() < deadline:
                time.sleep(0.05)
            rotated_snapshot = state8.snapshot()
            rotated_slot = rotated_snapshot["objects"].get("e158")
            assert rotated_slot and rotated_slot["name"] == "Where Arda", rotated_snapshot
            assert "health" in rotated_slot and "position" in rotated_slot, rotated_snapshot
        finally:
            stop8.set()
            thread8.join(1)

        # with an entity key nothing is handed over: standing still is not disappearing
        state9 = LiveState()
        state9.me_path = Path(tmp) / "me9.json"
        state9.me = {"object": "e1", "method": "join-default"}
        state9.objects["e1"] = {"object": "e1", "position": {"x": 1.0, "y": 1.0}, "position_at": time.time() - 60}
        state9.position("e77", {"x": 2.0, "y": 2.0, "elev_raw": 0})
        assert state9.me["object"] == "e1" and "followed_from" not in state9.me, state9.me

        # continuity: when the calibrated object goes quiet and another shows up where it was, take over
        state4 = LiveState()
        state4.me_path = Path(tmp) / "me4.json"
        state4.me = {"object": "0xold", "method": "walk", "at": time.time() - 100}
        state4.position("0xold", {"x": 100.0, "y": 100.0, "elev_raw": 1})
        state4.objects["0xold"]["position_at"] = time.time() - 60
        state4.position("0xnew", {"x": 103.0, "y": 101.0, "elev_raw": 1})
        assert state4.me["object"] == "0xnew", state4.me
        assert state4.me["followed_from"] == "0xold", state4.me
        # ...but not to something far away
        state5 = LiveState()
        state5.me_path = Path(tmp) / "me5.json"
        state5.me = {"object": "0xold", "method": "walk", "at": time.time() - 100}
        state5.position("0xold", {"x": 100.0, "y": 100.0, "elev_raw": 1})
        state5.objects["0xold"]["position_at"] = time.time() - 60
        state5.position("0xfar", {"x": 500.0, "y": 500.0, "elev_raw": 1})
        assert state5.me["object"] == "0xold", state5.me

        # auto identification: no button, the walker is adopted after two confirmations
        state6 = LiveState()
        state6.me_path = Path(tmp) / "me6.json"
        state6.me = {"object": None, "method": None}   # the constructor loads the real one
        state6.last_auto = 0.0
        base = time.time() - 6
        for step in range(6):
            state6.position("0xwalker", {"x": 100.0 + 10 * step, "y": 100.0, "elev_raw": 1})
            state6.position("0xstill", {"x": 900.0, "y": 900.0, "elev_raw": 1})
        state6.history["0xwalker"] = [(base + i, 100.0 + 10 * i, 100.0) for i in range(6)]
        state6._auto_identify(time.time())
        assert state6.me.get("object") is None, state6.me          # one window is not enough
        state6._auto_identify(time.time() + LiveState.AUTO_EVERY)
        assert state6.me["object"] == "0xwalker", state6.me
        assert state6.me["method"] == "auto" and state6.me["margin_over_next"] is None, state6.me
        # ...and it does not switch away while the tracked object is still the one walking
        state6.history["0xother"] = [(base + i, 500.0 + i, 500.0) for i in range(6)]
        state6._auto_identify(time.time() + 2 * LiveState.AUTO_EVERY)
        assert state6.me["object"] == "0xwalker", state6.me

        # when nothing moves the previous identification is kept, and the run says so
        state2.start_calibration(10.0)
        state2.position("0xidle", {"x": 500.0, "y": 500.0, "elev_raw": 1})
        quiet = state2.finish_calibration()
        assert quiet["object"] == "0xwalker" and quiet["note"], quiet
        stop.set()
    print("self-check ok: tail, position, health, mana, name, partial line, walk calibration, "
          "JSON strictness, and " + check_page_script())
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", type=Path, help="probe log to follow, or a directory of them")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--check", action="store_true", help="run the self-check and exit")
    parser.add_argument("--auto-capture", action="store_true",
                        help="start the join-probe capture whenever the game runs and no capture does")
    args = parser.parse_args(argv)
    if args.check:
        return self_check()
    if not args.log:
        parser.error("--log or --check is required")
    state = LiveState()
    stop = threading.Event()
    threading.Thread(target=tail, args=(args.log, state, stop), daemon=True).start()
    capture = Capture()
    if args.auto_capture:
        capture.watch()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state, capture))
    print(f"following {args.log}")
    print(f"open http://{args.host}:{args.port}/   (state: /state)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
