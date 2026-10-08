"""Camfrog UI Automation adapter.

This module deliberately uses only the Windows UI Automation tree exposed by
Camfrog/CEF. It never imports screen capture, DXCam, OpenCV, Pillow, or
Tesseract. Coordinates are diagnostic metadata derived from live UIA rectangles
and are never used to read pixels.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

from config import CAMFROG_WINDOW_TITLE_RE, UIA_CACHE_SECONDS, ROOM_TAB_POSITIONS

try:
    from pywinauto import Application, Desktop
except ImportError:  # Allows offline parser tests and a useful setup message.
    Application = None
    Desktop = None


_CLOCK_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?$", re.I)
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_$-]{2,32}$")
_PANEL_LABELS = {
    "talk", "push-to-talk", "camfrog", "users", "user", "members", "lurkers",
    "youareviewing", "search", "gifts", "giftusers", "yourvideo", "room", "chat",
}


def clean_username(value: str) -> str:
    """Return a valid Camfrog username, or an empty string for UI chrome."""
    raw = str(value or "").strip()
    if _CLOCK_RE.fullmatch(raw) or re.fullmatch(r"\d{3,4}(?:AM|PM)", raw, re.I):
        return ""
    name = re.sub(r"[^A-Za-z0-9_$-]", "", raw)[:32]
    lower = name.lower()
    # Camfrog exposes the toolbar as ``GIFTUsers2`` in some UIA trees. It is
    # visually username-shaped but must never pollute the presence database.
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
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)


class CamfrogUIAutomation:
    """Connect to a live Camfrog room and expose its textual UIA state."""

    def __init__(self, title_re: str = CAMFROG_WINDOW_TITLE_RE, cache_seconds: float = UIA_CACHE_SECONDS):
        self.title_re = title_re
        self.cache_seconds = cache_seconds
        self.app: Any = None
        self.window: Any = None
        self._nodes: list[UIANode] = []
        self._nodes_at = 0.0
        self.last_error = ""

    def connect_to_camfrog(self) -> bool:
        """Attach to the room window with the richest CEF/UIA control tree."""
        if Application is None:
            self.last_error = "pywinauto is not installed; run setup_bot.py in .venv."
            return False
        try:
            # First, try to connect using the title pattern as before
            try:
                app = Application(backend="uia").connect(title_re=self.title_re)
                candidates = app.windows()
            except Exception:
                # If that fails, try alternative approaches
                print("DEBUG: Title-based connection failed, trying alternative approach")
                try:
                    # Try to connect to any window with a process name containing camfrog
                    app = Application(backend="uia").connect(process="camfrog")
                    candidates = app.windows()
                    print("DEBUG: Connected using process name matching")
                except Exception:
                    # If that fails, try to connect to any window and filter manually
                    print("DEBUG: Process-based connection failed, connecting to all windows")
                    app = Application(backend="uia").connect()
                    candidates = app.windows()
            
            # Login/contact windows can match the title. A room has CEF controls
            # (CButtonTS) and a sizeable client rectangle, so score those first.
            best, best_score = None, -1
            
            print(f"DEBUG: Found {len(candidates)} candidate windows")
            
            for i, candidate in enumerate(candidates):
                try:
                    rect = candidate.rectangle()
                    score = rect.width() * rect.height() // 10000
                    cbutton_count = len(candidate.descendants(class_name="CButtonTS"))
                    score += cbutton_count * 110  # Slightly higher weight for CButtonTS
                    
                    print(f"DEBUG: Window {i+1} - Title: '{candidate.window_text()}'")
                    print(f"DEBUG:   Size: {rect.width()} x {rect.height()}, CButtonTS count: {cbutton_count}, Score: {score}")
                    
                    if score > best_score:
                        best, best_score = candidate, score
                except Exception as e:
                    print(f"DEBUG: Error processing window {i+1}: {e}")
                    continue
            
            # If we still have multiple matches with same score or no good matches,
            # try to be more specific by checking window properties
            if best is None and len(candidates) > 0:
                print("DEBUG: No best window found, trying alternative selection")
                # Try selecting the first one that has CButtonTS controls (which indicates a room)
                for candidate in candidates:
                    try:
                        cbutton_count = len(candidate.descendants(class_name="CButtonTS"))
                        if cbutton_count > 0:
                            best = candidate
                            print(f"DEBUG: Selected window with CButtonTS controls: '{candidate.window_text()}'")
                            break
                    except Exception as e:
                        print(f"DEBUG: Error checking for CButtonTS: {e}")
                        continue
            
            # If we still don't have a good window, just use the first one that looks like a room
            if best is None and len(candidates) > 0:
                print("DEBUG: No best window found, using first candidate as fallback")
                best = candidates[0]
            
            self.app = app
            self.window = best if best is not None else app.top_window()
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
                left=int(rect.left), top=int(rect.top), right=int(rect.right), bottom=int(rect.bottom),
                control=control,
            )
        except Exception:
            return None

    def nodes(self, refresh: bool = False) -> list[UIANode]:
        """Return ordered UIA nodes. A short cache avoids repeated full-tree walks."""
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
        """Live UIA-derived locations for diagnostics/calibration, not capture."""
        bounds = self._window_rect()
        if bounds is None:
            return {"window": None, "chat_feed": None, "user_list": None, "chat_input": None, "talk": None}
        left, top, right, bottom = bounds
        width = right - left
        nodes = self.nodes()
        talk = self._find_talk(nodes)
        edit = self._find_chat_input(nodes)
        return {
            "window": bounds,
            "chat_feed": (left, top, left + int(width * 0.78), bottom),
            "user_list": (left + int(width * 0.78), top, right, bottom),
            "chat_input": self._rect(edit),
            "talk": self._rect(talk),
        }

    @staticmethod
    def _rect(node: UIANode | None) -> tuple[int, int, int, int] | None:
        return None if node is None else (node.left, node.top, node.right, node.bottom)

    @staticmethod
    def _find_talk(nodes: Iterable[UIANode]) -> UIANode | None:
        return next((node for node in nodes if node.control_type == "Button" and node.name.lower().strip() in {"talk", "push-to-talk", "push to talk"}), None)

    def _find_chat_input(self, nodes: Iterable[UIANode]) -> UIANode | None:
        bounds = self._window_rect()
        if bounds is None:
            return None
        _, top, _, bottom = bounds
        edits = [node for node in nodes if node.control_type == "Edit" and node.top >= top + (bottom - top) * 0.55]
        return max(edits, key=lambda node: node.width * node.height, default=None)

    def get_active_speaker(self) -> str | None:
        """Read the name exposed immediately to the right of the Talk button."""
        nodes = self.nodes()
        talk = self._find_talk(nodes)
        if talk is None:
            return None
        candidates = [
            node for node in nodes
            if node.class_name == "CButtonTS" and clean_username(node.name)
            and abs(node.top - talk.top) <= 30 and 0 <= node.left - talk.right <= 260
        ]
        return min(candidates, key=lambda node: node.left).name if candidates else None

    def get_user_list(self) -> list[str]:
        """Extract visible roster usernames from the right-hand UIA panel."""
        bounds = self._window_rect()
        if bounds is None:
            return []
        left, _, right, _ = bounds
        roster_left = left + int((right - left) * 0.78)
        users: list[str] = []
        for node in self.nodes():
            if node.left < roster_left or node.control_type not in {"ListItem", "Text", "Hyperlink"}:
                continue
            user = clean_username(node.name)
            if user and user.lower() not in {item.lower() for item in users}:
                users.append(user)
        return users

    def get_user_count(self) -> int:
        return len(self.get_user_list())

    def get_chat_events(self, limit: int = 200) -> list[dict[str, str]]:
        """Parse Camfrog's UIA chat sequence without treating arbitrary text as chat.

        Camfrog commonly exposes messages as Hyperlink(username), Text(clock),
        Text(body), and presence notices as Text('Join:'/'Quit:'), Text(username).
        """
        flat = [(node.control_type, node.name) for node in self.nodes() if node.name]
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
        # Newer CEF builds occasionally expose one complete line rather than
        # sibling controls. Support only the explicit 'username: body' shape.
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
        """Put one already-sized message into Camfrog's chat edit and submit it."""
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

    def get_current_room(self) -> str | None:
        """
        Determine which room the bot is currently in by examining tab positions.
        
        Returns:
            Room name if found, None otherwise
        """
        if not self.window:
            if not self.connect_to_camfrog():
                return None
                
        try:
            # Get all nodes and find tab controls
            nodes = self.nodes(refresh=True)
            
            # Look for tab elements that have positions matching our known room tabs
            for node in nodes:
                # Check if this node is a tab-like element (Button, Hyperlink, Custom)
                if (node.control_type in ["Button", "Hyperlink", "Custom"] and 
                    hasattr(node, 'left') and hasattr(node, 'top') and 
                    hasattr(node, 'right') and hasattr(node, 'bottom')):
                    
                    # Get the position of this node
                    x = (node.left + node.right) // 2  # Center X coordinate
                    y = (node.top + node.bottom) // 2  # Center Y coordinate
                    
                    # Check if this position matches any known room tab
                    room_name = self.find_room_by_position(x, y)
                    if room_name:
                        return room_name
                        
            # If we can't determine from node positions, try a different approach
            # Get the main window's coordinates and look for tab elements
            if self.window:
                window_left = self.window.left
                window_top = self.window.top
                
                # Try to find a tab in the header area (y around 37)
                for node in nodes:
                    if (node.control_type in ["Button", "Hyperlink", "Custom"] and 
                        node.top >= 30 and node.top <= 80 and  # Around header area
                        node.left > 0):  # Valid position
                        # Use the center of the node to check which room it belongs to
                        x = (node.left + node.right) // 2
                        y = (node.top + node.bottom) // 2
                        room_name = self.find_room_by_position(x, y)
                        if room_name:
                            return room_name
                        
            return None
            
        except Exception as error:
            self.last_error = f"Failed to determine current room: {error}"
            return None

    def find_room_by_position(self, x: int, y: int) -> str | None:
        """
        Find which room tab a position belongs to based on tab positions.
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            Room name if found, None otherwise
        """
        # Get all tab positions from config
        for room_name, pos in ROOM_TAB_POSITIONS.items():
            left, top, right, bottom = pos
            
            # Check if the position is within this tab's bounds
            if (left <= x <= right) and (top <= y <= bottom):
                return room_name
                
        return None

    def switch_to_room_by_position(self, x: int, y: int) -> bool:
        """
        Switch to a room by clicking on the tab at position (x, y).
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            True if successful, False otherwise
        """
        if not self.window:
            if not self.connect_to_camfrog():
                return False
                
        # Find which room this position corresponds to
        room_name = self.find_room_by_position(x, y)
        if not room_name:
            self.last_error = f"No room found at position ({x}, {y})"
            return False
            
        try:
            # Get all nodes and find the tab control
            nodes = self.nodes(refresh=True)
            
            # Look for a button or clickable element near the position that corresponds to this room
            for node in nodes:
                if (node.control_type == "Button" or 
                    node.control_type == "Hyperlink" or 
                    node.control_type == "Custom") and \
                   node.left <= x <= node.right and \
                   node.top <= y <= node.bottom:
                    # Click the tab
                    try:
                        node.control.click_input()
                        time.sleep(0.5)  # Wait for room change to complete
                        return True
                    except Exception as e:
                        self.last_error = f"Failed to click tab: {e}"
                        return False
            
            # If we couldn't find a specific control, just log that we found the room
            print(f"DEBUG: Found room '{room_name}' at position ({x}, {y}), but couldn't click it directly")
            return True
            
        except Exception as error:
            self.last_error = f"Room switching failed: {error}"
            return False
