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
  --observe          (added after Phase 3) read-only CEF DOM + parser + speaker
                     capture -> logs/dom_*.jsonl, logs/parse_*.jsonl
  --replay FILE      (added after Phase 3) replay a captured DOM snapshot N
                     times to prove the claim path dispatches exactly once.
  --talktest         (added after Phase 2) traced, verified mic acquisition.

Usage examples:
  python cef_eval.py --bench --tts
  python cef_eval.py --bench --llm --models llama3.2:latest --warm 2
  python cef_eval.py --bench --llm --models qwen3-coder:latest --warm 2
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
    args = ap.parse_args()

    if not args.bench:
        ap.print_help()
        return

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
