#!/usr/bin/env python3
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
    BOT_SETTINGS,
    CHAT_HISTORY_LIMIT,
    DATABASE_PATH,
    DATA_DIR,
    LOG_DIR,
    MAX_CHAT_MESSAGE_LENGTH,
    MODERATION_ALLOWED_SENDERS,
    NATIVE_MODERATION_COMMANDS,
    POLL_INTERVAL_SECONDS,
    SUPPRESSED_DATA_DIR,
)
from ui_automation import CamfrogUIAutomation, clean_username


LOG = logging.getLogger("camfrog_bot")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")
_MOD_RE = re.compile(
    r"^\s*(?P<actor>[A-Za-z0-9_$-]{2,32})\s+(?:was\s+)?"
    r"(?P<action>unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\s+"
    r"(?P<target>[A-Za-z0-9_$-]{2,32})(?:\s+microphone)?\s*[.!]?\s*$",
    re.IGNORECASE,
)
_MOD_BY_RE = re.compile(
    r"^\s*(?P<target>[A-Za-z0-9_$-]{2,32})\s+was\s+"
    r"(?P<action>unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\s+by\s+"
    r"(?P<actor>[A-Za-z0-9_$-]{2,32})\s*[.!]?\s*$",
    re.IGNORECASE,
)
_HISTORY_RE = re.compile(
    r"^who\s+(?P<action>kicked|blocked|unblocked|banned|unbanned|punished|unpunished)"
    r"\s+(?P<target>[A-Za-z0-9_$-]{2,32})\s*\??$",
    re.IGNORECASE,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    """SQLite persistence with a separate, non-queryable suppression vault."""

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
                    active INTEGER NOT NULL DEFAULT 1
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
                    duration_seconds REAL NOT NULL DEFAULT 0
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
                    "INSERT OR REPLACE INTO bot_users(username, first_seen, last_seen, message_count, active) VALUES (?, ?, ?, ?, ?)",
                    (user["username"], user["first_seen"], user["last_seen"], user["message_count"], user["active"]),
                )
            for message in payload.get("messages", []):
                db.execute(
                    "INSERT OR IGNORE INTO bot_messages(event_key, username, body, observed_at, room_time) VALUES (?, ?, ?, ?, ?)",
                    (message["event_key"], message["username"], message["body"], message["observed_at"], message["room_time"]),
                )
            for grab in payload.get("mic_grabs", []):
                db.execute(
                    "INSERT INTO mic_grabs(username, started_at, duration_seconds) VALUES (?, ?, ?)",
                    (grab["username"], grab["started_at"], grab["duration_seconds"]),
                )
            db.execute("DELETE FROM suppressed_users WHERE username = ?", (username,))
        return True

    def record_message(self, username: str, body: str, room_time: str) -> None:
        if self.is_suppressed(username):
            return
        observed_at = now_iso()
        key = message_key(username, body, room_time)
        with self._session() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO bot_messages(event_key, username, body, observed_at, room_time) VALUES (?, ?, ?, ?, ?)",
                (key, username, body, observed_at, room_time),
            ).rowcount
            if inserted:
                db.execute(
                    """INSERT INTO bot_users(username, first_seen, last_seen, message_count, active)
                    VALUES (?, ?, ?, 1, 1)
                    ON CONFLICT(username) DO UPDATE SET last_seen=excluded.last_seen,
                    message_count=bot_users.message_count + 1, active=1""",
                    (username, observed_at, observed_at),
                )

    def record_presence(self, username: str, action: str, event_key: str) -> None:
        if self.is_suppressed(username):
            return
        observed_at = now_iso()
        with self._session() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO presence_events(event_key, username, action, observed_at) VALUES (?, ?, ?, ?)",
                (event_key, username, action, observed_at),
            ).rowcount
            if inserted:
                db.execute(
                    """INSERT INTO bot_users(username, first_seen, last_seen, message_count, active)
                    VALUES (?, ?, ?, 0, ?)
                    ON CONFLICT(username) DO UPDATE SET last_seen=excluded.last_seen, active=excluded.active""",
                    (username, observed_at, observed_at, action == "join"),
                )

    def record_moderation(self, event: dict[str, str], raw_text: str) -> None:
        key = message_key(event["actor"], f"{event['action']}:{event['target']}:{raw_text}")
        with self._session() as db:
            db.execute(
                "INSERT OR IGNORE INTO moderation_events(event_key, actor, target, action, observed_at, raw_text) VALUES (?, ?, ?, ?, ?, ?)",
                (key, event["actor"], event["target"], event["action"], now_iso(), raw_text),
            )

    def record_mic_grab(self, username: str, started_at: str, duration_seconds: float) -> None:
        username = clean_username(username)
        if not username or self.is_suppressed(username):
            return
        with self._session() as db:
            db.execute(
                "INSERT INTO mic_grabs(username, started_at, duration_seconds) VALUES (?, ?, ?)",
                (username, started_at, float(duration_seconds)),
            )

    def user_profile(self, username: str) -> dict[str, object] | None:
        with self._session() as db:
            user = db.execute("SELECT * FROM bot_users WHERE username = ?", (username,)).fetchone()
            if user is None:
                return None
            messages = db.execute("SELECT body FROM bot_messages WHERE username = ? ORDER BY id DESC LIMIT 20", (username,)).fetchall()
            words = Counter(word.casefold() for row in messages for word in _WORD_RE.findall(row["body"]))
            top_word, top_count = words.most_common(1)[0] if words else ("n/a", 0)
            return {**dict(user), "messages": [row["body"] for row in messages], "top_word": top_word, "top_count": top_count}

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
    """Main UIA monitor, active-speaker tracker, VB-Cable TTS broadcaster, and command dispatcher."""

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
        self._current_speaker: str | None = None
        self._speaker_started_iso: str = ""
        self._speaker_started_mono: float = 0.0

    def initialize(self) -> bool:
        if not self.ui_automation.connect_to_camfrog():
            LOG.error("%s", self.ui_automation.last_error)
            return False
        for event in self.ui_automation.get_chat_events():
            self._seen.add(self._event_key(event))
        self.running = True
        self.settings["running"] = True
        LOG.info("Connected to Camfrog via UI Automation.")
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
        """Track real mic grabs strictly from the active speaker next to Talk Button [1291,1169,1361,1195]."""
        speaker = None
        if hasattr(self.ui_automation, "get_active_speaker"):
            speaker = self.ui_automation.get_active_speaker()
        now_mono = time.monotonic()
        if speaker != self._current_speaker:
            if self._current_speaker and self._speaker_started_mono > 0:
                duration = max(0.5, now_mono - self._speaker_started_mono)
                self.store.record_mic_grab(self._current_speaker, self._speaker_started_iso, duration)
            self._current_speaker = speaker
            self._speaker_started_iso = now_iso() if speaker else ""
            self._speaker_started_mono = now_mono if speaker else 0.0

    def poll_once(self) -> int:
        processed = 0
        self._track_active_speaker()
        for event in self.ui_automation.get_chat_events():
            key = self._event_key(event)
            if key in self._seen:
                continue
            self._seen.add(key)
            processed += 1
            if event["kind"] == "presence":
                self.store.record_presence(event["user"], event["action"], key)
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
            return ["Transcription mode is on (strictly gated by active speaker on mic)."]
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
            if hasattr(self.ui_automation, "broadcast_tts_via_vbcable"):
                ok = self.ui_automation.broadcast_tts_via_vbcable(phrase, dry_run=self.dry_run)
                if ok:
                    return [f"Broadcasted via VB-Cable & Talk Button: {phrase[:160]}"]
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
        native = re.match(r"^!(unpunish|unblockmic|unban|topic|watchlist)\s+(.+)$", raw, re.I)
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
        return [f"{profile['username']}: seen since {profile['first_seen']}; {profile['message_count']} messages. Recent chat: {sample_text}"]

    def _info_on(self, username: str) -> list[str]:
        username = clean_username(username)
        profile = self.store.user_profile(username)
        if not profile:
            return [f"No stored statistics for {username or 'that user'}."]
        grabs, seconds = self.store.mic_stats(str(profile["username"]), 24 * 3600)
        return [f"{profile['username']}: {profile['message_count']} messages; top word '{profile['top_word']}' ({profile['top_count']}x); {grabs} mic grabs / {seconds:.0f}s in 24h."]

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
            candidate = f"{current}\n{line}"
            if len(candidate) > MAX_CHAT_MESSAGE_LENGTH and current != title:
                pages.append(current)
                current = f"{title}\n{line}"
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
        print("Camfrog bot running through UI Automation + VB-Cable TTS. Press Ctrl+C to stop.")
        while self.running:
            self.poll_once()
            time.sleep(max(0.1, interval))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Camfrog UI Automation bot (with VB-Cable TTS)")
    parser.add_argument("--dry-run", action="store_true", help="Read/process UIA text but print replies instead of sending them.")
    parser.add_argument("--once", action="store_true", help="Connect and execute one scan.")
    parser.add_argument("--interval", type=float, default=POLL_INTERVAL_SECONDS, help="Polling interval in seconds.")
    parser.add_argument("--locations", action="store_true", help="Print the live UIA-derived locations and exit.")
    args = parser.parse_args(argv)
    bot = CamfrogBot(dry_run=args.dry_run)
    if not bot.initialize():
        print(bot.ui_automation.last_error)
        return 1
    if args.locations:
        print(json.dumps(bot.ui_automation.layout_locations(), indent=2))
        return 0
    if args.once:
        print(f"Processed {bot.poll_once()} new UIA event(s).")
        return 0
    try:
        bot.run(args.interval)
    except KeyboardInterrupt:
        bot.kill_switch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
