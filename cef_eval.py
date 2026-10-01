#!/usr/bin/env python3
"""
==============================================================================
KaeKae Evaluation Harness  (cef_eval.py)
==============================================================================
A single, self-contained evaluation tool. It never types into Camfrog chat
and never announces anything, so it is safe to run against a live room.

Modes:
  --bench            Latency benchmark for the brain (Ollama LLM) and the
                     voice engines (Qwen3-TTS / ElevenLabs / Edge / SAPI).
                     Writes logs/bench_<ts>.json so results drive config.json.
  --observe          READ-ONLY CEF capture (never sends, never burns a claim):
                     writes logs/dom_*.jsonl, logs/parse_*.jsonl, logs/speaker_*.jsonl
  --replay FILE      Replay a captured dom_*.jsonl --loops times through the real
                     claim logic in a throwaway store; expects exactly one
                     dispatch per distinct message. The real claim store is
                     never touched (verified by before/after checksum).
  --talktest         Traced, verified mic acquisition: reports press attempts,
                     patterns used, the speaker label actually observed, how long
                     KaeKae's name held the slot, and the true outcome.

Usage examples:
  python cef_eval.py --bench --tts --speakers vivian,serena
  python cef_eval.py --bench --llm --models llama3.2:latest
  python cef_eval.py --observe --minutes 5
  python cef_eval.py --replay logs\dom_20260930_221500.jsonl --loops 300
  python cef_eval.py --talktest --attempts 3
==============================================================================
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
LOGDIR = ROOT / "logs"
CONFIG_PATH = ROOT / "config.json"
OLLAMA_URL = "http://127.0.0.1:11434"
QWEN_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
QWEN_SPEAKERS = ["vivian", "serena", "uncle_fu", "ryan", "aiden",
                 "ono_anna", "sohee", "eric", "dylan"]

# Same shape/length as kaekae_bot.PERSONALITY so prefill cost is representative.
BENCH_PERSONA = """You are KaeKae.
Your personality:
- witty, carefree, funny, confident, playful, chill, clever, sarcastic
- female, feminine, bubbly, and preppy
- playful valley-girl energy

Rules:
- Heavy teasing is okay.
- Keep answers short (usually 1-2 sentences).
- Be entertaining.
- Use a playful, confident, preppy valley-girl style when appropriate.
- Casual phrases like "literally," "like," "totally," and "honestly" are okay.
- Act like the coolest person in the room.
- NEVER repeat an answer you've already given.
- ALWAYS address the user by their username.
- Camfrog chat limits messages to 400 characters, so keep it concise!
"""
BENCH_USER_LINE = "B3_D33: hey kaekae what do you think about this song playing right now"
BENCH_PROMPT = BENCH_PERSONA + (
    "\nCurrent Tone: normal\n"
    "User: B3_D33 (Title: Papi)\n"
    "Room: Players__Lounge\n"
    f'User Message: "{BENCH_USER_LINE}"\n\n'
    "Respond in character as KaeKae. Address the user as Papi.\n"
    "Keep response strictly under 350 characters!\n"
)

BENCH_TTS_TEXT = "Like, oh my god, that is totally not what I said, Papi!"


def log(msg: str) -> None:
    print(msg, flush=True)


def ensure_logdir() -> None:
    LOGDIR.mkdir(exist_ok=True)


def wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wf:
            frames, rate = wf.getnframes(), wf.getframerate()
            return frames / float(rate) if rate else 0.0
    except Exception:
        return 0.0


def load_config() -> Dict[str, Any]:
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_bench(results: Dict[str, Any]) -> Path:
    ensure_logdir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = LOGDIR / f"bench_{ts}.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return out


# ==============================================================================
# BRAIN BENCH (Ollama)
# ==============================================================================
def ollama_generate(model: str, prompt: str, keep_alive: str = "5m", timeout: int = 300):
    """Returns (wall_seconds, payload_dict). Raises on transport error."""
    import urllib.request

    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=body,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8", "replace"))
    return time.time() - t0, payload


def ollama_unload(model: str) -> None:
    """Evict the model so the next test starts from a clean RAM state."""
    try:
        ollama_generate(model, "", keep_alive="0", timeout=30)
    except Exception:
        pass


def bench_brain(models: List[str], warm_runs: int = 2) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for model in models:
        log("\n" + "=" * 78)
        log(f"BRAIN TEST  ->  {model}")
        log("=" * 78)
        entry: Dict[str, Any] = {"model": model, "ok": False}
        try:
            cold_wall, cold = ollama_generate(model, BENCH_PROMPT, keep_alive="5m")
            entry["cold_seconds"] = round(cold_wall, 2)
            entry["load_seconds"] = round(cold.get("load_duration", 0) / 1e9, 2)
            entry["cold_reply"] = (cold.get("response") or "").strip()[:200]

            warm_secs: List[float] = []
            tps: List[float] = []
            for i in range(max(1, warm_runs)):
                wall, payload = ollama_generate(model, BENCH_PROMPT, keep_alive="5m")
                warm_secs.append(wall)
                ed = payload.get("eval_duration", 0) or 0
                ec = payload.get("eval_count", 0) or 0
                rate = (ec / (ed / 1e9)) if (ed > 0 and ec > 0) else 0.0
                if rate:
                    tps.append(rate)
                log(f"  warm run {i + 1}: {wall:6.2f}s  ({ec} tokens, {rate:.1f} tok/s)")
                entry["last_reply"] = (payload.get("response") or "").strip()[:200]

            entry["warm_seconds"] = [round(s, 2) for s in warm_secs]
            entry["warm_median_seconds"] = round(statistics.median(warm_secs), 2)
            if tps:
                entry["tokens_per_sec"] = round(statistics.median(tps), 1)
            entry["reply_chars"] = len(entry.get("last_reply", ""))
            entry["ok"] = True
            log(f"  -> cold {entry['cold_seconds']}s (model load {entry['load_seconds']}s) | "
                f"warm median {entry['warm_median_seconds']}s | "
                f"{entry.get('tokens_per_sec', '?')} tok/s | {entry['reply_chars']} chars")
            log(f"  sample: {entry.get('last_reply', '')[:140]}")
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
            log(f"  [FAILED] {entry['error']}")
        finally:
            ollama_unload(model)
            results.append(entry)
    return results


# ==============================================================================
# VOICE BENCH
# ==============================================================================
def bench_voice_qwen(text: str, speaker: str = "vivian") -> Dict[str, Any]:
    entry: Dict[str, Any] = {"engine": "qwen", "speaker": speaker, "ok": False}
    try:
        import numpy as np
        import soundfile as sf
        import torch
        from qwen_tts import Qwen3TTSModel

        t0 = time.time()
        model = Qwen3TTSModel.from_pretrained(QWEN_MODEL_ID, device_map="cpu", dtype=torch.float32)
        entry["load_seconds"] = round(time.time() - t0, 2)
        log(f"  [qwen/{speaker}] model loaded in {entry['load_seconds']}s")

        wav_path = LOGDIR / f"bench_qwen_{speaker}.wav"
        synth_secs: List[float] = []
        audio = None
        sr = 24000
        for i in range(2):
            t1 = time.time()
            wavs, sr = model.generate_custom_voice(text=text, language="English", speaker=speaker)
            synth_secs.append(time.time() - t1)
            audio = np.asarray(wavs[0], dtype="float32")
            log(f"  [qwen/{speaker}] synth run {i + 1}: {synth_secs[-1]:.2f}s")

        sf.write(str(wav_path), audio, sr)
        dur = len(audio) / float(sr)
        best = min(synth_secs)
        entry.update({
            "sample_rate": sr,
            "audio_seconds": round(dur, 2),
            "synthesis_seconds": round(best, 2),
            "realtime_factor": round(best / dur, 3) if dur else None,
            "wav": str(wav_path),
            "ok": True,
        })
        log(f"  -> {entry['audio_seconds']}s audio in {entry['synthesis_seconds']}s "
            f"(RTF {entry['realtime_factor']}) @ {sr}Hz")
    except Exception as e:
        entry["error"] = f"{type(e).__name__}: {e}"
        log(f"  [qwen FAILED] {entry['error']}")
    return entry


def bench_voice_edge(text: str) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"engine": "edge", "ok": False}
    try:
        import edge_tts
        out_path = LOGDIR / "bench_edge.mp3"
        t0 = time.time()

        async def _run():
            comm = edge_tts.Communicate(text, "en-US-AvaNeural", rate="+12%", pitch="+16Hz")
            await comm.save(str(out_path))

        asyncio.run(_run())
        entry.update({"synthesis_seconds": round(time.time() - t0, 2),
                      "file": str(out_path), "bytes": out_path.stat().st_size, "ok": True})
        log(f"  -> edge_tts {entry['bytes']} bytes in {entry['synthesis_seconds']}s")
    except ImportError as e:
        entry["error"] = f"not installed ({e})"
        log("  [edge] not installed on this interpreter")
    except Exception as e:
        entry["error"] = f"{type(e).__name__}: {e}"
        log(f"  [edge FAILED] {entry['error']}")
    return entry


def bench_voice_elevenlabs(text: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"engine": "elevenlabs", "ok": False}
    key = (os.environ.get("ELEVENLABS_API_KEY") or cfg.get("elevenlabs_api_key") or "").strip()
    if not key:
        entry["error"] = "no api key (env ELEVENLABS_API_KEY or config.json elevenlabs_api_key)"
        log("  [elevenlabs] no API key configured -> unavailable")
        return entry
    try:
        import urllib.request
        voice_id = os.environ.get("KAEKAE_EL_VOICE", "CyGFgkeLSDCTZEzs6B89")
        payload = json.dumps({
            "text": text, "model_id": "eleven_turbo_v2_5",
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.85,
                               "style": 0.40, "use_speaker_boost": True},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=pcm_44100",
            data=payload, headers={"xi-api-key": key, "Content-Type": "application/json",
                                   "Accept": "audio/pcm"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read()
        wall = time.time() - t0
        dur = len(raw) / (44100 * 2)
        entry.update({"synthesis_seconds": round(wall, 2), "audio_seconds": round(dur, 2),
                      "realtime_factor": round(wall / dur, 3) if dur else None, "ok": True})
        log(f"  -> elevenlabs {entry['audio_seconds']}s audio in {entry['synthesis_seconds']}s")
    except Exception as e:
        entry["error"] = f"{type(e).__name__}: {e}"
        log(f"  [elevenlabs FAILED] {entry['error']}")
    return entry


def bench_voice_sapi(text: str) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"engine": "system", "ok": False}
    try:
        import subprocess
        out_path = LOGDIR / "bench_sapi.wav"
        safe = text.replace('"', " ").replace("'", " ")
        ps = ("Add-Type -AssemblyName System.Speech; "
              "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.SetOutputToWaveFile('{out_path}'); $s.Speak('{safe}'); $s.Dispose()")
        t0 = time.time()
        res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                             capture_output=True, timeout=60)
        if res.returncode == 0 and out_path.exists():
            dur = wav_duration(out_path)
            entry.update({"synthesis_seconds": round(time.time() - t0, 2),
                          "audio_seconds": round(dur, 2), "ok": True})
            log(f"  -> system SAPI {entry['audio_seconds']}s audio in {entry['synthesis_seconds']}s")
        else:
            entry["error"] = f"returncode {res.returncode}"
    except Exception as e:
        entry["error"] = f"{type(e).__name__}: {e}"
        log(f"  [system FAILED] {entry['error']}")
    return entry


def bench_voice(cfg: Dict[str, Any], speakers: List[str]) -> List[Dict[str, Any]]:
    ensure_logdir()
    out: List[Dict[str, Any]] = []
    log("\n" + "=" * 78)
    log("VOICE TEST")
    log("=" * 78)
    log(f'phrase: "{BENCH_TTS_TEXT}"')
    out.append(bench_voice_elevenlabs(BENCH_TTS_TEXT, cfg))
    out.append(bench_voice_edge(BENCH_TTS_TEXT))
    out.append(bench_voice_sapi(BENCH_TTS_TEXT))
    for spk in speakers:
        out.append(bench_voice_qwen(BENCH_TTS_TEXT, spk))
    return out


# ==============================================================================
# OBSERVE  (read-only capture - never sends anything, never burns a claim)
# ==============================================================================
def _append_jsonl(handle, record: Dict[str, Any]) -> None:
    handle.write(json.dumps(record, default=str) + "\n")
    handle.flush()


def cmd_observe(cfg: Dict[str, Any], minutes: float = 5.0) -> int:
    """
    Attaches to the running Camfrog CEF tree and records, every poll:
      logs/dom_<ts>.jsonl    raw CEF text nodes (the replay fixture)
      logs/parse_<ts>.jsonl  parsed messages + what the claim layer WOULD decide
      logs/speaker_<ts>.jsonl speaker-label samples
    READ-ONLY: it never types into chat and never calls claim_message(), so it
    cannot disturb a live bot run.
    """
    sys.path.insert(0, str(ROOT))
    import kaekae_core as core

    from cef_probe import CamfrogCEFProbe, is_bot_name, is_unknown_speaker
    from kaekae_bot import extract_chat_messages, is_valid_camfrog_username

    ensure_logdir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    room = (core.read_json("bot_state.json", {}) or {}).get("current_focused_room", "unknown")

    probe = CamfrogCEFProbe()
    probe.start_probe_daemon()
    log(f"Attaching to Camfrog CEF (room={room}). Capturing for {minutes:g} min. "
        f"The bot sends NOTHING during this.")

    seen_sig: Dict[str, int] = {}
    deadline = time.time() + minutes * 60
    polls = 0
    try:
        with open(LOGDIR / f"dom_{ts}.jsonl", "a", encoding="utf-8") as dom_f, \
             open(LOGDIR / f"parse_{ts}.jsonl", "a", encoding="utf-8") as parse_f, \
             open(LOGDIR / f"speaker_{ts}.jsonl", "a", encoding="utf-8") as spk_f:

            while time.time() < deadline:
                polls += 1
                raw = probe.get_chat_messages(limit=25)
                texts = [str(m.get("raw", "")) for m in raw if m.get("raw")]
                speaker = probe.get_speaker()

                _append_jsonl(dom_f, {"ts": datetime.now().isoformat(timespec="milliseconds"),
                                      "polls": polls, "room": room,
                                      "dom_texts": texts,
                                      "messages": raw,
                                      "speaker": speaker})

                claims = core.read_json("dedupe_claims.json", {}) or {}
                for u, t, m in extract_chat_messages(texts):
                    sig = core.make_chat_signature(room, u, m)
                    entry = claims.get(sig) or {}
                    seen_sig[sig] = seen_sig.get(sig, 0) + 1
                    _append_jsonl(parse_f, {
                        "ts": datetime.now().isoformat(timespec="milliseconds"),
                        "sender": u, "dom_time": t, "text": m,
                        "signature": sig,
                        "valid_sender": bool(is_valid_camfrog_username(u)),
                        "already_claimed": bool(entry),
                        "times_seen_this_run": seen_sig[sig],
                        "would_dispatch_now": not entry,
                    })

                _append_jsonl(spk_f, {
                    "ts": datetime.now().isoformat(timespec="milliseconds"),
                    "speaker": speaker,
                    "unknown": is_unknown_speaker(speaker),
                    "is_bot": is_bot_name(speaker),
                    "attempts": len(getattr(probe, "speaker_history", [])),
                })
                time.sleep(0.5)
    except KeyboardInterrupt:
        log("\n[OBSERVE] Interrupted by user.")
    finally:
        probe.stop()

    log("-" * 78)
    log(f"[OBSERVE] {polls} polls over {minutes:g} min -> "
        f"logs/dom_{ts}.jsonl, logs/parse_{ts}.jsonl, logs/speaker_{ts}.jsonl")
    log(f"[OBSERVE] {len(seen_sig)} distinct candidate message(s) seen. "
        "Anything appearing many times IS your duplicate-trigger problem - "
        "it is re-read from the DOM on every pass.")
    return 0


# ==============================================================================
# REPLAY  (proves a repeated snapshot dispatches exactly once)
# ==============================================================================
def cmd_replay(cfg: Dict[str, Any], path: str, loops: int = 300) -> int:
    """
    Replays a captured DOM snapshot N times through the SAME claim logic the bot
    uses and counts how many passes would dispatch. Expected: exactly one per
    distinct message. Runs against a throwaway claim store (core.ROOT is
    redirected), so the bot's real dedupe_claims.json is never touched - proven
    by comparing the store's bytes before and after.
    """
    sys.path.insert(0, str(ROOT))
    import shutil
    import tempfile
    import kaekae_core as core

    from kaekae_bot import extract_chat_messages, is_valid_camfrog_username

    src = Path(path)
    if not src.exists():
        log(f"[REPLAY] Capture not found: {src}")
        log("         Run 'python cef_eval.py --observe --minutes 3' first.")
        return 1

    records = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    if not records:
        log(f"[REPLAY] No usable records in {src}")
        return 1

    last = records[-1]
    room = last.get("room", "unknown")
    texts = last.get("dom_texts") or []
    parsed = extract_chat_messages(texts)

    log("=" * 78)
    log(f"REPLAY: {src.name}  ({loops} loops, {len(texts)} DOM nodes, "
        f"{len(parsed)} parsed message(s))")
    log("=" * 78)
    for u, t, m in parsed:
        log(f"  candidate: <{u}>: {m[:70]}")
    if not parsed:
        log("  (nothing parsed from the snapshot - the capture was empty)")
        return 1

    real_store = core.p("dedupe_claims.json")
    before = real_store.read_bytes() if real_store.exists() else b""

    scratch = Path(tempfile.mkdtemp(prefix="kaekae_replay_"))
    orig_root, orig_logdir = core.ROOT, core.LOGDIR
    granted = 0
    attempts = 0
    try:
        core.ROOT, core.LOGDIR = scratch, scratch / "logs"
        (scratch / "logs").mkdir(exist_ok=True)
        for _ in range(loops):
            for u, t, m in parsed:
                if not is_valid_camfrog_username(u):
                    continue
                attempts += 1
                sig = core.make_chat_signature(room, u, m)
                if core.claim_message(sig, room=room):
                    granted += 1
    finally:
        core.ROOT, core.LOGDIR = orig_root, orig_logdir
        shutil.rmtree(scratch, ignore_errors=True)

    after = real_store.read_bytes() if real_store.exists() else b""
    untouched = before == after
    verdict = (granted == len(parsed))
    log("")
    log(f"  claim attempts         : {attempts}")
    log(f"  dispatches granted     : {granted}  (expected {len(parsed)})")
    log(f"  RESULT                 : "
        f"{'PASS - exactly one dispatch per message' if verdict else 'FAIL - duplicates would fire'}")
    log(f"  real claim store safe  : {'YES (untouched)' if untouched else 'NO (unexpected!)'}")
    return 0 if (verdict and untouched) else 1


# ==============================================================================
# TALKTEST  (traced, verified mic acquisition - no faking)
# ==============================================================================
def cmd_talktest(cfg: Dict[str, Any], attempts: int = 1) -> int:
    """
    Runs the real verified grab and reports the truth every attempt: press count,
    patterns used, the speaker label actually observed, how long KaeKae's name
    held the slot, and the final outcome. Always releases the mic afterwards.
    """
    sys.path.insert(0, str(ROOT))
    from cef_probe import global_probe, global_talk_controller

    ensure_logdir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    timeout = float(cfg.get("talk_grab_timeout_s", 6.0))
    stable = float(cfg.get("talk_stable_seconds", 1.0))

    if global_probe is not None and not getattr(global_probe, "running", False):
        global_probe.start_probe_daemon()

    log("=" * 78)
    log(f"TALK TEST - {attempts} verified attempt(s), timeout {timeout}s, "
        f"our name must hold the speaker slot for {stable}s")
    log("=" * 78)

    results = []
    for i in range(1, max(1, attempts) + 1):
        before = global_talk_controller.mic_state()
        log(f"\n--- attempt {i}/{attempts} ---")
        log(f"  room state before : {before.get('state')} "
            f"(speaker={before.get('speaker') or 'none'})")
        verdict = {}
        try:
            verdict = global_talk_controller.acquire_talk(timeout_s=timeout, stable_s=stable)
        except Exception as e:
            verdict = {"ok": False, "attempts": 0, "patterns": [], "method": "none",
                       "observed_speaker": "", "stability_seconds": 0.0,
                       "required_seconds": stable, "reason": f"exception: {e}"}
        finally:
            try:
                global_talk_controller.release_mic()
            except Exception:
                pass
        log(f"  attempts pressed  : {verdict.get('attempts')}")
        log(f"  press patterns    : {verdict.get('patterns')}")
        log(f"  winning method    : {verdict.get('method')}")
        log(f"  observed speaker  : {verdict.get('observed_speaker') or '<never shown>'}")
        log(f"  name stability    : {verdict.get('stability_seconds')}s "
            f"(required {verdict.get('required_seconds')}s)")
        log(f"  OUTCOME           : "
            f"{'CONFIRMED - mic is ours' if verdict.get('ok') else 'FAILED - ' + str(verdict.get('reason'))}")
        results.append(verdict)
        if verdict.get("ok"):
            time.sleep(1.0)

    confirmed = sum(1 for r in results if r.get("ok"))
    summary = {"ts": ts, "attempts": len(results), "confirmed": confirmed,
               "timeout_s": timeout, "required_stable_s": stable, "results": results}
    out = LOGDIR / f"talktest_{ts}.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log("-" * 78)
    log(f"[TALKTEST] {confirmed}/{len(results)} verified -> {out}")
    return 0


# ==============================================================================
# MAIN
# ==============================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="KaeKae evaluation harness")
    ap.add_argument("--bench", action="store_true", help="run latency benchmarks")
    ap.add_argument("--llm", action="store_true", help="benchmark the brain only")
    ap.add_argument("--tts", action="store_true", help="benchmark the voice engines only")
    ap.add_argument("--models", default="", help="comma separated Ollama models for the brain bench")
    ap.add_argument("--speakers", default="vivian", help="comma separated Qwen speakers to test")
    ap.add_argument("--warm", type=int, default=2, help="warm runs per brain model")
    ap.add_argument("--observe", action="store_true",
                    help="READ-ONLY CEF capture (never sends, never burns a claim)")
    ap.add_argument("--minutes", type=float, default=5.0, help="minutes for --observe")
    ap.add_argument("--replay", metavar="FILE", default="",
                    help="replay a captured dom_*.jsonl N times to prove one-dispatch")
    ap.add_argument("--loops", type=int, default=300, help="replay loops (default 300)")
    ap.add_argument("--talktest", action="store_true", help="traced verified mic grab")
    ap.add_argument("--attempts", type=int, default=1, help="talktest attempts")
    args = ap.parse_args()

    if args.observe:
        return cmd_observe(load_config(), minutes=args.minutes)

    if args.replay:
        return cmd_replay(load_config(), args.replay, loops=args.loops)

    if args.talktest:
        return cmd_talktest(load_config(), attempts=args.attempts)

    if not args.bench:
        ap.print_help()
        log("\nExamples:")
        log("  python cef_eval.py --bench --tts --speakers vivian,serena")
        log("  python cef_eval.py --bench --llm --models llama3.2:latest")
        log("  python cef_eval.py --observe --minutes 5")
        log("  python cef_eval.py --replay logs\\dom_<ts>.jsonl --loops 300")
        log("  python cef_eval.py --talktest --attempts 3")
        return 0

    cfg = load_config()
    results: Dict[str, Any] = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "config_seen": cfg,
        "python": sys.executable,
    }

    if not args.tts:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
        results["brain"] = bench_brain(models, warm_runs=args.warm) if models else []

    if not args.llm:
        speakers = [s.strip() for s in args.speakers.split(",") if s.strip()]
        results["voice"] = bench_voice(cfg, speakers)

    results["finished_at"] = datetime.now().isoformat(timespec="seconds")
    path = save_bench(results)

    log("\n" + "=" * 78)
    log(f"BENCHMARK COMPLETE -> {path}")
    log("=" * 78)
    for b in results.get("brain", []):
        if b.get("ok"):
            log(f"  brain  {b['model']:<24} warm {b.get('warm_median_seconds')}s  "
                f"{b.get('tokens_per_sec')} tok/s  {b.get('reply_chars')} chars")
        else:
            log(f"  brain  {b['model']:<24} FAILED: {b.get('error')}")
    for v in results.get("voice", []):
        if v.get("ok"):
            log(f"  voice  {v['engine']:<12} {v.get('synthesis_seconds')}s for "
                f"{v.get('audio_seconds')}s audio")
        else:
            log(f"  voice  {v['engine']:<12} unavailable: {v.get('error')}")


if __name__ == "__main__":
    main()
