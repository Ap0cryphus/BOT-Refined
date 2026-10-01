"""
==============================================================================
KAEKAE AUDIO WORKER (TERMINAL 2: MICROPHONE & SOUND ENGINE)
==============================================================================
Sole owner of audio + the Camfrog talk button:
1. Listens to room voices via the VB-Audio Virtual Cable.
2. Transcribes spoken voice via Whisper STT into audio_transcripts.jsonl.
3. Detects microphone wake triggers ("kae", "kaekae", "kaebot").
4. Consumes broadcast_queue.json (Terminal 1 !say / Terminal 3) and speaks each
   item on the Camfrog mic through the VERIFIED talk controller.
5. Publishes heartbeats so Terminal 3 shows real liveness.

It never types into Camfrog chat: chat lines go to Terminal 1 via chat_outbox.jsonl
(single chat writer rule).
==============================================================================
"""

import os
import sys
import time
import json
import threading

# Identify ourselves for the talk-state mirror
os.environ.setdefault("KAEKAE_TERMINAL", "t2")

if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.kernel32.SetConsoleTitleW("KaeKae Audio Engine [Terminal 2 - Voice & Virtual Cable]")
    except Exception:
        pass

print("=" * 76)
print("  KAEKAE AUDIO WORKER (TERMINAL 2: SOUND & VOICE ENGINE)")
print("=" * 76)

from cef_probe import (
    global_probe,
    global_talk_controller,
    synthesize_speech_to_wav,
    play_wav_to_virtual_cable,
    resolve_audio_output_device,
    get_configured_output_device,
    ELEVENLABS_VOICES,
    get_elevenlabs_api_key
)

try:
    import kaekae_core as core
except Exception:
    core = None

AUDIO_OUTPUT_DEVICE = get_configured_output_device()

print(f"  Target Audio Device  : '{AUDIO_OUTPUT_DEVICE}'")
if core is not None:
    _cfg = core.load_config()
    print(f"  Voice Engine         : {_cfg.get('engine', 'edge')} "
          f"(persona={_cfg.get('elevenlabs_persona', 'valley')}, "
          f"qwen_speaker={_cfg.get('qwen_speaker', 'vivian')})")
api_key = get_elevenlabs_api_key()
if api_key:
    masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
    print(f"  ElevenLabs API Key   : ACTIVE (Key: {masked})")
else:
    print("  ElevenLabs API Key   : not set (add 'elevenlabs_api_key' to config.json)")
print("  Chat writes          : OUTBOX mode (Terminal 1 owns the chat box)")
print("=" * 76 + "\n")

_stop = threading.Event()
_presynth_busy = threading.Event()


def presynth_loop():
    """Renders queued broadcasts to WAV AHEAD of time, off the microphone.

    The point is that when the room finally falls quiet we can grab and speak
    immediately. Synthesis takes 2-5s (much longer on the first Qwen load) and
    doing that while already holding the mic means holding it in silence.

    This walks the queue and renders the item AFTER the head, leaving the head
    alone: the consumer is about to pop that one, and re-writing a task that is
    being popped concurrently is how fields go missing."""
    print("[AUDIO WORKER] Pre-synthesis thread online (renders queued audio ahead of time).")
    while not _stop.is_set():
        try:
            if core is None:
                time.sleep(0.5)
                continue
            pending = core.read_json(core.STORE_BROADCAST_QUEUE, []) or []
            if not isinstance(pending, list) or len(pending) < 2:
                time.sleep(0.4)
                continue
            # Skip the head (the consumer owns it) and anything already rendered.
            nxt = None
            for it in pending[1:]:
                if isinstance(it, dict) and not it.get("audio_ready"):
                    nxt = it
                    break
            if not nxt or _presynth_busy.is_set():
                time.sleep(0.4)
                continue

            _presynth_busy.set()
            try:
                text = str(nxt.get("text") or "").strip()
                if text:
                    print(f"[PRESYNTH] Rendering queued line: {text[:60]!r}")
                    meta = core.render_broadcast_audio(
                        text, persona=nxt.get("persona") or "",
                        voice=nxt.get("voice") or "",
                        rate=nxt.get("rate") or "",
                        pitch=nxt.get("pitch") or "")
                    core.patch_broadcast(nxt.get("id", ""), {
                        "wav_path": meta.get("wav_path", ""),
                        "audio_duration_s": meta.get("audio_duration_s", 0.0),
                        "audio_ready": bool(meta.get("audio_ready")),
                        "engine": meta.get("engine", ""),
                    })
                    if meta.get("audio_ready"):
                        print(f"[PRESYNTH] Ready: {text[:50]!r} "
                              f"({meta.get('audio_duration_s')}s, {meta.get('engine')})")
                    else:
                        print(f"[PRESYNTH] Render FAILED: {meta.get('reason')}")
            finally:
                _presynth_busy.clear()
        except Exception as e:
            print(f"[PRESYNTH] warning: {e}")
        time.sleep(0.4)


def speech_queue_consumer_loop():
    """Consumes broadcast tasks and speaks them with a real, reported result."""
    print("[AUDIO WORKER] Broadcast consumer online.")
    if global_probe is not None and not getattr(global_probe, "running", False):
        try:
            global_probe.start_probe_daemon()
            print("[AUDIO WORKER] CEF speaker probe started (mic verification needs it).")
        except Exception as e:
            print(f"[AUDIO WORKER] Probe start notice: {e}")

    while not _stop.is_set():
        task = None
        if core is not None:
            try:
                task = core.pop_broadcast()
            except Exception as e:
                print(f"[AUDIO WORKER] Queue read warning: {e}")
        if not task:
            time.sleep(0.2)
            continue

        text = (task.get("text") or "").strip()
        if not text:
            continue
        persona = task.get("persona") or "valley"
        voice = task.get("voice") or "en-US-AvaNeural"
        rate = task.get("rate") or "+12%"
        pitch = task.get("pitch") or "+16Hz"
        source = task.get("source", "t1")

        # Use the audio the pre-synthesis thread already rendered, if it is
        # ready. The head item is deliberately NOT rendered by that thread (it
        # avoids racing the pop), so when it is the only item queued we render
        # it here - still before the mic is touched, never during a hold.
        wav_path = task.get("wav_path") or ""
        duration = float(task.get("audio_duration_s") or 0.0)
        if not (task.get("audio_ready") and wav_path and os.path.exists(wav_path)):
            print("[SPEECH QUEUE] No pre-rendered audio; rendering now (off the mic)...")
            meta = core.render_broadcast_audio(
                text, persona=persona, voice=voice, rate=rate, pitch=pitch) \
                if core is not None else {"audio_ready": False, "reason": "core unavailable"}
            wav_path = meta.get("wav_path", "") or ""
            duration = float(meta.get("audio_duration_s") or 0.0)
            if not meta.get("audio_ready"):
                print(f"[SPEECH QUEUE] Render failed: {meta.get('reason')}")

        print(f"\n[SPEECH QUEUE] Broadcasting: \"{text}\" (persona={persona}, from {source}"
              + (f", pre-rendered {duration}s" if duration else "") + ")...")

        result = None
        if global_talk_controller is not None:
            try:
                result = global_talk_controller.speak_and_hold(
                    text, voice=voice, rate=rate, pitch=pitch,
                    output_device=AUDIO_OUTPUT_DEVICE, persona=persona,
                    pre_rendered_wav=wav_path if duration else "",
                    pre_rendered_duration=duration,
                )
            except Exception as e:
                print(f"[AUDIO WORKER] Broadcast exception: {e}")
                result = {"ok": False, "reason": str(e)}
        else:
            temp_wav = "temp_say_broadcast.wav"
            engine = synthesize_speech_to_wav(text, temp_wav, voice=voice,
                                              rate=rate, pitch=pitch, persona=persona)
            played = play_wav_to_virtual_cable(temp_wav, AUDIO_OUTPUT_DEVICE) if engine else False
            result = {"ok": bool(played), "acquired": False, "playback_ok": bool(played),
                      "engine": engine, "reason": "" if engine else "TTS failed"}

        ok = result.get("ok") if isinstance(result, dict) else bool(result)
        if isinstance(result, dict):
            print(f"[SPEECH QUEUE] Result: ok={ok} acquired={result.get('acquired')} "
                  f"playback={result.get('playback_ok')} engine={result.get('engine')} "
                  f"speaker={result.get('observed_speaker')!r} attempts={result.get('attempts')}"
                  + (f" reason={result.get('reason')!r}" if result.get("reason") else ""))

        # Always record the real outcome. A failed broadcast that leaves no trace
        # is indistinguishable from one that was never attempted.
        if core is not None:
            try:
                core.log_event(
                    "broadcast",
                    ok=bool(ok),
                    acquired=bool(result.get("acquired")) if isinstance(result, dict) else None,
                    playback_ok=bool(result.get("playback_ok")) if isinstance(result, dict) else None,
                    engine=(result.get("engine") if isinstance(result, dict) else ""),
                    observed_speaker=(result.get("observed_speaker") if isinstance(result, dict) else ""),
                    attempts=(result.get("attempts") if isinstance(result, dict) else 0),
                    method=(result.get("method") if isinstance(result, dict) else ""),
                    reason=(result.get("reason") if isinstance(result, dict) else ""),
                    source=source,
                    text=text[:120],
                )
            except Exception as e:
                print(f"[SPEECH QUEUE] Broadcast log warning: {e}")

        # Re-queue a failed broadcast instead of destroying it, so a transient
        # failure (mic busy, TTS hiccup) does not silently eat the line.
        reason_now = (result.get("reason") or "") if isinstance(result, dict) else ""
        permanent = (
            reason_now.startswith("suppressed:")
            or reason_now.startswith("TTS synthesis failed")
            or reason_now.startswith("GATE")
        )
        if not ok and permanent:
            # A gate refusal or TTS failure is deterministic: retrying just burns
            # attempts instantly and, worse, re-claims the same text each pass.
            print(f"[SPEECH QUEUE] Not retrying ({reason_now}): {text[:60]!r}")
            if core is not None:
                try:
                    core.log_event("broadcast", ok=False, skipped=True,
                                   reason=reason_now, text=text[:120])
                except Exception:
                    pass
            print(f"[SPEECH QUEUE] Finished: \"{text}\"\n")
            continue

        if not ok:
            attempts = int(task.get("attempts", 0) or 0) + 1
            if attempts <= 3:
                task["attempts"] = attempts
                task["text"] = text
                task["persona"] = persona
                task["voice"] = voice
                task["rate"] = rate
                task["pitch"] = pitch
                task["source"] = source
                if core is not None:
                    try:
                        core.requeue_broadcast(task)
                        print(f"[SPEECH QUEUE] Re-queued after failure "
                              f"(attempt {attempts}/3): {text[:60]!r}")
                    except Exception as e:
                        print(f"[SPEECH QUEUE] Re-queue failed: {e}")
            else:
                print(f"[SPEECH QUEUE] GIVING UP after 3 failed attempts: {text[:60]!r}")
                if core is not None:
                    try:
                        core.log_event("broadcast", ok=False, gave_up=True,
                                       attempts=attempts, text=text[:120])
                    except Exception:
                        pass

        print(f"[SPEECH QUEUE] Finished: \"{text}\"\n")
    print("[AUDIO WORKER] Broadcast consumer stopped.")


def control_state_sync_loop(kb):
    """Mirrors Terminal 1 control flags (bot_state.json) into this process and
    publishes a heartbeat, so chat !transcribe/!listen affect THIS process too."""
    last_beat = 0.0
    while not _stop.is_set():
        try:
            if core is not None:
                if time.time() - last_beat > 5.0:
                    last_beat = time.time()
                    core.heartbeat("t2", engine=core.load_config().get("engine", ""))

                if kb is not None:
                    data = core.read_json("bot_state.json", {}) or {}
                    st = kb.state
                    changed = []
                    for key, attr in (("transcribe_enabled", "transcribe_enabled"),
                                      ("listening_enabled", "listening_enabled"),
                                      ("responses_muted", "responses_muted"),
                                      ("chatty_mode", "chatty_mode")):
                        if key in data:
                            new_val = bool(data[key])
                            with st.lock:
                                if getattr(st, attr) != new_val:
                                    setattr(st, attr, new_val)
                                    changed.append(f"{attr}={new_val}")
                    if changed:
                        print(f"[AUDIO WORKER] Adopted control state from Terminal 1: {', '.join(changed)}")
        except Exception as e:
            print(f"[AUDIO WORKER] Sync warning: {e}")
        time.sleep(2.0)
    print("[AUDIO WORKER] Control-state sync stopped.")


def start_room_audio_listener():
    """Starts the STT recorder plus the broadcast consumer."""
    import kaekae_bot as kb

    # Load persisted users/kicks/memory so mic-triggered lookups work here too.
    try:
        kb.load_all_persisted_data()
        print("[AUDIO WORKER] Persisted user/memory data loaded.")
    except Exception as e:
        print(f"[AUDIO WORKER] Data load notice: {e}")

    # Terminal 2 must never type into the Camfrog chat box.
    kb.CHAT_SEND_MODE = "outbox"

    threading.Thread(target=speech_queue_consumer_loop, daemon=True, name="BroadcastConsumer").start()
    threading.Thread(target=presynth_loop, daemon=True, name="PreSynth").start()
    threading.Thread(target=control_state_sync_loop, args=(kb,), daemon=True, name="ControlSync").start()

    try:
        kb.start_transcribe_hotkey_listener()
    except Exception as e:
        print(f"[AUDIO WORKER] Hotkey listener notice: {e}")

    if hasattr(kb, "voice_listener_worker"):
        kb.voice_listener_worker()
    else:
        print("[AUDIO WORKER ERROR] voice_listener_worker not found; queue consumer still running.")
        while not _stop.is_set():
            time.sleep(0.5)


if __name__ == "__main__":
    try:
        start_room_audio_listener()
    except KeyboardInterrupt:
        pass
    finally:
        _stop.set()
        try:
            if global_talk_controller is not None:
                global_talk_controller.release_mic()
        except Exception:
            pass
        print("\n[AUDIO WORKER] Stopped cleanly. Mic released.")