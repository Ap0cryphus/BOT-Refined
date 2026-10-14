"""
uia_interface.py — Task 1: Windows UI Accessibility Hook (Unified with CamfrogBot / KaeKae_Toad Pipeline)
=========================================================================================================

Production-ready modular UIA targeting & background message dispatcher designed for both:
- `publicaccess.tv` (PepeFrog streaming economy bot game inside Camfrog)
- `KaeKae_Toad` Camfrog Desktop / CEF / Browser Chat Wrapper (`camfrog_bot.py` & `ui_automation.py`)

Core Capabilities:
1. Shares the exact same `CamfrogUIAutomation` instance and calibrated coordinates as `KaeKae_Toad`:
   - Chat Window: `CHAT_WINDOW_RECT = (1281, 170, 2355, 1160)`
   - Chat Text Field: `CHAT_INPUT_RECT = (1396, 1206, 2497, 1241)`
   - User List: `USER_LIST_RECT = (2359, 141, 2559, 1160)`
   - Talk Button: `TALK_BUTTON_RECT = (1291, 1169, 1361, 1195)`
   - Active Speaker: `ACTIVE_SPEAKER_RECT = (1506, 1174, 1548, 1190)`
2. Automatically connects on first `send_command()` or `broadcast_microphone()` call if not already connected,
   so clicking any GUI button or starting the `Start_PepeFrog_GUI.bat` launcher sends `!spin`, `!heist`,
   or chat messages straight into the Camfrog room chat immediately.
3. Operates implicitly over UIA node pointers (`ValuePattern.SetValue`, `LegacyIAccessible`) and Win32
   `PostMessageW` (`WM_SETFOCUS`, `WM_CHAR`, `WM_KEYDOWN`/`WM_KEYUP`) so it minimizes focus-stealing
   from global hardware space, keeping the background terminal or game targeted cleanly.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

from config import (
    ACTIVE_SPEAKER_RECT,
    BOT_USERNAME,
    CAMFROG_WINDOW_TITLE_RE,
    CHAT_INPUT_RECT,
    CHAT_TEXT_RECT,
    CHAT_WINDOW_RECT,
    TALK_BUTTON_RECT,
    USER_LIST_RECT,
)
from ui_automation import CamfrogUIAutomation, UIANode

# Optional native `uiautomation` package support alongside `pywinauto`
try:
    import uiautomation as auto  # type: ignore[import-not-found]
except ImportError:
    auto = None


@dataclass(frozen=True)
class UIATargetMap:
    """Runtime UIA node descriptor pulled from video/desktop context runtime."""

    window_title_regex: str = CAMFROG_WINDOW_TITLE_RE
    chat_input_automation_id: str = "chat_input_field"
    chat_input_control_types: tuple[str, ...] = ("Pane", "Edit", "Document", "Custom", "Text")
    chat_input_class_names: tuple[str, ...] = (
        "Chrome_RenderWidgetHostHWND",
        "Intermediate D3D Window",
        "Edit",
        "RichEditD2DPT",
    )
    chat_input_rect: tuple[int, int, int, int] = CHAT_INPUT_RECT
    chat_feed_rect: tuple[int, int, int, int] = CHAT_WINDOW_RECT
    spin_wheel_rect: tuple[int, int, int, int] = (1281, 170, 2355, 780)


class UIAInterface:
    """Implicit Windows UI Automation & Win32 background hook shared between PepeFrog and KaeKae_Toad."""

    def __init__(
        self,
        target_map: UIATargetMap | None = None,
        *,
        dry_run: bool = False,
        log_callback: Callable[[str], None] | None = None,
        shared_adapter: CamfrogUIAutomation | None = None,
    ) -> None:
        self.target_map = target_map or UIATargetMap()
        self.dry_run = dry_run
        self._log_cb = log_callback
        # Share the exact CamfrogUIAutomation pipeline used by KaeKae_Toad (camfrog_bot.py)
        self.adapter = shared_adapter or CamfrogUIAutomation(title_re=self.target_map.window_title_regex)
        self._cached_input_node: UIANode | None = None
        self._cached_input_at: float = 0.0
        self.commands_dispatched: int = 0
        self.last_command: str = ""
        self.last_dispatch_mono: float = 0.0
        self.last_error: str = ""

    def _emit_log(self, msg: str) -> None:
        if self._log_cb is not None:
            try:
                self._log_cb(msg)
            except Exception:
                pass

    def connect(self) -> bool:
        """Attach to the target Camfrog desktop application or browser wrapper."""
        if self.dry_run:
            self._emit_log("[UIA-DRY-RUN] Virtual UIA hook initialized (no focus-stealing).")
            return True
        if self.adapter.is_connected():
            return True
        ok = self.adapter.connect_to_camfrog()
        if not ok:
            self.last_error = self.adapter.last_error
            self._emit_log(f"[UIA-WARN] {self.last_error}")
        else:
            hwnd_hex = f"0x{self.adapter._hwnd:X}" if self.adapter._hwnd else "UIA"
            self._emit_log(
                f"[UIA-OK] Bound to Camfrog HWND={hwnd_hex} | ChatInput={self.target_map.chat_input_rect} | Talk={TALK_BUTTON_RECT}"
            )
        return ok

    def locate_chat_text_field(self, *, force_refresh: bool = False) -> UIANode | None:
        """Resolve the exact 'Chat Text Field' UIA node pointer using calibrated bounding box & control type."""
        now = time.perf_counter()
        if (
            not force_refresh
            and self._cached_input_node is not None
            and (now - self._cached_input_at) < 1.5
        ):
            return self._cached_input_node

        nodes = self.adapter.nodes(refresh=True)
        node = self.adapter._find_chat_input(nodes)
        if node is not None:
            self._cached_input_node = node
            self._cached_input_at = now
            return node

        # Fallback: check native `uiautomation` Control tree if installed and window is a browser wrapper
        if auto is not None and os.name == "nt" and self.adapter._hwnd:
            try:
                root_ctrl = auto.ControlFromHandle(self.adapter._hwnd)
                if root_ctrl:
                    edit_ctrl = root_ctrl.EditControl(searchDepth=8)
                    if edit_ctrl and edit_ctrl.Exists(0, 0):
                        rect = edit_ctrl.BoundingRectangle
                        synthetic = UIANode(
                            control_type="Edit",
                            name=edit_ctrl.Name or "",
                            class_name=edit_ctrl.ClassName or "",
                            left=int(rect.left),
                            top=int(rect.top),
                            right=int(rect.right),
                            bottom=int(rect.bottom),
                            control=edit_ctrl,
                        )
                        self._cached_input_node = synthetic
                        self._cached_input_at = now
                        return synthetic
            except Exception:
                pass

        return None

    def send_command(self, command_text: str) -> bool:
        """Programmatically set Chat Text Field value and capture Enter key using KaeKae_Toad's proven Camfrog pipeline.

        Automatically connects to Camfrog if not yet connected so `!spin`, `!heist`, or chat lines always transmit.
        """
        cleaned = str(command_text or "").strip()
        if not cleaned:
            return False

        self.last_command = cleaned
        self.last_dispatch_mono = time.perf_counter()

        if self.dry_run:
            self.commands_dispatched += 1
            self._emit_log(f"[UIA-TX] (Background Node Pointer -> {self.target_map.chat_input_rect}): {cleaned}")
            return True

        # Auto-connect to Camfrog window if not yet attached
        if not self.adapter.is_connected() and not self.connect():
            self._emit_log(
                f"[UIA-RETRY] Camfrog window not attached yet ({self.last_error}); attempting direct send..."
            )

        # Ensure background window is un-minimized via SW_SHOWNOACTIVATE without stealing focus
        self.adapter._ensure_renderable_in_background()

        ok = self.adapter.send_chat_message(cleaned, dry_run=self.dry_run)

        if ok:
            self.commands_dispatched += 1
            self._emit_log(f"[UIA-TX] Sent '{cleaned}' to Camfrog Chat Text Field {self.target_map.chat_input_rect}")
            return True

        self.last_error = self.adapter.last_error or "Failed to dispatch command to Camfrog Chat Text Field."
        self._emit_log(f"[UIA-ERR] {self.last_error}")
        return False

    def broadcast_microphone(self, phrase: str, voice: str | None = None) -> bool:
        """Broadcast speech on the Camfrog room microphone as KaeKae_Toad using the previous update's exact logic:
        - Waits until Active Speaker `[1506, 1174, 1548, 1190]` is clear.
        - Performs 2 quick clicks + hold on Talk Button `[1291, 1169, 1361, 1195]`.
        - Verifies `'KaeKae_Toad'` persists for `1.3s` at Active Speaker `[1506, 1174, 1548, 1190]`.
        - Streams Microsoft Edge Neural TTS audio over VB-Cable (`CABLE Input`) and releases Talk Button.
        """
        cleaned = str(phrase or "").strip()
        if not cleaned:
            return False
        if not self.dry_run and not self.adapter.is_connected():
            self.connect()
        ok = self.adapter.broadcast_tts_via_vbcable(cleaned, dry_run=self.dry_run, voice=voice)
        if ok:
            used_voice = getattr(self.adapter, "tts_voice", "en-US-AriaNeural")
            self._emit_log(
                f"[MIC-TTS-OK] KaeKae_Toad spoke on mic [{used_voice}] (Talk={TALK_BUTTON_RECT}, SpeakerGate={ACTIVE_SPEAKER_RECT} 1.3s): {cleaned}"
            )
        else:
            self.last_error = self.adapter.last_error or "VB-Cable microphone broadcast failed."
            self._emit_log(f"[MIC-TTS-ERR] {self.last_error}")
        return ok

    def poll_chat_events(self) -> list[dict[str, str]]:
        """Pull live chat messages, presence events, and game/heist output lines from the Camfrog UIA tree."""
        if self.dry_run:
            return []
        if not self.adapter.is_connected():
            self.connect()
        self.adapter.nodes(refresh=True)
        return self.adapter.get_chat_events()

    def get_room_telemetry(self) -> dict[str, Any]:
        """Return live room user count, active speaker on microphone, and current window coordinates."""
        if self.dry_run:
            return {
                "connected": True,
                "room": "publicaccess.tv / Players__Lounge",
                "user_count": 32,
                "active_speaker": None,
                "chat_input_rect": self.target_map.chat_input_rect,
                "chat_feed_rect": self.target_map.chat_feed_rect,
                "talk_button_rect": TALK_BUTTON_RECT,
                "active_speaker_rect": ACTIVE_SPEAKER_RECT,
                "user_list_rect": USER_LIST_RECT,
            }
        if not self.adapter.is_connected():
            self.connect()
        self.adapter.nodes(refresh=True)
        users = self.adapter.get_user_list(refresh=False)
        count = self.adapter.get_user_count(refresh=False) or len(users)
        speaker = self.adapter.get_active_speaker(refresh=False)
        return {
            "connected": self.adapter.is_connected(),
            "room": self.adapter.get_current_room() or "Players__Lounge",
            "user_count": count,
            "listed_users": users,
            "active_speaker": speaker,
            "chat_input_rect": self.target_map.chat_input_rect,
            "chat_feed_rect": self.target_map.chat_feed_rect,
            "talk_button_rect": TALK_BUTTON_RECT,
            "active_speaker_rect": ACTIVE_SPEAKER_RECT,
            "user_list_rect": USER_LIST_RECT,
        }

    def auto_calibrate_camfrog(self) -> dict[str, Any]:
        """Auto-scan the Camfrog window on the user's screen, discover and lock the exact Chat Text Input Box
        and Talk Button coordinates, and save them to `data/camfrog_calibration.json`.
        """
        if self.dry_run:
            self._emit_log(
                f"[UIA-CALIBRATE] Auto-calibrated Camfrog Chat Input -> {self.target_map.chat_input_rect} (Screen Point: (1946, 1223))"
            )
            return {
                "window_rect": [1273, 0, 2567, 1399],
                "chat_input_rect": list(self.target_map.chat_input_rect),
                "chat_input_screen_pt": [1946, 1223],
                "talk_button_rect": list(TALK_BUTTON_RECT),
            }
        payload = self.adapter.auto_calibrate_camfrog()
        self._emit_log(
            f"[UIA-CALIBRATE] Locked Camfrog Chat Box at ScreenPt={payload.get('chat_input_screen_pt')} | Rect={payload.get('chat_input_rect')} (Saved to data/camfrog_calibration.json)"
        )
        return payload

    def calibrate_chat_input_from_cursor(self, delay_seconds: float = 3.0) -> dict[str, Any]:
        """Interactive 3-Second Mouse-Hover Calibrator: waits `delay_seconds` while the user hovers their
        mouse cursor inside the Camfrog chat text box, then locks that exact `(x, y)` screen coordinate
        and saves it to `data/camfrog_calibration.json`.
        """
        if self.dry_run:
            self._emit_log(
                "[UIA-CURSOR-CALIBRATED] Locked Camfrog Chat Box at cursor (1946, 1223) and saved to data/camfrog_calibration.json!"
            )
            return {
                "window_rect": [1273, 0, 2567, 1399],
                "chat_input_rect": list(self.target_map.chat_input_rect),
                "chat_input_screen_pt": [1946, 1223],
                "talk_button_rect": list(TALK_BUTTON_RECT),
                "talk_button_screen_pt": [1326, 1182],
                "calibration_mode": "cursor_pick",
            }
        self._emit_log(
            f"[UIA-CURSOR-CALIBRATE] Hover your mouse inside the Camfrog chat text box now ({delay_seconds:.1f}s countdown)..."
        )
        payload = self.adapter.calibrate_chat_input_from_cursor(delay_seconds=delay_seconds)
        self._emit_log(
            f"[UIA-CURSOR-CALIBRATED] Locked Camfrog Chat Box at cursor {payload.get('chat_input_screen_pt')}! Saved to data/camfrog_calibration.json."
        )
        return payload

    def calibrate_talk_button_from_cursor(self, delay_seconds: float = 3.0) -> dict[str, Any]:
        """Interactive 3-Second Mouse-Hover Calibrator for the Camfrog Talk Button: waits `delay_seconds`
        while the user hovers their mouse over the Camfrog Talk Button, locks that exact `(x, y)` pixel coordinate,
        and saves it to `data/camfrog_calibration.json` so KaeKae_Toad can grab the microphone directly.
        """
        if self.dry_run:
            self._emit_log(
                "[UIA-TALK-CALIBRATED] Locked Camfrog Talk Button at cursor (1326, 1182) and saved to data/camfrog_calibration.json!"
            )
            return {
                "window_rect": [1273, 0, 2567, 1399],
                "chat_input_rect": list(self.target_map.chat_input_rect),
                "chat_input_screen_pt": [1946, 1223],
                "talk_button_rect": list(TALK_BUTTON_RECT),
                "talk_button_screen_pt": [1326, 1182],
                "calibration_mode": "talk_cursor_pick",
            }
        self._emit_log(
            f"[UIA-TALK-CALIBRATE] Hover your mouse over the Camfrog Talk Button now ({delay_seconds:.1f}s countdown)..."
        )
        payload = self.adapter.calibrate_talk_button_from_cursor(delay_seconds=delay_seconds)
        self._emit_log(
            f"[UIA-TALK-CALIBRATED] Locked Camfrog Talk Button at cursor {payload.get('talk_button_screen_pt')}! Saved to data/camfrog_calibration.json."
        )
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
        Enter exact `(X, Y)` screen pixel coordinates straight in for the Chat Text Box and/or Talk Button.
        """
        if self.dry_run:
            cx, cy = (chat_x or 1946, chat_y or 1223)
            tx, ty = (talk_x or 1326, talk_y or 1182)
            self._emit_log(
                f"[UIA-PIXEL-CALIBRATED] Direct Pixel Lock applied -> ChatBox=({cx}, {cy}) | TalkButton=({tx}, {ty}) (Saved to data/camfrog_calibration.json)"
            )
            return {
                "window_rect": [1273, 0, 2567, 1399],
                "chat_input_rect": list(self.target_map.chat_input_rect),
                "chat_input_screen_pt": [cx, cy],
                "talk_button_rect": list(TALK_BUTTON_RECT),
                "talk_button_screen_pt": [tx, ty],
                "calibration_mode": "direct_pixel_entry",
            }
        payload = self.adapter.set_direct_pixel_calibration(
            chat_x=chat_x,
            chat_y=chat_y,
            talk_x=talk_x,
            talk_y=talk_y,
        )
        self._emit_log(
            f"[UIA-PIXEL-CALIBRATED] Direct Pixel Lock applied -> ChatBox={payload.get('chat_input_screen_pt')} | TalkButton={payload.get('talk_button_screen_pt')} (Saved to data/camfrog_calibration.json)"
        )
        return payload

    def get_setup_diagnostics(self) -> dict[str, Any]:
        """Run a comprehensive 4-step diagnostic for the 2560x1440 Right-Half Monitor Setup Wizard."""
        deps_status: dict[str, bool] = {}
        for mod_name in ("pywinauto", "cv2", "numpy", "pyautogui", "mss", "pytesseract", "keyboard"):
            try:
                __import__(mod_name)
                deps_status[mod_name] = True
            except Exception:
                deps_status[mod_name] = False

        if self.dry_run:
            return {
                "dependencies": deps_status,
                "all_deps_ok": all(deps_status.values()),
                "connected": True,
                "hwnd": "0x001A4F20",
                "window_title": "Players__Lounge — Camfrog Video Chat (publicaccess.tv)",
                "window_rect": (1273, 0, 2567, 1399),
                "calibrated_reference_rect": (1273, 0, 2567, 1399),
                "is_right_half_2560x1440": True,
                "scaled_chat_input_rect": self.target_map.chat_input_rect,
                "calibrated_chat_input_screen_pt": (1946, 1223),
                "calibrated_talk_button_screen_pt": (1326, 1182),
                "scaled_talk_button_rect": TALK_BUTTON_RECT,
                "scaled_active_speaker_rect": ACTIVE_SPEAKER_RECT,
                "scaled_chat_window_rect": CHAT_WINDOW_RECT,
            }

        connected = self.connect()
        raw_rect = self.adapter._get_window_rect()
        if isinstance(raw_rect, (list, tuple)) and len(raw_rect) == 4:
            win_rect = (int(raw_rect[0]), int(raw_rect[1]), int(raw_rect[2]), int(raw_rect[3]))
        else:
            win_rect = (1273, 0, 2567, 1399)
        hwnd_hex = f"0x{self.adapter._hwnd:X}" if self.adapter._hwnd else "None"
        win_title = ""
        if self.adapter.window is not None:
            try:
                win_title = str(self.adapter.window.window_text() or "")
            except Exception:
                win_title = "Camfrog Room Window"

        l, t, r, b = win_rect
        is_right_half = abs(l - 1273) <= 120 and r >= 2400
        cal_rect = self.adapter.calibrated_chat_input_rect or self.target_map.chat_input_rect
        return {
            "dependencies": deps_status,
            "all_deps_ok": all(deps_status.values()),
            "connected": connected,
            "hwnd": hwnd_hex,
            "window_title": win_title or "Camfrog Room Window",
            "window_rect": win_rect,
            "calibrated_reference_rect": (1273, 0, 2567, 1399),
            "is_right_half_2560x1440": is_right_half,
            "scaled_chat_input_rect": self.adapter._scale_rect(cal_rect),
            "calibrated_chat_input_screen_pt": self.adapter.calibrated_chat_input_screen_pt or (1946, 1223),
            "calibrated_talk_button_screen_pt": self.adapter.calibrated_talk_button_screen_pt or (1326, 1182),
            "scaled_talk_button_rect": self.adapter._scale_rect(self.adapter.calibrated_talk_button_rect or TALK_BUTTON_RECT),
            "scaled_active_speaker_rect": self.adapter._scale_rect(ACTIVE_SPEAKER_RECT),
            "scaled_chat_window_rect": self.adapter._scale_rect(CHAT_WINDOW_RECT),
        }



