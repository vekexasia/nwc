# /// script
# dependencies = ["evdev==2.0.0"]
# ///
import csv
import io
import json
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from evdev import UInput, ecodes as e

GAME_CLASS = "steam_app_1063730"
GAME_LOG = Path.home() / ".local/share/Steam/steamapps/compatdata/1063730/pfx/drive_c/users/steamuser/AppData/Local/AGS/New World/Game.log"
SCREENSHOT = Path(__file__).parent / "nw_capture/logs/login-last.png"


def window():
    windows = json.loads(subprocess.check_output(["hyprctl", "clients", "-j"], timeout=10))
    return next((w for w in windows if w["class"] == GAME_CLASS), None)


def button(words):
    text = " ".join(w["text"].upper() for w in words if w["text"].strip())
    # ponytail: English 1920x1080 UI only; add other layouts after verifying screenshots.
    if "PRESS ANY BUTTON TO CONTINUE" in text:
        return (960, 880)
    if "SELECT CHARACTER" in text:
        for w in words:
            if w["text"].upper() == "PLAY":
                x = int(w["left"]) + int(w["width"]) // 2
                y = int(w["top"]) + int(w["height"]) // 2
                if x > 1440 and y > 810:
                    return (x, y)
    return None


def main():
    SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
    log_path = SCREENSHOT.parent / "login-last.log"
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(log_path, mode="w")],
    )
    logging.info("START log=%s screenshot=%s; Ctrl+C stops automation, not the game", log_path, SCREENSHOT)
    if window():
        logging.error("New World is already open; close it before running this script.")
        raise SystemExit(1)
    logging.info("LAUNCH steam -applaunch 1063730 %s", sys.argv[1:])
    subprocess.run(["steam", "-applaunch", "1063730", *sys.argv[1:]], check=True, timeout=20)
    deadline = time.monotonic() + 600
    log_offset = None
    continued = False
    with tempfile.TemporaryDirectory(prefix="nw-login-") as tmp, UInput(
        {e.EV_KEY: [e.BTN_LEFT], e.EV_REL: [e.REL_X, e.REL_Y]}, name="nw-login-click"
    ) as mouse:
        logging.info("INPUT mouse created: nw-login-click")
        image = Path(tmp) / "screen.png"
        while time.monotonic() < deadline:
            time.sleep(2)
            w = window()
            if not w:
                logging.info("WAIT game window; %.0fs remaining", deadline - time.monotonic())
                continue
            logging.info("WINDOW pid=%s position=%s size=%s", w["pid"], w["at"], w["size"])
            if log_offset is not None:
                with GAME_LOG.open("rb") as log:
                    log.seek(log_offset)
                    joined = b"to new state InGame" in log.read()
                if not joined:
                    logging.info("WAIT InGame after Play; no further clicks")
                    continue
            if w["size"] != [1920, 1080]:
                logging.info("WAIT 1920x1080 window; no input")
                continue
            logging.info("FOCUS %s", w["address"])
            subprocess.run(["hyprctl", "dispatch", f'hl.dsp.focus({{window = "address:{w["address"]}"}})'], check=True, timeout=10)
            time.sleep(0.2)
            active = json.loads(subprocess.check_output(["hyprctl", "activewindow", "-j"], timeout=10))
            if active["address"] != w["address"]:
                logging.info("SKIP focus is on %s", active.get("class"))
                continue
            x, y = active["at"]
            subprocess.run(["grim", "-g", f"{x},{y} 1920x1080", str(image)], check=True, timeout=10)
            SCREENSHOT.write_bytes(image.read_bytes())
            logging.info("SCREENSHOT %s", SCREENSHOT)
            if log_offset is not None:
                logging.info("DONE InGame confirmed")
                return
            logging.info("OCR start")
            words = []
            for name, left, top, width, height in (
                ("header", 60, 120, 380, 55),
                ("play", 1595, 910, 140, 45),
                ("continue", 450, 840, 1050, 80),
            ):
                crop = Path(tmp) / f"{name}.png"
                subprocess.run(["magick", str(image), "-crop", f"{width}x{height}+{left}+{top}", "+repage", "-resize", "300%", "-colorspace", "Gray", str(crop)], check=True, timeout=10)
                tsv = subprocess.check_output(["tesseract", str(crop), "stdout", "-l", "eng", "--psm", "6", "tsv"], text=True, timeout=20)
                (SCREENSHOT.parent / f"login-{name}.tsv").write_text(tsv)
                for word in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
                    word["left"] = str(left + int(word["left"]) // 3)
                    word["top"] = str(top + int(word["top"]) // 3)
                    word["width"] = str(int(word["width"]) // 3)
                    word["height"] = str(int(word["height"]) // 3)
                    words.append(word)
            logging.info("OCR text=%r", " ".join(w["text"] for w in words if w["text"].strip()))
            target = button(words)
            if target is None:
                logging.info("SKIP no recognized Continue/Play button")
                continue
            if target == (960, 880) and continued:
                logging.info("SKIP Continue already clicked; waiting for selection")
                continue
            active_now = json.loads(subprocess.check_output(["hyprctl", "activewindow", "-j"], timeout=10))
            if any(active_now[k] != active[k] for k in ("address", "at", "size")):
                logging.info("SKIP window moved or focus changed during OCR")
                continue
            is_play = target != (960, 880)
            if is_play:
                log_offset = GAME_LOG.stat().st_size
            logging.info("CLICK %s local=%s global=%s", "Play" if is_play else "Continue", target, (x + target[0], y + target[1]))
            subprocess.run(["hyprctl", "dispatch", f"hl.dsp.cursor.move({{x = {x + target[0]}, y = {y + target[1]}}})"], check=True, timeout=10)
            mouse.write(e.EV_REL, e.REL_X, 1)
            mouse.syn()
            time.sleep(0.1)
            logging.info("INPUT left button DOWN")
            mouse.write(e.EV_KEY, e.BTN_LEFT, 1)
            mouse.syn()
            time.sleep(0.15)
            mouse.write(e.EV_KEY, e.BTN_LEFT, 0)
            mouse.syn()
            logging.info("INPUT left button UP")
            continued = True
    logging.error("TIMEOUT after 600 seconds; game left open, no further input")
    raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.warning("STOP requested; no further input, game left open")
        raise SystemExit(130)
    except Exception:
        logging.exception("FAILED; no further input, game left open")
        raise SystemExit(1)
