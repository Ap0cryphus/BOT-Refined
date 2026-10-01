"""Test whether the bot can win a mic by OUTLASTING a continuous human hold.

Established in a single-mic room: clicking cannot take a mic from somebody who
is continuously holding it (39 presses / 10s, zero wins). Camfrog gives a human
a long transmit timer and then drops them, so the only remaining route to a win
is to stay silent, wait for the human's timer to expire, and strike the instant
the bubble clears.

This proves or disproves that. It deliberately does NOT press while the human
holds - any early press just gives the human the mic back.

Run:  python mic_outlast.py
"""
import sys
import time
import threading
import statistics

try:
    import cef_probe as cp
except ImportError as e:
    print("cannot import cef_probe: %s" % e)
    sys.exit(2)


def median(vals):
    return statistics.median(vals) if vals else None


def fmt(v):
    return round(v, 1) if v is not None else "n/a"


def main():
    tc = cp.global_talk_controller
    cp.global_probe.start_probe_daemon()
    time.sleep(1.5)
    attach = tc.catch_talk_process() or {}
    if not attach.get("attached"):
        print("probe not attached to a Camfrog room window")
        return 1
    dev = cp.get_configured_output_device()
    print("=" * 70)
    print("MIC OUTLAST TEST - single-mic room")
    print("=" * 70)
    print("  attach=%s coords=%s device=%s" % (
        attach.get("attached"), attach.get("talk_coords"), dev))

    hold_window = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0

    print("\n  PHASE A - ADMIN: hold your mic and speak continuously.")
    print("  The bot will NOT press. It is waiting for your timer to run out.")
    print("  Keep going as long as you can (window: %.0fs)." % hold_window)

    rows = []
    t0 = time.time()
    released_at = None
    while time.time() - t0 < hold_window:
        name = tc.read_speaker_name()
        flow = tc.read_audio_flow()
        rows.append((round(time.time() - t0, 1),
                     round(flow, 1) if flow else None, name))
        if name and not cp.is_bot_name_strict(name):
            pass
        elif not name:
            if released_at is None and time.time() - t0 > 3:
                released_at = time.time() - t0
                print("\n    bubble cleared at t=%.1fs - striking NOW" % released_at)
                break
        time.sleep(0.15)

    humans = [n for _t, _f, n in rows if n and not cp.is_bot_name_strict(n)]
    flows = [f for _t, f, _n in rows if f is not None]
    print("\n  PHASE A result")
    print("    samples      = %d over %.1fs" % (len(rows), time.time() - t0))
    print("    flow median  = %s" % fmt(median(flows)))
    print("    human lead   = %s" % (max(set(humans), key=humans.count)
                                     if humans else None))
    print("    bot pressed  = NO (correct - never fought a live hold)")

    if released_at is None:
        print("\n  The admin held for the whole window, so the bot never got a")
        print("  free mic to take. Cannot test outlasting until the timer lapses.")
        return 2

    # ---- strike the instant the bubble clears --------------------------
    print("\n  PHASE B - striking: audio FIRST, then press-and-hold")
    cp.synthesize_speech_to_wav(
        "KaeKae here. The floor is mine now.",
        "temp_say_broadcast.wav", voice="en-US-AvaNeural",
        rate="+10%", pitch="+16Hz", persona="valley")

    stop = threading.Event()

    def _loop():
        while not stop.is_set():
            try:
                cp.play_wav_to_virtual_cable("temp_say_broadcast.wav", dev)
            except Exception:
                break

    threading.Thread(target=_loop, daemon=True).start()
    time.sleep(0.35)
    tc.fast_press_hold()

    b = []
    tb = time.time()
    while time.time() - tb < 8.0:
        nm = tc.read_speaker_name()
        f = tc.read_audio_flow()
        b.append((round(time.time() - tb, 2), round(f, 1) if f else None, nm))
        time.sleep(0.12)
    stop.set()
    tc.release_mic()

    names = [n for _t, _f, n in b if n]
    owned = [n for n in names if cp.is_bot_name_strict(n)]
    frac = len(owned) / float(len(names)) if names else 0.0
    print("\n  PHASE B result")
    for t, f, nm in b:
        mark = "  <== OURS" if cp.is_bot_name_strict(nm) else ""
        print("    t=%.1fs flow=%-6s name=%r%s" % (t, f, nm, mark))
    print("\n    owned %d/%d samples (%.0f%%)" % (
        len(owned), len(names), frac * 100))
    if frac >= 0.6:
        print("\n  RESULT: OUTLASTING WORKS - the bot took the mic cleanly.")
        return 0
    print("\n  RESULT: outlasting FAILED - the bot could not take the mic even")
    print("  after the human's bubble cleared.")
    return 1


if __name__ == "__main__":
    sys.exit(main())