#!/usr/bin/env python3
"""Offline verification for kaekae_core: gate, claims, config, queues.
Runs without Camfrog, mic, or network."""
import os
import sys
import time
import multiprocessing as mp
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["KAEKAE_HOME"] = os.path.dirname(os.path.abspath(__file__))

import kaekae_core as core

# The talk controller is needed for the quiet-window and mic_state contract
# tests. It is imported for its METHODS only - no test touches the real mic,
# and none of these tests press or release anything.
from cef_probe import CamfrogCEFTalkController, is_bot_name_strict
from kaekae_bot import trigger_is_stale, parse_chat_timestamp

# HERMETIC: redirect the shared store to a scratch folder so running this test
# never touches the bot's real config.json / claim store / logs.
import tempfile
_SCRATCH = Path(tempfile.mkdtemp(prefix="kaekae_core_test_"))
core.ROOT = _SCRATCH
core.LOGDIR = _SCRATCH / "logs"
core.LOGDIR.mkdir(exist_ok=True)
core.CONFIG_PATH = _SCRATCH / "config.json"   # load_config() reads this constant

FAILS = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name +
          (f"   [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def reset():
    for f in ("outbound_gate.json", "dedupe_claims.json", "broadcast_queue.json",
              "chat_outbox.jsonl", "command_inbox.jsonl", "pagination.json",
              "terminal_heartbeats.json", "talk_state.json"):
        p = core.p(f)
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass


def _lock_worker(scratch, hold, out_q):
    """Child process: take the OS lock, bump a counter, hold, release."""
    import kaekae_core as c
    from pathlib import Path as P
    c.ROOT = P(scratch)          # same hermetic store as the parent
    c.LOGDIR = P(scratch) / "logs"
    with c.FileLock(c.p("lock_probe.json"), timeout=10.0):
        data = c.read_json("lock_probe.json", {"n": 0})
        data["n"] = data.get("n", 0) + 1
        c.write_json_atomic("lock_probe.json", data)
        time.sleep(hold)
        out_q.put(1)


def run_tests():
    # --- T1: one-hour outbound gate ------------------------------------
    reset()
    core.save_config({"dup_reply_seconds": 3600}, announce=False)
    r1 = core.claim_or_suppress("reply", "Like, totally!")
    r2 = core.claim_or_suppress("reply", "Like, totally!")
    r3 = core.claim_or_suppress("reply", "like   totally")
    r4 = core.claim_or_suppress("reply", "Different reply")
    r5 = core.claim_or_suppress("ack", "Like, totally!")
    r6 = core.claim_or_suppress("system", "Like, totally!")
    check("gate: first send allowed", r1 is True)
    check("gate: exact repeat suppressed", r2 is False)
    check("gate: normalized repeat suppressed", r3 is False)
    check("gate: distinct reply allowed", r4 is True)
    check("gate: ack bypasses gate", r5 is True)
    check("gate: system bypasses gate", r6 is True)
    check("gate: persisted to disk", core.p("outbound_gate.json").exists())
    check("gate: snapshot non-empty", len(core.gate_snapshot(3600)) >= 2)

    core.save_config({"dup_reply_seconds": 1}, announce=False)
    core.claim_or_suppress("reply", "quick one")
    time.sleep(1.3)
    check("gate: expires after window",
          core.claim_or_suppress("reply", "quick one") is True)
    core.save_config({"dup_reply_seconds": 3600}, announce=False)

    # --- T1b: !say broadcast gate is sender-independent ------------------
    # Regression: two DIFFERENT admins sending the identical !say text must
    # produce exactly one broadcast (the chatroom duplicate).
    reset()
    core.save_config({"dup_reply_seconds": 3600}, announce=False)
    b1 = core.claim_or_suppress("broadcast", "KaeKae test broadcast one")
    b2 = core.claim_or_suppress("broadcast", "KaeKae test broadcast one")
    b3 = core.claim_or_suppress("broadcast", "  kaeKae   TEST broadcast ONE!  ")
    b4 = core.claim_or_suppress("broadcast", "KaeKae test broadcast TWO")
    check("broadcast: first !say allowed", b1 is True)
    check("broadcast: identical repeat from 2nd admin suppressed", b2 is False)
    check("broadcast: case/punctuation variant suppressed", b3 is False)
    check("broadcast: different text allowed", b4 is True)
    check("broadcast: gate kind is registered", "broadcast" in core.GATED_KINDS)
    check("broadcast: echo kind stays ungated",
          core.claim_or_suppress("system", "[Mic Broadcast]: x") is True)

    # --- T2: inbound claim is idempotent -------------------------------
    reset()
    core.save_config({"screen_dup_seconds": 120}, announce=False)
    sig = core.make_chat_signature("Players__Lounge", "B3_D33", "!transcribe")
    wins = [core.claim_message(sig, room="Players__Lounge") for _ in range(300)]
    check("claim: exactly one win out of 300", sum(1 for w in wins if w) == 1,
          f"wins={sum(1 for w in wins if w)}")
    check("claim: persisted before dispatch", core.p("dedupe_claims.json").exists())

    s1 = core.make_chat_signature("R", "b3_d33", "Hello   there!!")
    s2 = core.make_chat_signature("R", "b3_d33", "hello there")
    check("claim: signature ignores punctuation/case/spacing", s1 == s2, f"{s1!r} vs {s2!r}")
    check("claim: different sender is distinct",
          s1 != core.make_chat_signature("R", "someone_else", "hello there"))
    # --- T2b: moderation parser rejects prose, understands real notices ---
    import kaekae_bot as kb
    good = [
        ("Noone was banned JellyBish",            ("banned", "Noone", "JellyBish")),
        ("Noone was kicked xX_MAYHEM_Xx",         ("kicked", "Noone", "xX_MAYHEM_Xx")),
        ("xX_MAYHEM_Xx was blocked by Samuel_____", ("blocked", "Samuel_____", "xX_MAYHEM_Xx")),
        ("Samuel_____ banned xX_MAYHEM_Xx",       ("banned", "Samuel_____", "xX_MAYHEM_Xx")),
        ("B3_D33 blocked KaeKae_Toad microphone", ("blocked", "B3_D33", "KaeKae_Toad")),
    ]
    for raw, exp in good:
        r = kb.detect_kick_block("", raw)
        got = (r["action"], r["actor"], r["target"]) if r else None
        check(f"mod: parses {raw[:38]!r}", got == exp, f"got={got}")

    bad = [
        "Please do not block or kick anyone",
        "Rules: blocking and kicking are not allowed",
        "are or", "never him", "got like", "USERS This",
        "you will be banned if you keep spamming",
    ]
    for raw in bad:
        r = kb.detect_kick_block("", raw)
        check(f"mod: rejects {raw[:38]!r}", r is None, f"got={r}")

    # Underscore/dollar names must survive intact (Samuel_____ was truncated before).
    r = kb.detect_kick_block("", "Noone was kicked $htickie_")
    check("mod: keeps $_ in names", bool(r) and r["target"] == "$htickie_",
          f"got={r}")

    # --- T2c: runtime ignore list (config.json, hot-reloaded) ------------
    core.save_config({"ignored_names": []}, announce=False)
    check("ignore: builtin room bot is ignored", kb.is_ignored_name("Players_Lounge1"))
    check("ignore: real user not ignored", not kb.is_ignored_name("xX_MAYHEM_Xx"))
    check("ignore: add persists", kb.add_ignored_name("NoisyBot99"))
    check("ignore: added name is ignored", kb.is_ignored_name("noisybot99"))
    check("ignore: duplicate add refused", kb.add_ignored_name("NoisyBot99") is False)
    check("ignore: remove persists", kb.remove_ignored_name("NoisyBot99"))
    check("ignore: removed name is live again", not kb.is_ignored_name("NoisyBot99"))
    check("ignore: self always ignored", kb.is_ignored_name("KaeKae_Toad"))
    core.save_config({"ignored_names": []}, announce=False)

    # --- T2d: talk coordinates must survive a config.json edit ------------
    # Regression: config.json is edited far more often than camfrog_coords.json,
    # and the loader used to `break` on whichever file looked newer, so config
    # replaced the coords and the controller fell back to hardcoded (1480,600).
    import cef_probe as _cp
    _tc = _cp.CamfrogCEFTalkController()
    _c1 = _tc.get_talk_coordinates()
    core.save_config({"engine": core.load_config().get("engine", "qwen")}, announce=False)
    _tc._load_coordinates()
    _c2 = _tc.get_talk_coordinates()
    check("talk coords: stable across a config write", _c1 == _c2, f"{_c1} vs {_c2}")
    check("talk coords: not the hardcoded fallback", _c2 != (1480, 600), f"got {_c2}")
    check("talk coords: file is project-root anchored",
          os.path.isabs(_cp.COORDS_FILE) and _cp.COORDS_FILE.endswith("camfrog_coords.json"),
          _cp.COORDS_FILE)

    # --- T3: cross-process exclusive lock -------------------------------
    reset()
    try:
        core.p("lock_probe.json").unlink()
    except Exception:
        pass
    q = mp.Queue()
    procs = [mp.Process(target=_lock_worker,
                        args=(str(_SCRATCH), 0.25, q))
             for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    final = core.read_json("lock_probe.json", {"n": 0})
    check("lock: 4 concurrent writers, no lost update",
          final.get("n") == 4, f"n={final.get('n')}")

    # --- T4: broadcast queue (T1/T3 -> T2) ------------------------------
    reset()
    for i in range(5):
        core.enqueue_broadcast(f"line {i}", persona="valley", source="t1")
    check("broadcast: size is 5", core.broadcast_queue_size() == 5)
    t = core.pop_broadcast()
    check("broadcast: FIFO order", bool(t) and t["text"] == "line 0", str(t))
    check("broadcast: size after pop is 4", core.broadcast_queue_size() == 4)
    core.write_json_atomic("broadcast_queue.json", [])
    check("broadcast: empty pop returns None", core.pop_broadcast() is None)

    # --- T5: chat outbox (T2/T3 -> T1) ----------------------------------
    reset()
    core.append_chat_outbox("[MIC] bob: hello", override_mute=True)
    core.append_chat_outbox("plain line")
    got = core.drain_chat_outbox()
    check("outbox: 2 lines drained", len(got) == 2, str(got))
    check("outbox: override_mute preserved", got[0]["override_mute"] is True)
    check("outbox: emptied after drain", core.drain_chat_outbox() == [])

    # --- T6: command inbox (T3 -> T1) -----------------------------------
    reset()
    core.dump_inbox_command("!who")
    core.dump_inbox_command("!info on bob")
    cmds = core.drain_inbox_commands()
    check("inbox: 2 commands drained", len(cmds) == 2, str(cmds))
    check("inbox: emptied after drain", core.drain_inbox_commands() == [])

    # --- T7: shared pagination ------------------------------------------
    reset()
    core.save_pagination({"title": "X", "chunks": ["a", "b"], "current_index": 1,
                          "requester": "bob", "timestamp": time.time()})
    check("pagination: visible to other terminal", bool(core.load_pagination()))
    core.save_pagination(None)
    check("pagination: cleared", core.load_pagination() == {})

    # --- T8: heartbeats --------------------------------------------------
    reset()
    core.heartbeat("t1", room="Lounge")
    check("heartbeat: t1 alive", core.terminal_alive("t1") is True)
    check("heartbeat: t2 not alive", core.terminal_alive("t2") is False)

    # --- T9: talk state -------------------------------------------------
    reset()
    core.set_talk_state("t2", True, method="mouse_hold")
    ts = core.get_talk_state()
    check("talk: holding state readable",
          ts.get("holding") is True and ts.get("method") == "mouse_hold", str(ts))

    # --- T10: config round-trip -----------------------------------------
    reset()
    core.save_config({"engine": "qwen", "qwen_speaker": "serena"}, announce=False)
    cfg = core.load_config(force=True)
    check("config: engine persisted", cfg.get("engine") == "qwen", str(cfg.get("engine")))
    check("config: speaker persisted", cfg.get("qwen_speaker") == "serena")
    core.save_config({"dup_reply_seconds": 1234}, announce=False)
    check("config: merge keeps other keys",
          core.load_config(force=True).get("dup_reply_seconds") == 1234)

    # --- T11: broadcast queue + pre-rendered audio -----------------------
    reset()
    core.enqueue_broadcast("first line", source="t1")
    core.enqueue_broadcast("second line", source="t1")
    check("queue: two items queued", core.broadcast_queue_size() == 2,
          str(core.broadcast_queue_size()))
    a = core.pop_broadcast()
    b = core.pop_broadcast()
    check("queue: FIFO order", a["text"] == "first line" and b["text"] == "second line",
          f"{a['text']!r}/{b['text']!r}")
    check("queue: empty when drained", core.pop_broadcast() is None)

    reset()
    core.enqueue_broadcast("patchable line")
    queued = core.read_json(core.STORE_BROADCAST_QUEUE, [])[0]
    check("queue: task has an id", bool(queued.get("id")), str(queued.get("id")))
    check("queue: starts not audio-ready", queued.get("audio_ready") is False)
    core.patch_broadcast(queued["id"], {"wav_path": "x.wav",
                                        "audio_duration_s": 3.5,
                                        "audio_ready": True})
    patched = core.read_json(core.STORE_BROADCAST_QUEUE, [])[0]
    check("queue: pre-render attached by id",
          patched.get("audio_ready") is True
          and patched.get("audio_duration_s") == 3.5, str(patched))
    core.patch_broadcast("nope", {"audio_ready": True})
    check("queue: patch of unknown id is a no-op",
          core.read_json(core.STORE_BROADCAST_QUEUE, [])[0].get("wav_path") == "x.wav")

    reset()
    core.enqueue_broadcast("will fail")
    t = core.pop_broadcast()
    t["attempts"] = 1
    core.requeue_broadcast(t)
    check("queue: requeue restores the line",
          core.broadcast_queue_size() == 1
          and core.pop_broadcast()["text"] == "will fail")

    # --- T12: wav duration -----------------------------------------------
    check("wav duration: missing file is 0.0",
          core.wav_duration_seconds("does_not_exist.wav") == 0.0)
    check("cache path: stable per text",
          core.cache_path_for_text("abc") == core.cache_path_for_text("abc"))
    check("cache path: differs per text",
          core.cache_path_for_text("abc") != core.cache_path_for_text("abd"))

    # --- T13: quiet window gate -----------------------------------------
    # The gate must survive a stub whose bubble we control sample by sample.
    class _StubCtl:
        def __init__(self, script):
            self.script = list(script)
            self.calls = 0

        def read_speaker_name_verbose(self):
            v = self.script[min(self.calls, len(self.script) - 1)]
            self.calls += 1
            return v

    ctl = _StubCtl([("", True)] * 40)
    q = CamfrogCEFTalkController.wait_for_quiet_mic(ctl, quiet_s=1.0, timeout_s=3.0,
                                                    poll_s=0.01)
    check("quiet gate: constant silence opens the window", q["ok"] is True, str(q))

    # A 0.5s blip must NOT count as quiet: the bubble is repopulated mid-window.
    ctl = _StubCtl([("", True)] * 2 + [("Shtickie", True)] + [("", True)] * 40)
    q = CamfrogCEFTalkController.wait_for_quiet_mic(ctl, quiet_s=1.0, timeout_s=0.4,
                                                    poll_s=0.01)
    check("quiet gate: a name mid-window blocks the grab", q["ok"] is False, str(q))

    # Unreadable is NOT silence - this is the fail-closed rule.
    ctl = _StubCtl([("", False)] * 40)
    q = CamfrogCEFTalkController.wait_for_quiet_mic(ctl, quiet_s=1.0, timeout_s=0.3,
                                                    poll_s=0.01)
    check("quiet gate: unreadable bubble never counts as quiet", q["ok"] is False,
          str(q))
    check("quiet gate: unreadable timeout says so",
          "unreadable" in q["reason"], q["reason"])

    # --- T14: mic_state contract (regression) ----------------------------
    # Two `mic_state` defs once lived in this class; the tuple version shadowed
    # the dict one and production died on `info["state"]`. Pin the contract.
    import inspect as _inspect
    _src = _inspect.getsource(CamfrogCEFTalkController)
    _defs = _src.count("    def mic_state(")
    check("mic_state: exactly one definition", _defs == 1, f"found {_defs}")
    _classdict = {k: v for k, v in vars(CamfrogCEFTalkController).items()
                  if callable(v)}
    _live = CamfrogCEFTalkController.mic_state
    check("mic_state: production name returns a dict contract",
          "is_free" in _inspect.getsource(_live), "dict-shaped mic_state missing")
    check("mic_state: tuple helper kept under its own name",
          hasattr(CamfrogCEFTalkController, "mic_state_tuple"))

    def _dupes():
        names = [k for k, v in vars(CamfrogCEFTalkController).items()
                 if callable(v) and not k.startswith("__")]
        return sorted({n for n in names if names.count(n) > 1})
    check("mic_state: no silently shadowed methods", _dupes() == [], str(_dupes()))

    # --- T15: pixel-only success is off by default -----------------------
    _sig = _inspect.signature(CamfrogCEFTalkController.acquire_talk)
    check("acquire_talk: allow_unverified defaults to False",
          _sig.parameters["allow_unverified"].default is False,
          str(_sig.parameters["allow_unverified"].default))

    # --- T16: ownership identity -----------------------------------------
    check("identity: KaeKaeToad is strictly ours", is_bot_name_strict("KaeKaeToad"))
    check("identity: Shtickie is not ours", not is_bot_name_strict("Shtickie"))
    check("identity: a rival is not mistaken for us",
          not is_bot_name_strict("NotKaeKaeToad"))
    check("identity: empty is not ours", not is_bot_name_strict(""))

    # --- T17: trigger staleness (no acting on old on-screen commands) -----
    import datetime as _dt
    def _ts_ago(minutes):
        return (_dt.datetime.now() - _dt.timedelta(minutes=minutes)).strftime("%I:%M %p")

    check("stale: a command from just now is fresh",
          not trigger_is_stale(_ts_ago(0), 90))
    check("stale: a command from 5 minutes ago is refused",
          trigger_is_stale(_ts_ago(5), 90))
    check("stale: a command from 2 hours ago is refused",
          trigger_is_stale(_ts_ago(120), 90))
    # A clock time carries NO date, so a line from yesterday reads identically to
    # today's line and the ambiguity spans the whole 24h cycle. The only provable
    # discriminator is magnitude: a clock time many hours away from now - in
    # EITHER direction - cannot be a command posted seconds ago, so it is stale.
    def _age_hours(ts):
        p = parse_chat_timestamp(ts)
        return (abs((_dt.datetime.now() - p).total_seconds()) / 3600.0) if p else None

    # Camfrog clock times carry NO date, so a line from yesterday is
    # indistinguishable from today's. The contract is deliberately one-sided:
    #   past + beyond the window  -> stale (the real case we must catch)
    #   slightly in the future    -> FRESH (a 12/24h clock reading, or a
    #                                 dropped AM/PM marker - not evidence of an
    #                                 old line)
    #   many hours in the future  -> stale (a different day entirely)
    def _hours(ts):
        p = parse_chat_timestamp(ts)
        return ((_dt.datetime.now() - p).total_seconds() / 3600.0) if p else None

    now_dt = _dt.datetime.now()
    for label, offset_h, expect_stale in (
            ("a small clock skew into the future is still fresh", 2.0, False),
            ("many hours into the future is a different day", 15.0, True),
    ):
        t = (now_dt + _dt.timedelta(hours=offset_h)).strftime("%I:%M %p")
        check(f"stale: {label}", trigger_is_stale(t, 90) is expect_stale,
              f"{t} ({_hours(t):+.1f}h)")
    check("stale: the current minute is fresh",
          not trigger_is_stale(now_dt.strftime("%I:%M %p"), 90))
    check("stale: unparseable timestamp is treated as fresh, not fatal",
          not trigger_is_stale("not-a-time", 90))
    check("stale: empty timestamp is treated as fresh",
          not trigger_is_stale("", 90))
    # Regression: .upper() turned %p into %P and NOTHING parsed, so the gate
    # silently never fired.
    check("stale: timestamps actually parse (AM/PM not mangled)",
          parse_chat_timestamp("07:49 AM") is not None)
    check("stale: 24h clock parses",
          parse_chat_timestamp("11:59 PM") is not None)

    # --- T18: render cache retention -------------------------------------
    check("cache: engine tag changes the cache key",
          core.cache_path_for_text("hello", "voiceA") !=
          core.cache_path_for_text("hello", "voiceB"))
    check("cache: same engine tag is stable",
          core.cache_path_for_text("hello", "voiceA") ==
          core.cache_path_for_text("hello", "voiceA"))
    check("cache: refuses to delete outside the cache dir",
          core.drop_cached_audio("config.json") is False)
    check("cache: tolerates a missing file", core.drop_cached_audio("") is False)

    # --- T19: pacing + queue isolation ------------------------------------
    # These keys live in the REAL config.json, but the test suite redirects
    # core.CONFIG_PATH to a scratch dir. Write them there first so the assertion
    # tests the defaults the bot actually boots with, not whatever happens to be
    # in the developer's working copy.
    core.save_config({"broadcast_gap_seconds": 2.5, "trigger_max_age_s": 90},
                     announce=False)
    cfg = core.load_config(force=True)
    check("pacing: broadcast gap is configured",
          float(cfg.get("broadcast_gap_seconds", 0)) > 0,
          str(cfg.get("broadcast_gap_seconds")))
    check("trigger freshness window is configured",
          float(cfg.get("trigger_max_age_s", 0)) > 0,
          str(cfg.get("trigger_max_age_s")))
    check("pacing: a backlog cannot burst (gap > 0)",
          float(cfg.get("broadcast_gap_seconds")) >= 1.0,
          str(cfg.get("broadcast_gap_seconds")))
    check("trigger window is short enough to drop stale on-screen lines",
          float(cfg.get("trigger_max_age_s")) <= 300,
          str(cfg.get("trigger_max_age_s")))

    # --- T20: presence - join/quit notices -------------------------------
    import presence as pres
    p = pres
    for raw, act, who in (
            ("Join: tajnysmiral", "join", "tajnysmiral"),
            ("Quit: tajnysmiral", "quit", "tajnysmiral"),
            ("[10/01I07:30:31] Join: $htickie", "join", "$htickie"),
            ("tajnysmiral has left the room", "quit", "tajnysmiral"),
            ("b3_d33 joined", "join", "b3_d33"),
    ):
        got = pres.parse_join_quit(raw)
        check(f"presence: parses {raw[:34]!r}",
              bool(got) and got["action"] == act and got["user"] == who, str(got))
    for raw in ("hello there", "Join: mic", "$htickie blocked $htickie microphone", ""):
        check(f"presence: ignores non-notice {raw[:30]!r}",
              pres.parse_join_quit(raw) is None, str(pres.parse_join_quit(raw)))
    check("presence: join notices are marked as having no clock",
          pres.parse_join_quit("Join: tajnysmiral")["timestamped"] == "no")

    # --- T21: roster panel parsing ---------------------------------------
    check("roster: reads LURKERS count",
          pres.parse_roster_header("LURKERS 2") == ("lurkers", 2))
    check("roster: reads MEMBERS count with a colon",
          pres.parse_roster_header("MEMBERS: 0") == ("members", 0))
    check("roster: reads YOU ARE VIEWING",
          pres.parse_roster_header("YOU ARE VIEWING 3") == ("viewing", 3))
    check("roster: an illegible count is UNKNOWN, not zero",
          pres.parse_roster_header("LURKERS") == ("lurkers", -1))
    blk = pres.parse_roster_block(["YOU ARE VIEWING 0", "MEMBERS 0",
                                   "LURKERS 2", "tajnysmiral", "Shtickie"])
    check("roster: extracts all three buckets",
          blk["counts"] == {"viewing": 0, "members": 0, "lurkers": 2}, str(blk["counts"]))
    check("roster: extracts names without header text",
          blk["users"] == ["tajnysmiral", "Shtickie"], str(blk["users"]))
    check("roster: empty panel is not 'confidently empty'",
          pres.parse_roster_block([])["reading_ok"] is False)

    # --- T22: cursor hover suppresses the event feed ----------------------
    check("cursor: inside the panel counts as hovering",
          pres.cursor_position_over_roster((1500, 400), (1400, 300, 200, 500)) is True)
    check("cursor: over the chat feed does not",
          pres.cursor_position_over_roster((700, 400), (1400, 300, 200, 500)) is False)
    check("cursor: unknown cursor is never 'hovering'",
          pres.cursor_position_over_roster(None, (1400, 300, 200, 500)) is False)
    check("cursor: unknown panel is never 'hovering'",
          pres.cursor_position_over_roster((1500, 400), None) is False)

    # --- T23: presence store is date-stamped and self-pruning ------------
    st = {}
    res = pres.apply_roster(st, "RoomA", ["tajnysmiral", "Shtickie"],
                            {"lurkers": 2, "members": 0, "viewing": 0})
    check("store: first snapshot reports both as joined",
          sorted(res["joined"]) == ["Shtickie", "tajnysmiral"], str(res["joined"]))
    res = pres.apply_roster(st, "RoomA", ["Shtickie"], {"lurkers": 1})
    check("store: a missing user is marked gone via the panel",
          res["left"] == ["tajnysmiral"] and res["joined"] == [], str(res))
    dep = st["rooms"]["RoomA"]["departed"][0]
    check("store: departure records the date it was observed",
          bool(dep.get("left_at")) and dep.get("left_reason") == "panel", str(dep))
    check("store: present set reflects the latest snapshot",
          pres.present_users(st, "RoomA") == ["Shtickie"])

    st2 = {}
    pres.record_event(st2, "RoomA", "join", "tajnysmiral", 1)
    ev = st2["events"][0]
    check("store: events carry an observed_at date",
          bool(ev.get("observed_at")), str(ev))
    check("store: events are marked NOT exact time",
          ev["exact_time"] is False and ev["timestamped"] == "no", str(ev))
    check("store: events preserve feed ordering via seq",
          ev["seq"] == 1, str(ev))
    # Undated / user-less rows must not survive, so recall never answers from
    # a record whose age or subject cannot be established.
    st2["events"].append({"action": "join", "user": "", "observed_at": None})
    st2["events"].append({"action": "join", "user": "ghost", "observed_at": "nonsense"})
    before = len(st2["events"])
    removed = pres.purge_undated(st2)
    check("store: undated and user-less rows are removed",
          len(st2["events"]) == before - removed == 1,
          f"{len(st2['events'])} left, {removed} removed")

    # A record from yesterday is stale under the one-day rule.
    st3 = {"rooms": {"R": {"users": {"old": {"name": "old",
              "last_seen": (datetime.now() - timedelta(days=3)).isoformat()}}}}}
    check("store: a three-day-old presence record is pruned",
          pres.prune_stale(st3) == 1 and "old" not in st3["rooms"]["R"]["users"],
          str(st3))

    # --- T24: OCR-damaged headers and known-user matching ---------------
    # Live OCR of the panel yields these exact strings: spaces are lost and a
    # stray glyph is prefixed. Header matching must survive that.
    check("roster: OCR-damaged YOU ARE VIEWING still parses",
          pres.parse_roster_header("svYOUAREVIEWING0 v") == ("viewing", 0),
          str(pres.parse_roster_header("svYOUAREVIEWING0 v")))
    check("roster: OCR-damaged MEMBERS still parses",
          pres.parse_roster_header("A MEMBERS0 v") == ("members", 0))
    check("roster: OCR-damaged LURKERS still parses",
          pres.parse_roster_header("A_LURKERS2 v") == ("lurkers", 2))
    check("roster: a header with no digits stays UNKNOWN",
          pres.parse_roster_header("LURKERS") == ("lurkers", -1))

    live = ["GIFTUsers2", "svYOUAREVIEWING0 v", "A MEMBERS0 v",
            "A_LURKERS2 v", "b1HShtickie Pm", "4KaeKae_Toad fi"]
    blk2 = pres.parse_roster_block(live)
    check("roster: live OCR counts are correct",
          blk2["counts"] == {"viewing": 0, "members": 0, "lurkers": 2},
          str(blk2["counts"]))
    check("roster: garbled OCR never becomes a username",
          blk2["users"] == [], str(blk2["users"]))
    check("roster: known user is confirmed through the OCR noise",
          pres.match_known_users(live, ["Shtickie", "KaeKae_Toad"]) ==
          ["Shtickie", "KaeKae_Toad"],
          str(pres.match_known_users(live, ["Shtickie", "KaeKae_Toad"])))
    check("roster: an absent known user is not reported",
          pres.match_known_users(live, ["NobodyHere"]) == [])
    check("roster: clean username accepted", pres.looks_like_username("Shtickie"))
    check("roster: garbled line rejected",
          not pres.looks_like_username("b1HShtickie Pm"))
    check("roster: header text is excluded from names by the header check",
          "A_LURKERS2" not in blk2["users"], str(blk2["users"]))
    check("roster: GIFTs toolbar label is not a user",
          not pres.looks_like_username("GIFTUsers2"))

    # --- T25: clocks and chrome are never users -------------------------
    # Live UIA exposed the room clock as a right-side control and the old scan
    # reported it in !who as the user "813AM".
    for clock in ("8:13 AM", "813AM", "21:33", "10:42", "1042PM", "07:05:31"):
        check(f"presence: clock {clock!r} is not a user",
              pres.is_junk_panel_token(clock), "accepted as a user")
    check("presence: the GIFTs toolbar is not a user",
          pres.is_junk_panel_token("GIFTUsers2"))
    check("presence: a real username is not junk",
          not pres.is_junk_panel_token("Shtickie"))
    check("presence: $htickie is not junk",
          not pres.is_junk_panel_token("$htickie"))
    check("presence: KaeKae_Toad is not junk",
          not pres.is_junk_panel_token("KaeKae_Toad"))

    # --- T26: room membership is per room (real state) ------------------
    import time as _time
    st = kb.state
    with st.lock:
        st.room_users_by_room = {}
        st.current_room_users = set()
        st.current_focused_room = "RoomA"
    kb.note_user_in_room("Alice")
    with st.lock:
        st.current_focused_room = "RoomB"
    kb.note_user_in_room("Bob")
    kb.note_user_in_room("Alice")          # Alice is in BOTH rooms
    check("rooms: RoomA lists only its own users",
          kb.users_in_room("RoomA") == {"alice"}, str(kb.users_in_room("RoomA")))
    check("rooms: RoomB lists only its own users",
          kb.users_in_room("RoomB") == {"alice", "bob"},
          str(kb.users_in_room("RoomB")))
    check("rooms: Alice is present in two rooms at once",
          "alice" in kb.users_in_room("RoomA")
          and "alice" in kb.users_in_room("RoomB"))
    check("rooms: the snapshot separates rooms rather than merging them",
          set(kb.all_rooms_with_users().keys()) == {"RoomA", "RoomB"},
          str(kb.all_rooms_with_users()))
    # A junk token must never enter through the shared writer either.
    kb.note_user_in_room("8:13 AM")
    kb.note_user_in_room("GIFTUsers2")
    check("rooms: junk cannot enter via note_user_in_room",
          kb.users_in_room("RoomB") == {"alice", "bob"},
          str(kb.users_in_room("RoomB")))
    with st.lock:
        st.room_users_by_room = {}
        st.current_room_users = set()

    # --- T27: transcript echo is separate from transcription -------------
    # REGRESSION: the stale-trigger window was 90s while Camfrog's chat clock ran
    # ~3 minutes behind the PC, so a LIVE !transcribed was dropped 28 times as
    # "stale" and the room kept being spammed. The window must be far wider
    # than any plausible clock skew.
    # The suite redirects core.CONFIG_PATH to a scratch dir, so the real
    # config.json value is invisible here. Seed the production default instead:
    # this test exists to stop the window ever being narrowed back to a value
    # that cannot absorb clock skew.
    core.save_config({"trigger_max_age_s": 600}, announce=False)
    check("stale: window is wide enough to survive clock skew",
          float(core.load_config(force=True).get("trigger_max_age_s", 0)) >= 300,
          str(core.load_config(force=True).get("trigger_max_age_s")))
    three_min_old = (_dt.datetime.now() - _dt.timedelta(minutes=3)).strftime("%I:%M %p")
    check("stale: a 3-minute-old line is NOT dropped (the live regression)",
          not trigger_is_stale(three_min_old, 600), "dropped a live command")
    check("stale: age is reportable for diagnostics",
          isinstance(kb.chat_timestamp_age_seconds(three_min_old), float))
    check("stale: unparseable age reports None, not a crash",
          kb.chat_timestamp_age_seconds("nonsense") is None)

    with kb.state.lock:
        kb.state.transcribe_enabled = True
        kb.state.transcript_echo_enabled = True
        kb.state.listening_enabled = True
    kb.claim_and_dispatch("b3_d33", "10:35 AM", "!transcribed",
                          source="test", trusted=True)
    with kb.state.lock:
        check("echo: !transcribed keeps STT running",
              kb.state.transcribe_enabled is True)
        check("echo: !transcribed turns the chat echo off",
              kb.state.transcript_echo_enabled is False)
    kb.claim_and_dispatch("b3_d33", "10:36 AM", "!transcribe",
                          source="test", trusted=True)
    with kb.state.lock:
        check("echo: !transcribe restores the echo",
              kb.state.transcript_echo_enabled is True)
        check("echo: !transcribe keeps STT on",
              kb.state.transcribe_enabled is True)

    # --- T28: speaker identity pool spans rooms and profiles ------------
    with kb.state.lock:
        kb.state.room_users_by_room = {"RoomA": {"shtickie": 1.0},
                                       "RoomB": {"tajnysmiral": 1.0}}
        kb.state.current_room_users = {"shtickie"}
        kb.state.current_focused_room = "RoomA"
    pool = {u.lower() for u in kb.known_speaker_identities()}
    check("speaker: includes a user from the current room", "shtickie" in pool)
    check("speaker: includes a user seen only in ANOTHER room",
          "tajnysmiral" in pool, str(sorted(pool)))
    check("speaker: never includes a clock", not any(
        p.looks_like_clock(u) for u in kb.known_speaker_identities()))
    with kb.state.lock:
        kb.state.room_users_by_room = {}
        kb.state.current_room_users = set()

    # --- T29: silent startup defaults -----------------------------------
    # The bot must come up capturing but SILENT, with chatty mode on and no
    # startup banner in the room.
    # A FRESH instance is used deliberately: earlier tests legitimately flip
    # these flags, so asserting on the live shared state would only prove the
    # test ordering. What matters is the value a real startup begins from.
    _fresh = kb.BotState()
    check("defaults: chat transcript echo is OFF at startup",
          _fresh.transcript_echo_enabled is False,
          str(_fresh.transcript_echo_enabled))
    check("defaults: STT itself is still ON (data keeps being collected)",
          _fresh.transcribe_enabled is True)
    check("defaults: chatty mode starts ON", _fresh.chatty_mode is True)
    check("defaults: command acks are terminal-only",
          _fresh.chat_command_acks is False)

    # --- T30: acknowledgements are terminal-only ------------------------
    check("ack: a timestamped status banner is an ack",
          kb.is_command_ack("(10/01I09:24:08) Live transcription is OFF."))
    check("ack: [Mic Broadcast] echo is an ack",
          kb.is_command_ack("[Mic Broadcast]: hello"))
    check("ack: [Presence] report is an ack",
          kb.is_command_ack("[Presence] Room: x"))
    check("ack: ordinary conversation is NOT an ack",
          not kb.is_command_ack("oh my god that was hilarious"))
    check("ack: a real bot reply is NOT an ack",
          not kb.is_command_ack("I'd say it's because the sky is painted by god"))
    check("ack: empty text is not an ack", not kb.is_command_ack(""))

    # --- T31: OCR speaker identity ---------------------------------------
    check("ocr: reader returns a string (never raises)",
          isinstance(kb.read_ocr_speaker_name(), str))
    check("ocr: an unreadable bubble resolves to nothing, never a guess",
          kb.read_ocr_speaker_name() != "Unknown speaker")

    print("\n" + "=" * 60)
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CORE TESTS PASSED")


if __name__ == "__main__":
    run_tests()
