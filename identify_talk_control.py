# -*- coding: utf-8 -*-
"""TALK CONTROL IDENTIFIER - finds Camfrog's real talk/mic control(s).

The grab code presses a CALIBRATED coordinate (camfrog_coords.json). If that
value drifts, presses land on empty space and the grab silently fails. This tool
inspects the live CEF/UIA tree, scores every candidate control, and can WRITE the
winning coordinate back into camfrog_coords.json.

Usage:
    python identify_talk_control.py            # report only, changes nothing
    python identify_talk_control.py --apply    # write the winner to coords
    python identify_talk_control.py --top 10
"""
from __future__ import annotations
import sys, json, argparse, os

TALK_WORDS = ("talk", "mic", "microphone", "push", "ptt", "transmit", "speak", "hold")
MUTE_WORDS = ("mute", "unmute", "deafen", "speaker", "volume")
DROP_WORDS = ("dropdown", "arrow", "menu", "more options", "settings", "gear",
              "close", "minimize", "maximize", "help", "about", "chat", "send",
              "smile", "emoticon", "avatar", "add friend", "invite")


def score(name: str, ctype: str) -> tuple:
    low = (name or "").lower().strip()
    if not low:
        return (0, "unnamed")
    if any(w in low for w in DROP_WORDS):
        return (0, "excluded: dropdown/adjacent control")
    for w in MUTE_WORDS:
        if w in low:
            return (0, f"excluded: mute/speaker word '{w}'")
    hits = [w for w in TALK_WORDS if w in low]
    if hits:
        base = 60 + 10 * len(hits)
        if ctype.lower() in ("button", "checkbox"):
            base += 25
        if ctype.lower() in ("group", "pane", "custom"):
            base -= 15
        return (base, f"talk words {hits}, type={ctype}")
    return (0, "no talk keyword")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write winner into camfrog_coords.json")
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args()

    try:
        from pywinauto import Application
    except ImportError:
        print("pywinauto is required: pip install pywinauto")
        return 2

    app = None
    for kw in ({"process": None}, {"title_re": "(?i).*(Camfrog|Players__Lounge).*"}):
        try:
            if kw.get("process") is None:
                app = Application(backend="uia").connect(title_re=kw["title_re"])
            break
        except Exception:
            app = None
    if app is None:
        try:
            app = Application(backend="uia").connect(title_re="(?i).*Camfrog.*")
        except Exception as e:
            print(f"Could not attach to Camfrog: {e}")
            print("Is Camfrog OPEN and not minimized?")
            return 3

    try:
        win = app.top_window()
    except Exception:
        win = app.windows()[0]

    try:
        rect = win.rectangle()
        print(f"Camfrog window: {rect.left},{rect.top} {rect.width()}x{rect.height()}")
    except Exception:
        rect = None

    print("Scanning controls...\n")
    rows = []
    try:
        for i, ctrl in enumerate(win.descendants(), 1):
            try:
                ctype = ctrl.element_info.control_type or "?"
                name = (ctrl.element_info.name or "").strip()
                r = ctrl.rectangle()
            except Exception:
                continue
            s, why = score(name, ctype)
            if s > 0:
                rows.append((s, ctype, name, r, why))
    except Exception as e:
        print(f"Scan failed: {e}")
        return 3

    rows.sort(key=lambda t: -t[0])
    if not rows:
        print("NO talk-like control found in the accessibility tree.")
        print("Camfrog's talk button may be canvas-drawn with no UIA name.")
        print("Fallback: the calibrated coordinate in camfrog_coords.json is used.")
        return 1

    print(f"{'score':>5}  {'type':<10} {'name':<34} {'screen rect':<28} why")
    print("-" * 108)
    for s, ctype, name, r, why in rows[: args.top]:
        rect_s = f"{r.left},{r.top} {r.width()}x{r.height()}"
        print(f"{s:>5}  {ctype:<10} {name[:34]:<34} {rect_s:<28} {why}")

    best = rows[0]
    _, _, bname, brect, _ = best
    cx, cy = (brect.left + brect.right) // 2, (brect.top + brect.bottom) // 2
    print(f"\nBEST: {bname!r} -> center ({cx}, {cy})")

    cur = {}
    try:
        cur = json.load(open("camfrog_coords.json", encoding="utf-8"))
    except Exception:
        pass
    old = (cur.get("talk_button") or {}) if isinstance(cur.get("talk_button"), dict) else {}
    print(f"CURRENT calibrated: ({old.get('x')}, {old.get('y')})")
    if old.get("x") == cx and old.get("y") == cy:
        print("MATCH: calibrated coordinates already point at the best control.")
        return 0

    drift = ""
    if isinstance(old.get("x"), int):
        drift = f"  (drift {cx - old['x']:+d},{cy - old['y']:+d} px)"
    print(f"MISMATCH: calibrated coordinates are off.{drift}")

    if args.apply:
        cur["talk_button"] = {"x": int(cx), "y": int(cy)}
        with open("camfrog_coords.json", "w", encoding="utf-8") as f:
            json.dump(cur, f, indent=4)
        print(f"APPLIED: camfrog_coords.json talk_button -> ({int(cx)}, {int(cy)})")
    else:
        print("Run with --apply to write this into camfrog_coords.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
