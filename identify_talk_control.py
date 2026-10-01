# -*- coding: utf-8 -*-
"""TALK CONTROL IDENTIFIER - verifies where the Talk button really is.

Camfrog draws most of its controls as CANVAS with NO accessibility name: 82 of
the 83 real Buttons in the room expose an empty name. So there is nothing to
"find by name". This tool instead validates the calibrated coordinate against
the live control tree and reports:

  * whether the calibrated point still lands on a real Button
  * its size, and the pixel drift from the calibrated centre
  * nearby buttons, so a mis-calibration is obvious

Usage:
    python identify_talk_control.py            # report only, changes nothing
    python identify_talk_control.py --apply    # re-centre on the matched button
    python identify_talk_control.py --radius 200
"""
from __future__ import annotations
import sys, json, argparse

BTN_TYPES = {"Button", "CheckBox", "SplitButton", "ToggleButton"}


def attach():
    from pywinauto import Application
    try:
        import psutil
        pids = [p.info["pid"] for p in psutil.process_iter(["pid", "name"])
                if (p.info["name"] or "").lower() == "camfrog video chat.exe"]
        for pid in pids:
            try:
                return Application(backend="uia").connect(process=pid), f"PID {pid}"
            except Exception:
                continue
    except ImportError:
        pass
    for rx in ("(?i).*(Camfrog|Players__Lounge).*",):
        try:
            return Application(backend="uia").connect(title_re=rx), f"title {rx}"
        except Exception:
            continue
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--radius", type=int, default=140)
    args = ap.parse_args()

    try:
        app, how = attach()
    except ImportError:
        print("pywinauto is required: pip install pywinauto")
        return 2
    if app is None:
        print("Could not attach to Camfrog.")
        print("Is 'Camfrog Video Chat.exe' running and NOT minimized?")
        return 3

    win = app.top_window()
    wr = win.rectangle()
    print(f"Attached via {how}")
    print(f"Window: {wr.left},{wr.top}  {wr.width()}x{wr.height()}  "
          f"title={win.window_text()[:50]!r}\n")

    try:
        coords = json.load(open("camfrog_coords.json", encoding="utf-8"))
    except Exception:
        coords = {}
    tb = coords.get("talk_button") if isinstance(coords.get("talk_button"), dict) else {}
    tx, ty = tb.get("x"), tb.get("y")
    if not isinstance(tx, int) or not isinstance(ty, int):
        tx, ty = 1480, 600
        print("No calibrated talk_button found; using the built-in fallback (1480, 600).")
    print(f"Calibrated talk_button: ({tx}, {ty})\n")

    named = unnamed = near = 0
    nearby = []
    matched = None
    best = None
    for c in win.descendants():
        try:
            if (c.element_info.control_type or "") not in BTN_TYPES:
                continue
            r = c.rectangle()
            if r.width() <= 0 or r.height() <= 0:
                continue
            name = (c.element_info.name or "").strip()
            if name:
                named += 1
            else:
                unnamed += 1
            cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
            d = ((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5
            if d <= args.radius:
                nearby.append((d, r, name))
            if d < 30 and (best is None or d < best[0]):
                best = (d, r, name)
        except Exception:
            continue

    print(f"Buttons with an accessible NAME : {named}")
    print(f"Buttons WITHOUT any name        : {unnamed}")
    if named == 0:
        print("  -> Camfrog exposes no names; the calibrated coordinate is the")
        print("     only reliable handle, and must be re-validated by geometry.\n")

    if not nearby:
        print(f"NO button within {args.radius}px of ({tx}, {ty}).")
        print("The Talk button has almost certainly MOVED. Re-run calibrate_camfrog.py,")
        print("or drag the window, then re-run this tool.")
        return 1

    nearby.sort(key=lambda t: t[0])
    print(f"\nButtons within {args.radius}px of the calibrated point:")
    print(f"  {'dist':>5}  {'rect':<22} {'w x h':<9} name")
    print("  " + "-" * 62)
    for d, r, name in nearby[:8]:
        print(f"  {d:5.0f}  {r.left},{r.top} {r.width()}x{r.height():<6} "
              f"{(name[:22] if name else '(unnamed)')}")

    matched = best
    if matched is None:
        print("\nNo button is within 30px of the calibrated point -> CALIBRATION IS STALE.")
        d, r, name = nearby[0]
        print(f"Closest is {d:.0f}px away at ({r.left},{r.top}) {r.width()}x{r.height()}.")
        if args.apply:
            cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
            coords["talk_button"] = {"x": int(cx), "y": int(cy)}
            json.dump(coords, open("camfrog_coords.json", "w", encoding="utf-8"), indent=4)
            print(f"APPLIED: talk_button -> ({int(cx)}, {int(cy)})")
        else:
            print("Re-run with --apply to re-centre on it.")
        return 1

    d, r, name = matched
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    print(f"\nVALID: calibrated point sits on a real button.")
    print(f"  button rect : {r.left},{r.top} {r.width()}x{r.height()}")
    print(f"  its centre  : ({cx}, {cy})")
    print(f"  drift       : {cx - tx:+d}, {cy - ty:+d} px  (distance {d:.0f}px)")
    print(f"  name        : {name if name else '(unnamed - expected for Camfrog)'}")
    print(f"  hit area    : {r.width() * r.height()} px^2")

    if d <= 12:
        print("\nVERDICT: calibration is GOOD - the press will land on this button.")
        return 0
    print("\nVERDICT: usable, but off-centre. A 12px+ drift risks missing the button.")
    if args.apply:
        coords["talk_button"] = {"x": int(cx), "y": int(cy)}
        json.dump(coords, open("camfrog_coords.json", "w", encoding="utf-8"), indent=4)
        print(f"APPLIED: talk_button -> ({int(cx)}, {int(cy)})")
    else:
        print("Re-run with --apply to re-centre on the true centre.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
