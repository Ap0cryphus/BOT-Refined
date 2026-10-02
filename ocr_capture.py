"""High-rate OCR capture of the Camfrog chat feed.

The CEF/DOM path reads chat text accurately but on a slow cycle and, crucially,
misses the things that matter most: `!` trigger lines and the gray Join/Quit
notices. Those are captured here from pixels instead.

THE CENTRAL PROBLEM IS COST, NOT ACCURACY. OCR at 7 screenshots a second would
be hopeless if every frame were sent to Tesseract - one pass over this region
costs a few hundred ms, so the thread would never keep up the faster it sampled.

So the sampler SCREENS FIRST AND READS SECOND:

    screenshot  ->  hash the pixels  ->  unchanged?  skip OCR entirely

A static screen therefore costs one cheap screenshot and zero OCR. OCR only runs
when the feed actually changed, which is exactly when there is something new to
read. This is also what stops the "static loop" problem: a line sitting on screen
is read once, not seven times a second, because after the first read the pixels
stop changing.

Every line is fingerprinted so a re-render of the same conversation cannot
re-dispatch it. CEF and OCR feed the same dedupe, which is what lets the caller
treat them as two eyes on one scene rather than two sources fighting.

Deliberately separable from the microphone path: this module never touches the
talk button or the speaker bubble.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import deque
from typing import Any, Deque, Dict, Optional

TARGET_FPS = 7.0
MIN_INTERVAL = 1.0 / 12.0        # never faster than 12/s even if asked
MAX_OCR_PER_SEC = 4.0            # hard ceiling on Tesseract invocations
HASH_RESIZE = (250, 95)          # small enough that hashing is sub-millisecond

_USERNAME = r"[A-Za-z0-9_$\-]{2,32}"

# "B3_D33 5:48 AM header", "[10:42 AM] User: msg", or bare "User message"
_PAIR_RE = re.compile(
    rf"^({_USERNAME})\s+(\d{{1,2}}:\d{{2}}(?::\d{{2}})?\s*(?:AM|PM)?)\s+(.*)$")
_COLON_RE = re.compile(
    rf"^(\[\d{{1,2}}:\d{{2}}(?::\d{{2}})?\s*(?:AM|PM)?\]|\d{{1,2}}:\d{{2}}(?::\d{{2}})?\s*(?:AM|PM)?)?\s*"
    rf"({_USERNAME})\s*:\s*(.+)$")
_BARE_RE = re.compile(rf"^({_USERNAME})\s+(.+)$")
_STAMP_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?", re.IGNORECASE)
_SYSTEM_RE = re.compile(r"\(\d{2}/\d{2}I\d{2}:\d{2}:\d{2}\)")

# The bot's own name must never be read back as a user. If it were, the bot
# would read its own replies, treat them as a new participant, and reply again -
# a self-sustaining loop. This is the "static keeps looping" failure in its most
# damaging form, so it is filtered at the parse boundary rather than hoped over
# downstream. Callers may extend the set via BOT_NAMES.
BOT_NAMES = {"kaekae", "kaekae_toad", "kaekae_toad_", "kekae", "kae"}

_NOT_A_USER = {
    "you", "user", "someone", "somebody", "the", "a", "an", "it", "they",
    "him", "her", "admin", "operator", "camfrog", "room", "chat", "system",
    "quit", "join", "left", "enter", "exit", "top", "gifttusers", "users",
}


def _clean_user(raw: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_$\-]", "", (raw or "").strip())
    return name if len(name) >= 2 and name.lower() not in _NOT_A_USER else ""


def is_junk_line(text: str) -> bool:
    """True for panel chrome, clocks, or OCR noise that is not a chat line."""
    raw = (text or "").strip()
    if not raw or len(raw) > 400:
        return True
    compact = raw.replace(" ", "")
    if re.fullmatch(r"\d{1,2}[:.]?\d{2}(AM|PM)?", compact, re.IGNORECASE):
        return True
    if re.fullmatch(r"[^\w]{3,}", raw):          # pure punctuation
        return True
    if not re.search(r"[A-Za-z]{2,}", raw):
        return True
    return raw.lower() in _NOT_A_USER


def parse_feed_line(line: str) -> Optional[Dict[str, str]]:
    """Parses one OCR'd chat line into {user, timestamp, text, kind}.

    `kind` is "chat" or "trigger", so callers know whether a line is a command
    without re-inspecting the text."""
    raw = (line or "").strip()
    if not raw or is_junk_line(raw):
        return None
    # Strip a leading (mm/ddIhh:mm:ss) bot banner so bot lines are not read as users.
    raw = _SYSTEM_RE.sub("", raw).strip()

    user = ts = text = ""
    m = _PAIR_RE.match(raw)
    if m:
        user, ts, text = m.group(1), m.group(2), m.group(3)
    else:
        m = _COLON_RE.match(raw)
        if m:
            ts = (m.group(1) or "").strip("[] ")
            user, text = m.group(2), m.group(3)
        else:
            m = _BARE_RE.match(raw)
            if m:
                user, text = m.group(1), m.group(2)
                found = _STAMP_RE.search(text)
                if found:
                    ts = found.group(0)
                    text = text.replace(found.group(0), "", 1).strip()

    if not _clean_user(user) or not text:
        return None
    clean = _clean_user(user)
    if clean.lower() in BOT_NAMES or clean.lower() in _NOT_A_USER:
        return None
    return {
        "user": clean,
        "timestamp": ts or "",
        "text": text.strip(),
        "kind": "trigger" if text.lstrip().startswith("!") else "chat",
    }


class FeedStats:
    """Rolling counters that make the capture loop observable.

    These exist so "is OCR actually working, and is it keeping up?" is a number
    rather than an impression - the difference between a guess and a diagnosis
    when the bot goes quiet on a busy room. `efficiency` is the headline figure:
    the share of screenshots that actually needed OCR. Low is good, and low with
    a healthy trigger count is exactly the intended steady state.
    """

    def __init__(self):
        self.screenshots = 0
        self.ocr_runs = 0
        self.ocr_skipped_unchanged = 0
        self.ocr_throttled = 0
        self.ocr_errors = 0
        self.lines_parsed = 0
        self.lines_new = 0
        self.triggers_seen = 0
        self.started = time.time()
        self.last_ocr_at = 0.0
        self.last_error = ""
        self.recent_errors: Deque[str] = deque(maxlen=12)
        self._ocr_times: Deque[float] = deque(maxlen=40)

    def allow_ocr(self) -> bool:
        """Rate limiter so a fast-scrolling feed cannot flood Tesseract."""
        now = time.time()
        while self._ocr_times and now - self._ocr_times[0] > 1.0:
            self._ocr_times.popleft()
        if len(self._ocr_times) >= MAX_OCR_PER_SEC:
            self.ocr_throttled += 1
            return False
        self._ocr_times.append(now)
        return True

    def note_error(self, msg: str) -> None:
        self.ocr_errors += 1
        self.last_error = str(msg)[:160]
        self.recent_errors.append(f"{time.strftime('%H:%M:%S')} {self.last_error}")

    def snapshot(self) -> Dict[str, Any]:
        elapsed = max(0.001, time.time() - self.started)
        return {
            "uptime_s": round(elapsed, 1),
            "screenshots": self.screenshots,
            "screenshot_fps": round(self.screenshots / elapsed, 2),
            "ocr_runs": self.ocr_runs,
            "ocr_per_sec": round(self.ocr_runs / elapsed, 2),
            "ocr_skipped_unchanged": self.ocr_skipped_unchanged,
            "ocr_throttled": self.ocr_throttled,
            "ocr_errors": self.ocr_errors,
            "lines_parsed": self.lines_parsed,
            "lines_new": self.lines_new,
            "triggers_seen": self.triggers_seen,
            "efficiency": (round(self.ocr_runs / self.screenshots, 3)
                           if self.screenshots else 0.0),
            "last_error": self.last_error,
        }


def _region_hash(image) -> str:
    """Cheap fingerprint of a screenshot, for change detection."""
    try:
        small = image.convert("L").resize(HASH_RESIZE)
        return hashlib.md5(small.tobytes()).hexdigest()
    except Exception:
        return ""




# ---------------------------------------------------------------------------
# Region derivation and occlusion detection
#
# Hard-coded screen coordinates are a standing liability here. The Camfrog window
# has already moved AND doubled in height once during development (1294x782 ->
# 1294x1399), and a static crop silently slid onto whatever app happened to be
# under it. Regions are therefore derived from the LIVE window rectangle, and
# every sample checks that nothing else is covering the area.
# ---------------------------------------------------------------------------

def camfrog_window_rect():
    """Live (left, top, width, height) of the Camfrog room window, or None."""
    try:
        import kaekae_bot as kb
        win = kb.get_camfrog_window()
        if win is None:
            return None
        r = win.rectangle()
        return (int(r.left), int(r.top), int(r.width()), int(r.height()))
    except Exception:
        return None


def derive_feed_region(rect=None, top_frac: float = 0.12,
                       bottom_frac: float = 0.52,
                       left_frac: float = 0.012,
                       right_frac: float = 0.79) -> Dict[str, int]:
    """Derives the chat-feed crop from the window rectangle.

    Fractions rather than pixels so a resize re-scales the crop instead of
    leaving it pointing at the wrong thing. These were read off a 1294x1399
    window: the feed sits from roughly 12% to 52% of window height, and the
    roster panel and its right-hand edge start around 79% across.
    """
    if rect is None:
        rect = camfrog_window_rect()
    if not rect:
        return {}
    L, T, W, H = rect
    return {
        "left": int(L + W * left_frac),
        "top": int(T + H * top_frac),
        "width": int(W * (right_frac - left_frac)),
        "height": int(H * (bottom_frac - top_frac)),
    }


def occluding_window_name(region: Dict[str, int]) -> str:
    """Returns the title of a window sitting ON TOP of the region, else "".

    A screenshot of a screen region has no idea what is in front of it. Without
    this check any app that steals focus reads as garbled chat and the bot
    cheerfully "parses" a Windows dialog - the failure that produced lines like
    "Players Lounge 45 AM" and "ED omner yos".

    The test is handle identity, not geometry: whichever top-level window is top
    at the region's centre must BE the Camfrog window. A point being
    geometrically inside Camfrog's rectangle proves nothing - a maximized dialog
    sits inside the same rectangle while owning the pixels.
    """
    if not region:
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        cx = int(region["left"] + region["width"] / 2)
        cy = int(region["top"] + region["height"] / 2)
        hwnd = u.WindowFromPoint(wintypes.POINT(cx, cy))
        if not hwnd:
            return ""
        top = u.GetAncestor(hwnd, 2) or hwnd      # GA_ROOT

        def title(h):
            n = u.GetWindowTextLengthW(h)
            if not n:
                return ""
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            return b.value

        # Identify the Camfrog window by handle so "is this Camfrog?" is exact.
        cam_hwnd = None
        try:
            import kaekae_bot as kb
            win = kb.get_camfrog_window()
            cam_hwnd = getattr(win, "handle", None) if win is not None else None
        except Exception:
            cam_hwnd = None
        if cam_hwnd and int(top) == int(cam_hwnd):
            return ""
        name = title(top) or "<unnamed window>"
        if "camfrog" in name.lower() or name.lower().startswith("players__"):
            return ""                              # Camfrog by title, handle unknown
        return name
    except Exception:
        return ""

def ocr_lines(image) -> list:
    """Runs Tesseract over a chat-feed crop and returns cleaned text lines.

    psm 6 is deliberate: the feed is a uniform block of text, which is exactly
    what "treat the image as one uniform block" is for. psm 7 (single line) is
    what the speaker bubble uses and it performs badly over a whole feed."""
    try:
        import pytesseract
    except Exception as e:
        raise RuntimeError(f"pytesseract unavailable: {e}")
    try:
        big = image.resize((image.width * 2, image.height * 2))
        raw = pytesseract.image_to_string(big, config="--psm 6")
    except Exception:
        # Retry unscaled: a large upscale can exceed Tesseract's limits on a big
        # crop, and a noisier read beats losing the feed entirely.
        raw = pytesseract.image_to_string(image, config="--psm 6")
    return [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]


class ChatFeedOCR:
    """Samples the chat feed at TARGET_FPS and OCRs only what changed.

    `on_line` is called once per genuinely new line with the parsed dict. The
    caller decides what to do with it; this class never dispatches anything
    itself, which keeps the mic and chat paths decoupled from OCR timing.
    """

    def __init__(self, region: Dict[str, int], on_line=None,
                 on_join_quit=None, stats: Optional[FeedStats] = None,
                 fps: float = TARGET_FPS, check_occlusion: bool = True):
        self.region = region
        self.check_occlusion = check_occlusion
        self.occluded_by = ""
        self.occluded_since = 0.0
        self.on_line = on_line
        self.on_join_quit = on_join_quit
        self.stats = stats or FeedStats()
        self.fps = fps
        self.interval = max(MIN_INTERVAL, 1.0 / max(0.5, fps))
        self._last_hash = ""
        self._seen: Dict[str, float] = {}
        self._presence = None
        self._running = False
        self.last_lines: list = []

    def is_new(self, user: str, text: str, window_s: float = 900.0) -> bool:
        """True the first time a user+text pair is seen inside the window.

        The window is deliberately long: Camfrog re-renders the whole visible
        history constantly, so a line stays on screen a long time and would
        otherwise be re-dispatched on every scroll.
        """
        sig = line_signature(user, text)
        now = time.time()
        if self._seen.get(sig, 0.0) > now - window_s:
            return False
        self._seen[sig] = now
        if len(self._seen) > 4000:
            cutoff = now - window_s
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
        return True

    def sample_once(self) -> list:
        """One screenshot; OCR only if pixels changed. Returns new lines."""
        self.stats.screenshots += 1
        # Refuse to read a region another app is sitting on. Without this the
        # sampler happily OCRs a Windows dialog and reports its contents as
        # chat lines, which is worse than reading nothing at all.
        if self.check_occlusion:
            blocker = occluding_window_name(self.region)
            if blocker:
                if blocker != self.occluded_by:
                    print(f"[OCR FEED] PAUSED - '{blocker}' is covering the "
                          f"Camfrog chat feed. Not reading.")
                self.occluded_by = blocker
                self.occluded_since = time.time()
                self.stats.ocr_skipped_unchanged += 1
                return []
            if self.occluded_by:
                print("[OCR FEED] RESUMED - chat feed is visible again.")
                self.occluded_by = ""
                self.occluded_since = 0.0
        try:
            import pyautogui
        except Exception as e:
            self.stats.note_error(f"pyautogui unavailable: {e}")
            return []
        try:
            img = pyautogui.screenshot(region=(
                int(self.region["left"]), int(self.region["top"]),
                int(self.region["width"]), int(self.region["height"])))
        except Exception as e:
            self.stats.note_error(f"screenshot failed: {e}")
            return []

        digest = _region_hash(img)
        if digest and digest == self._last_hash:
            # Static screen: one cheap screenshot, no OCR. This is the whole
            # point of the design and the reason 7fps is affordable at all.
            self.stats.ocr_skipped_unchanged += 1
            return []
        self._last_hash = digest
        if not self.stats.allow_ocr():
            return []

        self.stats.ocr_runs += 1
        self.stats.last_ocr_at = time.time()
        try:
            lines = ocr_lines(img)
        except Exception as e:
            self.stats.note_error(f"ocr failed: {e}")
            return []
        self.last_lines = lines

        new_lines = []
        for raw in lines:
            self.stats.lines_parsed += 1
            # Join/Quit gray notices are system lines, not chat; they go to
            # presence recording rather than the message path.
            if self._presence is not None and self.on_join_quit:
                try:
                    jq = self._presence.parse_join_quit(raw)
                except Exception:
                    jq = None
                if jq:
                    try:
                        self.on_join_quit(jq, raw)
                    except Exception as e:
                        self.stats.note_error(f"join_quit handler: {e}")
                    continue

        # The feed is two lines per message, so it is parsed as a sequence.
        for parsed in parse_feed_lines(lines):
            if parsed["kind"] == "trigger":
                self.stats.triggers_seen += 1
            if not self.is_new(parsed["user"], parsed["text"]):
                continue
            self.stats.lines_new += 1
            new_lines.append(parsed)
            if self.on_line:
                try:
                    self.on_line(parsed)
                except Exception as e:
                    self.stats.note_error(f"line handler: {e}")
        return new_lines

    def run_forever(self, stop_event) -> None:
        """Sampling loop. Errors land in stats, never into the caller."""
        self._running = True
        if self._presence is None:
            try:
                import presence as p
                self._presence = p
            except Exception:
                self._presence = None
        while not stop_event.is_set():
            started = time.time()
            try:
                self.sample_once()
            except Exception as e:
                self.stats.note_error(f"loop: {e}")
            delay = self.interval - (time.time() - started)
            if delay > 0:
                stop_event.wait(delay)
        self._running = False



def line_signature(user: str, text: str) -> str:
    """Fingerprint used to stop one conversation being dispatched many times."""
    norm = re.sub(r"\s+", " ", (text or "").lower()).strip()
    return hashlib.sha1(
        f"{(user or '').lower()}|{norm}".encode("utf-8", "ignore")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Two-line message parser
#
# The feed is NOT "User: message" on one line. It renders as:
#
#     [avatar]  OMGitsANGEL                     10:52 AM
#               making me tenge
#
# i.e. a header line (username ... timestamp) followed by the message body. OCR
# also prefixes the header with avatar glyph noise ("-, ", "om ", "Y "), which
# is why the username is located by anchoring to the TRAILING timestamp rather
# than by taking the first token - the first token is the avatar, not the name.
#
# Timestamps OCR inconsistently ("10:52 AM", "10-52 AM", "1052 AD"), so the
# pattern is deliberately tolerant. Anchoring to end-of-line is what keeps a
# message that merely mentions a number from being mistaken for a header.
# ---------------------------------------------------------------------------

# The timestamp must be UNAMBIGUOUS or it eats the username. Allowing a bare
# 3-digit form let "OMGitsANGEL 1052 AM" parse as user="EL", because the engine
# was free to read "2 AM" as the time and leave "105" to the name. So a colon or
# dash is required, except for an explicit bare 4-digit clock.
_TS_CORE = (r"(?:\d{1,2}[:\-]\d{2}|\d{4})\s*[AaPp]?[MmDd]")
_TS_TAIL_RE = re.compile(
    # The username group allows spaces so an OCR'd "Players Lounge1" survives
    # intact and can be repaired against a known spelling; a greedy match takes
    # the whole name rather than just the last token.
    r"^(?:.*?\s)?(?P<user>[A-Za-z0-9_$\-][A-Za-z0-9_$\- ]{1,31})\s+"
    r"(?P<ts>" + _TS_CORE + r")\s*\S{0,3}\s*$")
_TS_TRAIL_RE = re.compile(r"\s*(?:" + _TS_CORE + r")\s*$")
_TS_ANY_RE = re.compile(r"\d{1,2}[:\-]?\d{2}\s*[AaPp]?[MmDd]")

_AVATAR_JUNK_RE = re.compile(r"^[^A-Za-z0-9_$]{0,6}([A-Za-z0-9_$]{1,2})\s+(?=[A-Za-z0-9_$])")


def _normalise_timestamp(ts: str) -> str:
    """Repairs the common OCR manglings of a clock time.

    "10-52 Ah" and "1052 AD" both mean 10:52 AM; the colon is cosmetic and the
    meridiem letters are frequently misread. The digit pair is what carries the
    information, so it is trusted and the meridiem is only used to pick a suffix.
    """
    digits = re.sub(r"\D", "", ts or "")
    if len(digits) >= 3:
        digits = digits[:4].rjust(4, "0")
        return f"{digits[:2]}:{digits[2:]}"
    return (ts or "").strip()


def _loose_key(name: str) -> str:
    """Comparison key that ignores punctuation and case.

    OCR reliably loses the underscore ("Players_Lounge1" -> "Players Lounge1")
    and occasionally drops a digit. Camfrog usernames cannot contain spaces, so
    a space in a parsed name is almost always a lost underscore, not a real
    character."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _edit_close(a: str, b: str, limit: int = 1) -> bool:
    """True when two strings are within `limit` edits (one-pass Levenshtein)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > limit:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return False
        prev = cur
    return prev[-1] <= limit


def _match_known(candidate: str, known_users) -> str:
    """Returns a known spelling only when one genuinely matches, else "".

    Distinguishing "matched a real identity" from "was returned unchanged" is
    essential: every candidate trivially compares equal to itself, so a caller
    that cannot tell the two apart will accept the first thing it tries.
    """
    key = _loose_key(candidate)
    if not key:
        return ""
    exact, close = [], []
    for u in (known_users or []):
        name = str(u or "").strip()
        k = _loose_key(name)
        if not k:
            continue
        if k == key:
            exact.append(name)
        elif abs(len(k) - len(key)) <= 1 and _edit_close(k, key):
            close.append(name)
    pool = exact or close
    if pool and len({_loose_key(p) for p in pool}) == 1:
        return pool[0]
    return ""


def correct_against_known(candidate: str, known_users) -> str:
    """Snaps an OCR'd name onto a spelling already proven in the room.

    Perfecting the regex is the wrong target - OCR is lossy by nature and the
    damage is unbounded ("Players Lounge1" for "Players_Lounge1", "CYBERBABY2"
    for "CYBERBABY12"). Matching loosely against known identities repairs those
    without pretending the pixels were clean, and an unmatched candidate is
    passed through unchanged rather than forced onto some similar name."""
    cand = (candidate or "").strip()
    if not cand:
        return ""
    key = _loose_key(cand)
    if not key:
        return cand
    exact, close = [], []
    for u in (known_users or []):
        name = str(u or "").strip()
        k = _loose_key(name)
        if not k:
            continue
        if k == key:
            exact.append(name)
        elif abs(len(k) - len(key)) <= 1 and _edit_close(k, key):
            close.append(name)
    pool = exact or close
    if pool and len({_loose_key(p) for p in pool}) == 1:
        return pool[0]
    return cand


def parse_header_line(line: str, known_users=None) -> Optional[Dict[str, str]]:
    """Parses "<avatar noise> <Username> <timestamp>" into {user, timestamp}.

    `known_users` is optional but strongly recommended: it is what repairs OCR's
    dropped underscores and digits using spellings already proven in the room."""
    raw = (line or "").strip()
    if not raw or _SYSTEM_RE.search(raw):
        return None
    m = _TS_TAIL_RE.match(raw)
    if not m:
        return None
    user = _clean_user(m.group("user"))
    if not user or user.lower() in BOT_NAMES or user.lower() in _NOT_A_USER:
        return None
    head = m.group("user").strip()
    user = _resolve_user(head, known_users) if known_users else head
    user = _clean_user(user)
    if not user or user.lower() in BOT_NAMES or user.lower() in _NOT_A_USER:
        return None
    return {"user": user, "timestamp": _normalise_timestamp(m.group("ts"))}


def _resolve_user(head: str, known_users) -> str:
    """Picks the real username out of "<avatar glyphs> <Username>".

    The avatar column OCRs to arbitrary 1-3 character junk ("Â©,", "PI", "PF)",
    "Y") that is indistinguishable from a short name by shape alone, so the
    decision is delegated to the known-user list: the longest trailing run of
    tokens that matches a real identity wins. That is why "PI Players Lounge1"
    resolves to "Players_Lounge1" instead of "PI Players Lounge1". Without a
    known list there is no basis to choose, so the last token is taken.
    """
    head = (head or "").strip()
    toks = head.split()
    if not toks:
        return ""
    # Longest trailing run first: it is the only run that can contain the full
    # name, and it is what disambiguates "PI Players Lounge1" from "Lounge1".
    for take in range(min(4, len(toks)), 0, -1):
        cand = " ".join(toks[-take:])
        hit = _match_known(cand, known_users)
        if hit:
            return hit
    return toks[-1]


def parse_message_body(line: str, user: str, timestamp: str) -> Optional[Dict[str, str]]:
    """Turns a body line into a message dict, stripping any trailing timestamp."""
    raw = _SYSTEM_RE.sub("", (line or "").strip()).strip()
    # The avatar column leaks into body lines as leading glyphs ("@ ", "Y ", "-,").
    # Left in place they change the dedupe signature, so the same message is
    # recorded twice under two spellings.
    raw = re.sub(r"^[^A-Za-z0-9_$\-\']{1,3}\s*", "", raw)
    raw = _TS_TRAIL_RE.sub("", raw).strip()
    if not raw or is_junk_line(raw):
        return None
    clean = _clean_user(user)
    if not clean:
        return None
    return {"user": clean, "timestamp": timestamp, "text": raw,
            "kind": "trigger" if raw.lstrip().startswith("!") else "chat"}


def parse_feed_lines(lines, known_users=None) -> List[Dict[str, str]]:
    """Parses a whole OCR'd feed into ordered message dicts.

    Stateful across lines because the layout is two lines per message: a header
    sets the speaker, and the following body line becomes their message. A body
    with no preceding header is attributed to a blank user and dropped rather
    than guessed, because attaching a message to the wrong person corrupts the
    profile store permanently."""
    out: List[Dict[str, str]] = []
    pending_user = ""
    pending_ts = ""
    for raw in (lines or []):
        line = (raw or "").strip()
        if not line or is_junk_line(line):
            continue
        header = parse_header_line(line, known_users)
        if header:
            pending_user = header["user"]
            pending_ts = header["timestamp"]
            continue
        # A body line. If it has a trailing time but no header preceded it, the
        # username was lost - record it without a user rather than invent one.
        if _TS_TAIL_RE.match(line):
            body = _TS_TRAIL_RE.sub("", line).strip()
            if pending_user and body:
                msg = parse_message_body(body, pending_user, pending_ts)
                if msg:
                    out.append(msg)
            continue
        if pending_user:
            msg = parse_message_body(line, pending_user, pending_ts)
            if msg:
                out.append(msg)
            pending_user = ""
            pending_ts = ""
    return out

