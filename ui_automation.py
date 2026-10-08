"""Camfrog UI Automation adapter with Desktop window enumeration, calibrated rectangles, and VB-Cable TTS."""

from __future__ import annotations

import ctypes
import re
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
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
    VB_CABLE_PLAYBACK_DEVICE,
    VB_CABLE_TTS_ENABLED,
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


_CLOCK_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?$", re.I)
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
    if _CLOCK_RE.fullmatch(raw) or re.fullmatch(r"\d{3,4}(?:AM|PM)", raw, re.I):
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
            self.last_error = "pywinauto is not installed; run setup_bot.py in .venv."
            return False

        try:
            # Enumerate all top-level UIA windows safely via Desktop(backend="uia").
            # Avoids calling Application(backend="uia").connect() with empty args.
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
                    if (
                        title_pattern.search(title)
                        or "camfrog" in title.lower()
                        or "camfrog" in cls_name.lower()
                        or (rect.left <= 1291 and rect.right >= 2550)
                    ):
                        candidates.append(win)
                except Exception:
                    continue

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
        cleaned_text = str(text or "").strip()
        if not cleaned_text or not VB_CABLE_TTS_ENABLED:
            return False
        if dry_run:
            return True

        l, t, r, b = TALK_BUTTON_RECT
        cx, cy = (l + r) // 2, (t + b) // 2  # (1326, 1182)

        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "tts_out.wav"
            # Generate WAV using Windows SAPI.SpVoice / SpeechSynthesizer
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

            # Hold down the Camfrog Talk Button while playing audio into CABLE Input
            try:
                if uia_press is not None:
                    uia_press(coords=(cx, cy))
                time.sleep(0.15)
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
        """Play WAV file specifically to 'CABLE Input (VB-Audio Virtual Cable)' if sounddevice/pyaudio is present."""
        try:
            import sounddevice as sd
            import wave as _wave
            import numpy as np

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
            # Fallback to winsound if sounddevice is not installed (assuming VB-Cable Input is default or routed)
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
