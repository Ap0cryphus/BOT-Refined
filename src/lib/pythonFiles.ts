/**
 * Complete, fixed Python scripts for C:\Users\newbe\AIBot
 * Fixes:
 * 1. pywinauto `Application(backend="uia").connect()` empty-argument crash
 * 2. Dynamic room topic window title changes (uses Desktop(backend="uia").windows() + handle/process_id + calibrated coordinates)
 * 3. Calibrated BoundingRectangles for Chat Pane(50033), Talk Button(50000), User List(50008), and the 3 ignored ListItem(50007) rects
 * 4. Fixed tab coordinates (1390, 50) -> Room List and (1550, 50) -> Players__Lounge
 * 5. Continuous background audio transcription & SQLite storage
 */

export const FIXED_CONFIG_PY = `"""Runtime configuration for the UI-Automation Camfrog bot."""

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
# We match known room names, Camfrog classes, or calibrated UIA rectangles.
CAMFROG_WINDOW_TITLE_RE = r"(?i).*(Players__Lounge|Drama_Central|Camfrog|Video Chat Room).*"
POLL_INTERVAL_SECONDS = 0.75
UIA_CACHE_SECONDS = 0.30
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

# Exact calibrated BoundingRectangles [left, top, right, bottom]
CHAT_WINDOW_RECT = (1281, 170, 2299, 1160)      # ControlType Pane(50033)
TALK_BUTTON_RECT = (1291, 1169, 1361, 1195)     # ControlType Button(50000)
USER_LIST_RECT = (2303, 141, 2559, 1160)        # ControlType List(50008), items at r=2559

# Specific ListItem(50007) rectangles inside User List to ignore (headers/separators)
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
    "transcription_mode": True,  # Continuous audio transcription storage enabled
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

export const FIXED_UI_AUTOMATION_PY = `"""Camfrog UI Automation adapter with Desktop window enumeration and calibrated rectangles."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

from config import (
    CAMFROG_WINDOW_TITLE_RE,
    CHAT_WINDOW_RECT,
    IGNORED_USER_LIST_RECTS,
    ROOM_TAB_CLICK_POINTS,
    ROOM_TAB_POSITIONS,
    TALK_BUTTON_RECT,
    UIA_CACHE_SECONDS,
    USER_LIST_RECT,
)

try:
    from pywinauto import Application, Desktop
    from pywinauto.mouse import click as uia_click, press as uia_press, release as uia_release
except ImportError:
    Application = None
    Desktop = None
    uia_click = None
    uia_press = None
    uia_release = None


_CLOCK_RE = re.compile(r"^\\d{1,2}:\\d{2}(?::\\d{2})?\\s*(?:AM|PM)?$", re.I)
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_$-]{2,32}$")
_PANEL_LABELS = {
    "talk", "push-to-talk", "camfrog", "users", "user", "members", "lurkers",
    "youareviewing", "search", "gifts", "giftusers", "yourvideo", "room", "chat",
}


def is_ignored_listitem_rect(rect_tuple: tuple[int, int, int, int] | None) -> bool:
    """Return True if the rectangle matches one of the 3 ignored ListItem(50007) slots."""
    if rect_tuple is None:
        return False
    l, t, r, b = rect_tuple
    for il, it, ir, ib in IGNORED_USER_LIST_RECTS:
        if abs(l - il) <= 2 and abs(t - it) <= 2 and abs(r - ir) <= 2 and abs(b - ib) <= 2:
            return True
    return False


def clean_username(value: str, rect_tuple: tuple[int, int, int, int] | None = None) -> str:
    """Return a valid Camfrog username, or an empty string for UI chrome / ignored rects."""
    if is_ignored_listitem_rect(rect_tuple):
        return ""
    raw = str(value or "").strip()
    if _CLOCK_RE.fullmatch(raw) or re.fullmatch(r"\\d{3,4}(?:AM|PM)", raw, re.I):
        return ""
    name = re.sub(r"[^A-Za-z0-9_$-]", "", raw)[:32]
    lower = name.lower()
    if lower == "giftusers2":
        return ""
    return name if _USERNAME_RE.fullmatch(name) and lower not in _PANEL_LABELS else ""


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
        self.last_error = ""

    def connect_to_camfrog(self) -> bool:
        """Attach to the Camfrog room window using Desktop(backend='uia').windows()."""
        if Application is None or Desktop is None:
            self.last_error = "pywinauto is not installed; run: pip install pywinauto"
            return False

        try:
            # Enumerate all top-level UIA windows safely via Desktop(backend="uia")
            # (Fixes: Application().connect() with no arguments raising ValueError)
            all_windows = Desktop(backend="uia").windows()
            candidates = []

            title_pattern = re.compile(self.title_re)
            for win in all_windows:
                try:
                    title = win.window_text() or ""
                    cls_name = win.class_name() or ""
                    rect = win.rectangle()
                    if rect.width() < 400 or rect.height() < 300:
                        continue
                    # Match by title regex, class name, or right-edge span covering calibrated coordinates
                    if (
                        title_pattern.search(title)
                        or "camfrog" in title.lower()
                        or "camfrog" in cls_name.lower()
                        or (rect.left <= 1291 and rect.right >= 2550)
                    ):
                        candidates.append(win)
                except Exception:
                    continue

            # If no obvious title/bounds matched, inspect visible large windows for CButtonTS or calibrated panes
            if not candidates:
                for win in all_windows:
                    try:
                        rect = win.rectangle()
                        if rect.width() >= 600 and rect.height() >= 400:
                            candidates.append(win)
                    except Exception:
                        continue

            best_win = None
            best_score = -1

            for win in candidates:
                try:
                    rect = win.rectangle()
                    title = win.window_text() or ""
                    score = 0
                    if title_pattern.search(title):
                        score += 500
                    # Check if window encompasses our calibrated Chat/UserList coordinates
                    if rect.left <= 1281 and rect.right >= 2559:
                        score += 1000
                    cbutton_count = len(win.descendants(class_name="CButtonTS"))
                    score += cbutton_count * 120
                    score += (rect.width() * rect.height()) // 20000

                    if score > best_score:
                        best_score = score
                        best_win = win
                except Exception:
                    continue

            if best_win is None or best_score <= 0:
                self.last_error = "Could not find an open Camfrog room window on the desktop."
                return False

            # Connect Application(backend="uia") using the winning window's integer handle
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
            return self.window is not None and bool(self.window.exists(timeout=0))
        except Exception:
            return False

    def _node_from_control(self, control: Any) -> UIANode | None:
        try:
            info = control.element_info
            rect = control.rectangle()
            return UIANode(
                control_type=(info.control_type or ""),
                name=(info.name or control.window_text() or "").strip(),
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
        nodes = self.nodes()
        talk = self._find_talk(nodes)
        edit = self._find_chat_input(nodes)
        return {
            "window": bounds,
            "chat_feed": CHAT_WINDOW_RECT,
            "user_list": USER_LIST_RECT,
            "chat_input": self._rect(edit),
            "talk": self._rect(talk) or TALK_BUTTON_RECT,
        }

    @staticmethod
    def _rect(node: UIANode | None) -> tuple[int, int, int, int] | None:
        return None if node is None else (node.left, node.top, node.right, node.bottom)

    @staticmethod
    def _find_talk(nodes: Iterable[UIANode]) -> UIANode | None:
        tl, tt, tr, tb = TALK_BUTTON_RECT
        for node in nodes:
            if node.control_type == "Button":
                if abs(node.left - tl) <= 15 and abs(node.top - tt) <= 15:
                    return node
                if node.name.lower().strip() in {"talk", "push-to-talk", "push to talk"}:
                    return node
        return None

    def _find_chat_input(self, nodes: Iterable[UIANode]) -> UIANode | None:
        bounds = self._window_rect()
        if bounds is None:
            return None
        _, top, _, bottom = bounds
        edits = [node for node in nodes if node.control_type == "Edit" and node.top >= top + (bottom - top) * 0.55]
        return max(edits, key=lambda node: node.width * node.height, default=None)

    def get_active_speaker(self) -> str | None:
        """Read the active speaker username immediately to the right of Talk Button [1291,1169,1361,1195]."""
        nodes = self.nodes()
        talk = self._find_talk(nodes)
        talk_top = talk.top if talk else TALK_BUTTON_RECT[1]
        talk_right = talk.right if talk else TALK_BUTTON_RECT[2]
        candidates = [
            node for node in nodes
            if (node.class_name == "CButtonTS" or node.control_type in {"Button", "Text", "Custom"})
            and clean_username(node.name, node.rect_tuple)
            and abs(node.top - talk_top) <= 35
            and 0 <= node.left - talk_right <= 300
        ]
        return min(candidates, key=lambda node: node.left).name if candidates else None

    def get_user_list(self) -> list[str]:
        """Extract usernames from User List [l=2303,t=141,r=2559,b=1160] while ignoring the 3 header ListItems."""
        ul_left, ul_top, ul_right, ul_bottom = USER_LIST_RECT
        users: list[str] = []
        for node in self.nodes():
            if is_ignored_listitem_rect(node.rect_tuple):
                continue
            # Match calibrated User List (r=2559 or inside [2303..2559])
            in_calibrated_list = (
                abs(node.right - ul_right) <= 10
                or (node.left >= ul_left - 20 and node.top >= ul_top - 10 and node.bottom <= ul_bottom + 10)
            )
            if not in_calibrated_list:
                continue
            if node.control_type not in {"ListItem", "Text", "Hyperlink"}:
                continue
            user = clean_username(node.name, node.rect_tuple)
            if user and user.lower() not in {item.lower() for item in users}:
                users.append(user)
        return users

    def get_user_count(self) -> int:
        return len(self.get_user_list())

    def get_chat_events(self, limit: int = 200) -> list[dict[str, str]]:
        """Parse chat events inside Chat Window Pane(50033) [l=1281,t=170,r=2299,b=1160]."""
        cl, ct, cr, cb = CHAT_WINDOW_RECT
        chat_nodes = [
            node for node in self.nodes()
            if node.name and not is_ignored_listitem_rect(node.rect_tuple)
            and (node.right <= cr + 40)
        ]
        flat = [(node.control_type, node.name) for node in chat_nodes]
        events: list[dict[str, str]] = []
        for index, (control_type, name) in enumerate(flat):
            lowered = name.lower().strip()
            if lowered in {"join:", "quit:"}:
                action = "join" if lowered == "join:" else "quit"
                user = clean_username(flat[index + 1][1]) if index + 1 < len(flat) else ""
                if user:
                    events.append({"kind": "presence", "action": action, "user": user, "text": "", "timestamp": ""})
                continue
            if _CLOCK_RE.fullmatch(name.strip()) and index > 0:
                user = clean_username(flat[index - 1][1])
                if not user:
                    continue
                body = ""
                for _, candidate in flat[index + 1:index + 4]:
                    if candidate and not _CLOCK_RE.fullmatch(candidate.strip()) and candidate.lower().strip() not in {"join:", "quit:"}:
                        body = candidate.strip()
                        break
                if body:
                    events.append({"kind": "message", "user": user, "text": body, "timestamp": name.strip()})

        for _, name in flat:
            if ":" not in name:
                continue
            user_raw, body = name.split(":", 1)
            user = clean_username(user_raw.replace(" says", ""))
            if user and body.strip():
                events.append({"kind": "message", "user": user, "text": body.strip(), "timestamp": ""})

        unique: list[dict[str, str]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for event in events:
            key = (event["kind"], event.get("action", ""), event["user"].lower(), event["text"])
            if key not in seen:
                seen.add(key)
                unique.append(event)
        return unique[-limit:]

    def send_chat_message(self, message: str, dry_run: bool = False) -> bool:
        if dry_run:
            return True
        node = self._find_chat_input(self.nodes(refresh=True))
        if node is None or node.control is None:
            self.last_error = "Camfrog chat input was not exposed through UI Automation."
            return False
        try:
            node.control.set_focus()
            try:
                node.control.set_edit_text(message)
            except Exception:
                node.control.type_keys(message, with_spaces=True, set_foreground=False)
            node.control.type_keys("{ENTER}", set_foreground=False)
            return True
        except Exception as error:
            self.last_error = f"Camfrog UIA chat send failed: {error}"
            return False

    def broadcast_tts_via_vbcable(self, text: str, dry_run: bool = False) -> bool:
        """Synthesize speech to WAV, route to VB-Cable ('CABLE Input'), and hold Talk Button [1291,1169,1361,1195]."""
        import subprocess, tempfile, wave
        from pathlib import Path
        from config import VB_CABLE_PLAYBACK_DEVICE, VB_CABLE_TTS_ENABLED

        cleaned_text = str(text or "").strip()
        if not cleaned_text or not VB_CABLE_TTS_ENABLED:
            return False
        if dry_run:
            return True

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
                    if wf.getframerate() > 0:
                        duration = max(0.5, wf.getnframes() / float(wf.getframerate()))
            except Exception:
                pass

            try:
                if uia_press is not None:
                    uia_press(coords=(cx, cy))
                time.sleep(0.15)
                try:
                    import sounddevice as sd, numpy as np
                    target_idx = next(
                        (i for i, d in enumerate(sd.query_devices())
                         if VB_CABLE_PLAYBACK_DEVICE.lower() in str(d.get("name", "")).lower()
                         and d.get("max_output_channels", 0) > 0),
                        None,
                    )
                    with wave.open(str(wav_path), "rb") as wf:
                        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                        if wf.getnchannels() > 1:
                            data = data.reshape(-1, wf.getnchannels())
                        sd.play(data, samplerate=wf.getframerate(), device=target_idx)
                        sd.wait()
                except Exception:
                    import winsound
                    winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
                return True
            finally:
                if uia_release is not None:
                    uia_release(coords=(cx, cy))

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

    def switch_to_room(self, room_name: str) -> bool:
        """Click the fixed tab coordinate (1390, 50) or (1550, 50)."""
        coords = ROOM_TAB_CLICK_POINTS.get(room_name)
        if not coords or uia_click is None:
            return False
        try:
            uia_click(coords=coords)
            time.sleep(0.4)
            return True
        except Exception as error:
            self.last_error = f"Tab click failed: {error}"
            return False
`;
