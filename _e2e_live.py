"""Live end-to-end test of the NEW production speak path.

Exercises exactly what audio_worker now does: render off-mic, wait for a real
quiet window, audio-first press, strict identity, and the >=50% audio bar.
"""
import sys
import time

sys.argv = ["x"]
import cef_probe as cp
import kaekae_core as core

PHRASE = "KaeKae here, testing the new queued broadcast path."


def main():
    tc = cp.global_talk_controller
    cp.global_probe.start_probe_daemon()
    time.sleep(1.5)
    attach = tc.catch_talk_process() or {}
    if not attach.get("attached"):
        print("NOT ATTACHED to a Camfrog room window")
        return 1
    print(f"attached={attach.get('attached')} coords={attach.get('talk_coords')}")

    print("\n--- 1. pre-render OFF the mic (queue-style) ---")
    t0 = time.time()
    meta = core.render_broadcast_audio(PHRASE)
    print(f"  ready={meta.get('audio_ready')} engine={meta.get('engine')} "
          f"duration={meta.get('audio_duration_s')}s in {time.time()-t0:.1f}s")
    if not meta.get("audio_ready"):
        print(f"  FAILED: {meta.get('reason')}")
        return 2

    print("\n--- 2. queue it the way chat_worker would ---")
    core.enqueue_broadcast(PHRASE, persona="valley")
    task = core.pop_broadcast()
    print(f"  popped id={task.get('id')} attempts={task.get('attempts')}")
    core.patch_broadcast("missing-id", {"audio_ready": True})   # no-op safety
    core.requeue_broadcast(task)
    task = core.pop_broadcast()
    print(f"  requeued and popped again: {task.get('text')[:40]!r}")

    print("\n--- 3. speak via the new production path ---")
    t1 = time.time()
    res = tc.speak_and_hold(
        task["text"],
        voice=task.get("voice") or "en-US-AvaNeural",
        rate=task.get("rate") or "+12%",
        pitch=task.get("pitch") or "+16Hz",
        output_device=cp.get_configured_output_device(),
        persona=task.get("persona") or "valley",
        gate=False,                       # already claimed in earlier tests
        pre_rendered_wav=meta["wav_path"],
        pre_rendered_duration=meta["audio_duration_s"],
    )
    print(f"\n=== RESULT (wall {time.time()-t1:.1f}s) ===")
    for k in ("ok", "acquired", "playback_ok", "observed_speaker", "method",
              "intended_duration_s", "heard_duration_s", "audio_fraction",
              "quiet_waited_s", "reason"):
        print(f"  {k:22} {res.get(k)}")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())