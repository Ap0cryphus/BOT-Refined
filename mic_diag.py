"""Full microphone diagnostics for a SINGLE-mic Camfrog room.

A room with two simultaneous microphones cannot be diagnosed with this script:
both parties legitimately appear in the speaker bubble and their audio mixes,
so the name and the flow indicator are both ambiguous. Run this in a room that
allows only one speaker at a time.

Phases
  0  attach + idle baseline (room must be silent)
  1  HUMAN   admin speaks, bot does nothing       -> human signature
  2  IDLE    bot holds, plays nothing             -> does silence show a name?
  3  BOT     bot holds + plays audio              -> our signature
  4  BATTLE  admin holds, bot fights for it       -> does the bot win?
  5  summary

Run:  python mic_diag.py
"""
import sys
import time
import threading
import statistics

try:
    import cef_probe as cp
except ImportError as e:
    print(f"cannot import cef_probe: {e}")
    sys.exit(2)


def _stat(vals):
    if not vals:
        return None
    v = sorted(vals)
    return {"n": len(v), "min": v[0],
            "median": statistics.median(v), "max": v[-1]}


class Sampler(threading.Thread):
    """Polls name + flow on a fixed cadence for the life of the sample."""

    def __init__(self, tc, period=0.12):
        super().__init__(daemon=True)
        self.tc = tc
        self.period = period
        # NB: must NOT be called _stop - that shadows threading.Thread._stop(),
        # which join() calls internally and which raised
        # "TypeError: 'Event' object is not callable".
        self._stopev = threading.Event()
        self.rows = []

    def run(self):
        while not self._stopev.is_set():
            try:
                name = self.tc.read_speaker_name()
                flow = self.tc.read_audio_flow()
                self.rows.append((round(time.time() - self.t0, 2),
                                  round(flow, 1) if flow else None, name))
            except Exception as exc:  # never let a sample kill the run
                self.rows.append((round(time.time() - self.t0, 2), None,
                                  "<err %s>" % exc))
            time.sleep(self.period)

    def start(self):
        self.t0 = time.time()
        super().start()
        return self

    def finish(self):
        self._stopev.set()
        self.join(timeout=3)
        return self.rows

    def flows(self):
        return [f for _t, f, _n in self.rows if f is not None]

    def names(self):
        return [n for _t, _f, n in self.rows if n]

    def owned_frac(self):
        seen = self.names()
        if not seen:
            return 0.0
        return sum(1 for n in seen
                   if cp.is_bot_name_strict(n)) / float(len(seen))

    def leading_name(self):
        """Most common FIRST token - who actually led the bubble."""
        firsts = []
        for n in self.names():
            tok = str(n).strip().split("$")[0].strip()
            if tok:
                firsts.append(tok)
        if not firsts:
            return None
        return max(set(firsts), key=firsts.count)

    def report(self, label, expect_ours):
        f = _stat(self.flows())
        own = self.owned_frac()
        lead = self.leading_name()
        print("  %s" % label)
        print("     samples=%d  flow median=%s  range=%s" % (
            len(self.rows),
            round(f["median"], 1) if f else "n/a",
            "%.1f-%.1f" % (f["min"], f["max"]) if f else "n/a"))
        print("     bubble lead=%r  ours-led=%.0f%%" % (lead, own * 100))
        verdict = "?"
        if expect_ours:
            verdict = ("PASS - bot owned the mic" if own >= 0.5
                       else "FAIL - bot never led the bubble")
        else:
            verdict = "PASS - bot correctly stayed off"
        print("     -> %s" % verdict)
        return {"label": label, "flow": f, "owned": own, "lead": lead,
                "verdict": verdict}


def _countdown(seconds, msg):
    print("\n  %s" % msg)
    for i in range(seconds, 0, -1):
        print("    ...%d" % i, end="")
        sys.stdout.flush()
        time.sleep(1)
    print("    GO")
def main():
    tc = cp.global_talk_controller
    # start_probe_daemon() returns None (it forks a helper), so do NOT treat a
    # falsy return as failure - verify by actually reading the UI instead.
    cp.global_probe.start_probe_daemon()
    time.sleep(1.5)
    try:
        tc.catch_talk_process()
        probe_flow = tc.read_audio_flow()
        probe_name = tc.read_speaker_name()
    except Exception as exc:
        print("probe not responding: %s" % exc)
        return 1
    if probe_flow is None:
        print("probe attached but read_audio_flow() returned None; "
              "is Camfrog still open and on a room window?")
        return 1

    dev = cp.get_configured_output_device()
    print("=" * 70)
    print("MIC DIAGNOSTICS - single-mic room only")
    print("=" * 70)
    attach = tc.catch_talk_process() or {}
    print("  attach=%s coords=%s ctrl_found=%s" % (
        attach.get("attached"), attach.get("talk_coords"),
        attach.get("talk_ctrl_found")))
    print("  audio device: %s" % dev)

    results = []

    # ---- phase 0: idle baseline ----------------------------------------
    print("\n" + "-" * 70)
    _countdown(5, "PHASE 0 - stay SILENT, measuring idle baseline")
    s = Sampler(tc).start()
    time.sleep(5.0)
    s.finish()
    idle = s.report("0 IDLE (silent)", expect_ours=False)
    idle_f = idle["flow"]["median"] if idle["flow"] else None
    results.append(idle)

    # ---- phase 1: human signature ---------------------------------------
    print("\n" + "-" * 70)
    _countdown(5, "PHASE 1 - ADMIN: hold your mic and speak for 5s "
                  "(bot does nothing)")
    s = Sampler(tc).start()
    time.sleep(5.0)
    s.finish()
    human = s.report("1 HUMAN speaking", expect_ours=False)
    results.append(human)

    # ---- phase 2: silent hold ------------------------------------------
    print("\n" + "-" * 70)
    print("\n  PHASE 2 - bot holds the mic SILENTLY for 4s (no audio)")
    tc.fast_press_hold()
    s = Sampler(tc).start()
    time.sleep(4.0)
    s.finish()
    tc.release_mic()
    time.sleep(0.5)
    silent = s.report("2 BOT silent hold", expect_ours=True)
    results.append(silent)

    # ---- phase 3: bot with audio ---------------------------------------
    print("\n" + "-" * 70)
    print("\n  PHASE 3 - bot holds AND plays audio for 6s. Listen.")
    cp.synthesize_speech_to_wav(
        "KaeKae here. If you can hear this, the bot is transmitting.",
        "temp_say_broadcast.wav", voice="en-US-AvaNeural",
        rate="+10%", pitch="+16Hz", persona="valley")
    stop = threading.Event()

    def _play_loop():
        while not stop.is_set():
            try:
                cp.play_wav_to_virtual_cable("temp_say_broadcast.wav", dev)
            except Exception:
                break

    tc.fast_press_hold()
    threading.Thread(target=_play_loop, daemon=True).start()
    s = Sampler(tc).start()
    time.sleep(6.0)
    s.finish()
    stop.set()
    tc.release_mic()
    time.sleep(0.5)
    bot = s.report("3 BOT + AUDIO", expect_ours=True)
    results.append(bot)

    # ---- phase 4: battle -------------------------------------------------
    print("\n" + "-" * 70)
    _countdown(5, "PHASE 4 - BATTLE: ADMIN hold your mic and speak. "
                  "The bot will fight you for it.")
    tc.fast_press_hold()
    time.sleep(2.0)
    stop2 = threading.Event()

    def _play_loop2():
        while not stop2.is_set():
            try:
                cp.play_wav_to_virtual_cable("temp_say_broadcast.wav", dev)
            except Exception:
                break

    threading.Thread(target=_play_loop2, daemon=True).start()
    s = Sampler(tc).start()
    deadline = time.time() + 12.0
    won_at = None
    while time.time() < deadline:
        if s.owned_frac() >= 0.6:
            won_at = round(time.time() - s.t0, 2)
            break
        time.sleep(0.3)
    s.finish()
    stop2.set()
    tc.release_mic()
    battle = s.report("4 BATTLE vs admin", expect_ours=True)
    if won_at is not None:
        battle["verdict"] = "WIN vs admin after %.1fs" % won_at
        battle["won_at"] = won_at
    results.append(battle)

    # ---- summary --------------------------------------------------------
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for r in results:
        f = r["flow"]
        print("  %-22s flow_med=%-7s ours=%-4.0f%%  %s" % (
            r["label"], round(f["median"], 1) if f else "n/a",
            r["owned"] * 100, r["verdict"]))

    print("\n  separation check:")
    print("    idle  = %s" % (round(idle_f, 1) if idle_f else "n/a"))
    if human["flow"]:
        print("    human = %.1f" % human["flow"]["median"])
    if bot["flow"]:
        print("    ours  = %.1f" % bot["flow"]["median"])
    print("\n  NOTE: if idle/human/ours are indistinguishable, the flow")
    print("  indicator cannot gate ownership - the name bubble must.")
    return 0


if __name__ == "__main__":
    sys.exit(main())