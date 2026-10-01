"""Room presence: who is in the Camfrog room, and when they came or went.

Three separate problems live here, and they have genuinely different levels of
confidence, so they are kept apart rather than merged into one "presence" idea.

1. JOIN / QUIT EVENTS.
   Camfrog prints "Join: tajnysmiral" and "Quit: tajnysmiral" into the chat feed
   with NO timestamp of any kind - not on the line, not in the chat node. The
   only ordering signal is POSITION: a join appearing below a quit happened
   after it. So the honest timestamp for these events is the PC clock at the
   moment we OBSERVE the line, and the ordering is preserved separately as a
   monotonic sequence number. We never pretend to know the second it happened.

2. THE RIGHT-HAND ROSTER PANEL.
   Camfrog docks a panel on the right of the chat feed reading
   "YOU ARE VIEWING <n>", "MEMBERS <n>" and "LURKERS <n>", listing every user in
   the room as of right now. This is a true snapshot of the present, unlike the
   chat feed which is a historical scrollback. It is read through UIA control
   text, and the header counts are parsed from the header lines themselves.

3. CURSOR HOVER SUPPRESSES THE EVENT FEED.
   While the mouse cursor sits over that roster panel, Camfrog stops emitting
   the Join/Quit lines - the notifications are suppressed, not merely hidden.
   So while hovering we are BLIND to arrivals and departures, and the only
   trustworthy refresh is to re-read the roster panel itself. That is why
   cursor_position_over_roster() exists: while it returns True, the event feed
   must not be treated as authoritative and the roster must be re-read.

Everything here is deliberately dependency-light and testable WITHOUT Camfrog:
pure parsing helpers take plain strings, and only the UIA readers need a window.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 1. Join / Quit parsing
# ---------------------------------------------------------------------------

_JOIN_RE = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)?(?:(\w+)\s+)?(join|joined|enter|entered)\b\s*:?\s*(.+?)\s*$",
    re.IGNORECASE)
_QUIT_RE = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)?(?:(\w+)\s+)?(quit|quits|left|leaves|exit|exited)\b\s*:?\s*(.+?)\s*$",
    re.IGNORECASE)
_SUBJ_LEFT_RE = re.compile(
    r"^\s*([A-Za-z0-9_$\-]{2,32})\s+(?:has\s+|have\s+)?(?:left|quit|disconnected|exited)\b.*$",
    re.IGNORECASE)
_SUBJ_JOIN_RE = re.compile(
    r"^\s*([A-Za-z0-9_$\-]{2,32})\s+(?:has\s+|have\s+)?(?:joined|entered)\b.*$",
    re.IGNORECASE)

# Noise that must never be mistaken for a username.
_NOT_A_USER = {
    "you", "user", "someone", "somebody", "he", "she", "they", "it", "the",
    "a", "an", "admin", "operator", "camfrog", "room", "chat", "mic",
    "microphone", "camera", "system", "server",
}


def clean_username(raw: str) -> str:
    """Normalises a candidate username to Camfrog's charset.

    Camfrog usernames are letters, digits, underscore, hyphen and '$'. Anything
    else is punctuation introduced by OCR or by the notice wording itself, so it
    is stripped rather than trusted."""
    if not raw:
        return ""
    txt = str(raw).strip().strip(":").strip()
    # Drop a trailing clause such as ", with a camera" or " microphone".
    txt = re.split(r"\s+(?:microphone|camera|with|and)\b", txt,
                   flags=re.IGNORECASE)[0]
    return re.sub(r"[^A-Za-z0-9_$\-]", "", txt)[:32]


def _valid(user: str) -> bool:
    if not user or len(user) < 2:
        return False
    return user.lower() not in _NOT_A_USER


def parse_join_quit(text: str) -> Optional[Dict[str, str]]:
    """Parses a Camfrog join/quit notice.

    Returns {"action": "join"|"quit", "user": "<name>", "timestamped": "no"}
    or None when the line is not a join/quit notice at all.

    `timestamped` is always "no": these notices genuinely carry no clock, and
    recording them as if they did would put a fabricated second in the audit log.
    """
    if not text:
        return None
    line = str(text).strip()
    if not line or len(line) > 160:
        return None

    # Quit first: "Quit" also matches the trailing words of some join notices
    # only after cleanup, and quit is the rarer/dangerous one to get right.
    for regex, action, group in (
            (_QUIT_RE, "quit", 3), (_JOIN_RE, "join", 3),
            (_SUBJ_LEFT_RE, "quit", 1), (_SUBJ_JOIN_RE, "join", 1)):
        m = regex.match(line)
        if not m:
            continue
        user = clean_username(m.group(group))
        if _valid(user):
            return {"action": action, "user": user, "timestamped": "no"}
    return None


# ---------------------------------------------------------------------------
# 2. Roster panel parsing
# ---------------------------------------------------------------------------

_COUNT_HEADERS = {
    "YOU ARE VIEWING": "viewing",
    "MEMBERS": "members",
    "LURKERS": "lurkers",
}


def parse_roster_header(line: str) -> Optional[Tuple[str, int]]:
    """Parses a roster header, tolerating OCR damage.

    OCR of this panel reliably loses the SPACES and often prefixes a stray glyph,
    so a real header arrives as "vYOUAREVIEWING0", "iMEMBERS0" or "ALURKERS2"
    rather than "LURKERS 2". Matching is therefore done on a
    letters-and-digits-only normalisation, scanning for the header anywhere in
    the line rather than anchoring to the start.

    Returns (bucket, count) or None. A header whose digits are unreadable
    returns -1 for UNKNOWN, never 0 - claiming an empty room we did not read
    would mark everyone as gone.
    """
    if not line:
        return None
    compact = re.sub(r"[^A-Za-z0-9]", "", str(line)).upper()
    if not compact:
        return None
    # Longest-first so "MEMBERS" is not shadowed by a shorter prefix and
    # "YOUAREVIEWING" is matched before a stray "VIEWING".
    for header, key in sorted(_COUNT_HEADERS.items(), key=lambda kv: -len(kv[0])):
        token = re.sub(r"[^A-Za-z0-9]", "", header).upper()
        idx = compact.find(token)
        if idx < 0:
            continue
        tail = compact[idx + len(token):]
        digits = re.sub(r"\D", "", tail)
        # Digits BEFORE the header are noise, not a count.
        return key, (int(digits) if digits else -1)
    return None


# Non-user chrome that sits in/near the panel and OCRs as username-shaped text.
# "GIFTUsers2" is the GIFTs/Users toolbar, not a person.
_UI_LABELS = {
    "gifttusers", "giftusers", "gifts", "users", "user", "username",
    "room", "rooms", "feed", "chat", "search", "add", "close", "menu",
    "yourvideo", "your video", "settings", "help", "invite", "gift",
    "members", "lurkers", "youareviewing", "viewing", "video", "audio",
}


def _is_ui_label(name: str) -> bool:
    norm = str(name or "").replace(" ", "").lower()
    if norm in _UI_LABELS:
        return True
    # OCR runs adjacent labels together and keeps their counters, so the GIFTs /
    # Users toolbar reads "GIFTUsers2". Strip trailing digits and retry.
    stripped = re.sub(r"\d+$", "", norm)
    return bool(stripped) and stripped in _UI_LABELS


def looks_like_username(text: str) -> bool:
    """True when an OCR'd line is clean enough to trust as a username.

    The panel OCR produces strings like "BRE1IshtickieO" - real name buried in
    garbage. Rather than store a mangled name as fact, this requires the line to
    be ALREADY a valid username with no surrounding junk, and to not be one of
    the panel's own UI labels."""
    raw = (text or "").strip()
    if not raw or len(raw) < 2 or len(raw) > 32:
        return False
    if not re.fullmatch(r"[A-Za-z0-9_$\-]+", raw):
        return False
    return not _is_ui_label(raw)



def match_known_users(ocr_lines: List[str], known_users: List[str],
                      min_len: int = 3) -> List[str]:
    """Identifies which KNOWN users appear in a set of OCR'd panel lines.

    Raw OCR of this panel is not trustworthy as a name source - it returns things
    like "b1HShtickie Pm" where the real name is buried in glyph noise.
    Inventing "b1HShtickie" as a user would poison the presence record and every
    later recall answer about that person.

    So the blob is only ever used to CONFIRM a name we already know about
    (from chat history or an earlier room scan). A user counts as present when
    their name appears as a substring of some line, compared case-insensitively.
    This can miss a name the OCR mangled beyond recognition, but it cannot
    fabricate one - a miss is recoverable, a false identity is not.
    """
    blob = " ".join(str(x) for x in (ocr_lines or [])).lower()
    if not blob:
        return []
    found: List[str] = []
    for user in (known_users or []):
        name = str(user or "").strip()
        if len(name) < min_len or name.lower() in _NOT_A_USER:
            continue
        if name.lower() in blob and name not in found:
            found.append(name)
    return found


def parse_roster_block(lines: List[str]) -> Dict[str, Any]:
    """Parses the roster panel's text into counts plus a list of names.

    `lines` is the panel's visible text in order. Names are the non-header
    lines; anything that parses as a count header is excluded from the names."""
    counts: Dict[str, int] = {}
    names: List[str] = []
    for raw in lines or []:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        head = parse_roster_header(text)
        if head:
            counts[head[0]] = head[1]
            continue
        name = clean_username(text)
        # Only lines that are ALREADY clean usernames count as names. OCR of this
        # panel yields "BRE1IshtickieO"; storing that as a user would put a
        # fabricated name into the presence record and into recall answers.
        if looks_like_username(text) and _valid(name) and name not in names:
            names.append(name)
    return {"counts": counts, "users": names,
            "reading_ok": bool(counts) or bool(names)}


def cursor_position_over_roster(cursor_xy: Optional[Tuple[int, int]],
                                roster_rect: Optional[Tuple[int, int, int, int]]) -> bool:
    """True when the cursor is inside the roster panel's rectangle.

    While this is True the Join/Quit feed is SUPPRESSED by Camfrog, so the bot is
    blind to arrivals and departures and must re-read the panel instead of
    trusting the event stream.

    `roster_rect` is (left, top, width, height) in screen coordinates."""
    if not cursor_xy or not roster_rect:
        return False
    cx, cy = cursor_xy
    left, top, width, height = roster_rect
    return (left <= cx < left + width) and (top <= cy < top + height)


def get_cursor_xy() -> Optional[Tuple[int, int]]:
    """Current cursor position, or None if it cannot be read (headless)."""
    try:
        import ctypes
        from ctypes import wintypes
        pt = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            return (int(pt.x), int(pt.y))
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 3. Presence store - date-stamped, self-pruning
# ---------------------------------------------------------------------------

PRESENCE_TTL_S = 900        # 15 min without a refresh before a user is stale
EVENT_RETENTION_H = 48       # join/quit audit trail
STALE_USER_DAYS = 1          # undated/stale rows are dropped


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def record_event(store: Dict[str, Any], room: str, action: str, user: str,
                 seq: int = 0) -> Dict[str, Any]:
    """Appends a join/quit event, stamped with the PC clock.

    Join/quit notices carry no time of their own, so `observed_at` is when we
    SAW the line and `seq` preserves the true feed ordering. `exact_time` is
    False so nobody later mistakes the observation time for when it happened."""
    events = store.setdefault("events", [])
    events.append({
        "room": room or "",
        "action": action,
        "user": user,
        "observed_at": _now_iso(),
        "observed_at_display": datetime.now().strftime("(%m/%dI%H:%M:%S)"),
        "seq": int(seq),
        "exact_time": False,
        "timestamped": "no",
        "source": "chat_feed",
    })
    prune_events(store)
    return events[-1]


def prune_events(store: Dict[str, Any]) -> int:
    """Drops events past the retention window, and any with no usable date.

    An event whose date cannot be established is worthless for recall, so it is
    removed rather than kept as noise."""
    events = store.get("events")
    if not isinstance(events, list):
        return 0
    cutoff = datetime.now() - timedelta(hours=EVENT_RETENTION_H)
    kept, dropped = [], 0
    for ev in events:
        seen = _parse_iso((ev or {}).get("observed_at"))
        if seen is None or seen < cutoff:
            dropped += 1
            continue
        kept.append(ev)
    store["events"] = kept
    return dropped


def apply_roster(store: Dict[str, Any], room: str, users: List[str],
                 counts: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Replaces the present-user set for a room from a fresh panel read.

    The panel is a true snapshot, so anyone missing from it is treated as GONE
    with `left_reason` "panel", distinguishing a panel refresh from an observed
    Quit notice."""
    rooms = store.setdefault("rooms", {})
    entry = rooms.setdefault(room or "", {"users": {}, "last_snapshot": ""})
    present = entry.setdefault("users", {})
    seen = {u.lower(): u for u in (users or []) if u}
    now = _now_iso()
    joined, left = [], []

    for key, display in seen.items():
        if key not in present:
            present[key] = {"name": display, "first_seen": now,
                            "last_seen": now, "seen_date": now[:10]}
            joined.append(display)
        else:
            present[key]["last_seen"] = now
            present[key]["seen_date"] = now[:10]

    for key in [k for k in present if k not in seen]:
        gone = present.pop(key)
        gone["left_at"] = now
        gone["left_reason"] = "panel"
        entry.setdefault("departed", []).append(gone)
        left.append(gone.get("name", key))

    entry["last_snapshot"] = now
    if counts is not None:
        entry["counts"] = counts
    prune_stale(store)
    return {"joined": joined, "left": left, "present": sorted(seen.values())}


def prune_stale(store: Dict[str, Any]) -> int:
    """Drops users/departures older than STALE_USER_DAYS or with no date.

    Returns the number of records removed."""
    cutoff = datetime.now() - timedelta(days=STALE_USER_DAYS)
    removed = 0
    rooms = store.get("rooms")
    if not isinstance(rooms, dict):
        return 0
    for entry in rooms.values():
        if not isinstance(entry, dict):
            continue
        users = entry.get("users")
        if isinstance(users, dict):
            for key in list(users):
                rec = users[key]
                seen = _parse_iso(rec.get("last_seen")) if isinstance(rec, dict) else None
                if seen is None or seen < cutoff:
                    del users[key]
                    removed += 1
        dep = entry.get("departed")
        if isinstance(dep, list):
            kept = []
            for rec in dep:
                seen = _parse_iso(rec.get("left_at")) if isinstance(rec, dict) else None
                if seen is not None and seen >= cutoff:
                    kept.append(rec)
                else:
                    removed += 1
            entry["departed"] = kept
    prune_events(store)
    return removed


def present_users(store: Dict[str, Any], room: str = "") -> List[str]:
    """Currently-present display names for a room."""
    entry = (store.get("rooms") or {}).get(room or "")
    if not isinstance(entry, dict):
        return []
    users = entry.get("users") or {}
    names = [(u.get("name") or k) for k, u in users.items() if isinstance(u, dict)]
    return sorted(n for n in names if n)


def purge_undated(store: Dict[str, Any]) -> int:
    """Removes every record with no parseable date anywhere in it.

    Used when loading a store written by an older build, so recall never answers
    from a row whose age cannot be established. Records not tied to a named user
    are removed too."""
    removed = 0
    events = store.get("events")
    if isinstance(events, list):
        kept = [e for e in events
                if isinstance(e, dict) and _parse_iso(e.get("observed_at"))
                and str(e.get("user") or "").strip()]
        removed += len(events) - len(kept)
        store["events"] = kept
    rooms = store.get("rooms")
    if isinstance(rooms, dict):
        for entry in rooms.values():
            if not isinstance(entry, dict):
                continue
            users = entry.get("users")
            if isinstance(users, dict):
                for key in list(users):
                    rec = users[key]
                    if (not isinstance(rec, dict)
                            or _parse_iso(rec.get("last_seen")) is None):
                        del users[key]
                        removed += 1
            dep = entry.get("departed")
            if isinstance(dep, list):
                kept = [r for r in dep if isinstance(r, dict)
                        and _parse_iso(r.get("left_at")) is not None
                        and str(r.get("name") or "").strip()]
                removed += len(dep) - len(kept)
                entry["departed"] = kept
    return removed


# ---------------------------------------------------------------------------
# 4. Live UIA reader for the roster panel
# ---------------------------------------------------------------------------


def _rect_tuple(r) -> Optional[Tuple[int, int, int, int]]:
    """Normalises a pywinauto rectangle to (left, top, width, height).

    The codebase sees BOTH shapes depending on the wrapper in play - some expose
    RECT.left as an attribute, others as a method - so calling one style blindly
    raises TypeError. Accept either."""
    def val(name):
        v = getattr(r, name, None)
        if callable(v):
            try:
                v = v()
            except Exception:
                return 0
        try:
            return int(v)
        except Exception:
            return 0
    try:
        return (val("left"), val("top"), val("width"), val("height"))
    except Exception:
        return None


def find_roster_rect(win) -> Optional[Tuple[int, int, int, int]]:
    """Locates the roster panel by its distinctive headers.

    Returns (left, top, width, height) in screen coordinates, or None."""
    if win is None:
        return None
    try:
        wr = _rect_tuple(win.rectangle())
        if not wr:
            return None
        found = []
        for ctrl in win.descendants():
            try:
                name = (ctrl.element_info.name or "").strip()
            except Exception:
                continue
            if not name or len(name) > 40:
                continue
            if parse_roster_header(name) is None:
                continue
            r = _rect_tuple(ctrl.rectangle())
            if r and r[2] > 0 and r[3] > 0:
                found.append(r)
        if not found:
            return None
        left = min(f[0] for f in found)
        top = min(f[1] for f in found)
        right = max(f[0] + f[2] for f in found)
        bottom = max(f[1] + f[3] for f in found)
        return (left, top, max(0, right - left), max(0, bottom - top))
    except Exception:
        return None


def _ocr_roster_region(region: Optional[Dict[str, Any]]) -> List[str]:
    """OCRs a roster region and returns its text lines.

    The roster panel is drawn INSIDE the CEF canvas, so UIA never exposes its
    headers as controls - the only way to read it is pixels. Region is a
    {"left","top","width","height"} dict in screen coordinates."""
    if not region:
        return []
    try:
        import pytesseract
        import pyautogui
        im = pyautogui.screenshot(region=(
            int(region["left"]), int(region["top"]),
            int(region["width"]), int(region["height"])))
        im = im.resize((im.width * 2, im.height * 2))
        raw = pytesseract.image_to_string(im, config="--psm 6")
        return [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    except Exception:
        return []


def default_roster_region(win, frac: float = 0.76,
                          top_frac: float = 0.12,
                          bottom_frac: float = 0.95) -> Optional[Dict[str, int]]:
    """Derives a default roster region from the room window's own rectangle.

    The panel is docked on the right, below the toolbar and above the status
    strip. This is a starting point, not a calibration - a saved
    `roster_ocr_region` in camfrog_coords.json always wins when present."""
    rect = _rect_tuple(win.rectangle()) if win is not None else None
    if not rect:
        return None
    wl, wt, ww, wh = rect
    left = wl + int(ww * frac)
    width = max(0, (wl + ww) - left - 6)
    height = max(0, int(wh * (bottom_frac - top_frac)))
    if width <= 10 or height <= 10:
        return None
    return {"left": left, "top": wt + int(wh * top_frac),
            "width": width, "height": height}


def read_roster(win, coords: Optional[Dict[str, Any]] = None,
                known_users: Optional[List[str]] = None) -> Dict[str, Any]:
    """Reads the roster panel: UIA first, OCR as the fallback.

    UIA is tried first because it is cheap and exact, but the panel is painted
    into the CEF canvas and exposes no headers at all, so OCR of the right-hand
    region is the path that actually works. A saved `roster_ocr_region` beats
    the derived default.

    COUNTS come straight from the OCR'd headers and are reliable. NAMES are not
    taken from raw OCR (it mangles them) but confirmed against `known_users`, so
    a garbled line can never invent a user.

    A failed read returns reading_ok=False - never an empty-but-confident roster,
    because an empty roster would mark everyone as having left."""
    # --- UIA path -------------------------------------------------------
    rect = find_roster_rect(win)
    if rect:
        left, top, width, height = rect
        lines: List[str] = []
        try:
            for ctrl in win.descendants():
                try:
                    txt = (ctrl.element_info.name or ctrl.window_text() or "").strip()
                except Exception:
                    continue
                if not txt or len(txt) > 40:
                    continue
                r = _rect_tuple(ctrl.rectangle())
                if not r:
                    continue
                if left <= r[0] < left + width and top <= r[1] < top + height:
                    lines.append(txt)
        except Exception:
            lines = []
        if lines:
            out = parse_roster_block(lines)
            out["rect"] = rect
            out["method"] = "uia"
            matched = match_known_users(lines, known_users or [])
            if matched:
                out["users"] = matched
            return out

    # --- OCR path -------------------------------------------------------
    region = None
    if isinstance(coords, dict):
        region = coords.get("roster_ocr_region")
    if not region:
        region = default_roster_region(win)
    lines = _ocr_roster_region(region)
    if not lines:
        return {"counts": {}, "users": [], "reading_ok": False,
                "rect": None, "method": "ocr",
                "reason": "roster unreadable via UIA and OCR"}
    out = parse_roster_block(lines)
    out["rect"] = region
    out["method"] = "ocr"
    # Never trust raw OCR for NAMES; confirm against identities we already know.
    out["users"] = match_known_users(lines, known_users or [])
    return out


