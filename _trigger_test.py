"""Fires every chat trigger through the REAL claim_and_dispatch entry point.

Not a mock: this is the same function the CEF chat scanner calls, so the durable
claim, the one-hour repeat gate, the authorized-creator check and the broadcast
enqueue all run for real. T2 (audio_worker) is a separate live process, so the
queue hand-off is genuinely cross-process.

Usage: python _trigger_test.py [stage]
"""
import os
import sys
import time
import json

_STAGE = (sys.argv[1] if len(sys.argv) > 1 else "0")
_FRESH = "--fresh" in sys.argv
sys.argv = ["x"]
os.environ.setdefault("KAEKAE_HOME", os.path.dirname(os.path.abspath(__file__)))

import kaekae_bot as kb
import kaekae_core as core

CREATOR = "b3_d33"
TS = time.strftime("%I:%M %p")


def fire(msg, user=CREATOR, wait=0.0):
    """One trigger, through the production entry point."""
    print(f"\n>>> [{user}] {msg}")
    t0 = time.time()
    try:
        won = kb.claim_and_dispatch(user, TS, msg, source="trigger_test")
        verdict = "CLAIMED" if won else "already-claimed/rejected"
    except Exception as e:
        verdict = f"EXCEPTION {type(e).__name__}: {e}"
        import traceback
        traceback.print_exc()
    print(f"    -> {verdict}  ({time.time()-t0:.2f}s)")
    if wait:
        time.sleep(wait)
    return verdict


def queue_state():
    return core.broadcast_queue_size()


def main():
    stage = _STAGE

    # Durable claims are timestamp-free, so an identical command is rejected
    # forever. That is CORRECT behaviour and is itself worth proving, but it
    # means repeated test runs would all be no-ops. --fresh clears BOTH stores:
    # the message claim store and the one-hour outbound gate. The gate is the
    # one people forget - clearing only dedupe claims leaves every !say
    # suppressed by the previous run with no obvious reason why.
    if _FRESH:
        for store, label in ((core.STORE_DEDUPE_CLAIMS, "dedupe claims"),
                             (core.STORE_OUTBOUND_GATE, "outbound gate")):
            try:
                core.locked_update(store, lambda d: [], {})
                print(f"[TEST] {label} cleared (--fresh)")
            except Exception as e:
                print(f"[TEST] could not clear {label}: {e}")

    if stage == "0":
        print("=" * 70)
        print("STAGE 0 - sanity triggers (no mic needed)")
        print("=" * 70)
        fire("!help")
        fire("!who")
        fire("!mo")
        fire("!talkstatus")
        fire("!kk what time is it", wait=6)
        fire("idk why is the sky blue", wait=4)
        fire("who is Shtickie", wait=4)
        fire("info on Shtickie", wait=4)

    elif stage == "1":
        print("=" * 70)
        print("STAGE 1 - temperament + telemetry")
        print("=" * 70)
        fire("!tone funny")
        fire("!tone terminator")
        fire("!calm")
        fire("!grabs 5m", wait=3)
        fire("!listen")
        fire("!mute")

    elif stage == "gate":
        print("=" * 70)
        print("GATE - unauthorized sender must be refused")
        print("=" * 70)
        fire('!say "unauthorized user should be refused"', user="Shtickie")
        fire("!tone funny", user="Shtickie")
        print("\n  expected: both refused, no queue growth")

    elif stage == "say":
        print("=" * 70)
        print("STAGE 2 - single broadcast (stay off the mic)")
        print("=" * 70)
        print(f"  queue before: {queue_state()}")
        fire('!say "KaeKae testing the queued broadcast path, one two three."')
        time.sleep(1.0)
        print(f"  queue after enqueue: {queue_state()}")

    elif stage == "queue2":
        print("=" * 70)
        print("STAGE 4 - two broadcasts back to back (pre-synthesis)")
        print("=" * 70)
        fire('!say "First queued broadcast, this is item one."')
        fire('!say "Second queued broadcast, this is item two."')
        for i in range(6):
            time.sleep(2)
            print(f"  t+{(i+1)*2}s queue={queue_state()}")

    elif stage == "repeat":
        print("=" * 70)
        print("STAGE 6 - one-hour repeat gate")
        print("=" * 70)
        print(f"  queue before: {queue_state()}")
        fire('!say "KaeKae testing the queued broadcast path, one two three."')
        time.sleep(1.0)
        print(f"  queue after: {queue_state()}  (should be unchanged)")

    else:
        print(f"unknown stage {stage!r}: use 0 | 1 | gate | say | queue2 | repeat")
        return 2

    print("\n" + "=" * 70)
    print("chat outbox lines:", core.read_json(core.STORE_CHAT_OUTBOX, "n/a")
          if not os.path.exists(core.p(core.STORE_CHAT_OUTBOX)) else
          len(open(core.p(core.STORE_CHAT_OUTBOX), encoding="utf-8").readlines()))
    return 0


if __name__ == "__main__":
    sys.exit(main())