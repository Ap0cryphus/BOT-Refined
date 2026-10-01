#!/usr/bin/env python3
"""
================================================================================
KaeKae Bot - Decoupled Audio Filer & User Speech Archiver
================================================================================
Handles:
  - Immediate non-blocking storage of 7-second audio chunks into:
      audio_memory/usernames/<speaker_username>/clip_<timestamp>.wav
  - Appends to each user's personal speech log:
      audio_memory/usernames/<speaker_username>/session_log.jsonl
  - Dispatches to asynchronous Whisper worker without delaying audio ingest.
================================================================================
"""

import os
import sys
import time
import json
import wave
import shutil
import queue
import threading
from datetime import datetime
from typing import Optional, Dict, Any

try:
    import numpy as np
except ImportError:
    np = None

try:
    from audio_dsp import dsp_cleaner
except ImportError:
    dsp_cleaner = None

AUDIO_MEMORY_DIR = os.path.join("audio_memory", "usernames")
AUDIO_CLIPS_DIR = "audio_clips"

class UserAudioFiler:
    def __init__(self, base_dir: str = AUDIO_MEMORY_DIR):
        self.base_dir = base_dir
        self.clips_dir = AUDIO_CLIPS_DIR
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.clips_dir, exist_ok=True)
        self.filing_queue = queue.Queue(maxsize=1000)
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def sanitize_username(self, raw_name: str) -> str:
        """Sanitizes username for clean folder structure."""
        if not raw_name or raw_name.lower() in ("unknown", "unknown speaker", ""):
            return "unidentified_speaker"
        clean = "".join(c for c in raw_name if c.isalnum() or c in ("_", "-", "$")).strip()
        return clean or "unidentified_speaker"

    def enqueue_chunk(self, audio_data: bytes, speaker: str, sample_rate: int = 16000, peak: int = 0, tone: str = "neutral"):
        """Non-blocking submission of a 7-second audio chunk."""
        item = {
            "audio_bytes": audio_data,
            "speaker": self.sanitize_username(speaker),
            "sample_rate": sample_rate,
            "peak": peak,
            "tone": tone,
            "timestamp": datetime.now().strftime("%Y%m%dT%H%M%S_%f"),
            "display_time": time.strftime("%H:%M:%S")
        }
        try:
            self.filing_queue.put_nowait(item)
        except queue.Full:
            print("[WARN] Audio filing queue full; dropping old buffer.")

    def _worker_loop(self):
        while self.running:
            try:
                item = self.filing_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                speaker = item["speaker"]
                user_folder = os.path.join(self.base_dir, speaker)
                os.makedirs(user_folder, exist_ok=True)

                filename = f"clip_{item['timestamp']}.wav"
                user_filepath = os.path.join(user_folder, filename)
                master_filepath = os.path.join(self.clips_dir, filename)

                # Apply local DSP noise gate, rumble filter and normalization
                audio_to_write = item["audio_bytes"]
                dsp_stats = {}
                if dsp_cleaner is not None and np is not None:
                    try:
                        arr = np.frombuffer(item["audio_bytes"], dtype=np.int16)
                        cleaned_arr, dsp_stats = dsp_cleaner.clean_chunk(arr)
                        audio_to_write = cleaned_arr.tobytes()
                    except Exception as e_dsp:
                        print(f"[AUDIO FILER DSP] Cleanup warning: {e_dsp}")

                # Write master WAV
                with wave.open(master_filepath, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(item["sample_rate"])
                    wf.writeframes(audio_to_write)

                # Copy to user directory
                shutil.copy2(master_filepath, user_filepath)

                # Append to session ledger
                log_entry = {
                    "timestamp": item["display_time"],
                    "speaker": speaker,
                    "clip": filename,
                    "peak": item["peak"],
                    "tone": item["tone"],
                    "clean_peak": dsp_stats.get("peak_after", item["peak"]),
                    "noise_floor": dsp_stats.get("noise_floor", 0.0)
                }
                with open(os.path.join(user_folder, "session_log.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry) + "\n")

                print(f"[{item['display_time']}] 📁 FILED CLEAN AUDIO: '{speaker}' (Peak {item['peak']} -> {dsp_stats.get('peak_after', item['peak'])}) -> {user_filepath}")

            except Exception as e:
                print(f"[AUDIO FILER ERROR] Failed to file audio: {e}")
            finally:
                self.filing_queue.task_done()

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="AudioFilerThread")
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

# Global singleton
global_audio_filer = UserAudioFiler()
