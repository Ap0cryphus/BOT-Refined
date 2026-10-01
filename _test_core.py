#!/usr/bin/env python3
"""Offline verification for kaekae_core: gate, claims, config, queues.
Runs without Camfrog, mic, or network."""
import os
import sys
import time
import multiprocessing as mp
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["KAEKAE_HOME"] = os.path.dirname(os.path.abspath(__file__))

import kaekae_core as core

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

    print("\n" + "=" * 60)
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL CORE TESTS PASSED")


if __name__ == "__main__":
    run_tests()
