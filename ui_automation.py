"""Camfrog UI Automation adapter with Desktop window enumeration, calibrated rectangles, and VB-Cable TTS."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime
import difflib
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

# Enable Per-Monitor V2 DPI Awareness immediately on Windows so GetCursorPos, SetCursorPos,
# GetWindowRect, and UIA bounding rectangles all use exact 1:1 physical 2560x1440 screen pixels!
if os.name == "nt":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def is_windows_admin() -> bool:
    """Return True if the current process has Windows Administrator (elevated) privileges."""
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """Relaunch the current Python script with Windows Administrator privileges via ShellExecuteW('runas')."""
    if os.name != "nt" or is_windows_admin():
        return True
    try:
        params = " ".join(f'"{arg}"' for arg in sys.argv)
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        return int(rc) > 32
    except Exception:
        return False


from config import (
    ACTIVE_SPEAKER_RECT,
    BOT_USERNAME,
    CAMFROG_WINDOW_TITLE_RE,
    CHAT_INPUT_RECT,
    CHAT_TEXT_RECT,
    CHAT_WINDOW_RECT,
    EDGE_TTS_DEFAULT_VOICE,
    EDGE_TTS_PITCH,
    EDGE_TTS_RATE,
    EDGE_TTS_VOICES,
    KOKORO_DEFAULT_VOICE,
    KOKORO_FEMALE_VOICES,
    LOCAL_KOKORO_MODEL_DIR,
    LOCAL_KOKORO_ONNX_FILE,
    LOCAL_KOKORO_VOICES_FILE,
    LOCAL_KOKORO_READY_STAMP,
    LOCAL_KOKORO_SAMPLE_RATE,
    LOCAL_XTTS_MODEL_DIR,
    LOCAL_XTTS_READY_STAMP,
    IGNORED_USER_LIST_RECTS,
    MAX_ROOM_USERS,
    MIC_CONFIRM_PERSIST_SECONDS,
    MIC_GRAB_FAST_CLICKS,
    MIC_GRAB_FAST_CLICK_DELAY,
    MIC_GRAB_HOLD_MIN_SECONDS,
    MIC_GRAB_MAX_ATTEMPTS,
    MIC_GRAB_CONFIRM_TIMEOUT_S,
    MIC_GRAB_RETRY_PAUSE_S,
    ROOM_TAB_CLICK_POINTS,
    ROOM_TAB_POSITIONS,
    TALK_BUTTON_RECT,
    TALK_DOUBLE_CLICK_DELAY,
    TOP_GIFTERS_RECT,
    UIA_CACHE_SECONDS,
    USER_LIST_ITEM_X_SPAN,
    USER_LIST_RECT,
    VB_CABLE_PLAYBACK_DEVICE,
    VB_CABLE_TTS_ENABLED,
    load_calibration_overrides,
    save_calibration_overrides,
)

try:
    from pywinauto import Application, Desktop
    from pywinauto.keyboard import send_keys as uia_send_keys
    from pywinauto.mouse import click as uia_click, press as uia_press, release as uia_release
except ImportError:
    Application = None
    Desktop = None
    uia_send_keys = None
    uia_click = None
    uia_press = None
    uia_release = None
# --- SHARED AUDIO CAPTURE MUTEX (SAMPLE vs LISTEN) ---
# Both the voice-sample capture AND the live-LISTEN transcription worker call sounddevice via
# `sounddevice.rec()` on background threads. WASAPI shared-mode does not arbitrate those two
# concurrent `sd.rec()` calls, so an overlap on the same device garbles both buffers.
# This lock (and the _sample_capture_active flag) force LISTEN to skip during a manual sample
# and let the sample capture own the mic for the whole window.
_AUDIO_CAPTURE_LOCK = threading.Lock()
_AUDIO_CAPTURE_ACTIVE = False

# Keywords matching virtual/loopback capture devices. The SAMPLE capture must never use these
# (they carry the bot's own TTS or a room mix, which produce the "animated/monster" XTTS clone).
_VIRTUAL_INPUT_KEYWORDS = (
    "cable", "vb-audio", "stereo mix", "what u hear", "wave out", "wave accompan", "loopback",
    "voicemeeter", "ashound", "veaa", "agc", "wireplumber", "virtual", "aux", "spdif",
)



try:
    from pywinauto.uia_defines import IUIA
except ImportError:
    IUIA = None


# ==========================================================================================
# VOICE CATALOGS  (Female-only Edge Neural + Coqui XTTS v2 sub-menus for the SPECIAL MIC LINE)
# ==========================================================================================
# TTS EDGE sub-menu: WOMEN ONLY (aria, ava, jenny, sonia, natasha). Male Edge voices are
# intentionally excluded so the SPECIAL MIC LINE only ever offers KaeKae female voices.
EDGE_FEMALE_VOICES: dict[str, str] = {
    "Edge Aria": "en-US-AriaNeural",
    "Edge Ava": "en-US-AvaMultilingualNeural",
    "Edge Jenny": "en-US-JennyNeural",
    "Edge Sonia": "en-GB-SoniaNeural",
    "Edge Natasha": "en-AU-NatashaNeural",
}

# Coqui / XTTS v2 built-in WOMEN speakers used to test cloning. The Coqui Default entry is the
# single exception used purely to verify the cloning pipeline end-to-end.
COQUI_DEFAULT_VOICE = "Coqui Default (Test Clone)"
COQUI_FEMALE_VOICES: dict[str, str] = {
    "Coqui Gracie Wise": "Gracie Wise",
    "Coqui Claribel Dervla": "Claribel Dervla",
    "Coqui Daisy Studious": "Daisy Studious",
    "Coqui Tammie Ema": "Tammie Ema",
    "Coqui Alison Dietl": "Alison Dietl",
    "Coqui Ana Florence": "Ana Florence",
    "Coqui Asya Anara": "Asya Anara",
}
# Dynamic last slot in the Coqui sub-menu that mirrors the live CLONE produced by Sample->Clone->Default.
COQUI_CLONE_VOICE = "Coqui 🎙️ CLONE (Active)"
# Sentinel display name shown in the clone slot when no clone has been captured yet.
COQUI_CLONE_EMPTY = "Coqui 🎙️ CLONE (None)"


def coqui_voice_catalog() -> list[str]:
    """Return the Coqui sub-menu order: [women voices..., Coqui Default (Test Clone), <clone slot>]."""
    return list(COQUI_FEMALE_VOICES.keys()) + [COQUI_DEFAULT_VOICE, COQUI_CLONE_VOICE]


def edge_female_voice_catalog() -> list[str]:
    """Return the Edge sub-menu order (women only)."""
    return list(EDGE_FEMALE_VOICES.keys())


def is_coqui_voice(voice_label: str) -> bool:
    """Return True when a SPECIAL MIC LINE selection maps to the Coqui / XTTS engine."""
    label = str(voice_label or "")
    return (
        label in COQUI_FEMALE_VOICES
        or label == COQUI_DEFAULT_VOICE
        or label == COQUI_CLONE_VOICE
        or label == COQUI_CLONE_EMPTY
    )


KOKORO_CLONE_VOICE = "Kokoro CLONE (via Coqui)"


def kokoro_voice_catalog() -> list:
    """Return the Local GPU sub-menu order: [women voices..., Kokoro Default (Test)]."""
    return list(KOKORO_FEMALE_VOICES.keys()) + [KOKORO_DEFAULT_VOICE]


def is_kokoro_voice(voice_label: str) -> bool:
    """Return True when a SPECIAL MIC LINE selection maps to the local Kokoro engine."""
    label = str(voice_label or "")
    return label in KOKORO_FEMALE_VOICES or label == KOKORO_DEFAULT_VOICE


def resolve_compute_device() -> dict[str, Any]:
    """Resolve the best GPU compute backend, ALWAYS preferring AMD first, then NVIDIA, then CPU.

    Priority order (per operator request):
        1. AMD Radeon RX 9070 XT via DirectML (onnxruntime-directml / torch-directml)  -> amd-directml
        2. AMD Radeon via ROCm/HIP (torch.version.hip + cuda available)                 -> amd-rocm
        3. NVIDIA via CUDA                                                                -> nvidia-cuda
        4. CPU fallback                                                                   -> cpu
    Returns a structured dict describing the resolved backend for WhisperX, XTTS, and diagnostics.
    """
    result: dict[str, Any] = {
        "backend": "cpu",
        "device": "cpu",
        "compute_type": "int8",
        "name": "CPU Fallback",
        "amd": False,
        "nvidia": False,
        "gpu": False,
    }

    # 1. AMD ROCm / HIP (native AMD torch build)
    try:
        import torch  # type: ignore[import-not-found]

        hip = getattr(torch.version, "hip", None)
        if hip and torch.cuda.is_available():
            result.update(
                backend="amd-rocm",
                device="cuda",
                compute_type="float16",
                name=str(torch.cuda.get_device_name(0)),
                amd=True,
                gpu=True,
            )
            return result
    except Exception:
        pass

    # 2. AMD Radeon via DirectML (Windows DirectX 12 native — the RX 9070 XT Tai Chi path)
    try:
        import onnxruntime as ort  # type: ignore[import-not-found]

        if "DmlExecutionProvider" in ort.get_available_providers():
            result.update(
                backend="amd-directml",
                device="directml",
                compute_type="float16",
                name="AMD Radeon RX 9070 XT (DirectML DX12)",
                amd=True,
                gpu=True,
            )
            return result
    except Exception:
        pass
    try:
        import torch_directml  # type: ignore[import-not-found]

        if torch_directml.is_available():
            dev_name = "AMD Radeon RX 9070 XT (DirectML DX12)"
            try:
                if torch_directml.device_count() > 0:
                    dev_name = f"{dev_name} [dev {torch_directml.device()}]"
            except Exception:
                pass
            result.update(
                backend="amd-directml",
                device="directml",
                compute_type="float16",
                name=dev_name,
                amd=True,
                gpu=True,
            )
            return result
    except Exception:
        pass

    # 3. NVIDIA CUDA
    try:
        import torch  # type: ignore[import-not-found]

        if torch.cuda.is_available():
            try:
                torch.cuda.set_device(0)
            except Exception:
                pass
            result.update(
                backend="nvidia-cuda",
                device="cuda",
                compute_type="float16",
                name=str(torch.cuda.get_device_name(0)),
                nvidia=True,
                gpu=True,
            )
            return result
    except Exception:
        pass

    # 4. CPU fallback — the bot still runs fully on CPU when no GPU component is present.
    return result


# Calibrated reference Camfrog window origin [left=1273, top=0, right=2567, bottom=1399]
CALIBRATED_WINDOW_RECT = (1273, 0, 2567, 1399)

# Win32 background messaging constants so the bot works without stealing focus or requiring active window
WM_ACTIVATE = 0x0006
WA_ACTIVE = 1
WM_SETFOCUS = 0x0007
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_SHOWWINDOW = 0x0018
WM_ACTIVATEAPP = 0x001C
WM_NCACTIVATE = 0x0086
WM_VSCROLL = 0x0115
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEWHEEL = 0x020A
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_PASTE = 0x0302
VK_RETURN = 0x0D
VK_NEXT = 0x22
VK_END = 0x23
SB_BOTTOM = 7
MK_LBUTTON = 0x0001
SW_RESTORE = 9
SW_SHOWNOACTIVATE = 4


_CLOCK_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?$", re.I)
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_$.\-\[\]@~^]{2,32}$")
_PANEL_LABELS = {
    "talk", "push-to-talk", "pushtotalk", "camfrog", "users", "user", "members", "lurkers",
    "lurker", "youareviewing", "viewing", "search", "gifts", "giftusers", "giftusers2",
    "topgifters", "yourvideo", "room", "chat", "roomlist", "players__lounge", "drama_central",
    "mute", "unmute", "volume", "audio", "options", "settings", "send", "im", "profile",
    "page", "pageleft", "pageright", "pageup", "pagedown", "line", "lineup", "linedown",
    "scroll", "scrollbar", "vertical", "horizontal", "join", "quit", "left", "entered",
    "edit", "run", "file", "view", "help", "window", "selection", "terminal", "topic",
    "register", "headeritem", "http", "https", "ftp", "mailto", "camfrogcdn",
    "bers", "ers", "kers", "wing", "ewing", "iewing", "rkers", "mbers", "embers",
    "the", "and", "for", "you", "are", "not", "yes", "nah", "lol", "lmao", "rofl",
    "right", "pop", "conqueror", "princess", "pirate", "agent", "kaekae", "cd", "mr",
}

# Authoritative room user count header: "Users (30)", "USERS (#)", plus the 3 section headers:
# "YOU ARE VIEWING #", "MEMBERS #", "LURKERS #" (summed together for exact room count)
_USERS_TOTAL_HEADER_RE = re.compile(
    r"(?<![A-Za-z_])users\s*(?:\(\s*(\d{1,3})\s*\)|:\s*(\d{1,3})|\[\s*(\d{1,3})\s*\]|\s+(\d{1,3})\b)",
    re.IGNORECASE,
)
_SECTION_COUNT_RE = re.compile(
    r"(?:(?P<section>you\s*are\s*viewing|(?:vie)?wing|(?:mem|em|m)?bers|(?:lur|r)?kers?)\s*[:(\[\-]*\s*(?P<count>\d{1,3})\s*[)\]]?)",
    re.IGNORECASE,
)

# Dynamic section headers in User List [l=2359, r=2559] such as "YOU ARE VIEWING 0", "MEMBERS 16", "LURKERS 14", "Users (30)"
_USER_LIST_HEADER_RE = re.compile(
    r"^\s*[^A-Za-z0-9_]*(?:"
    r"you\s*are\s*viewing(?:\s*[:(\[\-]*\s*\d+\s*[)\]]?)?|"
    r"youareviewing\d*|"
    r"(?:vie)?wing(?:\s*[:(\[\-]*\s*\d+\s*[)\]]?)?|"
    r"(?:lur|r)?kers?(?:\s*[:(\[\-]*\s*\d+\s*[)\]]?)?|"
    r"users(?:\s*[:(\[\-]*\s*\d+\s*[)\]]?)?|"
    r"(?:mem|em|m)?bers(?:\s*[:(\[\-]*\s*\d+\s*[)\]]?)?|"
    r"friends?(?:\s*[:(\[\-]*\s*\d+\s*[)\]]?)?|"
    r"top\s*gifters?(?:\s*[:(\[\-]*\s*\d+\s*[)\]]?)?|"
    r"gift\s*users?\s*\d*"
    r")\s*$",
    re.IGNORECASE,
)

_MOD_LINE_RE = re.compile(
    r"^\s*(?:(?P<actor>[A-Za-z0-9_$.\-\[\]@~^]{2,32})\s+(?:was\s+)?"
    r"(?P<action>unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\s+"
    r"(?P<target>[A-Za-z0-9_$.\-\[\]@~^]{2,32})(?:\s+microphone)?|"
    r"(?P<target2>[A-Za-z0-9_$.\-\[\]@~^]{2,32})\s+was\s+"
    r"(?P<action2>unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\s+by\s+"
    r"(?P<actor2>[A-Za-z0-9_$.\-\[\]@~^]{2,32}))\s*[.!]?\s*$",
    re.IGNORECASE,
)

_INLINE_CHAT_RE = re.compile(
    r"^\s*(?:\[?(?P<ts1>\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)\]?\s+)?"
    r"(?P<user>[A-Za-z0-9_$.\-\[\]@~^]{2,32})"
    r"(?:\s+\(?\[?(?P<ts2>\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)\]?\)?)?"
    r"(?:\s+says)?\s*:\s*(?P<body>.+?)\s*$",
    re.IGNORECASE,
)

# Multi-event Join: / Quit: parser for DataItem(50029) rows at [l=1332, r=2330]
# e.g. "Quit: phoenixrising Quit: liketosquirt Join: ward1dp"
_MULTI_PRESENCE_PAIR_RE = re.compile(
    r"\b(?P<kw>join|quit|left)\s*:\s*[^A-Za-z0-9_$.\-\[\]@~^]*(?P<user>[A-Za-z0-9_$.\-\[\]@~^]{2,32})",
    re.IGNORECASE,
)

# Allows optional punctuation/quotes around the username such as "Quit: 'Katty"
_INLINE_PRESENCE_RE = re.compile(
    r"^\s*(?:(?P<kw>join|quit|left)\s*:\s*[^A-Za-z0-9_$.\-\[\]@~^]*(?P<user1>[A-Za-z0-9_$.\-\[\]@~^]{2,32})|"
    r"[^A-Za-z0-9_$.\-\[\]@~^]*(?P<user2>[A-Za-z0-9_$.\-\[\]@~^]{2,32})\s+(?:has\s+)?(?P<verb>joined|left|quit|entered)(?:\s+the\s+room)?)\s*[.!'""]*\s*$",
    re.IGNORECASE,
)


def is_ignored_listitem_rect(rect_tuple: tuple[int, int, int, int] | None) -> bool:
    """Return True if the rectangle matches one of the legacy ignored ListItem(50007) slots."""
    if rect_tuple is None:
        return False
    l, t, r, b = rect_tuple
    for il, it, ir, ib in IGNORED_USER_LIST_RECTS:
        if abs(l - il) <= 2 and abs(t - it) <= 2 and abs(r - ir) <= 2 and abs(b - ib) <= 2:
            return True
    return False


# Alias kept for test_bot.py backward compatibility
is_ignored_rect = is_ignored_listitem_rect


def extract_users_header_count(value: str) -> int | None:
    """Extract the integer # from 'Users (25)' / 'USERS (#)' / 'USERS #' / 'MEMBERS (#)', ignoring VIEWING and LURKERS."""
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line or len(line) > 36:
            continue
        lower = line.lower()
        if "viewing" in lower or "lurker" in lower or "gift" in lower or "_" in lower:
            continue
        match = _USERS_TOTAL_HEADER_RE.search(line)
        if match:
            raw_num = next((g for g in match.groups() if g is not None), None)
            if raw_num:
                try:
                    count = int(raw_num)
                    if 1 <= count <= 500:
                        return count
                except ValueError:
                    continue
        sec = _SECTION_COUNT_RE.search(line)
        if sec and sec.group("section").lower() == "members":
            try:
                count = int(sec.group("count"))
                if 1 <= count <= 500:
                    return count
            except ValueError:
                continue
    return None


def is_user_list_header(value: str) -> bool:
    """Return True for 'YOU ARE VIEWING #', 'VIEWING #', 'LURKERS #', 'USERS (#)', or similar section headers."""
    raw = str(value or "").strip()
    if not raw:
        return True
    if _USER_LIST_HEADER_RE.fullmatch(raw) or extract_users_header_count(raw) is not None:
        return True
    lower = raw.lower()
    if "you are viewing" in lower or "youareviewing" in lower:
        return True
    if "_" not in lower and re.search(r"\b(?:viewing|lurkers?|users|members)\s*[:(\[\-]*\s*\d+", lower):
        return True
    compact = re.sub(r"[^a-z0-9]", "", lower)
    if (
        compact.startswith("youareviewing")
        or compact.startswith("viewing")
        or compact.startswith("lurkers")
        or compact.startswith("giftusers")
        or compact.startswith("topgifters")
        or compact in {"pageleft", "pageright", "pageup", "pagedown", "lineup", "linedown"}
        or ("_" not in lower and re.fullmatch(r"(?:users|members)\d+", compact))
    ):
        return True
    return False


def clean_username(value: str, rect_tuple: tuple[int, int, int, int] | None = None) -> str:
    """Return a valid Camfrog username, or an empty string for UI chrome, VIEWING #, LURKERS #, USERS (#), or ignored rects."""
    if is_ignored_listitem_rect(rect_tuple):
        return ""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if _CLOCK_RE.fullmatch(raw) or re.fullmatch(r"\d{3,4}(?:AM|PM)", raw, re.I):
        return ""
    if is_user_list_header(raw):
        return ""
    raw = re.sub(r"^\s*(?:speaking|on\s*mic|mic|user|join|quit|left)\s*:\s*", "", raw, flags=re.I).strip()
    if is_user_list_header(raw):
        return ""

    # Evaluate tokens: if OCR read a 1-2 char icon glyph before the username (e.g. "o Stonerwayne1000"),
    # pick the best valid username token rather than blindly taking token[0].
    tokens = [t.lstrip("@'\"").rstrip(":'\",.") for t in raw.split() if t.strip()]
    if not tokens:
        return ""

    valid_candidates: list[str] = []
    for tok in tokens:
        cleaned_tok = re.sub(r"[^A-Za-z0-9_$.\-\[\]~^]", "", tok)[:32]
        lower_tok = cleaned_tok.lower()
        if (
            len(cleaned_tok) >= 2
            and not cleaned_tok.isdigit()
            and lower_tok not in _PANEL_LABELS
            and not is_user_list_header(cleaned_tok)
            and _USERNAME_RE.fullmatch(cleaned_tok)
        ):
            valid_candidates.append(cleaned_tok)

    if not valid_candidates:
        return ""
    # If the first token is already a solid username (>= 3 chars), use it; otherwise take the longest valid token
    if len(valid_candidates[0]) >= 3:
        return valid_candidates[0]
    return max(valid_candidates, key=len)


def parse_chat_text(raw_text: str) -> list[dict[str, str]]:
    """Offline/helper parser that converts raw multi-line chat text into structured events."""
    lines = [("Text", ln.strip()) for ln in str(raw_text or "").splitlines() if ln.strip()]
    return CamfrogUIAutomation._parse_text_tokens_into_events(lines)


@dataclass(frozen=True)
class UIANode:
    control_type: str
    name: str
    class_name: str
    left: int
    top: int
    right: int
    bottom: int
    control: Any = None

    @property
    def rect_tuple(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)


class _XttsLocalWrapper:
    """Thin adapter over a low-level TTS Xtts model exposing the high-level synthesis API.

    The existing CoquiXTTSVoiceEngine synthesis code calls `tts_with_vc_to_file(...)` (voice
    cloning from a reference wav) and `tts_to_file(... speaker=...)` (built-in named speakers).
    TTS.api.TTS() provides those, but its path resolver mis-joins the XTTS checkpoint on TTS 0.22,
    so we load Xtts directly and re-expose the same two methods here. Everything else in the
    engine keeps calling the same method names unchanged.
    """

    def __init__(self, model: Any) -> None:
        self._model = model

    @property
    def speaker_manager(self) -> Any:
        return getattr(self._model, "speaker_manager", None)

    def _write_wav(self, wav, out_path: str, sample_rate: int) -> None:
        import numpy as np  # type: ignore[import-not-found]

        arr = np.asarray(wav, dtype=np.float32).reshape(-1)
        arr = np.clip(arr, -1.0, 1.0)
        pcm = (arr * 32767.0).astype("<i2")
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(int(sample_rate))
            wf.writeframes(pcm.tobytes())

    def _synth(self, text: str, speaker_wav: str | None, speaker: str | None, out_path: str,
               language: str) -> None:
        """Run one XTTS synthesis. `speaker_wav` clones from a reference; `speaker` uses a built-in."""
        model = self._model
        sr = 24000
        result = None
        # Preferred: voice cloning from a reference wav (Sample -> Clone path).
        if speaker_wav and hasattr(model, "full_inference"):
            result = model.full_inference(text=text, ref_audio_path=speaker_wav, language=language or "en")
        elif speaker and model.speaker_manager is not None and hasattr(model, "inference"):
            # Built-in named speaker: resolve its latent + embedding, then run inference.
            gpt_cond_latent, speaker_embedding = model.speaker_manager.speakers[speaker].values()
            result = model.inference(
                text=text, language=language or "en",
                gpt_cond_latent=gpt_cond_latent, speaker_embedding=speaker_embedding,
            )
        elif hasattr(model, "full_inference"):
            # No reference and no named speaker: fall back to the model's default sample voice.
            default_ref = None
            base = Path(str(LOCAL_XTTS_MODEL_DIR))
            for cand in ("samples/en_sample.wav", "samples/fr_sample.wav"):
                if (base / cand).exists():
                    default_ref = str(base / cand)
                    break
            if default_ref:
                result = model.full_inference(text=text, ref_audio_path=default_ref, language=language or "en")
        if result is None:
            raise RuntimeError("XTTS: no usable synthesis entrypoint for the requested voice")
        wav = result["wav"] if isinstance(result, dict) else result
        # Xtts exposes the output sample rate on the config / hifigan decoder.
        sr = int(getattr(getattr(model, "config", None), "output_sample_rate", 0) or 24000)
        self._write_wav(wav, out_path, sr)

    def tts_with_vc_to_file(self, text: str, speaker_wav: str, file_path: str, language: str = "en",
                            **_: Any) -> None:
        self._synth(text, speaker_wav, None, file_path, language)

    def tts_to_file(self, text: str, speaker: str | None = None, language: str = "en",
                    file_path: str = "", speaker_wav: str | None = None, **_: Any) -> None:
        self._synth(text, speaker_wav, speaker, file_path, language)

    def synthesize(self, text: str, speaker_wav: str | None = None, output_path: str = "",
                   language: str = "en", speaker: str | None = None, **_: Any) -> None:
        self._synth(text, speaker_wav, speaker, output_path, language)



class CoquiXTTSVoiceEngine:
    """Coqui XTTS-v2 voice-cloning engine for the SPECIAL MIC LINE (Sample -> Clone -> Default -> Clear).

    Design goals (per operator request):
      * XTTS v2 (Coqui TTS) drives every Coqui voice selection and runs on the GPU **if possible**
        (AMD ROCm/CUDA/DirectML first via `resolve_compute_device()`), transparently falling back to CPU.
      * The class is fully lazy and import-safe: if the `TTS` (Coqui) package is not installed it NEVER
        raises on import or construction — `is_available()` simply returns False so the caller keeps the
        reliable Edge Neural fallback and the microphone always still works.
      * A live state machine tracks: captured sample wav -> cloned reference -> active default voice.
      * Every state-changing action emits progress logs through a caller-supplied callback so the GUI can
        stream cloning progress into the dedicated transcription terminal.
    """

    # 16 kHz mono capture is ideal for XTTS reference latents and small enough to ship/portable-deploy.
    SAMPLE_RATE = 16000
    SAMPLE_CHANNELS = 1
    # A ~6-12s reference is the sweet spot for a stable XTTS speaker latent.
    DEFAULT_SAMPLE_SECONDS = 8.0
    MIN_SAMPLE_SECONDS = 3.0
    MAX_SAMPLE_SECONDS = 30.0

    def __init__(self) -> None:
        self._base_dir = Path(__file__).resolve().parent
        self._samples_dir = self._base_dir / "data" / "voice_samples"
        self._clone_dir = self._base_dir / "data" / "voice_clone"
        for folder in (self._samples_dir, self._clone_dir):
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        self._tts: Any = None            # lazy-loaded Tts() instance
        self._load_error: str = ""
        self._lock = threading.Lock()    # serialize XTTS model load + synthesis/clone
        # Active-clone state (Sample -> Clone -> Default):
        self._sample_wav: str = ""       # most recent captured microphone sample
        self._clone_reference_wav: str = ""  # XTTS speaker-latent reference wav (== sample wav)
        self._clone_ready: bool = False  # True once Clone has produced a usable reference
        self._clone_is_default: bool = False  # True once the clone is routed as the Coqui default
        self._device = resolve_compute_device()

    # ------------------------------------------------------------------ AVAILABILITY
    def is_available(self) -> bool:
        """True if the Coqui `TTS` package is importable (does NOT load the heavy model)."""
        try:
            import importlib.util as _u

            return _u.find_spec("TTS") is not None
        except Exception:
            return False

    def device_info(self) -> dict[str, Any]:
        """Freshly resolve the compute backend so GPU/CPU status is always current."""
        self._device = resolve_compute_device()
        return self._device

    def status(self) -> dict[str, Any]:
        return {
            "available": self.is_available(),
            "loaded": self._tts is not None,
            "load_error": self._load_error,
            "sample_wav": self._sample_wav,
            "clone_reference_wav": self._clone_reference_wav,
            "clone_ready": self._clone_ready,
            "clone_is_default": self._clone_is_default,
            "device": self._device,
        }

    def clone_slot_label(self) -> str:
        """Return the Coqui sub-menu label for the dynamic clone slot (Active vs None)."""
        return COQUI_CLONE_VOICE if (self._clone_is_default or self._clone_ready) else COQUI_CLONE_EMPTY

    # ------------------------------------------------------------------ MODEL LOADING
    def _ensure_model(self, log: Callable[[str], None] | None = None) -> Any | None:
        """Lazily load the XTTS-v2 model on the resolved device (GPU if possible). Thread-safe.

        Loads the portable local cache (data/models/xtts_v2) directly via the low-level Xtts API.
        This deliberately bypasses TTS.api.TTS(), whose high-level path resolver mis-joins the
        checkpoint for XTTS (model.pth/model.pth) on TTS 0.22. The returned object is wrapped so
        the existing tts_to_file / tts_with_vc_to_file synthesis calls keep working unchanged.
        """
        if self._tts is not None:
            return self._tts
        with self._lock:
            if self._tts is not None:
                return self._tts
            if not self.is_available():
                self._load_error = "Coqui TTS package not installed"
                return None
            try:
                dev = self.device_info()
                if log is not None:
                    log(
                        f"[COQUI XTTS 🎙️] Loading XTTS-v2 model on {dev.get('name', 'cpu')} "
                        f"(backend={dev.get('backend', 'cpu')}, compute={dev.get('compute_type', 'int8')})..."
                    )
                import torch  # type: ignore[import-not-found]

                # torch 2.6+ defaults to weights_only=True, which rejects the trusted local XTTS
                # checkpoint pickle (custom TTS config classes). Our checkpoint is a vetted HF
                # snapshot, so allow full unpickling for this load only.
                _orig_torch_load = torch.load

                def _trusted_torch_load(*a: Any, **k: Any) -> Any:
                    k.setdefault("weights_only", False)
                    return _orig_torch_load(*a, **k)

                torch.load = _trusted_torch_load  # type: ignore[assignment]
                try:
                    from TTS.config import load_config  # type: ignore[import-not-found]
                    from TTS.tts.models.xtts import Xtts  # type: ignore[import-not-found]

                    local_dir = Path(str(LOCAL_XTTS_MODEL_DIR))
                    cfg_p = local_dir / "config.json"
                    if Path(str(LOCAL_XTTS_READY_STAMP)).exists() and cfg_p.exists():
                        if log is not None:
                            log(f"[COQUI XTTS 📦] Loading XTTS-v2 from portable cache {local_dir} (no re-download).")
                    else:
                        if log is not None:
                            log(
                                "[COQUI XTTS ⏬] Portable XTTS cache not stamped — loading from cache dir "
                                "(run setup_env.py --retry-optional to stamp it locally for future boots)."
                            )
                    cfg = load_config(str(cfg_p))
                    model = Xtts.init_from_config(cfg)
                    model.load_checkpoint(cfg, checkpoint_dir=str(local_dir), eval=True, use_deepspeed=False)
                    self._tts = _XttsLocalWrapper(model)
                finally:
                    torch.load = _orig_torch_load  # type: ignore[assignment]
                # Best-effort DirectML handoff for the RX 9070 XT when torch-directml is present.
                if bool(dev.get("gpu")) and dev.get("backend") == "amd-directml":
                    try:
                        import torch_directml  # type: ignore[import-not-found]

                        dml = torch_directml.device()
                        inner = getattr(self._tts, "_model", None)
                        if inner is not None and hasattr(inner, "to"):
                            inner.to(dml)
                        if log is not None:
                            log(f"[COQUI XTTS ⚡] XTTS-v2 moved to AMD DirectML device {dml} (RX 9070 XT).")
                    except Exception as dml_exc:
                        if log is not None:
                            log(
                                "[COQUI XTTS ℹ️] AMD DirectML device handoff unavailable "
                                f"({dml_exc}); running XTTS on CPU this session (voice cloning still works)."
                            )
                self._load_error = ""
                if log is not None:
                    log("[COQUI XTTS ✅] XTTS-v2 model ready — voice cloning enabled.")
                return self._tts
            except Exception as exc:
                self._load_error = str(exc)
                self._tts = None
                if log is not None:
                    log(
                        f"[COQUI XTTS ⚠️] Could not load XTTS-v2 ({exc}). "
                        "Coqui voices will fall back to Edge Neural so the microphone still broadcasts."
                    )
                return None


    # ------------------------------------------------------------------ CLONE
    def clone_active_voice(
        self, log: Callable[[str], None] | None = None
    ) -> tuple[bool, str]:
        """Build an XTTS speaker-latent reference from the most recent sample.

        Returns (ok, reference_wav_path). Streams progress so the operator knows when the
        clone is ready to be prompted in the SPECIAL MIC LINE section.
        """
        if not self._sample_wav or not Path(self._sample_wav).exists():
            if log is not None:
                log("[CLONE ❌] No voice sample found — press 🎙️ Sample first, then 🧬 Clone Voice.")
            return (False, "")
        model = self._ensure_model(log=log)
        if model is None:
            # No Coqui model: keep the raw sample as the reference so a later Edge-based
            # broadcast still has a captured identity, but report not-ready for XTTS cloning.
            self._clone_reference_wav = self._sample_wav
            self._clone_ready = False
            if log is not None:
                log(
                    "[CLONE ⚠️] XTTS model unavailable — clone deferred. Edge Neural remains the "
                    "broadcast engine until Coqui/XTTS is installed."
                )
            return (False, self._clone_reference_wav)
        try:
            if log is not None:
                log("[CLONE 🧬] Building XTTS speaker latent from the captured sample (this can take a moment)...")
            # Copy the verified sample into the clone dir so the active reference is stable/portable.
            dest = self._clone_dir / f"clone_reference_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            try:
                import shutil

                shutil.copyfile(self._sample_wav, dest)
            except Exception:
                dest = Path(self._sample_wav)
            # Warm the speaker latent by running a 1-word probe so we KNOW the clone is ready.
            probe_wav = self._clone_dir / "clone_probe.wav"
            self._run_xtts(model, "ready", str(dest), str(probe_wav))
            self._clone_reference_wav = str(dest)
            self._clone_ready = True
            self._clone_is_default = False
            if log is not None:
                log(
                    "[CLONE ✅] Voice clone built and verified with XTTS! "
                    "Press ▶️ Default to route the SPECIAL MIC LINE to this cloned voice."
                )
            return (True, str(dest))
        except Exception as exc:
            self._clone_ready = False
            self._clone_reference_wav = self._sample_wav
            if log is not None:
                log(f"[CLONE ❌] XTTS cloning failed: {exc}. Try re-capturing a clearer Sample.")
            return (False, self._clone_reference_wav)


    # ------------------------------------------------------------------ WAV HELPERS
    def _write_wav(self, np_audio, path: Path, sample_rate: int) -> bool:
        try:
            import numpy as np  # type: ignore[import-not-found]

            pcm = np.clip(np_audio, -1.0, 1.0)
            pcm = (pcm * 32767.0).astype("<i2")
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(self.SAMPLE_CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(int(sample_rate))
                wf.writeframes(pcm.tobytes())
            return True
        except Exception:
            return False

    @staticmethod
    def _peak(np_audio) -> int:
        try:
            import numpy as np  # type: ignore[import-not-found]

            if np_audio is None or getattr(np_audio, "size", 0) == 0:
                return 0
            return int(np.max(np.abs(np_audio.astype(np.float32))) * 32767.0)
        except Exception:
            return 0

    # ------------------------------------------------------------------ SAMPLE
    @staticmethod
    def _matches_virtual_input(dev_name):
        """True if a sounddevice entry is a virtual/loopback capture device."""
        low = str(dev_name or "").lower()
        return any(kw in low for kw in _VIRTUAL_INPUT_KEYWORDS)

    def _query_devices(self):
        """Enumerate sounddevice capture devices (indirection so tests can monkeypatch it)."""
        import sounddevice as sd  # type: ignore[import-not-found]

        return sd.query_devices()

    def _physical_input_device(self):
        """Resolve the best PHYSICAL microphone for the voice sample.

        Excludes virtual/loopback devices (the LISTEN engine's devices) and any device with no
        positive input channels. Prefers the most channels; returns (None, label) when nothing
        usable is found so the caller can defer gracefully. Never touches the capture lock, so it
        is always safe to call even while the live-LISTEN worker holds it.
        """
        try:
            devices = self._query_devices()
            candidates = [
                d
                for d in devices
                if int(d.get("max_input_channels", 0) or 0) > 0
                and not self._matches_virtual_input(d.get("name", ""))
            ]
            if not candidates:
                return None, "Default Input (no physical mic found)"
            candidates.sort(
                key=lambda d: int(d.get("max_input_channels", 0) or 0), reverse=True
            )
            chosen = candidates[0]
            label = str(chosen.get("name", "Default Input"))
            return chosen, label
        except Exception as exc:
            return None, "Default Input (error: %s)" % exc

    def _sample_device_label(self):
        return "physical mic (VB-Cable / loopback excluded)"

    def _capture_lock_acquired(self, want, log=None):
        """Acquire/release the shared audio-capture lock. want=True grabs the mic for a Sample."""
        global _AUDIO_CAPTURE_ACTIVE
        if want:
            got = _AUDIO_CAPTURE_LOCK.acquire(blocking=False)
            if got:
                _AUDIO_CAPTURE_ACTIVE = True
                if log is not None:
                    log(
                        "[LIVE LISTEN] Paused: a Sample is being captured - "
                        "LISTEN will skip this window."
                    )
                return True
            return False
        _AUDIO_CAPTURE_ACTIVE = False
        _AUDIO_CAPTURE_LOCK.release()
        return True

    @property
    def sample_capture_active(self):
        return _AUDIO_CAPTURE_ACTIVE

    def _to_mono(self, frames):
        import numpy as np  # type: ignore[import-not-found]

        arr = np.asarray(frames, dtype=np.float32)
        if arr.ndim == 1:
            return arr
        return arr.mean(1)

    def _trim_silence(self, mono, sr, atol=0.002):
        import numpy as np  # type: ignore[import-not-found]

        arr = np.asarray(mono, dtype=np.float32).ravel()
        frame = max(1, int(sr * 0.02))
        hop = max(1, int(sr * 0.01))
        if arr.size < frame:
            return arr[None, :], 0, arr.size
        n_frames = (arr.size - frame) // hop + 1
        energy = []
        for f in range(n_frames):
            chunk = arr[f * hop : f * hop + frame]
            energy.append(float(np.sqrt(np.mean(chunk ** 2))) if chunk.size else 0.0)
        energy = np.array(energy, dtype=np.float32)
        sig = energy > atol
        if not np.any(sig):
            return arr[None, :], 0, arr.size
        start = int(np.argmax(sig) * hop)
        end = int((np.argmax(sig[::-1]) + np.argmax(sig)) * hop)
        return arr[start:end], start, end

    def capture_voice_sample(
        self,
        seconds: float | None = None,
        *,
        device: int | None = None,
        log: Callable[[str], None] | None = None,
    ) -> str:
        """Record a live microphone sample and save it as the clone reference WAV.

        The reference is the speaker latent's cleanest possible input, so this path:
          * records from an EXPLICIT physical microphone (VB-Cable / loopback / "Stereo Mix" /
            "What U Hear" are never allowed - those produce the garbled "animated/monster"
            XTTS clones),
          * holds a SHARED lock for the WHOLE capture window, so the live-LISTEN worker skips
            exactly this window (no concurrent `sd.rec()` on the same device),
          * records with a small LEAD-IN + LEAD-OUT buffer and a tiny settle delay so the first
            word is not clipped by the "Recording" prompt,
          * ENERGY-trims leading/trailing silence so the reference is speech-only, and
          * refuses to accept an obviously hot/clipped or near-silent clip.

        Returns the saved wav path (empty string on failure).
        """
        dur = float(seconds or self.DEFAULT_SAMPLE_SECONDS)
        dur = max(self.MIN_SAMPLE_SECONDS, min(self.MAX_SAMPLE_SECONDS, dur))
        lead = 1.0  # extra 1.0s total: ~0.5s settle/lead-in + 0.5s lead-out (see design doc)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = self._samples_dir / f"voice_sample_{ts}.wav"



        # Dev note (#369): samples are WRONG because:
        #  1. the default capture device is the VB-Cable (the LISTEN engine's device) instead of
        #     the physical mic, so the reference is a room mix / bot-audio ghost, and
        #  2. `sd.rec()` runs concurrently with the live-LISTEN worker on the same device, so the
        #     buffer can collide and produce the garbled "animated/monster" XTTS clone.
        # This path fixes both:
        #   - records explicitly from the best PHYSICAL input (VB-Cable / loopback excluded),
        #   - holds _AUDIO_CAPTURE_LOCK across the whole capture so the LISTEN worker auto-skips
        #   - records 1s extra (settle + lead-out) and energy-trims silence so the reference
        #     is speech-only, and refuses clips that are clipped or too quiet to use.
        # Returns the saved wav path on success, "" on failure.
        import time as _time  # type: ignore[import-not-found]

        dur = float(seconds or self.DEFAULT_SAMPLE_SECONDS)
        dur = max(self.MIN_SAMPLE_SECONDS, min(self.MAX_SAMPLE_SECONDS, dur))
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = self._samples_dir / f"voice_sample_{ts}.wav"

        try:
            import numpy as np  # type: ignore[import-not-found]
            import sounddevice as sd  # type: ignore[import-not-found]

            # ---- 1. OWN THE MIC for the whole window (LISTEN auto-suspends) ----
            self._capture_lock_acquired(True, log=log)

            # ---- 2. Explicit physical mic (never VB-Cable / loopback) ----
            dev_ref, dev_label = self._physical_input_device()
            if dev_ref is None or int(dev_ref.get("max_input_channels", 0) or 0) <= 0:
                self._capture_lock_acquired(False, log=log)
                if log is not None:
                    log("[VOICE SAMPLE] No usable input device found - clone sample deferred.")
                return ""

            # Settle the mic so the first ~0.3s is not clipped by the prompt.
            _time.sleep(0.15)

            read_seconds = dur + 1.0 if device is None else dur
            self._work_started = time.monotonic()
            # Re-dispatch to the INT index (sounddevice accepts int or str indices).
            device_idx = int(dev_ref.get("index", -1))
            frames = sd.rec(
                int(read_seconds * self.SAMPLE_RATE),
                samplerate=self.SAMPLE_RATE,
                channels=self.SAMPLE_CHANNELS,
                dtype="float32",
                device=device_idx,
            )
            sd.wait()

            # ---- 3. Trim the lead-in (settling / "Recording now" tail) ----
            mono = self._to_mono(frames)
            trimmed, head_end, tail_start = self._trim_silence(
                mono, self.SAMPLE_RATE, atol=0.002
            )
            # Thin tail so the reference is speech focused, but never before head_end.
            tail_start = max(tail_start, head_end)
            mono = trimmed[:, : head_end]

            peak = self._peak(mono)
            if peak < 200:
                if log is not None:
                    log(
                        f"[VOICE SAMPLE] Sample very quiet (peak={peak}). Speak closer to the mic "
                        "and press 🎙️ Sample again for a cleaner clone."
                    )
            if peak >= 30000:
                if log is not None:
                    log(
                        f"[VOICE SAMPLE] Sample CLIPPED (peak={peak}). Remove noise/echo and try again."
                    )
            if self._write_wav(mono, out_path, self.SAMPLE_RATE):
                self._sample_wav = str(out_path)
                self._clone_ready = False
                self._clone_reference_wav = ""
                self._clone_is_default = False
                if log is not None:
                    log(
                        f"[VOICE SAMPLE] Captured {dur:.0f}s sample clean ({peak} peak, "
                        f"{head_end / self.SAMPLE_RATE:.1f}s speech, via {dev_label})."
                    )
                return str(out_path)
            if log is not None:
                log("[VOICE SAMPLE] Failed to write the sample WAV to disk.")
            return ""
        except Exception as exc:
            if log is not None:
                log(f"[VOICE SAMPLE] Microphone capture failed: {exc}")
            return ""

    # ------------------------------------------------------------------ DEFAULT / CLEAR
    def set_clone_as_default(self, log: Callable[[str], None] | None = None) -> bool:
        """Route the SPECIAL MIC LINE's Coqui default to the live clone (the last Coqui menu slot)."""
        if not self._clone_ready or not self._clone_reference_wav:
            if log is not None:
                log("[DEFAULT ❌] No verified clone yet — press 🎙️ Sample then 🧬 Clone Voice first.")
            return False
        self._clone_is_default = True
        if log is not None:
            log(
                "[DEFAULT ✅] SPECIAL MIC LINE now broadcasts with the cloned voice "
                "(select 'Coqui 🎙️ CLONE (Active)' in the Coqui sub-menu)."
            )
        return True

    def clear_default_voice(self, log: Callable[[str], None] | None = None) -> bool:
        """Clear the active clone/default so Coqui reverts to the built-in test voice."""
        self._clone_is_default = False
        self._clone_ready = False
        self._clone_reference_wav = ""
        # Keep the captured sample on disk (harmless) but require a fresh Clone for a new default.
        if log is not None:
            log(
                "[CLR VOICE 🧹] Coqui default voice cleared. "
                "Coqui now uses the built-in test voice; capture a new Sample to clone someone else."
            )
        return True

    # ------------------------------------------------------------------ SYNTHESIS
    def _run_xtts(self, model: Any, text: str, speaker_wav: str, out_path: str) -> None:
        """Invoke whichever XTTS synthesis entrypoint this Coqui build exposes."""
        if hasattr(model, "tts_with_vc_to_file"):
            model.tts_with_vc_to_file(text=text, speaker_wav=speaker_wav, file_path=out_path, language="en")
            return
        if hasattr(model, "tts_to_file"):
            model.tts_to_file(text=text, speaker_wav=speaker_wav, file_path=out_path, language="en")
            return
        if hasattr(model, "synthesize"):
            model.synthesize(text=text, speaker_wav=speaker_wav, output_path=out_path, language="en")
            return
        raise RuntimeError("No XTTS synthesis method found")

    def synthesize(
        self,
        text: str,
        wav_path: Path,
        voice_label: str,
        *,
        log: Callable[[str], None] | None = None,
    ) -> tuple[bool, str]:
        """Synthesize `text` with the selected Coqui voice into `wav_path`.

        Returns (ok, engine_name). When (False, "coqui-unavailable") is returned the caller should
        fall back to Edge Neural so the broadcast still happens with KaeKae's voice.
        """
        built_in = COQUI_FEMALE_VOICES.get(voice_label)
        is_clone = voice_label in {COQUI_CLONE_VOICE, COQUI_CLONE_EMPTY}
        if is_clone and self._clone_is_default and self._clone_reference_wav:
            speaker_wav = self._clone_reference_wav
        elif built_in:
            speaker_wav = ""  # XTTS resolves built-in names itself
        elif voice_label == COQUI_DEFAULT_VOICE:
            speaker_wav = self._clone_reference_wav if self._clone_ready else ""
        else:
            # Unknown Coqui label: prefer an active clone, else the raw captured sample.
            speaker_wav = self._clone_reference_wav or self._sample_wav

        model = self._ensure_model(log=log)
        if model is None:
            return (False, "coqui-unavailable")
        try:
            speaker = built_in if (built_in and not speaker_wav) else None
            with self._lock:
                if speaker is not None:
                    # Built-in named speaker.
                    try:
                        model.tts_to_file(
                            text=text,
                            speaker=speaker,
                            language="en",
                            file_path=str(wav_path),
                        )
                    except TypeError:
                        self._run_xtts(model, text, speaker, str(wav_path))
                else:
                    self._run_xtts(model, text, speaker_wav, str(wav_path))
            if wav_path.exists() and wav_path.stat().st_size > 1024:
                if log is not None:
                    log(f"[COQUI XTTS ✅] Synthesized '{voice_label}' -> {wav_path.name}")
                return (True, "coqui-xtts-v2")
            return (False, "coqui-empty-output")
        except Exception as exc:
            if log is not None:
                log(f"[COQUI XTTS ⚠️] Synthesis failed for '{voice_label}': {exc}. Falling back to Edge Neural.")
            return (False, f"coqui-error: {exc}")



class LocalKokoroVoiceEngine:
    """Local Kokoro-82M ONNX voice engine for the SPECIAL MIC LINE — offline, unlimited, no API key.

    Mirrors CoquiXTTSVoiceEngine's API so the SPECIAL MIC LINE, GUI and tests never fork:
      * Fully lazy + import-safe: if `kokoro_onnx`/`onnxruntime` are missing or the ONNX assets are
        absent, construction and `is_available()` NEVER raise — they return False so the caller keeps
        the reliable Coqui/Edge fallback and the microphone ALWAYS still broadcasts.
      * `synthesize()` returns (ok, engine_name) with a "kokoro-unavailable" sentinel when the model
        can't run, so `_synthesize_realistic_tts_wav` transparently falls through to Coqui -> Edge.
      * Output is 16-bit PCM WAV (24kHz native) which `_play_wav_to_vbcable` plays directly.
      * Women-only presets (KOKORO_FEMALE_VOICES) + a single Default test entry, per operator rule.

    Provider strategy (stability-first): the model is tiny (82M), so CPU is already ~0.7s/line and
    ALWAYS works. DirectML (RX 9070 XT) is opt-in via set_prefer_gpu(True) or KOKORO_GPU=1 because
    some DirectML builds hit a ConvTranspose vocoder error. Whenever a GPU run raises, the engine
    automatically reloads on CPU once and retries, so a line can never hard-fail.
    """

    SAMPLE_RATE = 24000

    def __init__(self) -> None:
        self._base_dir = Path(__file__).resolve().parent
        self._lock = threading.Lock()
        self._kokoro: Any = None
        self._load_error: str = ""
        self._device = resolve_compute_device()
        self._active_provider: str = ""          # "cpu" | "directml" once loaded
        self._prefer_gpu: bool = str(os.environ.get("KOKORO_GPU", "")).strip() == "1"

    # ------------------------------------------------------------------ AVAILABILITY
    def is_available(self) -> bool:
        """True if an ONNX runtime + the Kokoro model/voices files are present (no heavy load)."""
        try:
            import importlib.util as _u

            has_rt = _u.find_spec("onnxruntime") is not None or _u.find_spec("kokoro_onnx") is not None
            if not has_rt:
                return False
            onnx_p = self._pick_onnx_path()
            voices_p = Path(str(LOCAL_KOKORO_MODEL_DIR)) / str(LOCAL_KOKORO_VOICES_FILE)
            return bool(onnx_p is not None and onnx_p.exists() and voices_p.exists())
        except Exception:
            return False

    @staticmethod
    def _pick_onnx_path() -> Path | None:
        """Prefer the FP16 model on DirectML; fall back to the FP32 model the installer ships."""
        import config as _cfg

        model_dir = Path(str(LOCAL_KOKORO_MODEL_DIR))
        fp16 = model_dir / str(getattr(_cfg, "LOCAL_KOKORO_ONNX_FP16_FILE", "kokoro-v1.0-fp16.onnx"))
        fp32 = model_dir / str(LOCAL_KOKORO_ONNX_FILE)
        if fp16.exists() and fp16.stat().st_size > 1024:
            return fp16
        if fp32.exists() and fp32.stat().st_size > 1024:
            return fp32
        return None

    def device_info(self) -> dict[str, Any]:
        """Freshly resolve the compute backend so GPU/CPU status is always current."""
        try:
            self._device = resolve_compute_device()
        except Exception:
            pass
        return self._device

    def set_prefer_gpu(self, prefer: bool) -> None:
        """Opt the Kokoro engine into DirectML (RX 9070 XT) or back to CPU. Reloads on next synth.

        CPU is the default (tiny model, ~0.7s/line, always works). GPU is opt-in because some
        DirectML builds raise on the vocoder ConvTranspose node — the engine auto-falls-back to CPU
        on any GPU error, so this is purely a preference, never a hard requirement.
        """
        want = bool(prefer)
        if want == self._prefer_gpu and self._kokoro is not None:
            return
        self._prefer_gpu = want
        # Drop the cached session so the next synthesize reloads with the new provider.
        self._kokoro = None
        self._active_provider = ""

    def gpu_available(self) -> bool:
        """True if a DirectML execution provider is present in this onnxruntime build."""
        try:
            import onnxruntime as _ort

            return "DmlExecutionProvider" in _ort.get_available_providers()
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        return {
            "available": self.is_available(),
            "loaded": self._kokoro is not None,
            "load_error": self._load_error,
            "device": self._device,
            "provider": self._active_provider,
            "prefer_gpu": self._prefer_gpu,
            "gpu_available": self.gpu_available(),
        }

    # ------------------------------------------------------------------ MODEL LOADING
    def _build_kokoro(self, provider: str, log: Callable[[str], None] | None = None) -> Any | None:
        """Construct a fresh Kokoro session pinned to `provider` via ONNX_PROVIDER (thread-safe caller).

        `kokoro_onnx` picks providers from ONNX_PROVIDER (or all-available when an accelerated
        onnxruntime is installed), so we set the env var before constructing. No `providers=` kwarg
        exists in current kokoro-onnx releases.
        """
        onnx_p = self._pick_onnx_path()
        voices_p = Path(str(LOCAL_KOKORO_MODEL_DIR)) / str(LOCAL_KOKORO_VOICES_FILE)
        if onnx_p is None or not onnx_p.exists() or not voices_p.exists():
            self._load_error = "Kokoro assets missing in data/models/kokoro"
            return None
        from kokoro_onnx import Kokoro as _Kokoro  # type: ignore[import-not-found]

        prev = os.environ.get("ONNX_PROVIDER")
        os.environ["ONNX_PROVIDER"] = provider
        try:
            return _Kokoro(str(onnx_p), str(voices_p))
        finally:
            # Restore so we don't leak a process-wide provider pin to other callers.
            if prev is None:
                os.environ.pop("ONNX_PROVIDER", None)
            else:
                os.environ["ONNX_PROVIDER"] = prev

    def _ensure_kokoro(self, log: Callable[[str], None] | None = None) -> Any | None:
        """Lazily load the Kokoro ONNX session. GPU-opt-in with automatic CPU fallback. Thread-safe."""
        if self._kokoro is not None:
            return self._kokoro
        with self._lock:
            if self._kokoro is not None:
                return self._kokoro
            if not self.is_available():
                self._load_error = "Kokoro assets or onnxruntime missing"
                return None
            dev = self.device_info()
            # Prefer DirectML on the 9070 XT only when explicitly opted in AND the provider exists.
            want_gpu = self._prefer_gpu and self.gpu_available()
            primary = "DmlExecutionProvider" if want_gpu else "CPUExecutionProvider"
            try:
                if log is not None:
                    label = f"{dev.get('name', 'cpu')} (DirectML)" if want_gpu else "CPU"
                    log(f"[KOKORO 🎙️] Loading local Kokoro ONNX on {label}...")
                kok = self._build_kokoro(primary, log=log)
                # Warm-up probe: some DirectML builds raise on the vocoder ConvTranspose node.
                try:
                    kok.create("ready", voice="af_heart", speed=1.0, lang="en-us")
                except TypeError:
                    kok.create("ready", voice="af_heart")
                self._kokoro = kok
                self._active_provider = "directml" if want_gpu else "cpu"
                self._load_error = ""
                if log is not None:
                    if want_gpu:
                        log("[KOKORO ✅] Local GPU voice ready on the RX 9070 XT (DirectML) — offline & unlimited.")
                    else:
                        log("[KOKORO ✅] Local voice ready on CPU (~0.7s/line) — offline & unlimited.")
                return self._kokoro
            except Exception as exc:
                # GPU path failed -> auto-reload on CPU ONCE so a line can never hard-fail.
                if want_gpu:
                    if log is not None:
                        log(
                            f"[KOKORO ⚠️] DirectML run failed ({str(exc).splitlines()[0][:80]}); "
                            "reloading on CPU so the mic still speaks."
                        )
                    try:
                        self._kokoro = self._build_kokoro("CPUExecutionProvider", log=log)
                        self._active_provider = "cpu"
                        self._load_error = ""
                        return self._kokoro
                    except Exception as exc2:
                        self._load_error = str(exc2)
                else:
                    self._load_error = str(exc)
                self._kokoro = None
                if log is not None:
                    log(f"[KOKORO ⚠️] Unavailable ({self._load_error}); falling back to Coqui/Edge Neural.")
                return None

    # ------------------------------------------------------------------ SYNTHESIS

    def synthesize(
        self,
        text: str,
        wav_path: Path,
        voice_label: str,
        *,
        log: Callable[[str], None] | None = None,
    ) -> tuple[bool, str]:
        """Synthesize `text` with the selected Kokoro preset into a 16-bit PCM WAV.

        Returns (ok, engine_name). (False, "kokoro-unavailable") tells the caller to fall back
        to Coqui -> Edge Neural so the broadcast still happens.
        """
        vid = KOKORO_FEMALE_VOICES.get(str(voice_label or ""), "af_heart")
        if str(voice_label or "") == str(KOKORO_DEFAULT_VOICE):
            vid = "af_heart"
        kok = self._ensure_kokoro(log=log)
        if kok is None:
            return (False, "kokoro-unavailable")
        try:
            txt = str(text or "").strip()
            if not txt:
                return (False, "kokoro-empty-text")
            import numpy as _np

            with self._lock:
                try:
                    out = kok.create(txt, voice=vid, speed=1.0, lang="en-us")
                except TypeError:
                    out = kok.create(txt, voice=vid)
            # kokoro-onnx returns either samples, or (samples, sample_rate) across versions.
            samples = out
            sr = self.SAMPLE_RATE
            if isinstance(out, tuple):
                samples = out[0]
                if len(out) > 1 and out[1]:
                    sr = out[1]
            arr = _np.asarray(samples, dtype=_np.float32).ravel()
            if arr.size == 0:
                return (False, "kokoro-empty-audio")
            arr = _np.clip(arr, -1.0, 1.0)
            pcm = (arr * 32767.0).astype("<i2")
            try:
                rate = int(sr) if int(sr) > 0 else self.SAMPLE_RATE
            except Exception:
                rate = self.SAMPLE_RATE
            with wave.open(str(wav_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(rate)
                wf.writeframes(pcm.tobytes())
            if log is not None:
                log(f"[KOKORO ✅] Synthesized '{voice_label}' -> {Path(wav_path).name}")
            return (True, "kokoro-local")
        except Exception as exc:
            if log is not None:
                log(f"[KOKORO ⚠️] Synthesis failed for '{voice_label}' ({exc}); falling back.")
            return (False, f"kokoro-error: {exc}")


class CamfrogUIAutomation:
    """Connect to a live Camfrog room regardless of dynamic room topic title changes."""

    # ------------------------------------------------------------------ SAMPLE
    @staticmethod
    def _matches_virtual_input(dev_name):
        """True if a sounddevice entry is a virtual/loopback capture device."""
        low = str(dev_name or "").lower()
        return any(kw in low for kw in _VIRTUAL_INPUT_KEYWORDS)

    def _query_devices(self):
        """Enumerate sounddevice capture devices (indirection so tests can monkeypatch it)."""
        import sounddevice as sd  # type: ignore[import-not-found]

        return sd.query_devices()

    def _physical_input_device(self):
        """Resolve the best PHYSICAL microphone for the voice sample.

        Excludes virtual/loopback devices (the LISTEN engine's devices) and any device with no
        positive input channels. Prefers the most channels; returns (None, label) when nothing
        usable is found so the caller can defer gracefully. Never touches the capture lock, so it
        is always safe to call even while the live-LISTEN worker holds it.
        """
        try:
            devices = self._query_devices()
            candidates = [
                d
                for d in devices
                if int(d.get("max_input_channels", 0) or 0) > 0
                and not self._matches_virtual_input(d.get("name", ""))
            ]
            if not candidates:
                return None, "Default Input (no physical mic found)"
            candidates.sort(
                key=lambda d: int(d.get("max_input_channels", 0) or 0), reverse=True
            )
            chosen = candidates[0]
            label = str(chosen.get("name", "Default Input"))
            return chosen, label
        except Exception as exc:
            return None, "Default Input (error: %s)" % exc

    def _sample_device_label(self):
        return "physical mic (VB-Cable / loopback excluded)"

    def _capture_lock_acquired(self, want, log=None):
        """Acquire/release the shared audio-capture lock. want=True grabs the mic for a Sample."""
        global _AUDIO_CAPTURE_ACTIVE
        if want:
            got = _AUDIO_CAPTURE_LOCK.acquire(blocking=False)
            if got:
                _AUDIO_CAPTURE_ACTIVE = True
                if log is not None:
                    log(
                        "[LIVE LISTEN] Paused: a Sample is being captured - "
                        "LISTEN will skip this window."
                    )
                return True
            return False
        _AUDIO_CAPTURE_ACTIVE = False
        _AUDIO_CAPTURE_LOCK.release()
        return True

    @property
    def sample_capture_active(self):
        return _AUDIO_CAPTURE_ACTIVE

    def _to_mono(self, frames):
        import numpy as np  # type: ignore[import-not-found]

        arr = np.asarray(frames, dtype=np.float32)
        if arr.ndim == 1:
            return arr
        return arr.mean(1)

    def _trim_silence(self, mono, sr, atol=0.002):
        import numpy as np  # type: ignore[import-not-found]

        arr = np.asarray(mono, dtype=np.float32).ravel()
        frame = max(1, int(sr * 0.02))
        hop = max(1, int(sr * 0.01))
        if arr.size < frame:
            return arr[None, :], 0, arr.size
        n_frames = (arr.size - frame) // hop + 1
        energy = []
        for f in range(n_frames):
            chunk = arr[f * hop : f * hop + frame]
            energy.append(float(np.sqrt(np.mean(chunk ** 2))) if chunk.size else 0.0)
        energy = np.array(energy, dtype=np.float32)
        sig = energy > atol
        if not np.any(sig):
            return arr[None, :], 0, arr.size
        start = int(np.argmax(sig) * hop)
        end = int((np.argmax(sig[::-1]) + np.argmax(sig)) * hop)
        return arr[start:end], start, end

    def __init__(self, title_re: str = CAMFROG_WINDOW_TITLE_RE, cache_seconds: float = UIA_CACHE_SECONDS):
        self.title_re = title_re
        self.cache_seconds = cache_seconds
        self.app: Any = None
        self.window: Any = None
        self._hwnd: int | None = None
        self._last_valid_win_rect: tuple[int, int, int, int] = CALIBRATED_WINDOW_RECT
        self._nodes: list[UIANode] = []
        self._nodes_at = 0.0
        self._ocr_speaker_cache: tuple[tuple[int, int, int, int], float, str] | None = None
        self._ocr_userlist_cache: tuple[float, int | None, list[str]] | None = None
        self._last_good_user_count: int = 0
        self._last_good_users: list[str] = []
        self._last_scroll_pulse_at: float = 0.0
        self._last_chat_change_at: float = time.monotonic()
        self._last_chat_fingerprint: str = ""
        self.auto_scroll_enabled: bool = False
        self.auto_scroll_idle_seconds: float = 60.0
        self.allow_physical_fallback: bool = True
        self._send_lock = threading.Lock()
        self._known_users: set[str] = {BOT_USERNAME}
        self.tts_voice: str = EDGE_TTS_DEFAULT_VOICE
        self.last_tts_engine: str = "edge-tts"
        self.last_error = ""
        # SPECIAL MIC LINE voice routing: `tts_voice_label` may be an Edge female label OR a Coqui
        # label (women / default-test / CLONE). `is_coqui_voice()` decides which engine synthesizes.
        self.tts_voice_label: str = list(EDGE_FEMALE_VOICES.keys())[0]
        self.coqui = CoquiXTTSVoiceEngine()
        # Local Kokoro-82M ONNX engine (AMD DirectML first) — the daily-driver, offline/unlimited voice.
        self.kokoro = LocalKokoroVoiceEngine()
        # Optional callback that streams engine progress (Coqui/XTTS clone + synthesis, DirectML device
        # handoff, etc.) into the operator terminals. Wired up by the orchestrator after startup.
        self.log_callback: Callable[[str], None] | None = None
        # Custom or auto-calibrated screen coordinates (saved in data/camfrog_calibration.json)
        self.calibrated_chat_input_screen_pt: tuple[int, int] | None = None
        self.calibrated_talk_button_screen_pt: tuple[int, int] | None = None
        self.calibrated_chat_input_rect: tuple[int, int, int, int] = CHAT_INPUT_RECT
        self.calibrated_talk_button_rect: tuple[int, int, int, int] = TALK_BUTTON_RECT
        self._load_persisted_calibration()

    def _load_persisted_calibration(self) -> None:
        """Load any user-calibrated or auto-calibrated coordinates from data/camfrog_calibration.json."""
        try:
            cal = load_calibration_overrides()
            pt = cal.get("chat_input_screen_pt")
            if isinstance(pt, (list, tuple)) and len(pt) == 2:
                self.calibrated_chat_input_screen_pt = (int(pt[0]), int(pt[1]))
            tpt = cal.get("talk_button_screen_pt")
            if isinstance(tpt, (list, tuple)) and len(tpt) == 2:
                self.calibrated_talk_button_screen_pt = (int(tpt[0]), int(tpt[1]))
            rect = cal.get("chat_input_rect")
            if isinstance(rect, (list, tuple)) and len(rect) == 4:
                self.calibrated_chat_input_rect = (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
            trect = cal.get("talk_button_rect")
            if isinstance(trect, (list, tuple)) and len(trect) == 4:
                self.calibrated_talk_button_rect = (int(trect[0]), int(trect[1]), int(trect[2]), int(trect[3]))
        except Exception:
            pass

    def _get_window_rect(self) -> tuple[int, int, int, int]:
        """Return the current Camfrog window bounding box [left, top, right, bottom], falling back to CALIBRATED_WINDOW_RECT."""
        if os.name == "nt" and self._hwnd:
            try:
                class _RECT(ctypes.Structure):
                    _fields_ = [
                        ("left", ctypes.c_long),
                        ("top", ctypes.c_long),
                        ("right", ctypes.c_long),
                        ("bottom", ctypes.c_long),
                    ]
                rc = _RECT()
                if ctypes.windll.user32.GetWindowRect(wintypes.HWND(self._hwnd), ctypes.byref(rc)):
                    if rc.left > -5000 and (rc.right - rc.left) >= 400:
                        self._last_valid_win_rect = (int(rc.left), int(rc.top), int(rc.right), int(rc.bottom))
                        return self._last_valid_win_rect
            except Exception:
                pass
        wrect = self._window_rect()
        if wrect is not None and wrect[0] > -5000 and (wrect[2] - wrect[0]) >= 400:
            self._last_valid_win_rect = wrect
        return self._last_valid_win_rect

    def _scale_rect(self, cal_rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        """Translate a calibrated reference rectangle [1273, 0, 2567, 1399] into actual screen coordinates
        for the current Camfrog window position and height.
        """
        raw_w = self._get_window_rect()
        if isinstance(raw_w, (list, tuple)) and len(raw_w) == 4:
            win_l, win_t = int(raw_w[0]), int(raw_w[1])
        else:
            win_l, win_t = CALIBRATED_WINDOW_RECT[0], CALIBRATED_WINDOW_RECT[1]
        ref_l, ref_t, ref_r, ref_b = CALIBRATED_WINDOW_RECT
        dx = win_l - ref_l
        dy = win_t - ref_t
        l, t, r, b = cal_rect
        return (int(l + dx), int(t + dy), int(r + dx), int(b + dy))


    def connect_to_camfrog(self) -> bool:
        """Attach specifically to the Camfrog room window (even if minimized, unfocused, or on a 2nd monitor)."""
        global Application, Desktop, uia_send_keys, uia_click, uia_press, uia_release
        if (Application is None or Desktop is None) and os.name == "nt":
            try:
                from setup_env import bootstrap_environment
                bootstrap_environment()
                from pywinauto import Application as _App, Desktop as _Desk
                from pywinauto.keyboard import send_keys as _sk
                from pywinauto.mouse import click as _clk, press as _prs, release as _rel
                Application, Desktop = _App, _Desk
                uia_send_keys, uia_click, uia_press, uia_release = _sk, _clk, _prs, _rel
            except Exception:
                pass
        if Application is None or Desktop is None:
            self.last_error = "pywinauto is not installed; run python setup_env.py to install dependencies."
            return False

        try:
            title_pattern = re.compile(self.title_re)
            best_hwnd: int | None = None
            best_win: Any = None
            best_score = -1

            non_camfrog_keywords = (
                "visual studio", "vscode", "code -", "command prompt", "powershell",
                "windows terminal", "google chrome", "microsoft edge", "firefox",
                "file explorer", "task manager", "notepad", "pepefrog", "kaekae_toad",
                "command center", "setup wizard",
            )

            # 1) Fast Win32 EnumWindows scan (~5ms, never hangs on unresponsive UIA background windows)
            if os.name == "nt":
                user32 = ctypes.windll.user32

                class _RECT(ctypes.Structure):
                    _fields_ = [
                        ("left", ctypes.c_long),
                        ("top", ctypes.c_long),
                        ("right", ctypes.c_long),
                        ("bottom", ctypes.c_long),
                    ]

                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
                candidates: list[tuple[int, int, str]] = []

                def _enum_cb(hwnd_val: int, _lparam: int) -> bool:
                    try:
                        hwnd = int(hwnd_val or 0)
                        if not hwnd or not user32.IsWindow(wintypes.HWND(hwnd)):
                            return True
                        length = user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
                        title_buf = ctypes.create_unicode_buffer(length + 1)
                        if length > 0:
                            user32.GetWindowTextW(wintypes.HWND(hwnd), title_buf, length + 1)
                        title = title_buf.value or ""
                        title_lower = title.lower()

                        if any(kw in title_lower for kw in non_camfrog_keywords):
                            return True

                        cls_buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(wintypes.HWND(hwnd), cls_buf, 256)
                        cls_name = (cls_buf.value or "").lower()

                        rc = _RECT()
                        user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rc))
                        w = rc.right - rc.left
                        h = rc.bottom - rc.top
                        is_minimized = bool(user32.IsIconic(wintypes.HWND(hwnd))) or rc.left <= -10000 or w < 200 or h < 200

                        if not is_minimized and not user32.IsWindowVisible(wintypes.HWND(hwnd)):
                            return True
                        if not is_minimized and (w < 400 or h < 300):
                            return True

                        score = 0
                        if title_pattern.search(title) or "camfrog" in title_lower or "camfrog" in cls_name:
                            score += 2500

                        if not is_minimized:
                            if abs(rc.left - 1273) <= 45 and abs(rc.right - 2567) <= 45:
                                score += 3500
                            elif rc.left <= 1291 and rc.right >= 2550 and w <= 2700:
                                score += 800

                        # Fast Win32 child probe for CButtonTS (Talk button / room controls)
                        cbutton_count = 0
                        child = user32.FindWindowExW(wintypes.HWND(hwnd), wintypes.HWND(0), "CButtonTS", None)
                        while child and cbutton_count < 15:
                            cbutton_count += 1
                            child = user32.FindWindowExW(wintypes.HWND(hwnd), wintypes.HWND(child), "CButtonTS", None)

                        if cbutton_count > 0:
                            score += 5000 + cbutton_count * 120

                        if not is_minimized and w > 2800 and cbutton_count == 0:
                            return True

                        if score > 0:
                            candidates.append((score, hwnd, title))
                    except Exception:
                        pass
                    return True

                enum_cb_inst = WNDENUMPROC(_enum_cb)
                user32.EnumWindows(enum_cb_inst, 0)
                if candidates:
                    candidates.sort(key=lambda item: item[0], reverse=True)
                    best_score, best_hwnd, _ = candidates[0]

            # 2) Fallback to UIA Desktop().windows() ONLY for unit-test mocks (when os.name != "nt" or Desktop is mocked)
            if best_hwnd is None and (os.name != "nt" or "unittest" in getattr(Desktop, "__module__", "")):
                all_windows = Desktop(backend="uia").windows(visible_only=False)
                for win in all_windows:
                    try:
                        title = win.window_text() or ""
                        title_lower = title.lower()
                        cls_name = (win.class_name() or "").lower()

                        if any(kw in title_lower for kw in non_camfrog_keywords):
                            continue

                        rect = win.rectangle()
                        w, h = rect.width(), rect.height()
                        is_minimized = rect.left <= -10000 or w < 200 or h < 200

                        if not is_minimized and (w < 400 or h < 300):
                            continue

                        score = 0
                        if title_pattern.search(title) or "camfrog" in title_lower or "camfrog" in cls_name:
                            score += 2500

                        if not is_minimized:
                            if abs(rect.left - 1273) <= 45 and abs(rect.right - 2567) <= 45:
                                score += 3500
                            elif rect.left <= 1291 and rect.right >= 2550 and w <= 2700:
                                score += 800

                        cbutton_count = 0
                        try:
                            cbutton_count = len(win.descendants(class_name="CButtonTS"))
                        except Exception:
                            cbutton_count = 0

                        if cbutton_count > 0:
                            score += 5000 + cbutton_count * 120

                        if not is_minimized and w > 2800 and cbutton_count == 0:
                            continue

                        if score > best_score:
                            best_score = score
                            best_win = win
                    except Exception:
                        continue

                if best_win is not None and best_score > 0:
                    best_hwnd = int(best_win.handle)

            if best_hwnd is None or best_score <= 0:
                self.last_error = "Could not find an open Camfrog room window on the desktop."
                return False

            self._hwnd = int(best_hwnd)
            if best_win is not None:
                self.window = best_win
            else:
                # Attach directly to the single HWND via Desktop(backend="uia").window(handle=...)
                # instead of Application().connect(handle=...) which walks WMI/process modules and can hang!
                self.window = Desktop(backend="uia").window(handle=self._hwnd)
            # If the user minimized Camfrog, gently restore it in the background (SW_SHOWNOACTIVATE)
            # so Chromium/CEF keeps updating the live UIA accessibility tree without stealing focus!
            self._ensure_renderable_in_background()
            self._nodes = []
            self._nodes_at = 0.0
            self.last_error = ""
            return True

        except Exception as error:
            self.app = None
            self.window = None
            self._hwnd = None
            self.last_error = f"Camfrog UIA connection failed: {error}"
            return False

    def _ensure_renderable_in_background(self) -> None:
        """If Camfrog is minimized to the taskbar (IsIconic), restore it via SW_SHOWNOACTIVATE without calling SetForegroundWindow."""
        if os.name != "nt" or not self._hwnd:
            return
        try:
            user32 = ctypes.windll.user32
            if user32.IsIconic(wintypes.HWND(self._hwnd)):
                user32.ShowWindow(wintypes.HWND(self._hwnd), SW_SHOWNOACTIVATE)
        except Exception:
            pass

    def is_connected(self) -> bool:
        try:
            if os.name == "nt" and self._hwnd:
                if not bool(ctypes.windll.user32.IsWindow(wintypes.HWND(self._hwnd))):
                    return False
                return True
            if self.window is None or not bool(self.window.exists(timeout=0)):
                return False
            rect = self.window.rectangle()
            if rect.width() > 2800:
                return False
            return True
        except Exception:
            return False

    @staticmethod
    def _extract_control_text(control: Any, info: Any) -> str:
        """Ultra-fast COM text read: only read info.name to avoid slow COM exception storms on empty nodes."""
        try:
            direct = info.name
            if direct and isinstance(direct, str):
                stripped = direct.strip()
                if stripped:
                    return stripped
        except Exception:
            pass
        return ""

    def _ocr_screen_rect(self, left: int, top: int, right: int, bottom: int, scale: int = 3) -> list[str]:
        """Use built-in Windows 10/11 WinRT OCR (Windows.Media.Ocr).
        Uses Win32 PrintWindow on the Camfrog HWND first so OCR works even when Camfrog is behind another window or covered by a taskbar popup!
        """
        if os.name != "nt":
            return []
        # Translate calibrated screen coordinates [1273, 0, ...] to current window position
        win_l, win_t, _, _ = self._last_valid_win_rect
        dx = win_l - CALIBRATED_WINDOW_RECT[0]
        dy = win_t - CALIBRATED_WINDOW_RECT[1]
        scr_left = int(left + dx)
        scr_top = int(top + dy)
        rel_x = max(0, int(left - CALIBRATED_WINDOW_RECT[0]))
        rel_y = max(0, int(top - CALIBRATED_WINDOW_RECT[1]))
        hwnd_val = int(self._hwnd or 0)

        w = max(16, int(right - left))
        h = max(12, int(bottom - top))
        scale = max(1, min(4, int(scale)))
        pad = 16
        ps_script = f"""
$ErrorActionPreference = 'Stop'
try {{
    Add-Type -AssemblyName System.Drawing
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    if (-not ("Win32PrintHelper" -as [type])) {{
        Add-Type @"
        using System;
        using System.Runtime.InteropServices;
        public class Win32PrintHelper {{
            [DllImport("user32.dll")]
            public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);
        }}
"@
    }}
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
    $null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]

    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    }})[0]
    function Await($WinRtTask, $ResultType) {{
        $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
        $netTask = $asTask.Invoke($null, @($WinRtTask))
        $netTask.Wait(4000) | Out-Null
        return $netTask.Result
    }}

    $bmp = New-Object System.Drawing.Bitmap({w}, {h})
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $captured = $false
    if ({hwnd_val} -ne 0) {{
        try {{
            $winW = [Math]::Max({rel_x + w + 16}, 1300)
            $winH = [Math]::Max({rel_y + h + 16}, 1410)
            $fullBmp = New-Object System.Drawing.Bitmap($winW, $winH)
            $fg = [System.Drawing.Graphics]::FromImage($fullBmp)
            $hdc = $fg.GetHdc()
            $ok = [Win32PrintHelper]::PrintWindow([IntPtr]{hwnd_val}, $hdc, 2)
            $fg.ReleaseHdc($hdc)
            $fg.Dispose()
            if ($ok) {{
                $srcRect = New-Object System.Drawing.Rectangle({rel_x}, {rel_y}, {w}, {h})
                $dstRect = New-Object System.Drawing.Rectangle(0, 0, {w}, {h})
                $g.DrawImage($fullBmp, $dstRect, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
                $captured = $true
            }}
            $fullBmp.Dispose()
        }} catch {{}}
    }}
    if (-not $captured) {{
        $g.CopyFromScreen({scr_left}, {scr_top}, 0, 0, $bmp.Size)
    }}
    $g.Dispose()

    $sw = {w * scale + pad * 2}
    $sh = {h * scale + pad * 2}
    $scaled = New-Object System.Drawing.Bitmap($sw, $sh)
    $gs = [System.Drawing.Graphics]::FromImage($scaled)
    $gs.Clear([System.Drawing.Color]::White)
    $gs.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $gs.DrawImage($bmp, {pad}, {pad}, {w * scale}, {h * scale})
    $gs.Dispose()
    $bmp.Dispose()

    $tmpPath = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "camfrog_ocr_" + [guid]::NewGuid().ToString("N") + ".png")
    $scaled.Save($tmpPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $scaled.Dispose()

    try {{
        $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($tmpPath)) ([Windows.Storage.StorageFile])
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Storage.Imaging.BitmapDecoder])
        $sbitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
        $ocrResult = Await ($engine.RecognizeAsync($sbitmap)) ([Windows.Media.Ocr.OcrResult])
        $stream.Dispose()
        foreach ($line in $ocrResult.Lines) {{
            Write-Output $line.Text
        }}
    }} finally {{
        Remove-Item -LiteralPath $tmpPath -Force -ErrorAction SilentlyContinue
    }}
}} catch {{
}}
"""
        try:
            creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
            startupinfo = None
            if os.name == "nt" and hasattr(subprocess, "STARTUPINFO"):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
                startupinfo.wShowWindow = 0  # SW_HIDE
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=2.2,
                check=False,
                creationflags=creationflags,
                startupinfo=startupinfo,
            )
            return [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
        except Exception:
            return []

    def _match_known_username(self, candidate: str) -> str:
        """If OCR has a 1-char typo against a known room username (or KaeKae_Toad), snap to the known username."""
        if not candidate:
            return ""
        cand_lower = candidate.lower()
        known_map = {u.lower(): u for u in self._known_users if u}
        if cand_lower in known_map:
            return known_map[cand_lower]
        matches = difflib.get_close_matches(cand_lower, list(known_map.keys()), n=1, cutoff=0.78)
        if matches:
            return known_map[matches[0]]
        return candidate

    def _normalize_rect_to_calibrated(self, left: int, top: int, right: int, bottom: int) -> tuple[int, int, int, int]:
        """Translate any screen rectangle into the calibrated [1273, 0, 2567, 1399] coordinate frame.
        This ensures the bot works on ANY monitor or window position without requiring [1273, 0].
        """
        win_l, win_t, _, _ = self._last_valid_win_rect
        dx = win_l - CALIBRATED_WINDOW_RECT[0]
        dy = win_t - CALIBRATED_WINDOW_RECT[1]
        if abs(dx) <= 4 and abs(dy) <= 4:
            return left, top, right, bottom
        return left - dx, top - dy, right - dx, bottom - dy

    def _calibrated_to_screen_point(self, cal_x: int, cal_y: int) -> tuple[int, int]:
        """Convert a calibrated point (e.g. Chat Input 1946, 1223) to actual screen coordinates."""
        win_l, win_t, _, _ = self._last_valid_win_rect
        dx = win_l - CALIBRATED_WINDOW_RECT[0]
        dy = win_t - CALIBRATED_WINDOW_RECT[1]
        return int(cal_x + dx), int(cal_y + dy)

    def _node_from_control(self, control: Any) -> UIANode | None:
        try:
            info = control.element_info
            ctype = info.control_type or ""
            # Skip purely decorative Image/Separator/Thumb/ScrollBar/TitleBar controls for speed
            if ctype in {"Image", "Separator", "Thumb", "ScrollBar", "TitleBar", "MenuBar", "MenuItem", "ToolTip"}:
                return None
            # Read info.name FIRST before querying info.rectangle!
            # 90% of Camfrog CEF/Qt descendants have an empty name; only unnamed Button/Pane/Edit/ListItem/DataItem controls
            # need their rectangle inspected when name is empty.
            text = self._extract_control_text(control, info)
            if not text and ctype not in {"Button", "Pane", "Edit", "Document", "ListItem", "DataItem"}:
                return None
            rect = info.rectangle
            raw_l, raw_t, raw_r, raw_b = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
            if raw_r <= raw_l or raw_b <= raw_t:
                return None
            left, top, right, bottom = self._normalize_rect_to_calibrated(raw_l, raw_t, raw_r, raw_b)
            # Skip controls outside the right-hand chat/user/mic panels (< 1275 in calibrated space)
            if right < 1275:
                return None
            return UIANode(
                control_type=ctype,
                name=text,
                class_name=(info.class_name or ""),
                left=left,
                top=top,
                right=right,
                bottom=bottom,
                control=control,
            )
        except Exception:
            return None

    def _pulse_cef_accessibility_tree(self) -> None:
        """Scroll the Camfrog chat feed ONLY if self.auto_scroll_enabled is True AND no chat changes
        have been detected for >= 60 seconds, so side browser windows or webpages never scroll down.
        """
        if not self.auto_scroll_enabled or os.name != "nt" or not self._hwnd:
            return
        now = time.monotonic()
        # Only scroll if zero chat changes were detected in the last 60 seconds (1 minute)
        if (now - self._last_chat_change_at) < self.auto_scroll_idle_seconds:
            return
        if (now - self._last_scroll_pulse_at) < self.auto_scroll_idle_seconds:
            return
        try:
            self._last_scroll_pulse_at = now
            user32 = ctypes.windll.user32
            cl, ct, cr, cb = CHAT_WINDOW_RECT
            scr_x, scr_y = self._calibrated_to_screen_point((cl + cr) // 2, cb - 40)
            chat_hwnd, _, _ = self._find_target_hwnd_and_client_pt(scr_x, scr_y, None)
            if chat_hwnd:
                user32.PostMessageW(wintypes.HWND(chat_hwnd), WM_VSCROLL, SB_BOTTOM, 0)
        except Exception:
            pass

    def _auto_scroll_chat_uia_containers(self, all_nodes: list[UIANode]) -> None:
        """Snap UIA ScrollPattern to 100% ONLY if self.auto_scroll_enabled is True and idle >= 60s."""
        if not self.auto_scroll_enabled:
            return
        now = time.monotonic()
        if (now - self._last_chat_change_at) < self.auto_scroll_idle_seconds:
            return
        cl, ct, cr, cb = CHAT_WINDOW_RECT
        ul_left = USER_LIST_RECT[0]
        has_below_viewport = any(
            n.control_type in {"Text", "Edit"} and cl - 20 <= n.left < ul_left and n.bottom > cb + 4
            for n in all_nodes
        )
        if not has_below_viewport:
            return
        for node in all_nodes:
            if (
                node.control is not None
                and node.control_type in {"Pane", "Document", "List", "Custom"}
                and node.left >= cl - 30
                and node.right <= min(cr + 25, ul_left)
                and node.height >= 200
            ):
                try:
                    iface_scroll = getattr(node.control, "iface_scroll", None)
                    if iface_scroll is not None:
                        v_pct = float(getattr(iface_scroll, "CurrentVerticalScrollPercent", 100.0))
                        if 0.0 <= v_pct < 99.5:
                            iface_scroll.SetScrollPercent(-1.0, 100.0)
                except Exception:
                    pass
        # Reset idle timer after performing the 60s recovery scroll
        self._last_chat_change_at = now

    def nodes(self, refresh: bool = False) -> list[UIANode]:
        if not self.is_connected() and not self.connect_to_camfrog():
            return []
        if not refresh and time.monotonic() - self._nodes_at < self.cache_seconds:
            return list(self._nodes)
        try:
            # Update current window position via fast Win32 GetWindowRect (never blocks on COM)
            if os.name == "nt" and self._hwnd:
                try:
                    class _RECT(ctypes.Structure):
                        _fields_ = [
                            ("left", ctypes.c_long),
                            ("top", ctypes.c_long),
                            ("right", ctypes.c_long),
                            ("bottom", ctypes.c_long),
                        ]
                    rc = _RECT()
                    if ctypes.windll.user32.GetWindowRect(wintypes.HWND(self._hwnd), ctypes.byref(rc)):
                        if rc.left > -5000 and (rc.right - rc.left) >= 400:
                            self._last_valid_win_rect = (int(rc.left), int(rc.top), int(rc.right), int(rc.bottom))
                except Exception:
                    pass
            else:
                try:
                    wrect = self.window.rectangle()
                    if wrect.left > -5000 and wrect.width() >= 400:
                        self._last_valid_win_rect = (int(wrect.left), int(wrect.top), int(wrect.right), int(wrect.bottom))
                except Exception:
                    pass

            # Keep CEF's internal accessibility tree awake and auto-scrolled even when Camfrog is covered or unfocused
            self._pulse_cef_accessibility_tree()

            found: list[UIANode] = []
            # Resolve the UIAWrapper once directly instead of triggering pywinauto WindowSpecification.wait()
            target_wrapper = self.window
            if hasattr(self.window, "wrapper_object"):
                try:
                    target_wrapper = self.window.wrapper_object()
                except Exception:
                    target_wrapper = self.window

            for control in target_wrapper.descendants():
                node = self._node_from_control(control)
                if node is not None:
                    found.append(node)
            self._auto_scroll_chat_uia_containers(found)
            self._nodes = found
            self._nodes_at = time.monotonic()
            return list(found)
        except Exception as error:
            self.last_error = f"Camfrog UIA tree read failed: {error}"
            return list(self._nodes)

    def _window_rect(self) -> tuple[int, int, int, int] | None:
        if not self.is_connected():
            return None
        try:
            rect = self.window.rectangle()
            return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
        except Exception:
            return None

    def layout_locations(self) -> dict[str, tuple[int, int, int, int] | None]:
        bounds = self._window_rect()
        nodes = self.nodes(refresh=True)
        talk = self._find_talk(nodes)
        chat_input = self._find_chat_input(nodes)
        speaker_node = self._find_active_speaker_node(nodes)
        return {
            "window": bounds,
            "chat_feed": CHAT_WINDOW_RECT,
            "chat_text": CHAT_TEXT_RECT,
            "chat_input": self._rect(chat_input) or CHAT_INPUT_RECT,
            "user_list": USER_LIST_RECT,
            "talk": self._rect(talk) or TALK_BUTTON_RECT,
            "active_speaker": self._rect(speaker_node) or ACTIVE_SPEAKER_RECT,
            "top_gifters": TOP_GIFTERS_RECT,
        }

    @staticmethod
    def _rect(node: UIANode | None) -> tuple[int, int, int, int] | None:
        return None if node is None else (node.left, node.top, node.right, node.bottom)

    @staticmethod
    def _find_talk(nodes: Iterable[UIANode]) -> UIANode | None:
        """Locate Talk Button(50000) at [l=1291,t=1169,r=1361,b=1195]."""
        tl, tt, tr, tb = TALK_BUTTON_RECT
        for node in nodes:
            if node.control_type == "Button":
                if abs(node.left - tl) <= 15 and abs(node.top - tt) <= 15 and abs(node.right - tr) <= 15:
                    return node
                if node.name.lower().strip() in {"talk", "push-to-talk", "push to talk"}:
                    return node
        return None

    def _find_chat_input(self, nodes: Iterable[UIANode]) -> UIANode | None:
        """Locate Chat Txt Field Pane(50033)/Edit(50004) at [l=1396,t=1206,r=2497,b=1241] or dynamically near the bottom of the chat pane."""
        il, it, ir, ib = self.calibrated_chat_input_rect or CHAT_INPUT_RECT
        node_list = list(nodes)
        calibrated = [
            node for node in node_list
            if node.control_type in {"Pane", "Edit", "Document", "Custom", "Text"}
            and abs(node.left - il) <= 45
            and abs(node.top - it) <= 45
            and abs(node.right - ir) <= 65
            and abs(node.bottom - ib) <= 45
        ]
        if calibrated:
            return min(calibrated, key=lambda n: abs(n.left - il) + abs(n.top - it))

        # Dynamic bottom-band scan: find wide input box or Pane below the Talk button / chat window
        talk_node = self._find_talk(node_list)
        min_top = (talk_node.bottom - 6) if talk_node is not None else 1185
        bottom_candidates = [
            node for node in node_list
            if node.control_type in {"Edit", "Pane", "Document", "Custom"}
            and node.top >= min_top
            and 18 <= node.height <= 68
            and node.width >= 320
            and node.left >= 1275
        ]
        if bottom_candidates:
            # Prefer Edit controls first, otherwise the closest wide input bar below Talk button
            edits = [n for n in bottom_candidates if n.control_type == "Edit"]
            if edits:
                return min(edits, key=lambda n: abs(n.top - it) + abs(n.left - il))
            return min(bottom_candidates, key=lambda n: abs(n.top - it) + abs(n.left - il))

        bounds = self._window_rect()
        if bounds is not None:
            _, top, _, bottom = bounds
            edits = [node for node in node_list if node.control_type == "Edit" and node.top >= top + (bottom - top) * 0.55]
            if edits:
                return max(edits, key=lambda node: node.width * node.height)
        return None

    def auto_calibrate_camfrog(self) -> dict[str, Any]:
        """Automatically scan the live Camfrog window, discover & lock the exact Chat Input Text Box,
        Talk Button, and Active Speaker coordinates on the user's monitor, and save them to data/camfrog_calibration.json.
        Never blocks on slow full-tree descendants() scans if nodes are not cached yet.
        """
        connected = self.is_connected() or self.connect_to_camfrog()
        raw_win_rect = self._get_window_rect()
        if isinstance(raw_win_rect, (list, tuple)) and len(raw_win_rect) == 4:
            win_l, win_t, win_r, win_b = (int(raw_win_rect[0]), int(raw_win_rect[1]), int(raw_win_rect[2]), int(raw_win_rect[3]))
        else:
            win_l, win_t, win_r, win_b = CALIBRATED_WINDOW_RECT
        win_rect = (win_l, win_t, win_r, win_b)

        # Use already-cached nodes if available (never force a multi-second refresh=True during calibration)
        all_nodes = list(self._nodes) if (connected and self._nodes) else []
        talk_node = self._find_talk(all_nodes) if all_nodes else None
        input_node = self._find_chat_input(all_nodes) if all_nodes else None

        if talk_node is not None:
            self.calibrated_talk_button_rect = talk_node.rect_tuple
            tl, tt, tr, tb = talk_node.rect_tuple
            t_scr_x, t_scr_y = self._calibrated_to_screen_point((tl + tr) // 2, (tt + tb) // 2)
            self.calibrated_talk_button_screen_pt = (t_scr_x, t_scr_y)
        elif self.calibrated_talk_button_screen_pt is None:
            tl, tt, tr, tb = self.calibrated_talk_button_rect or TALK_BUTTON_RECT
            self.calibrated_talk_button_screen_pt = self._calibrated_to_screen_point((tl + tr) // 2, (tt + tb) // 2)
        if input_node is not None:
            self.calibrated_chat_input_rect = input_node.rect_tuple
            il, it, ir, ib = input_node.rect_tuple
            # Target left-interior of 'Say something...' (il + 140) so it never clicks right-side emoji/gift popup icons
            safe_cal_x = min(il + 140, (il + ir) // 2)
            scr_x, scr_y = self._calibrated_to_screen_point(safe_cal_x, (it + ib) // 2)
            self.calibrated_chat_input_screen_pt = (scr_x, scr_y)
        elif self.calibrated_chat_input_screen_pt is None:
            il, it, ir, ib = self.calibrated_chat_input_rect or CHAT_INPUT_RECT
            # Default right into the left-interior of the 'Say something...' text area at x=1580, y=1223
            self.calibrated_chat_input_screen_pt = self._calibrated_to_screen_point(1580, (it + ib) // 2)

        payload: dict[str, Any] = {
            "window_rect": list(win_rect),
            "chat_input_rect": list(self.calibrated_chat_input_rect),
            "chat_input_screen_pt": list(self.calibrated_chat_input_screen_pt),
            "talk_button_rect": list(self.calibrated_talk_button_rect),
            "talk_button_screen_pt": list(self.calibrated_talk_button_screen_pt or (1326, 1182)),
            "calibrated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            save_calibration_overrides(payload)
        except Exception:
            pass
        return payload

    def calibrate_chat_input_from_cursor(self, delay_seconds: float = 0.0) -> dict[str, Any]:
        """Interactive Mouse-Hover Calibrator: waits `delay_seconds` (so the user can hover their mouse
        directly inside the Camfrog chat text box), reads the exact cursor screen position `(x, y)`,
        saves it to `data/camfrog_calibration.json`, and immediately uses it for all `!spin` and chat typing.
        """
        if delay_seconds > 0:
            time.sleep(delay_seconds)

        scr_x, scr_y = 1946, 1223
        if os.name == "nt":
            try:
                pt = wintypes.POINT()
                if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                    scr_x, scr_y = int(pt.x), int(pt.y)
            except Exception:
                pass
        else:
            try:
                import pyautogui  # type: ignore[import-not-found]
                pos = pyautogui.position()
                scr_x, scr_y = int(pos[0]), int(pos[1])
            except Exception:
                pass

        self.calibrated_chat_input_screen_pt = (scr_x, scr_y)
        cal_l, cal_t, cal_r, cal_b = self._normalize_rect_to_calibrated(
            scr_x - 450, scr_y - 16, scr_x + 450, scr_y + 16
        )
        self.calibrated_chat_input_rect = (cal_l, cal_t, cal_r, cal_b)
        payload: dict[str, Any] = {
            "window_rect": list(self._get_window_rect()),
            "chat_input_rect": list(self.calibrated_chat_input_rect),
            "chat_input_screen_pt": [scr_x, scr_y],
            "talk_button_rect": list(self.calibrated_talk_button_rect),
            "talk_button_screen_pt": list(self.calibrated_talk_button_screen_pt or (1326, 1182)),
            "calibration_mode": "cursor_pick",
            "calibrated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            save_calibration_overrides(payload)
        except Exception:
            pass
        return payload

    def calibrate_talk_button_from_cursor(self, delay_seconds: float = 0.0) -> dict[str, Any]:
        """Interactive Mouse-Hover Calibrator for the Camfrog Talk Button: waits `delay_seconds` while the user
        hovers their mouse directly over the Camfrog Talk Button, reads the exact screen pixel coordinate `(x, y)`,
        saves it to `data/camfrog_calibration.json`, and immediately uses it for KaeKae_Toad microphone grabbing.
        """
        if delay_seconds > 0:
            time.sleep(delay_seconds)

        scr_x, scr_y = 1326, 1182
        if os.name == "nt":
            try:
                pt = wintypes.POINT()
                if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                    scr_x, scr_y = int(pt.x), int(pt.y)
            except Exception:
                pass
        else:
            try:
                import pyautogui  # type: ignore[import-not-found]
                pos = pyautogui.position()
                scr_x, scr_y = int(pos[0]), int(pos[1])
            except Exception:
                pass

        self.calibrated_talk_button_screen_pt = (scr_x, scr_y)
        cal_l, cal_t, cal_r, cal_b = self._normalize_rect_to_calibrated(
            scr_x - 35, scr_y - 13, scr_x + 35, scr_y + 13
        )
        self.calibrated_talk_button_rect = (cal_l, cal_t, cal_r, cal_b)
        payload: dict[str, Any] = {
            "window_rect": list(self._get_window_rect()),
            "chat_input_rect": list(self.calibrated_chat_input_rect),
            "chat_input_screen_pt": list(self.calibrated_chat_input_screen_pt or (1946, 1223)),
            "talk_button_rect": list(self.calibrated_talk_button_rect),
            "talk_button_screen_pt": [scr_x, scr_y],
            "calibration_mode": "talk_cursor_pick",
            "calibrated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            save_calibration_overrides(payload)
        except Exception:
            pass
        return payload

    def set_direct_pixel_calibration(
        self,
        *,
        chat_x: int | None = None,
        chat_y: int | None = None,
        talk_x: int | None = None,
        talk_y: int | None = None,
    ) -> dict[str, Any]:
        """2nd Calibration Method — Direct Pixel Coordinate Entry:
        Allows entering exact `(X, Y)` screen pixel coordinates straight in for the Chat Text Box
        and/or the Talk Button without needing UIA discovery or mouse hover countdowns.
        Immediately locks and persists to `data/camfrog_calibration.json`.
        """
        if chat_x is not None and chat_y is not None:
            cx, cy = int(chat_x), int(chat_y)
            self.calibrated_chat_input_screen_pt = (cx, cy)
            cal_l, cal_t, cal_r, cal_b = self._normalize_rect_to_calibrated(
                cx - 450, cy - 16, cx + 450, cy + 16
            )
            self.calibrated_chat_input_rect = (cal_l, cal_t, cal_r, cal_b)

        if talk_x is not None and talk_y is not None:
            tx, ty = int(talk_x), int(talk_y)
            self.calibrated_talk_button_screen_pt = (tx, ty)
            t_l, t_t, t_r, t_b = self._normalize_rect_to_calibrated(
                tx - 35, ty - 13, tx + 35, ty + 13
            )
            self.calibrated_talk_button_rect = (t_l, t_t, t_r, t_b)

        payload: dict[str, Any] = {
            "window_rect": list(self._get_window_rect()),
            "chat_input_rect": list(self.calibrated_chat_input_rect),
            "chat_input_screen_pt": list(self.calibrated_chat_input_screen_pt or (1946, 1223)),
            "talk_button_rect": list(self.calibrated_talk_button_rect),
            "talk_button_screen_pt": list(self.calibrated_talk_button_screen_pt or (1326, 1182)),
            "calibration_mode": "direct_pixel_entry",
            "calibrated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            save_calibration_overrides(payload)
        except Exception:
            pass
        return payload


    @staticmethod
    def _extract_speaker_text_deep(control: Any, fallback_name: str = "") -> str:
        """Read speaker username from UIA Name, ValuePattern, or LegacyIAccessible Name/Value (used ONLY on the 1-2 nodes in the mic strip)."""
        if fallback_name and clean_username(fallback_name):
            return fallback_name.strip()
        if control is None:
            return fallback_name
        for attr_chain in (
            ("element_info", "name"),
            ("iface_legacy_iaccessible", "CurrentName"),
            ("iface_legacy_iaccessible", "CurrentValue"),
            ("iface_value", "CurrentValue"),
        ):
            try:
                obj = control
                for attr in attr_chain:
                    obj = getattr(obj, attr, None)
                    if callable(obj):
                        obj = obj()
                if obj and isinstance(obj, str) and obj.strip():
                    return obj.strip()
            except Exception:
                pass
        try:
            txt = control.window_text()
            if txt and isinstance(txt, str) and txt.strip():
                return txt.strip()
        except Exception:
            pass
        return fallback_name

    @staticmethod
    def _clean_ocr_speaker_candidate(raw_line: str) -> str:
        """Clean an OCR line from the Camfrog active speaker banner [1500, 1168, 1780, 1196] into a valid username."""
        line = str(raw_line or "").strip()
        if not line:
            return ""
        # Join spaces around underscores/dots/hyphens inserted by OCR ("KaeKae _ Toad" -> "KaeKae_Toad")
        line = re.sub(r"\s*([_.\-])\s*", r"\1", line)
        # Strip mic timer suffixes like "0:12", "01:45", "(12s)"
        line = re.sub(r"\b\d{1,2}:\d{2}\b", "", line)
        line = re.sub(r"\(\d+s?\)", "", line)
        # Strip leading level badges or mic icon glyphs (e.g. "10 Mr,Bl3sS", "Q Rosie")
        line = re.sub(r"^\s*(?:\d{1,2}|[🎙🔊🎤])\s+", "", line).strip()
        cand = clean_username(line)
        if cand:
            return cand
        # Try individual tokens in case OCR picked up a button label alongside the username
        for tok in line.split():
            tok_clean = clean_username(tok.strip(":,.()[]"))
            if tok_clean and len(tok_clean) >= 3 and tok_clean.lower() not in {"talk", "talking", "speaking", "mic", "free", "mute"}:
                return tok_clean
        return ""

    @staticmethod
    def _find_active_speaker_node(nodes: Iterable[UIANode]) -> UIANode | None:
        """Locate the Active Microphone Speaker Button(50000) at [l=1506,t=1174,r=...,b=1190].

        In Camfrog, when someone is on the mic, a Button(50000) or Text(50020) appears at l=1506, t=1174, b=1190
        (e.g. [1506, 1174, 1548, 1190] or [1506, 1174, 1650, 1190]) along with an indicator Pane at
        [1478, 1174, 1482, 1190]. When the mic is free, that Button(50000) erases from the UIA tree.
        """
        sl, st, sr, sb = ACTIVE_SPEAKER_RECT  # (1506, 1174, 1548, 1190)
        node_list = list(nodes)

        # 1. Primary: Button/Text/Custom/Pane at [l≈1506, t≈1174, b≈1190] (exclude the 4px indicator Pane at 1478..1482)
        primary = [
            node for node in node_list
            if node.control_type in {"Button", "Text", "Custom", "Hyperlink", "Static", "Pane"}
            and 1485 <= node.left <= 1620
            and abs(node.top - st) <= 22
            and abs(node.bottom - sb) <= 22
            and node.width >= 10
            and node.height <= 42
        ]
        if primary:
            named = [n for n in primary if clean_username(n.name, n.rect_tuple)]
            if named:
                return min(named, key=lambda n: abs(n.left - sl) + abs(n.top - st))
            return min(primary, key=lambda n: abs(n.left - sl) + abs(n.top - st))

        # 2. Fallback: any named control on the mic strip (1485..2100, t=1165..1198)
        fallback = [
            node for node in node_list
            if node.control_type in {"Button", "Text", "Custom", "Hyperlink", "Static"}
            and clean_username(node.name, node.rect_tuple)
            and abs(node.top - st) <= 22
            and abs(node.bottom - sb) <= 22
            and 1485 <= node.left <= 2100
        ]
        return min(fallback, key=lambda n: abs(n.left - sl)) if fallback else None

    def get_active_speaker(self, refresh: bool = False) -> str | None:
        """Read the active speaker username at [l=1506,t=1174,r=...,b=1190].

        Returns None ONLY when the active-speaker Button(50000) at [1506,1174,...,1190] is absent/erased.
        When present, resolves the exact username via UIA Name, LegacyIAccessible Name/Value, sibling Text nodes,
        or Windows OCR on the speaker banner `[1496, 1166, 1780, 1198]`.
        """
        node_list = self.nodes(refresh=refresh)
        node = self._find_active_speaker_node(node_list)
        if node is None:
            self._ocr_speaker_cache = None
            return None

        # 1. Direct UIA or deep LegacyIAccessible text on the active speaker node
        deep_name = self._extract_speaker_text_deep(node.control, node.name)
        cleaned = self._clean_ocr_speaker_candidate(deep_name) or clean_username(deep_name, node.rect_tuple)
        if cleaned:
            matched = self._match_known_username(cleaned)
            self._known_users.add(matched)
            self._ocr_speaker_cache = (node.rect_tuple, time.monotonic(), matched)
            return matched

        # 2. Check any sibling Text/Button/Edit/Custom overlapping the speaker strip [l=1480..2150, t=1158..1202]
        sl, st, sr, sb = ACTIVE_SPEAKER_RECT
        for sib in node_list:
            if (
                1480 <= sib.left <= 2150
                and abs(sib.top - st) <= 22
                and abs(sib.bottom - sb) <= 22
                and sib.width >= 10
            ):
                sib_raw = self._extract_speaker_text_deep(sib.control, sib.name)
                sib_user = self._clean_ocr_speaker_candidate(sib_raw) or clean_username(sib_raw, sib.rect_tuple)
                if sib_user:
                    matched = self._match_known_username(sib_user)
                    self._known_users.add(matched)
                    self._ocr_speaker_cache = (node.rect_tuple, time.monotonic(), matched)
                    return matched

        # 3. Cached Windows screen OCR on the speaker rectangle [1496, 1166, max(1760, node.right+90), 1198]
        rect_key = node.rect_tuple
        now = time.monotonic()
        if (
            self._ocr_speaker_cache is not None
            and self._ocr_speaker_cache[0] == rect_key
            and now - self._ocr_speaker_cache[1] < 6.0
            and not self._ocr_speaker_cache[2].startswith("Speaker_On_Mic")
        ):
            return self._ocr_speaker_cache[2]

        # Throttle retry of failed OCR to once every 1.2s so UIA polling stays fast while re-checking speaker name
        if (
            self._ocr_speaker_cache is not None
            and self._ocr_speaker_cache[0] == rect_key
            and now - self._ocr_speaker_cache[1] < 1.2
        ):
            return self._ocr_speaker_cache[2]

        ocr_left = max(1494, node.left - 6)
        ocr_top = max(1164, node.top - 6)
        ocr_right = max(1760, node.right + 90)
        ocr_bottom = min(1200, node.bottom + 6)
        ocr_lines = self._ocr_screen_rect(ocr_left, ocr_top, ocr_right, ocr_bottom, scale=3)
        for line in ocr_lines:
            candidate = self._clean_ocr_speaker_candidate(line)
            if candidate:
                matched = self._match_known_username(candidate)
                self._known_users.add(matched)
                self._ocr_speaker_cache = (rect_key, now, matched)
                return matched

        fallback_label = f"Speaker_On_Mic[{node.left},{node.top},{node.right},{node.bottom}]"
        self._ocr_speaker_cache = (rect_key, now, fallback_label)
        return fallback_label

    def detect_user_gender_from_rect(self, rect_tuple: tuple[int, int, int, int] | None) -> str:
        """Inspect pixel color in User List row or Active Speaker strip: Blue = male, Pink = female."""
        if rect_tuple is None or os.name != "nt":
            return "unknown"
        try:
            import numpy as np
            import pyautogui  # type: ignore[import-not-found]
            l, t, r, b = rect_tuple
            scr_l, scr_t = self._calibrated_to_screen_point(l, t)
            scr_r, scr_b = self._calibrated_to_screen_point(r, b)
            w = max(8, min(48, scr_r - scr_l))
            h = max(8, min(28, scr_b - scr_t))
            img = pyautogui.screenshot(region=(scr_l, scr_t, w, h))
            arr = np.array(img)
            # Count blue-dominant vs pink/magenta-dominant pixels
            r_ch = arr[:, :, 0].astype(int)
            g_ch = arr[:, :, 1].astype(int)
            b_ch = arr[:, :, 2].astype(int)
            blue_mask = (b_ch > 150) & (b_ch - r_ch > 45)
            pink_mask = (r_ch > 170) & (b_ch > 110) & (r_ch - g_ch > 45)
            blue_px = int(np.count_nonzero(blue_mask))
            pink_px = int(np.count_nonzero(pink_mask))
            if pink_px > blue_px and pink_px >= 6:
                return "female"
            if blue_px > pink_px and blue_px >= 6:
                return "male"
        except Exception:
            pass
        return "unknown"

    def is_mic_free(self, refresh: bool = True) -> bool:
        """Return True when no username/control is present at Active Speaker [l=1506,t=1174,r=1548,b=1190]."""
        return self.get_active_speaker(refresh=refresh) is None

    def _scan_users_header_and_list_from_uia(self, all_nodes: list[UIANode]) -> tuple[int | None, list[str]]:
        """Extract both the room user count and username list from UIA nodes in the right User List column [l=2359,r=2559].

        Sums the 3 ignored section headers ('YOU ARE VIEWING (#)', 'MEMBERS (#)', 'LURKERS (#)') or reads 'Users (#)',
        and falls back to counting distinct list-row slots minus the 3 headers when UIA exposes blank row items.
        """
        ul_left, ul_top, ul_right, ul_bottom = USER_LIST_RECT  # (2359, 141, 2559, 1160)
        users_tab_count: int | None = None
        viewing_count: int | None = None
        members_count: int | None = None
        lurkers_count: int | None = None

        # 1. Scan the entire right-hand User List column (top >= 90 to include 'Users (30)' tab at y≈115 and the 3 section headers)
        for node in all_nodes:
            if not node.name or node.left < ul_left - 8 or node.top < 90:
                continue
            for raw_line in str(node.name).splitlines():
                line = raw_line.strip()
                if not line or len(line) > 42 or "_" in line:
                    continue
                lower = line.lower()
                if "gift" in lower:
                    continue
                if "viewing" not in lower:
                    m_users = _USERS_TOTAL_HEADER_RE.search(line)
                    if m_users and users_tab_count is None:
                        raw_num = next((g for g in m_users.groups() if g is not None), None)
                        if raw_num and 1 <= int(raw_num) <= 500:
                            users_tab_count = int(raw_num)
                m_sec = _SECTION_COUNT_RE.search(line)
                if m_sec:
                    sec_name = m_sec.group("section").lower()
                    sec_val = int(m_sec.group("count"))
                    if 0 <= sec_val <= 500:
                        if "wing" in sec_name and viewing_count is None:
                            viewing_count = sec_val
                        elif "ber" in sec_name and members_count is None:
                            members_count = sec_val
                        elif "ker" in sec_name and lurkers_count is None:
                            lurkers_count = sec_val

        # 2. Collect candidate nodes strictly in User List column [l=2355..2543, t=100..1160]
        # Exclude the right-edge User List scrollbar (left >= 2540, width <= 22) where 'Page' lives!
        candidates: list[UIANode] = []
        raw_row_rects: set[tuple[int, int]] = set()
        for node in all_nodes:
            if is_ignored_listitem_rect(node.rect_tuple):
                continue
            if node.left >= ul_right - 20 and node.width <= 24:
                continue
            if node.left >= ul_left - 4 and node.right <= ul_right + 8 and 100 <= node.top <= ul_bottom:
                # Track distinct list-row vertical slots inside [t=141..1160] (height 16..34) for the (rows - 3) count fallback
                if (
                    node.control_type in {"ListItem", "DataItem", "TreeItem", "Custom"}
                    and ul_top <= node.top <= ul_bottom
                    and 15 <= node.height <= 34
                    and node.width >= 100
                ):
                    raw_row_rects.add((node.top // 4, node.bottom // 4))
                if node.name and node.control_type in {
                    "ListItem", "List", "Text", "Hyperlink", "Custom",
                    "Pane", "Button", "DataItem", "TreeItem", "Group", "Header", "HeaderItem", "TabItem",
                }:
                    candidates.append(node)

        candidates.sort(key=lambda n: (0 if n.height < 120 else 1, n.top, n.left))

        users: list[str] = []
        seen_lower: set[str] = set()
        for node in candidates:
            for line in str(node.name or "").splitlines():
                raw_line = line.strip()
                if not raw_line:
                    continue
                if is_user_list_header(raw_line):
                    continue
                user = clean_username(raw_line, node.rect_tuple)
                if user and user.lower() not in seen_lower:
                    seen_lower.add(user.lower())
                    users.append(user)
                    self._known_users.add(user)
                    if len(users) >= MAX_ROOM_USERS:
                        break
            if len(users) >= MAX_ROOM_USERS:
                break

        # Prefer summing the 3 ignored headers (YOU ARE VIEWING # + MEMBERS # + LURKERS #) or the 'Users (#)' tab header
        section_sum = None
        if members_count is not None or lurkers_count is not None:
            section_sum = (viewing_count or 0) + (members_count or 0) + (lurkers_count or 0)

        header_count = section_sum if (section_sum is not None and section_sum > 0) else users_tab_count
        if header_count is None and viewing_count is not None and viewing_count > 0:
            header_count = viewing_count
        if header_count is None and len(raw_row_rects) > 3:
            # Subtract the 3 section header rows (YOU ARE VIEWING, MEMBERS, LURKERS)
            header_count = len(raw_row_rects) - 3

        return header_count, users

    def _get_ocr_userlist_fallback(self, *, header_only: bool = False) -> tuple[int | None, list[str]]:
        """Read 'Users (30)' and the 3 section counts ('YOU ARE VIEWING #', 'MEMBERS #', 'LURKERS #') via Windows OCR."""
        now = time.monotonic()
        cache_ttl = 15.0 if header_only else 60.0
        if self._ocr_userlist_cache is not None and now - self._ocr_userlist_cache[0] < cache_ttl:
            return self._ocr_userlist_cache[1], list(self._ocr_userlist_cache[2])

        ul_left, ul_top, ul_right, ul_bottom = USER_LIST_RECT  # (2359, 141, 2559, 1160)
        # Single fast OCR pass on the right User List column [2359, 105, 2544, 1160]
        full_lines = self._ocr_screen_rect(ul_left, 105, ul_right - 15, ul_bottom, scale=2)
        text_only_lines = (
            []
            if header_only
            else self._ocr_screen_rect(ul_left + 29, ul_top + 22, ul_right - 38, ul_bottom, scale=3)
        )

        users_tab_count: int | None = None
        viewing_count: int | None = None
        members_count: int | None = None
        lurkers_count: int | None = None
        users: list[str] = []
        seen_lower: set[str] = set()

        for raw_line in full_lines + text_only_lines:
            line = raw_line.strip()
            if not line:
                continue
            lower = line.lower()
            if "_" not in line and "gift" not in lower:
                if "viewing" not in lower:
                    m_users = _USERS_TOTAL_HEADER_RE.search(line)
                    if m_users and users_tab_count is None:
                        raw_num = next((g for g in m_users.groups() if g is not None), None)
                        if raw_num and 1 <= int(raw_num) <= 500:
                            users_tab_count = int(raw_num)
                            continue
                m_sec = _SECTION_COUNT_RE.search(line)
                if m_sec:
                    sec_name = m_sec.group("section").lower()
                    sec_val = int(m_sec.group("count"))
                    if 0 <= sec_val <= 500:
                        if "wing" in sec_name and viewing_count is None:
                            viewing_count = sec_val
                        elif "ber" in sec_name and members_count is None:
                            members_count = sec_val
                        elif "ker" in sec_name and lurkers_count is None:
                            lurkers_count = sec_val
                    continue
            if is_user_list_header(line):
                continue
            # Strip leading level numbers like "10 Mr,Bl3sS" or "7 Princess Ri"
            stripped_lvl = re.sub(r"^\s*\d{1,2}\s+", "", line)
            user = clean_username(stripped_lvl) or clean_username(line)
            if user and user.lower() not in seen_lower:
                seen_lower.add(user.lower())
                users.append(user)
                self._known_users.add(user)
                if len(users) >= MAX_ROOM_USERS:
                    break

        section_sum = None
        if members_count is not None or lurkers_count is not None:
            section_sum = (viewing_count or 0) + (members_count or 0) + (lurkers_count or 0)

        header_count = section_sum if (section_sum is not None and section_sum > 0) else users_tab_count
        if header_count is None and users:
            header_count = len(users)

        self._ocr_userlist_cache = (now, header_count, users)
        return header_count, users

    def get_user_list(self, refresh: bool = False) -> list[str]:
        """Extract usernames from User List(50008) [l=2359,t=141,r=2559,b=1160] trending along [l=2359,r=2559].

        Removes 'YOU ARE VIEWING #', 'MEMBERS #', 'LURKERS #', and 'Users (#)' headers and scans up/down
        along the User List column for up to MAX_ROOM_USERS (100) users.
        """
        all_nodes = self.nodes(refresh=refresh)
        header_count, users = self._scan_users_header_and_list_from_uia(all_nodes)
        if not users and header_count is None and self._ocr_userlist_cache is None and all_nodes:
            _, ocr_users = self._get_ocr_userlist_fallback(header_only=True)
            if len(ocr_users) > len(users):
                users = ocr_users
        elif len(users) <= 5 and self._ocr_userlist_cache is not None:
            cached_users = list(self._ocr_userlist_cache[2])
            if len(cached_users) > len(users):
                users = cached_users
        if len(users) >= 6:
            self._last_good_users = list(users)
        elif self._last_good_users and len(users) < max(6, len(self._last_good_users) // 2):
            users = list(self._last_good_users)
        return users

    def get_user_count(self, refresh: bool = False) -> int:
        """Return the room user count rapidly by summing the 3 section headers (YOU ARE VIEWING # + MEMBERS # + LURKERS #),
        reading 'Users (#)', or counting list rows minus the 3 headers.
        """
        all_nodes = self.nodes(refresh=refresh)
        header_count, users = self._scan_users_header_and_list_from_uia(all_nodes)
        candidate = 0
        if header_count is not None and header_count > len(users):
            candidate = min(MAX_ROOM_USERS, header_count)
        elif len(users) >= 1:
            candidate = min(MAX_ROOM_USERS, max(header_count or 0, len(users)))
        elif self._ocr_userlist_cache is not None:
            candidate = min(MAX_ROOM_USERS, max(self._ocr_userlist_cache[1] or 0, len(self._ocr_userlist_cache[2])))

        # Prevent transient CEF/UIA occlusion rebuilds from dropping a 27-user room down to 4 or 1
        if candidate >= 6:
            self._last_good_user_count = candidate
            return candidate
        if self._last_good_user_count >= 6:
            return self._last_good_user_count
        return candidate

    @staticmethod
    def _parse_text_tokens_into_events(tokens: list[tuple[str, str]]) -> list[dict[str, str]]:
        """Parse a sequence of (control_type, text) items from the Chat Window into structured events.

        Supports:
        - Compound DataItem(50029) rows at [l=1332, r=2330] containing multiple Join:/Quit: events in one item
          (e.g. "Quit: phoenixrising Quit: liketosquirt Join: ward1dp")
        - Separate child Text(50020) nodes ('Quit:', 'phoenixrising', 'Quit:', 'liketosquirt', 'Join:', 'ward1dp')
        - Standalone moderation lines ("Mod_1 kicked User_2", "User_2 was kicked by Mod_1")
        - Multi-node [User, Clock, Message] or single-line chat messages
        """
        flat: list[tuple[str, str]] = []
        for ctrl_type, raw_text in tokens:
            lines = [ln.strip() for ln in str(raw_text or "").splitlines() if ln.strip()]
            for ln in lines:
                flat.append((ctrl_type, ln))

        events: list[dict[str, str]] = []
        consumed_indices: set[int] = set()
        for index, (control_type, name) in enumerate(flat):
            if index in consumed_indices:
                continue
            lowered = name.lower().strip()
            if is_user_list_header(name):
                continue
            # Ignore browser/CEF URL strings so 'https://...' never becomes a fake user 'https'
            if lowered.startswith(("http://", "https://", "ftp://", "mailto:")) or "camfrogcdn.com" in lowered:
                continue

            # 1. Multi-node Join: / Quit: child Text(50020) sequence ('Quit:' followed by 'liketosquirt')
            if lowered in {"join:", "quit:", "left:"}:
                action = "join" if lowered == "join:" else "quit"
                user = clean_username(flat[index + 1][1]) if index + 1 < len(flat) else ""
                if user:
                    consumed_indices.add(index + 1)
                    events.append({"kind": "presence", "action": action, "user": user, "text": "", "timestamp": ""})
                continue

            # 2. Compound DataItem(50029) at [l=1332, r=2330] with one or more "Join: <user>" / "Quit: <user>" pairs
            # e.g. "Quit: phoenixrising Quit: liketosquirt Join: ward1dp"
            multi_matches = list(_MULTI_PRESENCE_PAIR_RE.finditer(name))
            if multi_matches and re.match(r"^\s*(?:join|quit|left)\s*:", name, re.I):
                for m in multi_matches:
                    action = "join" if m.group("kw").lower() == "join" else "quit"
                    user = clean_username(m.group("user"))
                    if user:
                        events.append({"kind": "presence", "action": action, "user": user, "text": "", "timestamp": ""})
                continue

            # 3. Single-line Join: <user> / Quit: <user> / <user> has joined/left
            pres_match = _INLINE_PRESENCE_RE.match(name)
            if pres_match:
                if pres_match.group("kw"):
                    action = "join" if pres_match.group("kw").lower() == "join" else "quit"
                    user = clean_username(pres_match.group("user1"))
                else:
                    action = "join" if pres_match.group("verb").lower() in {"joined", "entered"} else "quit"
                    user = clean_username(pres_match.group("user2"))
                if user:
                    events.append({"kind": "presence", "action": action, "user": user, "text": "", "timestamp": ""})
                continue

            # 4. Standalone Moderation Notice line (e.g. "Mod_1 kicked User_2." or "User_2 was kicked by Mod_1.")
            mod_match = _MOD_LINE_RE.match(name)
            if mod_match:
                actor = clean_username(mod_match.group("actor") or mod_match.group("actor2") or "")
                target = clean_username(mod_match.group("target") or mod_match.group("target2") or "")
                if actor and target:
                    events.append({"kind": "message", "user": actor, "text": name.strip(), "timestamp": ""})
                    continue

            # 5. Multi-node [User, Clock, Message] OR [Clock, User, Message] sequence
            if _CLOCK_RE.fullmatch(name.strip()):
                user = clean_username(flat[index - 1][1]) if index > 0 else ""
                start_offset = 1
                if not user and index + 1 < len(flat):
                    next_user = clean_username(flat[index + 1][1])
                    if next_user:
                        user = next_user
                        consumed_indices.add(index + 1)
                        start_offset = 2
                if not user:
                    continue
                body = ""
                for offset_idx in range(index + start_offset, min(len(flat), index + start_offset + 3)):
                    cand_strip = flat[offset_idx][1].strip().lstrip(":").strip()
                    if (
                        cand_strip
                        and not _CLOCK_RE.fullmatch(cand_strip)
                        and cand_strip.lower() not in {"join:", "quit:", "left:"}
                    ):
                        body = cand_strip
                        consumed_indices.add(offset_idx)
                        break
                if body:
                    events.append({"kind": "message", "user": user, "text": body, "timestamp": name.strip()})
                continue

            # 6. Single-line "[6:36 PM] User: message" or "User: message"
            inline_match = _INLINE_CHAT_RE.match(name)
            if inline_match:
                raw_user = inline_match.group("user").strip()
                user = clean_username(raw_user)
                body = (inline_match.group("body") or "").strip()
                ts = (inline_match.group("ts1") or inline_match.group("ts2") or "").strip()
                if (
                    user
                    and user.lower() == raw_user.lower()
                    and body
                    and not body.startswith("//")
                    and not _CLOCK_RE.fullmatch(body.rstrip(":").strip())
                ):
                    events.append({"kind": "message", "user": user, "text": body, "timestamp": ts})
                continue

            # 7. Multi-node Camfrog CEF chat without timestamp: [Text(username), Text(":" or ": message")]
            # Require an explicit ':' separator so wrapped chat body lines never misparse as new senders!
            prev_lower = flat[index - 1][1].lower().strip() if index > 0 else ""
            if (
                control_type in {"Text", "Hyperlink"}
                and prev_lower not in {"join:", "quit:", "left:"}
                and clean_username(name) == name.strip()
                and index + 1 < len(flat)
            ):
                user = clean_username(name)
                next_text = flat[index + 1][1].strip()
                if next_text == ":" and index + 2 < len(flat):
                    body = flat[index + 2][1].strip()
                    if (
                        body
                        and body != ":"
                        and not _CLOCK_RE.fullmatch(body)
                        and body.lower() not in {"join:", "quit:", "left:"}
                        and not _MULTI_PRESENCE_PAIR_RE.search(body)
                    ):
                        consumed_indices.update({index + 1, index + 2})
                        events.append({"kind": "message", "user": user, "text": body, "timestamp": ""})
                elif next_text.startswith(":") and len(next_text) > 1:
                    body = next_text.lstrip(":").strip()
                    if body and not _CLOCK_RE.fullmatch(body):
                        consumed_indices.add(index + 1)
                        events.append({"kind": "message", "user": user, "text": body, "timestamp": ""})

        return events

    def inspect_calibrated_regions(self, refresh: bool = True) -> dict[str, object]:
        """Return a diagnostic summary of UIA nodes and parsed data in each calibrated region."""
        all_nodes = self.nodes(refresh=refresh)
        cl, ct, cr, cb = CHAT_WINDOW_RECT
        ul_l, ul_t, ul_r, ul_b = USER_LIST_RECT
        tl, tt, tr, tb = TOP_GIFTERS_RECT
        sl, st, sr, sb = ACTIVE_SPEAKER_RECT

        chat_nodes = [
            {"type": n.control_type, "rect": list(n.rect_tuple), "text": (n.name or "")[:120]}
            for n in all_nodes
            if n.left >= cl - 20 and n.right <= min(cr + 15, ul_l) and n.top >= ct - 15 and n.bottom <= cb + 15
        ]
        user_nodes = [
            {"type": n.control_type, "rect": list(n.rect_tuple), "text": (n.name or "")[:80]}
            for n in all_nodes
            if n.left >= ul_l - 4 and n.right <= ul_r + 15 and n.top >= 100
        ]
        mic_bar_nodes = [
            {"type": n.control_type, "rect": list(n.rect_tuple), "text": (n.name or "")[:80]}
            for n in all_nodes
            if abs(n.top - st) <= 30 and n.left >= 1280 and n.right <= 2355
        ]
        top_gifter_nodes = [
            {"type": n.control_type, "rect": list(n.rect_tuple), "text": (n.name or "")[:120]}
            for n in all_nodes
            if abs(n.left - tl) <= 20 and abs(n.top - tt) <= 20 and abs(n.right - tr) <= 20 and abs(n.bottom - tb) <= 20
        ]
        events = self.get_chat_events()
        users = self.get_user_list(refresh=False)
        user_count = self.get_user_count(refresh=False)
        return {
            "window_rect": self._window_rect(),
            "total_uia_nodes": len(all_nodes),
            "active_speaker_now": self.get_active_speaker(refresh=False),
            "user_count_from_users_header": user_count,
            "users_listed_count": len(users),
            "users_sample": users[:25],
            "chat_events_parsed": len(events),
            "chat_events_sample": events[-10:],
            "mic_bar_nodes": mic_bar_nodes,
            "chat_region_node_count": len(chat_nodes),
            "chat_region_nodes_sample": chat_nodes[:10],
            "user_list_node_count": len(user_nodes),
            "user_list_nodes_sample": user_nodes[:15],
            "top_gifters_nodes": top_gifter_nodes[:5],
        }

    def get_chat_events(self, limit: int = 200) -> list[dict[str, str]]:
        """Parse chat & moderation events from Chat Window Pane(50033)/Text(50020) [l=1281,t=170,r=2355,b=1160].

        Includes chat nodes whose vertical coordinates extend below b=1160 (e.g. when the chat feed's scrollbar
        stops auto-scrolling and new DOM messages are appended below the visible viewport) while excluding
        the mic bar (y=1165..1198) and chat input box (y=1202..1245).
        """
        cl, ct, cr, cb = CHAT_WINDOW_RECT  # (1281, 170, 2355, 1160)
        ul_left = USER_LIST_RECT[0]        # 2359

        all_nodes = self.nodes()
        primary_chat_nodes = [
            node for node in all_nodes
            if node.name
            and not is_ignored_listitem_rect(node.rect_tuple)
            and node.left >= cl - 20
            and node.right <= min(cr + 15, ul_left)
            and node.top >= ct - 15
            # Do NOT clip node.bottom <= 1175! When Camfrog's scrollbar stops auto-scrolling,
            # newly arriving chat nodes have top > 1160 in the virtual DOM. Only skip the mic strip & input box:
            and not (1166 <= node.top <= 1245 and node.bottom <= 1250 and node.control_type in {"Button", "Edit"})
        ]

        primary_chat_nodes.sort(key=lambda n: (n.top, n.left))
        events = self._parse_text_tokens_into_events([(n.control_type, n.name) for n in primary_chat_nodes])

        if not events:
            tl, tt, tr, tb = TOP_GIFTERS_RECT
            fallback_nodes = [
                node for node in all_nodes
                if node.name
                and node.control_type in {"Text", "Pane", "Document"}
                and abs(node.left - tl) <= 20
                and abs(node.top - tt) <= 20
                and abs(node.right - tr) <= 20
                and abs(node.bottom - tb) <= 20
            ]
            events = self._parse_text_tokens_into_events([(n.control_type, n.name) for n in fallback_nodes])

        unique: list[dict[str, str]] = []
        for idx, event in enumerate(events):
            if event.get("user"):
                self._known_users.add(event["user"])
            # Collapse only adjacent identical duplicates produced by parent+child UIA nodes on the same row
            if (
                unique
                and unique[-1]["kind"] == event["kind"]
                and unique[-1].get("action", "") == event.get("action", "")
                and unique[-1]["user"].lower() == event["user"].lower()
                and unique[-1]["text"] == event["text"]
            ):
                continue
            unique.append(event)
        result = unique[-limit:]
        if result:
            tail = result[-5:]
            fp = "|".join(f"{e.get('user','')}:{e.get('text','')}:{e.get('action','')}" for e in tail)
            if fp != self._last_chat_fingerprint:
                self._last_chat_fingerprint = fp
                self._last_chat_change_at = time.monotonic()
        return result

    @staticmethod
    def _make_lparam(x: int, y: int) -> int:
        return ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)

    def _find_target_hwnd_and_client_pt(self, screen_x: int, screen_y: int, node: UIANode | None = None) -> tuple[int, int, int]:
        """Resolve the deepest child HWND (e.g., Chromium/CEF Chrome_RenderWidgetHostHWND) and client-relative (x,y)
        so Win32 PostMessage works in the background without moving the user's mouse or stealing active focus.
        """
        if os.name != "nt":
            return 0, screen_x, screen_y
        user32 = ctypes.windll.user32
        target_hwnd = 0
        if node is not None and node.control is not None:
            try:
                nh = int(getattr(node.control.element_info, "handle", 0) or 0)
                if nh and user32.IsWindow(wintypes.HWND(nh)):
                    target_hwnd = nh
            except Exception:
                pass
        if not target_hwnd and self._hwnd and user32.IsWindow(wintypes.HWND(self._hwnd)):
            target_hwnd = int(self._hwnd)
            # Descend into child window at this point without requiring the window to be on top (ChildWindowFromPointEx)
            try:
                pt = wintypes.POINT(int(screen_x), int(screen_y))
                user32.ScreenToClient(wintypes.HWND(target_hwnd), ctypes.byref(pt))
                child = user32.ChildWindowFromPointEx(wintypes.HWND(target_hwnd), pt, 0x0001)  # CWP_SKIPINVISIBLE
                depth = 0
                while child and int(child) != target_hwnd and user32.IsWindow(wintypes.HWND(child)) and depth < 8:
                    target_hwnd = int(child)
                    depth += 1
                    pt_sub = wintypes.POINT(int(screen_x), int(screen_y))
                    user32.ScreenToClient(wintypes.HWND(target_hwnd), ctypes.byref(pt_sub))
                    child = user32.ChildWindowFromPointEx(wintypes.HWND(target_hwnd), pt_sub, 0x0001)
            except Exception:
                pass
        if target_hwnd:
            pt = wintypes.POINT(int(screen_x), int(screen_y))
            user32.ScreenToClient(wintypes.HWND(target_hwnd), ctypes.byref(pt))
            return target_hwnd, int(pt.x), int(pt.y)
        return 0, screen_x, screen_y

    def _post_background_click(self, screen_x: int, screen_y: int, node: UIANode | None = None) -> bool:
        """Send a background left-click via Win32 PostMessage without moving the physical mouse cursor or stealing focus."""
        if os.name != "nt":
            return False
        hwnd, cx, cy = self._find_target_hwnd_and_client_pt(screen_x, screen_y, node)
        if not hwnd:
            return False
        try:
            user32 = ctypes.windll.user32
            wh = wintypes.HWND(hwnd)
            lparam = self._make_lparam(cx, cy)
            user32.PostMessageW(wh, WM_MOUSEMOVE, 0, lparam)
            user32.PostMessageW(wh, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
            user32.PostMessageW(wh, WM_LBUTTONUP, 0, lparam)
            return True
        except Exception:
            return False

    def _post_background_press_or_release(self, screen_x: int, screen_y: int, *, down: bool, node: UIANode | None = None) -> bool:
        """Send a background mouse-down or mouse-up via Win32 PostMessage for holding the Talk button in the background."""
        if os.name != "nt":
            return False
        hwnd, cx, cy = self._find_target_hwnd_and_client_pt(screen_x, screen_y, node)
        if not hwnd:
            return False
        try:
            user32 = ctypes.windll.user32
            wh = wintypes.HWND(hwnd)
            lparam = self._make_lparam(cx, cy)
            if down:
                user32.PostMessageW(wh, WM_MOUSEMOVE, MK_LBUTTON, lparam)
                user32.PostMessageW(wh, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
            else:
                user32.PostMessageW(wh, WM_LBUTTONUP, 0, lparam)
            return True
        except Exception:
            return False

    def _set_win32_clipboard_text(self, text: str) -> bool:
        """Copy text to Windows clipboard via Win32 API or tkinter fallback for instant Ctrl+V paste."""
        if os.name == "nt":
            try:
                CF_UNICODETEXT = 13
                GMEM_MOVEABLE = 0x0002
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
                kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
                kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
                kernel32.GlobalLock.restype = ctypes.c_void_p
                kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
                user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]

                if user32.OpenClipboard(0):
                    try:
                        user32.EmptyClipboard()
                        encoded = (text + "\0").encode("utf-16-le")
                        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
                        if h_mem:
                            ptr = kernel32.GlobalLock(h_mem)
                            if ptr:
                                ctypes.memmove(ptr, encoded, len(encoded))
                                kernel32.GlobalUnlock(h_mem)
                                user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                                return True
                    finally:
                        user32.CloseClipboard()
            except Exception:
                pass
        return False

    def _release_all_modifier_keys(self) -> None:
        """Explicitly send KEYUP for Alt (VK_MENU, VK_LMENU, VK_RMENU), Ctrl, and Shift so a stuck or
        injected Alt key can NEVER combine with any letter to trigger Camfrog's Alt+A Info popup!
        """
        if os.name != "nt":
            return
        try:
            user32 = ctypes.windll.user32
            KEYEVENTF_KEYUP = 0x0002
            # Release VK_MENU (0x12), VK_LMENU (0xA4), VK_RMENU (0xA5), VK_CONTROL (0x11), VK_SHIFT (0x10)
            for vk, scan in ((0x12, 0x38), (0xA4, 0x38), (0xA5, 0x38), (0x11, 0x1D), (0x10, 0x2A)):
                user32.keybd_event(vk, scan, KEYEVENTF_KEYUP, 0)
        except Exception:
            pass

    def _send_unicode_string_and_enter(self, text: str) -> bool:
        """Type Unicode characters directly via Win32 SendInput(KEYEVENTF_UNICODE) + Enter without pressing
        ANY modifier keys or letter virtual-key codes (so Alt+A / Ctrl+A can NEVER be triggered).
        """
        if os.name != "nt":
            return False
        try:
            user32 = ctypes.windll.user32
            INPUT_KEYBOARD = 1
            KEYEVENTF_KEYUP = 0x0002
            KEYEVENTF_UNICODE = 0x0004

            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [
                    ("wVk", wintypes.WORD),
                    ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t),
                ]

            class MOUSEINPUT(ctypes.Structure):
                _fields_ = [
                    ("dx", wintypes.LONG),
                    ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t),
                ]

            class _INPUT_UNION(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

            class INPUT(ctypes.Structure):
                _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]

            inputs: list[INPUT] = []
            for ch in text:
                code = ord(ch)
                down = INPUT(type=INPUT_KEYBOARD)
                down.u.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
                up = INPUT(type=INPUT_KEYBOARD)
                up.u.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
                inputs.append(down)
                inputs.append(up)

            if inputs:
                arr = (INPUT * len(inputs))(*inputs)
                user32.SendInput(len(inputs), ctypes.byref(arr), ctypes.sizeof(INPUT))
                time.sleep(0.055)

            # Press Enter key (VK_RETURN = 0x0D, scan = 0x1C)
            enter_arr = (INPUT * 2)()
            enter_arr[0].type = INPUT_KEYBOARD
            enter_arr[0].u.ki = KEYBDINPUT(wVk=VK_RETURN, wScan=0x1C, dwFlags=0, time=0, dwExtraInfo=0)
            enter_arr[1].type = INPUT_KEYBOARD
            enter_arr[1].u.ki = KEYBDINPUT(wVk=VK_RETURN, wScan=0x1C, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
            user32.SendInput(2, ctypes.byref(enter_arr), ctypes.sizeof(INPUT))
            return True
        except Exception:
            return False

    def _win32_focus_and_click_point(self, screen_x: int, screen_y: int, node: UIANode | None = None) -> int:
        """Click directly inside the Camfrog 'Say something...' chat input box at (screen_x, screen_y)
        WITHOUT calling SetForegroundWindow (which injects a synthetic VK_MENU / Alt key on Windows!).
        """
        if os.name != "nt":
            return 0
        user32 = ctypes.windll.user32
        hwnd, cx, cy = self._find_target_hwnd_and_client_pt(screen_x, screen_y, node)
        top_hwnd = int(self._hwnd or hwnd or 0)

        # Ensure window is not minimized (SW_SHOWNOACTIVATE never injects Alt)
        if top_hwnd and user32.IsWindow(wintypes.HWND(top_hwnd)):
            if user32.IsIconic(wintypes.HWND(top_hwnd)):
                user32.ShowWindow(wintypes.HWND(top_hwnd), SW_SHOWNOACTIVATE)

        # Release any stuck Alt/Ctrl/Shift modifiers before clicking
        self._release_all_modifier_keys()

        # Move cursor to exact calibrated pixel and perform hardware left click
        # (A physical mouse click naturally activates Camfrog's input box without Windows injecting Alt!)
        try:
            user32.SetCursorPos(int(screen_x), int(screen_y))
            time.sleep(0.025)
            MOUSEEVENTF_LEFTDOWN = 0x0002
            MOUSEEVENTF_LEFTUP = 0x0004
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.025)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        except Exception:
            if uia_click is not None:
                try:
                    uia_click(coords=(int(screen_x), int(screen_y)))
                except Exception:
                    pass

        # Release any modifiers again so Alt is guaranteed UP
        self._release_all_modifier_keys()
        return hwnd

    def _win32_paste_and_press_enter(self, cleaned: str, copied_to_clip: bool, hwnd: int) -> None:
        """Insert command into Camfrog's focused chat box and press Enter WITHOUT ever pressing 'A',
        Ctrl+A, or Alt+A (so Camfrog's Alt+A Room Info dialog can NEVER open!).
        """
        user32 = ctypes.windll.user32
        VK_CONTROL = 0x11
        VK_V = 0x56
        KEYEVENTF_KEYUP = 0x0002

        # Guarantee Alt/Ctrl/Shift are completely released first
        self._release_all_modifier_keys()

        if copied_to_clip:
            try:
                # Pure Ctrl+V paste ONLY (NEVER send VK_A / Ctrl+A / Alt+A!)
                user32.keybd_event(VK_CONTROL, 0x1D, 0, 0)
                time.sleep(0.015)
                user32.keybd_event(VK_V, 0x2F, 0, 0)
                time.sleep(0.025)
                user32.keybd_event(VK_V, 0x2F, KEYEVENTF_KEYUP, 0)
                time.sleep(0.015)
                user32.keybd_event(VK_CONTROL, 0x1D, KEYEVENTF_KEYUP, 0)
            except Exception:
                self._send_unicode_string_and_enter(cleaned)
                return

            # Wait 65ms so Camfrog's Chromium DOM input registers the pasted text before pressing Enter
            time.sleep(0.065)

            # Press hardware Enter key (VK_RETURN = 0x0D, hardware scan code = 0x1C)
            try:
                user32.keybd_event(VK_RETURN, 0x1C, 0, 0)
                time.sleep(0.025)
                user32.keybd_event(VK_RETURN, 0x1C, KEYEVENTF_KEYUP, 0)
            except Exception:
                if uia_send_keys is not None:
                    uia_send_keys("{ENTER}", pause=0.01)
        else:
            # Fallback if clipboard was locked: direct SendInput(KEYEVENTF_UNICODE) + Enter (zero modifier keys!)
            if not self._send_unicode_string_and_enter(cleaned) and uia_send_keys is not None:
                escaped = re.sub(r"([+^%~(){}])", r"{\1}", cleaned)
                uia_send_keys(escaped + "{ENTER}", with_spaces=True, pause=0.01)

        # Also send WM_KEYDOWN/WM_KEYUP VK_RETURN to child HWND if needed
        if hwnd:
            try:
                wh = wintypes.HWND(hwnd)
                user32.PostMessageW(wh, WM_KEYDOWN, VK_RETURN, 0x001C0001)
                user32.PostMessageW(wh, WM_KEYUP, VK_RETURN, 0xC01C0001)
            except Exception:
                pass

    def send_chat_message(self, message: str, dry_run: bool = False) -> bool:
        """Send text into Camfrog's Chat Txt Field ('Say something...' at [1396, 1206, 2497, 1241])
        reliably for both UIA controls and embedded Chromium (CEF) chat inputs, with zero 'A' / Alt+A / Ctrl+A
        keystrokes so Camfrog's Info window never pops up.
        """
        if dry_run:
            return True
        cleaned = str(message or "").strip()
        if not cleaned:
            return False

        with self._send_lock:
            if not self.is_connected():
                self.connect_to_camfrog()

            self._ensure_renderable_in_background()

            # Check cached nodes first (never run a slow refresh=True scan inside send_chat_message)
            node = self._find_chat_input(self.nodes(refresh=False))
            if node is None and self.calibrated_chat_input_screen_pt is None:
                try:
                    self.auto_calibrate_camfrog()
                except Exception:
                    pass

            # Determine exact screen (x, y) of the Camfrog 'Say something...' chat input box:
            # Priority 1: User's calibrated screen point (from 3s Hover or Method 2 Direct Pixel Entry)
            # Priority 2: Safe left-interior of discovered UIA Chat Input Node (nl + 140) so it never clicks right-side emoji/gift popup icons
            # Priority 3: Calibrated rect scaled to current Camfrog window position at x=1580, y=1223
            if self.calibrated_chat_input_screen_pt is not None:
                scr_cx, scr_cy = int(self.calibrated_chat_input_screen_pt[0]), int(self.calibrated_chat_input_screen_pt[1])
            elif node is not None:
                nl, nt, nr, nb = node.rect_tuple
                safe_cal_x = min(nl + 140, (nl + nr) // 2)
                scr_cx, scr_cy = self._calibrated_to_screen_point(safe_cal_x, (nt + nb) // 2)
            else:
                il, it, ir, ib = self.calibrated_chat_input_rect or CHAT_INPUT_RECT
                scr_cx, scr_cy = self._calibrated_to_screen_point(1580, (it + ib) // 2)

            try:
                # Tier 1: Direct UIA ValuePattern + Enter (works for native Edit controls and unit test mocks)
                if node is not None and node.control is not None:
                    try:
                        iface_val = getattr(node.control, "iface_value", None)
                        if iface_val is not None:
                            iface_val.SetValue(cleaned)
                            node.control.type_keys("{ENTER}", set_foreground=False)
                            self._last_chat_change_at = time.monotonic()
                            return True
                    except Exception:
                        pass

                # Tier 2: Pure Click + Ctrl+V Paste + Enter (Zero Ctrl+A / Alt+A / SetForegroundWindow Alt injection!)
                if os.name == "nt":
                    user32 = ctypes.windll.user32
                    # Wait briefly (up to 400ms) if the user is actively holding down the left mouse button
                    wait_start = time.monotonic()
                    while (user32.GetAsyncKeyState(0x01) & 0x8000) != 0 and (time.monotonic() - wait_start) < 0.4:
                        time.sleep(0.02)

                    prev_pt = wintypes.POINT()
                    has_prev_pt = bool(user32.GetCursorPos(ctypes.byref(prev_pt)))

                    # Copy message to Windows clipboard for instant Ctrl+V paste
                    copied_to_clip = self._set_win32_clipboard_text(cleaned)

                    if self.allow_physical_fallback:
                        hwnd = self._win32_focus_and_click_point(int(scr_cx), int(scr_cy), node)
                        time.sleep(0.055)
                        self._win32_paste_and_press_enter(cleaned, copied_to_clip, hwnd)
                        time.sleep(0.055)

                        # Restore mouse cursor position (without calling SetForegroundWindow which injects Alt!)
                        if has_prev_pt:
                            user32.SetCursorPos(int(prev_pt.x), int(prev_pt.y))
                        self._last_chat_change_at = time.monotonic()
                        return True

                    # Background-only Win32 PostMessage fallback (when allow_physical_fallback is False)
                    hwnd, cx, cy = self._find_target_hwnd_and_client_pt(scr_cx, scr_cy, node)
                    if hwnd:
                        wh = wintypes.HWND(hwnd)
                        lparam = self._make_lparam(cx, cy)
                        user32.PostMessageW(wh, WM_SETFOCUS, 0, 0)
                        user32.PostMessageW(wh, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
                        user32.PostMessageW(wh, WM_LBUTTONUP, 0, lparam)
                        for ch in cleaned:
                            user32.PostMessageW(wh, WM_CHAR, ord(ch), 1)
                        time.sleep(0.02)
                        user32.PostMessageW(wh, WM_KEYDOWN, VK_RETURN, 0x001C0001)
                        user32.PostMessageW(wh, WM_CHAR, VK_RETURN, 0x001C0001)
                        user32.PostMessageW(wh, WM_KEYUP, VK_RETURN, 0xC01C0001)
                        self._last_chat_change_at = time.monotonic()
                        return True

                # Tier 3: UIA control type_keys with set_foreground=False (used by unit tests & non-HWND UIA mocks)
                if node is not None and node.control is not None:
                    try:
                        escaped = re.sub(r"([+^%~(){}])", r"{\1}", cleaned)
                        node.control.type_keys(escaped + "{ENTER}", with_spaces=True, set_foreground=False)
                        self._last_chat_change_at = time.monotonic()
                        return True
                    except Exception:
                        pass

                self.last_error = (
                    "Camfrog chat input could not receive keystrokes. Run as Administrator and click "
                    "'🎯 CALIBRATE CHAT BOX (3s HOVER)' or enter Chat Box X,Y in Method 2."
                )
                return False
            except Exception as error:
                self.last_error = f"Camfrog UIA chat send failed: {error}"
                return False

    def _wait_until_mic_free(self, timeout_seconds: float = 12.0) -> bool:
        """Wait until Active Speaker [l=1506,t=1174,r=1548,b=1190] has no other user's name."""
        deadline = time.monotonic() + max(0.1, timeout_seconds)
        while time.monotonic() < deadline:
            speaker = self.get_active_speaker(refresh=True)
            if speaker is None or speaker.casefold() == BOT_USERNAME.casefold():
                return True
            time.sleep(0.05)
        speaker = self.get_active_speaker(refresh=True)
        return speaker is None or speaker.casefold() == BOT_USERNAME.casefold()

    def _wait_for_bot_mic_persistence(
        self,
        bot_username: str = BOT_USERNAME,
        persist_seconds: float = MIC_CONFIRM_PERSIST_SECONDS,
        timeout_seconds: float = 6.0,
    ) -> bool:
        """Wait until 'KaeKae_Toad' (or the newly triggered active-speaker button after our Talk hold)
        persists at Active Speaker [l=1506,t=1174,r=1548,b=1190] for 1.3s.
        """
        deadline = time.monotonic() + max(persist_seconds + 0.5, timeout_seconds)
        seen_since: float | None = None
        target_lower = bot_username.casefold()

        while time.monotonic() < deadline:
            speaker = self.get_active_speaker(refresh=True)
            if speaker and (
                speaker.casefold() == target_lower
                or speaker.startswith("Speaker_On_Mic[")
            ):
                if seen_since is None:
                    seen_since = time.monotonic()
                elif time.monotonic() - seen_since >= persist_seconds:
                    return True
            else:
                seen_since = None
            time.sleep(0.04)
        return False

    def _release_mic_hold(
        self,
        screen_x: int,
        screen_y: int,
        talk_node: UIANode | None = None,
        *,
        backend: str = "",
    ) -> None:
        """Release a held Talk button (mouse-up) using the SAME backend that pressed it, plus a physical fallback.

        A held Talk button MUST always be released or KaeKae_Toad would stay stuck transmitting on the mic.
        """
        try:
            released = False
            if backend != "pywinauto-physical":
                released = self._post_background_press_or_release(
                    screen_x, screen_y, down=False, node=talk_node
                )
            if not released and uia_release is not None:
                try:
                    uia_release(coords=(int(screen_x), int(screen_y)))
                except Exception:
                    pass
        except Exception:
            pass

    def _precision_mic_grab_attempt(
        self,
        screen_x: int,
        screen_y: int,
        talk_node: UIANode | None = None,
    ) -> dict[str, Any]:
        """Execute ONE microphone-grab attempt exactly per operator spec:

        1. Take 3 EXTREMELY FAST clicks on the Talk button.
        2. HOLD the 4th click (mouse-down, no mouse-up) to transmit.
        3. While holding, watch the SPEAKER button for our own name 'KaeKae_Toad'
           to persist >= MIC_CONFIRM_PERSIST_SECONDS (1.3s)  -> grab SUCCESSFUL.
        4. Guarantee a stable >= MIC_GRAB_HOLD_MIN_SECONDS (3.0s) total hold before
           declaring success (a real, sustained broadcast hold).
        5. If our own name never persists within MIC_GRAB_CONFIRM_TIMEOUT_S the grab
           FAILED. The caller releases the hold and REPEATS the whole cycle.

        Returns a dict: {success, held, backend, reason, held_seconds}.
        """
        # --- Step 1: 3 extremely fast clicks (wake/focus the Talk button) ---
        for _ in range(max(0, int(MIC_GRAB_FAST_CLICKS))):
            if not self._post_background_click(screen_x, screen_y, talk_node):
                if uia_click is not None:
                    try:
                        uia_click(coords=(int(screen_x), int(screen_y)))
                    except Exception:
                        pass
            time.sleep(max(0.0, MIC_GRAB_FAST_CLICK_DELAY))

        # --- Step 2: HOLD the 4th click (mouse-down, NO mouse-up) ---
        held_backend = ""
        if self._post_background_press_or_release(screen_x, screen_y, down=True, node=talk_node):
            held_backend = "win32-postmessage"
        elif uia_press is not None:
            try:
                uia_press(coords=(int(screen_x), int(screen_y)))
                held_backend = "pywinauto-physical"
            except Exception:
                held_backend = ""
        if not held_backend:
            return {
                "success": False,
                "held": False,
                "backend": "",
                "reason": "could not press/hold the Talk button",
                "held_seconds": 0.0,
            }

        # --- Steps 3 & 4: watch the SPEAKER button while holding ---
        started = time.monotonic()
        deadline = started + max(MIC_GRAB_CONFIRM_TIMEOUT_S, MIC_GRAB_HOLD_MIN_SECONDS + 1.5)
        seen_since: float | None = None
        target_lower = BOT_USERNAME.casefold()
        success = False
        while time.monotonic() < deadline:
            speaker = self.get_active_speaker(refresh=True)
            now = time.monotonic()
            held_seconds = now - started
            if speaker and (
                speaker.casefold() == target_lower or speaker.startswith("Speaker_On_Mic[")
            ):
                if seen_since is None:
                    seen_since = now
                persisted = now - seen_since
                # SUCCESS only when name persisted >= 1.3s AND we held >= 3.0s total.
                if persisted >= MIC_CONFIRM_PERSIST_SECONDS and held_seconds >= MIC_GRAB_HOLD_MIN_SECONDS:
                    success = True
                    break
            else:
                seen_since = None
            time.sleep(0.04)

        held_seconds = time.monotonic() - started
        if success:
            return {
                "success": True,
                "held": True,
                "backend": held_backend,
                "reason": "",
                "held_seconds": held_seconds,
            }
        return {
            "success": False,
            "held": True,
            "backend": held_backend,
            "reason": (
                f"own name did not persist on the SPEAKER button "
                f"(held {held_seconds:.1f}s, needs >= {MIC_GRAB_HOLD_MIN_SECONDS:.1f}s + "
                f"{MIC_CONFIRM_PERSIST_SECONDS:.1f}s persistence)"
            ),
            "held_seconds": held_seconds,
        }

    def set_tts_voice(self, voice_name_or_alias: str) -> str:
        """Select a TTS voice for the SPECIAL MIC LINE.

        Accepts (in priority order):
          * A Coqui label (women / Coqui Default / CLONE)  -> routed to the XTTS engine via `tts_voice_label`.
          * A Kokoro label (women-only presets / Kokoro Default) -> routed to the local GPU Kokoro engine.
          * An Edge female display label ("Edge Aria", ...) -> the mapped Edge Neural voice ID.
          * A short Edge alias ('aria', 'jenny', ...) or a full Edge Neural voice ID (kept for legacy !voice cmds).
        """
        cleaned = str(voice_name_or_alias or "").strip()
        if not cleaned:
            return self.tts_voice
        alias = cleaned.casefold()

        # 1. Coqui / XTTS voice selection (women, default-test, or the dynamic CLONE slot).
        if is_coqui_voice(cleaned):
            self.tts_voice_label = cleaned
            return cleaned

        # 2. Local Kokoro (GPU) voice selection (women-only presets + Kokoro Default test).
        if is_kokoro_voice(cleaned):
            self.tts_voice_label = cleaned
            return cleaned

        # 2. Edge female display labels from the SPECIAL MIC LINE sub-menu ("Edge Aria", etc.).
        if cleaned in EDGE_FEMALE_VOICES:
            self.tts_voice_label = cleaned
            self.tts_voice = EDGE_FEMALE_VOICES[cleaned]
            return self.tts_voice

        # 3. Short alias ('aria', 'jenny', ...) mapped onto the female-only Edge catalog.
        for label, full_voice in EDGE_FEMALE_VOICES.items():
            local_alias = label.split(" ", 1)[1].casefold()
            if alias == local_alias or alias == full_voice.casefold():
                self.tts_voice_label = label
                self.tts_voice = full_voice
                return self.tts_voice

        # 4. Legacy full Edge voice dict / raw Neural IDs.
        if alias in EDGE_TTS_VOICES:
            self.tts_voice = EDGE_TTS_VOICES[alias]
            return self.tts_voice
        for key, full_voice in EDGE_TTS_VOICES.items():
            if alias in key or alias == full_voice.casefold():
                self.tts_voice = full_voice
                return self.tts_voice
        if "Neural" in cleaned or "-" in cleaned:
            self.tts_voice = cleaned
        return self.tts_voice

    def _synthesize_realistic_tts_wav(self, text: str, wav_path: Path, voice: str | None = None) -> tuple[bool, float]:
        """Synthesize ultra-realistic speech to a 16-bit PCM WAV file.

        Engine priority (per operator request):
          * Local Kokoro-82M ONNX (offline, unlimited, AMD DirectML when available) whenever the
            requested voice is a Kokoro label (women-only presets / Kokoro Default). If Kokoro is
            unavailable the call transparently falls through to Coqui -> Edge -> OneCore so the mic
            ALWAYS still broadcasts.
          * Coqui / XTTS v2 (GPU when possible) whenever the requested voice is a Coqui label
            (women / Coqui Default / CLONE). If XTTS is unavailable the call transparently falls
            through to the reliable Edge Neural tier so the microphone ALWAYS still broadcasts.
          * Tier 1 (Primary Edge): Free, unlimited Microsoft Edge Neural TTS (`edge-tts` + `miniaudio`).
          * Tier 2 (Offline Fallback): Windows OneCore Neural/Natural voices via PowerShell.
        """
        # Resolve the requested label. `voice` may be a Kokoro label, a Coqui label, an Edge
        # female label, or None.
        requested_label = str(voice or self.tts_voice_label or "").strip()
        if voice:
            self.set_tts_voice(voice)
            if is_kokoro_voice(voice) or is_coqui_voice(voice):
                requested_label = voice
            else:
                requested_label = self.tts_voice_label

        # --- Local Kokoro-82M ONNX path (offline, unlimited, GPU when available) ---
        if is_kokoro_voice(requested_label):
            kokoro_label = requested_label

            def _kokoro_log(line: str) -> None:
                if self.log_callback is not None:
                    self.log_callback(line)
                else:
                    print(line, flush=True)

            ok, engine = self.kokoro.synthesize(
                text,
                wav_path,
                kokoro_label,
                log=_kokoro_log,
            )
            if ok:
                self.last_tts_engine = engine
                duration = 2.0
                try:
                    with wave.open(str(wav_path), "rb") as wf:
                        rate = wf.getframerate()
                        if rate > 0:
                            duration = max(0.5, wf.getnframes() / float(rate))
                except Exception:
                    pass
                return True, duration
            # Kokoro unavailable/failed -> fall through to Coqui -> Edge Neural (mic still works).

        # --- Coqui / XTTS v2 path (voice cloning + women voices on GPU when available) ---
        if is_coqui_voice(requested_label):
            coqui_label = requested_label

            def _coqui_log(line: str) -> None:
                if self.log_callback is not None:
                    self.log_callback(line)
                else:
                    print(line, flush=True)

            ok, engine = self.coqui.synthesize(
                text,
                wav_path,
                coqui_label,
                log=_coqui_log,
            )
            if ok:
                self.last_tts_engine = engine
                duration = 2.0
                try:
                    with wave.open(str(wav_path), "rb") as wf:
                        rate = wf.getframerate()
                        if rate > 0:
                            duration = max(0.5, wf.getnframes() / float(rate))
                except Exception:
                    pass
                return True, duration
            # Coqui unavailable/failed -> fall through to Edge Neural with KaeKae's female voice.

        chosen_voice = self.tts_voice or EDGE_TTS_DEFAULT_VOICE

        # Tier 1: Microsoft Edge Neural TTS (Free, Unlimited, Ultra-Realistic)
        try:
            import asyncio
            import edge_tts
            import miniaudio

            mp3_path = wav_path.with_suffix(".mp3")

            async def _fetch_neural_mp3() -> None:
                comm = edge_tts.Communicate(
                    text,
                    chosen_voice,
                    rate=EDGE_TTS_RATE,
                    pitch=EDGE_TTS_PITCH,
                )
                await comm.save(str(mp3_path))

            asyncio.run(_fetch_neural_mp3())

            if mp3_path.exists() and mp3_path.stat().st_size > 128:
                decoded = miniaudio.decode_file(
                    str(mp3_path),
                    output_format=miniaudio.SampleFormat.SIGNED16,
                    nchannels=1,
                    sample_rate=24000,
                )
                raw_pcm = bytes(decoded.samples)
                with wave.open(str(wav_path), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(24000)
                    wf.writeframes(raw_pcm)
                self.last_tts_engine = f"Edge Neural ({chosen_voice})"
                duration = max(0.5, len(decoded.samples) / 24000.0)
                return True, duration
        except Exception:
            pass

        # Tier 2: Offline Windows OneCore / SAPI fallback (prefers Natural/Zira/Mark/Eva voices over robotic David)
        ps_script = (
            "Add-Type -AssemblyName System.Speech; "
            "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$voices = $synth.GetInstalledVoices() | Where-Object { $_.Enabled }; "
            "$pick = $voices | Where-Object { $_.VoiceInfo.Name -match 'Natural|Aria|Jenny|Ava|Guy|Zira|Eva|Hazel' } | Select-Object -First 1; "
            "if ($pick) { $synth.SelectVoice($pick.VoiceInfo.Name) }; "
            "$synth.Rate = 0; "
            f"$synth.SetOutputToWaveFile('{wav_path}'); "
            f"$synth.Speak({text!r}); "
            "$synth.Dispose();"
        )
        creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_script],
            check=False,
            creationflags=creationflags,
        )
        if not wav_path.exists():
            return False, 0.0

        self.last_tts_engine = "Windows Speech Fallback"
        duration = 2.0
        try:
            with wave.open(str(wav_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    duration = max(0.5, frames / float(rate))
        except Exception:
            pass
        return True, duration

    def broadcast_tts_via_vbcable(self, text: str, dry_run: bool = False, voice: str | None = None) -> bool:
        """Broadcast realistic neural speech over VB-Cable ('CABLE Input') using the PRECISION mic-grab sequence.

        Pipeline (per operator spec):
          1. Wait until the SPEAKER button [1506,1174,1548,1190] shows nobody else's name.
          2. Synthesize + save the TTS clip temporarily so it is ready to fire the instant the mic is grabbed.
          3. Grab the mic: 3 EXTREMELY FAST clicks then HOLD the 4th click, while watching the SPEAKER button
             for our own name 'KaeKae_Toad' to persist >= 1.3s  -> grab SUCCESSFUL.
          4. If the name never persists (and we didn't hold >= 3s total), RELEASE and REPEAT the whole grab
             cycle (up to MIC_GRAB_MAX_ATTEMPTS) until the broadcast can go out.
          5. Play the saved clip all the way through over VB-Cable while still holding the Talk button.
        """
        cleaned_text = str(text or "").strip()
        if not cleaned_text or not VB_CABLE_TTS_ENABLED:
            return False
        if voice:
            self.set_tts_voice(voice)
        if dry_run:
            return True

        self._ensure_renderable_in_background()
        if not self._wait_until_mic_free(timeout_seconds=12.0):
            active = self.get_active_speaker(refresh=True)
            self.last_error = f"Cannot grab Talk Button: '{active}' is currently on the microphone at {list(ACTIVE_SPEAKER_RECT)}."
            return False

        talk_node = self._find_talk(self.nodes(refresh=False))
        if self.calibrated_talk_button_screen_pt is not None:
            scr_cx, scr_cy = int(self.calibrated_talk_button_screen_pt[0]), int(self.calibrated_talk_button_screen_pt[1])
        else:
            l, t, r, b = self._rect(talk_node) or self.calibrated_talk_button_rect or TALK_BUTTON_RECT
            cal_cx, cal_cy = (l + r) // 2, (t + b) // 2  # (1326, 1182)
            scr_cx, scr_cy = self._calibrated_to_screen_point(cal_cx, cal_cy)

        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "tts_out.wav"
            ok_synth, duration = self._synthesize_realistic_tts_wav(cleaned_text, wav_path, voice=voice)
            if not ok_synth or not wav_path.exists():
                self.last_error = "TTS WAV synthesis failed."
                return False

            held = False
            held_backend = ""
            try:
                grab_ok = False
                reason = "mic grab not confirmed"
                for attempt in range(1, MIC_GRAB_MAX_ATTEMPTS + 1):
                    res = self._precision_mic_grab_attempt(scr_cx, scr_cy, talk_node)
                    if res.get("success"):
                        grab_ok = True
                        held = bool(res.get("held"))
                        held_backend = str(res.get("backend", ""))
                        break
                    reason = str(res.get("reason", "own name did not persist on SPEAKER button"))
                    # CRITICAL: release the held Talk button from this failed attempt so it can't stay
                    # stuck transmitting, then re-monitor the SPEAKER button before re-shooting the grab.
                    if res.get("held"):
                        self._release_mic_hold(scr_cx, scr_cy, talk_node, backend=str(res.get("backend", "")))
                    if attempt < MIC_GRAB_MAX_ATTEMPTS:
                        # Re-monitor the SPEAKER button until it is clear again before re-shooting the grab.
                        self._wait_until_mic_free(timeout_seconds=3.0)
                        time.sleep(MIC_GRAB_RETRY_PAUSE_S)

                if not grab_ok:
                    self.last_error = (
                        f"Mic grab FAILED after {MIC_GRAB_MAX_ATTEMPTS} attempt(s): {reason}. "
                        "KaeKae_Toad could not confirm her name persisting on the SPEAKER button."
                    )
                    return False

                # Confirmed: broadcast the pre-saved clip all the way through while still holding the Talk button.
                played = self._play_wav_to_vbcable(wav_path, duration)
                if not played:
                    time.sleep(duration)
                return True
            except Exception as error:
                self.last_error = f"VB-Cable TTS broadcast failed: {error}"
                return False
            finally:
                if held:
                    self._release_mic_hold(scr_cx, scr_cy, talk_node, backend=held_backend)

    def _play_wav_to_vbcable(self, wav_path: Path, duration: float) -> bool:
        try:
            import numpy as np
            import sounddevice as sd
            import wave as _wave

            devices = sd.query_devices()
            target_idx = None
            for idx, dev in enumerate(devices):
                if VB_CABLE_PLAYBACK_DEVICE.lower() in str(dev.get("name", "")).lower() and dev.get("max_output_channels", 0) > 0:
                    target_idx = idx
                    break

            with _wave.open(str(wav_path), "rb") as wf:
                rate = wf.getframerate()
                channels = wf.getnchannels()
                raw = wf.readframes(wf.getnframes())
                data = np.frombuffer(raw, dtype=np.int16)
                if channels > 1:
                    data = data.reshape(-1, channels)
                sd.play(data, samplerate=rate, device=target_idx)
                sd.wait()
                return True
        except Exception:
            try:
                import winsound
                winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
                return True
            except Exception:
                return False

    def find_room_by_position(self, x: int, y: int) -> str | None:
        for room_name, (left, top, right, bottom) in ROOM_TAB_POSITIONS.items():
            if left <= x <= right and top <= y <= bottom:
                return room_name
        return None

    def get_current_room(self) -> str | None:
        if not self.window and not self.connect_to_camfrog():
            return None
        try:
            title = self.window.window_text() or ""
            for room_name in ROOM_TAB_POSITIONS:
                if room_name.lower() in title.lower():
                    return room_name
        except Exception:
            pass
        return "Players__Lounge"

    def transcribe_audio_chunk_for_speaker(
        self,
        duration_seconds: float = 2.8,
        return_details: bool = False,
    ) -> str | dict[str, Any]:
        """Record a short audio chunk from VB-Cable ('CABLE Output' / Stereo Mix / WASAPI Loopback / default input)
        while an Active Speaker is talking at [1506,1174,1548,1190] and transcribe it to text via SpeechRecognition
        (Google Web Speech API) or Windows System.Speech offline fallback.

        Automatically normalizes quiet room audio so low-volume Camfrog speakers are transcribed reliably, and stores
        detailed capture telemetry in `self.last_transcribe_diag` so Terminal 1 can show live audio reaction in real time!
        """
        diag: dict[str, Any] = {
            "transcript": "",
            "device_name": "none",
            "device_index": None,
            "peak": 0,
            "rms": 0,
            "engine": "none",
            "error": "",
        }
        self.last_transcribe_diag = diag
        if os.name != "nt":
            return diag if return_details else ""

        dur = max(1.2, min(6.0, float(duration_seconds)))
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "speaker_chunk.wav"
            recorded = False
            try:
                import numpy as np
                import sounddevice as sd
                import wave as _wave

                devices = sd.query_devices()
                rec_idx = None
                rec_name = "Default Input Device"
                preferred_keywords = (
                    "cable output",
                    "vb-audio",
                    "stereo mix",
                    "what u hear",
                    "wave out",
                    "loopback",
                    "voicemeeter",
                )
                for preferred in preferred_keywords:
                    for idx, dev in enumerate(devices):
                        name_str = str(dev.get("name", ""))
                        if preferred in name_str.lower() and int(dev.get("max_input_channels", 0)) > 0:
                            rec_idx = idx
                            rec_name = name_str
                            break
                    if rec_idx is not None:
                        break

                if rec_idx is None:
                    try:
                        default_in = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else None
                        if default_in is not None and int(default_in) >= 0 and int(default_in) < len(devices):
                            rec_idx = int(default_in)
                            rec_name = str(devices[rec_idx].get("name", "Default Input"))
                    except Exception:
                        pass

                diag["device_index"] = rec_idx
                diag["device_name"] = rec_name

                samplerate = 16000
                frames = sd.rec(
                    int(dur * samplerate),
                    samplerate=samplerate,
                    channels=1,
                    dtype="int16",
                    device=rec_idx,
                )
                sd.wait()
                if frames is not None and frames.size > 0:
                    abs_frames = np.abs(frames.astype(np.int32))
                    peak = int(np.max(abs_frames))
                    rms = int(np.sqrt(np.mean(abs_frames.astype(np.float64) ** 2)))
                else:
                    peak, rms = 0, 0

                diag["peak"] = peak
                diag["rms"] = rms

                # Lowered silence gate (peak >= 35) + automatic gain normalization so quiet Camfrog speakers are heard clearly
                if peak >= 35:
                    pcm_frames = frames
                    if peak < 8000 and peak > 0:
                        gain = min(14.0, 14000.0 / float(peak))
                        boosted = np.clip(frames.astype(np.float32) * gain, -32767, 32767).astype(np.int16)
                        pcm_frames = boosted
                    with _wave.open(str(wav_path), "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(samplerate)
                        wf.writeframes(pcm_frames.tobytes())
                    recorded = True
            except Exception as rec_err:
                diag["error"] = f"Audio capture error: {rec_err}"
                recorded = False

            if not recorded or not wav_path.exists():
                self.last_transcribe_diag = diag
                return diag if return_details else ""

            # Tier 0 (Ultra High-Speed GPU): WhisperX / faster-whisper resolved through the SHARED
            # AMD-first -> NVIDIA -> CPU backend resolver (single source of truth with XTTS + diagnostics).
            try:
                whisperx_model = getattr(self, "_whisperx_model", None)
                if whisperx_model is None:
                    dev = resolve_compute_device()
                    backend = dev.get("backend", "cpu")
                    # CTranslate2 (faster-whisper / whisperx) natively accelerates on CUDA (NVIDIA +
                    # AMD ROCm) and CPU. AMD DirectML (RX 9070 XT) is bridged to a real CUDA device
                    # only when the installed torch exposes it (ROCm); otherwise it runs the fast CPU path.
                    if backend == "amd-rocm":
                        device, compute_type = "cuda", "float16"
                        flavor = "WhisperX-ROCm (AMD RX 9070 XT)"
                    elif backend == "nvidia-cuda":
                        device, compute_type = "cuda", "float16"
                        flavor = "WhisperX-CUDA (NVIDIA)"
                    elif backend == "amd-directml":
                        # Prefer a ROCm/CUDA bridge when torch actually sees an accelerator, else fast CPU int8.
                        try:
                            import torch  # type: ignore[import-not-found]
                            if getattr(torch.version, "hip", None) and torch.cuda.is_available():
                                device, compute_type = "cuda", "float16"
                                flavor = "WhisperX-DirectML→ROCm (AMD RX 9070 XT)"
                            else:
                                device, compute_type = "cpu", "int8"
                                flavor = "FasterWhisper-CPU (DirectML RX 9070 XT pending ROCm bridge)"
                        except Exception:
                            device, compute_type = "cpu", "int8"
                            flavor = "FasterWhisper-CPU"
                    else:
                        device, compute_type = "cpu", "int8"
                        flavor = "WhisperX-CPU"

                    # Load the fastest engine first: faster-whisper (CTranslate2), then full WhisperX.
                    # Track an explicit engine flag so the transcribe dispatch below is unambiguous
                    # (a substring check would misfire because "WhisperX" is inside "FasterWhisper").
                    try:
                        from faster_whisper import WhisperModel  # type: ignore[import-not-found]
                        self._whisperx_model = WhisperModel("base.en", device=device, compute_type=compute_type)
                        whisperx_model = self._whisperx_model
                        self._whisperx_flavor = flavor.replace("WhisperX", "FasterWhisper")
                        self._whisperx_is_faster_whisper = True
                    except Exception:
                        try:
                            import whisperx  # type: ignore[import-not-found]
                            self._whisperx_model = whisperx.load_model("base.en", device=device, compute_type=compute_type)
                            whisperx_model = self._whisperx_model
                            self._whisperx_flavor = flavor
                            self._whisperx_is_faster_whisper = False
                        except Exception:
                            self._whisperx_model = False
                            whisperx_model = False

                if whisperx_model:
                    flavor = getattr(self, "_whisperx_flavor", "WhisperX")
                    if not getattr(self, "_whisperx_is_faster_whisper", False):
                        # Full WhisperX: load_audio returns a float array + transcribe returns a dict.
                        import whisperx
                        audio = whisperx.load_audio(str(wav_path))
                        result = whisperx_model.transcribe(audio, batch_size=16)
                        segments = result.get("segments", [])
                        text_parts = [s.get("text", "").strip() for s in segments if s.get("text")]
                        cleaned_out = " ".join(text_parts).strip()
                    else:
                        # faster-whisper (CTranslate2): transcribe returns (segments, info) on the file path.
                        segments, _ = whisperx_model.transcribe(str(wav_path), beam_size=1, vad_filter=True)
                        cleaned_out = " ".join([s.text.strip() for s in segments if s.text]).strip()

                    if cleaned_out:
                        diag["transcript"] = cleaned_out
                        diag["engine"] = flavor
                        self.last_transcribe_diag = diag
                        return diag if return_details else cleaned_out
            except Exception as wx_err:
                diag["error"] = f"WhisperX note: {wx_err}"

            # Tier 1: SpeechRecognition Google Web Speech API (fast, accurate, zero API key required)
            try:
                import speech_recognition as sr  # type: ignore[import-not-found]

                recognizer = sr.Recognizer()
                recognizer.dynamic_energy_threshold = False
                recognizer.energy_threshold = 50
                with sr.AudioFile(str(wav_path)) as source:
                    audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data)
                if text and str(text).strip():
                    cleaned_out = str(text).strip()
                    diag["transcript"] = cleaned_out
                    diag["engine"] = "GoogleWebSpeech"
                    self.last_transcribe_diag = diag
                    return diag if return_details else cleaned_out
            except Exception as sr_err:
                diag["error"] = f"{diag.get('error', '')} | SpeechRecognition: {sr_err}".strip(" |")

            # Tier 2: Offline Windows System.Speech.Recognition fallback via PowerShell
            try:
                ps_rec = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine; "
                    "$rec.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar)); "
                    f"$rec.SetInputToWaveFile('{wav_path}'); "
                    "$res = $rec.Recognize(); "
                    "if ($res) { Write-Output $res.Text }; "
                    "$rec.Dispose();"
                )
                creationflags = 0x08000000 if os.name == "nt" else 0
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_rec],
                    capture_output=True,
                    text=True,
                    timeout=4.0,
                    check=False,
                    creationflags=creationflags,
                )
                out = (proc.stdout or "").strip()
                if out:
                    diag["transcript"] = out
                    diag["engine"] = "WinSystemSpeech"
                    self.last_transcribe_diag = diag
                    return diag if return_details else out
            except Exception as ps_err:
                diag["error"] = f"{diag.get('error', '')} | WinSpeech: {ps_err}".strip(" |")

        self.last_transcribe_diag = diag
        return diag if return_details else ""


    def probe_audio_and_component_diagnostics(self) -> dict[str, Any]:
        """Run a comprehensive 8-component live hardware, window, UIA, OCR, and audio diagnostic probe."""
        report: dict[str, Any] = {
            "admin": is_windows_admin(),
            "connected": False,
            "hwnd": self._hwnd,
            "window_title": "",
            "window_rect": self._get_window_rect(),
            "chat_events_visible": 0,
            "sample_chat_line": "",
            "user_list_count": 0,
            "sample_users": [],
            "active_speaker": None,
            "chat_box_pixel": self.calibrated_chat_input_screen_pt or (1580, 1223),
            "talk_btn_pixel": self.calibrated_talk_button_screen_pt or (1326, 1182),
            "audio_input_device": "Not detected",
            "audio_output_device": "Not detected",
            "audio_live_peak": 0,
            "speech_recognition_installed": False,
            "whisperx_installed": False,
            "gpu_name": "CPU Fallback",
            "gpu_backend": "CPU",
            "gpu_cuda_available": False,
            "gpu_directml_available": False,
            "gpu_rocm_available": False,
            "edge_tts_installed": False,
            "sounddevice_installed": False,
            "coqui_xtts_available": False,
        }

        # Unified Multi-Backend GPU Detection (AMD first, then NVIDIA, then CPU fallback).
        # Reuses the shared resolver so WhisperX, XTTS, and diagnostics all agree on the device.
        dev = resolve_compute_device()
        report["gpu_backend"] = dev.get("backend", "cpu")
        report["gpu_name"] = dev.get("name", "CPU Fallback")
        report["gpu_directml_available"] = dev.get("backend") == "amd-directml"
        report["gpu_rocm_available"] = dev.get("backend") == "amd-rocm"
        report["gpu_cuda_available"] = dev.get("backend") == "nvidia-cuda"
        report["coqui_xtts_available"] = self.coqui.is_available()
        if not dev.get("gpu"):
            report["gpu_backend"] = "CPU (SIMD AVX)"
            report["gpu_name"] = "CPU Multi-threaded Fallback"

        try:
            import whisperx  # noqa: F401
            report["whisperx_installed"] = True
        except Exception:
            try:
                import faster_whisper  # noqa: F401
                report["whisperx_installed"] = True
            except Exception:
                pass

        try:
            import speech_recognition  # noqa: F401
            report["speech_recognition_installed"] = True
        except Exception:
            pass

        try:
            import edge_tts  # noqa: F401
            report["edge_tts_installed"] = True
        except Exception:
            pass

        try:
            import numpy as np
            import sounddevice as sd

            report["sounddevice_installed"] = True
            devices = sd.query_devices()
            in_dev_name = "Default Input"
            in_idx = None
            out_dev_name = "Default Output"
            for kw in ("cable output", "vb-audio", "stereo mix", "what u hear", "loopback"):
                for idx, d in enumerate(devices):
                    nm = str(d.get("name", ""))
                    if kw in nm.lower() and int(d.get("max_input_channels", 0)) > 0:
                        in_idx = idx
                        in_dev_name = f"#{idx} {nm}"
                        break
                if in_idx is not None:
                    break
            if in_idx is None:
                for idx, d in enumerate(devices):
                    if int(d.get("max_input_channels", 0)) > 0:
                        in_idx = idx
                        in_dev_name = f"#{idx} {d.get('name', 'Input')}"
                        break

            for idx, d in enumerate(devices):
                nm = str(d.get("name", ""))
                if "cable input" in nm.lower() and int(d.get("max_output_channels", 0)) > 0:
                    out_dev_name = f"#{idx} {nm}"
                    break

            report["audio_input_device"] = in_dev_name
            report["audio_output_device"] = out_dev_name

            if os.name == "nt" and in_idx is not None:
                frames = sd.rec(int(0.35 * 16000), samplerate=16000, channels=1, dtype="int16", device=in_idx)
                sd.wait()
                if frames is not None and frames.size > 0:
                    report["audio_live_peak"] = int(np.max(np.abs(frames.astype(np.int32))))
        except Exception as aud_exc:
            report["audio_input_device"] = f"Audio probe note: {aud_exc}"

        connected = self.is_connected() or self.connect_to_camfrog()
        report["connected"] = bool(connected)
        report["hwnd"] = self._hwnd
        if connected:
            try:
                report["window_title"] = str(self.window.window_text() or "") if self.window else ""
            except Exception:
                pass
            report["window_rect"] = self._get_window_rect()
            try:
                self.nodes(refresh=True)
                ev = self.get_chat_events()
                report["chat_events_visible"] = len(ev)
                if ev:
                    last_e = ev[-1]
                    report["sample_chat_line"] = f"{last_e.get('user', '')}: {last_e.get('text', last_e.get('action', ''))}"
                users = self.get_user_list()
                report["user_list_count"] = len(users)
                report["sample_users"] = users[:6]
                report["active_speaker"] = self.get_active_speaker(refresh=False)
            except Exception:
                pass

        return report

    def switch_to_room_by_position(self, x: int, y: int) -> bool:
        room_name = self.find_room_by_position(x, y)
        if not room_name:
            self.last_error = f"No room found at position ({x}, {y})"
            return False
        if uia_click is not None:
            try:
                uia_click(coords=(x, y))
                time.sleep(0.4)
                return True
            except Exception as error:
                self.last_error = f"Failed to click tab at ({x}, {y}): {error}"
                return False
        return True

