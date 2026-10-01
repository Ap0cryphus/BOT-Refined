# -*- coding: utf-8 -*-
"""MIC GRAB TEST - grabs the Camfrog talk button, speaks, releases.

The real failure mode is a mic battle: someone is mid-sentence, the first press
does not stick, and a broadcast either interrupts them or is lost. This tool
presses the talk control REPEATEDLY until the grab sticks (or the attempt
budget runs out), speaks the phrase, then releases cleanly.

Usage:
    python mic_grab_test.py                       # default phrase, 12 attempts
    python mic_grab_test.py --phrase "hello"      # custom phrase
    python mic_grab_test.py --attempts 20 --wait 30
    python mic_grab_test.py --no-audio            # press/release only, stay silent
"""
from __future__ import annotations
import argparse, json, sys, time

sys.path.insert(0, __file__.rsplit("\\", 1)[0])

DEFAULT_PHRASE = "Hello motherfuckers"


def log(msg: str) -> None:
    print(f"[GRAB TEST] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phrase", default=DEFAULT_PHRASE)
    ap.add_argument("--attempts", type=int, default=12)
    ap.add_argument("--wait", type=float, default=20.0,
                    help="seconds to keep retrying the grab")
    ap.add_argument("--gap", type=float, default=0.12)
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--voice", default="en-US-AvaNeural")
    args = ap.parse_args()

    try:
        import cef_probe as cp
    except ImportError as e:
        log(f"cannot import cef_probe: {e}")
        return 2

    tc = cp.global_talk_controller
    cp.global_probe.start_probe_daemon()
    time.sleep(2.0)

    info = tc.catch_talk_process()
    log(f"attach={info.get('attached')} coords={tc.get_talk_coordinates()} "
        f"ctrl={'yes' if tc.talk_button_ctrl else 'no'} "
        f"cef_hwnd={tc.cef_render_hwnd}")
    if not tc.talk_button_ctrl:
        log("WARNING: no UIA talk control found; falling back to coordinate press.")

    held = False
    method = ""
    start = time.time()
    tries = 0
    # Keep re-pressing until the hold sticks. uia first: it is the only strategy
    # observed to actually open the mic on a canvas-drawn button.
    order = ("uia", "mouse_hold", "cef_hwnd", "f10")
    while tries < args.attempts and time.time() - start < args.wait:
        tries += 1
        pattern = order[(tries - 1) % len(order)]
        try:
            if held:
                tc._quick_release()
                time.sleep(args.gap)
            ok = tc._press_pattern(pattern)
        except Exception as e:
            log(f"press {pattern} raised {e}")
            ok = False
        if ok and getattr(tc, "is_holding", False):
            held = True
            method = tc.active_method
            spk = ""
            try:
                spk = cp.global_probe.get_speaker()
            except Exception:
                pass
            log(f"attempt {tries}: {pattern} -> HELD via {method} (speaker={spk!r})")
            # Re-press once more to be sure the hold is stable before speaking.
            time.sleep(0.15)
            tc._press_pattern("uia" if tc.talk_button_ctrl else "mouse_hold")
            time.sleep(0.15)
            break
        log(f"attempt {tries}: {pattern} -> not held")
        time.sleep(args.gap)

    result = {
        "held": held, "method": method, "tries": tries,
        "coords": tc.get_talk_coordinates(),
        "phrase": "" if args.no_audio else args.phrase,
    }

    if not held:
        log("GRAB FAILED - mic never stuck. Releasing any partial hold.")
        tc.release_mic()
        result["ok"] = False
        print(json.dumps(result, indent=1))
        return 1

    log(f"GRAB OK via {method} after {tries} attempt(s); mic is open.")

    if not args.no_audio:
        try:
            engine = cp.synthesize_speech_to_wav(args.phrase, "temp_say_broadcast.wav",
                                                 voice=args.voice, rate="+12%",
                                                 pitch="+16Hz", persona="valley")
            log(f"TTS engine={engine}")
            if engine:
                dev = cp.get_configured_output_device()
                time.sleep(0.18)
                played = cp.play_wav_to_virtual_cable("temp_say_broadcast.wav", dev)
                result["playback_ok"] = bool(played)
                log(f"playback_ok={played} via {dev}")
            else:
                result["playback_ok"] = False
                log("TTS failed - mic is held but nothing will play.")
        except Exception as e:
            result["playback_ok"] = False
            log(f"audio error: {e}")
        finally:
            time.sleep(0.3)

    log("releasing mic...")
    released = tc.release_mic()
    result["released"] = bool(released)
    result["ok"] = True
    log(f"released={released}, holding now={getattr(tc, 'is_holding', False)}")

    if cp._core is not None:
        try:
            cp._core.log_event("talk", action="grab_test", **{
                k: str(v) for k, v in result.items()})
        except Exception:
            pass

    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
