"""Camfrog UI Automation adapter with Desktop window enumeration, calibrated rectangles, and VB-Cable TTS."""

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
        """Ultra-fast COM text read: only read info.name (and rich_text if present) to avoid 45-second COM exception storms."""
        try:
            direct = info.name
            if direct and isinstance(direct, str):
                stripped = direct.strip()
                if stripped:
                    return stripped
        except Exception:
            pass
        try:
            rt = getattr(info, "rich_text", "")
            if rt and isinstance(rt, str):
                stripped = rt.strip()
                if stripped:
                    return stripped
        except Exception:
            pass
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
            ctype = info.control_type or ""
            # Skip purely decorative Image/Separator/Thumb/ScrollBar/TitleBar controls for speed
            if ctype in {"Image", "Separator", "Thumb", "ScrollBar", "TitleBar", "MenuBar", "MenuItem", "ToolTip"}:
                return None
            # Read info.name FIRST before querying info.rectangle!
            # 90% of Camfrog CEF/Qt descendants have an empty name; only unnamed Button/Pane/Edit controls
            # (like the Active Speaker button at [1506,1174,1548,1190] or Chat Input at [1396,1206,2497,1241])
            # need their rectangle inspected when name is empty.
            text = self._extract_control_text(control, info)
            if not text and ctype not in {"Button", "Pane", "Edit", "Document"}:
                return None
            rect = info.rectangle
            left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
            # Skip invisible / offscreen controls or video grid tiles on the left side (< 1275)
            if right <= left or bottom <= top or right < 1275:
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
            compact_line = re.sub(r"\s*_\s*", "_", line.strip())
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
                escaped = re.sub(r"([+^%~(){}])", r"{\1}", cleaned)
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
