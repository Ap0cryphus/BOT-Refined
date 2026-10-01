# -*- coding: utf-8 -*-
"""TALK WATCH - records everything that changes while Talk is held.

Camfrog does not expose the active-speaker label, so the bot has no reliable
"is my mic open?" signal. This tool answers that empirically: it snapshots the
CEF accessibility tree, the Talk button's UIA properties, and the button's pixel
signature on every poll, and writes every CHANGE to a JSONL file.

How to use:
  1. python talk_watch.py --seconds 45        (starts sampling)
  2. Manually HOLD the Talk button ~5s, release, wait, hold again ~5s
  3. Stop it.  Read logs/talkwatch_<date>.jsonl for what changed.

Whatever moves while the button is held IS the signal the bot should verify on.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TYPES = {"Text", "Hyperlink", "ListItem", "Edit", "Document", "Pane", "Custom"}


def _dim(v):
    """pywinauto RECT exposes width()/height() as METHODS on some backends and as
    plain attributes on others. Normalise both to an int."""
    return v() if callable(v) else v


def pixelsig(pyautogui, rect, pad=2, retries=3):
    """Mean luminance + hash of the Talk button region.

    The first grab can fail transiently (screen still waking / DPI settle), which
    silently produced baseline=None and made every later comparison useless - so
    retry before giving up."""
    region = (int(rect.left) - pad, int(rect.top) - pad,
              int(_dim(rect.width)) + pad * 2, int(_dim(rect.height)) + pad * 2)
    for i in range(retries):
        try:
            im = pyautogui.screenshot(region=region)
            g = im.convert("L")
            px = list(g.getdata())
            return round(sum(px) / len(px), 2), hashlib.md5(bytes(px)).hexdigest()[:12]
        except Exception:
            time.sleep(0.25)
    return None, None


def treesig(win):
    """Map of visible text -> rect, for diffing."""
    out = {}
    try:
        for c in win.descendants():
            try:
                if (c.element_info.control_type or "") not in TYPES:
                    continue
                t = (c.element_info.name or "").strip()
                if not t:
                    continue
                r = c.rectangle()
                if r.width() <= 0:
                    continue
                out[t] = (r.left, r.top, r.width(), r.height())
            except Exception:
                continue
    except Exception:
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=45.0)
    ap.add_argument("--poll", type=float, default=0.10)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    try:
        import cef_probe as cp
    except ImportError as e:
        print("import cef_probe failed:", e)
        return 2
    try:
        import pyautogui
    except ImportError:
        print("pyautogui required")
        return 2

    tc = cp.global_talk_controller
    cp.global_probe.start_probe_daemon()
    time.sleep(1.5)
    info = tc.catch_talk_process()
    if not tc.talk_button_ctrl:
        print("No Talk control found:", info)
        return 3

    ctrl = tc.talk_button_ctrl
    rect = ctrl.rectangle()
    print(f"Talk button: name={ctrl.element_info.name!r} "
          f"class={ctrl.element_info.class_name!r} "
          f"auto_id={ctrl.element_info.automation_id!r}")
    print(f"rect={rect.left},{rect.top} {_dim(rect.width)}x{_dim(rect.height)}")
    print(f"Sampling for {args.seconds:.0f}s at {args.poll:.2f}s.")
    print(">>> HOLD the Talk button for ~5s, release, then hold again.\n")

    from pywinauto import Application
    win = None
    try:
        pid = cp.global_probe.main_pid or (cp.global_probe.cef_pids or [None])[0]
        if pid:
            win = Application(backend="uia").connect(process=pid).top_window()
    except Exception as e:
        print("tree watch unavailable:", e)

    outfile = args.out or os.path.join("logs", f"talkwatch_{datetime.now():%Y%m%d}.jsonl")
    os.makedirs("logs", exist_ok=True)

    t0 = time.time()

    def emit(rec):
        rec["t"] = round(time.time() - t0, 3)
        rec.setdefault("wall", datetime.now().strftime("%H:%M:%S.%f")[:-3])
        with open(outfile, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    base_tree = treesig(win) if win else {}
    base_avg, base_hash = pixelsig(pyautogui, rect)
    emit({"kind": "baseline", "node_count": len(base_tree),
          "pix_avg": base_avg, "pix_hash": base_hash,
          "uia_name": ctrl.element_info.name,
          "uia_enabled": bool(ctrl.is_enabled()),
          "uia_visible": bool(ctrl.is_visible())})
    print(f"baseline: {len(base_tree)} nodes, pixel avg={base_avg} hash={base_hash}")

    prev_tree = dict(base_tree)
    prev_pix = (base_avg, base_hash)
    n = 0
    while time.time() - t0 < args.seconds:
        time.sleep(args.poll)
        n += 1
        el = time.time() - t0
        try:
            cur_name = ctrl.element_info.name
            cur_en = bool(ctrl.is_enabled())
            cur_vis = bool(ctrl.is_visible())
            r2 = ctrl.rectangle()
            geom = (int(r2.left), int(r2.top), int(_dim(r2.width)), int(_dim(r2.height)))
        except Exception:
            cur_name, cur_en, cur_vis, geom = None, None, None, None

        avg, h = pixelsig(pyautogui, rect)
        pix_changed = (h != prev_pix[1])
        dark = (avg is not None and base_avg is not None and avg < base_avg - 8)

        tree = treesig(win) if win else {}
        new = {k: v for k, v in tree.items() if k not in prev_tree}
        gone = {k: v for k, v in prev_tree.items() if k not in tree}

        if pix_changed or new or gone or cur_name != "Talk " or geom != (int(rect.left), int(rect.top), int(_dim(rect.width)), int(_dim(rect.height))):
            emit({"kind": "change", "t": el, "pix_avg": avg, "pix_hash": h,
                  "pix_changed": pix_changed, "darker_than_idle": dark,
                  "uia_name": cur_name, "uia_enabled": cur_en, "uia_visible": cur_vis,
                  "uia_geom": geom,
                  "new_text": list(new.keys())[:8], "gone_text": list(gone.keys())[:8]})
            if dark:
                print(f"  [{el:5.1f}s] DARK  avg={avg}  <- talk likely OPEN "
                      f"new={list(new.keys())[:2]}")

        prev_tree = tree
        prev_pix = (avg, h)

    emit({"kind": "end", "polls": n})
    print(f"\nDone. {n} polls -> {outfile}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
