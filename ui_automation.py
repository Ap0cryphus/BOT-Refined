"""Camfrog UI Automation adapter with Desktop window enumeration, calibrated rectangles, and VB-Cable TTS."""

from __future__ import annotations

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
}

# Dynamic section headers in User List [l=2359, r=2559] such as "YOU ARE VIEWING 3", "VIEWING 2", "LURKERS 18"
_USER_LIST_HEADER_RE = re.compile(
    r"^\s*(?:"
    r"you\s*are\s*viewing(?:\s*[:()\-]*\s*\d+\s*\)?)?|"
    r"youareviewing\d*|"
    r"viewing(?:\s*[:()\-]*\s*\d+\s*\)?)?|"
    r"lurkers?(?:\s*[:()\-]*\s*\d+\s*\)?)?|"
    r"users?(?:\s*[:()\-]*\s*\d+\s*\)?)?|"
    r"members?(?:\s*[:()\-]*\s*\d+\s*\)?)?|"
    r"friends?(?:\s*[:()\-]*\s*\d+\s*\)?)?|"
    r"top\s*gifters?(?:\s*[:()\-]*\s*\d+\s*\)?)?|"
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

_INLINE_PRESENCE_RE = re.compile(
    r"^\s*(?:(?P<kw>join|quit|left)\s*:\s*(?P<user1>[A-Za-z0-9_$.\-\[\]@~^]{2,32})|"
    r"(?P<user2>[A-Za-z0-9_$.\-\[\]@~^]{2,32})\s+has\s+(?P<verb>joined|left|quit)(?:\s+the\s+room)?)\s*[.!]?\s*$",
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


def is_user_list_header(value: str) -> bool:
    """Return True for 'YOU ARE VIEWING #', 'VIEWING #', 'LURKERS #', or similar section headers."""
    raw = str(value or "").strip()
    if not raw:
        return True
    if _USER_LIST_HEADER_RE.fullmatch(raw):
        return True
    lower = raw.lower()
    if "you are viewing" in lower or "youareviewing" in lower:
        return True
    if re.search(r"\b(?:viewing|lurkers?)\s*[:()\-]*\s*\d+", lower):
        return True
    compact = re.sub(r"[^a-z0-9]", "", lower)
    if (
        compact.startswith("youareviewing")
        or compact.startswith("viewing")
        or compact.startswith("lurkers")
        or compact.startswith("giftusers")
        or compact.startswith("topgifters")
    ):
        return True
    return False


def clean_username(value: str, rect_tuple: tuple[int, int, int, int] | None = None) -> str:
    """Return a valid Camfrog username, or an empty string for UI chrome, VIEWING #, LURKERS #, or ignored rects."""
    if is_ignored_listitem_rect(rect_tuple):
        return ""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if _CLOCK_RE.fullmatch(raw) or re.fullmatch(r"\d{3,4}(?:AM|PM)", raw, re.I):
        return ""
    if is_user_list_header(raw):
        return ""
    # Strip leading @ mention prefix while keeping valid special characters
    trimmed = raw.lstrip("@").strip()
    name = re.sub(r"[^A-Za-z0-9_$.\-\[\]~^]", "", trimmed)[:32]
    lower = name.lower()
    if not name or lower in _PANEL_LABELS or is_user_list_header(name):
        return ""
    return name if _USERNAME_RE.fullmatch(name) else ""


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

    @staticmethod
    def _extract_control_text(control: Any, info: Any) -> str:
        """Extract text from UIA Name, window_text, ValuePattern, TextPattern, or LegacyIAccessible."""
        parts: list[str] = []
        for getter in (
            lambda: info.name,
            lambda: control.window_text(),
            lambda: getattr(control.iface_value, "CurrentValue", ""),
            lambda: control.iface_text.DocumentRange.GetText(-1),
            lambda: (control.legacy_properties() or {}).get("Value", ""),
            lambda: (control.legacy_properties() or {}).get("Name", ""),
        ):
            try:
                val = getter()
                if val and isinstance(val, str) and val.strip():
                    cleaned = val.strip()
                    if cleaned not in parts:
                        parts.append(cleaned)
            except Exception:
                continue
        if not parts:
            try:
                texts = [t.strip() for t in control.texts() if isinstance(t, str) and t.strip()]
                if texts:
                    return "\n".join(texts)
            except Exception:
                pass
            return ""
        # Return the longest/most complete representation
        return max(parts, key=len)

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
        # 1. Exact calibrated Pane(50033) / Edit / Document at [l=1396,t=1206,r=2497,b=1241]
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

        # 2. Fallback to any Edit control in lower portion of window
        bounds = self._window_rect()
        if bounds is not None:
            _, top, _, bottom = bounds
            edits = [node for node in node_list if node.control_type == "Edit" and node.top >= top + (bottom - top) * 0.55]
            if edits:
                return max(edits, key=lambda node: node.width * node.height)
        return None

    @staticmethod
    def _find_active_speaker_node(nodes: Iterable[UIANode]) -> UIANode | None:
        """Locate the Active Microphone Speaker Button(50000) at [l=1506,t=1174,r=1548,b=1190]."""
        sl, st, sr, sb = ACTIVE_SPEAKER_RECT
        node_list = list(nodes)
        # 1. Check calibrated Button(50000) at [l=1506,t=1174,r=1548,b=1190] (right edge can stretch with name length)
        primary = [
            node for node in node_list
            if node.control_type in {"Button", "Text", "Custom", "Pane"}
            and abs(node.left - sl) <= 35
            and abs(node.top - st) <= 20
            and abs(node.bottom - sb) <= 20
            and clean_username(node.name, node.rect_tuple)
        ]
        if primary:
            return min(primary, key=lambda n: abs(n.left - sl) + abs(n.top - st))

        # 2. Fallback: any speaker indicator immediately to the right of Talk Button [1291,1169,1361,1195]
        tl, tt, tr, tb = TALK_BUTTON_RECT
        fallback = [
            node for node in node_list
            if (node.class_name == "CButtonTS" or node.control_type in {"Button", "Text", "Custom"})
            and clean_username(node.name, node.rect_tuple)
            and abs(node.top - st) <= 30
            and 0 <= node.left - tr <= 320
        ]
        return min(fallback, key=lambda n: abs(n.left - sl)) if fallback else None

    def get_active_speaker(self, refresh: bool = False) -> str | None:
        """Read the active speaker username at [l=1506,t=1174,r=1548,b=1190]. Returns None when empty/erased."""
        node = self._find_active_speaker_node(self.nodes(refresh=refresh))
        if node is None:
            return None
        cleaned = clean_username(node.name, node.rect_tuple)
        return cleaned or None

    def is_mic_free(self, refresh: bool = True) -> bool:
        """Return True when no username is flowing in Active Speaker [l=1506,t=1174,r=1548,b=1190]."""
        return self.get_active_speaker(refresh=refresh) is None

    def get_user_list(self, refresh: bool = False) -> list[str]:
        """Extract usernames from User List(50008) [l=2359,t=141,r=2559,b=1160] trending along [l=2359,r=2559].

        Removes 'YOU ARE VIEWING #' / 'VIEWING #' and 'LURKERS #' headers and scans up/down
        along the [l=2359, r=2559] coordinate trend for up to MAX_ROOM_USERS (100) users.
        """
        ul_left, ul_top, ul_right, ul_bottom = USER_LIST_RECT
        span_l, span_r = USER_LIST_ITEM_X_SPAN

        candidates: list[UIANode] = []
        for node in self.nodes(refresh=refresh):
            if is_ignored_listitem_rect(node.rect_tuple):
                continue
            # Skip the parent List(50008) container itself
            if node.control_type == "List" and node.height > 200:
                continue
            # Match items trending on [l=2359, r=2559] (or inside [2359..2559] within vertical bounds [141..1160])
            matches_x_trend = (
                (abs(node.left - span_l) <= 15 and abs(node.right - span_r) <= 15)
                or (node.left >= ul_left - 15 and node.right <= ul_right + 15 and abs(node.right - span_r) <= 15)
            )
            in_y_bounds = (node.top >= ul_top - 15) and (node.bottom <= ul_bottom + 15)
            if not (matches_x_trend and in_y_bounds):
                continue
            if node.control_type not in {"ListItem", "Text", "Hyperlink", "Custom", "Pane", "Button"}:
                continue
            candidates.append(node)

        # Sort vertically top-to-bottom so dynamic position changes are scanned cleanly
        candidates.sort(key=lambda n: (n.top, n.left))

        users: list[str] = []
        seen_lower: set[str] = set()
        for node in candidates:
            for line in str(node.name or "").splitlines():
                raw_line = line.strip()
                if not raw_line or is_user_list_header(raw_line):
                    continue
                user = clean_username(raw_line, node.rect_tuple)
                if user and user.lower() not in seen_lower:
                    seen_lower.add(user.lower())
                    users.append(user)
                    if len(users) >= MAX_ROOM_USERS:
                        return users
        return users

    def get_user_count(self, refresh: bool = False) -> int:
        """Return the number of active users in the room from the trending [l=2359,r=2559] user list (max 100)."""
        return len(self.get_user_list(refresh=refresh))

    @staticmethod
    def _parse_text_tokens_into_events(tokens: list[tuple[str, str]]) -> list[dict[str, str]]:
        """Parse a sequence of (control_type, text) items from the Chat Window into structured events."""
        # Expand any multi-line text blocks into individual lines while keeping original tokens
        flat: list[tuple[str, str]] = []
        for ctrl_type, raw_text in tokens:
            lines = [ln.strip() for ln in str(raw_text or "").splitlines() if ln.strip()]
            for ln in lines:
                flat.append((ctrl_type, ln))

        events: list[dict[str, str]] = []
        for index, (control_type, name) in enumerate(flat):
            lowered = name.lower().strip()
            if is_user_list_header(name):
                continue

            # 1. Multi-node Join: / Quit:
            if lowered in {"join:", "quit:", "left:"}:
                action = "join" if lowered == "join:" else "quit"
                user = clean_username(flat[index + 1][1]) if index + 1 < len(flat) else ""
                if user:
                    events.append({"kind": "presence", "action": action, "user": user, "text": "", "timestamp": ""})
                continue

            # 2. Single-line Join: <user> / Quit: <user> / <user> has joined/left
            pres_match = _INLINE_PRESENCE_RE.match(name)
            if pres_match:
                if pres_match.group("kw"):
                    action = "join" if pres_match.group("kw").lower() == "join" else "quit"
                    user = clean_username(pres_match.group("user1"))
                else:
                    action = "join" if pres_match.group("verb").lower() == "joined" else "quit"
                    user = clean_username(pres_match.group("user2"))
                if user:
                    events.append({"kind": "presence", "action": action, "user": user, "text": "", "timestamp": ""})
                continue

            # 3. Standalone Moderation Notice line (e.g. "Mod_1 kicked User_2." or "User_2 was kicked by Mod_1.")
            mod_match = _MOD_LINE_RE.match(name)
            if mod_match:
                actor = clean_username(mod_match.group("actor") or mod_match.group("actor2") or "")
                target = clean_username(mod_match.group("target") or mod_match.group("target2") or "")
                if actor and target:
                    events.append({"kind": "message", "user": actor, "text": name.strip(), "timestamp": ""})
                    continue

            # 4. Multi-node [User, Clock, Message] sequence
            if _CLOCK_RE.fullmatch(name.strip()) and index > 0:
                user = clean_username(flat[index - 1][1])
                if not user:
                    continue
                body = ""
                for _, candidate in flat[index + 1:index + 4]:
                    cand_strip = candidate.strip()
                    if (
                        cand_strip
                        and not _CLOCK_RE.fullmatch(cand_strip)
                        and cand_strip.lower() not in {"join:", "quit:", "left:"}
                    ):
                        body = cand_strip
                        break
                if body:
                    events.append({"kind": "message", "user": user, "text": body, "timestamp": name.strip()})
                continue

            # 5. Single-line "[6:36 PM] User: message" or "User: message"
            inline_match = _INLINE_CHAT_RE.match(name)
            if inline_match:
                user = clean_username(inline_match.group("user"))
                body = (inline_match.group("body") or "").strip()
                ts = (inline_match.group("ts1") or inline_match.group("ts2") or "").strip()
                if user and body:
                    events.append({"kind": "message", "user": user, "text": body, "timestamp": ts})

        return events

    def get_chat_events(self, limit: int = 200) -> list[dict[str, str]]:
        """Parse chat & moderation events from Chat Window Pane(50033)/Text(50020) [l=1281,t=170,r=2355,b=1160].

        Falls back to Top Gifters / combined Text(50020) [l=1281,t=71,r=2559,b=1160] only if primary
        Chat Window nodes yielded no events.
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
            and node.bottom <= cb + 15
        ]

        # Sort by vertical position then horizontal position so chat lines flow chronologically
        primary_chat_nodes.sort(key=lambda n: (n.top, n.left))
        events = self._parse_text_tokens_into_events([(n.control_type, n.name) for n in primary_chat_nodes])

        # Fallback: check Top Gifters / Outer Text(50020) [l=1281,t=71,r=2559,b=1160] if primary had no events
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

        node = self._find_chat_input(self.nodes(refresh=True))
        il, it, ir, ib = self._rect(node) or CHAT_INPUT_RECT
        cx, cy = (il + ir) // 2, (it + ib) // 2  # (1946, 1223)

        try:
            # Because Pane(50033) [1396,1206,2497,1241] has IsKeyboardFocusable=False,
            # click its center coordinate first to focus the CEF text input.
            if uia_click is not None:
                uia_click(coords=(cx, cy))
                time.sleep(0.08)

            if node is not None and node.control is not None:
                try:
                    node.control.set_edit_text(cleaned)
                    node.control.type_keys("{ENTER}", set_foreground=False)
                    return True
                except Exception:
                    try:
                        node.control.type_keys(cleaned, with_spaces=True, set_foreground=False)
                        node.control.type_keys("{ENTER}", set_foreground=False)
                        return True
                    except Exception:
                        pass

            if uia_send_keys is not None:
                # Escape pywinauto special brace characters in plain chat text
                escaped = re.sub(r"([+^%~(){}])", r"{\1}", cleaned)
                uia_send_keys(escaped, with_spaces=True, pause=0.01)
                uia_send_keys("{ENTER}", pause=0.02)
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
        """Wait until 'KaeKae_Toad' persists at Active Speaker [l=1506,t=1174,r=1548,b=1190] for 1.3s."""
        deadline = time.monotonic() + max(persist_seconds + 0.5, timeout_seconds)
        seen_since: float | None = None
        target_lower = bot_username.casefold()

        while time.monotonic() < deadline:
            speaker = self.get_active_speaker(refresh=True)
            if speaker and speaker.casefold() == target_lower:
                if seen_since is None:
                    seen_since = time.monotonic()
                elif time.monotonic() - seen_since >= persist_seconds:
                    return True
            else:
                seen_since = None
            time.sleep(0.05)
        return False

    def broadcast_tts_via_vbcable(self, text: str, dry_run: bool = False) -> bool:
        """Broadcast speech over VB-Cable ('CABLE Input') using Talk Button [l=1291,t=1169,r=1361,b=1195]:
        1. Wait until Active Speaker [l=1506,t=1174,r=1548,b=1190] is empty (no user on mic).
        2. Perform 2 quick clicks on Talk Button [1291,1169,1361,1195], then press & hold.
        3. Wait until 'KaeKae_Toad' persists in [1506,1174,1548,1190] for 1.3 seconds.
        4. Play TTS WAV audio over VB-Cable while holding button.
        5. Release Talk Button to finish broadcast and let other users take the microphone.
        """
        cleaned_text = str(text or "").strip()
        if not cleaned_text or not VB_CABLE_TTS_ENABLED:
            return False
        if dry_run:
            return True

        # Do not click Talk Button if another user's name is flowing in [1506,1174,1548,1190]
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

            # Perform 2 quick clicks and then hold Talk Button [1291,1169,1361,1195]
            try:
                if uia_click is not None:
                    uia_click(coords=(cx, cy))
                    time.sleep(TALK_DOUBLE_CLICK_DELAY)
                    uia_click(coords=(cx, cy))
                    time.sleep(TALK_DOUBLE_CLICK_DELAY)
                if uia_press is not None:
                    uia_press(coords=(cx, cy))

                # Wait until "KaeKae_Toad" persists at [1506,1174,1548,1190] for 1.3 seconds before starting audio
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
        """Play WAV file specifically to 'CABLE Input (VB-Audio Virtual Cable)' if sounddevice is present."""
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
