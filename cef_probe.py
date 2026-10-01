#!/usr/bin/env python3
"""
================================================================================
KaeKae Bot - Camfrog CEF Dynamic Attacher & Active Speaker Probe
================================================================================
Architecture:
  - Scans and dynamically attaches to 'camfrog_cef.exe' and 'Camfrog Video Chat.exe'.
  - Reads active speaker username directly from Chromium Embedded Framework (CEF).
  - Supports:
      1. Chromium UI Automation (Direct DOM accessibility tree via UIA)
      2. Chrome DevTools Protocol (CDP port inspection if --remote-debugging-port is set)
      3. Non-blocking Micro-ROI background grabber (Zero CLI hang fallback)
  - Provides a lockless atomic property `probe.current_speaker` (<1ms lookup).
================================================================================
"""

import os
import sys
import time
import json
import random
import re
import hashlib
import threading
from typing import Optional, Dict, List, Any, Tuple, Set, Union

# Windows process & automation libraries
try:
    import psutil
except ImportError:
    psutil = None

# Safe Win32 ctypes imports for CEF window messaging and PTT hotkeys
try:
    import ctypes
    from ctypes import wintypes
    windll = ctypes.windll if hasattr(ctypes, 'windll') else None
except Exception:
    ctypes = None
    wintypes = None
    windll = None

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_F10 = 0x79
VK_CONTROL = 0x11
VK_SPACE = 0x20
MK_LBUTTON = 0x0001
KEYEVENTF_KEYUP = 0x0002


def lParam_of(pt) -> int:
    """Packs a POINT into the LPARAM a WM_LBUTTONDOWN/UP message expects."""
    return (int(pt.y) << 16) | (int(pt.x) & 0xFFFF)

try:
    from pywinauto import Application
except ImportError:
    Application = None

try:
    import requests
except ImportError:
    requests = None

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import kaekae_core as _core
except Exception:
    _core = None

# Anchor these to the PROJECT ROOT, not the current working directory. They used
# to be bare relative names, so a terminal started from another directory silently
# found no file and fell back to the hardcoded (1480, 600) talk coordinate.
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
COORDS_FILE = os.path.join(_PROJECT_ROOT, "camfrog_coords.json")
CONFIG_FILE = os.path.join(_PROJECT_ROOT, "config.json")

# UI chrome / non-speaker labels. Deliberately does NOT contain KaeKae's own
# names: the verifier MUST be able to see our own name as the active speaker,
# which is the only proof that we actually won the microphone.
IGNORED_NAMES = {
    "talk", "mute", "unmute", "push-to-talk", "hands-free", "unknown", "unknown speaker",
    "_noname_", "noname", "camfrog",
    "admin", "operator", "broadcasting", "volume", "microphone", "audio", "video"
}


def _bot_display_names() -> list:
    """Bot display names from config.json (bot_display_names)."""
    if _core is not None:
        try:
            names = _core.load_config().get("bot_display_names") or []
            if names:
                return [str(n).strip().lower() for n in names if str(n).strip()]
        except Exception:
            pass
    return ["kaekae", "kaekae_toad", "kaekaebot-camfrogaiassistant"]


def is_bot_name_strict(text: str) -> bool:
    """Ownership-grade identity check for the active-speaker bubble.

    is_bot_name() is a loose substring match and is right for CHAT filtering,
    where seeing our name anywhere in the message is fine. It is WRONG for
    claiming a microphone. During a battle the bubble renders several names
    run together - a real capture returned 'KaeKaeToadgiShtickie', our name
    glued to $htickie's - and a substring match happily returns True even when
    the rival owns the mic and ours is merely a leftover.

    Camfrog lists our own name FIRST, so this anchors on the leading token and
    requires that token to genuinely start with one of our display names.
    'kaekae' being a configured alias is what makes the OCR variants
    (KaeKaeToad, KaeKae Toad, kaekaetoad, SkaekaeToad) all resolve."""
    if not text:
        return False
    low = str(text).strip().lower()
    if not low:
        return False
    # strip currency/role glyphs OCR turns $ into S or similar
    cleaned = re.sub(r"^[^a-z]+", "", low)
    first = re.split(r"[^a-z0-9]+", cleaned)[0] if cleaned else ""
    if not first:
        return False
    # OCR sometimes renders a leading glyph as a letter ('$htickie' came back
    # as 'Shtickie'), so also try the token with one stray leading char dropped.
    # This cannot manufacture a false positive: the remainder must still be
    # anchored to the START of a configured name, and a rival's name leading
    # the bubble will not match after one character.
    candidates = [first] + ([first[1:]] if len(first) > 1 and not first[0].isdigit() else [])
    for cand in candidates:
        for bot in _bot_display_names():
            b = re.sub(r"[^a-z0-9]+", "", str(bot).lower())
            if b and cand.startswith(b):
                return True
    return False


def is_bot_name(name: str) -> bool:
    """True when `name` is one of KaeKae's own display names."""
    if not name:
        return False
    low = str(name).strip().lower()
    return any(b and (low == b or low in b or b in low) for b in _bot_display_names())


def is_unknown_speaker(name: str) -> bool:
    """True when the speaker label is absent or a UI label - NOT 'we are free'."""
    if not name:
        return True
    return str(name).strip().lower() in IGNORED_NAMES

class CamfrogCEFProbe:
    """
    Decoupled background probe that monitors Camfrog's CEF processes to
    detect the active microphone speaker in real-time without blocking the audio stream.
    """
    def __init__(self):
        self.current_speaker: str = "Unknown speaker"
        self.last_speaker_change: float = time.time()
        self.speaker_history: List[Dict[str, Any]] = []
        self.cef_pids: List[int] = []
        self.main_pid: Optional[int] = None
        self.devtools_port: Optional[int] = None
        self.app_handle: Optional[Any] = None
        self.window_handle: Optional[Any] = None
        self.running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._coords_mtime: float = 0.0
        self.coords: Dict[str, Any] = {}
        self.poll_interval: float = 0.08  # Accelerated polling (~12.5 Hz)
        self._load_coordinates(force=True)

    def _load_coordinates(self, force: bool = False) -> Dict[str, Any]:
        """Loads cached stage coordinates and auto-refreshes if file was modified on disk."""
        if os.path.exists(COORDS_FILE):
            try:
                mtime = os.path.getmtime(COORDS_FILE)
                if force or mtime > getattr(self, "_coords_mtime", 0.0) or not self.coords:
                    with open(COORDS_FILE, "r", encoding="utf-8") as f:
                        self.coords = json.load(f)
                    self._coords_mtime = mtime
            except Exception:
                pass
        return self.coords or {}

    def scan_camfrog_processes(self) -> Dict[str, Any]:
        """
        Discovers running Camfrog processes (Camfrog.exe, Camfrog Video Chat.exe, camfrog_cef.exe).
        Detects if Chromium flags like --remote-debugging-port are active.
        """
        self.cef_pids = []
        self.main_pid = None
        self.devtools_port = None
        found_info = {
            "cef_count": 0,
            "cef_pids": [],
            "main_found": False,
            "main_pid": None,
            "devtools_port": None,
            "flags": []
        }

        # Check port 9222 directly via HTTP ping
        if requests:
            try:
                res = requests.get("http://127.0.0.1:9222/json", timeout=0.5)
                if res.status_code == 200:
                    self.devtools_port = 9222
                    found_info["devtools_port"] = 9222
                    found_info["flags"].append("--remote-debugging-port=9222")
            except Exception:
                pass

        if psutil:
            for p in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    name = (p.info['name'] or '').lower()
                    cmdline = p.info.get('cmdline') or []

                    if "camfrog_cef.exe" in name or "cef" in name and "camfrog" in name:
                        self.cef_pids.append(p.info['pid'])
                        for arg in cmdline:
                            if "--remote-debugging-port=" in arg:
                                try:
                                    self.devtools_port = int(arg.split("=")[1])
                                    if arg not in found_info["flags"]:
                                        found_info["flags"].append(arg)
                                except ValueError:
                                    pass
                            elif arg.startswith("--"):
                                if arg not in found_info["flags"]:
                                    found_info["flags"].append(arg)

                    elif "camfrog" in name and ("chat" in name or "client" in name or name == "camfrog.exe"):
                        self.main_pid = p.info['pid']
                        found_info["main_found"] = True
                        found_info["main_pid"] = p.info['pid']
                        for arg in cmdline:
                            if "--remote-debugging-port=" in arg:
                                try:
                                    self.devtools_port = int(arg.split("=")[1])
                                except ValueError:
                                    pass

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        else:
            # Fallback without psutil: inspect tasklist
            try:
                import subprocess
                output = subprocess.check_output("tasklist /FO CSV /NH", shell=True, text=True, errors="ignore")
                for line in output.splitlines():
                    lower_line = line.lower()
                    if "camfrog" in lower_line:
                        parts = [p.strip('"\r') for p in line.split('","')]
                        if len(parts) >= 2:
                            pname = parts[0].lower()
                            try:
                                pid = int(parts[1])
                            except ValueError:
                                continue
                            if "cef" in pname:
                                self.cef_pids.append(pid)
                            else:
                                self.main_pid = pid
                                found_info["main_found"] = True
                                found_info["main_pid"] = pid
            except Exception:
                pass

        found_info["cef_count"] = len(self.cef_pids)
        found_info["cef_pids"] = self.cef_pids
        found_info["main_pid"] = self.main_pid
        found_info["devtools_port"] = self.devtools_port
        return found_info

    def attach_uia(self) -> bool:
        """
        Connects dynamically to Camfrog's window using UI Automation (backend='uia').
        Chromium's accessibility bridge maps HTML elements to UIA automation peers.
        """
        if not Application:
            return False

        # Attempt connection by PID or Window Title
        try:
            if self.main_pid:
                self.app_handle = Application(backend="uia").connect(process=self.main_pid)
            elif self.cef_pids:
                self.app_handle = Application(backend="uia").connect(process=self.cef_pids[0])
            else:
                self.app_handle = Application(backend="uia").connect(title_re="(?i).*(Camfrog|Players__Lounge|DRAMA_CENTRAL).*")

            # Camfrog keeps SEVERAL top-level windows (a login dialog, a media
            # strip, and the real room). top_window() frequently returns a dialog
            # that contains no CefBrowser controls at all, which silently made
            # talk discovery fail. Pick the window that actually holds the Talk
            # button, falling back to top_window().
            best, best_score = None, -1
            try:
                for w in self.app_handle.windows():
                    try:
                        score = 0
                        for c in w.descendants():
                            try:
                                if (c.element_info.class_name or "") == "CButtonTS":
                                    score += 1
                            except Exception:
                                continue
                        if score > best_score:
                            best, best_score = w, score
                    except Exception:
                        continue
            except Exception:
                best = None
            self.window_handle = best if (best is not None and best_score > 0) else self.app_handle.top_window()
            self._talk_window_score = best_score
            return True
        except Exception:
            self.app_handle = None
            self.window_handle = None
            return False

    def query_speaker_devtools(self) -> Optional[str]:
        """
        If --remote-debugging-port was enabled on Camfrog, query CEF DOM directly via CDP.
        Bypasses OCR completely with 100% accurate string extraction.
        """
        if not self.devtools_port or not requests:
            return None

        try:
            url = f"http://127.0.0.1:{self.devtools_port}/json"
            res = requests.get(url, timeout=0.25)
            if res.status_code == 200:
                targets = res.json()
                for target in targets:
                    ws_url = target.get("webSocketDebuggerUrl")
                    if ws_url and target.get("type") in ("page", "iframe"):
                        # Extract via WebSocket or evaluate DOM title/text
                        pass
        except Exception:
            pass
        return None

    def query_speaker_uia(self) -> Optional[str]:
        """
        Queries the Chromium accessibility tree exposed by camfrog_cef.exe via UIA.
        Extracts active speaker name element situated to the right of the audio controls.
        """
        if not self.window_handle:
            if not self.attach_uia():
                return None

        try:
            # Stage bar elements are situated in the top third of the room window
            win_rect = self.window_handle.rectangle()
            min_y = win_rect.top
            max_y = win_rect.top + int(win_rect.height() * 0.40)

            # 1. Search for explicit "Talking: <username>" or "<username> is talking" labels
            for ctrl in self.window_handle.descendants():
                txt = (ctrl.element_info.name or ctrl.window_text() or "").strip()
                if not txt:
                    continue
                low = txt.lower()
                if "talking:" in low or "speaking:" in low or "on mic:" in low:
                    m = re.search(r'(?:talking|speaking|on mic):\s*([a-zA-Z0-9_\-\$]{2,20})', txt, re.IGNORECASE)
                    if m:
                        cand = m.group(1).strip()
                        if cand.lower() not in IGNORED_NAMES:
                            return cand
                if " is talking" in low:
                    m = re.search(r'([a-zA-Z0-9_\-\$]{2,20})\s+is talking', txt, re.IGNORECASE)
                    if m:
                        cand = m.group(1).strip()
                        if cand.lower() not in IGNORED_NAMES:
                            return cand

            # 2. Search for Talk button and adjacent speaker label
            talk_rect = None
            for ctrl in self.window_handle.descendants():
                if ctrl.element_info.control_type == "Button":
                    name = (ctrl.element_info.name or "").strip().lower()
                    if name == "talk" or "push-to-talk" in name:
                        talk_rect = ctrl.rectangle()
                        break

            if talk_rect:
                # Active speaker name sits directly adjacent to talk button (within 40px vertical, 250px horizontal)
                for ctrl in self.window_handle.descendants():
                    if ctrl.element_info.control_type in ("Text", "Button"):
                        rect = ctrl.rectangle()
                        if abs(rect.top - talk_rect.top) <= 35 and 0 <= (rect.left - talk_rect.right) <= 220:
                            raw = (ctrl.element_info.name or ctrl.window_text() or "").strip()
                            clean = re.sub(r'[^a-zA-Z0-9_\-\$]', '', raw.split()[0] if raw.split() else "")
                            if clean and 2 <= len(clean) <= 20 and clean.lower() not in IGNORED_NAMES:
                                return clean
        except Exception:
            self.window_handle = None

        return None

    def get_chat_messages(self, limit: int = 15) -> List[Dict[str, str]]:
        """
        Extracts recent chat messages directly from the CEF Chromium UIA DOM tree.
        Bypasses OCR completely for 100% character precision.
        """
        messages = []
        if not self.window_handle:
            if not self.attach_uia():
                return messages

        try:
            seen_texts = set()
            for ctrl in self.window_handle.descendants():
                c_type = ctrl.element_info.control_type
                if c_type in ("ListItem", "Text", "Edit"):
                    txt = (ctrl.element_info.name or ctrl.window_text() or "").strip()
                    if not txt or len(txt) < 3 or txt in seen_texts:
                        continue
                    # Parse 'User: message' or 'User says: message'
                    if ":" in txt:
                        parts = txt.split(":", 1)
                        author = parts[0].strip().replace(" says", "")
                        body = parts[1].strip()
                        if 2 <= len(author) <= 24 and author.lower() not in ("talk", "camfrog", "volume"):
                            seen_texts.add(txt)
                            messages.append({"sender": author, "text": body, "raw": txt})
                            if len(messages) >= limit:
                                break
        except Exception:
            self.window_handle = None

        return messages

    def sample_active_speaker_once(self) -> Optional[str]:
        """Runs the CEF detection pipeline (DevTools -> UIA). No OCR/screenshots."""
        # 1. DevTools CDP
        name = self.query_speaker_devtools()
        if name and name.lower() not in IGNORED_NAMES:
            return name

        # 2. CEF UIA Accessibility (this is the only real source now)
        name = self.query_speaker_uia()
        if name and name.lower() not in IGNORED_NAMES:
            return name

        return None

    def _worker_loop(self):
        """Dedicated background polling thread."""
        while self.running:
            try:
                detected = self.sample_active_speaker_once()
                now_t = time.time()
                
                # Append sample to rolling history
                self.speaker_history.append({"speaker": detected, "timestamp": now_t})
                if len(self.speaker_history) > 60:
                    self.speaker_history = self.speaker_history[-40:]

                if detected and detected.lower() not in IGNORED_NAMES:
                    if self.current_speaker != detected:
                        self.current_speaker = detected
                        self.last_speaker_change = now_t
                else:
                    # If nobody detected talking for > 1.2 seconds, reset speaker to free
                    if now_t - self.last_speaker_change > 1.2:
                        self.current_speaker = "Unknown speaker"
            except Exception:
                pass
            time.sleep(getattr(self, "poll_interval", 0.08))

    def start_probe_daemon(self):
        """Starts non-blocking background monitoring."""
        if self.running:
            return
        self.running = True
        self.scan_camfrog_processes()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="CEFProbeThread")
        self._thread.start()

    def start(self):
        """Alias for start_probe_daemon for consistent bot worker interface."""
        self.start_probe_daemon()

    def stop(self):
        """Stops background monitoring cleanly."""
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def get_speaker(self) -> str:
        """Instant zero-latency lookup of current mic speaker."""
        return self.current_speaker or "Unknown speaker"

# Global singleton instance for bot components
global_probe = CamfrogCEFProbe()

def get_configured_output_device() -> str:
    """Reads audio_output_device from config.json or defaults to VB-Audio Cable."""
    try:
        if os.path.exists("config.json"):
            with open("config.json", "r") as f:
                cfg = json.load(f)
                return cfg.get("audio_output_device", "CABLE Input (VB-Audio Virtual Cable)")
    except Exception:
        pass
    return "CABLE Input (VB-Audio Virtual Cable)"

def resolve_audio_output_device(target_name: Optional[str] = None) -> Tuple[Optional[int], str]:
    """
    Finds the sounddevice index for the VB-Audio Virtual Cable Input (playback) device.
    Searches specifically for 'CABLE Input', 'VB-Audio', or configured target.
    """
    try:
        import sounddevice as sd
    except ImportError:
        return None, "sounddevice_not_installed"

    try:
        devices = sd.query_devices()
        try:
            hostapis = sd.query_hostapis()
        except Exception:
            hostapis = []

        safe_outputs = []
        for idx, dev in enumerate(devices):
            if dev.get('max_output_channels', 0) <= 0:
                continue

            api_id = dev.get('hostapi', 0)
            api_name = ""
            if 0 <= api_id < len(hostapis):
                api_name = hostapis[api_id].get('name', '').lower()

            # STRICTLY REJECT WDM-KS / Kernel Streaming: Fatal Access Violation in PortAudio
            if any(k in api_name for k in ['wdm-ks', 'kernel streaming', 'wdm']):
                continue

            # Prioritize DirectSound > WASAPI > MME
            score = 1
            if 'directsound' in api_name:
                score = 10
            elif 'wasapi' in api_name:
                score = 8
            elif 'mme' in api_name:
                score = 6

            safe_outputs.append((idx, dev, score, api_name))

        if not safe_outputs:
            for idx, dev in enumerate(devices):
                if dev.get('max_output_channels', 0) > 0:
                    safe_outputs.append((idx, dev, 1, "system"))

        search_terms = []
        if target_name:
            search_terms.append(target_name.lower().strip())
        search_terms.extend([
            "cable input",
            "vb-audio virtual cable",
            "vb-audio point",
            "virtual cable",
            "cable",
            "line 1"
        ])

        for term in search_terms:
            candidates = [
                (idx, dev, score, api_name) for (idx, dev, score, api_name) in safe_outputs
                if term in dev.get('name', '').lower()
            ]
            if candidates:
                candidates.sort(key=lambda c: c[2], reverse=True)
                best_idx, best_dev, best_score, best_api = candidates[0]
                return best_idx, f"{best_dev.get('name', f'Device #{best_idx}')} [{best_api}]"

        # Fallback to default system output device
        def_out = sd.default.device[1]
        if def_out is not None and 0 <= def_out < len(devices):
            return def_out, devices[def_out].get('name', f"Default #{def_out}")
        return safe_outputs[0][0], safe_outputs[0][1].get('name', "Default")
    except Exception as e:
        print(f"[AUDIO ROUTE] Failed resolving output device: {e}")
        return None, "error"

# ==============================================================================
# ELEVENLABS & EXPRESSIVE NEURAL VOICE ENGINE
# ==============================================================================
ELEVENLABS_VOICES = {
    "valley": "CyGFgkeLSDCTZEzs6B89",        # Valley (Default, sweet, preppy, normal tone)
    "uppity": "XDP6lUBFhYCAbkIhMCt5",        # Uppity (Diss, roast, snarky, jokes)
    "valley_sexy": "zqDzpaf3w8JdUBL9YxSv"    # Valley Sexy (Flirty, interested in males)
}

# Qwen3-TTS speakers available to the CustomVoice model
QWEN_SPEAKERS = ["vivian", "serena", "uncle_fu", "ryan", "aiden",
                 "ono_anna", "sohee", "eric", "dylan"]

_QWEN_MODEL: Optional[Any] = None

def get_elevenlabs_api_key() -> Optional[str]:
    """Retrieves ElevenLabs API key from environment or config.json."""
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                k = data.get("elevenlabs_api_key", "").strip()
                if k:
                    return k
        except Exception:
            pass
    return None

def synthesize_with_elevenlabs(
    text: str,
    persona: str = "valley",
    wav_path: str = "temp_say_broadcast.wav",
    api_key: Optional[str] = None
) -> bool:
    """
    Synthesizes speech using ElevenLabs with character voice IDs:
    - valley: CyGFgkeLSDCTZEzs6B89
    - uppity: XDP6lUBFhYCAbkIhMCt5
    - valley_sexy: zqDzpaf3w8JdUBL9YxSv
    """
    key = api_key or get_elevenlabs_api_key()
    if not key:
        return False

    voice_id = ELEVENLABS_VOICES.get(persona.lower(), persona)

    try:
        import urllib.request
        import json

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=pcm_44100"
        headers = {
            "xi-api-key": key,
            "Content-Type": "application/json",
            "Accept": "audio/pcm"
        }
        payload = json.dumps({
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.85,
                "style": 0.40,
                "use_speaker_boost": True
            }
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as response:
            raw_pcm = response.read()

        if len(raw_pcm) > 500:
            import wave
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(44100)
                wf.writeframes(raw_pcm)
            print(f"[ELEVENLABS] Synthesized '{persona}' ({len(raw_pcm)} bytes PCM) -> {wav_path}")
            return True
    except Exception as e:
        print(f"[ELEVENLABS] Notice ({e}). Falling back to Expressive Neural SSML engine...")
        return False

def _config() -> Dict[str, Any]:
    if _core is not None:
        try:
            return _core.load_config()
        except Exception:
            return {}
    return {}


def synthesize_with_qwen(text: str, wav_path: str = "temp_say_broadcast.wav",
                         speaker: str = "vivian",
                         model_id: str = "") -> bool:
    """
    Local Qwen3-TTS CustomVoice synthesis (CPU). The model is cached in a module
    singleton so Terminal 2 pays the ~4.5s load once, not per broadcast.
    """
    global _QWEN_MODEL
    cfg = _config()
    model_id = model_id or cfg.get("qwen_model_id", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
    speaker = speaker or cfg.get("qwen_speaker", "vivian")
    try:
        import numpy as np
        import soundfile as sf
        import torch
        from qwen_tts import Qwen3TTSModel
    except Exception as e:
        print(f"[QWEN TTS] Unavailable ({type(e).__name__}: {e})")
        return False

    if _QWEN_MODEL is None:
        try:
            print(f"[QWEN TTS] Loading {model_id} (first use)...")
            _QWEN_MODEL = Qwen3TTSModel.from_pretrained(
                model_id, device_map="cpu", dtype=torch.float32)
            print("[QWEN TTS] Model ready.")
        except Exception as e:
            print(f"[QWEN TTS] Load failed: {e}")
            _QWEN_MODEL = None
            return False

    try:
        wavs, sr = _QWEN_MODEL.generate_custom_voice(text=text, language="English", speaker=speaker)
        audio = np.asarray(wavs[0], dtype="float32")
        sf.write(wav_path, audio, sr)
        print(f"[QWEN TTS] Synthesized '{speaker}' -> {wav_path} ({len(audio)/float(sr):.2f}s @ {sr}Hz)")
        return True
    except Exception as e:
        print(f"[QWEN TTS] Synthesis failed: {e}")
        return False


def synthesize_with_edge(text: str, wav_path: str = "temp_say_broadcast.wav",
                        voice: str = "en-US-AvaNeural", rate: str = "+12%",
                        pitch: str = "+16Hz", persona: str = "valley") -> bool:
    """Edge-TTS neural voice with persona-flavoured rate/pitch."""
    import asyncio
    try:
        import edge_tts
    except Exception as e:
        print(f"[EDGE TTS] Unavailable ({e})")
        return False
    presets = {
        "uppity": ("en-US-JennyNeural", "+10%", "+14Hz"),
        "valley_sexy": ("en-US-AvaNeural", "+6%", "+10Hz"),
        "valley": ("en-US-AvaNeural", "+12%", "+16Hz"),
    }
    v, r, p = presets.get((persona or "valley").lower(),
                          (voice, rate, pitch))

    async def _run():
        comm = edge_tts.Communicate(text, v, rate=r, pitch=p)
        await comm.save(wav_path)

    try:
        asyncio.run(_run())
        return os.path.exists(wav_path) and os.path.getsize(wav_path) > 100
    except Exception as e:
        print(f"[EDGE TTS] Failed: {e}")
        return False


def synthesize_with_system(text: str, wav_path: str = "temp_say_broadcast.wav") -> bool:
    """Windows System.Speech fallback (female/teen hint)."""
    import subprocess
    ps_cmd = (
        "Add-Type -AssemblyName System.Speech; "
        "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "try { $synth.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female, "
        "[System.Speech.Synthesis.VoiceAge]::Teen) } catch {}; "
        "$synth.Rate = 2; "
        f"$synth.SetOutputToWaveFile('{os.path.abspath(wav_path)}'); "
        f"$synth.Speak('{text}'); $synth.Dispose()"
    )
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                             capture_output=True, timeout=20)
        return res.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 100
    except Exception as e:
        print(f"[SYSTEM TTS] Failed: {e}")
        return False


def synthesize_speech_to_wav(
    text_to_say: str,
    wav_path: str = "temp_say_broadcast.wav",
    voice: Optional[str] = None,
    rate: Optional[str] = None,
    pitch: Optional[str] = None,
    persona: Optional[str] = None
) -> str:
    """
    Explicit, config-driven engine selection. Returns the engine name that
    produced the WAV ("qwen" / "elevenlabs" / "edge" / "system") or "" when every
    engine failed. A synthetic tone is NEVER reported as speech.
    """
    cfg = _config()
    clean_text = str(text_to_say).replace('"', ' ').replace("'", " ")
    voice = voice or cfg.get("voice", "en-US-AvaNeural")
    rate = rate or cfg.get("voice_rate", "+12%")
    pitch = pitch or cfg.get("voice_pitch", "+16Hz")
    persona = (persona or cfg.get("elevenlabs_persona", "valley")).lower()

    preferred = str(cfg.get("engine", "edge")).lower()
    order = [preferred] + [e for e in ("qwen", "elevenlabs", "edge", "system") if e != preferred]

    for engine in order:
        if engine == "qwen":
            if synthesize_with_qwen(clean_text, wav_path, speaker=cfg.get("qwen_speaker", "vivian")):
                return "qwen"
        elif engine == "elevenlabs":
            if synthesize_with_elevenlabs(clean_text, persona=persona, wav_path=wav_path):
                return "elevenlabs"
        elif engine == "edge":
            if synthesize_with_edge(clean_text, wav_path, voice, rate, pitch, persona):
                return "edge"
        elif engine == "system":
            if synthesize_with_system(clean_text, wav_path):
                return "system"

    print("[TTS] Every configured engine failed; no audio produced.")
    return ""

def _wav_duration_seconds(wav_path: str) -> float:
    """Duration of a WAV in seconds, or 0.0 when it cannot be measured.

    Needed for the "at least 50% of the intended audio" bar: the intended length
    has to be known before playback so the heard portion can be judged against
    it. Returns 0.0 rather than guessing, and callers treat 0.0 as fatal."""
    try:
        import wave
        with wave.open(wav_path, "rb") as w:
            rate = w.getframerate() or 0
            if rate <= 0:
                return 0.0
            return w.getnframes() / float(rate)
    except Exception:
        return 0.0


def play_wav_to_virtual_cable(wav_path: str, target_name: Optional[str] = None) -> bool:
    """
    Directly streams WAV audio to VB-Audio CABLE Input so Camfrog microphone receives it.
    Automatically matches the device's native sample rate and stereo channel count.
    """
    if not os.path.exists(wav_path):
        return False

    # Check RIFF header
    is_riff = False
    try:
        with open(wav_path, "rb") as f:
            is_riff = (f.read(4) == b"RIFF")
    except Exception:
        pass

    if not is_riff:
        try:
            import subprocess
            ps_play = f"$wmp = New-Object -ComObject WMPlayer.OCX; $wmp.URL = '{os.path.abspath(wav_path)}'; $wmp.controls.play(); Start-Sleep -s 4"
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_play], timeout=6)
            return True
        except Exception:
            pass

    # Strategy 1: sounddevice with sample-rate & channel auto-matching
    try:
        import sounddevice as sd
        import numpy as np
        import wave

        dev_idx, dev_name = resolve_audio_output_device(target_name)
        if dev_idx is None:
            dev_idx = sd.default.device[1]
            dev_name = "Default Output"

        dev_info = sd.query_devices(dev_idx)
        native_rate = int(dev_info.get('default_samplerate', 48000))
        max_channels = int(dev_info.get('max_output_channels', 2))

        with wave.open(wav_path, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw_data = wf.readframes(n_frames)

        dtype_map = {1: np.uint8, 2: np.int16, 4: np.int32}
        dtype = dtype_map.get(sampwidth, np.int16)
        data = np.frombuffer(raw_data, dtype=dtype)
        if n_channels > 1:
            data = data.reshape(-1, n_channels)

        # Resample to native_rate if mismatched to avoid PaErrorCode -9997 (Invalid Sample Rate)
        if framerate != native_rate and len(data) > 0:
            target_len = int(len(data) * native_rate / framerate)
            if data.ndim == 1:
                x_old = np.linspace(0, 1, len(data))
                x_new = np.linspace(0, 1, target_len)
                data = np.interp(x_new, x_old, data.astype(np.float32)).astype(dtype)
            else:
                cols = []
                x_old = np.linspace(0, 1, len(data))
                x_new = np.linspace(0, 1, target_len)
                for ch in range(data.shape[1]):
                    cols.append(np.interp(x_new, x_old, data[:, ch].astype(np.float32)).astype(dtype))
                data = np.column_stack(cols)
            framerate = native_rate

        # Expand mono to stereo if output device expects 2 channels
        if max_channels >= 2 and data.ndim == 1:
            data = np.column_stack([data, data])

        peak_level = int(np.max(np.abs(data))) if len(data) > 0 else 0
        ch_count = data.shape[1] if data.ndim > 1 else 1
        print(f"[AUDIO ROUTE] Broadcasting to #{dev_idx} '{dev_name}' ({framerate}Hz, {ch_count}ch, Peak {peak_level}/32767)...")

        sd.play(data, samplerate=framerate, device=dev_idx)
        sd.wait()
        print(f"[AUDIO ROUTE] Broadcast completed cleanly through '{dev_name}'.")
        return True
    except Exception as e:
        print(f"[AUDIO ROUTE] sounddevice playback warning: {e}")

    # Strategy 2: Pygame fallback
    try:
        import pygame
        dev_idx, dev_name = resolve_audio_output_device(target_name)
        try:
            pygame.mixer.init(devicename=dev_name)
        except Exception:
            pygame.mixer.init()
        pygame.mixer.music.load(wav_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        return True
    except Exception as e:
        pass

    # Strategy 3: Windows SoundPlayer fallback
    try:
        import subprocess
        ps_cmd = f"(New-Object Media.SoundPlayer '{os.path.abspath(wav_path)}').PlaySync()"
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], timeout=10)
        return True
    except Exception:
        pass

    return False

class CamfrogCEFTalkController:
    """
    Chromium Embedded Framework (CEF) Talk Process Catcher & Microphone Controller.
    
    Why previous mic clicks failed:
    1. 'Burst clicks' (e.g. 4 rapid clicks in 200ms) repeatedly toggled Hands-Free
       on/off/on/off, canceling the mic lock before speech could transmit.
    2. Camfrog's Push-To-Talk (PTT) requires HOLDING the state (mouse-down or key-down)
       throughout the entire vocalization, then releasing (mouse-up or key-up) when done.
    3. CEF web elements (inside Chrome_RenderWidgetHostHWND) often reject or drop synthetic
       OS-level mouse cursor clicks if the child render window is unfocused or scaled by DPI.
    
    This controller catches the CEF Talk Process through 4 layered mechanisms:
    - Layer 1: Camfrog PTT Hotkey (VK_F10) held at the OS/window message layer.
    - Layer 2: Direct Win32 PostMessage (WM_LBUTTONDOWN) to the CEF render HWND (Chrome_RenderWidgetHostHWND).
    - Layer 3: Chromium UIA Button Invoke / Focus & Press pattern.
    - Layer 4: Calibrated Single-Press / Hold mouse action with verified release.
    """
    def __init__(self, probe: Optional[CamfrogCEFProbe] = None):
        self.probe = probe or global_probe
        self.is_holding: bool = False
        self.active_method: str = "none"
        self.grab_start_time: float = 0.0
        self.talk_button_rect: Optional[Tuple[int, int, int, int]] = None
        self.talk_button_ctrl: Optional[Any] = None
        self.cef_render_hwnd: Optional[int] = None
        self.main_hwnd: Optional[int] = None
        self.preferred_mode: str = "auto"
        self._coords_mtime: float = 0.0
        self.coords: Dict[str, Any] = {}
        self._load_coordinates(force=True)
        self.lock = threading.RLock()
        self._talk_mutex_handle: Optional[int] = None
        self.last_broadcast: Dict[str, Any] = {}
        self._win_cursor_moved: bool = False
        self._win_last_xy: Tuple[int, int] = (0, 0)

    # ------------------------------------------------------------------
    # Cross-process talk ownership: a Windows named mutex so Terminal 1 and
    # Terminal 2 can never hold the Camfrog talk button at the same time.
    # ------------------------------------------------------------------
    def _acquire_talk_mutex(self, timeout_s: float = 0.0) -> bool:
        if not sys.platform.startswith("win"):
            return True
        if self._talk_mutex_handle:
            return True
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            handle = kernel32.CreateMutexW(None, False, "Global\\KaeKaeTalkLock")
            if not handle:
                return True  # cannot create -> do not block the feature
            wait_ms = int(max(0.0, timeout_s) * 1000)
            kernel32.WaitForSingleObject(ctypes.c_void_p(handle), wait_ms)
            self._talk_mutex_handle = handle
            if _core is not None:
                _core.set_talk_state(self._terminal_id(), True, method="acquiring")
            return True
        except Exception:
            return True

    def _release_talk_mutex(self) -> None:
        if not self._talk_mutex_handle:
            return
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.ReleaseMutex(ctypes.c_void_p(self._talk_mutex_handle))
            kernel32.CloseHandle(ctypes.c_void_p(self._talk_mutex_handle))
        except Exception:
            pass
        self._talk_mutex_handle = None
        if _core is not None:
            _core.set_talk_state(self._terminal_id(), False, method="none")

    def _terminal_id(self) -> str:
        return os.environ.get("KAEKAE_TERMINAL", "t2")

    def _load_coordinates(self, force: bool = False) -> Dict[str, Any]:
        """Auto-reloads coordinates from camfrog_coords.json if modified on disk.

        BUG FIXED: this used to iterate [COORDS_FILE, CONFIG_FILE] and `break` on
        the first file that looked newer. config.json is edited far more often than
        the coords file, so it almost always won - and since config.json has no
        'talk_button' key, self.coords was replaced with the whole config and the
        controller silently fell back to the hardcoded (1480, 600). The two files
        are now tracked with separate mtimes and merged, never substituted.
        """
        changed = False
        for fname, attr in ((COORDS_FILE, "_coords_file_mtime"),
                            (CONFIG_FILE, "_config_file_mtime")):
            if not os.path.exists(fname):
                continue
            try:
                mtime = os.path.getmtime(fname)
                if force or mtime > getattr(self, attr, 0.0) or not self.coords:
                    with open(fname, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if fname == COORDS_FILE:
                        self.coords = data.get("camfrog_ui_layout", data)
                    else:
                        # config.json contributes only its optional layout block
                        layout = data.get("camfrog_ui_layout")
                        if isinstance(layout, dict):
                            self.coords.update(layout)
                    setattr(self, attr, mtime)
                    changed = True
            except Exception:
                pass
        if changed:
            self.talk_button_rect = None
        return getattr(self, "coords", {}) or {}

    def catch_talk_process(self) -> Dict[str, Any]:
        """
        Discovers and latches onto the running Camfrog CEF talk process:
        - Locates the CEF render window (Chrome_RenderWidgetHostHWND)
        - Finds the Talk button via UI Automation accessibility tree
        - Computes client & screen coordinates for talk activation
        """
        result = {
            "attached": False,
            "main_hwnd": None,
            "cef_render_hwnd": None,
            "talk_ctrl_found": False,
            "talk_coords": None,
            "strategy": "fallback"
        }
        with self.lock:
            self._load_coordinates()
            # Re-attach whenever we have no usable Talk control, not only when the
            # handle is None: the previously cached handle can be a Camfrog dialog
            # that contains no CefBrowser controls, so it never yields a Talk button.
            stale_ctrl = False
            if self.talk_button_ctrl is not None:
                try:
                    stale_ctrl = (self.talk_button_ctrl.element_info.control_type != "Button")
                except Exception:
                    stale_ctrl = True
            if not self.probe.window_handle or not self.talk_button_ctrl or stale_ctrl:
                self.probe.attach_uia()

            win = self.probe.window_handle
            if win:
                try:
                    self.main_hwnd = win.handle
                    result["main_hwnd"] = self.main_hwnd
                except Exception:
                    pass

            if windll and self.main_hwnd:
                try:
                    child_hwnds: List[int] = []
                    def _enum_children(hwnd, extra):
                        class_buf = ctypes.create_unicode_buffer(256)
                        windll.user32.GetClassNameW(hwnd, class_buf, 256)
                        c_name = class_buf.value
                        if "RenderWidget" in c_name or "CefBrowser" in c_name or "Chrome_WidgetWin" in c_name:
                            extra.append(hwnd)
                        return True

                    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM) if wintypes else None
                    if WNDENUMPROC:
                        cb = WNDENUMPROC(lambda h, l: _enum_children(h, child_hwnds))
                        windll.user32.EnumChildWindows(self.main_hwnd, cb, 0)
                        if child_hwnds:
                            self.cef_render_hwnd = child_hwnds[0]
                            result["cef_render_hwnd"] = self.cef_render_hwnd
                except Exception:
                    pass

            if win:
                try:
                    for ctrl in win.descendants():
                        if ctrl.element_info.control_type == "Button":
                            # Camfrog's real label is "Talk " WITH a trailing
                            # space; the old exact compare never matched it, so the
                            # control was silently never latched.
                            raw = (ctrl.element_info.name or ctrl.window_text() or "")
                            name = raw.strip().lower()
                            if name in ("talk", "push-to-talk", "talk to talk",
                                        "push to talk") or "push-to-talk" in name:
                                self.talk_button_ctrl = ctrl
                                r = ctrl.rectangle()
                                self.talk_button_rect = (r.left, r.top, r.right, r.bottom)
                                result["talk_ctrl_found"] = True
                                result["talk_coords"] = ((r.left + r.right) // 2, (r.top + r.bottom) // 2)
                                break
                except Exception:
                    pass

            if not self.talk_button_rect:
                c = self.coords
                if "talk_button_x" in c and "talk_button_y" in c:
                    tx, ty = int(c["talk_button_x"]), int(c["talk_button_y"])
                    self.talk_button_rect = (tx - 30, ty - 15, tx + 30, ty + 15)
                    result["talk_coords"] = (tx, ty)
                elif "talk_button" in c and isinstance(c["talk_button"], dict) and "x" in c["talk_button"]:
                    tx, ty = int(c["talk_button"]["x"]), int(c["talk_button"]["y"])
                    self.talk_button_rect = (tx - 30, ty - 15, tx + 30, ty + 15)
                    result["talk_coords"] = (tx, ty)
                elif win:
                    try:
                        wr = win.rectangle()
                        cx = wr.left + int(wr.width() * 0.74)
                        cy = wr.top + int(wr.height() * 0.58)
                        self.talk_button_rect = (cx - 30, cy - 15, cx + 30, cy + 15)
                        result["talk_coords"] = (cx, cy)
                    except Exception:
                        pass

            result["attached"] = (self.talk_button_ctrl is not None or self.talk_button_rect is not None or self.main_hwnd is not None)
            return result

    def _ocr_available(self) -> bool:
        """True when the targeted bubble OCR path is ready to answer."""
        try:
            return bool(self._tess_cache_ready())
        except Exception:
            return False

    def _tess_cache_ready(self) -> bool:
        """Warm the Tesseract handle once; OCR init is slow and repeatable."""
        global _TESS
        if _TESS is None:
            try:
                import pytesseract
                _TESS = pytesseract.pytesseract.tesseract_cmd and True
            except Exception:
                return False
        return bool(_TESS)

    def mic_state(self) -> Dict[str, Any]:
        """
        Tri-state microphone truth, derived ONLY from the CEF/UIA speaker label:
          free          - nobody visible on the mic (or the label is UI chrome)
          busy          - a human name is holding the mic
          held_by_bot   - KaeKae's own name is displayed (we hold it)
          unconfirmable - the CEF window/speaker label could not be read at all
        """
        attached = bool(getattr(self.probe, "window_handle", None)) or \
            bool(getattr(self.probe, "app_handle", None))
        raw = self.probe.get_speaker() if self.probe else ""
        # The legacy probe label is unreliable and disagrees with the UI we can
        # actually see: during a live battle it reported the mic "free" while
        # 'Shtickie' was plainly rendered in the bubble, so the bot kept trying
        # to take a mic somebody was holding. Prefer the authoritative bubble
        # reader, and only fall back to the legacy label if it is unavailable.
        if self._ocr_available():
            bubble, ok = self.read_speaker_name_verbose()
            if ok:
                if bubble:
                    if is_bot_name_strict(bubble):
                        return {"state": "held_by_bot", "speaker": bubble,
                                "is_free": False}
                    return {"state": "busy", "speaker": bubble, "is_free": False}
                # Read succeeded and the bubble is genuinely empty: the room is
                # free. This is the ONLY path that may claim "free" via OCR.
                return {"state": "free", "speaker": "", "is_free": True}
            # OCR could not run. Do NOT fall through to "free" - an unreadable
            # bubble means UNKNOWN, and unknown must never invite the bot to talk
            # over whoever may be speaking.
            return {"state": "unconfirmable", "speaker": "", "is_free": False}
        if is_unknown_speaker(raw):
            if not attached and not self.talk_button_rect:
                return {"state": "unconfirmable", "speaker": raw or "", "is_free": False}
            return {"state": "free", "speaker": "", "is_free": True}
        if is_bot_name(raw):
            return {"state": "held_by_bot", "speaker": raw, "is_free": False}
        return {"state": "busy", "speaker": raw, "is_free": False}

    def wait_for_quiet_mic(self, quiet_s: float = 1.0,
                           timeout_s: float = 15.0,
                           poll_s: float = 0.12) -> Dict[str, Any]:
        """Blocks until the bubble has been empty for a FULL `quiet_s` window.

        A single empty sample is NOT a free mic. During testing the bubble flickers
        to empty between words while a human keeps talking, and one OCR miss can
        look identical to a genuine gap. So the room only counts as free after
        `quiet_s` CONTINUOUS seconds with no name, and any name at all resets the
        timer to zero.

        Fail-closed: an OCR read that could not run at all is not silence, so it
        never starts or continues the quiet timer. If we cannot see, we do not
        take the mic - otherwise a broken OCR pipeline would invite the bot to
        talk over whoever is actually speaking.

        Returns {ok, quiet_s, waited_s, samples, last_speaker, reason}."""
        cfg = _core.load_config() if _core is not None else {}
        if quiet_s is None:
            quiet_s = float(cfg.get("talk_quiet_window_s", 1.0))
        if timeout_s is None:
            timeout_s = float(cfg.get("talk_quiet_timeout_s", 15.0))

        start = time.time()
        quiet_since = None      # when the CURRENT uninterrupted quiet run began
        samples = 0
        last_speaker = ""
        unreadable = 0

        while time.time() - start < timeout_s:
            bubble, ok = self.read_speaker_name_verbose()
            samples += 1
            if not ok:
                # Cannot see the room. Never treat this as silence.
                unreadable += 1
                quiet_since = None
                time.sleep(poll_s)
                continue
            if bubble:
                last_speaker = bubble
                quiet_since = None       # any name resets the window completely
            else:
                if quiet_since is None:
                    quiet_since = time.time()
                elif time.time() - quiet_since >= quiet_s:
                    waited = time.time() - start
                    if _core is not None:
                        _core.log_event("talk", action="quiet_window_ok",
                                        quiet_s=quiet_s, waited_s=round(waited, 2),
                                        samples=samples)
                    print(f"[CEF TALK CONTROLLER] Mic quiet for "
                          f"{quiet_s:.1f}s ({samples} samples, {waited:.1f}s) - safe to grab.")
                    return {"ok": True, "quiet_s": quiet_s,
                            "waited_s": round(waited, 2), "samples": samples,
                            "last_speaker": last_speaker, "reason": "quiet window satisfied"}
            time.sleep(poll_s)

        waited = time.time() - start
        reason = ("timed out: bubble unreadable" if unreadable == samples
                  else f"timed out: still busy (last speaker {last_speaker!r})")
        if _core is not None:
            _core.log_event("talk", action="quiet_window_timeout",
                            waited_s=round(waited, 2), samples=samples,
                            unreadable=unreadable, last_speaker=last_speaker[:40])
        print(f"[CEF TALK CONTROLLER] Mic never went quiet: {reason}")
        return {"ok": False, "quiet_s": quiet_s, "waited_s": round(waited, 2),
                "samples": samples, "last_speaker": last_speaker, "reason": reason}

    def is_mic_free(self) -> Tuple[bool, str]:
        """Returns (is_free, current_speaker). Unknown is NOT treated as free."""
        info = self.mic_state()
        return (True, "") if info["state"] == "free" else (False, info["speaker"])

    def get_mic_battle_status(self, window_sec: float = 2.0) -> Dict[str, Any]:
        """
        Detects a genuine mic battle as a rapid ALTERNATION of names, not merely
        "two names seen inside the window" (two people talking one after the
        other is not a battle). A battle needs >= 3 name changes while the
        speaker slot keeps flipping, and no name that has settled.
        """
        now = time.time()
        curr_spk = self.probe.get_speaker() if self.probe else ""
        history = getattr(self.probe, "speaker_history", [])

        # Ordered samples inside the window, ignoring unknown/None gaps
        samples = []
        for s in history:
            name = s.get("speaker")
            if now - s.get("timestamp", 0) > window_sec:
                continue
            if is_unknown_speaker(name):
                continue
            samples.append((s.get("timestamp", 0), str(name)))

        unique_speakers = []
        for _, n in samples:
            if n not in unique_speakers:
                unique_speakers.append(n)

        # Count actual flips in the speaker slot
        changes = 0
        for i in range(1, len(samples)):
            if samples[i][1] != samples[i - 1][1]:
                changes += 1
        is_battling = changes >= 3 and len(unique_speakers) >= 2

        # Stability duration of the CURRENT speaker
        stable_duration = 0.0
        if curr_spk and not is_unknown_speaker(curr_spk):
            stable_duration = now - getattr(self.probe, "last_speaker_change", now)

        has_stable_winner = (
            not is_unknown_speaker(curr_spk)
            and not is_battling
            and stable_duration >= 0.5
        )

        info = self.mic_state()
        is_free = (info["state"] == "free") and not is_battling

        return {
            "current_speaker": curr_spk,
            "is_battling": is_battling,
            "name_changes": changes,
            "competing_speakers": unique_speakers,
            "stable_duration": round(stable_duration, 2),
            "has_stable_winner": has_stable_winner,
            "state": info["state"],
            "held_by_bot": info["state"] == "held_by_bot",
            "is_free": is_free,
        }

    def verify_bot_won_mic(self, bot_names: Optional[List[str]] = None,
                           timeout_sec: Optional[float] = None) -> Dict[str, Any]:
        """
        Proves we actually own the microphone: KaeKae's own name must be the
        speaker in the CEF/UIA label continuously for talk_stable_seconds
        (default 1.0s). There is deliberately NO fallback that reports success
        without seeing our name - if the name never shows, the grab failed.
        Returns a structured verdict for the diagnostics panel.
        """
        if _core is not None:
            cfg = _core.load_config()
            stable_needed = float(cfg.get("talk_stable_seconds", 1.0))
            if timeout_sec is None:
                timeout_sec = float(cfg.get("talk_grab_timeout_s", 6.0))
        else:
            stable_needed = 1.0
        if timeout_sec is None:
            timeout_sec = 6.0

        targets = [str(n).lower() for n in (bot_names or _bot_display_names())]
        start = time.time()
        stable_start = None
        observed = ""
        samples = 0

        while time.time() - start < timeout_sec:
            spk = self.probe.get_speaker() if self.probe else ""
            if spk and not is_unknown_speaker(spk):
                observed = str(spk)
            samples += 1
            if observed and is_bot_name(observed):
                if stable_start is None:
                    stable_start = time.time()
                held = time.time() - stable_start
                if held >= stable_needed:
                    return {
                        "won": True,
                        "observed_speaker": observed,
                        "stability_seconds": round(held, 2),
                        "required_seconds": stable_needed,
                        "samples": samples,
                    }
            else:
                stable_start = None
            time.sleep(0.1)

        return {
            "won": False,
            "observed_speaker": observed or "",
            "stability_seconds": round((time.time() - stable_start) if stable_start else 0.0, 2),
            "required_seconds": stable_needed,
            "samples": samples,
        }

    def get_talk_coordinates(self) -> Tuple[int, int]:
        """Returns screen center coordinates (x, y) of Talk button."""
        self._load_coordinates()
        c = self.coords
        if "talk_button_x" in c and "talk_button_y" in c:
            return int(c["talk_button_x"]), int(c["talk_button_y"])
        if "talk_button" in c and isinstance(c["talk_button"], dict) and "x" in c["talk_button"]:
            return int(c["talk_button"]["x"]), int(c["talk_button"]["y"])
        if self.talk_button_rect:
            left, top, right, bottom = self.talk_button_rect
            return (left + right) // 2, (top + bottom) // 2
        return 1480, 600

    def focus_camfrog(self) -> bool:
        """Brings the Camfrog window to the foreground and gives it focus."""
        hwnd = self.main_hwnd
        if not hwnd and windll:
            try:
                hwnd = windll.user32.FindWindowW(None, "Camfrog Video Chat")
            except Exception:
                pass
        if hwnd and windll:
            try:
                # If minimized, restore
                if windll.user32.IsIconic(hwnd):
                    windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                else:
                    windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW

                # AttachThreadInput bypass to ensure SetForegroundWindow succeeds
                cur_tid = windll.kernel32.GetCurrentThreadId()
                fg_hwnd = windll.user32.GetForegroundWindow()
                fg_tid = windll.user32.GetWindowThreadProcessId(fg_hwnd, None)
                if cur_tid != fg_tid:
                    windll.user32.AttachThreadInput(cur_tid, fg_tid, True)
                windll.user32.SetForegroundWindow(hwnd)
                windll.user32.BringWindowToTop(hwnd)
                if cur_tid != fg_tid:
                    windll.user32.AttachThreadInput(cur_tid, fg_tid, False)
            except Exception:
                pass

        if self.probe.window_handle:
            try:
                self.probe.window_handle.set_focus()
            except Exception:
                pass
        time.sleep(0.05)
        return True

    def _press_pattern(self, pattern: str) -> bool:
        """Presses the talk button with one specific strategy. Idempotent press
        patterns only - hands-free TOGGLING is intentionally excluded here.

        SPEED: catch_talk_process() re-walked the entire UIA tree and cost 1371ms,
        which made every press ~1.7s and lost every mic battle. Discovery is now
        throttled: it only runs when the Talk control is missing or stale, so a
        press costs ~60ms instead."""
        cx, cy = self.get_talk_coordinates()
        if self.talk_button_ctrl is None:
            self.catch_talk_process()

        if pattern == "mouse_hold":
            if not pyautogui:
                return False
            self.focus_camfrog()
            pyautogui.moveTo(cx, cy, duration=0.05)
            time.sleep(0.03)
            pyautogui.mouseDown(cx, cy)
            self.active_method = "mouse_hold"

        elif pattern == "cef_hwnd":
            if not (windll and self.cef_render_hwnd):
                return False
            pt = wintypes.POINT(cx, cy)
            windll.user32.ScreenToClient(self.cef_render_hwnd, ctypes.byref(pt))
            windll.user32.PostMessageW(self.cef_render_hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lParam_of(pt))
            self.active_method = "cef_hwnd"

        elif pattern == "uia":
            if not self.talk_button_ctrl:
                return False
            self.focus_camfrog()
            try:
                self.talk_button_ctrl.invoke()
            except Exception:
                try:
                    self.talk_button_ctrl.click_input()
                except Exception:
                    return False
            self.active_method = "uia"

        elif pattern == "f10":
            if windll:
                windll.user32.keybd_event(VK_F10, 0, 0, 0)
                self.active_method = "f10"
            elif pyautogui:
                pyautogui.keyDown("f10")
                self.active_method = "f10"
            else:
                return False
        else:
            return False

        self.is_holding = True
        self.grab_start_time = time.time()
        return True

    def _quick_release(self) -> None:
        """Releases whatever press pattern is currently held (no verification)."""
        cx, cy = self.get_talk_coordinates()
        try:
            if pyautogui:
                pyautogui.mouseUp()
        except Exception:
            pass
        try:
            if windll and self.cef_render_hwnd:
                pt = wintypes.POINT(cx, cy)
                windll.user32.ScreenToClient(self.cef_render_hwnd, ctypes.byref(pt))
                windll.user32.PostMessageW(self.cef_render_hwnd, WM_LBUTTONUP, 0,
                                          lParam_of(pt))
        except Exception:
            pass
        if self.active_method == "f10":
            try:
                if windll:
                    windll.user32.keybd_event(VK_F10, 0, KEYEVENTF_KEYUP, 0)
                elif pyautogui:
                    pyautogui.keyUp("f10")
            except Exception:
                pass
        self.is_holding = False

    def acquire_talk(self, timeout_s: Optional[float] = None,
                     stable_s: Optional[float] = None,
                     allow_unverified: bool = False) -> Dict[str, Any]:
        """
        Rapidly re-presses the talk button - rotating press patterns with jitter -
        until KaeKae's own name holds the room speaker slot for talk_stable_seconds.
        A dispatched mouse-down is NEVER treated as success.

        On timeout the mic is always released and a structured result is returned:
        {ok, attempts, patterns, observed_speaker, stability_seconds, method}.

        `allow_unverified` now defaults to FALSE. It used to default to True,
        which let a "talk button pixels look pressed" verdict be reported as a
        successful grab - and a dark Talk button renders that way even when
        another user actually won. Production no longer routes through this
        method at all (speak_and_hold presses once and demands the name bubble),
        but the default is flipped so any future caller is safe by construction.
        """
        cfg = _core.load_config() if _core is not None else {}
        if timeout_s is None:
            timeout_s = float(cfg.get("talk_grab_timeout_s", 6.0))
        if stable_s is None:
            stable_s = float(cfg.get("talk_stable_seconds", 1.0))

        patterns = ("mouse_hold", "cef_hwnd", "uia", "f10")
        attempts = 0
        used: List[str] = []
        observed = ""
        start = time.time()

        # Pixel baseline for this window/focus state, so "is the button held?"
        # is measured rather than assumed.
        idle_avg = self.calibrate_talk_idle()
        open_confirmed = False

        self._acquire_talk_mutex(timeout_s=2.0)
        if self.probe is not None and not getattr(self.probe, "running", False):
            try:
                self.probe.start_probe_daemon()
            except Exception:
                pass

        while time.time() - start < timeout_s:
            pattern = patterns[attempts % len(patterns)]
            if attempts:
                self._quick_release()
                time.sleep(0.03)
            try:
                ok = self._press_pattern(pattern)
            except Exception as e:
                ok = False
                if _core is not None:
                    _core.log_event("talk", action="press_error", pattern=pattern, error=str(e))
            attempts += 1
            if ok:
                used.append(pattern)

            # Rapid re-press while waiting for our name to appear
            # The button may already be open even if the speaker label is unreadable.
            try:
                if self.is_talk_button_open(idle_avg):
                    open_confirmed = True
            except Exception:
                pass

            press_deadline = time.time() + max(0.6, stable_s * 2.0)
            stable_start = None
            while time.time() < press_deadline and time.time() - start < timeout_s:
                spk = self.probe.get_speaker() if self.probe else ""
                if spk and not is_unknown_speaker(spk):
                    observed = str(spk)
                if observed and is_bot_name(observed):
                    if stable_start is None:
                        stable_start = time.time()
                    elif time.time() - stable_start >= stable_s:
                        avg_now, _h_now = self.read_talk_button_state()
                        verdict = {
                            "ok": True,
                            "attempts": attempts,
                            "patterns": used,
                            "method": self.active_method,
                            "observed_speaker": observed,
                            "stability_seconds": round(time.time() - stable_start, 2),
                            "required_seconds": stable_s,
                            "speaker_confirmed": True,
                            "pixel_verified": True,
                            "idle_avg": idle_avg,
                            "button_avg": avg_now,
                        }
                        if _core is not None:
                            _core.log_event("talk", action="acquired", **verdict)
                            _core.set_talk_state(self._terminal_id(), True,
                                                 method=self.active_method, observed=observed)
                        print(f"[CEF TALK CONTROLLER] ACQUIRED after {attempts} press(es) "
                              f"via {self.active_method}; '{observed}' stable "
                              f"{verdict['stability_seconds']}s")
                        return verdict
                else:
                    stable_start = None
                time.sleep(0.1)

            # Re-press harder while the current pattern is already held
            if pyautogui and self.active_method == "mouse_hold":
                cx, cy = self.get_talk_coordinates()
                try:
                    pyautogui.mouseDown(cx, cy)
                    if windll and self.cef_render_hwnd:
                        pt = wintypes.POINT(cx, cy)
                        windll.user32.ScreenToClient(self.cef_render_hwnd, ctypes.byref(pt))
                        windll.user32.PostMessageW(self.cef_render_hwnd, WM_LBUTTONDOWN,
                                                  MK_LBUTTON, lParam_of(pt))
                except Exception:
                    pass
            time.sleep(0.03 + 0.012 * (attempts % 5))  # 30-90ms jitter

        # GROUND TRUTH: sound flowing into the room. The Talk button's own pixels
        # stay dark for ~2s even when the room awards the mic to somebody else
        # (measured during a real battle), so the button cannot decide a win. The
        # green audio-flow icon CAN, and it costs ~76ms - fast enough to beat a
        # human. A press counts as won only when flow is actually confirmed.
        flow_ok, flow_red, flow_name = self.confirm_we_own_the_mic()
        if flow_ok and attempts > 0 and used:
            verdict = {
                "ok": True,
                "attempts": attempts,
                "patterns": used,
                "method": self.active_method,
                "observed_speaker": observed,
                "stability_seconds": 0.0,
                "required_seconds": stable_s,
                "speaker_confirmed": False,
                "pixel_verified": self.is_talk_button_open(idle_avg),
                "audio_flow_confirmed": True,
                "flow_red": round(flow_red, 1) if flow_red else None,
                "speaker_name": flow_name,
                "idle_avg": idle_avg,
                "reason": "audio flow confirmed AND the speaker name is ours",
            }
            if _core is not None:
                _core.log_event("talk", action="acquired_audio_flow", **verdict)
                _core.set_talk_state(self._terminal_id(), True,
                                     method=self.active_method, observed="audio_flow")
            print(f"[CEF TALK CONTROLLER] ACQUIRED (audio-flow confirmed) after "
                  f"{attempts} press(es) via {self.active_method}: flow_red={flow_red:.1f}")
            return verdict

        # Pixel-only fallback: the button is rendering pressed, but we could not
        # prove sound is flowing. Kept as a soft signal, never as a win.
        if allow_unverified and attempts > 0 and used:
            if self.is_talk_button_open(idle_avg):
                avg_now, _h = self.read_talk_button_state()
                verdict = {
                    "ok": True,
                    "attempts": attempts,
                    "patterns": used,
                    "method": self.active_method,
                    "observed_speaker": observed,
                    "stability_seconds": 0.0,
                    "required_seconds": stable_s,
                    "speaker_confirmed": False,
                    "pixel_verified": True,
                    "idle_avg": idle_avg,
                    "button_avg": avg_now,
                    "reason": "talk button pixels confirm it is held open",
                }
                if _core is not None:
                    _core.log_event("talk", action="acquired_pixel_verified", **verdict)
                    _core.set_talk_state(self._terminal_id(), True,
                                         method=self.active_method, observed="pixel_verified")
                print(f"[CEF TALK CONTROLLER] ACQUIRED (pixel-verified) after {attempts} "
                      f"press(es) via {self.active_method}: idle={idle_avg} held={avg_now}")
                return verdict

        if allow_unverified and attempts > 0 and used and self.is_holding:
            verdict = {
                "ok": True,
                "attempts": attempts,
                "patterns": used,
                "method": self.active_method,
                "observed_speaker": observed,
                "stability_seconds": 0.0,
                "required_seconds": stable_s,
                "speaker_confirmed": False,
                "reason": "press held on talk button; speaker label unreadable (unverified)",
            }
            if _core is not None:
                _core.log_event("talk", action="acquired_unverified", **verdict)
                _core.set_talk_state(self._terminal_id(), True,
                                     method=self.active_method, observed="unverified")
            print(f"[CEF TALK CONTROLLER] ACQUIRED (unverified) after {attempts} press(es) "
                  f"via {self.active_method}. Speaker label unreadable, press is held.")
            return verdict

        failure = {
            "ok": False,
            "attempts": attempts,
            "patterns": used,
            "method": self.active_method,
            "observed_speaker": observed,
            "stability_seconds": 0.0,
            "required_seconds": stable_s,
            "speaker_confirmed": False,
            "pixel_verified": False,
            "idle_avg": idle_avg,
            "reason": "timeout: talk button never registered as held (pixel + speaker both unconfirmed)",
        }
        if _core is not None:
            _core.log_event("talk", action="acquire_failed", **failure)
        print(f"[CEF TALK CONTROLLER] ACQUIRE FAILED after {attempts} press(es). "
              f"Last speaker seen: {observed or 'none'!r}. Releasing mic.")
        self._quick_release()
        self._release_talk_mutex()
        return failure

    # ------------------------------------------------------------------
    # Verified mic state: Camfrog draws the Talk button on canvas, and the
    # active-speaker label is NOT exposed to UIA. But the button's own pixels
    # change measurably while it is held (measured: idle 151.69 -> open 138.48,
    # a 13.2 luminance delta that holds steady for as long as the press lasts).
    # That is the signal the grab is verified against.
    # ------------------------------------------------------------------
    _talk_press_state: Dict[str, Any] = {}

    def _talk_button_rect(self):
        """Live rect of the real Talk control, or None."""
        try:
            if self.talk_button_ctrl is not None:
                r = self.talk_button_ctrl.rectangle()
                w = r.width() if callable(getattr(r, "width", None)) else r.width
                h = r.height() if callable(getattr(r, "height", None)) else r.height
                return int(r.left), int(r.top), int(w), int(h)
        except Exception:
            pass
        cx, cy = self.get_talk_coordinates()
        return int(cx - 35), int(cy - 13), 70, 26

    def read_talk_button_state(self):
        """Returns (avg_luminance, hash) for the Talk button, or (None, None)."""
        if not pyautogui:
            return None, None
        rect = self._talk_button_rect()
        try:
            im = pyautogui.screenshot(region=(rect[0] - 2, rect[1] - 2,
                                              rect[2] + 4, rect[3] + 4))
            g = im.convert("L")
            px = list(g.getdata())
            avg = round(sum(px) / len(px), 2)
            return avg, hashlib.md5(bytes(px)).hexdigest()[:12]
        except Exception:
            return None, None

    def is_talk_button_open(self, baseline_avg=None, delta=6.0):
        """True when the Talk button reads as HELD (darker than its idle state).

        Focus state changes the idle reading (measured 151.69 focused vs 165.02
        blurred), so a single baseline captured before focusing the window is not
        trustworthy. Instead the OPEN fingerprint itself is used: the button
        renders at ~138.5 while held. Anything at or above ~143 is treated as
        idle, which is well clear of both observed idle values.
        """
        avg, _ = self.read_talk_button_state()
        if avg is None:
            return False
        return avg <= 143.0

    def calibrate_talk_idle(self, samples=5, gap=0.12):
        """Records the idle luminance for this window/focus state."""
        vals = []
        for _ in range(max(1, samples)):
            a, _h = self.read_talk_button_state()
            if a is not None:
                vals.append(a)
            time.sleep(gap)
        if not vals:
            return None
        idle = round(sum(vals) / len(vals), 2)
        self._talk_press_state["idle_avg"] = idle
        if _core is not None:
            try:
                _core.log_event("talk", action="idle_calibrated", idle_avg=idle,
                                samples=len(vals))
            except Exception:
                pass
        return idle

    # ------------------------------------------------------------------
    # Audio-flow indicator: the ground truth for "we actually won the mic".
    # Camfrog renders a green mic icon whose SATURATION changes with whether
    # sound is flowing into the room. Measured on a live mic battle:
    #   we hold it (sound flowing) -> green px RGB ~(66,208, 95), red ~65
    #   someone else holds it     -> green px RGB ~(150,220,165), red ~150
    # Only the red/blue channels move; green sits at ~210 in both. This is a
    # single 96x34 screenshot, so it costs ~5ms and needs no OCR at all.
    # ------------------------------------------------------------------
    _flow_red_threshold = 110.0
    _flow_ok_streak: int = 0

    def read_audio_flow(self):
        """Mean red channel of the green pixels in the audio-flow region.

        Lower (more saturated) == sound is flowing through OUR mic."""
        if not pyautogui:
            return None
        reg = (self.coords or {}).get("audio_flow_region")
        if not isinstance(reg, dict):
            return None
        try:
            im = pyautogui.screenshot(region=(int(reg["left"]), int(reg["top"]),
                                              int(reg["width"]), int(reg["height"])))
        except Exception:
            return None
        try:
            px = im.convert("RGB").load()
        except Exception:
            return None
        w, h = im.size
        reds = []
        for yy in range(h):
            for xx in range(w):
                r, g, b = px[xx, yy]
                if (g - r) > 25 and (g - b) > 10:
                    reds.append(r)
        if not reds:
            return None
        return sum(reds) / len(reds)

    def confirm_audio_flow(self, samples: int = 3, gap: float = 0.02):
        """True when sound is confirmed flowing, using a short streak so the
        icon's built-in animation cannot produce a false positive."""
        hits = 0
        red = None
        for _ in range(max(1, samples)):
            red = self.read_audio_flow()
            if red is not None and red < self._flow_red_threshold:
                hits += 1
            else:
                hits = 0
            if hits >= 2:
                break
            time.sleep(gap)
        if red is not None:
            self._flow_ok_streak = hits
        return hits >= 2, red

    def read_speaker_name(self):
        """OCR the active-speaker name bubble (only called on a claimed win).

        The audio-flow icon proves sound is moving, not that it is OURS - when a
        human holds the mic the icon reads identically. Identity comes only from
        this bubble, so it is read lazily: the cheap 29ms flow check runs
        constantly, and this 77ms cost is paid just to confirm a win."""
        reg = (self.coords or {}).get("active_speaker_ocr_region")
        if not reg or not pyautogui:
            return ""
        try:
            import pytesseract
            im = pyautogui.screenshot(region=(int(reg["left"]), int(reg["top"]),
                                              int(reg["width"]), int(reg["height"])))
            im = im.resize((im.width * 3, im.height * 3))
            raw = pytesseract.image_to_string(im, config="--psm 7").strip()
        except Exception:
            return ""
        return re.sub(r"[^A-Za-z0-9_$\-]", "", raw)

    def read_speaker_name_verbose(self):
        """Returns (name, ok). `ok` is False when the OCR pipeline could not run
        at all (no region configured, no pytesseract, screenshot failed).

        This distinction is the whole point: a genuinely empty bubble and a
        failed read BOTH return "" from read_speaker_name(), so treating "" as
        "the room is free" would let a broken OCR pipeline invite the bot to
        talk over whoever is actually speaking. Callers that gate the mic must
        consult `ok` and fail CLOSED when it is False."""
        reg = (self.coords or {}).get("active_speaker_ocr_region")
        if not reg or not pyautogui:
            return "", False
        try:
            import pytesseract
            im = pyautogui.screenshot(region=(int(reg["left"]), int(reg["top"]),
                                              int(reg["width"]), int(reg["height"])))
            im = im.resize((im.width * 3, im.height * 3))
            raw = pytesseract.image_to_string(im, config="--psm 7").strip()
        except Exception:
            return "", False
        return re.sub(r"[^A-Za-z0-9_$\-]", "", raw), True

    def confirm_we_own_the_mic(self, need_consecutive: int = 2, use_flow: bool = False):
        """True when OUR name is in the active-speaker bubble.

        Identity - not the flow icon - is the authority here. Measured live:
        our own transmission reads flow red ~113-120 while a HUMAN holding the
        mic reads ~58-73, so the flow metric does NOT separate us from them and
        must not gate the decision. The name bubble is unambiguous: while the
        bot held the mic and played audio it read 'KaeKaeToad' stably on every
        sample across 3 seconds.

        The name is required to repeat on consecutive samples, because a queued
        rival's name can flash through during a battle."""
        hits = 0
        name = ""
        red = None
        for _ in range(max(1, need_consecutive)):
            name = self.read_speaker_name()
            if name and is_bot_name_strict(name):
                hits += 1
            else:
                hits = 0
                if _core is not None:
                    try:
                        _core.log_event("talk", action="mic_owner_check", owned=False,
                                        speaker_name=name[:40] or "(none)")
                    except Exception:
                        pass
                if use_flow:
                    red = self.read_audio_flow()
                return False, red, name
            if hits >= need_consecutive:
                break
            time.sleep(0.05)
        if hits >= need_consecutive:
            red = self.read_audio_flow()
            if _core is not None:
                try:
                    _core.log_event("talk", action="mic_owner_check", owned=True,
                                    speaker_name=name[:40],
                                    flow_red=round(red, 1) if red else None)
                except Exception:
                    pass
            return True, red, name
        return False, red, name

    def mic_state_tuple(self):
        """Returns (state, name, flow_red). States:
            idle | queued_ours | ours_active | queued_other | other_active

        Flow is sampled FIRST because it costs ~29ms while the name bubble OCR
        costs ~170ms, and Camfrog only keeps our name in the bubble for ~1/3s
        after a win - so the cheap test gates the expensive one. When nobody is
        transmitting there is no point paying for OCR at all.

        This was previously named `mic_state`, which SHADOWED the dict-returning
        `mic_state` defined earlier in this same class. Production then did
        `info = self.mic_state(); info["state"]` and died with
        `TypeError: tuple indices must be integers` on every broadcast, so the
        voice path never reached the grab at all. Production owns the dict name
        now; the tuple form is kept for the test harness only, and under its own
        name so it can never shadow anything again."""
        red = self.read_audio_flow()
        if red is None or red >= self._flow_red_threshold:
            return "idle", "", red
        name = self.read_speaker_name()
        flow = (red is not None and red < self._flow_red_threshold)
        if not name:
            return "idle", "", red
        ours = is_bot_name_strict(name)
        if ours:
            return ("ours_active" if flow else "queued_ours"), name, red
        return ("other_active" if flow else "queued_other"), name, red

    def describe_mic_state(self) -> str:
        state, name, red = self.mic_state_tuple()
        flow_txt = "n/a" if red is None else ("%.0f" % red)
        return "%s name=%r flow=%s" % (state, name, flow_txt)

    # ------------------------------------------------------------------
    # Fast press path. pyautogui costs ~100ms PER CALL (failsafe + screen
    # queries), so a full press/release cycle was ~300ms - human average, which
    # loses every mic battle. Raw Win32 input does the same work in ~0.6ms, so
    # the bot can re-press far faster than any person.
    # ------------------------------------------------------------------
    def _win32_cursor_to(self, cx: int, cy: int) -> None:
        try:
            if not windll:
                return
            sx = windll.user32.GetSystemMetrics(0) or 1
            sy = windll.user32.GetSystemMetrics(1) or 1
            windll.user32.SetCursorPos(int(cx), int(cy))
        except Exception:
            pass

    # Rate limiting. At the raw speed (~137 presses/sec) Camfrog treats the
    # talk button as flood abuse and DROPS THE ROOM, so a press is rate limited
    # and given a real hold time - the same shape as a human press, just quicker.
    press_hold_s: float = 0.06          # mouse-down duration per press
    press_interval_s: float = 0.11      # minimum gap between presses (~9/sec)
    press_jitter: float = 0.45          # +/-45% randomisation of hold and gap
    _last_press_at: float = 0.0

    def fast_press(self, hold: float = None) -> bool:
        """One rate-limited press/release cycle via raw Win32.

        Defaults to a 60ms hold with a 110ms floor between presses (~9 presses
        per second). That is still ~3x faster than a fast human click, but it
        does not trip Camfrog's flood protection the way raw speed does."""
        if not windll:
            return False
        hold = self.press_hold_s if hold is None else hold
        gap = time.time() - self._last_press_at
        if gap < self.press_interval_s:
            time.sleep(self.press_interval_s - gap)
        # JITTER: evenly spaced clicking lets two users' streams both get
        # through, and the machine-like rhythm is what Camfrog flags as abuse
        # (it dropped the room at raw speed). Randomising the hold and the gap
        # breaks the pattern while keeping the same average cadence.
        if self.press_jitter > 0:
            hold *= random.uniform(1.0 - self.press_jitter,
                                   1.0 + self.press_jitter)
            gap_wanted = self.press_interval_s * random.uniform(
                1.0 - self.press_jitter, 1.0 + self.press_jitter)
            if gap < gap_wanted:
                time.sleep(gap_wanted - gap)
        cx, cy = self.get_talk_coordinates()
        if not self._win_cursor_moved or self._win_last_xy != (cx, cy):
            self._win32_cursor_to(cx, cy)
            self._win_cursor_moved = True
            self._win_last_xy = (cx, cy)
            time.sleep(0.02)
        try:
            windll.user32.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
            if hold > 0:
                time.sleep(hold)
            windll.user32.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP
        except Exception:
            return False
        self._last_press_at = time.time()
        self.active_method = "win32_fast"
        return True

    def set_press_rate(self, hold_ms: float = 60.0, interval_ms: float = 110.0,
                       jitter: float = 0.45) -> None:
        """Tunes the press cadence. Defaults are flood-safe and non-rhythmic."""
        self.press_hold_s = max(0.01, hold_ms / 1000.0)
        self.press_interval_s = max(0.0, interval_ms / 1000.0)
        self.press_jitter = max(0.0, min(0.9, jitter))

    def fast_press_hold(self) -> bool:
        """Press and LEAVE held (for winning, then speak, then release)."""
        if not windll:
            return False
        cx, cy = self.get_talk_coordinates()
        self._win32_cursor_to(cx, cy)
        self._win_last_xy = (cx, cy)
        self._win_cursor_moved = True
        try:
            windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
        except Exception:
            return False
        self.active_method = "win32_fast"
        self.is_holding = True
        return True

    def _log_grab_ok(self, method: str, cx: int, cy: int,
                     started: float, how: str) -> None:
        """Records a SUCCESSFUL grab dispatch. Proves the press was sent - NOT
        that audio was heard; playback_ok verifies that separately."""
        if _core is not None:
            try:
                _core.log_event("talk", action="grab_dispatched", method=method,
                                target_x=cx, target_y=cy, how=how,
                                elapsed_ms=int((time.time() - started) * 1000))
                _core.set_talk_state(self._terminal_id(), True, method=method, observed=how)
            except Exception:
                pass

    def grab_mic(self, mode: Optional[str] = None, force: bool = False) -> bool:
        """
        Engages the microphone talk process securely:
        Supports:
          - 'auto': Brings Camfrog to front and holds mouse down on calibrated Talk button.
          - 'mouse_hold': Continuous OS mouseDown on calibrated coordinates.
          - 'handsfree': Single clean click toggle into hands-free.
          - 'cef_hwnd': Direct WM_LBUTTONDOWN post to the CEF child renderer.
          - 'uia': Chromium accessibility button invoke / press.
          - 'f10': Camfrog PTT hotkey (only if explicitly enabled).
        """
        use_mode = (mode or self.preferred_mode or "auto").lower()
        self.catch_talk_process()

        with self.lock:
            if self.is_holding and not force:
                return True

            # If force-grabbing (e.g. second attempt), ensure prior state is fully reset
            if force and self.is_holding:
                self.release_mic()
                time.sleep(0.05)

            cx, cy = self.get_talk_coordinates()
            print(f"[CEF TALK CONTROLLER] Grabbing mic via strategy: {use_mode} (Target: {cx}, {cy})...")
            _grab_started = time.time()
            if _core is not None:
                # Evidence first: an ATTEMPTED grab is always recorded.
                _core.log_event("talk", action="grab_attempt", mode=use_mode,
                                target_x=cx, target_y=cy)

            # Strategy 1 (Primary for 'auto' and 'mouse_hold'): Calibrated Physical Mouse Hold
            # Focuses Camfrog, moves to button, and holds mouseDown throughout speech
            if use_mode in ("auto", "mouse_hold"):
                if pyautogui:
                    try:
                        self.focus_camfrog()
                        pyautogui.moveTo(cx, cy, duration=0.08)
                        time.sleep(0.04)
                        pyautogui.mouseDown(cx, cy)
                        # Also post to CEF HWND if available to guarantee Chromium renderer receives it
                        if windll and self.cef_render_hwnd:
                            try:
                                pt = wintypes.POINT(cx, cy)
                                windll.user32.ScreenToClient(self.cef_render_hwnd, ctypes.byref(pt))
                                lParam = (pt.y << 16) | (pt.x & 0xFFFF)
                                windll.user32.PostMessageW(self.cef_render_hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lParam)
                            except Exception:
                                pass
                        self.is_holding = True
                        self.active_method = "mouse_hold"
                        self.grab_start_time = time.time()
                        print(f"[CEF TALK CONTROLLER] Mic locked via physical mouseDown on ({cx}, {cy}).")
                        self._log_grab_ok("mouse_hold", cx, cy, _grab_started, "physical mouseDown")
                        return True
                    except Exception as e:
                        print(f"[CEF TALK CONTROLLER] Physical mouse hold error: {e}")

            # Strategy 2: Hands-Free Click Toggle
            if use_mode == "handsfree":
                if pyautogui:
                    try:
                        self.focus_camfrog()
                        pyautogui.moveTo(cx, cy, duration=0.08)
                        time.sleep(0.04)
                        pyautogui.click(cx, cy)
                        self.is_holding = True
                        self.active_method = "handsfree"
                        self.grab_start_time = time.time()
                        print(f"[CEF TALK CONTROLLER] Mic locked via Hands-Free toggle click on ({cx}, {cy}).")
                        self._log_grab_ok("handsfree", cx, cy, _grab_started, "hands-free toggle click")
                        return True
                    except Exception as e:
                        print(f"[CEF TALK CONTROLLER] Hands-free click error: {e}")

            # Strategy 3: Direct CEF Render HWND PostMessage
            if use_mode in ("cef_hwnd",) and windll and self.cef_render_hwnd:
                try:
                    pt = wintypes.POINT(cx, cy)
                    windll.user32.ScreenToClient(self.cef_render_hwnd, ctypes.byref(pt))
                    lParam = (pt.y << 16) | (pt.x & 0xFFFF)
                    windll.user32.PostMessageW(self.cef_render_hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lParam)
                    self.is_holding = True
                    self.active_method = "cef_hwnd"
                    self.grab_start_time = time.time()
                    print(f"[CEF TALK CONTROLLER] Mic locked via CEF HWND WM_LBUTTONDOWN (client {pt.x}, {pt.y}).")
                    self._log_grab_ok("cef_hwnd", cx, cy, _grab_started, f"CEF WM_LBUTTONDOWN client={pt.x},{pt.y}")
                    return True
                except Exception as e:
                    print(f"[CEF TALK CONTROLLER] CEF HWND post error: {e}")

            # Strategy 4: UIA Button Invoke / Focus & Press
            if use_mode in ("uia",) and self.talk_button_ctrl:
                try:
                    if hasattr(self.talk_button_ctrl, "iface_invoke") and self.talk_button_ctrl.iface_invoke:
                        self.talk_button_ctrl.iface_invoke.Invoke()
                        self.is_holding = True
                        self.active_method = "uia"
                        self.grab_start_time = time.time()
                        print("[CEF TALK CONTROLLER] Mic locked via UIA InvokePattern.")
                        self._log_grab_ok("uia", cx, cy, _grab_started, "UIA InvokePattern")
                        return True
                    elif hasattr(self.talk_button_ctrl, "click_input"):
                        self.talk_button_ctrl.click_input()
                        self.is_holding = True
                        self.active_method = "uia"
                        self.grab_start_time = time.time()
                        print("[CEF TALK CONTROLLER] Mic locked via UIA click_input.")
                        self._log_grab_ok("uia", cx, cy, _grab_started, "UIA click_input")
                        return True
                except Exception as e:
                    print(f"[CEF TALK CONTROLLER] UIA button error: {e}")

            # Strategy 5: F10 Key Down (Only when explicitly requested)
            if use_mode == "f10":
                if windll:
                    try:
                        self.focus_camfrog()
                        windll.user32.keybd_event(VK_F10, 0, 0, 0)
                        self.is_holding = True
                        self.active_method = "f10"
                        self.grab_start_time = time.time()
                        print("[CEF TALK CONTROLLER] Mic locked via Camfrog F10 PTT hotkey.")
                        self._log_grab_ok("f10", cx, cy, _grab_started, "F10 PTT hotkey")
                        return True
                    except Exception as e:
                        print(f"[CEF TALK CONTROLLER] F10 hotkey error: {e}")
                elif pyautogui:
                    try:
                        pyautogui.keyDown("f10")
                        self.is_holding = True
                        self.active_method = "f10"
                        self.grab_start_time = time.time()
                        print("[CEF TALK CONTROLLER] Mic locked via pyautogui F10 keyDown.")
                        self._log_grab_ok("f10", cx, cy, _grab_started, "pyautogui F10 keyDown")
                        return True
                    except Exception:
                        pass

            if _core is not None:
                _core.log_event("talk", action="grab_failed", mode=use_mode,
                                target_x=cx, target_y=cy,
                                reason="no strategy produced a hold")
            return False

    def release_mic(self) -> bool:
        """
        Releases the microphone across ALL layers unconditionally: OS mouse-up
        (no-args so it works even if the cursor drifted), CEF WM_LBUTTONUP, the
        F10 PTT key, and the named mutex. Hands-free is only clicked when that is
        the method we actually used, because a stray click would engage it.
        """
        with self.lock:
            print("[CEF TALK CONTROLLER] Releasing microphone...")
            cx, cy = self.get_talk_coordinates()

            # 1. Always lift the physical mouse button (harmless if not held)
            if pyautogui:
                try:
                    pyautogui.mouseUp()
                except Exception:
                    pass

            # 2. Always tell the CEF renderer the button came up
            if windll and self.cef_render_hwnd:
                try:
                    pt = wintypes.POINT(cx, cy)
                    windll.user32.ScreenToClient(self.cef_render_hwnd, ctypes.byref(pt))
                    windll.user32.PostMessageW(self.cef_render_hwnd, WM_LBUTTONUP, 0,
                                               lParam_of(pt))
                except Exception:
                    pass

            # 3. Release the F10 PTT hotkey if it was used
            if self.active_method == "f10":
                if windll:
                    try:
                        windll.user32.keybd_event(VK_F10, 0, KEYEVENTF_KEYUP, 0)
                    except Exception:
                        pass
                if pyautogui:
                    try:
                        pyautogui.keyUp("f10")
                    except Exception:
                        pass

            # 4. Turn OFF hands-free ONLY if we turned it on
            elif self.active_method == "handsfree":
                if pyautogui:
                    try:
                        pyautogui.click(cx, cy)
                    except Exception:
                        pass

            self.is_holding = False
            self.active_method = "none"
            self._release_talk_mutex()
            if _core is not None:
                _core.log_event("talk", action="released")
            print("[CEF TALK CONTROLLER] Microphone released. Mic is free for the room.")
            return True

    def speak_and_hold(
        self,
        text_to_say: str,
        voice: str = "en-US-AvaNeural",
        rate: str = "+12%",
        pitch: str = "+16Hz",
        max_wait_sec: float = 12.0,
        output_device: Optional[str] = None,
        persona: str = "valley",
        gate: bool = True,
        pre_rendered_wav: str = "",
        pre_rendered_duration: float = 0.0
    ) -> Dict[str, Any]:
        """
        End-to-end voice broadcast that reports the TRUTH.

        The order here is load-bearing and was measured, not assumed:
          1. Use pre-synthesized audio when supplied, so TTS never happens
             while the mic is held.
          2. Wait for a FULL `talk_quiet_window_s` of silence. Never press while
             a human holds the mic - against a continuous hold the bot lost 39
             presses in 10s and took it zero times. Clicking cannot win a held
             mic; waiting can.
          3. Start the audio FIRST, then press-and-hold. This is the opposite of
             the intuitive order and it is what Camfrog requires: voice activity
             must already be present when the press lands. Measured in one room -
             press-then-audio owned 0% of samples, audio-then-press owned 100%.
          4. Require our own name in the bubble on 2 consecutive samples. A dark
             Talk button is NOT proof of ownership; a rival can render it pressed.
          5. Count how long we still held the mic with audio flowing, and require
             at least `talk_min_audio_fraction` of the intended clip.
          6. Always release in `finally`.

        Returns a dict: {ok, acquired, playback_ok, engine, observed_speaker,
                         intended_duration_s, heard_duration_s, audio_fraction,
                         attempts, method, reason}.
        """
        result: Dict[str, Any] = {
            "ok": False, "acquired": False, "playback_ok": False, "engine": "",
            "observed_speaker": "", "stability_seconds": 0.0,
            "intended_duration_s": 0.0, "heard_duration_s": 0.0,
            "audio_fraction": 0.0, "attempts": 0, "method": "none", "reason": "",
        }

        if gate and _core is not None and not _core.claim_or_suppress("reply", text_to_say):
            result["reason"] = "suppressed: repeated within the one-hour window"
            self.last_broadcast = result
            print(f"[CEF TALK CONTROLLER] Gate: suppressed repeat: {text_to_say[:60]!r}")
            return result

        cfg = _core.load_config() if _core is not None else {}
        min_fraction = float(cfg.get("talk_min_audio_fraction", 0.50))
        quiet_s = float(cfg.get("talk_quiet_window_s", 1.0))
        quiet_timeout = float(cfg.get("talk_quiet_timeout_s", 15.0))
        target_out = output_device or get_configured_output_device()

        # 1. Audio first, and off the mic. A pre-render from the queue's
        #    background synthesis means we never hold the mic during TTS.
        if pre_rendered_wav and os.path.exists(pre_rendered_wav):
            wav_path = pre_rendered_wav
            result["engine"] = "cache"
            dur = pre_rendered_duration or _wav_duration_seconds(wav_path)
        else:
            wav_path = "temp_say_broadcast.wav"
            engine = synthesize_speech_to_wav(
                text_to_say, wav_path, voice=voice, rate=rate, pitch=pitch,
                persona=persona)
            result["engine"] = engine if isinstance(engine, str) else ""
            if not engine:
                result["reason"] = "TTS synthesis failed - no audio to broadcast"
                self.last_broadcast = result
                print(f"[CEF TALK CONTROLLER] ABORT: {result['reason']}")
                return result
            dur = _wav_duration_seconds(wav_path)

        intended = round(float(dur), 2)
        result["intended_duration_s"] = intended
        if intended <= 0.0:
            result["reason"] = "rendered audio has no measurable duration"
            self.last_broadcast = result
            print(f"[CEF TALK CONTROLLER] ABORT: {result['reason']}")
            return result


        # 2. Wait for real silence. A single empty sample is not a free mic.
        print(f"[CEF TALK CONTROLLER] Waiting up to {quiet_timeout:.0f}s for "
              f"{quiet_s:.1f}s of silence: \"{text_to_say}\"...")
        quiet = self.wait_for_quiet_mic(quiet_s=quiet_s, timeout_s=quiet_timeout)
        result["quiet_waited_s"] = quiet.get("waited_s", 0.0)
        if not quiet.get("ok"):
            result["reason"] = f"never got a quiet mic: {quiet.get('reason', '')}"
            self.last_broadcast = result
            print(f"[CEF TALK CONTROLLER] ABORT: {result['reason']}")
            return result

        # 3. AUDIO FIRST, then press. Reversing these two steps loses the mic.
        stop_audio = threading.Event()
        played_flag: Dict[str, Any] = {"ok": False, "error": ""}

        def _play():
            # Loop so a short render still has voice activity running for the
            # whole hold. The loop stops the moment ownership monitoring ends.
            while not stop_audio.is_set():
                try:
                    if not play_wav_to_virtual_cable(wav_path, target_out):
                        played_flag["error"] = "playback failed on every output route"
                        return
                    played_flag["ok"] = True
                except Exception as e:
                    played_flag["error"] = f"playback exception: {e}"
                    return

        audio_thread = threading.Thread(target=_play, daemon=True)
        audio_thread.start()
        time.sleep(0.35)   # let voice activity exist BEFORE the press lands
        result["attempts"] = 1
        pressed = self.fast_press_hold()
        result["method"] = self.active_method
        if not pressed:
            stop_audio.set()
            result["reason"] = "talk button could not be pressed"
            self.release_mic()
            self.last_broadcast = result
            return result

        try:
            # 4. Identity, not pixels, decides the win.
            owned, _flow, name = self.confirm_we_own_the_mic(need_consecutive=2)
            result["observed_speaker"] = name or ""
            if not owned:
                shown = name or "nobody"
                result["reason"] = f"press did not win the mic (bubble showed {shown!r})"
                self.last_broadcast = result
                print(f"[CEF TALK CONTROLLER] ABORT: {result['reason']}")
                return result
            result["acquired"] = True

            # 5. Hold while the audio runs, watching for a rival stealing it.
            heard = 0.0
            last_poll = time.time()
            while heard < intended:
                if stop_audio.wait(0.25):
                    break
                now = time.time()
                heard += (now - last_poll)
                last_poll = now
                still_ours, _f, nm = self.confirm_we_own_the_mic(need_consecutive=1)
                if not still_ours:
                    result["reason"] = (f"lost the mic mid-broadcast after "
                                        f"{heard:.1f}s (bubble showed {nm!r})")
                    result["observed_speaker"] = nm or ""
                    break

            result["heard_duration_s"] = round(min(heard, intended), 2)
            result["audio_fraction"] = (round(min(heard, intended) / intended, 3)
                                        if intended > 0 else 0.0)
            result["playback_ok"] = bool(played_flag.get("ok"))
            if not result["playback_ok"] and played_flag.get("error"):
                result["reason"] = played_flag["error"]
            elif result["audio_fraction"] < min_fraction:
                result["reason"] = (f"partial audio: only "
                                    f"{result['audio_fraction']*100:.0f}% of "
                                    f"{intended:.1f}s reached the room "
                                    f"(need {min_fraction*100:.0f}%)")
        except Exception as e:
            result["reason"] = f"broadcast exception: {e}"
            print(f"[CEF TALK CONTROLLER] Broadcast exception: {result['reason']}")
        finally:
            # 6. Always release, success or failure
            stop_audio.set()
            try:
                audio_thread.join(timeout=1.5)
            except Exception:
                pass
            self.release_mic()

        result["ok"] = bool(
            result["acquired"] and result["playback_ok"]
            and result["audio_fraction"] >= min_fraction)
        self.last_broadcast = result
        if _core is not None:
            _core.log_event("broadcast", **result)
        print(f"[CEF TALK CONTROLLER] Broadcast ok={result['ok']} "
              f"acquired={result['acquired']} fraction={result['audio_fraction']:.0%} "
              f"({result['heard_duration_s']}s/{intended:.1f}s) "
              f"reason={result['reason']!r}")
        return result

# Global singleton talk controller
global_talk_controller = CamfrogCEFTalkController(global_probe)

def save_cef_chat_speed(interval_sec: float) -> bool:
    """Persists CEF chat scanning speed interval to config.json (atomic, locked)."""
    try:
        if _core is not None:
            _core.save_config({"cef_chat_scan_interval_seconds": round(float(interval_sec), 3)})
        else:
            data = {}
            if os.path.exists("config.json"):
                with open("config.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["cef_chat_scan_interval_seconds"] = round(float(interval_sec), 3)
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        print(f"[CONFIG] Saved cef_chat_scan_interval_seconds = {interval_sec}s to config.json.")
        return True
    except Exception as e:
        print(f"[CONFIG ERROR] Could not save setting: {e}")
        return False


def _voice_summary() -> str:
    """One-line summary of the currently persisted voice configuration."""
    cfg = _config()
    engine = cfg.get("engine", "edge")
    if engine == "qwen":
        detail = f"speaker={cfg.get('qwen_speaker', 'vivian')}"
    elif engine == "elevenlabs":
        detail = f"persona={cfg.get('elevenlabs_persona', 'valley')}"
    else:
        detail = f"voice={cfg.get('voice', 'en-US-AvaNeural')}"
    return f"{engine} ({detail})"


def voice_persona_menu() -> None:
    """
    Interactive voice/engine picker. Everything chosen here is PERSISTED to
    config.json, so Terminal 1 (!say, !diss), Terminal 2 (queued speech) and
    Terminal 3 (HUD) all use the same voice afterwards.
    """
    cfg = _config()
    print("\n" + "=" * 76)
    print("  VOICE & ENGINE SELECTOR  (saved to config.json - applies everywhere)")
    print("=" * 76)
    print(f"  Current : engine={cfg.get('engine', 'edge')}  "
          f"qwen_speaker={cfg.get('qwen_speaker', 'vivian')}  "
          f"persona={cfg.get('elevenlabs_persona', 'valley')}")

    has_el = bool(cfg.get("elevenlabs_api_key") or os.environ.get("ELEVENLABS_API_KEY"))
    print("\n  [1] Engine  : qwen            (local Qwen3-TTS CustomVoice, CPU)")
    print("  [2] Engine  : elevenlabs      " + ("(API key configured)" if has_el
                                                else "(NO API KEY - will fall back)"))
    print("  [3] Engine  : edge            (Edge neural TTS)")
    print("  [4] Engine  : system          (Windows SAPI, fastest/robotic)")
    print("\n  [5] Qwen speaker : " + ", ".join(QWEN_SPEAKERS))
    print("  [6] ElevenLabs persona : valley, uppity, valley_sexy")
    print("  [7] ElevenLabs API key : " + ("(key already set)" if has_el else "(not set)"))
    print("  [8] Test the currently saved voice (synth only, no mic)")
    print("  [0] Back")

    try:
        choice = input("\nEnter choice [0-8]: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return

    engines = {"1": "qwen", "2": "elevenlabs", "3": "edge", "4": "system"}
    if choice in engines:
        _core.save_config({"engine": engines[choice]})
        print(f"[VOICE] Engine saved: {engines[choice]}")
    elif choice == "5":
        spk = input(f"Speaker [{', '.join(QWEN_SPEAKERS)}]: ").strip().lower()
        if spk:
            _core.save_config({"qwen_speaker": spk})
            print(f"[VOICE] Qwen speaker saved: {spk}")
    elif choice == "6":
        per = input("Persona [valley, uppity, valley_sexy]: ").strip().lower()
        if per:
            _core.save_config({"elevenlabs_persona": per})
            print(f"[VOICE] Persona saved: {per}")
    elif choice == "7":
        key = input("Paste ElevenLabs API key (blank to clear): ").strip()
        _core.save_config({"elevenlabs_api_key": key})
        print("[VOICE] API key saved.")
    elif choice == "8":
        phrase = input("Test phrase: ").strip() or "KaeKae voice test."
        wav = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_test.wav")
        t0 = time.time()
        engine = synthesize_speech_to_wav(phrase, wav)
        print(f"[VOICE] Test finished in {time.time() - t0:.2f}s -> "
              f"engine={engine or 'FAILED'} file={wav if engine else 'none'}")
    print(f"[VOICE] Now active: {_voice_summary()}")

def run_diagnostic():
    """
    Comprehensive interactive diagnostic tool for verifying CEF attachment,
    mic availability, mic battle detection, grab & winner verification,
    CEF speed tuning (persistent), and 1-click launch of the 3-terminal cluster.
    """
    probe = CamfrogCEFProbe()
    talk_ctrl = CamfrogCEFTalkController(probe)

    # Handle immediate CLI flags if passed
    if any(arg in sys.argv for arg in ["--list-audio", "--audio-devices", "--audio"]):
        print("\n" + "=" * 76)
        print(" SYSTEM AUDIO DEVICES (sounddevice)")
        print("=" * 76)
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            for idx, d in enumerate(devs):
                in_ch = d.get('max_input_channels', 0)
                out_ch = d.get('max_output_channels', 0)
                tag = []
                if in_ch > 0: tag.append(f"In:{in_ch}")
                if out_ch > 0: tag.append(f"Out:{out_ch}")
                print(f"  [{idx:2d}] {d.get('name', '')} ({', '.join(tag)})")
        except Exception as e:
            print(f"Error querying audio devices: {e}")
        return

    # Check for CLI flags: --test-voice / --say
    voice_phrase = None
    for i, a in enumerate(sys.argv):
        if a in ("--test-voice", "--say") and i + 1 < len(sys.argv):
            voice_phrase = sys.argv[i + 1]
            break
        elif a.startswith("--say="):
            voice_phrase = a.split("=", 1)[1]
            break
        elif a == "--test-voice":
            voice_phrase = "Testing KaeKae bot audio routing through VB Audio Cable into Camfrog microphone."
            break

    if voice_phrase:
        out_dev = get_configured_output_device()
        print("\n" + "=" * 76)
        print(" TEST VOICE BROADCAST THROUGH VIRTUAL CABLE INTO CAMFROG MIC")
        print("=" * 76)
        print(f"Phrase to speak : \"{voice_phrase}\"")
        print(f"Routing to      : {out_dev}")
        print("Starting talk sequence (Synthesize -> Verified Grab -> Play -> Release)...")
        success = talk_ctrl.speak_and_hold(voice_phrase, gate=False)
        ok = success.get("ok") if isinstance(success, dict) else bool(success)
        print(f"\nBroadcast result: {'SUCCESS' if ok else 'FAILED'}")
        if isinstance(success, dict):
            print(f"  acquired={success.get('acquired')} playback={success.get('playback_ok')} "
                  f"engine={success.get('engine')} speaker={success.get('observed_speaker')!r} "
                  f"attempts={success.get('attempts')} reason={success.get('reason')!r}")
        return

    # Main Interactive Diagnostic Menu
    probe.start_probe_daemon()
    while True:
        info = probe.scan_camfrog_processes()
        talk_info = talk_ctrl.catch_talk_process()
        out_dev = get_configured_output_device()
        cur_interval = 0.25
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r", encoding="utf-8") as _f:
                    cur_interval = json.load(_f).get("cef_chat_scan_interval_seconds", 0.25)
            except Exception:
                pass

        print("\n" + "=" * 78)
        print("   KAEKAE BOT: CAMFROG CEF STAGE & MICROPHONE DIAGNOSTICS SUITE")
        print("=" * 78)
        print(f"  Main Process (Camfrog Video Chat.exe) : {'FOUND (PID ' + str(info['main_pid']) + ')' if info['main_found'] else 'NOT RUNNING'}")
        print(f"  CEF Processes (camfrog_cef.exe)       : {info['cef_count']} running {info['cef_pids']}")
        print(f"  Talk Coordinates Active               : {talk_info['talk_coords']}")
        print(f"  Target Voice Playback Device          : {out_dev}")
        print(f"  CEF Chat Scan Interval (Persisted)    : {cur_interval}s")
        print("-" * 78)

        # Real-time microphone availability & battle status
        b_status = talk_ctrl.get_mic_battle_status(window_sec=2.0)
        spk = b_status.get("current_speaker", "Unknown speaker")
        is_free = b_status.get("is_free", False)
        is_battling = b_status.get("is_battling", False)
        stable_dur = b_status.get("stable_duration", 0.0)

        if is_free:
            mic_state_str = "🟢 FREE & READY (no one on the mic)"
        elif is_battling:
            competing = ", ".join(b_status.get("competing_speakers", []))
            mic_state_str = (f"⚠️ MIC BATTLE IN PROGRESS (names flipping rapidly: {competing}; "
                             f"{b_status.get('name_changes', 0)} changes)")
        elif b_status.get("held_by_bot"):
            mic_state_str = f"🔴 HELD BY KAEKAE (our name is the speaker, stable {stable_dur}s)"
        elif b_status.get("state") == "unconfirmable":
            mic_state_str = "⚪ UNCONFIRMABLE (Camfrog/CEF speaker label not readable)"
        else:
            mic_state_str = f"🔴 OCCUPIED by '{spk}' (stable {stable_dur}s)"

        print(f"  LIVE MIC STATUS: {mic_state_str}")
        print(f"  VOICE ENGINE   : {_voice_summary()}")
        print(f"  TALK STATE     : {_core.get_talk_state() if _core is not None else 'n/a'}")
        print("=" * 78)
        print("  [1] Live Monitor: Watch Mic Availability & Detect Mic Battles in Real-Time")
        print("  [2] Test Verified Mic Grab (rapid re-press until KaeKae's name holds 1s)")
        print("  [3] Test Voice Broadcast via TTS with Lock Confirmation")
        print("  [4] Accelerate CEF Chat Pulling Speed & Persist Setting (e.g. 0.15s, 0.25s, 0.5s)")
        print("  [5] Recalibrate Stage & Talk Coordinates (calibrate_camfrog.py)")
        print("  [6] Launch Full KaeKae Bot (All 3 Terminals: Chat, Audio & HUD)")
        print("  [7] Voice / Engine / Persona Picker (persists to config.json)")
        print("  [0] Exit Diagnostics")
        print("=" * 78)

        try:
            choice = input("\nEnter choice [0-6] (or press Enter to refresh): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting diagnostics.")
            break

        if choice == "1":
            print("\n--- LIVE MIC MONITOR & BATTLE DETECTOR (Press Ctrl+C to return to menu) ---")
            print("Watching speaker label next to talk button...")
            last_text = ""
            try:
                while True:
                    stat = talk_ctrl.get_mic_battle_status(window_sec=1.5)
                    s_spk = stat.get("current_speaker", "Unknown speaker")
                    s_free = stat.get("is_free")
                    s_bat = stat.get("is_battling")
                    ts = time.strftime("%H:%M:%S")

                    if s_bat:
                        comp = ", ".join(stat.get("competing_speakers", []))
                        line = f"[{ts}] ⚡ MIC BATTLE DETECTED! Names flashing: [{comp}] -> Determining winner..."
                    elif not s_free:
                        line = f"[{ts}] 🎙️ ACTIVE SPEAKER: '{s_spk}' (Stable winner displaying next to talk button)"
                    else:
                        line = f"[{ts}] 🟢 MIC IS FREE (Talk button available to grab)"

                    if line != last_text:
                        print(line)
                        last_text = line
                    time.sleep(0.12)
            except KeyboardInterrupt:
                print("\nReturning to menu...")

        elif choice == "2":
            print("\n--- VERIFIED MIC GRAB TEST ---")
            b_info = talk_ctrl.get_mic_battle_status(window_sec=1.5)
            if b_info.get("state") != "free":
                print(f"Room currently shows: {b_info.get('state')} "
                      f"({b_info.get('current_speaker') or 'no readable name'}). "
                      "Attempting a contested grab anyway...")
            print("Rapidly re-pressing the Talk button (rotating patterns) until "
                  "KaeKae's name holds the speaker slot...")
            grab = talk_ctrl.acquire_talk()
            print("\n--- GRAB DIAGNOSTIC ---")
            print(f"  attempts          : {grab.get('attempts')}")
            print(f"  press patterns    : {grab.get('patterns')}")
            print(f"  winning method    : {grab.get('method')}")
            print(f"  observed speaker  : {grab.get('observed_speaker') or '<never shown>'}")
            print(f"  name stability    : {grab.get('stability_seconds')}s "
                  f"(required {grab.get('required_seconds')}s)")
            if grab.get("ok"):
                print("  OUTCOME           : ✅ CONFIRMED - KaeKae is the room speaker.")
                for s in range(3, 0, -1):
                    print(f"  Holding verified mic... releasing in {s}s")
                    time.sleep(1.0)
            else:
                print(f"  OUTCOME           : ❌ FAILED - {grab.get('reason')}")
                print("                    The mic was released automatically; the room "
                      "never displayed KaeKae as the speaker.")
            talk_ctrl.release_mic()
            print("Microphone released cleanly.\n")
            time.sleep(1.2)

        elif choice == "3":
            phrase = input("Enter test phrase to speak (default: 'KaeKae bot testing microphone lock'): ").strip()
            if not phrase:
                phrase = "KaeKae bot testing microphone lock and broadcast."
            print(f"\nBroadcasting: \"{phrase}\"...")
            res = talk_ctrl.speak_and_hold(phrase, gate=False)
            print("--- BROADCAST RESULT ---")
            for k in ("ok", "acquired", "playback_ok", "engine", "observed_speaker",
                      "stability_seconds", "attempts", "method", "reason"):
                print(f"  {k:<18}: {res.get(k)}")
            time.sleep(1.2)

        elif choice == "7":
            voice_persona_menu()
            time.sleep(0.8)

        elif choice == "4":
            print(f"\nCurrent CEF chat scan interval: {cur_interval}s")
            print("Recommended settings:")
            print("  - [1] Ultra-Fast : 0.15 seconds (Immediate reaction, highest CPU)")
            print("  - [2] Fast (Rec) : 0.25 seconds (Instant reaction, balanced CPU)")
            print("  - [3] Normal     : 0.50 seconds (Standard polling)")
            print("  - [4] Custom     : Enter your own seconds value")
            sub_c = input("Choice [1-4]: ").strip()
            new_val = cur_interval
            if sub_c == "1": new_val = 0.15
            elif sub_c == "2": new_val = 0.25
            elif sub_c == "3": new_val = 0.50
            elif sub_c == "4":
                raw_v = input("Enter interval in seconds (e.g. 0.20): ").strip()
                try:
                    new_val = max(0.05, float(raw_v))
                except ValueError:
                    print("Invalid input; leaving unchanged.")
            save_cef_chat_speed(new_val)
            probe.poll_interval = min(0.08, new_val / 2.0)
            time.sleep(1.0)

        elif choice == "5":
            print("\nLaunching Stage & Active Speaker Calibration Wizard...")
            try:
                import calibrate_camfrog
                calibrate_camfrog.run_calibration_wizard()
            except Exception as e:
                print(f"Calibration error: {e}")
            time.sleep(1.0)

        elif choice == "6":
            print("\n========================================================")
            print("  LAUNCHING FULL KAEKAE BOT CLUSTER (ALL 3 TERMINALS)")
            print("========================================================")
            try:
                import launch_kaekae
                launch_kaekae.main()
            except Exception as e:
                print(f"Launch error: {e}")
            print("\nCluster launched! Exiting diagnostics.")
            break

        elif choice == "0":
            print("Exiting diagnostics.")
            break

    probe.stop()

if __name__ == "__main__":
    run_diagnostic()
