// Auto-synchronized local Python files for C:\Users\newbe\AIBot

export const FIXED_CONFIG_PY = `"""Runtime configuration for the UI-Automation Camfrog bot with VB-Cable TTS."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
SUPPRESSED_DATA_DIR = DATA_DIR / "suppressed"
DATABASE_PATH = DATA_DIR / "camfrog_bot.db"

CAPTURE_BACKEND = "uia"
OCR_ENABLED = False
DXCAM_ENABLED = False
TESSERACT_ENABLED = False
IMAGE_CAPTURE_ENABLED = False

# Window title can change dynamically when room topic changes.
CAMFROG_WINDOW_TITLE_RE = r"(?i).*(Players__Lounge|Drama_Central|Camfrog|Video Chat Room).*"
POLL_INTERVAL_SECONDS = 0.35
UIA_CACHE_SECONDS = 0.15
MAX_CHAT_MESSAGE_LENGTH = 425
CHAT_HISTORY_LIMIT = 10

# Fixed tab click coordinates (x, y) and bounding boxes [left, top, right, bottom]
ROOM_TAB_CLICK_POINTS = {
    "Room List": (1390, 50),
    "Players__Lounge": (1550, 50),
}

ROOM_TAB_POSITIONS = {
    "Room List": [1313, 37, 1473, 71],
    "Players__Lounge": [1473, 37, 1633, 71],
    "Drama_Central": [1633, 37, 1793, 71],
}

# Exact calibrated BoundingRectangles [left, top, right, bottom] for newer Camfrog UIA
# 1. Chat Window (to pull users' text and catch moderation events)
CHAT_WINDOW_RECT = (1281, 170, 2355, 1160)      # ControlType Pane(50033), IsKeyboardFocusable=True
CHAT_TEXT_RECT = (1281, 170, 2355, 1160)        # ControlType Text(50020), IsKeyboardFocusable=False

# 2. Chat Txt Field (for the bot to input text to send communications to the chatroom)
CHAT_INPUT_RECT = (1396, 1206, 2497, 1241)      # ControlType Pane(50033), IsKeyboardFocusable=False

# 3. User List (watched on startup for initial roster, then Join:/Quit: in Chat Window tracks duration)
USER_LIST_RECT = (2359, 141, 2559, 1160)        # ControlType List(50008), IsKeyboardFocusable=True
USER_LIST_ITEM_X_SPAN = (2359, 2559)            # Trending [l=2359, r=2559] for list items up/down the list
MAX_ROOM_USERS = 100                            # Never more than 100 people in a chatroom

# 4. Talk Button (2 quick clicks + hold to transmit audio, then release button to finish broadcast)
TALK_BUTTON_RECT = (1291, 1169, 1361, 1195)     # ControlType Button(50000), IsKeyboardFocusable=True
TALK_DOUBLE_CLICK_DELAY = 0.06

# 5. Active Speaker on Microphone (flows current speaker name; disappears/erases when mic is free)
# Broadcasting must not start until BOT_USERNAME ("KaeKae_Toad") persists here for 1.3 seconds.
ACTIVE_SPEAKER_RECT = (1506, 1174, 1548, 1190)  # ControlType Button(50000), IsKeyboardFocusable=True
BOT_USERNAME = "KaeKae_Toad"
MIC_CONFIRM_PERSIST_SECONDS = 1.3

# 6. Top Gifters / Combined Text Overlay (above Chat visually; ignored unless fallback text is needed)
TOP_GIFTERS_RECT = (1281, 71, 2559, 1160)       # ControlType Text(50020), IsKeyboardFocusable=False

# Legacy ignored rects kept for backwards compatibility alongside dynamic VIEWING # / LURKERS # filtering
IGNORED_USER_LIST_RECTS = {
    (2303, 141, 2559, 163),
    (2303, 207, 2559, 229),
    (2303, 867, 2559, 889),
}

# VB-Cable configuration (already installed on host machine)
VB_CABLE_PLAYBACK_DEVICE = "CABLE Input"   # Matches "CABLE Input (VB-Audio Virtual Cable)"
VB_CABLE_RECORDING_DEVICE = "CABLE Output" # Matches "CABLE Output (VB-Audio Virtual Cable)"
VB_CABLE_TTS_ENABLED = True

BOT_SETTINGS = {
    "chat_mode": False,
    "silent_mode": False,
    "transcription_mode": True,
    "running": True,
}

MODERATION_ALLOWED_SENDERS: set[str] = set()
NATIVE_MODERATION_COMMANDS = {"unpunish", "unblockmic", "unban", "topic", "watchlist"}

TRIGGER_NAMES = (
    "kaekae", "!chat", "!chatoff", "!shutup", "!transcribe", "!transcribed",
    "!suppress", "!unsuppress", "!say", "!diss", "!who is", "!info on",
    "!grabs", "-", "!idk", "who kicked/blocked/banned/punished", "!happy",
    "!sad", "!mad", "!triggers",
)
`;

export const FIXED_UI_AUTOMATION_PY = `"""Camfrog UI Automation adapter with Desktop window enumeration, calibrated rectangles, and VB-Cable TTS."""

from __future__ import annotations

import difflib
import os
import re
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from config import (
    ACTIVE_SPEAKER_RECT,
    BOT_USERNAME,
    CAMFROG_WINDOW_TITLE_RE,
    CHAT_INPUT_RECT,
    CHAT_TEXT_RECT,
    CHAT_WINDOW_RECT,
    IGNORED_USER_LIST_RECTS,
    MAX_ROOM_USERS,
    MIC_CONFIRM_PERSIST_SECONDS,
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


_CLOCK_RE = re.compile(r"^\\d{1,2}:\\d{2}(?::\\d{2})?\\s*(?:AM|PM)?$", re.I)
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32}$")
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
    r"(?<![A-Za-z_])users\\s*(?:\\(\\s*(\\d{1,3})\\s*\\)|:\\s*(\\d{1,3})|\\[\\s*(\\d{1,3})\\s*\\]|\\s+(\\d{1,3})\\b)",
    re.IGNORECASE,
)
_SECTION_COUNT_RE = re.compile(
    r"(?:(?P<section>you\\s*are\\s*viewing|(?:vie)?wing|(?:mem|em|m)?bers|(?:lur|r)?kers?)\\s*[:(\\[\\-]*\\s*(?P<count>\\d{1,3})\\s*[)\\]]?)",
    re.IGNORECASE,
)

# Dynamic section headers in User List [l=2359, r=2559] such as "YOU ARE VIEWING 0", "MEMBERS 16", "LURKERS 14", "Users (30)"
_USER_LIST_HEADER_RE = re.compile(
    r"^\\s*[^A-Za-z0-9_]*(?:"
    r"you\\s*are\\s*viewing(?:\\s*[:(\\[\\-]*\\s*\\d+\\s*[)\\]]?)?|"
    r"youareviewing\\d*|"
    r"(?:vie)?wing(?:\\s*[:(\\[\\-]*\\s*\\d+\\s*[)\\]]?)?|"
    r"(?:lur|r)?kers?(?:\\s*[:(\\[\\-]*\\s*\\d+\\s*[)\\]]?)?|"
    r"users(?:\\s*[:(\\[\\-]*\\s*\\d+\\s*[)\\]]?)?|"
    r"(?:mem|em|m)?bers(?:\\s*[:(\\[\\-]*\\s*\\d+\\s*[)\\]]?)?|"
    r"friends?(?:\\s*[:(\\[\\-]*\\s*\\d+\\s*[)\\]]?)?|"
    r"top\\s*gifters?(?:\\s*[:(\\[\\-]*\\s*\\d+\\s*[)\\]]?)?|"
    r"gift\\s*users?\\s*\\d*"
    r")\\s*$",
    re.IGNORECASE,
)

_MOD_LINE_RE = re.compile(
    r"^\\s*(?:(?P<actor>[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32})\\s+(?:was\\s+)?"
    r"(?P<action>unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\\s+"
    r"(?P<target>[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32})(?:\\s+microphone)?|"
    r"(?P<target2>[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32})\\s+was\\s+"
    r"(?P<action2>unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\\s+by\\s+"
    r"(?P<actor2>[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32}))\\s*[.!]?\\s*$",
    re.IGNORECASE,
)

_INLINE_CHAT_RE = re.compile(
    r"^\\s*(?:\\[?(?P<ts1>\\d{1,2}:\\d{2}(?::\\d{2})?\\s*(?:AM|PM)?)\\]?\\s+)?"
    r"(?P<user>[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32})"
    r"(?:\\s+\\(?\\[?(?P<ts2>\\d{1,2}:\\d{2}(?::\\d{2})?\\s*(?:AM|PM)?)\\]?\\)?)?"
    r"(?:\\s+says)?\\s*:\\s*(?P<body>.+?)\\s*$",
    re.IGNORECASE,
)

# Multi-event Join: / Quit: parser for DataItem(50029) rows at [l=1332, r=2330]
# e.g. "Quit: phoenixrising Quit: liketosquirt Join: ward1dp"
_MULTI_PRESENCE_PAIR_RE = re.compile(
    r"\\b(?P<kw>join|quit|left)\\s*:\\s*[^A-Za-z0-9_$.\\-\\[\\]@~^]*(?P<user>[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32})",
    re.IGNORECASE,
)

# Allows optional punctuation/quotes around the username such as "Quit: 'Katty"
_INLINE_PRESENCE_RE = re.compile(
    r"^\\s*(?:(?P<kw>join|quit|left)\\s*:\\s*[^A-Za-z0-9_$.\\-\\[\\]@~^]*(?P<user1>[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32})|"
    r"[^A-Za-z0-9_$.\\-\\[\\]@~^]*(?P<user2>[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32})\\s+(?:has\\s+)?(?P<verb>joined|left|quit|entered)(?:\\s+the\\s+room)?)\\s*[.!'""]*\\s*$",
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
    if "_" not in lower and re.search(r"\\b(?:viewing|lurkers?|users|members)\\s*[:(\\[\\-]*\\s*\\d+", lower):
        return True
    compact = re.sub(r"[^a-z0-9]", "", lower)
    if (
        compact.startswith("youareviewing")
        or compact.startswith("viewing")
        or compact.startswith("lurkers")
        or compact.startswith("giftusers")
        or compact.startswith("topgifters")
        or compact in {"pageleft", "pageright", "pageup", "pagedown", "lineup", "linedown"}
        or ("_" not in lower and re.fullmatch(r"(?:users|members)\\d+", compact))
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
    if _CLOCK_RE.fullmatch(raw) or re.fullmatch(r"\\d{3,4}(?:AM|PM)", raw, re.I):
        return ""
    if is_user_list_header(raw):
        return ""
    raw = re.sub(r"^\\s*(?:speaking|on\\s*mic|mic|user|join|quit|left)\\s*:\\s*", "", raw, flags=re.I).strip()
    if is_user_list_header(raw):
        return ""

    # Evaluate tokens: if OCR read a 1-2 char icon glyph before the username (e.g. "o Stonerwayne1000"),
    # pick the best valid username token rather than blindly taking token[0].
    tokens = [t.lstrip("@'\\"").rstrip(":'\\",.") for t in raw.split() if t.strip()]
    if not tokens:
        return ""

    valid_candidates: list[str] = []
    for tok in tokens:
        cleaned_tok = re.sub(r"[^A-Za-z0-9_$.\\-\\[\\]~^]", "", tok)[:32]
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


class CamfrogUIAutomation:
    """Connect to a live Camfrog room regardless of dynamic room topic title changes."""

    def __init__(self, title_re: str = CAMFROG_WINDOW_TITLE_RE, cache_seconds: float = UIA_CACHE_SECONDS):
        self.title_re = title_re
        self.cache_seconds = cache_seconds
        self.app: Any = None
        self.window: Any = None
        self._nodes: list[UIANode] = []
        self._nodes_at = 0.0
        self._ocr_speaker_cache: tuple[tuple[int, int, int, int], float, str] | None = None
        self._ocr_userlist_cache: tuple[float, int | None, list[str]] | None = None
        self._known_users: set[str] = {BOT_USERNAME}
        self.last_error = ""

    def connect_to_camfrog(self) -> bool:
        """Attach specifically to the Camfrog room window [1273, 0, 2567, 1399] (never IDE/browser windows)."""
        if Application is None or Desktop is None:
            self.last_error = "pywinauto is not installed; run setup_bot.py in .venv."
            return False

        try:
            all_windows = Desktop(backend="uia").windows()
            title_pattern = re.compile(self.title_re)
            best_win = None
            best_score = -1

            non_camfrog_keywords = (
                "visual studio", "vscode", "code -", "command prompt", "powershell",
                "windows terminal", "google chrome", "microsoft edge", "firefox",
                "file explorer", "task manager", "notepad",
            )

            for win in all_windows:
                try:
                    rect = win.rectangle()
                    if rect.width() < 400 or rect.height() < 300:
                        continue
                    title = win.window_text() or ""
                    title_lower = title.lower()
                    cls_name = (win.class_name() or "").lower()

                    if any(kw in title_lower for kw in non_camfrog_keywords):
                        continue

                    score = 0
                    if title_pattern.search(title) or "camfrog" in title_lower or "camfrog" in cls_name:
                        score += 2500

                    # Exact calibrated Camfrog window bounds [1273, 0, 2567, 1399]
                    if abs(rect.left - 1273) <= 45 and abs(rect.right - 2567) <= 45:
                        score += 3500
                    elif rect.left <= 1291 and rect.right >= 2550 and rect.width() <= 2700:
                        score += 800

                    cbutton_count = len(win.descendants(class_name="CButtonTS"))
                    if cbutton_count > 0:
                        score += 5000 + cbutton_count * 120

                    # Penalize multi-monitor fullscreen wrapper windows (e.g. [0, 0, 3640, 1920]) that have no CButtonTS
                    if rect.width() > 2800 and cbutton_count == 0:
                        continue

                    if score > best_score:
                        best_score = score
                        best_win = win
                except Exception:
                    continue

            if best_win is None or best_score <= 0:
                self.last_error = "Could not find an open Camfrog room window on the desktop."
                return False

            self.app = Application(backend="uia").connect(handle=best_win.handle)
            self.window = self.app.window(handle=best_win.handle)
            self._nodes = []
            self._nodes_at = 0.0
            self.last_error = ""
            return True

        except Exception as error:
            self.app = None
            self.window = None
            self.last_error = f"Camfrog UIA connection failed: {error}"
            return False

    def is_connected(self) -> bool:
        try:
            if self.window is None or not bool(self.window.exists(timeout=0)):
                return False
            rect = self.window.rectangle()
            # Reconnect if attached to a fullscreen non-Camfrog window (>2800px wide)
            if rect.width() > 2800:
                return False
            return True
        except Exception:
            return False

    @staticmethod
    def _extract_control_text(control: Any, info: Any) -> str:
        """Fast COM text extraction: return immediately on info.name, only query legacy patterns for empty controls."""
        try:
            direct = info.name
            if direct and isinstance(direct, str) and direct.strip():
                return direct.strip()
        except Exception:
            pass
        try:
            rt = getattr(info, "rich_text", "")
            if rt and isinstance(rt, str) and rt.strip():
                return rt.strip()
        except Exception:
            pass
        for getter in (
            lambda: getattr(control.iface_legacy_iaccessible, "CurrentName", ""),
            lambda: getattr(control.iface_legacy_iaccessible, "CurrentValue", ""),
            lambda: getattr(control.iface_value, "CurrentValue", ""),
        ):
            try:
                val = getter()
                if val and isinstance(val, str) and val.strip():
                    return val.strip()
            except Exception:
                continue
        return ""

    @staticmethod
    def _ocr_screen_rect(left: int, top: int, right: int, bottom: int, scale: int = 3) -> list[str]:
        """Use built-in Windows 10/11 WinRT OCR (Windows.Media.Ocr) with white border padding for small UI text."""
        if os.name != "nt":
            return []
        w = max(16, int(right - left))
        h = max(12, int(bottom - top))
        scale = max(1, min(4, int(scale)))
        pad = 16
        ps_script = f"""
$ErrorActionPreference = 'Stop'
try {{
    Add-Type -AssemblyName System.Drawing
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
    $null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]

    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation\`1'
    }})[0]
    function Await($WinRtTask, $ResultType) {{
        $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
        $netTask = $asTask.Invoke($null, @($WinRtTask))
        $netTask.Wait(4000) | Out-Null
        return $netTask.Result
    }}

    $bmp = New-Object System.Drawing.Bitmap({w}, {h})
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen({int(left)}, {int(top)}, 0, 0, $bmp.Size)
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
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
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
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=4.5,
                check=False,
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

    def _node_from_control(self, control: Any) -> UIANode | None:
        try:
            info = control.element_info
            rect = control.rectangle()
            text = self._extract_control_text(control, info)
            return UIANode(
                control_type=(info.control_type or ""),
                name=text,
                class_name=(info.class_name or ""),
                left=int(rect.left),
                top=int(rect.top),
                right=int(rect.right),
                bottom=int(rect.bottom),
                control=control,
            )
        except Exception:
            return None

    def nodes(self, refresh: bool = False) -> list[UIANode]:
        if not self.is_connected() and not self.connect_to_camfrog():
            return []
        if not refresh and time.monotonic() - self._nodes_at < self.cache_seconds:
            return list(self._nodes)
        try:
            found: list[UIANode] = []
            for control in self.window.descendants():
                node = self._node_from_control(control)
                if node is not None:
                    found.append(node)
            self._nodes = found
            self._nodes_at = time.monotonic()
            return list(found)
        except Exception as error:
            self.last_error = f"Camfrog UIA tree read failed: {error}"
            self.window = None
            return []

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
        """Locate Chat Txt Field Pane(50033) at [l=1396,t=1206,r=2497,b=1241] (IsKeyboardFocusable=False)."""
        il, it, ir, ib = CHAT_INPUT_RECT
        node_list = list(nodes)
        calibrated = [
            node for node in node_list
            if node.control_type in {"Pane", "Edit", "Document", "Custom", "Text"}
            and abs(node.left - il) <= 25
            and abs(node.top - it) <= 25
            and abs(node.right - ir) <= 35
            and abs(node.bottom - ib) <= 25
        ]
        if calibrated:
            return min(calibrated, key=lambda n: abs(n.left - il) + abs(n.top - it))

        bounds = self._window_rect()
        if bounds is not None:
            _, top, _, bottom = bounds
            edits = [node for node in node_list if node.control_type == "Edit" and node.top >= top + (bottom - top) * 0.55]
            if edits:
                return max(edits, key=lambda node: node.width * node.height)
        return None

    @staticmethod
    def _find_active_speaker_node(nodes: Iterable[UIANode]) -> UIANode | None:
        """Locate the Active Microphone Speaker Button(50000) at [l=1506,t=1174,r=...,b=1190].

        In Camfrog, when someone is on the mic, a Button(50000) appears at l=1506, t=1174, b=1190
        (e.g. [1506, 1174, 1548, 1190] or [1506, 1174, 1607, 1190]) along with an indicator Pane at
        [1478, 1174, 1482, 1190]. When the mic is free, that Button(50000) erases from the UIA tree.
        """
        sl, st, sr, sb = ACTIVE_SPEAKER_RECT  # (1506, 1174, 1548, 1190)
        tl, tt, tr, tb = TALK_BUTTON_RECT     # (1291, 1169, 1361, 1195)
        node_list = list(nodes)

        # 1. Primary: Button(50000) at [l≈1506, t≈1174, b≈1190] (exclude the 4px indicator Pane at 1478..1482)
        primary = [
            node for node in node_list
            if node.control_type in {"Button", "Text", "Custom", "Hyperlink", "Static"}
            and abs(node.left - sl) <= 25
            and abs(node.top - st) <= 16
            and abs(node.bottom - sb) <= 16
            and node.width >= 12
            and node.height <= 36
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
            and abs(node.top - st) <= 20
            and abs(node.bottom - sb) <= 20
            and 1485 <= node.left <= 2100
        ]
        return min(fallback, key=lambda n: abs(n.left - sl)) if fallback else None

    def get_active_speaker(self, refresh: bool = False) -> str | None:
        """Read the active speaker username at [l=1506,t=1174,r=...,b=1190].

        Returns None ONLY when the active-speaker Button(50000) at [1506,1174,...,1190] is absent/erased.
        When present, resolves the username via UIA Name, sibling Text nodes, or Windows OCR on the button rect.
        """
        node_list = self.nodes(refresh=refresh)
        node = self._find_active_speaker_node(node_list)
        if node is None:
            self._ocr_speaker_cache = None
            return None

        # 1. Direct UIA / LegacyIAccessible text on the active speaker node
        cleaned = clean_username(node.name, node.rect_tuple)
        if cleaned:
            matched = self._match_known_username(cleaned)
            self._known_users.add(matched)
            return matched

        # 2. Check any sibling Text/Button overlapping the speaker button [l=1490..2100, t=1164..1198]
        sl, st, sr, sb = ACTIVE_SPEAKER_RECT
        for sib in node_list:
            if (
                sib.name
                and 1490 <= sib.left <= 2100
                and abs(sib.top - st) <= 18
                and abs(sib.bottom - sb) <= 18
            ):
                sib_user = clean_username(sib.name, sib.rect_tuple)
                if sib_user:
                    matched = self._match_known_username(sib_user)
                    self._known_users.add(matched)
                    return matched

        # 3. Cached Windows screen OCR on the exact speaker Button(50000) rectangle [1506, 1174, node.right, 1190]
        rect_key = node.rect_tuple
        now = time.monotonic()
        if (
            self._ocr_speaker_cache is not None
            and self._ocr_speaker_cache[0] == rect_key
            and now - self._ocr_speaker_cache[1] < 3.5
        ):
            return self._ocr_speaker_cache[2]

        ocr_left = max(1502, node.left - 3)
        ocr_top = max(1168, node.top - 4)
        ocr_right = max(ocr_left + 45, node.right + 8)
        ocr_bottom = min(1198, node.bottom + 4)
        ocr_lines = self._ocr_screen_rect(ocr_left, ocr_top, ocr_right, ocr_bottom, scale=3)
        for line in ocr_lines:
            # Join any spaces OCR inserted inside an underscored username (e.g. "KaeKae _ Toad" -> "KaeKae_Toad")
            compact_line = re.sub(r"\\s*_\\s*", "_", line.strip())
            candidate = clean_username(compact_line)
            if candidate:
                matched = self._match_known_username(candidate)
                self._ocr_speaker_cache = (rect_key, now, matched)
                return matched

        fallback_label = f"Speaker_On_Mic[{node.left},{node.top},{node.right},{node.bottom}]"
        self._ocr_speaker_cache = (rect_key, now, fallback_label)
        return fallback_label

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
            stripped_lvl = re.sub(r"^\\s*\\d{1,2}\\s+", "", line)
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
        _, users = self._scan_users_header_and_list_from_uia(all_nodes)
        if len(users) <= 1 and self._ocr_userlist_cache is None:
            _, ocr_users = self._get_ocr_userlist_fallback()
            if len(ocr_users) > len(users):
                users = ocr_users
        elif len(users) <= 1 and self._ocr_userlist_cache is not None:
            users = list(self._ocr_userlist_cache[2])
        return users

    def get_user_count(self, refresh: bool = False) -> int:
        """Return the room user count rapidly by summing the 3 section headers (YOU ARE VIEWING # + MEMBERS # + LURKERS #),
        reading 'Users (#)', or counting list rows minus the 3 headers.
        """
        all_nodes = self.nodes(refresh=refresh)
        header_count, users = self._scan_users_header_and_list_from_uia(all_nodes)
        if header_count is not None and header_count > len(users):
            return min(MAX_ROOM_USERS, header_count)
        if len(users) >= 2:
            return min(MAX_ROOM_USERS, len(users))
        ocr_count, ocr_users = self._get_ocr_userlist_fallback(header_only=True)
        best = max(header_count or 0, ocr_count or 0, len(users), len(ocr_users))
        return min(MAX_ROOM_USERS, best)

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
            if multi_matches and re.match(r"^\\s*(?:join|quit|left)\\s*:", name, re.I):
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
        """Parse chat & moderation events from Chat Window Pane(50033)/Text(50020) [l=1281,t=170,r=2355,b=1160]."""
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
            and node.bottom <= cb + 15
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
        seen: set[tuple[str, str, str, str]] = set()
        for event in events:
            if event.get("user"):
                self._known_users.add(event["user"])
            key = (event["kind"], event.get("action", ""), event["user"].lower(), event["text"])
            if key not in seen:
                seen.add(key)
                unique.append(event)
        return unique[-limit:]

    def send_chat_message(self, message: str, dry_run: bool = False) -> bool:
        """Send text into Chat Txt Field Pane(50033) [l=1396,t=1206,r=2497,b=1241] (IsKeyboardFocusable=False)."""
        if dry_run:
            return True
        cleaned = str(message or "").strip()
        if not cleaned:
            return False

        node = self._find_chat_input(self.nodes(refresh=False))
        il, it, ir, ib = self._rect(node) or CHAT_INPUT_RECT
        cx, cy = (il + ir) // 2, (it + ib) // 2  # (1946, 1223)

        try:
            # 1. Click inside the Chat Txt Field Pane(50033) at (1946, 1223) so CEF/Qt activates the text input cursor
            if uia_click is not None:
                uia_click(coords=(cx, cy))
                time.sleep(0.06)

            # 2. Only call set_edit_text if the control is a native Win32/UIA Edit box
            if node is not None and node.control_type == "Edit" and node.control is not None:
                try:
                    node.control.set_edit_text(cleaned)
                    if uia_send_keys is not None:
                        uia_send_keys("{ENTER}", pause=0.01)
                    else:
                        node.control.type_keys("{ENTER}", set_foreground=False)
                    return True
                except Exception:
                    pass

            # 3. For Camfrog's Pane(50033) chat input [1396,1206,2497,1241], send keystrokes directly after clicking
            if uia_send_keys is not None:
                escaped = re.sub(r"([+^%~(){}])", r"{\\1}", cleaned)
                uia_send_keys(escaped, with_spaces=True, pause=0.005)
                uia_send_keys("{ENTER}", pause=0.01)
                return True

            if node is not None and node.control is not None:
                node.control.type_keys(cleaned, with_spaces=True, set_foreground=False)
                node.control.type_keys("{ENTER}", set_foreground=False)
                return True

            self.last_error = "Camfrog chat input could not receive keystrokes."
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
            time.sleep(0.12)
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
            time.sleep(0.05)
        return False

    def broadcast_tts_via_vbcable(self, text: str, dry_run: bool = False) -> bool:
        """Broadcast speech over VB-Cable ('CABLE Input') using Talk Button [l=1291,t=1169,r=1361,b=1195]."""
        cleaned_text = str(text or "").strip()
        if not cleaned_text or not VB_CABLE_TTS_ENABLED:
            return False
        if dry_run:
            return True

        if not self._wait_until_mic_free(timeout_seconds=12.0):
            active = self.get_active_speaker(refresh=True)
            self.last_error = f"Cannot click Talk Button: '{active}' is currently on the microphone at [1506,1174,1548,1190]."
            return False

        l, t, r, b = TALK_BUTTON_RECT
        cx, cy = (l + r) // 2, (t + b) // 2  # (1326, 1182)

        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "tts_out.wav"
            ps_script = (
                "Add-Type -AssemblyName System.Speech; "
                "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$synth.SetOutputToWaveFile('{wav_path}'); "
                f"$synth.Speak({cleaned_text!r}); "
                "$synth.Dispose();"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=False)
            if not wav_path.exists():
                self.last_error = "TTS WAV synthesis failed."
                return False

            duration = 2.0
            try:
                with wave.open(str(wav_path), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    if rate > 0:
                        duration = max(0.5, frames / float(rate))
            except Exception:
                pass

            try:
                if uia_click is not None:
                    uia_click(coords=(cx, cy))
                    time.sleep(TALK_DOUBLE_CLICK_DELAY)
                    uia_click(coords=(cx, cy))
                    time.sleep(TALK_DOUBLE_CLICK_DELAY)
                if uia_press is not None:
                    uia_press(coords=(cx, cy))

                if not self._wait_for_bot_mic_persistence(
                    bot_username=BOT_USERNAME,
                    persist_seconds=MIC_CONFIRM_PERSIST_SECONDS,
                    timeout_seconds=6.0,
                ):
                    self.last_error = (
                        f"'{BOT_USERNAME}' did not persist for {MIC_CONFIRM_PERSIST_SECONDS}s "
                        f"at Active Speaker [1506,1174,1548,1190]; broadcast aborted."
                    )
                    return False

                played = self._play_wav_to_vbcable(wav_path, duration)
                if not played:
                    time.sleep(duration)
                return True
            except Exception as error:
                self.last_error = f"VB-Cable TTS broadcast failed: {error}"
                return False
            finally:
                if uia_release is not None:
                    try:
                        uia_release(coords=(cx, cy))
                    except Exception:
                        pass

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
`;

export const FIXED_CAMFROG_BOT_PY = `#!/usr/bin/env python3
"""Camfrog bot main process with calibrated UIA coordinates, VB-Cable TTS, and active-speaker tracking."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sqlite3
import time
from collections import Counter, deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from config import (
    ACTIVE_SPEAKER_RECT,
    BOT_SETTINGS,
    BOT_USERNAME,
    CHAT_HISTORY_LIMIT,
    CHAT_INPUT_RECT,
    CHAT_WINDOW_RECT,
    DATABASE_PATH,
    LOG_DIR,
    MAX_CHAT_MESSAGE_LENGTH,
    MAX_ROOM_USERS,
    MIC_CONFIRM_PERSIST_SECONDS,
    MODERATION_ALLOWED_SENDERS,
    NATIVE_MODERATION_COMMANDS,
    POLL_INTERVAL_SECONDS,
    SUPPRESSED_DATA_DIR,
    TALK_BUTTON_RECT,
    USER_LIST_RECT,
)
from ui_automation import CamfrogUIAutomation, clean_username


LOG = logging.getLogger("camfrog_bot")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")
_MOD_RE = re.compile(
    r"^\\s*(?P<actor>[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32})\\s+(?:was\\s+)?"
    r"(?P<action>unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\\s+"
    r"(?P<target>[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32})(?:\\s+microphone)?\\s*[.!]?\\s*$",
    re.IGNORECASE,
)
_MOD_BY_RE = re.compile(
    r"^\\s*(?P<target>[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32})\\s+was\\s+"
    r"(?P<action>unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\\s+by\\s+"
    r"(?P<actor>[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32})\\s*[.!]?\\s*$",
    re.IGNORECASE,
)
_HISTORY_RE = re.compile(
    r"^who\\s+(?P<action>kicked|blocked|unblocked|banned|unbanned|punished|unpunished)"
    r"\\s+(?P<target>[A-Za-z0-9_$.\\-\\[\\]@~^]{2,32})\\s*\\??$",
    re.IGNORECASE,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _seconds_between_iso(start_iso: str, end_iso: str) -> float:
    if not start_iso or not end_iso:
        return 0.0
    try:
        start_dt = datetime.fromisoformat(start_iso)
        end_dt = datetime.fromisoformat(end_iso)
        return max(0.0, (end_dt - start_dt).total_seconds())
    except Exception:
        return 0.0


def normalize_message(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def message_key(user: str, text: str, timestamp: str = "") -> str:
    source = "|".join((user.casefold(), normalize_message(text), timestamp.casefold()))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def detect_moderation(text: str) -> dict[str, str] | None:
    """Parse a complete Camfrog moderation notice; reject conversational prose."""
    for pattern in (_MOD_BY_RE, _MOD_RE):
        match = pattern.match(str(text or ""))
        if not match:
            continue
        actor = clean_username(match.group("actor"))
        target = clean_username(match.group("target"))
        if actor and target:
            return {"actor": actor, "target": target, "action": match.group("action").lower()}
    return None


class CamfrogStore:
    """SQLite persistence with a separate, non-queryable suppression vault and Join/Quit chat duration tracking."""

    def __init__(self, database_path: Path = DATABASE_PATH, suppressed_dir: Path = SUPPRESSED_DATA_DIR):
        self.database_path = Path(database_path)
        self.suppressed_dir = Path(suppressed_dir)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.suppressed_dir.mkdir(parents=True, exist_ok=True)
        self._create_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _session(self) -> Iterable[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _create_schema(self) -> None:
        with self._session() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS bot_users (
                    username TEXT PRIMARY KEY COLLATE NOCASE,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    joined_at TEXT NOT NULL DEFAULT '',
                    total_chat_seconds REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS bot_messages (
                    id INTEGER PRIMARY KEY,
                    event_key TEXT UNIQUE NOT NULL,
                    username TEXT NOT NULL,
                    body TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    room_time TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS presence_events (
                    id INTEGER PRIMARY KEY,
                    event_key TEXT UNIQUE NOT NULL,
                    username TEXT NOT NULL,
                    action TEXT NOT NULL CHECK(action IN ('join', 'quit')),
                    observed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS moderation_events (
                    id INTEGER PRIMARY KEY,
                    event_key TEXT UNIQUE NOT NULL,
                    actor TEXT NOT NULL,
                    target TEXT NOT NULL,
                    action TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    raw_text TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mic_grabs (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    duration_seconds REAL NOT NULL DEFAULT 0,
                    transcript TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS suppressed_users (
                    username TEXT PRIMARY KEY COLLATE NOCASE,
                    suppressed_at TEXT NOT NULL,
                    vault_file TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_bot_messages_user_time ON bot_messages(username, observed_at);
                CREATE INDEX IF NOT EXISTS idx_moderation_target_time ON moderation_events(target, observed_at);
                """
            )
            # Ensure existing SQLite databases gain the new columns cleanly
            for ddl in (
                "ALTER TABLE bot_users ADD COLUMN joined_at TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE bot_users ADD COLUMN total_chat_seconds REAL NOT NULL DEFAULT 0",
                "ALTER TABLE mic_grabs ADD COLUMN transcript TEXT NOT NULL DEFAULT ''",
            ):
                try:
                    db.execute(ddl)
                except sqlite3.OperationalError:
                    pass

    def is_suppressed(self, username: str) -> bool:
        with self._session() as db:
            return db.execute("SELECT 1 FROM suppressed_users WHERE username = ?", (username,)).fetchone() is not None

    def suppress(self, username: str) -> bool:
        username = clean_username(username)
        if not username or self.is_suppressed(username):
            return False
        with self._session() as db:
            user = db.execute("SELECT * FROM bot_users WHERE username = ?", (username,)).fetchone()
            messages = db.execute("SELECT * FROM bot_messages WHERE username = ? ORDER BY id", (username,)).fetchall()
            grabs = db.execute("SELECT * FROM mic_grabs WHERE username = ? ORDER BY id", (username,)).fetchall()
            payload = {
                "username": username,
                "suppressed_at": now_iso(),
                "user": dict(user) if user else None,
                "messages": [dict(row) for row in messages],
                "mic_grabs": [dict(row) for row in grabs],
            }
            vault = self.suppressed_dir / f"{username.casefold()}.json"
            vault.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            db.execute("DELETE FROM bot_messages WHERE username = ?", (username,))
            db.execute("DELETE FROM mic_grabs WHERE username = ?", (username,))
            db.execute("DELETE FROM bot_users WHERE username = ?", (username,))
            db.execute(
                "INSERT INTO suppressed_users(username, suppressed_at, vault_file) VALUES (?, ?, ?)",
                (username, payload["suppressed_at"], str(vault)),
            )
        return True

    def unsuppress(self, username: str) -> bool:
        username = clean_username(username)
        with self._session() as db:
            row = db.execute("SELECT vault_file FROM suppressed_users WHERE username = ?", (username,)).fetchone()
            if row is None:
                return False
            vault = Path(row["vault_file"])
            try:
                payload = json.loads(vault.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return False
            user = payload.get("user")
            if user:
                db.execute(
                    """INSERT OR REPLACE INTO bot_users(
                        username, first_seen, last_seen, message_count, active, joined_at, total_chat_seconds
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        user["username"],
                        user["first_seen"],
                        user["last_seen"],
                        user["message_count"],
                        user["active"],
                        user.get("joined_at", ""),
                        float(user.get("total_chat_seconds", 0.0)),
                    ),
                )
            for message in payload.get("messages", []):
                db.execute(
                    "INSERT OR IGNORE INTO bot_messages(event_key, username, body, observed_at, room_time) VALUES (?, ?, ?, ?, ?)",
                    (message["event_key"], message["username"], message["body"], message["observed_at"], message["room_time"]),
                )
            for grab in payload.get("mic_grabs", []):
                db.execute(
                    "INSERT INTO mic_grabs(username, started_at, duration_seconds, transcript) VALUES (?, ?, ?, ?)",
                    (grab["username"], grab["started_at"], grab["duration_seconds"], grab.get("transcript", "")),
                )
            db.execute("DELETE FROM suppressed_users WHERE username = ?", (username,))
        return True

    def seed_initial_users(self, usernames: Iterable[str]) -> int:
        """Seed initial room roster from User List [l=2359,t=141,r=2559,b=1160] when the bot first starts."""
        observed_at = now_iso()
        seeded = 0
        with self._session() as db:
            # Reset active=0 on all pre-existing users first so stale sessions never inflate active_user_count() into the 50s-70s
            db.execute("UPDATE bot_users SET active = 0")
            for raw in usernames:
                user = clean_username(raw)
                if not user or self.is_suppressed(user):
                    continue
                existing = db.execute(
                    "SELECT joined_at, active FROM bot_users WHERE username = ?",
                    (user,),
                ).fetchone()
                if existing is None:
                    db.execute(
                        """INSERT INTO bot_users(
                            username, first_seen, last_seen, message_count, active, joined_at, total_chat_seconds
                        ) VALUES (?, ?, ?, 0, 1, ?, 0)""",
                        (user, observed_at, observed_at, observed_at),
                    )
                else:
                    joined_at = existing["joined_at"] or observed_at
                    db.execute(
                        "UPDATE bot_users SET last_seen = ?, active = 1, joined_at = ? WHERE username = ?",
                        (observed_at, joined_at, user),
                    )
                seeded += 1
                if seeded >= MAX_ROOM_USERS:
                    break
        return seeded

    def record_message(self, username: str, body: str, room_time: str, *, mark_active: bool = True) -> None:
        username = clean_username(username)
        if not username or self.is_suppressed(username):
            return
        observed_at = now_iso()
        key = message_key(username, body, room_time)
        active_val = 1 if mark_active else 0
        joined_val = observed_at if mark_active else ""
        with self._session() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO bot_messages(event_key, username, body, observed_at, room_time) VALUES (?, ?, ?, ?, ?)",
                (key, username, body, observed_at, room_time),
            ).rowcount
            if inserted:
                if mark_active:
                    db.execute(
                        """INSERT INTO bot_users(username, first_seen, last_seen, message_count, active, joined_at, total_chat_seconds)
                        VALUES (?, ?, ?, 1, 1, ?, 0)
                        ON CONFLICT(username) DO UPDATE SET
                            last_seen=excluded.last_seen,
                            message_count=bot_users.message_count + 1,
                            active=1,
                            joined_at=CASE WHEN bot_users.joined_at = '' THEN excluded.joined_at ELSE bot_users.joined_at END""",
                        (username, observed_at, observed_at, joined_val),
                    )
                else:
                    db.execute(
                        """INSERT INTO bot_users(username, first_seen, last_seen, message_count, active, joined_at, total_chat_seconds)
                        VALUES (?, ?, ?, 1, 0, '', 0)
                        ON CONFLICT(username) DO UPDATE SET
                            last_seen=excluded.last_seen,
                            message_count=bot_users.message_count + 1""",
                        (username, observed_at, observed_at),
                    )

    def record_presence(self, username: str, action: str, event_key: str) -> None:
        """Record Join: or Quit: from the Chat Window and update the user's duration in chat."""
        username = clean_username(username)
        if not username or self.is_suppressed(username):
            return
        observed_at = now_iso()
        with self._session() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO presence_events(event_key, username, action, observed_at) VALUES (?, ?, ?, ?)",
                (event_key, username, action, observed_at),
            ).rowcount
            if not inserted:
                return
            existing = db.execute(
                "SELECT joined_at, total_chat_seconds FROM bot_users WHERE username = ?",
                (username,),
            ).fetchone()
            if action == "join":
                if existing is None:
                    db.execute(
                        """INSERT INTO bot_users(
                            username, first_seen, last_seen, message_count, active, joined_at, total_chat_seconds
                        ) VALUES (?, ?, ?, 0, 1, ?, 0)""",
                        (username, observed_at, observed_at, observed_at),
                    )
                else:
                    db.execute(
                        "UPDATE bot_users SET last_seen = ?, active = 1, joined_at = ? WHERE username = ?",
                        (observed_at, observed_at, username),
                    )
            else:  # action == "quit"
                if existing is None:
                    db.execute(
                        """INSERT INTO bot_users(
                            username, first_seen, last_seen, message_count, active, joined_at, total_chat_seconds
                        ) VALUES (?, ?, ?, 0, 0, '', 0)""",
                        (username, observed_at, observed_at),
                    )
                else:
                    elapsed = _seconds_between_iso(existing["joined_at"] or "", observed_at)
                    new_total = float(existing["total_chat_seconds"] or 0.0) + elapsed
                    db.execute(
                        "UPDATE bot_users SET last_seen = ?, active = 0, joined_at = '', total_chat_seconds = ? WHERE username = ?",
                        (observed_at, new_total, username),
                    )

    def record_moderation(self, event: dict[str, str], raw_text: str) -> None:
        key = message_key(event["actor"], f"{event['action']}:{event['target']}:{raw_text}")
        with self._session() as db:
            db.execute(
                "INSERT OR IGNORE INTO moderation_events(event_key, actor, target, action, observed_at, raw_text) VALUES (?, ?, ?, ?, ?, ?)",
                (key, event["actor"], event["target"], event["action"], now_iso(), raw_text),
            )

    def record_mic_grab(self, username: str, started_at: str, duration_seconds: float, transcript: str = "") -> None:
        username = clean_username(username)
        if not username or self.is_suppressed(username):
            return
        with self._session() as db:
            db.execute(
                "INSERT INTO mic_grabs(username, started_at, duration_seconds, transcript) VALUES (?, ?, ?, ?)",
                (username, started_at, float(duration_seconds), str(transcript or "").strip()),
            )

    def active_user_count(self) -> int:
        """Return the number of users currently marked active in the room (from Initial User List + Join: - Quit:)."""
        with self._session() as db:
            row = db.execute("SELECT COUNT(*) FROM bot_users WHERE active = 1").fetchone()
            return int(row[0]) if row else 0

    def user_chat_duration_seconds(self, username: str) -> float:
        with self._session() as db:
            row = db.execute(
                "SELECT active, joined_at, total_chat_seconds FROM bot_users WHERE username = ?",
                (username,),
            ).fetchone()
            if row is None:
                return 0.0
            total = float(row["total_chat_seconds"] or 0.0)
            if row["active"] and row["joined_at"]:
                total += _seconds_between_iso(row["joined_at"], now_iso())
            return total

    def user_profile(self, username: str) -> dict[str, object] | None:
        with self._session() as db:
            user = db.execute("SELECT * FROM bot_users WHERE username = ?", (username,)).fetchone()
            if user is None:
                return None
            messages = db.execute("SELECT body FROM bot_messages WHERE username = ? ORDER BY id DESC LIMIT 20", (username,)).fetchall()
            words = Counter(word.casefold() for row in messages for word in _WORD_RE.findall(row["body"]))
            top_word, top_count = words.most_common(1)[0] if words else ("n/a", 0)
            user_dict = dict(user)
            chat_seconds = float(user_dict.get("total_chat_seconds") or 0.0)
            if user_dict.get("active") and user_dict.get("joined_at"):
                chat_seconds += _seconds_between_iso(str(user_dict["joined_at"]), now_iso())
            return {
                **user_dict,
                "messages": [row["body"] for row in messages],
                "top_word": top_word,
                "top_count": top_count,
                "chat_duration_seconds": chat_seconds,
            }

    def mic_stats(self, username: str | None, seconds: int) -> tuple[int, float]:
        cutoff = datetime.fromtimestamp(time.time() - seconds, timezone.utc).isoformat(timespec="seconds")
        query = "SELECT COUNT(*), COALESCE(SUM(duration_seconds), 0) FROM mic_grabs WHERE started_at >= ?"
        args: tuple[object, ...] = (cutoff,)
        if username:
            query += " AND username = ?"
            args = (cutoff, username)
        with self._session() as db:
            count, duration = db.execute(query, args).fetchone()
        return int(count), float(duration)

    def moderation_history(self, action: str, target: str) -> list[sqlite3.Row]:
        with self._session() as db:
            return db.execute(
                "SELECT actor, target, action, observed_at FROM moderation_events WHERE action = ? AND target = ? COLLATE NOCASE ORDER BY id DESC LIMIT 10",
                (action, target),
            ).fetchall()


class CamfrogBot:
    """Main UIA monitor, initial roster + Join/Quit tracker, VB-Cable TTS broadcaster, and command dispatcher."""

    def __init__(self, *, dry_run: bool = False, automation: CamfrogUIAutomation | None = None, store: CamfrogStore | None = None):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=LOG_DIR / "bot.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        self.ui_automation = automation or CamfrogUIAutomation()
        self.store = store or CamfrogStore()
        self.dry_run = dry_run
        self.settings = dict(BOT_SETTINGS)
        self.running = False
        self._seen: set[str] = set()
        self._recent_messages: deque[tuple[str, str]] = deque(maxlen=CHAT_HISTORY_LIMIT)
        self._pages: dict[str, deque[str]] = {}
        self._diss_jobs: dict[str, float] = {}
        self._queued_broadcasts: deque[str] = deque()
        self._current_speaker: str | None = None
        self._speaker_started_iso: str = ""
        self._speaker_started_mono: float = 0.0
        self.initial_users: list[str] = []

    def initialize(self, *, mark_existing_seen: bool = True) -> bool:
        if not self.ui_automation.connect_to_camfrog():
            LOG.error("%s", self.ui_automation.last_error)
            return False

        # 1. Watch User List [l=2359,t=141,r=2559,b=1160] on startup to record initial room roster (filtering VIEWING # / LURKERS #)
        if hasattr(self.ui_automation, "get_user_list"):
            try:
                self.initial_users = list(self.ui_automation.get_user_list() or [])
                self.store.seed_initial_users(self.initial_users)
                LOG.info("Seeded %d initial room users from User List %s.", len(self.initial_users), USER_LIST_RECT)
            except Exception as error:
                LOG.warning("Initial user list scan failed: %s", error)

        # 2. Mark pre-existing chat scrollback as seen in continuous mode so we only dispatch on new live events,
        #    while still recording messages, Join:/Quit: presence, and moderation notices from visible scrollback!
        if mark_existing_seen:
            for event in self.ui_automation.get_chat_events():
                key = self._event_key(event)
                self._seen.add(key)
                if event.get("kind") == "presence":
                    self.store.record_presence(event.get("user", ""), event.get("action", "join"), key)
                elif event.get("kind") == "message":
                    self.store.record_message(
                        event.get("user", ""),
                        event.get("text", ""),
                        event.get("timestamp", ""),
                        mark_active=False,
                    )
                    moderation = detect_moderation(event.get("text", ""))
                    if moderation:
                        self.store.record_moderation(moderation, event.get("text", ""))

        self.running = True
        self.settings["running"] = True
        LOG.info(
            "Connected to Camfrog via UI Automation (Chat=%s, Input=%s, UserList=%s, Talk=%s, ActiveSpeaker=%s).",
            CHAT_WINDOW_RECT,
            CHAT_INPUT_RECT,
            USER_LIST_RECT,
            TALK_BUTTON_RECT,
            ACTIVE_SPEAKER_RECT,
        )
        return True

    def kill_switch(self) -> None:
        self.running = False
        self.settings["running"] = False
        LOG.warning("Kill switch requested.")

    def silent_switch(self, enabled: bool | None = None) -> bool:
        if enabled is None:
            enabled = not self.settings["silent_mode"]
        self.settings["silent_mode"] = bool(enabled)
        return self.settings["silent_mode"]

    def _event_key(self, event: dict[str, str]) -> str:
        return message_key(event.get("user", ""), f"{event.get('kind', '')}:{event.get('action', '')}:{event.get('text', '')}", event.get("timestamp", ""))

    def _track_active_speaker(self) -> None:
        """Watch Active Speaker Button(50000) [l=1506,t=1174,r=1548,b=1190] continuously.

        - Connects transcription/mic-grab tracking to the active speaker on the microphone.
        - Detects when the speaker's name disappears (or control erases from UI tree) to mark the mic free
          and dispatch any queued bot broadcasts.
        """
        speaker = None
        if hasattr(self.ui_automation, "get_active_speaker"):
            speaker = self.ui_automation.get_active_speaker()
        now_mono = time.monotonic()
        if speaker != self._current_speaker:
            if (
                self._current_speaker
                and self._speaker_started_mono > 0
                and self._current_speaker.casefold() != BOT_USERNAME.casefold()
            ):
                duration = max(0.5, now_mono - self._speaker_started_mono)
                self.store.record_mic_grab(self._current_speaker, self._speaker_started_iso, duration)
                LOG.info("Mic grab recorded: %s (%.1fs)", self._current_speaker, duration)
            self._current_speaker = speaker
            self._speaker_started_iso = now_iso() if speaker else ""
            self._speaker_started_mono = now_mono if speaker else 0.0

        # When Active Speaker [1506,1174,1548,1190] clears (nobody on mic), flush queued TTS broadcasts
        if speaker is None and self._queued_broadcasts and hasattr(self.ui_automation, "broadcast_tts_via_vbcable"):
            next_phrase = self._queued_broadcasts.popleft()
            self.ui_automation.broadcast_tts_via_vbcable(next_phrase, dry_run=self.dry_run)

    def poll_once(self) -> int:
        processed = 0
        if hasattr(self.ui_automation, "nodes"):
            self.ui_automation.nodes(refresh=True)
        self._track_active_speaker()
        for event in self.ui_automation.get_chat_events():
            key = self._event_key(event)
            if key in self._seen:
                continue
            self._seen.add(key)
            processed += 1
            if event["kind"] == "presence":
                self.store.record_presence(event["user"], event["action"], key)
                LOG.info("Presence event: %s -> %s", event["action"], event["user"])
            elif event["kind"] == "message":
                self._handle_message(event["user"], event["text"], event.get("timestamp", ""))
        self._run_scheduled_disses()
        return processed

    def _handle_message(self, sender: str, text: str, room_time: str) -> None:
        sender = clean_username(sender)
        if not sender or (self.store.is_suppressed(sender) and text.strip().casefold() != "!unsuppress"):
            return
        self.store.record_message(sender, text, room_time)
        self._recent_messages.append((sender, text))
        moderation = detect_moderation(text)
        if moderation:
            self.store.record_moderation(moderation, text)
            LOG.info("Moderation notice recorded: %s %s %s", moderation["actor"], moderation["action"], moderation["target"])
            return

        for reply in self._dispatch(sender, text):
            self.send_reply(sender, reply)

    def _dispatch(self, sender: str, text: str) -> list[str]:
        raw = text.strip()
        normalized = raw.casefold()
        if raw == "-":
            return self._next_page(sender)
        history = _HISTORY_RE.match(raw)
        if history:
            return self._history_reply(sender, history.group("action").lower(), history.group("target"))
        if normalized == "!chat":
            self.settings["chat_mode"] = True
            return ["Chat mode is on."]
        if normalized in {"!chatoff", "!chat off"}:
            self.settings["chat_mode"] = False
            self._diss_jobs.clear()
            return ["Chat mode is off."]
        if normalized == "!shutup":
            self.silent_switch(True)
            return ["Silent mode is on; I will keep monitoring without replying."]
        if normalized == "!transcribe":
            self.settings["transcription_mode"] = True
            return ["Transcription mode is on (strictly gated by active speaker at [1506,1174,1548,1190])."]
        if normalized == "!transcribed":
            self.settings["transcription_mode"] = False
            return ["Transcription is off."]
        if normalized == "!suppress":
            return ["Your stored profile was moved out of normal bot queries." if self.store.suppress(sender) else "Your profile is already suppressed."]
        if normalized == "!unsuppress":
            return ["Your stored profile was restored." if self.store.unsuppress(sender) else "No recoverable suppressed profile was found."]
        if normalized.startswith("!who is "):
            return self._who_is(raw[8:].strip())
        if normalized.startswith("!info on "):
            return self._info_on(raw[9:].strip())
        if normalized.startswith("!grabs"):
            return self._grabs(raw[6:].strip())
        if normalized.startswith("!idk "):
            question = raw[5:].strip()
            return [f"@{sender}, no answer engine is configured yet, so I cannot answer: {question[:220]}"]
        if normalized.startswith("!say"):
            phrase = raw[4:].strip()
            if not phrase:
                return ["Usage: !say <message to broadcast over VB-Cable>"]
            active_speaker = (
                self.ui_automation.get_active_speaker()
                if hasattr(self.ui_automation, "get_active_speaker")
                else None
            )
            if active_speaker and active_speaker.casefold() != BOT_USERNAME.casefold():
                self._queued_broadcasts.append(phrase)
                return [
                    f"Mic is in use by {active_speaker} at [1506,1174,1548,1190]; queued broadcast until mic clears: {phrase[:140]}"
                ]
            if hasattr(self.ui_automation, "broadcast_tts_via_vbcable"):
                ok = self.ui_automation.broadcast_tts_via_vbcable(phrase, dry_run=self.dry_run)
                if ok:
                    return [
                        f"Broadcasted via VB-Cable (2 clicks + hold on {TALK_BUTTON_RECT}, '{BOT_USERNAME}' persisted {MIC_CONFIRM_PERSIST_SECONDS}s at {ACTIVE_SPEAKER_RECT}): {phrase[:140]}"
                    ]
                return [f"VB-Cable TTS failed: {self.ui_automation.last_error}"]
            return ["VB-Cable TTS adapter unavailable."]
        if normalized.startswith("!diss"):
            target = clean_username(raw[5:].strip()) or "the room"
            self._diss_jobs[target] = time.monotonic()
            return [f"Light roast mode is on for {target}; !chatoff stops it."]
        if normalized in {"!happy", "!sad", "!mad"}:
            if not self.settings["chat_mode"]:
                return ["Turn on chat mode first with !chat."]
            self.settings["tone"] = normalized[1:]
            return [f"Tone set to {normalized[1:]}."]
        if normalized in {"!triggers", "!help"}:
            return ["Triggers: !chat, !chatoff, !shutup, !suppress, !unsuppress, !who is, !info on, !grabs, !idk, !diss, !say, moderation history, and - for next page."]
        native = re.match(r"^!(unpunish|unblockmic|unban|topic|watchlist)\\s+(.+)$", raw, re.I)
        if native:
            return self._native_moderation(sender, native.group(1).lower(), native.group(2).strip())
        if "kaekae" in normalized and self.settings["chat_mode"]:
            context = self._recent_messages[-1][1] if self._recent_messages else ""
            return [f"@{sender}, I'm here. I caught: {context[:180]}"]
        return []

    def _native_moderation(self, sender: str, action: str, argument: str) -> list[str]:
        if action not in NATIVE_MODERATION_COMMANDS:
            return []
        if sender.casefold() not in {name.casefold() for name in MODERATION_ALLOWED_SENDERS}:
            return ["Native moderation commands are disabled until an operator is added to MODERATION_ALLOWED_SENDERS."]
        return [f"/{action} {argument}".strip()]

    def _who_is(self, username: str) -> list[str]:
        username = clean_username(username)
        profile = self.store.user_profile(username)
        if not profile:
            return [f"No stored profile for {username or 'that user'}."]
        samples = profile["messages"][:3]
        sample_text = " | ".join(samples) if samples else "no saved chat yet"
        chat_mins = float(profile.get("chat_duration_seconds") or 0.0) / 60.0
        status = "in room" if profile.get("active") else "left room"
        return [
            f"{profile['username']} ({status}, {chat_mins:.1f}m in chat): seen since {profile['first_seen']}; "
            f"{profile['message_count']} messages. Recent chat: {sample_text}"
        ]

    def _info_on(self, username: str) -> list[str]:
        username = clean_username(username)
        profile = self.store.user_profile(username)
        if not profile:
            return [f"No stored statistics for {username or 'that user'}."]
        grabs, seconds = self.store.mic_stats(str(profile["username"]), 24 * 3600)
        chat_mins = float(profile.get("chat_duration_seconds") or 0.0) / 60.0
        return [
            f"{profile['username']}: {profile['message_count']} messages; room time {chat_mins:.1f}m; "
            f"top word '{profile['top_word']}' ({profile['top_count']}x); {grabs} mic grabs / {seconds:.0f}s in 24h."
        ]

    def _grabs(self, arguments: str) -> list[str]:
        parts = arguments.split()
        duration_map = {"5m": 300, "30m": 1800, "1h": 3600, "24h": 86400, "72h": 259200}
        username = None
        seconds = 86400
        for part in parts:
            if part.casefold() in duration_map:
                seconds = duration_map[part.casefold()]
            else:
                username = clean_username(part) or username
        count, duration = self.store.mic_stats(username, seconds)
        label = username or "room"
        return [f"Mic grabs for {label}: {count} grabs, {duration:.0f}s over the last {seconds // 60} minutes."]

    def _history_reply(self, requester: str, action: str, target: str) -> list[str]:
        target = clean_username(target)
        if not target:
            return []
        rows = self.store.moderation_history(action, target)
        if not rows:
            return [f"No {action} record for {target}."]
        lines = [f"{row['observed_at']}: {row['actor']} {row['action']} {row['target']}" for row in rows]
        return self._paginate(f"Moderation history for {target}", lines, requester)

    def _paginate(self, title: str, lines: Iterable[str], recipient: str) -> list[str]:
        pages: list[str] = []
        current = title
        for line in lines:
            candidate = f"{current}\\n{line}"
            if len(candidate) > MAX_CHAT_MESSAGE_LENGTH and current != title:
                pages.append(current)
                current = f"{title}\\n{line}"
            else:
                current = candidate
        pages.append(current)
        self._pages[recipient.casefold()] = deque(pages[1:])
        return pages[:1]

    def _next_page(self, sender: str) -> list[str]:
        pages = self._pages.get(sender.casefold())
        if not pages:
            return ["No queued page for you."]
        next_message = pages.popleft()
        if not pages:
            self._pages.pop(sender.casefold(), None)
        return [next_message]

    def _run_scheduled_disses(self) -> None:
        if not self.settings.get("chat_mode") or self.settings.get("silent_mode"):
            return
        now = time.monotonic()
        roasts = (
            "Your comeback is still loading, but the confidence arrived early.",
            "That take needs a software update and a snack break.",
            "Respectfully, the room has heard stronger opinions from a loading spinner.",
        )
        for target, due in list(self._diss_jobs.items()):
            if now >= due:
                self.send_reply(target, f"{target}: {roasts[int(now) % len(roasts)]}")
                self._diss_jobs[target] = now + 60

    def send_reply(self, recipient: str, message: str) -> bool:
        if self.settings["silent_mode"]:
            LOG.info("Silent mode suppressed reply to %s: %s", recipient, message)
            return False
        sent = True
        for page in self._split_for_chat(message):
            if self.dry_run:
                LOG.info("DRY RUN reply to %s: %s", recipient, page)
                print(f"[dry-run -> {recipient}] {page}")
            else:
                sent = self.ui_automation.send_chat_message(page) and sent
                if not sent:
                    LOG.error("%s", self.ui_automation.last_error)
                    break
        return sent

    @staticmethod
    def _split_for_chat(message: str) -> list[str]:
        text = str(message).strip()
        return [text[index:index + MAX_CHAT_MESSAGE_LENGTH] for index in range(0, len(text), MAX_CHAT_MESSAGE_LENGTH)] or [""]

    def run(self, interval: float = POLL_INTERVAL_SECONDS) -> None:
        if not self.running and not self.initialize():
            raise RuntimeError(self.ui_automation.last_error)
        user_count = (
            self.ui_automation.get_user_count()
            if hasattr(self.ui_automation, "get_user_count")
            else len(self.initial_users)
        )
        print(
            f"Camfrog bot running (USERS (#): {user_count} | Roster seeded: {len(self.initial_users)} from {USER_LIST_RECT}). "
            f"Watching Chat {CHAT_WINDOW_RECT}, Input {CHAT_INPUT_RECT}, Talk {TALK_BUTTON_RECT}, "
            f"Active Speaker {ACTIVE_SPEAKER_RECT} ('{BOT_USERNAME}' {MIC_CONFIRM_PERSIST_SECONDS}s gate). "
            "Press Ctrl+C to stop."
        )
        while self.running:
            self.poll_once()
            time.sleep(max(0.1, interval))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Camfrog UI Automation bot (with VB-Cable TTS)")
    parser.add_argument("--dry-run", action="store_true", help="Read/process UIA text but print replies instead of sending them.")
    parser.add_argument("--once", action="store_true", help="Connect and execute one full scan (including visible scrollback).")
    parser.add_argument("--interval", type=float, default=POLL_INTERVAL_SECONDS, help="Polling interval in seconds.")
    parser.add_argument("--locations", action="store_true", help="Print the live UIA-derived locations and exit.")
    parser.add_argument("--inspect", action="store_true", help="Print diagnostic UIA nodes inside all calibrated regions and exit.")
    args = parser.parse_args(argv)
    bot = CamfrogBot(dry_run=args.dry_run)
    if not bot.initialize(mark_existing_seen=not args.once):
        print(bot.ui_automation.last_error)
        return 1
    if args.locations:
        print(json.dumps(bot.ui_automation.layout_locations(), indent=2))
        return 0
    if args.inspect:
        if hasattr(bot.ui_automation, "inspect_calibrated_regions"):
            print(json.dumps(bot.ui_automation.inspect_calibrated_regions(refresh=True), indent=2))
        return 0
    if args.once:
        speaker = bot.ui_automation.get_active_speaker() if hasattr(bot.ui_automation, "get_active_speaker") else None
        user_count = (
            bot.ui_automation.get_user_count()
            if hasattr(bot.ui_automation, "get_user_count")
            else len(bot.initial_users)
        )
        print(
            f"Room User Count ('USERS (#)'): {user_count} | Listed Usernames [l=2359,r=2559]: {len(bot.initial_users)} "
            f"{bot.initial_users[:15]}"
        )
        print(f"Active Speaker [1506,1174,1548,1190]: {speaker or 'None (mic free / erased)'}")
        count = bot.poll_once()
        print(f"Processed {count} UIA chat/presence event(s) from Chat Window {CHAT_WINDOW_RECT}.")
        if count == 0 and hasattr(bot.ui_automation, "inspect_calibrated_regions"):
            print("Diagnostic region snapshot:")
            print(json.dumps(bot.ui_automation.inspect_calibrated_regions(refresh=False), indent=2))
        return 0
    try:
        bot.run(args.interval)
    except KeyboardInterrupt:
        bot.kill_switch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
`;

export const FIXED_ROOM_MONITOR_PY = `#!/usr/bin/env python3
"""
Second terminal script to monitor all information from Camfrog rooms.
Uses the fixed Desktop(backend="uia") connection and calibrated coordinates:
- Chat Window Pane(50033) / Text(50020): [l=1281,t=170,r=2355,b=1160]
- Chat Txt Field Pane(50033): [l=1396,t=1206,r=2497,b=1241]
- User List List(50008): [l=2359,t=141,r=2559,b=1160] (reads 'USERS (#)' count + usernames, filters VIEWING # / LURKERS #)
- Talk Button Button(50000): [l=1291,t=1169,r=1361,b=1195] (2 clicks + hold)
- Active Speaker Button(50000): [l=1506,t=1174,r=1548,b=1190] (KaeKae_Toad 1.3s persistence gate)
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from camfrog_bot import CamfrogBot, detect_moderation
from config import (
    ACTIVE_SPEAKER_RECT,
    CHAT_INPUT_RECT,
    CHAT_WINDOW_RECT,
    POLL_INTERVAL_SECONDS,
    ROOM_TAB_CLICK_POINTS,
    TALK_BUTTON_RECT,
    USER_LIST_RECT,
)
from ui_automation import CamfrogUIAutomation


class RoomMonitor:
    """Monitors and displays all room information in a terminal while also dispatching bot triggers (!triggers, !who is, etc.)."""

    def __init__(self, *, dry_run: bool = False):
        self.bot = CamfrogBot(dry_run=dry_run)
        self.ui_automation = self.bot.ui_automation
        self.store = self.bot.store
        self.running = False
        self.last_events: set[str] = set()

    def start_monitoring(self) -> bool:
        print("=== CAMFROG ROOM MONITOR + BOT TRIGGER PIPELINE ===")
        print("Connecting to Camfrog...")
        if not self.bot.initialize(mark_existing_seen=True):
            print(f"ERROR: Could not connect to Camfrog: {self.ui_automation.last_error}")
            return False

        # Sync initial scrollback events so we only display and trigger on new live events
        for event in self.ui_automation.get_chat_events():
            event_key = f"{event.get('kind', '')}:{event.get('user', '')}:{event.get('text', '')}:{event.get('timestamp', '')}"
            self.last_events.add(event_key)

        print("Connected to Camfrog successfully!")
        print(f"Locations: {json.dumps(self.ui_automation.layout_locations())}")
        initial_users = self.bot.initial_users
        user_count = self.ui_automation.get_user_count(refresh=False)
        print(
            f"Initial Room Roster [l={USER_LIST_RECT[0]},r={USER_LIST_RECT[2]}] "
            f"(USERS (#): {user_count} | Listed: {len(initial_users)}): "
            f"{', '.join(initial_users[:15])}"
        )
        print(
            f"Fast polling active (every {POLL_INTERVAL_SECONDS}s) + live bot triggers enabled "
            f"(!triggers, !who is, !info on, !say, etc.) -> Chat Input {CHAT_INPUT_RECT}.\\n"
        )
        self.running = True

        try:
            while self.running:
                self._display_room_info()
                time.sleep(max(0.25, POLL_INTERVAL_SECONDS))
        except KeyboardInterrupt:
            print("\\nMonitoring stopped by user.")
            self.running = False

        return True

    def _display_room_info(self) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Force a fresh UIA snapshot each cycle so Active Speaker, USERS (#), and Chat are up to date
        self.ui_automation.nodes(refresh=True)
        self.bot._track_active_speaker()
        current_room = self.ui_automation.get_current_room()
        speaker = self.ui_automation.get_active_speaker(refresh=False)
        users = self.ui_automation.get_user_list(refresh=False)
        users_header_count = self.ui_automation.get_user_count(refresh=False)

        events = self.ui_automation.get_chat_events()
        new_events = []
        for event in events:
            event_key = f"{event.get('kind', '')}:{event.get('user', '')}:{event.get('text', '')}:{event.get('timestamp', '')}"
            if event_key not in self.last_events:
                self.last_events.add(event_key)
                new_events.append(event)
                if event.get("kind") == "presence":
                    self.store.record_presence(event.get("user", ""), event.get("action", "join"), event_key)
                elif event.get("kind") == "message":
                    self.bot._handle_message(event.get("user", ""), event.get("text", ""), event.get("timestamp", ""))

        self.bot._run_scheduled_disses()

        # Prefer the sum of the 3 User List headers (YOU ARE VIEWING + MEMBERS + LURKERS) / Users (#) count
        effective_count = users_header_count if users_header_count > 0 else (len(users) or self.store.active_user_count())
        print(
            f"[{timestamp}] Room: {current_room or 'Unknown'} | "
            f"Users: {effective_count} (Listed: {len(users)}, Active Tracked: {self.store.active_user_count()}) | "
            f"Mic @ {ACTIVE_SPEAKER_RECT}: {speaker or 'FREE (erased)'}"
        )

        if new_events:
            print(f"  New Events ({len(new_events)}) from Chat Window {CHAT_WINDOW_RECT}:")
            for event in new_events[-10:]:
                event_type = event.get("kind", "unknown")
                user = event.get("user", "unknown")
                text = event.get("text", "")
                ts = event.get("timestamp", "")

                if event_type == "message":
                    print(f"    [MSG] {ts} {user}: {text}")
                    moderation = detect_moderation(text)
                    if moderation:
                        print(f"    [MOD] {moderation['actor']} {moderation['action']} {moderation['target']}")
                elif event_type == "presence":
                    action = event.get("action", "unknown")
                    dur_sec = self.store.user_chat_duration_seconds(user)
                    verb = "joined" if action == "join" else "quit"
                    print(f"    [PRESENCE] {user} {verb} the room (tracked duration: {dur_sec:.0f}s)")

        print("-" * 72)


def main():
    monitor = RoomMonitor()
    monitor.start_monitoring()


if __name__ == "__main__":
    main()
`;

export const FIXED_ROOM_DATA_PROCESSOR_PY = `#!/usr/bin/env python3
"""
Process information from different Camfrog rooms using calibrated coordinates:
- (1390, 50) -> Room List
- (1550, 50) -> Players__Lounge
- Chat Window Pane(50033)/Text(50020): [l=1281,t=170,r=2355,b=1160]
- Chat Txt Field Pane(50033): [l=1396,t=1206,r=2497,b=1241]
- User List(50008): [l=2359,t=141,r=2559,b=1160] (trending [l=2359,r=2559], max 100)
- Talk Button(50000): [l=1291,t=1169,r=1361,b=1195]
- Active Speaker Button(50000): [l=1506,t=1174,r=1548,b=1190]
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui_automation import CamfrogUIAutomation


class RoomDataProcessor:
    """Process data from different rooms and set up logic based on room context."""

    def __init__(self):
        self.ui_automation = CamfrogUIAutomation()
        self.room_commands = {
            "Players__Lounge": [r"!players", r"!lounge", r"!room info"],
            "Drama_Central": [r"!drama", r"!central", r"!showtime"],
            "Room List": [r"!rooms", r"!list", r"!switch"],
        }
        self.room_triggers = {
            "Players__Lounge": {
                "trigger_words": ["game", "play", "match"],
                "response_template": "@{user} Let's play some games in the lounge!",
                "action": "send_to_room",
            },
            "Drama_Central": {
                "trigger_words": ["drama", "argument", "fight"],
                "response_template": "@{user} This is a drama central - keep it civil!",
                "action": "send_to_room",
            },
        }

    def process_message(self, room_name, user, message):
        print(f"[{room_name}] {user}: {message}")
        message_lower = message.lower()
        if message_lower.startswith("!"):
            self.handle_command(room_name, user, message)
        if room_name in self.room_triggers:
            trigger_config = self.room_triggers[room_name]
            for trigger_word in trigger_config["trigger_words"]:
                if trigger_word in message_lower:
                    response = trigger_config["response_template"].format(user=user)
                    print(f"  -> Triggered: {response}")
                    return response
        return None

    def handle_command(self, room_name, user, message):
        print(f"  Command detected in {room_name}: {message}")

    def get_room_context(self, room_name):
        users = self.ui_automation.get_user_list()
        return {
            "room": room_name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "active_users": users,
            "user_count": len(users),
            "active_speaker": self.ui_automation.get_active_speaker(),
            "message_count": len(self.ui_automation.get_chat_events()),
        }


def main():
    print("Camfrog Room Data Processor")
    print("=" * 40)
    processor = RoomDataProcessor()
    for room, user, message in [
        ("Players__Lounge", "Alice", "!players"),
        ("Players__Lounge", "Bob", "Let's play a game!"),
        ("Room List", "Eve", "!rooms"),
    ]:
        processor.process_message(room, user, message)


if __name__ == "__main__":
    main()
`;

export const FIXED_TEST_BOT_PY = `"""Offline tests for the UIA bot; no Camfrog window is required."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from camfrog_bot import CamfrogBot, CamfrogStore, detect_moderation
from config import (
    ACTIVE_SPEAKER_RECT,
    BOT_USERNAME,
    CHAT_INPUT_RECT,
    CHAT_WINDOW_RECT,
    MIC_CONFIRM_PERSIST_SECONDS,
    TALK_BUTTON_RECT,
    USER_LIST_RECT,
)
from ui_automation import (
    CamfrogUIAutomation,
    UIANode,
    clean_username,
    extract_users_header_count,
    is_user_list_header,
)


class FakeAutomation:
    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []
        self.sent: list[str] = []
        self.tts_broadcasts: list[str] = []
        self.user_list: list[str] = ["Stonerwayne1000", "Rosie", "nico1ee"]
        self.active_speaker: str | None = None
        self.last_error = ""

    def connect_to_camfrog(self) -> bool:
        return True

    def get_user_list(self) -> list[str]:
        return list(self.user_list)

    def get_chat_events(self) -> list[dict[str, str]]:
        return list(self.events)

    def get_active_speaker(self) -> str | None:
        return self.active_speaker

    def send_chat_message(self, message: str) -> bool:
        self.sent.append(message)
        return True

    def broadcast_tts_via_vbcable(self, text: str, dry_run: bool = False) -> bool:
        self.tts_broadcasts.append(text)
        return True


class CamfrogBotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.ui = FakeAutomation()
        self.bot = CamfrogBot(
            automation=self.ui,
            store=CamfrogStore(root / "bot.db", root / "suppressed"),
        )
        self.assertTrue(self.bot.initialize())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_records_message_and_serves_info(self) -> None:
        self.ui.events = [{"kind": "message", "user": "Alice_1", "text": "Python Python testing", "timestamp": "1:00 PM"}]
        self.bot.poll_once()
        profile = self.bot.store.user_profile("Alice_1")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["message_count"], 1)
        self.bot._handle_message("Alice_1", "!info on Alice_1", "1:01 PM")
        self.assertTrue(any("Alice_1: 2 messages" in message for message in self.ui.sent))

    def test_suppression_can_be_reversed_by_the_same_user(self) -> None:
        self.bot._handle_message("Alice_1", "A stored line", "1:00 PM")
        self.bot._handle_message("Alice_1", "!suppress", "1:01 PM")
        self.assertTrue(self.bot.store.is_suppressed("Alice_1"))
        self.bot._handle_message("Alice_1", "!unsuppress", "1:02 PM")
        self.assertFalse(self.bot.store.is_suppressed("Alice_1"))
        self.assertIsNotNone(self.bot.store.user_profile("Alice_1"))

    def test_moderation_parser_rejects_prose(self) -> None:
        self.assertEqual(
            detect_moderation("Mod_1 unbanned User_2"),
            {"actor": "Mod_1", "target": "User_2", "action": "unbanned"},
        )
        self.assertIsNone(detect_moderation("Please do not ban User_2"))

    def test_ui_text_and_viewing_lurkers_filtered(self) -> None:
        self.assertEqual(clean_username("8:13 AM"), "")
        self.assertEqual(clean_username("GIFTUsers2"), "")
        self.assertEqual(clean_username("YOU ARE VIEWING 3", (2359, 141, 2559, 163)), "")
        self.assertEqual(clean_username("VIEWING 5", (2359, 185, 2559, 207)), "")
        self.assertEqual(clean_username("LURKERS 14", (2359, 520, 2559, 542)), "")
        self.assertEqual(clean_username("USERS (48)", (2359, 165, 2543, 187)), "")
        self.assertEqual(extract_users_header_count("USERS (48)"), 48)
        self.assertEqual(extract_users_header_count("USERS 35"), 35)
        self.assertEqual(extract_users_header_count("MEMBERS 17"), 17)
        self.assertIsNone(extract_users_header_count("YOU ARE VIEWING (0)"))
        self.assertIsNone(extract_users_header_count("VIEWING 4"))
        self.assertIsNone(extract_users_header_count("LURKERS (12)"))
        self.assertTrue(is_user_list_header("YOU ARE VIEWING 2"))
        self.assertTrue(is_user_list_header("LURKERS 19"))
        self.assertTrue(is_user_list_header("USERS (48)"))
        self.assertEqual(clean_username("HeaderItem", (2303, 141, 2559, 163)), "")
        self.assertEqual(clean_username("Alice_1", (2359, 240, 2543, 262)), "Alice_1")

    def test_active_speaker_detected_even_when_uia_name_empty(self) -> None:
        # Even if Button(50000) at [1506,1174,1548,1190] has empty UIA Name, _find_active_speaker_node detects it
        unnamed_mic_btn = UIANode("Button", "", "CButtonTS", 1506, 1174, 1548, 1190)
        found = CamfrogUIAutomation._find_active_speaker_node([unnamed_mic_btn])
        self.assertIsNotNone(found)
        self.assertEqual(found.rect_tuple, (1506, 1174, 1548, 1190))

    def test_initial_user_list_and_join_quit_duration(self) -> None:
        # Initial users from User List [l=2359,t=141,r=2559,b=1160] are seeded on initialize()
        profile = self.bot.store.user_profile("Stonerwayne1000")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["active"], 1)
        # Simulate Quit: event in Chat Window [l=1281,t=170,r=2355,b=1160]
        self.ui.events = [{"kind": "presence", "action": "quit", "user": "Stonerwayne1000", "text": "", "timestamp": ""}]
        self.bot.poll_once()
        updated = self.bot.store.user_profile("Stonerwayne1000")
        self.assertEqual(updated["active"], 0)

    def test_say_waits_when_mic_occupied_and_broadcasts_when_free(self) -> None:
        # When mic is free ([1506,1174,1548,1190] is empty), !say broadcasts immediately
        self.ui.active_speaker = None
        self.bot._handle_message("Alice_1", "!say Hello Players Lounge", "1:03 PM")
        self.assertEqual(self.ui.tts_broadcasts, ["Hello Players Lounge"])

        # When another user is on the mic at [1506,1174,1548,1190], !say queues until mic clears
        self.ui.active_speaker = "Rosie"
        self.bot._handle_message("Alice_1", "!say Queued until Rosie finishes", "1:04 PM")
        self.assertEqual(len(self.ui.tts_broadcasts), 1)
        # Now Rosie finishes and [1506,1174,1548,1190] erases/clears
        self.ui.active_speaker = None
        self.bot.poll_once()
        self.assertEqual(self.ui.tts_broadcasts, ["Hello Players Lounge", "Queued until Rosie finishes"])

    def test_compound_dataitem_presence_and_user_count_minus_3(self) -> None:
        # 1. Compound DataItem(50029) at [l=1332,r=2330] containing multiple Quit:/Join: events in a single item
        tokens = [
            ("DataItem", "Quit: phoenixrising Quit: liketosquirt Join: ward1dp"),
            ("Text", "Quit:"),
            ("Text", "phoenixrising"),
            ("Text", "Quit:"),
            ("Text", "liketosquirt"),
            ("Text", "Join:"),
            ("Text", "ward1dp"),
        ]
        events = CamfrogUIAutomation._parse_text_tokens_into_events(tokens)
        presence_pairs = [(e["action"], e["user"]) for e in events if e["kind"] == "presence"]
        self.assertIn(("quit", "phoenixrising"), presence_pairs)
        self.assertIn(("quit", "liketosquirt"), presence_pairs)
        self.assertIn(("join", "ward1dp"), presence_pairs)

        # 2. User List counting: sums the 3 ignored section headers (YOU ARE VIEWING # + MEMBERS # + LURKERS #)
        #    and excludes Page scrollbar and OCR header fragments
        ui = CamfrogUIAutomation()
        fake_nodes = [
            UIANode("ListItem", "YOU ARE VIEWING (2)", "", 2359, 141, 2543, 163),
            UIANode("ListItem", "MEMBERS (16)", "", 2359, 165, 2543, 187),
            UIANode("ListItem", "10 Mr,Bl3sS", "", 2359, 190, 2543, 212),
            UIANode("ListItem", "tsyko", "", 2359, 215, 2543, 237),
            UIANode("ListItem", "Gothic_Chaos", "", 2359, 240, 2543, 262),
            UIANode("ListItem", "LURKERS (12)", "", 2359, 520, 2543, 542),
            UIANode("ListItem", "KaeKae_Toad", "", 2359, 545, 2543, 567),
            UIANode("Button", "Page", "", 2544, 200, 2559, 800),
        ]
        count, users = ui._scan_users_header_and_list_from_uia(fake_nodes)
        self.assertEqual(count, 30)  # 2 YOU ARE VIEWING + 16 MEMBERS + 12 LURKERS = 30
        self.assertNotIn("Page", users)
        self.assertIn("tsyko", users)
        self.assertIn("Gothic_Chaos", users)
        self.assertIn("KaeKae_Toad", users)

        # 3. Verify URLs ('https://...') and OCR header fragments ('BERS', 'ERS', 'lol', 'right') are rejected as usernames
        self.assertEqual(clean_username("BERS"), "")
        self.assertEqual(clean_username("ERS"), "")
        self.assertEqual(clean_username("lol"), "")
        self.assertEqual(clean_username("right"), "")
        self.assertEqual(clean_username("https"), "")
        url_events = CamfrogUIAutomation._parse_text_tokens_into_events([
            ("Text", "https://static.camfrogcdn.com/vue_static/pages/room_browser.html#/home"),
            ("Text", "$htickie"),
            ("Text", ":"),
            ("Text", "!triggers"),
        ])
        self.assertEqual(len(url_events), 1)
        self.assertEqual(url_events[0]["user"], "$htickie")
        self.assertEqual(url_events[0]["text"], "!triggers")

        # 4. Verify !triggers dispatches reply to Chat Txt Field
        self.bot._handle_message("$htickie", "!triggers", "2:00 PM")
        self.assertTrue(any("Triggers: !chat" in msg for msg in self.ui.sent))

    def test_calibrated_coordinates_constants(self) -> None:
        self.assertEqual(CHAT_WINDOW_RECT, (1281, 170, 2355, 1160))
        self.assertEqual(CHAT_INPUT_RECT, (1396, 1206, 2497, 1241))
        self.assertEqual(USER_LIST_RECT, (2359, 141, 2559, 1160))
        self.assertEqual(TALK_BUTTON_RECT, (1291, 1169, 1361, 1195))
        self.assertEqual(ACTIVE_SPEAKER_RECT, (1506, 1174, 1548, 1190))
        self.assertEqual(BOT_USERNAME, "KaeKae_Toad")
        self.assertEqual(MIC_CONFIRM_PERSIST_SECONDS, 1.3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
`;
