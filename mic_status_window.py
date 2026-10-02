# -*- coding: utf-8 -*-
"""MIC STATUS WINDOW - live view of the Camfrog talk strip via dxcam.

Shows, updating ~10x/sec:
  * the talk button strip (calibrated, so a layout move is obvious at a glance)
  * the green audio-flow icon and its measured value
  * the active-speaker bubble and whether the bot owns the mic
  * the current mic state (free / busy / ours / unconfirmable)

This is a DIAGNOSTIC view. It does not make the grab faster: the contest loop is
gated by press cadence (flood safety), and the flow read is only ~4% of a loop
unit. dxcam captures ~900x faster than pyautogui, which matters for smoothness
here, not for winning the mic.

Usage:
    python mic_status_window.py
    python mic_status_window.py --fps 5
"""
from __future__ import annotations
import argparse, os, sys, threading, time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_cam():
    try:
        import dxcam
        return dxcam.create(output_color="RGB")
    except Exception as e:
        print("dxcam unavailable (%s) - falling back to pyautogui" % e)
        return None


def grab(cam, box):
    """box=(l,t,w,h) -> numpy RGB array, or None."""
    l, t, w, h = box
    if cam is not None:
        try:
            return cam.grab(region=(l, t, l + w, t + h))
        except Exception:
            return None
    try:
        import numpy as np, pyautogui
        return np.asarray(pyautogui.screenshot(region=(l, t, w, h)).convert("RGB"))
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--pad", type=int, default=60,
                    help="pixels of context shown around the talk strip")
    args = ap.parse_args()

    try:
        import cef_probe as cp
    except ImportError as e:
        print("import cef_probe failed:", e)
        return 2

    tc = cp.global_talk_controller
    try:
        cp.global_probe.start_probe_daemon()
    except Exception:
        pass
    time.sleep(1.0)
    try:
        tc.catch_talk_process()
    except Exception:
        pass

    coords = tc.coords or {}
    tb = coords.get("talk_button") or {"x": 1326, "y": 1182}
    flow = coords.get("audio_flow_region") or {"left": tb["x"], "top": tb["y"] - 17,
                                              "width": 96, "height": 34}
    bubble = coords.get("active_speaker_ocr_region") or {"left": flow["left"],
                                                       "top": flow["top"], "width": 180,
                                                       "height": 28}
    l = min(tb["x"], flow["left"], bubble["left"]) - args.pad
    r = max(tb["x"], flow["left"] + flow["width"], bubble["left"] + bubble["width"]) + args.pad
    t = min(tb["y"], flow["top"], bubble["top"]) - args.pad
    bo = max(tb["y"], flow["top"] + flow["height"], bubble["top"] + bubble["height"]) + args.pad
    box = (int(l), int(t), int(r - l), int(bo - t))

    # Share the single permitted dxcam instance rather than creating another:
    # dxcam allows one per output and a second create() silently breaks both.
    import live_capture as _lc
    cap = _lc.shared()
    root = tk.Tk()
    root.title("KaeKae - live mic status")
    root.configure(bg="#101014")
    root.resizable(False, False)
    scale = 3
    img_lbl = tk.Label(root, bd=0, highlightthickness=1, highlightbackground="#2a2a33")
    img_lbl.pack(padx=8, pady=(8, 4))
    info = tk.Label(root, text="starting...", justify="left", anchor="w",
                    bg="#101014", fg="#d8d8e0", font=("Consolas", 10))
    info.pack(padx=10, pady=(0, 8), fill="x")

    state = {"frames": 0, "fps": 0.0, "last": time.time(), "cam": cap.backend}
    stop = threading.Event()

    from PIL import Image, ImageTk

    def tick():
        if stop.is_set():
            return
        cap.refresh()
        arr = cap.region(box)
        if arr is not None:
            try:
                im = Image.fromarray(arr)
                im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
                photo = ImageTk.PhotoImage(im)
                img_lbl.configure(image=photo)
                img_lbl.image = photo
            except Exception:
                pass
        # textual state (uses cef_probe's own calibrated readers)
        try:
            name = tc.read_speaker_name()
            owned = cp.is_bot_name_strict(name) if name else False
        except Exception:
            name, owned = "(unreadable)", False
        try:
            red = tc.read_audio_flow()
        except Exception:
            red = None
        try:
            st = tc.mic_state_tuple()[0]
        except Exception:
            st = "?"
        now = time.time()
        dt = now - state["last"]
        state["last"] = now
        if dt > 0:
            state["fps"] = state["fps"] * 0.8 + (1.0 / dt) * 0.2
        state["frames"] += 1
        colour = "#7dffa0" if owned else ("#d8d8e0" if name else "#6a6a76")
        info.configure(text=(
            "capture : %s   %5.1f fps   frame %d\n"
            "strip   : x%d..%d  y%d..%d\n"
            "button  : (%d, %d)\n"
            "flow    : %s%s\n"
            "speaker : %s\n"
            "state   : %s%s"
        ) % (
            state["cam"], state["fps"], state["frames"],
            box[0], box[0] + box[2], box[1], box[1] + box[3],
            tb["x"], tb["y"],
            ("n/a" if red is None else "%.1f" % red),
            "  (below threshold)" if red is not None and red < tc._flow_red_threshold else "",
            (name or "(none)"),
            st,
            "   <-- WE OWN IT" if owned else "",
        ), fg=colour)
        root.after(max(20, int(1000 / max(1.0, args.fps))), tick)

    print("status window running. Close the window or press Ctrl+C to stop.")
    root.after(300, tick)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        try:
            cap.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
